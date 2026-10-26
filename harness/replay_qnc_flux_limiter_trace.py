"""Strict offline replay of the PR457 native QNC flux-limiter trace.

The reader preserves binary32 words. Replay checks numerical operators and a
same-run ADVECT_TEND join; it does not assign named-process causality or certify
physical number units or closure.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from itertools import product
from pathlib import Path
import re
from typing import Mapping

import numpy as np

from harness.analyze_upstream_nc_trace import UpstreamNCTrace
from harness.g33_s15_probe import fma32 as _exact_fma32


MAGIC_V1 = "# KDM6AD_QNC_FLUX_TRACE_V1"
MAGIC = "# KDM6AD_QNC_FLUX_TRACE_V2"
ROW_HEADER_V1 = ("VAL", "step", "rk_step", "stage", "i", "k", "j", "field", "dtype", "raw_hex")
ROW_HEADER = ("VAL", "time_step_s", "rk_step", "stage", "i", "k", "j", "field", "dtype", "raw_hex")
NATIVE_STEP_SECONDS = 20  # first column is nl_get_time_step(1), not grid%itimestep
TARGET_IKJ = (221, 6, 63)
FACE_NEIGHBORS_IKJ = {
    (220, 6, 63), (222, 6, 63),
    (221, 6, 62), (221, 6, 64),
    (221, 5, 63), (221, 7, 63),
}
STAGE_RK: Mapping[str, tuple[int, ...]] = {
    "RK1_START": (1,), "RK1_AFTER_Y": (1,), "RK1_AFTER_X": (1,), "RK1_AFTER_Z": (1,),
    "RK3_PD_PRE_LIMIT": (3,), "RK3_PD_LIMIT_CELL": (3,), "RK3_PD_POST_LIMIT_FACES": (3,),
    "RK3_AFTER_Z": (3,), "RK3_AFTER_X": (3,), "RK3_AFTER_Y": (3,),
}
PD_FACE_FIELDS = (
    "FX_WEST", "FX_EAST", "FY_SOUTH", "FY_NORTH", "FZ_BOTTOM", "FZ_TOP",
    "FX_LOW_WEST", "FX_LOW_EAST", "FY_LOW_SOUTH", "FY_LOW_NORTH",
    "FZ_LOW_BOTTOM", "FZ_LOW_TOP",
)
STAGE_FIELDS: Mapping[str, tuple[str, ...]] = {
    "RK1_START": ("TENDENCY",),
    "RK1_AFTER_Y": ("TENDENCY", "F_Y_LOWER", "F_Y_UPPER", "MRDY"),
    "RK1_AFTER_X": ("TENDENCY", "F_X_LOWER", "F_X_UPPER", "MRDX"),
    "RK1_AFTER_Z": ("TENDENCY", "F_Z_LOWER", "F_Z_UPPER", "RDZW"),
    "RK3_PD_PRE_LIMIT": ("TENDENCY", "PH_LOW", "FLUX_OUT", *PD_FACE_FIELDS),
    "RK3_PD_LIMIT_CELL": ("PH_LOW", "FLUX_OUT", "LIMIT_HIT", "SCALE"),
    "RK3_PD_POST_LIMIT_FACES": (*PD_FACE_FIELDS, "MSFTX", "MSFTY", "RDX", "RDY", "RDZW", "DT_STEP"),
    "RK3_AFTER_Z": ("TENDENCY",),
    "RK3_AFTER_X": ("TENDENCY",),
    "RK3_AFTER_Y": ("TENDENCY",),
}
_HEX32 = re.compile(r"[0-9A-Fa-f]{8}\Z")
_BOOL = re.compile(r"(?:00|01)\Z")
FluxKey = tuple[int, int, str, int, int, int, str]


@dataclass(frozen=True)
class FluxTraceValue:
    step: int
    rk: int
    stage: str
    i: int
    k: int
    j: int
    field: str
    dtype: str
    bits: int | bool

    @property
    def value(self) -> np.float32 | bool:
        if self.dtype == "bool":
            return bool(self.bits)
        return np.asarray([self.bits], dtype=np.uint32).view(np.float32)[0]

    @property
    def raw_hex(self) -> str:
        return ("01" if self.bits else "00") if self.dtype == "bool" else f"{int(self.bits):08X}"


@dataclass(frozen=True)
class FluxTraceGroup:
    index: int
    semantic_role: str
    values: Mapping[FluxKey, FluxTraceValue]
    row_order: tuple[FluxKey, ...]

    def at(self, rk: int, stage: str, field: str, coordinate_ikj=TARGET_IKJ) -> FluxTraceValue:
        i, k, j = coordinate_ikj
        return self.values[(NATIVE_STEP_SECONDS, rk, stage, i, k, j, field)]


@dataclass(frozen=True)
class FluxTrace:
    protocol_version: int
    groups: tuple[FluxTraceGroup, ...]
    sha256: str
    byte_count: int
    filename: str

    def select_qnc_scalar_group(self, group_index: int | None = None) -> FluxTraceGroup:
        """Select the single V2 group, which has an explicit moist-step filter."""
        if self.protocol_version != 2:
            raise ValueError("V1 has no moist/scalar namespace and is not eligible for QNC replay")
        selected = 0 if group_index is None else group_index
        if selected != 0:
            raise ValueError("V2 has one context-filtered scalar QNC group at index 0")
        return self.groups[0]


def _key(row: FluxTraceValue) -> FluxKey:
    return (row.step, row.rk, row.stage, row.i, row.k, row.j, row.field)


def _validate_flux_group(group: FluxTraceGroup) -> None:
    expected: set[FluxKey] = set()
    for stage in ("RK1_START", "RK1_AFTER_Y", "RK1_AFTER_X", "RK1_AFTER_Z"):
        expected.update((NATIVE_STEP_SECONDS, 1, stage, *TARGET_IKJ, f) for f in STAGE_FIELDS[stage])
    for stage in ("RK3_PD_PRE_LIMIT", "RK3_PD_POST_LIMIT_FACES", "RK3_AFTER_Z", "RK3_AFTER_X", "RK3_AFTER_Y"):
        expected.update((NATIVE_STEP_SECONDS, 3, stage, *TARGET_IKJ, f) for f in STAGE_FIELDS[stage])
    for coord in (TARGET_IKJ, *FACE_NEIGHBORS_IKJ):
        expected.update((NATIVE_STEP_SECONDS, 3, "RK3_PD_LIMIT_CELL", *coord, f) for f in STAGE_FIELDS["RK3_PD_LIMIT_CELL"])
    missing, extra = expected - set(group.values), set(group.values) - expected
    if missing or extra:
        raise ValueError(f"incomplete/unexpected flux records; missing={len(missing)} extra={len(extra)}")
    stage_order: list[tuple[int, str]] = []
    for key in group.row_order:
        item = (key[1], key[2])
        if not stage_order or stage_order[-1] != item:
            stage_order.append(item)
    expected_order = [
        (1, "RK1_START"), (1, "RK1_AFTER_Y"), (1, "RK1_AFTER_X"), (1, "RK1_AFTER_Z"),
        (3, "RK3_PD_PRE_LIMIT"), (3, "RK3_PD_LIMIT_CELL"), (3, "RK3_PD_POST_LIMIT_FACES"),
        (3, "RK3_AFTER_Z"), (3, "RK3_AFTER_X"), (3, "RK3_AFTER_Y"),
    ]
    if stage_order != expected_order:
        raise ValueError(f"unexpected stage order: {stage_order}")


def validate_flux_trace(trace: FluxTrace) -> None:
    expected_groups = 1
    if len(trace.groups) != expected_groups:
        raise ValueError(f"V{trace.protocol_version} requires {expected_groups} complete capture group(s), got {len(trace.groups)}")
    for group in trace.groups:
        _validate_flux_group(group)


def read_qnc_flux_trace(path: str | Path) -> FluxTrace:
    """Read the namespace-filtered V2 trace; the first field is native time-step seconds."""
    source = Path(path)
    raw = source.read_bytes()
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("flux trace must be ASCII") from exc
    if not lines:
        raise ValueError("flux trace is empty")
    if lines[0] == MAGIC_V1:
        raise ValueError("V1 flux trace lacks moist-step namespace; preserve as unattributed engineering evidence only")
    if lines[0] != MAGIC:
        raise ValueError(f"flux trace must start with exact V2 header {MAGIC!r}")
    protocol_version = 2
    expected_header = ROW_HEADER
    start = 1
    if len(lines) > 1 and lines[1].startswith("#"):
        if tuple(lines[1][1:].split()) != expected_header:
            raise ValueError("flux row header does not match the versioned ten-column schema")
        start = 2

    group_rows: list[dict[FluxKey, FluxTraceValue]] = []
    group_orders: list[list[FluxKey]] = []
    rows: dict[FluxKey, FluxTraceValue] = {}
    order: list[FluxKey] = []
    for line_no, line in enumerate(lines[start:], start=start + 1):
        if not line:
            raise ValueError(f"line {line_no}: blank rows are invalid")
        col = line.split()
        if len(col) != 10 or col[0] != "VAL":
            raise ValueError(f"line {line_no}: expected 10 whitespace-separated VAL fields")
        _, time_s, rk_s, stage, i_s, k_s, j_s, field, dtype, hex_word = col
        try:
            step, rk, i, k, j = map(int, (time_s, rk_s, i_s, k_s, j_s))
        except ValueError as exc:
            raise ValueError(f"line {line_no}: time-step seconds, RK and coordinates must be integers") from exc
        if step != NATIVE_STEP_SECONDS:
            raise ValueError(f"line {line_no}: expected native step seconds {NATIVE_STEP_SECONDS}, got {step}")
        if stage not in STAGE_RK or rk not in STAGE_RK[stage]:
            raise ValueError(f"line {line_no}: stage {stage!r} is invalid for RK {rk}")
        if field not in STAGE_FIELDS[stage]:
            raise ValueError(f"line {line_no}: unexpected field {field!r} for {stage}")
        coord = (i, k, j)
        allowed = {TARGET_IKJ, *FACE_NEIGHBORS_IKJ} if stage == "RK3_PD_LIMIT_CELL" else {TARGET_IKJ}
        if coord not in allowed:
            raise ValueError(f"line {line_no}: unexpected target/donor coordinate {coord}")
        if dtype == "f32":
            if not _HEX32.fullmatch(hex_word):
                raise ValueError(f"line {line_no}: f32 word must have 8 hex digits")
            bits: int | bool = int(hex_word, 16)
            if not np.isfinite(np.asarray([bits], dtype=np.uint32).view(np.float32)[0]):
                raise ValueError(f"line {line_no}: nonfinite f32 record")
        elif dtype == "bool":
            if field != "LIMIT_HIT" or not _BOOL.fullmatch(hex_word):
                raise ValueError(f"line {line_no}: only LIMIT_HIT may be bool 00/01")
            bits = hex_word == "01"
        else:
            raise ValueError(f"line {line_no}: unsupported dtype {dtype!r}")
        if stage == "RK1_START" and order:
            group_rows.append(rows)
            group_orders.append(order)
            rows, order = {}, []
        elif not order and stage != "RK1_START":
            raise ValueError(f"line {line_no}: each capture group must begin at RK1_START")
        row = FluxTraceValue(step, rk, stage, i, k, j, field, dtype, bits)
        key = _key(row)
        if key in rows:
            raise ValueError(f"line {line_no}: duplicate trace key {key}")
        rows[key] = row
        order.append(key)
    if not rows:
        raise ValueError("flux trace contains no VAL rows")
    group_rows.append(rows)
    group_orders.append(order)
    groups = []
    for index, (row_values, row_order) in enumerate(zip(group_rows, group_orders)):
        role = "context_filtered_scalar_qnc"
        groups.append(FluxTraceGroup(index, role, row_values, tuple(row_order)))
    trace = FluxTrace(protocol_version, tuple(groups), hashlib.sha256(raw).hexdigest(), len(raw), source.name)
    validate_flux_trace(trace)
    return trace


def _f32(value: float | np.float32) -> np.float32:
    return np.float32(value)


def _bits(value: np.float32) -> int:
    return int(np.asarray([value], dtype=np.float32).view(np.uint32)[0])


def _summary(value: np.float32) -> dict[str, object]:
    return {"value": float(value), "bits_hex": f"{_bits(value):08X}"}


def _add(a: np.float32, b: np.float32) -> np.float32:
    return _f32(_f32(a) + _f32(b))


def _sub(a: np.float32, b: np.float32) -> np.float32:
    return _f32(_f32(a) - _f32(b))


def _mul(a: np.float32, b: np.float32) -> np.float32:
    return _f32(_f32(a) * _f32(b))


def _div(a: np.float32, b: np.float32) -> np.float32:
    return _f32(_f32(a) / _f32(b))


def _fma(a: np.float32, b: np.float32, c: np.float32) -> np.float32:
    return _f32(_exact_fma32(float(a), float(b), float(c)))


def _value(trace: FluxTraceGroup, rk: int, stage: str, field: str, coord=TARGET_IKJ) -> np.float32:
    return trace.at(rk, stage, field, coord).value  # type: ignore[return-value]


def _value_row(trace: FluxTraceGroup, rk: int, stage: str, field: str, coord=TARGET_IKJ) -> FluxTraceValue:
    return trace.at(rk, stage, field, coord)


def _replay_step(before: np.float32, factor: np.float32, delta: np.float32, observed: np.float32) -> dict[str, object]:
    separate = _sub(before, _mul(factor, delta))
    fused = _fma(-factor, delta, before)
    return {
        "before": _summary(before), "factor": _summary(factor), "delta": _summary(delta),
        "observed": _summary(observed), "separate_f32": _summary(separate),
        "separate_match": _bits(separate) == _bits(observed),
        "outer_fma": _summary(fused), "outer_fma_match": _bits(fused) == _bits(observed),
    }


def _rk1_directional_replay(trace: FluxTraceGroup) -> list[dict[str, object]]:
    previous = _value(trace, 1, "RK1_START", "TENDENCY")
    out = []
    for axis, stage, low, high, metric in (
        ("Y", "RK1_AFTER_Y", "F_Y_LOWER", "F_Y_UPPER", "MRDY"),
        ("X", "RK1_AFTER_X", "F_X_LOWER", "F_X_UPPER", "MRDX"),
        ("Z", "RK1_AFTER_Z", "F_Z_LOWER", "F_Z_UPPER", "RDZW"),
    ):
        delta = _sub(_value(trace, 1, stage, high), _value(trace, 1, stage, low))
        fac = _value(trace, 1, stage, metric)
        actual = _value(trace, 1, stage, "TENDENCY")
        out.append({"axis": axis, **_replay_step(previous, fac, delta, actual)})
        previous = actual
    return out


def _rk3_divergence_replay(trace: FluxTraceGroup) -> list[dict[str, object]]:
    face_stage = "RK3_PD_POST_LIMIT_FACES"
    previous = _value(trace, 3, "RK3_PD_PRE_LIMIT", "TENDENCY")
    out = []
    z = _sub(_value(trace, 3, face_stage, "FZ_TOP"), _value(trace, 3, face_stage, "FZ_BOTTOM"))
    z = _add(z, _value(trace, 3, face_stage, "FZ_LOW_TOP"))
    z = _sub(z, _value(trace, 3, face_stage, "FZ_LOW_BOTTOM"))
    z_factor = _value(trace, 3, face_stage, "RDZW")
    z_after = _value(trace, 3, "RK3_AFTER_Z", "TENDENCY")
    out.append({"axis": "Z", **_replay_step(previous, z_factor, z, z_after)})
    previous = z_after

    x = _sub(_value(trace, 3, face_stage, "FX_EAST"), _value(trace, 3, face_stage, "FX_WEST"))
    x = _add(x, _value(trace, 3, face_stage, "FX_LOW_EAST"))
    x = _sub(x, _value(trace, 3, face_stage, "FX_LOW_WEST"))
    x_factor = _mul(_value(trace, 3, face_stage, "MSFTX"), _value(trace, 3, face_stage, "RDX"))
    x_after = _value(trace, 3, "RK3_AFTER_X", "TENDENCY")
    out.append({"axis": "X", **_replay_step(previous, x_factor, x, x_after)})
    previous = x_after

    y = _sub(_value(trace, 3, face_stage, "FY_NORTH"), _value(trace, 3, face_stage, "FY_SOUTH"))
    y = _add(y, _value(trace, 3, face_stage, "FY_LOW_NORTH"))
    y = _sub(y, _value(trace, 3, face_stage, "FY_LOW_SOUTH"))
    y_factor = _mul(_value(trace, 3, face_stage, "MSFTX"), _value(trace, 3, face_stage, "RDY"))
    y_after = _value(trace, 3, "RK3_AFTER_Y", "TENDENCY")
    out.append({"axis": "Y", **_replay_step(previous, y_factor, y, y_after)})
    return out


def _face_donor(field: str, value: np.float32) -> tuple[int, int, int]:
    i, k, j = TARGET_IKJ
    if field == "FX_WEST":
        return TARGET_IKJ if value < 0 else (i - 1, k, j)
    if field == "FX_EAST":
        return TARGET_IKJ if value > 0 else (i + 1, k, j)
    if field == "FY_SOUTH":
        return TARGET_IKJ if value < 0 else (i, k, j - 1)
    if field == "FY_NORTH":
        return TARGET_IKJ if value > 0 else (i, k, j + 1)
    if field == "FZ_BOTTOM":
        return TARGET_IKJ if value > 0 else (i, k - 1, j)
    if field == "FZ_TOP":
        return TARGET_IKJ if value < 0 else (i, k + 1, j)
    raise ValueError(f"unknown face {field}")


def _cell_limiter(trace: FluxTrace, coord) -> dict[str, object]:
    return {
        "PH_LOW": _value(trace, 3, "RK3_PD_LIMIT_CELL", "PH_LOW", coord),
        "FLUX_OUT": _value(trace, 3, "RK3_PD_LIMIT_CELL", "FLUX_OUT", coord),
        "LIMIT_HIT": bool(_value_row(trace, 3, "RK3_PD_LIMIT_CELL", "LIMIT_HIT", coord).value),
        "SCALE": _value(trace, 3, "RK3_PD_LIMIT_CELL", "SCALE", coord),
    }


def _ph_low_replay(trace: FluxTrace, upstream: UpstreamNCTrace) -> tuple[np.float32, np.float32, list[dict[str, object]]]:
    coord = TARGET_IKJ
    upcoord = (coord[0], coord[2], coord[1])
    # post-PD scalar_old is the base state used to construct the low-order state
    source = "RKSCALAR_PD_AFTER"
    qold = upstream.at(upcoord, 3, source, "SCALAR_OLD").f32
    c1 = upstream.at(upcoord, 3, source, "C1H").f32
    c2 = upstream.at(upcoord, 3, source, "C2H").f32
    mu_old = upstream.at(upcoord, 3, source, "MU_OLD_ARG").f32
    mu_base = upstream.at(upcoord, 3, source, "MU_BASE").f32
    dt = _value(trace, 3, "RK3_PD_POST_LIMIT_FACES", "DT_STEP")
    f = {field: _value(trace, 3, "RK3_PD_PRE_LIMIT", field) for field in PD_FACE_FIELDS}
    observed = _value(trace, 3, "RK3_PD_PRE_LIMIT", "PH_LOW")
    msftx = _value(trace, 3, "RK3_PD_POST_LIMIT_FACES", "MSFTX")
    msfty = _value(trace, 3, "RK3_PD_POST_LIMIT_FACES", "MSFTY")
    rdx = _value(trace, 3, "RK3_PD_POST_LIMIT_FACES", "RDX")
    rdy = _value(trace, 3, "RK3_PD_POST_LIMIT_FACES", "RDY")
    rdzw = _value(trace, 3, "RK3_PD_POST_LIMIT_FACES", "RDZW")
    mass_first = _add(_mul(c1, mu_base), c2)
    mass = _add(mass_first, _mul(c1, mu_old))
    storage = _mul(mass, qold)
    dx = _sub(f["FX_LOW_EAST"], f["FX_LOW_WEST"])
    dy = _sub(f["FY_LOW_NORTH"], f["FY_LOW_SOUTH"])
    dz = _sub(f["FZ_LOW_TOP"], f["FZ_LOW_BOTTOM"])
    x_term, y_term = _mul(rdx, dx), _mul(rdy, dy)
    h_inner = _add(x_term, y_term)
    map_factor = _mul(msftx, msfty)
    h = _mul(map_factor, h_inner)
    v_factor = _mul(msfty, rdzw)
    v = _mul(v_factor, dz)
    divergence = _add(h, v)
    result = _sub(storage, _mul(dt, divergence))

    mass_first_fma = _fma(c1, mu_base, c2)
    x_y_fma = _fma(rdx, dx, y_term)
    candidates = []
    for fuse_mass_first, fuse_mass_second, fuse_horizontal_sum, fuse_vertical_sum, fuse_final_subtract in product((False, True), repeat=5):
        first = mass_first_fma if fuse_mass_first else mass_first
        mass_candidate = _fma(c1, mu_old, first) if fuse_mass_second else _add(first, _mul(c1, mu_old))
        storage_candidate = _mul(mass_candidate, qold)
        h_inner_candidate = x_y_fma if fuse_horizontal_sum else h_inner
        h_candidate = _mul(map_factor, h_inner_candidate)
        div_candidate = _fma(v_factor, dz, h_candidate) if fuse_vertical_sum else _add(h_candidate, v)
        value = _fma(-dt, div_candidate, storage_candidate) if fuse_final_subtract else _sub(storage_candidate, _mul(dt, div_candidate))
        flags = {
            "mass_first": fuse_mass_first,
            "mass_second": fuse_mass_second,
            "horizontal_sum": fuse_horizontal_sum,
            "vertical_sum": fuse_vertical_sum,
            "final_subtract": fuse_final_subtract,
        }
        candidates.append({"fma_sites": flags, "value": _summary(value), "matches_observed": _bits(value) == _bits(observed)})
    return result, dt, candidates


def _flux_out_replay(trace: FluxTrace, upstream: UpstreamNCTrace, dt: np.float32) -> np.float32:
    del upstream  # Geometry/metrics are captured in the face snapshot stage.
    f = {field: _value(trace, 3, "RK3_PD_PRE_LIMIT", field) for field in PD_FACE_FIELDS}
    msftx = _value(trace, 3, "RK3_PD_POST_LIMIT_FACES", "MSFTX")
    msfty = _value(trace, 3, "RK3_PD_POST_LIMIT_FACES", "MSFTY")
    rdx = _value(trace, 3, "RK3_PD_POST_LIMIT_FACES", "RDX")
    rdy = _value(trace, 3, "RK3_PD_POST_LIMIT_FACES", "RDY")
    rdzw = _value(trace, 3, "RK3_PD_POST_LIMIT_FACES", "RDZW")
    x = _sub(_f32(max(0.0, float(f["FX_EAST"]))), _f32(min(0.0, float(f["FX_WEST"]))))
    y = _sub(_f32(max(0.0, float(f["FY_NORTH"]))), _f32(min(0.0, float(f["FY_SOUTH"]))))
    z = _sub(_f32(min(0.0, float(f["FZ_TOP"]))), _f32(max(0.0, float(f["FZ_BOTTOM"]))))
    h = _add(_mul(rdx, x), _mul(rdy, y))
    h = _mul(_mul(msftx, msfty), h)
    v = _mul(_mul(msfty, rdzw), z)
    return _mul(dt, _add(h, v))


def _limiter_replay(trace: FluxTraceGroup, upstream: UpstreamNCTrace) -> dict[str, object]:
    pre = {field: _value(trace, 3, "RK3_PD_PRE_LIMIT", field) for field in PD_FACE_FIELDS}
    post = {field: _value(trace, 3, "RK3_PD_POST_LIMIT_FACES", field) for field in PD_FACE_FIELDS}
    ph = _value(trace, 3, "RK3_PD_PRE_LIMIT", "PH_LOW")
    flux_out = _value(trace, 3, "RK3_PD_PRE_LIMIT", "FLUX_OUT")
    ph_calc, dt, ph_fma_candidates = _ph_low_replay(trace, upstream)
    upstream_dt = upstream.at((TARGET_IKJ[0], TARGET_IKJ[2], TARGET_IKJ[1]), 3, "RKSCALAR_PD_AFTER", "DT_RK").f32
    flux_out_calc = _flux_out_replay(trace, upstream, dt)
    cells = {coord: _cell_limiter(trace, coord) for coord in (TARGET_IKJ, *FACE_NEIGHBORS_IKJ)}
    pre_cell = cells[TARGET_IKJ]
    eps = _f32(1.0e-20)
    cell_results = {}
    for coord, cell in cells.items():
        cell_ph, cell_out = _f32(cell["PH_LOW"]), _f32(cell["FLUX_OUT"])
        hit = bool(cell["LIMIT_HIT"])
        expected_hit = bool(cell_out > cell_ph)
        expected_scale = max(_f32(0.0), _div(cell_ph, _add(cell_out, eps))) if hit else _f32(1.0)
        scale = _f32(cell["SCALE"])
        cell_results["i%d_k%d_j%d" % coord] = {
            "ph_low": _summary(cell_ph), "flux_out": _summary(cell_out),
            "limit_hit": hit, "expected_hit": expected_hit, "branch_match": bool(hit == expected_hit),
            "scale": _summary(scale), "expected_scale": _summary(expected_scale),
            "scale_match": _bits(scale) == _bits(expected_scale),
        }
    correction_results = {}
    for face in ("FX_WEST", "FX_EAST", "FY_SOUTH", "FY_NORTH", "FZ_BOTTOM", "FZ_TOP"):
        donor = _face_donor(face, pre[face])
        budget = cells[donor]
        scale = _f32(budget["SCALE"]) if budget["LIMIT_HIT"] else _f32(1.0)
        expected_post = _mul(pre[face], scale) if budget["LIMIT_HIT"] else pre[face]
        correction_results[face] = {
            "pre": _summary(pre[face]), "post": _summary(post[face]),
            "donor_ikj": list(donor), "donor_scale": _summary(scale),
            "matches": _bits(expected_post) == _bits(post[face]),
        }
    low_unchanged = {
        field: _bits(pre[field]) == _bits(post[field])
        for field in PD_FACE_FIELDS if field.startswith(("FX_LOW_", "FY_LOW_", "FZ_LOW_"))
    }
    ph_fma_matches = [row for row in ph_fma_candidates if row["matches_observed"]]
    return {
        "dt_step_matches_upstream_dt_rk": _bits(dt) == _bits(upstream_dt),
        "pre_vs_target_limit_cell": _bits(ph) == _bits(pre_cell["PH_LOW"]) and _bits(flux_out) == _bits(pre_cell["FLUX_OUT"]),
        "ph_low_replay": {
            "observed": _summary(ph), "computed": _summary(ph_calc),
            "matches": _bits(ph) == _bits(ph_calc),
            "source_terms_missing": [],
            "all_advect_scalar_pd_ph_low_operands_captured": True,
            "candidate_scope": "complete advect_scalar_pd operand replay; FMA variants remain arithmetic candidates, not compiler evidence",
            "fma_contraction_candidates": ph_fma_candidates,
            "matching_fma_candidates": ph_fma_matches,
        },
        "flux_out_replay": {"observed": _summary(flux_out), "computed": _summary(flux_out_calc), "matches": _bits(flux_out) == _bits(flux_out_calc)},
        "limit_cells": cell_results, "correction_faces": correction_results,
        "low_order_faces_unchanged": low_unchanged,
    }


def analyze_qnc_flux_limiter_trace(
    trace: FluxTrace,
    *,
    group_index: int | None = None,
    upstream_trace: UpstreamNCTrace,
    run_id: str,
    upstream_run_id: str,
    run_config: Mapping[str, int],
) -> dict[str, object]:
    """Replay the RK1 and RK3 flux path and join final tendencies to V4/V6."""
    validate_flux_trace(trace)
    selected = trace.select_qnc_scalar_group(group_index)
    if not run_id or upstream_run_id != run_id:
        raise ValueError("flux and upstream NC traces must have the same explicit run_id")
    expected_config = {"scalar_adv_opt": 1, "rk_ord": 3, "h_sca_adv_order": 5, "v_sca_adv_order": 3, "zadvect_implicit": 0}
    for field, expected in expected_config.items():
        if field not in run_config or int(run_config[field]) != expected:
            raise ValueError(f"run config {field} must be {expected}")
    target_upstream = (TARGET_IKJ[0], TARGET_IKJ[2], TARGET_IKJ[1])
    rk1 = _rk1_directional_replay(selected)
    rk3 = _rk3_divergence_replay(selected)
    limiter = _limiter_replay(selected, upstream_trace)
    joins = []
    for rk, stage in ((1, "RK1_AFTER_Z"), (3, "RK3_AFTER_Y")):
        actual = _value(selected, rk, stage, "TENDENCY")
        adv = upstream_trace.at(target_upstream, rk, "RKSCALAR_BEFORE", "ADVECT_TEND").f32
        joins.append({"rk_step": rk, "flux_tendency": _summary(actual), "same_run_ADVECT_TEND": _summary(adv), "matches": _bits(actual) == _bits(adv)})
    checks = [
        all(row["separate_match"] or row["outer_fma_match"] for row in rk1),
        all(row["separate_match"] or row["outer_fma_match"] for row in rk3),
        all(row["matches"] for row in joins),
        limiter["dt_step_matches_upstream_dt_rk"],
        limiter["pre_vs_target_limit_cell"],
        limiter["ph_low_replay"]["matches"] or bool(limiter["ph_low_replay"]["matching_fma_candidates"]),
        limiter["flux_out_replay"]["matches"],
        all(row["branch_match"] for row in limiter["limit_cells"].values()),
        all(row["scale_match"] for row in limiter["limit_cells"].values()),
        all(row["matches"] for row in limiter["correction_faces"].values()),
        all(limiter["low_order_faces_unchanged"].values()),
    ]
    return {
        "schema": "kdm6ad.qnc_flux_limiter_replay.v1", "run_id": run_id,
        "flux_trace": {"file": trace.filename, "sha256": trace.sha256, "bytes": trace.byte_count, "protocol_version": trace.protocol_version},
        "selected_capture_group": {"index": selected.index, "source_role": selected.semantic_role},
        "upstream_trace": {"file": upstream_trace.path_name, "sha256": upstream_trace.sha256},
        "target_ikj": list(TARGET_IKJ), "run_config": dict(run_config),
        "rk1_directional_tendency_replay": rk1,
        "rk3_pd_applied_divergence_replay": rk3,
        "same_run_advect_tend_join": joins,
        "rk3_pd_limiter": limiter,
        "all_captured_replays_match_a_source_or_outer_fma_candidate": all(checks),
        "scope": {"process_attribution": "not inferred", "number_units": "not certified", "budget_closure": "not certified"},
    }
