"""
첫 단계 smoke test — kdm6_torch가 import 되고, ops가 grad을 제대로 흘리는지만 확인.

ops.py와 state.py가 채워지면 이 테스트가 통과해야 함. 통과 후 본격 포팅 단계로.
"""
from __future__ import annotations

import pytest
import torch


def test_import():
    from kdm6 import constants, ops, state  # noqa: F401
    from kdm6 import Handle, Parameters, kdm6_fn, kdm6_step, make_parameters  # noqa: F401


def test_constants_have_expected_values():
    """Fortran 직역 정합 — 변경 없이 그대로인지."""
    from kdm6 import constants as c
    assert c.PEAUT == 0.40, "yhlee 조정값 (원본 0.55 → 0.40)"
    assert c.NCRK1 == 3.03e3
    assert c.NCRK2 == 2.59e15
    assert c.QCRMIN == 1.0e-9
    assert c.LAMDAIMAX == 1.82e6


def test_safe_div_basic():
    """safe_div가 0/0 보호 + 일반 case 통과."""
    from kdm6.ops import safe_div
    a = torch.tensor([1.0, 2.0, 3.0], dtype=torch.float64, requires_grad=True)
    b = torch.tensor([2.0, 4.0, 6.0], dtype=torch.float64)
    r = safe_div(a, b)
    r.sum().backward()
    assert a.grad is not None
    assert torch.allclose(r, torch.tensor([0.5, 0.5, 0.5], dtype=torch.float64))


def test_safe_div_signed_small_negative_denominator():
    """safe_div_signed가 작은 음수 분모에서 부호를 보존하고 finite를 유지."""
    from kdm6.ops import EPS, safe_div_signed

    num = torch.tensor([1.0], dtype=torch.float64)
    denom = torch.tensor([-EPS / 2.0], dtype=torch.float64)
    r = safe_div_signed(num, denom)

    assert torch.isfinite(r).all()
    assert r.item() < 0.0
    assert torch.allclose(r, torch.tensor([-1.0 / EPS], dtype=torch.float64))


def test_safe_sqrt_zero_boundary():
    """safe_sqrt(0)이 NaN 안 만들고 grad이 유한."""
    from kdm6.ops import safe_sqrt
    x = torch.tensor([0.0, 1.0, 4.0], dtype=torch.float64, requires_grad=True)
    r = safe_sqrt(x)
    r.sum().backward()
    assert torch.isfinite(r).all()
    assert torch.isfinite(x.grad).all()


def test_clip_positive_subgradient():
    """clip_positive(-x)의 grad이 0 (Type B stop-gradient 동작)."""
    from kdm6.ops import clip_positive
    x = torch.tensor([-1.0, 0.5, -0.1], dtype=torch.float64, requires_grad=True)
    y = clip_positive(x).sum()
    y.backward()
    # 음수 위치 grad = 0
    assert x.grad[0].item() == 0.0
    assert x.grad[2].item() == 0.0
    # 양수 위치 grad = 1
    assert x.grad[1].item() == 1.0


def test_smooth_minmod_eager_mode():
    """eager minmod가 표준 정의대로 작동."""
    from kdm6.ops import smooth_minmod
    # same sign: returns smaller magnitude with sign
    a = torch.tensor([2.0, -3.0, 1.0], dtype=torch.float64)
    b = torch.tensor([3.0, -1.0, 2.0], dtype=torch.float64)
    r = smooth_minmod(a, b, mode="eager")
    expected = torch.tensor([2.0, -1.0, 1.0], dtype=torch.float64)
    assert torch.allclose(r, expected)
    # opposite sign → 0
    a2 = torch.tensor([1.0, -1.0], dtype=torch.float64)
    b2 = torch.tensor([-1.0, 1.0], dtype=torch.float64)
    r2 = smooth_minmod(a2, b2, mode="eager")
    assert torch.allclose(r2, torch.zeros(2, dtype=torch.float64))


def test_clip_neg_default_off():
    """from_fortran_arrays 기본 동작은 음수 prognostic을 보존."""
    from kdm6.state import from_fortran_arrays

    def scalar3d(value: float) -> torch.Tensor:
        return torch.tensor([[[value]]], dtype=torch.float64)

    state = from_fortran_arrays(
        th=scalar3d(300.0),
        qv=scalar3d(1.0e-3),
        qc=scalar3d(-1.0e-12),
        qr=scalar3d(0.0),
        qi=scalar3d(0.0),
        qs=scalar3d(0.0),
        qg=scalar3d(0.0),
        nccn=scalar3d(100.0),
        nc=scalar3d(0.0),
        ni=scalar3d(0.0),
        nr=scalar3d(0.0),
        bg=scalar3d(0.0),
        im=1,
        kme=1,
        jme=1,
        requires_grad=False,
    )

    assert state.qc.item() == pytest.approx(-1.0e-12)


def test_zeros_like_state_preserves_shape_dtype():
    """zeros_like_state가 각 필드의 shape/dtype/device를 보존한 0 state를 만든다."""
    from kdm6.state import PROG_FIELDS, State, zeros_like_state

    base = torch.arange(6, dtype=torch.float64).reshape(2, 3)
    state = State(**{name: base + idx for idx, name in enumerate(PROG_FIELDS)})
    zeros = zeros_like_state(state)

    for name in PROG_FIELDS:
        original = getattr(state, name)
        zero_field = getattr(zeros, name)
        assert zero_field.shape == original.shape
        assert zero_field.dtype == original.dtype
        assert zero_field.device == original.device
        assert torch.allclose(zero_field, torch.zeros_like(original))


def test_state_dot_basic():
    """state_dot(s, s)는 12개 필드 squared norm의 합과 같다."""
    from kdm6.state import PROG_FIELDS, State, state_dot

    base = torch.arange(1, 7, dtype=torch.float64).reshape(2, 3)
    state = State(**{name: base + idx for idx, name in enumerate(PROG_FIELDS)})
    expected = torch.zeros((), dtype=torch.float64)
    for field in state:
        expected = expected + (field * field).sum()

    result = state_dot(state, state)

    assert result.shape == torch.Size([])
    assert torch.allclose(result, expected)


def test_kdm6_pure_per_column_mstep_independence():
    """1:1 fix #10 — per-column sedimentation mstep: a heterogeneous multi-column batch must
    equal the per-column (B=1) stack. With the old scalar mstep (=max over columns) the columns
    were coupled and diverged O(1e-1) at dt large enough for mstep>1; per-column mstep makes
    each column independent (off-column substeps gate to 0)."""
    from kdm6.state import State, Forcing
    from kdm6.runtime import _kdm6_pure, make_parameters
    B, K = 3, 4
    mk = lambda cv: torch.tensor([[v] * K for v in cv], dtype=torch.float64)
    # heterogeneous precip loadings -> different per-column fall speed -> different mstep
    s = State(th=mk([290., 290., 290.]), qv=mk([1.4e-2] * 3), qc=mk([1e-3] * 3),
              qr=mk([1e-5, 5e-3, 1e-3]), qi=mk([0.] * 3), qs=mk([0., 2e-3, 5e-4]),
              qg=mk([0., 1e-3, 2e-4]), nccn=mk([1e9] * 3), nc=mk([1e8] * 3),
              ni=mk([0.] * 3), nr=mk([1e4, 1e5, 5e4]), bg=mk([0.] * 3))
    f = Forcing(rho=mk([1.0] * 3), pii=mk([0.97] * 3), p=mk([9e4] * 3), delz=mk([500.] * 3))
    out_batched = _kdm6_pure(s, f, make_parameters(), dt=600.0)  # dt=600 -> loops>1, mstep>1
    for i in range(B):
        si = State(*[getattr(s, fl)[i:i + 1] for fl in s._fields])
        fi = Forcing(*[getattr(f, fl)[i:i + 1] for fl in f._fields])
        out_i = _kdm6_pure(si, fi, make_parameters(), dt=600.0)
        for fl in s._fields:
            assert torch.allclose(getattr(out_batched, fl)[i:i + 1], getattr(out_i, fl),
                                  rtol=1e-10, atol=1e-15), \
                f"#10 regressed: column {i} field {fl} differs (scalar-mstep coupling)"


def test_kdm6_pure_complete_rain_evap_nccn_budget():
    """1:1 NR->NCCN budget — a dry, sub-saturated, lightly-raining warm column evaporates its
    rain to completion in-step, firing the complete-rain-evap branch (warm.py rain_complete_evap
    -> coordinator NR->NCCN, coordinator.cpp:1170/1254): nr must zero, qr must zero, the evaporated
    rain-drop count must recycle into nccn (a 4D-Var-relevant CCN term), and evaporated mass must
    return to vapor. Matches C++ kdm6_fn on this exact IC to relΔ 4.53e-15 — see the [RAIN-EVAP]
    RCEOUT dump in kdm6_libtorch/tests/test_autograd_endtoend.cpp. This is the one driver branch
    the standard-IC CPPOUT parity (rce=0 there) cannot exercise. .item()-free (tensor ops only) per
    the autograd rule."""
    from kdm6.state import State, Forcing
    from kdm6.runtime import _kdm6_pure, make_parameters
    m = lambda v: torch.tensor([[v, v]], dtype=torch.float64)
    s = State(th=m(300.0), qv=m(2.0e-3), qc=m(0.0), qr=m(5.0e-6), qi=m(0.0),
              qs=m(0.0), qg=m(0.0), nccn=m(1.0e9), nc=m(0.0), ni=m(0.0),
              nr=m(1.0e4), bg=m(0.0))
    f = Forcing(rho=m(1.0), pii=m(0.97), p=m(9.0e4), delz=m(500.0))
    o = _kdm6_pure(s, f, make_parameters(), dt=120.0)
    assert torch.isfinite(o.nccn).all() and torch.isfinite(o.qr).all()
    assert (o.qr == 0).all(), "rain did not fully evaporate (rce branch did not fire)"
    assert (o.nr == 0).all(), "NR not zeroed after complete rain evaporation"
    folded = o.nccn - 1.0e9
    assert (folded > 1.0e3).all(), "evaporated NR did not recycle into NCCN"
    assert (folded < 1.0e4).all(), "NCCN gain exceeds the available rain-drop count"
    assert (o.qv > 2.0e-3).all(), "evaporated rain mass did not return to vapor"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
