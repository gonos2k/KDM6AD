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

from .obs_ingest import ObsPayload, collocate

_F64 = dict(dtype=torch.float64)


@dataclass
class SuperObs:
    """모델격자 관측장 (B = 모델 컬럼 수)."""
    bt: torch.Tensor            # (B, nch) — 셀 평균 BT [K]
    obs_quality: torch.Tensor   # (B, nch) — 0=사용가능
    n_pixels: torch.Tensor      # (B, nch) — 셀·채널별 기여 화소 수
    n_assigned_pixels: int      # 배정된 원화소 총수 (진단)
    n_dropped_far: int          # max_dist 밖 화소 수 (진단)


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
    # KD-트리 사상 + index_add 조합 — 전 경로가 O(N log B) (brute-force 제거).
    mapping = build_pixel_mapping(payload.lat, payload.lon, grid_lat, grid_lon,
                                  max_dist_km=max_dist_km)
    return superob_with_mapping(payload, mapping, int(grid_lat.numel()),
                                min_pixels=min_pixels)


def save_superobs(so: SuperObs, path) -> None:
    """슬롯 산출물 저장 (torch.save) — 전처리는 1회, 소비는 다회."""
    torch.save(dict(bt=so.bt, obs_quality=so.obs_quality, n_pixels=so.n_pixels,
                    n_assigned_pixels=so.n_assigned_pixels,
                    n_dropped_far=so.n_dropped_far), path)


def load_superobs(path) -> SuperObs:
    d = torch.load(path, weights_only=True)
    return SuperObs(bt=d["bt"], obs_quality=d["obs_quality"],
                    n_pixels=d["n_pixels"],
                    n_assigned_pixels=int(d["n_assigned_pixels"]),
                    n_dropped_far=int(d["n_dropped_far"]))


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
                    lat=pl.lat[m], lon=pl.lon[m])
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
    try:
        from scipy.spatial import cKDTree
    except ImportError:                                    # pragma: no cover
        idx, dist = collocate(obs_lat, obs_lon, grid_lat, grid_lon)
        mapping = idx.clone()
        mapping[dist > max_dist_km] = -1
        return mapping
    tree = cKDTree(_unit_xyz(grid_lat, grid_lon))
    d_chord, idx = tree.query(_unit_xyz(obs_lat, obs_lon), k=1)
    # 대원거리 게이트를 현거리로 환산: chord = 2·sin(d_gc/2R)
    R = 6371.0088
    chord_max = 2.0 * math.sin(max_dist_km / (2.0 * R))
    mapping = torch.as_tensor(idx, dtype=torch.int64)
    mapping[torch.as_tensor(d_chord) > chord_max] = -1
    return mapping


def superob_with_mapping(payload: ObsPayload, mapping: torch.Tensor, B: int,
                         *, min_pixels: int = 3) -> SuperObs:
    """사전계산 사상으로 superob — collocation 생략 (mapping 전환 방식).

    payload 화소 순서는 mapping 을 만든 화소 순서와 동일해야 한다
    (같은 어댑터·같은 stride — 길이 불일치는 즉시 거부).
    """
    if payload.n_obs != mapping.numel():
        raise ValueError(
            f"payload pixel count {payload.n_obs} != mapping {mapping.numel()} "
            "-- mapping was built for a different pixel set/stride")
    # Input-validation contract (external review P1-3): min_pixels < 1 makes
    # `good = n >= min_pixels` accept EMPTY cells (0/0 mean + usable quality);
    # an out-of-range mapping index scatters out of bounds (or silently
    # wraps). Reject at the boundary rather than mis-compute.
    if not (isinstance(B, int) and B > 0):
        raise ValueError(f"B (column count) must be a positive int (got {B!r})")
    if not (isinstance(min_pixels, int) and min_pixels >= 1):
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
                    n_dropped_far=int((~near).sum()))
