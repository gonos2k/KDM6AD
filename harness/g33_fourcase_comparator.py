#!/usr/bin/env python3
"""G3.3-M four-case tri-state comparator — the verdict core.

Consumes FOUR normalized runs — legacy-F, legacy-C++, conservative-F,
conservative-C++ — and adjudicates whether the observed Fortran↔C++ difference
originated in conservative-only arithmetic. This module is the pure verdict
logic; the bundle readers (Fortran run_fortran_abc bundle + C++ run_cpp_abc
bundle) normalize into the record form below and are wired in separately, so the
adjudication is unit-testable without the heavy builds.

Normalized run form (one per backend/variant):
  ops:    {scalar_seq_id: (op_id, field, cell_role, k, species, dtype, bits)}
          scalar_seq_id = op_seq_id * B + (col-1)  — op_seq OUTER, column INNER,
          the single cross-tree total order both trees scalarize to.
  stages: {(stage, n, field, k, col): bits}  — the pre-sed / substep_pre / surface
          snapshots, already lane-expanded to match across trees.

Verdict taxonomy (structural errors are kept OUT of INCONCLUSIVE):
  INVALID_EVIDENCE — the two runs do not describe the same record universe.
  INCONCLUSIVE     — a pre-sed / substep_pre divergence (upstream / fall-speed /
                     gating), or no cross-tree divergence to attribute, or the two
                     pairs diverge at different ops.
  FAIL             — the conservative pair first diverges at a conservative-only
                     (ρΔz / no-clamp) operation absent from the legacy ladder.
  PASS             — both pairs first diverge at the SAME shared operation.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import g33_schema as schema  # noqa: E402

VERDICTS = ("PASS", "FAIL", "INCONCLUSIVE", "INVALID_EVIDENCE")
# pre-sed stages: a first divergence here cannot be attributed to sedimentation.
_PRESED_STAGES = ("outer_pre_sed", "substep_pre")


def conservative_only_ops():
    """(op_id, field) present in the conservative ladder but NOT the legacy one —
    the ρΔz transfer, the actual-outflow-rate accumulator, the dropped clamp."""
    def fields(algo):
        return {(op, f) for role in ("TOP", "INTERIOR", "BOTTOM")
                for sp in ("qr", "nr")
                for op in schema.ops_for_species(algo, role, sp)
                for f, _ in schema.op_fields(algo, role, op)}
    return fields("conservative") - fields("legacy")


@dataclass(frozen=True)
class PairDivergence:
    """The first Fortran↔C++ divergence within one variant pair."""
    invalid: str | None = None          # structural mismatch -> INVALID_EVIDENCE
    stage: tuple | None = None          # first pre-sed/substep_pre mismatch key
    op: tuple | None = None             # (scalar_seq, op_id, field, cell_role, k, species)


def _stage_sort_key(key):
    stage, n, field, k, col = key
    order = {"outer_pre_sed": 0, "substep_pre": 1, "surface": 2}.get(stage, 9)
    return (order, n, col, k, field)


def compare_pair(f_run, c_run) -> PairDivergence:
    """First Fortran↔C++ divergence for one variant, pre-sed stages before ops."""
    fs, cs = f_run["stages"], c_run["stages"]
    if set(fs) != set(cs):
        return PairDivergence(invalid=f"stage universe differs "
                              f"(F-only {len(set(fs)-set(cs))}, C-only {len(set(cs)-set(fs))})")
    fo, co = f_run["ops"], c_run["ops"]
    if set(fo) != set(co):
        return PairDivergence(invalid=f"op universe differs "
                              f"(F-only {len(set(fo)-set(co))}, C-only {len(set(co)-set(fo))})")

    # pre-sed / substep_pre first, in canonical stage order.
    for key in sorted(fs, key=_stage_sort_key):
        if key[0] in _PRESED_STAGES and fs[key] != cs[key]:
            return PairDivergence(stage=key)
    # then the op ladder, in scalar_seq order.
    for seq in sorted(fo):
        if fo[seq] != co[seq]:
            op_id, field, role, k, species, _dtype, _bits = fo[seq]
            return PairDivergence(op=(seq, op_id, field, role, k, species))
    return PairDivergence()          # bit-identical


def classify(legacy: PairDivergence, conservative: PairDivergence):
    """(verdict, reason). See the module docstring for the taxonomy."""
    if legacy.invalid:
        return "INVALID_EVIDENCE", f"legacy pair: {legacy.invalid}"
    if conservative.invalid:
        return "INVALID_EVIDENCE", f"conservative pair: {conservative.invalid}"
    if legacy.stage:
        return "INCONCLUSIVE", f"legacy pre-sed divergence at {legacy.stage}"
    if conservative.stage:
        return "INCONCLUSIVE", f"conservative pre-sed divergence at {conservative.stage}"

    lo, co = legacy.op, conservative.op
    if lo is None and co is None:
        return "INCONCLUSIVE", ("no cross-tree divergence in either pair — backends "
                                "bit-identical at this fixture (mstep=1 does not "
                                "exercise the multi-sub-cycle drift)")
    cons_only = conservative_only_ops()
    if co is not None and (co[1], co[2]) in cons_only:
        return "FAIL", (f"conservative pair first-diverges at conservative-only "
                        f"{co[1]}.{co[2]} (scalar_seq {co[0]}) — a ρΔz/no-clamp op "
                        f"absent from the legacy ladder")
    if lo is not None and co is not None and lo[:3] == co[:3]:
        return "PASS", (f"both pairs first-diverge at the shared op {lo[1]}.{lo[2]} "
                        f"(scalar_seq {lo[0]}) — a mechanism common to both variants")
    return "INCONCLUSIVE", (f"the two pairs diverge at different ops: "
                            f"legacy {lo}, conservative {co}")


def adjudicate(legacy_f, legacy_c, conservative_f, conservative_c):
    """Full four-case adjudication -> {verdict, reason, legacy, conservative}."""
    leg = compare_pair(legacy_f, legacy_c)
    con = compare_pair(conservative_f, conservative_c)
    verdict, reason = classify(leg, con)
    return {"verdict": verdict, "reason": reason,
            "legacy_first_divergence": {"stage": leg.stage, "op": leg.op, "invalid": leg.invalid},
            "conservative_first_divergence": {"stage": con.stage, "op": con.op, "invalid": con.invalid}}
