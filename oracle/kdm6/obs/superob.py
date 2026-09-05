"""동화 체계 1단계 — 관측 전처리: GK2A → 수치모델 격자 (superobbing).

체계 (실험 설계 지시로 재설계, 2026-07-07):
  [1] 어댑터   gk2a_l1b(KO)/gk2a_l1b_fd(FD) → ObsPayload (원해상도)
  [2] 전처리   본 모듈 — 전 모델도메인 모델격자 관측장 생성·저장 (슬롯별 산출물)
  [3] 동화     J/adjoint/minimizer 는 이 산출물만 소비
  [4] 검증     O−B/O−A·영상 비교도 같은 산출물·같은 모델격자

원칙: 자료동화의 기준 프레임은 **수치모델 수행영역**이다. 위성 관측은 동화·검증에
쓰이기 전에 모델 격자·해상도로 전처리되어야 하며(각 모델 셀에 배정된 원해상도
화소들의 평균 = superob), 하류 소비자는 원해상도 payload 를 직접 만지지 않는다.
(payload_to_column_obs 의 최근접-단일화소 배정은 점검증용 — 동화 경로에서는
본 모듈이 표준이다.)

방식:
  - 화소 배정: 원해상도 화소 → 최근접 모델 컬럼 (chunked haversine; max_dist
    게이트로 도메인 밖 화소 배제).
  - 셀 평균: quality-0 화소만 채널별 평균. 기여 화소 수 < min_pixels 이면
    그 셀·채널은 quality=1 (미충족 셀을 조용히 흉내내지 않음 — reject-don't-drop).
  - n_pixels 를 진단으로 보존 (대표성 잡음의 사후 분석용).

산출 SuperObs 는 ColumnObs 와 동일 소비 규약: bt/obs_quality (B, nch),
미관측 컬럼 quality=1 → 기존 양측-QC mask 가 자동 배제.
"""
from __future__ import annotations

import math

from dataclasses import dataclass

import torch

from .obs_ingest import (ObsPayload, _validate_coordinate_tensors, collocate,
                         haversine_km)

_F64 = dict(dtype=torch.float64)


@dataclass
class SuperObs:
    """모델격자 관측장 (B = 모델 컬럼 수)."""
    bt: torch.Tensor            # (B, nch) — 셀 평균 BT [K]
    obs_quality: torch.Tensor   # (B, nch) — 0=사용가능
    n_pixels: torch.Tensor      # (B, nch) — 셀·채널별 기여 화소 수
    n_assigned_pixels: int      # 배정된 원화소 총수 (진단)
    n_dropped_far: int          # max_dist 밖 화소 수 (진단)
    valid_time_utc: "str | None" = None  # data-derived slot stamp


def superob_to_model_grid(payload: ObsPayload, grid_lat: torch.Tensor,
                          grid_lon: torch.Tensor, *,
                          max_dist_km: float, min_pixels: int = 3) -> SuperObs:
    """원해상도 payload → 모델격자 superob.

    grid_lat/lon: (B,) 모델 컬럼 좌표 (frame reader 의 b = j·nx+i flatten).
    max_dist_km: 배정 게이트 — 모델 셀 반대각(Δx·√2/2)보다 약간 크게 주면
    도메인 내부 화소는 전부 배정되고 밖은 떨어진다 (5 km 격자 → 4 km 권장).
    """
    # Input-validation contract (external review P1-3): a non-finite or
    # non-positive gate silently mis-collocates (min_pixels is validated in
    # superob_with_mapping, the shared chokepoint).
    if not (math.isfinite(max_dist_km) and max_dist_km > 0.0):
        raise ValueError(
            f"max_dist_km must be finite and > 0 (got {max_dist_km!r})")
    if payload.bias is not None or payload.channel_gate is not None:
        raise ValueError(
            "superob_to_model_grid does not consume ObsPayload.bias/channel_gate; "
            "apply these fields in an obs-eval adapter before superobbing")
    # KD-트리 사상 + index_add 조합 — 전 경로가 O(N log B) (brute-force 제거).
    mapping = build_pixel_mapping(payload.lat, payload.lon, grid_lat, grid_lon,
                                  max_dist_km=max_dist_km)
    return superob_with_mapping(payload, mapping, int(grid_lat.numel()),
                                min_pixels=min_pixels)


_SUPEROB_REQUIRED_KEYS = frozenset({
    "bt", "obs_quality", "n_pixels", "n_assigned_pixels", "n_dropped_far",
})
_SUPEROB_OPTIONAL_KEYS = frozenset({"valid_time_utc"})


def _validate_superob_archive(d) -> None:
    """Validate the small, tensor-only SuperObs archive schema."""
    if not isinstance(d, dict):
        raise ValueError("SuperObs archive must contain a dictionary")
    keys = set(d)
    missing = _SUPEROB_REQUIRED_KEYS - keys
    unknown = keys - _SUPEROB_REQUIRED_KEYS - _SUPEROB_OPTIONAL_KEYS
    if missing:
        raise ValueError(f"SuperObs archive missing keys: {sorted(missing)}")
    if unknown:
        raise ValueError(f"SuperObs archive has unknown keys: {sorted(unknown)}")

    tensors = {}
    for name in ("bt", "obs_quality", "n_pixels"):
        value = d[name]
        if not isinstance(value, torch.Tensor):
            raise ValueError(f"SuperObs archive {name} must be a tensor")
        if value.dtype != torch.float64:
            raise ValueError(
                f"SuperObs archive {name} must use torch.float64 "
                f"(got {value.dtype})")
        if value.ndim != 2 or value.shape[0] < 1 or value.shape[1] < 1:
            raise ValueError(
                f"SuperObs archive {name} must be a non-empty 2-D tensor "
                f"(got shape {tuple(value.shape)})")
        tensors[name] = value
    shape = tensors["bt"].shape
    if tensors["obs_quality"].shape != shape or tensors["n_pixels"].shape != shape:
        raise ValueError(
            "SuperObs archive bt, obs_quality, and n_pixels must have "
            f"the same (B, nch) shape (got {tuple(tensors['bt'].shape)}, "
            f"{tuple(tensors['obs_quality'].shape)}, "
            f"{tuple(tensors['n_pixels'].shape)})")

    quality = tensors["obs_quality"]
    n_pixels = tensors["n_pixels"]
    if not torch.isfinite(quality).all():
        raise ValueError("SuperObs archive obs_quality contains non-finite values")
    if not bool(((quality == 0.0) | (quality == 1.0)).all()):
        raise ValueError("SuperObs archive obs_quality must contain only 0 or 1")
    usable = quality == 0.0
    bt = tensors["bt"]
    if not torch.isfinite(bt[usable]).all():
        raise ValueError("SuperObs archive usable bt contains non-finite values")
    if not torch.isfinite(n_pixels).all() or bool((n_pixels < 0.0).any()):
        raise ValueError("SuperObs archive n_pixels must be finite and >= 0")
    if not bool((n_pixels == torch.round(n_pixels)).all()):
        raise ValueError("SuperObs archive n_pixels must contain integer counts")
    if bool((n_pixels[usable] < 1.0).any()):
        raise ValueError("SuperObs archive usable cells need n_pixels >= 1")

    for name in ("n_assigned_pixels", "n_dropped_far"):
        value = d[name]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(
                f"SuperObs archive {name} must be a plain int >= 0 "
                f"(got {value!r})")
    # Each source pixel contributes at most once per channel, and a usable
    # cell cannot claim zero contributors.  This catches swapped counts and
    # malformed tensors without introducing a mapping/provenance schema.
    if bool((n_pixels.sum(dim=0) > d["n_assigned_pixels"]).any()):
        raise ValueError(
            "SuperObs archive n_pixels exceeds n_assigned_pixels for a channel")

    if "valid_time_utc" in d:
        stamp = d["valid_time_utc"]
        if stamp is not None and not isinstance(stamp, str):
            raise ValueError("SuperObs archive valid_time_utc must be str or None")


def save_superobs(so: SuperObs, path) -> None:
    """슬롯 산출물 저장 (torch.save) — 전처리는 1회, 소비는 다회."""
    archive = dict(bt=so.bt, obs_quality=so.obs_quality, n_pixels=so.n_pixels,
                   n_assigned_pixels=so.n_assigned_pixels,
                   n_dropped_far=so.n_dropped_far,
                   valid_time_utc=so.valid_time_utc)
    _validate_superob_archive(archive)
    torch.save(archive, path)


def load_superobs(path) -> SuperObs:
    d = torch.load(path, weights_only=True)
    _validate_superob_archive(d)
    return SuperObs(bt=d["bt"], obs_quality=d["obs_quality"],
                    n_pixels=d["n_pixels"],
                    n_assigned_pixels=int(d["n_assigned_pixels"]),
                    n_dropped_far=int(d["n_dropped_far"]),
                    # Archives made before timestamp propagation remain
                    # explicitly untimed; a date-aware downstream consumer
                    # must apply its existing fail-closed date guard.
                    valid_time_utc=d.get("valid_time_utc"))


def preprocess_gk2a_ko_slot(gk2a_root, timestamp: str, channels,
                            grid_lat: torch.Tensor, grid_lon: torch.Tensor,
                            cal_table: dict, out_path=None, *,
                            stride: int = 1, max_dist_km: float = 4.0,
                            min_pixels: int = 3) -> SuperObs:
    """KO 슬롯 1개의 전처리 파이프: 어댑터 → superob → (저장).

    stride=1 이 표준 (2 km 전화소); 모델 도메인 bbox 밖 화소는 사전 필터로
    제거해 collocation 비용을 줄인다.
    """
    from .gk2a_l1b import read_ko_slot, slot_files
    from .obs_ingest import ObsPayload
    pl = read_ko_slot(slot_files(gk2a_root, timestamp, channels=channels),
                      cal_table, stride=stride)
    m = ((pl.lat >= grid_lat.min() - 0.1) & (pl.lat <= grid_lat.max() + 0.1)
         & (pl.lon >= grid_lon.min() - 0.1) & (pl.lon <= grid_lon.max() + 0.1))
    pl = ObsPayload(bt=pl.bt[m], obs_quality=pl.obs_quality[m],
                    lat=pl.lat[m], lon=pl.lon[m],
                    bias=None if pl.bias is None else pl.bias[m],
                    channel_gate=(None if pl.channel_gate is None
                                  else pl.channel_gate[m]),
                    valid_time_utc=pl.valid_time_utc)
    so = superob_to_model_grid(pl, grid_lat, grid_lon,
                               max_dist_km=max_dist_km, min_pixels=min_pixels)
    if out_path is not None:
        save_superobs(so, out_path)
    return so


# ─── mapping 전환 방식 (시불변 사상 사전계산) ────────────────────────────────
# KO 격자·모델 격자 모두 고정 → 화소→셀 사상은 시불변. 한 번 계산·저장하면
# 이후 슬롯 전처리는 haversine 없이 index_add 만으로 수행된다 (실측 188s → ~1s).


def _unit_xyz(lat: torch.Tensor, lon: torch.Tensor):
    la, lo = torch.deg2rad(lat), torch.deg2rad(lon)
    cl = torch.cos(la)
    return torch.stack([cl * torch.cos(lo), cl * torch.sin(lo),
                        torch.sin(la)], dim=-1).numpy()


def build_pixel_mapping(obs_lat: torch.Tensor, obs_lon: torch.Tensor,
                        grid_lat: torch.Tensor, grid_lon: torch.Tensor,
                        *, max_dist_km: float) -> torch.Tensor:
    """화소별 배정 컬럼 인덱스 (far 는 -1) — 슬롯 간 재사용 사상.

    알고리즘: KD-트리 (단위구면 3-D 좌표) — 현거리(chord)와 대원거리는 단조
    동치라 최근접이 동일하다. O(N log B); brute-force 전쌍 haversine
    (O(N·B) = 2.7e10 평가, 실측 187 s)의 교체 — 실측 ~1 s, 사상 결과 동일.
    scipy 부재 시 chunked brute-force 로 폴백 (결과 동일, 느림).
    """
    import math
    if not (math.isfinite(max_dist_km) and max_dist_km > 0.0):
        raise ValueError(
            f"max_dist_km must be finite and > 0 (got {max_dist_km!r})")
    # Validate before selecting SciPy KDTree.  The fallback calls collocate,
    # but the fast branch otherwise used to bypass its finite/range/degenerate
    # grid checks entirely.
    _validate_coordinate_tensors(obs_lat, obs_lon, grid_lat, grid_lon)
    try:
        from scipy.spatial import cKDTree
    except ImportError:                                    # pragma: no cover
        idx, dist = collocate(obs_lat, obs_lon, grid_lat, grid_lon)
        mapping = idx.clone()
        mapping[dist > max_dist_km] = -1
        return mapping
    tree = cKDTree(_unit_xyz(grid_lat, grid_lon))
    _, idx = tree.query(_unit_xyz(obs_lat, obs_lon), k=1)
    mapping = torch.as_tensor(idx, dtype=torch.int64)
    # Use the actual shared great-circle distance for the gate.  Converting a
    # large distance to a chord with sin() folds values above pi*R back into
    # the near side of the sphere (e.g. 50,000 km rejects an exact hit), and
    # can disagree with the brute-force fallback at strict boundaries.
    nearest_lat = grid_lat[mapping]
    nearest_lon = grid_lon[mapping]
    dist = haversine_km(obs_lat, obs_lon, nearest_lat, nearest_lon)
    mapping[dist > max_dist_km] = -1
    return mapping


def superob_with_mapping(payload: ObsPayload, mapping: torch.Tensor, B: int,
                         *, min_pixels: int = 3) -> SuperObs:
    """사전계산 사상으로 superob — collocation 생략 (mapping 전환 방식).

    payload 화소 순서는 mapping 을 만든 화소 순서와 동일해야 한다
    (같은 어댑터·같은 stride — 길이 불일치는 즉시 거부).
    """
    if (isinstance(B, bool) or not isinstance(B, int) or B <= 0):
        raise ValueError(f"B (column count) must be a positive int (got {B!r})")
    if not isinstance(mapping, torch.Tensor):
        raise ValueError("mapping must be a rank-1 torch.Tensor")
    if mapping.ndim != 1:
        raise ValueError(
            f"mapping must be rank-1 (got shape {tuple(mapping.shape)})")
    if mapping.dtype != torch.int64:
        raise ValueError(
            f"mapping must use torch.int64 (got {mapping.dtype})")
    if payload.n_obs != mapping.numel():
        raise ValueError(
            f"payload pixel count {payload.n_obs} != mapping {mapping.numel()} "
            "-- mapping was built for a different pixel set/stride")
    if payload.bias is not None or payload.channel_gate is not None:
        raise ValueError(
            "superob_with_mapping does not consume ObsPayload.bias/channel_gate; "
            "apply these fields in an obs-eval adapter before superobbing")
    # Input-validation contract (external review P1-3): min_pixels < 1 makes
    # `good = n >= min_pixels` accept EMPTY cells (0/0 mean + usable quality);
    # an out-of-range mapping index scatters out of bounds (or silently
    # wraps). Reject at the boundary rather than mis-compute.
    if (isinstance(min_pixels, bool) or not isinstance(min_pixels, int)
            or min_pixels < 1):
        raise ValueError(f"min_pixels must be an int >= 1 (got {min_pixels!r})")
    if bool(((mapping >= B) | (mapping < -1)).any()):
        raise ValueError(
            f"mapping contains column indices outside [-1, {B}) — a stale "
            "mapping or wrong B would scatter out of range")
    near = mapping >= 0
    idx = mapping[near]
    nch = payload.nch
    bt = torch.zeros((B, nch), **_F64)
    quality = torch.ones((B, nch), **_F64)
    n_pix = torch.zeros((B, nch), **_F64)
    for j in range(nch):
        okp = payload.obs_quality[near, j] == 0
        n_ok = int(okp.sum())
        if n_ok == 0:
            continue
        s = torch.zeros(B, **_F64).index_add_(0, idx[okp], payload.bt[near][okp, j])
        n = torch.zeros(B, **_F64).index_add_(0, idx[okp], torch.ones(n_ok, **_F64))
        good = n >= min_pixels
        bt[good, j] = s[good] / n[good]
        quality[good, j] = 0.0
        n_pix[:, j] = n
    return SuperObs(bt=bt, obs_quality=quality, n_pixels=n_pix,
                    n_assigned_pixels=int(near.sum()),
                    n_dropped_far=int((~near).sum()),
                    valid_time_utc=payload.valid_time_utc)
