"""dual estimation mainline API 게이트 (적대 검토의 필수 테스트 5종).

  1. 무관측 dual prior: x_a == xb (torch.equal) AND θ_a == θ_b (정확).
  2. 결합 클로저 FD: v_x 성분과 v_θ 성분을 각각 FD로 찔러 수동 gradient 대조
     (상태 ~1e-5, θ는 qck1 f32-계단 바닥 감안 2e-3 — test_param_grad_g4와 동일 근거).
  3. 파라미터 양수성: v_θ = ±큰값에서도 θ > 0 (log-CVT 구조 보장) + 비활성
     파라미터는 θ_b 정확 유지.
  4. mask-게이밍 회귀: n_valid가 클로저 간 감소하는 가짜 obs_eval →
     RuntimeError; 불변이면 통과.
  5. j_trace 기계가독성: dict 필드 완비 + json.dumps 직렬화 가능.
"""
from __future__ import annotations

import json

import pytest
import torch

import kdm6.constants as c
from kdm6.da_dual import (ParamPrior, default_param_prior, params_from_vtheta,
                          run_dual_minimizer, PNAMES)
from kdm6.da_window import WindowConfig
from kdm6.state import Forcing, State

DT = 20.0
_F64 = dict(dtype=torch.float64)


def _t2(a, b):
    return torch.tensor([[a, b]], **_F64)


def _mk_state():
    return State(th=_t2(296.8, 282.4), qv=_t2(1.40e-2, 2.0e-3),
                 qc=_t2(1.0e-3, 5.0e-4), qr=_t2(1.0e-4, 1.0e-5),
                 qi=_t2(0.0, 1.0e-6), qs=_t2(0.0, 5.0e-5),
                 qg=_t2(0.0, 1.0e-5), nccn=_t2(1.0e9, 1.0e9),
                 nc=_t2(1.0e8, 1.0e8), ni=_t2(0.0, 1.0e8),
                 nr=_t2(1.0e4, 1.0e3), bg=_t2(0.0, 0.0))


def _mk_forcing():
    return Forcing(rho=_t2(1.089, 0.9567), pii=_t2(0.9704, 0.9031),
                   p=_t2(9.0e4, 7.0e4), delz=_t2(500.0, 500.0))


def _b_sigma(xb):
    sig_th = torch.full_like(xb.th, 0.5)
    return State(*(sig_th if f == "th" else torch.zeros_like(getattr(xb, f))
                   for f in State._fields))


def _quad_obs(y_target):
    """합성 관측항: J = ½Σ(th_T − y)², n_valid = 원소 수 (RTTOV 불요)."""
    def obs_eval(t, x_t):
        if t != 2:
            return None
        d = x_t.th - y_target
        j = 0.5 * (d * d).sum()
        adj = State(*(d.clone() if f == "th" else torch.zeros_like(getattr(x_t, f))
                      for f in State._fields))
        return float(j), adj, int(d.numel()), "synthetic-quad"
    return obs_eval


def test_no_observation_dual_prior():
    """무관측 → 분석 = 배경 (상태·파라미터 모두 정확히)."""
    xb, fc = _mk_state(), _mk_forcing()
    prior = default_param_prior(0.2)
    res = run_dual_minimizer(xb, [fc, fc], lambda t, x: None,
                             WindowConfig(dt=DT), _b_sigma(xb), prior,
                             max_iter=3)
    for f in State._fields:
        assert torch.equal(getattr(res.x_analysis, f), getattr(xb, f)), f
    for i, n in enumerate(PNAMES):
        assert float(res.theta_analysis[i]) == float(prior.theta_b[i]), n
    assert float(res.v_state.abs().max()) == 0.0
    assert float(res.v_theta.abs().max()) == 0.0


def test_joint_closure_fd():
    """결합 gradient FD: 상태 성분(해석적 1e-5)과 θ 성분(f32-계단 2e-3)."""
    xb, fc = _mk_state(), _mk_forcing()
    forcings = [fc, fc]
    y = xb.th + 0.3                                     # 목표를 살짝 이동
    obs = _quad_obs(y)
    prior = default_param_prior(0.2, active=("peaut",))
    b_sigma = _b_sigma(xb)
    cfg = WindowConfig(dt=DT)

    from kdm6.da_minimizer import _stack, cvt_to_state
    from kdm6.da_dual import params_from_vtheta
    from kdm6.da_window import run_da_window
    import dataclasses

    def J_at(vx_pert=None, vth_pert=None):
        v_x = torch.zeros_like(_stack(b_sigma))
        v_th = torch.zeros(4, **_F64)
        if vx_pert is not None:
            v_x[vx_pert[0]] += vx_pert[1]
        if vth_pert is not None:
            v_th[vth_pert[0]] += vth_pert[1]
        x0 = cvt_to_state(xb, b_sigma, v_x)
        params = params_from_vtheta(prior, v_th, live=False)
        jobs = [0.0]
        def oa(t, x_t):
            out = obs(t, x_t)
            if out is None:
                return None
            jobs[0] += out[0]
            return out[1]
        run_da_window(x0, forcings, oa,
                      dataclasses.replace(cfg, params=params))
        return 0.5 * float((v_x ** 2).sum()) + 0.5 * float((v_th ** 2).sum()) + jobs[0]

    # v=0에서의 수동 gradient — run_dual_minimizer 클로저와 동일 산식을 재현
    v_x0 = torch.zeros_like(_stack(b_sigma))
    v_th0 = torch.zeros(4, **_F64)
    params_live = params_from_vtheta(prior, v_th0, live=True)
    jobs_acc = [0.0]
    def oa2(t, x_t):
        out = obs(t, x_t)
        if out is None:
            return None
        jobs_acc[0] += out[0]
        return out[1]
    r = run_da_window(cvt_to_state(xb, b_sigma, v_x0), forcings, oa2,
                      dataclasses.replace(cfg, params=params_live, param_grads=True))
    g_x = v_x0 + _stack(b_sigma) * _stack(r.adj_x0)
    gp = torch.zeros(4, **_F64)
    for i, n in enumerate(PNAMES):
        if r.grad_params and n in r.grad_params:
            gp[i] = r.grad_params[n].to(torch.float64)
    theta0 = torch.stack([params_live[i].detach() for i in range(4)])
    g_th = v_th0 + prior.sigma_log * theta0 * gp

    # FD: 상태 th 성분 (field 0, cell 0)
    idx = (0, 0, 0)
    h = 1.0e-4
    fd_x = (J_at(vx_pert=(idx, h)) - J_at(vx_pert=(idx, -h))) / (2 * h)
    rel_x = abs(fd_x - float(g_x[idx])) / max(abs(fd_x), 1e-30)
    assert rel_x < 1.0e-5, (fd_x, float(g_x[idx]), rel_x)

    # FD: θ 성분 (peaut = index 0); f32-계단 바닥 → h 크게 + 완화 허용오차
    hth = 5.0e-3
    fd_th = (J_at(vth_pert=(0, hth)) - J_at(vth_pert=(0, -hth))) / (2 * hth)
    rel_th = abs(fd_th - float(g_th[0])) / max(abs(fd_th), 1e-30)
    assert rel_th < 2.0e-3, (fd_th, float(g_th[0]), rel_th)


def test_parameter_positivity_and_inactive_pin():
    prior = default_param_prior(0.2, active=("peaut", "ncrk1"))
    for v in (torch.full((4,), 10.0, **_F64), torch.full((4,), -10.0, **_F64)):
        th = params_from_vtheta(prior, v)
        for i in range(4):
            assert float(th[i]) > 0.0
    # 비활성(ncrk2/eccbrk)은 임의 v에서도 θ_b 정확 유지
    th = params_from_vtheta(prior, torch.tensor([1.0, -2.0, 3.0, -4.0], **_F64))
    assert float(th[2]) == float(prior.theta_b[2])
    assert float(th[3]) == float(prior.theta_b[3])


def test_mask_gaming_gate():
    """n_valid가 클로저 간 줄어드는 가짜 obs_eval → RuntimeError."""
    xb, fc = _mk_state(), _mk_forcing()
    y = xb.th + 0.3
    calls = [0]

    def gaming_obs(t, x_t):
        if t != 2:
            return None
        calls[0] += 1
        d = x_t.th - y
        n_valid = 2 if calls[0] <= 1 else 1        # 두 번째 클로저부터 항 탈락
        j = 0.5 * (d * d).sum()
        adj = State(*(d.clone() if f == "th" else torch.zeros_like(getattr(x_t, f))
                      for f in State._fields))
        return float(j), adj, n_valid, "sig-const"

    with pytest.raises(RuntimeError, match="n_valid changed"):
        run_dual_minimizer(xb, [fc, fc], gaming_obs, WindowConfig(dt=DT),
                           _b_sigma(xb), default_param_prior(0.2), max_iter=4)


def test_j_trace_machine_readable():
    xb, fc = _mk_state(), _mk_forcing()
    res = run_dual_minimizer(xb, [fc, fc], _quad_obs(xb.th + 0.3),
                             WindowConfig(dt=DT), _b_sigma(xb),
                             default_param_prior(0.2, active=("peaut",)),
                             max_iter=2)
    s = json.dumps(res.j_trace)                     # 직렬화 가능해야
    assert all(set(e) >= {"total", "j_state", "j_theta", "j_obs"} for e in res.j_trace)
    assert res.j_trace[-1]["total"] <= res.j_trace[0]["total"]   # 감소(또는 동일)
    assert json.loads(s)[0]["n_valid"] == {"2": 2} or res.j_trace[0]["n_valid"] == {2: 2}


def test_mask_gaming_gate_none_bypass():
    """우회 봉쇄 (stop-review): n_valid를 줄이는 대신 슬롯을 None으로 소멸시키는
    obs_eval — 슬롯 집합 변화로 RuntimeError."""
    xb, fc = _mk_state(), _mk_forcing()
    y = xb.th + 0.3
    calls = [0]

    def vanishing_obs(t, x_t):
        if t != 2:
            return None
        calls[0] += 1
        if calls[0] > 1:
            return None                              # 2번째 클로저부터 슬롯 소멸
        d = x_t.th - y
        adj = State(*(d.clone() if f == "th" else torch.zeros_like(getattr(x_t, f))
                      for f in State._fields))
        return float(0.5 * (d * d).sum()), adj, int(d.numel()), "sig-const"

    with pytest.raises(RuntimeError, match="slots changed"):
        run_dual_minimizer(xb, [fc, fc], vanishing_obs, WindowConfig(dt=DT),
                           _b_sigma(xb), default_param_prior(0.2), max_iter=4)


def test_two_tuple_obs_eval_rejected():
    """재검토 blocker-1: 2-튜플 obs_eval(기존 상태의존-mask 경로)은 dual에서 거부."""
    xb, fc = _mk_state(), _mk_forcing()

    def legacy_obs(t, x_t):
        if t != 2:
            return None
        d = x_t.th - (xb.th + 0.3)
        adj = State(*(d.clone() if f == "th" else torch.zeros_like(getattr(x_t, f))
                      for f in State._fields))
        return float(0.5 * (d * d).sum()), adj          # 2-튜플

    with pytest.raises(RuntimeError, match="2-tuple obs_eval bypasses"):
        run_dual_minimizer(xb, [fc, fc], legacy_obs, WindowConfig(dt=DT),
                           _b_sigma(xb), default_param_prior(0.2), max_iter=2)


def test_signature_substitution_gate():
    """재검토 blocker-2: n_valid 동일·mask 치환(서명 변경) → RuntimeError."""
    xb, fc = _mk_state(), _mk_forcing()
    calls = [0]

    def substituting_obs(t, x_t):
        if t != 2:
            return None
        calls[0] += 1
        d = x_t.th - (xb.th + 0.3)
        adj = State(*(d.clone() if f == "th" else torch.zeros_like(getattr(x_t, f))
                      for f in State._fields))
        sig = "maskA" if calls[0] <= 1 else "maskB"     # 개수 유지, 정체 치환
        return float(0.5 * (d * d).sum()), adj, 2, sig

    with pytest.raises(RuntimeError, match="signature changed"):
        run_dual_minimizer(xb, [fc, fc], substituting_obs, WindowConfig(dt=DT),
                           _b_sigma(xb), default_param_prior(0.2), max_iter=4)


def test_param_prior_finite_and_active_validation():
    """재검토 #5/#6: NaN/Inf theta·sigma 거부, active 오타 거부."""
    with pytest.raises(ValueError, match="finite"):
        ParamPrior(theta_b=torch.tensor([float("nan"), 1.0, 1.0, 1.0], **_F64),
                   sigma_log=torch.zeros(4, **_F64))
    with pytest.raises(ValueError, match="finite"):
        ParamPrior(theta_b=torch.ones(4, **_F64),
                   sigma_log=torch.tensor([float("inf"), 0, 0, 0], **_F64))
    with pytest.raises(ValueError, match="unknown parameter names"):
        default_param_prior(0.2, active=("peuat",))     # 오타 → loud


def test_frozen_adapter_uses_background_trajectory(monkeypatch):
    """재검토 #3/#7 + stop-review: ① t>0 동결이 배경 궤적 M(x_b→t) 상태로 평가
    ② mask가 궤적-기준 rad_quality로 선택됨(수치 검증) ③ 내부 루프에서 x_t가
    바뀌어도 반환 서명·n_valid 불변."""
    import kdm6.da_dual as dd
    xb, fc = _mk_state(), _mk_forcing()
    y_bt = torch.full((1, 16), 250.0, **_F64)
    y_rq = torch.zeros((1, 16), **_F64)

    def fake_clear_bt(x_state, fc_t, cfg):
        # xb 그대로면 rad_quality=1(무효), 진화 상태면 0(유효) — 동결이 궤적
        # 기준인지 수치로 구분된다
        is_xb = torch.equal(x_state.th, xb.th)
        rq = torch.ones((1, 16), **_F64) if is_xb else torch.zeros((1, 16), **_F64)
        leaves = State(*(f.detach().clone().requires_grad_(True) for f in x_state))
        bt = (torch.full((1, 16), 260.0, **_F64)
              + 0.0 * (leaves.th.sum() + leaves.qv.sum()))   # th·qv 연결
        return bt, rq, leaves

    import kdm6.da_driver as drv
    monkeypatch.setattr(drv, "batched_clear_bt", fake_clear_bt)
    obs = dd.make_dual_frozen_obs_eval(
        xb, [fc, fc], {0: (y_bt, y_rq), 2: (y_bt, y_rq)},
        type("C", (), {"obs_sigma": 1.0})(), WindowConfig(dt=DT),
        dd.default_param_prior(0.2))
    # ② t=0 동결은 x_b(rq=1→무효 0개), t=2 동결은 진화 상태(rq=0→16개 유효)
    out0 = obs(0, xb)
    out2 = obs(2, xb)
    assert out0[2] == 0, "t=0 n_valid는 x_b 기준 0이어야"
    assert out2[2] == 16, "t=2 n_valid가 16이 아니면 궤적 아닌 x_b에서 동결된 것"
    # ③ 내부 상태가 바뀌어도 서명·n_valid 동결 유지
    x_moved = State(*(f + 0.01 for f in xb))
    out2b = obs(2, x_moved)
    assert out2b[2] == out2[2] and out2b[3] == out2[3]


def test_three_tuple_requires_optout():
    """재검토 #4: 서명 없는 3-튜플은 기본값에서 거부, 명시적 opt-out만 허용."""
    xb, fc = _mk_state(), _mk_forcing()

    def sigless_obs(t, x_t):
        if t != 2:
            return None
        d = x_t.th - (xb.th + 0.3)
        adj = State(*(d.clone() if f == "th" else torch.zeros_like(getattr(x_t, f))
                      for f in State._fields))
        return float(0.5 * (d * d).sum()), adj, int(d.numel())

    with pytest.raises(RuntimeError, match="signature"):
        run_dual_minimizer(xb, [fc, fc], sigless_obs, WindowConfig(dt=DT),
                           _b_sigma(xb), default_param_prior(0.2), max_iter=2)
    res = run_dual_minimizer(xb, [fc, fc], sigless_obs, WindowConfig(dt=DT),
                             _b_sigma(xb), default_param_prior(0.2), max_iter=2,
                             require_signature=False)
    assert res.j_trace


def test_theta_overflow_guard():
    """재검토 #5: exp 오버플로 θ → FloatingPointError (조용한 Inf 차단)."""
    from kdm6.da_dual import params_from_vtheta
    prior = default_param_prior(0.2)
    with pytest.raises(FloatingPointError, match="non-finite"):
        params_from_vtheta(prior, torch.full((4,), 1.0e5, **_F64))
