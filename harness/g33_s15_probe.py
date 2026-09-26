#!/usr/bin/env python3
"""Pinned, fail-closed tooling for the bounded S15 host diagnostic.

The native instrumentation is prepared in a disposable source copy. This
module replays the raw stdout event protocol without using rounded decimal
values: every REAL input is represented by its original f32 word.
"""

from __future__ import annotations

import argparse
import csv
from fractions import Fraction
import hashlib
import json
import math
import re
import shutil
import struct
import sys
from pathlib import Path
from typing import Iterable


PROTOCOL = "KDM6AD-S15-RAW32-v1"
REFERENCE_SCHEMA = "KDM6AD-S15-INDEPENDENT-PLAN-v1"
REFERENCE_FIELDS = (
    "capture_window", "qib_owner_site", "qib_owner_name", "qib_summary_keys",
    "qib_transition_count", "qib_first_event_keys",
    "melt_first_event_count", "melt_first_event_keys", "first_qib_key", "first_melt_key",
)
CAPTURE_WINDOW = {
    "first_timestep": 1,
    "last_timestep": 1,
    "selection": "first model timestep only",
}
QIB_OWNER_SITE = 5
QIB_OWNER_NAME = "scalar_tile_loop_2"  # scalar_old/scalar fields, the actual QIB owner.
QIB_EXPECTED_RK_STAGES = (1, 2, 3)
QIB_EXPECTED_TILE_BOUNDS = ((1, 235, 1, 142), (1, 235, 143, 283))


def expected_qib_summary_keys() -> list[list[int]]:
    """Pinned step-1 owner/tile/RK census for the retained LC05 1-rank layout."""
    return [[1, rk, QIB_OWNER_SITE, *tile]
            for rk in QIB_EXPECTED_RK_STAGES for tile in QIB_EXPECTED_TILE_BOUNDS]
SOURCE_PINS = {
    "dyn_em/module_em.F": "7695bfb05a7f99763334a6e69523bbcc1de0f2c659177a18c10a6e1cf530a0c7",
    "dyn_em/solve_em.F": "d66e9db1bba8f37e3f46d30c2fd74bdf8def411adf233376a69e0b401c6d3d1f",
    "phys/module_mp_kdm6.F": "fc0a72d33a5e61803fea56eb9118018039c6da8b5775813032b4861a2bd66eb5",
}
SHADOW_TAG = "! KDM6AD-S15-PROBE"
S10_MACRO = "KDM6_PROGB_VALIDITY_CAPTURE"

QIB_COLUMNS = (
    "kind", "step", "rk", "owner", "tile_i0", "tile_i1", "tile_j0", "tile_j1",
    "i", "j", "k", "before", "after", "reference", "advect", "msfty",
    "other_tend", "dt", "c1", "c2", "muold", "munew",
)
MELT_COLUMNS = (
    "kind", "step", "lat", "substep", "progb_site", "i", "k", "qg0", "brs0",
    "qcrmin", "brs_min", "qg_gate", "brs_gate", "rhox_valid", "rhox", "t0", "t1", "cpm",
    "xlf", "pgmlt", "qr0", "qr1", "qg1", "brs1", "den", "dz",
)


class ProbeError(ValueError):
    pass


def f32(word: str) -> float:
    """Decode exactly one unsigned 32-bit raw IEEE word."""
    if len(word) != 8 or any(c not in "0123456789abcdefABCDEF" for c in word):
        raise ProbeError(f"invalid f32 word: {word!r}")
    return struct.unpack(">f", bytes.fromhex(word))[0]


def f32_word(value: float) -> str:
    try:
        return struct.pack(">f", value).hex().upper()
    except OverflowError:
        return "FF800000" if value < 0.0 else "7F800000"


def mul32(a: float, b: float) -> float:
    return f32(f32_word(a * b))


def add32(a: float, b: float) -> float:
    return f32(f32_word(a + b))


def div32(a: float, b: float) -> float:
    return f32(f32_word(a / b))


def _round_ratio_to_even(numerator: int, denominator: int) -> int:
    quotient, remainder = divmod(numerator, denominator)
    twice = remainder * 2
    if twice > denominator or (twice == denominator and quotient & 1):
        quotient += 1
    return quotient


def _fraction_to_f32_word(value: Fraction) -> str:
    """Round an exact rational to binary32, nearest-even, without double rounding."""
    sign = 0x80000000 if value < 0 else 0
    numerator = abs(value.numerator)
    denominator = value.denominator
    if numerator == 0:
        return f"{sign:08X}"
    exponent = numerator.bit_length() - denominator.bit_length()
    if exponent >= 0:
        if numerator < (denominator << exponent):
            exponent -= 1
    elif (numerator << -exponent) < denominator:
        exponent -= 1
    if exponent < -126:
        significand = _round_ratio_to_even(numerator << 149, denominator)
        if significand == 0:
            return f"{sign:08X}"
        if significand >= (1 << 23):
            return f"{sign | (1 << 23):08X}"
        return f"{sign | significand:08X}"
    shift = 23 - exponent
    if shift >= 0:
        significand = _round_ratio_to_even(numerator << shift, denominator)
    else:
        significand = _round_ratio_to_even(numerator, denominator << -shift)
    if significand >= (1 << 24):
        significand >>= 1
        exponent += 1
    if exponent > 127:
        return f"{sign | 0x7F800000:08X}"
    bits = sign | ((exponent + 127) << 23) | (significand - (1 << 23))
    return f"{bits:08X}"


def fma32(a: float, b: float, c: float) -> float:
    """One correctly rounded binary32 fused multiply-add."""
    exact = Fraction(*a.as_integer_ratio()) * Fraction(*b.as_integer_ratio())
    exact += Fraction(*c.as_integer_ratio())
    return f32(_fraction_to_f32_word(exact))


def replay_rk_scalar_f32(operands: dict[str, str], line: int = 0) -> dict[str, object]:
    """Replay generic rk_update_scalar arithmetic from raw f32 operands.

    This arithmetic helper deliberately has no species or owner label. The A
    discovery mismatch is a generic scalar call and cannot establish a QIB
    witness without the B owner field.
    """
    names = ("reference", "advect", "msfty", "other_tend", "dt", "c1", "c2", "muold", "munew")
    vals = {name: f32(operands[name]) for name in names}
    if any(not math.isfinite(value) for value in vals.values()):
        raise ProbeError(f"line {line}: non-finite QIB input operand")
    advective_term = mul32(vals["advect"], vals["msfty"])
    tendency = add32(advective_term, vals["other_tend"])
    old_mass = fma32(vals["c1"], vals["muold"], vals["c2"])
    new_mass = fma32(vals["c1"], vals["munew"], vals["c2"])
    old_scaled = mul32(old_mass, vals["reference"])
    tendency_scaled = mul32(vals["dt"], tendency)
    if not all(math.isfinite(value) for value in
               (advective_term, tendency, old_mass, new_mass, old_scaled, tendency_scaled)):
        raise ProbeError(f"line {line}: non-finite QIB tendency or mass intermediate")
    if new_mass <= 0.0:
        raise ProbeError(f"line {line}: invalid RK air-mass denominator")
    numerator = fma32(old_mass, vals["reference"], tendency_scaled)
    if not math.isfinite(numerator):
        raise ProbeError(f"line {line}: non-finite QIB numerator")
    result = div32(numerator, new_mass)
    if not math.isfinite(result):
        raise ProbeError(f"line {line}: non-finite replayed QIB output")
    return {"replayed_after_bits": f32_word(result),
            "old_mass_bits": f32_word(old_mass),
            "new_mass_bits": f32_word(new_mass),
            "tendency_bits": f32_word(tendency),
            "numerator_bits": f32_word(numerator)}


def _row_values(row: dict[str, str], required: Iterable[str], line: int) -> None:
    missing = [k for k in required if k not in row]
    if missing:
        raise ProbeError(f"line {line}: missing columns {missing}")
    if any(row[k] == "" for k in required):
        raise ProbeError(f"line {line}: empty required field")


def replay_qib(row: dict[str, str], line: int = 0) -> dict[str, object]:
    _row_values(row, QIB_COLUMNS, line)
    if row["kind"] != "QIB":
        raise ProbeError(f"line {line}: expected QIB row")
    if int(row["owner"]) != QIB_OWNER_SITE:
        raise ProbeError(f"line {line}: QIB row came from non-QIB scalar owner {row['owner']}")
    vals = {k: f32(row[k]) for k in QIB_COLUMNS[11:]}
    before, observed_after = vals["before"], vals["after"]
    if row["before"].upper() != row["reference"].upper():
        raise ProbeError(f"line {line}: before word is not the formula's reference input")
    if not math.isfinite(observed_after):
        raise ProbeError(f"line {line}: non-finite output is not a QIB sign transition")
    arithmetic = replay_rk_scalar_f32(row, line)
    if arithmetic["replayed_after_bits"] != f32_word(observed_after):
        raise ProbeError(
            f"line {line}: QIB replay gives {arithmetic['replayed_after_bits']}, "
            f"capture has {f32_word(observed_after)}"
        )
    if not (before >= 0.0 and observed_after < 0.0):
        raise ProbeError(f"line {line}: row is not a nonnegative-to-negative transition")
    return {
        "key": tuple(int(row[k]) for k in ("step", "rk", "owner", "i", "j", "k")),
        "before_bits": row["before"].upper(),
        "after_bits": row["after"].upper(),
        "advective_tendency": mul32(vals["advect"], vals["msfty"]),
        "other_tendency": vals["other_tend"],
        **arithmetic,
        "arithmetic_model": "binary32_fmadd_mass_and_numerator",
    }


def replay_melt(row: dict[str, str], line: int = 0) -> dict[str, object]:
    required = list(MELT_COLUMNS)
    # An invalid rhox is represented by an empty field, never by a read value.
    if "rhox" not in row:
        raise ProbeError(f"line {line}: missing rhox field")
    _row_values({k: ("0" if k == "rhox" and row.get("rhox_valid") == "0" else v)
                 for k, v in row.items()}, required, line)
    if row["kind"] != "MELT":
        raise ProbeError(f"line {line}: expected MELT row")
    if int(row["progb_site"]) not in range(1, 8):
        raise ProbeError(f"line {line}: invalid ProgB owner site")
    valid = row["rhox_valid"]
    if valid not in {"0", "1"}:
        raise ProbeError(f"line {line}: rhox_valid must be 0 or 1")
    if valid == "0" and row["rhox"] != "":
        raise ProbeError(f"line {line}: undefined rhox must not be read or serialized")
    if valid == "1" and row["rhox"] == "":
        raise ProbeError(f"line {line}: valid rhox is missing")
    floats = ("qg0", "brs0", "qcrmin", "brs_min", "qg_gate", "brs_gate",
              "t0", "t1", "cpm", "xlf", "pgmlt", "qr0", "qr1", "qg1",
              "brs1", "den", "dz")
    v = {k: f32(row[k]) for k in floats}
    finite_required = ("qg0", "brs0", "qcrmin", "brs_min", "qg_gate", "brs_gate", "t0", "t1",
                       "cpm", "xlf", "pgmlt", "qr0", "qr1", "qg1", "den", "dz")
    if not all(math.isfinite(v[k]) for k in finite_required):
        raise ProbeError(f"line {line}: non-finite required melt operand")
    if not (v["qcrmin"] > 0.0 and v["brs_min"] > 0.0 and v["den"] > 0.0 and
            v["dz"] > 0.0 and v["cpm"] > 0.0 and v["xlf"] > 0.0):
        raise ProbeError(f"line {line}: invalid threshold or positive physical measure")
    expected_valid = v["qg_gate"] > v["qcrmin"] or v["brs_gate"] > v["brs_min"]
    if (valid == "1") != expected_valid:
        raise ProbeError(f"line {line}: rhox validity does not match the captured ProgB gate")
    if not math.isfinite(v["qg1"]) or v["qg1"] < 0.0 or v["qr0"] < 0.0 or v["qr1"] < 0.0:
        raise ProbeError(f"line {line}: invalid post-melt mass state")
    if not (v["pgmlt"] >= -v["qg0"]):
        raise ProbeError(f"line {line}: applied melt exceeds available graupel mass")
    if not (v["qg0"] > 0.0 and v["pgmlt"] < 0.0):
        raise ProbeError(f"line {line}: not a positive-graupel melt event")
    if not (v["qg0"] <= v["qcrmin"] and v["brs0"] <= v["brs_min"]):
        raise ProbeError(f"line {line}: event is outside configured trace-qg cutoff")
    if f32_word(add32(v["qg0"], v["pgmlt"])) != f32_word(v["qg1"]):
        raise ProbeError(f"line {line}: qg update does not replay")
    if f32_word(add32(v["qr0"], -v["pgmlt"])) != f32_word(v["qr1"]):
        raise ProbeError(f"line {line}: qr update does not replay")
    expected_t1 = add32(v["t0"], mul32(div32(v["xlf"], v["cpm"]), v["pgmlt"]))
    if f32_word(expected_t1) != f32_word(v["t1"]):
        raise ProbeError(f"line {line}: temperature update does not replay")
    # Preserve the exact operands and report integrated terms in float64. The
    # density basis is conditional and remains visible in the result.
    dqg = float(v["qg1"]) - float(v["qg0"])
    dqr = float(v["qr1"]) - float(v["qr0"])
    layer_mass = float(v["den"]) * float(v["dz"])
    applied_melt_mass = layer_mass * (-float(v["pgmlt"]))
    latent_work_signed = float(v["xlf"]) * layer_mass * float(v["pgmlt"])
    thermal_work = layer_mass * float(v["cpm"]) * (float(v["t1"]) - float(v["t0"]))
    eta = f32("00000001")
    if v["qg0"] < 100.0 * eta:
        representability = "no_admissible_positive_volume"
    elif v["qg0"] < 900.0 * eta:
        representability = "sparse_admissible_volume_set"
    else:
        representability = "multiple_admissible_volumes_possible"
    if not math.isfinite(v["brs0"]) or v["brs0"] <= 0.0:
        apparent_rho = None
        pair_class = "invalid_nonpositive_volume"
    else:
        apparent_rho = float(v["qg0"]) / float(v["brs0"])
        pair_class = "active" if 100.0 <= apparent_rho <= 900.0 else "trace"
    if valid == "1":
        rhox = f32(row["rhox"])
        if not math.isfinite(rhox) or not (100.0 <= rhox <= 900.0):
            raise ProbeError(f"line {line}: defined rhox is outside the ProgB density range")
        if not math.isfinite(v["brs1"]):
            raise ProbeError(f"line {line}: non-finite post-volume with defined rhox")
        # Source: brs = brs + pgmlt/rhox. The Fortran path rounds the
        # division and addition separately; undefined-rhox rows stay untrusted.
        expected_brs1 = add32(v["brs0"], div32(v["pgmlt"], rhox))
        if f32_word(expected_brs1) != f32_word(v["brs1"]):
            raise ProbeError(f"line {line}: brs update does not replay")
    else:
        rhox = None
        expected_brs1 = None
    if valid == "0":
        post_pair_class = "untrusted_rhox_undefined"
        post_density = None
    elif not math.isfinite(v["brs1"]):
        post_pair_class = "invalid_nonfinite_volume"
        post_density = None
    elif v["brs1"] < 0.0:
        post_pair_class = "invalid_negative_volume"
        post_density = None
    elif v["qg1"] == 0.0 and v["brs1"] == 0.0:
        post_pair_class = "empty"
        post_density = None
    elif v["qg1"] > 0.0 and v["brs1"] == 0.0:
        post_pair_class = "invalid_missing_volume"
        post_density = None
    elif v["qg1"] == 0.0 and v["brs1"] > 0.0:
        post_pair_class = "invalid_volume_without_mass"
        post_density = None
    else:
        post_density = float(v["qg1"]) / float(v["brs1"])
        post_pair_class = "active" if 100.0 <= post_density <= 900.0 else "trace"
    return {
        "key": tuple(int(row[k]) for k in
                     ("step", "lat", "substep", "progb_site", "i", "k")),
        "rhox_valid": valid == "1",
        "rhox_used": rhox,
        "brs1_update_bits": f32_word(expected_brs1) if expected_brs1 is not None else None,
        "brs1_replay_scope": "source_order_f32_update" if expected_brs1 is not None else "untrusted_rhox_undefined",
        "apparent_density_raw": apparent_rho,
        "pair_class": pair_class,
        "post_pair_class": post_pair_class,
        "apparent_density_post": post_density,
        "f32_admissibility_class": representability,
        "qg_delta_mixing_ratio": dqg,
        "qr_delta_mixing_ratio": dqr,
        "layer_mass_measure_kg_m2_per_mixing_ratio": layer_mass,
        "applied_melt_mass_kg_m2_conditional": applied_melt_mass,
        "latent_cooling_j_m2_conditional": latent_work_signed if valid == "1" else None,
        "latent_cooling_candidate_j_m2_conditional": latent_work_signed,
        "latent_energy_magnitude_j_m2_conditional": -latent_work_signed if valid == "1" else None,
        "thermal_work_j_m2_conditional": thermal_work if valid == "1" else None,
        "thermal_work_candidate_j_m2_conditional": thermal_work,
        "thermal_minus_latent_j_m2_conditional": (thermal_work - latent_work_signed) if valid == "1" else None,
        "thermal_minus_latent_candidate_j_m2_conditional": thermal_work - latent_work_signed,
        "thermal_latent_exact_match": (thermal_work == latent_work_signed) if valid == "1" else None,
        "thermo_ledger_status": "conditional_local_match_candidate" if valid == "1" else "untrusted_rhox_undefined",
        "post_volume_finite": math.isfinite(v["brs1"]) if valid == "1" else None,
    }


def parse_capture(path: Path) -> tuple[list[dict[str, str]], list[tuple[int, ...]] | None]:
    raw_lines = path.read_text(encoding="ascii").splitlines()
    event_lines = [line.split() for line in raw_lines
                   if line.split() and line.split()[0] in {"S15Q", "S15QC", "S15M"}]
    if event_lines and not raw_lines[0].startswith("kind,"):
        rows: list[dict[str, str]] = []
        summaries: list[tuple[int, ...]] = []
        for line_no, fields in enumerate(event_lines, start=1):
            tag, values = fields[0], fields[1:]
            try:
                ints = [int(value, 10) for value in values]
            except ValueError as exc:
                raise ProbeError(f"native line {line_no}: fields must be decimal integers") from exc
            if tag == "S15QC":
                if len(ints) != 8:
                    raise ProbeError(f"native line {line_no}: malformed S15QC width {len(ints)}")
                summaries.append(tuple(ints))
                continue
            if tag == "S15Q":
                if len(ints) != 21:
                    raise ProbeError(f"native line {line_no}: malformed S15Q width {len(ints)}")
                keys = QIB_COLUMNS
                values_by_key = ints[:10] + [f"{x & 0xffffffff:08X}" for x in ints[10:]]
                row = dict(zip(keys, ["QIB"] + [str(x) for x in values_by_key[:10]] + values_by_key[10:]))
                replay_qib(row, line_no)
                rows.append(row)
                continue
            if tag == "S15M":
                if len(ints) not in {24, 25}:
                    raise ProbeError(f"native line {line_no}: malformed S15M width {len(ints)}")
                base = ints[:13]
                rhox_valid = base[12]
                if rhox_valid not in {0, 1} or (rhox_valid and len(ints) != 25) or (not rhox_valid and len(ints) != 24):
                    raise ProbeError(f"native line {line_no}: rhox validity/width mismatch")
                metadata = [str(x) for x in base[:6]]
                initial = [f"{x & 0xffffffff:08X}" for x in base[6:12]]
                row_values = metadata + initial + [str(rhox_valid)]
                rest_start = 13
                if rhox_valid:
                    row_values.append(f"{ints[13] & 0xffffffff:08X}")
                    rest_start = 14
                else:
                    row_values.append("")
                row_values += [f"{x & 0xffffffff:08X}" for x in ints[rest_start:]]
                row = dict(zip(MELT_COLUMNS, ["MELT"] + row_values))
                replay_melt(row, line_no)
                rows.append(row)
        return rows, summaries

    with path.open(newline="", encoding="ascii") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ProbeError("capture has no CSV header")
        rows = []
        for line, row in enumerate(reader, start=2):
            kind = row.get("kind")
            if kind == "QIB":
                replay_qib(row, line)
            elif kind == "MELT":
                replay_melt(row, line)
            else:
                raise ProbeError(f"line {line}: unknown row kind {kind!r}")
            rows.append(row)
        return rows, None


def verify_plan(rows: list[dict[str, str]], plan_path: Path,
                summaries: list[tuple[int, ...]] | None = None,
                expected_plan_sha256: str | None = None,
                capture_path: Path | None = None) -> dict[str, int]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan.get("protocol") != PROTOCOL or plan.get("status") != "independent_expected_plan":
        raise ProbeError("plan is not a pinned independent S15 plan")
    if not expected_plan_sha256 or len(expected_plan_sha256) != 64:
        raise ProbeError("an out-of-band SHA-256 pin is required for the independent plan")
    if sha256(plan_path) != expected_plan_sha256.lower():
        raise ProbeError("independent plan SHA-256 differs from the external pin")
    ref_meta = plan.get("independent_reference")
    if not isinstance(ref_meta, dict):
        raise ProbeError("plan lacks an independent reference artifact")
    reference_rel = Path(str(ref_meta.get("path", "")))
    if not reference_rel.name or reference_rel.is_absolute() or ".." in reference_rel.parts:
        raise ProbeError("independent reference path must be a safe relative path")
    reference_path = (plan_path.parent / reference_rel).resolve()
    plan_resolved = plan_path.resolve()
    capture_resolved = capture_path.resolve() if capture_path is not None else None
    if reference_path == plan_resolved or reference_path == capture_resolved:
        raise ProbeError("independent reference must be separate from plan and capture")
    try:
        reference_path.relative_to(plan_path.parent.resolve())
    except ValueError as exc:
        raise ProbeError("independent reference must remain within the plan directory") from exc
    if not reference_path.is_file() or sha256(reference_path) != ref_meta.get("sha256"):
        raise ProbeError("independent reference artifact is missing or has a digest mismatch")
    method = str(ref_meta.get("method", "")).strip()
    if not method or "s15 capture stream" in method.casefold():
        raise ProbeError("reference method is missing or derives expectations from the S15 stream")
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    if reference.get("schema") != REFERENCE_SCHEMA:
        raise ProbeError("independent reference schema mismatch")
    for field in REFERENCE_FIELDS:
        if plan.get(field) != reference.get(field):
            raise ProbeError(f"plan field {field} differs from the pinned independent reference")
    if capture_path is None or plan.get("capture_sha256") != sha256(capture_path):
        raise ProbeError("plan is not bound to this captured event stream")
    if plan.get("capture_window") != CAPTURE_WINDOW:
        raise ProbeError("independent plan does not pin the timestep-1 capture window")
    if not summaries:
        raise ProbeError("native plan verification requires the complete S15QC summary census")
    qrows = [r for r in rows if r["kind"] == "QIB"]
    mrows = [r for r in rows if r["kind"] == "MELT"]
    if any(int(row[0]) != CAPTURE_WINDOW["first_timestep"] for row in summaries):
        raise ProbeError("S15QC contains rows outside the pinned timestep-1 window")
    if any(row[7] < 0 for row in summaries):
        raise ProbeError("S15QC transition counts cannot be negative")
    if any(int(row["step"]) != CAPTURE_WINDOW["first_timestep"] for row in qrows + mrows):
        raise ProbeError("S15 event contains a row outside the pinned timestep-1 window")
    transition_count = sum(row[7] for row in summaries)
    summary_keys = [list(row[:7]) for row in summaries]
    if len(set(map(tuple, summary_keys))) != len(summary_keys):
        raise ProbeError("duplicate QIB owner/tile/stage summaries")
    expected_summary_keys = plan.get("qib_summary_keys")
    if expected_summary_keys != summary_keys:
        raise ProbeError("QIB owner/tile/stage summary key set differs from independent plan")
    if plan.get("qib_owner_site") != QIB_OWNER_SITE:
        raise ProbeError("independent plan does not pin the QIB-producing source call owner")
    if plan.get("qib_owner_name") != QIB_OWNER_NAME:
        raise ProbeError("independent plan does not name the QIB-producing source call owner")
    owner_schedule = plan.get("owner_schedule")
    if not isinstance(owner_schedule, dict):
        raise ProbeError("independent plan lacks its source-declared QIB owner schedule")
    if (owner_schedule.get("owner_site") != QIB_OWNER_SITE or
            owner_schedule.get("owner_name") != QIB_OWNER_NAME):
        raise ProbeError("source-declared QIB owner schedule does not match the pinned owner")
    pinned_summary_keys = expected_qib_summary_keys()
    if expected_summary_keys != pinned_summary_keys:
        raise ProbeError("QIB summary census was shrunk or changed from the pinned source schedule")
    if owner_schedule.get("expected_summary_keys") != pinned_summary_keys:
        raise ProbeError("QIB summary census differs from the source-declared owner schedule")
    if owner_schedule.get("expected_summary_cardinality") != len(pinned_summary_keys):
        raise ProbeError("QIB summary cardinality differs from the source-declared owner schedule")
    expected_first_event_keys = plan.get("qib_first_event_keys")
    if not isinstance(expected_first_event_keys, list) or len(expected_first_event_keys) != len(summaries):
        raise ProbeError("independent plan lacks one first-event key slot per QIB summary")
    event_counts: dict[tuple[int, ...], int] = {}
    events_by_tile: dict[tuple[int, ...], dict[str, str]] = {}
    for row in qrows:
        key = tuple(int(row[k]) for k in
                    ("step", "rk", "owner", "tile_i0", "tile_i1", "tile_j0", "tile_j1"))
        i, j = int(row["i"]), int(row["j"])
        if not (int(row["tile_i0"]) <= i <= int(row["tile_i1"]) and
                int(row["tile_j0"]) <= j <= int(row["tile_j1"])):
            raise ProbeError("QIB first-event cell is outside its owned tile")
        event_counts[key] = event_counts.get(key, 0) + 1
        events_by_tile[key] = row
    if any(n != 1 for n in event_counts.values()):
        raise ProbeError("expected one first-event row per positive-count tile/stage")
    positive = {tuple(row[:7]) for row in summaries if row[7] > 0}
    if set(event_counts) != positive:
        raise ProbeError("first-event rows do not match positive-count summaries")
    for index, summary in enumerate(summaries):
        key = tuple(summary[:7])
        expected_key = expected_first_event_keys[index]
        if summary[7] > 0:
            if expected_key is None or list(replay_qib(events_by_tile[key])["key"]) != expected_key:
                raise ProbeError("per-tile first QIB event key differs from independent plan")
        elif expected_key is not None:
            raise ProbeError("zero-count QIB summary has an expected first-event key")
        melt_substep_keys = [tuple(int(row[k]) for k in ("step", "lat", "substep"))
                             for row in mrows]
        if len(set(melt_substep_keys)) != len(melt_substep_keys):
            raise ProbeError("duplicate trace-melt witness for timestep/latitude-row/substep")
    melt_keys = [tuple(int(row[k]) for k in
                       ("step", "lat", "substep", "progb_site", "i", "k"))
                 for row in mrows]
    expected_melt_keys_raw = plan.get("melt_first_event_keys")
    if not isinstance(expected_melt_keys_raw, list):
        raise ProbeError("independent plan lacks the complete first-melt key census")
    if any(not isinstance(key, list) or len(key) != 6 or
           any(not isinstance(part, int) for part in key)
           for key in expected_melt_keys_raw):
        raise ProbeError("independent first-melt key census is malformed")
    expected_melt_keys = [tuple(key) for key in expected_melt_keys_raw]
    if len(set(expected_melt_keys)) != len(expected_melt_keys):
        raise ProbeError("independent first-melt key census contains duplicates")
    if sorted(melt_keys) != sorted(expected_melt_keys):
        raise ProbeError("first-melt key census differs from independent plan")
    if plan.get("qib_transition_count") != transition_count:
        raise ProbeError("QIB transition count differs from independent plan")
    if plan.get("melt_first_event_count") != len(mrows):
        raise ProbeError("trace melt event count differs from independent plan")
    expected_first_q = plan.get("first_qib_key")
    expected_first_m = plan.get("first_melt_key")
    actual_q = list(replay_qib(qrows[0])["key"]) if qrows else None
    actual_m = list(replay_melt(mrows[0])["key"]) if mrows else None
    if actual_q != expected_first_q or actual_m != expected_first_m:
        raise ProbeError("first event key differs from independent plan")
    return {"qib_transitions": transition_count, "trace_melt_first_events": len(mrows)}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_pre_link_binding(binding: dict[str, object]) -> dict[str, int]:
    """Verify plan-bound S15 compile inputs against the r6 receipt and disk.

    This is a read-only freshness check. It does not link, launch, or authorize
    a B run; callers must repeat it immediately before any future link.
    """
    receipt_meta = binding.get("compile_receipt")
    if not isinstance(receipt_meta, dict):
        raise ProbeError("pre-link binding lacks its r6 compile receipt")
    receipt_path = Path(str(receipt_meta.get("path", "")))
    if not receipt_path.is_file() or sha256(receipt_path) != receipt_meta.get("sha256"):
        raise ProbeError("r6 compile receipt is missing or changed")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("schema") != "KDM6AD-S15-FOCUSED-COMPILE-RECEIPT-v2":
        raise ProbeError("pre-link binding does not reference the owner-scoped r6 receipt")
    if binding.get("owner_site") != receipt.get("qib_owner_site") or \
            binding.get("owner_name") != receipt.get("qib_owner_name"):
        raise ProbeError("pre-link binding owner differs from the r6 compile receipt")

    expected_groups = (
        ("generated_shadow_sources", receipt.get("generated_shadow_source_sha256", {})),
        ("preprocessed_fortran", {
            name: item.get("sha256")
            for name, item in receipt.get("files", {}).get("preprocessed_fortran", {}).items()
        }),
        ("objects", {
            name: item.get("sha256")
            for name, item in receipt.get("files", {}).get("objects", {}).items()
        }),
    )
    checked = 0
    for group_name, receipt_hashes in expected_groups:
        entries = binding.get(group_name)
        if not isinstance(entries, dict) or set(entries) != set(receipt_hashes):
            raise ProbeError(f"pre-link {group_name} set differs from the r6 receipt")
        for name, item in entries.items():
            if not isinstance(item, dict) or item.get("sha256") != receipt_hashes[name]:
                raise ProbeError(f"pre-link {group_name} digest for {name} differs from r6")
            path = Path(str(item.get("path", "")))
            if not path.is_file() or sha256(path) != item["sha256"]:
                raise ProbeError(f"pre-link {group_name} file is missing or changed: {name}")
            checked += 1

    archive = binding.get("baseline_archive")
    receipt_archive = receipt.get("baseline_link_inputs", {}).get("untouched_s8_archive", {})
    if not isinstance(archive, dict) or archive.get("sha256") != receipt_archive.get("sha256"):
        raise ProbeError("pre-link baseline archive differs from the r6 receipt")
    archive_path = Path(str(archive.get("path", "")))
    if (not archive_path.is_file() or sha256(archive_path) != archive["sha256"] or
            archive_path.stat().st_size != receipt_archive.get("bytes")):
        raise ProbeError("untouched S8 baseline archive is missing or changed")
    checked += 1
    return {"bound_inputs_verified": checked}


def verify_plan_pin(plan_path: Path, expected_sha256: str) -> str:
    """Require an out-of-band plan digest before any native gate accepts it."""
    if len(expected_sha256) != 64 or any(c not in "0123456789abcdefABCDEF" for c in expected_sha256):
        raise ProbeError("an external 64-digit SHA-256 pin is required for the run plan")
    actual = sha256(plan_path) if plan_path.is_file() else ""
    if actual.lower() != expected_sha256.lower():
        raise ProbeError("run plan SHA-256 differs from the external pin")
    return actual


STALE_A_EXECUTABLE_SHA256 = "a2e5af8d8f32561ee06f81f6b3a2cf5539cb15c869cf8630b4fdda813ea3c1a1"


def verify_postlink_binding(plan_path: Path, expected_plan_sha256: str,
                            link_receipt_path: Path,
                            expected_link_receipt_sha256: str) -> dict[str, int]:
    """Read-only launch gate for a B run plan or its original link plan."""
    plan_sha = verify_plan_pin(plan_path, expected_plan_sha256)
    if len(expected_link_receipt_sha256) != 64 or any(
            c not in "0123456789abcdefABCDEF" for c in expected_link_receipt_sha256):
        raise ProbeError("an external 64-digit SHA-256 pin is required for the link receipt")
    if not link_receipt_path.is_file() or sha256(link_receipt_path).lower() != expected_link_receipt_sha256.lower():
        raise ProbeError("link receipt is missing or differs from its external SHA-256 pin")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    link = json.loads(link_receipt_path.read_text(encoding="utf-8"))
    if plan.get("schema") == "KDM6AD-S15-NATIVE-B-PRE-RUN-PLAN-v1":
        link_meta = plan.get("link_receipt", {})
        planned_link_path = Path(str(link_meta.get("path", "")))
        if not planned_link_path.is_absolute():
            planned_link_path = plan_path.parent / planned_link_path
        if (planned_link_path.resolve() != link_receipt_path.resolve() or
                link_meta.get("sha256") != expected_link_receipt_sha256.lower()):
            raise ProbeError("link receipt differs from the immutable B pre-run plan")
        build_meta = plan.get("build_plan", {})
        build_path = Path(str(build_meta.get("path", "")))
        if not build_path.is_absolute():
            build_path = plan_path.parent / build_path
        build_sha = verify_plan_pin(build_path, str(build_meta.get("sha256", "")))
        build_plan = json.loads(build_path.read_text(encoding="utf-8"))
        contract = build_plan.get("post_link_guard_contract", {})
        binding = build_plan.get("pre_link_binding", {})
        expected_inputs = build_plan.get("owner_schedule", {}).get("input_hashes", {})
        launch_inputs = plan.get("input_files")
        if not isinstance(launch_inputs, dict) or set(launch_inputs) != set(expected_inputs):
            raise ProbeError("B pre-run plan lacks the complete retained LC05 input set")
        for name, expected_sha in expected_inputs.items():
            item = launch_inputs[name]
            input_path = Path(str(item.get("path", ""))) if isinstance(item, dict) else Path()
            if (not isinstance(item, dict) or item.get("sha256") != expected_sha or
                    not input_path.is_file() or sha256(input_path) != expected_sha):
                raise ProbeError(f"B pre-run plan input is missing or differs from the build plan: {name}")
        expected_executable = plan.get("executable", {})
    else:
        build_sha = plan_sha
        build_plan = plan
        contract = plan.get("post_link_guard_contract", {})
        binding = plan.get("pre_link_binding", {})
        expected_inputs = plan.get("owner_schedule", {}).get("input_hashes", {})
        launch_inputs = None
        expected_executable = None
    if link.get("schema") != contract.get("schema") or link.get("status") != contract.get("status"):
        raise ProbeError("link receipt does not satisfy the plan's owner-scoped B-link contract")
    if link.get("plan_sha256") != build_sha:
        raise ProbeError("link receipt is not bound to this externally pinned build plan")
    if link.get("compile_receipt_sha256") != binding.get("compile_receipt", {}).get("sha256"):
        raise ProbeError("link receipt is not bound to the build plan's r6 compile receipt")
    prelink = verify_pre_link_binding(binding)

    expected_objects = binding.get("objects", {})
    actual_objects = link.get("s15_overlay_objects")
    if not isinstance(actual_objects, dict) or set(actual_objects) != set(expected_objects):
        raise ProbeError("linked S15 object set differs from the exact r6 object set")
    for name, expected in expected_objects.items():
        actual = actual_objects[name]
        if (not isinstance(actual, dict) or actual.get("sha256") != expected.get("sha256") or
                actual.get("path") != expected.get("path")):
            raise ProbeError(f"linked S15 object digest differs from r6: {name}")

    archive = binding.get("baseline_archive", {})
    linked_archive = link.get("untouched_s8_archive", {})
    if (not isinstance(linked_archive, dict) or
            linked_archive.get("sha256") != archive.get("sha256") or
            linked_archive.get("path") != archive.get("path")):
        raise ProbeError("link receipt does not bind the pinned untouched S8 archive")
    if link.get("canonical_host_modified") is not False:
        raise ProbeError("link receipt does not certify the canonical host remained untouched")

    executable = link.get("executable", {})
    if not isinstance(executable, dict):
        raise ProbeError("link receipt lacks a fresh B executable record")
    exe_path = Path(str(executable.get("path", "")))
    exe_sha = executable.get("sha256")
    if exe_sha == STALE_A_EXECUTABLE_SHA256:
        raise ProbeError("refusing stale A executable; B must be linked from the r6 owner-scoped objects")
    if (not exe_path.is_file() or exe_path.is_symlink() or not isinstance(exe_sha, str) or
            sha256(exe_path) != exe_sha):
        raise ProbeError("B executable is missing, redirected, or changed since the link receipt")
    if expected_executable is not None:
        if (not isinstance(expected_executable, dict) or
                expected_executable.get("path") != str(exe_path) or
                expected_executable.get("sha256") != exe_sha):
            raise ProbeError("fresh B executable differs from the immutable pre-run plan")

    input_files = link.get("input_files")
    if not isinstance(input_files, dict) or set(input_files) != set(expected_inputs):
        raise ProbeError("link receipt lacks the complete retained LC05 input set")
    input_count = 0
    for name, expected_sha in expected_inputs.items():
        item = input_files[name]
        if not isinstance(item, dict) or item.get("sha256") != expected_sha:
            raise ProbeError(f"link receipt input hash differs from the plan: {name}")
        input_path = Path(str(item.get("path", "")))
        if not input_path.is_file() or sha256(input_path) != expected_sha:
            raise ProbeError(f"retained LC05 input is missing or changed: {name}")
        input_count += 1
    return {"r6_objects_verified": len(expected_objects),
            "launch_inputs_verified": input_count,
            "prelink_inputs_verified": prelink["bound_inputs_verified"]}


def check_shadow_digest(path: Path, expected_sha256: str, relpath: str) -> None:
    actual = sha256(path)
    if actual != expected_sha256:
        raise ProbeError(f"generated shadow digest mismatch for {relpath}: {actual}")


def _s15_guard(label: str, code: str, base: str | None = None) -> str:
    begin = f"{SHADOW_TAG} BEGIN:{label}\n"
    end = f"{SHADOW_TAG} END:{label}\n"
    block = begin + f"#ifdef {S10_MACRO}\n{code}"
    if base is not None:
        block += "#else\n" + base
        if not base.endswith("\n"):
            block += "\n"
    return block + "#endif\n" + end


def _s15_strip(text: str) -> str:
    while f"{SHADOW_TAG} BEGIN:" in text:
        start = text.index(f"{SHADOW_TAG} BEGIN:")
        line_end = text.index("\n", start) + 1
        label = text[start + len(f"{SHADOW_TAG} BEGIN:"):line_end].strip()
        marker = f"{SHADOW_TAG} END:{label}\n"
        end = text.find(marker, line_end)
        if end < 0:
            raise ProbeError(f"missing generated S15 end marker for {label}")
        block = text[line_end:end]
        if not block.startswith(f"#ifdef {S10_MACRO}\n") or not block.endswith("#endif\n"):
            raise ProbeError(f"malformed generated S15 block {label}")
        body = block[len(f"#ifdef {S10_MACRO}\n"):-len("#endif\n")]
        if "#else\n" in body:
            if body.count("#else\n") != 1:
                raise ProbeError(f"nested/duplicate #else in S15 block {label}")
            _, base = body.split("#else\n", 1)
        else:
            base = ""
        text = text[:start] + base + text[end + len(marker):]
    return text


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ProbeError(f"{label}: expected one source anchor, found {count}")
    return text.replace(old, new, 1)


def add_qib_index_import(text: str) -> str:
    """Import the Registry-generated P_QIB index only in the diagnostic build."""
    original = (
        "  USE module_state_description, only: param_first_scalar, p_qr, p_qv, p_qc, "
        "p_qg, p_qi, p_qs, tiedtkescheme,ntiedtkescheme, heldsuarez, &\n"
    )
    instrumented = original.replace("p_qi, p_qs,", "p_qi, p_qs, p_qib,", 1)
    return _replace_once(text, original,
                         _s15_guard("qib_index_import", instrumented, original),
                         "Registry QIB index import")


def instrument_module_em(text: str) -> str:
    text = add_qib_index_import(text)
    signature = "                             rk_step, dt, spec_zone,        &\n"
    sig_new = ("                             rk_step, s15_step, s15_owner, dt, spec_zone, &\n")
    if text.count(signature) != 2:
        raise ProbeError(f"rk_update_scalar signature: expected two routines, found {text.count(signature)}")
    text = text.replace(signature, _s15_guard("step_arg", sig_new, signature), 1)
    decl = "   INTEGER ,                INTENT(IN   ) :: scs, sce, rk_step, spec_zone\n"
    if text.count(decl) != 2:
        raise ProbeError(f"rk_update_scalar declarations: expected two routines, found {text.count(decl)}")
    text = text.replace(decl,
        decl + _s15_guard("rk_locals",
        "   INTEGER, INTENT(IN) :: s15_step\n"
        "   INTEGER, INTENT(IN) :: s15_owner\n"
        "   CHARACTER(LEN=8) :: s15_log_env\n"
        "   INTEGER :: s15_log_status, s15_count\n"
        "   LOGICAL :: s15_enabled, s15_first\n"
        "   REAL :: s15_before\n"), 1)
    anchor = "    IF ( rk_step == 1 ) THEN\n"
    init = _s15_guard("rk_stage_init",
        "    s15_enabled = .false.\n"
        "    s15_first = .false.\n"
        "    s15_count = 0\n"
        f"    if (scs.eq.P_QIB .and. sce.eq.P_QIB .and. s15_owner.eq.{QIB_OWNER_SITE}) then\n"
        "      s15_log_env = ''\n"
        "      call get_environment_variable('KDM6_S15_NATIVE_CAPTURE_LOG', &\n"
        "                                   s15_log_env, status=s15_log_status)\n"
        "      s15_enabled = s15_log_status.eq.0 .and. trim(s15_log_env).eq.'1' .and. s15_step.eq.1\n"
        "    endif\n")
    text = _replace_once(text, anchor, init + anchor, "rk stage initialization")
    formula = (
        "        scalar_2(i,k,j,im) = ((c1(k)*muold(i)+c2(k))*scalar_1(i,k,j,im)   &\n"
        "                             + dt*tendency(i,k,j))/(c1(k)*munew(i)+c2(k))\n")
    if text.count(formula) != 2:
        raise ProbeError(f"QIB update formula: expected 2 source arms, found {text.count(formula)}")
    before = _s15_guard("qib_capture_before",
        "        if (s15_enabled .and. im.eq.P_QIB) s15_before = scalar_1(i,k,j,im)\n")
    after = _s15_guard("qib_capture_after",
        "        if (s15_enabled .and. im.eq.P_QIB) then\n"
        "          if (s15_before.ge.0. .and. s15_before.le.huge(s15_before) .and. &\n"
        "              scalar_2(i,k,j,im).lt.0. .and. &\n"
        "              scalar_2(i,k,j,im).ge.-huge(scalar_2(i,k,j,im))) then\n"
        "          s15_count = s15_count + 1\n"
        "          if (.not.s15_first) then\n"
        "            s15_first = .true.\n"
        "            write(*,'(A,21(1X,I0))') 'S15Q',s15_step,rk_step,s15_owner,its,ite,jts,jte,i,j,k, &\n"
        "              transfer(s15_before,0),transfer(scalar_2(i,k,j,im),0), &\n"
        "              transfer(scalar_1(i,k,j,im),0),transfer(advect_tend(i,k,j),0), &\n"
        "              transfer(msfty(i,j),0),transfer(sc_tend(i,k,j,im),0),transfer(dt,0), &\n"
        "              transfer(c1(k),0),transfer(c2(k),0),transfer(muold(i),0),transfer(munew(i),0)\n"
        "          endif\n"
        "          endif\n"
        "        endif\n")
    text = text.replace(formula, before + formula + after)
    end = "END SUBROUTINE rk_update_scalar\n"
    summary = _s15_guard("qib_capture_summary",
        "    if (s15_enabled .and. scs.eq.P_QIB .and. sce.eq.P_QIB) &\n"
        "      write(*,'(A,8(1X,I0))') 'S15QC',s15_step,rk_step,s15_owner,its,ite,jts,jte,s15_count\n")
    return _replace_once(text, end, summary + end, "rk stage summary")


def instrument_solve_em(text: str) -> str:
    pattern = re.compile(r"CALL rk_update_scalar\([\s\S]*?kte=k_end[ \t]*\)[ \t]*\n", re.I)
    index = 0
    def replacement(match: re.Match[str]) -> str:
        nonlocal index
        index += 1
        base = match.group(0)
        if "rk_step=rk_step, dt=dt_rk" not in base:
            raise ProbeError("unexpected rk_update_scalar call shape")
        changed = base.replace("rk_step=rk_step, dt=dt_rk",
                               f"rk_step=rk_step, s15_step=grid%itimestep, s15_owner={index}, dt=dt_rk", 1)
        return _s15_guard(f"step_call_{index}", changed, base)
    text, count = pattern.subn(replacement, text)
    if count != 5:
        raise ProbeError(f"solve_em rk_update_scalar sites: expected 5, found {count}")
    return text


def unify_capture_gate(text: str) -> str:
    """Use the S15 switch for both QIB records and S10 validity-mask capture."""
    old = (
        "     kdm6_progb_capture_env = ''\n"
        "     call get_environment_variable('KDM6_PROGB_VALIDITY_CAPTURE_LOG', &\n"
        "          kdm6_progb_capture_env)\n"
        "     capture_enabled = (trim(kdm6_progb_capture_env) == '1')\n"
    )
    new = old.replace("KDM6_PROGB_VALIDITY_CAPTURE_LOG", "KDM6_S15_NATIVE_CAPTURE_LOG")
    return _replace_once(text, old, _s15_guard("unified_capture_gate", new, old),
                         "S10/S15 runtime capture gate")


def _record_progb_gate_inputs(text: str) -> str:
    lines = text.splitlines(keepends=True)
    sites = [i for i, line in enumerate(lines)
             if "S10_CAPTURE_BEGIN:progb_call_" in line]
    if len(sites) != 7:
        raise ProbeError(f"expected 7 S10 ProgB gate sites, found {len(sites)}")
    for site_no, marker_index in reversed(list(enumerate(sites, start=1))):
        macro_index = next((i for i in range(marker_index + 1, min(marker_index + 4, len(lines)))
                            if lines[i].strip() == f"#ifdef {S10_MACRO}"), None)
        if macro_index is None:
            raise ProbeError(f"S10 ProgB site {site_no} lacks its macro guard")
        call_index = next((i for i in range(marker_index - 1, max(-1, marker_index - 12), -1)
                           if "call ProgB_param(" in lines[i]), None)
        if call_index is None:
            raise ProbeError(f"S10 ProgB site {site_no} lacks a nearby call start")
        if any(line.rstrip().endswith(")") for line in lines[call_index:marker_index]):
            raise ProbeError(f"S10 ProgB site {site_no} marker is not inside the call argument list")
        code = (
            "   if (capture_enabled) then\n"
            "   do k = kts, kte\n"
            "     do i = its, ite\n"
            "       s15_gate_qg(i,k) = qrs_tmp(i,k,3)\n"
            "       s15_gate_brs(i,k) = brs(i,k)\n"
            "     enddo\n"
            "   enddo\n"
            "   endif\n"
        )
        # S10 places its capture marker on the continued final argument line.
        # Snapshot before the CALL begins, never inside the argument list.
        lines.insert(call_index, _s15_guard(f"progb_gate_inputs_{site_no}", code))
    return "".join(lines)


def _insert_s15_mp_locals(text: str) -> str:
    integer_anchor = "   integer                            :: i, j, k, mstepmax,mstepmax_i,         &\n"
    integer_decl = integer_anchor + (
        "                                         iprt, latd, lond, loop, loops, ifsat, &\n"
        "                                         n, idim, kdim\n"
    )
    local_block = _s15_guard("mp_locals",
        "   logical :: s15_trace_seen\n"
        "   real :: s15_qg0,s15_brs0,s15_t0,s15_cpm,s15_xlf,s15_qr0\n"
        "   real, dimension(its:ite,kts:kte) :: s15_gate_qg,s15_gate_brs\n")
    return _replace_once(text, integer_decl, local_block + integer_decl,
                         "kdm62D S15 locals")


def instrument_module_mp(text: str) -> str:
    # `capture_rhox_assigned` comes from the guarded S10 mask. False means the
    # S15 logger must emit only the flag and must not read rhox.
    text = unify_capture_gate(text)
    text = _insert_s15_mp_locals(text)
    text = _record_progb_gate_inputs(text)
    loop_anchor = "   do loop = 1,loops\n"
    text = _replace_once(text, loop_anchor,
        loop_anchor + _s15_guard("substep_reset", "     s15_trace_seen = .false.\n"),
        "kdm62D substep reset")
    graupel_anchor = (
        "            if(qrs(i,k,3).gt.0.) then\n"
        "! revised \n"
        "              coeres = (rslope2(i,k,3))*sqrt(rslope(i,k,3)*rslopeb(i,k,3))           &\n")
    saves = _s15_guard("pre_melt_operands",
        "              if (capture_enabled) then\n"
        "              s15_qg0 = qrs(i,k,3)\n"
        "              s15_brs0 = brs(i,k)\n"
        "              s15_t0 = t(i,k)\n"
        "              s15_cpm = cpm(i,k)\n"
        "              s15_xlf = xlf\n"
        "              s15_qr0 = qrs(i,k,1)\n"
        "              endif\n")
    text = _replace_once(text, graupel_anchor,
        graupel_anchor.replace("              coeres", saves + "              coeres"),
        "graupel melt pre-operands")
    brs_update = "              brs(i,k) = brs(i,k) + (pgmlt(i,k)/rhox(i,k))\n"
    event = _s15_guard("trace_melt_event",
        "              if (capture_enabled .and. capture_step.eq.1) then\n"
        "              if (.not.s15_trace_seen .and. s15_qg0.gt.0. .and. &\n"
        "                  s15_qg0.le.qcrmin .and. s15_brs0.le.1.e-15 .and. &\n"
        "                  pgmlt(i,k).lt.0.) then\n"
        "                s15_trace_seen = .true.\n"
        "                if (capture_rhox_assigned(i,k)) then\n"
        "                  write(*,'(A,25(1X,I0))') 'S15M',capture_step,lat,loop,capture_last_site,i,k, &\n"
        "                    transfer(s15_qg0,0),transfer(s15_brs0,0),transfer(qcrmin,0),transfer(1.e-15,0), &\n"
        "                    transfer(s15_gate_qg(i,k),0),transfer(s15_gate_brs(i,k),0),1, &\n"
        "                    transfer(rhox(i,k),0),transfer(s15_t0,0),transfer(t(i,k),0), &\n"
        "                    transfer(s15_cpm,0),transfer(s15_xlf,0),transfer(pgmlt(i,k),0), &\n"
        "                    transfer(s15_qr0,0),transfer(qrs(i,k,1),0), &\n"
        "                    transfer(qrs(i,k,3),0),transfer(brs(i,k),0),transfer(den(i,k),0),transfer(delz(i,k),0)\n"
        "                else\n"
        "                  write(*,'(A,24(1X,I0))') 'S15M',capture_step,lat,loop,capture_last_site,i,k, &\n"
        "                    transfer(s15_qg0,0),transfer(s15_brs0,0),transfer(qcrmin,0),transfer(1.e-15,0), &\n"
        "                    transfer(s15_gate_qg(i,k),0),transfer(s15_gate_brs(i,k),0),0, &\n"
        "                    transfer(s15_t0,0),transfer(t(i,k),0),transfer(s15_cpm,0),transfer(s15_xlf,0), &\n"
        "                    transfer(pgmlt(i,k),0),transfer(s15_qr0,0),transfer(qrs(i,k,1),0), &\n"
        "                    transfer(qrs(i,k,3),0),transfer(brs(i,k),0),transfer(den(i,k),0),transfer(delz(i,k),0)\n"
        "                endif\n"
        "              endif\n"
        "              endif\n")
    return _replace_once(text, brs_update, brs_update + event, "trace melt event record")


def prepare_shadow(source_root: Path, shadow_root: Path) -> None:
    """Generate guarded overlays in a disposable tree; never write source_root."""
    staged = shadow_root / "host"
    if staged.exists():
        raise ProbeError(f"shadow source directory already exists: {staged}")
    for rel, digest in SOURCE_PINS.items():
        src = source_root / rel
        if src.is_symlink() or not src.is_file():
            raise ProbeError(f"source is not a regular file: {src}")
        actual = sha256(src)
        if actual != digest:
            raise ProbeError(f"source pin mismatch for {rel}: {actual}")
    for rel in SOURCE_PINS:
        src = source_root / rel
        dst = staged / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        if sha256(dst) != SOURCE_PINS[rel]:
            raise ProbeError(f"copy digest mismatch for {rel}")
    em_path = staged / "dyn_em/module_em.F"
    em_path.write_text(instrument_module_em(em_path.read_text(encoding="latin1")), encoding="latin1")
    solve_path = staged / "dyn_em/solve_em.F"
    solve_path.write_text(instrument_solve_em(solve_path.read_text(encoding="latin1")), encoding="latin1")
    mp_path = staged / "phys/module_mp_kdm6.F"
    # Reuse S10's assignment-validity instrumentation; it carries the exact
    # per-ProgB-call mask to the consumer without touching an OUT value.
    try:
        from make_progb_validity_capture import build as build_s10_overlay
    except ImportError as exc:
        raise ProbeError("S10 overlay generator is unavailable in this checkout") from exc
    s10_manifest = shadow_root / "s10_validity_overlay_manifest.json"
    build_s10_overlay(source_root / "phys/module_mp_kdm6.F", mp_path, s10_manifest, "mp37")
    mp_path.write_text(instrument_module_mp(mp_path.read_text(encoding="utf-8")), encoding="utf-8")
    manifest = {
        "protocol": PROTOCOL,
        "status": "guarded_shadow_overlay_generated_not_compiled",
        "capture_window": CAPTURE_WINDOW,
        "source_root": str(source_root.resolve()),
        "sources": SOURCE_PINS,
        "shadow_sources": {
            rel: sha256(staged / rel) for rel in SOURCE_PINS
        },
        "s10_overlay_manifest": str(s10_manifest.resolve()),
        "note": "Canonical input was read-only; generated overlays are uncompiled and make no physics decision.",
    }
    (shadow_root / "s15_source_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    em = (source_root / "dyn_em/module_em.F").read_text(encoding="latin1")
    solve = (source_root / "dyn_em/solve_em.F").read_text(encoding="latin1")
    mp = (source_root / "phys/module_mp_kdm6.F").read_text(encoding="latin1")
    anchor_counts = {
        "solve_em.rk_update_scalar_calls": solve.count("CALL rk_update_scalar("),
        "module_em.rk_update_scalar_definition": em.count("SUBROUTINE rk_update_scalar("),
        "module_em.rk_update_scalar_formula": len(re.findall(
            r"scalar_2\(i,k,j,im\)\s*=\s*\(\(c1\(k\)\*muold\(i\)\+c2\(k\)\)", em, re.I
        )),
        "module_mp.kdm62D_calls": len(re.findall(r"call\s+kdm62D\s*\(", mp, re.I)),
        "module_mp.ProgB_param_calls": len(re.findall(r"call\s+ProgB_param\s*\(", mp, re.I)),
        "module_mp.ProgB_param_definition": len(re.findall(r"subroutine\s+ProgB_param\s*\(", mp, re.I)),
        "module_mp.graupel_melt_consumer": mp.count(
            "brs(i,k) = brs(i,k) + (pgmlt(i,k)/rhox(i,k))"
        ),
    }
    expected = {
        "solve_em.rk_update_scalar_calls": 5,
        "module_em.rk_update_scalar_definition": 1,
        "module_em.rk_update_scalar_formula": 2,
        "module_mp.kdm62D_calls": 1,
        "module_mp.ProgB_param_calls": 7,
        "module_mp.ProgB_param_definition": 1,
        "module_mp.graupel_melt_consumer": 1,
    }
    if anchor_counts != expected:
        raise ProbeError(f"source anchors changed; refusing patch plan: {anchor_counts}")
    patch_plan = {
        "protocol": PROTOCOL,
        "status": "generated_guarded_shadow_patch_uncompiled",
        "capture_window": CAPTURE_WINDOW,
        "runtime_environment": "KDM6_S15_NATIVE_CAPTURE_LOG controls both QIB records and S10 validity-mask production",
        "source_sha256": SOURCE_PINS,
        "anchor_counts": anchor_counts,
        "hooks": [
            {
                "source": "dyn_em/module_em.F",
                "site": "rk_update_scalar result assignments (both RK branches)",
                "capture": "P_QIB sign transitions; one first row and count per tile/stage",
                "operands": ["scalar_2 before/after", "scalar_1", "advect_tend", "msfty", "sc_tend", "dt", "c1", "c2", "muold", "munew"],
            },
            {
                "source": "phys/module_mp_kdm6.F",
                "site": "ProgB_param output gate and pgmlt consumer",
                "capture": "rhox validity mask from gate; first positive-trace applied melt per step/column/substep",
                "operands": ["qg", "brs", "qg_gate", "brs_gate", "rhox only if valid", "qr", "T", "cpm", "xlf", "pgmlt", "den", "delz"],
            },
        ],
        "limitations": [
            "The patch is generated but uncompiled; it contains no measured event/count values.",
            "Source-strip audit and compiled same-build control/capture equality are prerequisites to native evidence.",
            "No undefined rhox value may be read or serialized when its validity flag is false.",
        ],
    }
    (shadow_root / "s15_patch_plan.json").write_text(
        json.dumps(patch_plan, indent=2) + "\n", encoding="utf-8"
    )


def audit_shadow(source_root: Path, shadow_root: Path) -> None:
    manifest = json.loads((shadow_root / "s15_source_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("protocol") != PROTOCOL:
        raise ProbeError("shadow manifest protocol mismatch")
    shadow_hashes = manifest.get("shadow_sources")
    if not isinstance(shadow_hashes, dict):
        raise ProbeError("shadow manifest lacks generated-source digests")
    for rel, digest in SOURCE_PINS.items():
        src, staged = source_root / rel, shadow_root / "host" / rel
        if sha256(src) != digest:
            raise ProbeError(f"source changed since preparation: {rel}")
        if not staged.is_file():
            raise ProbeError(f"missing staged source: {rel}")
        expected_shadow_sha = shadow_hashes.get(rel)
        if not isinstance(expected_shadow_sha, str) or len(expected_shadow_sha) != 64:
            raise ProbeError(f"shadow manifest lacks a valid staged digest for {rel}")
        check_shadow_digest(staged, expected_shadow_sha, rel)
        text = staged.read_text(encoding="utf-8" if rel.endswith("module_mp_kdm6.F") else "latin1")
        text = _s15_strip(text)
        if rel.endswith("module_mp_kdm6.F"):
            try:
                from make_progb_validity_capture import strip_capture as strip_s10_overlay
            except ImportError as exc:
                raise ProbeError("S10 overlay stripper is unavailable in this checkout") from exc
            text = strip_s10_overlay(text)
        stripped = text.encode("utf-8" if rel.endswith("module_mp_kdm6.F") else "latin1")
        if hashlib.sha256(stripped).hexdigest() != digest:
            raise ProbeError(f"unmarked source change or strip mismatch: {rel}")


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("source_root", type=Path)
    prep.add_argument("shadow_root", type=Path)
    audit = sub.add_parser("audit")
    audit.add_argument("source_root", type=Path)
    audit.add_argument("shadow_root", type=Path)
    replay = sub.add_parser("replay")
    replay.add_argument("capture", type=Path)
    replay.add_argument("--plan", type=Path, required=True)
    replay.add_argument("--plan-sha256", required=True,
                        help="out-of-band SHA-256 of the independently prepared expected plan")
    prelink = sub.add_parser("prelink-check")
    prelink.add_argument("--plan", type=Path, required=True,
                         help="predeclared S15 run plan containing its r6 input binding")
    prelink.add_argument("--plan-sha256", required=True,
                         help="external SHA-256 pin of the complete run plan")
    launch = sub.add_parser("launch-check")
    launch.add_argument("--plan", type=Path, required=True)
    launch.add_argument("--plan-sha256", required=True,
                         help="external SHA-256 pin of the complete run plan")
    launch.add_argument("--link-receipt", type=Path, required=True)
    launch.add_argument("--link-receipt-sha256", required=True,
                         help="external SHA-256 pin of the B link receipt")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "prepare":
            prepare_shadow(args.source_root, args.shadow_root)
            print("S15 shadow sources staged; no instrumentation or host run was performed")
        elif args.cmd == "audit":
            audit_shadow(args.source_root, args.shadow_root)
            print("S15 source/strip audit PASS")
        elif args.cmd == "prelink-check":
            plan_sha = verify_plan_pin(args.plan, args.plan_sha256)
            plan = json.loads(args.plan.read_text(encoding="utf-8"))
            counts = verify_pre_link_binding(plan.get("pre_link_binding", {}))
            print(json.dumps({"status": "PASS_current_snapshot_only",
                              "plan_sha256": plan_sha, **counts}, sort_keys=True))
        elif args.cmd == "launch-check":
            counts = verify_postlink_binding(args.plan, args.plan_sha256,
                                             args.link_receipt,
                                             args.link_receipt_sha256)
            print(json.dumps({"status": "PASS_read_only_launch_gate",
                              **counts}, sort_keys=True))
        else:
            rows, summaries = parse_capture(args.capture)
            counts = verify_plan(rows, args.plan, summaries,
                                 args.plan_sha256, args.capture)
            print(json.dumps({"protocol": PROTOCOL, "counts": counts}, sort_keys=True))
    except (OSError, ProbeError, json.JSONDecodeError) as exc:
        print(f"S15 REFUSED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
