"""Tier-0 조립 검증: 실프레임 OSSE 민감도 사이클 (da_driver).

frame reader → 컬럼 선택 → 창 adjoint + 배치 live RTTOV obs → WindowResult.
wrfout(사설 host 트리) + live RTTOV 둘 다 필요 — 없으면 skip.

correctness 불변식 (타이밍 무관):
  - 진실==배경이면 innovation=0 → J≈0, adj_x0.th ≈ 0 (자기일관성).
  - 배경 섭동 시 J>0, 관측 필드(th) covector가 유한·비영이며 창을 통해
    x0까지 전파된다.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch

from kdm6.da_driver import OsseObsConfig, run_osse_sensitivity
from kdm6.da_window import WindowConfig
from kdm6.io import read_wrfout_frame
from kdm6.state import Forcing, State

from tests.test_rttov_case_writer import (
    _CHANNELS, _HAVE_EXE, _fixture_p_half, _fixture_tq, make_live_run_k)

_REPO = Path(__file__).resolve().parents[2]
_WRFOUT = _REPO / "host" / "KIM-meso_v1.0" / "run" / "wrfout.37.quarter_ss.nc"
needs_all = pytest.mark.skipif(
    not (_WRFOUT.exists() and _HAVE_EXE),
    reason="needs local SS wrfout + live RTTOV (AD-RTTOV)")

_F64 = dict(dtype=torch.float64)
B_TEST, T_TEST, DT = 6, 3, 300.0


def _sub(frame, idx):
    s = State(**{k: v[idx] for k, v in frame.state._asdict().items()})
    f = Forcing(**{k: v[idx] for k, v in frame.forcing._asdict().items()})
    return s, f


def _obs_cfg(tmp_path):
    from kdm6.obs.model_profile_builder import RttovProfileConfig
    from kdm6.obs.rttov_case_writer import fixture_layer_pressure
    from kdm6.obs.rttov_input_builder import RttovInputConfig
    import numpy as np
    profile_cfg = RttovProfileConfig(
        gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
        rttov_layer_pressure=torch.as_tensor(
            np.asarray(fixture_layer_pressure(), dtype=float), **_F64),
        rttov_level_pressure=torch.as_tensor(
            np.asarray(_fixture_p_half(), dtype=float), **_F64))
    input_cfg = RttovInputConfig(coef_id="ami_501_test", channels=_CHANNELS)
    # 모델-상단(~60 hPa) 위 기준 프로파일: 픽스처 001의 T/Q (regression-limit
    # 플래그 방지 — 클램프 상수 연장은 rad_quality=1로 mask 전멸, 실측)
    t_ref_np, q_ref_np = _fixture_tq()
    return OsseObsConfig(run_k=make_live_run_k(tmp_path / "osse_case"),
                         profile_cfg=profile_cfg, input_cfg=input_cfg,
                         obs_sigma=1.0,
                         t_ref=torch.as_tensor(np.asarray(t_ref_np, dtype=float), **_F64),
                         q_ref=torch.as_tensor(np.asarray(q_ref_np, dtype=float), **_F64))


@needs_all
def test_osse_cycle_end_to_end(tmp_path):
    frame = read_wrfout_frame(str(_WRFOUT), time_idx=1)
    idx = torch.linspace(0, frame.state.th.shape[0] - 1, B_TEST).long()
    x_true, f = _sub(frame, idx)
    forcings = [f] * T_TEST
    cfg = WindowConfig(dt=DT)
    obs_cfg = _obs_cfg(tmp_path)

    # 배경 = 진실 + 하층 th 섭동 (+0.5 K, k<10)
    th_b = x_true.th.clone()
    th_b[:, :10] += 0.5
    x_bg = x_true._replace(th=th_b)

    rep = run_osse_sensitivity(x_true, x_bg, forcings, [T_TEST], cfg, obs_cfg)

    assert rep.n_obs_times == 1
    assert rep.j_obs > 0.0                                # innovation 존재
    g = rep.window.adj_x0.th
    assert torch.isfinite(g).all()
    assert float(g.abs().sum()) > 0.0                     # 민감도가 x0까지 전파
    assert rep.adj_norms["th"] > 0.0
    assert len(rep.top_th) == 5


@needs_all
def test_osse_selfconsistency_zero_innovation(tmp_path):
    """진실==배경 → innovation=0 → J≈0, ∂J/∂x0 ≈ 0 (전 체인 자기일관성)."""
    frame = read_wrfout_frame(str(_WRFOUT), time_idx=1)
    idx = torch.linspace(0, frame.state.th.shape[0] - 1, B_TEST).long()
    x_true, f = _sub(frame, idx)
    rep = run_osse_sensitivity(x_true, x_true, [f] * T_TEST, [T_TEST],
                               WindowConfig(dt=DT), _obs_cfg(tmp_path))
    assert rep.j_obs == pytest.approx(0.0, abs=1e-10)
    assert float(rep.window.adj_x0.th.abs().max()) == pytest.approx(0.0, abs=1e-12)


def test_truth_side_quality_flags_gate_the_mask():
    """Codex stop-review 회귀 가드 (mock — 어디서나 실행): 진실측 rad_quality가
    플래그한 채널의 y(무효 관측, 절대값 1e6)는 innovation에서 배제돼야 한다.
    수정 전(진실측 QC 무시)이면 J가 ~1e12로 폭발, 수정 후엔 ~0."""
    from kdm6.da_driver import make_innovation_obs_adjoint, OsseObsConfig
    from kdm6.obs.model_profile_builder import RttovProfileConfig
    from kdm6.obs.rttov_input_builder import RttovInputConfig

    B, nlev, nch, nlay = 2, 12, 4, 9

    def mock_run_k(rin):
        n = rin.nprofiles
        bt = np.full((n, nch), 250.0)
        k = {"T": np.zeros((n, nch, nlay)), "Q": np.zeros((n, nch, nlay))}
        return bt, k, np.zeros((n, nch))          # 배경측은 전 채널 깨끗

    p_lay = torch.linspace(100.0, 900.0, nlay, **_F64)
    p_half = torch.linspace(95.0, 905.0, nlay + 1, **_F64)
    cfg = OsseObsConfig(
        run_k=mock_run_k,
        profile_cfg=RttovProfileConfig(
            gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
            rttov_layer_pressure=p_lay, rttov_level_pressure=p_half),
        input_cfg=RttovInputConfig(coef_id="mock", channels=tuple(range(1, nch + 1))),
        obs_sigma=1.0)

    # 진실측 y: 채널 0은 플래그(quality=1) + 절대값 1e6, 나머지는 mock bt와 동일
    y_bt = torch.full((B, nch), 250.0, **_F64)
    y_bt[:, 0] = 1.0e6
    y_rq = torch.zeros((B, nch), **_F64)
    y_rq[:, 0] = 1.0                              # 진실측에서만 플래그
    y_store = {1: (y_bt, y_rq)}

    z = torch.zeros((B, nlev), **_F64)
    x = State(th=torch.full((B, nlev), 280.0, **_F64),
              qv=torch.full((B, nlev), 5.0e-3, **_F64),
              qc=z, qr=z, qi=z, qs=z, qg=z, nccn=z, nc=z, ni=z, nr=z, bg=z)
    p_model = torch.linspace(9.5e4, 1.0e4, nlev, **_F64).repeat(B, 1)  # WRF: k↑ p↓
    f = Forcing(rho=torch.ones_like(z), pii=torch.ones_like(z),
                p=p_model, delz=torch.ones_like(z))

    j_acc: list = []
    adj = make_innovation_obs_adjoint([f], y_store, cfg, j_acc)(1, x)
    assert adj is not None
    # 플래그 채널 배제 → 잔차 0인 채널만 남아 J ~ 0 (무시하면 ~1e12)
    assert j_acc[0] < 1.0, f"truth-side flagged channel leaked into J: {j_acc[0]:.3e}"


@needs_all
def test_osse_analysis_reduces_background_error(tmp_path):
    """조인트 DA 게이트: CVT+L-BFGS 분석이 J를 낮추고, 관측된 자유도(th)의
    배경 오차를 진실 대비 줄인다 (실프레임 + live RTTOV, 소규모)."""
    from kdm6.da_driver import run_osse_analysis

    frame = read_wrfout_frame(str(_WRFOUT), time_idx=1)
    idx = torch.linspace(0, frame.state.th.shape[0] - 1, 4).long()
    x_true, f = _sub(frame, idx)
    forcings = [f] * 2                                    # 짧은 창 (테스트 비용)
    cfg = WindowConfig(dt=DT)
    obs_cfg = _obs_cfg(tmp_path)

    th_b = x_true.th.clone(); th_b[:, :10] += 0.8
    x_bg = x_true._replace(th=th_b)

    z = torch.zeros_like(x_true.th)
    b_sigma = State(th=torch.full_like(z, 1.0), qv=z, qc=z, qr=z, qi=z, qs=z,
                    qg=z, nccn=z, nc=z, ni=z, nr=z, bg=z)

    rep = run_osse_analysis(x_true, x_bg, forcings, [2], cfg, obs_cfg,
                            b_sigma, max_iter=4)

    assert rep.minimize.j_trace[-1] < rep.minimize.j_trace[0], rep.minimize.j_trace
    assert rep.th_err_an < rep.th_err_bg, (rep.th_err_an, rep.th_err_bg)
    # σ=0 필드는 배경 고정 (CVT 제어 제외)
    assert rep.qv_err_an == pytest.approx(rep.qv_err_bg, rel=1e-12)


@needs_all
def test_flip_direction_physical_asymmetry(tmp_path):
    """Codex 검토 보강: zero-innovation 자기일관성은 진실·배경 양쪽에 대칭으로
    들어간 flip/단위 오류를 못 잡는다. 물리 비대칭으로 방향을 고정: WRF k=0
    (지표면) th 섭동은 IR 창채널 BT를 크게 움직이고, k=K-1(모델 상단) 섭동은
    거의 못 움직여야 한다. flip이 뒤집혀 있으면 이 비대칭이 역전된다."""
    from kdm6.da_driver import batched_clear_bt

    frame = read_wrfout_frame(str(_WRFOUT), time_idx=1)
    idx = torch.linspace(0, frame.state.th.shape[0] - 1, 2).long()
    x, f = _sub(frame, idx)
    cfg = _obs_cfg(tmp_path)

    with torch.no_grad():
        bt0, _, _ = batched_clear_bt(x, f, cfg)
        x_sfc = x._replace(th=torch.cat([x.th[:, :1] + 2.0, x.th[:, 1:]], dim=1))
        bt_sfc, _, _ = batched_clear_bt(x_sfc, f, cfg)
        x_top = x._replace(th=torch.cat([x.th[:, :-1], x.th[:, -1:] + 2.0], dim=1))
        bt_top, _, _ = batched_clear_bt(x_top, f, cfg)

    d_sfc = float((torch.as_tensor(bt_sfc) - torch.as_tensor(bt0)).abs().max())
    d_top = float((torch.as_tensor(bt_top) - torch.as_tensor(bt0)).abs().max())
    assert d_sfc > 5.0 * max(d_top, 1.0e-6), (
        f"surface-vs-top BT asymmetry wrong: |dBT_sfc|={d_sfc:.4f} vs "
        f"|dBT_top|={d_top:.4f} — WRF<->RTTOV flip direction suspect")
