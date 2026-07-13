"""superob 전처리 검증 — GK2A → 모델격자 사상의 순수/실데이터 게이트."""
from __future__ import annotations

from pathlib import Path

import pytest
import torch

from kdm6.obs.obs_ingest import ObsPayload
from kdm6.obs.superob import superob_to_model_grid

_F64 = dict(dtype=torch.float64)
_REPO = Path(__file__).resolve().parents[2]
_GK2A = _REPO / "GK2A"
_CAL = _REPO / "oracle" / "kdm6" / "obs" / "data" / "gk2a_ami_cal_202507190000.json"
_WRFIN = Path("/Users/yhlee/KDM6AD+/KIM-meso_v1.0/test/"
              "ss_real_case_20260619_063620/SS/wrfinput_d01")
needs_real = pytest.mark.skipif(
    not (_GK2A.is_dir() and _CAL.exists() and _WRFIN.exists()),
    reason="GK2A / cal / LC05 wrfinput 부재")


def _payload(lat, lon, bt_vals, quality=None, nch=2):
    n = len(lat)
    bt = torch.zeros((n, nch), **_F64)
    bt[:, 0] = torch.tensor(bt_vals, **_F64)
    bt[:, 1] = torch.tensor(bt_vals, **_F64) + 1.0
    q = torch.zeros((n, nch), **_F64) if quality is None else quality
    return ObsPayload(bt=bt, obs_quality=q,
                      lat=torch.tensor(lat, **_F64), lon=torch.tensor(lon, **_F64))


def test_superob_cell_mean_and_min_pixels():
    """셀 평균이 정확하고, min_pixels 미달 셀은 quality=1."""
    glat = torch.tensor([35.0, 36.0], **_F64)
    glon = torch.tensor([125.0, 125.0], **_F64)
    # 셀0 주변 3화소 (250/252/254 → 평균 252), 셀1 주변 1화소 (min_pixels 미달)
    pl = _payload(lat=[35.001, 35.002, 34.999, 36.001],
                  lon=[125.0, 125.001, 124.999, 125.0],
                  bt_vals=[250.0, 252.0, 254.0, 260.0])
    so = superob_to_model_grid(pl, glat, glon, max_dist_km=4.0, min_pixels=3)
    assert float(so.bt[0, 0]) == pytest.approx(252.0)
    assert float(so.obs_quality[0, 0]) == 0.0
    assert float(so.obs_quality[1, 0]) == 1.0          # 화소 1개 → 미충족
    assert float(so.n_pixels[0, 0]) == 3.0
    assert so.n_dropped_far == 0


def test_superob_quality_pixels_excluded_and_far_gate():
    """플래그 화소는 평균에서 배제; max_dist 밖 화소는 far-drop 집계."""
    glat = torch.tensor([35.0, 36.0], **_F64)
    glon = torch.tensor([125.0, 125.0], **_F64)
    q = torch.zeros((5, 2), **_F64); q[1, 0] = 1.0     # 화소1의 ch0만 플래그
    pl = _payload(lat=[35.001, 35.002, 34.999, 35.0, 20.0],
                  lon=[125.0, 125.001, 124.999, 125.002, 100.0],
                  bt_vals=[250.0, 999.0, 254.0, 252.0, 300.0], quality=q)
    so = superob_to_model_grid(pl, glat, glon, max_dist_km=4.0, min_pixels=3)
    assert float(so.bt[0, 0]) == pytest.approx(252.0)  # 999 배제 (250+254+252)/3
    # ch1은 화소1도 quality-0 → 4화소 평균 (251+1000+255+253)/4
    assert float(so.bt[0, 1]) == pytest.approx((251.0 + 1000.0 + 255.0 + 253.0) / 4)
    assert so.n_dropped_far == 1


@needs_real
def test_superob_full_model_domain_real():
    """실데이터: GK2A 00 UTC 전화소 → LC05 전 도메인 superob — 커버리지·물리성."""
    from kdm6.io.frame_reader import read_wrfout_frame
    from kdm6.obs.gk2a_l1b import CLEAN_IR_CHANNELS, load_cal_table, read_ko_slot, slot_files
    fr = read_wrfout_frame(str(_WRFIN), 0)
    cal = load_cal_table(_CAL)
    pl = read_ko_slot(slot_files(_GK2A, "202507190000", channels=CLEAN_IR_CHANNELS),
                      cal, stride=2)                    # 4km 화소 (테스트 경량)
    # 4km 솎음 밀도에선 5km 셀당 화소 1-2개 — min_pixels=1로 낮춘다
    # (운영 전처리는 stride=1(2km)로 셀당 ~6화소 → 기본 min_pixels=3 사용).
    so = superob_to_model_grid(pl, fr.meta["lat"], fr.meta["lon"],
                               max_dist_km=4.0, min_pixels=1)
    B = fr.state.th.shape[0]
    cov = float((so.obs_quality[:, 12] == 0).float().mean())
    assert cov > 0.3                                    # KO 커버 영역 (~39%)
    ok = so.obs_quality[:, 12] == 0
    assert 180.0 < float(so.bt[ok, 12].min()) and float(so.bt[ok, 12].max()) < 320.0
    # superob 평활 효과: 셀 평균이므로 원화소보다 극값이 안쪽
    assert float(so.bt[ok, 12].min()) >= float(pl.bt[:, 12].min()) - 1e-9


# ── input-validation contract (external review P1-3) ────────────────────────

def test_superob_min_pixels_must_be_positive():
    """min_pixels < 1 makes `good = n >= 0` include EMPTY cells -> 0/0 mean
    and a spuriously usable quality flag; reject at the boundary."""
    glat = torch.tensor([35.0, 36.0], **_F64)
    glon = torch.tensor([125.0, 125.0], **_F64)
    pl = _payload(lat=[35.001], lon=[125.0], bt_vals=[250.0])
    for bad in (0, -1):
        with pytest.raises(ValueError, match="min_pixels"):
            superob_to_model_grid(pl, glat, glon, max_dist_km=4.0,
                                  min_pixels=bad)


def test_superob_max_dist_must_be_finite_positive():
    glat = torch.tensor([35.0], **_F64)
    glon = torch.tensor([125.0], **_F64)
    pl = _payload(lat=[35.001], lon=[125.0], bt_vals=[250.0])
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="max_dist_km"):
            superob_to_model_grid(pl, glat, glon, max_dist_km=bad,
                                  min_pixels=1)


def test_superob_with_mapping_validates_B_and_mapping_range():
    from kdm6.obs.superob import superob_with_mapping
    pl = _payload(lat=[35.0, 36.0], lon=[125.0, 125.0], bt_vals=[250.0, 251.0])
    good = torch.tensor([0, 1], dtype=torch.int64)
    with pytest.raises(ValueError, match="B"):
        superob_with_mapping(pl, good, 0, min_pixels=1)
    with pytest.raises(ValueError, match="min_pixels"):
        superob_with_mapping(pl, good, 2, min_pixels=0)
    bad_hi = torch.tensor([0, 2], dtype=torch.int64)   # >= B: out of range
    with pytest.raises(ValueError, match="mapping"):
        superob_with_mapping(pl, bad_hi, 2, min_pixels=1)
    bad_lo = torch.tensor([0, -2], dtype=torch.int64)  # < -1: out of range
    with pytest.raises(ValueError, match="mapping"):
        superob_with_mapping(pl, bad_lo, 2, min_pixels=1)
