"""실관측 인제스트 코어 — payload 스키마 + collocation (계획 §4 마지막 항목).

지금까지 obs 규약은 `_build_mask`/`compute_obs_loss`/테스트들에 **암묵적**이었다
(감사 지적). 이 모듈이 그것을 공식화한다:

  ObsPayload  : 관측 묶음의 검증된 스키마 (bt/obs_quality/bias/channel_gate +
                위경도). L1B 파일 디코더는 이 스키마를 만들어내는 **어댑터**로
                별도 구현한다 (실데이터 없이 쓴 디코더는 검증 불가 — 인터페이스만
                고정하고 구현은 데이터 확보 시).
  collocation : 관측 (lat, lon) → 최근접 모델 컬럼. grid-agnostic 순수 함수 —
                이상화 SS 케이스는 XLAT/XLONG이 전부 0(지리 없음)이라 실그리드
                검증이 불가하므로, 합성 그리드로 검증하고 퇴화 그리드는 loud
                거부한다.
  통합 규약    : payload → (B, nch) 컬럼-정렬 bt/quality. **관측이 배정되지 않은
                컬럼은 obs_quality=1(unusable)** — 기존 양측-QC mask가 자동으로
                걸러내므로 driver/innovation 항은 무변경으로 소비한다.

충돌 규칙: 한 컬럼에 여러 관측이 배정되면 최근접이 이기고 나머지는 drop으로
집계된다(침묵 아님 — diagnostics에 카운트). thinning은 상류 책임.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Optional

import torch

_F64 = dict(dtype=torch.float64)
_EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True)
class ObsPayload:
    """관측 묶음 스키마 (한 관측시각 슬롯).

    규약 (기존 _build_mask/compute_obs_loss와 동일):
      bt          : (n_obs, nch) f64 — 관측 BT [K]
      obs_quality : (n_obs, nch) f64 — 0=사용가능, 비0=플래그 (keep-mask 아님!)
      lat, lon    : (n_obs,) f64 — 관측 footprint 중심 [deg]
      bias        : optional (n_obs, nch) — 정적 바이어스 (detached로 소비됨)
      channel_gate: optional (n_obs, nch) — 진짜 keep-조건 (1=keep)
    """
    bt: torch.Tensor
    obs_quality: torch.Tensor
    lat: torch.Tensor
    lon: torch.Tensor
    bias: Optional[torch.Tensor] = None
    channel_gate: Optional[torch.Tensor] = None
    valid_time_utc: Optional[str] = None    # data-derived slot stamp (yyyymmddHHMM)

    def __post_init__(self):
        # The ingestion contract is f64 end to end.  Without this boundary a
        # float32 payload reaches the f64 ``index_add_`` accumulators in the
        # collocation consumers and fails there with an opaque dtype error.
        # Check optional fields too: they are part of the same payload record.
        required = {"bt", "obs_quality", "lat", "lon"}
        for name in ("bt", "obs_quality", "lat", "lon", "bias", "channel_gate"):
            value = getattr(self, name)
            if value is None and name in required:
                raise ValueError(f"{name} must be a torch.Tensor")
            if value is not None and not isinstance(value, torch.Tensor):
                raise ValueError(f"{name} must be a torch.Tensor")
            if value is not None and value.dtype != torch.float64:
                raise ValueError(
                    f"{name} must use torch.float64 (got {value.dtype})")
        bt = self.bt
        if bt.ndim != 2:
            raise ValueError(f"bt must be (n_obs, nch), got ndim={bt.ndim}")
        n_obs, nch = bt.shape
        if self.obs_quality.shape != (n_obs, nch):
            raise ValueError(
                f"obs_quality shape {tuple(self.obs_quality.shape)} != bt "
                f"{(n_obs, nch)}")
        for name in ("lat", "lon"):
            v = getattr(self, name)
            if v.shape != (n_obs,):
                raise ValueError(f"{name} shape {tuple(v.shape)} != ({n_obs},)")
        for name in ("bias", "channel_gate"):
            v = getattr(self, name)
            if v is not None and v.shape != (n_obs, nch):
                raise ValueError(
                    f"{name} shape {tuple(v.shape)} != bt {(n_obs, nch)}")
        if not torch.isfinite(bt).all():
            raise ValueError("bt contains non-finite values")
        if not torch.isfinite(self.obs_quality).all():
            raise ValueError("obs_quality contains non-finite values")
        if not torch.isfinite(self.lat).all() or not torch.isfinite(self.lon).all():
            raise ValueError("lat/lon contains non-finite values")
        if bool((self.lat.abs() > 90.0).any()) or bool((self.lon.abs() > 360.0).any()):
            raise ValueError("lat/lon out of range")
        if self.bias is not None and not torch.isfinite(self.bias).all():
            raise ValueError("bias contains non-finite values")
        if self.channel_gate is not None:
            if not torch.isfinite(self.channel_gate).all():
                raise ValueError("channel_gate contains non-finite values")
            if bool((self.channel_gate < 0.0).any()) or bool((self.channel_gate > 1.0).any()):
                raise ValueError("channel_gate must be in [0, 1]")

    @property
    def n_obs(self) -> int:
        return int(self.bt.shape[0])

    @property
    def nch(self) -> int:
        return int(self.bt.shape[1])


def haversine_km(lat1, lon1, lat2, lon2) -> torch.Tensor:
    """대원거리 [km] — 브로드캐스트 가능한 torch 구현."""
    to_r = torch.deg2rad
    dlat = to_r(lat2 - lat1)
    dlon = to_r(lon2 - lon1)
    a = (torch.sin(dlat / 2) ** 2
         + torch.cos(to_r(lat1)) * torch.cos(to_r(lat2)) * torch.sin(dlon / 2) ** 2)
    return 2.0 * _EARTH_RADIUS_KM * torch.asin(torch.sqrt(torch.clamp(a, 0.0, 1.0)))


def collocate(obs_lat: torch.Tensor, obs_lon: torch.Tensor,
              grid_lat: torch.Tensor, grid_lon: torch.Tensor
              ) -> tuple[torch.Tensor, torch.Tensor]:
    """관측 → 최근접 모델 컬럼: (col_idx (n_obs,), dist_km (n_obs,)).

    grid_lat/lon: (B,) flat 컬럼 좌표 (frame reader의 b = j·nx + i 순서와 동일
    flatten을 호출자가 보장). 퇴화 그리드(전 좌표 동일 — 이상화 케이스의 all-0
    XLAT/XLONG이 정확히 이 꼴)는 최근접이 무의미하므로 loud 거부.
    """
    _validate_coordinate_tensors(obs_lat, obs_lon, grid_lat, grid_lon)
    # Validate the model grid first even when the observation slot is empty. An
    # empty slot is a valid no-data result only on a valid, geolocated model
    # grid; returning before validation would turn malformed grids into a
    # misleading empty success.  Once the shared coordinate contract passes,
    # there is no distance matrix to build and the geometric policy is vacuous.
    if obs_lat.numel() == 0:
        return (torch.empty((0,), dtype=torch.int64, device=grid_lat.device),
                torch.empty((0,), dtype=grid_lat.dtype, device=grid_lat.device))
    # 청크 처리: 전체 (n_obs, B) 거리행렬은 실규모(50k obs × 66k 컬럼)에서
    # 26GB로 OOM — LC05 실그리드 첫 접촉에서 실측 확인. 관측 축을 나눠
    # 피크 메모리를 chunk×B×8B (~0.5GB @1024×66k)로 제한한다.
    chunk = max(1, int(2 ** 26 // max(grid_lat.numel(), 1)))     # ~512MB f64 상한
    idx_parts, dist_parts = [], []
    for s in range(0, obs_lat.numel(), chunk):
        d = haversine_km(obs_lat[s:s + chunk, None], obs_lon[s:s + chunk, None],
                         grid_lat[None, :], grid_lon[None, :])   # (chunk, B)
        dd, ii = d.min(dim=1)
        idx_parts.append(ii)
        dist_parts.append(dd)
    return torch.cat(idx_parts), torch.cat(dist_parts)


def _validate_coordinate_tensors(obs_lat: torch.Tensor, obs_lon: torch.Tensor,
                                 grid_lat: torch.Tensor,
                                 grid_lon: torch.Tensor) -> None:
    """Validate the coordinate contract shared by every collocation backend."""
    if (not isinstance(obs_lat, torch.Tensor)
            or not isinstance(obs_lon, torch.Tensor)
            or obs_lat.ndim != 1 or obs_lon.shape != obs_lat.shape):
        raise ValueError("obs_lat/obs_lon must be matching 1-D tensors")
    if (not isinstance(grid_lat, torch.Tensor)
            or not isinstance(grid_lon, torch.Tensor)
            or grid_lat.ndim != 1 or grid_lon.shape != grid_lat.shape):
        raise ValueError("grid_lat/grid_lon must be matching 1-D tensors")
    if not torch.isfinite(obs_lat).all() or not torch.isfinite(obs_lon).all():
        raise ValueError("observation coordinates must be finite")
    if not torch.isfinite(grid_lat).all() or not torch.isfinite(grid_lon).all():
        raise ValueError("grid coordinates must be finite")
    if bool((obs_lat.abs() > 90.0).any()) or bool((obs_lon.abs() > 360.0).any()):
        raise ValueError("observation coordinates out of range")
    if bool((grid_lat.abs() > 90.0).any()) or bool((grid_lon.abs() > 360.0).any()):
        raise ValueError("grid coordinates out of range")
    if grid_lat.numel() < 2:
        raise ValueError("grid must have at least 2 columns")
    if bool((grid_lat == grid_lat[0]).all()) and bool((grid_lon == grid_lon[0]).all()):
        raise ValueError(
            "degenerate grid: all columns share one (lat, lon) — an idealized "
            "case (all-zero XLAT/XLONG) has no geolocation; collocation is "
            "undefined there")


@dataclass
class ColumnObs:
    """payload를 배치 컬럼 공간으로 정렬한 결과 — driver가 그대로 소비.

    bt/obs_quality: (B, nch). 관측 미배정 컬럼은 obs_quality=1 (양측-QC mask가
    자동 배제; bt 값은 0 placeholder — mask=0이라 절대 소비되지 않음).
    """
    bt: torch.Tensor
    obs_quality: torch.Tensor
    n_assigned: int
    n_dropped_far: int
    n_dropped_collision: int
    col_of_obs: torch.Tensor           # (n_obs,) — 배정 컬럼 (-1 = dropped)
    valid_time_utc: "str | None" = None   # propagated from ObsPayload
    bias: Optional[torch.Tensor] = None          # (B, nch), if supplied by payload
    channel_gate: Optional[torch.Tensor] = None  # (B, nch), if supplied by payload


def payload_to_column_obs(payload: ObsPayload, grid_lat: torch.Tensor,
                          grid_lon: torch.Tensor, *,
                          max_dist_km: float) -> ColumnObs:
    """collocation + 충돌 해소 + 컬럼-정렬 (B, nch) 관측 생성."""
    if not (math.isfinite(max_dist_km) and max_dist_km >= 0.0):
        raise ValueError(
            f"max_dist_km must be finite and >= 0 (got {max_dist_km!r})")
    B = int(grid_lat.numel())
    nch = payload.nch
    idx, dist = collocate(payload.lat, payload.lon, grid_lat, grid_lon)

    bt = torch.zeros((B, nch), **_F64)
    quality = torch.ones((B, nch), **_F64)              # 기본: 전 컬럼 unusable
    bias = (torch.zeros((B, nch), **_F64)
            if payload.bias is not None else None)
    channel_gate = (torch.zeros((B, nch), **_F64)
                    if payload.channel_gate is not None else None)
    best_dist = torch.full((B,), float("inf"), **_F64)
    col_of_obs = torch.full((payload.n_obs,), -1, dtype=torch.int64)
    owner_of_col = torch.full((B,), -1, dtype=torch.int64)

    n_far = 0
    n_coll = 0
    order = torch.argsort(dist)                          # 가까운 관측부터 배정
    for o in order.tolist():
        b = int(idx[o])
        if float(dist[o]) > max_dist_km:
            n_far += 1
            continue
        if float(best_dist[b]) <= float(dist[o]):
            n_coll += 1                                  # 더 가까운 관측이 선점
            continue
        prev = int(owner_of_col[b])
        if prev >= 0:                                    # (동률 역전은 argsort상 불가)
            n_coll += 1
            col_of_obs[prev] = -1
        best_dist[b] = dist[o]
        owner_of_col[b] = o
        col_of_obs[o] = b
        bt[b] = payload.bt[o]
        quality[b] = payload.obs_quality[o]
        if bias is not None:
            bias[b] = payload.bias[o]
        if channel_gate is not None:
            channel_gate[b] = payload.channel_gate[o]

    return ColumnObs(bt=bt, obs_quality=quality,
                     n_assigned=int((col_of_obs >= 0).sum()),
                     n_dropped_far=n_far, n_dropped_collision=n_coll,
                     col_of_obs=col_of_obs,
                     bias=bias, channel_gate=channel_gate,
                     valid_time_utc=payload.valid_time_utc)
