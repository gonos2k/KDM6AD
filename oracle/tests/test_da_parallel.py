"""프로세스-샤딩 병렬 드라이버 검증 (da_parallel).

핵심 게이트: 병렬(N spawn worker) 결과가 순차 in-process 참조와 **torch.equal**
(비트단위) — 컬럼 독립성 + 스레드-1 고정 하에서 프로세스 경계는 수치에 어떤
영향도 없어야 한다. wrfout + live RTTOV 필요 (없으면 skip).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch

from kdm6.da_parallel import build_shard_specs, run_sharded_sensitivity
from kdm6.io import read_wrfout_frame
from kdm6.state import Forcing, State

from tests.test_rttov_case_writer import (
    _CHANNELS, _HAVE_EXE, _fixture_p_half, _fixture_tq)

_REPO = Path(__file__).resolve().parents[2]
_WRFOUT = _REPO / "host" / "KIM-meso_v1.0" / "run" / "wrfout.37.quarter_ss.nc"
needs_all = pytest.mark.skipif(
    not (_WRFOUT.exists() and _HAVE_EXE),
    reason="needs local SS wrfout + live RTTOV (AD-RTTOV)")
_F64 = dict(dtype=torch.float64)


@needs_all
def test_parallel_equals_sequential_bitwise(tmp_path):
    from kdm6.obs.rttov_case_writer import fixture_layer_pressure

    frame = read_wrfout_frame(str(_WRFOUT), time_idx=1)
    idx = torch.linspace(0, frame.state.th.shape[0] - 1, 8).long()
    x_true = State(**{k: v[idx] for k, v in frame.state._asdict().items()})
    f = Forcing(**{k: v[idx] for k, v in frame.forcing._asdict().items()})
    th_b = x_true.th.clone(); th_b[:, :10] += 0.5
    x_bg = x_true._replace(th=th_b)

    tr, qr = _fixture_tq()
    common = dict(
        n_steps=2, dt=300.0, obs_times=[2],
        profile_kwargs=dict(
            gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
            rttov_layer_pressure=torch.as_tensor(
                np.asarray(fixture_layer_pressure(), dtype=float), **_F64),
            rttov_level_pressure=torch.as_tensor(
                np.asarray(_fixture_p_half(), dtype=float), **_F64)),
        input_kwargs=dict(coef_id="ami_501_test", channels=_CHANNELS),
        obs_sigma=1.0,
        t_ref=torch.as_tensor(np.asarray(tr, dtype=float), **_F64),
        q_ref=torch.as_tensor(np.asarray(qr, dtype=float), **_F64))
    shard_idx = [torch.arange(0, 4), torch.arange(4, 8)]

    specs_p = build_shard_specs(x_true, x_bg, f, shard_idx,
                                case_root=str(tmp_path / "par"), **common)
    specs_s = build_shard_specs(x_true, x_bg, f, shard_idx,
                                case_root=str(tmp_path / "seq"), **common)

    out_p = run_sharded_sensitivity(specs_p, n_workers=2, parallel=True)
    out_s = run_sharded_sensitivity(specs_s, n_workers=1, parallel=False)

    assert out_p["n_shards"] == out_s["n_shards"] == 2
    assert out_p["j_obs"] == out_s["j_obs"]               # float 합도 동일해야
    for k in State._fields:
        a, b = getattr(out_p["adj_x0"], k), getattr(out_s["adj_x0"], k)
        assert torch.equal(a, b), f"parallel != sequential on {k}"
    # 민감도 실재 (관측 필드)
    assert float(out_p["adj_x0"].th.abs().sum()) > 0.0


@needs_all
def test_partition_guards_reject_overlap_and_gap(tmp_path):
    """재조립 가드: 중복/누락 분할은 loud하게 거부."""
    from kdm6.obs.rttov_case_writer import fixture_layer_pressure

    frame = read_wrfout_frame(str(_WRFOUT), time_idx=1)
    idx = torch.linspace(0, frame.state.th.shape[0] - 1, 4).long()
    x = State(**{k: v[idx] for k, v in frame.state._asdict().items()})
    f = Forcing(**{k: v[idx] for k, v in frame.forcing._asdict().items()})
    tr, qr = _fixture_tq()
    common = dict(
        n_steps=1, dt=300.0, obs_times=[1],
        profile_kwargs=dict(
            gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
            rttov_layer_pressure=torch.as_tensor(
                np.asarray(fixture_layer_pressure(), dtype=float), **_F64),
            rttov_level_pressure=torch.as_tensor(
                np.asarray(_fixture_p_half(), dtype=float), **_F64)),
        input_kwargs=dict(coef_id="ami_501_test", channels=_CHANNELS),
        obs_sigma=1.0,
        t_ref=torch.as_tensor(np.asarray(tr, dtype=float), **_F64),
        q_ref=torch.as_tensor(np.asarray(qr, dtype=float), **_F64))

    # 중복 분할
    specs = build_shard_specs(x, x, f, [torch.arange(0, 3), torch.arange(2, 4)],
                              case_root=str(tmp_path / "ov"), **common)
    with pytest.raises(RuntimeError, match="overlap"):
        run_sharded_sensitivity(specs, n_workers=1, parallel=False)
    # 누락 분할
    specs = build_shard_specs(x, x, f, [torch.arange(0, 2), torch.arange(3, 4)],
                              case_root=str(tmp_path / "gap"), **common)
    with pytest.raises(RuntimeError, match="union"):
        run_sharded_sensitivity(specs, n_workers=1, parallel=False)
