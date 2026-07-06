"""첫 실관측 innovation 게이트 — LC05 x0 (2025-07-19 00 UTC) vs 실 GK2A (§6.2 ②③).

전 체인(검정계수→DN→BT→LCC 지오로케이션→collocation→wrfinput 상태 유도→RTTOV
프로파일→clear-sky H→adjoint)의 통합 물리 게이트. 핵심 불변식:

  - 실그리드 collocation: 배정률·충돌·BT 물리범위.
  - 맑음-추정 O-B: window 채널(ir112) |mean| < 2K, std < 3K — 7단 체인 어디든
    계통 오차(단위/K-순서/파장/투영)가 있으면 수 K bias로 즉시 실패한다
    (실측 2026-07-07: ir112 mean −0.04K std 1.19K, ir123 +0.05K/1.16K).
  - 실관측 adjoint: J>0, ∂J/∂th nonzero, 최대 감도 레벨이 하부 대류권
    (IR window 가중함수의 교과서적 위치 — 실측 k=10 ≈ 792hPa).

게이트: 외부 자산 4종 필요 — LC05 wrfinput(KDM6AD+), GK2A KO 세트, 검정 테이블,
live RTTOV. 하나라도 없으면 skip (공개 CI에선 항상 skip; 로컬 실검증용).
"""
from __future__ import annotations

from pathlib import Path

import pytest
import torch

_REPO = Path(__file__).resolve().parents[2]
_WRFIN = Path("/Users/yhlee/KDM6AD+/KIM-meso_v1.0/test/"
              "ss_real_case_20260619_063620/SS/wrfinput_d01")
_GK2A = _REPO / "GK2A"
_CAL = _REPO / "oracle" / "kdm6" / "obs" / "data" / "gk2a_ami_cal_202507190000.json"

try:
    from test_rttov_case_writer import _HAVE_EXE
except Exception:                                            # pragma: no cover
    _HAVE_EXE = False

needs_all = pytest.mark.skipif(
    not (_WRFIN.exists() and _GK2A.is_dir() and _CAL.exists() and _HAVE_EXE),
    reason="LC05 wrfinput / GK2A KO / cal table / live RTTOV 중 부재")

_F64 = dict(dtype=torch.float64)


@pytest.fixture(scope="module")
def lc05_collocated():
    from kdm6.io.frame_reader import read_wrfout_frame
    from kdm6.obs.gk2a_l1b import (CLEAN_IR_CHANNELS, load_cal_table,
                                   read_ko_slot, slot_files)
    from kdm6.obs.obs_ingest import payload_to_column_obs
    fr = read_wrfout_frame(str(_WRFIN), 0)
    cal = load_cal_table(_CAL)
    # 주간 케이스 표준: sw038 제외 깨끗한 IR 9채널 (사용자 지시 2026-07-07)
    pl = read_ko_slot(slot_files(_GK2A, "202507190000", channels=CLEAN_IR_CHANNELS),
                      cal, stride=8)
    co = payload_to_column_obs(pl, fr.meta["lat"], fr.meta["lon"], max_dist_km=4.0)
    return fr, co


@needs_all
def test_real_grid_collocation_physical(lc05_collocated):
    fr, co = lc05_collocated
    B = fr.state.th.shape[0]
    assert co.n_assigned > 0.08 * B          # stride 8 → ~10% 배정 (실측 ~12%)
    assert co.n_dropped_collision == 0       # 16km 솎음 > 5km 격자 → 1:1
    ok = co.obs_quality[:, 12] == 0
    bt = co.bt[ok, 12]
    assert 180.0 < float(bt.min()) and float(bt.max()) < 320.0
    assert fr.meta["nccn_fallback"] is True  # wrfinput QNCCN=0 → 래퍼 폴백 작동


@needs_all
def test_real_innovation_omb_and_adjoint(lc05_collocated, tmp_path):
    import numpy as np
    from kdm6.da_driver import OsseObsConfig, batched_clear_bt
    from kdm6.obs.model_profile_builder import RttovProfileConfig
    from kdm6.obs.rttov_case_writer import fixture_layer_pressure, make_live_run_k
    from kdm6.obs.rttov_input_builder import RttovInputConfig
    from kdm6.state import Forcing, State
    from test_rttov_case_writer import _CHANNELS, _fixture_p_half, _fixture_tq

    fr, co = lc05_collocated
    assigned = torch.where(co.obs_quality[:, 12] == 0)[0]
    order = assigned[torch.argsort(co.bt[assigned, 12])]
    sel = order[torch.linspace(0, len(order) - 1, 64).long()]   # 층화 64컬럼
    x0 = State(**{k: v[sel] for k, v in fr.state._asdict().items()})
    fc = Forcing(**{k: v[sel] for k, v in fr.forcing._asdict().items()})
    y_bt, y_rq = co.bt[sel], co.obs_quality[sel]

    tr, qr = _fixture_tq()
    cfg = OsseObsConfig(
        run_k=make_live_run_k(tmp_path / "real_innov_case"),
        profile_cfg=RttovProfileConfig(
            gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
            rttov_layer_pressure=torch.as_tensor(
                np.asarray(fixture_layer_pressure(), dtype=float), **_F64),
            rttov_level_pressure=torch.as_tensor(
                np.asarray(_fixture_p_half(), dtype=float), **_F64)),
        input_cfg=RttovInputConfig(coef_id="ami_501_test", channels=_CHANNELS),
        obs_sigma=1.0,
        t_ref=torch.as_tensor(np.asarray(tr, dtype=float), **_F64),
        q_ref=torch.as_tensor(np.asarray(qr, dtype=float), **_F64))

    bt_mod, rad_quality, leaves = batched_clear_bt(x0, fc, cfg)
    mask = ((y_rq == 0) & (rad_quality == 0)).double()

    # 맑음-추정(관측 IR105 상위 25%) window 채널 O-B — 체인 계통오차 게이트
    clear = y_bt[:, 12] > torch.quantile(y_bt[:, 12], 0.75)
    j112 = 13                                                    # ir112
    m = (mask[:, j112] > 0) & clear
    assert int(m.sum()) >= 8
    d = (y_bt[:, j112] - bt_mod.detach()[:, j112])[m]
    assert abs(float(d.mean())) < 2.0, f"ir112 clear O-B mean {float(d.mean()):+.2f}K"
    assert float(d.std()) < 3.0, f"ir112 clear O-B std {float(d.std()):.2f}K"

    # 실관측 innovation adjoint — nonzero + 하부 대류권 최대 감도
    j_obs = 0.5 * ((mask * (bt_mod - y_bt) / cfg.obs_sigma) ** 2).sum()
    assert float(j_obs.detach()) > 0.0
    j_obs.backward()
    th_g = leaves.th.grad
    assert th_g is not None and float(th_g.norm()) > 0.0
    kmax = int(th_g.abs().sum(0).argmax())
    assert 3 <= kmax <= 20, f"th-adjoint peak k={kmax} (하부 대류권 기대)"


@needs_all
def test_real_allsky_beats_clear_on_cloudy_columns(lc05_collocated, tmp_path):
    """첫 실관측 all-sky 게이트 (kdm6ad+da.md 본류): 구름 컬럼(관측 IR105<270K)
    에서 (a) all-sky |O-B| < clear-sky |O-B| 가 다수, (b) 하이드로미티어
    gradient(∂J/∂qi) nonzero — 관측→구름상태 역전파 경로의 존재 증명.

    실측 (2026-07-07, B=24): clear mean −46.4K → all-sky −13.6K, 24/24 개선;
    ∂J/∂qc~1.2e9, ∂J/∂qi~4.8e8, ∂J/∂qs~3.6e8. 여기선 B=6 경량 게이트.
    """
    import numpy as np
    from kdm6.da_driver import OsseObsConfig, _blend_above_model_top, batched_clear_bt
    from kdm6.obs.model_profile_builder import (RttovProfileConfig,
                                                model_to_rttov_tensors)
    from kdm6.obs.rttov_case_writer import fixture_layer_pressure, make_live_run_k
    from kdm6.obs.rttov_input_builder import RttovInputConfig
    from kdm6.obs.rttov_obs_operator import RttovObsOp
    from kdm6.state import Forcing, State
    from test_rttov_case_writer import (_CHANNELS, _HAVE_CLOUD_EXE,
                                        _fixture_p_half, _fixture_tq)
    if not _HAVE_CLOUD_EXE:
        pytest.skip("live cloud RTTOV (ami_cloud) 부재")

    fr, co = lc05_collocated
    qtot = (fr.state.qc + fr.state.qi + fr.state.qs).sum(1)
    cloudy = torch.where((co.obs_quality[:, 12] == 0) & (co.bt[:, 12] < 270.0)
                         & (qtot > 1e-5))[0]
    order = cloudy[torch.argsort(co.bt[cloudy, 12])]
    sel = order[torch.linspace(0, len(order) - 1, 6).long()]
    x0 = State(**{k: v[sel] for k, v in fr.state._asdict().items()})
    fc = Forcing(**{k: v[sel] for k, v in fr.forcing._asdict().items()})
    y_bt, y_rq = co.bt[sel], co.obs_quality[sel]

    tr, qr = _fixture_tq()
    p_half_t = torch.as_tensor(np.asarray(_fixture_p_half(), dtype=float), **_F64)
    p_lay_t = torch.as_tensor(np.asarray(fixture_layer_pressure(), dtype=float), **_F64)
    ccfg = OsseObsConfig(
        run_k=make_live_run_k(tmp_path / "clear"),
        profile_cfg=RttovProfileConfig(
            gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
            rttov_layer_pressure=p_lay_t, rttov_level_pressure=p_half_t),
        input_cfg=RttovInputConfig(coef_id="ami_501_test", channels=_CHANNELS),
        obs_sigma=1.0,
        t_ref=torch.as_tensor(np.asarray(tr, dtype=float), **_F64),
        q_ref=torch.as_tensor(np.asarray(qr, dtype=float), **_F64))
    bt_clear = batched_clear_bt(x0, fc, ccfg)[0].detach()

    pcfg = RttovProfileConfig(gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
                              rttov_layer_pressure=p_lay_t,
                              rttov_level_pressure=p_half_t, cloud=True)
    icfg = RttovInputConfig(coef_id="ami_cloud", channels=_CHANNELS)
    j105, better, qi_norm2 = 12, 0, 0.0
    for i in range(len(sel)):
        leaves = State(*(torch.flip(f[i], [-1]).detach().clone().requires_grad_(True)
                         for f in x0))
        fcol = Forcing(rho=torch.flip(fc.rho[i], [-1]),
                       pii=torch.flip(fc.pii[i], [-1]),
                       p=torch.flip(fc.p[i], [-1]) / 100.0,
                       delz=torch.flip(fc.delz[i], [-1]))
        prof = model_to_rttov_tensors(leaves, fcol, pcfg, xland=fr.xland[sel][i])
        p_top = fcol.p[0].reshape(1)
        t_lay = _blend_above_model_top(prof.t_lay.unsqueeze(0), ccfg.t_ref,
                                       prof.p_lay, p_top, octaves=1.0).squeeze(0)
        q_lay = _blend_above_model_top(prof.q_lay.unsqueeze(0), ccfg.q_ref,
                                       prof.p_lay, p_top, octaves=4.0).squeeze(0)
        above = (prof.p_lay < p_top).double().detach()
        bt_i, rq_i = RttovObsOp.apply(
            make_live_run_k(tmp_path / f"allsky_{i}"), icfg,
            t_lay, q_lay, None, prof.p_half,
            prof.clw * (1 - above), prof.ciw * (1 - above),
            prof.deff_liq, prof.deff_ice, prof.cfrac)
        mask = ((y_rq[i] == 0) & (rq_i.reshape(-1) == 0)).double()
        j_i = 0.5 * ((mask * (bt_i.reshape(-1) - y_bt[i])) ** 2).sum()
        j_i.backward()
        if abs(float(bt_i.reshape(-1)[j105].detach()) - float(y_bt[i, j105])) < \
           abs(float(bt_clear[i, j105]) - float(y_bt[i, j105])):
            better += 1
        g = leaves.qi.grad
        if g is not None:
            qi_norm2 += float(g.norm()) ** 2
    assert better >= 4, f"all-sky가 clear보다 나은 컬럼 {better}/6 (≥4 기대)"
    assert qi_norm2 > 0.0, "∂J/∂qi 전부 0 — 관측→구름상태 역전파 경로 부재"
