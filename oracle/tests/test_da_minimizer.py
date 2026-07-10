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

import pytest
import torch

from kdm6.da_cvt import CVT_LINEAR, U64, cvt_apply, make_default_cvt
from kdm6.da_minimizer import MinimizeResult, cvt_to_state, run_minimizer, _stack
from kdm6.da_window import WindowConfig, run_da_window
from kdm6.state import State, Forcing

from _cvt_test_util import fd_check

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


# ── full-field KDM6 CVT (hybrid add/mul spec) ────────────────────────────────


def _obs_field_at(t_obs: int, field: str, y: torch.Tensor, sigma_o: float):
    """시각 t_obs에서 임의 필드 전체를 관측 (합성 H=identity on field)."""
    def obs_eval(t: int, x_t: State):
        if t != t_obs:
            return None
        r = (getattr(x_t, field) - y) / sigma_o
        j = 0.5 * (r * r).sum()
        adj = _zeros_state(x_t)._replace(**{field: r / sigma_o})
        return j, adj
    return obs_eval


def test_closure_gradient_matches_fd_full_field():
    """T11: 11개 σ>0 필드 전부 — 하이브리드 CVT 체인룰 vs 도출-허용오차 FD."""
    xb = _mk_state()._replace(ni=_t2(0.0, 1.0e4))     # ni 셀1: cap headroom 확보
    spec, b_sigma = make_default_cvt(xb, enable_indirect=True,
                                     sigma_overrides={"nccn": 0.3})
    forcings = [_mk_forcing()] * 2
    cfg = WindowConfig(dt=DT)
    truth_final = run_da_window(xb, forcings, lambda t, x: None, cfg).state_final
    y = truth_final.th + 0.3
    obs_eval = _obs_th_at(2, y, sigma_o=0.5)

    def j_and_grad(v: torch.Tensor):
        x0, jac = cvt_apply(xb, b_sigma, v, spec)
        acc = []

        def obs_adjoint(t, x_t):
            out = obs_eval(t, x_t)
            if out is None:
                return None
            acc.append(out[0])
            return out[1]

        res = run_da_window(x0, forcings, obs_adjoint, cfg)
        j = 0.5 * (v * v).sum() + torch.stack(acc).sum()
        return float(j), v + jac * _stack(res.adj_x0)

    controlled = [f for f in State._fields
                  if float(getattr(b_sigma, f).abs().max()) > 0.0]
    assert len(controlled) == 11 and "bg" not in controlled
    v0 = torch.zeros((12, 1, 2), **_F64)
    for f in controlled:
        v0[State._fields.index(f), 0, 1] = 0.1     # 셀 (0,1): 전 필드 σ>0
    _, g = j_and_grad(v0)

    tiers = {}
    for f in controlled:
        idx = (State._fields.index(f), 0, 1)
        tiers[f] = fd_check(lambda v: j_and_grad(v)[0], v0, idx, float(g[idx]))
    assert tiers["th"] == "strong" and tiers["qv"] == "strong", tiers


def test_no_obs_window_returns_background_spec():
    """T12: 전 필드 spec + 무관측 → 분석 == 배경 bitwise, n_created 전부 0."""
    xb = _mk_state()
    spec, b_sigma = make_default_cvt(xb)
    res = run_minimizer(xb, [_mk_forcing()] * 2, lambda t, x: None,
                        WindowConfig(dt=DT), b_sigma, max_iter=5, cvt=spec)
    assert res.jobs_final == 0.0
    for k in State._fields:
        assert torch.equal(getattr(res.x_analysis, k),
                           getattr(xb, k).to(torch.float64)), k
    assert res.cvt is not None
    assert all(n == 0 for n in res.cvt["n_created"].values())


def test_run_minimizer_all_add_spec_bitwise_matches_none():
    """T13: cvt=None vs cvt=CVT_LINEAR — run 수준 bitwise 잠금 (lockstep pin)."""
    x_true = _mk_state()
    forcings = [_mk_forcing()] * 2
    cfg = WindowConfig(dt=DT)
    y = run_da_window(x_true, forcings, lambda t, x: None, cfg).state_final.th
    xb = x_true._replace(th=x_true.th + 0.8)
    b_sigma = _sigma(th=1.0)
    r0 = run_minimizer(xb, forcings, _obs_th_at(2, y, sigma_o=0.1),
                       cfg, b_sigma, max_iter=15)
    r1 = run_minimizer(xb, forcings, _obs_th_at(2, y, sigma_o=0.1),
                       cfg, b_sigma, max_iter=15, cvt=CVT_LINEAR)
    for k in State._fields:
        assert torch.equal(getattr(r0.x_analysis, k),
                           getattr(r1.x_analysis, k)), k
    assert torch.equal(r0.v, r1.v)
    assert r0.j_trace == r1.j_trace
    assert r0.cvt is None and r1.cvt is not None


def test_zero_direct_fields_prior_pinned_t0_only():
    """T14: t=0 단독 th 관측 → M^T 경유조차 없는 필드의 v 행은 정확히 0
    (zero-row 불변) + 분석 배경 고정 bitwise."""
    xb = _mk_state()
    spec, b_sigma = make_default_cvt(xb, enable_indirect=True)
    y = xb.th - 0.5
    res = run_minimizer(xb, [_mk_forcing()] * 2,
                        _obs_th_at(0, y, sigma_o=0.5),
                        WindowConfig(dt=DT), b_sigma, max_iter=8, cvt=spec)
    for f in ("qr", "qg", "nr", "qc", "qv"):       # t=0 th 관측 → th 외 covector 0
        fi = State._fields.index(f)
        assert float(res.v[fi].abs().max()) == 0.0, f
        assert torch.equal(getattr(res.x_analysis, f), getattr(xb, f)), f
    assert not torch.equal(res.x_analysis.th, xb.th)


def test_active_fields_sigma_mismatch_spec_only():
    """T15: active_fields와 σ>0 불일치 — spec 경로만 ValueError, 레거시는 허용."""
    xb = _mk_state()
    spec, b_sigma = make_default_cvt(xb)           # qv/qc 등 σ>0
    cfg = WindowConfig(dt=DT, active_fields=("th",))
    with pytest.raises(ValueError):
        run_minimizer(xb, [_mk_forcing()] * 2, lambda t, x: None, cfg,
                      b_sigma, max_iter=2, cvt=spec)
    res = run_minimizer(xb, [_mk_forcing()] * 2, lambda t, x: None, cfg,
                        b_sigma, max_iter=2)       # 승인된 레거시 패턴 — 무예외
    assert res.jobs_final == 0.0


def test_ni_cap_crossing_selfheals():
    """T16: entry clamp(ni≤1e6) 위 관측 견인 — 예외 없이 완료, 유한, J 비증가."""
    xb = _mk_state()._replace(ni=_t2(3.0e5, 3.0e5))
    spec, b_sigma = make_default_cvt(xb)
    assert float(b_sigma.ni.min()) > 0.0           # 3e5·e^{0.9} < 1e6 → V4 통과
    y = torch.full_like(xb.ni, 2.0e6)              # cap 위 — 도달 불가
    res = run_minimizer(xb, [_mk_forcing()] * 2,
                        _obs_field_at(1, "ni", y, sigma_o=1.0e5),
                        WindowConfig(dt=DT), b_sigma, max_iter=8, cvt=spec)
    ni_i = State._fields.index("ni")
    assert float(res.v[ni_i].abs().max()) < 40.0
    for f in State._fields:
        assert bool(torch.isfinite(getattr(res.x_analysis, f)).all()), f
    assert res.j_trace[-1] <= res.j_trace[0]


def test_minimizer_qcrmin_crossing_robust():
    """T24: QCRMIN(1e-9) 근방 qr을 바닥 아래로 견인 — 분기 플립 강건성."""
    xb = _mk_state()._replace(qr=_t2(5.0e-9, 5.0e-9))
    spec, b_sigma = make_default_cvt(xb, enable_indirect=True)
    y = torch.zeros_like(xb.qr)
    res = run_minimizer(xb, [_mk_forcing()] * 2,
                        _obs_field_at(1, "qr", y, sigma_o=1.0e-9),
                        WindowConfig(dt=DT), b_sigma, max_iter=8, cvt=spec)
    for f in State._fields:
        assert bool(torch.isfinite(getattr(res.x_analysis, f)).all()), f
    assert res.j_trace[-1] <= res.j_trace[0]


def test_eps_creation_and_removal_mechanism_synthetic_obs():
    """T25: ε>0 생성/제거 메커니즘 — 합성 필드 관측 전용.

    frozen all-sky H 경유 생성을 입증하지 않는다(cfrac detached gate — da_cvt
    docstring ceiling 참조). 여기서는 CVT 메커니즘 자체만 검증한다.
    """
    eps = 1.0e-5
    forcings = [_mk_forcing()] * 2
    cfg = WindowConfig(dt=DT)

    # 생성: xb.qc ≡ 0 + ε>0 → σ 유지(V3), 관측이 qc>0 생성
    xb = _mk_state()._replace(qc=_t2(0.0, 0.0))
    spec, b_sigma = make_default_cvt(xb, eps_overrides={"qc": eps})
    assert float(b_sigma.qc.min()) > 0.0
    y = torch.full_like(xb.qc, 2.0e-4)
    res = run_minimizer(xb, forcings, _obs_field_at(1, "qc", y, sigma_o=1.0e-5),
                        cfg, b_sigma, max_iter=10, cvt=spec)
    assert float(res.x_analysis.qc.max()) > 0.0
    assert res.j_trace[-1] < res.j_trace[0]
    assert res.cvt["n_created"]["qc"] > 0

    # 제거 쌍둥이: xb.qc > 0 → y=0, ratio 바닥 + −ε 하계 감사.
    # t=0 직접 관측으로 메커니즘만 프로브 — t=1 관측은 KDM6 스텝의 qc 재생성
    # 때문에 J-최적 ratio가 ~0.22에서 바닥남(실측: max_iter 10→30에서 J는
    # 25.8→22.8로 내려가는데 ratio는 0.16→0.22 — 물리 최적, 최적화 미수렴 아님).
    xb2 = _mk_state()
    spec2, b_sig2 = make_default_cvt(xb2, eps_overrides={"qc": eps})
    y2 = torch.zeros_like(xb2.qc)
    res2 = run_minimizer(xb2, forcings,
                         _obs_field_at(0, "qc", y2, sigma_o=1.0e-5),
                         cfg, b_sig2, max_iter=30, cvt=spec2)
    assert res2.cvt["ratio_minmax"]["qc"][0] < 0.1
    assert res2.cvt["min_analysis"]["qc"] >= \
        -eps - 4.0 * U64 * (float(xb2.qc.max()) + eps)
