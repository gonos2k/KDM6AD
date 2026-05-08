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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
