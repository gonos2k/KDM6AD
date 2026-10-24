"""Prepare source-pinned native SAT/MP137 B512 blocks; never execute KDM/RTTOV."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np


SCHEMA = "kdm6.native_satellite_case_block.v1"
NX, NY, LEVELS = 234, 282, 39
N_COLUMNS = NX * NY
CHUNK_COLUMNS = 512
CHANNELS = (10, 11, 12, 13, 14, 15, 16)
STATE_FIELDS = ("TH", "Q", "QC", "QR", "QI", "QS", "QG", "NN", "NC", "NI", "NR", "BG")
FORCING_FIELDS = ("DEN", "PII", "P", "DELZ")
UPPER_REFERENCE_LEVELS = 27
MASS_AIR_KG_MOL = 28.9647e-3
WATER_VAPOR_KG_MOL = 18.01528e-3
NATIVE_TIME = "2025-07-19_00:00:40"
NATIVE_STEP = 2
_CACHE: dict[str, dict] = {}
_TIME_ATTRS = (
    "scene_acquisition_time",
    "mission_reference_time",
    "observation_start_time",
    "observation_end_time",
    "time_synchro_obt",
    "time_synchro_utc",
)


class CasePreparationError(ValueError):
    """Invalid pinned case data or block."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for data in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(data)
    return digest.hexdigest()


def _physical_experiment(archived):
    """Keep only physical map settings; prior single-target fields are historical."""
    required = (
        "factorial_mode",
        "qr_transport",
        "batch_columns",
        "levels",
        "dt_seconds",
        "ncmin_land",
        "ncmin_sea",
    )
    if not isinstance(archived, dict) or any(name not in archived for name in required):
        raise CasePreparationError(
            "archived candidate experiment lacks physical map fields"
        )
    if (
        archived["factorial_mode"] != "norm_actual"
        or archived["qr_transport"] != "actual_departure"
        or archived["batch_columns"] != CHUNK_COLUMNS
        or archived["levels"] != LEVELS
        or archived["dt_seconds"] != 20.0
        or any(
            isinstance(archived[name], bool) or not np.isfinite(float(archived[name]))
            for name in ("ncmin_land", "ncmin_sea")
        )
    ):
        raise CasePreparationError(
            "case must match norm_actual/actual_departure B512/L39 dt=20"
        )
    return {
        "schema": "kdm6.native_satellite_case_physics.v1",
        **{name: archived[name] for name in required},
    }


def _finite(value, name, *, shape=None, dtype=np.float64):
    array = np.asarray(value)
    if array.dtype.kind not in "fiu" or array.dtype.kind == "b":
        raise CasePreparationError(f"{name} must be real numeric data")
    array = np.asarray(array, dtype=dtype)
    if shape is not None and array.shape != shape:
        raise CasePreparationError(f"{name} shape {array.shape} differs from {shape}")
    if not np.isfinite(array).all():
        raise CasePreparationError(f"{name} contains non-finite values")
    return array


def validate_packet_manifest(manifest, *, nx=NX, ny=NY, chunk_columns=CHUNK_COLUMNS):
    columns = nx * ny
    if manifest.get("schema") != "kdm6.ice_factorial_endpoint_preparation.v2":
        raise CasePreparationError("unexpected endpoint packet schema")
    if manifest.get("chunk_columns") != chunk_columns:
        raise CasePreparationError("endpoint packet is not fixed B512")
    coverage = manifest.get("coverage", {})
    if (
        coverage.get("columns_expected") != columns
        or coverage.get("columns_written") != columns
        or coverage.get("missing") != 0
        or coverage.get("duplicate") != 0
        or coverage.get("included_edges") is not True
    ):
        raise CasePreparationError(
            "packet manifest does not certify complete edge-inclusive coverage"
        )
    mapping = manifest.get("mapping", {})
    if (
        mapping.get("state_order") != list(STATE_FIELDS)
        or mapping.get("forcing_order") != list(FORCING_FIELDS)
        or mapping.get("mu_total")
        != "float32(MUB + MU_2), native addition before widening"
    ):
        raise CasePreparationError(
            "packet state/forcing/MU mapping differs from captured contract"
        )
    chunks = manifest.get("chunks")
    if not isinstance(chunks, list) or len(chunks) != math.ceil(
        columns / chunk_columns
    ):
        raise CasePreparationError(
            "packet must contain the full contiguous chunk inventory"
        )
    for index, entry in enumerate(chunks):
        start = index * chunk_columns
        stop = min(start + chunk_columns, columns)
        if (
            entry.get("start_flat") != start
            or entry.get("stop_flat_exclusive") != stop
            or entry.get("columns") != stop - start
            or entry.get("path") != f"chunk_{start:05d}_{stop:05d}.npz"
            or entry.get("bytes", 0) <= 0
            or not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("sha256", "")))
        ):
            raise CasePreparationError(
                f"manifest chunk {index} range/hash/size invalid"
            )
    if (
        nx == NX
        and ny == NY
        and chunk_columns == CHUNK_COLUMNS
        and chunks[-1]["columns"] != 452
    ):
        raise CasePreparationError("native packet final chunk must contain 452 columns")
    return chunks


def verify_packet_chunks(
    packet_root: Path,
    manifest,
    *,
    nx=NX,
    ny=NY,
    levels=LEVELS,
    chunk_columns=CHUNK_COLUMNS,
):
    """Hash and inspect every payload without padding or mutating source arrays."""
    packet_root = Path(packet_root).resolve()
    chunks = validate_packet_manifest(
        manifest, nx=nx, ny=ny, chunk_columns=chunk_columns
    )
    columns = nx * ny
    seen = np.zeros(columns, dtype=bool)
    negative_raw = {name: 0 for name in STATE_FIELDS}
    negative_condensate = {name: 0 for name in ("QC", "QG", "QI", "QR", "QS")}
    for index, entry in enumerate(chunks):
        path = (packet_root / entry["path"]).resolve()
        if packet_root not in path.parents or not path.is_file():
            raise CasePreparationError(
                f"packet chunk {index} is missing or escapes packet directory"
            )
        if (
            path.stat().st_size != entry["bytes"]
            or sha256_file(path) != entry["sha256"]
        ):
            raise CasePreparationError(
                f"packet chunk {index} differs from its manifest SHA/size"
            )
        with np.load(path, allow_pickle=False) as archive:
            if set(archive.files) != {
                "state",
                "forcing",
                "xland",
                "flat_indices",
                "i",
                "j",
            }:
                raise CasePreparationError(
                    f"packet chunk {index} keys differ from endpoint schema"
                )
            state = np.asarray(archive["state"])
            forcing = np.asarray(archive["forcing"])
            xland = np.asarray(archive["xland"])
            flat = np.asarray(archive["flat_indices"])
            ii, jj = np.asarray(archive["i"]), np.asarray(archive["j"])
            start, stop, count = (
                entry["start_flat"],
                entry["stop_flat_exclusive"],
                entry["columns"],
            )
            expected = np.arange(start, stop, dtype=np.int32)
            if (
                state.dtype != np.float64
                or state.shape != (12, count, levels)
                or forcing.dtype != np.float64
                or forcing.shape != (4, count, levels)
                or xland.dtype != np.float64
                or xland.shape != (count,)
                or flat.dtype != np.int32
                or flat.shape != (count,)
                or ii.dtype != np.int32
                or ii.shape != (count,)
                or jj.dtype != np.int32
                or jj.shape != (count,)
                or not np.array_equal(flat, expected)
                or not np.array_equal(ii, expected % nx)
                or not np.array_equal(jj, expected // nx)
                or seen[start:stop].any()
                or not np.isfinite(state).all()
                or not np.isfinite(forcing).all()
                or not np.isfinite(xland).all()
                or not np.isin(xland, (1.0, 2.0)).all()
                or not (forcing > 0.0).all()
            ):
                raise CasePreparationError(
                    f"packet chunk {index} has padded, duplicate, nonfinite, or misordered data"
                )
            seen[start:stop] = True
            for row, name in enumerate(STATE_FIELDS):
                negative_raw[name] += int(np.count_nonzero(state[row] < 0.0))
            for name in negative_condensate:
                row = STATE_FIELDS.index(name)
                negative_condensate[name] += int(np.count_nonzero(state[row] < 0.0))
    if not seen.all():
        raise CasePreparationError(
            f"packet payload files cover only {int(seen.sum())}/{columns} flat indices"
        )
    coverage = manifest["coverage"]
    if coverage.get("negative_raw_state_values_by_field") != negative_raw:
        raise CasePreparationError(
            "packet raw negative-value counts differ from manifest"
        )
    if coverage.get("negative_condensate_values_preserved") != negative_condensate:
        raise CasePreparationError(
            "packet negative-condensate preservation counts differ from manifest"
        )
    return {
        "chunks_hashed_and_checked": len(chunks),
        "columns_checked": columns,
        "missing": 0,
        "duplicate": 0,
        "padded_rows": 0,
        "negative_raw_state_values_by_field": negative_raw,
        "negative_condensate_values_preserved": negative_condensate,
    }


def _raw16_inventory(root: Path):
    """Record all local raw 16-channel KO files; pixel payloads are not loaded."""
    import netCDF4

    pattern = re.compile(r"gk2a_ami_le1b_([a-z0-9]+)_ko[0-9]+lc_202507190000\.nc\Z")
    files = sorted(root.glob("*_ko*lc_202507190000.nc"))
    if len(files) != 16:
        raise CasePreparationError(f"expected 16 raw KO slot files, found {len(files)}")
    result, seen = [], set()
    for path in files:
        match = pattern.fullmatch(path.name)
        if match is None or match.group(1) in seen:
            raise CasePreparationError(
                f"invalid or duplicate raw KO channel file {path.name}"
            )
        seen.add(match.group(1))
        with netCDF4.Dataset(path, "r") as dataset:
            if "image_pixel_values" not in dataset.variables:
                raise CasePreparationError(f"{path.name} lacks image_pixel_values")
            variable = dataset.variables["image_pixel_values"]
            if len(variable.shape) != 2 or min(variable.shape) <= 0:
                raise CasePreparationError(
                    f"{path.name} image_pixel_values is not a nonempty 2-D raster"
                )
            declared_width = (
                dataset.getncattr("image_width")
                if "image_width" in dataset.ncattrs()
                else variable.shape[1]
            )
            declared_height = (
                dataset.getncattr("image_height")
                if "image_height" in dataset.ncattrs()
                else variable.shape[0]
            )
            if (int(declared_height), int(declared_width)) != tuple(variable.shape):
                raise CasePreparationError(
                    f"{path.name} raster dimensions disagree with image attributes"
                )
            time_attrs = {
                name: str(dataset.getncattr(name))
                for name in _TIME_ATTRS
                if name in dataset.ncattrs()
            }
            valid_bits = (
                variable.getncattr("number_of_valid_bits_per_pixel")
                if "number_of_valid_bits_per_pixel" in variable.ncattrs()
                else None
            )
            projection = (
                str(dataset.getncattr("projection_type"))
                if "projection_type" in dataset.ncattrs()
                else None
            )
            pixel_size = (
                float(dataset.getncattr("pixel_size"))
                if "pixel_size" in dataset.ncattrs()
                else None
            )
            stored_dtype = str(variable.dtype)
        result.append(
            {
                "channel": match.group(1),
                "path": str(path.resolve()),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
                "pixel_shape": [int(declared_height), int(declared_width)],
                "stored_dtype": stored_dtype,
                "valid_bits": None if valid_bits is None else int(valid_bits),
                "pixel_size": pixel_size,
                "projection_type": projection,
                "time_attributes": time_attrs,
            }
        )
    return result


def _checkpoint_cache(path: Path):
    import netCDF4

    sha = sha256_file(path)
    arrays = {}
    mass_dims = ("Time", "bottom_top", "south_north", "west_east")
    interface_dims = ("Time", "bottom_top_stag", "south_north", "west_east")
    surface_dims = ("Time", "south_north", "west_east")
    with netCDF4.Dataset(path, "r") as dataset:
        dataset.set_auto_maskandscale(False)
        for name, size in (
            ("west_east", NX),
            ("south_north", NY),
            ("bottom_top", LEVELS),
            ("bottom_top_stag", LEVELS + 1),
        ):
            if name not in dataset.dimensions or len(dataset.dimensions[name]) != size:
                raise CasePreparationError(f"checkpoint {name} dimension differs")
        if "Time" not in dataset.dimensions or len(dataset.dimensions["Time"]) != 1:
            raise CasePreparationError("checkpoint must contain one Time record")
        times = dataset.variables.get("Times")
        if times is None:
            raise CasePreparationError("checkpoint lacks Times")
        stamp = b"".join(np.asarray(times[0]).tolist()).decode("ascii").strip("\x00 ")
        if stamp != NATIVE_TIME:
            raise CasePreparationError(
                f"checkpoint time {stamp!r} differs from {NATIVE_TIME}"
            )
        timestep = dataset.variables.get("ITIMESTEP")
        if (
            timestep is None
            or int(np.asarray(timestep[:]).reshape(-1)[0]) != NATIVE_STEP
        ):
            raise CasePreparationError(
                "checkpoint ITIMESTEP differs from endpoint step 2"
            )
        if (
            int(getattr(dataset, "MP_PHYSICS", -1)) != 137
            or int(getattr(dataset, "USE_THETA_M", -1)) != 1
        ):
            raise CasePreparationError(
                "checkpoint is not the bound MP137/use_theta_m=1 case"
            )
        mass_fields = ("THM_2", "QVAPOR")
        interface_fields = ("PH_2", "PHB")
        surface_fields = (
            "MUB",
            "MU_2",
            "TSK",
            "T2",
            "Q2",
            "U10",
            "V10",
            "SINALPHA",
            "COSALPHA",
            "XLAND",
            "SNOWC",
            "SEAICE",
            "HGT",
            "EMISS",
            "XLAT",
            "XLONG",
        )
        coefficient_fields = {
            "C3H": ("bottom_top", LEVELS),
            "C4H": ("bottom_top", LEVELS),
            "C3F": ("bottom_top_stag", LEVELS + 1),
            "C4F": ("bottom_top_stag", LEVELS + 1),
            "FNM": ("bottom_top", LEVELS),
            "FNP": ("bottom_top", LEVELS),
        }
        for name in mass_fields:
            var = dataset.variables.get(name)
            if (
                var is None
                or tuple(var.dimensions) != mass_dims
                or np.dtype(var.dtype) != np.dtype(np.float32)
            ):
                raise CasePreparationError(f"{name} must be REAL4 [Time,K,j,i]")
            arrays[name] = np.asarray(var[0], dtype=np.float32).copy()
        for name in interface_fields:
            var = dataset.variables.get(name)
            if (
                var is None
                or tuple(var.dimensions) != interface_dims
                or np.dtype(var.dtype) != np.dtype(np.float32)
            ):
                raise CasePreparationError(f"{name} must be REAL4 [Time,K+1,j,i]")
            arrays[name] = np.asarray(var[0], dtype=np.float32).copy()
        for name in surface_fields:
            var = dataset.variables.get(name)
            if (
                var is None
                or tuple(var.dimensions) != surface_dims
                or np.dtype(var.dtype) != np.dtype(np.float32)
            ):
                raise CasePreparationError(f"{name} must be REAL4 [Time,j,i]")
            arrays[name] = np.asarray(var[0], dtype=np.float32).copy()
        for name, (dimension, size) in coefficient_fields.items():
            var = dataset.variables.get(name)
            if (
                var is None
                or tuple(var.dimensions) != ("Time", dimension)
                or np.dtype(var.dtype) != np.dtype(np.float32)
            ):
                raise CasePreparationError(f"{name} must be REAL4 [Time,{dimension}]")
            value = np.asarray(var[0], dtype=np.float32).reshape(-1)
            if value.shape != (size,):
                raise CasePreparationError(
                    f"{name} coefficient length differs from {size}"
                )
            arrays[name] = value.copy()
        if any(not np.isfinite(value).all() for value in arrays.values()):
            raise CasePreparationError("checkpoint contains non-finite native fields")
    return sha, arrays


def _input_cache(path: Path):
    required = (
        "obs_bt",
        "obs_dqf",
        "obs_qc",
        "model_lat",
        "model_lon",
        "native_flat_index",
        "ko_nearest_row",
        "ko_nearest_col",
        "ko_nearest_flat_index",
        "ko_distance_m",
        "ko_nearest_lat_deg",
        "ko_nearest_lon_deg",
        "ami_geometry_zenangle_deg",
        "ami_geometry_azangle_deg",
        "ami_geometry_sunzenangle_deg",
        "ami_geometry_sunazangle_deg",
        "ami_geometry_lat_deg",
        "ami_geometry_lon_deg",
        "ami_geometry_elevation_km",
        "ko_channel_ids_1based",
        "ko_channel_names",
        "rttov_reference__p_lay_hPa",
        "rttov_reference__p_half_hPa",
        "rttov_reference__t_K",
        "rttov_reference__q_ppmv",
        "rttov_reference__o3_ppmv",
        "rttov_reference__co2_ppmv",
    )
    arrays = {}
    with np.load(path, allow_pickle=False) as archive:
        missing = sorted(set(required) - set(archive.files))
        if missing:
            raise CasePreparationError(
                f"KO input bundle missing required arrays {missing}"
            )
        for name in required:
            arrays[name] = np.asarray(archive[name]).copy()
    return arrays


def _validate_input_arrays(arrays):
    for name in (
        "model_lat",
        "model_lon",
        "native_flat_index",
        "ko_nearest_row",
        "ko_nearest_col",
        "ko_nearest_flat_index",
        "ko_distance_m",
        "ko_nearest_lat_deg",
        "ko_nearest_lon_deg",
        "ami_geometry_zenangle_deg",
        "ami_geometry_azangle_deg",
        "ami_geometry_sunzenangle_deg",
        "ami_geometry_sunazangle_deg",
        "ami_geometry_lat_deg",
        "ami_geometry_lon_deg",
        "ami_geometry_elevation_km",
    ):
        if arrays[name].shape != (NY, NX):
            raise CasePreparationError(f"{name} must have shape {(NY, NX)}")
        if arrays[name].dtype.kind in "fi" and not np.isfinite(arrays[name]).all():
            raise CasePreparationError(f"{name} contains non-finite values")
    if not np.array_equal(
        arrays["native_flat_index"].reshape(-1), np.arange(N_COLUMNS, dtype=np.int32)
    ):
        raise CasePreparationError("native map is not C-order j*nx+i")
    pixel_flat = arrays["ko_nearest_flat_index"].reshape(-1).astype(np.int64)
    if (
        pixel_flat.size != N_COLUMNS
        or (pixel_flat < 0).any()
        or (pixel_flat >= 900 * 900).any()
    ):
        raise CasePreparationError(
            "KO nearest pixel indices are outside the 900×900 raster"
        )
    if int(np.unique(pixel_flat).size) != N_COLUMNS:
        raise CasePreparationError(
            "native-to-KO mapping is not one-pixel-per-native-column"
        )
    if not np.array_equal(
        pixel_flat,
        arrays["ko_nearest_row"].reshape(-1).astype(np.int64) * 900
        + arrays["ko_nearest_col"].reshape(-1).astype(np.int64),
    ):
        raise CasePreparationError("KO pixel row/column and flat-index map differ")
    obs_shape = (N_COLUMNS, 7)
    for name in ("obs_bt", "obs_dqf", "obs_qc"):
        if arrays[name].shape != obs_shape:
            raise CasePreparationError(f"{name} must have shape {obs_shape}")
    if tuple(np.asarray(arrays["ko_channel_ids_1based"]).tolist()) != CHANNELS:
        raise CasePreparationError(
            "input observation channels differ from physical AMI 10..16"
        )
    if (
        not np.isfinite(arrays["obs_bt"]).all()
        or not np.isfinite(arrays["obs_qc"]).all()
    ):
        raise CasePreparationError("source observation BT/QC contain non-finite values")
    if (
        np.any(arrays["obs_qc"] != np.rint(arrays["obs_qc"]))
        or np.any(arrays["obs_qc"] < np.iinfo(np.int32).min)
        or np.any(arrays["obs_qc"] > np.iinfo(np.int32).max)
    ):
        raise CasePreparationError(
            "source obs_qc values are not exactly representable integer codes"
        )
    source_valid = (arrays["obs_dqf"] == 0) & (arrays["obs_qc"].astype(np.int32) == 0)
    if not source_valid.all():
        raise CasePreparationError(
            "source seven-channel QC is not zero for every mapped native column"
        )
    expected_shapes = {
        "rttov_reference__p_lay_hPa": (69,),
        "rttov_reference__p_half_hPa": (70,),
        "rttov_reference__t_K": (69,),
        "rttov_reference__q_ppmv": (69,),
        "rttov_reference__o3_ppmv": (69,),
        "rttov_reference__co2_ppmv": (69,),
    }
    for name, shape in expected_shapes.items():
        _finite(arrays[name], name, shape=shape)
    return source_valid


def _verify_actual_qr_library(paths, experiment):
    """Verify the built binary and canonical overlay without depending on an old worktree."""
    from harness.run_native_candidate_observation import sha256_file, select_library

    if (
        experiment.get("qr_transport") != "actual_departure"
        or experiment.get("factorial_mode") != "norm_actual"
    ):
        raise CasePreparationError(
            "the candidate library must be the norm_actual/actual_departure case"
        )
    library = select_library(paths, role="candidate")
    receipt_path = Path(paths["candidate_build_receipt"])
    overlay_path = Path(paths["candidate_overlay_manifest"])
    if not receipt_path.is_file() or not overlay_path.is_file():
        raise CasePreparationError(
            "candidate build receipt/overlay manifest is missing"
        )
    receipt_bytes = receipt_path.read_bytes()
    receipt = json.loads(receipt_bytes)
    if receipt.get("library_sha256") != library["sha256"]:
        raise CasePreparationError(
            "candidate library hash differs from its build receipt"
        )
    overlay_resolved = str(overlay_path.resolve())
    if receipt.get("source_sha256", {}).get(overlay_resolved) != sha256_file(
        overlay_path
    ):
        raise CasePreparationError(
            "candidate overlay manifest is not pinned by build receipt"
        )
    overlay = json.loads(overlay_path.read_bytes())
    required = {
        "schema": "kdm6.actual_qr_overlay.v1",
        "candidate_mode": "actual_departure",
        "required_ice_mode": "norm_actual",
        "mode_environment": "KDM6_QR_TRANSPORT",
        "default": "legacy",
    }
    if any(overlay.get(key) != value for key, value in required.items()):
        raise CasePreparationError("overlay does not attest the selected actual-QR map")
    for name, expected in overlay.get("overlay_sha256", {}).items():
        source = overlay_path.parent / name
        if not source.is_file() or sha256_file(source) != expected:
            raise CasePreparationError(
                f"candidate overlay TU differs from its source manifest: {name}"
            )
    return {
        **library,
        "qr_transport": experiment["qr_transport"],
        "build_receipt_path": str(receipt_path.resolve()),
        "build_receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "overlay_manifest_path": overlay_resolved,
        "overlay_manifest_sha256": sha256_file(overlay_path),
        "transport_attestation": required,
        "overlay_sha256": overlay.get("overlay_sha256", {}),
        "build_source_sha256": receipt.get("source_sha256", {}),
        "source_path_policy": "binary receipt and canonical overlay bytes verified; old temporary source paths are not required",
    }


def load_case_config(paths=None):
    """Return JSON-safe case identity and cache only selected source arrays."""
    from harness import run_native_candidate_observation as candidate

    resolved = candidate.resolve_paths(paths)
    experiment = _physical_experiment(candidate.experiment_metadata())
    packet_manifest_path = resolved["packets"] / "manifest.json"
    observation_record_path = (
        Path(__file__).resolve().parents[1]
        / "harness/evidence/actual_qr_transport_2026-10-24/observation_prepared.json"
    )
    observation_manifest_path = observation_record_path.parent / "manifest.json"
    preflight_path = resolved["observations"].parent / "PREFLIGHT.json"
    for path in (
        packet_manifest_path,
        observation_record_path,
        observation_manifest_path,
        preflight_path,
    ):
        if not path.is_file():
            raise CasePreparationError(f"case provenance file is missing: {path}")
    packet_manifest_bytes = packet_manifest_path.read_bytes()
    packet_manifest = json.loads(packet_manifest_bytes)
    packet_validation = verify_packet_chunks(resolved["packets"], packet_manifest)
    packet_manifest_sha = hashlib.sha256(packet_manifest_bytes).hexdigest()
    observation_record_bytes = observation_record_path.read_bytes()
    observation_record = json.loads(observation_record_bytes)
    if (
        observation_record.get("schema")
        != "kdm6.native_candidate_observation_prepared.v1"
    ):
        raise CasePreparationError("prepared observation receipt schema differs")
    observation_manifest = json.loads(observation_manifest_path.read_bytes())
    receipt_rel = (
        "harness/evidence/actual_qr_transport_2026-10-24/observation_prepared.json"
    )
    if (
        observation_manifest.get("artifact_sha256", {}).get(receipt_rel)
        != hashlib.sha256(observation_record_bytes).hexdigest()
    ):
        raise CasePreparationError(
            "prepared observation receipt differs from its public manifest pin"
        )
    pinned = {
        str(Path(path).resolve()): digest
        for path, digest in observation_record.get("source_sha256", {}).items()
    }
    source_paths = {
        "checkpoint": resolved["checkpoint"],
        "observations": resolved["observations"],
        "packet_manifest": packet_manifest_path,
        "prep_reference": resolved["prep_reference"],
        "finish_reference": resolved["finish_reference"],
    }
    logical_suffixes = {
        "prep_reference": "harness/evidence/native_prep_ad_2026-10-21/native39_prep_ad.json",
        "finish_reference": "harness/evidence/applied_finish_ad_2026-10-21/native39_finish_ad.json",
    }
    verified_sources = {}
    for name, path in source_paths.items():
        if not path.is_file():
            raise CasePreparationError(f"case input {name} is missing: {path}")
        digest = sha256_file(path)
        receipt_source_path = str(path.resolve())
        expected = pinned.get(str(path.resolve()))
        if expected is None and name in logical_suffixes:
            suffix = logical_suffixes[name]
            matches = [
                (raw_path, raw_digest)
                for raw_path, raw_digest in observation_record.get(
                    "source_sha256", {}
                ).items()
                if str(raw_path).replace("\\", "/").endswith(suffix)
            ]
            if len(matches) == 1:
                receipt_source_path, expected = matches[0]
        if expected != digest:
            raise CasePreparationError(
                f"case input {name} differs from prepared receipt source pin"
            )
        verified_sources[name] = {
            "path": str(path.resolve()),
            "receipt_source_path": receipt_source_path,
            "sha256": digest,
        }
    if (
        packet_manifest.get("source", {}).get("checkpoint_sha256")
        != verified_sources["checkpoint"]["sha256"]
    ):
        raise CasePreparationError("packet source checkpoint hash differs")
    if packet_manifest.get("source", {}).get("checkpoint_times") != NATIVE_TIME:
        raise CasePreparationError("packet is not the captured 00:00:40 endpoint")
    prep_record = json.loads(resolved["prep_reference"].read_bytes())
    finish_record = json.loads(resolved["finish_reference"].read_bytes())
    if (
        prep_record.get("schema") != "kdm6.native_prep_ad.v1"
        or prep_record.get("passed") is not True
    ):
        raise CasePreparationError("prep reference is not a passed native_prep record")
    if (
        finish_record.get("schema") != "kdm6.applied_finish_ad.v1"
        or finish_record.get("passed") is not True
    ):
        raise CasePreparationError(
            "finish reference is not a passed native finish record"
        )
    if (
        prep_record.get("input_sha256", {}).get("checkpoint")
        != verified_sources["checkpoint"]["sha256"]
    ):
        raise CasePreparationError(
            "prep reference checkpoint differs from packet/current checkpoint"
        )
    if prep_record.get("input_sha256", {}).get("namelist") != sha256_file(
        resolved["namelist"]
    ):
        raise CasePreparationError("prep reference namelist differs from case")
    prep_configuration = prep_record.get("configuration")
    finish_configuration = finish_record.get("configuration")
    zero_out_configuration = finish_record.get("zero_out")
    if not all(
        isinstance(x, dict)
        for x in (prep_configuration, finish_configuration, zero_out_configuration)
    ):
        raise CasePreparationError("prep/finish configuration records are malformed")
    if finish_configuration.get("dt") != experiment["dt_seconds"]:
        raise CasePreparationError(
            "finish reference dt differs from the B512 experiment"
        )
    library = _verify_actual_qr_library(resolved, experiment)
    raw16_inventory = _raw16_inventory(Path("/Users/yhlee/KDM6AD-k/GK2A/00"))
    selected_channels = {"wv073", "ir087", "ir096", "ir105", "ir112", "ir123", "ir133"}
    selected_inventory = {
        row["channel"]: row
        for row in raw16_inventory
        if row["channel"] in selected_channels
    }
    if set(selected_inventory) != selected_channels or any(
        row["pixel_shape"] != [900, 900] for row in selected_inventory.values()
    ):
        raise CasePreparationError(
            "the seven selected channels must be present on 900×900 raw grids"
        )
    preflight = json.loads(preflight_path.read_bytes())
    preflight_input_sha = preflight.get("input_bundle", {}).get("sha256")
    if preflight_input_sha != verified_sources["observations"]["sha256"]:
        raise CasePreparationError(
            "original seven-channel bundle differs from the preflight baseline hash"
        )
    preflight_input_sha = preflight.get("input_bundle", {}).get("sha256")
    if preflight_input_sha != verified_sources["observations"]["sha256"]:
        raise CasePreparationError(
            "original seven-channel input bundle differs from preflight baseline pin"
        )
    selected7 = preflight.get("channels", {}).get("per_channel", {})
    selected7_counts = {}
    for channel in ("wv073", "ir087", "ir096", "ir105", "ir112", "ir123", "ir133"):
        if channel not in selected7:
            raise CasePreparationError(
                f"preflight lacks selected raw channel {channel}"
            )
        selected7_counts[channel] = {
            key: selected7[channel].get(key)
            for key in (
                "source_file",
                "source_sha256",
                "dqf_counts",
                "reader_quality_counts",
                "dn_stats",
            )
        }
    cache_material = {
        "checkpoint": verified_sources["checkpoint"]["sha256"],
        "observations": verified_sources["observations"]["sha256"],
        "packet_manifest": packet_manifest_sha,
        "prep": verified_sources["prep_reference"]["sha256"],
        "finish": verified_sources["finish_reference"]["sha256"],
        "library": library["sha256"],
    }
    cache_key = hashlib.sha256(
        json.dumps(cache_material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    config = {
        "schema": "kdm6.native_satellite_case_config.v1",
        "paths": {name: str(path) for name, path in resolved.items()},
        "experiment": experiment,
        "grid": {"nx": NX, "ny": NY, "levels": LEVELS, "columns": N_COLUMNS},
        "checkpoint_time": NATIVE_TIME,
        "checkpoint_itimestep": NATIVE_STEP,
        "packet_manifest": packet_manifest,
        "packet_manifest_sha256": packet_manifest_sha,
        "packet_validation": packet_validation,
        "verified_sources": verified_sources,
        "prep_configuration": prep_configuration,
        "finish_configuration": finish_configuration,
        "zero_out_configuration": zero_out_configuration,
        "library": library,
        "raw16_channel_inventory": raw16_inventory,
        "observation_qualification": {
            "unique_pixel_id_count": N_COLUMNS,
            "native_columns": N_COLUMNS,
            "all_native_columns_have_seven_source_qc_zero": True,
            "source_valid_channel_count": N_COLUMNS * 7,
            "source_channel_cells_expected": N_COLUMNS * 7,
            "source_seven_channel_counts": selected7_counts,
            "original_seven_input_sha256": verified_sources["observations"]["sha256"],
            "preflight_baseline_input_sha256": preflight_input_sha,
            "original_seven_baseline_hash_match": True,
            "pixel_time_verified": False,
            "time_slot": "202507190000",
            "weight_per_native_cell": 1.0,
            "mapping_semantics": "one unique nearest KO pixel per native physical column; no source pixel repeats",
        },
        "cache_key": cache_key,
    }
    _CACHE[cache_key] = _load_case_cache(config)
    return config


def _load_case_cache(config):
    paths = {name: Path(value) for name, value in config["paths"].items()}
    checkpoint_sha, checkpoint = _checkpoint_cache(paths["checkpoint"])
    if checkpoint_sha != config["verified_sources"]["checkpoint"]["sha256"]:
        raise CasePreparationError("checkpoint changed since case config was pinned")
    inputs = _input_cache(paths["observations"])
    if (
        sha256_file(paths["observations"])
        != config["verified_sources"]["observations"]["sha256"]
    ):
        raise CasePreparationError("KO input bundle changed while loading arrays")
    source_valid = _validate_input_arrays(inputs)
    if not source_valid.all():
        raise CasePreparationError("source quality mask differs from case admission")
    preflight = json.loads(
        (paths["observations"].parent / "PREFLIGHT.json").read_bytes()
    )
    upper = preflight.get("native_grid", {}).get(
        "reference_extension_layers_by_cell", {}
    )
    if upper.get("center_count_values") != {"27": N_COLUMNS} or upper.get(
        "interface_count_values"
    ) != {"27": N_COLUMNS}:
        raise CasePreparationError(
            "native reference extension is not fixed at 27 upper layers per cell"
        )
    reference = {
        "p_lay_hpa": _finite(inputs["rttov_reference__p_lay_hPa"], "reference p_lay"),
        "p_half_hpa": _finite(
            inputs["rttov_reference__p_half_hPa"], "reference p_half"
        ),
        "t_k": _finite(inputs["rttov_reference__t_K"], "reference T"),
        "q_ppmv": _finite(inputs["rttov_reference__q_ppmv"], "reference Q"),
        "o3_ppmv": _finite(inputs["rttov_reference__o3_ppmv"], "reference O3"),
        "co2_ppmv": _finite(inputs["rttov_reference__co2_ppmv"], "reference CO2"),
        "fixed_upper_count": UPPER_REFERENCE_LEVELS,
    }
    return {
        "checkpoint": checkpoint,
        "inputs": inputs,
        "source_valid": source_valid,
        "reference": reference,
        "fastem": _read_fastem(paths["template"]),
        "checkpoint_sha256": checkpoint_sha,
        "observation_sha256": config["verified_sources"]["observations"]["sha256"],
    }


def _prep_batch(theta_m, qv, mu, ph, geometry, configuration):
    """Vectorized transcription of native_prep._intermediates; no KDM call."""
    ptop = float(configuration["ptop"])
    rd = float(configuration["rd"])
    p0 = float(configuration["p0"])
    t0 = float(configuration["t0"])
    alpha = float(configuration["alpha"])
    gamma = float(configuration["gamma"])
    kappa = float(configuration["kappa"])
    gravity = float(configuration["g"])
    phb = geometry["phb"]
    c3h, c4h, c3f, c4f = (
        geometry["c3h"],
        geometry["c4h"],
        geometry["c3f"],
        geometry["c4f"],
    )
    if np.any(theta_m + t0 <= 0.0) or np.any(qv < 0.0) or np.any(mu <= 0.0):
        raise CasePreparationError(
            "checkpoint T_2/QV/MU fails native prep physical-domain checks"
        )
    with np.errstate(over="raise", invalid="raise", divide="raise", under="ignore"):
        dphi = (ph[:, 1:] + phb[:, 1:]) - (ph[:, :-1] + phb[:, :-1])
        h = c3h * mu[:, None] + c4h + ptop
        p_down = c3f[:, :-1] * mu[:, None] + c4f[:, :-1] + ptop
        p_up = c3f[:, 1:] * mu[:, None] + c4f[:, 1:] + ptop
        log_depth = np.log(p_down / p_up)
        volume = dphi / h / log_depth
        temp_moist = theta_m + t0
        pressure = p0 * (rd * temp_moist / (p0 * volume)) ** gamma
        pii = (pressure / p0) ** kappa
        theta_dry = temp_moist / (1.0 + alpha * qv)
        rho = 1.0 / volume
        delz = dphi / gravity
    arrays = (
        dphi,
        h,
        p_down,
        p_up,
        log_depth,
        volume,
        pressure,
        pii,
        theta_dry,
        rho,
        delz,
    )
    if (
        any(not np.isfinite(value).all() for value in arrays)
        or np.any(dphi <= 0.0)
        or np.any(h <= 0.0)
        or np.any(p_down <= p_up)
        or np.any(p_up <= 0.0)
        or np.any(volume <= 0.0)
        or np.any(delz <= 0.0)
    ):
        raise CasePreparationError(
            "checkpoint batch fails native prep positive/finite validation"
        )
    return np.stack((theta_dry, rho, pii, pressure, delz), axis=0)


def _read_fastem(template):
    skin = Path(template) / "in/profiles/001/sfc/01/skin.txt"
    if not skin.is_file():
        raise CasePreparationError(f"RTTOV skin file missing: {skin}")
    text = skin.read_text()
    values = []
    for index in range(1, 6):
        match = re.search(rf"(?im)^\s*k0%fastem\({index}\)\s*=\s*([^,!/\s]+)", text)
        if match is None:
            raise CasePreparationError(f"RTTOV skin is missing FASTEM({index})")
        values.append(float(match.group(1)))
    if not np.isfinite(values).all():
        raise CasePreparationError("RTTOV FASTEM values must be finite")
    return tuple(values)


def _surface_profile_rows(native_surface, *, fastem):
    """Make the same per-profile RTTOV surface records used by the native column path."""
    xland = native_surface["xland"]
    hgt = native_surface["hgt_m"]
    tsk, t2 = native_surface["tsk_K"], native_surface["t2_K"]
    q2 = native_surface["q2_kgkg_dry"]
    u10, v10 = native_surface["u10_m_s"], native_surface["v10_m_s"]
    sina, cosa = native_surface["sinalpha"], native_surface["cosalpha"]
    snow, seaice = native_surface["snow_fraction"], native_surface["seaice_fraction"]
    if not np.isin(xland, (1.0, 2.0)).all():
        raise CasePreparationError(
            "surface XLAND must use WRF codes 1 (land) or 2 (water)"
        )
    if not np.all((-1.0 <= hgt / 1000.0) & (hgt / 1000.0 <= 20.0)):
        raise CasePreparationError("checkpoint HGT is outside RTTOV elevation range")
    if np.any((snow < 0.0) | (snow > 1.0)) or np.any((seaice < 0.0) | (seaice > 1.0)):
        raise CasePreparationError(
            "checkpoint snow/seaice values must be fractions in [0,1]"
        )
    if not np.all(np.abs(sina * sina + cosa * cosa - 1.0) <= 1.0e-6):
        raise CasePreparationError(
            "checkpoint SINALPHA/COSALPHA fail the native rotation-basis check"
        )
    if np.any((tsk < 50.0) | (tsk > 400.0)) or np.any((t2 < 50.0) | (t2 > 400.0)):
        raise CasePreparationError(
            "checkpoint TSK/T2 are outside RTTOV surface temperature bounds"
        )
    q2_mol = np.maximum(q2, 0.0) / WATER_VAPOR_KG_MOL
    q2_ppmv_moist = 1.0e6 * q2_mol / ((1.0 / MASS_AIR_KG_MOL) + q2_mol)
    if np.any((q2_ppmv_moist < 50.0) | (q2_ppmv_moist > 2.0e5)):
        raise CasePreparationError(
            "checkpoint Q2 converts outside RTTOV ppmv-moist bounds"
        )
    earth_u = u10 * cosa - v10 * sina
    earth_v = u10 * sina + v10 * cosa
    profiles = []
    for row in range(xland.size):
        land = xland[row] == 1.0
        ice = (not land) and seaice[row] > 0.0
        profiles.append(
            {
                "skin": {
                    "surftype": 0 if land else 2 if ice else 1,
                    "watertype": 0 if land else 1,
                    "t": float(tsk[row]),
                    "salinity": 0.0 if land else 35.0,
                    "foam_fraction": 0.0,
                    "snow_fraction": float(snow[row]),
                    "fastem": [0.0] * 5 if land else [float(v) for v in fastem],
                },
                "near_surface": {
                    "t2m": float(t2[row]),
                    "q2m": float(q2_ppmv_moist[row]),
                    "wind_u10m": float(earth_u[row]),
                    "wind_v10m": float(earth_v[row]),
                    "wind_fetch": 0.0,
                },
            }
        )
    return profiles


def _cache_for_config(config):
    if (
        not isinstance(config, dict)
        or config.get("schema") != "kdm6.native_satellite_case_config.v1"
    ):
        raise TypeError("config must be returned by load_case_config")
    cache_key = config.get("cache_key")
    if not isinstance(cache_key, str) or len(cache_key) != 64:
        raise CasePreparationError("case config cache key is malformed")
    if cache_key not in _CACHE:
        _CACHE[cache_key] = _load_case_cache(config)
    return _CACHE[cache_key]


def load_case_block(config, chunk_index):
    """Load one original B512/final452 block; preserve it and expose native metadata."""
    if isinstance(chunk_index, bool) or not isinstance(chunk_index, (int, np.integer)):
        raise TypeError("chunk_index must be an integer")
    manifest = config.get("packet_manifest") if isinstance(config, dict) else None
    chunks = manifest.get("chunks") if isinstance(manifest, dict) else None
    if not isinstance(chunks, list) or not 0 <= int(chunk_index) < len(chunks):
        raise IndexError("chunk_index is outside packet manifest")
    grid = config.get("grid", {})
    nx, ny, levels, columns = (
        int(grid.get("nx", 0)),
        int(grid.get("ny", 0)),
        int(grid.get("levels", 0)),
        int(grid.get("columns", 0)),
    )
    if nx <= 0 or ny <= 0 or levels <= 0 or columns != nx * ny:
        raise CasePreparationError("case grid metadata is invalid")
    cache = _cache_for_config(config)
    paths = {name: Path(value) for name, value in config["paths"].items()}
    entry = chunks[int(chunk_index)]
    chunk_path = (paths["packets"] / entry["path"]).resolve()
    if paths["packets"].resolve() not in chunk_path.parents:
        raise CasePreparationError("packet chunk escapes pinned packet directory")
    if (
        sha256_file(chunk_path) != entry["sha256"]
        or chunk_path.stat().st_size != entry["bytes"]
    ):
        raise CasePreparationError(
            f"packet chunk {chunk_index} differs from its manifest pin"
        )
    with np.load(chunk_path, allow_pickle=False) as archive:
        if set(archive.files) != {
            "state",
            "forcing",
            "xland",
            "flat_indices",
            "i",
            "j",
        }:
            raise CasePreparationError(
                "packet chunk key set differs from endpoint schema"
            )
        packet_state = np.asarray(archive["state"]).copy()
        packet_forcing = np.asarray(archive["forcing"]).copy()
        packet_xland = np.asarray(archive["xland"]).copy()
        flat_indices = np.asarray(archive["flat_indices"]).copy()
        packet_i, packet_j = (
            np.asarray(archive["i"]).copy(),
            np.asarray(archive["j"]).copy(),
        )
    count = int(entry["columns"])
    start, stop = int(entry["start_flat"]), int(entry["stop_flat_exclusive"])
    expected_flat = np.arange(start, stop, dtype=np.int32)
    if (
        count != stop - start
        or packet_state.dtype != np.float64
        or packet_state.shape != (12, count, levels)
        or packet_forcing.dtype != np.float64
        or packet_forcing.shape != (4, count, levels)
        or packet_xland.dtype != np.float64
        or packet_xland.shape != (count,)
        or flat_indices.dtype != np.int32
        or packet_i.dtype != np.int32
        or packet_j.dtype != np.int32
        or flat_indices.shape != (count,)
        or packet_i.shape != (count,)
        or packet_j.shape != (count,)
        or not np.array_equal(flat_indices, expected_flat)
        or not np.array_equal(packet_i, flat_indices % nx)
        or not np.array_equal(packet_j, flat_indices // nx)
        or not np.isfinite(packet_state).all()
        or not np.isfinite(packet_forcing).all()
        or not np.isfinite(packet_xland).all()
        or not np.isin(packet_xland, (1.0, 2.0)).all()
    ):
        raise CasePreparationError(
            f"chunk {chunk_index} has invalid, padded, or misordered packet data"
        )
    if start < 0 or stop > columns:
        raise CasePreparationError("packet flat range is outside configured grid")
    flat_indices = expected_flat
    checkpoint, inputs = cache["checkpoint"], cache["inputs"]
    i, j = flat_indices % nx, flat_indices // nx

    def profile(name):
        values = checkpoint[name]
        nlevels = levels + 1 if name in ("PH_2", "PHB") else levels
        if values.shape != (nlevels, ny, nx):
            raise CasePreparationError(
                f"checkpoint profile {name} shape differs from configured grid"
            )
        return np.ascontiguousarray(values[:, j, i].T.astype(np.float64))

    def surface(name):
        values = checkpoint[name]
        if values.shape != (ny, nx):
            raise CasePreparationError(
                f"checkpoint surface {name} shape differs from configured grid"
            )
        return np.ascontiguousarray(values[j, i].astype(np.float64))

    theta_m = profile("THM_2")
    qv = profile("QVAPOR")
    ph = profile("PH_2")
    geometry = {
        "phb": profile("PHB"),
        "c3h": np.broadcast_to(
            checkpoint["C3H"].astype(np.float64), (count, levels)
        ).copy(),
        "c4h": np.broadcast_to(
            checkpoint["C4H"].astype(np.float64), (count, levels)
        ).copy(),
        "c3f": np.broadcast_to(
            checkpoint["C3F"].astype(np.float64), (count, levels + 1)
        ).copy(),
        "c4f": np.broadcast_to(
            checkpoint["C4F"].astype(np.float64), (count, levels + 1)
        ).copy(),
    }
    mub, mu_2 = checkpoint["MUB"][j, i], checkpoint["MU_2"][j, i]
    mu = np.ascontiguousarray(
        np.asarray(mub + mu_2, dtype=np.float32).astype(np.float64)
    )
    if not np.isfinite(mu).all() or np.any(mu <= 0.0):
        raise CasePreparationError(
            "checkpoint float32(MUB+MU_2) is not positive finite"
        )
    native_surface = {
        "xland": surface("XLAND"),
        "hgt_m": surface("HGT"),
        "tsk_K": surface("TSK"),
        "t2_K": surface("T2"),
        "q2_kgkg_dry": surface("Q2"),
        "u10_m_s": surface("U10"),
        "v10_m_s": surface("V10"),
        "sinalpha": surface("SINALPHA"),
        "cosalpha": surface("COSALPHA"),
        "snow_fraction": surface("SNOWC"),
        "seaice_fraction": surface("SEAICE"),
        "emissivity_raw": surface("EMISS"),
        "model_lat_deg": surface("XLAT"),
        "model_lon_deg": surface("XLONG"),
    }
    for name, input_name in (
        ("model_lat_deg", "model_lat"),
        ("model_lon_deg", "model_lon"),
    ):
        from_checkpoint = native_surface[name].astype(np.float32)
        from_input = inputs[input_name].reshape(-1)[flat_indices].astype(np.float32)
        if from_checkpoint.tobytes() != from_input.tobytes():
            raise CasePreparationError(
                f"checkpoint {name} differs bitwise from original input grid"
            )
    if (
        native_surface["xland"].astype(np.float32).tobytes()
        != packet_xland.astype(np.float32).tobytes()
    ):
        raise CasePreparationError("checkpoint XLAND differs from original packet")
    if (
        not np.isfinite(packet_state[1]).all()
        or packet_state[1].tobytes() != qv.astype(np.float64).tobytes()
    ):
        raise CasePreparationError(
            "checkpoint QV differs bitwise from original packet state"
        )
    obs_bt = _finite(inputs["obs_bt"][flat_indices], "obs_bt", shape=(count, 7))
    obs_dqf = np.asarray(inputs["obs_dqf"][flat_indices]).copy()
    obs_qc = _finite(inputs["obs_qc"][flat_indices], "obs_qc", shape=(count, 7))
    if (
        np.any(obs_qc != np.rint(obs_qc))
        or np.any(obs_qc < np.iinfo(np.int32).min)
        or np.any(obs_qc > np.iinfo(np.int32).max)
    ):
        raise CasePreparationError(
            "block obs_qc is not exactly representable as int32 codes"
        )
    obs_qc_codes = obs_qc.astype(np.int32)
    obs_valid = (obs_dqf == 0) & (obs_qc_codes == 0)
    if not obs_valid.all():
        raise CasePreparationError(
            "source seven-channel observation QC not zero in block"
        )
    pixel_row = np.asarray(
        inputs["ko_nearest_row"].reshape(-1)[flat_indices], dtype=np.int32
    ).copy()
    pixel_col = np.asarray(
        inputs["ko_nearest_col"].reshape(-1)[flat_indices], dtype=np.int32
    ).copy()
    pixel_flat = np.asarray(
        inputs["ko_nearest_flat_index"].reshape(-1)[flat_indices], dtype=np.int32
    ).copy()
    pixel_lat = _finite(
        inputs["ko_nearest_lat_deg"].reshape(-1)[flat_indices], "pixel_lat"
    )
    pixel_lon = _finite(
        inputs["ko_nearest_lon_deg"].reshape(-1)[flat_indices], "pixel_lon"
    )
    pixel_distance = _finite(
        inputs["ko_distance_m"].reshape(-1)[flat_indices], "pixel_distance_m"
    )
    rttov_geometry = {
        "zenangle": _finite(
            inputs["ami_geometry_zenangle_deg"].reshape(-1)[flat_indices], "zenangle"
        ),
        "azangle": _finite(
            inputs["ami_geometry_azangle_deg"].reshape(-1)[flat_indices], "azangle"
        ),
        "sunzenangle": _finite(
            inputs["ami_geometry_sunzenangle_deg"].reshape(-1)[flat_indices],
            "sunzenangle",
        ),
        "sunazangle": _finite(
            inputs["ami_geometry_sunazangle_deg"].reshape(-1)[flat_indices],
            "sunazangle",
        ),
        "latitude": native_surface["model_lat_deg"].copy(),
        "longitude": native_surface["model_lon_deg"].copy(),
        "elevation": native_surface["hgt_m"] / 1000.0,
    }
    ko_geometry_lat = _finite(
        inputs["ami_geometry_lat_deg"].reshape(-1)[flat_indices],
        "KO geometry pixel latitude",
    )
    ko_geometry_lon = _finite(
        inputs["ami_geometry_lon_deg"].reshape(-1)[flat_indices],
        "KO geometry pixel longitude",
    )
    if not np.array_equal(ko_geometry_lat, pixel_lat) or not np.array_equal(
        ko_geometry_lon, pixel_lon
    ):
        raise CasePreparationError(
            "original KO geometry pixel coordinates differ from the mapping"
        )
    if not np.allclose(
        rttov_geometry["elevation"],
        native_surface["hgt_m"] / 1000.0,
        rtol=0.0,
        atol=1.0e-6,
    ):
        raise CasePreparationError(
            "RTTOV geometry elevation differs from current checkpoint HGT"
        )
    surface_profiles = _surface_profile_rows(native_surface, fastem=cache["fastem"])
    rttov_geometry_profiles = [
        {name: float(values[row]) for name, values in rttov_geometry.items()}
        for row in range(count)
    ]
    negative_nc = np.any(packet_state[8] < 0.0, axis=1)
    negative_ni = np.any(packet_state[9] < 0.0, axis=1)
    cost_eligible = ~(negative_nc | negative_ni)
    reason = np.asarray(
        [
            "+".join(
                name
                for flag, name in (
                    (negative_nc[row], "negative_NC"),
                    (negative_ni[row], "negative_NI"),
                )
                if flag
            )
            or "eligible"
            for row in range(count)
        ],
        dtype="U24",
    )
    prep_output = _prep_batch(
        theta_m, qv, mu, ph, geometry, config["prep_configuration"]
    )
    packet_target = np.concatenate((packet_state[0:1], packet_forcing), axis=0)
    prep_maxabs = np.max(np.abs(prep_output - packet_target), axis=(0, 2))
    prep_close = np.asarray(
        [
            np.allclose(
                prep_output[:, row], packet_target[:, row], rtol=2.0e-13, atol=1.0e-13
            )
            for row in range(count)
        ],
        dtype=bool,
    )
    if not prep_close.all():
        row = int(np.flatnonzero(~prep_close)[0])
        raise CasePreparationError(
            f"checkpoint prep differs from packet in row {row}: {prep_maxabs[row]:.17g}"
        )
    return {
        "schema": SCHEMA,
        "chunk_index": int(chunk_index),
        "chunk_sha256": entry["sha256"],
        "start_flat": start,
        "stop_flat": stop,
        "flat_indices": flat_indices.copy(),
        "i": packet_i,
        "j": packet_j,
        "B": count,
        "L": levels,
        "theta_m": theta_m,
        "thm_pert": theta_m,
        "qv": qv,
        "mu": mu,
        "ph": ph,
        "rest": np.ascontiguousarray(packet_state[2:12]),
        "packet_state": packet_state,
        "packet_forcing": packet_forcing,
        "xland": packet_xland.copy(),
        "geometry": geometry,
        "fnm": checkpoint["FNM"].astype(np.float64).copy(),
        "fnp": checkpoint["FNP"].astype(np.float64).copy(),
        "native_surface": native_surface,
        "surface": native_surface,
        "surface_profiles": surface_profiles,
        "rttov_geometry": rttov_geometry,
        "rttov_geometry_profiles": rttov_geometry_profiles,
        "geometry_profiles": rttov_geometry_profiles,
        "model_lat": native_surface["model_lat_deg"].copy(),
        "model_lon": native_surface["model_lon_deg"].copy(),
        "obs_bt": obs_bt,
        "obs_dqf": obs_dqf,
        "obs_qc_raw": obs_qc,
        "obs_qc_codes": obs_qc_codes,
        "obs_source_valid": obs_valid,
        "pixel_row": pixel_row,
        "pixel_col": pixel_col,
        "pixel_flat_index": pixel_flat,
        "pixel_lat": pixel_lat,
        "pixel_lon": pixel_lon,
        "ko_geometry_pixel_lat": ko_geometry_lat,
        "ko_geometry_pixel_lon": ko_geometry_lon,
        "pixel_distance_m": pixel_distance,
        "reference": cache["reference"],
        "fixed_upper_count": UPPER_REFERENCE_LEVELS,
        "prep_output": prep_output,
        "prep_maxabs_vs_packet": prep_maxabs,
        "prep_allclose": prep_close,
        "initial_admission": {
            "negative_nc": negative_nc,
            "negative_ni": negative_ni,
            "cost_eligible": cost_eligible,
            "reason": reason,
            "excluded_from_cost_rows": int((~cost_eligible).sum()),
            "original_full_b_retained": True,
            "original_packet_state_unchanged": True,
            "physical_number_admission": False,
        },
        "preparation_status": {
            "status": "PREPARED_OFFLINE_BLOCK",
            "packet_chunk_sha256_verified": True,
            "checkpoint_prep_rows_compared": count,
            "checkpoint_prep_all_rows_within_tolerance": bool(prep_close.all()),
            "source_qc_all_selected_channels_valid": bool(obs_valid.all()),
            "cost_eligible_rows": int(cost_eligible.sum()),
            "cost_excluded_initial_negative_nc_or_ni_rows": int((~cost_eligible).sum()),
            "original_full_b_retained": True,
        },
        "observation_qualification": config["observation_qualification"],
        "checkpoint_sha256": cache["checkpoint_sha256"],
        "observation_sha256": cache["observation_sha256"],
        "packet_manifest_sha256": config["packet_manifest_sha256"],
        "ncmin_land": float(config["experiment"]["ncmin_land"]),
        "ncmin_sea": float(config["experiment"]["ncmin_sea"]),
        "dt_seconds": float(config["experiment"]["dt_seconds"]),
    }
