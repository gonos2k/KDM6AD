"""Validate and summarize value-only KDM6 activation traces.

This reader does not execute KDM6. Number fields remain in native KDM6
coordinates: their physical number-density basis is not certified here.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np


HEADER = ("call", "stage", "row0", "level_bottom0", "dt_s", "field", "kind", "value")
BATCH = 512
LEVELS = 39
TRACE_ROW = 368
TRACE_LEVELS = (4, 16, 17, 18)
SOURCE_RECEIPT_SCHEMA = "kdm6.block22_activation_observer.v1"
PINNED_SOURCE_SHA256 = "373e77cc9f81bd77603c6993a53cd8dfd5e9b3b401da6e102d90bc16028f280e"
PINNED_COORDINATOR_SHA256 = "fdeff2b8c306a2bcba2c6c9127d36836bce6629a2135d5d80a02175de0ec106f"
PINNED_PRODUCER_SHA256 = "226122484e791cc786d6a52e5bf56888f75a2cc45b161968a1a7939503cc3c17"
TRACE_ENV = "KDM6_BLOCK22_ACTIVATION_TRACE"
NCCN_MIN = 1.0e8
NCCN_MAX = 2.0e10
NCMAX = 5.0e10
QCRMIN = 1.0e-9
QMIN = 1.0e-15
EPS = 1.0e-15
ACTK = 0.6
ACTR = 1.5
DENR = 1000.0
PI = 3.14159265358979323846


class TraceError(ValueError):
    """Malformed, incomplete, or unpinned activation trace."""


STAGE_FIELDS = {
    "micro_entry": ({"t", "qv", "qc", "nc", "nccn"}, set()),
    "post_state_update": ({"t", "qv", "qc", "nc", "nccn"}, set()),
    "post_reclass_ice": ({"t", "qv", "qc", "nc", "nccn"}, set()),
    "post_reclass_rain": ({"t", "qv", "qc", "nc", "nccn"}, set()),
    "post_threshold": ({"t", "qv", "qc", "nc", "nccn"}, set()),
    "post_final_dsd": ({"t", "qv", "qc", "nc", "nccn"}, set()),
    "activation_entry": (
        {"t", "qv", "qc", "nc", "nccn", "qs1", "p", "rho_d", "xl", "cpm"},
        set(),
    ),
    "activation_fraction": (
        {"qs1_safe", "sw_percent", "sw_ratio", "activated_fraction"},
        {"sw_positive", "sw_at_zero", "fraction_saturated", "sw_ratio_at_one"},
    ),
    "activation_pre_gate": (
        {"ncact_raw", "ncact_capped"},
        {"raw_zero", "reservoir_tie", "reservoir_cap"},
    ),
    "activation_gated": (
        {"ncact", "pcact_raw", "pcact"},
        {"qv_cap_tie", "qv_cap"},
    ),
    "post_activation": (
        {"qv_pp_raw", "qv_pp", "qc_pp", "t_pp", "nc_pp", "nccn_pp", "qs1_pp"},
        set(),
    ),
    "post_satadj": (
        {
            "qv_final", "qc_final", "t_final", "nc_final", "nccn_final_raw",
            "nccn_final", "nc_evap_amount", "pcond",
        },
        {
            "complete_evap", "pcond_positive", "nccn_below_min", "nccn_at_min",
            "nccn_at_max", "nccn_above_max",
        },
    ),
    "threshold_masks": (
        set(), {"keep_qc", "keep_qi", "keep_qr", "keep_qs", "keep_qg"}
    ),
    "final_dsd_before_absolute_cap": (
        {"nc_before", "nc_snapped", "nc_gated", "ncmin", "nc_at_max"},
        {
            "nc_snap_gate", "nc_snap_changed", "nc_at_absolute_max",
            "nc_absolute_cap_would_apply",
        },
    ),
}
REQUIRED_STAGES = (
    "micro_entry",
    "post_state_update",
    "post_reclass_ice",
    "post_reclass_rain",
    "activation_entry",
    "activation_fraction",
    "activation_pre_gate",
    "activation_gated",
    "post_activation",
    "post_satadj",
    "threshold_masks",
    "post_threshold",
    "final_dsd_before_absolute_cap",
    "post_final_dsd",
)
TRACE_RECORD_ORDER = ("micro_entry", "schedule", *REQUIRED_STAGES[1:])
SCHEDULE_FIELDS = ("mstepmax_main", "mstep_main", "mstepmax_ice", "mstep_ice")
TIE_FIELDS = (
    ("activation_fraction", "sw_at_zero"),
    ("activation_fraction", "sw_ratio_at_one"),
    ("activation_pre_gate", "reservoir_tie"),
    ("activation_gated", "qv_cap_tie"),
    ("post_satadj", "complete_evap"),
    ("post_satadj", "nccn_at_min"),
    ("post_satadj", "nccn_at_max"),
    ("final_dsd_before_absolute_cap", "nc_at_absolute_max"),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256(Path(path).read_bytes())


def _int(text: str, key: str) -> int:
    if not re.fullmatch(r"-?\d+", text):
        raise TraceError(f"{key} must be an integer")
    return int(text)


def _finite(text: str, key: str) -> float:
    try:
        value = float(text)
    except ValueError as exc:
        raise TraceError(f"{key} must be numeric") from exc
    if not math.isfinite(value):
        raise TraceError(f"{key} must be finite")
    return value


def _sample_value(text: str, kind: str, key: str):
    value = _finite(text, key)
    if kind == "bool":
        if value not in (0.0, 1.0):
            raise TraceError(f"{key} boolean sample must be 0 or 1")
        return bool(value)
    return value


def _receipt(path: Path) -> dict:
    raw = Path(path).read_bytes()
    try:
        receipt = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TraceError("source receipt must be valid UTF-8 JSON") from exc
    expected = {
        "schema": SOURCE_RECEIPT_SCHEMA,
        "source_sha256": PINNED_SOURCE_SHA256,
        "coordinator_sha256": PINNED_COORDINATOR_SHA256,
        "producer_sha256": PINNED_PRODUCER_SHA256,
        "trace_env": TRACE_ENV,
        "B": BATCH,
        "L": LEVELS,
        "row0": TRACE_ROW,
        "levels_bottom0": list(TRACE_LEVELS),
    }
    for key, value in expected.items():
        if receipt.get(key) != value:
            raise TraceError(f"source receipt {key} does not match pinned observer")
    return {
        "name": Path(path).name,
        "sha256": sha256(raw),
        "schema": receipt["schema"],
        "source_sha256": receipt["source_sha256"],
        "coordinator_sha256": receipt["coordinator_sha256"],
        "producer_sha256": receipt["producer_sha256"],
        "trace_env": receipt["trace_env"],
        "scope": receipt.get("scope", ""),
    }


def _bits(text: str, key: str) -> np.ndarray:
    byte_count = BATCH * LEVELS // 8
    if len(text) != byte_count * 2 or not re.fullmatch(r"[0-9a-fA-F]+", text):
        raise TraceError(f"{key} bit payload must be {byte_count * 2} hex characters")
    raw = bytes.fromhex(text)
    unpacked = np.unpackbits(np.frombuffer(raw, dtype=np.uint8), bitorder="little")
    if unpacked.size != BATCH * LEVELS:
        raise TraceError(f"{key} bit payload has wrong size")
    return unpacked.reshape(BATCH, LEVELS).astype(bool)


def read_trace(trace_path: Path, receipt_path: Path) -> dict:
    """Read, pin, and validate all 14 stages plus each full B512 schedule."""
    trace_path = Path(trace_path)
    trace_raw = trace_path.read_bytes()
    receipt = _receipt(Path(receipt_path))
    try:
        text = trace_raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TraceError("trace must be UTF-8 TSV") from exc
    rows = csv.reader(text.splitlines(), delimiter="\t")
    if tuple(next(rows, ())) != HEADER:
        raise TraceError(f"trace header must be exactly {HEADER}")

    # Each call keeps selected samples, complete masks, and schedule vectors apart.
    calls: dict[int, dict] = {}
    seen = set()
    for line_no, row in enumerate(rows, start=2):
        if len(row) != len(HEADER):
            raise TraceError(f"line {line_no} must have {len(HEADER)} TSV columns")
        call_text, stage, row_text, level_text, dt_text, field, kind, value_text = row
        call = _int(call_text, f"line {line_no} call")
        row0 = _int(row_text, f"line {line_no} row0")
        level = _int(level_text, f"line {line_no} level_bottom0")
        dt = _finite(dt_text, f"line {line_no} dt_s")
        if call < 1 or dt <= 0.0 or not field:
            raise TraceError(f"invalid call, dt_s, or field at line {line_no}")
        if stage not in (*REQUIRED_STAGES, "schedule"):
            raise TraceError(f"unknown stage {stage!r} at line {line_no}")
        key = (call, stage, row0, level, field)
        if key in seen:
            raise TraceError(f"duplicate trace record {key}")
        seen.add(key)
        item = calls.setdefault(
            call, {"dt_s": dt, "samples": {}, "bits": {}, "schedule": {}}
        )
        if item["dt_s"] != dt:
            raise TraceError(f"dt_s differs within call {call}")

        if stage == "schedule":
            if kind != "f64" or level != -1 or field not in SCHEDULE_FIELDS:
                raise TraceError(f"invalid schedule record at line {line_no}")
            if row0 != -1 and not 0 <= row0 < BATCH:
                raise TraceError(f"schedule row0 out of range at line {line_no}")
            item["schedule"].setdefault(field, {})[row0] = _finite(
                value_text, f"line {line_no} schedule value"
            )
            continue

        float_fields, bool_fields = STAGE_FIELDS[stage]
        if row0 == -1 and level == -1:
            if field not in bool_fields or kind != "bits":
                raise TraceError(f"only bool fields may carry full B512 bits at line {line_no}")
            item["bits"].setdefault(stage, {})[field] = _bits(
                value_text, f"line {line_no} {stage}.{field}"
            )
            continue
        if row0 != TRACE_ROW or level not in TRACE_LEVELS:
            raise TraceError(f"sample must be row {TRACE_ROW}, levels {TRACE_LEVELS} at line {line_no}")
        if field in float_fields and kind == "f64":
            value = _sample_value(value_text, kind, f"line {line_no} {field}")
        elif field in bool_fields and kind == "bool":
            value = _sample_value(value_text, kind, f"line {line_no} {field}")
        else:
            raise TraceError(f"field/kind mismatch for {stage}.{field} at line {line_no}")
        item["samples"].setdefault(stage, {}).setdefault(field, {})[level] = value

    if not calls:
        raise TraceError("trace contains no records")
    ordinals = sorted(calls)
    if ordinals != list(range(1, len(ordinals) + 1)):
        raise TraceError("call ordinals must be consecutive from 1")
    for call, item in calls.items():
        if set(item["samples"]) != set(REQUIRED_STAGES):
            missing = sorted(set(REQUIRED_STAGES) - set(item["samples"]))
            extra = sorted(set(item["samples"]) - set(REQUIRED_STAGES))
            raise TraceError(f"call {call} stage coverage mismatch; missing={missing}, extra={extra}")
        for stage in REQUIRED_STAGES:
            float_fields, bool_fields = STAGE_FIELDS[stage]
            observed = item["samples"][stage]
            if set(observed) != float_fields | bool_fields:
                raise TraceError(f"call {call} {stage} field coverage mismatch")
            for field in float_fields | bool_fields:
                if set(observed[field]) != set(TRACE_LEVELS):
                    raise TraceError(f"call {call} {stage}.{field} sample levels incomplete")
        expected_bits = {
            stage: fields
        for stage, (_, fields) in STAGE_FIELDS.items()
            if fields
        }
        if set(item["bits"]) != set(expected_bits):
            raise TraceError(f"call {call} full boolean stage coverage mismatch")
        for stage, fields in expected_bits.items():
            if set(item["bits"][stage]) != fields:
                raise TraceError(f"call {call} {stage} full boolean field coverage mismatch")
            for field, array in item["bits"][stage].items():
                for level in TRACE_LEVELS:
                    bit_value = bool(array[TRACE_ROW, level])
                    if item["samples"][stage][field][level] != bit_value:
                        raise TraceError(f"call {call} {stage}.{field} sample disagrees with full mask")
        if set(item["schedule"]) != set(SCHEDULE_FIELDS):
            raise TraceError(f"call {call} schedule field coverage mismatch")
        for field in ("mstepmax_main", "mstepmax_ice"):
            if set(item["schedule"][field]) != {-1}:
                raise TraceError(f"call {call} schedule {field} must contain only the recorded maximum")
        for field in ("mstep_main", "mstep_ice"):
            values = item["schedule"][field]
            if set(values) != set(range(BATCH)):
                raise TraceError(f"call {call} schedule {field} must cover all 512 rows")
        for field in SCHEDULE_FIELDS:
            values = item["schedule"][field]
            if any(
                value < 1.0 or value > 100.0 or not value.is_integer()
                for value in values.values()
            ):
                raise TraceError(f"call {call} schedule {field} values must be integers in 1..100")
        for field in ("mstepmax_main", "mstepmax_ice"):
            values = item["schedule"][field]
            maximum = int(values[-1])
            vector_field = field.replace("mstepmax_", "mstep_")
            if maximum != int(max(item["schedule"][vector_field].values())):
                raise TraceError(f"call {call} schedule maximum {field} differs from full B512 schedule")
        # Keep JSON-serializable summary inputs while retaining NumPy masks for comparisons.
        item["schedule"] = {
            field: np.asarray([values[row] for row in range(BATCH)], dtype=np.int64)
            if field.startswith("mstep_")
            else int(values[-1])
            for field, values in item["schedule"].items()
        }
        item["branch_counts"] = _branch_counts(item["bits"])

    return {
        "trace_name": trace_path.name,
        "trace_sha256": sha256(trace_raw),
        "source_receipt": receipt,
        "calls": calls,
    }


def _branch_counts(bits: dict) -> dict:
    result = {}
    for stage, fields in bits.items():
        result[stage] = {}
        for field, array in fields.items():
            packed = np.packbits(array.reshape(-1).astype(np.uint8), bitorder="little").tobytes()
            canonical = array.astype(np.uint8, copy=False).tobytes(order="C")
            result[stage][field] = {
                "true_cells": int(np.count_nonzero(array)),
                "false_cells": int(array.size - np.count_nonzero(array)),
                "cells": int(array.size),
                "bool_array_sha256": sha256(canonical),
                "packed_little_bitorder_sha256": sha256(packed),
            }
    return result


def _activation_constant() -> float:
    """Reproduce the source's explicitly step-rounded float32 mass constant."""
    f32 = np.float32
    ax = f32(f32(ACTR) * f32(1.0e-6))
    ax3 = f32(f32(ax * ax) * ax)
    pi_f = f32(PI)
    k_f = f32(f32(f32(f32(4.0) * pi_f) * f32(DENR)) * ax3)
    return float(k_f)


PCACT_MASS_CONST = _activation_constant()


def _get(samples: dict, stage: str, field: str, level: int):
    try:
        return samples[stage][field][level]
    except KeyError as exc:
        raise TraceError(f"missing sample {stage}.{field} at level {level}") from exc


def _activation_formula(samples: dict, level: int, dt: float) -> dict:
    entry = samples["activation_entry"]
    qv = float(entry["qv"][level])
    nc = float(entry["nc"][level])
    nccn = float(entry["nccn"][level])
    qs1_safe = max(float(entry["qs1"][level]), QCRMIN)
    sw = (qv / qs1_safe - 1.0) * 100.0
    ratio = max(sw / 0.48, 0.0)
    fraction = min(1.0, max(ratio, EPS) ** ACTK)
    # These separate Python operations mirror the source's non-fused order.
    ncact_numerator = max((nccn + nc) * fraction - nc, 0.0)
    ncact_raw = ncact_numerator / dt
    ncact_capped = min(ncact_raw, max(nccn, 0.0) / dt)
    ncact = ncact_capped if sw > 0.0 else 0.0
    qv_cap = max(qv, 0.0) / dt
    rho_d = float(entry["rho_d"][level])
    pcact_raw = PCACT_MASS_CONST * ncact / (3.0 * rho_d)
    pcact = min(pcact_raw, qv_cap)
    return {
        "qs1_safe": qs1_safe,
        "sw_percent": sw,
        "sw_ratio": ratio,
        "activated_fraction": fraction,
        "ncact_raw": ncact_raw,
        "ncact_capped": ncact_capped,
        "ncact": ncact,
        "pcact_raw": pcact_raw,
        "pcact": pcact,
        "qv_cap": qv_cap,
    }


def _same_value(actual, expected):
    return bool(float(actual) == float(expected))


def _same_float64_bits(actual, expected):
    left = np.asarray(float(actual), dtype="<f8").tobytes()
    right = np.asarray(float(expected), dtype="<f8").tobytes()
    return left == right


def _replay(samples: dict, level: int, dt: float) -> dict:
    entry = samples["activation_entry"]
    frac = samples["activation_fraction"]
    rates = samples["activation_gated"]
    gate = bool(frac["sw_positive"][level])
    qv = float(entry["qv"][level])
    qc = float(entry["qc"][level])
    temp = float(entry["t"][level])
    nc = float(entry["nc"][level])
    nccn = float(entry["nccn"][level])
    pcact = float(rates["pcact"][level])
    ncact = float(rates["ncact"][level])
    xl = float(entry["xl"][level])
    cpm_safe = max(float(entry["cpm"][level]), QCRMIN)

    qv_raw = qv - pcact * dt
    qv_pp = max(qv_raw, 0.0) if gate else qv_raw
    qc_pp = max(qc + pcact * dt, 0.0)
    t_pp = temp + (pcact * xl / cpm_safe) * dt
    nc_pp = max(nc + ncact * dt, 0.0)
    nccn_pp = max(nccn - ncact * dt, 0.0)

    sat = samples["post_satadj"]
    pcond = float(sat["pcond"][level])
    complete = bool(sat["complete_evap"][level])
    evap_amount = nc_pp if complete else 0.0
    nc_final = max(nc_pp - evap_amount, 0.0)
    nccn_raw = nccn_pp + evap_amount
    qv_final = qv_pp - pcond * dt
    qc_final = max(qc_pp + pcond * dt, 0.0)
    t_final = t_pp + (pcond * xl / cpm_safe) * dt
    nccn_final = min(max(nccn_raw, NCCN_MIN), NCCN_MAX)

    keep_qc = bool(samples["threshold_masks"]["keep_qc"][level])
    qc_threshold = qc_final if keep_qc else 0.0
    nc_threshold = nc_final if keep_qc else 0.0
    dsd = samples["final_dsd_before_absolute_cap"]
    nc_gated = float(dsd["nc_snapped"][level]) if bool(dsd["nc_snap_gate"][level]) else float(dsd["nc_before"][level])
    nc_dsd = float(dsd["nc_at_max"][level]) if bool(dsd["nc_absolute_cap_would_apply"][level]) else nc_gated
    return {
        "post_activation": {
            "qv_pp_raw": qv_raw, "qv_pp": qv_pp, "qc_pp": qc_pp,
            "t_pp": t_pp, "nc_pp": nc_pp, "nccn_pp": nccn_pp,
        },
        "post_satadj": {
            "qv_final": qv_final, "qc_final": qc_final, "t_final": t_final,
            "nc_final": nc_final, "nccn_final_raw": nccn_raw,
            "nccn_final": nccn_final, "nc_evap_amount": evap_amount,
        },
        "post_threshold": {"qc": qc_threshold, "nc": nc_threshold, "nccn": nccn_final},
        "post_final_dsd": {"nc": nc_dsd, "nccn": nccn_final},
    }


def _branch_flag_checks(samples: dict, level: int, dt: float) -> dict:
    formula = _activation_formula(samples, level, dt)
    entry = samples["activation_entry"]
    postact = samples["post_activation"]
    sat = samples["post_satadj"]
    dsd = samples["final_dsd_before_absolute_cap"]
    qc_after = float(sat["qc_final"][level])
    nc_before = float(dsd["nc_before"][level])
    nc_snapped = float(dsd["nc_snapped"][level])
    nc_gated = float(dsd["nc_gated"][level])
    nccn_raw = float(sat["nccn_final_raw"][level])
    pcond = float(sat["pcond"][level])
    dt_value = float(dt)

    expected = {
        ("activation_fraction", "sw_positive"): formula["sw_percent"] > 0.0,
        ("activation_fraction", "sw_at_zero"): formula["sw_percent"] == 0.0,
        ("activation_fraction", "fraction_saturated"): formula["activated_fraction"] >= 1.0,
        ("activation_fraction", "sw_ratio_at_one"): formula["sw_ratio"] == 1.0,
        ("activation_pre_gate", "raw_zero"): formula["ncact_raw"] <= 0.0,
        ("activation_pre_gate", "reservoir_tie"): formula["ncact_raw"] == max(float(entry["nccn"][level]), 0.0) / dt_value,
        ("activation_pre_gate", "reservoir_cap"): formula["ncact_raw"] > max(float(entry["nccn"][level]), 0.0) / dt_value,
        ("activation_gated", "qv_cap_tie"): formula["pcact_raw"] == max(float(entry["qv"][level]), 0.0) / dt_value,
        ("activation_gated", "qv_cap"): formula["pcact_raw"] > max(float(entry["qv"][level]), 0.0) / dt_value,
        ("post_satadj", "complete_evap"): pcond == -float(postact["qc_pp"][level]) / dt_value,
        ("post_satadj", "pcond_positive"): pcond > 0.0,
        ("post_satadj", "nccn_below_min"): nccn_raw < NCCN_MIN,
        ("post_satadj", "nccn_at_min"): nccn_raw == NCCN_MIN,
        ("post_satadj", "nccn_at_max"): nccn_raw == NCCN_MAX,
        ("post_satadj", "nccn_above_max"): nccn_raw > NCCN_MAX,
        ("threshold_masks", "keep_qc"): qc_after > QMIN,
        ("final_dsd_before_absolute_cap", "nc_snap_gate"): nc_before >= float(dsd["ncmin"][level]),
        ("final_dsd_before_absolute_cap", "nc_snap_changed"): nc_snapped != nc_before,
        ("final_dsd_before_absolute_cap", "nc_at_absolute_max"): nc_gated == NCMAX,
        ("final_dsd_before_absolute_cap", "nc_absolute_cap_would_apply"): nc_gated > NCMAX,
    }
    checks = {}
    for (stage, field), expected_value in expected.items():
        observed = bool(samples[stage][field][level])
        checks[f"{stage}.{field}"] = {
            "captured": observed,
            "source_operand_recomputed": bool(expected_value),
            "matches": observed == bool(expected_value),
        }
    return {
        "checks": checks,
        "all_recomputed_flags_match": all(item["matches"] for item in checks.values()),
        "not_recomputed_due_to_missing_state_operands": [
            "threshold_masks.keep_qi",
            "threshold_masks.keep_qr",
            "threshold_masks.keep_qs",
            "threshold_masks.keep_qg",
        ],
    }


def _field_residuals(actual: dict, replay: dict) -> dict:
    result = {}
    for field, expected in replay.items():
        if field in actual:
            observed = float(actual[field])
            result[field] = {
                "captured": observed,
                "recomputed_source_order": float(expected),
                "captured_minus_recomputed": observed - float(expected),
                "exact_equal": _same_value(observed, expected),
                "same_binary64_bits": _same_float64_bits(observed, expected),
                "captured_signbit": bool(np.signbit(observed)),
                "recomputed_signbit": bool(np.signbit(float(expected))),
            }
    return result


def _pair_change(
    donor_name: str,
    receiver_name: str,
    donor_before: float,
    receiver_before: float,
    donor_after: float,
    receiver_after: float,
    signed_transfer: float,
) -> dict:
    """Compare captured species changes with a signed donor-to-receiver amount."""
    donor_delta = donor_after - donor_before
    receiver_delta = receiver_after - receiver_before
    return {
        "accounting_order": "differences of captured f64 species endpoints; math.fsum combines those two differences",
        "signed_transfer_amount": signed_transfer,
        "donor_delta": donor_delta,
        "receiver_delta": receiver_delta,
        "species_delta": {
            donor_name: donor_delta,
            receiver_name: receiver_delta,
        },
        "species_delta_fsum": math.fsum([donor_delta, receiver_delta]),
        "endpoint_sum_difference": (donor_after + receiver_after)
        - (donor_before + receiver_before),
        "donor_delta_plus_transfer_residual": donor_delta + signed_transfer,
        "receiver_delta_minus_transfer_residual": receiver_delta - signed_transfer,
        "species_rate_transfer_residuals": {
            donor_name: donor_delta + signed_transfer,
            receiver_name: receiver_delta - signed_transfer,
        },
    }


def _target_report(samples: dict, level: int, dt: float) -> dict:
    formula = _activation_formula(samples, level, dt)
    replay = _replay(samples, level, dt)
    entry = samples["activation_entry"]
    before_nc = float(entry["nc"][level])
    before_nn = float(entry["nccn"][level])
    act = samples["post_activation"]
    sat = samples["post_satadj"]
    threshold = samples["post_threshold"]
    final = samples["post_final_dsd"]
    postact_sum = float(act["nc_pp"][level]) + float(act["nccn_pp"][level])
    postsat_raw_sum = float(sat["nc_final"][level]) + float(sat["nccn_final_raw"][level])
    postsat_clamped_sum = float(sat["nc_final"][level]) + float(sat["nccn_final"][level])
    before_qv = float(entry["qv"][level])
    before_qc = float(entry["qc"][level])
    before_nc = float(entry["nc"][level])
    before_nn = float(entry["nccn"][level])
    after_qv_act = float(act["qv_pp"][level])
    after_qc_act = float(act["qc_pp"][level])
    after_nc_act = float(act["nc_pp"][level])
    after_nn_act = float(act["nccn_pp"][level])
    qv_after_act = float(sat["qv_final"][level])
    qc_after_act = float(sat["qc_final"][level])
    ncact_amount = float(samples["activation_gated"]["ncact"][level]) * dt
    pcact_amount = float(samples["activation_gated"]["pcact"][level]) * dt
    pcond_amount = float(sat["pcond"][level]) * dt
    stage_fields = (
        ("activation_entry", ("t", "qv", "qc", "nc", "nccn", "qs1", "p", "rho_d", "xl", "cpm")),
        ("activation_fraction", ("sw_percent", "sw_ratio", "activated_fraction")),
        ("activation_pre_gate", ("ncact_raw", "ncact_capped")),
        ("activation_gated", ("ncact", "pcact_raw", "pcact")),
        ("post_activation", ("qv_pp", "qc_pp", "t_pp", "nc_pp", "nccn_pp", "qs1_pp")),
        ("post_satadj", ("qv_final", "qc_final", "t_final", "nc_final", "nccn_final_raw", "nccn_final", "pcond", "nc_evap_amount")),
        ("post_threshold", ("qv", "qc", "t", "nc", "nccn")),
        ("final_dsd_before_absolute_cap", ("nc_before", "nc_snapped", "nc_gated", "ncmin", "nc_at_max")),
        ("post_final_dsd", ("qv", "qc", "t", "nc", "nccn")),
    )
    table = {
        stage: {field: float(samples[stage][field][level]) for field in fields}
        for stage, fields in stage_fields
    }
    table["activation_fraction"]["sw_positive"] = bool(samples["activation_fraction"]["sw_positive"][level])
    table["post_satadj"]["complete_evap"] = bool(sat["complete_evap"][level])
    number = {
        "coordinate_scope": "raw NC/NCCN KDM state coordinates; physical number-density units are not certified",
        "before_activation_sum": before_nc + before_nn,
        "post_activation_sum": postact_sum,
        "post_satadj_before_nccn_clamp_sum": postsat_raw_sum,
        "post_satadj_after_nccn_clamp_sum": postsat_clamped_sum,
        "nccn_clamp_add_coordinate": float(sat["nccn_final"][level]) - float(sat["nccn_final_raw"][level]),
        "post_threshold_sum": float(threshold["nc"][level]) + float(threshold["nccn"][level]),
        "post_final_dsd_sum": float(final["nc"][level]) + float(final["nccn"][level]),
        "post_activation_pair_delta": postact_sum - (before_nc + before_nn),
        "post_activation_pair_species_change_fsum_coordinate": math.fsum(
            [after_nc_act - before_nc, after_nn_act - before_nn]
        ),
        "complete_evap_transfer_coordinate": float(sat["nc_evap_amount"][level]),
        "activation_rate_transfer_and_residuals": _pair_change(
            "NCCN", "NC", before_nn, before_nc, after_nn_act, after_nc_act, ncact_amount
        ),
        "activation_pcact_mass_pair_and_residuals_kg_kg": _pair_change(
            "QV", "QC", before_qv, before_qc, after_qv_act, after_qc_act, pcact_amount
        ),
        "satadj_pcond_mass_pair_and_residuals_kg_kg": _pair_change(
            "QV", "QC", after_qv_act, after_qc_act, qv_after_act, qc_after_act, pcond_amount
        ),
        "pair_accounting_limit": "rate-times-dt and endpoint coordinate arithmetic only; not a physical number-unit or whole-microphysics closure certification",
    }
    replay_residuals = {}
    for stage in ("post_activation", "post_satadj", "post_threshold", "post_final_dsd"):
        actual_stage = {
            field: values[level] for field, values in samples[stage].items()
        }
        expected_stage = replay[stage]
        replay_residuals[stage] = _field_residuals(actual_stage, expected_stage)
    formula_residuals = {}
    source_fields = {
        "activation_fraction": ("qs1_safe", "sw_percent", "sw_ratio", "activated_fraction"),
        "activation_pre_gate": ("ncact_raw", "ncact_capped"),
        "activation_gated": ("ncact", "pcact_raw", "pcact"),
    }
    for stage, fields in source_fields.items():
        formula_residuals[stage] = {
            field: {
                "captured": float(samples[stage][field][level]),
                "recomputed_source_formula": float(formula[field]),
                "captured_minus_recomputed": float(samples[stage][field][level]) - float(formula[field]),
                "exact_equal": _same_value(samples[stage][field][level], formula[field]),
                "same_binary64_bits": _same_float64_bits(samples[stage][field][level], formula[field]),
                "captured_signbit": bool(np.signbit(float(samples[stage][field][level]))),
                "recomputed_signbit": bool(np.signbit(float(formula[field]))),
            }
            for field in fields
        }
    return {
        "level_bottom0": level,
        "stage_values": table,
        "captured_branch_flag_checks": _branch_flag_checks(samples, level, dt),
        "source_formula_replay": {
            "kind": "independent Python float64 replay in documented source operation order; comparison is reported, not asserted bitwise",
            "pcact_mass_constant_float32_rounded": PCACT_MASS_CONST,
            "formula_values": formula,
            "captured_vs_recomputed": formula_residuals,
        },
        "state_replay_using_captured_rates_and_operands": {
            "kind": "source-ordered algebra replay from captured rates, masks, and operands; not a new KDM execution",
            "captured_vs_recomputed": replay_residuals,
        },
        "NC_plus_NCCN_coordinate_ledger": number,
    }


def analyze_trace(parsed: dict) -> dict:
    """Build per-call target tables, full-B branch counts, and schedule summaries."""
    calls = []
    for ordinal in sorted(parsed["calls"]):
        item = parsed["calls"][ordinal]
        samples = item["samples"]
        schedules = item["schedule"]
        calls.append(
            {
                "call": ordinal,
                "dt_s": item["dt_s"],
                "schedule": {
                    "mstepmax_main": int(schedules["mstepmax_main"]),
                    "mstepmax_ice": int(schedules["mstepmax_ice"]),
                    "mstep_main_counts": _counts(schedules["mstep_main"]),
                    "mstep_ice_counts": _counts(schedules["mstep_ice"]),
                },
                "branch_masks": item["branch_counts"],
                "targets": [_target_report(samples, level, item["dt_s"]) for level in TRACE_LEVELS],
            }
        )
    return {
        "schema": "kdm6.block22_activation_analysis.v1",
        "analysis_producer_sha256": file_sha256(Path(__file__)),
        "trace": {k: v for k, v in parsed.items() if k != "calls"},
        "required_stages": list(REQUIRED_STAGES),
        "trace_record_order": list(TRACE_RECORD_ORDER),
        "source_contract": {
            "sw_percent": "(qv / max(qs1, QCRMIN) - 1) * 100",
            "activated_fraction": "min(1, max(sw_percent / 0.48, 0, EPS) ** ACTK)",
            "ncact_raw": "max((nccn + nc) * activated_fraction - nc, 0) / dt_s",
            "ncact": "min(ncact_raw, max(nccn, 0) / dt_s), then zero when sw_percent <= 0",
            "pcact": "min(PCACT_MASS_CONST * ncact / (3 * rho_d), max(qv, 0) / dt_s)",
            "mass_coordinate_units": {
                "qv_qc": "kg/kg",
                "pcact_pcond": "kg/kg/s",
                "temperature": "K",
                "rho_d": "kg/m3",
                "pressure": "Pa",
                "dt": "s",
            },
            "number_coordinate_units": "NC/NCCN and ncact retain native KDM coordinates; physical number-density basis is unverified and no absolute m^-3 certification is made",
            "constants": {
                "QCRMIN": QCRMIN,
                "QMIN": QMIN,
                "EPS": EPS,
                "ACTK": ACTK,
                "NCCN_MIN": NCCN_MIN,
                "NCCN_MAX": NCCN_MAX,
                "NCMAX": NCMAX,
                "PCACT_MASS_CONST_float32_rounded": PCACT_MASS_CONST,
            },
        },
        "calls": calls,
        "interpretation_limits": [
            "This is an offline analysis of observer captures; it does not execute or replay KDM6.",
            "NC/NCCN sums and clamp additions are native state-coordinate accounting only; their physical number-density unit is not certified.",
            "Branch masks cover the recorded activation, cleanup, and DSD predicates only; they are not a complete proof of all internal branches or a finite-difference derivative.",
            "Numerical formula comparisons use Python float64 source-order replay and report residuals without asserting bitwise parity.",
        ],
    }


def _counts(values: np.ndarray) -> dict:
    unique, counts = np.unique(values, return_counts=True)
    return {str(int(value)): int(count) for value, count in zip(unique, counts)}


def compare_branches(base: dict, probe: dict) -> dict:
    """Compare captured bool masks by call; this is not complete internal-branch proof."""
    if sorted(base["calls"]) != sorted(probe["calls"]):
        raise TraceError("base and probe call ordinals differ")
    results = []
    for ordinal in sorted(base["calls"]):
        base_call = base["calls"][ordinal]
        probe_call = probe["calls"][ordinal]
        if base_call["dt_s"] != probe_call["dt_s"]:
            raise TraceError(f"base/probe dt_s differs at call {ordinal}")
        left = base_call["bits"]
        right = probe_call["bits"]
        if set(left) != set(right):
            raise TraceError(f"base/probe boolean stages differ at call {ordinal}")
        fields = []
        for stage in sorted(left):
            if set(left[stage]) != set(right[stage]):
                raise TraceError(f"base/probe boolean fields differ at call {ordinal} {stage}")
            for field in sorted(left[stage]):
                a, b = left[stage][field], right[stage][field]
                fields.append(
                    {
                        "stage": stage,
                        "field": field,
                        "changed_cells": int(np.count_nonzero(a != b)),
                        "base_true_cells": int(np.count_nonzero(a)),
                        "probe_true_cells": int(np.count_nonzero(b)),
                        "target_row0": TRACE_ROW,
                        "target_row_changed_levels": np.flatnonzero(
                            a[TRACE_ROW] != b[TRACE_ROW]
                        ).astype(int).tolist(),
                        "base_true_target_levels": np.flatnonzero(
                            a[TRACE_ROW]
                        ).astype(int).tolist(),
                        "probe_true_target_levels": np.flatnonzero(
                            b[TRACE_ROW]
                        ).astype(int).tolist(),
                    }
                )
        ties = {}
        for stage, field in TIE_FIELDS:
            ties[f"{stage}.{field}"] = {
                "base_tie_cells": int(np.count_nonzero(left[stage][field])),
                "probe_tie_cells": int(np.count_nonzero(right[stage][field])),
            }
        schedule_changes = {}
        for field in ("mstep_main", "mstep_ice"):
            a = base_call["schedule"][field]
            b = probe_call["schedule"][field]
            schedule_changes[field] = {
                "changed_rows": int(np.count_nonzero(a != b)),
                "base_max": int(base_call["schedule"][field.replace("mstep_", "mstepmax_")]),
                "probe_max": int(probe_call["schedule"][field.replace("mstep_", "mstepmax_")]),
            }
        results.append({
            "call": ordinal,
            "schedule_changes": schedule_changes,
            "mask_changes": fields,
            "recorded_tie_counts": ties,
        })
    return {
        "scope": "captured masks and recorded equality predicates only; not complete finite-difference or internal-branch proof",
        "calls": results,
    }


def compare_trace_calls(
    base_trace: dict, base_call: int, probe_trace: dict, probe_call: int
) -> dict:
    """Compare selected call ordinals from separate traces, regardless of ordinal equality."""
    if base_call not in base_trace["calls"] or probe_call not in probe_trace["calls"]:
        raise TraceError("base/probe call ordinal is absent from trace")
    base = {"calls": {1: base_trace["calls"][base_call]}}
    probe = {"calls": {1: probe_trace["calls"][probe_call]}}
    result = compare_branches(base, probe)
    result["base_call"] = int(base_call)
    result["probe_call"] = int(probe_call)
    result["base_trace"] = {
        "trace_name": base_trace["trace_name"],
        "trace_sha256": base_trace["trace_sha256"],
        "source_receipt_sha256": base_trace["source_receipt"]["sha256"],
    }
    result["probe_trace"] = {
        "trace_name": probe_trace["trace_name"],
        "trace_sha256": probe_trace["trace_sha256"],
        "source_receipt_sha256": probe_trace["source_receipt"]["sha256"],
    }
    return result


def compare_call_pair(trace: dict, base_call: int, probe_call: int) -> dict:
    """Compare two call ordinals stored in one trace file."""
    return compare_trace_calls(trace, base_call, trace, probe_call)


def _write_new(path: Path, payload: dict) -> None:
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"output path must be new: {path}")
    encoded = (json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(encoded)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--compare-trace", type=Path)
    parser.add_argument("--compare-receipt", type=Path)
    parser.add_argument("--base-call", type=int)
    parser.add_argument("--probe-call", type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError(f"output path must be new: {args.output}")
    if (args.compare_trace is None) != (args.compare_receipt is None):
        raise TraceError("--compare-trace and --compare-receipt must be supplied together")
    if (args.base_call is None) != (args.probe_call is None):
        raise TraceError("--base-call and --probe-call must be supplied together")
    base = read_trace(args.trace, args.receipt)
    report = analyze_trace(base)
    if args.compare_trace is not None:
        probe = read_trace(args.compare_trace, args.compare_receipt)
        if args.base_call is None:
            report["branch_comparison"] = compare_branches(base, probe)
        else:
            report["branch_comparison"] = compare_trace_calls(
                base, args.base_call, probe, args.probe_call
            )
    elif args.base_call is not None:
        report["branch_comparison"] = compare_call_pair(base, args.base_call, args.probe_call)
    _write_new(args.output, report)
    print(json.dumps({"output": str(args.output), "sha256": file_sha256(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
