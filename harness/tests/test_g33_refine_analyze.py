"""The refinement analyzer, and the design rule that makes a sweep a refinement.

The §9 sweep as specified does not refine — the kernel picks its own internal step
from `delt`, and 1/2/3/6/12 maps onto dtcld 100/150/100/50/25. A test suite that
only checked the arithmetic would have passed while the experiment measured
nothing, so the design rule is asserted here alongside it.
"""
import math
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_refine_analyze as ra   # noqa: E402

DTCLDCR = 120.0


def dtcld(delt):
    """The kernel's own internal step (F:930-932), which is what refines."""
    loops = max(int(delt / DTCLDCR + 0.5), 1)
    return delt if delt <= DTCLDCR else delt / loops


# ── the design rule ──────────────────────────────────────────────────────────

def test_the_sweep_as_specified_is_not_a_refinement():
    """N=2 integrates COARSER than N=1 and N=3 duplicates N=1. Measured on this
    sequence, the error to the finest is non-monotone, which reads as an operator
    that does not converge and is a sweep that does not refine."""
    steps = [dtcld(300 / n) for n in (1, 2, 3, 6, 12)]
    assert steps == [100.0, 150.0, 100.0, 50.0, 25.0]
    assert steps[1] > steps[0], "N=2 is coarser than N=1"
    assert steps[2] == steps[0], "N=3 duplicates N=1"
    assert steps != sorted(steps, reverse=True), "not monotonically refining"


def test_N2_exceeds_the_kernels_own_stability_criterion():
    """nint(150/120) = 1, and the delt <= dtcldcr guard does not apply, so the
    member runs a 150 s step against the code's own 120 s limit."""
    assert dtcld(150.0) == 150.0 > DTCLDCR


def test_the_corrected_chain_halves_cleanly():
    steps = [dtcld(300 / n) for n in (3, 6, 12, 24)]
    assert steps == [100.0, 50.0, 25.0, 12.5]
    for a, b in zip(steps, steps[1:]):
        assert a == 2 * b


def test_the_policy_control_pair_shares_an_internal_step():
    """N=1 and N=3 integrate identically (three 100 s steps) and differ only in how
    many times the coefficients are refreshed. That is what makes the pair a
    controlled contrast rather than two more sweep members."""
    assert dtcld(300.0) == dtcld(100.0) == 100.0
    assert max(int(300.0 / DTCLDCR + 0.5), 1) == 3     # N=1: one call, 3 subcycles
    assert max(int(100.0 / DTCLDCR + 0.5), 1) == 1     # N=3: three calls, 1 each


def test_the_split_is_exact_in_f32_for_every_member():
    """A member carrying a division rounding the others do not would put a
    difference into the sequence that is not the operator's."""
    for n in (1, 2, 3, 4, 6, 12, 24):
        q = struct.unpack("<f", struct.pack("<f", 300.0 / n))[0]
        assert q == 300.0 / n, n


# ── the analyzer ─────────────────────────────────────────────────────────────

def _run(**vals):
    return {("state", f, 1, 0): v for f, v in vals.items()}


def test_order_is_log2_of_the_error_ratio():
    s = {100.0: 4.0, 50.0: 2.0, 25.0: 1.0}
    assert [round(p, 9) for _, _, _, p in ra.orders(s)] == [1.0, 1.0]


def test_second_order_reads_as_two():
    s = {100.0: 4.0, 50.0: 1.0}
    assert round(ra.orders(s)[0][3], 9) == 2.0


def test_a_bit_identical_member_reports_no_order_rather_than_zero():
    """A zero difference means two members agree to the last bit. That is an
    absence of the signal a rate describes, not a rate of zero — and log2(0) would
    otherwise raise or produce -inf."""
    assert ra.orders({100.0: 0.0, 50.0: 1.0})[0][3] is None
    assert ra.orders({100.0: 1.0, 50.0: 0.0})[0][3] is None


def test_non_halving_neighbours_are_skipped():
    """p = log2(E_h/E_h2) is only an order when the step actually halved. 100->75
    is a 4/3 ratio and reporting it as an order would misstate the exponent."""
    assert ra.orders({100.0: 4.0, 75.0: 2.0}) == []


def test_mass_and_number_are_reported_separately():
    """A mass field and a number moment can converge at different rates, and
    averaging them hides exactly the number-moment behaviour the conservative-nr
    blocker is about."""
    assert not set(ra.MASS) & set(ra.NUMBER)
    r = _run(qr=1.0, nr=2.0)
    assert ra._keys(r, "mass") != ra._keys(r, "number")


def test_the_norm_is_a_max_not_a_mean():
    """Most cells of an arithmetic-synthetic fixture are quiet; a mean would
    mostly measure how many."""
    a = {("state", "qr", 1, k): 0.0 for k in range(10)}
    b = dict(a); b[("state", "qr", 1, 3)] = 1.0
    assert ra._norm(a, b, list(a)) == 1.0


def test_successive_pairs_are_derived_not_hardcoded():
    """The doubling pairs must follow the members present — a hardcoded list built
    for 1/2/3/6/12 silently drops the 12->24 estimate the corrected chain adds."""
    runs = {n: _run(qr=float(n)) for n in (3, 6, 12, 24)}
    got = ra.successive(runs)["mass"]
    assert set(got) == {100.0, 50.0, 25.0}


def test_error_to_finest_uses_the_actual_finest_member(tmp_path):
    runs = {n: _run(qr=float(n)) for n in (3, 6, 12, 24)}
    got = ra.to_finest(runs)["mass"]
    assert 12.5 not in got, "the finest member is the reference, not a data point"
    assert set(got) == {100.0, 50.0, 25.0}
