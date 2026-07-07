"""GK2A AMI L1B(KO, ko020lc) → ObsPayload 어댑터 (계획 §6 파이프라인 ①).

입력 산출물의 특성 (실파일 실측, 2025-07-19 KO 세트):
  - `image_pixel_values` (900×900 uint16) DN + LC 투영 속성만 있음 — **검정계수
    없음** (원본 ela020ge에서 재격자되며 검정 속성 탈락, 실측 확인).
  - 검정계수는 같은 날짜의 FD 원본(noaa-gk2a-pds S3)에서 추출한 테이블 JSON을
    사용 (data/gk2a_ami_cal_202507190000.json — 채널별 gain/offset/Teff c0-c2/
    물리상수, provenance 포함).

DN→BT 변환은 AD-RTTOV에서 검증된 로직의 1:1 이식:
  valid DN = raw & (2^13-1), quality = bits 13-14 (0=정상)
  radiance [mW m⁻² sr⁻¹ cm] = offset + gain·DN
  Teff = Planck⁻¹(radiance, ν=10⁴/λμm)   (h·c·σ/k / ln(2hc²σ³/L + 1))
  Tbb  = c0 + c1·Teff + c2·Teff²

지오로케이션: KO 격자는 Lambert Conformal Conic (파일 속성: sp1=30, sp2=60,
origin 38N/126E, 픽셀 2km, UL (-899, +899) km). 지구반경은 파일에 없어 KMA LCC
표준 구면 반경 **6371.00877 km**를 사용 — 게이트: (1) 원점 픽셀 = (38, 126)
정확 (반경 무관 불변식), (2) pyproj 독립 구현과 전 격자 교차검증.

출력: ObsPayload — RTTOV 16채널 레이아웃, 미제공 채널(solar 등)은
obs_quality=1(unusable)로 채워 양측-QC mask가 자동 배제.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Sequence

import numpy as np
import torch

from .obs_ingest import ObsPayload

_F64 = dict(dtype=torch.float64)

# RTTOV AMI 채널 순서 (AD-RTTOV AMI_16_CHANNEL_ORDER와 동일)
AMI_CHANNELS = ["vi004", "vi005", "vi006", "vi008", "nr013", "nr016",
                "sw038", "wv063", "wv069", "wv073", "ir087", "ir096",
                "ir105", "ir112", "ir123", "ir133"]
IR_CHANNELS = AMI_CHANNELS[6:]                     # RTTOV ch 7-16 (열적외)
# 주간 케이스 표준 세트: sw038(3.8μm) 제외 — 주간 태양반사 혼입으로 BT 오염
# (실측 376K @ 09-12 KST; 운영 관례상 주간 배제/특별처리 대상). 야간 케이스나
# 태양보정 도입 시에만 sw038 포함을 고려한다.
CLEAN_IR_CHANNELS = [c for c in IR_CHANNELS if c != "sw038"]   # 9채널

# KMA LCC 표준 구면 반경 [m] — KO/EA LC 격자 규격 (파일 속성엔 반경이 없음).
EARTH_RADIUS_M = 6371008.77


# ─── LCC 역변환 (Snyder, 구면) ───────────────────────────────────────────────


def _lcc_params(sp1_deg: float, sp2_deg: float, lat0_deg: float):
    p1, p2, p0 = map(math.radians, (sp1_deg, sp2_deg, lat0_deg))
    n = (math.log(math.cos(p1) / math.cos(p2))
         / math.log(math.tan(math.pi / 4 + p2 / 2) / math.tan(math.pi / 4 + p1 / 2)))
    F = math.cos(p1) * math.tan(math.pi / 4 + p1 / 2) ** n / n
    rho0 = EARTH_RADIUS_M * F / math.tan(math.pi / 4 + p0 / 2) ** n
    return n, F, rho0


def ko_grid_latlon(attrs: dict) -> tuple[np.ndarray, np.ndarray]:
    """KO LC 격자의 픽셀중심 (lat, lon) [deg] — (ny, nx) 각각.

    attrs: L1B 글로벌 속성 dict (standard_parallel1/2, origin_latitude,
    central_meridian, pixel_size, upper_left_easting/northing, image_width/height).
    """
    n, F, rho0 = _lcc_params(attrs["standard_parallel1"],
                             attrs["standard_parallel2"],
                             attrs["origin_latitude"])
    lam0 = math.radians(attrs["central_meridian"])
    px = float(attrs["pixel_size"])
    nx, ny = int(attrs["image_width"]), int(attrs["image_height"])
    # 픽셀 중심 좌표: UL 속성은 UL 픽셀의 중심 (NMSC 관례 — 대칭 UL/-LR ±899km가
    # 900픽셀·2km와 정합하는 유일한 해석: 899 = (900-1)/2 × 2 km)
    x = attrs["upper_left_easting"] + px * np.arange(nx)          # (nx,)
    y = attrs["upper_left_northing"] - px * np.arange(ny)         # (ny,) 북→남
    X, Y = np.meshgrid(x, y)                                      # (ny, nx)
    rho = np.sign(n) * np.sqrt(X ** 2 + (rho0 - Y) ** 2)
    theta = np.arctan2(X, rho0 - Y)
    lon = np.degrees(lam0 + theta / n)
    lat = np.degrees(2.0 * np.arctan((EARTH_RADIUS_M * F / rho) ** (1.0 / n))
                     - math.pi / 2)
    return lat, lon


# ─── DN → BT (AD-RTTOV 검증 로직 1:1) ───────────────────────────────────────


def load_cal_table(path: str | Path) -> dict:
    tab = json.loads(Path(path).read_text())
    if "channels" not in tab:
        raise ValueError(f"{path}: not a GK2A cal table (no 'channels')")
    return tab


def dn_to_bt(raw: np.ndarray, cal: dict) -> tuple[np.ndarray, np.ndarray]:
    """uint16 raw → (BT [K], quality flag) — 둘 다 (ny, nx).

    quality: 0=정상 (bits 13-14), 비0=플래그. BT는 플래그 픽셀에서도 계산되나
    소비측 mask가 배제한다 (reject-don't-drop: NaN 주입 대신 플래그 유지).
    """
    dn = (raw & ((1 << 13) - 1)).astype(np.float64)
    quality = ((raw >> 13) & 0b11).astype(np.float64)
    gain, offset = cal["DN_to_Radiance_Gain"], cal["DN_to_Radiance_Offset"]
    lam_um = float(cal["channel_center_wavelength"])  # FD 속성이 문자열인 채널 존재
    h, c, k = (cal["Plank_constant_h"], cal["light_speed"],
               cal["Boltzmann_constant_k"])
    rad = offset + gain * dn                                      # mW m-2 sr-1 cm
    sigma_m = (10000.0 / lam_um) * 100.0                          # m-1
    l_sigma = np.clip(rad * 1.0e-3 / 100.0, 1e-30, None)          # W m-2 sr-1 (m-1)-1
    teff = h * c * sigma_m / k / np.log((2.0 * h * c * c * sigma_m ** 3) / l_sigma + 1.0)
    tbb = cal["Teff_to_Tbb_c0"] + cal["Teff_to_Tbb_c1"] * teff \
        + cal["Teff_to_Tbb_c2"] * teff * teff
    return tbb, quality


# ─── 슬롯 읽기 → ObsPayload ─────────────────────────────────────────────────


_FN_RE = re.compile(r"gk2a_ami_le1b_([a-z0-9]+)_ko020lc_(\d{12})\.nc$")


def read_ko_slot(files: Sequence[str | Path], cal_table: dict,
                 *, stride: int = 8) -> ObsPayload:
    """한 시각 슬롯의 KO 채널 파일들 → ObsPayload (RTTOV 16채널 레이아웃).

    files: 같은 타임스탬프의 채널 파일 경로들 (IR 10개 권장). 파일명에서 채널을
    파싱하고 타임스탬프 불일치는 거부. stride: 픽셀 솎음 (8 → 16 km 간격,
    900² → ~12.7k 관측; collocation/thinning의 상류 단계).
    """
    by_ch: dict[str, Path] = {}
    stamp = None
    for f in files:
        m = _FN_RE.search(str(f))
        if not m:
            raise ValueError(f"not a KO L1B filename: {f}")
        ch, ts = m.group(1), m.group(2)
        if stamp is None:
            stamp = ts
        elif ts != stamp:
            raise ValueError(f"mixed timestamps in one slot: {stamp} vs {ts} ({f})")
        by_ch[ch] = Path(f)
    unknown = set(by_ch) - set(AMI_CHANNELS)
    if unknown:
        raise ValueError(f"unknown AMI channels: {sorted(unknown)}")

    lat = lon = None
    bt_all: dict[str, np.ndarray] = {}
    q_all: dict[str, np.ndarray] = {}
    for ch, path in sorted(by_ch.items()):
        import netCDF4                       # 검증 뒤로 지연 — 파일명/타임스탬프
        ds = netCDF4.Dataset(str(path))
        try:
            raw = np.ma.filled(ds.variables["image_pixel_values"][:], 0).astype(np.uint16)
            if lat is None:
                attrs = {a: ds.getncattr(a) for a in ds.ncattrs()}
                lat, lon = ko_grid_latlon(attrs)
            cal = cal_table["channels"].get(ch)
            if cal is None:
                raise ValueError(f"cal table has no channel {ch!r}")
            bt, q = dn_to_bt(raw, cal)
            bt_all[ch], q_all[ch] = bt, q
        finally:
            ds.close()

    sl = (slice(stride // 2, None, stride),) * 2       # 중심-오프셋 솎음
    lat_s, lon_s = lat[sl].reshape(-1), lon[sl].reshape(-1)
    n_obs = lat_s.size
    nch = len(AMI_CHANNELS)
    bt_full = np.zeros((n_obs, nch))
    q_full = np.ones((n_obs, nch))                     # 미제공 채널 = unusable
    for ch, bt in bt_all.items():
        j = AMI_CHANNELS.index(ch)
        bt_full[:, j] = bt[sl].reshape(-1)
        q_full[:, j] = q_all[ch][sl].reshape(-1)
    return ObsPayload(
        bt=torch.as_tensor(bt_full, **_F64),
        obs_quality=torch.as_tensor(q_full, **_F64),
        lat=torch.as_tensor(np.ascontiguousarray(lat_s), **_F64),
        lon=torch.as_tensor(np.ascontiguousarray(lon_s), **_F64))


def slot_files(root: str | Path, timestamp: str,
               channels: Sequence[str] = IR_CHANNELS) -> list[Path]:
    """디렉토리 트리에서 타임스탬프 슬롯의 채널 파일들을 찾는다 (없으면 에러)."""
    root = Path(root)
    out = []
    for ch in channels:
        hits = sorted(root.rglob(f"gk2a_ami_le1b_{ch}_ko020lc_{timestamp}.nc"))
        if not hits:
            raise FileNotFoundError(
                f"channel {ch} @ {timestamp} not found under {root}")
        out.append(hits[0])
    return out
