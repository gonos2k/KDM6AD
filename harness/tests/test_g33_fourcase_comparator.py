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
import g33_fortran_dump as fd          # noqa: E402
import struct                          # noqa: E402


def _f32(bits):
    return struct.unpack(">f", struct.pack(">I", bits & 0xFFFFFFFF))[0]


def _branch_bits(field, group):
    """Derive a branch flag from the operands already placed in this op group —
    a real producer's flag agrees with its own operands, and the validator now
    recomputes it, so synthetic evidence must too."""
    if field == "cap_active":
        return int(_f32(group["source_reservoir"]) < _f32(group["outflow_pre_cap"]))
    if field == "inflow_cap_active":
        return int(_f32(group["source_reservoir"]) < _f32(group["inflow_pre_cap"]))
    for f in ("q_plus_in_preclamp", "n_plus_in_preclamp", "q_minus_out", "n_minus_out"):
        if f in group:
            return int(_f32(group[f]) < 0.0)
    return 0


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
                elif mech.domain_rule(fld) == mech.BOOL_BRANCH:
                    b = _branch_bits(fld, group) if n <= mstep else 0
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


def _final(bits=None):
    """The whole-step cumulative precipitation phase."""
    bits = bits or {}
    return [{"loop": 0, "chain": "-", "stage": "final_output", "n": 0, "col": 1,
             "k": -1, "field": f, "dtype": "f32",
             "bits": bits.get(f, (hash(f) & 0x3FFFFFFF) or 1)}
            for f in schema.semantic_stage_fields("final_output")]


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


def test_shared_falk_divergence_is_shared_seed():
    d = {(1, 1, 1, "QR_FALK", "mul_work1"): 0xABCD}
    assert _verdict(_run("legacy"), _run("legacy", bits=d),
                    _run("conservative"), _run("conservative", bits=d)) == cmp.SHARED_SEED_CANDIDATE


# ── P0-1: fall_after is a shared accumulator add, not a variant result ─────────
def test_fall_after_both_pairs_is_shared_seed_not_fail():
    d = {(1, 1, 1, "QR_FALLACC", "fall_after"): 0x4242}
    v = _verdict(_run("legacy"), _run("legacy", bits=d),
                 _run("conservative"), _run("conservative", bits=d))
    assert v == cmp.SHARED_SEED_CANDIDATE


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
def test_cumulative_rain_output_both_pairs_is_shared_seed():
    # the comparable OUTPUT is the whole-step cumulative, not a per-loop increment
    d = {"rain_precip_cumulative": 0x77}
    assert _verdict(_run("legacy", stages=_final()), _run("legacy", stages=_final(d)),
                    _run("conservative", stages=_final()),
                    _run("conservative", stages=_final(d))) == cmp.SHARED_SEED_CANDIDATE


def test_cumulative_snow_output_both_pairs_is_inconclusive():
    d = {"snow_precip_cumulative": 0x77}
    assert _verdict(_run("legacy", stages=_final()), _run("legacy", stages=_final(d)),
                    _run("conservative", stages=_final()),
                    _run("conservative", stages=_final(d))) == "INCONCLUSIVE"


def test_per_loop_increment_is_not_in_the_comparable_set():
    # Fortran does not emit it, so comparing it would compare different quantities
    assert "rain_increment" not in schema.semantic_stage_fields("surface")
    assert "rain_precip_cumulative" in schema.semantic_stage_fields("final_output")


def test_surface_species_sum_both_pairs_is_shared_seed():
    d = {"bottom_fall_total": 0x5678}
    assert _verdict(_run("legacy", stages=_surface()), _run("legacy", stages=_surface(d)),
                    _run("conservative", stages=_surface()),
                    _run("conservative", stages=_surface(d))) == cmp.SHARED_SEED_CANDIDATE


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


def test_interior_q_minus_out_both_pairs_is_shared_seed():
    d = {(1, 1, 1, "QR_UPDATE", "q_minus_out"): 0xBEEF}
    assert _verdict(_run("legacy"), _run("legacy", bits=d),
                    _run("conservative"), _run("conservative", bits=d)) == cmp.SHARED_SEED_CANDIDATE


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


# ── heterogeneous mstep: the REAL producer topologies ────────────────────────
def _topo_run(algo, mstep_by_col, emit_inactive, bits=None):
    """One run with per-column mstep. `emit_inactive` picks the producer shape:
    False = Fortran (op records for ACTIVE columns only), True = C++ (a whole [B]
    payload per substep, so inactive lanes carry op records at their no-op values)."""
    bits, ops, st = bits or {}, [], []
    maxn = max(mstep_by_col.values())
    for col, m in sorted(mstep_by_col.items()):
        for n in range(1, maxn + 1):
            active = n <= m
            for field, dt, b in (("gate", "u8", 1 if active else 0), ("mstep", "i32", m)):
                st.append({"loop": 1, "chain": "main", "stage": "substep_pre", "n": n,
                           "col": col, "k": -1, "field": field, "dtype": dt, "bits": b})
            if not active and not emit_inactive:
                continue
            for opid in schema.ops_for_species(algo, "INTERIOR", "qr"):
                group = {}
                for fld, dt in schema.op_fields(algo, "INTERIOR", opid):
                    key = (n, col, 1, opid, fld)
                    if key in bits:
                        b = bits[key] & _MASK[dt]
                    elif mech.domain_rule(fld) == mech.BOOL_BRANCH:
                        b = _branch_bits(fld, group) if active else 0
                    else:
                        b = _base(dt, *key)
                        if not active:
                            spec = mech.mechanism(algo, "INTERIOR", "qr", opid, fld)
                            if spec.inactive in (mech.ZERO, mech.FALSE):
                                b = 0
                            elif spec.inactive == mech.EQUAL_TO:
                                b = group.get(spec.inactive_ref, 0)
                    group[fld] = b
                    ops.append({"loop": 1, "chain": "main", "n": n, "col": col, "k": 1,
                                "role": "INTERIOR", "species": "qr", "op_id": opid,
                                "field": fld, "dtype": dt, "bits": b})
    return {"algorithm": algo, "B": 3, "K": 4, "ops": ops, "stages": st}


def test_fortran_active_only_vs_cpp_all_lanes_compares():
    # mstep = {col1: 1, col2: 2}: at n=2 the Fortran run has NO col-1 op records
    # while the C++ run does. The universes still align on the ACTIVE stream.
    m = {1: 1, 2: 2}
    fort = _topo_run("legacy", m, emit_inactive=False)
    cpp = _topo_run("legacy", m, emit_inactive=True)
    d = cmp.compare_pair(fort, cpp)
    assert d.invalid is None and d.phase is None       # identical where comparable


def test_heterogeneous_topology_still_finds_an_active_divergence():
    m = {1: 1, 2: 2}
    d = {(2, 2, 1, "QR_FALK", "mul_work1"): 0xABCD}     # col 2 is ACTIVE at n=2
    div = cmp.compare_pair(_topo_run("legacy", m, False),
                           _topo_run("legacy", m, True, bits=d))
    assert div.phase == "op" and div.tag == "FALK/mul_work1" and div.identity[4] == 2


def test_cpp_inactive_lane_diff_is_diagnostics_only():
    m = {1: 1, 2: 2}
    # col 1 at n=2 is INACTIVE and exists only in the C++ run -> not the verdict.
    div = cmp.compare_pair(_topo_run("legacy", m, False), _topo_run("legacy", m, True))
    assert div.phase is None and div.invalid is None


def test_backends_with_different_mstep_is_inconclusive_not_invalid():
    # Fortran mstep=1 (no n=2 ops at all), C++ mstep=2 (real n=2 ops): the op
    # universes genuinely differ, but the cause is the upstream substep count.
    fort = _topo_run("legacy", {1: 1, 2: 1}, emit_inactive=False)
    cpp = _topo_run("legacy", {1: 2, 2: 2}, emit_inactive=True)
    div = cmp.compare_pair(fort, cpp)
    assert div.invalid is None, div.invalid
    assert div.phase == "substep_pre" and div.identity[6] in ("gate", "mstep")
    verdict, reason = cmp.classify(div, cmp.Divergence())
    assert verdict == "INCONCLUSIVE" and "upstream" in reason


# ── branch authority: the producer flag is checked, never trusted ────────────
def _both(**kw):
    """A run pair identical on both sides (so any rejection is the validator's)."""
    r = _run("legacy", **kw)
    return r, _run("legacy", **kw)


def test_branch_flag_out_of_range_is_invalid():
    r, c = _both(bits={(1, 1, 1, "QR_OUTFLOW", "cap_active"): 2})
    div = cmp.compare_pair(r, c)
    assert div.invalid and "not 0/1" in div.invalid


def test_branch_flag_contradicting_its_operands_is_invalid():
    # flip cap_active away from what min(pre_cap, reservoir) actually selects
    base = _run("legacy")
    grp = {o["field"]: o["bits"] for o in base["ops"] if o["op_id"] == "QR_OUTFLOW"}
    truth = int(_f32(grp["source_reservoir"]) < _f32(grp["outflow_pre_cap"]))
    r, c = _both(bits={(1, 1, 1, "QR_OUTFLOW", "cap_active"): 1 - truth})
    div = cmp.compare_pair(r, c)
    assert div.invalid and "contradicts its own operands" in div.invalid


def test_branch_tie_is_accepted_and_flag_must_be_zero():
    # pre_cap == reservoir: min() TIEs, so `pre_cap > reservoir` is false.
    same = 0x3F800000
    ok = {(1, 1, 1, "QR_OUTFLOW", "outflow_pre_cap"): same,
          (1, 1, 1, "QR_OUTFLOW", "source_reservoir"): same,
          (1, 1, 1, "QR_OUTFLOW", "cap_active"): 0}
    assert cmp.compare_pair(*_both(bits=ok)).invalid is None
    bad = {**ok, (1, 1, 1, "QR_OUTFLOW", "cap_active"): 1}
    assert cmp.compare_pair(*_both(bits=bad)).invalid is not None


def test_nan_operand_in_active_branch_is_invalid():
    nan = 0x7FC00000
    r, c = _both(bits={(1, 1, 1, "QR_OUTFLOW", "outflow_pre_cap"): nan})
    div = cmp.compare_pair(r, c)
    assert div.invalid and ("UNORDERED" in div.invalid or "non-finite" in div.invalid)


def test_clamp_flag_contradicting_preclamp_sign_is_invalid():
    # preclamp is positive, so the positivity clamp cannot have fired
    r, c = _both(bits={(1, 1, 1, "QR_UPDATE", "q_plus_in_preclamp"): 0x3F800000,
                       (1, 1, 1, "QR_UPDATE", "clamp_active"): 1})
    div = cmp.compare_pair(r, c)
    assert div.invalid and "contradicts its own operands" in div.invalid


# ── active-lane numerical domain (closed world) ──────────────────────────────
def test_nan_in_a_shared_intermediate_cannot_pass():
    # both pairs diverge at the SAME shared rung, but the value is NaN: the domain
    # gate must reject it before the shared-key PASS rule is reached.
    nan64 = 0x7FF8000000000000            # mul_work1 is f64
    d = {(1, 1, 1, "QR_FALK", "mul_work1"): nan64}
    v = _verdict(_run("legacy"), _run("legacy", bits=d),
                 _run("conservative"), _run("conservative", bits=d))
    assert v == "INVALID_EVIDENCE"


def test_negative_conservative_transport_is_invalid_before_fail():
    neg = 0xBF800000                       # -1.0
    r = cmp.adjudicate(_run("legacy"), _run("legacy"), _run("conservative"),
                       _run("conservative", bits={(1, 1, 1, "QR_INFLOW", "inflow_final"): neg}))
    assert r["verdict"] == "INVALID_EVIDENCE"


def test_zero_grid_metric_is_invalid():
    r, c = _both(bits={(1, 1, 1, "QR_INFLOW", "delz_safe_dst"): 0})
    div = cmp.compare_pair(r, c)
    assert div.invalid and "strictly positive" in div.invalid


def test_reverse_topology_order_does_not_crash():
    # P1-1: C++-shaped run first, Fortran-shaped second — the second lacks the
    # inactive identities entirely. The comparator must report, not raise.
    m = {1: 1, 2: 2}
    div = cmp.compare_pair(_topo_run("legacy", m, emit_inactive=True),
                           _topo_run("legacy", m, emit_inactive=False))
    assert div.invalid is not None or div.phase is None


# ── the pure comparator may not declare PASS ─────────────────────────────────
def test_pure_adjudicate_never_returns_pass():
    d = {(1, 1, 1, "QR_FALK", "mul_work1"): 0xABCD}
    r = cmp.adjudicate(_run("legacy"), _run("legacy", bits=d),
                       _run("conservative"), _run("conservative", bits=d))
    assert r["verdict"] == cmp.SHARED_SEED_CANDIDATE
    assert "PASS" not in r["verdict"]          # promotion belongs to the verified entry


def _decide(runs):
    """The IDENTITY + arithmetic layer, on four normalized runs.

    Not adjudicate_verified: that entry now derives each run from the verified
    artifact itself (owner P0-4), so there is no place to hand it a synthetic run —
    which is the property under test elsewhere. _adjudicate_normalized is the layer
    these cases are about, and it cannot promote.
    """
    return cmp._adjudicate_normalized(*runs, promote=False)


def test_the_decision_api_refuses_plain_dictionaries():
    # normalized runs carry no attestation; a verdict built from them would describe
    # evidence nobody anchored. Enforced by TYPE, not by callers remembering.
    with pytest.raises(TypeError, match="VerifiedFourCase"):
        cmp.adjudicate_verified({"algorithm": "legacy"})


def test_an_unready_leg_cannot_reach_a_verdict():
    """A leg whose artifact is not decision-grade stops the decision, whatever its
    numbers say."""
    frozen = cmp._deep_freeze({"algorithm": "legacy"})
    ready = [cmp.DecisionLeg(n, type("A", (), {"verdict_ready": True})(), frozen)
             for n in ("legacy-C++", "conservative-F", "conservative-C++")]
    unready = cmp.DecisionLeg("legacy-F",
                              type("A", (), {"verdict_ready": False})(), frozen)
    r = cmp.adjudicate_verified(
        cmp.VerifiedFourCase(unready, *ready, _token=cmp._FACTORY_TOKEN))
    assert r["verdict"] == "INVALID_EVIDENCE" and "not decision-grade" in r["reason"]


def test_a_decision_leg_cannot_be_handed_a_run(monkeypatch):
    """The factory derives each run from the ARTIFACT. Previously the carrier took
    the verified artifact and the normalized dict separately, so a genuine leg could
    be paired with a run from another fixture — the artifact carried the attestation
    while the comparator read the dict (owner P0-4)."""
    with pytest.raises(TypeError, match="nowhere to pass one in"):
        cmp.VerifiedFourCase.of(legacy_fortran={"algorithm": "legacy"},
                                legacy_cpp=None, conservative_fortran=None,
                                conservative_cpp=None)


def test_a_paired_run_is_read_only():
    frozen = cmp._deep_freeze({"stages": [{"bits": 1}], "ops": []})
    with pytest.raises(TypeError):
        frozen["stages"] = []


def test_the_debug_path_cannot_report_a_decision_verdict():
    # a shared seed in an unattested run reports its own name, so automation reading
    # only the verdict string cannot mistake it for a decision
    r = cmp.adjudicate_unattested(_run("legacy"), _run("legacy"),
                                  _run("conservative"), _run("conservative"))
    assert r["verdict"] != cmp.PASS_MECHANISM


def test_verified_entry_refuses_legs_without_identity():
    # the synthetic runs carry no problem identity, so the decision entry stops
    # before it ever looks at the arithmetic
    r = _decide(([_run("legacy"), _run("legacy"),
                                           _run("conservative"), _run("conservative")]))
    assert r["verdict"] == "INVALID_EVIDENCE" and "problem identity" in r["reason"]


def test_verified_entry_refuses_a_different_problem():
    ident = {"fixture_sha256": "a" * 64, "parameter_sha256": "b" * 64, "B": 3, "K": 4}
    legs = [_run("legacy"), _run("legacy"), _run("conservative"), _run("conservative")]
    for leg in legs:
        leg["problem"] = dict(ident)
    legs[3]["problem"] = dict(ident, fixture_sha256="c" * 64)     # a different fixture
    r = _decide((legs))
    assert r["verdict"] == "INVALID_EVIDENCE" and "same problem" in r["reason"]



# -- problem identity has TWO levels (owner P0-C2) -----------------------------

_IDENT = {"fixture_sha256": "a" * 64, "parameter_sha256": "b" * 64, "B": 3, "K": 4,
          "local_parameter_sha256": "c" * 64}


def _four_legs(**per_leg):
    """Four runs sharing one problem identity; per_leg patches an index's problem."""
    legs = [_run("legacy"), _run("legacy"), _run("conservative"), _run("conservative")]
    for leg in legs:
        leg["problem"] = dict(_IDENT)
    for idx, patch in per_leg.items():
        legs[int(idx[1:])]["problem"] = dict(_IDENT, **patch)
    return _decide(legs)


def test_the_four_legs_must_share_the_SEDIMENTATION_identity():
    r = (_four_legs(i2={"fixture_sha256": "f" * 64}))
    assert r["verdict"] == "INVALID_EVIDENCE"
    assert "same problem" in r["reason"]


def test_backend_local_parameters_are_compared_WITHIN_a_backend():
    """ccn0/scale_h exist only in the Fortran leg. Flattening them into the four-way
    identity forced a choice between dropping them — which is what happened, so they
    were checked nowhere — and demanding C++ carry a hash of variables it does not
    have. Two Fortran legs built with different local parameters are not the same
    full step, and that is now said at the level where it applies."""
    # index 2 is conservative-F; index 0 is legacy-F
    r = (_four_legs(i2={"local_parameter_sha256": "9" * 64}))
    assert r["verdict"] == "INVALID_EVIDENCE"
    assert "backend-local parameters" in r["reason"]


def test_a_local_parameter_difference_ACROSS_backends_is_not_an_error():
    # the C++ legs have no ccn0/scale_h at all; requiring them to match Fortran's
    # hash would make every real four-case run INVALID
    r = (_four_legs(i1={"local_parameter_sha256": None},
                                           i3={"local_parameter_sha256": None}))
    assert "backend-local" not in (r.get("reason") or "")


# -- promotion is scoped to what the identity establishes (owner P0-C2 6) ------

def test_only_the_op_ladder_may_promote():
    """Every op rung is replayed from its own dumped operands, so the causal inputs
    of a divergence there are sealed by the evidence itself.

    The entry snapshots are NOT: a difference first appearing at outer_pre_sed or
    substep_pre says the state ARRIVING at sedimentation already differed, which is a
    statement about what produced that state. Widening this needs a per-field argument
    that the inputs are sealed, not a judgement that a phase feels close enough.
    """
    assert cmp.promotable_phase("op")
    for phase in ("outer_pre_sed", "substep_pre", "surface", "final_output",
                  "outer_post_sed", "outer_post_micro"):
        assert not cmp.promotable_phase(phase), phase


def test_the_promotable_phase_set_is_exactly_the_op_ladder():
    # a phase added later must be classified deliberately, not inherit promotion
    assert cmp._SEDIMENTATION_PHASES == frozenset(("op",))


def test_a_whole_step_seed_is_reported_as_a_full_step_claim():
    d = {"rain_precip_cumulative": 0x77}
    legs = [_run("legacy", stages=_final()), _run("legacy", stages=_final(d)),
            _run("conservative", stages=_final()), _run("conservative", stages=_final(d))]
    # the pure comparator still calls it a shared seed...
    assert cmp.adjudicate(*legs)["verdict"] == cmp.SHARED_SEED_CANDIDATE
    # ...and the phase it sits at is one that cannot be promoted
    phase = cmp.adjudicate(*legs)["legacy_first_divergence"]["phase"]
    assert phase == "final_output" and not cmp.promotable_phase(phase)


# -- a refusal must not carry a promotion's words (owner P0-4) -----------------

def _promotion_branch(phase, reason="both pairs at that phase"):
    """Drive the promotion branch the way _adjudicate_normalized does.

    The verdict and the reason used to be assigned in different places: the branch
    chose the verdict, and the promotion wording was applied unconditionally after
    it. So an INCONCLUSIVE result came back reading "PASS_MECHANISM (promoted from a
    shared seed)" with evidence_strength PARTIAL.
    """
    r = {"verdict": cmp.SHARED_SEED_CANDIDATE, "reason": reason,
         "legacy_first_divergence": {"phase": phase}}
    return cmp._promote_shared_seed(r) if hasattr(cmp, "_promote_shared_seed") else None


def test_a_non_promotable_phase_yields_a_consistent_refusal():
    d = {"rain_precip_cumulative": 0x77}
    legs = [_run("legacy", stages=_final()), _run("legacy", stages=_final(d)),
            _run("conservative", stages=_final()), _run("conservative", stages=_final(d))]
    for leg in legs:
        leg["problem"] = dict(_IDENT)
    r = cmp._adjudicate_normalized(*legs, promote=True)
    if r["verdict"] == "INCONCLUSIVE":
        assert "PASS_MECHANISM" not in r["reason"], (
            "a refusal must not be worded as a promotion — a reader taking the "
            "reason at face value would misread it")
        assert r.get("evidence_strength") in (None, "NONE")
        assert "not_established" not in r or not r["not_established"]


def test_a_missing_phase_is_not_promotable():
    # a shared seed always has a phase, so a missing one is malformed, not permissive
    assert cmp.promotable_phase(None) is False
    assert cmp.promotable_phase("op") is True


def test_the_four_case_cannot_be_assembled_by_hand():
    """Documenting of() as "the" path is not the same as making it the only one. A
    public dataclass constructor let a caller assemble the object from legs it built
    itself — which is exactly what the factory exists to prevent."""
    with pytest.raises(TypeError, match="built by VerifiedFourCase.of"):
        cmp.VerifiedFourCase(1, 2, 3, 4)


# -- the two comparison boundaries are different problems (owner PR A) ---------

def test_a_wrapper_leg_and_a_kernel_leg_are_not_the_same_problem():
    """The wrapper path applies kdm6's height-dependent CCN profile before the
    kernel; the C++ port has no counterpart, so the legs enter with different nccn.
    Mixing them compares two different numerical problems — which is what produced
    the dt=300 `outer_pre_sed.nccn` divergence in the first place."""
    r = cmp.adjudicate_verified.__wrapped__ if hasattr(
        cmp.adjudicate_verified, "__wrapped__") else None
    mixed = _four_legs(i0={"entry_boundary": fd.KERNEL_ENTRY})
    assert mixed["verdict"] == "INVALID_EVIDENCE"
    assert "same problem" in mixed["reason"]


def test_the_boundary_is_part_of_the_identity_not_beside_it():
    a = cmp.SedimentationIdentity.of(dict(_IDENT, entry_boundary=fd.KERNEL_ENTRY))
    b = cmp.SedimentationIdentity.of(dict(_IDENT, entry_boundary=fd.WRAPPER_INPUT))
    assert a != b, "the boundary must distinguish two otherwise-identical problems"
    assert cmp.SedimentationIdentity.of(_IDENT).entry_boundary == fd.WRAPPER_INPUT, (
        "a run that predates the kernel path is a wrapper run by construction")
