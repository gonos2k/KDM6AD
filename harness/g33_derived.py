#!/usr/bin/env python3
"""Comparator-side recomputation of every derived flag, from raw operand bits.

Owner adjudication (review vs main@9f7a9fe): producer-emitted flags —
mstep_exact_integer, gate_exact_01, active_mask, *_floor_active, cap/clamp
branches — are demoted to debugging aids. A producer that emits both an operand
and a verdict about that operand is attesting to its own arithmetic; acceptance
authority is what THIS module recomputes from the raw payloads.

The producer flags are still cross-checked (check_producer_flags): a producer
whose own verdicts disagree with a recomputation from its own operands is not
mis-flagged, it is broken, and the run is invalid before any cross-tree
comparison starts.

Two deliberate semantic splits, documented rather than hidden:

- Floor activity has a VALUE view and a BITS view. The producer computes
  `safe != raw` (value semantics — what the C++ expression says), so the
  cross-check reproduces exactly that. The comparator's own authority is the
  raw-bit inequality, which additionally sees value-equal bit-different
  replacements (the class of mechanism a first-divergence gate exists to see).

- min()/clamp() selections are the 4-state BRANCH enum (LEFT_SELECTED /
  RIGHT_SELECTED / TIE / UNORDERED), never a boolean: at a TIE both backends
  produce the SAME value from DIFFERENT branch semantics, which a boolean
  hides — and with a NaN operand both a<b and b<a are false, so a 3-state
  enum misfiles NaN as TIE. UNORDERED is always recorded; it is a FAIL only
  in an active, finite-required cell (unordered_failures).
"""
from __future__ import annotations

import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from g33_dump import (BRANCH_LEFT_SELECTED, BRANCH_RIGHT_SELECTED, BRANCH_TIE,
                      BRANCH_UNORDERED, G33Corruption)

_W = {"f32": 4, "f64": 8, "i32": 4, "u8": 1}
_FMT = {"f32": ">f", "f64": ">d", "i32": ">i", "u8": ">B"}

# mstep is a NUMERICAL algorithm variable (CFL sub-cycling count), not a physical
# quantity — its bound is an ALGORITHMIC contract, not a physical range. A decoded
# value outside it is an invalid run, not a rounding finding.
MSTEP_RANGE = (1, 100)   # algorithmic contract range

# Floor relation (owner math review §2.2): the branch condition is raw vs the
# threshold, not "did the output change". `safe != raw` is a RESULT comparison
# and bit inequality is a REPRESENTATION comparison — neither is the branch.
FLOOR_BELOW = 0          # raw <  qcrmin  -> clamp fires
FLOOR_AT_OR_ABOVE = 1    # raw >= qcrmin  -> raw passes through (tie included)
FLOOR_UNORDERED = 2      # NaN operand    -> verdict deferred to the masks


def unpack_values(dtype: str, payload: bytes) -> list:
    if dtype not in _W:
        raise G33Corruption(f"unknown dtype {dtype!r}")
    w = _W[dtype]
    if len(payload) % w:
        raise G33Corruption(f"payload of {len(payload)} bytes is not a multiple of {w}")
    return [struct.unpack(_FMT[dtype], payload[i:i + w])[0]
            for i in range(0, len(payload), w)]


def _raw_bits(dtype: str, payload: bytes) -> list:
    w = _W[dtype]
    fmt = {1: ">B", 4: ">I", 8: ">Q"}[w]
    return [struct.unpack(fmt, payload[i:i + w])[0]
            for i in range(0, len(payload), w)]


def derive_mstep(dtype: str, payload: bytes) -> dict:
    """decoded_i32 and exact_integer from the NATIVE mstep bits.

    int32(2) cannot hide 2.0 vs 2.0000000000000004 — the exactness flag is what
    tells them apart, so it must come from the bits, not from the producer.
    Decoding reproduces the producer's `.to(kInt32)`: truncation toward zero.
    A non-finite substep count is not a flag, it is an invalid run.
    """
    if dtype == "i32":                          # Fortran native: integral by type
        vals = unpack_values("i32", payload)
        return {"decoded_i32": vals, "exact_integer": [1] * len(vals)}
    if dtype not in ("f32", "f64"):
        raise G33Corruption(f"mstep_native cannot be {dtype!r}")
    vals = unpack_values(dtype, payload)
    for i, v in enumerate(vals):
        if not math.isfinite(v):
            raise G33Corruption(f"mstep_native[{i}] is non-finite ({v!r})")
    return {"decoded_i32": [int(math.trunc(v)) for v in vals],
            "exact_integer": [1 if float(v).is_integer() else 0 for v in vals]}


def derive_gate(dtype: str, payload: bytes) -> dict:
    """exact_01, active_mask and decoded_u8 from the NATIVE gate bits.

    Value semantics on purpose — the producer expressions are (gate==0)||(gate==1)
    and (gate!=0), both value comparisons, and the cross-check must reproduce what
    the producer computes. A gate of 0.5 is flagged non-exact rather than raising:
    that inexactness IS a finding for the comparator, not an I/O error. decoded_u8
    is None at non-exact positions — decoding a non-0/1 gate has no meaning the
    manifest can express.
    """
    if dtype == "u8":
        vals = unpack_values("u8", payload)
        return {"exact_01": [1 if v in (0, 1) else 0 for v in vals],
                "active_mask": [1 if v != 0 else 0 for v in vals],
                "decoded_u8": [v if v in (0, 1) else None for v in vals]}
    if dtype not in ("f32", "f64"):
        raise G33Corruption(f"gate_native cannot be {dtype!r}")
    vals = unpack_values(dtype, payload)
    exact = [1 if (v == 0.0 or v == 1.0) else 0 for v in vals]
    return {"exact_01": exact,
            # NaN != 0 is True in Python and in the producer's tensor compare
            "active_mask": [1 if v != 0 else 0 for v in vals],
            "decoded_u8": [int(v) if e else None for v, e in zip(vals, exact)]}


def derive_floor_active(dtype: str, raw_payload: bytes, safe_payload: bytes) -> dict:
    """Both views of "did the safe-floor change the value at this cell".

    value_changed reproduces the producer's `(safe != raw)`; bits_changed is the
    comparator's stronger authority — it also sees a value-equal bit-different
    replacement (+0.0 -> -0.0), exactly the mechanism class only a raw-bit view
    can see.
    """
    if len(raw_payload) != len(safe_payload):
        raise G33Corruption("floor operands have different payload sizes")
    raw_v, safe_v = unpack_values(dtype, raw_payload), unpack_values(dtype, safe_payload)
    raw_b, safe_b = _raw_bits(dtype, raw_payload), _raw_bits(dtype, safe_payload)
    return {"value_changed": [1 if s != r else 0 for r, s in zip(raw_v, safe_v)],
            "bits_changed": [1 if sb != rb else 0 for rb, sb in zip(raw_b, safe_b)]}


def _coerce_threshold(dtype: str, qcrmin: float) -> tuple:
    """qcrmin as the backend actually sees it: rounded through the dtype.

    Comparing f32 raw values against a full-precision Python float threshold
    would use a boundary NEITHER backend computes with.
    """
    if dtype not in ("f32", "f64"):
        raise G33Corruption(f"floor operand cannot be {dtype!r}")
    bits = struct.unpack({"f32": ">I", "f64": ">Q"}[dtype],
                         struct.pack(_FMT[dtype], qcrmin))[0]
    value = struct.unpack(_FMT[dtype], struct.pack(_FMT[dtype], qcrmin))[0]
    return value, bits


def classify_floor(dtype: str, raw_payload: bytes, qcrmin: float) -> list:
    """Per-element FLOOR relation of raw against the dtype-faithful threshold."""
    thr, _ = _coerce_threshold(dtype, qcrmin)
    out = []
    for v in unpack_values(dtype, raw_payload):
        if math.isnan(v):
            out.append(FLOOR_UNORDERED)
        else:
            out.append(FLOOR_BELOW if v < thr else FLOOR_AT_OR_ABOVE)
    return out


def check_floor_semantics(dtype: str, raw_payload: bytes, safe_payload: bytes,
                          qcrmin: float) -> dict:
    """The floor authority: relation to the threshold, plus a BIT-EXACT check
    that the emitted safe value is max(raw, qcrmin) under that relation.

    BELOW must yield exactly the threshold's bits and AT_OR_ABOVE exactly the
    raw bits (a tie returns identical bits from either branch, so it needs no
    fourth state here — the branch enum's TIE ambiguity does not arise for a
    max against a constant). UNORDERED elements carry no bit expectation; NaN
    propagation is backend-defined and its verdict belongs to the masks.
    """
    if len(raw_payload) != len(safe_payload):
        raise G33Corruption("floor operands have different payload sizes")
    thr_v, thr_bits = _coerce_threshold(dtype, qcrmin)
    rel = classify_floor(dtype, raw_payload, qcrmin)
    raw_b = _raw_bits(dtype, raw_payload)
    safe_b = _raw_bits(dtype, safe_payload)
    for i, (r, rb, sb) in enumerate(zip(rel, raw_b, safe_b)):
        if r == FLOOR_UNORDERED:
            continue
        expected = thr_bits if r == FLOOR_BELOW else rb
        if sb != expected:
            raise G33Corruption(
                f"safe[{i}] bits 0x{sb:x} != max(raw, qcrmin) bits 0x{expected:x} "
                f"(relation {'BELOW' if r == FLOOR_BELOW else 'AT_OR_ABOVE'}, "
                f"threshold {thr_v!r}) — the clamp is not the declared semantics")
    return {"relation": rel,
            "representation_changed": [1 if a != b else 0
                                       for a, b in zip(raw_b, safe_b)]}


def classify_min(dtype: str, left_payload: bytes, right_payload: bytes) -> list:
    """Per-element BRANCH enum for min(left, right).

    At a TIE both backends yield the same value from different branch semantics —
    precisely what a first-divergence gate must see and a boolean cap_active
    hides. A NaN operand is UNORDERED, not TIE and not an exception: a<b and b<a
    are both false, so a 3-state enum silently misfiles NaN as TIE, and raising
    would fail LEGITIMATE dumps — KDM6 evaluates raw divide/sqrt in dead
    branches and masks afterwards (protocol §236), so NaN operands are expected
    there. This function reports what the bits say; whether an UNORDERED
    comparison is a defect depends on the masks — unordered_failures() applies
    the verdict rule.
    """
    lv, rv = unpack_values(dtype, left_payload), unpack_values(dtype, right_payload)
    if len(lv) != len(rv):
        raise G33Corruption("min operands have different lengths")
    out = []
    for a, b in zip(lv, rv):
        if isinstance(a, float) and (math.isnan(a) or math.isnan(b)):
            out.append(BRANCH_UNORDERED)
        else:
            out.append(BRANCH_LEFT_SELECTED if a < b
                       else BRANCH_RIGHT_SELECTED if b < a else BRANCH_TIE)
    return out


def unordered_failures(branches: list, active_mask: list,
                       finite_required_mask: list) -> list:
    """Indices where min() was UNORDERED in an active, finite-required cell.

    Owner rule: active && finite_required && UNORDERED is a FAIL — a NaN reached
    a comparison the physics actually takes, and min()-with-NaN is exactly where
    the two languages' semantics part ways. UNORDERED in a dead or
    non-finite-required cell stays recorded in `branches` but is not a failure:
    that is the documented KDM6 dead-branch pattern, and failing on it would
    train whoever runs the gate to ignore it.
    """
    if not (len(branches) == len(active_mask) == len(finite_required_mask)):
        raise G33Corruption("branch/mask length mismatch")
    return [i for i, (br, a, fr)
            in enumerate(zip(branches, active_mask, finite_required_mask))
            if br == BRANCH_UNORDERED and a and fr]


# fields check_producer_flags MUST find; a cross-check that silently skips an
# absent operand is vacuous, which is the failure mode this whole file replaces
_REQUIRED = ("mstep_input_native", "mstep_native",
             "mstep_decoded_i32", "mstep_exact_integer",
             "gate_native", "gate_decoded_u8", "gate_exact_01", "active_mask",
             "dend_raw", "dend_safe", "dend_floor_active",
             "delz_raw", "delz_safe", "delz_floor_active",
             "qcrmin_effective", "dtcld_effective")


def check_producer_flags(fields: dict, n: int, qcrmin: float,
                         dtcld: float = None) -> None:
    """Cross-check every producer-emitted flag against a recomputation from the
    producer's own raw operands.

    `fields` maps field name -> (dtype, payload) for ONE substep_pre group;
    `n` is this substep's 1-based index and `qcrmin` the scheme floor from the
    run contract. Any disagreement means the producer's arithmetic is not what
    its evidence claims — the run is invalid, so this raises rather than
    reports.
    """
    if not (type(n) is int and n >= 1):    # `type is int` also excludes bool
        raise G33Corruption(f"substep index n must be a positive int, got {n!r}")
    missing = [f for f in _REQUIRED if f not in fields]
    if missing:
        raise G33Corruption(f"cross-check is missing operand(s): {missing}")

    def _got(name):
        dtype, payload = fields[name]
        return unpack_values(dtype, payload)

    def _demand(name, expected, producer):
        for i, (e, p) in enumerate(zip(expected, producer)):
            if e != p:
                raise G33Corruption(
                    f"producer flag {name}[{i}] = {p} but recomputation from its "
                    f"own operands gives {e} — the producer's arithmetic is not "
                    f"what its evidence claims")
        if len(expected) != len(producer):
            raise G33Corruption(f"producer flag {name} has wrong length")

    m = derive_mstep(*fields["mstep_native"])
    _demand("mstep_decoded_i32", m["decoded_i32"], _got("mstep_decoded_i32"))
    _demand("mstep_exact_integer", m["exact_integer"], _got("mstep_exact_integer"))

    # RECOMPUTED exactness must hold — the protocol's acceptance is
    # "exact_integer == true", not merely "the producer's exact flag agrees
    # with the recomputation". A run that HONESTLY reports mstep_native=2.5 with
    # exact=0 was passing: the producer was not caught lying, but the run is
    # still invalid (a non-integral substep count is a broken caller contract).
    bad_exact = [i for i, ok in enumerate(m["exact_integer"]) if not ok]
    if bad_exact:
        raise G33Corruption(
            f"mstep_native is not exactly integral at columns {bad_exact[:16]} "
            f"— a non-integral substep count is an invalid run, not a finding")
    lo, hi = MSTEP_RANGE
    for i, mv in enumerate(m["decoded_i32"]):
        if not (lo <= mv <= hi):
            raise G33Corruption(
                f"mstep_decoded_i32[{i}] = {mv} outside the algorithmic contract "
                f"range [{lo}, {hi}] — an invalid run")

    # P0-3: mstep_native is the EFFECTIVE (post-clamp) value; mstep_input_native
    # is the RAW mstep_col the caller passed. In a valid run the clamp is a
    # no-op, so their bits must be identical — a break means the caller passed a
    # mstep below the [1, ...] contract and the clamp masked it, which is a
    # caller/runtime contract error, not a rounding finding. Bit-exact, per the
    # native dtype (i32 for Fortran, f64 for C++).
    idt, iraw = fields["mstep_input_native"]
    edt, eraw = fields["mstep_native"]
    if idt != edt:
        raise G33Corruption(
            f"mstep_input_native ({idt}) and mstep_native ({edt}) dtypes differ")
    if _raw_bits(idt, iraw) != _raw_bits(edt, eraw):
        raise G33Corruption(
            "mstep_input_native != mstep_native — the clamp changed the caller's "
            "mstep, so the caller passed a sub-contract value (invalid run, not a "
            "rounding finding)")

    # P0-5: the threshold/timestep the substep ACTUALLY used, checked against the
    # sealed contract bits. Raw/safe results alone cannot catch a wrong sealed
    # qcrmin when every rho,dz sits far above it. The dtype is VALIDATED, not
    # assumed: reading a producer's f32 payload as f64 would misalign the bytes
    # and mask exactly the mismatch this check exists to find.
    qdt, qraw = fields["qcrmin_effective"]
    if qdt != "f64":
        raise G33Corruption(f"qcrmin_effective dtype {qdt!r} is not f64")
    _, qbits = _coerce_threshold("f64", qcrmin)
    for i, qv in enumerate(_raw_bits(qdt, qraw)):
        if qv != qbits:
            raise G33Corruption(
                f"qcrmin_effective[{i}] bits 0x{qv:x} != sealed contract qcrmin "
                f"0x{qbits:x} — the run used a threshold the evidence does not seal")
    if dtcld is not None:
        ddt, draw = fields["dtcld_effective"]
        if ddt != "f64":
            raise G33Corruption(f"dtcld_effective dtype {ddt!r} is not f64")
        _, dbits = _coerce_threshold("f64", float(dtcld))
        for i, dv in enumerate(_raw_bits(ddt, draw)):
            if dv != dbits:
                raise G33Corruption(
                    f"dtcld_effective[{i}] bits 0x{dv:x} != sealed dtcld 0x{dbits:x}")

    g = derive_gate(*fields["gate_native"])
    _demand("gate_exact_01", g["exact_01"], _got("gate_exact_01"))
    _demand("active_mask", g["active_mask"], _got("active_mask"))
    _demand("gate_decoded_u8", g["decoded_u8"], _got("gate_decoded_u8"))
    # The gate is DERIVED state, not free state: gate_b(n) = [n <= mstep_b]
    # (owner math review §2.1). Checking only that the gate is exactly 0/1
    # cannot catch a gate that is WRONG but exactly 0/1 — the law ties it to
    # the operand it is derived from.
    _demand("gate_vs_mstep_law", [1 if n <= mv else 0 for mv in m["decoded_i32"]],
            g["decoded_u8"])

    for sp in ("dend", "delz"):
        dt_raw, raw = fields[f"{sp}_raw"]
        dt_safe, safe = fields[f"{sp}_safe"]
        if dt_raw != dt_safe:
            raise G33Corruption(f"{sp}_raw/{sp}_safe dtype mismatch")
        # authority: relation to the threshold + bit-exact max(raw, qcrmin)
        check_floor_semantics(dt_raw, raw, safe, qcrmin)
        # cross-check: the producer's own (safe != raw) flag, value semantics
        fl = derive_floor_active(dt_raw, raw, safe)
        _demand(f"{sp}_floor_active", fl["value_changed"], _got(f"{sp}_floor_active"))
