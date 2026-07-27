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
      same SHARED rung both pairs   -> SHARED_SEED_CANDIDATE (tag + dtype + cell),
                                       with the raw-bit signature (ULP delta +
                                       direction) recorded. Only adjudicate_verified
                                       promotes it, and only to PASS_MECHANISM.
"""
from __future__ import annotations

import os
import struct
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import g33_evidence_validate as gev  # noqa: E402
import g33_mechanism as mech         # noqa: E402
import g33_replay as replay          # noqa: E402
import g33_schema as schema          # noqa: E402

# The PURE comparator answers "where do they first differ", so its best outcome is a
# CANDIDATE: both pairs first diverged at the same shared rung. Promoting that
# additionally requires ladder fidelity, branch/domain validity, four-way
# same-problem identity and external attestation — only adjudicate_verified() has
# seen those, and even it stops at PASS_MECHANISM.
SHARED_SEED_CANDIDATE = "SHARED_SEED_CANDIDATE"
SEED_VERDICTS = (SHARED_SEED_CANDIDATE, "FAIL", "INCONCLUSIVE", "INVALID_EVIDENCE")
#: The strongest verdict this tool can reach. It certifies the MECHANISM question —
#: the observed Fortran<->C++ difference did not originate in conservative-only
#: arithmetic — on the fixture at hand. It is deliberately NOT called PASS: the
#: protocol's PASS additionally requires the seed to be causally connected to the
#: historical output divergence and to propagate downstream, neither of which a
#: synthetic fixture can establish. That promotion is the owner's, not the tool's.
PASS_MECHANISM = "PASS_MECHANISM"
VERDICTS = (PASS_MECHANISM, "FAIL", "INCONCLUSIVE", "INVALID_EVIDENCE")
_ALGOS = ("legacy", "conservative")
_STAGES = ("outer_pre_sed", "substep_pre", "surface", "final_output")
_LOOP_LAST = 1 << 30      # sorts a whole-step record after every loop
_PRESED = ("outer_pre_sed", "substep_pre")
# Canonical execution order within one outer loop: the pre-sed snapshot, then each
# CHAIN's full substep sequence (chain is the OUTER loop, n the inner — matching the
# schedule), then the surface accumulation. Encoded as the leading order fields
# (loop, major, chain_rank, n, phase, ...).
_CHAIN_RANK = {"-": 0, "main": 1, "ice": 2}
_WIDTH = {"f32": 32, "f64": 64, "i32": 32, "u8": 8}


def _lane_of(identity) -> gev.LaneKey:
    """The LaneKey of an op identity — destructured by NAME so a change to the
    identity layout cannot silently produce a wrong lane key."""
    _kind, loop, chain, n, col = identity[:5]
    return gev.LaneKey(loop, chain, n, col)


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
    policy: str | None = None    # MechanismSpec.inactive relation (ops only)


def _int(v, what):
    """Accept a genuine int only — reject bool and any float (int(1.9)->1, int(True)
    ->1 would silently coerce structurally-wrong evidence)."""
    if isinstance(v, bool) or not isinstance(v, int):
        raise StructuralError(f"{what} must be an int, got {v!r}")
    return v


def _bits(v, dt):
    b = _int(v, "bits")
    if dt not in _WIDTH:
        raise StructuralError(f"unknown dtype {dt!r}")
    if b < 0 or b >= (1 << _WIDTH[dt]):
        raise StructuralError(f"bits {v!r} out of range for dtype {dt}")
    return b


def _events(run) -> list[Event]:
    try:
        algo = run["algorithm"]
        if algo not in _ALGOS:
            raise StructuralError(f"unknown algorithm {algo!r}")
        B, K = _int(run["B"], "B"), _int(run["K"], "K")
        if B < 1 or K < 2:
            raise StructuralError(f"degenerate B={B} K={K}")
        out: list[Event] = []
        for o in run["ops"]:
            role, sp, op_id, fld, dt = (o["role"], o["species"], o["op_id"],
                                        o["field"], o["dtype"])
            col, k, n = _int(o["col"], "col"), _int(o["k"], "k"), _int(o["n"], "n")
            if not (1 <= col <= B):
                raise StructuralError(f"op col {col} out of 1..{B}")
            if not (0 <= k < K):
                raise StructuralError(f"op k {k} out of 0..{K - 1}")
            if n < 1:
                raise StructuralError(f"op n {n} < 1")
            if role != schema.cell_role(k, K):
                raise StructuralError(f"op role {role} != cell_role({k},{K})")
            try:
                sr = schema.species_rank(sp)
                oo = schema.op_ordinal(algo, role, sp, op_id)
                fo = schema.field_ordinal(algo, role, op_id, fld)
                want_dt = schema.field_dtype(algo, role, op_id, fld)
            except (KeyError, ValueError, NotImplementedError) as e:
                raise StructuralError(f"op not in schema: {op_id}.{fld} [{role}/{sp}]") from e
            if dt != want_dt:
                raise StructuralError(f"dtype {op_id}.{fld}: got {dt} want {want_dt}")
            spec = mech.mechanism(algo, role, sp, op_id, fld)
            loop, chain = _int(o["loop"], "loop"), o["chain"]
            if loop < 1 or chain not in _CHAIN_RANK:
                raise StructuralError(f"bad op loop/chain {loop}/{chain!r}")
            out.append(Event(
                order=(loop, 1, _CHAIN_RANK[chain], n, 1, k, sr, oo, fo, col),
                phase="op",
                identity=("op", loop, chain, n, col, k, role, sp, op_id, fld, dt),
                shared_key=("op", loop, chain, n, col, k, role, sp, spec.tag, dt),
                kind=spec.kind, tag=spec.tag, dtype=dt, bits=_bits(o["bits"], dt),
                policy=spec.inactive))
        for s in run["stages"]:
            stage, fld, dt = s["stage"], s["field"], s["dtype"]
            if stage not in _STAGES:
                raise StructuralError(f"unknown stage {stage!r}")
            col, k, n = _int(s["col"], "col"), _int(s["k"], "k"), _int(s["n"], "n")
            loop, chain = _int(s["loop"], "loop"), s["chain"]
            # final_output is the whole-step result: loop 0 marks "not loop-scoped",
            # so its identity does not depend on how many loops the run took.
            lo_min = 0 if stage == "final_output" else 1
            if loop < lo_min or chain not in _CHAIN_RANK:
                raise StructuralError(f"bad stage loop/chain {loop}/{chain!r}")
            if not (1 <= col <= B):
                raise StructuralError(f"stage col {col} out of 1..{B}")
            try:                                  # rejects unknown field AND dtype
                want_dt = schema.semantic_stage_field_dtype(stage, fld)
            except KeyError as e:
                raise StructuralError(f"unknown {stage} field {fld!r}") from e
            if dt != want_dt:
                raise StructuralError(f"stage dtype {stage}.{fld}: got {dt} want {want_dt}")
            fo = schema.stage_field_ordinal(stage, fld)
            if stage in ("surface", "final_output"):
                if n != 0 or k != -1:
                    raise StructuralError(f"{stage} must have n=0 k=-1, got n={n} k={k}")
                spec = mech.surface_mechanism(fld)
                final = stage == "final_output"
                if final and loop != 0:
                    raise StructuralError(f"final_output must have loop=0, got {loop}")
                out.append(Event(
                    # a whole-step output sorts after every loop's surface records
                    order=((_LOOP_LAST if final else loop), (3 if final else 2),
                           0, 0, 0, 0, 0, 0, fo, col),
                    phase=stage,
                    identity=(stage, loop, n, col, k, fld, dt),
                    shared_key=(stage, loop, col, spec.tag, dt),
                    kind=spec.kind, tag=spec.tag, dtype=dt, bits=_bits(s["bits"], dt)))
            else:                                 # outer_pre_sed | substep_pre(n)
                if not (k == -1 or 0 <= k < K):
                    raise StructuralError(f"{stage} k {k} out of -1..{K - 1}")
                if stage == "outer_pre_sed" and n != 0:
                    raise StructuralError(f"outer_pre_sed must have n=0, got {n}")
                if stage == "substep_pre" and n < 1:
                    raise StructuralError(f"substep_pre must have n>=1, got {n}")
                major = 0 if stage == "outer_pre_sed" else 1
                out.append(Event(
                    order=(loop, major, _CHAIN_RANK[chain], n, 0, k, 0, 0, fo, col),
                    phase=stage,
                    identity=(stage, loop, chain, n, col, k, fld, dt),
                    shared_key=None, kind=None, tag=None, dtype=dt,
                    bits=_bits(s["bits"], dt)))
    except (KeyError, TypeError, ValueError, IndexError, NotImplementedError) as e:
        # P0-6: any malformed normalized record is INVALID_EVIDENCE, not a crash.
        raise StructuralError(f"malformed normalized run: {e!r}") from e
    out.sort(key=lambda e: e.order)
    ids = [e.identity for e in out]
    if len(ids) != len(set(ids)):
        raise StructuralError("duplicate record identity")
    return out


def _mono(bits, w):
    """IEEE bit pattern -> order-preserving unsigned int (Dawson transform)."""
    msb = 1 << (w - 1)
    return (~bits & ((1 << w) - 1)) if (bits & msb) else (bits | msb)


def _signature(dt, f_bits, c_bits):
    """Raw-bit divergence signature for the result — direction + ULP distance."""
    sig = {"dtype": dt, "f_bits": f"{f_bits:#x}", "c_bits": f"{c_bits:#x}",
           "xor": f"{f_bits ^ c_bits:#x}"}
    w = {"f32": 32, "f64": 64}.get(dt)        # ULP ordering is float-only
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
    inactive_diffs: tuple = ()   # op diffs in gate-inactive lanes (diagnostics only)


def _gate_defining(e) -> bool:
    """A substep_pre gate/mstep event — the pair that DEFINES which op records exist."""
    return e.phase == "substep_pre" and e.identity[6] in ("gate", "mstep")


def compare_pair(f_run, c_run) -> Divergence:
    """First Fortran↔C++ divergence for one variant, in canonical event order.

    The two producers have different op topologies (Fortran emits ACTIVE columns
    only; C++ writes whole [B] payloads), and a legitimately different mstep makes
    even the ACTIVE universes differ. So the comparison is bounded rather than
    global:

      1. Each run's own gate contract is validated independently.
      2. The gate/mstep sub-stream — which DEFINES the op universe — is compared
         first to find the earliest point where the two runs stop describing the
         same set of records. Everything before that point is comparable.
      3. Inside that comparable prefix the events are walked in true INTERLEAVED
         execution order, so a divergence born in an n=1 op is still attributed to
         that op and not to a later stage.
      4. Only ACTIVE-lane ops enter the verdict stream. An inactive lane's rungs are
         already pinned to their no-op values by the gate contract, so they are
         diagnostics, never the first divergence.
    """
    try:
        fe, ce = _events(f_run), _events(c_run)
    except StructuralError as e:
        return Divergence(invalid=str(e))
    try:
        f_active = gev.validate_gate_semantics(f_run, mech)
        gev.validate_gate_semantics(c_run, mech)
    except gev.GateSemanticsError as e:
        return Divergence(invalid=f"gate semantics: {e}")

    fmap, cmap = {e.identity: e for e in fe}, {e.identity: e for e in ce}
    # (2) the gate/mstep universe itself must match — both producers emit one per
    # lane, so a difference here is malformed evidence, not a physics difference.
    # (2) A different mstep means a different NUMBER of substeps, so the gate/mstep
    # records themselves need not cover the same set — each run emits its own range.
    # The earliest disagreement is therefore either a differing value on a shared
    # record, or a record only one run has at all; both are upstream differences.
    f_gate = {e.identity: e for e in fe if _gate_defining(e)}
    c_gate = {e.identity: e for e in ce if _gate_defining(e)}
    disagreements = [(e.order, e, c_gate[i].bits)
                     for i, e in f_gate.items()
                     if i in c_gate and e.bits != c_gate[i].bits]
    disagreements += [((f_gate.get(i) or c_gate[i]).order, f_gate.get(i) or c_gate[i], None)
                      for i in set(f_gate) ^ set(c_gate)]
    cutoff = cut_ev = cut_other = None
    if disagreements:
        cutoff, cut_ev, cut_other = min(disagreements, key=lambda t: t[0])

    def _in_scope(e):
        if cutoff is not None and e.order >= cutoff:
            return False
        if e.phase != "op":
            return True
        return f_active.get(_lane_of(e.identity), True)     # ACTIVE ops only

    f_scope = [e for e in fe if _in_scope(e)]
    c_ids = {e.identity for e in ce if _in_scope(e)}
    f_ids = {e.identity for e in f_scope}
    if f_ids != c_ids:
        fo, co = len(f_ids - c_ids), len(c_ids - f_ids)
        return Divergence(invalid=f"record identity universe differs "
                          f"(F-only {fo}, C-only {co})")

    # `.get` not `[]`: with the runs supplied in the other order the second run may
    # not carry that inactive identity at all (its producer emits active lanes only),
    # and the comparator must not raise on a shape it is designed to tolerate.
    inactive = [e.identity for e in fe
                if e.phase == "op" and not f_active.get(_lane_of(e.identity), True)
                and (o := cmap.get(e.identity)) is not None and e.bits != o.bits
                ] if not cutoff else []
    for e in f_scope:                                  # canonical interleaved order
        ce_e = cmap[e.identity]
        if e.bits != ce_e.bits:
            return Divergence(phase=e.phase, identity=e.identity,
                              shared_key=e.shared_key, kind=e.kind, tag=e.tag,
                              signature=_signature(e.dtype, e.bits, ce_e.bits),
                              inactive_diffs=tuple(inactive))
    if cut_ev is not None:
        # the comparable prefix is clean, so the earliest real difference is the
        # gate/mstep itself — an upstream CFL / fall-speed difference. (No signature
        # when the record exists in only one run: there is nothing to subtract.)
        sig = (_signature(cut_ev.dtype, cut_ev.bits, cut_other)
               if cut_other is not None else None)
        return Divergence(phase=cut_ev.phase, identity=cut_ev.identity,
                          shared_key=cut_ev.shared_key, kind=cut_ev.kind,
                          tag=cut_ev.tag, signature=sig,
                          inactive_diffs=tuple(inactive))
    return Divergence(inactive_diffs=tuple(inactive))   # no active divergence


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
        return SHARED_SEED_CANDIDATE, (
            f"both pairs first-diverge at the shared mechanism {legacy.tag} "
            f"{legacy.shared_key} — common to both variants (a PASS candidate: "
            f"promotion also needs fidelity, identity and attestation)")
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
                "kind": x.kind, "tag": x.tag, "signature": x.signature,
                "inactive_lane_diffs": len(x.inactive_diffs)}
    return {"verdict": verdict, "reason": reason,
            "legacy_first_divergence": _d(leg),
            "conservative_first_divergence": _d(con)}


def adjudicate_verified(legacy_f, legacy_c, conservative_f, conservative_c):
    """DECISION entry point — use this, not adjudicate(), for a C4 verdict.

    `adjudicate()` is pure verdict logic over four already-trusted runs. It answers
    "where do they first differ", not "is this evidence real". This wrapper adds the
    checks a decision needs before that question is even meaningful, starting with
    LADDER FIDELITY: each run's dumped rungs must equal a recomputation from its own
    operands (g33_replay). Without it a COMMONLY-wrong instrumentation shadow — the
    same wrong expression emitted by both variants of one backend — would appear as a
    shared-mechanism first divergence and could read as PASS.

    Attestation of the four legs (VerifiedFortranLeg / same-problem preflight) is the
    remaining piece and lands with the CLI; until then this promotes nothing on its
    own, it only refuses evidence that is not self-consistent."""
    legs = (("legacy-F", legacy_f), ("legacy-C++", legacy_c),
            ("conservative-F", conservative_f), ("conservative-C++", conservative_c))
    def _invalid(reason):
        return {"verdict": "INVALID_EVIDENCE", "reason": reason,
                "legacy_first_divergence": None, "conservative_first_divergence": None}

    # FOUR-WAY SAME PROBLEM: all four legs must describe one problem. Comparing
    # legs built from different fixtures or parameters would be a category error,
    # not a mechanism finding.
    ids = {name: run.get("problem") for name, run in legs}
    if any(v is None for v in ids.values()):
        missing = sorted(n for n, v in ids.items() if v is None)
        return _invalid(f"legs without a problem identity: {missing}")
    distinct = {tuple(sorted(v.items())) for v in ids.values()}
    if len(distinct) != 1:
        return _invalid(f"the four legs do not describe the same problem: {ids}")

    for name, run in legs:
        try:
            replay.replay_run(run)
        except (replay.FidelityError, KeyError, TypeError, ValueError) as e:
            return _invalid(f"{name} ladder fidelity: {e}")
    result = adjudicate(legacy_f, legacy_c, conservative_f, conservative_c)
    if result["verdict"] == SHARED_SEED_CANDIDATE:
        # Every gate above has passed, so the candidate may be promoted — but only
        # to the MECHANISM tier. What is still missing is not a check that could be
        # added here; it is evidence a synthetic fixture cannot contain.
        result["verdict"] = PASS_MECHANISM
        result["reason"] = ("PASS_MECHANISM (promoted from a shared seed): "
                            + result["reason"])
        result["evidence_strength"] = "PARTIAL"
        result["not_established"] = [
            "the seed is causally connected to the historical output divergence",
            "the difference propagates downstream through qv/t to the final state",
            "the mechanism is the one the historical Gate-B failure exhibited",
        ]
    result["problem"] = dict(ids["legacy-F"])
    return result
