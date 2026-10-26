"""Value-only observation adapter for a captured native WRF checkpoint.

Checkpoint state, pressure, surface, and geometry are read from the validated
NativeCheckpoint itself. Static KO observation metadata and the fixed RTTOV
reference are read from the existing case loader inputs. No KDM call, cleanup,
finish map, or derived EOS replacement is performed here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, NamedTuple
import hashlib
import json
from pathlib import Path

import numpy as np
import torch

from harness.native_host_transition import NativeCheckpoint, _checkpoint_header

NX, NY, LEVELS = 234, 282, 39
COLUMNS = NX * NY
CHUNK_COLUMNS = 512
TAIL_COLUMNS = 452
CENTER_FIELDS = (
    "THM_2", "QVAPOR", "QCLOUD", "QICE", "QSNOW", "QNCLOUD", "QNICE",
    "QRAIN", "QGRAUP", "QNCCN", "QNRAIN", "QIB", "P", "PB", "AL",
    "ALB", "RHO",
)
INTERFACE_FIELDS = ("PH_2", "PHB")
SURFACE_FIELDS = (
    "MUB", "MU_2", "TSK", "T2", "Q2", "U10", "V10", "SINALPHA",
    "COSALPHA", "XLAND", "SNOWC", "SEAICE", "HGT", "EMISS", "XLAT", "XLONG",
)
VERTICAL_FIELDS = ("FNM", "FNP")
NUMBER_FIELDS = ("QNCCN", "QNCLOUD", "QNICE", "QNRAIN", "QIB")


class CheckpointNativeProfile(NamedTuple):
    thm_pert: torch.Tensor
    qv: torch.Tensor
    p_center_Pa: torch.Tensor
    phi_interfaces: torch.Tensor


class CheckpointCloudState(NamedTuple):
    """All raw checkpoint mass and number fields; the evaluator reads 5 fields."""
    qc: torch.Tensor
    qi: torch.Tensor
    qs: torch.Tensor
    nc: torch.Tensor
    ni: torch.Tensor
    qr: torch.Tensor
    qg: torch.Tensor
    nccn: torch.Tensor
    nr: torch.Tensor
    bg: torch.Tensor


class NativeCheckpointOutput(NamedTuple):
    """Duck-compatible with native_observation_batch; deliberately no finish field."""
    native_profile: CheckpointNativeProfile
    cloud_state: CheckpointCloudState
    rho_d: torch.Tensor


@dataclass(frozen=True)
class NativeCheckpointObservationBatch:
    block: dict
    output: NativeCheckpointOutput
    provenance: dict


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def original_chunk_bounds(columns: int = COLUMNS, chunk_columns: int = CHUNK_COLUMNS):
    """Original contiguous partition: 128 B512 blocks and one final B452 block."""
    if type(columns) is not int or columns <= 0:
        raise ValueError("columns must be a positive integer")
    if chunk_columns != CHUNK_COLUMNS:
        raise ValueError("checkpoint adapter preserves the original B512 partition")
    return tuple((start, min(start + chunk_columns, columns))
                 for start in range(0, columns, chunk_columns))


def _f32_sum(left, right):
    a, b = np.asarray(left), np.asarray(right)
    if a.dtype != np.float32 or b.dtype != np.float32 or a.shape != b.shape:
        raise TypeError("native source sums require matching float32 operands")
    return np.add(a, b, dtype=np.float32)


def _rho_d_from_al(al, alb):
    """Replay WRF's native REAL4 dry-density assignment: 1./(AL+ALB)."""
    a, b = np.asarray(al), np.asarray(alb)
    if a.dtype != np.float32 or b.dtype != np.float32 or a.shape != b.shape:
        raise TypeError("AL/ALB must be matching float32 inverse-density fields")
    inverse = np.add(a, b, dtype=np.float32)
    if not np.isfinite(inverse).all() or np.any(inverse <= 0.0):
        raise ValueError("AL+ALB must be finite positive inverse dry density")
    rho_d = np.divide(np.float32(1.0), inverse, dtype=np.float32)
    if not np.isfinite(rho_d).all() or np.any(rho_d <= 0.0):
        raise ValueError("checkpoint-derived dry density must be finite positive")
    return rho_d


def _flat_profile(value, flat_indices, *, nx, ny, levels):
    array = np.asarray(value)
    flat = np.asarray(flat_indices)
    if array.dtype != np.float32 or array.shape != (levels, ny, nx):
        raise ValueError(f"profile must be float32[{levels},{ny},{nx}]")
    if flat.ndim != 1 or flat.dtype != np.int32 or np.any(flat < 0) or np.any(flat >= nx * ny):
        raise ValueError("flat_indices must be valid int32 j*nx+i indices")
    return np.ascontiguousarray(array.reshape(levels, nx * ny)[:, flat].T)


def _flat_surface(value, flat_indices, *, nx, ny):
    array = np.asarray(value)
    flat = np.asarray(flat_indices)
    if array.dtype != np.float32 or array.shape != (ny, nx):
        raise ValueError(f"surface must be float32[{ny},{nx}]")
    if flat.ndim != 1 or flat.dtype != np.int32 or np.any(flat < 0) or np.any(flat >= nx * ny):
        raise ValueError("flat_indices must be valid int32 j*nx+i indices")
    return np.ascontiguousarray(array.reshape(nx * ny)[flat])


def _tensor64(value):
    return torch.from_numpy(np.ascontiguousarray(np.asarray(value, dtype=np.float64)))


def checkpoint_output_from_fields(fields, flat_indices, *, nx, ny, levels):
    """Build profile tensors from actual REAL4 checkpoint fields, without prep."""
    flat = np.asarray(flat_indices)
    if flat.dtype != np.int32 or flat.ndim != 1 or not flat.size:
        raise ValueError("flat_indices must be a nonempty int32 vector")
    selected = {
        name: _flat_profile(fields[name], flat, nx=nx, ny=ny, levels=levels)
        for name in CENTER_FIELDS
    }
    ph = _flat_profile(fields["PH_2"], flat, nx=nx, ny=ny, levels=levels + 1)
    phb = _flat_profile(fields["PHB"], flat, nx=nx, ny=ny, levels=levels + 1)
    # The WRF source expressions add in REAL4 and then hand off the fields.
    p_center = _f32_sum(selected["P"], selected["PB"])
    phi = _f32_sum(ph, phb)
    rho_d = _rho_d_from_al(selected["AL"], selected["ALB"])
    native = CheckpointNativeProfile(
        _tensor64(selected["THM_2"]), _tensor64(selected["QVAPOR"]),
        _tensor64(p_center), _tensor64(phi),
    )
    cloud = CheckpointCloudState(
        _tensor64(selected["QCLOUD"]), _tensor64(selected["QICE"]),
        _tensor64(selected["QSNOW"]), _tensor64(selected["QNCLOUD"]),
        _tensor64(selected["QNICE"]), _tensor64(selected["QRAIN"]),
        _tensor64(selected["QGRAUP"]), _tensor64(selected["QNCCN"]),
        _tensor64(selected["QNRAIN"]), _tensor64(selected["QIB"]),
    )
    return NativeCheckpointOutput(native, cloud, _tensor64(rho_d)), selected


def _observation_metadata(case_config):
    from harness.prepare_native_satellite_case import (
        UPPER_REFERENCE_LEVELS, _input_cache, _read_fastem, _surface_profile_rows,
        _validate_input_arrays,
    )
    if (not isinstance(case_config, dict)
            or case_config.get("schema") != "kdm6.native_satellite_case_config.v1"):
        raise TypeError("case_config must come from the existing native case metadata loader")
    if (case_config.get("grid", {}).get("nx"), case_config.get("grid", {}).get("ny"),
            case_config.get("grid", {}).get("levels"), case_config.get("grid", {}).get("columns")) != (NX, NY, LEVELS, COLUMNS):
        raise ValueError("KO observation metadata grid differs from native 5 km grid")
    paths = case_config.get("paths", {})
    observation_path = Path(paths["observations"])
    observation_sha = sha256_file(observation_path)
    if observation_sha != case_config.get("verified_sources", {}).get("observations", {}).get("sha256"):
        raise ValueError("KO observation asset differs from case-config source pin")
    inputs = _input_cache(observation_path)
    _validate_input_arrays(inputs)
    preflight_path = observation_path.parent / "PREFLIGHT.json"
    preflight = json.loads(preflight_path.read_bytes())
    if preflight.get("input_bundle", {}).get("sha256") != observation_sha:
        raise ValueError("preflight does not bind the observation asset")
    ext = preflight.get("native_grid", {}).get("reference_extension_layers_by_cell", {})
    if (ext.get("center_count_values") != {str(UPPER_REFERENCE_LEVELS): COLUMNS}
            or ext.get("interface_count_values") != {str(UPPER_REFERENCE_LEVELS): COLUMNS}):
        raise ValueError("fixed upper-reference extension differs from source preflight")
    reference = {
        "p_lay_hpa": np.asarray(inputs["rttov_reference__p_lay_hPa"], dtype=np.float64).copy(),
        "p_half_hpa": np.asarray(inputs["rttov_reference__p_half_hPa"], dtype=np.float64).copy(),
        "t_k": np.asarray(inputs["rttov_reference__t_K"], dtype=np.float64).copy(),
        "q_ppmv": np.asarray(inputs["rttov_reference__q_ppmv"], dtype=np.float64).copy(),
        "o3_ppmv": np.asarray(inputs["rttov_reference__o3_ppmv"], dtype=np.float64).copy(),
        "co2_ppmv": np.asarray(inputs["rttov_reference__co2_ppmv"], dtype=np.float64).copy(),
        "fixed_upper_count": UPPER_REFERENCE_LEVELS,
    }
    return inputs, reference, _read_fastem(paths["template"]), observation_sha, _surface_profile_rows


def _read_checkpoint_fields(checkpoint: NativeCheckpoint):
    import netCDF4
    if not isinstance(checkpoint, NativeCheckpoint):
        raise TypeError("checkpoint must be a value-validated NativeCheckpoint")
    if checkpoint._validated_sha256 != checkpoint.file.sha256:
        raise ValueError("checkpoint is missing NativeCheckpoint.capture validation")
    checkpoint.file.verify()
    groups = {"center": CENTER_FIELDS, "interface": INTERFACE_FIELDS,
              "surface": SURFACE_FIELDS, "vertical": VERTICAL_FIELDS}
    fields, units = {}, {}
    with netCDF4.Dataset(checkpoint.file.path, "r") as dataset:
        dataset.set_auto_maskandscale(False)
        stamp, step, schema = _checkpoint_header(dataset)
        if (stamp, step, schema) != (checkpoint.time, checkpoint.itimestep, checkpoint.schema):
            raise ValueError("checkpoint header/schema changed after validation")
        if int(getattr(dataset, "MP_PHYSICS", -1)) != 137 or int(getattr(dataset, "USE_THETA_M", -1)) != 1:
            raise ValueError("checkpoint is not the MP137/use_theta_m=1 case")
        dimensions = {"west_east": NX, "south_north": NY,
                      "bottom_top": LEVELS, "bottom_top_stag": LEVELS + 1}
        if any(name not in dataset.dimensions or len(dataset.dimensions[name]) != size
               for name, size in dimensions.items()):
            raise ValueError("checkpoint dimensions differ from native 282x234x39 layout")
        for group, names in groups.items():
            for name in names:
                if name not in dataset.variables:
                    raise ValueError(f"checkpoint is missing actual field {name}")
                var = dataset.variables[name]
                expected_dims = (("Time", "bottom_top_stag", "south_north", "west_east") if group == "interface" else
                                 ("Time", "bottom_top", "south_north", "west_east") if group == "center" else
                                 ("Time", "bottom_top") if group == "vertical" else
                                 ("Time", "south_north", "west_east"))
                if tuple(var.dimensions) != expected_dims or np.dtype(var.dtype) != np.dtype(np.float32):
                    raise ValueError(f"{name} must be float32 with dimensions {expected_dims}")
                if any(key in var.ncattrs() for key in ("scale_factor", "add_offset")):
                    raise ValueError(f"packed native checkpoint field {name} is unsupported")
                units[name] = str(getattr(var, "units", "unspecified"))
                value = np.asarray(var[0], dtype=np.float32).copy()
                if not np.isfinite(value).all():
                    raise ValueError(f"checkpoint field {name} is nonfinite")
                fields[name] = value
    checkpoint.file.verify()
    # These unit attributes distinguish mass pressure/geopotential/density inputs.
    required_units = {"P": "pa", "PB": "pa", "PH_2": "m2 s-2", "PHB": "m2 s-2",
                      "AL": "m3 kg-1", "ALB": "m3 kg-1", "RHO": "kg m-3"}
    for name, expected in required_units.items():
        if units[name].strip().lower() != expected:
            raise ValueError(f"checkpoint {name} units {units[name]!r} differ from {expected!r}")
    return fields, units


def _build_surface_block(fields, flat, inputs, fastem, surface_profile_rows):
    surface = {name: _flat_surface(fields[name], flat, nx=NX, ny=NY) for name in SURFACE_FIELDS}
    # Native grid coordinates must stay aligned with the pinned KO navigation.
    for actual, source in (("XLAT", "model_lat"), ("XLONG", "model_lon")):
        expected = np.asarray(inputs[source], dtype=np.float32).reshape(-1)[flat]
        if not np.array_equal(surface[actual].view(np.uint32), expected.view(np.uint32)):
            raise ValueError(f"checkpoint {actual} differs from static observation grid")
    native_surface = {
        "xland": surface["XLAND"].astype(np.float64), "hgt_m": surface["HGT"].astype(np.float64),
        "tsk_K": surface["TSK"].astype(np.float64), "t2_K": surface["T2"].astype(np.float64),
        "q2_kgkg_dry": surface["Q2"].astype(np.float64), "u10_m_s": surface["U10"].astype(np.float64),
        "v10_m_s": surface["V10"].astype(np.float64), "sinalpha": surface["SINALPHA"].astype(np.float64),
        "cosalpha": surface["COSALPHA"].astype(np.float64), "snow_fraction": surface["SNOWC"].astype(np.float64),
        "seaice_fraction": surface["SEAICE"].astype(np.float64), "emissivity_raw": surface["EMISS"].astype(np.float64),
        "model_lat_deg": surface["XLAT"].astype(np.float64), "model_lon_deg": surface["XLONG"].astype(np.float64),
    }
    surfaces = surface_profile_rows(native_surface, fastem=fastem)
    rttov_geometry = {
        name: np.asarray(inputs[source]).reshape(-1)[flat].astype(np.float64)
        for name, source in (("zenangle", "ami_geometry_zenangle_deg"),
                             ("azangle", "ami_geometry_azangle_deg"),
                             ("sunzenangle", "ami_geometry_sunzenangle_deg"),
                             ("sunazangle", "ami_geometry_sunazangle_deg"))
    }
    rttov_geometry.update({
        "latitude": native_surface["model_lat_deg"],
        "longitude": native_surface["model_lon_deg"],
        "elevation": native_surface["hgt_m"] / 1000.0,
    })
    return native_surface, surfaces, rttov_geometry


def iter_native_checkpoint_batches(checkpoint: NativeCheckpoint, case_config: dict) -> Iterator[NativeCheckpointObservationBatch]:
    """Yield current checkpoint profiles in the original 128xB512+tail452 schedule.

    Observation metadata and upper reference remain from the pinned KO case;
    every prognostic/surface/geometry profile value in each yielded block is
    read from this `NativeCheckpoint`. Packet state arrays are never consulted.
    """
    inputs, reference, fastem, observation_sha, surface_profile_rows = _observation_metadata(case_config)
    fields, units = _read_checkpoint_fields(checkpoint)
    rho_all = _rho_d_from_al(fields["AL"], fields["ALB"])
    saved_rho = fields["RHO"]
    rho_match = rho_all.view(np.uint32) == saved_rho.view(np.uint32)
    edge = np.zeros((NY, NX), dtype=np.bool_)
    edge[[0, -1], :] = True
    edge[:, [0, -1]] = True
    edge3 = np.broadcast_to(edge, rho_match.shape)
    density_record = {
        "source_expression": "REAL4(1.0) / REAL4(AL + ALB)",
        "source_units": {"AL": units["AL"], "ALB": units["ALB"]},
        "rho_d_units": "kg dry air m-3",
        "saved_RHO_units": units["RHO"],
        "saved_RHO_bit_matches": int(np.count_nonzero(rho_match)),
        "saved_RHO_total_values": int(rho_match.size),
        "saved_RHO_interior_mismatches": int(np.count_nonzero((~rho_match) & (~edge3))),
        "saved_RHO_edge_ring_mismatches": int(np.count_nonzero((~rho_match) & edge3)),
        "saved_RHO_max_abs_difference": float(np.max(np.abs(rho_all - saved_rho))),
        "selected_density_source": "AL/ALB-derived native dry density for all columns; saved RHO is an audit comparison only",
    }
    if not np.array_equal(fields["XLAND"].astype(np.float32), fields["XLAND"]):
        raise ValueError("checkpoint XLAND must remain REAL4")
    for chunk_index, (start, stop) in enumerate(original_chunk_bounds()):
        flat = np.arange(start, stop, dtype=np.int32)
        output, selected = checkpoint_output_from_fields(fields, flat, nx=NX, ny=NY, levels=LEVELS)
        native_surface, surfaces, rttov_geometry = _build_surface_block(
            fields, flat, inputs, fastem, surface_profile_rows
        )
        obs_qc_raw = np.asarray(inputs["obs_qc"][flat]).copy()
        obs_qc_codes = obs_qc_raw.astype(np.int32)
        if not np.array_equal(obs_qc_raw, obs_qc_codes.astype(np.float64)):
            raise ValueError("observation QC metadata is not exactly integer-valued")
        negative_nc = np.any(selected["QNCLOUD"] < 0.0, axis=1)
        negative_ni = np.any(selected["QNICE"] < 0.0, axis=1)
        reasons = ["+".join(name for flag, name in ((negative_nc[r], "negative_NC"),
                                                    (negative_ni[r], "negative_NI")) if flag) or "eligible"
                   for r in range(flat.size)]
        source_valid = ((np.asarray(inputs["obs_dqf"][flat]) == 0) & (obs_qc_codes == 0))
        block = {
            "B": int(flat.size), "L": LEVELS, "chunk_index": chunk_index,
            "start_flat": start, "stop_flat_exclusive": stop,
            "flat_indices": flat, "i": (flat % NX).astype(np.int32), "j": (flat // NX).astype(np.int32),
            "obs_bt": np.asarray(inputs["obs_bt"][flat], dtype=np.float64).copy(),
            "obs_dqf": np.asarray(inputs["obs_dqf"][flat]).copy(),
            "obs_qc_raw": obs_qc_raw, "obs_qc_codes": obs_qc_codes,
            "obs_source_valid": source_valid,
            "initial_admission": {
                "cost_eligible": ~(negative_nc | negative_ni),
                "negative_nc": negative_nc, "negative_ni": negative_ni, "reasons": reasons,
            },
            "xland": native_surface["xland"], "native_surface": native_surface,
            "surface_profiles": surfaces, "rttov_geometry": rttov_geometry,
            "fnm": np.asarray(fields["FNM"], dtype=np.float64).copy(),
            "fnp": np.asarray(fields["FNP"], dtype=np.float64).copy(),
            "reference": reference,
        }
        provenance = {
            "schema": "kdm6.native_checkpoint_observation_batch.v1",
            "checkpoint_sha256": checkpoint.file.sha256,
            "checkpoint_time": checkpoint.time, "checkpoint_itimestep": checkpoint.itimestep,
            "checkpoint_path": str(checkpoint.file.path),
            "observation_asset_sha256": observation_sha,
            "grid": {"nx": NX, "ny": NY, "levels": LEVELS, "columns": COLUMNS},
            "flat_range": [start, stop], "columns": int(flat.size),
            "state_sources": {"thm_pert": "THM_2", "qv": "QVAPOR", "qc": "QCLOUD",
                               "qi": "QICE", "qs": "QSNOW", "nc": "QNCLOUD", "ni": "QNICE",
                               "qr": "QRAIN", "qg": "QGRAUP", "nccn": "QNCCN", "nr": "QNRAIN", "bg": "QIB"},
            "raw_number_units_from_checkpoint": {name: units[name] for name in NUMBER_FIELDS},
            "raw_number_unit_certification": False,
            "center_pressure": "REAL4 P+PB, widened after source-ordered addition; Pa",
            "full_interface_geopotential": "REAL4 PH_2+PHB, widened after source-ordered addition; m2 s-2",
            "physical_temperature": "Existing native profile EOS reconstruction from actual THM_2, QVAPOR and P+PB; no old T or ideal-volume substitution",
            "interface_pressure": "Checkpoint has no saved P8W field. Existing P8W contract derives native interfaces from actual P+PB centers, PH_2+PHB geopotential and actual FNM/FNP; source REAL4 fields are widened then the profile-builder formula runs in float64. P_HYD is not substituted; matching unavailable checkpoint REAL4 P8W bits is unmeasured.",
            "dry_density_audit": density_record,
            "surface_source_fields": list(SURFACE_FIELDS),
            "extra_kdm_cleanup_finish_calls": 0,
        }
        yield NativeCheckpointObservationBatch(block, output, provenance)
    checkpoint.file.verify()


def evaluate_checkpoint_observation_batch(batch: NativeCheckpointObservationBatch, case_config: dict, workspace, *, with_k=True):
    """Delegate an already-built checkpoint batch to the unchanged evaluator.

    This function is the only adapter entry point that can launch RTTOV, and it
    does so only when an execution caller explicitly invokes it.
    """
    from harness.native_observation_batch import evaluate_observation_batch
    if not isinstance(batch, NativeCheckpointObservationBatch):
        raise TypeError("batch must be created by iter_native_checkpoint_batches")
    return evaluate_observation_batch(batch.block, batch.output, case_config, workspace, with_k=with_k)
