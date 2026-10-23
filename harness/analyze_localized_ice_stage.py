#!/usr/bin/env python3
"""Audit saved localized B=512 actual-arrival ice stage traces.

This is a value-only reader of four already executed calls. It validates the
frozen request/response and source/trace receipts, then computes per-column
stage inventories using the actual request's fixed binary64 DEN*DELZ measure.
It never invokes KDM6, WRF, RTTOV, an optimizer or a derivative backend.
"""

from __future__ import annotations

import argparse
from io import BytesIO, StringIO
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
from typing import Iterable

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CASE_ROOT = Path(
    "/Users/yhlee/KDM6AD-k/host/research_evidence/localized_ice_stage_20261024_c2f9214a"
)
DEFAULT_MANIFEST = Path(
    "/Users/yhlee/KDM6AD-k/host/research_evidence/"
    "mp137_ice_factorial_20261023/domain_preparation_fp64_final/manifest.json"
)
DEFAULT_EXECUTABLE = Path(
    "/Users/yhlee/KDM6AD-k/host/research_evidence/"
    "mp137_ice_factorial_20261023/batch_tool_build/ice_factorial_batch"
)
DEFAULT_PRIOR_RUNS = Path(
    "/Users/yhlee/KDM6AD-k/host/research_evidence/mp137_domain_factorial_20261023/full"
)
DEFAULT_FINISH_REFERENCE = (
    ROOT / "harness/evidence/applied_finish_ad_2026-10-21/native39_finish_ad.json"
)
MODES = ("norm_actual", "raw_actual")
CHUNK_INDICES = (34, 40)
CHUNK_COLUMNS = 512
LEVELS = 39
TOTAL_COLUMNS = 65_988
NX, NY = 234, 282
WATER_FIELDS = ("QV", "QC", "QR", "QI", "QS", "QG")
WATER_TRACE_FIELDS = tuple(name.lower() + "_kg_kg" for name in WATER_FIELDS)
WATER_STAGES = ("pre_sed", "post_sed", "post_micro")
REQUEST_HEADER = struct.Struct("<8sIII3d")
EXPECTED_MANIFEST_SHA256 = (
    "24630a58b03e54d90cc4bb6c6167e0571b02d2d002095424b19789286914601d"
)
EXPECTED_TOOL_SHA256 = (
    "b8051d8b8c983dd91e98c98204d900b27da39054eceeb282d4f9e0025cf894e7"
)
EXPECTED_CONTROLLER_SHA256 = (
    "8599fbdc4eb6b6f338575f90d746116d50e3bee7d542be438b183650331f7689"
)
SELECTED_FLAT_INDICES = (17_662, 20_488)


class StageAuditError(ValueError):
    """Saved trace data or provenance does not satisfy the audit contract."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_record(line: str, *, source: str, line_number: int) -> dict[str, str]:
    """Parse one whitespace-separated key=value trace row without key loss."""
    row: dict[str, str] = {}
    for token in line.split():
        if "=" not in token:
            raise StageAuditError(f"{source}:{line_number}: token lacks '=': {token!r}")
        key, value = token.split("=", 1)
        if not key or key in row:
            raise StageAuditError(
                f"{source}:{line_number}: duplicate/empty key {key!r}"
            )
        row[key] = value
    if not row:
        raise StageAuditError(f"{source}:{line_number}: empty trace row")
    return row


def read_records(
    path: Path, verified_bytes: bytes | None = None
) -> list[dict[str, str]]:
    rows = []
    data = Path(path).read_bytes() if verified_bytes is None else verified_bytes
    with StringIO(data.decode("ascii")) as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                raise StageAuditError(f"{path.name}:{number}: blank trace row")
            rows.append(parse_record(line, source=path.name, line_number=number))
    return rows


def _text(row: dict[str, str], name: str) -> str:
    try:
        return row[name]
    except KeyError as exc:
        raise StageAuditError(f"trace row missing required field {name!r}") from exc


def _float(row: dict[str, str], name: str) -> float:
    try:
        value = float(row[name])
    except (KeyError, ValueError) as exc:
        raise StageAuditError(
            f"trace field {name!r} is missing or not numeric"
        ) from exc
    if not math.isfinite(value):
        raise StageAuditError(f"trace field {name!r} is nonfinite")
    return value


def _int(row: dict[str, str], name: str) -> int:
    value = _float(row, name)
    if value != int(value):
        raise StageAuditError(f"trace field {name!r} is not an integer")
    return int(value)


def same_bits(actual, expected) -> bool:
    a, b = np.asarray(actual), np.asarray(expected)
    return (
        a.shape == b.shape
        and a.dtype == np.float64
        and b.dtype == np.float64
        and np.array_equal(a.view(np.uint64), b.view(np.uint64))
    )


def parse_water_stage_rows(
    rows: Iterable[dict[str, str]],
    *,
    mode: str,
    batch: int,
    levels: int,
    forcing: np.ndarray,
) -> dict[str, np.ndarray]:
    """Parse exact stage order, bottom-first levels, and request density/depth."""
    rows = list(rows)
    expected_keys = [
        (stage, col, level)
        for stage in WATER_STAGES
        for col in range(batch)
        for level in range(levels)
    ]
    if len(rows) != len(expected_keys):
        raise StageAuditError(
            f"water trace has {len(rows)} rows; expected {len(expected_keys)}"
        )
    state = np.empty(
        (len(WATER_STAGES), len(WATER_FIELDS), batch, levels), dtype=np.float64
    )
    dend = np.empty((len(WATER_STAGES), batch, levels), dtype=np.float64)
    delz = np.empty_like(dend)
    seen = set()
    stage_index = {name: i for i, name in enumerate(WATER_STAGES)}
    for row, expected in zip(rows, expected_keys):
        if (
            _text(row, "schema") != "kdm6.ice_factorial_water_stage.v1"
            or _text(row, "record") != "water_stage"
        ):
            raise StageAuditError("unexpected water-stage schema/record")
        key = (_text(row, "stage"), _int(row, "column"), _int(row, "level_bottom0"))
        if key in seen:
            raise StageAuditError(f"duplicate water-stage row {key}")
        seen.add(key)
        if key != expected:
            raise StageAuditError(
                f"water-stage order/orientation mismatch: got {key}, expected {expected}"
            )
        stage, col, level = key
        if _text(row, "factor_mode") != mode:
            raise StageAuditError("water-stage factor mode differs from call receipt")
        if (
            _int(row, "subcycle") != 0
            or _int(row, "loops") != 1
            or _float(row, "dt_call_s") != 20.0
            or _float(row, "dtcld_s") != 20.0
        ):
            raise StageAuditError("water-stage timestep/subcycle metadata differs")
        si = stage_index[stage]
        dend[si, col, level] = _float(row, "DEND_kg_m3")
        delz[si, col, level] = _float(row, "DELZ_m")
        state[si, :, col, level] = [_float(row, name) for name in WATER_TRACE_FIELDS]
    if (
        not np.isfinite(state).all()
        or not np.isfinite(dend).all()
        or not np.isfinite(delz).all()
        or np.any(dend <= 0.0)
        or np.any(delz <= 0.0)
    ):
        raise StageAuditError(
            "water stages require finite states and positive DEN/DELZ"
        )
    if forcing.shape != (4, batch, levels):
        raise StageAuditError("request forcing shape differs from water stage grid")
    for si, stage in enumerate(WATER_STAGES):
        if not same_bits(dend[si], forcing[0]) or not same_bits(delz[si], forcing[3]):
            raise StageAuditError(
                f"{stage} density/thickness differs bitwise from actual request forcing"
            )
    return {"states": state, "dend": dend[0], "delz": delz[0]}


ICE_LAYER_FIELDS = (
    "QI_before_kg_kg",
    "QI_after_kg_kg",
    "out_applied_qi",
    "arrival_applied_qi",
    "out_attempt_qi",
    "falk_qi_code_value",
    "work1_qi",
    "workn_qi",
    "DEND_kg_m3",
    "DELZ_m",
    "DEND_safe_kg_m3",
    "DELZ_safe_m",
)


def parse_ice_layer_rows(
    rows: Iterable[dict[str, str]],
    *,
    mode: str,
    batch: int,
    levels: int,
    forcing: np.ndarray,
    water_states: np.ndarray,
) -> dict[str, np.ndarray]:
    """Parse top-first applied-transfer rows and map them to bottom-first levels."""
    rows = list(rows)
    if not rows:
        raise StageAuditError("ice-layer trace is empty")
    substeps = sorted({_int(row, "substep") for row in rows})
    if substeps != list(range(1, max(substeps) + 1)):
        raise StageAuditError("ice-layer substeps are missing or nonconsecutive")
    expected = [
        (step, top, col)
        for step in substeps
        for top in range(levels)
        for col in range(batch)
    ]
    if len(rows) != len(expected):
        raise StageAuditError(
            f"ice-layer trace has {len(rows)} rows; expected {len(expected)}"
        )
    data = {
        name: np.empty((len(substeps), batch, levels), dtype=np.float64)
        for name in ICE_LAYER_FIELDS
    }
    mstep = np.empty((len(substeps), batch, levels), dtype=np.int64)
    gate = np.empty_like(mstep)
    seen = set()
    for row, expected_key in zip(rows, expected):
        if (
            _text(row, "schema") != "kdm6.ice_factorial_layer.v1"
            or _text(row, "record") != "ice_factor_layer"
            or _text(row, "order") != "top_first"
            or _text(row, "recurrence") != "actual_departure"
            or _text(row, "factor_mode") != mode
        ):
            raise StageAuditError(
                "ice-layer schema/orientation/recurrence/mode mismatch"
            )
        step, top, col = (
            _int(row, "substep"),
            _int(row, "level_top0"),
            _int(row, "column"),
        )
        key = (step, top, col)
        if key in seen:
            raise StageAuditError(f"duplicate ice-layer row {key}")
        seen.add(key)
        if key != expected_key:
            raise StageAuditError(
                f"ice-layer order/orientation mismatch: got {key}, expected {expected_key}"
            )
        if _float(row, "dtcld_s") != 20.0:
            raise StageAuditError("ice-layer dtcld differs from the frozen call")
        bottom_level, si = levels - 1 - top, step - 1
        for name in ICE_LAYER_FIELDS:
            data[name][si, col, bottom_level] = _float(row, name)
        mstep[si, col, bottom_level] = _int(row, "mstep")
        gate[si, col, bottom_level] = _int(row, "gate")
        if (
            gate[si, col, bottom_level] not in (0, 1)
            or mstep[si, col, bottom_level] < step
        ):
            raise StageAuditError("ice-layer gate/mstep metadata is inconsistent")
        if (
            data["DEND_kg_m3"][si, col, bottom_level] <= 0
            or data["DELZ_m"][si, col, bottom_level] <= 0
            or data["DEND_safe_kg_m3"][si, col, bottom_level] <= 0
            or data["DELZ_safe_m"][si, col, bottom_level] <= 0
        ):
            raise StageAuditError("ice-layer density/thickness must be positive")
    if any(not np.isfinite(a).all() for a in data.values()):
        raise StageAuditError("ice-layer trace contains nonfinite values")
    if not same_bits(data["DEND_kg_m3"][0], forcing[0]) or not same_bits(
        data["DELZ_m"][0], forcing[3]
    ):
        raise StageAuditError(
            "ice-layer DEN/DELZ differs from request after orientation map"
        )
    before, after = data["QI_before_kg_kg"], data["QI_after_kg_kg"]
    if not same_bits(before[0], water_states[0, 3]):
        raise StageAuditError("first ice QI_before differs from pre_sed water stage")
    for si in range(1, len(substeps)):
        if not same_bits(before[si], after[si - 1]):
            raise StageAuditError("ice substeps do not carry QI exactly")
    if not same_bits(after[-1], water_states[1, 3]):
        raise StageAuditError("last ice QI_after differs from post_sed water stage")
    if np.any(data["arrival_applied_qi"][:, :, -1] != 0.0):
        raise StageAuditError("top ice layer has nonzero above-boundary arrival")
    return {
        "substeps": np.asarray(substeps, dtype=np.int32),
        "mstep": mstep,
        "gate": gate,
        **data,
    }


def parse_common_ice_rows(
    rows: Iterable[dict[str, str]],
    *,
    mode: str,
    batch: int,
    levels: int,
    forcing: np.ndarray,
    precip: np.ndarray,
) -> dict:
    """Validate common velocity/bottom records; never equate raw fall with applied export."""
    rows = list(rows)
    velocity = [r for r in rows if r.get("record") == "ice_velocity"]
    bottom = [r for r in rows if r.get("record") == "ice_bottom"]
    if len(velocity) != 2 * batch * levels or len(bottom) != batch:
        raise StageAuditError(
            "common ice trace record counts are incomplete or duplicated"
        )
    stages = ("runtime_input_normalized", "post_main_handoff")
    # The runtime emits velocity rows stage → column → top-first level.
    expected = [
        (stage, col, level)
        for stage in stages
        for col in range(batch)
        for level in range(levels)
    ]
    seen = set()
    for row, exp in zip(velocity, expected):
        if (
            _text(row, "schema") != "kdm6.ice_boundary_trace.v1"
            or _text(row, "order") != "top_first"
        ):
            raise StageAuditError("ice velocity schema/orientation mismatch")
        key = (_text(row, "stage"), _int(row, "column"), _int(row, "level_top0"))
        if key in seen or key != exp:
            raise StageAuditError(f"ice velocity order/duplicate mismatch: {key}")
        seen.add(key)
        if _float(row, "dtcld_s") != 20.0:
            raise StageAuditError("ice velocity dtcld differs")
        expected_basis = (
            "vt_over_delz"
            if key[0] == "runtime_input_normalized" or mode == "norm_actual"
            else "raw_vt"
        )
        if _text(row, "basis") != expected_basis:
            raise StageAuditError("ice velocity basis differs from mode")
        col, top = key[1], key[2]
        level = levels - 1 - top
        if (
            _float(row, "DEND_kg_m3") != forcing[0, col, level]
            or _float(row, "DELZ_m") != forcing[3, col, level]
        ):
            raise StageAuditError(
                "ice velocity measure differs from request after orientation map"
            )
        for name in ("work1_qi", "workn_qi", "mstep"):
            _float(row, name)
        if key[0] == "runtime_input_normalized":
            _float(row, "mstepmax")
    bottom_data = {}
    for col, row in enumerate(bottom):
        if (
            _text(row, "schema") != "kdm6.ice_boundary_trace.v1"
            or _text(row, "order") != "top_first"
            or _int(row, "column") != col
            or _int(row, "bottom_top0") != levels - 1
            or _int(row, "levels") != levels
        ):
            raise StageAuditError(
                "ice bottom row missing, duplicate or wrongly oriented"
            )
        if (
            _float(row, "dtcld_s") != 20.0
            or _float(row, "DELZ_bottom_m") != forcing[3, col, 0]
        ):
            raise StageAuditError(
                "ice-bottom thickness differs from bottom request level"
            )
        total_names = (
            "rain_increment_total_mm",
            "snow_ice_subset_mm",
            "graupel_subset_mm",
        )
        total = [_float(row, name) for name in total_names]
        if not np.array_equal(
            np.asarray(total, dtype=np.float64).view(np.uint64),
            precip[:, col].view(np.uint64),
        ):
            raise StageAuditError(
                "ice-bottom precip diagnostic differs from response; total/subsets must not be recombined"
            )
        bottom_data[col] = dict(row)
    return {"bottom": bottom_data, "velocity_records": len(velocity)}


def rounded_mass_inventory(
    state: np.ndarray, density: np.ndarray, thickness: np.ndarray
) -> np.ndarray:
    """Field-by-column fixed-measure inventory using rounded products plus fsum."""
    s, d, z = (np.asarray(x, dtype=np.float64) for x in (state, density, thickness))
    if s.ndim != 3 or d.shape != s.shape[1:] or z.shape != s.shape[1:]:
        raise StageAuditError("mass state and measure shapes differ")
    if (
        any(not np.isfinite(x).all() for x in (s, d, z))
        or np.any(d <= 0)
        or np.any(z <= 0)
    ):
        raise StageAuditError(
            "mass inventory requires finite states and positive DEN/DELZ"
        )
    w = d * z
    return np.asarray(
        [
            [
                math.fsum(
                    float(s[field, col, k] * w[col, k]) for k in range(s.shape[2])
                )
                for col in range(s.shape[1])
            ]
            for field in range(s.shape[0])
        ],
        dtype=np.float64,
    )


def rounded_total_mass_change(
    state_delta: np.ndarray, density: np.ndarray, thickness: np.ndarray
) -> np.ndarray:
    """Sum rounded delta×DEN×DELZ products across species and levels per column."""
    delta, d, z = (
        np.asarray(x, dtype=np.float64) for x in (state_delta, density, thickness)
    )
    if delta.ndim != 3 or d.shape != delta.shape[1:] or z.shape != delta.shape[1:]:
        raise StageAuditError("mass change and measure shapes differ")
    if (
        any(not np.isfinite(x).all() for x in (delta, d, z))
        or np.any(d <= 0)
        or np.any(z <= 0)
    ):
        raise StageAuditError(
            "mass change requires finite states and positive DEN/DELZ"
        )
    weights = d * z
    return np.asarray(
        [
            math.fsum(
                float(delta[f, c, k] * weights[c, k])
                for f in range(delta.shape[0])
                for k in range(delta.shape[2])
            )
            for c in range(delta.shape[1])
        ],
        dtype=np.float64,
    )


def ice_transfer_budget(
    pre_qi: np.ndarray,
    post_qi: np.ndarray,
    departure: np.ndarray,
    arrival: np.ndarray,
    weights: np.ndarray,
) -> dict:
    """Separate QI inventory, applied bottom departure and arrival amounts."""
    pre, post, dep, arr, w = (
        np.asarray(x, dtype=np.float64)
        for x in (pre_qi, post_qi, departure, arrival, weights)
    )
    if pre.ndim != 2 or any(x.shape != pre.shape for x in (post, dep, arr, w)):
        raise StageAuditError("QI transfer inputs must share shape (B,L)")
    if any(not np.isfinite(x).all() for x in (pre, post, dep, arr, w)) or np.any(
        w <= 0
    ):
        raise StageAuditError(
            "QI transfer inputs require finite values and positive measure"
        )
    if (
        np.any(pre < 0)
        or np.any(post < 0)
        or np.any(dep < 0)
        or np.any(arr < 0)
        or np.any(arr[:, -1] != 0)
    ):
        raise StageAuditError(
            "QI transfer states/departures/arrivals outside trace contract"
        )
    B, L = pre.shape
    out = {
        k: np.empty(B, dtype=np.float64)
        for k in (
            "state_change",
            "actual_bottom_departure",
            "bottom_net_depletion",
            "total_departure",
            "total_arrival",
            "transfer_identity_residual",
            "ice_boundary_residual",
            "roundoff_gate",
        )
    }
    eps = np.finfo(np.float64).eps
    for c in range(B):
        delta = math.fsum(float((post[c, k] - pre[c, k]) * w[c, k]) for k in range(L))
        total_dep = math.fsum(float(dep[c, k] * w[c, k]) for k in range(L))
        total_arr = math.fsum(float(arr[c, k] * w[c, k]) for k in range(L))
        bottom = float(dep[c, 0] * w[c, 0])
        out["state_change"][c] = delta
        out["actual_bottom_departure"][c] = bottom
        out["bottom_net_depletion"][c] = float((pre[c, 0] - post[c, 0]) * w[c, 0])
        out["total_departure"][c] = total_dep
        out["total_arrival"][c] = total_arr
        out["transfer_identity_residual"][c] = math.fsum((delta, total_dep, -total_arr))
        out["ice_boundary_residual"][c] = math.fsum((delta, bottom))
        scale = (
            math.fsum(
                float((abs(pre[c, k]) + abs(post[c, k])) * w[c, k]) for k in range(L)
            )
            + abs(total_dep)
            + abs(total_arr)
        )
        out["roundoff_gate"][c] = 256 * eps * max(scale, 1e-30)
    return out


def distribution(values: np.ndarray) -> dict:
    x = np.asarray(values, dtype=np.float64).reshape(-1)
    if not x.size or not np.isfinite(x).all():
        raise StageAuditError("statistics require finite nonempty values")
    a = np.sort(x, kind="stable")
    return {
        "count": int(x.size),
        "min": float(a[0]),
        "max": float(a[-1]),
        "unweighted_column_mean": math.fsum(float(v) for v in x) / x.size,
        "rank_p01": float(a[int(0.01 * (x.size - 1))]),
        "rank_p50": float(a[int(0.5 * (x.size - 1))]),
        "rank_p99": float(a[int(0.99 * (x.size - 1))]),
    }


def _decode_request(data: bytes) -> tuple[dict, np.ndarray, np.ndarray, np.ndarray]:
    if len(data) < REQUEST_HEADER.size:
        raise StageAuditError("request shorter than fixed header")
    magic, version, batch, levels, dt, nc_land, nc_sea = REQUEST_HEADER.unpack_from(
        data
    )
    if (
        magic != b"K6BATI1\0"
        or version != 1
        or batch != CHUNK_COLUMNS
        or levels != LEVELS
        or (dt, nc_land, nc_sea) != (20.0, 10.0, 10.0)
    ):
        raise StageAuditError("request header differs from frozen localized call")
    cells = batch * levels
    expected = REQUEST_HEADER.size + (12 * cells + 4 * cells + batch) * 8
    if len(data) != expected:
        raise StageAuditError("request byte length differs from B,L")
    pos = REQUEST_HEADER.size
    state = (
        np.frombuffer(data, dtype="<f8", count=12 * cells, offset=pos)
        .copy()
        .reshape(12, batch, levels)
    )
    pos += 12 * cells * 8
    forcing = (
        np.frombuffer(data, dtype="<f8", count=4 * cells, offset=pos)
        .copy()
        .reshape(4, batch, levels)
    )
    pos += 4 * cells * 8
    xland = np.frombuffer(data, dtype="<f8", count=batch, offset=pos).copy()
    if (
        not all(np.isfinite(x).all() for x in (state, forcing, xland))
        or np.any(forcing <= 0.0)
        or not np.isin(xland, (1.0, 2.0)).all()
    ):
        raise StageAuditError(
            "request arrays are nonfinite or outside their admitted domain"
        )
    return (
        {"dt_seconds": dt, "ncmin_land": nc_land, "ncmin_sea": nc_sea},
        state,
        forcing,
        xland,
    )


def _load_source_chunk(
    manifest_path: Path,
    entry: dict,
    *,
    expected_sha: str,
    request_state: np.ndarray,
    request_forcing: np.ndarray,
    request_xland: np.ndarray,
) -> dict:
    path = (manifest_path.parent / entry["path"]).resolve()
    if not path.is_relative_to(manifest_path.parent.resolve()):
        raise StageAuditError("packet chunk path escapes prepared-data directory")
    data = path.read_bytes()
    if sha256_bytes(data) != expected_sha or expected_sha != entry.get("sha256"):
        raise StageAuditError(
            "source chunk hash differs from final manifest/execution receipt"
        )
    with np.load(BytesIO(data), allow_pickle=False) as z:
        required = {"state", "forcing", "xland", "flat_indices", "i", "j"}
        if set(z.files) != required:
            raise StageAuditError("prepared chunk field set differs from packet schema")
        if any(z[name].dtype != np.float64 for name in ("state", "forcing", "xland")):
            raise StageAuditError("prepared state/forcing/xland must be binary64")
        if not (
            same_bits(z["state"], request_state)
            and same_bits(z["forcing"], request_forcing)
            and same_bits(z["xland"], request_xland)
        ):
            raise StageAuditError(
                "request bytes differ from the verified source packet tensors"
            )
        start, end = entry["start_flat"], entry["stop_flat_exclusive"]
        flat = z["flat_indices"]
        if (
            not np.array_equal(flat, np.arange(start, end, dtype=flat.dtype))
            or not np.array_equal(z["i"], flat % NX)
            or not np.array_equal(z["j"], flat // NX)
            or flat.shape != (CHUNK_COLUMNS,)
        ):
            raise StageAuditError(
                "source chunk flat indices/i,j disagree with native C-order"
            )
    return {
        "path_identifier": entry["path"],
        "sha256": expected_sha,
        "start_flat": entry["start_flat"],
        "stop_flat_exclusive": entry["stop_flat_exclusive"],
    }


def analyze(
    case_root: Path = CASE_ROOT,
    output: Path | None = None,
    manifest_path: Path = DEFAULT_MANIFEST,
    executable: Path = DEFAULT_EXECUTABLE,
    prior_run_root: Path = DEFAULT_PRIOR_RUNS,
    finish_reference: Path = DEFAULT_FINISH_REFERENCE,
):
    """Audit the four saved trace-on calls and write only to fresh private output."""
    from harness.run_domain_ice_factorial import build_plan

    case_root, manifest_path, executable, prior_run_root, finish_reference = map(
        Path, (case_root, manifest_path, executable, prior_run_root, finish_reference)
    )
    if output is None:
        output = case_root / "stage_analysis"
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise StageAuditError(f"analysis output must be a fresh directory: {output}")
    execution = json.loads((case_root / "execution.json").read_text())
    prepared = json.loads((case_root / "prepared.json").read_text())
    controller_path = case_root / "controller.py"
    controller_sha = sha256_file(controller_path)
    if (
        controller_sha != prepared.get("controller_sha256")
        or controller_sha != execution.get("controller_sha256")
        or controller_sha != EXPECTED_CONTROLLER_SHA256
    ):
        raise StageAuditError(
            "controller source identity differs from its prepared/execution receipts"
        )
    if (
        prepared.get("calls_planned") != 4
        or prepared.get("B") != CHUNK_COLUMNS
        or prepared.get("L") != LEVELS
        or prepared.get("dt") != 20
    ):
        raise StageAuditError("prepared localized call contract differs")
    expected_modes = {"norm_actual", "raw_actual"}
    expected_indices = {34, 40}
    if (
        set(prepared.get("modes", [])) != expected_modes
        or set(prepared.get("indices", [])) != expected_indices
    ):
        raise StageAuditError(
            "prepared mode/chunk selections differ from the localized four-call design"
        )
    if execution.get("calls") != 4 or len(execution.get("receipts", [])) != 4:
        raise StageAuditError(
            "execution receipt must contain exactly four captured calls"
        )
    if manifest_path.is_file() is False or executable.is_file() is False:
        raise StageAuditError("prepared manifest or executable is missing")
    manifest_sha = sha256_file(manifest_path)
    tool_sha = sha256_file(executable)
    manifest = json.loads(manifest_path.read_text())
    plans = {
        mode: build_plan(
            manifest_path,
            executable,
            mode=mode,
            workers=10,
            dt=20.0,
            ncmin_land=10.0,
            ncmin_sea=10.0,
        )
        for mode in MODES
    }
    if manifest_sha != EXPECTED_MANIFEST_SHA256 or tool_sha != EXPECTED_TOOL_SHA256:
        raise StageAuditError(
            "final packet/tool SHA differs from the frozen run identity"
        )
    finish = json.loads(finish_reference.read_text())
    if (
        finish.get("zero_out", {}).get("mode") != 2
        or finish.get("configuration", {}).get("dt") != 20.0
    ):
        raise StageAuditError(
            "offline cleanup reference differs from dt20/interior mode-2 contract"
        )
    receipts = execution["receipts"]
    expected_keys = {(mode, index) for mode in MODES for index in CHUNK_INDICES}
    actual_keys = [(r.get("mode"), r.get("batch_index")) for r in receipts]
    if len(set(actual_keys)) != len(actual_keys) or set(actual_keys) != expected_keys:
        raise StageAuditError(
            "execution receipts are duplicate or do not cover the four selected cases"
        )
    by_key = {(r["mode"], r["batch_index"]): r for r in receipts}
    case_results = {}
    case_arrays = {}
    selected_columns = {}
    request_by_chunk = {}
    for mode, index in sorted(expected_keys):
        plan_row = plans[mode]["chunks"][index]
        rec = by_key[(mode, index)]
        if (
            rec.get("manifest_sha256") != manifest_sha
            or rec.get("tool_sha256") != tool_sha
        ):
            raise StageAuditError("execution receipt manifest/tool pin differs")
        start = plan_row["start"]
        case = case_root / f"{mode}_chunk{index:03d}"
        receipt_path = case / "receipt.json"
        case_receipt = json.loads(receipt_path.read_text())
        if case_receipt != rec:
            raise StageAuditError("execution.json and case receipt differ")
        if (
            rec.get("B"),
            rec.get("L"),
            rec.get("start_flat"),
            rec.get("stop_flat_exclusive"),
        ) != (CHUNK_COLUMNS, LEVELS, start, start + CHUNK_COLUMNS):
            raise StageAuditError(
                "receipt B/L/native extent differs from fixed selected batch"
            )
        if (
            rec.get("KDM_calls"),
            rec.get("native_host_steps"),
            rec.get("RTTOV_calls"),
        ) != (1, 0, 0):
            raise StageAuditError("trace receipt call/host/RTTOV attribution differs")
        if not rec.get("trace_on_matches_prior_trace_off_bytes"):
            raise StageAuditError(
                "trace-on response is not byte-identical to prior trace-off response"
            )
        request_path = case / "request.bin"
        response_path = case / "response.bin"
        log_path = case / "resource.log"
        request_bytes = request_path.read_bytes()
        response_bytes = response_path.read_bytes()
        if (
            sha256_bytes(request_bytes) != rec["request_sha256"]
            or sha256_bytes(response_bytes) != rec["response_sha256"]
        ):
            raise StageAuditError(
                "request/response bytes differ from controller receipt"
            )
        prior_receipt_path = prior_run_root / mode / f"chunk-{index:05d}.receipt.json"
        prior_response_path = prior_run_root / mode / f"chunk-{index:05d}.response.bin"
        prior = json.loads(prior_receipt_path.read_text())
        if (
            prior.get("request_sha256") != rec["request_sha256"]
            or prior.get("response_sha256") != rec["response_sha256"]
            or prior.get("tool_sha256") != tool_sha
            or prior_response_path.read_bytes() != response_bytes
        ):
            raise StageAuditError(
                "trace-on call is not the pinned prior trace-off request/response"
            )
        expected_trace_files = ("ice.tsv", "ice.tsv.layers.tsv", "ice.tsv.water.tsv")
        trace_buffers = {}
        for name in expected_trace_files:
            path = case / name
            pin = rec.get("traces", {}).get(name)
            content = path.read_bytes()
            if (
                not pin
                or sha256_bytes(content) != pin["sha256"]
                or len(content) != pin["bytes"]
            ):
                raise StageAuditError(
                    f"trace artifact hash/length differs from receipt: {name}"
                )
            trace_buffers[name] = content
        if sha256_file(log_path) != rec.get("log_sha256"):
            raise StageAuditError("resource log hash differs from trace receipt")
        _, state, forcing, xland = _decode_request(request_bytes)
        source_entry = manifest["chunks"][index]
        source_info = _load_source_chunk(
            manifest_path,
            source_entry,
            expected_sha=rec["source_chunk_sha256"],
            request_state=state,
            request_forcing=forcing,
            request_xland=xland,
        )
        if plans[mode]["chunks"][index]["source_sha256"] != rec["source_chunk_sha256"]:
            raise StageAuditError("source chunk hash differs from admitted batch plan")
        old = request_by_chunk.setdefault(index, request_bytes)
        if old != request_bytes:
            raise StageAuditError(
                "factorial modes do not share identical frozen per-chunk requests"
            )
        from harness.ice_factorial_batch import unpack_response

        response = unpack_response(response_bytes)
        if (
            response["B"] != CHUNK_COLUMNS
            or response["L"] != LEVELS
            or not same_bits(response["state_in"], state)
            or not same_bits(response["forcing_in"], forcing)
        ):
            raise StageAuditError(
                "response echoed operands differ from the verified request"
            )
        water = parse_water_stage_rows(
            read_records(
                case / "ice.tsv.water.tsv", trace_buffers["ice.tsv.water.tsv"]
            ),
            mode=mode,
            batch=CHUNK_COLUMNS,
            levels=LEVELS,
            forcing=forcing,
        )
        stages = water["states"]
        if not same_bits(stages[0], state[1:7]):
            raise StageAuditError("pre_sed water fields differ from request input")
        if not same_bits(stages[2], response["state_out"][1:7]):
            raise StageAuditError("post_micro water fields differ from response output")
        if not same_bits(stages[0, 0:2], stages[1, 0:2]):
            raise StageAuditError("QV/QC changed between pre_sed and post_sed")
        layer = parse_ice_layer_rows(
            read_records(
                case / "ice.tsv.layers.tsv", trace_buffers["ice.tsv.layers.tsv"]
            ),
            mode=mode,
            batch=CHUNK_COLUMNS,
            levels=LEVELS,
            forcing=forcing,
            water_states=stages,
        )
        common = parse_common_ice_rows(
            read_records(case / "ice.tsv", trace_buffers["ice.tsv"]),
            mode=mode,
            batch=CHUNK_COLUMNS,
            levels=LEVELS,
            forcing=forcing,
            precip=response["precip"],
        )
        dend, delz = water["dend"], water["delz"]
        weights = dend * delz
        inventories = np.stack(
            [rounded_mass_inventory(stages[i], dend, delz) for i in range(3)], axis=0
        )
        zero = finish["zero_out"]
        threshold = float(zero["threshold"])
        clean = stages[2].copy()
        clean[0] = np.maximum(clean[0], 0.0)
        clean[1:] = np.where(clean[1:] < threshold, 0.0, clean[1:])
        clean_inventory = rounded_mass_inventory(clean, dend, delz)
        main_delta = rounded_mass_inventory(stages[1] - stages[0], dend, delz)
        micro_delta = rounded_mass_inventory(stages[2] - stages[1], dend, delz)
        cleanup_delta = rounded_mass_inventory(clean - stages[2], dend, delz)
        total_change = rounded_total_mass_change(stages[2] - stages[0], dend, delz)
        precip = response["precip"]
        residual = total_change + precip[0]
        applied_out = np.asarray(
            [
                [
                    math.fsum(
                        float(layer["out_applied_qi"][s, c, k])
                        for s in range(len(layer["substeps"]))
                    )
                    for k in range(LEVELS)
                ]
                for c in range(CHUNK_COLUMNS)
            ],
            dtype=np.float64,
        )
        applied_arrival = np.asarray(
            [
                [
                    math.fsum(
                        float(layer["arrival_applied_qi"][s, c, k])
                        for s in range(len(layer["substeps"]))
                    )
                    for k in range(LEVELS)
                ]
                for c in range(CHUNK_COLUMNS)
            ],
            dtype=np.float64,
        )
        ice = ice_transfer_budget(
            stages[0, 3], stages[1, 3], applied_out, applied_arrival, weights
        )
        layer_update_resid = np.zeros(CHUNK_COLUMNS)
        for c in range(CHUNK_COLUMNS):
            local = []
            for sidx in range(len(layer["substeps"])):
                for k in range(LEVELS):
                    q0 = layer["QI_before_kg_kg"][sidx, c, k]
                    q1 = layer["QI_after_kg_kg"][sidx, c, k]
                    outq = layer["out_applied_qi"][sidx, c, k]
                    arrq = layer["arrival_applied_qi"][sidx, c, k]
                    local.append(abs(float(q1 - (q0 - outq + arrq))))
            layer_update_resid[c] = max(local, default=0.0)
        local_scale = np.maximum(
            np.max(np.abs(layer["QI_before_kg_kg"]), axis=(0, 2)), 1e-30
        )
        local_gate = 64 * np.finfo(np.float64).eps * local_scale
        if np.any(layer_update_resid > local_gate):
            raise StageAuditError("ice applied-out/arrival state update identity fails")
        bottom = common["bottom"]
        bottom_actual = np.asarray(ice["actual_bottom_departure"])
        bottom_net = np.asarray(ice["bottom_net_depletion"])
        bottom_arrival = np.asarray(
            [
                math.fsum(
                    float(layer["arrival_applied_qi"][s, c, 0] * weights[c, 0])
                    for s in range(len(layer["substeps"]))
                )
                for c in range(CHUNK_COLUMNS)
            ]
        )
        bottom_report = np.asarray(
            [
                _float(bottom[c], "fall_qi_bottom_kg_m3_s")
                * _float(bottom[c], "DELZ_bottom_m")
                * _float(bottom[c], "dtcld_s")
                for c in range(CHUNK_COLUMNS)
            ]
        )
        nonzero_pre_post = {
            field: int(
                np.count_nonzero(
                    stages[0, i].view(np.uint64) != stages[1, i].view(np.uint64)
                )
            )
            for i, field in enumerate(WATER_FIELDS)
        }
        if nonzero_pre_post["QV"] or nonzero_pre_post["QC"]:
            raise StageAuditError(
                "unexpected vapor/cloud changes across pre_sed/post_sed"
            )
        selected = {}
        for flat in SELECTED_FLAT_INDICES:
            if start <= flat < start + CHUNK_COLUMNS:
                col = flat - start
                selected[str(flat)] = {
                    "flat_index": flat,
                    "i0": flat % NX,
                    "j0": flat // NX,
                    "i_fortran": flat % NX + 1,
                    "j_fortran": flat // NX + 1,
                    "chunk_index": index,
                    "chunk_local_column": col,
                    "mode": mode,
                    "water_fields": list(WATER_FIELDS),
                    "DEND_kg_m3": dend[col].tolist(),
                    "DELZ_m": delz[col].tolist(),
                    "DENxDELZ_kg_m2": weights[col].tolist(),
                    "states_bottomfirst": {
                        st: {
                            f: stages[si, fi, col].tolist()
                            for fi, f in enumerate(WATER_FIELDS)
                        }
                        for si, st in enumerate(WATER_STAGES)
                    },
                    "uniform_cleanup_threshold": threshold,
                    "uniform_cleanup_state_bottomfirst": {
                        f: clean[fi, col].tolist() for fi, f in enumerate(WATER_FIELDS)
                    },
                    "inventories_kg_m2": {
                        f: {
                            st: float(inventories[si, fi, col])
                            for si, st in enumerate(WATER_STAGES)
                        }
                        for fi, f in enumerate(WATER_FIELDS)
                    },
                    "stage_changes_kg_m2": {
                        "pre_to_post_sed": {
                            f: float(main_delta[fi, col])
                            for fi, f in enumerate(WATER_FIELDS)
                        },
                        "post_sed_to_post_micro": {
                            f: float(micro_delta[fi, col])
                            for fi, f in enumerate(WATER_FIELDS)
                        },
                        "post_micro_to_cleanup": {
                            f: float(cleanup_delta[fi, col])
                            for fi, f in enumerate(WATER_FIELDS)
                        },
                    },
                    "precipitation_mm": {
                        "total_once": float(precip[0, col]),
                        "snow_ice_subset": float(precip[1, col]),
                        "graupel_subset": float(precip[2, col]),
                    },
                    "six_species_change_plus_total_precip_residual_kg_m2": float(
                        residual[col]
                    ),
                    "ice_bottom": {
                        "actual_departure_kg_m2": float(bottom_actual[col]),
                        "bottom_net_state_depletion_kg_m2": float(bottom_net[col]),
                        "applied_arrival_kg_m2": float(bottom_arrival[col]),
                        "raw_code_report_increment": float(bottom_report[col]),
                        "reported_minus_applied": float(
                            bottom_report[col] - bottom_actual[col]
                        ),
                    },
                    "ice_layers_topfirst": [
                        {
                            "level_top0": top,
                            "level_bottom0": LEVELS - 1 - top,
                            "substeps": [
                                {
                                    "substep": int(step),
                                    "QI_before_kg_kg": float(
                                        layer["QI_before_kg_kg"][
                                            si, col, LEVELS - 1 - top
                                        ]
                                    ),
                                    "out_applied_qi_kg_kg": float(
                                        layer["out_applied_qi"][
                                            si, col, LEVELS - 1 - top
                                        ]
                                    ),
                                    "arrival_applied_qi_kg_kg": float(
                                        layer["arrival_applied_qi"][
                                            si, col, LEVELS - 1 - top
                                        ]
                                    ),
                                    "QI_after_kg_kg": float(
                                        layer["QI_after_kg_kg"][
                                            si, col, LEVELS - 1 - top
                                        ]
                                    ),
                                    "falk_qi_code_value": float(
                                        layer["falk_qi_code_value"][
                                            si, col, LEVELS - 1 - top
                                        ]
                                    ),
                                }
                                for si, step in enumerate(layer["substeps"])
                            ],
                        }
                        for top in range(LEVELS)
                    ],
                    "scope_note": "State/transfer diagnostics; raw-falk physical dimensions conditional; no inner-rain causal attribution.",
                }
        metrics = {
            "mode": mode,
            "batch_index": index,
            "start_flat": start,
            "stop_flat_exclusive": start + CHUNK_COLUMNS,
            "columns": CHUNK_COLUMNS,
            "levels": LEVELS,
            "water_trace_rows": 3 * CHUNK_COLUMNS * LEVELS,
            "ice_layer_trace_rows": len(
                read_records(
                    case / "ice.tsv.layers.tsv", trace_buffers["ice.tsv.layers.tsv"]
                )
            ),
            "ice_bottom_records": len(bottom),
            "substeps": layer["substeps"].tolist(),
            "mstep_min": int(layer["mstep"].min()),
            "mstep_max": int(layer["mstep"].max()),
            "pre_sed_matches_input_bitwise": True,
            "post_micro_matches_output_bitwise": True,
            "post_sed_QV_QC_unchanged_bitwise": True,
            "pre_to_post_sed_nonzero_cells": nonzero_pre_post,
            "inventory_by_field_kg_m2": {
                f: {
                    st: distribution(inventories[si, fi])
                    for si, st in enumerate(WATER_STAGES)
                }
                for fi, f in enumerate(WATER_FIELDS)
            },
            "stage_delta_by_field_kg_m2": {
                "pre_to_post_sed": {
                    f: distribution(main_delta[fi]) for fi, f in enumerate(WATER_FIELDS)
                },
                "post_sed_to_post_micro": {
                    f: distribution(micro_delta[fi])
                    for fi, f in enumerate(WATER_FIELDS)
                },
                "post_micro_to_uniform_cleanup": {
                    f: distribution(cleanup_delta[fi])
                    for fi, f in enumerate(WATER_FIELDS)
                },
            },
            "six_species_change_plus_total_precip_residual_kg_m2": distribution(
                residual
            ),
            "precipitation_total_once_mm": distribution(precip[0]),
            "snow_ice_subset_mm": distribution(precip[1]),
            "graupel_subset_mm": distribution(precip[2]),
            "ice_QI_inventory_change_kg_m2": distribution(ice["state_change"]),
            "ice_QI_actual_bottom_departure_kg_m2": distribution(bottom_actual),
            "ice_QI_bottom_net_state_depletion_kg_m2": distribution(bottom_net),
            "ice_QI_bottom_arrival_kg_m2": distribution(bottom_arrival),
            "ice_QI_raw_bottom_report_increment_code_value": distribution(
                bottom_report
            ),
            "ice_QI_report_minus_applied_bottom_departure": distribution(
                bottom_report - bottom_actual
            ),
            "ice_QI_state_change_plus_bottom_outflow_residual_kg_m2": distribution(
                ice["ice_boundary_residual"]
            ),
            "ice_QI_transfer_identity_residual_kg_m2": distribution(
                ice["transfer_identity_residual"]
            ),
            "ice_QI_roundoff_gate_kg_m2": distribution(ice["roundoff_gate"]),
            "ice_QI_within_roundoff_gate_count": int(
                np.count_nonzero(
                    abs(ice["ice_boundary_residual"]) <= ice["roundoff_gate"]
                )
            ),
            "ice_layer_state_update_residual_maxabs": float(layer_update_resid.max()),
            "ice_layer_state_update_gate_max": float(local_gate.max()),
            "receipts": source_info,
            "calls": {
                "prior_trace_call": 1,
                "analysis_added_KDM_calls": 0,
                "host_steps": 0,
                "RTTOV_calls": 0,
            },
            "interpretation_limits": [
                "No inner-rain causal attribution.",
                "Raw velocity/code-flux dimensions remain conditional.",
                "Ice residual is a fixed-measure diagnostic, not physical conservation certification.",
            ],
        }
        arrays = {
            "water_stage_state_bottomfirst": stages,
            "DEND_kg_m3": dend,
            "DELZ_m": delz,
            "measure_DENxDELZ_kg_m2": weights,
            "stage_inventory_kg_m2": inventories,
            "uniform_cleanup_inventory_kg_m2": clean_inventory,
            "pre_to_post_sed_delta_kg_m2": main_delta,
            "post_sed_to_post_micro_delta_kg_m2": micro_delta,
            "post_micro_to_cleanup_delta_kg_m2": cleanup_delta,
            "precip_total_snowice_graupel_mm": precip,
            "ice_QI_out_applied_bottomfirst": layer["out_applied_qi"],
            "ice_QI_arrival_applied_bottomfirst": layer["arrival_applied_qi"],
            "ice_QI_before_bottomfirst": layer["QI_before_kg_kg"],
            "ice_QI_after_bottomfirst": layer["QI_after_kg_kg"],
            "ice_QI_actual_bottom_departure_kg_m2": bottom_actual,
            "ice_QI_bottom_net_depletion_kg_m2": bottom_net,
            "ice_QI_bottom_arrival_kg_m2": bottom_arrival,
            "ice_QI_reported_bottom_increment_code_value": bottom_report,
            "ice_QI_boundary_residual_kg_m2": ice["ice_boundary_residual"],
            "six_species_residual_kg_m2": residual,
        }
        case_key = f"{mode}_chunk{index:03d}"
        case_results[case_key] = metrics
        case_arrays[case_key] = arrays
        selected_columns[case_key] = selected
    summary = {
        "schema": "kdm6.localized_ice_stage_analysis.v1",
        "analysis_KDM_calls": 0,
        "calls_by_mode_chunk": case_results,
        "selected_by_case": selected_columns,
        "source_identity": {
            "manifest_sha256": manifest_sha,
            "tool_sha256": tool_sha,
            "controller_sha256": controller_sha,
            "finish_reference_sha256": sha256_file(finish_reference),
        },
        "design": {
            "modes": list(MODES),
            "chunks": list(CHUNK_INDICES),
            "B": CHUNK_COLUMNS,
            "L": LEVELS,
            "native_grid": [NX, NY],
            "selected_columns": list(SELECTED_FLAT_INDICES),
        },
        "calls": {
            "trace_on_prior_KDM_calls": 4,
            "analysis_added_KDM_calls": 0,
            "native_host_steps": 0,
            "RTTOV_calls": 0,
        },
        "interpretation_limits": [
            "No inner-rain causal attribution.",
            "Raw velocity/code-flux dimensions remain conditional.",
            "Fixed-measure residuals do not certify physical conservation.",
        ],
    }
    output.mkdir(parents=True)
    for key, arrays in case_arrays.items():
        with (output / f"{key}.npz").open("xb") as stream:
            np.savez_compressed(stream, **arrays)
    summary["source_identity"]["analysis_source_sha256"] = sha256_file(Path(__file__))
    with (output / "analysis.json").open("x") as stream:
        stream.write(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-root", type=Path, default=CASE_ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--executable", type=Path, default=DEFAULT_EXECUTABLE)
    parser.add_argument("--prior-run-root", type=Path, default=DEFAULT_PRIOR_RUNS)
    parser.add_argument(
        "--finish-reference", type=Path, default=DEFAULT_FINISH_REFERENCE
    )
    args = parser.parse_args(argv)
    result = analyze(
        args.case_root,
        args.output,
        manifest_path=args.manifest,
        executable=args.executable,
        prior_run_root=args.prior_run_root,
        finish_reference=args.finish_reference,
    )
    print(
        json.dumps(
            {
                "analysis_KDM_calls": result["analysis_KDM_calls"],
                "case_count": len(result["calls_by_mode_chunk"]),
                "selected_by_case": list(result["selected_by_case"]),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
