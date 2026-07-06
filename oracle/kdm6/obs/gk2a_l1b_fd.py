"""GK2A AMI L1B **FD(전구, fd020ge)** → ObsPayload 어댑터 (§6.2 3h-창 확장).

KO(ko020lc) 어댑터와의 차이:
  - 투영: geos (CGMS 표준; coff/loff/cfac/lfac, sub_longitude[rad]) — AD-RTTOV
    검증 구현의 벡터화 이식. lfac<0 (y가 남향 증가) 그대로 수식에 흡수.
  - **검정계수 내장**: FD 원본은 DN_to_Radiance_Gain 등 검정 속성을 파일에
    가짐 → 외부 테이블 불필요, 파일 자신의 계수로 dn_to_bt (KO 동결 테이블의
    출처가 바로 이 속성들 — 같은 날짜 검정 동일함을 실측 확인).
  - 도메인 윈도우: 전구 5500²에서 한반도 박스만 — forward 투영 공식 대신
    **역변환 성긴-스캔**(50픽셀 간격 → bbox 포함 픽셀의 min/max ± 마진)으로
    윈도우를 찾는다 (수식 하나 줄이고 오류 여지 최소화; 비용 ~12k 픽셀).

DN→BT·quality 비트·ObsPayload 레이아웃은 gk2a_l1b(KO)와 공유 — 채널 결측은
동일하게 quality=1 자동 마스킹.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

import numpy as np
import torch

from .gk2a_l1b import AMI_CHANNELS, dn_to_bt
from .obs_ingest import ObsPayload

_F64 = dict(dtype=torch.float64)
_FD_RE = re.compile(r"gk2a_ami_le1b_([a-z0-9]+)_fd020ge_(\d{12})\.nc$")

_CAL_ATTRS = ["DN_to_Radiance_Gain", "DN_to_Radiance_Offset",
              "Teff_to_Tbb_c0", "Teff_to_Tbb_c1", "Teff_to_Tbb_c2",
              "Plank_constant_h", "light_speed", "Boltzmann_constant_k",
              "channel_center_wavelength"]
_GEO_ATTRS = ["coff", "loff", "cfac", "lfac", "sub_longitude",
              "nominal_satellite_height", "earth_equatorial_radius",
              "earth_polar_radius"]


def geos_latlon(lines: np.ndarray, cols: np.ndarray, g: dict
                ) -> tuple[np.ndarray, np.ndarray]:
    """geos 역변환 (CGMS; AD-RTTOV gk2a_ami_geolocation의 벡터화 1:1).

    반환 (lat, lon) [deg]; 지구원반 밖 픽셀은 NaN.
    """
    # GK2A의 cfac/lfac는 counts-per-DEGREE (실측: 2.04e7 → 픽셀당 3.2e-3°=
    # 56μrad = 2km/42164km ✓) — CGMS 원형(라디안 기준)과 달리 deg→rad 변환 필요.
    # 업스트림 AD-RTTOV 구현은 이 변환이 없어 부위성점(x=y=0)에서만 정확했음
    # (중심-픽셀 테스트만 있어 잠복 — 본 이식에서 전구 프로브로 발견).
    x = np.deg2rad((cols - g["coff"]) * (2.0 ** 16) / g["cfac"])
    y = np.deg2rad((lines - g["loff"]) * (2.0 ** 16) / g["lfac"])
    lon0, h = g["sub_longitude"], g["nominal_satellite_height"]
    a, b = g["earth_equatorial_radius"], g["earth_polar_radius"]
    cosx, sinx = np.cos(x), np.sin(x)
    cosy, siny = np.cos(y), np.sin(y)
    a2_b2 = (a * a) / (b * b)
    sd_term = (h * cosx * cosy) ** 2 - (cosy ** 2 + a2_b2 * siny ** 2) * (h * h - a * a)
    off = sd_term < 0
    sd = np.sqrt(np.where(off, 0.0, sd_term))
    sn = (h * cosx * cosy - sd) / (cosy ** 2 + a2_b2 * siny ** 2)
    s1 = h - sn * cosx * cosy
    s2 = sn * sinx * cosy
    # s3 부호: CGMS 원형(-sn·siny)은 lfac>0(남향-양) 규약용 — GK2A는 lfac<0
    # (북쪽 라인이 y>0)이므로 +sn·siny 가 옳다. 적도(부위성점)에선 lat=0이라
    # 이 반구 반전도 중심-픽셀 테스트에 잡히지 않았음 (두 번째 잠복 버그).
    s3 = sn * siny
    lon = np.degrees(lon0 + np.arctan2(s2, s1))
    lat = np.degrees(np.arctan(a2_b2 * s3 / np.sqrt(s1 ** 2 + s2 ** 2)))
    lat[off] = np.nan
    lon[off] = np.nan
    return lat, lon


def find_domain_window(g: dict, *, bbox: tuple[float, float, float, float],
                       n: int = 5500, coarse: int = 50, margin: int = 60
                       ) -> tuple[int, int, int, int]:
    """(lat0, lat1, lon0, lon1) bbox를 덮는 픽셀 윈도우 (l0, l1, c0, c1).

    역변환 성긴-스캔: coarse 간격 격자를 geolocate → bbox 내 픽셀의 min/max에
    coarse+margin 여유. 윈도우가 비면 loud 에러 (bbox가 원반 밖).
    """
    lat0, lat1, lon0, lon1 = bbox
    ii = np.arange(0, n, coarse, dtype=np.float64)
    L, C = np.meshgrid(ii, ii, indexing="ij")
    lat, lon = geos_latlon(L, C, g)
    inside = ((lat >= lat0) & (lat <= lat1) & (lon >= lon0) & (lon <= lon1))
    if not inside.any():
        raise ValueError(f"bbox {bbox} not on the FD disk")
    li, ci = np.where(inside)
    l0 = max(0, int(ii[li.min()]) - coarse - margin)
    l1 = min(n, int(ii[li.max()]) + coarse + margin)
    c0 = max(0, int(ii[ci.min()]) - coarse - margin)
    c1 = min(n, int(ii[ci.max()]) + coarse + margin)
    return l0, l1, c0, c1


def read_fd_slot(files: Sequence[str | Path], *,
                 bbox: tuple[float, float, float, float] = (31.0, 45.0, 118.0, 134.6),
                 stride: int = 4) -> ObsPayload:
    """한 시각 슬롯의 FD(2km) 채널 파일들 → 한반도-윈도우 ObsPayload.

    검정계수는 각 파일의 내장 속성에서 직접. 타임스탬프 혼합·비 2km 해상도 거부.
    stride 4 → 8km 솎음 (KO stride 4와 동일 밀도).
    """
    import netCDF4

    by_ch: dict[str, Path] = {}
    stamp = None
    for f in files:
        m = _FD_RE.search(str(f))
        if not m:
            raise ValueError(f"not an FD 2km L1B filename: {f}")
        ch, ts = m.group(1), m.group(2)
        if stamp is None:
            stamp = ts
        elif ts != stamp:
            raise ValueError(f"mixed timestamps in one slot: {stamp} vs {ts} ({f})")
        by_ch[ch] = Path(f)
    unknown = set(by_ch) - set(AMI_CHANNELS)
    if unknown:
        raise ValueError(f"unknown AMI channels: {sorted(unknown)}")

    win = lat = lon = None
    bt_all: dict[str, np.ndarray] = {}
    q_all: dict[str, np.ndarray] = {}
    for ch, path in sorted(by_ch.items()):
        ds = netCDF4.Dataset(str(path))
        try:
            if win is None:
                g = {a: float(ds.getncattr(a)) for a in _GEO_ATTRS}
                n = ds.dimensions["dim_image_y"].size
                win = find_domain_window(g, bbox=bbox, n=n)
                l0, l1, c0, c1 = win
                L, C = np.meshgrid(np.arange(l0, l1, dtype=np.float64),
                                   np.arange(c0, c1, dtype=np.float64),
                                   indexing="ij")
                lat, lon = geos_latlon(L, C, g)
            l0, l1, c0, c1 = win
            raw = np.ma.filled(
                ds.variables["image_pixel_values"][l0:l1, c0:c1], 0
            ).astype(np.uint16)
            cal = {a: ds.getncattr(a) for a in _CAL_ATTRS}
            bt, q = dn_to_bt(raw, cal)
            bt_all[ch], q_all[ch] = bt, q
        finally:
            ds.close()

    sl = (slice(stride // 2, None, stride),) * 2
    lat_s, lon_s = lat[sl].reshape(-1), lon[sl].reshape(-1)
    keep = np.isfinite(lat_s) & np.isfinite(lon_s)      # 원반-밖 가드
    lat_s, lon_s = lat_s[keep], lon_s[keep]
    n_obs = lat_s.size
    nch = len(AMI_CHANNELS)
    bt_full = np.zeros((n_obs, nch))
    q_full = np.ones((n_obs, nch))
    for ch, bt in bt_all.items():
        j = AMI_CHANNELS.index(ch)
        bt_full[:, j] = bt[sl].reshape(-1)[keep]
        q_full[:, j] = q_all[ch][sl].reshape(-1)[keep]
    return ObsPayload(
        bt=torch.as_tensor(bt_full, **_F64),
        obs_quality=torch.as_tensor(q_full, **_F64),
        lat=torch.as_tensor(np.ascontiguousarray(lat_s), **_F64),
        lon=torch.as_tensor(np.ascontiguousarray(lon_s), **_F64))


def fd_slot_files(root: str | Path, timestamp: str,
                  channels: Sequence[str]) -> list[Path]:
    """디렉토리 트리에서 FD 2km 슬롯 채널 파일들 (없으면 에러)."""
    root = Path(root)
    out = []
    for ch in channels:
        hits = sorted(root.rglob(f"gk2a_ami_le1b_{ch}_fd020ge_{timestamp}.nc"))
        if not hits:
            raise FileNotFoundError(f"FD channel {ch} @ {timestamp} not under {root}")
        out.append(hits[0])
    return out
