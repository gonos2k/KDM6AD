#!/usr/bin/env python3
"""G3.3-M INDEPENDENT expectation-manifest generator (protocol §7b, §8a).

Completeness must NOT be the writer's self-report: a buggy writer that drops a
record AND under-reports its own count would pass. This module derives the EXACT
expected record-key set from the fixture + the KNOWN substep/re-slope schedule,
in the canonical total order (§8a), assigning each record a canonical `op_seq_id`.
The comparator requires  observed_keys == expected_keys  (the container's
header.record_count_expected is informational only).

The schedule is supplied as a declared descriptor computed by the harness
INDEPENDENTLY of the dump writer — NOT read back from the container. It encodes
the conditional re-slope: C++ main re-slope runs after every main substep, but
ICE re-slope runs only when `n < mstepmax_ice` (protocol §7b).

First scope (owner-mandated): qr/nr mass+number ladders + re-slope + outer
boundary. Widen only on INCONCLUSIVE.
"""
from __future__ import annotations

# ── op templates: (algorithm, cell_role, species) -> [op_id, ...] ────────────
# Mass and number are DISTINCT expression families (§3): falk_nr omits dend,
# dn_out has no /dend, dn_in is Delta-z only. Legacy TOP directly clamps (no
# separate outflow/inflow); conservative TOP computes dq_out first (no inflow).
def _mass_ops(algorithm: str, role: str) -> list[str]:
    if role == "TOP":
        # legacy TOP clamps directly (no outflow rung); conservative TOP caps first.
        return ["QR_FALK", "QR_FALLACC", "QR_UPDATE"] if algorithm == "legacy" \
            else ["QR_FALK", "QR_OUTFLOW", "QR_FALLACC", "QR_UPDATE"]
    # INTERIOR / BOTTOM
    return ["QR_FALK", "QR_OUTFLOW", "QR_FALLACC", "QR_INFLOW", "QR_UPDATE"]


def _number_ops(algorithm: str, role: str) -> list[str]:
    # MUST mirror _mass_ops' algorithm split: the conservative TOP number path
    # DOES compute an outflow (dn_out = min(falk_nr*dtcld, nr)), so omitting
    # NR_OUTFLOW here would let a dump that skips it match the manifest.
    if role == "TOP":
        return ["NR_FALK", "NR_FALLACC", "NR_UPDATE"] if algorithm == "legacy" \
            else ["NR_FALK", "NR_OUTFLOW", "NR_FALLACC", "NR_UPDATE"]
    return ["NR_FALK", "NR_OUTFLOW", "NR_FALLACC", "NR_INFLOW", "NR_UPDATE"]


# Fields per op — keyed by (algorithm, cell_role, op_id), because the field SET
# genuinely differs by role: legacy TOP clamps directly and therefore has NO
# inflow rung (so no q_plus_in_preclamp), while INTERIOR does.
#
# DTYPES ARE DERIVED FROM THE SOURCE CONTRACT, not guessed:
#   work1_qr / workn_qr are f64 (the f64-vt chain, sedimentation.cpp §34), and
#   mstep_col = clamp(...).to(w1_qr.dtype())  (runtime.cpp:495) is therefore ALSO
#   f64 — NOT the state f32. gate_col = (...).to(state dtype) is f32.
#   Torch promotion then gives: f32*f32->f32, f32*f64->f64, f64/f64->f64,
#   f64*f32->f64, and a C++ double SCALAR does not promote an f32 tensor.
# A disagreement with the writer surfaces as a fail-closed key mismatch.
def _op_fields(algorithm: str, role: str, op_id: str) -> list[tuple[str, str]]:
    if op_id == "QR_FALK":     # dend(f32)*q(f32) -> f32; *work1(f64) -> f64; /mstep(f64) -> f64
        return [("mul_dend_q", "f32"), ("mul_work1", "f64"), ("div_mstep", "f64"),
                ("falk_precast", "f64"), ("shadow_falk_f32", "f32"), ("falk_f32", "f32")]
    if op_id == "NR_FALK":     # number family omits dend: nr(f32)*workn(f64) -> f64
        return [("mul_workn", "f64"), ("div_mstep", "f64"),
                ("falk_precast", "f64"), ("shadow_falk_f32", "f32"), ("falk_f32", "f32")]
    # Outflow/inflow MUST expose every arithmetic rung, including the value that
    # enters the min() (…_pre_cap). Collapsing them to just the final result would
    # let an incomplete dump match the manifest and would make it impossible to say
    # WHICH rung first diverged — the exact failure P1-9 forbids.
    # cap_active / clamp_active are a 3-valued BRANCH enum, not a boolean:
    #   0 = LEFT_SELECTED, 1 = RIGHT_SELECTED, 2 = TIE.
    # A boolean hides the TIE case, where both backends yield the SAME value from
    # DIFFERENT branch semantics — precisely what a first-divergence gate must see.
    if op_id == "QR_OUTFLOW":         # min(falk*dtcld/dend_safe, q)   [both algorithms]
        return [("mul_dt", "f32"), ("outflow_pre_cap", "f32"),
                ("source_reservoir", "f32"), ("cap_active", "u8"), ("dq_out", "f32")]
    if op_id == "NR_OUTFLOW":         # min(falk_nr*dtcld, nr) — NO /dend for numbers
        return [("outflow_pre_cap", "f32"), ("source_reservoir", "f32"),
                ("cap_active", "u8"), ("dn_out", "f32")]
    if op_id == "QR_INFLOW":
        if algorithm == "conservative":
            # prev_out * (dend_safe_src*delz_RAW_src) / (dend_safe_dst*delz_SAFE_dst); no cap
            return [("prev_out", "f32"), ("dend_safe_src", "f32"), ("delz_raw_src", "f32"),
                    ("dend_safe_dst", "f32"), ("delz_safe_dst", "f32"),
                    ("src_metric", "f32"), ("dst_metric", "f32"),
                    ("mul_src", "f32"), ("inflow_final", "f32")]
        # legacy: min(stored_falk_prev*delz_RAW_src/delz_SAFE_dst*dtcld/dend_safe_dst, q[k-1])
        return [("stored_falk_prev", "f32"), ("delz_raw_src", "f32"),
                ("delz_safe_dst", "f32"), ("dend_safe_dst", "f32"),
                ("mul_delz_src", "f32"), ("div_delz_dst", "f32"), ("mul_dt", "f32"),
                ("inflow_pre_cap", "f32"), ("source_reservoir", "f32"),
                ("inflow_cap_active", "u8"), ("inflow_final", "f32")]
    if op_id == "NR_INFLOW":
        if algorithm == "conservative":   # prev_out_nr * delz_RAW_src / delz_SAFE_dst; no dtcld, no cap
            return [("prev_out_nr", "f32"), ("delz_raw_src", "f32"), ("delz_safe_dst", "f32"),
                    ("mul_delz_src", "f32"), ("inflow_final", "f32")]
        # legacy: min(stored_falk_nr_prev*delz_RAW_src/delz_SAFE_dst*dtcld, nr[k-1])
        return [("stored_falk_nr_prev", "f32"), ("delz_raw_src", "f32"),
                ("delz_safe_dst", "f32"), ("mul_delz_src", "f32"), ("div_delz_dst", "f32"),
                ("inflow_pre_cap", "f32"), ("source_reservoir", "f32"),
                ("inflow_cap_active", "u8"), ("inflow_final", "f32")]
    # §4 fall accumulator — REQUIRED to trace qr seed -> rain_increment as an op
    # path. Legacy adds the RAW stored falk; conservative adds the ACTUAL capped
    # outflow RATE (dq_out*dend_safe/dtcld). Omitting this let a dump that skips
    # the accumulator match the manifest.
    if op_id == "QR_FALLACC":
        if algorithm == "conservative":
            return [("fall_before", "f32"), ("dq_out", "f32"), ("mul_dend_safe", "f32"),
                    ("fall_increment", "f32"), ("fall_after", "f32")]
        return [("fall_before", "f32"), ("fall_increment", "f32"), ("fall_after", "f32")]
    if op_id == "NR_FALLACC":
        if algorithm == "conservative":          # fall_nr += dn_out/dtcld
            return [("fall_before", "f32"), ("dn_out", "f32"),
                    ("fall_increment", "f32"), ("fall_after", "f32")]
        return [("fall_before", "f32"), ("fall_increment", "f32"), ("fall_after", "f32")]
    if op_id == "QR_UPDATE":
        f = [("q_before", "f32"), ("q_minus_out", "f32")]
        if role != "TOP":
            f.append(("q_plus_in_preclamp", "f32"))
        if algorithm == "legacy":
            f.append(("clamp_active", "u8"))      # conservative has NO positivity clamp
        return f + [("q_post", "f32")]
    if op_id == "NR_UPDATE":
        f = [("n_before", "f32"), ("n_minus_out", "f32")]
        if role != "TOP":
            f.append(("n_plus_in_preclamp", "f32"))
        if algorithm == "legacy":
            f.append(("clamp_active", "u8"))
        return f + [("n_post", "f32")]
    raise KeyError(op_id)

# Stage fields are (name, dtype, shape_kind) with shape_kind "BK" (whole field)
# or "B" (per-column). substep_pre is WHOLE-K: the final max cell can sit at an
# interior level, so a TOP-only snapshot could show equal inputs there while
# work1_qr had already diverged at k=3 — and the gate would misattribute the
# seed to `falk`.
_STAGE_FIELDS_BASE = {
    "outer_pre_sed":   [("qr", "f32", "BK"), ("nr", "f32", "BK"), ("qv", "f32", "BK"),
                        ("th", "f32", "BK"), ("rho", "f32", "BK"), ("delz", "f32", "BK")],
    "outer_post_sed":  [("qr", "f32", "BK"), ("nr", "f32", "BK"), ("qv", "f32", "BK"),
                        ("th", "f32", "BK")],
    "outer_post_micro": [("qr", "f32", "BK"), ("nr", "f32", "BK"), ("qv", "f32", "BK"),
                        ("th", "f32", "BK")],
    # substep_pre is WHOLE-K, emitted once per substep (k=-1). Three fields the
    # protocol names are NOT here, each for a stated reason rather than omission:
    #   mstepmax_i32 (§55) — BLOCKED, needs owner adjudication. The value only
    #     exists as `int /*mstepmax*/`, an UNNAMED parameter of
    #     substep_advection_torch. Naming it is a production edit and changes the
    #     macro-OFF projection, breaking the textual-identity guarantee. It cannot
    #     be dumped under the current freeze.
    #   gate_mask, finite_required_mask (§236/§237) — the protocol attaches these
    #     to EACH OP RECORD (the dead-branch/NaN policy is per-operation), not to
    #     the substep entry state. Demanding them here made the manifest
    #     unsatisfiable while still not covering the ops they belong to.
    # Its dtypes
    # are the DECLARED source-contract model: work1/workn are f64 (the f64-vt
    # chain), and mstep_native is therefore ALSO f64 — mstep_col is built as
    # clamp(...).to(w1_qr.dtype()) (runtime.cpp:495), NOT the state f32; only
    # gate_native is state-dtype f32 (gate_col = (...).to(state dtype)). The first
    # diagnostic run VALIDATES this model: a dtype/shape disagreement with the
    # writer surfaces as a fail-closed key mismatch — never a silent pass.
    "substep_pre":     [("qr", "f32", "BK"), ("nr", "f32", "BK"),
                        ("work1_qr", "f64", "BK"), ("workn_qr", "f64", "BK"),
                        ("dend_raw", "f32", "BK"), ("dend_safe", "f32", "BK"),
                        ("dend_floor_active", "u8", "BK"),
                        ("delz_raw", "f32", "BK"), ("delz_safe", "f32", "BK"),
                        ("delz_floor_active", "u8", "BK"),
                        # per-column: mstep/gate are level-independent
                        ("mstep_native", "NATIVE_MSTEP", "B"),
                        ("mstep_decoded_i32", "i32", "B"),
                        ("mstep_exact_integer", "u8", "B"),
                        ("gate_native", "NATIVE_GATE", "B"),
                        ("gate_decoded_u8", "u8", "B"),
                        ("gate_exact_01", "u8", "B"),
                        ("active_mask", "u8", "B")],
    "substep_post":    [("qr", "f32", "BK"), ("nr", "f32", "BK"), ("qs", "f32", "BK"),
                        ("qg", "f32", "BK"), ("brs", "f32", "BK")],
    "reslope_input":   [("qr", "f32", "BK"), ("nr", "f32", "BK")],
    "reslope_output":  [("work1_qr", "f64", "BK"), ("workn_qr", "f64", "BK")],
    # §4 surface diagnostic — emitted once per outer loop after the main+ice
    # chains (surface_accumulation_torch). Without it the qr-seed -> precip
    # divergence can only be asserted by cell-set inclusion, not shown as an op path.
    "surface":         [("bottom_fall", "f32", "B"), ("delz_bottom", "f32", "B"),
                        ("surface_mul1", "f32", "B"), ("surface_mul_dt", "f32", "B"),
                        ("rain_increment", "f32", "B"), ("snow_increment", "f32", "B"),
                        ("graupel_increment", "f32", "B")],
}

# Backend-specific NATIVE dtypes (P0-5). The C++ path carries mstep as the f64
# work1 dtype and gate as state f32; a Fortran reference carries an INTEGER mstep
# and a LOGICAL gate. Forcing one contract on both would either corrupt the
# evidence (casting native values) or fail forever (expectation mismatch).
# Cross-tree comparison therefore uses the SEMANTIC fields
# (mstep_decoded_i32 / mstep_exact_integer / gate_decoded_u8); the native bits are
# retained for per-backend provenance only.
_NATIVE = {
    "cpp":     {"NATIVE_MSTEP": "f64", "NATIVE_GATE": "f32"},
    "fortran": {"NATIVE_MSTEP": "i32", "NATIVE_GATE": "u8"},
}

# Fields whose cross-tree comparison is semantic, not raw-bit.
SEMANTIC_CROSS_TREE_FIELDS = ("mstep_decoded_i32", "mstep_exact_integer",
                              "gate_decoded_u8", "gate_exact_01")


def _stage_fields(stage: str, backend: str):
    """Stage fields with NATIVE_* resolved for this backend."""
    nat = _NATIVE[backend]
    return [(f, nat.get(d, d), k) for f, d, k in _STAGE_FIELDS_BASE[stage]]


# Which species each chain ACTUALLY transports. substep_advection_* carries
# qr/nr/qs/qg/brs; ice_substep_advection_* carries ONLY qi/ni. Demanding QR_*/NR_*
# records on the ice chain would require operations that do not exist, so the
# completeness check could never be satisfied — and an unsatisfiable check is a
# useless one.
_CHAIN_SPECIES = {"main": ["qr", "nr", "qs", "qg", "brs"], "ice": ["qi", "ni"]}


def _ops_for_species(algorithm: str, role: str, species: str) -> list[str]:
    if species == "qr":
        return _mass_ops(algorithm, role)
    if species == "nr":
        return _number_ops(algorithm, role)
    # qs/qg/brs/qi/ni are outside the owner-mandated first scope; fail loudly
    # rather than emit plausible-looking but wrong op ids.
    raise NotImplementedError(
        f"species {species!r} is outside the first scope (qr/nr); add its op "
        f"templates before widening species_scope")


def _cell_role(k: int, K: int) -> str:
    # canonical top-first: k=0 is TOP, k=K-1 is BOTTOM
    if k == 0:
        return "TOP"
    if k == K - 1:
        return "BOTTOM"
    return "INTERIOR"


def expected_records(schedule: dict) -> list[dict]:
    """Return the ordered expected record keys for one (case, pair, backend).

    schedule keys: case_id, pair_id, backend, algorithm(legacy|conservative),
    B, K, loops, mstepmax_main[loops], mstepmax_ice[loops],
    species_scope(subset of {qr,nr}). op_seq_id is the canonical index.
    """
    # Fail LOUD on a malformed schedule. _mass_ops/_number_ops treat anything that
    # is not "legacy" as conservative, so a typo like "conservatve" would have
    # silently produced a conservative manifest.
    algo = schedule["algorithm"]
    if algo not in ("legacy", "conservative"):
        raise ValueError(f"algorithm must be 'legacy' or 'conservative', got {algo!r}")
    backend = schedule["backend"]
    if backend not in _NATIVE:
        raise ValueError(f"backend must be one of {sorted(_NATIVE)}, got {backend!r}")
    B, K = int(schedule["B"]), int(schedule["K"])
    loops = int(schedule["loops"])
    mm_main = schedule["mstepmax_main"]
    mm_ice = schedule["mstepmax_ice"]
    if loops < 1 or B < 1 or K < 2:
        raise ValueError(f"degenerate schedule loops={loops} B={B} K={K} (K>=2 so TOP != BOTTOM)")
    for nm, mm in (("mstepmax_main", mm_main), ("mstepmax_ice", mm_ice)):
        if len(mm) != loops:
            raise ValueError(f"{nm} has {len(mm)} entries, expected loops={loops}")
        if any(int(x) < 1 for x in mm):
            raise ValueError(f"{nm} contains a value < 1: {list(mm)}")
    species = list(schedule.get("species_scope", ["qr", "nr"]))
    # A malformed scope must FAIL, never silently shrink the manifest: skipping a
    # chain whose in-scope species list is empty is correct for ice, but if the
    # scope itself is empty or misspelled the SAME skip drops the main chain too,
    # leaving a manifest with no op records — under which an empty dump reads as
    # "complete" and the whole op check is disabled. Fail-open, not fail-closed.
    known = {s for v in _CHAIN_SPECIES.values() for s in v}
    if not species:
        raise ValueError("species_scope is empty — refusing to emit a manifest "
                         "that would vacuously accept a dump with no op records")
    unknown = sorted(set(species) - known)
    if unknown:
        raise ValueError(f"species_scope contains unknown species {unknown}; "
                         f"known: {sorted(known)}")
    base = {"case_id": schedule["case_id"], "pair_id": schedule["pair_id"],
            "backend": schedule["backend"]}
    recs: list[dict] = []

    def emit(stage, fields, *, outer_loop, chain="-", n=0, cell_role="-",
             species_id="-", op_id="-", k=-1, shape=None):
        # `k` is the CANONICAL level index and is part of the record identity.
        # Without it, cell_role alone (TOP/INTERIOR/BOTTOM) makes every interior
        # level k=1..K-2 collide: for K>=4 the manifest would expect the same key
        # more than once, so a dump that emits one interior cell twice and skips
        # another still matches the multiset — and a comparator pairing C++ vs
        # Fortran records by key could pair k=1 against k=2. Protocol §8a puts
        # canonical_k in the total order for exactly this reason.
        # k = -1 means "not a per-level record" (whole-field or per-column stages).
        for spec in fields:
            if len(spec) == 3:                      # stage field: shape kind given
                field, dtype, kind = spec
                shp = [B, K] if kind == "BK" else [B]
            else:                                   # op field: always per-column
                field, dtype = spec
                shp = list(shape) if shape else [B]
            recs.append({**base, "seq_no": len(recs), "op_seq_id": len(recs),
                         "outer_loop": outer_loop, "chain": chain, "n": n,
                         "cell_role": cell_role, "k": k, "species": species_id,
                         "op_id": op_id, "stage": stage, "field": field,
                         "dtype": dtype, "shape": shp})

    for loop in range(1, loops + 1):
        emit("outer_pre_sed", _stage_fields("outer_pre_sed", backend), outer_loop=loop, shape=[B, K])
        for chain, mmax_list in (("main", mm_main), ("ice", mm_ice)):
            # A chain transporting no in-scope species contributes NOTHING: its
            # substep_pre/post and re-slope fields are chain-specific too (ice
            # uses work1_qi/workn_qi, not work1_qr), so emitting them here would
            # again demand records that cannot exist. The ice re-slope conditional
            # below stays implemented for when ice enters scope.
            if not [s for s in _CHAIN_SPECIES[chain] if s in species]:
                continue
            mmax = int(mmax_list[loop - 1])
            for n in range(1, mmax + 1):
                # per-level (B,) slices captured at the top cell (matches the overlay)
                # WHOLE-K: per-level fields are [B,K]; mstep/gate are [B]
                emit("substep_pre", _stage_fields("substep_pre", backend), outer_loop=loop,
                     chain=chain, n=n)
                # only the species this chain actually transports, intersected
                # with the requested scope (ice carries qi/ni, never qr/nr)
                chain_species = [s for s in _CHAIN_SPECIES[chain] if s in species]
                for k in range(K):
                    role = _cell_role(k, K)
                    for sp in chain_species:
                        ops = _ops_for_species(algo, role, sp)
                        for op_id in ops:
                            emit("op", _op_fields(algo, role, op_id), outer_loop=loop, chain=chain,
                                 n=n, cell_role=role, k=k, species_id=sp, op_id=op_id,
                                 shape=[B])
                emit("substep_post", _stage_fields("substep_post", backend), outer_loop=loop,
                     chain=chain, n=n, shape=[B, K])
                # conditional re-slope: main after every substep; ice only n<mstepmax_ice
                if chain == "main" or n < mmax:
                    emit("reslope_input", _stage_fields("reslope_input", backend), outer_loop=loop,
                         chain=chain, n=n, shape=[B, K])
                    emit("reslope_output", _stage_fields("reslope_output", backend), outer_loop=loop,
                         chain=chain, n=n, shape=[B, K])
        # surface accumulation runs once per outer loop, after main+ice chains
        emit("surface", _stage_fields("surface", backend), outer_loop=loop, shape=[B])
        emit("outer_post_sed", _stage_fields("outer_post_sed", backend), outer_loop=loop, shape=[B, K])
        emit("outer_post_micro", _stage_fields("outer_post_micro", backend), outer_loop=loop, shape=[B, K])
    # INSTRUMENTED SCOPE. op_seq_id is a MEASURED process-global counter, and it
    # only counts records the overlay actually emits. Numbering the manifest over
    # stages that are not instrumented yet therefore offsets every declared window
    # past the measured values: with substep-only instrumentation the first real
    # record measures 0 while its container declares [6, N], so the writer rejects
    # it and the real overlay can never produce a valid container.
    #
    # The scope is DECLARED, never defaulted. "all stages" as a silent default is
    # what produced the offset; "whatever the dump contains" as a silent default
    # would let the manifest shrink to fit a truncated dump — the failure this
    # whole manifest exists to prevent. An explicit list makes the evidence say
    # which stages it is complete WITH RESPECT TO.
    inst = schedule.get("instrumented_stages")
    if not isinstance(inst, (list, tuple)) or not inst:
        raise ValueError(
            "schedule must declare instrumented_stages (a non-empty list of stage "
            "names); there is no safe default — see the offset failure above")
    inst = set(inst)
    present = {r["stage"] for r in recs}
    unknown = inst - present
    if unknown:
        raise ValueError(f"instrumented_stages names unknown stage(s): {sorted(unknown)} "
                         f"(known: {sorted(present)})")
    recs = [r for r in recs if r["stage"] in inst]
    for i, r in enumerate(recs):
        r["seq_no"] = i
        r["op_seq_id"] = i

    # Belt-and-suspenders against a vacuous gate: a manifest with no op records
    # would accept any dump that also has none. If we ever get here with zero,
    # the schedule (loops / mstepmax / scope) is degenerate — refuse it.
    if not any(r["stage"] == "op" for r in recs):
        raise ValueError("manifest contains no op records — a dump with no ops "
                         "would vacuously 'match'; check loops/mstepmax/species_scope")
    # EVERY expected key must be unique. If two records share a key the multiset
    # comparison cannot tell a legitimate second occurrence from a duplicate that
    # replaced a missing one — e.g. before `k` joined the identity, all interior
    # levels collided and a dump could emit k=1 twice, never touch k=2, and still
    # read as complete. Enforce it here so any future identity gap fails loudly.
    from collections import Counter as _C
    _dupes = {k: v for k, v in _C(record_key(r) for r in recs).items() if v > 1}
    if _dupes:
        raise ValueError(
            f"{len(_dupes)} expected key(s) are not unique — the record identity "
            f"cannot distinguish these records, so completeness checking is unsound. "
            f"example: {next(iter(_dupes))}")
    return recs


# The stages the C++ sedimentation overlay emits TODAY. Outer-loop, surface and
# re-slope stages are protocol steps 4/8 and are not instrumented yet. This is a
# declaration of current scope, not of the protocol's target scope: a run_index
# built over stages nothing emits offsets every declared op_seq window past the
# measured counter, and the real overlay can then never produce a valid
# container. test_overlay_stage_scope_matches_the_source pins it to the source.
CPP_OVERLAY_STAGES = ("substep_pre", "op")


def container_id(rec: dict) -> str:
    """The container a record belongs to.

    Outer-loop stages are split PRE/POST rather than sharing one container: the
    substeps run between them, so a single outer container would span an op_seq
    range that ENCLOSES the substep containers. Overlapping ranges make the
    header's global_op_seq_start/end unfalsifiable — a record misfiled from a
    substep into the outer container would still satisfy the range check. Split
    this way every container is contiguous by construction.
    """
    if rec["chain"] == "-":
        side = "pre" if rec["stage"] == "outer_pre_sed" else "post"
        return f"L{rec['outer_loop']}_outer_{side}"
    return f"L{rec['outer_loop']}_{rec['chain']}_n{rec['n']}"


def run_index(schedule: dict) -> dict:
    """INDEPENDENT top-level index of the exact container set, fixed BEFORE the run.

    The protocol described one container per (case, backend); the overlay actually
    writes one per (case, pair, backend, outer_loop, chain, n) because the COMPLETE
    footer may only be written by an explicit finalize() inside the substep. Both
    are workable, but with the two descriptions disagreeing neither completeness
    nor canonical order is well defined. This resolves it in favour of the
    implementation and adds the missing piece: an index that pins the container
    SET and each container's op_seq range, so a container that never appears is a
    detectable absence rather than a silent one.
    """
    recs = expected_records(schedule)
    groups: dict = {}
    for r in recs:
        groups.setdefault(container_id(r), []).append(r)
    containers = []
    for cid, rs in groups.items():
        osi = [r["op_seq_id"] for r in rs]
        containers.append({
            "container_id": cid,
            "outer_loop": rs[0]["outer_loop"],
            "chain": rs[0]["chain"],
            "n": rs[0]["n"],
            "first_op_seq_id": min(osi),
            "last_op_seq_id": max(osi),
            "record_count": len(rs),
            "path": f"{schedule['backend']}_{schedule['algorithm']}_"
                    f"{schedule['case_id']}_{cid}.g33",
        })
    containers.sort(key=lambda c: c["first_op_seq_id"])
    # every container must be a CONTIGUOUS op_seq block, and the blocks must tile
    # [0, total-1] exactly — no gap, no overlap.
    cursor = 0
    for c in containers:
        span = c["last_op_seq_id"] - c["first_op_seq_id"] + 1
        if span != c["record_count"]:
            raise ValueError(
                f"container {c['container_id']} is not contiguous: span {span} "
                f"!= {c['record_count']} records")
        if c["first_op_seq_id"] != cursor:
            raise ValueError(
                f"container {c['container_id']} starts at {c['first_op_seq_id']}, "
                f"expected {cursor} (gap or overlap in the op_seq tiling)")
        cursor = c["last_op_seq_id"] + 1
    if cursor != len(recs):
        raise ValueError(f"containers cover {cursor} ops, expected {len(recs)}")
    return {"case_id": schedule["case_id"], "pair_id": schedule["pair_id"],
            "backend": schedule["backend"], "algorithm": schedule["algorithm"],
            "total_records": len(recs),
            "global_op_seq_start": 0, "global_op_seq_end": len(recs) - 1,
            "containers": containers}


def op_seq_map(index: dict) -> str:
    """KDM6_G33_OP_SEQ_MAP for the overlay: "cid:first:last,...".

    The overlay reads its own container's declared window from this instead of
    computing one, so a container that executes out of order emits measured
    op_seq_ids outside its declared window and the reader rejects it.
    """
    return ",".join(f"{c['container_id']}:{c['first_op_seq_id']}:{c['last_op_seq_id']}"
                    for c in index["containers"])


def record_key(rec: dict) -> tuple:
    """The identity tuple used for observed==expected set comparison (payload-free)."""
    return (rec["case_id"], rec["pair_id"], rec["backend"], rec.get("op_seq_id", -1),
            rec["outer_loop"], rec["chain"], rec["n"], rec["cell_role"],
            rec.get("k", -1), rec["species"], rec["op_id"], rec["stage"],
            rec["field"], rec["dtype"], tuple(rec["shape"]))


def expected_key_set(schedule: dict) -> set:
    return {record_key(r) for r in expected_records(schedule)}


def expected_key_counts(schedule: dict) -> "Counter":
    """Expected MULTIPLICITY of every key (every key is expected exactly once)."""
    from collections import Counter
    return Counter(record_key(r) for r in expected_records(schedule))


def completeness_diff(observed_records, schedule: dict) -> dict:
    """Fail-closed completeness verdict as a MULTISET comparison.

    A set comparison is duplicate-BLIND: two records carrying the same key (e.g.
    the surface stage emitted once per chain instead of once per outer loop)
    collapse into one element and the check passes. The container reader only
    rejects duplicate seq_no, which such records need not share. So completeness
    must compare counts, not membership.

    Returns {'missing', 'extra', 'duplicated'} as Counters; the run is complete
    iff all three are empty.
    """
    from collections import Counter
    exp = expected_key_counts(schedule)
    obs = Counter(record_key(r) for r in observed_records)
    missing = Counter({k: exp[k] - obs.get(k, 0) for k in exp if obs.get(k, 0) < exp[k]})
    extra = Counter({k: c for k, c in obs.items() if k not in exp})
    duplicated = Counter({k: obs[k] - exp[k] for k in exp if obs.get(k, 0) > exp[k]})
    return {"missing": missing, "extra": extra, "duplicated": duplicated}
