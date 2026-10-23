#!/usr/bin/env python3
"""Prepare endpoint-initialized native-grid KDM6 split-physics packets.

This is a value-only preparation step. It does not invoke KDM6, WRF, RTTOV or
an observation cost, and its endpoint state is not represented as the next
executed MP call or as a forecast step. The raw checkpoint number fields are
preserved in the KDM6 ABI order without asserting their physical number basis.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
CONFIG_PATH = ROOT / "harness/evidence/native_prep_ad_2026-10-21/native39_prep_ad.json"
DEFAULT_CHECKPOINT = Path(
    "/Users/yhlee/KDM6AD-k/host/research_evidence/mp137_two_step_20261020/"
    "TWO_STEP_SAVED_DA/calls/live_yws3nddy/wrfrst_d01_2025-07-19_00:00:40"
)
DEFAULT_NAMELIST = DEFAULT_CHECKPOINT.parent / "namelist.output"
DEFAULT_OUTPUT = Path(
    "/Users/yhlee/KDM6AD-k/host/research_evidence/"
    "mp137_ice_factorial_20261023/domain_preparation_fp64"
)
GRID = (282, 234)
LEVELS = 39
CHUNK_COLUMNS = 512
STATE_FIELDS = ("TH", "Q", "QC", "QR", "QI", "QS", "QG", "NN", "NC", "NI", "NR", "BG")
FORCING_FIELDS = ("DEN", "PII", "P", "DELZ")
STATE_SOURCE = (
    "native_prep.TH", "QVAPOR", "QCLOUD", "QRAIN", "QICE", "QSNOW", "QGRAUP",
    "QNCCN", "QNCLOUD", "QNICE", "QNRAIN", "QIB",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def chunk_bounds(columns: int, chunk_size: int = CHUNK_COLUMNS):
    if type(columns) is not int or columns <= 0 or type(chunk_size) is not int or chunk_size <= 0:
        raise ValueError("columns and chunk_size must be positive integers")
    for start in range(0, columns, chunk_size):
        yield start, min(start + chunk_size, columns)


def _read_flat(variable, start: int, stop: int, *, ny: int, nx: int, levels: int | None):
    """Read a bounded contiguous flat-column range without loading whole fields."""
    expected_dims = (("Time", "south_north", "west_east") if levels is None else
                     ("Time", "bottom_top_stag", "south_north", "west_east")
                     if "bottom_top_stag" in variable.dimensions else
                     ("Time", "bottom_top", "south_north", "west_east"))
    if tuple(variable.dimensions) != expected_dims:
        raise ValueError(f"{variable.name} has unexpected dimensions {variable.dimensions}")
    out_levels = levels
    out = np.empty((stop - start,) if levels is None else (stop - start, out_levels), dtype=np.float32)
    first_row, last_row = start // nx, (stop - 1) // nx
    if last_row >= ny:
        raise ValueError("flat-column range lies outside the native grid")
    offset = 0
    for j in range(first_row, last_row + 1):
        i0 = start % nx if j == first_row else 0
        i1 = ((stop - 1) % nx + 1) if j == last_row else nx
        if levels is None:
            values = np.asarray(variable[0, j:j + 1, i0:i1], dtype=np.float32).reshape(-1)
            out[offset:offset + values.size] = values
        else:
            values = np.asarray(variable[0, :, j:j + 1, i0:i1], dtype=np.float32).reshape(levels, -1).T
            out[offset:offset + values.shape[0], :] = values
        offset += i1 - i0
    if offset != stop - start:
        raise AssertionError("internal flat-column read coverage error")
    return out


def _check_finite(name: str, values: np.ndarray) -> None:
    if not np.isfinite(values).all():
        bad = int((~np.isfinite(values)).sum())
        raise ValueError(f"{name} contains {bad} nonfinite values")


def _preflight(thm, qv, mu_total, ph, phb, c3h, c4h, c3f, c4f, config):
    for name, values in (("THM_2", thm), ("QVAPOR", qv), ("MU total", mu_total),
                         ("PH_2", ph), ("PHB", phb), ("C3H", c3h), ("C4H", c4h),
                         ("C3F", c3f), ("C4F", c4f)):
        _check_finite(name, values)
    if np.any(thm + config["t0"] <= 0.0):
        raise ValueError("T_2 + T0 must be positive in every column")
    if np.any(qv < 0.0) or np.any(mu_total <= 0.0):
        raise ValueError("QVAPOR must be nonnegative and MU total positive")
    dphi = (ph + phb)[:, 1:] - (ph + phb)[:, :-1]
    h = c3h[None, :] * mu_total[:, None] + c4h[None, :] + config["ptop"]
    pd = c3f[None, :-1] * mu_total[:, None] + c4f[None, :-1] + config["ptop"]
    pu = c3f[None, 1:] * mu_total[:, None] + c4f[None, 1:] + config["ptop"]
    if np.any(dphi <= 0.0) or np.any(h <= 0.0) or np.any(pd <= pu) or np.any(pu <= 0.0):
        raise ValueError("native geometry fails positive dphi, hybrid mass, or p_d > p_u > 0 checks")
    ell = np.log(pd / pu)
    volume = dphi / h / ell
    if not np.isfinite(volume).all() or np.any(volume <= 0.0):
        raise ValueError("native specific volume must be finite and positive")


def _native_prep_batch(thm, qv, mu_total, ph, phb, c3h, c4h, c3f, c4f, config):
    """Batch the pure continuous map; input arrays are [column, level]."""
    import torch
    from oracle.kdm6.native_prep import FrozenPrepGeometry, NativePrepState, NativePrepConfig, _intermediates

    conf = NativePrepConfig(**config)
    state = NativePrepState(*(torch.from_numpy(np.ascontiguousarray(x, dtype=np.float64))
                              for x in (thm, qv, mu_total, ph)))
    batch_geometry = (phb, np.broadcast_to(c3h, (thm.shape[0], LEVELS)),
                      np.broadcast_to(c4h, (thm.shape[0], LEVELS)),
                      np.broadcast_to(c3f, (thm.shape[0], LEVELS + 1)),
                      np.broadcast_to(c4f, (thm.shape[0], LEVELS + 1)))
    geometry = FrozenPrepGeometry(*(torch.from_numpy(np.ascontiguousarray(x, dtype=np.float64))
                                    for x in batch_geometry))

    def one_column(s, g):
        values = _intermediates(NativePrepState(*s), FrozenPrepGeometry(*g), conf)
        return (values["theta_dry"], values["rho"], values["pii"],
                values["pressure"], values["delz"])

    # vmap maps all 5 state and geometry components over the leading column axis.
    geometry_tuple = tuple(getattr(geometry, name) for name in ("phb", "c3h", "c4h", "c3f", "c4f"))
    result = torch.vmap(one_column)(tuple(state), geometry_tuple)
    return np.stack([value.detach().cpu().numpy() for value in result], axis=0)


def _packet_arrays(prep, raw_state_fields, xland):
    """Build ABI ordered binary64 packet arrays without changing source values."""
    if prep.dtype != np.float64 or prep.ndim != 3 or prep.shape[0] != 5:
        raise TypeError("native prep values must be float64 with shape [5,B,39]")
    if len(raw_state_fields) != len(STATE_FIELDS) - 1:
        raise ValueError("eleven checkpoint state fields must follow prepared TH")
    columns = prep.shape[1]
    state = np.empty((len(STATE_FIELDS), columns, LEVELS), dtype=np.float64)
    state[0] = prep[0]
    for row, values in enumerate(raw_state_fields, start=1):
        source = np.asarray(values)
        if source.shape != (columns, LEVELS) or source.dtype.kind != "f":
            raise ValueError(f"raw state field {STATE_FIELDS[row]} has wrong shape or dtype")
        state[row] = source.astype(np.float64)
    forcing = np.ascontiguousarray(prep[1:], dtype=np.float64)
    xland64 = np.asarray(xland).astype(np.float64)
    if xland64.shape != (columns,):
        raise ValueError("XLAND must have one value per column")
    return state, forcing, xland64


def _sample_check(packet_state, packet_forcing, index, thm, qv, mu_total, ph, phb,
                  c3h, c4h, c3f, c4f, config):
    import torch
    from oracle.kdm6.native_prep import FrozenPrepGeometry, NativePrepState, NativePrepConfig, native_prep

    state = NativePrepState(torch.tensor(np.array(thm[index], copy=True), dtype=torch.float64),
                            torch.tensor(np.array(qv[index], copy=True), dtype=torch.float64),
                            torch.tensor(float(mu_total[index]), dtype=torch.float64),
                            torch.tensor(np.array(ph[index], copy=True), dtype=torch.float64))
    geometry = FrozenPrepGeometry(**{
        name: torch.tensor(np.array(value[index] if value.ndim == 2 else value, copy=True), dtype=torch.float64)
        for name, value in (("phb", phb), ("c3h", c3h), ("c4h", c4h), ("c3f", c3f), ("c4f", c4f))
    })
    result = native_prep(state, geometry, NativePrepConfig(**config))
    scalar = np.stack([value.numpy() for value in result])
    actual = np.concatenate((packet_state[0, index][None, :], packet_forcing[:, index]), axis=0)
    if not np.allclose(actual, scalar, rtol=2e-13, atol=1e-13):
        raise ValueError(f"batched native prep differs from public 1-D forward at sample column {index}")


def _namelist_time(path: Path) -> str:
    import re
    text = path.read_text()
    match = re.search(r"(?im)^\s*start_date\s*=\s*['\"]([^'\"]+)['\"]", text)
    if match:
        start = datetime.strptime(match.group(1), "%Y-%m-%d_%H:%M:%S")
    else:
        def first_int(key):
            value = re.search(rf"(?im)^\s*{key}\s*=\s*(?:(\d+)\s*\*\s*)?(-?\d+)", text)
            if not value:
                raise ValueError(f"namelist.output is missing {key}")
            return int(value.group(2))
        start = datetime(*(first_int(key) for key in
                           ("start_year", "start_month", "start_day", "start_hour", "start_minute", "start_second")))
    # This offline packet is pinned to the captured 40-second endpoint.
    expected = datetime.strptime("2025-07-19_00:00:40", "%Y-%m-%d_%H:%M:%S")
    if start > expected or (expected - start).total_seconds() != 40:
        raise ValueError("namelist start time does not identify the pinned 00:00:40 checkpoint endpoint")
    return expected.strftime("%Y-%m-%d_%H:%M:%S")


def verify_prep_source_contract(namelist_text: str, checkpoint_attrs: dict,
                                dimensions: dict[str, int], actual_times: str) -> dict:
    """Require the namelist, checkpoint metadata, endpoint and grid to fit this prep map."""
    from harness.run_ss_case import _namelist_assignments

    assignments = _namelist_assignments(namelist_text)

    def integer(key):
        values = assignments.get(key)
        if not values:
            raise ValueError(f"namelist is missing required selector {key!r}")
        token = values[0].strip().replace("D", "E").replace("d", "e")
        value = float(token)
        if not np.isfinite(value) or value != int(value):
            raise ValueError(f"namelist selector {key} must be an integer")
        return int(value)

    def logical(key):
        values = assignments.get(key)
        if not values:
            raise ValueError(f"namelist is missing required selector {key!r}")
        token = values[0].strip().lower().strip(".")
        if token in ("t", "true"):
            return True
        if token in ("f", "false"):
            return False
        raise ValueError(f"namelist selector {key} is not a supported Fortran logical")

    selectors = {"mp_physics": integer("mp_physics"),
                 "use_theta_m": integer("use_theta_m"),
                 "hypsometric_opt": integer("hypsometric_opt"),
                 "non_hydrostatic": logical("non_hydrostatic")}
    expected_selectors = {"mp_physics": 137, "use_theta_m": 1,
                          "hypsometric_opt": 2, "non_hydrostatic": True}
    if selectors != expected_selectors:
        raise ValueError(f"namelist prep selectors {selectors} differ from required {expected_selectors}")

    for name, expected in (("MP_PHYSICS", 137), ("USE_THETA_M", 1)):
        if name not in checkpoint_attrs:
            raise ValueError(f"checkpoint is missing required global attribute {name}")
        actual = int(checkpoint_attrs[name])
        if actual != expected:
            raise ValueError(f"checkpoint {name}={actual}, expected {expected}")
    expected_dims = {"west_east": GRID[1], "south_north": GRID[0],
                     "bottom_top": LEVELS, "bottom_top_stag": LEVELS + 1}
    if dimensions != expected_dims:
        raise ValueError(f"checkpoint dimensions {dimensions} differ from required {expected_dims}")
    expected_time = "2025-07-19_00:00:40"
    if actual_times != expected_time:
        raise ValueError(f"checkpoint Times={actual_times}, expected {expected_time}")
    return {"status": "passed", "namelist_selectors": selectors,
            "checkpoint_global_attributes": {name: int(checkpoint_attrs[name])
                                             for name in ("MP_PHYSICS", "USE_THETA_M")},
            "checkpoint_dimensions": dimensions, "checkpoint_times": actual_times}


def prepare(checkpoint: Path, namelist: Path, output: Path, *, chunk_size: int = CHUNK_COLUMNS):
    try:
        import netCDF4
    except ImportError as exc:
        raise RuntimeError("netCDF4 is required for native restart preparation") from exc
    if output.exists() or output.is_symlink():
        raise ValueError(f"output path already exists: {output}")
    if not checkpoint.is_file() or not namelist.is_file():
        raise FileNotFoundError("checkpoint and explicit namelist.output must both exist")
    conf_data = json.loads(CONFIG_PATH.read_text())
    config = conf_data["configuration"]
    if int(conf_data.get("levels", LEVELS)) != LEVELS:
        raise ValueError("native prep configuration does not declare 39 levels")
    expected_time = _namelist_time(namelist)
    ny, nx = GRID
    total = ny * nx
    output.mkdir(parents=True)
    chunks = []
    coverage = np.zeros(total, dtype=np.uint8)
    raw_negative_counts = {name: 0 for name in STATE_FIELDS}
    sample_checks = 0
    recorded_samples = set()
    with netCDF4.Dataset(checkpoint) as ds:
        ds.set_auto_maskandscale(False)
        for name, expected in (("west_east", nx), ("south_north", ny),
                               ("bottom_top", LEVELS), ("bottom_top_stag", LEVELS + 1)):
            if len(ds.dimensions.get(name, ())) != expected:
                raise ValueError(f"checkpoint dimension {name} differs from required {expected}")
        if "Times" not in ds.variables:
            raise ValueError("checkpoint has no Times")
        times = np.asarray(ds.variables["Times"][0]).tobytes().decode("ascii").rstrip("\x00 ")
        if times != expected_time:
            raise ValueError(f"checkpoint Times={times}, expected {expected_time}")
        dimensions = {name: len(ds.dimensions[name]) for name in
                     ("west_east", "south_north", "bottom_top", "bottom_top_stag")}
        checkpoint_attrs = {name: ds.getncattr(name) for name in ("MP_PHYSICS", "USE_THETA_M")
                            if name in ds.ncattrs()}
        source_contract = verify_prep_source_contract(
            namelist.read_text(), checkpoint_attrs, dimensions, times)
        required = set(("THM_2", "QVAPOR", "MU_2", "MUB", "PH_2", "PHB", "C3H", "C4H",
                        "C3F", "C4F", "XLAND", "QCLOUD", "QRAIN", "QICE", "QSNOW", "QGRAUP",
                        "QNCCN", "QNCLOUD", "QNICE", "QNRAIN", "QIB"))
        missing = sorted(required - set(ds.variables))
        if missing:
            raise ValueError(f"checkpoint lacks required native endpoint fields: {missing}")
        for name in required:
            var = ds.variables[name]
            if np.dtype(var.dtype) != np.dtype("float32"):
                raise ValueError(f"{name} is not stored as native binary32")
            if any(attr in var.ncattrs() for attr in ("scale_factor", "add_offset")):
                raise ValueError(f"packed field {name} is unsupported")
        coeff = {name: np.asarray(ds.variables[name][0], dtype=np.float32).astype(np.float64)
                 for name in ("C3H", "C4H", "C3F", "C4F")}
        if coeff["C3H"].shape != (LEVELS,) or coeff["C3F"].shape != (LEVELS + 1,):
            raise ValueError("native hybrid coefficient shape mismatch")
        for start, stop in chunk_bounds(total, chunk_size):
            B = stop - start
            thm = _read_flat(ds.variables["THM_2"], start, stop, ny=ny, nx=nx, levels=LEVELS).astype(np.float64)
            qv = _read_flat(ds.variables["QVAPOR"], start, stop, ny=ny, nx=nx, levels=LEVELS).astype(np.float64)
            mu2 = _read_flat(ds.variables["MU_2"], start, stop, ny=ny, nx=nx, levels=None).astype(np.float32)
            mub = _read_flat(ds.variables["MUB"], start, stop, ny=ny, nx=nx, levels=None).astype(np.float32)
            mu_total = (mub + mu2).astype(np.float32).astype(np.float64)  # native f32 addition, then widen
            ph = _read_flat(ds.variables["PH_2"], start, stop, ny=ny, nx=nx, levels=LEVELS + 1).astype(np.float64)
            phb = _read_flat(ds.variables["PHB"], start, stop, ny=ny, nx=nx, levels=LEVELS + 1).astype(np.float64)
            xland = _read_flat(ds.variables["XLAND"], start, stop, ny=ny, nx=nx, levels=None)
            _check_finite("XLAND", xland)
            if not np.isin(xland, (1.0, 2.0)).all():
                raise ValueError("XLAND contains values outside native WRF categories {1,2}")
            _preflight(thm, qv, mu_total, ph, phb,
                       coeff["C3H"], coeff["C4H"], coeff["C3F"], coeff["C4F"], config)
            prep = _native_prep_batch(thm, qv, mu_total, ph, phb,
                                      coeff["C3H"], coeff["C4H"], coeff["C3F"], coeff["C4F"], config)
            raw_state_fields = [_read_flat(ds.variables[source], start, stop,
                                           ny=ny, nx=nx, levels=LEVELS)
                                for source in STATE_SOURCE[1:]]
            state, forcing, xland_packet = _packet_arrays(prep, raw_state_fields, xland)
            for name, values in zip(STATE_FIELDS, state):
                _check_finite(name, values)
                raw_negative_counts[name] += int((values < 0.0).sum())
            for name, values in zip(FORCING_FIELDS, forcing):
                _check_finite(name, values)
            if coverage[start:stop].any():
                raise AssertionError("duplicate flat-column coverage")
            coverage[start:stop] = 1
            indices = np.arange(start, stop, dtype=np.int32)
            chunk_name = f"chunk_{start:05d}_{stop:05d}.npz"
            chunk_path = output / chunk_name
            np.savez(chunk_path, state=state, forcing=forcing, xland=xland_packet,
                     flat_indices=indices, i=indices % nx, j=indices // nx)
            with np.load(chunk_path, allow_pickle=False) as stored:
                stored_state = stored["state"]
                stored_forcing = stored["forcing"]
                stored_xland = stored["xland"]
                if stored_state.dtype != np.float64 or stored_forcing.dtype != np.float64 or stored_xland.dtype != np.float64:
                    raise ValueError(f"{chunk_name} did not preserve the required binary64 packet dtype")
                if not (np.array_equal(stored_state, state) and
                        np.array_equal(stored_forcing, forcing) and
                        np.array_equal(stored_xland, xland_packet) and
                        np.array_equal(stored["flat_indices"], indices)):
                    raise ValueError(f"{chunk_name} readback differs from the prepared binary64 inputs")
                for local in (0, B // 2, B - 1):
                    if start in (0, (total // 2 // chunk_size) * chunk_size,
                                 ((total - 1) // chunk_size) * chunk_size):
                        recorded_samples.add(start + local)
                    _sample_check(stored_state, stored_forcing, local, thm, qv, mu_total, ph, phb,
                                  coeff["C3H"], coeff["C4H"], coeff["C3F"], coeff["C4F"], config)
                    sample_checks += 1
            chunks.append({"path": chunk_name, "start_flat": start, "stop_flat_exclusive": stop,
                           "columns": B, "sha256": sha256(chunk_path), "bytes": chunk_path.stat().st_size})
    if not np.all(coverage == 1):
        raise AssertionError(f"grid coverage incomplete: {int((coverage == 0).sum())} missing")
    # A representative list is deterministic and includes all chunk edges.
    samples = sorted(recorded_samples)
    summary = {
        "schema": "kdm6.ice_factorial_endpoint_preparation.v2",
        "status": "PREPARED_OFFLINE_ENDPOINT_INITIALIZED; SPLIT_PHYSICS_EXECUTION_PENDING",
        "interpretation": "Saved MP137 endpoint restart at 00:00:40 used as offline initial condition; not the actual next MP call and not a forecast step.",
        "execution": {"kdm6_forward": False, "wrf_or_host": False, "rttov": False,
                      "observation_cost": False, "split_physics_execution": "pending"},
        "source": {"checkpoint": str(checkpoint.resolve()), "checkpoint_sha256": sha256(checkpoint),
                   "namelist_output": str(namelist.resolve()), "namelist_output_sha256": sha256(namelist),
                   "config": str(CONFIG_PATH.relative_to(ROOT)), "config_sha256": sha256(CONFIG_PATH),
                   "checkpoint_times": expected_time, "grid": {"west_east": nx, "south_north": ny,
                   "mass_levels": LEVELS, "interface_levels": LEVELS + 1}},
        "source_preflight": source_contract,
        "mapping": {"state_order": list(STATE_FIELDS), "state_source": list(STATE_SOURCE),
                    "forcing_order": list(FORCING_FIELDS), "forcing_source": ["native_prep.rho", "native_prep.pii", "native_prep.pressure", "native_prep.delz"],
                    "number_basis": "research legacy raw restart operands; captured f32 values preserved; physical-number admission=false",
                    "mass_number_volume_convention_certified": False,
                    "mu_total": "float32(MUB + MU_2), native addition before widening",
                    "thermodynamic_lift": "continuous fp64 native_prep._intermediates batched with torch.vmap; native prep outputs and checkpoint values widened/preserved in binary64 packet",
                    "packet_dtype": "float64 for state[12,B,39], forcing[4,B,39], xland[B]; checkpoint f32 operands widen exactly, prep results remain f64",
                    "geometry": "PH_2/PHB and native C3H/C4H/C3F/C4F; no fixture remapping"},
        "coverage": {"columns_expected": total, "columns_written": int(coverage.sum()),
                     "missing": int((coverage == 0).sum()), "duplicate": 0,
                     "included_edges": True, "edge_qc": "all native columns passed positive finite prep preflight",
                     "sampled_1d_forward_columns": samples,
                     "sampled_1d_forward_checks": sample_checks,
                     "negative_raw_state_values_by_field": raw_negative_counts,
                     "negative_condensate_values_preserved": {
                         name: raw_negative_counts[name] for name in ("QC", "QR", "QI", "QS", "QG")}},
        "chunk_columns": chunk_size, "chunks": chunks,
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n")
    summary["manifest_sha256"] = sha256(manifest_path)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--namelist-output", type=Path, default=DEFAULT_NAMELIST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--chunk-columns", type=int, default=CHUNK_COLUMNS)
    args = parser.parse_args(argv)
    result = prepare(args.checkpoint, args.namelist_output, args.output, chunk_size=args.chunk_columns)
    print(json.dumps({k: result[k] for k in ("schema", "status", "coverage", "manifest_sha256")}, indent=2))


if __name__ == "__main__":
    main()
