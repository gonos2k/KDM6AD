"""wrfout frame → State/Forcing reader (DA_REALTIME_PLAN T0-1).

호스트 물리가 실제로 받는 필드는 wrfout 원변수가 아니라 phy_prep가 파생한 것들이다
(host module_big_step_utilities_em.F phy_prep). 이 모듈은 그 파생을 fp64 torch로
1:1 미러한다. "조용히 틀리는" 파생 4종이 본체:

  1. THM→th 역변환  — USE_THETA_M=1(기본)일 때 예후변수는 θm−T0(wrfout `THM`).
     phy_prep F:105: th = (t+t0)/(1+Rv/Rd·qv).  wrfout `T`는 진단 dry θ−T0라
     th == T+T0 교차검증이 가능하다(테스트 불변식).
  2. rho 재구성 — phy_prep F:127: rho = 1/alt·(1+qv). ALT은 restart 전용이라
     wrfout에 없음 → 이상기체 EOS로 재구성: p = ρ_d·R_d·θm·π (WRF 상태방정식;
     Tv 항등식 p = ρ_moist·R_d·Tv 와 동치) → ρ_d = p/(R_d·θm·π), rho = ρ_d·(1+qv).
     검증: 정수압 일관성 dp/dz ≈ −rho·g (rho와 delz를 동시에 잡음).
  3. PH/PHB→delz — phy_prep F:148: dz8w(k) = z_w(k+1)−z_w(k), z_w = (PH+PHB)/g
     (w-스태거 41레벨 → 질량 40레벨 delz).
  4. t=0 nccn 폴백 — wrapper module_mp_kdm6ad.F ITIMESTEP==1 init:
     Z_SUM 하부누적, land: (5000·e^{−0.4·Z/1000}+100)·1e6,
     sea: (150·e^{−0.35·Z/1000}+10)·1e6.

파생은 전부 순수 함수(netCDF 무관) — 공개 CI에서 픽스처만으로 회귀 가능하고,
read_wrfout_frame은 netCDF 배관 + 순수 함수 호출로만 구성된다.

State 12필드 소스 (전부 wrfout에 존재, kdm6adscheme 히스토리 패키지):
  th←(THM 파생), qv←QVAPOR, qc←QCLOUD, qr←QRAIN, qi←QICE, qs←QSNOW, qg←QGRAUP,
  nccn←QNCCN(t=0 전부 0이면 폴백), nc←QNCLOUD, ni←QNICE, nr←QNRAIN, bg←QIB.

레이아웃: WRF (Time, bottom_top, south_north, west_east) → (B, K) fp64,
column (i, j) ↦ b = j·nx + i (meta에 기록). K는 WRF와 동일하게 bottom-up.
"""
from __future__ import annotations

from typing import NamedTuple

import numpy as np
import torch

from ..state import State, Forcing

# WRF share/module_model_constants.F 값 (오라클 물리 상수와 별개 — 호스트 dynamics
# 파생의 미러이므로 WRF 값을 쓴다).
G = 9.81
R_D = 287.0
R_V = 461.6
CP = 7.0 * R_D / 2.0          # 1004.5
RCP = R_D / CP
T0 = 300.0
P1000MB = 1.0e5

_F64 = dict(dtype=torch.float64)


# ─── 파생 4종 — 순수 함수 (netCDF 무관, 전부 (B, K) 또는 (B,) fp64) ────────────


def derive_p_pii(p_pert: torch.Tensor, pb: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    """phy_prep F:124-125 — p = P+PB, pii = (p/p1000mb)**rcp."""
    p = p_pert + pb
    pii = (p / P1000MB) ** RCP
    return p, pii


def derive_th(thm_pert: torch.Tensor, qv: torch.Tensor) -> torch.Tensor:
    """phy_prep F:105 (use_theta_m=1) — th = (THM+T0)/(1+Rv/Rd·qv)."""
    return (thm_pert + T0) / (1.0 + (R_V / R_D) * qv)


def derive_rho(p: torch.Tensor, thm_pert: torch.Tensor, pii: torch.Tensor,
               qv: torch.Tensor) -> torch.Tensor:
    """phy_prep F:127(rho = 1/alt·(1+qv))의 EOS 재구성 — ALT은 wrfout에 없음.

    WRF 상태방정식 p = ρ_d·R_d·θm·π  (⇔ p = ρ_moist·R_d·Tv, Tv 항등식) 에서
    ρ_d = p/(R_d·θm·π), rho = ρ_d·(1+qv).
    """
    thm = thm_pert + T0
    rho_d = p / (R_D * thm * pii)
    return rho_d * (1.0 + qv)


def derive_delz(ph: torch.Tensor, phb: torch.Tensor) -> torch.Tensor:
    """phy_prep F:148 — delz(k) = z_w(k+1) − z_w(k), z_w = (PH+PHB)/g.

    ph/phb: (B, K+1) w-스태거 geopotential → (B, K) 층두께.
    """
    z_w = (ph + phb) / G
    return z_w[:, 1:] - z_w[:, :-1]


def nccn_init_profile(delz: torch.Tensor, is_land: torch.Tensor) -> torch.Tensor:
    """wrapper module_mp_kdm6ad.F ITIMESTEP==1 nccn(NN) init의 미러.

    Z_SUM(k) = Σ_{k'<=k} delz(k')  (해당 층 두께 포함 하부누적 — Fortran 루프 그대로:
    Z_SUM을 먼저 더한 뒤 NN(k)을 계산).
    land (XLAND==1): (5000·exp(−0.4·Z/1000) + 100)·1e6
    sea            : (150 ·exp(−0.35·Z/1000) + 10 )·1e6
    delz: (B, K), is_land: (B,) bool → (B, K).
    """
    z_sum = torch.cumsum(delz, dim=1)
    land = (5000.0 * torch.exp(-0.4 * z_sum / 1000.0) + 100.0) * 1.0e6
    sea = (150.0 * torch.exp(-0.35 * z_sum / 1000.0) + 10.0) * 1.0e6
    return torch.where(is_land[:, None], land, sea)


# ─── netCDF 배관 ──────────────────────────────────────────────────────────────


class FrameData(NamedTuple):
    state: State          # (B, K) fp64 × 12
    forcing: Forcing      # (B, K) fp64 × 4
    xland: torch.Tensor   # (B,) fp64 — WRF 관례 1=land, 2=water
    meta: dict            # nx, ny, kme, time_idx, path, b = j*nx + i, nccn_fallback


def _flat(var, time_idx: int) -> torch.Tensor:
    """(Time, K[, +1], ny, nx) → (B, K[.+1]) fp64;  (Time, ny, nx) → (B,) fp64."""
    a = torch.from_numpy(var[time_idx, ...].astype("float64"))
    if a.dim() == 3:                      # (K, ny, nx) → (B, K)
        return a.permute(1, 2, 0).reshape(-1, a.shape[0])
    return a.reshape(-1)                  # (ny, nx) → (B,)


def read_wrfout_frame(path: str, time_idx: int = 0) -> FrameData:
    """wrfout 프레임 하나를 State/Forcing으로 읽는다 (파생은 위 순수 함수 위임)."""
    import netCDF4

    ds = netCDF4.Dataset(path)
    try:
        if int(getattr(ds, "USE_THETA_M", 1)) != 1:
            # use_theta_m=0이면 wrfout T가 곧 dry θ−T0 (phy_prep F:113) — 이 리더는
            # =1 경로(THM 파생)만 검증됐으므로 명시적으로 거부한다 (silent-wrong 방지).
            raise ValueError("read_wrfout_frame: USE_THETA_M != 1 is not supported yet")

        qv = _flat(ds.variables["QVAPOR"], time_idx)
        thm_pert = _flat(ds.variables["THM"], time_idx)
        p, pii = derive_p_pii(_flat(ds.variables["P"], time_idx),
                              _flat(ds.variables["PB"], time_idx))
        rho = derive_rho(p, thm_pert, pii, qv)
        delz = derive_delz(_flat(ds.variables["PH"], time_idx),
                           _flat(ds.variables["PHB"], time_idx))
        xland = _flat(ds.variables["XLAND"], time_idx)

        nccn = _flat(ds.variables["QNCCN"], time_idx)
        nccn_fallback = bool((nccn == 0).all())
        if nccn_fallback:
            # 첫 히스토리 프레임이 물리 1스텝 이전에 쓰였을 때 QNCCN은 전부 0 —
            # wrapper의 ITIMESTEP==1 초기화를 미러해 채운다.
            nccn = nccn_init_profile(delz, xland == 1.0)

        state = State(
            th=derive_th(thm_pert, qv),
            qv=qv,
            qc=_flat(ds.variables["QCLOUD"], time_idx),
            qr=_flat(ds.variables["QRAIN"], time_idx),
            qi=_flat(ds.variables["QICE"], time_idx),
            qs=_flat(ds.variables["QSNOW"], time_idx),
            qg=_flat(ds.variables["QGRAUP"], time_idx),
            nccn=nccn,
            nc=_flat(ds.variables["QNCLOUD"], time_idx),
            ni=_flat(ds.variables["QNICE"], time_idx),
            nr=_flat(ds.variables["QNRAIN"], time_idx),
            bg=_flat(ds.variables["QIB"], time_idx),
        )
        forcing = Forcing(rho=rho, pii=pii, p=p, delz=delz)
        meta = dict(
            path=str(path), time_idx=time_idx,
            nx=ds.dimensions["west_east"].size,
            ny=ds.dimensions["south_north"].size,
            kme=ds.dimensions["bottom_top"].size,
            column_order="b = j*nx + i (C-order flatten of (south_north, west_east))",
            nccn_fallback=nccn_fallback,
        )
        # 실사례 격자면 컬럼 위경도를 meta에 노출 — collocation(obs_ingest)용.
        # (B,) flatten은 state와 동일한 b = j*nx + i C-order.
        if "XLAT" in ds.variables and "XLONG" in ds.variables:
            meta["lat"] = torch.tensor(
                np.asarray(ds.variables["XLAT"][time_idx], dtype=np.float64).reshape(-1))
            meta["lon"] = torch.tensor(
                np.asarray(ds.variables["XLONG"][time_idx], dtype=np.float64).reshape(-1))
        return FrameData(state=state, forcing=forcing, xland=xland, meta=meta)
    finally:
        ds.close()
