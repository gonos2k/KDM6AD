#!/usr/bin/env python3
"""G3.3-M four-case tri-state comparator — the verdict core.

Given the four normalized runs (legacy-F/legacy-C++/conservative-F/conservative-
C++), adjudicate whether the observed Fortran↔C++ difference originated in
conservative-only arithmetic. This is the pure verdict logic over a canonical
EVENT STREAM; the bundle readers that produce the normalized runs are wired in
separately (g33_bundle_io/g33_normalize).

Normalized run (one per backend/variant):
  {"algorithm": "legacy"|"conservative",
   "ops":    [ {n,col,k,role,species,op_id,field,dtype,bits,op_seq_id}, ... ],
   "stages": [ {stage,n,col,k,field,dtype,bits}, ... ]}   # stage incl. surface
  op_seq_id is the UNIQUE per-record total-order index (Fortran scalar_seq_id =
  schema op_seq_id · B + column); it is cross-checked for monotonicity in the
  schema-canonical order, never used to define that order.

Design contract (owner P0 closeout):
  * Canonical execution order is re-derived from the SCHEMA ordinals, never
    trusted from the producer's op_seq_id (that field is only cross-checked for
    consistency, then discarded). Order = outer_pre_sed, then per substep n
    [substep_pre(n) BEFORE ops(n)], then surface — so a divergence born in an n=1
    op is not misattributed to the substep_pre(n=2) it later perturbs.
  * Comparison is IDENTITY-FIRST: a differing / DUPLICATED record identity is
    INVALID_EVIDENCE, not a numerical divergence.
  * Attribution uses the role/species/expression-aware MechanismSpec.kind
    (g33_mechanism), not a field-set difference:
      - input carry differs first          -> INVALID_EVIDENCE (inconsistent)
      - pre-sed / out-of-scope species      -> INCONCLUSIVE
      - conservative-only arithmetic        -> FAIL
      - same SHARED rung in BOTH pairs      -> PASS  (aligned on the
        variant-independent mechanism tag AND dtype/rounding domain)
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import g33_mechanism as mech  # noqa: E402
import g33_schema as schema    # noqa: E402

VERDICTS = ("PASS", "FAIL", "INCONCLUSIVE", "INVALID_EVIDENCE")
_ALGOS = ("legacy", "conservative")
_STAGES = ("outer_pre_sed", "substep_pre", "surface")
_PRESED = ("outer_pre_sed", "substep_pre")
# Species rank in the authoritative schedule (g33_expectation _CHAIN_SPECIES:
# main [qr,nr,qs,qg,brs] then ice [qi,ni]) — the total op order within a substep
# is (k, species, op_ordinal, field_ordinal) with the column lane innermost.
_SPECIES_RANK = {s: i for i, s in enumerate(
    ["qr", "nr", "qs", "qg", "brs", "qi", "ni"])}
# Explicit surface field order (P0-9): per-species operands, then the shared
# species sum, then the shared metric inputs — NOT alphabetic.
_SURFACE_ORDER = ["bottom_fall_qr", "bottom_fall_qs", "bottom_fall_qg",
                  "bottom_fall_qi", "bottom_fall_total", "delz_bottom",
                  "surface_denr"]
_SURFACE_N = 10 ** 9          # order surface after every substep


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
    bits: int
    seq: int | None     # producer op_seq_id — cross-checked, not authoritative


def _events(run) -> list[Event]:
    algo = run.get("algorithm")
    if algo not in _ALGOS:
        raise StructuralError(f"unknown algorithm {algo!r}")
    out: list[Event] = []
    for o in run["ops"]:
        role, sp, op_id, fld = o["role"], o["species"], o["op_id"], o["field"]
        try:
            oo = schema.op_ordinal(algo, role, sp, op_id)
            fo = schema.field_ordinal(algo, role, op_id, fld)
            want_dt = schema.field_dtype(algo, role, op_id, fld)
        except (KeyError, ValueError) as e:
            raise StructuralError(f"op not in schema: {op_id}.{fld} [{role}/{sp}]") from e
        if o["dtype"] != want_dt:
            raise StructuralError(
                f"dtype mismatch {op_id}.{fld}: got {o['dtype']} want {want_dt}")
        if sp not in _SPECIES_RANK:
            raise StructuralError(f"unknown species {sp!r}")
        spec = mech.mechanism(algo, role, sp, op_id, fld)
        # schema-canonical total order: (n, k, species, op, field, col) — col inner.
        out.append(Event(
            order=(o["n"], 1, o["k"], _SPECIES_RANK[sp], oo, fo, o["col"]),
            phase="op",
            identity=("op", o["n"], o["col"], o["k"], role, sp, op_id, fld, o["dtype"]),
            shared_key=("op", o["n"], o["col"], o["k"], role, sp, spec.tag, o["dtype"]),
            kind=spec.kind, tag=spec.tag, bits=o["bits"], seq=o["op_seq_id"]))
    for s in run["stages"]:
        stage, fld = s["stage"], s["field"]
        if stage not in _STAGES:
            raise StructuralError(f"unknown stage {stage!r}")
        if stage == "surface":
            fo = _SURFACE_ORDER.index(fld) if fld in _SURFACE_ORDER else len(_SURFACE_ORDER)
            spec = mech.surface_mechanism(fld)
            out.append(Event(
                order=(_SURFACE_N, 0, 0, 0, 0, fo, s["col"]),   # after every substep
                phase="surface",
                identity=("surface", s["n"], s["col"], s["k"], fld, s["dtype"]),
                shared_key=("surface", s["col"], spec.tag, s["dtype"]),
                kind=spec.kind, tag=spec.tag, bits=s["bits"], seq=None))
        else:                                     # outer_pre_sed | substep_pre(n)
            n = 0 if stage == "outer_pre_sed" else s["n"]   # outer_pre_sed precedes n=1
            out.append(Event(
                order=(n, 0, s["k"], 0, 0, 0, s["col"]),     # phase 0 < ops (phase 1)
                phase=stage,
                identity=(stage, s["n"], s["col"], s["k"], fld, s["dtype"]),
                shared_key=None, kind=None, tag=None, bits=s["bits"], seq=None))
    out.sort(key=lambda e: e.order)
    # P0-4 duplicate identity — the dict-of-identity build below would silently
    # coalesce them, hiding a missing/extra record.
    ids = [e.identity for e in out]
    if len(ids) != len(set(ids)):
        raise StructuralError("duplicate record identity")
    # P0-5 the unique per-record op_seq_id must be strictly increasing in the
    # schema-canonical order derived above; a producer that renumbers records
    # inconsistently is rejected, not trusted to define the order.
    seqs = [e.seq for e in out if e.phase == "op"]
    if any(a >= b for a, b in zip(seqs, seqs[1:])):
        raise StructuralError("op_seq_id inconsistent with schema-canonical order")
    return out


@dataclass(frozen=True)
class Divergence:
    invalid: str | None = None
    phase: str | None = None
    identity: tuple | None = None
    shared_key: tuple | None = None
    kind: str | None = None
    tag: str | None = None


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
        if e.bits != cmap[e.identity].bits:
            return Divergence(phase=e.phase, identity=e.identity,
                              shared_key=e.shared_key, kind=e.kind, tag=e.tag)
    return Divergence()                           # bit-identical


def classify(legacy: Divergence, conservative: Divergence):
    """(verdict, reason). Evidence-integrity outranks any numerical verdict."""
    pairs = (("legacy", legacy), ("conservative", conservative))
    # 1. structural evidence failure in EITHER pair.
    for name, d in pairs:
        if d.invalid:
            return "INVALID_EVIDENCE", f"{name} pair: {d.invalid}"
    # 2. an input/carry differing FIRST means upstream matched but a carry did
    #    not — the evidence is internally inconsistent, not a mechanism verdict.
    for name, d in pairs:
        if d.kind == mech.INPUT:
            return "INVALID_EVIDENCE", (f"{name} pair: carry/input {d.tag} "
                                        f"{d.identity} differs while its source matched")
    # 3. a pre-sed divergence cannot be attributed to sedimentation arithmetic.
    for name, d in pairs:
        if d.phase in _PRESED:
            return "INCONCLUSIVE", f"{name} divergence upstream at {d.phase} {d.identity}"
    # 4. an out-of-scope species (snow/ice/graupel) has no qr/nr provenance here.
    for name, d in pairs:
        if d.kind == mech.OUT_OF_SCOPE:
            return "INCONCLUSIVE", (f"{name} first-diverges at out-of-scope {d.tag} "
                                    f"{d.identity} — upstream provenance not instrumented")
    # 5. conservative pair first-diverges in genuinely conservative-only arithmetic.
    if conservative.kind == mech.CONSERVATIVE:
        return "FAIL", (f"conservative pair first-diverges at {conservative.tag} "
                        f"{conservative.identity} — arithmetic absent from the legacy ladder")
    # 6. neither pair diverged.
    if legacy.phase is None and conservative.phase is None:
        return "INCONCLUSIVE", "no cross-tree divergence in either pair at this fixture"
    # 7. both pairs first-diverge at the SAME shared rung (tag + dtype + cell).
    if (legacy.kind == mech.SHARED and conservative.kind == mech.SHARED
            and legacy.shared_key is not None
            and legacy.shared_key == conservative.shared_key):
        return "PASS", (f"both pairs first-diverge at the shared mechanism {legacy.tag} "
                        f"{legacy.shared_key} — common to both variants")
    return "INCONCLUSIVE", (f"pairs diverge differently: legacy {legacy.phase}/"
                            f"{legacy.tag}/{legacy.shared_key}, conservative "
                            f"{conservative.phase}/{conservative.tag}/{conservative.shared_key}")


def _require_algorithm(run, want, label):
    if run.get("algorithm") != want:
        raise StructuralError(f"{label} run algorithm is {run.get('algorithm')!r}, want {want!r}")


def adjudicate(legacy_f, legacy_c, conservative_f, conservative_c):
    try:                                          # P0-6 algorithm preflight
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
                "kind": x.kind, "tag": x.tag}
    return {"verdict": verdict, "reason": reason,
            "legacy_first_divergence": _d(leg),
            "conservative_first_divergence": _d(con)}
