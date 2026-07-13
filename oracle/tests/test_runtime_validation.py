"""Runtime input-validation contract (external review P1-2 / P1-3, Python side).

The operational C++/ABI path is code-frozen (mp37<->mp137 f32 parity), so these
guards live at the Python oracle boundary. For VALID inputs the numerical path
is unchanged (byte-identical) — the guards only fire on out-of-contract input
that would otherwise silently mis-compute:

  * dt<=0 was a "no-op" that still round-tripped th through t=th*pii then
    th=t/pii — NOT bitwise identity; a true no-op returns the input state.
  * NaN/Inf dt and NaN/Inf ncmin_* were accepted and poisoned the run.
  * xland was flattened + expand_as, so a scalar (numel 1) silently broadcast
    one land/sea regime over every column instead of erroring.
"""
from __future__ import annotations

import math

import pytest
import torch

from kdm6.runtime import _kdm6_pure, make_parameters
from kdm6.state import Forcing, State

_F64 = dict(dtype=torch.float64)


def _mk(B=3, K=4):
    mk = lambda v: torch.full((B, K), float(v), **_F64)
    s = State(th=mk(290.0), qv=mk(1.4e-2), qc=mk(1e-3), qr=mk(1e-4),
              qi=mk(0.0), qs=mk(0.0), qg=mk(0.0), nccn=mk(1e9), nc=mk(1e8),
              ni=mk(0.0), nr=mk(1e4), bg=mk(0.0))
    f = Forcing(rho=mk(1.0), pii=mk(0.97), p=mk(9e4), delz=mk(500.0))
    return s, f


@pytest.mark.parametrize("dt", [0.0, -1.0, -600.0])
def test_dt_nonpositive_is_exact_bitwise_noop(dt):
    """dt<=0 returns the input state UNCHANGED — every field bitwise equal.
    The Exner value 0.9000000000000007 is chosen so the OLD path's
    th = (th*pii)/pii = 290.00000000000006 != 290.0 — i.e. the round-trip
    was demonstrably NOT a bitwise no-op; the direct return fixes it."""
    s, f = _mk()
    f = f._replace(pii=torch.full_like(f.pii, 0.9000000000000007))
    assert not torch.equal((s.th * f.pii) / f.pii, s.th)   # round-trip shifts
    out = _kdm6_pure(s, f, make_parameters(), dt=dt)
    for name in State._fields:
        assert torch.equal(getattr(out, name), getattr(s, name)), name


@pytest.mark.parametrize("dt", [float("nan"), float("inf"), float("-inf")])
def test_dt_nonfinite_rejected(dt):
    s, f = _mk()
    with pytest.raises(ValueError, match="dt"):
        _kdm6_pure(s, f, make_parameters(), dt=dt)


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_ncmin_nonfinite_rejected(bad):
    s, f = _mk()
    with pytest.raises(ValueError, match="ncmin_land"):
        _kdm6_pure(s, f, make_parameters(), dt=60.0, ncmin_land=bad)
    with pytest.raises(ValueError, match="ncmin_sea"):
        _kdm6_pure(s, f, make_parameters(), dt=60.0, ncmin_sea=bad)


def test_ncmin_negative_rejected():
    s, f = _mk()
    with pytest.raises(ValueError, match="ncmin"):
        _kdm6_pure(s, f, make_parameters(), dt=60.0, ncmin_land=-1.0)


def test_xland_must_be_one_value_per_column():
    """A scalar xland (numel 1) must NOT broadcast one regime over B columns
    — the contract is one value per column (numel == B)."""
    s, f = _mk(B=3)
    xland = torch.tensor([2.0], **_F64)              # scalar — would broadcast
    with pytest.raises(ValueError, match="xland"):
        _kdm6_pure(s, f, make_parameters(), dt=60.0, xland=xland)


def test_xland_nonfinite_rejected():
    s, f = _mk(B=3)
    xland = torch.tensor([1.0, float("nan"), 2.0], **_F64)
    with pytest.raises(ValueError, match="xland"):
        _kdm6_pure(s, f, make_parameters(), dt=60.0, xland=xland)


def test_xland_correct_shape_accepted():
    s, f = _mk(B=3)
    xland = torch.tensor([1.0, 2.0, 1.0], **_F64)     # one per column: fine
    out = _kdm6_pure(s, f, make_parameters(), dt=60.0, xland=xland)
    assert out.th.shape == s.th.shape
    # (B, K) column-shaped xland is also one-per-column and accepted
    out2 = _kdm6_pure(s, f, make_parameters(), dt=60.0,
                      xland=xland.reshape(3, 1))
    assert out2.th.shape == s.th.shape
