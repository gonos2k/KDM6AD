"""The activity filter must exclude what the arithmetic did not read — and nothing else.

A filter that excludes too much hides real divergences, which is strictly worse
than the problem it solves. So every exclusion here is paired with a case that
must survive it.
"""
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_activity as act        # noqa: E402
import g33_update_replay as rp    # noqa: E402


def _f64bits(x):
    return struct.unpack("<Q", struct.pack("<d", float(x)))[0]


def _run(freeze_rates=(0.0, 0.0, 0.0), t=243.0, loop=1, col=1, k=0):
    stages = [{"stage": "micro_freeze_heat", "loop": loop, "col": col, "k": k,
               "field": f, "bits": rp.bits32(v)}
              for f, v in (("t_pre_freeze", t), ("xlf", 3.34e5),
                           ("cpm", 1005.0), ("phom", 0.0))]
    stages += [{"stage": "micro_freeze_heat", "loop": loop, "col": col, "k": k,
                "field": n, "bits": _f64bits(v)}
               for n, v in zip(act._FREEZE_RATES, freeze_rates)]
    stages += [{"stage": "micro_pre_state_update", "loop": loop, "col": col,
                "k": k, "field": "t", "bits": rp.bits32(t)}]
    stages += [{"stage": "micro_qr_operands", "loop": loop, "col": col, "k": k,
                "field": n, "bits": rp.bits32(0.0)}
               for n in ("praut", "prevp", "psacr", "paacw", "pseml", "cold_gate")]
    return {"stages": stages}


def _ids(run):
    return {i[6] for i in act.noncausal_stage_records(run)}


# ── micro_freeze_heat: the coefficient is only read when something freezes ────

def test_the_coefficients_are_noncausal_when_no_rate_fires():
    """The exact v14 case: a 289 K cell where xlf differs and is multiplied by 0."""
    assert _ids(_run(freeze_rates=(0.0, 0.0, 0.0))) >= {"xlf", "cpm"}


def test_the_coefficients_are_CAUSAL_when_any_rate_fires():
    """One nonzero rate is enough — this is where the real seed was."""
    for rates in ((1e-9, 0, 0), (0, 1e-9, 0), (0, 0, 1e-9)):
        assert not ({"xlf", "cpm"} & _ids(_run(freeze_rates=rates))), rates


def test_the_rates_themselves_are_never_excluded():
    """A rate that differs, differs — there is no cell where it is not read."""
    assert not (set(act._FREEZE_RATES) & _ids(_run(freeze_rates=(0.0, 0.0, 0.0))))


def test_an_incomplete_record_is_left_VISIBLE():
    """Missing evidence must not be read as 'inactive'; that would let a truncated
    dump quietly suppress its own gaps."""
    run = _run(freeze_rates=(0.0, 0.0, 0.0))
    run["stages"] = [r for r in run["stages"] if r["field"] != "pfrzdtr"]
    assert not ({"xlf", "cpm"} & _ids(run))


# ── micro_qr_operands: only the taken arm ────────────────────────────────────

def test_a_cold_cell_excludes_the_warm_only_operands():
    ex = _ids(_run(t=243.0))
    assert {"paacw", "pseml"} <= ex
    assert "psacr" not in ex and "praut" not in ex


def test_a_warm_cell_excludes_the_cold_only_operands():
    ex = _ids(_run(t=300.0))
    assert "psacr" in ex
    assert "paacw" not in ex and "praut" not in ex


def test_the_common_operands_are_never_excluded():
    for t in (243.0, 300.0):
        assert "prevp" not in _ids(_run(t=t)) and "praut" not in _ids(_run(t=t))


def test_cold_gate_is_always_shown():
    """It is the producer's own claim about its branch, and a claim is evidence
    about the producer whether or not it turns out to match.

    An earlier version of this docstring said it was "the evidence that the two
    backends disagree at t == t0c". That disagreement was withdrawn: the C++
    predicate is `supcol >= 0` (coordinator.cpp:1737), i.e. `t <= t0c`, the same
    as Fortran F:2638 — and near t0c the subtraction is exact in f32, so `supcol`
    adds no rounding either. What this field now verifies is that the two
    predicates AGREE, boundary included."""
    for t in (243.0, 300.0):
        assert "cold_gate" not in _ids(_run(t=t))


def test_no_base_state_leaves_the_operands_VISIBLE():
    run = _run(t=243.0)
    run["stages"] = [r for r in run["stages"]
                     if r["stage"] != "micro_pre_state_update"]
    assert not ({"paacw", "pseml"} & _ids(run))


# ── scope ─────────────────────────────────────────────────────────────────────

def test_only_stages_with_a_RULE_are_touched():
    """A stage the module knows nothing about must contribute no exclusions, so
    adding one cannot silently start hiding differences."""
    run = _run()
    run["stages"].append({"stage": "outer_post_micro", "loop": 1, "col": 1,
                          "k": 0, "field": "qr", "bits": 0})
    assert all(i[0] in ("micro_freeze_heat", "micro_qr_operands")
               for i in act.noncausal_stage_records(run))


def test_the_identity_shape_matches_the_comparators():
    """The filter works by identity equality, so a layout drift would silently
    exclude nothing at all — which is exactly how a guard becomes vacuous."""
    ids = act.noncausal_stage_records(_run())
    assert ids
    for i in ids:
        assert len(i) == 8 and i[2] == "-" and i[3] == 0


# ── the EXACT counterfactual (owner review §8) ───────────────────────────────
#
# "is some rate nonzero" is a proxy. The question is whether the coefficient
# difference survives the three f32 stores, and a nonzero rate can be far too
# small for that. These exercise the two-run path; the tests above exercise the
# one-run fallback, which excludes strictly less.

def _pair(rate, xlf_f=3.34e5, xlf_c=3.34e5):
    f = _run(freeze_rates=(0.0, 0.0, rate))
    c = _run(freeze_rates=(0.0, 0.0, rate))
    for st in c["stages"]:
        if st["stage"] == "micro_freeze_heat" and st["field"] == "xlf":
            st["bits"] = rp.bits32(xlf_c)
    for st in f["stages"]:
        if st["stage"] == "micro_freeze_heat" and st["field"] == "xlf":
            st["bits"] = rp.bits32(xlf_f)
    return f, c


def _co(f, c):
    return {i[6] for i in act.noncausal_stage_records(f, c)}


def test_a_coefficient_that_moves_t_is_CAUSAL():
    f, c = _pair(rate=1.0e-3, xlf_c=3.40e5)     # big enough to tip the store
    assert not ({"xlf", "cpm"} & _co(f, c))


def test_a_NONZERO_rate_too_small_to_move_t_is_NOT_causal():
    """The case the any-rate-nonzero proxy gets wrong: the formula reads the
    coefficient, but no difference in it survives the rounding, so it cannot be the
    load-bearing operand of this divergence."""
    f, c = _pair(rate=1.0e-30, xlf_c=3.40e5)
    assert {"xlf", "cpm"} <= _co(f, c)
    # ...and the weaker one-run rule keeps it, which is why the pair matters
    assert not ({"xlf", "cpm"} & _ids(f))


def test_identical_coefficients_are_never_causal():
    f, c = _pair(rate=1.0e-3)                    # same xlf on both sides
    assert {"xlf", "cpm"} <= _co(f, c)


def test_a_missing_counterpart_falls_back_and_excludes_LESS():
    f, c = _pair(rate=1.0e-3, xlf_c=3.40e5)
    c["stages"] = [s for s in c["stages"] if s["stage"] != "micro_freeze_heat"]
    assert not ({"xlf", "cpm"} & _co(f, c)), "fallback must not start hiding things"
