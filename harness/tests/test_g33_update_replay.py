"""The qr update replay, and the mutations it must catch.

A fidelity check that cannot fail certifies nothing, so every property here is
paired with a perturbation that must break it.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_update_replay as rp  # noqa: E402

DT = 100.0


def _cell(qr_pre=1.0e-7, **rates):
    ops = {n: 0.0 for _s, n in rp.COLD_TERMS + rp.WARM_TERMS}
    ops.update(rates)
    return rp.bits32(qr_pre), ops


# ── the branch, recomputed rather than trusted ────────────────────────────────

def test_the_branch_comes_from_the_recorded_temperature():
    assert rp.is_cold(rp.bits32(243.0))
    assert not rp.is_cold(rp.bits32(300.0))


def test_the_boundary_goes_to_COLD_because_Fortran_uses_le():
    """Fortran F:2638 is `t <= t0c`; the C++ gates on `supcol > 0`, i.e. `t < t0c`.

    They disagree at exactly t == t0c, and this replay follows the REFERENCE. The
    disagreement is a real contract gap that needs its own threshold fixture and an
    owner decision — encoding it here as a passing assertion is how it stays visible
    instead of becoming a silent convention.
    """
    assert rp.is_cold(rp.bits32(rp.T0C)), "t == t0c must take the cold arm (Fortran)"
    assert not rp.is_cold(np.uint32(rp.bits32(rp.T0C) + 1).item()), "one ULP above is warm"


@pytest.mark.parametrize("cold", [True, False])
def test_only_the_taken_arms_operands_are_branch_active(cold):
    active = rp.branch_active_fields(cold)
    assert {"praut", "pracw", "prevp"} <= active, "the three common terms"
    if cold:
        assert "paacw" not in active and "pseml" not in active
        assert {"piacr", "pgacr", "psacr", "pmulrs", "pmulrg"} <= active
    else:
        assert "piacr" not in active and "psacr" not in active
        assert {"paacw", "pseml", "pgeml"} <= active


# ── the arithmetic ────────────────────────────────────────────────────────────

def test_paacw_is_added_TWICE_not_doubled():
    """`+paacw+paacw` and `+2*paacw` differ in f32 association, and the source has
    the first. A replay that folded them would pass on most values and drift on the
    ones where the intermediate rounds differently."""
    a = np.float32(1.0)
    b = np.float32(np.nextafter(np.float32(3.0e-8), np.float32(1)))
    twice = np.float32(np.float32(a + b) + b)
    doubled = np.float32(a + np.float32(2.0) * b)
    assert twice != doubled, "pick a value where the two forms actually differ"
    ops = {n: 0.0 for _s, n in rp.WARM_TERMS}
    ops["paacw"] = float(b)
    assert rp.rate_sum(ops, cold=False) == np.float32(np.float32(np.float32(0) + b) + b)


def test_the_clamp_is_applied():
    qr, ops = _cell(qr_pre=1.0e-9, prevp=-1.0)      # drives the sum far negative
    assert rp.replay_qr(qr, ops, DT, cold=True) == rp.bits32(0.0)


def test_a_reordered_sum_is_not_the_same_answer():
    """f32 addition is not associative, so the ORDER in COLD_TERMS is a claim about
    the source. Show the claim has content."""
    # A cancelling pair with a tiny term that survives in one order and not the
    # other: forward, praut is absorbed by pracw and the pair cancels to 0;
    # reversed, the pair cancels first and praut survives.
    ops = {n: 0.0 for _s, n in rp.COLD_TERMS}
    ops.update(praut=1.0e-9, pracw=1.0, prevp=-1.0)
    forward = rp.rate_sum(ops, cold=True)
    s = np.float32(0.0)
    for sign, name in reversed(rp.COLD_TERMS):
        v = np.float32(ops[name])
        s = np.float32(s + v) if sign == "+" else np.float32(s - v)
    assert forward != s, "this fixture does not distinguish the orders"


# ── verify_leg, and the mutations it must catch ───────────────────────────────

def _leg(qr_pre=1.0e-7, t=243.0, praut=2.0e-10):
    pre = {("qr", 1, 0): rp.bits32(qr_pre), ("t", 1, 0): rp.bits32(t)}
    operands = {(n, 1, 0): rp.bits32(0.0)
                for _s, n in rp.COLD_TERMS + rp.WARM_TERMS}
    operands[("praut", 1, 0)] = rp.bits32(praut)
    cold = rp.is_cold(rp.bits32(t))
    ops = {n: rp.f32(operands[(n, 1, 0)])
           for n in rp.branch_active_fields(cold)}
    post = {("qr", 1, 0): rp.replay_qr(pre[("qr", 1, 0)], ops, DT, cold)}
    return pre, operands, post


def test_a_consistent_leg_replays_exactly():
    pre, operands, post = _leg()
    assert rp.verify_leg(pre, operands, post, DT) == []


def test_a_one_ULP_perturbation_of_the_BASE_STATE_fails():
    """The owner-required mutation: the whole reason micro_pre_state_update exists
    is that the base was not sealed, so a 1-ULP change to it must be detected."""
    pre, operands, post = _leg()
    pre = dict(pre)
    pre[("qr", 1, 0)] = pre[("qr", 1, 0)] + 1
    bad = rp.verify_leg(pre, operands, post, DT)
    assert len(bad) == 1 and bad[0]["branch"] == "cold"


def test_a_one_ULP_perturbation_of_an_ACTIVE_operand_fails():
    pre, operands, post = _leg()
    operands = dict(operands)
    operands[("praut", 1, 0)] = operands[("praut", 1, 0)] + 1
    assert rp.verify_leg(pre, operands, post, DT)


def test_perturbing_an_INACTIVE_operand_does_NOT_fail():
    """A cold cell's qr does not read paacw. If perturbing it broke the replay, the
    replay would be reading the wrong arm."""
    pre, operands, post = _leg(t=243.0)
    operands = dict(operands)
    operands[("paacw", 1, 0)] = rp.bits32(1.0e-3)
    assert rp.verify_leg(pre, operands, post, DT) == []


def test_a_missing_operand_raises_rather_than_passing():
    pre, operands, post = _leg()
    operands = {k: v for k, v in operands.items() if k[0] != "psacr"}
    with pytest.raises(ValueError, match="psacr"):
        rp.verify_leg(pre, operands, post, DT)


def test_a_warm_cell_uses_the_warm_arm():
    pre, operands, post = _leg(t=300.0)
    assert rp.verify_leg(pre, operands, post, DT) == []
    operands = dict(operands)
    operands[("paacw", 1, 0)] = rp.bits32(1.0e-9)   # active in the warm arm
    assert rp.verify_leg(pre, operands, post, DT)
