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
needs_fcst = pytest.mark.skipif(
    not __import__("pathlib").Path(
        "/Users/yhlee/KDM6AD-k/host/lc05_da_run/klfs_lc05_fcst.202507190000").exists(),
    reason="LC05 3h fcst 부재")
needs_all = pytest.mark.skipif(
    not (_WRFOUT.exists() and _HAVE_EXE),
    reason="needs local SS wrfout + live RTTOV (AD-RTTOV)")
_F64 = dict(dtype=torch.float64)


def _small_shard_inputs():
    B, K = 3, 2
    def field(offset):
        return torch.arange(B * K, dtype=torch.float64).reshape(B, K) + offset
    x = State(*(field(i + 1.0) for i, _ in enumerate(State._fields)))
    f = Forcing(*(field(i + 20.0) for i, _ in enumerate(Forcing._fields)))
    return x, x.clone() if hasattr(x, "clone") else State(*[v.clone() for v in x]), f


def test_build_shard_specs_slices_frozen_rho_d_in_requested_order(tmp_path):
    x, _, f = _small_shard_inputs()
    rho_d = torch.tensor([[1.0, 10.0], [2.0, 20.0], [3.0, 30.0]], **_F64)
    layer = torch.tensor([700.0, 900.0], **_F64)
    profile = {"rho_d": rho_d, "rttov_layer_pressure": layer, "cloud": True,
               "marker": "preserve"}
    specs = build_shard_specs(
        x, x, f, [torch.tensor([2, 0])], n_steps=1, dt=300.0, obs_times=[1],
        case_root=str(tmp_path), profile_kwargs=profile,
        input_kwargs={"channels": (1, 2)})
    got = specs[0].profile_kwargs
    assert torch.equal(specs[0].col_idx, torch.tensor([2, 0]))
    assert torch.equal(got["rho_d"], rho_d[[2, 0]])
    assert got["marker"] == "preserve" and got["cloud"] is True
    assert torch.equal(got["rttov_layer_pressure"], layer)
    assert got["rho_d"].data_ptr() != rho_d.data_ptr()
    assert got["rttov_layer_pressure"].data_ptr() != layer.data_ptr()


@pytest.mark.parametrize("profile_update, message", [
    ({"rho_d": torch.ones((3, 1), **_F64)}, "full shape"),
    ({"rho_d": torch.tensor([[1.0, float("nan")], [2.0, 2.0], [3.0, 3.0]], **_F64)},
     "finite"),
])
def test_build_shard_specs_rejects_malformed_frozen_density(tmp_path, profile_update, message):
    x, _, f = _small_shard_inputs()
    with pytest.raises(ValueError, match=message):
        build_shard_specs(
            x, x, f, [torch.tensor([0, 2])], n_steps=1, dt=300.0, obs_times=[1],
            case_root=str(tmp_path), profile_kwargs=profile_update,
            input_kwargs={"channels": (1, 2)})


@pytest.mark.parametrize("indices, message", [
    (torch.tensor([[0, 1]]), "1-D"),
    (torch.tensor([0.0, 1.0]), "integer"),
    (torch.tensor([0, 3]), "outside"),
    (torch.tensor([1, 1]), "duplicates"),
])
def test_build_shard_specs_rejects_malformed_indices(tmp_path, indices, message):
    x, _, f = _small_shard_inputs()
    with pytest.raises(ValueError, match=message):
        build_shard_specs(
            x, x, f, [indices], n_steps=1, dt=300.0, obs_times=[1],
            case_root=str(tmp_path), profile_kwargs={},
            input_kwargs={"channels": (1, 2)})


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


@needs_all
def test_partition_guard_rejects_trailing_gap(tmp_path):
    """Codex stop-review 회귀 가드: 누락이 꼬리쪽(마지막 컬럼들)이어도 union
    가드가 발화해야 한다 — max+1 유도였다면 침묵 통과했을 케이스."""
    from kdm6.obs.rttov_case_writer import fixture_layer_pressure

    frame = read_wrfout_frame(str(_WRFOUT), time_idx=1)
    idx = torch.linspace(0, frame.state.th.shape[0] - 1, 4).long()
    x = State(**{k: v[idx] for k, v in frame.state._asdict().items()})
    f = Forcing(**{k: v[idx] for k, v in frame.forcing._asdict().items()})
    tr, qr = _fixture_tq()
    specs = build_shard_specs(
        x, x, f, [torch.arange(0, 3)],                    # 컬럼 3 (꼬리) 누락
        n_steps=1, dt=300.0, obs_times=[1],
        case_root=str(tmp_path / "tg"),
        profile_kwargs=dict(
            gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
            rttov_layer_pressure=torch.as_tensor(
                np.asarray(fixture_layer_pressure(), dtype=float), **_F64),
            rttov_level_pressure=torch.as_tensor(
                np.asarray(_fixture_p_half(), dtype=float), **_F64)),
        input_kwargs=dict(coef_id="ami_501_test", channels=_CHANNELS),
        t_ref=torch.as_tensor(np.asarray(tr, dtype=float), **_F64),
        q_ref=torch.as_tensor(np.asarray(qr, dtype=float), **_F64))
    assert specs[0].b_total == 4
    with pytest.raises(RuntimeError, match="union"):
        run_sharded_sensitivity(specs, n_workers=1, parallel=False)


def _synthetic_cloudy_window_inputs():
    """Small, valid cloudy columns for the value-only sharding regression."""
    B, K = 4, 2

    def full(value):
        return torch.full((B, K), value, dtype=torch.float64)

    state = State(
        th=full(290.0), qv=full(1.4e-2), qc=full(1.0e-3), qr=full(1.0e-5),
        qi=full(0.0), qs=full(0.0), qg=full(0.0), nccn=full(1.0e9),
        # This is above the maritime safety floor but below the land floor.
        nc=full(50.0), ni=full(0.0), nr=full(1.0e4), bg=full(0.0))
    forcing = Forcing(rho=full(1.0), pii=full(0.97), p=full(9.0e4),
                      delz=full(500.0))
    xland = torch.tensor([1.0, 2.0, 1.0, 2.0], dtype=torch.float64)
    return state, [forcing] * 12, xland


def test_sharded_forward_window_synthetic_cloudy_columns_bitwise():
    """Portable 12-step value window: two workers equal serial, including controls."""
    from kdm6.da_parallel import sharded_forward_window
    from kdm6.runtime import kdm6_step

    state, forcings, xland = _synthetic_cloudy_window_inputs()

    def serial(**controls):
        x = state
        for forcing in forcings:
            x, handle = kdm6_step(x, forcing, None, 300.0, value_only=True,
                                   **controls)
            handle.close()
        return x

    plain = serial()
    plain_sharded = sharded_forward_window(
        state, forcings, 300.0, n_workers=2)
    for name in State._fields:
        assert torch.equal(getattr(plain, name), getattr(plain_sharded, name)), \
            f"plain sharded != serial on {name}"

    controls = dict(xland=xland, ncmin_land=100.0, ncmin_sea=10.0)
    controlled = serial(**controls)
    controlled_sharded = sharded_forward_window(
        state, forcings, 300.0, n_workers=2, **controls)
    for name in State._fields:
        assert torch.equal(getattr(controlled, name),
                           getattr(controlled_sharded, name)), \
            f"controlled sharded != serial on {name}"

    # nc=50 is below the land floor and above the sea floor, so this route must
    # change the result rather than merely carry unused control arguments.
    assert not torch.equal(plain.nc, controlled.nc)


@needs_fcst
def test_sharded_forward_window_bitwise():
    """값-전용 창 전방의 컬럼 샤딩 ≡ 단일 프로세스 (bitwise) — 프로브/영상 병렬화
    게이트. (stdin-spawn 함정 회피를 위해 pytest 파일 기반으로 고정.)"""
    import torch
    from kdm6.da_parallel import sharded_forward_window
    from kdm6.io.frame_reader import read_wrfout_frame
    from kdm6.runtime import kdm6_step
    from kdm6.state import Forcing, State

    FCST = "/Users/yhlee/KDM6AD-k/host/lc05_da_run/klfs_lc05_fcst.202507190000"
    required_frames = 12
    import netCDF4
    ds = netCDF4.Dataset(FCST)
    try:
        actual_frames = int(ds.dimensions["Time"].size)
    finally:
        ds.close()
    if actual_frames < required_frames:
        pytest.skip(
            f"private forecast has {actual_frames} Time frames; "
            f"required {required_frames}")
    fr = read_wrfout_frame(FCST, 0)
    sel = torch.arange(30000, 30128)
    x0 = State(*(f[sel] for f in fr.state))
    fcs = []
    for t in range(required_frames):
        frt = read_wrfout_frame(FCST, t)
        fcs.append(Forcing(*(f[sel] for f in frt.forcing)))
    x = x0
    for t in range(required_frames):
        x, h = kdm6_step(x, fcs[t], None, 300.0, value_only=True)
        h.close()
    ref = torch.stack(list(x))
    xs = sharded_forward_window(x0, fcs, 300.0, n_workers=2)
    assert torch.equal(ref, torch.stack(list(xs)))
    # xland/ncmin 경로 (Codex stop-review: 행동-변경 입력 관통 게이트)
    xland = fr.xland[sel]
    x2 = x0
    for t in range(required_frames):
        x2, h = kdm6_step(x2, fcs[t], None, 300.0, value_only=True,
                          xland=xland, ncmin_land=10.0, ncmin_sea=5.0)
        h.close()
    ref2 = torch.stack(list(x2))
    xs2 = sharded_forward_window(x0, fcs, 300.0, xland=xland,
                                 ncmin_land=10.0, ncmin_sea=5.0, n_workers=2)
    assert torch.equal(ref2, torch.stack(list(xs2)))
    assert not torch.equal(ref, ref2)      # xland 경로가 실제로 행동을 바꿈을 확인
