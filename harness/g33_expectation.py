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

# stage (non-op) snapshot fields.
_STAGE_FIELDS = {
    "outer_pre_sed":   [("qr", "f32"), ("nr", "f32"), ("qv", "f32"), ("th", "f32"),
                        ("rho", "f32"), ("delz", "f32")],
    "outer_post_sed":  [("qr", "f32"), ("nr", "f32"), ("qv", "f32"), ("th", "f32")],
    "outer_post_micro": [("qr", "f32"), ("nr", "f32"), ("qv", "f32"), ("th", "f32")],
    # substep_pre is emitted as per-level (B,) slices at the top cell. Its dtypes
    # are the DECLARED source-contract model: work1/workn are f64 (the f64-vt
    # chain), and mstep_native is therefore ALSO f64 — mstep_col is built as
    # clamp(...).to(w1_qr.dtype()) (runtime.cpp:495), NOT the state f32; only
    # gate_native is state-dtype f32 (gate_col = (...).to(state dtype)). The first
    # diagnostic run VALIDATES this model: a dtype/shape disagreement with the
    # writer surfaces as a fail-closed key mismatch — never a silent pass.
    "substep_pre":     [("work1_qr", "f64"), ("workn_qr", "f64"),
                        ("mstep_native", "f64"), ("mstep_decoded_i32", "i32"),
                        ("mstep_exact_integer", "u8"),
                        ("gate_native", "f32"), ("gate_exact_01", "u8"),
                        ("active_mask", "u8"),
                        ("dend_raw", "f32"), ("dend_safe", "f32"),
                        ("delz_raw", "f32"), ("delz_safe", "f32")],
    "substep_post":    [("qr", "f32"), ("nr", "f32"), ("qs", "f32"), ("qg", "f32"), ("brs", "f32")],
    "reslope_input":   [("qr", "f32"), ("nr", "f32")],
    "reslope_output":  [("work1_qr", "f64"), ("workn_qr", "f64")],
    # §4 surface diagnostic — emitted once per outer loop after the main+ice
    # chains (surface_accumulation_torch). Without it the qr-seed -> precip
    # divergence can only be asserted by cell-set inclusion, not shown as an op path.
    "surface":         [("bottom_fall", "f32"), ("delz_bottom", "f32"),
                        ("surface_mul1", "f32"), ("surface_mul_dt", "f32"),
                        ("rain_increment", "f32"), ("snow_increment", "f32"),
                        ("graupel_increment", "f32")],
}


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
    algo = schedule["algorithm"]
    B, K = int(schedule["B"]), int(schedule["K"])
    loops = int(schedule["loops"])
    mm_main = schedule["mstepmax_main"]
    mm_ice = schedule["mstepmax_ice"]
    species = list(schedule.get("species_scope", ["qr", "nr"]))
    base = {"case_id": schedule["case_id"], "pair_id": schedule["pair_id"],
            "backend": schedule["backend"]}
    recs: list[dict] = []

    def emit(stage, fields, *, outer_loop, chain="-", n=0, cell_role="-",
             species_id="-", op_id="-", shape):
        for field, dtype in fields:
            recs.append({**base, "seq_no": len(recs), "op_seq_id": len(recs),
                         "outer_loop": outer_loop, "chain": chain, "n": n,
                         "cell_role": cell_role, "species": species_id,
                         "op_id": op_id, "stage": stage, "field": field,
                         "dtype": dtype, "shape": shape})

    for loop in range(1, loops + 1):
        emit("outer_pre_sed", _STAGE_FIELDS["outer_pre_sed"], outer_loop=loop, shape=[B, K])
        for chain, mmax_list in (("main", mm_main), ("ice", mm_ice)):
            mmax = int(mmax_list[loop - 1])
            for n in range(1, mmax + 1):
                # per-level (B,) slices captured at the top cell (matches the overlay)
                emit("substep_pre", _STAGE_FIELDS["substep_pre"], outer_loop=loop,
                     chain=chain, n=n, cell_role="TOP", shape=[B])
                for k in range(K):
                    role = _cell_role(k, K)
                    for sp in species:
                        ops = _mass_ops(algo, role) if sp == "qr" else _number_ops(algo, role)
                        for op_id in ops:
                            emit("op", _op_fields(algo, role, op_id), outer_loop=loop, chain=chain,
                                 n=n, cell_role=role, species_id=sp, op_id=op_id, shape=[B])
                emit("substep_post", _STAGE_FIELDS["substep_post"], outer_loop=loop,
                     chain=chain, n=n, shape=[B, K])
                # conditional re-slope: main after every substep; ice only n<mstepmax_ice
                if chain == "main" or n < mmax:
                    emit("reslope_input", _STAGE_FIELDS["reslope_input"], outer_loop=loop,
                         chain=chain, n=n, shape=[B, K])
                    emit("reslope_output", _STAGE_FIELDS["reslope_output"], outer_loop=loop,
                         chain=chain, n=n, shape=[B, K])
        # surface accumulation runs once per outer loop, after main+ice chains
        emit("surface", _STAGE_FIELDS["surface"], outer_loop=loop, shape=[B])
        emit("outer_post_sed", _STAGE_FIELDS["outer_post_sed"], outer_loop=loop, shape=[B, K])
        emit("outer_post_micro", _STAGE_FIELDS["outer_post_micro"], outer_loop=loop, shape=[B, K])
    return recs


def record_key(rec: dict) -> tuple:
    """The identity tuple used for observed==expected set comparison (payload-free)."""
    return (rec["outer_loop"], rec["chain"], rec["n"], rec["cell_role"],
            rec["species"], rec["op_id"], rec["stage"], rec["field"],
            rec["dtype"], tuple(rec["shape"]))


def expected_key_set(schedule: dict) -> set:
    return {record_key(r) for r in expected_records(schedule)}
