"""실관측 인제스트 코어 검증 (obs_ingest — 스키마·collocation·컬럼 정렬).

전부 합성 그리드 기반 (이상화 SS 케이스는 XLAT/XLONG=0이라 실그리드 검증 불가 —
그 퇴화 케이스 자체를 거부 게이트로 검증한다).
"""
from __future__ import annotations

import math

import pytest
import torch

from kdm6.obs.obs_ingest import (
    ColumnObs, ObsPayload, collocate, haversine_km, payload_to_column_obs)

_F64 = dict(dtype=torch.float64)


def _grid(nlat=5, nlon=5, lat0=35.0, lon0=125.0, dstep=0.5):
    """합성 정규 격자 → flat (B,) 좌표 (b = j*nlon + i 관례)."""
    lats = lat0 + dstep * torch.arange(nlat, **_F64)
    lons = lon0 + dstep * torch.arange(nlon, **_F64)
    glat = lats[:, None].expand(nlat, nlon).reshape(-1)
    glon = lons[None, :].expand(nlat, nlon).reshape(-1)
    return glat, glon


def _payload(lat, lon, nch=4, quality=None):
    n = len(lat)
    bt = 250.0 + torch.arange(n, **_F64)[:, None].expand(n, nch).clone()
    q = torch.zeros((n, nch), **_F64) if quality is None else quality
    return ObsPayload(bt=bt, obs_quality=q,
                      lat=torch.tensor(lat, **_F64), lon=torch.tensor(lon, **_F64))


# ─── 스키마 ──────────────────────────────────────────────────────────────────


def test_payload_schema_rejects_bad_shapes_and_values():
    with pytest.raises(ValueError, match="obs_quality shape"):
        ObsPayload(bt=torch.zeros((2, 4), **_F64), obs_quality=torch.zeros((2, 3), **_F64),
                   lat=torch.zeros(2, **_F64), lon=torch.zeros(2, **_F64))
    with pytest.raises(ValueError, match="lat shape"):
        ObsPayload(bt=torch.zeros((2, 4), **_F64), obs_quality=torch.zeros((2, 4), **_F64),
                   lat=torch.zeros(3, **_F64), lon=torch.zeros(2, **_F64))
    with pytest.raises(ValueError, match="non-finite"):
        bad = torch.zeros((1, 4), **_F64); bad[0, 0] = float("nan")
        ObsPayload(bt=bad, obs_quality=torch.zeros((1, 4), **_F64),
                   lat=torch.zeros(1, **_F64), lon=torch.zeros(1, **_F64))
    with pytest.raises(ValueError, match="out of range"):
        ObsPayload(bt=torch.zeros((1, 4), **_F64), obs_quality=torch.zeros((1, 4), **_F64),
                   lat=torch.tensor([95.0], **_F64), lon=torch.zeros(1, **_F64))


# ─── haversine / collocation ────────────────────────────────────────────────


def test_haversine_known_value():
    """적도 경도 1° ≈ 111.19 km."""
    d = haversine_km(torch.tensor(0.0, **_F64), torch.tensor(0.0, **_F64),
                     torch.tensor(0.0, **_F64), torch.tensor(1.0, **_F64))
    assert abs(float(d) - 111.195) < 0.05


def test_collocate_exact_hit_and_nearest():
    glat, glon = _grid()
    # 정확 일치: 격자점 (2,3) = b = 2*5+3 = 13
    idx, dist = collocate(torch.tensor([36.0], **_F64), torch.tensor([126.5], **_F64),
                          glat, glon)
    assert int(idx[0]) == 13 and float(dist[0]) < 1e-6
    # 근접점: (35.1, 125.1) → 최근접은 (35.0, 125.0) = b=0
    idx, dist = collocate(torch.tensor([35.1], **_F64), torch.tensor([125.1], **_F64),
                          glat, glon)
    assert int(idx[0]) == 0
    assert 0.0 < float(dist[0]) < 20.0


def test_collocate_rejects_degenerate_grid():
    """이상화 케이스(XLAT/XLONG 전부 0)의 정확한 꼴 — loud 거부."""
    z = torch.zeros(10, **_F64)
    with pytest.raises(ValueError, match="degenerate grid"):
        collocate(torch.tensor([35.0], **_F64), torch.tensor([125.0], **_F64), z, z)


# ─── payload → 컬럼 정렬 ─────────────────────────────────────────────────────


def test_column_obs_assignment_and_unobserved_flagging():
    glat, glon = _grid()
    pl = _payload(lat=[36.0, 35.0], lon=[126.5, 125.0])      # b=13, b=0
    co = payload_to_column_obs(pl, glat, glon, max_dist_km=10.0)
    assert isinstance(co, ColumnObs)
    assert co.n_assigned == 2 and co.n_dropped_far == 0
    assert co.col_of_obs.tolist() == [13, 0]
    assert torch.equal(co.bt[13], pl.bt[0]) and torch.equal(co.bt[0], pl.bt[1])
    # 배정 컬럼은 payload quality(0=사용가능), 미배정 컬럼은 1(unusable)
    assert float(co.obs_quality[13].max()) == 0.0
    assert float(co.obs_quality[0].max()) == 0.0
    others = [b for b in range(25) if b not in (0, 13)]
    assert all(float(co.obs_quality[b].min()) == 1.0 for b in others)


def test_column_obs_far_gate_and_collision():
    glat, glon = _grid()
    # obs0: 격자점 b=0 정확 / obs1: b=0에서 ~7km / obs2: 도메인 밖 (far)
    pl = _payload(lat=[35.0, 35.06, 20.0], lon=[125.0, 125.0, 100.0])
    co = payload_to_column_obs(pl, glat, glon, max_dist_km=15.0)
    assert co.n_dropped_far == 1
    assert co.n_dropped_collision == 1                       # obs1이 obs0에 패배
    assert co.col_of_obs.tolist()[0] == 0
    assert co.col_of_obs.tolist()[1] == -1
    assert co.col_of_obs.tolist()[2] == -1
    assert torch.equal(co.bt[0], pl.bt[0])                   # 최근접(obs0)이 승자


def test_column_obs_feeds_both_sides_qc_mask():
    """통합 규약: 미배정 컬럼 quality=1이 기존 _build_mask에서 자동 배제된다."""
    from kdm6.obs.rttov_obs_operator import _build_mask
    glat, glon = _grid(nlat=2, nlon=2)
    pl = _payload(lat=[35.0], lon=[125.0], nch=4)            # b=0만 관측
    co = payload_to_column_obs(pl, glat, glon, max_dist_km=10.0)
    rad_quality = torch.zeros((4, 4), **_F64)                # 모델측 전 채널 깨끗
    mask = _build_mask({"bt": co.bt, "obs_quality": co.obs_quality}, rad_quality)
    assert float(mask[0].sum()) == 4.0                       # 관측 컬럼만 살아있음
    assert float(mask[1:].sum()) == 0.0
