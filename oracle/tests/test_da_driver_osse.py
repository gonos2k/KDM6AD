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
