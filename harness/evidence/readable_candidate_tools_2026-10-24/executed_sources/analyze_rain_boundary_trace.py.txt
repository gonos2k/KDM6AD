"""Strict offline QR budget reader for the saved B512 boundary traces.

It invokes no model code. Every traced call is tied to the frozen request and
response. QR transfer accounting uses the request's fixed DEND*DELZ measure;
QR fallout diagnostics remain separate from applied state departure and total
multi-species surface precipitation.
"""

from __future__ import annotations

import argparse
from io import BytesIO, TextIOWrapper
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from harness.ice_factorial_batch import IN_HEADER, unpack_response
from harness.rain_boundary_budget import reported_budget, step_budget, surface_component

TRACE_ROOT = Path("/Users/yhlee/KDM6AD-k/host/research_evidence/qr_boundary_20261024")
FROZEN_ROOT = Path(
    "/Users/yhlee/KDM6AD-k/host/research_evidence/mp137_domain_factorial_20261023/full"
)
STAGE_ROOT = (
    Path(__file__).resolve().parent / "evidence/localized_ice_budget_ad_2026-10-24"
)
MODES = ("norm_actual", "raw_actual")
CHUNKS = (34, 40)
TARGET_ROWS = {34: 254, 40: 8}
B, L, DT, DENR = 512, 39, 20.0, 1000.0
SAFE_FLOOR = 1.0e-9
POST_SED_STAGE_SHA256 = {
    (
        "norm_actual",
        34,
    ): "7b0d6ab4220b919d772cea4aeaf3d6c23299477d40d2734422391112c2bd9fb4",
    (
        "norm_actual",
        40,
    ): "fc02a143edb2a6ea43193dd77a11e96278ca98b054a574f415cdf89d3fcff0a2",
    (
        "raw_actual",
        34,
    ): "62ebee38d367cac6ffeeb477ab677c465ba063e3f6d7dddee6f8b8c4174b27be",
    (
        "raw_actual",
        40,
    ): "a759529fcfbfa583732b239ee84c510f94f0f71503943bd424ad85b5400d9e8c",
}
QR_FLOATS = (
    "dtcld_s",
    "DEND_code",
    "DEND_safe_code",
    "DELZ_code",
    "DELZ_safe_code",
    "DELZ_above_code",
    "work1_qr_code",
    "workn_qr_code",
    "QR_before_code",
    "falk_qr_stored_code",
    "falk_qr_prev_stored_code",
    "QR_out_cap_operand_code",
    "QR_above_cap_operand_post_update_code",
    "dqr_out_attempt_reconstructed_code",
    "dqr_out_min_attempt_before_diagnostic_code",
    "dqr_out_applied_operand_code",
    "dqr_arrival_attempt_reconstructed_code",
    "dqr_arrival_min_attempt_above_diagnostic_code",
    "dqr_arrival_applied_operand_code",
    "QR_realized_before_minus_after_code",
    "QR_after_code",
    "fall_qr_accum_before_code",
    "fall_qr_accum_after_code",
)
QR_INTS = (
    "call_index",
    "n",
    "column",
    "level_top0",
    "top",
    "mstep",
    "gate",
    "dqr_out_operand_present",
    "arrival_operand_present",
)
SURFACE_FLOATS = (
    "dtcld_s",
    "fall_qr_bottom_code",
    "fall_qs_bottom_code",
    "fall_qg_bottom_code",
    "fall_qi_bottom_code",
    "DELZ_bottom_m",
    "DENR_surface_constant",
    "surface_total_from_rain_increment_mm",
    "surface_snow_ice_subset_mm",
    "surface_graupel_subset_mm",
)
SURFACE_INTS = ("call_index", "column", "bottom_level_top0")


class TraceError(ValueError):
    """A saved trace or receipt does not match the admitted B512 execution."""


def compare_post_sed_qr(trace_top_first, stage_bottom_first):
    """Require trace endpoint and prior saved post-sed QR to match bitwise."""
    trace = np.asarray(trace_top_first)
    stage = np.asarray(stage_bottom_first)
    if trace.shape != (B, L) or stage.shape != (B, L):
        raise TraceError("post-sed QR profile shape differs from B512/L39")
    if trace.dtype != np.float64 or stage.dtype != np.float64:
        raise TraceError("post-sed QR profiles must be stored float64")
    trace_bottom_first = trace[:, ::-1]
    if not same_bits(trace_bottom_first, stage):
        raise TraceError("final traced QR differs from saved post-sed QR bitwise")
    return trace_bottom_first


def load_post_sed_qr_reference(stage_root: Path, mode: str, chunk: int):
    """Load a hash-pinned independently saved post-sed stage snapshot."""
    key = (mode, chunk)
    if key not in POST_SED_STAGE_SHA256:
        raise TraceError("post-sed reference is outside the admitted case set")
    name = f"stage_{mode}_chunk{chunk:03d}.npz"
    path = Path(stage_root) / name
    archive_bytes = path.read_bytes()
    digest = sha256(archive_bytes)
    if digest != POST_SED_STAGE_SHA256[key]:
        raise TraceError("post-sed stage archive differs from pinned prior evidence")
    with np.load(BytesIO(archive_bytes), allow_pickle=False) as archive:
        if "water_stage_state_bottomfirst" not in archive:
            raise TraceError("post-sed archive lacks saved water stage state")
        stages = archive["water_stage_state_bottomfirst"]
    if stages.shape != (3, 6, B, L) or stages.dtype != np.float64:
        raise TraceError("post-sed saved water-stage array has unexpected layout")
    reference = stages[1, 2]
    if not np.isfinite(reference).all():
        raise TraceError("post-sed saved QR profile contains nonfinite values")
    return reference, {"archive": name, "archive_sha256": digest}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: Path) -> str:
    return sha256(Path(path).read_bytes())


def same_bits(left, right) -> bool:
    a = np.ascontiguousarray(left, dtype=np.float64)
    b = np.ascontiguousarray(right, dtype=np.float64)
    return a.shape == b.shape and a.tobytes() == b.tobytes()


def _fields(line: str) -> dict[str, str]:
    result = {}
    for token in line.split():
        pair = token.split("=", 1)
        if len(pair) != 2 or pair[0] in result:
            raise TraceError("malformed or duplicate trace key")
        result[pair[0]] = pair[1]
    if not result:
        raise TraceError("empty trace row")
    return result


def _number(row: dict[str, str], key: str) -> float:
    try:
        x = float(row[key])
    except (KeyError, ValueError) as exc:
        raise TraceError(f"invalid numeric trace field {key}") from exc
    if not math.isfinite(x):
        raise TraceError(f"nonfinite trace field {key}")
    return x


def _integer(row: dict[str, str], key: str) -> int:
    x = _number(row, key)
    if not x.is_integer():
        raise TraceError(f"nonintegral trace field {key}")
    return int(x)


def parse_qr_trace(data: bytes, mode: str, *, batch=B, levels=L, steps=5):
    """Parse exactly n->level_top0->column row order."""
    shape = (steps, levels, batch)
    out = {name: np.empty(shape, dtype=np.float64) for name in QR_FLOATS}
    out.update({name: np.empty(shape, dtype=np.int32) for name in QR_INTS})
    expected_count = steps * levels * batch
    row_count = 0
    stream = TextIOWrapper(BytesIO(data), encoding="ascii", newline="")
    try:
        for ix, line in enumerate(stream):
            row_count = ix + 1
            if ix >= expected_count:
                raise TraceError("QR trace has extra rows")
            row = _fields(line)
            if (row.get("schema"), row.get("record"), row.get("factor_mode")) != (
                "kdm6.rain_boundary.v1",
                "qr_layer",
                mode,
            ):
                raise TraceError("QR schema, record, or mode mismatch")
            n0, rem = divmod(ix, levels * batch)
            k, b = divmod(rem, batch)
            if (
                _integer(row, "n"),
                _integer(row, "level_top0"),
                _integer(row, "column"),
            ) != (n0 + 1, k, b):
                raise TraceError(f"QR row order/coverage failure at row {ix}")
            if _integer(row, "call_index") != 0:
                raise TraceError("expected exactly one sedimentation_chain call")
            for name in QR_FLOATS:
                out[name][n0, k, b] = _number(row, name)
            for name in QR_INTS:
                out[name][n0, k, b] = _integer(row, name)
    except UnicodeDecodeError as exc:
        raise TraceError("QR trace must be ASCII") from exc
    finally:
        stream.close()
    if row_count != expected_count:
        raise TraceError(f"QR trace rows {row_count} != expected {expected_count}")
    return out


def validate_qr_trace(qr, state, forcing, *, steps=5):
    """Check request geometry, n-chain, source attempts, cap operands, and updates."""
    state, forcing = (
        np.asarray(state, dtype=np.float64),
        np.asarray(forcing, dtype=np.float64),
    )
    if (
        state.ndim != 3
        or state.shape[0] != 12
        or forcing.shape != (4, state.shape[1], state.shape[2])
        or state.shape[1] < 1
        or state.shape[2] < 1
    ):
        raise TraceError("request state/forcing dimensions differ")
    batch, levels = state.shape[1:]
    shape = (steps, levels, batch)
    if any(qr[k].shape != shape for k in QR_FLOATS + QR_INTS):
        raise TraceError("parsed QR trace has an unexpected array shape")
    if np.any(qr["dtcld_s"] != DT):
        raise TraceError("QR dtcld differs from the frozen dt20 request")
    if np.any(state[3] < 0):
        raise TraceError(
            "request QR is negative, so entry QR differs after the source clamp"
        )
    for name, got, expected in (
        ("DEND", qr["DEND_code"][0], forcing[0, :, ::-1].T),
        ("DELZ", qr["DELZ_code"][0], forcing[3, :, ::-1].T),
        ("first QR", qr["QR_before_code"][0], state[3, :, ::-1].T),
    ):
        if not same_bits(got, expected):
            raise TraceError(f"{name} differs bitwise from frozen request")
    if np.any(qr["DEND_code"] <= 0) or np.any(qr["DELZ_code"] <= 0):
        raise TraceError("QR trace geometry must be positive")
    if not same_bits(qr["DEND_safe_code"], np.maximum(qr["DEND_code"], SAFE_FLOOR)):
        raise TraceError("DEND safe-floor values differ from source")
    if not same_bits(qr["DELZ_safe_code"], np.maximum(qr["DELZ_code"], SAFE_FLOOR)):
        raise TraceError("DELZ safe-floor values differ from source")
    mstep = qr["mstep"][0, 0]
    if (
        np.any(mstep < 1)
        or np.any(mstep > 100)
        or not np.all(qr["mstep"] == mstep[None, None, :])
    ):
        raise TraceError("QR local mstep is invalid or not column-constant")
    if int(mstep.max()) != steps:
        raise TraceError("trace n range differs from batch global mstepmax")
    gates = (np.arange(1, steps + 1)[:, None, None] <= mstep[None, None, :]).astype(
        np.int32
    )
    if not np.array_equal(qr["gate"], np.broadcast_to(gates, shape)):
        raise TraceError("QR gate differs from per-column mstep schedule")
    top = np.zeros(shape, dtype=np.int32)
    top[:, 0, :] = 1
    present = np.ones(shape, dtype=np.int32)
    present[:, 0, :] = 0
    if not np.array_equal(qr["top"], top):
        raise TraceError("top flag/order mismatch")
    if not np.array_equal(qr["dqr_out_operand_present"], present):
        raise TraceError("top/out operand-presence flags mismatch")
    if not np.array_equal(qr["arrival_operand_present"], present):
        raise TraceError("top/arrival operand-presence flags mismatch")

    dt = qr["dtcld_s"]
    dend_safe, delz_safe = qr["DEND_safe_code"], qr["DELZ_safe_code"]
    out_attempt = qr["falk_qr_stored_code"] * dt / dend_safe
    if not same_bits(out_attempt, qr["dqr_out_attempt_reconstructed_code"]):
        raise TraceError("out attempt differs from original left-associated expression")
    out_min = np.minimum(out_attempt, qr["QR_before_code"])
    if not same_bits(out_min, qr["dqr_out_min_attempt_before_diagnostic_code"]):
        raise TraceError("out min-attempt diagnostic differs from source operand")
    if not same_bits(qr["QR_out_cap_operand_code"], qr["QR_before_code"]):
        raise TraceError("local out cap operand differs from QR entry state")
    expected_prev = np.zeros(shape, dtype=np.float64)
    expected_prev[:, 1:, :] = qr["falk_qr_stored_code"][:, :-1, :]
    if not same_bits(expected_prev, qr["falk_qr_prev_stored_code"]):
        raise TraceError("stored above falk differs from preceding upper-level record")
    expected_above_post = qr["QR_before_code"].copy()
    expected_above_post[:, 1:, :] = qr["QR_after_code"][:, :-1, :]
    if not same_bits(expected_above_post, qr["QR_above_cap_operand_post_update_code"]):
        raise TraceError("arrival cap reservoir differs from upper post-update QR")
    expected_delz_above = np.zeros(shape, dtype=np.float64)
    expected_delz_above[:, 1:, :] = qr["DELZ_code"][:, :-1, :]
    if not same_bits(expected_delz_above, qr["DELZ_above_code"]):
        raise TraceError("arrival thickness differs from upper layer DELZ")
    arr_attempt = np.zeros(shape, dtype=np.float64)
    arr_attempt[:, 1:, :] = (
        qr["falk_qr_prev_stored_code"][:, 1:, :]
        * qr["DELZ_above_code"][:, 1:, :]
        / delz_safe[:, 1:, :]
        * dt[:, 1:, :]
        / dend_safe[:, 1:, :]
    )
    if not same_bits(arr_attempt, qr["dqr_arrival_attempt_reconstructed_code"]):
        raise TraceError(
            "arrival attempt differs from original left-associated expression"
        )
    arr_min = np.minimum(arr_attempt, expected_above_post)
    if not same_bits(arr_min, qr["dqr_arrival_min_attempt_above_diagnostic_code"]):
        raise TraceError("arrival min-attempt diagnostic differs from post-update cap")

    if not same_bits(
        qr["dqr_out_applied_operand_code"][:, 0, :], np.zeros((steps, batch))
    ):
        raise TraceError(
            "top departure has no named dqr operand and must use before-after"
        )
    if not same_bits(
        qr["dqr_arrival_applied_operand_code"][:, 0, :], np.zeros((steps, batch))
    ):
        raise TraceError("top boundary has no arrival")
    if not same_bits(qr["dqr_out_applied_operand_code"][:, 1:, :], out_min[:, 1:, :]):
        raise TraceError("interior applied departure differs from actual dqr_k operand")
    if not same_bits(
        qr["dqr_arrival_applied_operand_code"][:, 1:, :], arr_min[:, 1:, :]
    ):
        raise TraceError("applied arrival differs from actual dqr_above operand")

    realized = qr["QR_before_code"] - qr["QR_after_code"]
    if not same_bits(realized, qr["QR_realized_before_minus_after_code"]):
        raise TraceError("realized before-after field differs")
    # The top update is QR=max(QR-entry - attempt, 0), with no explicit dqr_k.
    post = np.maximum(qr["QR_before_code"] - out_min + arr_min, 0.0)
    post[:, 0, :] = np.maximum(
        qr["QR_before_code"][:, 0, :] - out_attempt[:, 0, :], 0.0
    )
    if not same_bits(post, qr["QR_after_code"]):
        raise TraceError("QR post-state differs from source update equation")
    if np.any(qr["QR_before_code"] < 0) or np.any(qr["QR_after_code"] < 0):
        raise TraceError("QR state is negative")
    expected_fall_after = qr["fall_qr_accum_before_code"] + qr["falk_qr_stored_code"]
    if not same_bits(expected_fall_after, qr["fall_qr_accum_after_code"]):
        raise TraceError(
            "fall accumulator differs from previous fall plus current falk"
        )
    if np.any(qr["fall_qr_accum_before_code"][0] != 0):
        raise TraceError("first substep fall accumulator is not zero")
    if not same_bits(
        qr["fall_qr_accum_before_code"][1:], qr["fall_qr_accum_after_code"][:-1]
    ):
        raise TraceError("fall accumulator does not chain across substeps")
    if not same_bits(qr["QR_before_code"][1:], qr["QR_after_code"][:-1]):
        raise TraceError("QR state does not chain across substeps")
    actual_out = qr["dqr_out_applied_operand_code"].copy()
    # The top source update has no named applied-dqr operand. Its realized
    # departure is the observed before-after state change, not the separate
    # reconstructed min-attempt diagnostic.
    actual_out[:, 0, :] = realized[:, 0, :]
    return actual_out, qr["dqr_arrival_applied_operand_code"].copy(), realized


def parse_surface_trace(
    data: bytes,
    mode: str,
    precip: np.ndarray,
    fall_qr_bottom: np.ndarray,
    delz_bottom: np.ndarray,
    *,
    batch: int = B,
    levels: int = L,
):
    out = {name: np.empty(batch, dtype=np.float64) for name in SURFACE_FLOATS}
    expected_keys = {"schema", "record", "factor_mode", *SURFACE_FLOATS, *SURFACE_INTS}
    row_count = 0
    stream = TextIOWrapper(BytesIO(data), encoding="ascii", newline="")
    try:
        for col, line in enumerate(stream):
            row_count = col + 1
            if col >= batch:
                raise TraceError("surface trace has extra rows")
            row = _fields(line)
            if set(row) != expected_keys:
                raise TraceError("surface trace key set differs")
            if (row.get("schema"), row.get("record"), row.get("factor_mode")) != (
                "kdm6.rain_boundary.v1",
                "surface",
                mode,
            ):
                raise TraceError("surface schema/record/mode mismatch")
            if (
                _integer(row, "call_index"),
                _integer(row, "column"),
                _integer(row, "bottom_level_top0"),
            ) != (0, col, levels - 1):
                raise TraceError("surface call, order, or bottom coordinate mismatch")
            for name in SURFACE_FLOATS:
                out[name][col] = _number(row, name)
    except UnicodeDecodeError as exc:
        raise TraceError("surface trace must be ASCII") from exc
    finally:
        stream.close()
    if row_count != batch:
        raise TraceError(f"surface rows {row_count} != {batch}")
    if np.any(out["dtcld_s"] != DT) or np.any(out["DENR_surface_constant"] != DENR):
        raise TraceError("surface dt or DENR differs from source")
    if not same_bits(out["fall_qr_bottom_code"], fall_qr_bottom):
        raise TraceError(
            "surface QR fall differs from last substep's bottom accumulator"
        )
    if not same_bits(out["DELZ_bottom_m"], delz_bottom):
        raise TraceError("surface bottom DELZ differs from request")
    total_rate = (
        (out["fall_qr_bottom_code"] + out["fall_qs_bottom_code"])
        + out["fall_qg_bottom_code"]
    ) + out["fall_qi_bottom_code"]
    total = surface_component(total_rate, delz_bottom, DT, DENR)
    snow_ice = surface_component(
        out["fall_qs_bottom_code"] + out["fall_qi_bottom_code"], delz_bottom, DT, DENR
    )
    graupel = surface_component(out["fall_qg_bottom_code"], delz_bottom, DT, DENR)
    qr_reported = surface_component(out["fall_qr_bottom_code"], delz_bottom, DT, DENR)
    for name, computed, response in (
        ("surface_total_from_rain_increment_mm", total, precip[0]),
        ("surface_snow_ice_subset_mm", snow_ice, precip[1]),
        ("surface_graupel_subset_mm", graupel, precip[2]),
    ):
        if not same_bits(out[name], computed) or not same_bits(computed, response):
            raise TraceError(f"{name} formula differs from surface trace/response")
    return out, qr_reported


def parse_request(data: bytes, expected_sha: str):
    if sha256(data) != expected_sha or len(data) < IN_HEADER.size:
        raise TraceError("request bytes/hash differ from execution receipt")
    magic, version, batch, levels, dt, nland, nsea = IN_HEADER.unpack_from(data)
    if (magic, version, batch, levels, dt, nland, nsea) != (
        b"K6BATI1\0",
        1,
        B,
        L,
        DT,
        10.0,
        10.0,
    ):
        raise TraceError("request header differs from frozen B512 batch")
    count = (12 + 4) * batch * levels + batch
    if len(data) != IN_HEADER.size + count * 8:
        raise TraceError("request length differs from B,L header")
    v = np.frombuffer(data, dtype="<f8", offset=IN_HEADER.size).copy()
    if not np.isfinite(v).all():
        raise TraceError("request payload contains nonfinite values")
    ns, nf = 12 * batch * levels, 4 * batch * levels
    state = v[:ns].reshape(12, batch, levels)
    forcing = v[ns : ns + nf].reshape(4, batch, levels)
    xland = v[-batch:]
    if not np.isin(xland, (1.0, 2.0)).all() or np.any(forcing <= 0):
        raise TraceError("request XLAND/forcing invalid")
    return state, forcing, xland


def _frozen_case_paths(root: Path, mode: str, chunk: int):
    """Support the frozen public flat chunk layout and an equivalent directory layout."""
    stem = f"chunk-{chunk:05d}"
    directory = root / mode / stem
    if directory.is_dir():
        return (
            directory / "receipt.json",
            directory / "request.bin",
            directory / "response.bin",
        )
    parent = root / mode
    return (
        parent / f"{stem}.receipt.json",
        parent / f"{stem}.request.bin",
        parent / f"{stem}.response.bin",
    )


def analyze_case(
    case_dir: Path,
    frozen_request: Path,
    frozen_response: Path,
    stage_root: Path,
    mode: str,
    chunk: int,
    target: int,
    receipt: dict,
):
    request = (case_dir / "request.bin").read_bytes()
    state, forcing, xland = parse_request(request, receipt["request_sha256"])
    if request != Path(frozen_request).read_bytes():
        raise TraceError("traced request differs from frozen request")
    response_bytes = (case_dir / "response.bin").read_bytes()
    if sha256(response_bytes) != receipt.get("response_sha256"):
        raise TraceError("response hash differs from trace receipt")
    if response_bytes != Path(frozen_response).read_bytes():
        raise TraceError("trace response differs from frozen B512 output")
    response = unpack_response(response_bytes)
    if response["B"] != B or response["L"] != L:
        raise TraceError("response shape differs from B512/L39")
    if not same_bits(response["state_in"], state) or not same_bits(
        response["forcing_in"], forcing
    ):
        raise TraceError("response echo differs from verified request")
    qdata = (case_dir / "trace.qr.tsv").read_bytes()
    sdata = (case_dir / "trace.surface.tsv").read_bytes()
    for name, data in (("trace.qr.tsv", qdata), ("trace.surface.tsv", sdata)):
        meta = receipt["trace_files"].get(name, {})
        if meta.get("sha256") != sha256(data) or meta.get("bytes") != len(data):
            raise TraceError(f"{name} hash/length differs from trace receipt")
    qr = parse_qr_trace(qdata, mode)
    departure, arrival, _realized = validate_qr_trace(qr, state, forcing)
    density = qr["DEND_code"][0].T
    depth = qr["DELZ_code"][0].T
    budgets = []
    for n in range(5):
        budgets.append(
            step_budget(
                qr["QR_before_code"][n].T,
                qr["QR_after_code"][n].T,
                departure[n].T,
                arrival[n].T,
                density,
                depth,
            )
        )
    surface, qr_reported = parse_surface_trace(
        sdata,
        mode,
        response["precip"],
        qr["fall_qr_accum_after_code"][-1, -1, :],
        forcing[3, :, 0],
    )
    total = reported_budget(budgets, qr_reported)
    bottom_arrival = np.array(
        [
            math.fsum(float(step["actual_bottom_arrival"][b]) for step in budgets)
            for b in range(B)
        ]
    )
    initial, final = qr["QR_before_code"][0].T, qr["QR_after_code"][-1].T
    bottom_net = density[:, -1] * depth[:, -1] * (initial[:, -1] - final[:, -1])
    bottom_relation = total["actual_bottom_departure"] - bottom_arrival - bottom_net
    endpoint_delta = np.array(
        [
            math.fsum(float(v) for v in density[b] * depth[b] * (final[b] - initial[b]))
            for b in range(B)
        ]
    )
    endpoint_vs_steps = endpoint_delta - total["state_change"]
    endpoint_gate = np.array(
        [
            256
            * np.finfo(float).eps
            * max(
                1.0,
                math.fsum(
                    float(v)
                    for v in density[b]
                    * depth[b]
                    * (np.abs(initial[b]) + np.abs(final[b]))
                ),
            )
            for b in range(B)
        ]
    )
    step_residual = np.stack(
        [step["state_plus_bottom_plus_internal_residual"] for step in budgets]
    )
    step_gate = np.stack([step["roundoff_gate"] for step in budgets])
    if np.any(np.abs(step_residual) > step_gate):
        raise TraceError("per-substep QR inventory identity exceeds its roundoff gate")
    if np.any(np.abs(bottom_relation) > total["roundoff_gate"]):
        raise TraceError("bottom departure-arrival does not equal QR net depletion")
    if np.any(np.abs(endpoint_vs_steps) > endpoint_gate):
        raise TraceError("substep QR changes do not telescope to endpoint state")
    if np.any(np.abs(total["decomposition_residual"]) > total["roundoff_gate"]):
        raise TraceError("QR plus reported diagnostic decomposition exceeds its gate")
    interface_gaps = np.stack([step["interface_gaps"] for step in budgets])
    qr_diag_minus_bottom = total["reported_bottom_minus_applied"]
    cap_out = np.count_nonzero(
        qr["dqr_out_attempt_reconstructed_code"] > qr["QR_out_cap_operand_code"],
        axis=(0, 1),
    )
    cap_in = np.count_nonzero(
        qr["dqr_arrival_attempt_reconstructed_code"]
        > qr["QR_above_cap_operand_post_update_code"],
        axis=(0, 1),
    )
    post_sed_reference, post_sed_provenance = load_post_sed_qr_reference(
        stage_root, mode, chunk
    )
    post_sed_trace_bottom_first = compare_post_sed_qr(final, post_sed_reference)
    arrays = {
        **{
            f"step_{key}": np.stack([step[key] for step in budgets])
            for key in (
                "state_change",
                "actual_bottom_departure",
                "actual_bottom_arrival",
                "bottom_net_depletion",
                "internal_departure_minus_arrival",
                "state_plus_bottom_plus_internal_residual",
                "roundoff_gate",
            )
        },
        "step_interface_gaps": interface_gaps,
        "qr_state_change": total["state_change"],
        "qr_actual_bottom_departure": total["actual_bottom_departure"],
        "qr_actual_bottom_arrival": bottom_arrival,
        "qr_bottom_net_depletion": bottom_net,
        "qr_internal_departure_minus_arrival": total[
            "internal_departure_minus_arrival"
        ],
        "qr_reported_surface_diagnostic_mm": qr_reported,
        "qr_reported_minus_applied_bottom": qr_diag_minus_bottom,
        "qr_state_plus_qr_reported_diagnostic": total["state_plus_reported"],
        "qr_decomposition_residual": total["decomposition_residual"],
        "qr_decomposition_gate": total["roundoff_gate"],
        "qr_endpoint_delta_minus_step_sum": endpoint_vs_steps,
        "qr_bottom_out_minus_in_minus_net": bottom_relation,
        "outflow_cap_count": cap_out,
        "arrival_cap_count": cap_in,
        "surface_total_precip_mm": response["precip"][0],
        "surface_snow_ice_subset_mm": response["precip"][1],
        "surface_graupel_subset_mm": response["precip"][2],
        "post_sed_qr_top_first": final,
        "post_sed_qr_trace_bottom_first": post_sed_trace_bottom_first,
        "post_sed_qr_reference_bottom_first": post_sed_reference,
    }
    target_rows = []
    for n in range(5):
        for k in range(L):

            def get(key):
                return float(qr[key][n, k, target])

            target_rows.append(
                {
                    "n": n + 1,
                    "level_top0": k,
                    "column_local": target,
                    "mstep": int(qr["mstep"][n, k, target]),
                    "gate": int(qr["gate"][n, k, target]),
                    "DEND": get("DEND_code"),
                    "DELZ": get("DELZ_code"),
                    "QR_before": get("QR_before_code"),
                    "falk_stored": get("falk_qr_stored_code"),
                    "out_attempt": get("dqr_out_attempt_reconstructed_code"),
                    "out_applied": float(departure[n, k, target]),
                    "arrival_attempt": get("dqr_arrival_attempt_reconstructed_code"),
                    "arrival_cap_upper_post": get(
                        "QR_above_cap_operand_post_update_code"
                    ),
                    "arrival_applied": float(arrival[n, k, target]),
                    "QR_after": get("QR_after_code"),
                    "fall_accum_before": get("fall_qr_accum_before_code"),
                    "fall_accum_after": get("fall_qr_accum_after_code"),
                }
            )
    flat = chunk * B + target
    all_gaps = interface_gaps.ravel()
    target_gaps = interface_gaps[:, target, :].ravel()
    selected = {
        "mode": mode,
        "chunk": chunk,
        "column_local": target,
        "flat_index": flat,
        "i0": flat % 234,
        "j0": flat // 234,
        "i1": flat % 234 + 1,
        "j1": flat // 234 + 1,
        "local_mstep": int(qr["mstep"][0, 0, target]),
        "global_mstepmax": 5,
        "state_change_kg_m2": float(total["state_change"][target]),
        "actual_bottom_departure_kg_m2": float(
            total["actual_bottom_departure"][target]
        ),
        "actual_bottom_arrival_kg_m2": float(bottom_arrival[target]),
        "net_bottom_depletion_kg_m2": float(bottom_net[target]),
        "internal_departure_minus_arrival_kg_m2": float(
            total["internal_departure_minus_arrival"][target]
        ),
        "reported_qr_bottom_diagnostic_mm": float(qr_reported[target]),
        "diagnostic_minus_actual_bottom_departure": float(qr_diag_minus_bottom[target]),
        "state_plus_qr_diagnostic": float(total["state_plus_reported"][target]),
        "decomposition_residual": float(total["decomposition_residual"][target]),
        "interface_gap_sign_counts": {
            "positive": int(np.count_nonzero(target_gaps > 0)),
            "negative": int(np.count_nonzero(target_gaps < 0)),
            "zero": int(np.count_nonzero(target_gaps == 0)),
        },
        "outflow_caps": int(cap_out[target]),
        "arrival_caps": int(cap_in[target]),
        "surface_total_precip_mm": float(response["precip"][0, target]),
        "trace_rows": target_rows,
    }
    summary = {
        "columns": B,
        "levels": L,
        "steps": 5,
        "local_mstep_min": int(qr["mstep"][0, 0].min()),
        "local_mstep_max": int(qr["mstep"][0, 0].max()),
        "source_chunk_sha256": receipt["source_chunk_sha256"],
        "request_sha256": receipt["request_sha256"],
        "response_sha256": receipt["response_sha256"],
        "trace_qr_sha256": receipt["trace_files"]["trace.qr.tsv"]["sha256"],
        "trace_surface_sha256": receipt["trace_files"]["trace.surface.tsv"]["sha256"],
        "all_interface_gap_sign_counts": {
            "positive": int(np.count_nonzero(all_gaps > 0)),
            "negative": int(np.count_nonzero(all_gaps < 0)),
            "zero": int(np.count_nonzero(all_gaps == 0)),
        },
        "state_change": _summary_distribution(total["state_change"]),
        "bottom_departure": _summary_distribution(total["actual_bottom_departure"]),
        "bottom_arrival": _summary_distribution(bottom_arrival),
        "bottom_net_depletion": _summary_distribution(bottom_net),
        "internal_gap_sum": _summary_distribution(
            total["internal_departure_minus_arrival"]
        ),
        "reported_minus_applied_bottom": _summary_distribution(qr_diag_minus_bottom),
        "state_plus_qr_diagnostic": _summary_distribution(total["state_plus_reported"]),
        "max_abs_substep_identity_residual": float(
            np.max(np.abs(arrays["step_state_plus_bottom_plus_internal_residual"]))
        ),
        "max_substep_roundoff_gate": float(np.max(arrays["step_roundoff_gate"])),
        "max_abs_endpoint_minus_step_sum": float(np.max(np.abs(endpoint_vs_steps))),
        "max_abs_bottom_relation_residual": float(np.max(np.abs(bottom_relation))),
        "max_abs_decomposition_residual": float(
            np.max(np.abs(total["decomposition_residual"]))
        ),
        "max_decomposition_roundoff_gate": float(np.max(total["roundoff_gate"])),
        "cap_out_events": int(cap_out.sum()),
        "cap_arrival_events": int(cap_in.sum()),
        "post_sed_endpoint": "final QR_after matches the independently saved post_sed water-stage QR profile bitwise after converting top-first trace order to bottom-first stage order",
        "post_sed_reference": {
            **post_sed_provenance,
            "array": "water_stage_state_bottomfirst[1,2,:,:]",
            "stage_index": 1,
            "stage_label": "post_sed",
            "water_species_index": 2,
            "profile_order": "bottomfirst",
            "trace_profile_order": "topfirst",
            "compared_bitwise": True,
        },
    }
    return arrays, selected, summary


def _summary_distribution(values):
    a = np.asarray(values, dtype=np.float64).reshape(-1)
    if not a.size or not np.isfinite(a).all():
        raise TraceError("summary requires finite nonempty values")
    ordered = np.sort(a, kind="stable")
    return {
        "count": int(a.size),
        "min": float(ordered[0]),
        "max": float(ordered[-1]),
        "unweighted_column_mean": math.fsum(float(x) for x in a) / a.size,
    }


def analyze(
    run_root: Path = TRACE_ROOT,
    frozen_root: Path = FROZEN_ROOT,
    output: Path | None = None,
    stage_root: Path = STAGE_ROOT,
):
    run_root, frozen_root, stage_root = (
        Path(run_root),
        Path(frozen_root),
        Path(stage_root),
    )
    if output is None:
        output = run_root / "analysis"
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise TraceError(f"output must be a fresh directory: {output}")
    execution_bytes = (run_root / "execution.json").read_bytes()
    execution = json.loads(execution_bytes)
    build = json.loads((run_root / "build_v2" / "receipt.json").read_text())
    expected_keys = {
        (mode, chunk, trace)
        for mode in MODES
        for chunk in CHUNKS
        for trace in ("off", "on")
    }
    records = execution.get("receipts", [])
    if (
        execution.get("KDM_calls") != 8
        or execution.get("host_steps") != 0
        or execution.get("RTTOV_calls") != 0
    ):
        raise TraceError(
            "execution receipt does not describe the eight value-only calls"
        )
    if (
        len(records) != 8
        or {(r.get("mode"), r.get("batch_index"), r.get("trace")) for r in records}
        != expected_keys
    ):
        raise TraceError("execution receipt case universe differs")
    controller = run_root / "run_traces.py"
    if file_sha(controller) != execution.get("controller_sha256"):
        raise TraceError("trace runner source differs from execution receipt")
    if (
        build.get("translation_units_rebuilt") != 2
        or build.get("operational_install_changed") is not False
    ):
        raise TraceError("QR tracing build is not isolated")
    if set(build.get("changed_object_members", [])) != {
        "sedimentation.cpp.o",
        "coordinator.cpp.o",
    }:
        raise TraceError("unexpected changed archive members")
    tool = run_root / "build_v2" / "ice_factorial_qr_trace"
    archive = run_root / "build_v2" / "libkdm6_qr_trace.a"
    if file_sha(tool) != build.get("batch_tool_sha256") or file_sha(
        archive
    ) != build.get("archive_sha256"):
        raise TraceError("traced tool/archive bytes differ from build receipt")
    output.mkdir(parents=True, exist_ok=False)
    result = {
        "schema": "kdm6.qr_boundary_analysis.v1",
        "scope": "read-only analysis of 8 existing trace-on/off calls; no KDM during analysis",
        "cases": {},
    }
    selected = []
    for mode in MODES:
        for chunk in CHUNKS:
            prior_path, frozen_request, frozen_response = _frozen_case_paths(
                frozen_root, mode, chunk
            )
            prior = json.loads(prior_path.read_text())
            case_key = (mode, chunk, "on")
            receipt = next(
                r
                for r in records
                if (r["mode"], r["batch_index"], r["trace"]) == case_key
            )
            if (
                receipt["tool_sha256"] != build["batch_tool_sha256"]
                or receipt["prior_tool_sha256"] != prior["tool_sha256"]
            ):
                raise TraceError(
                    "trace/prior tool hashes differ from build/frozen receipts"
                )
            for k in (
                "request_sha256",
                "response_sha256",
                "source_chunk_sha256",
                "manifest_sha256",
            ):
                if receipt[k] != prior[k]:
                    raise TraceError(f"trace/frozen {k} mismatch")
            off = next(
                r
                for r in records
                if (r["mode"], r["batch_index"], r["trace"]) == (mode, chunk, "off")
            )
            if (
                off["response_sha256"] != prior["response_sha256"]
                or receipt["response_sha256"] != prior["response_sha256"]
            ):
                raise TraceError("traced/off/frozen response hashes differ")
            case_dir = run_root / "runs" / f"{mode}_chunk{chunk:03d}_on"
            on_files = receipt.get("trace_files", {})
            if set(on_files) != {"trace.qr.tsv", "trace.surface.tsv"}:
                raise TraceError("trace-on receipt files differ")
            arrays, selected_row, case_summary = analyze_case(
                case_dir,
                frozen_request,
                frozen_response,
                stage_root,
                mode,
                chunk,
                TARGET_ROWS[chunk],
                receipt,
            )
            name = f"{mode}_chunk{chunk:03d}.npz"
            with (output / name).open("xb") as stream:
                np.savez_compressed(stream, **arrays)
            case_summary.update({"npz": name, "npz_sha256": file_sha(output / name)})
            result["cases"][f"{mode}_chunk{chunk:03d}"] = case_summary
            selected.append(selected_row)
    result["selected_columns"] = selected
    result["execution_sha256"] = sha256(execution_bytes)
    result["build_receipt_sha256"] = file_sha(run_root / "build_v2" / "receipt.json")
    result["limits"] = [
        "Fixed code-measure DEND*DELZ; physical host mass/area and historical-number certification are outside this trace.",
        "QR-only reported fall diagnostic is distinct from applied QR bottom departure and total ABI surface precipitation.",
        "The final QR profile was independently saved as the post_sed water stage in the earlier B512 run and matches this trace bitwise; this is an endpoint consistency check, not independent validation of the physical budget equations.",
    ]
    with (output / "selected_rows.json").open("x") as stream:
        json.dump(selected, stream, indent=2, allow_nan=False)
    with (output / "summary.json").open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, default=TRACE_ROOT)
    parser.add_argument("--frozen-root", type=Path, default=FROZEN_ROOT)
    parser.add_argument("--stage-root", type=Path, default=STAGE_ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    analyze(args.run_root, args.frozen_root, args.output, args.stage_root)
