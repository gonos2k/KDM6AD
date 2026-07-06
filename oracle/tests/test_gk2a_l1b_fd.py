"""GK2A FD(전구) 어댑터 검증 — geos 지오로케이션 + 교차-투영 BT 게이트.

geos 역변환에서 발견·수정한 **업스트림(AD-RTTOV) 잠복 버그 2종**을 회귀 고정:
  ① cfac/lfac 단위: GK2A는 counts-per-DEGREE (CGMS 원형은 라디안 기준) —
     deg→rad 누락 시 부위성점(x=y=0)에서만 정확 (스케일 ~57× 축소).
  ② s3 부호: GK2A lfac<0(북쪽 라인 y>0) 규약에서 CGMS 원형의 -sn·siny는
     반구 반전 — 적도에선 lat=0이라 역시 중심-픽셀 테스트에 무증상.
  둘 다 "검증점이 대칭점 위"라 잠복했던 사례 — 여기의 비대칭(북반구) 프로브가
  회귀 가드다.

교차-투영 게이트 (FD+KO 실데이터 존재 시): 같은 스캔(202507190100)의 KO(LCC)
vs FD(geos) BT — wv063(매끄러운 장) 중앙값 <0.5K (실측 0.114K)이면 두 독립
지오로케이션·검정 경로가 부픽셀 수준으로 상호 증명된다.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch

from kdm6.obs.gk2a_l1b_fd import (find_domain_window, geos_latlon,
                                  fd_slot_files, read_fd_slot)

_REPO = Path(__file__).resolve().parents[2]
_FD01 = Path("/Users/yhlee/KDM6AD+/observations/gk2a/202507190100_fd")
_GK2A = _REPO / "GK2A"
_CAL = _REPO / "oracle" / "kdm6" / "obs" / "data" / "gk2a_ami_cal_202507190000.json"
needs_fd = pytest.mark.skipif(
    not (_FD01.is_dir() and _GK2A.is_dir() and _CAL.exists()),
    reason="FD 01:00 originals / GK2A KO / cal table 부재")

# GK2A AMI FD 2km 실속성 (202507190100 ir105 파일에서 채록)
_G = dict(coff=2750.5, loff=2750.5, cfac=20425338.903339352,
          lfac=-20425338.903339352, sub_longitude=2.2375121010567303,
          nominal_satellite_height=42164000.0,
          earth_equatorial_radius=6378137.0, earth_polar_radius=6356752.3)


def test_geos_center_and_hemisphere():
    """중심 = 부위성점 (0N, 128.2E) + **북쪽 라인은 북위** (버그② 회귀 가드)."""
    lat, lon = geos_latlon(np.array([2750.5]), np.array([2750.5]), _G)
    assert abs(lat[0]) < 1e-9 and abs(lon[0] - 128.2) < 1e-6
    lat_n, _ = geos_latlon(np.array([500.0]), np.array([2750.5]), _G)
    assert lat_n[0] > 45.0, f"북쪽 라인이 북위가 아님: {lat_n[0]:.2f} (버그② 반구 반전)"
    lat_s, _ = geos_latlon(np.array([5000.0]), np.array([2750.5]), _G)
    assert lat_s[0] < -45.0


def test_geos_pixel_scale_is_2km():
    """인접 픽셀 간 지상거리 ≈ 2km (버그① deg/rad 스케일 회귀 가드 —
    라디안 오독 시 ~0.035km로 붕괴)."""
    lat, lon = geos_latlon(np.array([2750.5, 2750.5]), np.array([2750.5, 2751.5]), _G)
    dkm = abs(lon[1] - lon[0]) * 111.32 * np.cos(np.radians(lat[0]))
    assert 1.7 < dkm < 2.3, f"픽셀 스케일 {dkm:.3f}km (2km 기대)"


def test_find_domain_window_korea_and_offdisk():
    l0, l1, c0, c1 = find_domain_window(_G, bbox=(31.0, 45.0, 118.0, 134.6))
    assert 0 < l0 < l1 < 5500 and 0 < c0 < c1 < 5500
    # 윈도우 네 모서리 재검증: bbox를 실제로 덮는가
    lat, lon = geos_latlon(np.array([float(l0), float(l1 - 1)]),
                           np.array([float(c0), float(c1 - 1)]), _G)
    assert np.nanmax(lat) > 45.0 and np.nanmin(lat) < 31.0
    with pytest.raises(ValueError, match="not on the FD disk"):
        find_domain_window(_G, bbox=(-5.0, 5.0, 250.0, 260.0))   # 원반 반대편


def test_read_fd_slot_rejects_bad_names(tmp_path):
    a = tmp_path / "gk2a_ami_le1b_ir105_ko020lc_202507190100.nc"   # KO 파일명
    a.touch()
    with pytest.raises(ValueError, match="not an FD 2km"):
        read_fd_slot([a])


@needs_fd
def test_cross_projection_bt_agreement():
    """같은 스캔의 KO(LCC) vs FD(geos): wv063 |ΔBT| 중앙값 < 0.5K (실측 0.114K).

    지오로케이션이 수 km라도 틀리면 매끄러운 WV 장에서도 어긋난다 — 두 독립
    투영·검정 경로의 상호 증명 게이트.
    """
    from kdm6.obs.gk2a_l1b import IR_CHANNELS, load_cal_table, read_ko_slot, slot_files
    from kdm6.obs.obs_ingest import collocate
    cal = load_cal_table(_CAL)
    ch9 = [c for c in IR_CHANNELS if c != "ir133"]
    fd = read_fd_slot(fd_slot_files(_FD01, "202507190100", ch9), stride=8)
    ko = read_ko_slot(slot_files(_GK2A, "202507190100", channels=ch9), cal, stride=8)
    idx, dist = collocate(ko.lat, ko.lon, fd.lat, fd.lon)
    near = dist < 2.0
    assert int(near.sum()) > 300                      # 오프셋 격자라 부분 매칭
    j = 7                                             # wv063
    m = near & (ko.obs_quality[:, j] == 0) & (fd.obs_quality[idx, j] == 0)
    d = (ko.bt[m, j] - fd.bt[idx[m], j]).abs()
    assert float(d.median()) < 0.5, f"wv063 교차 |ΔBT| 중앙값 {float(d.median()):.3f}K"
