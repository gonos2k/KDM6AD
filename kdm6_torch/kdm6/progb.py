"""
KDM6 ProgB_param oracle — graupel volume + density-dependent DSD parameters.

원본:
  - module_mp_kdm6.F: 3332-3425 (`SUBROUTINE ProgB_param`)
  - module_mp_kdm6.F: 3090-3099 (`kdm6init` 의 hail_opt-의존 graupel 상수)

역할:
  graupel mass `qg`(=qrs(:,:,3))와 volume mixing ratio `bg`(=brs)로부터 graupel
  density `rhox`를 진단하고, 9-point lookup table에서 `avtg, bvtg`를 보간해
  DSD-derived 14개 scalar/tensor 출력을 산출한다. Park-Lim 2024 (WDM6-graupel)에서
  도입된 prognostic graupel volume 대응.

7-Step 분해의 Step A (procedures/kdm62d-port-decomposition.md). 후행 단계 B-E의
saturation/warm/ice/sed가 이 모듈의 출력을 입력으로 받는다.

AD 가이드 (procedures/kdm62d-port-decomposition.md):
  - 외부 게이트 `qg <= qcrmin AND bg <= 1e-15` → 모든 출력 0 (branch zero)
  - rhox 클램프 [100, 900] (subgradient = 0 at boundary, OK)
  - 9-point table interp → `torch.searchsorted` + linear (piecewise-linear, C^0)
  - `rgmma(x) = Γ(x)` → `torch.exp(torch.lgamma(x))` per-cell tensor (review6 audit fix)
"""
from __future__ import annotations

from math import exp, lgamma, pi as _pi
from typing import NamedTuple

import torch

from . import constants as c
from . import fconst as _fc
from .ops import EPS

# ─── ProgB_param 헤더 상수 (Fortran header parameters) ─────────────────────────

RHO_MIN = 100.0       # kg m⁻³, graupel density floor
RHO_MAX = 900.0       # kg m⁻³, graupel density ceiling
RHO_MID = 400.0       # kg m⁻³, default graupel density (Park-Lim 2024)
BRS_MIN = 1.0e-15     # m³ kg⁻¹, min. allowable bulk volume mixing ratio

# 9-point graupel density → terminal-velocity coefficient lookup
DENSITY_TABLE: tuple[float, ...] = (
    100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0, 900.0,
)
AVTG_TABLE: tuple[float, ...] = (
    54.9153, 74.2262, 88.8313, 101.0411, 111.7359, 121.3625, 130.1841, 138.3714, 146.0422,
)
BVTG_TABLE: tuple[float, ...] = (
    0.5446, 0.5375, 0.5339, 0.5316, 0.5299, 0.5286, 0.5275, 0.5266, 0.5258,
)

# kdm6init: hail_opt=0 (graupel) 기본값. constants.py에서 직접 import.
N0G = c.N0G
LAMDAGMAX = c.LAMDAGMAX


# ─── Public types ─────────────────────────────────────────────────────────────


class ProgBParams(NamedTuple):
    """`kdm6init`에서 정해지는 graupel-side 시간/공간 불변 스칼라."""

    qcrmin: float
    dmg: float
    mug: float
    n0g: float
    g1pdgmg: float    # rgmma(1 + dmg + mug)
    g1pmg: float      # rgmma(1 + mug)   — mug==0이면 1.0
    rslopegmax: float # 1 / lamdagmax


class ProgBOutputs(NamedTuple):
    rhox: torch.Tensor            # graupel density [kg m⁻³]
    bg: torch.Tensor              # updated volume mixing ratio (consistency)
    cmg: torch.Tensor             # pi * rhox / 6
    pidn0g: torch.Tensor
    avtg: torch.Tensor
    bvtg: torch.Tensor
    bvtg1: torch.Tensor           # 1 + bvtg
    bvtg2: torch.Tensor           # 2.5 + 0.5*bvtg + mug
    bvtg3: torch.Tensor           # 3 + bvtg + mug
    bvtg4: torch.Tensor           # 4 + bvtg
    g1pbg: torch.Tensor           # rgmma(bvtg1)
    g3pbg: torch.Tensor           # rgmma(bvtg3)
    g4pbg: torch.Tensor           # rgmma(bvtg4)
    g5pbgo2: torch.Tensor         # rgmma(bvtg2)
    g1pdgbgmg: torch.Tensor       # rgmma(dgbgmug1)
    dgbgmug1: torch.Tensor        # 1 + dmg + bvtg + mug
    rslopegbmax: torch.Tensor     # rslopegmax ** bvtg
    pvtg: torch.Tensor
    precg2: torch.Tensor


# ─── helpers ──────────────────────────────────────────────────────────────────


def _rgmma_scalar(x: float) -> float:
    """Fortran `rgmma(x) = exp(GAMMLN(x)) = Γ(x)` 직역. review6 audit에서 부호 수정
    (이전 구현은 1/Γ였음)."""
    # Fortran rgmma = f32 expf(f32 gammln) — differs from exp(lgamma) at non-integer args (step-67 class)
    return _fc.rgmma_f(x)


class _RgmmaF32(torch.autograd.Function):
    """Elementwise Fortran rgmma on float32 — mirrors C++ ops::rgmma_t.

    forward: fconst.rgmma_f per cell (f32 expf of the f32-rounded double-Lanczos
    GAMMLN; torch.lgamma f32 differs at non-integer args). backward: the exact
    derivative Gamma(x)*digamma(x) on the saved tensors.
    """

    @staticmethod
    def forward(ctx, x: torch.Tensor) -> torch.Tensor:
        import numpy as np
        xc = x.detach().contiguous()
        flat = xc.view(-1).numpy()
        out = np.fromiter((_fc.rgmma_f(float(v)) for v in flat),
                          dtype=np.float32, count=flat.size).reshape(tuple(xc.shape))
        out_t = torch.from_numpy(out).to(x.device)
        ctx.save_for_backward(x, out_t)
        return out_t

    @staticmethod
    def backward(ctx, go: torch.Tensor) -> torch.Tensor:
        x, out = ctx.saved_tensors
        return go * out * torch.digamma(x)


def _rgmma_tensor(x: torch.Tensor) -> torch.Tensor:
    """Per-cell rgmma = Γ(x) — dtype-dispatched like C++ ops::rgmma_t:
    f32 → Fortran GAMMLN mirror (elementwise fconst.rgmma_f); f64 (oracle) →
    exp(lgamma), which the C++ f64 path matches exactly."""
    if x.dtype == torch.float32:
        return _RgmmaF32.apply(x)
    return torch.exp(torch.lgamma(x))


def _scalar(value: float, ref: torch.Tensor) -> torch.Tensor:
    return torch.as_tensor(value, dtype=ref.dtype, device=ref.device)


def default_progb_params() -> ProgBParams:
    """`kdm6init`이 ProgB_param에 넘기는 graupel-side 파생 상수 묶음.

    Derivations
    -----------
    - `g1pmg = 1` if `mug==0` else `rgmma(1+mug)` (Fortran kdm6init:3166-3170)
    - `g1pdgmg = rgmma(1 + dmg + mug)`
    - `rslopegmax = 1 / lamdagmax`
    """
    g1pdgmg = _rgmma_scalar(1.0 + c.DMG + c.MUG)
    g1pmg = 1.0 if c.MUG == 0.0 else _rgmma_scalar(1.0 + c.MUG)
    rslopegmax = 1.0 / LAMDAGMAX

    return ProgBParams(
        qcrmin=c.QCRMIN,
        dmg=c.DMG,
        mug=c.MUG,
        n0g=N0G,
        g1pdgmg=g1pdgmg,
        g1pmg=g1pmg,
        rslopegmax=rslopegmax,
    )


# ─── core kernel ──────────────────────────────────────────────────────────────


def progb_param_torch(
    qg: torch.Tensor,
    bg: torch.Tensor,
    *,
    params: ProgBParams,
) -> ProgBOutputs:
    """ProgB_param Fortran 직역 — graupel density + DSD parameter diagnosis.

    Parameters
    ----------
    qg : (B, K) tensor
        graupel mass mixing ratio [kg/kg]. Fortran의 `qrs(i,k,3)`.
    bg : (B, K) tensor
        graupel bulk volume mixing ratio [m³/kg]. Fortran의 `brs(i,k)`.
    params : ProgBParams
        시간 불변 스칼라 묶음 — `default_progb_params()`로 생성.

    Returns
    -------
    ProgBOutputs
        14개 텐서/스칼라 패키지. 모든 텐서는 `qg`/`bg` 입력 그래프와 연결.
    """
    if qg.shape != bg.shape:
        raise ValueError(f"qg shape {qg.shape} != bg shape {bg.shape}")

    dtype = qg.dtype
    device = qg.device
    Tbl = torch.tensor(DENSITY_TABLE, dtype=dtype, device=device)
    aTbl = torch.tensor(AVTG_TABLE, dtype=dtype, device=device)
    bTbl = torch.tensor(BVTG_TABLE, dtype=dtype, device=device)

    # ── 외부 게이트: graupel가 의미있게 존재하는가 ───────────────────────────
    # Fortran: if (qrs(i,k,3) > qcrmin .or. brs(i,k) > brs_min) ...
    active = (qg > params.qcrmin) | (bg > BRS_MIN)
    zero = torch.zeros_like(qg)

    # ── rhox 진단 + clamp ─────────────────────────────────────────────────
    # Fortran: rhox = qg / max(bg, brs_min);  rhox = clamp(rhox, [100, 900])
    bg_safe = torch.clamp(bg, min=BRS_MIN)
    rhox_raw = qg / bg_safe
    rhox = torch.clamp(rhox_raw, min=RHO_MIN, max=RHO_MAX)
    # inactive cell은 RHO_MID로 채워 cmg=π·400/6 같은 spurious 계산 방지 후 zero gate.
    rhox = torch.where(active, rhox, _scalar(RHO_MID, qg))

    # bg 갱신 (consistency): bg = qg / rhox (active일 때만, 아니면 입력 보존)
    bg_new = torch.where(active, qg / rhox, bg)

    # ── cmg, pidn0g ──────────────────────────────────────────────────────
    # Fortran: cmg = pi * rhox / 6;  pidn0g = cmg * n0g * g1pdgmg / g1pmg
    cmg_raw = _pi * rhox / 6.0
    cmg = torch.where(active, cmg_raw, zero)
    pidn0g = cmg * params.n0g * params.g1pdgmg / params.g1pmg

    # ── 9-point linear interpolation: rhox → (avtg, bvtg) ────────────────
    # rhox는 이미 [100, 900]에 clamp됨. searchsorted+linear interp으로 매끄럽게.
    # right=True: Tbl[i-1] <= rhox < Tbl[i]; 단, rhox==RHO_MAX인 경우 idx_right==9가
    # 되어 out-of-bounds. 그러므로 idx_right를 [1, 8]로 clamp.
    idx_right = torch.searchsorted(Tbl, rhox.contiguous(), right=True)
    idx_right = idx_right.clamp(min=1, max=Tbl.numel() - 1)  # ∈ [1, 8]
    idx_left = idx_right - 1                                  # ∈ [0, 7]

    Tbl_left = Tbl[idx_left]
    Tbl_right = Tbl[idx_right]
    aTbl_left = aTbl[idx_left]
    aTbl_right = aTbl[idx_right]
    bTbl_left = bTbl[idx_left]
    bTbl_right = bTbl[idx_right]

    # Fortran F:3385-3387: tmp2 = 1./(Tbl(sy+1)-Tbl(sy)) — ONE rounded
    # reciprocal reused for avtg AND bvtg — then
    #   aTbl(sy) + ((rhox-Tbl(sy))*(aTbl(sy+1)-aTbl(sy)))*tmp2
    # every op individually rounded left-to-right (-ffp-contract=off). A direct
    # (rhox-Tbl_left)/width division is NOT bit-equal (fl(1/100) is inexact;
    # IEEE sweep finding — mirrors the C++ progb.cpp fix).
    width = Tbl_right - Tbl_left            # = 100 (always)
    tmp2 = 1.0 / width
    d1 = rhox - Tbl_left
    avtg_raw = aTbl_left + (d1 * (aTbl_right - aTbl_left)) * tmp2
    bvtg_raw = bTbl_left + (d1 * (bTbl_right - bTbl_left)) * tmp2
    # Exact-endpoint branch (Fortran F:3404 `else if (rhox==Tbl(9))`), mirrored
    # by construction rather than relying on lerp round-trip coincidence.
    avtg_raw = torch.where(rhox == Tbl[-1], aTbl[-1], avtg_raw)
    bvtg_raw = torch.where(rhox == Tbl[-1], bTbl[-1], bvtg_raw)

    avtg = torch.where(active, avtg_raw, zero)
    bvtg = torch.where(active, bvtg_raw, zero)

    # ── derived sums (active 여부와 무관하게 산식 그대로; bvtg=0 → safe) ───
    bvtg1 = 1.0 + bvtg
    bvtg2 = 2.5 + 0.5 * bvtg + params.mug
    bvtg3 = 3.0 + bvtg + params.mug
    bvtg4 = 4.0 + bvtg
    dgbgmug1 = 1.0 + params.dmg + bvtg + params.mug

    # rgmma family — bvtg* > 0 보장됨 (active=True에선 bvtg1≥1, ...; active=False에선
    # bvtg=0 → bvtg1=1, bvtg2=2.5+mug>0, ...). 안전상 EPS clamp.
    g1pbg = _rgmma_tensor(torch.clamp(bvtg1, min=EPS))
    g3pbg = _rgmma_tensor(torch.clamp(bvtg3, min=EPS))
    g4pbg = _rgmma_tensor(torch.clamp(bvtg4, min=EPS))
    g5pbgo2 = _rgmma_tensor(torch.clamp(bvtg2, min=EPS))
    g1pdgbgmg = _rgmma_tensor(torch.clamp(dgbgmug1, min=EPS))

    # ── rslopegbmax = rslopegmax ** bvtg (per-cell, since bvtg is a tensor) ─
    rslopegmax_t = _scalar(params.rslopegmax, qg)
    rslopegbmax_raw = rslopegmax_t.expand_as(bvtg).pow(bvtg)
    rslopegbmax = torch.where(active, rslopegbmax_raw, zero)

    # ── pvtg, precg2 ─────────────────────────────────────────────────────
    pvtg_raw = avtg * g1pdgbgmg / params.g1pdgmg
    pvtg = torch.where(active, pvtg_raw, zero)

    # precg2 = 4 * 0.31 * sqrt(avtg) * g5pbgo2; sqrt(0)의 backward는 inf →
    # 미분 보호: avtg를 EPS clamp 후 sqrt, 그리고 mask zero로 마무리.
    precg2_raw = 4.0 * 0.31 * torch.sqrt(torch.clamp(avtg, min=EPS)) * g5pbgo2
    precg2 = torch.where(active, precg2_raw, zero)

    # 비활성 셀의 derived 출력은 zero로 mask (downstream graupel mask와 일관)
    g1pbg = torch.where(active, g1pbg, zero)
    g3pbg = torch.where(active, g3pbg, zero)
    g4pbg = torch.where(active, g4pbg, zero)
    g5pbgo2 = torch.where(active, g5pbgo2, zero)
    g1pdgbgmg = torch.where(active, g1pdgbgmg, zero)
    bvtg1 = torch.where(active, bvtg1, zero)
    bvtg2 = torch.where(active, bvtg2, zero)
    bvtg3 = torch.where(active, bvtg3, zero)
    bvtg4 = torch.where(active, bvtg4, zero)
    dgbgmug1 = torch.where(active, dgbgmug1, zero)

    return ProgBOutputs(
        rhox=rhox,
        bg=bg_new,
        cmg=cmg,
        pidn0g=pidn0g,
        avtg=avtg,
        bvtg=bvtg,
        bvtg1=bvtg1,
        bvtg2=bvtg2,
        bvtg3=bvtg3,
        bvtg4=bvtg4,
        g1pbg=g1pbg,
        g3pbg=g3pbg,
        g4pbg=g4pbg,
        g5pbgo2=g5pbgo2,
        g1pdgbgmg=g1pdgbgmg,
        dgbgmug1=dgbgmug1,
        rslopegbmax=rslopegbmax,
        pvtg=pvtg,
        precg2=precg2,
    )


__all__ = [
    "ProgBParams",
    "ProgBOutputs",
    "DENSITY_TABLE",
    "AVTG_TABLE",
    "BVTG_TABLE",
    "RHO_MIN",
    "RHO_MAX",
    "RHO_MID",
    "BRS_MIN",
    "default_progb_params",
    "progb_param_torch",
]
