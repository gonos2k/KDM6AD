#!/usr/bin/env python3
"""G3.3-M four-case tri-state comparator — the verdict core.

Given the four normalized runs (legacy-F/legacy-C++/conservative-F/conservative-
C++), adjudicate whether the observed Fortran↔C++ difference originated in
conservative-only arithmetic. This is the pure verdict logic over a canonical
EVENT STREAM; the bundle readers that produce the normalized runs are wired in
separately (g33_bundle_io/g33_normalize).

Normalized run (one per backend/variant):
  {"algorithm": "legacy"|"conservative",
   "ops":    [ {n,col,k,role,species,op_id,field,dtype,bits}, ... ],
   "stages": [ {stage,n,col,k,field,dtype,bits}, ... ]}   # stage incl. surface

Design contract (owner P0 closeout):
  * Canonical execution order comes ENTIRELY from the schema single-authority
    (g33_schema.species_rank / op_ordinal / field_ordinal / stage_field_ordinal):
    outer_pre_sed, then per substep n [substep_pre(n) BEFORE ops(n)], then surface;
    within a substep (k, species, op, field) with the column lane innermost. The
    producer's own sequence numbers are NOT consumed — the comparator regenerates
    the order, so a producer that renumbers records cannot bias it.
  * Comparison is IDENTITY-FIRST: a differing / duplicated identity, an unknown
    stage/species/field, a dtype that disagrees with the schema, or any malformed
    record is INVALID_EVIDENCE — never a numerical divergence or a crash.
  * Attribution uses the closed-world MechanismSpec.kind (g33_mechanism):
      causal_carry differs first  -> INVALID_EVIDENCE (internally inconsistent)
      external_input differs first -> INCONCLUSIVE (unsealed precondition)
      pre-sed / out_of_scope       -> INCONCLUSIVE
      conservative-only arithmetic -> FAIL
      same SHARED rung both pairs   -> PASS  (tag + dtype + cell), with the raw-bit
                                       signature (ULP delta + direction) recorded.
"""
from __future__ import annotations

import os
import struct
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import g33_mechanism as mech  # noqa: E402
import g33_schema as schema    # noqa: E402

VERDICTS = ("PASS", "FAIL", "INCONCLUSIVE", "INVALID_EVIDENCE")
_ALGOS = ("legacy", "conservative")
_STAGES = ("outer_pre_sed", "substep_pre", "surface")
_PRESED = ("outer_pre_sed", "substep_pre")
_SURFACE_N = 10 ** 9          # order surface after every substep
_WIDTH = {"f32": 32, "f64": 64}


class StructuralError(Exception):
    """Evidence is malformed — verdict is INVALID_EVIDENCE, never a divergence."""


@dataclass(frozen=True)
class Event:
    order: tuple        # canonical execution order (schema-derived)
    phase: str          # outer_pre_sed | substep_pre | op | surface
    identity: tuple     # WITHIN-pair match key (F vs C++, same variant) incl. dtype
    shared_key: tuple | None   # VARIANT-INDEPENDENT identity for cross-pair PASS
    kind: str | None    # MechanismSpec.kind (None for pre-sed stages)
    tag: str | None
    dtype: str
    bits: int


def _events(run) -> list[Event]:
    try:
        algo = run["algorithm"]
        if algo not in _ALGOS:
            raise StructuralError(f"unknown algorithm {algo!r}")
        out: list[Event] = []
        for o in run["ops"]:
            role, sp, op_id, fld, dt = (o["role"], o["species"], o["op_id"],
                                        o["field"], o["dtype"])
            try:
                sr = schema.species_rank(sp)
                oo = schema.op_ordinal(algo, role, sp, op_id)
                fo = schema.field_ordinal(algo, role, op_id, fld)
                want_dt = schema.field_dtype(algo, role, op_id, fld)
            except (KeyError, ValueError) as e:
                raise StructuralError(f"op not in schema: {op_id}.{fld} [{role}/{sp}]") from e
            if dt != want_dt:
                raise StructuralError(f"dtype {op_id}.{fld}: got {dt} want {want_dt}")
            spec = mech.mechanism(algo, role, sp, op_id, fld)
            out.append(Event(
                order=(o["n"], 1, o["k"], sr, oo, fo, o["col"]),
                phase="op",
                identity=("op", o["n"], o["col"], o["k"], role, sp, op_id, fld, dt),
                shared_key=("op", o["n"], o["col"], o["k"], role, sp, spec.tag, dt),
                kind=spec.kind, tag=spec.tag, dtype=dt, bits=_bits(o["bits"], dt)))
        for s in run["stages"]:
            stage, fld, dt = s["stage"], s["field"], s["dtype"]
            if stage not in _STAGES:
                raise StructuralError(f"unknown stage {stage!r}")
            if stage == "surface":
                fo = schema.stage_field_ordinal("surface", fld)
                spec = mech.surface_mechanism(fld)
                out.append(Event(
                    order=(_SURFACE_N, 0, 0, 0, 0, fo, s["col"]),
                    phase="surface",
                    identity=("surface", s["n"], s["col"], s["k"], fld, dt),
                    shared_key=("surface", s["col"], spec.tag, dt),
                    kind=spec.kind, tag=spec.tag, dtype=dt, bits=_bits(s["bits"], dt)))
            else:                                 # outer_pre_sed | substep_pre(n)
                n = 0 if stage == "outer_pre_sed" else s["n"]
                fo = schema.stage_field_ordinal(stage, fld)
                out.append(Event(
                    order=(n, 0, s["k"], 0, 0, fo, s["col"]),
                    phase=stage,
                    identity=(stage, s["n"], s["col"], s["k"], fld, dt),
                    shared_key=None, kind=None, tag=None, dtype=dt,
                    bits=_bits(s["bits"], dt)))
    except (KeyError, TypeError, ValueError, IndexError) as e:
        # P0-6: any malformed normalized record is INVALID_EVIDENCE, not a crash.
        raise StructuralError(f"malformed normalized run: {e!r}") from e
    out.sort(key=lambda e: e.order)
    ids = [e.identity for e in out]
    if len(ids) != len(set(ids)):
        raise StructuralError("duplicate record identity")
    return out


def _bits(v, dt):
    b = int(v)
    if b < 0 or b >= (1 << _WIDTH.get(dt, 8)):
        raise StructuralError(f"bits {v!r} out of range for dtype {dt}")
    return b


def _mono(bits, w):
    """IEEE bit pattern -> order-preserving unsigned int (Dawson transform)."""
    msb = 1 << (w - 1)
    return (~bits & ((1 << w) - 1)) if (bits & msb) else (bits | msb)


def _signature(dt, f_bits, c_bits):
    """Raw-bit divergence signature for the result — direction + ULP distance."""
    sig = {"dtype": dt, "f_bits": f"{f_bits:#x}", "c_bits": f"{c_bits:#x}",
           "xor": f"{f_bits ^ c_bits:#x}"}
    w = _WIDTH.get(dt)
    if w:
        ulp = _mono(c_bits, w) - _mono(f_bits, w)
        sig["ulp_delta"] = ulp
        sig["direction"] = "C>F" if ulp > 0 else ("C<F" if ulp < 0 else "equal")
    return sig


@dataclass(frozen=True)
class Divergence:
    invalid: str | None = None
    phase: str | None = None
    identity: tuple | None = None
    shared_key: tuple | None = None
    kind: str | None = None
    tag: str | None = None
    signature: dict | None = None


def compare_pair(f_run, c_run) -> Divergence:
    """First Fortran↔C++ divergence for one variant, in canonical event order."""
    try:
        fe, ce = _events(f_run), _events(c_run)
    except StructuralError as e:
        return Divergence(invalid=str(e))
    fmap = {e.identity: e for e in fe}
    cmap = {e.identity: e for e in ce}
    if set(fmap) != set(cmap):
        fo, co = len(set(fmap) - set(cmap)), len(set(cmap) - set(fmap))
        return Divergence(invalid=f"record identity universe differs "
                          f"(F-only {fo}, C-only {co})")
    for e in fe:                                  # canonical order
        ce_e = cmap[e.identity]
        if e.bits != ce_e.bits:
            return Divergence(phase=e.phase, identity=e.identity,
                              shared_key=e.shared_key, kind=e.kind, tag=e.tag,
                              signature=_signature(e.dtype, e.bits, ce_e.bits))
    return Divergence()                           # bit-identical


def classify(legacy: Divergence, conservative: Divergence):
    """(verdict, reason). Evidence-integrity outranks any numerical verdict."""
    pairs = (("legacy", legacy), ("conservative", conservative))
    for name, d in pairs:                         # 1. structural failure
        if d.invalid:
            return "INVALID_EVIDENCE", f"{name} pair: {d.invalid}"
    for name, d in pairs:                         # 2. carry inconsistency
        if d.kind == mech.CAUSAL_CARRY:
            return "INVALID_EVIDENCE", (f"{name} pair: causal carry {d.tag} "
                                        f"{d.identity} differs while its source matched")
    for name, d in pairs:                         # 3. upstream (pre-sed)
        if d.phase in _PRESED:
            return "INCONCLUSIVE", f"{name} divergence upstream at {d.phase} {d.identity}"
    for name, d in pairs:                         # 4. unsealed external precondition
        if d.kind == mech.EXTERNAL_INPUT:
            return "INCONCLUSIVE", (f"{name} first-diverges at external input {d.tag} "
                                    f"{d.identity} — a fixture/parameter precondition, "
                                    f"not sealed by bundle preflight")
    for name, d in pairs:                         # 5. out-of-scope species/output
        if d.kind == mech.OUT_OF_SCOPE:
            return "INCONCLUSIVE", (f"{name} first-diverges at out-of-scope {d.tag} "
                                    f"{d.identity} — no instrumented provenance")
    # 6. FAIL DEFINITION (owner-pinned, 2026-07): G3.3-M FAILs iff the conservative
    #    pair's first cross-tree divergence lands in conservative-only arithmetic —
    #    ANY such mismatch fails, even when the legacy pair also diverges at its
    #    corresponding variant-specific rung in parallel. FAIL is decided by the
    #    conservative pair alone; the legacy pair is not a mitigating control.
    if conservative.kind == mech.CONSERVATIVE:
        return "FAIL", (f"conservative pair first-diverges at {conservative.tag} "
                        f"{conservative.identity} — arithmetic absent from the legacy ladder")
    if legacy.phase is None and conservative.phase is None:   # 7. no divergence
        return "INCONCLUSIVE", "no cross-tree divergence in either pair at this fixture"
    if (legacy.kind == mech.SHARED and conservative.kind == mech.SHARED  # 8. shared
            and legacy.shared_key is not None
            and legacy.shared_key == conservative.shared_key):
        return "PASS", (f"both pairs first-diverge at the shared mechanism {legacy.tag} "
                        f"{legacy.shared_key} — common to both variants")
    return "INCONCLUSIVE", (f"pairs diverge differently: legacy {legacy.phase}/"
                            f"{legacy.tag}, conservative {conservative.phase}/{conservative.tag}")


def _require_algorithm(run, want, label):
    if run.get("algorithm") != want:
        raise StructuralError(f"{label} run algorithm is {run.get('algorithm')!r}, want {want!r}")


def adjudicate(legacy_f, legacy_c, conservative_f, conservative_c):
    try:                                          # algorithm preflight
        _require_algorithm(legacy_f, "legacy", "legacy_f")
        _require_algorithm(legacy_c, "legacy", "legacy_c")
        _require_algorithm(conservative_f, "conservative", "conservative_f")
        _require_algorithm(conservative_c, "conservative", "conservative_c")
    except StructuralError as e:
        return {"verdict": "INVALID_EVIDENCE", "reason": str(e),
                "legacy_first_divergence": None, "conservative_first_divergence": None}
    leg = compare_pair(legacy_f, legacy_c)
    con = compare_pair(conservative_f, conservative_c)
    verdict, reason = classify(leg, con)

    def _d(x):
        return {"invalid": x.invalid, "phase": x.phase, "identity": x.identity,
                "kind": x.kind, "tag": x.tag, "signature": x.signature}
    return {"verdict": verdict, "reason": reason,
            "legacy_first_divergence": _d(leg),
            "conservative_first_divergence": _d(con)}
