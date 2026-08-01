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
from types import MappingProxyType

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import g33_activity as activity     # noqa: E402
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
#: What an unattested debug run may report at best. A separate name so a caller that
#: reads only the verdict cannot mistake it for a decision-grade result.
UNATTESTED_MECHANISM_CANDIDATE = "UNATTESTED_MECHANISM_CANDIDATE"
VERDICTS = (PASS_MECHANISM, "FAIL", "INCONCLUSIVE", "INVALID_EVIDENCE")
_ALGOS = ("legacy", "conservative")
_STAGES = ("kernel_call_input", "kernel_init_constants",
           "kernel_after_entry_clamp", "outer_pre_sed", "substep_pre", "surface",
           "final_output",
           "outer_post_sed", "micro_post_melt", "micro_freeze_heat",
           "micro_call_progb_aux",
           "micro_post_freeze", "micro_pre_state_update",
           "micro_qr_operands", "micro_post_state_update",
           "outer_post_micro")
#: Execution order WITHIN one outer loop. The two bridge snapshots sit after the
#: surface accumulation: outer_post_sed is the sedimentation result, outer_post_micro
#: is what the next loop starts from (owner P0-C1).
_STAGE_MAJOR = {"kernel_init_constants": 0, "kernel_call_input": 1,
                "kernel_after_entry_clamp": 2, "outer_pre_sed": 3,
                "substep_pre": 4, "surface": 5, "outer_post_sed": 6,
                "micro_post_melt": 7, "micro_freeze_heat": 8,
                "micro_call_progb_aux": 9, "micro_post_freeze": 10,
                "micro_pre_state_update": 11, "micro_qr_operands": 12,
                "micro_post_state_update": 13,
                "outer_post_micro": 14, "final_output": 15}
#: Where a shared seed may be promoted on the SEDIMENTATION identity alone.
#:
#: Only the op ladder. Every rung there is replayed from its own dumped operands, so
#: the causal inputs of the divergence are sealed by the evidence itself. Nothing else
#: is: `outer_pre_sed` and `substep_pre` are ENTRY snapshots, and a difference first
#: appearing at a snapshot says the state arriving at sedimentation already differed —
#: which is a statement about what produced that state, not about sedimentation. The
#: surface accumulation, the whole-step output and both bridge snapshots are full-step
#: claims whose preconditions include what runs between the sub-cycles.
#:
#: Widening this needs a per-field argument that the causal inputs are sealed, not a
#: judgement that the phase feels close enough to sedimentation (owner P0-8).
_SEDIMENTATION_PHASES = frozenset(("op",))

#: Whole-K snapshots taken once per outer loop (n=0), as opposed to per substep.
_OUTER_SNAPSHOTS = ("outer_pre_sed", "outer_post_sed", "outer_post_micro")
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


@dataclass(frozen=True)
class DecisionLeg:
    """One backend leg, with its normalized run derived from the artifact ITSELF.

    Built only by VerifiedFourCase.of(); no public path lets a caller supply the run.
    The previous carrier took the verified artifact and the normalized dict
    SEPARATELY, so a genuine leg could be paired with a run from another fixture — the
    artifact carried the attestation while the comparator read the dict, and nothing
    tied the two together (owner P0-4).
    """
    name: str
    verified: object                 # VerifiedCppLeg | VerifiedFortranLeg
    normalized: MappingProxyType     # derived here, read-only

    @property
    def verdict_ready(self) -> bool:
        return bool(getattr(self.verified, "verdict_ready", False))


def _deep_freeze(obj):
    """Read-only all the way down, so a paired run cannot be edited afterwards."""
    if isinstance(obj, dict):
        return MappingProxyType({k: _deep_freeze(v) for k, v in obj.items()})
    if isinstance(obj, (list, tuple)):
        return tuple(_deep_freeze(v) for v in obj)
    return obj


#: Handed to __init__ by of() and nothing else. A public dataclass constructor let a
#: caller assemble the object from legs it built itself, which is the whole thing the
#: factory exists to prevent — documenting of() as "the" path is not the same as
#: making it the only one.
_FACTORY_TOKEN = object()


@dataclass(frozen=True)
class VerifiedFourCase:
    """The four decision-grade legs, as one object.

    Constructing this is the ONLY way to obtain PASS_MECHANISM, and `of()` is the
    only way to construct it at all — the constructor refuses anyone else.
    """
    legacy_fortran: DecisionLeg
    legacy_cpp: DecisionLeg
    conservative_fortran: DecisionLeg
    conservative_cpp: DecisionLeg
    _token: object = None

    def __post_init__(self):
        if self._token is not _FACTORY_TOKEN:
            raise TypeError(
                "VerifiedFourCase is built by VerifiedFourCase.of(), which derives "
                "each run from its verified artifact and applies the cross-leg "
                "conditions — assembling one directly skips both")

    @classmethod
    def of(cls, *, legacy_fortran, legacy_cpp, conservative_fortran,
           conservative_cpp, gate_a_report=None,
           require_source_authorization: bool = False) -> "VerifiedFourCase":
        """Normalize each VERIFIED ARTIFACT here, deep-freeze it, and pair them.

        The caller hands over four verified legs and nothing else, so a forged event
        stream has nowhere to enter: the run is derived from the artifact whose
        attestation is being relied upon.
        """
        import g33_bundle_io as _bio
        import g33_fortran_bundle_io as _fbio
        import g33_normalize as _nz
        named = (("legacy-F", legacy_fortran, "legacy", _fbio.VerifiedFortranLeg),
                 ("legacy-C++", legacy_cpp, "legacy", _bio.VerifiedCppLeg),
                 ("conservative-F", conservative_fortran, "conservative",
                  _fbio.VerifiedFortranLeg),
                 ("conservative-C++", conservative_cpp, "conservative",
                  _bio.VerifiedCppLeg))
        legs = []
        for name, art, algo, want in named:
            # isinstance, not hasattr. Duck typing let anything carrying `.run` and
            # `verdict_ready=True` through — the attributes a stub has by accident are
            # exactly the ones a forgery would supply on purpose.
            if not isinstance(art, want):
                raise TypeError(
                    f"{name}: expected {want.__name__}, got {type(art).__name__} — "
                    f"the decision API derives the run from the artifact, so there is "
                    f"nowhere to pass one in")
            if want is _fbio.VerifiedFortranLeg:
                if art.run.algorithm != algo:
                    raise TypeError(f"{name}: leg is {art.run.algorithm!r}, not {algo!r}")
                run = _nz.from_fortran_run(art.run)
            else:
                if str(art.contract["schedule"].get("algorithm")) != algo:
                    raise TypeError(
                        f"{name}: leg is "
                        f"{art.contract['schedule'].get('algorithm')!r}, not {algo!r}")
                run = _nz.from_cpp_evidence(art)
            legs.append(DecisionLeg(name, art, _deep_freeze(run)))
        # CROSS-LEG conditions, inside the factory. They used to live only in the CLI,
        # so a library caller reaching of() directly skipped them entirely.
        pair = {"legacy": legacy_fortran, "conservative": conservative_fortran}
        if len({leg.build.toolchain() for leg in pair.values()}) != 1:
            raise TypeError(
                "the two Fortran control legs were not built from one toolchain")
        if gate_a_report is not None:
            _fbio.authorized_by_gate_a(gate_a_report, pair)
        elif require_source_authorization:
            raise TypeError(
                "a decision needs the Gate A scope report: excluding the variant "
                "module from the toolchain comparison is what lets the legs differ "
                "there, and allowing them to differ is not authorizing one")
        return cls(*legs, _token=_FACTORY_TOKEN)

    @property
    def legs(self):
        return tuple((leg.name, leg) for leg in
                     (self.legacy_fortran, self.legacy_cpp,
                      self.conservative_fortran, self.conservative_cpp))

    def unready(self) -> list:
        """Names of legs that are not decision-grade."""
        return [name for name, leg in self.legs if not leg.verdict_ready]

    def runs(self) -> tuple:
        return tuple(leg.normalized for _name, leg in self.legs)

    def mechanism_admissible(self) -> bool:
        """Whether this fixture may support a MECHANISM verdict (owner P0-8).

        Resolved from the fixture authority on disk by the `fixture_sha256` the legs
        themselves carry — not from a field on this object, which a caller could set.
        Fails closed: an unresolvable or disagreeing fixture is not admissible, because
        the alternative is promoting on a fixture nobody can look up.
        """
        import g33_fixture_v1 as gfx
        shas = {leg.normalized["problem"]["fixture_sha256"] for _n, leg in self.legs}
        if len(shas) != 1:
            return False
        want = shas.pop()
        for fixture_id in gfx.FIXTURES:
            try:
                _spec, authority = gfx.load_fixture(fixture_id)
            except Exception:                 # an unloadable entry decides nothing
                continue
            if gfx.fixture_sha256(authority) == want:
                return gfx.FIXTURES[fixture_id].mechanism_admissible
        return False


@dataclass(frozen=True)
class SedimentationIdentity:
    """What makes four legs comparable: one fixture, one common parameter set, one
    grid. Deliberately EXCLUDES parameters only one backend has — those are a
    full-step property, and holding all four legs to them would either fail always or
    force the value to be dropped (which is what used to happen)."""
    fixture_sha256: str
    parameter_sha256: str
    B: int
    K: int
    #: The comparison boundary. A wrapper leg and a kernel leg solve different
    #: problems — the wrapper additionally rewrites nccn from a height profile the
    #: C++ port does not have — so this belongs in the identity, not beside it.
    entry_boundary: str

    @classmethod
    def of(cls, problem: dict) -> "SedimentationIdentity":
        # NO DEFAULT (owner P0-9). Defaulting to the wrapper boundary meant two
        # malformed runs that BOTH omitted it were both read as wrapper legs and passed
        # the same-problem check — the field would have been declared and unenforced,
        # which is the failure mode the versioned ids exist to prevent. Support for
        # pre-boundary streams belongs in the parser (which does still default, since a
        # stream from before the kernel path was a wrapper run by construction), not in
        # the decision identity.
        if "entry_boundary" not in problem:
            raise StructuralError(
                "a leg's problem identity has no comparison boundary: a decision "
                "cannot assume which function the leg entered")
        return cls(problem["fixture_sha256"], problem["parameter_sha256"],
                   problem["B"], problem["K"], problem["entry_boundary"])


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
                # An op belongs to its substep, so it shares substep_pre's major and
                # sorts after it on the 5th field. Hardcoding the major here meant
                # renumbering _STAGE_MAJOR silently reordered ops relative to the
                # substep gate that scopes them.
                order=(loop, _STAGE_MAJOR["substep_pre"], _CHAIN_RANK[chain], n, 1,
                       k, sr, oo, fo, col),
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
            lo_min = 0 if stage in ("final_output", "kernel_call_input",
                                    "kernel_init_constants",
                                    "kernel_after_entry_clamp") else 1
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
                    order=((_LOOP_LAST if final else loop), _STAGE_MAJOR[stage],
                           0, 0, 0, 0, 0, 0, fo, col),
                    phase=stage,
                    identity=(stage, loop, n, col, k, fld, dt),
                    shared_key=(stage, loop, col, spec.tag, dt),
                    kind=spec.kind, tag=spec.tag, dtype=dt, bits=_bits(s["bits"], dt)))
            else:                                 # outer_pre_sed | substep_pre(n)
                if not (k == -1 or 0 <= k < K):
                    raise StructuralError(f"{stage} k {k} out of -1..{K - 1}")
                if stage in _OUTER_SNAPSHOTS and n != 0:
                    raise StructuralError(f"{stage} must have n=0, got {n}")
                if stage == "substep_pre" and n < 1:
                    raise StructuralError(f"substep_pre must have n>=1, got {n}")
                major = _STAGE_MAJOR[stage]
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
    """Raw-bit divergence signature for the result — direction + ULP distance.

    The magnitude is emitted TWICE, under names that say which is which. A single
    `ulp_delta` was read as a distance in one place and as a signed difference in
    another — the artifact carried -2281 while a finding table wrote it as +2281
    with a bare delta sign, and nothing in either said which convention applied.
    A quantity whose sign a reader has to infer is a quantity whose sign gets
    inferred wrong.
    """
    sig = {"dtype": dt, "f_bits": f"{f_bits:#x}", "c_bits": f"{c_bits:#x}",
           "xor": f"{f_bits ^ c_bits:#x}"}
    w = {"f32": 32, "f64": 64}.get(dt)        # ULP ordering is float-only
    if w:
        ulp = _mono(c_bits, w) - _mono(f_bits, w)
        sig["signed_ulp_delta"] = ulp          # ordered(C) - ordered(F)
        sig["ulp_distance_abs"] = abs(ulp)
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

    # Stage records the REFERENCE's arithmetic does not read at that cell. Same
    # treatment as a gate-inactive op lane: out of the verdict, into diagnostics.
    # The v14 gate named `xlf` at a 289 K cell with all three freeze rates zero —
    # a coefficient multiplied by zero — as its first divergence.
    noncausal = activity.noncausal_stage_records(f_run)

    def _in_scope(e):
        if cutoff is not None and e.order >= cutoff:
            return False
        if e.identity in noncausal:
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
                if (e.identity in noncausal
                    or (e.phase == "op"
                        and not f_active.get(_lane_of(e.identity), True)))
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
    # 2b. THE PREMISE, not a finding (owner P0-3). The same-problem preflight compares
    # fixture and parameter HASHES — what the two legs were configured with. It cannot
    # see what actually reached the kernel, which is the thing the wrapper rewrites.
    # A difference here says the two backends were handed different problems, so every
    # downstream comparison is a category error; it is an adapter or fixture defect,
    # never evidence about conservative-only arithmetic.
    for name, d in pairs:
        if d.phase in ("kernel_init_constants", "kernel_call_input",
                       "kernel_after_entry_clamp"):
            return "INVALID_EVIDENCE", (
                f"{name} legs entered kdm62D with different arguments at {d.identity} "
                f"— the comparison premise fails before any physics runs; this is an "
                f"adapter/fixture defect, not a mechanism finding")
    for name, d in pairs:                         # 3. upstream (pre-sed)
        if d.phase in _PRESED:
            return "INCONCLUSIVE", f"{name} divergence upstream at {d.phase} {d.identity}"
    # 3b. AFTER THE SEDIMENTATION OUTPUT (owner P0-C1, narrowed by owner P0-1.3). The
    # wording used to say "born AFTER sedimentation, in the microphysics", which is
    # stronger than the records: the 12 carried prognostics are not the whole input to the
    # microphysics, so
    #
    #     x_F == x_C   and   a_F != a_C   =>   M(x, a_F) != M(x, a_C)
    #
    # was consistent with everything observed, and the seed would then be in the auxiliary
    # calculation. `micro_call_progb_aux` records that bundle now, so the reason points at it
    # rather than asserting past it.
    #
    # The bridge makes this sayable at
    # all: before it, a difference born in loop L's microphysics first became visible
    # at loop L+1's pre-sed entry and was reported as "upstream at outer_pre_sed",
    # which named where it was SEEN rather than where it came from.
    #
    # Still INCONCLUSIVE, and deliberately so. That a divergence appeared after the
    # sedimentation result matched is evidence it did not come from conservative-only
    # arithmetic — but calling that a mechanism PASS is a C4 adjudication, which is
    # the owner's and not this tool's. What changes here is the attribution the
    # reason carries, not the tier.
    for name, d in pairs:
        if d.phase == "outer_post_micro":
            return "INCONCLUSIVE", (
                f"{name} first-diverges at {d.phase} {d.identity} — the sedimentation "
                f"OUTPUT, micro_call_progb_aux (the ProgB bundle, one of the six groups "
                f"the micro call receives) and micro_post_state_update all matched, "
                f"so this is the first OBSERVED difference and it appeared after the "
                f"two-branch state update and its ProgB brs re-clamp: in Picons/Nicons, "
                f"the saturation adjustment, or the final re-slope. The rate blocks, the "
                f"mass-conservation feedback and the state update itself are EXCLUDED by "
                f"micro_post_state_update. That narrows WHERE it was observed; whether "
                f"it ORIGINATED there is still a separate question, and attribution is "
                f"owner adjudication")
    # 3c. THE PRE-MICRO AUXILIARY (owner P0-4). Without a branch of its own this fell
    # through to the generic "pairs diverge differently", which names the phase and says
    # nothing about what it means — and what it means is specific: the ProgB bundle the
    # rates read already differs BEFORE any prognostic-state update, so the seed is
    # upstream of the microphysics arithmetic, not in it.
    #
    # It is placed after the post-micro branch deliberately: micro_call_progb_aux sorts EARLIER
    # in canonical order, so if it were the first divergence the post-micro branch could
    # not have matched, and ordering these two by source position rather than by phase
    # rank would make the reason depend on where the code sits.
    for name, d in pairs:
        # 3b'. THE BISECTION. Reached only when the ProgB bundle handed to the
        # microphysics matched, so the difference is inside the microphysics and on
        # the FIRST half of it: the warm and cold rate blocks, the mass-conservation
        # feedback, the two-branch state update, or the ProgB brs re-clamp. Picons,
        # the saturation adjustment and the final re-slope are excluded — they run
        # after this snapshot. That is a narrower statement than "in the
        # microphysics" and it is the reason this stage exists.
        if d.phase == "micro_post_state_update":
            return "INCONCLUSIVE", (
                f"{name} first-diverges at {d.phase} {d.identity} — the ProgB bundle "
                f"the rates read matched, and so did micro_qr_operands, the CLOSED "
                f"operand set of the qr update line; the difference is inside the "
                f"microphysics and BEFORE Picons/Nicons and the saturation "
                f"adjustment: in the summation itself, in another update line's "
                f"operands, the mass-conservation feedback, or the ProgB brs "
                f"re-clamp. This is NOT a statement about "
                f"conservative-only interface arithmetic; attribution is owner "
                f"adjudication")
        # 3b''. THE OPERANDS. Reached when the state at micro_post_state_update
        # matched but an operand of the qr update line did not — so the difference is
        # in whichever rate produced that operand, upstream of the update arithmetic.
        # The closed-set property is what makes the converse readable too: if this
        # stage matches and micro_post_state_update does not, the operands were equal
        # and the summation was not.
        if d.phase == "micro_qr_operands":
            return "INCONCLUSIVE", (
                f"{name} first-diverges at {d.phase} {d.identity} — an OPERAND of the "
                f"qr update line differs while the state entering the microphysics and "
                f"the ProgB bundle matched, so the difference is in the rate that "
                f"produced it, not in the update arithmetic. This is NOT a statement "
                f"about conservative-only interface arithmetic; attribution is owner "
                f"adjudication")
        # THE FREEZE HEAT OPERANDS. Reached when the post-melt state matched but
        # an operand of the three t-stores did not — so the difference is in
        # whichever rate produced it, upstream of the heat arithmetic.
        if d.phase == "micro_freeze_heat":
            return "INCONCLUSIVE", (
                f"{name} first-diverges at {d.phase} {d.identity} — an OPERAND of "
                f"the D2-D4 freeze heat term differs while the post-D1-melt state "
                f"matched, so the difference is in the rate or coefficient that "
                f"produced it, not in the t-store arithmetic. This is NOT a "
                f"statement about conservative-only interface arithmetic; "
                f"attribution is owner adjudication")
        # THE MELT-FREEZE CHAIN, split. v12 showed the seed is one field of the
        # update base (t, one ULP) acquired somewhere between outer_post_sed and
        # that base. These two snapshots say which half.
        if d.phase == "micro_post_freeze":
            return "INCONCLUSIVE", (
                f"{name} first-diverges at {d.phase} {d.identity} — the post-D1-melt "
                f"state matched, so the difference is in what runs between: the "
                f"post-melt re-slope, the D2-D4 freeze, or the post-freeze re-slope. "
                f"This is NOT a statement about conservative-only interface "
                f"arithmetic; attribution is owner adjudication")
        if d.phase == "micro_post_melt":
            return "INCONCLUSIVE", (
                f"{name} first-diverges at {d.phase} {d.identity} — the sedimentation "
                f"result matched and the state differs by the end of the D1 melt loop, "
                f"so the difference is in D1 melt or the homogeneous freeze that shares "
                f"it. This is NOT a statement about conservative-only interface "
                f"arithmetic; attribution is owner adjudication")
        # THE UPDATE BASE. Reached when the ProgB bundle matched but the state
        # state_update actually reads did not. That state is NOT outer_post_sed's:
        # D1 melt, homogeneous freeze, both re-slopes and the rate blocks run in
        # between. A difference here means the qr update line cannot be replayed
        # from equal inputs, whatever the rate operands do downstream — so it is
        # reported ahead of them rather than as one more differing quantity.
        if d.phase == "micro_pre_state_update":
            return "INCONCLUSIVE", (
                f"{name} first-diverges at {d.phase} {d.identity} — the BASE state "
                f"state_update reads differs, while the ProgB bundle and the "
                f"sedimentation result matched. What runs between them is D1 melt, "
                f"homogeneous freeze, the post-melt re-slope, D2-D4 freeze and the "
                f"post-freeze re-slope, and the difference is in one of those. The "
                f"rate operands downstream cannot be read as the cause while their "
                f"base differs. This is NOT a statement about conservative-only "
                f"interface arithmetic; attribution is owner adjudication")
        if d.phase == "micro_call_progb_aux":
            return "INCONCLUSIVE", (
                f"{name} first-diverges at {d.phase} {d.identity} — the ProgB auxiliary "
                f"entering the microphysics differs BEFORE any prognostic-state update, "
                f"so the seed is upstream of the microphysics arithmetic. This is NOT a "
                f"statement about conservative-only interface arithmetic; attribution is "
                f"owner adjudication")
        if d.phase == "outer_post_sed":
            return "INCONCLUSIVE", (
                f"{name} first-diverges at {d.phase} {d.identity} — the sedimentation "
                f"RESULT differs while every instrumented substep matched, so the "
                f"difference is in sedimentation but not on the recorded ladder")
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


def promotable_phase(phase) -> bool:
    """May a shared seed at `phase` be promoted on the SEDIMENTATION identity alone?

    Only inside sedimentation. Elsewhere — the surface accumulation, the whole-step
    output, either bridge snapshot — the seed is a claim about the FULL step, whose
    preconditions include everything that runs between the sub-cycles, and
    SedimentationIdentity does not establish those (owner P0-C2 §6).
    """
    # None is NOT promotable. A shared seed always HAS a phase, so a missing one is a
    # malformed result rather than a permissive case, and fail-open is the wrong
    # default at a decision boundary.
    return phase in _SEDIMENTATION_PHASES


def _adjudicate_normalized(legacy_f, legacy_c, conservative_f, conservative_c,
                           *, promote: bool):
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

    # SAME PROBLEM, AT TWO LEVELS (owner P0-C2). Comparing legs built from different
    # fixtures or parameters would be a category error, not a mechanism finding — but
    # "the same problem" is not one predicate:
    #
    #   SedimentationIdentity  the fixture, the common parameters and the grid. All
    #                          FOUR legs must share it; it is what makes them
    #                          comparable at all.
    #   FullStepIdentity       the above PLUS parameters only one backend has
    #                          (Fortran's ccn0/scale_h). Only the two legs of that
    #                          backend can be held to it.
    #
    # Flattening these into one dict forced a choice between dropping the local
    # parameters — which is what happened, so they were never checked anywhere — and
    # demanding C++ carry a hash of variables it does not have.
    ids = {name: run.get("problem") for name, run in legs}
    if any(v is None for v in ids.values()):
        missing = sorted(n for n, v in ids.items() if v is None)
        return _invalid(f"legs without a problem identity: {missing}")
    try:
        sed = {name: SedimentationIdentity.of(v) for name, v in ids.items()}
    except (KeyError, StructuralError) as e:
        # A missing key and a missing BOUNDARY are the same kind of fact about the
        # evidence, so both become INVALID_EVIDENCE. Letting the StructuralError
        # propagate would exit 6 (a harness defect) for something that is a defect in
        # the bundle.
        return _invalid(f"a leg's problem identity is unusable: {e}")
    if len(set(sed.values())) != 1:
        return _invalid(f"the four legs do not describe the same problem: {ids}")
    # ...and within one backend, the full-step preconditions must agree too.
    for backend, pair in (("F", ("legacy-F", "conservative-F")),
                          ("C++", ("legacy-C++", "conservative-C++"))):
        local = {n: (ids[n].get("local_parameter_sha256"),
                     ids[n].get("initialization_digest")) for n in pair}
        if len(set(local.values())) != 1:
            return _invalid(
                f"the two {backend} legs disagree on backend-local parameters, so "
                f"they are not the same full step: {local}")

    for name, run in legs:
        try:
            replay.replay_run(run)
        except (replay.FidelityError, KeyError, TypeError, ValueError) as e:
            return _invalid(f"{name} ladder fidelity: {e}")
    result = adjudicate(legacy_f, legacy_c, conservative_f, conservative_c)
    if result["verdict"] == SHARED_SEED_CANDIDATE and promote:
        # A seed OUTSIDE sedimentation is a statement about the whole step, and the
        # whole step's preconditions are not the sedimentation ones: what happens
        # between the sub-cycles enters it. Promoting such a seed on
        # SedimentationIdentity alone would claim more than the identity establishes.
        phase = (result.get("legacy_first_divergence") or {}).get("phase")
        if not promotable_phase(phase):
            # A refusal must not carry a promotion's words. The reason and the
            # evidence_strength used to be assigned OUTSIDE this branch, so an
            # INCONCLUSIVE verdict came back reading "PASS_MECHANISM (promoted from a
            # shared seed)" with evidence_strength PARTIAL — a result that contradicts
            # itself, and that any reader taking the reason at face value would
            # misread as a promotion.
            result["verdict"] = "INCONCLUSIVE"
            result["reason"] = (
                f"both pairs share a seed, but at {phase} — outside sedimentation, so "
                f"this is a FULL-STEP claim and the sedimentation identity does not "
                f"establish its preconditions: " + result["reason"])
            result["evidence_strength"] = "NONE"
        else:
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


def adjudicate_verified(evidence: VerifiedFourCase) -> dict:
    """THE decision entry point. Only a VerifiedFourCase can reach PASS_MECHANISM.

    Taking four plain dicts made the promotion reachable by any caller willing to
    build them, with the readiness check living in the CLI. A property enforced by
    convention at one call site is not a property of the system.
    """
    if not isinstance(evidence, VerifiedFourCase):
        raise TypeError(
            "adjudicate_verified requires a VerifiedFourCase — normalized dicts alone "
            "carry no attestation, and a verdict built from them would describe "
            "evidence nobody anchored")
    unready = evidence.unready()
    if unready:
        return {"verdict": "INVALID_EVIDENCE",
                "reason": f"legs that are not decision-grade: {unready}",
                "legacy_first_divergence": None,
                "conservative_first_divergence": None}
    # WHAT THE FIXTURE MAY DECIDE (owner P0-8). A structural probe like
    # boundary_mapping_v1 carries deliberately out-of-band prognostics to exercise code
    # paths; a mechanism verdict from it would be a claim about physics drawn from
    # values chosen to be unphysical. The fixture declares its ceiling and this is
    # where it binds — a declaration nothing reads stops nothing.
    return _adjudicate_normalized(*evidence.runs(),
                                  promote=evidence.mechanism_admissible())


def adjudicate_unattested(legacy_f, legacy_c, conservative_f, conservative_c) -> dict:
    """Numerics only, for debugging. Structurally cannot return PASS_MECHANISM.

    A shared seed here reports UNATTESTED_MECHANISM_CANDIDATE, so an automation that
    reads only the verdict string cannot mistake a debug run for a decision.
    """
    result = _adjudicate_normalized(legacy_f, legacy_c, conservative_f,
                                    conservative_c, promote=False)
    if result["verdict"] == SHARED_SEED_CANDIDATE:
        result["verdict"] = UNATTESTED_MECHANISM_CANDIDATE
    return result
