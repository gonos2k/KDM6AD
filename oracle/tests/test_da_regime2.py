"""Regime-2 (모델 맑음 / 관측 구름) 자료동화 — M-gate 증명과 pseudo-RH 부트스트랩.

배경이 진짜 맑음(전 응결수 0)이고 미포화(RH<100%)이면 3중 gate가 닫힌다:
CVT(V3: σ=0 at xb=0), H(cfrac detached), M(satadj 과포화 분기). 특히 M-gate:
∂pcond/∂qv = 0 이웃 → t≥1 qc-관측의 adjoint가 qv0/th0에 정확히 0으로 도달,
L-BFGS는 prior에 pin된다 (T-R2a 음성 대조). 설계 해법(pseudo-RH 부트스트랩)은
T-R2b가 검증한다.
"""
from __future__ import annotations

import torch

from kdm6 import thermo
from kdm6.da_cvt import make_default_cvt
from kdm6.da_minimizer import run_minimizer
from kdm6.da_window import WindowConfig, run_da_window
from kdm6.state import Forcing, State

DT = 20.0
_F64 = dict(dtype=torch.float64)


def _t2(a, b):
    return torch.tensor([[a, b]], **_F64)


def _mk_clear_state(rh: float = 0.97):
    """진짜 regime-2 배경: 전 응결수 0 + 미포화 (RH=rh)."""
    th, pii, p = _t2(296.8, 282.4), _t2(0.9704, 0.9031), _t2(9.0e4, 7.0e4)
    qs = thermo.compute_qs_water(th * pii, p, params=thermo.default_thermo_params())
    z = torch.zeros_like(th)
    return State(th=th, qv=rh * qs, qc=z.clone(), qr=z.clone(), qi=z.clone(),
                 qs=z.clone(), qg=z.clone(), nccn=torch.full_like(th, 1.0e9),
                 nc=z.clone(), ni=z.clone(), nr=z.clone(), bg=z.clone())


def _mk_forcing():
    return Forcing(rho=_t2(1.089, 0.9567), pii=_t2(0.9704, 0.9031),
                   p=_t2(9.0e4, 7.0e4), delz=_t2(500.0, 500.0))


def _zeros(ref):
    return State(**{k: torch.zeros_like(v) for k, v in ref._asdict().items()})


def _obs_qc_at(t_obs: int, y: torch.Tensor, sigma_o: float):
    """t_obs에서 qc 전체 관측 (합성 '구름 관측' — H=identity on qc)."""
    def obs_eval(t, x_t):
        if t != t_obs:
            return None
        r = (x_t.qc - y) / sigma_o
        j = 0.5 * (r * r).sum()
        adj = _zeros(x_t)._replace(qc=r / sigma_o)
        return j, adj
    return obs_eval


def test_regime2_negative_control_m_gate_pins_prior():
    """T-R2a: 미포화 clear 배경 + t=1 구름 관측, pseudo 없음 → satadj
    과포화 분기가 닫혀 ∂J_obs/∂(qv0,th0) ≡ 0 — 전 필드 prior pin (bitwise).
    (M-gate의 존재 증명: regime-2가 '조용히 아무것도 못 하는' 현행 상태.)"""
    xb = _mk_clear_state(rh=0.97)
    forcings = [_mk_forcing()]
    cfg = WindowConfig(dt=DT)
    # 배경 forward가 진짜 맑음 유지인지 먼저 고정 (자기일관)
    fin = run_da_window(xb, forcings, lambda t, x: None, cfg).state_final
    assert float(fin.qc.abs().max()) == 0.0, "배경이 자발 응결 — RH 조정 필요"

    y = torch.full_like(xb.qc, 2.0e-4)              # 구름을 요구하는 관측
    spec, b_sigma = make_default_cvt(xb)
    assert float(b_sigma.qc.abs().max()) == 0.0     # V3: 생성 DOF 없음
    res = run_minimizer(xb, forcings, _obs_qc_at(1, y, sigma_o=1.0e-5),
                        cfg, b_sigma, max_iter=8, cvt=spec)
    assert res.jobs_final > 0.0                     # 관측은 활성인데
    for f in State._fields:                         # 아무것도 못 움직인다
        assert torch.equal(getattr(res.x_analysis, f), getattr(xb, f)), f
    assert float(res.v.abs().max()) == 0.0


def test_regime2_pseudo_rh_bootstrap_creates_cloud():
    """T-R2b: pseudo-RH 부트스트랩 — 동일 배경·동일 구름 관측에 동결 pseudo
    항을 합성하면 (a) qv0 가습 방향 증분, (b) 분석 forward에서 qc(t=1) > 0
    (모델 satadj가 생성 — CVT가 아님: x_a.qc0 == 0 bitwise), (c) J 하강,
    (d) |Δth| ≤ 3σ_th (냉각 유계)."""
    from kdm6.da_regime2 import (frozen_saturation_target,
                                 wrap_obs_eval_with_pseudo_rh)

    xb = _mk_clear_state(rh=0.97)
    fc = _mk_forcing()
    forcings = [fc]
    cfg = WindowConfig(dt=DT)
    y = torch.full_like(xb.qc, 2.0e-4)
    spec, b_sigma = make_default_cvt(xb)

    base = _obs_qc_at(1, y, sigma_o=1.0e-5)
    cols = torch.tensor([0])                        # 동결 C2 (단일 컬럼, K=2층)
    target = frozen_saturation_target(xb, fc, cols)  # (1+δ)·상전이-인지 qs
    obs_eval = wrap_obs_eval_with_pseudo_rh(
        base, t_obs=1, cols=cols, target=target, sigma_p=2.0e-4)
    res = run_minimizer(xb, forcings, obs_eval, cfg, b_sigma,
                        max_iter=20, cvt=spec)

    assert res.j_trace[-1] < res.j_trace[0]
    assert bool((res.x_analysis.qv > xb.qv).any()), "가습 방향 증분 없음"
    assert torch.equal(res.x_analysis.qc, xb.qc)    # 생성은 CVT 경유가 아님
    # 강건 교차 (판정 수정 ①): 분석 qv가 live 물-포화를 '설계상' 넘는다
    qs_live = thermo.compute_qs_water(res.x_analysis.th * fc.pii, fc.p,
                                      params=thermo.default_thermo_params())
    assert bool((res.x_analysis.qv[0, 0] > qs_live[0, 0])), \
        "정지점이 미포화 — 교차가 라인서치 운에 의존 (판정 flaw 1 재발)"
    fin = run_da_window(res.x_analysis, forcings, lambda t, x: None,
                        cfg).state_final
    assert float(fin.qc.max()) > 0.0, "모델이 구름을 생성하지 못함"
    dth = (res.x_analysis.th - xb.th).abs().max()
    assert float(dth) <= 3.0 * 0.8, f"냉각 aliasing 초과: {float(dth)}"


# ── gated live: 실관측 regime-2 (LC05 모델-맑음/관측-구름 컬럼) ──────────────

def _lc05_gate():
    from pathlib import Path
    import pytest as _pt
    repo = Path(__file__).resolve().parents[2]
    wrfin = Path("/Users/yhlee/KDM6AD+/KIM-meso_v1.0/test/"
                 "ss_real_case_20260619_063620/SS/wrfinput_d01")
    gk2a = repo / "GK2A"
    cal = repo / "oracle" / "kdm6" / "obs" / "data" / "gk2a_ami_cal_202507190000.json"
    try:
        from test_rttov_case_writer import _HAVE_CLOUD_EXE, _HAVE_EXE
    except Exception:
        _HAVE_EXE = _HAVE_CLOUD_EXE = False
    if not (wrfin.exists() and gk2a.is_dir() and cal.exists()
            and _HAVE_EXE and _HAVE_CLOUD_EXE):
        _pt.skip("LC05/GK2A/검정/live cloud RTTOV 부재")
    return wrfin, gk2a, cal


def test_regime2_live_bootstrap_lc05(tmp_path):
    """T-R2c: 실관측 regime-2 — 모델-맑음/관측-구름 4컬럼, all-sky 어댑터 +
    동결 pseudo-RH(구름정상 온도매칭 층) 합성, 슬롯 t=1.
    게이트: J 하강 + 분석 forward에서 qc(t1) 생성(≥1 컬럼) + Δth 유계."""
    import numpy as np
    from kdm6.da_cvt import make_default_cvt
    from kdm6.da_driver import OsseObsConfig
    from kdm6.da_dual import (default_param_prior, make_dual_frozen_obs_eval,
                              run_dual_minimizer)
    from kdm6.da_regime2 import (cloud_top_levels, frozen_saturation_target,
                                 wrap_dual_obs_eval_with_pseudo_rh)
    from kdm6.io.frame_reader import read_wrfout_frame
    from kdm6.obs.gk2a_l1b import (CLEAN_IR_CHANNELS, load_cal_table,
                                   read_ko_slot, slot_files)
    from kdm6.obs.obs_ingest import payload_to_column_obs
    from kdm6.obs.model_profile_builder import RttovProfileConfig
    from kdm6.obs.rttov_case_writer import (fixture_layer_pressure,
                                            make_live_run_k)
    from kdm6.obs.rttov_input_builder import RttovInputConfig
    from test_rttov_case_writer import _CHANNELS, _fixture_p_half, _fixture_tq

    wrfin, gk2a, cal_p = _lc05_gate()
    fr = read_wrfout_frame(str(wrfin), 0)
    cal = load_cal_table(cal_p)
    pl = read_ko_slot(slot_files(gk2a, "202507190000",
                                 channels=CLEAN_IR_CHANNELS), cal, stride=8)
    co = payload_to_column_obs(pl, fr.meta["lat"], fr.meta["lon"],
                               max_dist_km=4.0)

    qtot = (fr.state.qc + fr.state.qi + fr.state.qs).sum(-1)
    r2 = torch.where((co.obs_quality[:, 12] == 0) & (co.bt[:, 12] < 270.0)
                     & (qtot < 1.0e-6))[0]           # 모델-맑음/관측-구름
    assert r2.numel() >= 4, f"regime-2 컬럼 부족: {int(r2.numel())}"
    sel = r2[torch.argsort(co.bt[r2, 12])[:4]]       # 가장 찬(구름 짙은) 4개
    xb = State(**{k: v[sel] for k, v in fr.state._asdict().items()})
    fc = Forcing(**{k: v[sel] for k, v in fr.forcing._asdict().items()})
    y_bt, y_rq = co.bt[sel], co.obs_quality[sel]

    tr, qr = _fixture_tq()
    obs_cfg = OsseObsConfig(
        run_k=make_live_run_k(tmp_path / "r2"),
        profile_cfg=RttovProfileConfig(
            gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
            rttov_layer_pressure=torch.as_tensor(
                np.asarray(fixture_layer_pressure(), dtype=float), **_F64),
            rttov_level_pressure=torch.as_tensor(
                np.asarray(_fixture_p_half(), dtype=float), **_F64),
            cloud=True),
        input_cfg=RttovInputConfig(coef_id="ami_cloud", channels=_CHANNELS),
        obs_sigma=1.0,
        t_ref=torch.as_tensor(np.asarray(tr, dtype=float), **_F64),
        q_ref=torch.as_tensor(np.asarray(qr, dtype=float), **_F64))

    cfg = WindowConfig(dt=300.0)
    prior = default_param_prior(0.2)
    K = xb.th.shape[1]
    spec, b_sigma = make_default_cvt(xb, qv_levels=K)   # 상층 구름 → 전층 qv
    cols = torch.arange(4)                              # 동결 C2 = 전 선택 컬럼
    levels = cloud_top_levels(xb, fc, cols, y_bt[:, 12])
    target = frozen_saturation_target(xb, fc, cols)     # 상전이-인지, 동결
    base = make_dual_frozen_obs_eval(xb, [fc], {1: (y_bt, y_rq)}, obs_cfg,
                                     cfg, prior, cloud=True,
                                     xland=fr.xland[sel])
    obs_eval = wrap_dual_obs_eval_with_pseudo_rh(
        base, t_obs=1, cols=cols, target=target, sigma_p=2.0e-4,
        levels=levels)
    res = run_dual_minimizer(xb, [fc], obs_eval, cfg, b_sigma, prior,
                             max_iter=6, cvt=spec)

    assert res.j_trace[-1]["total"] < res.j_trace[0]["total"]
    fin = run_da_window(res.x_analysis, [fc], lambda t, x: None,
                        cfg).state_final
    # 냉구름 컬럼(BT<270K)의 생성물은 빙정 핵생성 경유 qi (실측: RH_ice가
    # 1.08 문턱을 넘은 컬럼에서 qi 생성; 물-포화 아래라 qc가 아님)
    created = float((fin.qc + fin.qi + fin.qs).max())
    assert created > 0.0, "실관측 부트스트랩이 구름(수물질)을 생성하지 못함"
    dth = float((res.x_analysis.th - xb.th).abs().max())
    assert dth <= 3.0 * 0.8, f"냉각 aliasing 초과: {dth}"
    # σ=0 필드 pin 유지 (regime-2 경로가 다른 계약을 흔들지 않음)
    for f in ("qr", "qg", "nr", "nccn", "bg"):
        assert torch.equal(getattr(res.x_analysis, f), getattr(xb, f)), f


def test_dual_pseudo_wrapper_reports_count_and_connectivity():
    """Codex 지적 회귀: ① n_valid 가산 = 실제 활성 pseudo 셀 수 (인덱스
    목록 levels 포함), ② 합성 connected_fields에 qv가 반드시 포함
    (base 태그에 없어도 — pseudo가 qv 직접 민감도를 부여하므로)."""
    from kdm6.da_dual import ObsEvalResult
    from kdm6.da_regime2 import (frozen_saturation_target,
                                 wrap_dual_obs_eval_with_pseudo_rh)

    xb = _mk_clear_state(rh=0.97)
    fc = _mk_forcing()
    cols = torch.tensor([0])
    target = frozen_saturation_target(xb, fc, cols)

    def base(t, x_t):                        # th 전용 커스텀 base (qv 태그 없음)
        if t != 1:
            return None
        adj = _zeros(x_t)
        return ObsEvalResult(j=1.0, adj=adj, n_valid=7, signature="base-sig")
    base.connected_fields = ("th",)

    K = xb.th.shape[1]
    for levels, expect in ((None, 1 * K),                      # 전층
                           (torch.tensor([1]), 1),             # 인덱스 목록
                           (torch.tensor([[True, False]]), 1)):  # bool mask
        w = wrap_dual_obs_eval_with_pseudo_rh(
            base, t_obs=1, cols=cols, target=target, sigma_p=2.0e-4,
            levels=levels)
        out = w(1, xb)
        assert out.n_valid == 7 + expect, (levels, out.n_valid)
        assert "qv" in w.connected_fields
        assert "th" in w.connected_fields


def test_dual_pseudo_wrapper_rejects_duplicates():
    """Codex 지적 회귀: 중복 cols/인덱스형 levels는 j 이중 계상 + 비누적
    scatter의 covector 불일치(adj ≠ ∇j)와 n_valid 과대 집계 — 즉시 거부."""
    import pytest
    from kdm6.da_dual import ObsEvalResult
    from kdm6.da_regime2 import (frozen_saturation_target,
                                 wrap_dual_obs_eval_with_pseudo_rh,
                                 wrap_obs_eval_with_pseudo_rh)

    xb = _mk_clear_state(rh=0.97)
    fc = _mk_forcing()
    cols = torch.tensor([0])
    target = frozen_saturation_target(xb, fc, cols)

    def base(t, x_t):
        return None
    with pytest.raises(ValueError, match="duplicate"):
        wrap_dual_obs_eval_with_pseudo_rh(
            base, t_obs=1, cols=cols, target=target, sigma_p=2.0e-4,
            levels=torch.tensor([1, 1]))
    with pytest.raises(ValueError, match="duplicate"):
        wrap_dual_obs_eval_with_pseudo_rh(
            base, t_obs=1, cols=torch.tensor([0, 0]),
            target=target.repeat(2, 1), sigma_p=2.0e-4)
    with pytest.raises(ValueError, match="duplicate"):
        wrap_obs_eval_with_pseudo_rh(
            base, t_obs=1, cols=torch.tensor([0, 0]),
            target=target.repeat(2, 1), sigma_p=2.0e-4)
