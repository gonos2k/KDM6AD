"""T2-6 창-선형화 API 검증 (유지 핸들 + 반복 vjp/jvp).

게이트:
  1. apply_adjoint ≡ run_da_window.adj_x0 (torch.equal) — 유지-핸들 경로와
     recompute 경로는 같은 fp64 결정론 그래프이므로 비트 일치해야 한다.
  2. 반복 재적용 무결성 — 같은 선형화에 다른 covector를 연속 적용해도 새
     선형화와 일치 (retain_graph 재적용이 그래프를 오염하지 않음).
  3. 창 전체 쌍대성 <u, M v> == <Mᵀ u, v> — 접선·수반이 같은 선형 연산자의
     양면임을 창 단위로 확인 (1e-12).
"""
from __future__ import annotations

import pytest
import torch

from kdm6.da_linearization import WindowLinearization
from kdm6.da_window import WindowConfig, run_da_window
from kdm6.state import State, Forcing

DT = 20.0
_F64 = dict(dtype=torch.float64)


def _t2(a, b):
    return torch.tensor([[a, b]], **_F64)


def _mk_state():
    return State(
        th=_t2(296.8, 282.4), qv=_t2(1.40e-2, 2.0e-3),
        qc=_t2(1.0e-3, 5.0e-4), qr=_t2(1.0e-4, 1.0e-5),
        qi=_t2(0.0, 1.0e-6), qs=_t2(0.0, 5.0e-5),
        qg=_t2(0.0, 1.0e-5), nccn=_t2(1.0e9, 1.0e9),
        nc=_t2(1.0e8, 1.0e8), ni=_t2(0.0, 1.0e8),
        nr=_t2(1.0e4, 1.0e3), bg=_t2(0.0, 0.0),
    )


def _mk_forcing():
    return Forcing(rho=_t2(1.089, 0.9567), pii=_t2(0.9704, 0.9031),
                   p=_t2(9.0e4, 7.0e4), delz=_t2(500.0, 500.0))


def _unit_state(seed):
    g = torch.Generator().manual_seed(seed)
    return State(*(torch.randn((1, 2), generator=g, **_F64)
                   for _ in State._fields))


def _dot(a: State, b: State) -> torch.Tensor:
    return sum((x * y).sum() for x, y in zip(a, b))


def test_apply_adjoint_equals_run_da_window():
    x0, forcings = _mk_state(), [_mk_forcing()] * 3
    obs = {1: _unit_state(11), 3: _unit_state(13)}
    ref = run_da_window(x0, forcings, lambda t, x: obs.get(t),
                        WindowConfig(dt=DT)).adj_x0
    with WindowLinearization(x0, forcings, dt=DT) as lin:
        adj = lin.apply_adjoint(obs)
    for k in State._fields:
        assert torch.equal(getattr(adj, k), getattr(ref, k)), k


def test_repeat_apply_is_uncorrupted():
    x0, forcings = _mk_state(), [_mk_forcing()] * 2
    u1, u2 = {2: _unit_state(21)}, {2: _unit_state(22), 0: _unit_state(23)}
    with WindowLinearization(x0, forcings, dt=DT) as lin:
        _ = lin.apply_adjoint(u1)                     # 1차 적용 (그래프 소비 시도)
        second = lin.apply_adjoint(u2)                # 2차 적용
    with WindowLinearization(x0, forcings, dt=DT) as fresh:
        ref = fresh.apply_adjoint(u2)
    for k in State._fields:
        assert torch.equal(getattr(second, k), getattr(ref, k)), k


def test_window_adjoint_tangent_duality():
    """<u, M v>|_T == <Mᵀ u, v>|_0 — 창 전체 선형 연산자 쌍대성 (1e-12)."""
    x0, forcings = _mk_state(), [_mk_forcing()] * 3
    u = _unit_state(31)                               # x_T 공간 covector
    v = _unit_state(32)                               # x_0 공간 tangent
    with WindowLinearization(x0, forcings, dt=DT) as lin:
        mv = lin.apply_tangent(v)["final"]            # M v (x_T 공간)
        mtu = lin.apply_adjoint({3: u})               # Mᵀ u (x_0 공간)
    lhs, rhs = float(_dot(u, mv)), float(_dot(mtu, v))
    denom = max(abs(lhs), abs(rhs), 1e-30)
    assert abs(lhs - rhs) / denom < 1e-12, (lhs, rhs)


def test_tangent_obs_times_convention():
    """apply_tangent의 t-시각 접선은 스텝 t 적용 전(x_t 공간) — t=0은 v0 자신."""
    x0, forcings = _mk_state(), [_mk_forcing()] * 2
    v = _unit_state(41)
    with WindowLinearization(x0, forcings, dt=DT) as lin:
        out = lin.apply_tangent(v, obs_times=[0, 2])
    for k in State._fields:
        assert torch.equal(getattr(out[0], k),
                           getattr(v, k).to(torch.float64)), k
    assert set(out) == {0, 2, "final"}
    for k in State._fields:
        assert torch.equal(getattr(out[2], k), getattr(out["final"], k)), k


def test_max_b_guard_and_close():
    big = State(**{k: torch.zeros((513, 2), **_F64) for k in State._fields})
    with pytest.raises(ValueError, match="max_b"):
        WindowLinearization(big, [_mk_forcing()], dt=DT)
    lin = WindowLinearization(_mk_state(), [_mk_forcing()], dt=DT)
    lin.close()
    with pytest.raises(RuntimeError, match="closed"):
        lin.apply_adjoint({1: _unit_state(1)})
