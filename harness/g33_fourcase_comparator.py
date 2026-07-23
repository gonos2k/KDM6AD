#!/usr/bin/env python3
"""G3.3-M four-case tri-state comparator — the verdict core (owner P0-3..7).

Given the four normalized runs (legacy-F/legacy-C++/conservative-F/conservative-
C++), adjudicate whether the observed Fortran↔C++ difference originated in
conservative-only arithmetic. This is the pure verdict logic over a canonical
EVENT STREAM; the bundle readers that produce the normalized runs are wired in
separately (g33_bundle_io/g33_normalize).

Normalized run (one per backend/variant):
  {"algorithm": "legacy"|"conservative",
   "ops":    [ {n,col,k,role,species,op_id,field,dtype,bits,op_seq_id}, ... ],
   "stages": [ {stage,n,col,k,field,dtype,bits}, ... ]}   # stage incl. surface

The events are ordered by ACTUAL execution — outer_pre_sed, then per substep n
substep_pre(n) BEFORE ops(n), then surface — so a divergence born in an n=1 op is
NOT misattributed to the substep_pre(n=2) it later perturbs (P0-3). Comparison is
IDENTITY-FIRST: a differing record identity is INVALID_EVIDENCE, not a numerical
divergence (P0-6). PASS aligns on the VARIANT-INDEPENDENT logical identity of a
SHARED mechanism rung, not a per-variant numeric ordinal (P0-4). Attribution uses
explicit mechanism tags (P0-5), not a field-set difference.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import g33_mechanism as mech  # noqa: E402

VERDICTS = ("PASS", "FAIL", "INCONCLUSIVE", "INVALID_EVIDENCE")
_PRESED = ("outer_pre_sed", "substep_pre")
_SURFACE_N = 10 ** 9          # order surface after every substep


@dataclass(frozen=True)
class Event:
    order: tuple        # canonical execution order
    phase: str          # outer_pre_sed | substep_pre | op | surface
    identity: tuple     # WITHIN-pair match key (F vs C++, same variant) incl. dtype
    shared_key: tuple   # VARIANT-INDEPENDENT logical identity (for cross-pair PASS)
    mechanism: str | None
    bits: int


def _events(run) -> list[Event]:
    algo = run["algorithm"]
    out: list[Event] = []
    for o in run["ops"]:
        ident = ("op", o["n"], o["col"], o["k"], o["role"], o["species"],
                 o["op_id"], o["field"], o["dtype"])
        out.append(Event(
            order=(o["n"], 1, o["op_seq_id"], o["col"], 0, ""),
            phase="op",
            identity=ident,
            shared_key=("op", o["n"], o["col"], o["k"], o["role"], o["species"],
                        o["op_id"], o["field"]),
            mechanism=mech.mechanism(algo, o["op_id"], o["field"]),
            bits=o["bits"]))
    for s in run["stages"]:
        if s["stage"] == "surface":
            order = (_SURFACE_N, 0, 0, s["col"], 0, s["field"])
            m = mech.surface_mechanism(s["field"])
        elif s["stage"] == "outer_pre_sed":
            order = (0, 0, 0, s["col"], s["k"], s["field"])
            m = None
        else:                                    # substep_pre(n)
            order = (s["n"], 0, 0, s["col"], s["k"], s["field"])
            m = None
        ident = (s["stage"], s["n"], s["col"], s["k"], s["field"], s["dtype"])
        out.append(Event(order=order, phase=s["stage"], identity=ident,
                          shared_key=ident[:-1], mechanism=m, bits=s["bits"]))
    out.sort(key=lambda e: e.order)
    return out


@dataclass(frozen=True)
class Divergence:
    invalid: str | None = None
    phase: str | None = None
    identity: tuple | None = None
    shared_key: tuple | None = None
    mechanism: str | None = None


def compare_pair(f_run, c_run) -> Divergence:
    """First Fortran↔C++ divergence for one variant, in canonical event order."""
    fe, ce = _events(f_run), _events(c_run)
    fmap = {e.identity: e for e in fe}
    cmap = {e.identity: e for e in ce}
    if set(fmap) != set(cmap):
        fo, co = len(set(fmap) - set(cmap)), len(set(cmap) - set(fmap))
        return Divergence(invalid=f"record identity universe differs "
                          f"(F-only {fo}, C-only {co})")
    for e in fe:                                  # canonical order
        if e.bits != cmap[e.identity].bits:
            return Divergence(phase=e.phase, identity=e.identity,
                              shared_key=e.shared_key, mechanism=e.mechanism)
    return Divergence()                           # bit-identical


def classify(legacy: Divergence, conservative: Divergence):
    """(verdict, reason). Structural errors stay OUT of INCONCLUSIVE."""
    if legacy.invalid:
        return "INVALID_EVIDENCE", f"legacy pair: {legacy.invalid}"
    if conservative.invalid:
        return "INVALID_EVIDENCE", f"conservative pair: {conservative.invalid}"
    # a pre-sed / substep_pre divergence cannot be attributed to sedimentation.
    for name, d in (("legacy", legacy), ("conservative", conservative)):
        if d.phase in _PRESED:
            return "INCONCLUSIVE", f"{name} divergence upstream at {d.phase} {d.identity}"

    lo, co = legacy.phase, conservative.phase
    if lo is None and co is None:
        return "INCONCLUSIVE", ("no cross-tree divergence in either pair — backends "
                                "bit-identical at this fixture (mstep=1 does not "
                                "exercise the multi-sub-cycle drift)")
    # conservative pair first-diverges in genuinely conservative-only arithmetic.
    if conservative.mechanism and mech.is_conservative_only(conservative.mechanism):
        return "FAIL", (f"conservative pair first-diverges at {conservative.mechanism} "
                        f"{conservative.identity} — arithmetic absent from the legacy "
                        f"ladder")
    # both pairs first-diverge at the SAME shared rung (variant-independent identity).
    if (legacy.shared_key is not None and legacy.shared_key == conservative.shared_key
            and legacy.mechanism and mech.is_shared(legacy.mechanism)
            and conservative.mechanism and mech.is_shared(conservative.mechanism)):
        return "PASS", (f"both pairs first-diverge at the shared mechanism "
                        f"{legacy.mechanism} {legacy.shared_key} — common to both variants")
    return "INCONCLUSIVE", (f"pairs diverge differently: legacy {legacy.phase}/"
                            f"{legacy.mechanism}/{legacy.shared_key}, conservative "
                            f"{conservative.phase}/{conservative.mechanism}/"
                            f"{conservative.shared_key}")


def adjudicate(legacy_f, legacy_c, conservative_f, conservative_c):
    leg = compare_pair(legacy_f, legacy_c)
    con = compare_pair(conservative_f, conservative_c)
    verdict, reason = classify(leg, con)

    def _d(x):
        return {"invalid": x.invalid, "phase": x.phase,
                "identity": x.identity, "mechanism": x.mechanism}
    return {"verdict": verdict, "reason": reason,
            "legacy_first_divergence": _d(leg),
            "conservative_first_divergence": _d(con)}
