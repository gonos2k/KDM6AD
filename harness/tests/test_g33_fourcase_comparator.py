"""Verdict-matrix unit tests for the four-case comparator core (public CI — no
build). Synthetic runs from the REAL schema vocabulary exercise the owner's PR#66A
closeout matrix: fall_after as a shared accumulator add (not a false FAIL), the
mass/number conservative labels, the closed-world taxonomy, causal-carry vs
external-input, surface output increments, and malformed-input -> INVALID."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))
import g33_fourcase_comparator as cmp  # noqa: E402
import g33_mechanism as mech           # noqa: E402
import g33_schema as schema            # noqa: E402


_MASK = {"f32": 0xFFFFFFFF, "f64": 0xFFFFFFFFFFFFFFFF, "u8": 0xFF}
# clearing the sign bit and the exponent MSB keeps a synthetic value finite AND
# non-negative, which the ACTIVE-lane domain check requires.
_SAFE = {"f32": 0x3FFFFFFF, "f64": 0x3FFFFFFFFFFFFFFF, "u8": 0xFF}


def _base(dt, n, col, k, opid, fld):
    return (hash((n, col, k, opid, fld)) & _SAFE[dt]) or 1


def _species_run(algo, sp, cells, stages, bits, mstep=1):
    """Build a well-formed normalized run. Each op lane carries its substep_pre gate
    AND mstep records, with gate == (n <= mstep); a lane where n > mstep is a real
    dead lane, so every rung is filled with the no-op value its MechanismSpec
    relation demands (ZERO / EQUAL_TO its input / FALSE)."""
    bits = bits or {}
    ops, lanes = [], set()
    for n, col, k, role in cells:
        lanes.add((n, col))
        for opid in schema.ops_for_species(algo, role, sp):
            group = {}
            for fld, dt in schema.op_fields(algo, role, opid):
                key = (n, col, k, opid, fld)
                if key in bits:
                    b = bits[key] & _MASK[dt]
                else:
                    b = _base(dt, *key)
                    if n > mstep:                       # dead lane
                        spec = mech.mechanism(algo, role, sp, opid, fld)
                        if spec.inactive in (mech.ZERO, mech.FALSE):
                            b = 0
                        elif spec.inactive == mech.EQUAL_TO:
                            b = group.get(spec.inactive_ref, 0)
                group[fld] = b
                ops.append({"loop": 1, "chain": "main", "n": n, "col": col, "k": k,
                            "role": role, "species": sp, "op_id": opid,
                            "field": fld, "dtype": dt, "bits": b})
    st = []
    for n, col in sorted(lanes):
        st.append({"loop": 1, "chain": "main", "stage": "substep_pre", "n": n,
                   "col": col, "k": -1, "field": "gate", "dtype": "u8",
                   "bits": 1 if n <= mstep else 0})
        st.append({"loop": 1, "chain": "main", "stage": "substep_pre", "n": n,
                   "col": col, "k": -1, "field": "mstep", "dtype": "i32",
                   "bits": mstep})
    st += list(stages or [])
    return {"algorithm": algo, "B": 3, "K": 4, "ops": ops, "stages": st}


def _run(algo, cells=((1, 1, 1, "INTERIOR"),), stages=None, bits=None, mstep=1):
    return _species_run(algo, "qr", cells, stages, bits, mstep)


def _nr_run(algo, cells=((1, 1, 1, "INTERIOR"),), bits=None):
    return _species_run(algo, "nr", cells, None, bits)


def _surface(bits=None):
    bits = bits or {}
    return [{"loop": 1, "chain": "-", "stage": "surface", "n": 0, "col": 1, "k": -1,
             "field": f, "dtype": "f32", "bits": bits.get(f, (hash(f) & 0x3FFFFFFF) or 1)}
            for f in schema.semantic_surface_fields()]


# a dead lane can only exist at n > mstep, so the inactive cases run at n=2/mstep=1
DEAD = ((2, 1, 1, "INTERIOR"),)


def _verdict(lf, lc, cf, cc):
    return cmp.adjudicate(lf, lc, cf, cc)["verdict"]


# ── core verdicts ─────────────────────────────────────────────────────────────
def test_no_divergence_is_inconclusive():
    assert _verdict(_run("legacy"), _run("legacy"),
                    _run("conservative"), _run("conservative")) == "INCONCLUSIVE"


def test_shared_falk_divergence_is_pass():
    d = {(1, 1, 1, "QR_FALK", "mul_work1"): 0xABCD}
    assert _verdict(_run("legacy"), _run("legacy", bits=d),
                    _run("conservative"), _run("conservative", bits=d)) == "PASS"


# ── P0-1: fall_after is a shared accumulator add, not a variant result ─────────
def test_fall_after_both_pairs_is_pass_not_fail():
    d = {(1, 1, 1, "QR_FALLACC", "fall_after"): 0x4242}
    v = _verdict(_run("legacy"), _run("legacy", bits=d),
                 _run("conservative"), _run("conservative", bits=d))
    assert v == "PASS"


def test_conservative_fall_increment_is_fail():
    r = cmp.adjudicate(_run("legacy"), _run("legacy"), _run("conservative"),
                       _run("conservative", bits={(1, 1, 1, "QR_FALLACC", "fall_increment"): 9}))
    assert r["verdict"] == "FAIL" and "RATE_ACCUMULATION" in r["reason"]


def test_fall_before_is_invalid_causal_carry():
    r = cmp.adjudicate(_run("legacy"), _run("legacy"), _run("conservative"),
                       _run("conservative", bits={(1, 1, 1, "QR_FALLACC", "fall_before"): 7}))
    assert r["verdict"] == "INVALID_EVIDENCE" and "causal carry" in r["reason"]


# ── P0-2: mass (ρΔz) vs number (Δz) conservative inflow labels ─────────────────
def test_conservative_qr_inflow_labeled_mass_rhodz():
    r = cmp.adjudicate(_run("legacy"), _run("legacy"), _run("conservative"),
                       _run("conservative", bits={(1, 1, 1, "QR_INFLOW", "inflow_final"): 9}))
    assert r["verdict"] == "FAIL" and "CONS_MASS_RHODZ_INFLOW" in r["reason"]


def test_conservative_nr_inflow_labeled_number_dz():
    r = cmp.adjudicate(_nr_run("legacy"), _nr_run("legacy"), _nr_run("conservative"),
                       _nr_run("conservative", bits={(1, 1, 1, "NR_INFLOW", "inflow_final"): 9}))
    assert r["verdict"] == "FAIL" and "CONS_NUMBER_DZ_INFLOW" in r["reason"]


# ── P0-3: closed-world taxonomy ───────────────────────────────────────────────
def test_taxonomy_is_closed_world():
    mech.check_universe()                          # exact schema coverage + canary
    import pytest
    with pytest.raises(mech.TaxonomyHole):
        mech.mechanism("legacy", "INTERIOR", "qr", "QR_UPDATE", "invented_field")


# ── P0-4: surface output increments ───────────────────────────────────────────
def test_surface_rain_increment_both_pairs_is_pass():
    d = {"rain_increment": 0x77}
    assert _verdict(_run("legacy", stages=_surface()), _run("legacy", stages=_surface(d)),
                    _run("conservative", stages=_surface()),
                    _run("conservative", stages=_surface(d))) == "PASS"


def test_surface_snow_increment_both_pairs_is_inconclusive():
    d = {"snow_increment": 0x77}
    assert _verdict(_run("legacy", stages=_surface()), _run("legacy", stages=_surface(d)),
                    _run("conservative", stages=_surface()),
                    _run("conservative", stages=_surface(d))) == "INCONCLUSIVE"


def test_surface_species_sum_both_pairs_is_pass():
    d = {"bottom_fall_total": 0x5678}
    assert _verdict(_run("legacy", stages=_surface()), _run("legacy", stages=_surface(d)),
                    _run("conservative", stages=_surface()),
                    _run("conservative", stages=_surface(d))) == "PASS"


def test_surface_out_of_scope_species_both_pairs_is_inconclusive():
    d = {"bottom_fall_qs": 0x1234}
    assert _verdict(_run("legacy", stages=_surface()), _run("legacy", stages=_surface(d)),
                    _run("conservative", stages=_surface()),
                    _run("conservative", stages=_surface(d))) == "INCONCLUSIVE"


# ── P0-5: external input is not evidence corruption ───────────────────────────
def test_delz_bottom_external_input_is_inconclusive_not_invalid():
    d = {"delz_bottom": 0x1111}          # grid metric — a precondition, not a result
    r = cmp.adjudicate(_run("legacy", stages=_surface()), _run("legacy", stages=_surface(d)),
                       _run("conservative", stages=_surface()),
                       _run("conservative", stages=_surface(d)))
    assert r["verdict"] == "INCONCLUSIVE" and "external input" in r["reason"]


# ── P0-6: malformed normalized input -> INVALID_EVIDENCE, never a crash ───────
def test_missing_key_is_invalid_not_crash():
    b = _run("conservative")
    del b["ops"][0]["dtype"]
    assert _verdict(_run("legacy"), _run("legacy"), _run("conservative"), b) == "INVALID_EVIDENCE"


def test_wrong_type_is_invalid_not_crash():
    b = _run("conservative")
    b["ops"][0]["bits"] = "not-an-int"
    assert _verdict(_run("legacy"), _run("legacy"), _run("conservative"), b) == "INVALID_EVIDENCE"


def test_unknown_surface_field_is_invalid_not_crash():
    b = _run("conservative", stages=[{"stage": "surface", "n": 0, "col": 1, "k": -1,
                                      "field": "bogus_out", "dtype": "f32", "bits": 1}])
    assert _verdict(_run("legacy"), _run("legacy"),
                    _run("conservative", stages=[]), b) == "INVALID_EVIDENCE"


# ── role-aware TOP depletion + shared interior ────────────────────────────────
def test_top_q_minus_out_both_pairs_is_not_pass():
    top = ((1, 1, 0, "TOP"),)
    d = {(1, 1, 0, "QR_UPDATE", "q_minus_out"): 0xBEEF}
    v = _verdict(_run("legacy", cells=top, bits=d), _run("legacy", cells=top),
                 _run("conservative", cells=top, bits=d), _run("conservative", cells=top))
    assert v == "FAIL"


def test_interior_q_minus_out_both_pairs_is_pass():
    d = {(1, 1, 1, "QR_UPDATE", "q_minus_out"): 0xBEEF}
    assert _verdict(_run("legacy"), _run("legacy", bits=d),
                    _run("conservative"), _run("conservative", bits=d)) == "PASS"


# ── structural guards ─────────────────────────────────────────────────────────
def test_identity_universe_mismatch_is_invalid():
    b = _run("conservative")
    b["ops"] = b["ops"][:-1]
    assert _verdict(_run("legacy"), _run("legacy"), _run("conservative"), b) == "INVALID_EVIDENCE"


def test_duplicate_identity_is_invalid():
    b = _run("conservative")
    b["ops"].append(dict(b["ops"][0]))
    assert _verdict(_run("legacy"), _run("legacy"), _run("conservative"), b) == "INVALID_EVIDENCE"


def test_algorithm_typo_is_invalid():
    bad = _run("conservative")
    bad["algorithm"] = "conservativ"
    assert _verdict(_run("legacy"), _run("legacy"), bad, _run("conservative")) == "INVALID_EVIDENCE"


def test_dtype_mismatch_vs_schema_is_invalid():
    b = _run("conservative")
    b["ops"][0]["dtype"] = "f64"                   # QR_FALK.mul_dend_q is f32
    assert _verdict(_run("legacy"), _run("legacy"), _run("conservative"), b) == "INVALID_EVIDENCE"


def test_unknown_stage_is_invalid():
    b = _run("conservative", stages=[{"stage": "reslope_output", "n": 1, "col": 1,
                                      "k": 1, "field": "qr", "dtype": "f32", "bits": 1}])
    assert _verdict(_run("legacy"), _run("legacy"), _run("conservative", stages=[]),
                    b) == "INVALID_EVIDENCE"


# ── P0-6: fail-closed gaps (all must be INVALID, never a crash) ────────────────
def test_out_of_scope_species_op_is_invalid_not_crash():
    b = _run("conservative")
    b["ops"][0]["species"] = "qs"          # schema raises NotImplementedError
    assert _verdict(_run("legacy"), _run("legacy"), _run("conservative"), b) == "INVALID_EVIDENCE"


def test_unknown_substep_field_is_invalid():
    b = _run("conservative", stages=[{"stage": "substep_pre", "n": 1, "col": 1,
                                      "k": -1, "field": "invented", "dtype": "f32", "bits": 1}])
    assert _verdict(_run("legacy"), _run("legacy"), _run("conservative", stages=[]),
                    b) == "INVALID_EVIDENCE"


def test_wrong_stage_dtype_is_invalid():
    d = [{"stage": "surface", "n": 0, "col": 1, "k": -1, "field": "rain_increment",
          "dtype": "u8", "bits": 1}]              # schema says rain_increment is f32
    assert _verdict(_run("legacy"), _run("legacy"), _run("conservative", stages=[]),
                    _run("conservative", stages=d)) == "INVALID_EVIDENCE"


def test_role_k_mismatch_is_invalid():
    b = _run("conservative")
    b["ops"][0]["role"] = "BOTTOM"          # k=1 in K=4 is INTERIOR, not BOTTOM
    assert _verdict(_run("legacy"), _run("legacy"), _run("conservative"), b) == "INVALID_EVIDENCE"


def test_col_out_of_range_is_invalid():
    b = _run("conservative")
    b["ops"][0]["col"] = 0                   # col must be 1..B
    assert _verdict(_run("legacy"), _run("legacy"), _run("conservative"), b) == "INVALID_EVIDENCE"


def test_float_bits_is_invalid():
    b = _run("conservative")
    b["ops"][0]["bits"] = 1.9                # must be a genuine int, not coerced
    assert _verdict(_run("legacy"), _run("legacy"), _run("conservative"), b) == "INVALID_EVIDENCE"


def test_missing_BK_is_invalid():
    b = _run("conservative")
    del b["B"]
    assert _verdict(_run("legacy"), _run("legacy"), _run("conservative"), b) == "INVALID_EVIDENCE"


def test_mechanism_out_of_schema_key_raises():
    import pytest
    with pytest.raises(mech.TaxonomyHole):
        mech.mechanism("legacy", "TOP", "qr", "QR_OUTFLOW", "dq_out")  # no outflow at legacy TOP


# ── gate semantics: only PRE-GATE rungs may differ in a dead lane ─────────────
def test_inactive_lane_pre_gate_diff_is_not_the_verdict():
    d = {(2, 1, 1, "QR_FALK", "mul_work1"): 0xABCD}      # pre-gate diagnostic
    div = cmp.compare_pair(_run("legacy", cells=DEAD, mstep=1),
                           _run("legacy", cells=DEAD, mstep=1, bits=d))
    assert div.phase is None and div.inactive_diffs and not div.invalid


def test_active_lane_op_diff_is_the_verdict():
    d = {(1, 1, 1, "QR_FALK", "mul_work1"): 0xABCD}
    div = cmp.compare_pair(_run("legacy"), _run("legacy", bits=d))
    assert div.phase == "op" and div.tag == "FALK/mul_work1"


@pytest.mark.parametrize("op_id,field", [
    ("QR_FALK", "falk_f32"), ("QR_FALK", "falk_precast"),
    ("QR_OUTFLOW", "dq_out"), ("QR_OUTFLOW", "mul_dt"),
    ("QR_FALLACC", "fall_increment"), ("QR_INFLOW", "inflow_final"),
])
def test_inactive_lane_nonzero_transport_is_invalid(op_id, field):
    d = {(2, 1, 1, op_id, field): 0x3F800000}
    div = cmp.compare_pair(_run("legacy", cells=DEAD, mstep=1),
                           _run("legacy", cells=DEAD, mstep=1, bits=d))
    assert div.invalid and "gate semantics" in div.invalid


@pytest.mark.parametrize("op_id,field", [
    ("QR_FALLACC", "fall_after"), ("QR_UPDATE", "q_minus_out"),
    ("QR_UPDATE", "q_plus_in_preclamp"), ("QR_UPDATE", "q_post"),
])
def test_inactive_lane_moved_state_is_invalid(op_id, field):
    d = {(2, 1, 1, op_id, field): 0x3F800000}
    div = cmp.compare_pair(_run("legacy", cells=DEAD, mstep=1),
                           _run("legacy", cells=DEAD, mstep=1, bits=d))
    assert div.invalid and "gate semantics" in div.invalid


def test_inactive_lane_clamp_fired_is_invalid():
    d = {(2, 1, 1, "QR_UPDATE", "clamp_active"): 1}
    div = cmp.compare_pair(_run("legacy", cells=DEAD, mstep=1),
                           _run("legacy", cells=DEAD, mstep=1, bits=d))
    assert div.invalid and "gate semantics" in div.invalid


def test_active_lane_nonfinite_transport_is_invalid():
    d = {(1, 1, 1, "QR_FALK", "falk_f32"): 0x7F800000}   # +Inf in an ACTIVE lane
    div = cmp.compare_pair(_run("legacy", bits=d), _run("legacy", bits=d))
    assert div.invalid and "gate semantics" in div.invalid


def test_active_lane_negative_transport_is_invalid():
    d = {(1, 1, 1, "QR_UPDATE", "q_post"): 0xBF800000}   # -1.0 state
    div = cmp.compare_pair(_run("legacy", bits=d), _run("legacy", bits=d))
    assert div.invalid and "domain" in div.invalid


# ── P0-1: the gate must follow from this column's own mstep ──────────────────
def test_gate_contradicting_its_own_mstep_is_invalid():
    r = _run("legacy")                       # n=1, mstep=1 -> gate must be 1
    for st in r["stages"]:
        if st["field"] == "gate":
            st["bits"] = 0
    div = cmp.compare_pair(r, r)
    assert div.invalid and "gate law" in div.invalid


def test_missing_mstep_record_is_invalid():
    r = _run("legacy")
    r["stages"] = [s for s in r["stages"] if s["field"] != "mstep"]
    assert cmp.compare_pair(r, r).invalid


# ── P0-7: a VALID but different gate is upstream, not corrupt evidence ───────
def test_backends_with_different_valid_mstep_is_inconclusive():
    # both runs obey gate == (n <= mstep), but their mstep differs -> a CFL /
    # fall-speed difference upstream of sedimentation, NOT evidence corruption.
    f = _run("legacy", cells=DEAD, mstep=1)      # n=2 inactive
    c = _run("legacy", cells=DEAD, mstep=2)      # n=2 active
    div = cmp.compare_pair(f, c)
    assert div.invalid is None and div.phase == "substep_pre"
    verdict, reason = cmp.classify(div, cmp.Divergence())
    assert verdict == "INCONCLUSIVE" and "upstream" in reason


# ── P0-2: the active mask is never defaulted ─────────────────────────────────
def test_missing_gate_record_is_invalid():
    r = _run("legacy")
    r["stages"] = [s for s in r["stages"] if s["field"] != "gate"]
    assert cmp.compare_pair(r, r).invalid


# ── P0-3: outer_loop / chain are part of the event identity ──────────────────
def test_outer_loop_is_in_the_identity():
    r = _run("legacy")
    ev = cmp._events(r)
    op = next(e for e in ev if e.phase == "op")
    assert op.identity[1] == 1 and op.identity[2] == "main"      # loop, chain
    # the same (n,col,k,op,field) in a DIFFERENT outer loop is a distinct record
    r2 = _run("legacy")
    for o in r2["ops"]:
        o["loop"] = 2
    for st in r2["stages"]:
        st["loop"] = 2
    ids = {e.identity for e in cmp._events(r)} | {e.identity for e in cmp._events(r2)}
    assert len(ids) == 2 * len(cmp._events(r))


def test_loop2_sorts_after_loop1_surface():
    r = _run("legacy", stages=_surface())
    r2 = _run("legacy", stages=_surface())
    for rec in r2["ops"] + r2["stages"]:
        rec["loop"] = 2
    merged = {"algorithm": "legacy", "B": 3, "K": 4,
              "ops": r["ops"] + r2["ops"], "stages": r["stages"] + r2["stages"]}
    ev = cmp._events(merged)
    loops = [e.identity[1] for e in ev]
    assert loops == sorted(loops)        # every loop-1 event precedes every loop-2
