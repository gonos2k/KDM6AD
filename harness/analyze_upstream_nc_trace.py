"""Strict offline reader and replay for native pre-KDM QNC scalar records.

The trace is a value-only instrument of the native RK scalar update. It preserves
raw binary32 operand bits; the replay reports exact matches only when an
explicit f32 operation sequence reproduces the recorded output. It does not
infer a physical cause for NC/QC pairs or certify number units.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from typing import Any, Mapping

import numpy as np

from harness.g33_s15_probe import fma32 as _fraction_fma32
from harness.native_moment_trace_records import MomentTraceInventory


MAGIC = "# KDM6AD_UPSTREAM_NC_TRACE_V1"
ROW_HEADER = (
    "VAL", "step", "rk_step", "stage", "i", "k", "j", "field", "dtype", "raw_hex",
)
TARGETS: Mapping[str, tuple[int, int, int]] = {
    "target_221_63_6": (221, 63, 6),
    "target_91_94_4": (91, 94, 4),
}
GENERIC_FIELDS = (
    "QNC", "SCALAR_OLD", "SCALAR_TEND", "ADVECT_TEND", "H_TENDENCY",
    "Z_TENDENCY", "MU_OLD", "MU_NEW", "MU_BASE", "C1H", "C2H",
    "MSFTY", "DT_RK", "TENDEC",
)
PD_FIELDS = (
    "QNC", "SCALAR_OLD", "SCALAR_TEND", "MU_OLD_ARG", "MU_NEW_ARG",
    "MU_BASE", "C1H", "C2H", "DT_RK",
)
STAGE_FIELDS: Mapping[str, tuple[str, ...]] = {
    "RKSCALAR_BEFORE": GENERIC_FIELDS,
    "RKSCALAR_AFTER": GENERIC_FIELDS,
    "RKSCALAR_PD_BEFORE": PD_FIELDS,
    "RKSCALAR_PD_AFTER": PD_FIELDS,
    "PRE_MICROPHYSICS": ("QNC",),
}
_HEX32 = re.compile(r"[0-9A-Fa-f]{8}\Z")
_HEX_BOOL = re.compile(r"(?:00|01)\Z")
Key = tuple[int, int, str, int, int, int, str]


@dataclass(frozen=True)
class UpstreamValue:
    step: int
    rk_step: int
    stage: str
    i: int
    k: int
    j: int
    field: str
    dtype: str
    bits: int | bool

    @property
    def f32(self) -> np.float32:
        if self.dtype != "f32":
            raise TypeError(f"{self.field} at {self.stage} is {self.dtype}, not f32")
        return np.asarray([self.bits], dtype=np.uint32).view(np.float32)[0]

    @property
    def value(self) -> float | bool:
        return bool(self.bits) if self.dtype == "bool" else float(self.f32)

    @property
    def raw_hex(self) -> str:
        if self.dtype == "bool":
            return "01" if self.bits else "00"
        return f"{int(self.bits):08X}"


@dataclass(frozen=True)
class UpstreamNCTrace:
    values: Mapping[Key, UpstreamValue]
    row_order: tuple[Key, ...]
    sha256: str
    byte_count: int
    path_name: str

    def at(
        self, target: tuple[int, int, int], rk_step: int, stage: str, field: str
    ) -> UpstreamValue:
        i, j, k = target
        return self.values[(3, rk_step, stage, i, k, j, field)]


def _key(row: UpstreamValue) -> Key:
    return (row.step, row.rk_step, row.stage, row.i, row.k, row.j, row.field)


def read_upstream_nc_trace(path: str | Path) -> UpstreamNCTrace:
    """Parse the strict single-file V1 trace, preserving f32 bits and row order."""
    source = Path(path)
    raw = source.read_bytes()
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("upstream trace must be ASCII") from exc
    if not lines or lines[0] != MAGIC:
        raise ValueError(f"trace must start with the exact {MAGIC!r} header")

    row_start = 1
    if len(lines) > 1 and lines[1].startswith("#"):
        if tuple(lines[1][1:].split()) != ROW_HEADER:
            raise ValueError("trace row-header comment does not match the V1 column schema")
        row_start = 2

    values: dict[Key, UpstreamValue] = {}
    order: list[Key] = []
    allowed_coords = set(TARGETS.values())
    for line_no, line in enumerate(lines[row_start:], start=row_start + 1):
        if not line:
            raise ValueError(f"line {line_no}: blank rows are not allowed")
        parts = line.split()
        if len(parts) != 10 or parts[0] != "VAL":
            raise ValueError(f"line {line_no}: expected 10 whitespace-separated VAL fields")
        _, step_s, rk_s, stage, i_s, k_s, j_s, field, dtype, raw_hex = parts
        try:
            step, rk_step, i, k, j = map(int, (step_s, rk_s, i_s, k_s, j_s))
        except ValueError as exc:
            raise ValueError(f"line {line_no}: timestep, RK step and coordinates must be integers") from exc
        if step != 3 or rk_step not in (0, 1, 2, 3):
            raise ValueError(f"line {line_no}: unexpected step/RK step {step}/{rk_step}")
        if (i, j, k) not in allowed_coords:
            raise ValueError(f"line {line_no}: unexpected coordinate {(i, j, k)}")
        if stage not in STAGE_FIELDS or field not in STAGE_FIELDS[stage]:
            raise ValueError(f"line {line_no}: unexpected stage/field {stage}/{field}")
        if stage == "PRE_MICROPHYSICS":
            if rk_step != 0:
                raise ValueError(f"line {line_no}: PRE_MICROPHYSICS must use rk_step=0")
        elif rk_step == 0:
            raise ValueError(f"line {line_no}: RK stages require rk_step 1..3")
        if field == "TENDEC":
            if dtype != "bool" or not _HEX_BOOL.fullmatch(raw_hex):
                raise ValueError(f"line {line_no}: TENDEC must be bool 00 or 01")
            bits: int | bool = raw_hex == "01"
        else:
            if dtype != "f32" or not _HEX32.fullmatch(raw_hex):
                raise ValueError(f"line {line_no}: {field} must be 8-hex-digit f32")
            bits = int(raw_hex, 16)
            value = np.asarray([bits], dtype=np.uint32).view(np.float32)[0]
            if not np.isfinite(value):
                raise ValueError(f"line {line_no}: {field} is nonfinite")
        row = UpstreamValue(step, rk_step, stage, i, k, j, field, dtype, bits)
        row_key = _key(row)
        if row_key in values:
            raise ValueError(f"line {line_no}: duplicate stage coordinate/field {row_key}")
        values[row_key] = row
        order.append(row_key)

    if not values:
        raise ValueError("upstream trace contains no VAL rows")
    return UpstreamNCTrace(
        values=values,
        row_order=tuple(order),
        sha256=hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw),
        path_name=source.name,
    )


def _f32_bits(value: np.float32) -> int:
    return int(np.asarray([value], dtype=np.float32).view(np.uint32)[0])


def _add(a: np.float32, b: np.float32) -> np.float32:
    return np.float32(np.float32(a) + np.float32(b))


def _mul(a: np.float32, b: np.float32) -> np.float32:
    return np.float32(np.float32(a) * np.float32(b))


def _div(a: np.float32, b: np.float32) -> np.float32:
    return np.float32(np.float32(a) / np.float32(b))


def _fma32(a: np.float32, b: np.float32, c: np.float32) -> np.float32:
    """Use the repository's exact Fraction-based, single-rounded f32 FMA."""
    return np.float32(_fraction_fma32(float(a), float(b), float(c)))


def _bits_row(trace: UpstreamNCTrace, target: tuple[int, int, int], rk: int, stage: str, field: str) -> int | bool:
    return trace.at(target, rk, stage, field).bits


def _val(trace: UpstreamNCTrace, target: tuple[int, int, int], rk: int, stage: str, field: str) -> np.float32:
    return trace.at(target, rk, stage, field).f32


def _f32_summary(value: np.float32) -> dict[str, Any]:
    return {"value": float(value), "bits_hex": f"{_f32_bits(value):08X}"}


def _stage_snapshot(
    trace: UpstreamNCTrace, target: tuple[int, int, int], rk: int, stage: str
) -> dict[str, dict[str, Any]]:
    fields = STAGE_FIELDS[stage]
    result: dict[str, dict[str, Any]] = {}
    for field in fields:
        row = trace.at(target, rk, stage, field)
        result[field] = {"value": row.value, "dtype": row.dtype, "bits_hex": row.raw_hex}
    return result


def _generic_replay(trace: UpstreamNCTrace, target: tuple[int, int, int], rk: int, *, fused: bool = False) -> dict[str, Any]:
    before = "RKSCALAR_BEFORE"
    after = "RKSCALAR_AFTER"
    qnc = _val(trace, target, rk, before, "QNC")
    scalar_old = _val(trace, target, rk, before, "SCALAR_OLD")
    # rk_update_scalar copies scalar_2 into scalar_1 on the first RK stage.
    base = qnc if rk == 1 else scalar_old
    mu_old = _add(_val(trace, target, rk, before, "MU_OLD"), _val(trace, target, rk, before, "MU_BASE"))
    mu_new = _add(_val(trace, target, rk, before, "MU_NEW"), _val(trace, target, rk, before, "MU_BASE"))
    c1 = _val(trace, target, rk, before, "C1H")
    c2 = _val(trace, target, rk, before, "C2H")
    dt = _val(trace, target, rk, before, "DT_RK")
    advect = _val(trace, target, rk, before, "ADVECT_TEND")
    msfty = _val(trace, target, rk, before, "MSFTY")
    sc_tend = _val(trace, target, rk, before, "SCALAR_TEND")
    tendency = _fma32(advect, msfty, sc_tend) if fused else _add(_mul(advect, msfty), sc_tend)
    if fused:
        coeff_num = _fma32(c1, mu_old, c2)
        coeff_den = _fma32(c1, mu_new, c2)
        dt_term = _mul(dt, tendency)
        numerator = _fma32(coeff_num, base, dt_term)
    else:
        coeff_num = _add(_mul(c1, mu_old), c2)
        coeff_den = _add(_mul(c1, mu_new), c2)
        dt_term = _mul(dt, tendency)
        numerator = _add(_mul(coeff_num, base), dt_term)
    predicted = _div(numerator, coeff_den)
    observed = _val(trace, target, rk, after, "QNC")
    old_after = _val(trace, target, rk, after, "SCALAR_OLD")
    old_expected = qnc if rk == 1 else scalar_old
    return {
        "rk_step": rk,
        "mode": "fma_contraction_candidate" if fused else "separate_f32_ops",
        "qnc_base_operand": "QNC" if rk == 1 else "SCALAR_OLD",
        "operands_before": _stage_snapshot(trace, target, rk, before),
        "operands_after": _stage_snapshot(trace, target, rk, after),
        "tendency": _f32_summary(tendency),
        "old_mass_factor": _f32_summary(coeff_num),
        "new_mass_factor": _f32_summary(coeff_den),
        "dt_tendency": _f32_summary(dt_term),
        "numerator": _f32_summary(numerator),
        "predicted_qnc": _f32_summary(predicted),
        "observed_qnc": _f32_summary(observed),
        "qnc_bitwise_match": _f32_bits(predicted) == _f32_bits(observed),
        "scalar_old_expected_after": _f32_summary(old_expected),
        "scalar_old_observed_after": _f32_summary(old_after),
        "scalar_old_bitwise_match": _f32_bits(old_expected) == _f32_bits(old_after),
        "tenddec": bool(_bits_row(trace, target, rk, before, "TENDEC")),
    }


def _pd_replay(trace: UpstreamNCTrace, target: tuple[int, int, int]) -> dict[str, Any]:
    rk = 3
    before = "RKSCALAR_PD_BEFORE"
    after = "RKSCALAR_PD_AFTER"
    qnc_before = _val(trace, target, rk, before, "QNC")
    qnc_after = _val(trace, target, rk, after, "QNC")
    scalar_old = _val(trace, target, rk, before, "SCALAR_OLD")
    sc_tend = _val(trace, target, rk, before, "SCALAR_TEND")
    mu_old = _add(_val(trace, target, rk, before, "MU_OLD_ARG"), _val(trace, target, rk, before, "MU_BASE"))
    mu_new = _add(_val(trace, target, rk, before, "MU_NEW_ARG"), _val(trace, target, rk, before, "MU_BASE"))
    c1 = _val(trace, target, rk, before, "C1H")
    c2 = _val(trace, target, rk, before, "C2H")
    dt = _val(trace, target, rk, before, "DT_RK")
    coeff_num = _add(_mul(c1, mu_old), c2)
    coeff_den = _add(_mul(c1, mu_new), c2)
    tendency = _add(np.float32(0.0), sc_tend)
    predicted = _div(_add(_mul(coeff_num, scalar_old), _mul(dt, tendency)), coeff_den)
    observed = _val(trace, target, rk, after, "SCALAR_OLD")
    tend_after = _val(trace, target, rk, after, "SCALAR_TEND")
    return {
        "rk_step": rk,
        "operands_before": _stage_snapshot(trace, target, rk, before),
        "operands_after": _stage_snapshot(trace, target, rk, after),
        "predicted_scalar_old": _f32_summary(predicted),
        "observed_scalar_old": _f32_summary(observed),
        "scalar_old_bitwise_match": _f32_bits(predicted) == _f32_bits(observed),
        "qnc_unchanged_bitwise": _f32_bits(qnc_before) == _f32_bits(qnc_after),
        "scalar_tend_after": _f32_summary(tend_after),
        "scalar_tend_zeroed": _f32_bits(tend_after) == 0,
    }


def _validate_inventory(trace: UpstreamNCTrace) -> None:
    for target_name, target in TARGETS.items():
        expected: set[Key] = set()
        for rk in (1, 2, 3):
            for stage in ("RKSCALAR_BEFORE", "RKSCALAR_AFTER"):
                expected.update((3, rk, stage, target[0], target[2], target[1], f) for f in GENERIC_FIELDS)
        for stage in ("RKSCALAR_PD_BEFORE", "RKSCALAR_PD_AFTER"):
            expected.update((3, 3, stage, target[0], target[2], target[1], f) for f in PD_FIELDS)
        expected.add((3, 0, "PRE_MICROPHYSICS", target[0], target[2], target[1], "QNC"))
        actual = {key for key in trace.values if key[3:6] == (target[0], target[2], target[1])}
        missing, extra = expected - actual, actual - expected
        if missing or extra:
            raise ValueError(f"{target_name}: incomplete or unexpected trace keys; missing={len(missing)} extra={len(extra)}")
        for rk in (1, 2, 3):
            if _bits_row(trace, target, rk, "RKSCALAR_BEFORE", "TENDEC"):
                raise ValueError(f"{target_name}: expected tendec=false for native scalar stage {rk}")
            for field in GENERIC_FIELDS:
                if field in ("QNC", "SCALAR_OLD"):
                    continue
                before = _bits_row(trace, target, rk, "RKSCALAR_BEFORE", field)
                after = _bits_row(trace, target, rk, "RKSCALAR_AFTER", field)
                if before != after:
                    raise ValueError(f"{target_name}: rk_update_scalar unexpectedly changed read-only {field} at RK {rk}")
            old_before = _bits_row(trace, target, rk, "RKSCALAR_BEFORE", "SCALAR_OLD")
            old_expected = _bits_row(trace, target, rk, "RKSCALAR_BEFORE", "QNC") if rk == 1 else old_before
            if _bits_row(trace, target, rk, "RKSCALAR_AFTER", "SCALAR_OLD") != old_expected:
                raise ValueError(f"{target_name}: unexpected scalar_1 writeback at generic RK {rk}")

        for field in PD_FIELDS:
            before = _bits_row(trace, target, 3, "RKSCALAR_PD_BEFORE", field)
            after = _bits_row(trace, target, 3, "RKSCALAR_PD_AFTER", field)
            if field == "SCALAR_OLD":
                continue
            if field == "SCALAR_TEND":
                if after != 0:
                    raise ValueError(f"{target_name}: final positive-def update did not clear scalar_tend")
            elif before != after:
                raise ValueError(f"{target_name}: positive-def update unexpectedly changed read-only {field}")

        # Confirm event order from the filtered file stream, including the
        # positive-def tendency update before the final ordinary RK update.
        stages = [(key[1], key[2]) for key in trace.row_order if key[3:6] == (target[0], target[2], target[1])]
        expected_order: list[tuple[int, str]] = []
        for rk in (1, 2):
            expected_order.extend(((rk, "RKSCALAR_BEFORE"), (rk, "RKSCALAR_AFTER")))
        expected_order.extend(((3, "RKSCALAR_PD_BEFORE"), (3, "RKSCALAR_PD_AFTER"), (3, "RKSCALAR_BEFORE"), (3, "RKSCALAR_AFTER"), (0, "PRE_MICROPHYSICS")))
        # Producer writes complete stage snapshots in source execution order.
        grouped: list[tuple[int, str]] = []
        for item in stages:
            if not grouped or grouped[-1] != item:
                grouped.append(item)
        if grouped != expected_order:
            raise ValueError(f"{target_name}: unexpected event order {grouped}")


def _compare_premicro_to_kdm(trace: UpstreamNCTrace, target: tuple[int, int, int], kdm: MomentTraceInventory | None) -> dict[str, Any] | None:
    if kdm is None:
        return None
    i, j, k = target
    owner_ids = [call for call, header in kdm.headers.items() if header.step == 3 and header.owns(i, j)]
    if len(owner_ids) != 1:
        raise ValueError(f"expected one KDM step-3 call owning {(i, j)}, found {owner_ids}")
    key = (owner_ids[0], "MP_INPUT", i, k, j, "NC")
    if key not in kdm.values:
        raise ValueError(f"KDM trace missing MP_INPUT NC at {key}")
    if kdm.values[key].dtype != "f32" or kdm.values[key].owner != "host":
        raise ValueError(f"KDM MP_INPUT NC must be a host-side f32 record at {key}")
    upstream = _bits_row(trace, target, 0, "PRE_MICROPHYSICS", "QNC")
    kdm_bits = kdm.values[key].bits
    return {
        "kdm_call_id": owner_ids[0],
        "upstream_pre_microphysics_bits_hex": f"{int(upstream):08X}",
        "kdm_mp_input_bits_hex": f"{int(kdm_bits):08X}",
        "bitwise_match": int(upstream) == int(kdm_bits),
    }


def analyze_upstream_nc_trace(
    trace: UpstreamNCTrace,
    *,
    run_id: str,
    kdm_trace: MomentTraceInventory | None = None,
    kdm_run_id: str | None = None,
) -> dict[str, Any]:
    """Validate complete two-target coverage, replay f32 stages, and compare KDM input."""
    if not run_id:
        raise ValueError("run_id must be nonempty")
    if kdm_trace is not None and kdm_run_id != run_id:
        raise ValueError("kdm_run_id must explicitly match run_id before boundary comparison")
    _validate_inventory(trace)
    reports: dict[str, Any] = {}
    for name, target in TARGETS.items():
        generic = []
        for rk in (1, 2, 3):
            generic.append({
                "source_order": _generic_replay(trace, target, rk),
                "fused_candidate": _generic_replay(trace, target, rk, fused=True),
            })
        reports[name] = {
            "global_i_j_k": list(target),
            "pd_step3": _pd_replay(trace, target),
            "generic_rk_steps": generic,
            "pre_microphysics_qnc": _f32_summary(_val(trace, target, 0, "PRE_MICROPHYSICS", "QNC")),
            "pre_microphysics_matches_kdm_mp_input": _compare_premicro_to_kdm(trace, target, kdm_trace),
        }
    return {
        "schema": "kdm6ad.upstream_nc_trace_analysis.v1",
        "run_id": run_id,
        "trace": {"file": trace.path_name, "sha256": trace.sha256, "bytes": trace.byte_count},
        "targets": reports,
        "scope": {
            "purpose": "audit the native qnc scalar update through the pre-KDM wrapper boundary",
            "units": "not certified by this trace",
            "mechanistic_attribution": "not inferred from operand replay",
            "f32_replay": "source-order candidate is compared bitwise; no exactness claim unless the observed bits match",
            "higher_derivatives_or_cost": "not evaluated",
        },
    }


def compare_upstream_nc_runs(control: UpstreamNCTrace, candidate: UpstreamNCTrace) -> dict[str, Any]:
    """Report first per-target recorded divergence while retaining the full key scope."""
    _validate_inventory(control)
    _validate_inventory(candidate)
    results: dict[str, Any] = {}
    for name, target in TARGETS.items():
        keys = [
            key for key in control.row_order
            if key[3:6] == (target[0], target[2], target[1])
        ]
        differing = []
        for key in keys:
            a, b = control.values[key], candidate.values.get(key)
            if b is None:
                raise ValueError(f"candidate missing control key {key}")
            if a.dtype != b.dtype:
                raise ValueError(f"run dtype mismatch at {key}: {a.dtype}/{b.dtype}")
            if a.bits != b.bits:
                differing.append({
                    "step": key[0], "rk_step": key[1], "stage": key[2], "field": key[6],
                    "control_bits_hex": a.raw_hex, "candidate_bits_hex": b.raw_hex,
                })
        if len(control.values) != len(candidate.values):
            raise ValueError("control and candidate traces have different key counts")
        results[name] = {
            "first_divergence": differing[0] if differing else None,
            "differing_records": len(differing),
            "compared_records": len(keys),
            "differences": differing,
        }
    return {
        "schema": "kdm6ad.upstream_nc_trace_run_comparison.v1",
        "control_sha256": control.sha256,
        "candidate_sha256": candidate.sha256,
        "targets": results,
        "scope": "bitwise stage comparison only; no causal or physical attribution",
    }
