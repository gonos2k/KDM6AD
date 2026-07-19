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
        return ["QR_FALK", "QR_UPDATE"] if algorithm == "legacy" \
            else ["QR_FALK", "QR_OUTFLOW", "QR_UPDATE"]
    # INTERIOR / BOTTOM
    return ["QR_FALK", "QR_OUTFLOW", "QR_INFLOW", "QR_UPDATE"]


def _number_ops(algorithm: str, role: str) -> list[str]:
    if role == "TOP":
        return ["NR_FALK", "NR_UPDATE"]
    return ["NR_FALK", "NR_OUTFLOW", "NR_INFLOW", "NR_UPDATE"]


# fields per op (dtype). Refined alongside the C++ writer (steps 7/9); the KEY
# SET (op-level completeness) is authoritative now.
_OP_FIELDS = {
    "QR_FALK":   [("falk_f32", "f32"), ("falk_precast", "f64")],
    "QR_OUTFLOW": [("dq_out", "f32"), ("cap_active", "u8"), ("source_reservoir", "f32")],
    "QR_INFLOW": [("src_metric", "f32"), ("dst_metric", "f32"), ("inflow_numerator", "f32"),
                  ("inflow_cap_active", "u8"), ("inflow_final", "f32")],
    "QR_UPDATE": [("q_before", "f32"), ("q_minus_out", "f32"), ("q_plus_in_preclamp", "f32"),
                  ("clamp_active", "u8"), ("q_post", "f32")],
    "NR_FALK":   [("falk_f32", "f32"), ("falk_precast", "f64")],
    "NR_OUTFLOW": [("dn_out", "f32"), ("cap_active", "u8"), ("source_reservoir", "f32")],
    "NR_INFLOW": [("delz_src", "f32"), ("delz_safe_dst", "f32"), ("inflow_final", "f32")],
    "NR_UPDATE": [("n_before", "f32"), ("n_minus_out", "f32"), ("n_plus_in_preclamp", "f32"),
                  ("clamp_active", "u8"), ("n_post", "f32")],
}

# stage (non-op) snapshot fields.
_STAGE_FIELDS = {
    "outer_pre_sed":   [("qr", "f32"), ("nr", "f32"), ("qv", "f32"), ("th", "f32"),
                        ("rho", "f32"), ("delz", "f32")],
    "outer_post_sed":  [("qr", "f32"), ("nr", "f32"), ("qv", "f32"), ("th", "f32")],
    "outer_post_micro": [("qr", "f32"), ("nr", "f32"), ("qv", "f32"), ("th", "f32")],
    "substep_pre":     [("qr", "f32"), ("nr", "f32"), ("work1_qr", "f64"), ("workn_qr", "f64"),
                        ("mstep_native", "f64"), ("mstepmax", "i32"), ("gate", "u8"),
                        ("rho", "f32"), ("delz", "f32")],
    "substep_post":    [("qr", "f32"), ("nr", "f32"), ("qs", "f32"), ("qg", "f32"), ("brs", "f32")],
    "reslope_input":   [("qr", "f32"), ("nr", "f32")],
    "reslope_output":  [("work1_qr", "f64"), ("workn_qr", "f64")],
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
                emit("substep_pre", _STAGE_FIELDS["substep_pre"], outer_loop=loop,
                     chain=chain, n=n, shape=[B, K])
                for k in range(K):
                    role = _cell_role(k, K)
                    for sp in species:
                        ops = _mass_ops(algo, role) if sp == "qr" else _number_ops(algo, role)
                        for op_id in ops:
                            emit("op", _OP_FIELDS[op_id], outer_loop=loop, chain=chain,
                                 n=n, cell_role=role, species_id=sp, op_id=op_id, shape=[B])
                emit("substep_post", _STAGE_FIELDS["substep_post"], outer_loop=loop,
                     chain=chain, n=n, shape=[B, K])
                # conditional re-slope: main after every substep; ice only n<mstepmax_ice
                if chain == "main" or n < mmax:
                    emit("reslope_input", _STAGE_FIELDS["reslope_input"], outer_loop=loop,
                         chain=chain, n=n, shape=[B, K])
                    emit("reslope_output", _STAGE_FIELDS["reslope_output"], outer_loop=loop,
                         chain=chain, n=n, shape=[B, K])
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
