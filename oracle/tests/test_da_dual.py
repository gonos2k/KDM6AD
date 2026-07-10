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


def _P(**kw):
    """합성 테스트용 정책: tuple 반환 opt-in (production 기본은 dataclass-only)."""
    from kdm6.da_dual import ObsGatePolicy
    return ObsGatePolicy(allow_tuple_returns=True, **kw)


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


def _bad_b_sigma_shape(xb):
    good = _b_sigma(xb)
    vals = []
    for f in State._fields:
        v = getattr(good, f)
        if f == "th":
            vals.append(torch.zeros((1, 1), **_F64))       # broadcastable but wrong
        else:
            vals.append(v)
    return State(*vals)


def test_b_sigma_shape_rejected_in_minimizers():
    """b_sigma must match xb field shapes exactly; broadcasting corrupts CVT."""
    xb, fc = _mk_state(), _mk_forcing()
    bad = _bad_b_sigma_shape(xb)
    from kdm6.da_minimizer import run_minimizer
    with pytest.raises(ValueError, match="b_sigma.th shape"):
        run_minimizer(xb, [fc], lambda t, x: None, WindowConfig(dt=DT), bad, max_iter=1)
    with pytest.raises(ValueError, match="b_sigma.th shape"):
        run_dual_minimizer(xb, [fc], lambda t, x: None, WindowConfig(dt=DT), bad,
                           default_param_prior(0.2), max_iter=1,
                           require_obs_slots=False)


def test_policy_and_result_boundary_validation():
    from kdm6.da_dual import ObsGatePolicy, ObsEvalResult
    with pytest.raises(TypeError, match="require_signature must be bool"):
        ObsGatePolicy(require_signature="no")
    xb = _mk_state()
    adj = State(*(torch.zeros_like(getattr(xb, f)) for f in State._fields))
    with pytest.raises(ValueError, match="n_valid must be >= 0"):
        ObsEvalResult(j=0.0, adj=adj, n_valid=-1, signature="sig")


def test_custom_obs_eval_j_scalar_and_finite_required():
    xb, fc = _mk_state(), _mk_forcing()
    adj = State(*(torch.zeros_like(getattr(xb, f)) for f in State._fields))

    def vector_j(t, x_t):
        if t != 1:
            return None
        return torch.tensor([1.0, 2.0], **_F64), adj, 2, "sig"

    with pytest.raises(ValueError, match="obs_eval j must be scalar"):
        run_dual_minimizer(xb, [fc], vector_j, WindowConfig(dt=DT), _b_sigma(xb),
                           default_param_prior(0.2), max_iter=1, policy=_P())

    def nan_j(t, x_t):
        if t != 1:
            return None
        return torch.tensor(float("nan"), **_F64), adj, 2, "sig"

    with pytest.raises(FloatingPointError, match="obs_eval j is non-finite"):
        run_dual_minimizer(xb, [fc], nan_j, WindowConfig(dt=DT), _b_sigma(xb),
                           default_param_prior(0.2), max_iter=1, policy=_P())


def test_no_observation_dual_prior():
    """무관측 → 분석 = 배경 (상태·파라미터 모두 정확히)."""
    xb, fc = _mk_state(), _mk_forcing()
    prior = default_param_prior(0.2)
    res = run_dual_minimizer(xb, [fc, fc], lambda t, x: None,
                             WindowConfig(dt=DT), _b_sigma(xb), prior,
                             max_iter=3, require_obs_slots=False)
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
                           _b_sigma(xb), default_param_prior(0.2), max_iter=4,
                           policy=_P())


def test_j_trace_machine_readable():
    xb, fc = _mk_state(), _mk_forcing()
    res = run_dual_minimizer(xb, [fc, fc], _quad_obs(xb.th + 0.3),
                             WindowConfig(dt=DT), _b_sigma(xb),
                             default_param_prior(0.2, active=("peaut",)),
                             max_iter=2, policy=_P())
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
                           _b_sigma(xb), default_param_prior(0.2), max_iter=4,
                           policy=_P())


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
                           _b_sigma(xb), default_param_prior(0.2), max_iter=2,
                           policy=_P())


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
                           _b_sigma(xb), default_param_prior(0.2), max_iter=4,
                           policy=_P())


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
    """재검토 #3/#7: ① t>0 동결이 배경 궤적 상태로 평가(수치 검증: t0=0/t2=16)
    ② 내부 루프에서 x_t가 바뀌어도 서명·n_valid 불변 ③ zero-valid 슬롯은
    opt-in 없으면 거부 ④ y_rq shape 불일치 거부."""
    import kdm6.da_dual as dd
    xb, fc = _mk_state(), _mk_forcing()
    y_bt = torch.full((1, 16), 250.0, **_F64)
    y_rq = torch.zeros((1, 16), **_F64)

    def fake_clear_bt(x_state, fc_t, cfg):
        is_xb = torch.equal(x_state.th, xb.th)
        rq = torch.ones((1, 16), **_F64) if is_xb else torch.zeros((1, 16), **_F64)
        leaves = State(*(f.detach().clone().requires_grad_(True) for f in x_state))
        bt = (torch.full((1, 16), 260.0, **_F64)
              + 0.0 * (leaves.th.sum() + leaves.qv.sum()))
        return bt, rq, leaves

    import kdm6.da_driver as drv
    monkeypatch.setattr(drv, "batched_clear_bt", fake_clear_bt)
    cfg_obs = type("C", (), {"obs_sigma": 1.0})()
    prior = dd.default_param_prior(0.2)
    # ③ t=0은 x_b 기준 rq=1 → 유효 0 → 기본값에서 거부 (H3)
    with pytest.raises(RuntimeError, match="zero valid obs"):
        dd.make_dual_frozen_obs_eval(xb, [fc, fc],
                                     {0: (y_bt, y_rq), 2: (y_bt, y_rq)},
                                     cfg_obs, WindowConfig(dt=DT), prior)
    obs = dd.make_dual_frozen_obs_eval(
        xb, [fc, fc], {0: (y_bt, y_rq), 2: (y_bt, y_rq)},
        cfg_obs, WindowConfig(dt=DT), prior, allow_zero_valid_slots=True)
    # ① t=0 동결은 x_b(무효 0개), t=2는 진화 상태(16개) — 궤적 기준의 수치 증거
    out0, out2 = obs(0, xb), obs(2, xb)
    assert out0.n_valid == 0 and out2.n_valid == 16
    # ② 내부 상태 이동에도 서명·n_valid 동결
    x_moved = State(*(f + 0.01 for f in xb))
    out2b = obs(2, x_moved)
    assert out2b.n_valid == out2.n_valid and out2b.signature == out2.signature
    # ④ y_rq shape (16,) → broadcasting 침묵 통과 대신 거부 (H1)
    with pytest.raises(ValueError, match="silent broadcast"):
        dd.make_dual_frozen_obs_eval(
            xb, [fc, fc], {2: (y_bt, torch.zeros(16, **_F64))},
            cfg_obs, WindowConfig(dt=DT), prior)


def test_obs_eval_result_dataclass_accepted():
    """재검토 M2: ObsEvalResult 반환이 튜플과 동등하게 수용·게이트됨."""
    from kdm6.da_dual import ObsEvalResult
    xb, fc = _mk_state(), _mk_forcing()

    def dc_obs(t, x_t):
        if t != 2:
            return None
        d = x_t.th - (xb.th + 0.3)
        adj = State(*(d.clone() if f == "th" else torch.zeros_like(getattr(x_t, f))
                      for f in State._fields))
        return ObsEvalResult(j=float(0.5 * (d * d).sum()), adj=adj,
                             n_valid=int(d.numel()), signature="dc-sig")

    res = run_dual_minimizer(xb, [fc, fc], dc_obs, WindowConfig(dt=DT),
                             _b_sigma(xb), default_param_prior(0.2, active=("peaut",)),
                             max_iter=2)
    assert res.j_trace[-1]["total"] <= res.j_trace[0]["total"]


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
                           _b_sigma(xb), default_param_prior(0.2), max_iter=2,
                           policy=_P())
    res = run_dual_minimizer(xb, [fc, fc], sigless_obs, WindowConfig(dt=DT),
                             _b_sigma(xb), default_param_prior(0.2), max_iter=2,
                             policy=_P(require_signature=False))
    assert res.j_trace


def test_theta_overflow_guard():
    """재검토 #5: exp 오버플로 θ → FloatingPointError (조용한 Inf 차단)."""
    from kdm6.da_dual import params_from_vtheta
    prior = default_param_prior(0.2)
    with pytest.raises(FloatingPointError, match="non-finite"):
        params_from_vtheta(prior, torch.full((4,), 1.0e5, **_F64))


def test_zero_valid_slot_rejected_at_minimizer():
    """stop-review: 어댑터 밖(커스텀 obs_eval)의 n_valid=0 슬롯도 최소화기가
    기본 거부; opt-in 시 통과."""
    xb, fc = _mk_state(), _mk_forcing()

    def empty_obs(t, x_t):
        if t != 2:
            return None
        adj = State(*(torch.zeros_like(getattr(x_t, f)) for f in State._fields))
        return 0.0, adj, 0, "empty-sig"

    with pytest.raises(RuntimeError, match="n_valid=0"):
        run_dual_minimizer(xb, [fc, fc], empty_obs, WindowConfig(dt=DT),
                           _b_sigma(xb), default_param_prior(0.2), max_iter=2,
                           policy=_P())
    res = run_dual_minimizer(xb, [fc, fc], empty_obs, WindowConfig(dt=DT),
                             _b_sigma(xb), default_param_prior(0.2), max_iter=2,
                             policy=_P(allow_zero_valid_slots=True))
    assert float(res.v_state.abs().max()) == 0.0        # 관측 없음 → 배경 유지


def test_no_slots_rejected_by_default():
    """재검토 H1: 슬롯이 전혀 보고되지 않는 custom obs_eval은 기본 거부 —
    관측시각 인덱스 불일치가 'prior-only 성공'으로 위장하는 경로 차단."""
    xb, fc = _mk_state(), _mk_forcing()
    with pytest.raises(RuntimeError, match="no observation slots"):
        run_dual_minimizer(xb, [fc, fc], lambda t, x: None,
                           WindowConfig(dt=DT), _b_sigma(xb),
                           default_param_prior(0.2), max_iter=2)


def test_none_or_empty_signature_rejected():
    """재검토 blocker: 4-튜플의 서명이 None/빈 문자열이면 '서명 있음' 위장 —
    비어있지 않은 str/bytes 강제."""
    xb, fc = _mk_state(), _mk_forcing()

    def make_obs(sig):
        def obs(t, x_t):
            if t != 2:
                return None
            d = x_t.th - (xb.th + 0.3)
            adj = State(*(d.clone() if f == "th" else torch.zeros_like(getattr(x_t, f))
                          for f in State._fields))
            return float(0.5 * (d * d).sum()), adj, int(d.numel()), sig
        return obs

    for bad in (None, "", 123):
        with pytest.raises(RuntimeError, match="NON-EMPTY"):
            run_dual_minimizer(xb, [fc, fc], make_obs(bad), WindowConfig(dt=DT),
                               _b_sigma(xb), default_param_prior(0.2), max_iter=2,
                               policy=_P())


def test_collect_window_trajectory_matches_probe():
    """재검토 H2: forward-전용 수집기 ≡ run_da_window 프로브 (bitwise) —
    η/η_pre 약한구속 증분이 있는 창에서 관측-시점 상태 규약까지 동일."""
    from kdm6.da_window import collect_window_trajectory, run_da_window
    xb, fc = _mk_state(), _mk_forcing()
    eta = [State(*(0.001 * torch.ones_like(f) if n == "th" else torch.zeros_like(f)
                   for n, f in zip(State._fields, xb))) for _ in range(2)]
    eta_pre = [State(*(0.0005 * torch.ones_like(f) if n == "qv" else torch.zeros_like(f)
                       for n, f in zip(State._fields, xb))) for _ in range(2)]
    cfg = WindowConfig(dt=DT, eta=eta, eta_pre=eta_pre)

    probe_states = {}
    def probe(tt, x_t):
        probe_states[tt] = State(*(f.detach().clone() for f in x_t))
        return None
    run_da_window(xb, [fc, fc], probe, cfg)
    traj = collect_window_trajectory(xb, [fc, fc], cfg, {0, 1, 2})
    for tt in (0, 1, 2):
        for i, f in enumerate(State._fields):
            assert torch.equal(traj[tt][i], probe_states[tt][i]), (tt, f)
    with pytest.raises(ValueError, match="outside window"):
        collect_window_trajectory(xb, [fc, fc], cfg, {5})
    # shape 가드 (stop-review): 잘못된 shape의 η는 broadcast로 침묵 오염되는
    # 대신 run_da_window와 동일하게 거부돼야 한다
    bad_eta = [State(*(torch.zeros(1, 1, dtype=torch.float64)
                       for _ in State._fields)) for _ in range(2)]
    with pytest.raises(ValueError, match="eta"):
        collect_window_trajectory(xb, [fc, fc],
                                  WindowConfig(dt=DT, eta=bad_eta), {2})


def test_adapter_policy_and_entry_validation(monkeypatch):
    """4차 배선 게이트: ① 어댑터가 ObsGatePolicy.allow_zero_valid_slots를 실제
    소비 ② y_by_time 초과 원소 거부 (미배선이면 즉시 실패하는 항목들)."""
    import kdm6.da_dual as dd
    from kdm6.da_dual import ObsGatePolicy
    xb, fc = _mk_state(), _mk_forcing()
    y_bt = torch.full((1, 16), 250.0, **_F64)
    y_rq = torch.zeros((1, 16), **_F64)

    def fake_clear_bt(x_state, fc_t, cfg):
        rq = torch.ones((1, 16), **_F64)                # 전 채널 무효 → zero-valid
        leaves = State(*(f.detach().clone().requires_grad_(True) for f in x_state))
        bt = torch.full((1, 16), 260.0, **_F64) + 0.0 * (leaves.th.sum() + leaves.qv.sum())
        return bt, rq, leaves

    import kdm6.da_driver as drv
    monkeypatch.setattr(drv, "batched_clear_bt", fake_clear_bt)
    cfg_obs = type("C", (), {"obs_sigma": 1.0})()
    prior = dd.default_param_prior(0.2)
    # ② 초과 원소 (4개) → 거부
    with pytest.raises(ValueError, match="y_by_time"):
        dd.make_dual_frozen_obs_eval(xb, [fc, fc],
                                     {2: (y_bt, y_rq, None, "extra")},
                                     cfg_obs, WindowConfig(dt=DT), prior)
    # ① policy.allow_zero_valid_slots=True가 어댑터 zero-valid 거부를 해제
    obs = dd.make_dual_frozen_obs_eval(
        xb, [fc, fc], {2: (y_bt, y_rq)}, cfg_obs, WindowConfig(dt=DT), prior,
        policy=ObsGatePolicy(allow_zero_valid_slots=True))
    assert obs(2, xb).n_valid == 0


def test_frozen_obs_slot_boundary_validation():
    """Frozen slot contract is enforced at the dataclass boundary, not only upstream."""
    from kdm6.da_dual import _FrozenObsSlot
    mask = torch.ones((1, 2), **_F64)
    y_bt = torch.full((1, 2), 250.0, **_F64)
    sigma = torch.tensor(1.0, **_F64)

    _FrozenObsSlot(mask=mask, n_valid=2, signature="sig", y_bt=y_bt,
                   bias=torch.zeros((2,), **_F64), sigma=sigma)
    for bad_n_valid in (True, 1.0, -1):
        with pytest.raises((TypeError, ValueError), match="n_valid"):
            _FrozenObsSlot(mask=mask, n_valid=bad_n_valid, signature="sig",
                           y_bt=y_bt, bias=None, sigma=sigma)
    with pytest.raises(TypeError, match="signature"):
        _FrozenObsSlot(mask=mask, n_valid=2, signature="", y_bt=y_bt,
                       bias=None, sigma=sigma)
    with pytest.raises(ValueError, match="mask.*y_bt"):
        _FrozenObsSlot(mask=torch.ones((2,), **_F64), n_valid=2, signature="sig",
                       y_bt=y_bt, bias=None, sigma=sigma)
    with pytest.raises(ValueError, match="bias"):
        _FrozenObsSlot(mask=mask, n_valid=2, signature="sig", y_bt=y_bt,
                       bias=torch.zeros((3,), **_F64), sigma=sigma)


def test_frozen_adapter_calls_collector_not_probe(monkeypatch):
    """재검토 M3: 어댑터가 collect_window_trajectory를 실제 호출하고
    run_da_window 프로브는 호출하지 않음 — 미배선 회귀의 직접 spy."""
    import kdm6.da_dual as dd
    import kdm6.da_window as dw
    xb, fc = _mk_state(), _mk_forcing()
    called = {"collect": 0}
    real_collect = dw.collect_window_trajectory

    def spy_collect(*a, **k):
        called["collect"] += 1
        return real_collect(*a, **k)

    def forbid_run(*a, **k):
        raise AssertionError("adapter must not call run_da_window (full-VJP probe)")

    monkeypatch.setattr(dw, "collect_window_trajectory", spy_collect)
    monkeypatch.setattr(dd, "run_da_window", forbid_run)

    def fake_clear_bt(x_state, fc_t, cfg):
        rq = torch.zeros((1, 16), **_F64)
        leaves = State(*(f.detach().clone().requires_grad_(True) for f in x_state))
        bt = torch.full((1, 16), 260.0, **_F64) + 0.0 * (leaves.th.sum() + leaves.qv.sum())
        return bt, rq, leaves
    import kdm6.da_driver as drv
    monkeypatch.setattr(drv, "batched_clear_bt", fake_clear_bt)
    dd.make_dual_frozen_obs_eval(
        xb, [fc, fc], {2: (torch.full((1, 16), 250.0, **_F64),
                           torch.zeros((1, 16), **_F64))},
        type("C", (), {"obs_sigma": 1.0})(), WindowConfig(dt=DT),
        dd.default_param_prior(0.2))
    assert called["collect"] == 1


def test_frozen_adapter_freezes_operator_config_reference(monkeypatch):
    """Adapter construction freezes the obs operator config used by the inner H(x)."""
    import dataclasses
    import kdm6.da_dual as dd
    xb, fc = _mk_state(), _mk_forcing()
    y_bt = torch.full((1, 16), 250.0, **_F64)
    y_rq = torch.zeros((1, 16), **_F64)

    @dataclasses.dataclass
    class Cfg:
        obs_sigma: float = 1.0
        operator_offset: float = 10.0

    def fake_clear_bt(x_state, fc_t, cfg):
        rq = torch.zeros((1, 16), **_F64)
        leaves = State(*(f.detach().clone().requires_grad_(True) for f in x_state))
        bt = (torch.full((1, 16), 250.0 + float(cfg.operator_offset), **_F64)
              + 0.0 * (leaves.th.sum() + leaves.qv.sum()))
        return bt, rq, leaves

    import kdm6.da_driver as drv
    monkeypatch.setattr(drv, "batched_clear_bt", fake_clear_bt)
    cfg_obs = Cfg()
    prior = dd.default_param_prior(0.2)
    obs = dd.make_dual_frozen_obs_eval(xb, [fc], {1: (y_bt, y_rq)},
                                       cfg_obs, WindowConfig(dt=DT), prior)
    j_before = obs(1, xb).j
    cfg_obs.operator_offset = 50.0
    assert obs(1, xb).j == j_before


def test_freeze_real_osse_obs_cfg_semantics():
    """Real OsseObsConfig fields that define H(x) survive freeze and fingerprinting."""
    import kdm6.da_dual as dd
    from kdm6.da_driver import OsseObsConfig
    from kdm6.obs.model_profile_builder import RttovProfileConfig
    from kdm6.obs.rttov_input_builder import RttovInputConfig

    def run_k(_rin):
        raise AssertionError("not called")
    run_k.solar_channels = (1,)
    p_lay = torch.tensor([100.0, 200.0], **_F64)
    p_half = torch.tensor([50.0, 150.0, 250.0], **_F64)
    cfg = OsseObsConfig(
        run_k=run_k,
        profile_cfg=RttovProfileConfig(2, "mixing_ratio_kgkg_dry", p_lay, p_half),
        input_cfg=RttovInputConfig("coef-a", (1, 2), surface={"z": 1.0}),
        obs_sigma=torch.tensor([1.0, 2.0], **_F64),
        t_ref=torch.tensor([250.0, 251.0], **_F64),
        q_ref=torch.tensor([10.0, 11.0], **_F64),
        t_blend_octaves=1.5,
        q_blend_octaves=3.5)
    frozen = dd._freeze_obs_cfg(cfg)
    assert frozen.input_cfg.coef_id == "coef-a"
    assert frozen.input_cfg.channels == (1, 2)
    assert frozen.profile_cfg.qv_convention == "mixing_ratio_kgkg_dry"
    assert torch.equal(frozen.profile_cfg.rttov_layer_pressure, p_lay)
    assert torch.equal(frozen.obs_sigma, torch.tensor([1.0, 2.0], **_F64))
    fp_before = dd._obs_cfg_fingerprint(frozen)
    cfg.input_cfg.surface["z"] = 99.0
    cfg.t_ref[0] = -999.0
    run_k.solar_channels = (2,)
    assert torch.equal(frozen.t_ref, torch.tensor([250.0, 251.0], **_F64))
    assert frozen.input_cfg.surface["z"] == 1.0
    assert dd._obs_cfg_fingerprint(frozen) == fp_before
    import dataclasses
    changed = dataclasses.replace(
        frozen, input_cfg=frozen.input_cfg._replace(coef_id="coef-b"))
    assert dd._obs_cfg_fingerprint(changed) != fp_before


def test_frozen_adapter_sigma_value_changes_signature(monkeypatch):
    """Frozen signatures include the actual obs_sigma value, not only shape/dtype."""
    import kdm6.da_dual as dd
    xb, fc = _mk_state(), _mk_forcing()
    y_bt = torch.full((1, 16), 250.0, **_F64)
    y_rq = torch.zeros((1, 16), **_F64)

    def fake_clear_bt(x_state, fc_t, cfg):
        rq = torch.zeros((1, 16), **_F64)
        leaves = State(*(f.detach().clone().requires_grad_(True) for f in x_state))
        bt = torch.full((1, 16), 260.0, **_F64) + 0.0 * (leaves.th.sum() + leaves.qv.sum())
        return bt, rq, leaves

    import kdm6.da_driver as drv
    monkeypatch.setattr(drv, "batched_clear_bt", fake_clear_bt)
    prior = dd.default_param_prior(0.2)
    obs_1 = dd.make_dual_frozen_obs_eval(
        xb, [fc], {1: (y_bt, y_rq)}, type("C", (), {"obs_sigma": 1.0})(),
        WindowConfig(dt=DT), prior)
    obs_2 = dd.make_dual_frozen_obs_eval(
        xb, [fc], {1: (y_bt, y_rq)}, type("C", (), {"obs_sigma": 2.0})(),
        WindowConfig(dt=DT), prior)
    assert obs_1(1, xb).signature != obs_2(1, xb).signature


def test_frozen_adapter_y_rq_domain_validation(monkeypatch):
    """superob quality flags are frozen non-negative codes; 0 keeps, nonzero drops."""
    import kdm6.da_dual as dd
    xb, fc = _mk_state(), _mk_forcing()
    y_bt = torch.full((1, 16), 250.0, **_F64)

    def fake_clear_bt(x_state, fc_t, cfg):
        rq = torch.zeros((1, 16), **_F64)
        leaves = State(*(f.detach().clone().requires_grad_(True) for f in x_state))
        bt = torch.full((1, 16), 260.0, **_F64) + 0.0 * (leaves.th.sum() + leaves.qv.sum())
        return bt, rq, leaves

    import kdm6.da_driver as drv
    monkeypatch.setattr(drv, "batched_clear_bt", fake_clear_bt)
    cfg_obs = type("C", (), {"obs_sigma": 1.0})()
    prior = dd.default_param_prior(0.2)
    flagged = torch.zeros((1, 16), **_F64); flagged[0, 0] = 2.0
    obs = dd.make_dual_frozen_obs_eval(xb, [fc], {1: (y_bt, flagged)},
                                       cfg_obs, WindowConfig(dt=DT), prior)
    assert obs(1, xb).n_valid == 15
    flagged_alt = torch.zeros((1, 16), **_F64); flagged_alt[0, 0] = 3.0
    obs_alt = dd.make_dual_frozen_obs_eval(xb, [fc], {1: (y_bt, flagged_alt)},
                                           cfg_obs, WindowConfig(dt=DT), prior)
    assert obs_alt(1, xb).n_valid == 15
    assert obs_alt(1, xb).signature != obs(1, xb).signature
    bad_nan = torch.zeros((1, 16), **_F64); bad_nan[0, 0] = float("nan")
    bad_negative = torch.zeros((1, 16), **_F64); bad_negative[0, 0] = -1.0
    for bad, match in ((bad_nan, "finite"), (bad_negative, "non-negative")):
        with pytest.raises(ValueError, match=match):
            dd.make_dual_frozen_obs_eval(xb, [fc], {1: (y_bt, bad)},
                                         cfg_obs, WindowConfig(dt=DT), prior)


def test_bytes_signature_normalized_and_strict_n_valid():
    """재검토 H1/H2: bytes 서명은 hex로 정규화돼 trace가 JSON 직렬화되고,
    bool/float/음수 n_valid는 거부."""
    xb, fc = _mk_state(), _mk_forcing()

    def make_obs(n_valid, sig=b"maskhash"):
        def obs(t, x_t):
            if t != 2:
                return None
            d = x_t.th - (xb.th + 0.3)
            adj = State(*(d.clone() if f == "th" else torch.zeros_like(getattr(x_t, f))
                          for f in State._fields))
            return float(0.5 * (d * d).sum()), adj, n_valid, sig
        return obs

    res = run_dual_minimizer(xb, [fc, fc], make_obs(2), WindowConfig(dt=DT),
                             _b_sigma(xb), default_param_prior(0.2), max_iter=2,
                             policy=_P())
    json.dumps(res.j_trace)                               # bytes였다면 실패
    assert res.j_trace[0]["signature"]["2"] if isinstance(
        list(res.j_trace[0]["signature"])[0], str) else res.j_trace[0]["signature"][2]
    for bad in (True, 1.7, -1):
        with pytest.raises((TypeError, ValueError)):
            run_dual_minimizer(xb, [fc, fc], make_obs(bad), WindowConfig(dt=DT),
                               _b_sigma(xb), default_param_prior(0.2), max_iter=2,
                               policy=_P())

def test_policy_kwarg_conflict_rejected():
    """재검토 M1: policy와 non-default legacy kwarg 동시 지정 → 거부."""
    from kdm6.da_dual import ObsGatePolicy
    xb, fc = _mk_state(), _mk_forcing()
    with pytest.raises(ValueError, match="not both"):
        run_dual_minimizer(xb, [fc, fc], lambda t, x: None, WindowConfig(dt=DT),
                           _b_sigma(xb), default_param_prior(0.2),
                           require_signature=False,
                           policy=ObsGatePolicy(require_obs_slots=False))


def test_round5_contract_gates(monkeypatch):
    """5차 검토 게이트: ① 관측값/sigma 동결 — 어댑터 생성 후 외부 in-place/
    cfg 수정이 목적함수에 무영향 ② 시각 키 bool/float 거부 ③ 어댑터 policy/kwarg
    충돌 거부 ④ result.policy 감사 기록 ⑤ tuple 반환 기본 거부(dataclass-only)."""
    import kdm6.da_dual as dd
    from kdm6.da_dual import ObsGatePolicy, ObsEvalResult
    xb, fc = _mk_state(), _mk_forcing()
    y_bt = torch.full((1, 16), 250.0, **_F64)
    y_rq = torch.zeros((1, 16), **_F64)

    def fake_clear_bt(x_state, fc_t, cfg):
        rq = torch.zeros((1, 16), **_F64)
        leaves = State(*(f.detach().clone().requires_grad_(True) for f in x_state))
        bt = torch.full((1, 16), 260.0, **_F64) + 0.0 * (leaves.th.sum() + leaves.qv.sum())
        return bt, rq, leaves
    import kdm6.da_driver as drv
    monkeypatch.setattr(drv, "batched_clear_bt", fake_clear_bt)
    cfg_obs = type("C", (), {"obs_sigma": 1.0})()
    prior = dd.default_param_prior(0.2)

    # ① 관측값 + sigma 동결
    ybt_mut = y_bt.clone()
    obs = dd.make_dual_frozen_obs_eval(xb, [fc, fc], {2: (ybt_mut, y_rq)},
                                       cfg_obs, WindowConfig(dt=DT), prior)
    out_before = obs(2, xb)
    j_before = out_before.j
    sig_before = out_before.signature
    ybt_mut += 100.0                                    # 외부 in-place 오염 시도
    cfg_obs.obs_sigma = 7.0                             # live cfg 오염 시도
    out_after = obs(2, xb)
    assert out_after.j == j_before, "관측값/sigma가 동결되지 않음"
    assert out_after.signature == sig_before

    # ② 시각 키 엄격
    for bad_key in (1.7, True):
        with pytest.raises((TypeError, ValueError)):
            dd.make_dual_frozen_obs_eval(xb, [fc, fc], {bad_key: (y_bt, y_rq)},
                                         cfg_obs, WindowConfig(dt=DT), prior)

    # ③ 어댑터 충돌 거부
    with pytest.raises(ValueError, match="not both"):
        dd.make_dual_frozen_obs_eval(xb, [fc, fc], {2: (y_bt, y_rq)},
                                     cfg_obs, WindowConfig(dt=DT), prior,
                                     allow_zero_valid_slots=True,
                                     policy=ObsGatePolicy())

    # ④ result.policy 기록 + ⑤ dataclass-only 기본
    def dc_obs(t, x_t):
        if t != 2:
            return None
        d_ = x_t.th - (xb.th + 0.3)
        adj = State(*(d_.clone() if f == "th" else torch.zeros_like(getattr(x_t, f))
                      for f in State._fields))
        return ObsEvalResult(j=float(0.5 * (d_ * d_).sum()), adj=adj,
                             n_valid=2, signature="s")
    res = run_dual_minimizer(xb, [fc, fc], dc_obs, WindowConfig(dt=DT),
                             _b_sigma(xb), prior, max_iter=2)
    assert res.policy == dict(require_signature=True, allow_zero_valid_slots=False,
                              require_obs_slots=True, allow_tuple_returns=False)

    def tup_obs(t, x_t):
        out = dc_obs(t, x_t)
        return None if out is None else (out.j, out.adj, out.n_valid, out.signature)
    with pytest.raises(TypeError, match="ObsEvalResult"):
        run_dual_minimizer(xb, [fc, fc], tup_obs, WindowConfig(dt=DT),
                           _b_sigma(xb), prior, max_iter=2)


# ── full-field KDM6 CVT (hybrid add/mul spec) — dual 경로 ────────────────────


def test_dual_fd_with_spec():
    """T17: 하이브리드 spec의 결합 클로저 gradient — 상태(add+mul) FD 대조 +
    (불변인) θ 체인이 spec 활성 상태에서도 기존 게이트를 유지하는지."""
    import dataclasses

    from kdm6.da_cvt import cvt_apply, make_default_cvt
    from kdm6.da_minimizer import _stack
    from kdm6.da_window import run_da_window
    from _cvt_test_util import fd_check

    xb, fc = _mk_state(), _mk_forcing()
    forcings = [fc, fc]
    obs = _quad_obs(xb.th + 0.3)
    prior = default_param_prior(0.2, active=("peaut",))
    spec, b_sigma = make_default_cvt(xb, enable_indirect=True)
    cfg = WindowConfig(dt=DT)

    def J_at(v_x, v_th):
        x0, _ = cvt_apply(xb, b_sigma, v_x, spec)
        params = params_from_vtheta(prior, v_th, live=False)
        jobs = [0.0]

        def oa(t, x_t):
            out = obs(t, x_t)
            if out is None:
                return None
            jobs[0] += out[0]
            return out[1]

        run_da_window(x0, forcings, oa, dataclasses.replace(cfg, params=params))
        return (0.5 * float((v_x ** 2).sum()) + 0.5 * float((v_th ** 2).sum())
                + jobs[0])

    v_x0 = torch.zeros((12, 1, 2), **_F64)
    for f in ("th", "qv", "qc"):                   # add 1개 + mul 2개 프로브
        v_x0[State._fields.index(f), 0, 0] = 0.1
    v_th0 = torch.zeros(4, **_F64)

    x0, jac = cvt_apply(xb, b_sigma, v_x0, spec)
    params_live = params_from_vtheta(prior, v_th0, live=True)
    jobs_acc = [0.0]

    def oa2(t, x_t):
        out = obs(t, x_t)
        if out is None:
            return None
        jobs_acc[0] += out[0]
        return out[1]

    r = run_da_window(x0, forcings, oa2,
                      dataclasses.replace(cfg, params=params_live,
                                          param_grads=True))
    g_x = v_x0 + jac * _stack(r.adj_x0)

    tiers = {}
    for f in ("th", "qv", "qc"):
        idx = (State._fields.index(f), 0, 0)
        tiers[f] = fd_check(lambda vv: J_at(vv, v_th0), v_x0, idx,
                            float(g_x[idx]))
    assert tiers["th"] == "strong", tiers

    # θ 체인(불변)이 spec 활성에서도 기존 2e-3 게이트 유지
    gp = torch.zeros(4, **_F64)
    if r.grad_params:
        for i, n in enumerate(PNAMES):
            if n in r.grad_params:
                gp[i] = r.grad_params[n].to(torch.float64)
    theta0 = torch.stack([params_live[i].detach() for i in range(4)])
    g_th = v_th0 + prior.sigma_log * theta0 * gp
    hth = 5.0e-3
    vp = v_th0.clone(); vp[0] += hth
    vm = v_th0.clone(); vm[0] -= hth
    fd_th = (J_at(v_x0, vp) - J_at(v_x0, vm)) / (2 * hth)
    rel_th = abs(fd_th - float(g_th[0])) / max(abs(fd_th), 1e-30)
    assert rel_th < 2.0e-3, (fd_th, float(g_th[0]), rel_th)


def test_dual_no_obs_prior_pinned_spec():
    """T18: 전 필드 spec + 무관측 → 상태·θ 모두 배경 고정 (bitwise/정확)."""
    from kdm6.da_cvt import make_default_cvt
    xb, fc = _mk_state(), _mk_forcing()
    prior = default_param_prior(0.2)
    spec, b_sigma = make_default_cvt(xb, enable_indirect=True)
    res = run_dual_minimizer(xb, [fc, fc], lambda t, x: None,
                             WindowConfig(dt=DT), b_sigma, prior,
                             max_iter=3, require_obs_slots=False, cvt=spec)
    for f in State._fields:
        assert torch.equal(getattr(res.x_analysis, f), getattr(xb, f)), f
    for i, n in enumerate(PNAMES):
        assert float(res.theta_analysis[i]) == float(prior.theta_b[i]), n
    assert float(res.v_state.abs().max()) == 0.0
    assert float(res.v_theta.abs().max()) == 0.0


def test_dual_all_add_spec_bitwise_matches_none():
    """T19: dual에서 cvt=None vs CVT_LINEAR — run 수준 bitwise 잠금."""
    from kdm6.da_cvt import CVT_LINEAR
    xb, fc = _mk_state(), _mk_forcing()
    obs_y = xb.th + 0.3
    prior = default_param_prior(0.2, active=("peaut",))
    r0 = run_dual_minimizer(xb, [fc, fc], _quad_obs(obs_y), WindowConfig(dt=DT),
                            _b_sigma(xb), prior, max_iter=6, policy=_P())
    r1 = run_dual_minimizer(xb, [fc, fc], _quad_obs(obs_y), WindowConfig(dt=DT),
                            _b_sigma(xb), prior, max_iter=6, policy=_P(),
                            cvt=CVT_LINEAR)
    for f in State._fields:
        assert torch.equal(getattr(r0.x_analysis, f),
                           getattr(r1.x_analysis, f)), f
    assert torch.equal(r0.v_state, r1.v_state)
    assert torch.equal(r0.v_theta, r1.v_theta)
    assert r0.j_trace == r1.j_trace
    assert r0.cvt is None and r1.cvt is not None


def _obs_th_slot_at(t_obs, xb, tag):
    """t_obs 단일 슬롯 th 관측 (connected_fields 표기 포함)."""
    def obs_eval(t, x_t):
        if t != t_obs:
            return None
        d = x_t.th - (xb.th + 0.3)
        j = 0.5 * (d * d).sum()
        adj = State(*(d.clone() if f == "th" else torch.zeros_like(getattr(x_t, f))
                      for f in State._fields))
        return float(j), adj, int(d.numel()), tag
    obs_eval.connected_fields = ("th",)
    return obs_eval


def test_dual_t0_only_dead_fields_raise():
    """T20/V7: t=0 단독 슬롯 + connected 밖 σ>0 → 확정 기울기-0 필드를
    '제어됨'으로 위장하는 구성 거부; t≥1 슬롯이 있으면 M^T 도달 가능 → 통과."""
    from kdm6.da_cvt import make_default_cvt
    xb, fc = _mk_state(), _mk_forcing()
    prior = default_param_prior(0.2)
    spec, b_sigma = make_default_cvt(xb)           # qv/qc/... σ>0, connected 밖

    with pytest.raises(ValueError, match="qv"):
        run_dual_minimizer(xb, [fc, fc], _obs_th_slot_at(0, xb, "t0"),
                           WindowConfig(dt=DT), b_sigma, prior,
                           max_iter=2, policy=_P(), cvt=spec)

    res = run_dual_minimizer(xb, [fc, fc], _obs_th_slot_at(1, xb, "t1"),
                             WindowConfig(dt=DT), b_sigma, prior,
                             max_iter=2, policy=_P(), cvt=spec)
    assert res.cvt is not None

    # 유효 0개 t≥1 슬롯은 M^T 결합 증거가 아님 — V7 우회 불가
    # (allow_zero_valid_slots opt-in 하에서도 기울기-보유 슬롯만 센다)
    def obs_t0_plus_empty_t1(t, x_t):
        if t == 0:
            d = x_t.th - (xb.th + 0.3)
            j = 0.5 * (d * d).sum()
            adj = State(*(d.clone() if f == "th"
                          else torch.zeros_like(getattr(x_t, f))
                          for f in State._fields))
            return float(j), adj, int(d.numel()), "t0-full"
        if t == 1:
            zadj = State(*(torch.zeros_like(getattr(x_t, f))
                           for f in State._fields))
            return 0.0, zadj, 0, "t1-empty"
        return None
    obs_t0_plus_empty_t1.connected_fields = ("th",)
    with pytest.raises(ValueError, match="qv"):
        run_dual_minimizer(xb, [fc, fc], obs_t0_plus_empty_t1,
                           WindowConfig(dt=DT), b_sigma, prior, max_iter=2,
                           policy=_P(allow_zero_valid_slots=True), cvt=spec)


def test_frozen_adapter_exposes_connected_fields(monkeypatch):
    """T21: clear-sky 동결 어댑터가 connected_fields=("th","qv")를 표기."""
    import kdm6.da_dual as dd
    import kdm6.da_driver as drv
    xb, fc = _mk_state(), _mk_forcing()
    y_bt = torch.full((1, 16), 250.0, **_F64)
    y_rq = torch.zeros((1, 16), **_F64)

    def fake_clear_bt(x_state, fc_t, cfg):
        leaves = State(*(f.detach().clone().requires_grad_(True)
                         for f in x_state))
        bt = (torch.full((1, 16), 260.0, **_F64)
              + 0.0 * (leaves.th.sum() + leaves.qv.sum()))
        return bt, torch.zeros((1, 16), **_F64), leaves

    monkeypatch.setattr(drv, "batched_clear_bt", fake_clear_bt)
    cfg_obs = type("C", (), {"obs_sigma": 1.0})()
    obs = dd.make_dual_frozen_obs_eval(xb, [fc, fc], {2: (y_bt, y_rq)},
                                       cfg_obs, WindowConfig(dt=DT),
                                       dd.default_param_prior(0.2))
    assert obs.connected_fields == ("th", "qv")


def test_dual_result_records_cvt():
    """T22: spec 경로는 round-trip 가능한 cvt 레코드, 레거시는 None."""
    from kdm6.da_cvt import CvtSpec, make_default_cvt
    xb, fc = _mk_state(), _mk_forcing()
    obs_y = xb.th + 0.3
    prior = default_param_prior(0.2)
    spec, b_sigma = make_default_cvt(xb, enable_indirect=True)
    res = run_dual_minimizer(xb, [fc, fc], _quad_obs(obs_y), WindowConfig(dt=DT),
                             b_sigma, prior, max_iter=3, policy=_P(), cvt=spec)
    assert res.cvt is not None
    assert CvtSpec.from_dict(res.cvt["spec"]) == spec
    json.dumps(res.cvt)                             # 직렬화 가능해야 함
    res0 = run_dual_minimizer(xb, [fc, fc], _quad_obs(obs_y), WindowConfig(dt=DT),
                              _b_sigma(xb), prior, max_iter=2, policy=_P())
    assert res0.cvt is None
