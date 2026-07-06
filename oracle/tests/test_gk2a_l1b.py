"""GK2A KO L1B → ObsPayload 어댑터 검증 (계획 §6 파이프라인 ①).

두 층위:
  1. 순수 함수 (어디서나): LCC 역변환의 원점 불변식·pyproj 교차검증(있을 때),
     DN→BT 손계산 대조, 파일명/타임스탬프 가드.
  2. 실데이터 (GK2A/ 디렉토리 + 검정 테이블 존재 시): 실슬롯 payload의 물리성
     (BT 범위·solar 채널 마스킹) — 지오로케이션·검정·스키마의 통합 게이트.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
import torch

from kdm6.obs.gk2a_l1b import (
    AMI_CHANNELS, EARTH_RADIUS_M, IR_CHANNELS, dn_to_bt, ko_grid_latlon,
    load_cal_table, read_ko_slot, slot_files)

_REPO = Path(__file__).resolve().parents[2]
_GK2A = _REPO / "GK2A"
_CAL = _REPO / "oracle" / "kdm6" / "obs" / "data" / "gk2a_ami_cal_202507190000.json"
needs_data = pytest.mark.skipif(
    not (_GK2A.is_dir() and _CAL.exists()),
    reason="GK2A/ KO data or cal table absent")

_KO_ATTRS = dict(standard_parallel1=30.0, standard_parallel2=60.0,
                 origin_latitude=38.0, central_meridian=126.0,
                 pixel_size=2000.0, upper_left_easting=-899000.0,
                 upper_left_northing=899000.0, image_width=900, image_height=900)


# ─── 1. 순수 함수 ────────────────────────────────────────────────────────────


def test_lcc_origin_invariant():
    """easting=northing=0 → 정확히 (38, 126) — 반경 무관 불변식.

    (4-픽셀 평균은 위도의 y-곡률 2차항 ~6e-6°가 남으므로 부적합 — 원점을
    픽셀 중심에 정확히 놓은 1×1 합성 격자로 직접 평가한다.)"""
    attrs = dict(_KO_ATTRS, image_width=1, image_height=1,
                 upper_left_easting=0.0, upper_left_northing=0.0)
    lat, lon = ko_grid_latlon(attrs)
    assert abs(float(lat[0, 0]) - 38.0) < 1e-12
    assert abs(float(lon[0, 0]) - 126.0) < 1e-12


def test_lcc_matches_pyproj_if_available():
    """독립 구현(pyproj) 전 격자 교차검증 — 실측 |Δ|max ~ 6e-14°."""
    pyproj = pytest.importorskip("pyproj")
    lat, lon = ko_grid_latlon(_KO_ATTRS)
    crs = pyproj.CRS.from_proj4(
        f"+proj=lcc +lat_1=30 +lat_2=60 +lat_0=38 +lon_0=126 "
        f"+R={EARTH_RADIUS_M} +x_0=0 +y_0=0 +units=m +no_defs")
    tr = pyproj.Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    x = _KO_ATTRS["upper_left_easting"] + 2000.0 * np.arange(900)
    y = _KO_ATTRS["upper_left_northing"] - 2000.0 * np.arange(900)
    X, Y = np.meshgrid(x, y)
    lon_p, lat_p = tr.transform(X, Y)
    assert np.abs(lat - lat_p).max() < 1e-9
    assert np.abs(lon - lon_p).max() < 1e-9


def test_dn_to_bt_hand_computed():
    """단일 픽셀 손계산 대조 (ir105 실계수) + quality 비트 추출."""
    cal = dict(DN_to_Radiance_Gain=-0.0198196955025196,
               DN_to_Radiance_Offset=161.580139160156,
               Teff_to_Tbb_c0=-0.142866448475177,
               Teff_to_Tbb_c1=1.00064069572049,
               Teff_to_Tbb_c2=-5.50443294960498e-07,
               Plank_constant_h=6.62606957e-34, light_speed=299792458.0,
               Boltzmann_constant_k=1.3806488e-23,
               channel_center_wavelength="10.5")
    dn = 3000
    raw = np.array([[dn | (0b01 << 13)]], dtype=np.uint16)   # quality=1 플래그 실험
    bt, q = dn_to_bt(raw, cal)
    assert q[0, 0] == 1.0
    # 손계산 (같은 수식)
    rad = cal["DN_to_Radiance_Offset"] + cal["DN_to_Radiance_Gain"] * dn
    sig = (10000.0 / 10.5) * 100.0
    h, c, k = cal["Plank_constant_h"], cal["light_speed"], cal["Boltzmann_constant_k"]
    teff = h * c * sig / k / math.log((2 * h * c * c * sig ** 3) / (rad * 1e-3 / 100.0) + 1)
    tbb = cal["Teff_to_Tbb_c0"] + cal["Teff_to_Tbb_c1"] * teff + cal["Teff_to_Tbb_c2"] * teff ** 2
    assert abs(float(bt[0, 0]) - tbb) < 1e-9
    assert 180.0 < tbb < 320.0                                # 물리 범위


def test_read_ko_slot_rejects_mixed_timestamps(tmp_path):
    a = tmp_path / "gk2a_ami_le1b_ir105_ko020lc_202507190000.nc"
    b = tmp_path / "gk2a_ami_le1b_ir112_ko020lc_202507190002.nc"
    a.touch(); b.touch()
    with pytest.raises(ValueError, match="mixed timestamps"):
        read_ko_slot([a, b], {"channels": {}})


# ─── 2. 실데이터 통합 (GK2A/ + 검정 테이블 게이트) ──────────────────────────


@needs_data
def test_real_slot_payload_physical():
    cal = load_cal_table(_CAL)
    files = slot_files(_GK2A, "202507190000")
    assert len(files) == len(IR_CHANNELS)
    pl = read_ko_slot(files, cal, stride=16)                 # 32km 솎음(테스트 경량)
    assert pl.nch == 16
    j = AMI_CHANNELS.index("ir105")
    ok = pl.obs_quality[:, j] == 0
    bt = pl.bt[ok, j]
    assert float(ok.float().mean()) > 0.95                   # KO 내부는 대부분 정상
    assert 180.0 < float(bt.min()) and float(bt.max()) < 320.0
    assert 250.0 < float(bt.mean()) < 300.0                  # 7월 한반도 IR105
    # solar 6채널은 미제공 → 전부 unusable
    assert bool((pl.obs_quality[:, :6] == 1).all())
    # 위경도가 KO 도메인 내
    assert 28.0 < float(pl.lat.min()) and float(pl.lat.max()) < 47.5
    assert 113.0 < float(pl.lon.min()) and float(pl.lon.max()) < 139.0
