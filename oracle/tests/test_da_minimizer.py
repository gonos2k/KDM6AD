"""T1-4 strong-constraint CVT + L-BFGS minimizer 검증 (docs/DA_REALTIME_PLAN.md).

전부 correctness 기반(타이밍 무관·실제 오라클 물리·(1,2) 미니 배치):
  1. closure gradient의 FD 대조 — CVT 체인룰(∂J/∂v = v + σ_b⊙adj_x0)이 창
     adjoint와 정확히 결합되는가 (창 adjoint 자체의 정확성은 test_da_window가
     full-graph autograd 일치로 이미 보증 — 여기선 그 위의 새 배관만 검증).
  2. twin experiment — 분석 증분 1회가 J를 낮추고(정밀 검토가 요구한 gate),
     관측 자유도에서 배경보다 진실에 가까워지는가.
  3. 무관측 창 → 분석 == 배경 (J_b 단독 최소점).
  4. σ_b=0 필드는 제어 제외 (배경 고정, bitwise).
"""
from __future__ import annotations

import torch

from kdm6.da_minimizer import MinimizeResult, cvt_to_state, run_minimizer, _stack
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


def _zeros_state(ref: State) -> State:
    return State(**{k: torch.zeros_like(v) for k, v in ref._asdict().items()})


def _sigma(th=0.0, qv=0.0) -> State:
    z = _zeros_state(_mk_state())
    return z._replace(th=torch.full_like(z.th, th), qv=torch.full_like(z.qv, qv))


def _obs_th_at(t_obs: int, y: torch.Tensor, sigma_o: float):
    """시각 t_obs에서 th 전체를 관측: j=½Σ((th−y)/σo)², adj=∂j/∂x_t."""
    def obs_eval(t: int, x_t: State):
        if t != t_obs:
            return None
        r = (x_t.th - y) / sigma_o
        j = 0.5 * (r * r).sum()
        adj = _zeros_state(x_t)._replace(th=r / sigma_o)
        return j, adj
    return obs_eval


def test_closure_gradient_matches_fd():
    """∂J/∂v (수동 CVT 체인룰) vs 중앙 FD — th·qv 제어성분 각 1개."""
    xb = _mk_state()
    forcings = [_mk_forcing()] * 2
    cfg = WindowConfig(dt=DT)
    b_sigma = _sigma(th=1.0, qv=2.0e-3)
    sig = _stack(b_sigma)
    truth_final = run_da_window(xb, forcings, lambda t, x: None, cfg).state_final
    y = truth_final.th + 0.3                       # 인위적 잔차
    obs_eval = _obs_th_at(2, y, sigma_o=0.5)

    def j_and_grad(v: torch.Tensor):
        x0 = cvt_to_state(xb, b_sigma, v)
        acc = []

        def obs_adjoint(t, x_t):
            out = obs_eval(t, x_t)
            if out is None:
                return None
            acc.append(out[0])
            return out[1]

        res = run_da_window(x0, forcings, obs_adjoint, cfg)
        j = 0.5 * (v * v).sum() + torch.stack(acc).sum()
        grad = v + sig * _stack(res.adj_x0)
        return float(j), grad

    v0 = torch.zeros_like(sig)
    v0[0, 0, 0] = 0.2                              # th 성분 비영점에서 검증
    v0[1, 0, 1] = -0.1                             # qv 성분
    _, g = j_and_grad(v0)
    h = 1.0e-5
    for (fi, bi, ki) in ((0, 0, 0), (1, 0, 1)):
        vp = v0.clone(); vp[fi, bi, ki] += h
        vm = v0.clone(); vm[fi, bi, ki] -= h
        fd = (j_and_grad(vp)[0] - j_and_grad(vm)[0]) / (2 * h)
        rel = abs(fd - float(g[fi, bi, ki])) / max(abs(fd), 1e-30)
        assert rel < 1.0e-5, (fi, bi, ki, fd, float(g[fi, bi, ki]), rel)


def test_twin_experiment_reduces_j_and_moves_toward_truth():
    """정밀 검토 gate: 분석 증분이 J_obs+J_b를 낮추고, 관측 dof(th)에서
    배경보다 진실에 가까워진다."""
    x_true = _mk_state()
    forcings = [_mk_forcing()] * 2
    cfg = WindowConfig(dt=DT)
    y = run_da_window(x_true, forcings, lambda t, x: None, cfg).state_final.th

    xb = x_true._replace(th=x_true.th + 0.8)       # 배경 오차 +0.8 K
    b_sigma = _sigma(th=1.0)
    res = run_minimizer(xb, forcings, _obs_th_at(2, y, sigma_o=0.1),
                        cfg, b_sigma, max_iter=15)

    assert isinstance(res, MinimizeResult)
    assert res.n_window_evals >= 2
    assert res.j_trace[-1] < res.j_trace[0], res.j_trace
    err_b = float((xb.th - x_true.th).abs().sum())
    err_a = float((res.x_analysis.th - x_true.th).abs().sum())
    assert err_a < err_b, (err_a, err_b)
    # 강한 관측(σo=0.1 ≪ σb=1.0) → 오차가 크게 줄어야 함
    assert err_a < 0.5 * err_b, (err_a, err_b)


def test_no_obs_window_returns_background():
    xb = _mk_state()
    res = run_minimizer(xb, [_mk_forcing()] * 2, lambda t, x: None,
                        WindowConfig(dt=DT), _sigma(th=1.0, qv=2.0e-3), max_iter=5)
    assert res.jobs_final == 0.0
    for k in State._fields:
        assert torch.equal(getattr(res.x_analysis, k), getattr(xb, k).to(torch.float64)), k


def test_zero_sigma_field_stays_at_background():
    x_true = _mk_state()
    forcings = [_mk_forcing()] * 2
    cfg = WindowConfig(dt=DT)
    y = run_da_window(x_true, forcings, lambda t, x: None, cfg).state_final.th
    xb = x_true._replace(th=x_true.th + 0.8, qr=x_true.qr * 1.5)
    res = run_minimizer(xb, forcings, _obs_th_at(2, y, sigma_o=0.1),
                        cfg, _sigma(th=1.0), max_iter=10)   # qr 등 σ=0
    for k in ("qv", "qc", "qr", "nccn", "bg"):
        assert torch.equal(getattr(res.x_analysis, k),
                           getattr(xb, k).to(torch.float64)), k
    assert not torch.equal(res.x_analysis.th, xb.th.to(torch.float64))
