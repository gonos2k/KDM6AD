"""
KDM6 NISLFV-PLM sedimentation oracle — Step E.

원본: module_mp_kdm6.F (sedimentation은 여러 영역에 분산):
  E1 (1130-1141): work1/workn / delz 정규화
  E2 (1148-1205): single-substep advection (qr/nr/qs/qg/brs)
  E3 (1218-1234): ProgB + slope 재호출 (coordinator 영역)
  E4 (1240-?):    ice substep (qi/ni)
  E5:             surface accumulation (rain/snow/graupel ground rate)

Sedimentation은 *grid-coupled + sub-stepping* 알고리즘이라 oracle 단위가 한 cell이
아니라 *(B, K) column*. mstep(substep 횟수)는 정수 연산이라 oracle 외부에서 결정,
한 substep을 미분 가능 함수로 작성한다.

AD 가이드:
  - vertical chain (k = kte-1 → kts)은 *sequential* 명시 loop
  - mstep는 caller가 결정 (정수)
  - max(qx - dqx_below + dqx_above, 0) 패턴: clamp(min=0) (subgrad 0 OK)
"""
from __future__ import annotations

from typing import NamedTuple

import torch

from . import constants as c


# ─── Step E1: work1/workn / delz 정규화 ──────────────────────────────────────


def normalize_work_by_delz_torch(
    work: torch.Tensor,
    delz: torch.Tensor,
) -> torch.Tensor:
    """Fortran 1130-1135, 1229-1234 — work / delz.

    work: (B, K) — slope module 출력 또는 ProgB derived velocity.
    delz: (B, K) — layer thickness [m].
    Returns: work / delz [1/s].
    """
    return work / torch.clamp(delz, min=c.QCRMIN)


# ─── Step E2: One-substep advection (rain/snow/graupel + brs + nrs) ──────────


class SubstepAdvectionParams(NamedTuple):
    """E2 시간불변 스칼라."""
    qcrmin: float


def default_substep_advection_params() -> SubstepAdvectionParams:
    return SubstepAdvectionParams(qcrmin=c.QCRMIN)


class SubstepAdvectionState(NamedTuple):
    """E2 입력/출력 state (mutable through substep)."""
    qr: torch.Tensor      # (B, K)
    nr: torch.Tensor
    qs: torch.Tensor
    qg: torch.Tensor
    brs: torch.Tensor


class SubstepAdvectionOutputs(NamedTuple):
    state: SubstepAdvectionState   # 갱신된 state
    fall_qr: torch.Tensor          # 누적 fall rate [kg/m²/s], 표면 누적용
    fall_nr: torch.Tensor
    fall_qs: torch.Tensor
    fall_qg: torch.Tensor
    fall_brs: torch.Tensor


def substep_advection_torch(
    state: SubstepAdvectionState,
    fall_qr_in: torch.Tensor,      # 누적 fall rate (이전 substep까지)
    fall_nr_in: torch.Tensor,
    fall_qs_in: torch.Tensor,
    fall_qg_in: torch.Tensor,
    fall_brs_in: torch.Tensor,
    work1_qr: torch.Tensor,        # work1(:,:,1)/delz (E1 output)
    workn_qr: torch.Tensor,
    work1_qs: torch.Tensor,        # work1(:,:,2)/delz
    work1_qg: torch.Tensor,        # work1(:,:,3)/delz (also for brs)
    delz: torch.Tensor,
    dend: torch.Tensor,            # density × delz product (ProgB output)
    *,
    mstep: int = 1,                # legacy global divisor (used iff mstep_col is None)
    mstep_col: torch.Tensor | None = None,  # (B,) per-column int-valued divisor + gate
    n_current: int = 1,            # current substep index (1-indexed) for per-column gate
    dtcld: float,
    params: SubstepAdvectionParams,
) -> SubstepAdvectionOutputs:
    """Fortran 1148-1205 — one substep of NISLFV-PLM advection.

    Algorithm:
      Top cell (k = kte): falk = dend·qx·work1/mstep, qx -= falk·dtcld/dend
      Interior (k = kte-1 → kts):
          falk[k] = dend[k]·qx[k]·work1[k]/mstep
          dqx[k]      = min(falk[k]·dtcld/dend[k], qx[k])
          dqx_above   = min(falk[k+1]·delz[k+1]/delz[k]·dtcld/dend[k], qx[k+1])
          qx[k] = max(qx[k] - dqx[k] + dqx_above, 0)

    Conventions:
      Tensors shape (B, K) where K=0 corresponds to *top* (kte) and K=K-1 to *bottom* (kts).
      Fortran의 `for k = kte → kts`는 PyTorch에서 `for k_idx = 0 → K-1`.
    """
    K = state.qr.shape[-1]
    dend_safe = torch.clamp(dend, min=params.qcrmin)
    delz_safe = torch.clamp(delz, min=params.qcrmin)
    # falk_scale broadcasts against (B,) per-level slices x[:, k].
    # Per-column path: divisor 1/mstep(i) * gate (n<=mstep(i)) -> (B,) (mirrors C++).
    # Legacy scalar path: 1/mstep, gate always 1.
    if mstep_col is not None:
        mstep_col_safe = torch.clamp(mstep_col.to(dend.dtype), min=1.0)
        gate = (mstep_col_safe >= float(n_current)).to(dend.dtype)
        falk_scale = gate / mstep_col_safe
    else:
        falk_scale = 1.0 / float(mstep)

    # AD-friendly: build new column lists instead of in-place indexed assignment.
    # k_idx 0 = top (kte), k_idx K-1 = bottom (kts).
    qr_cols = [state.qr[:, k] for k in range(K)]
    nr_cols = [state.nr[:, k] for k in range(K)]
    qs_cols = [state.qs[:, k] for k in range(K)]
    qg_cols = [state.qg[:, k] for k in range(K)]
    brs_cols = [state.brs[:, k] for k in range(K)]
    fall_qr_cols = [fall_qr_in[:, k] for k in range(K)]
    fall_nr_cols = [fall_nr_in[:, k] for k in range(K)]
    fall_qs_cols = [fall_qs_in[:, k] for k in range(K)]
    fall_qg_cols = [fall_qg_in[:, k] for k in range(K)]
    fall_brs_cols = [fall_brs_in[:, k] for k in range(K)]

    # ── Top cell (k=0) ─────────────────────────────────────────────────
    falk_qr_top = dend[:, 0] * qr_cols[0] * work1_qr[:, 0] * falk_scale
    falk_nr_top = nr_cols[0] * workn_qr[:, 0] * falk_scale
    falk_qs_top = dend[:, 0] * qs_cols[0] * work1_qs[:, 0] * falk_scale
    falk_qg_top = dend[:, 0] * qg_cols[0] * work1_qg[:, 0] * falk_scale
    falk_brs_top = dend[:, 0] * brs_cols[0] * work1_qg[:, 0] * falk_scale

    fall_qr_cols[0] = fall_qr_cols[0] + falk_qr_top
    fall_nr_cols[0] = fall_nr_cols[0] + falk_nr_top
    fall_qs_cols[0] = fall_qs_cols[0] + falk_qs_top
    fall_qg_cols[0] = fall_qg_cols[0] + falk_qg_top
    fall_brs_cols[0] = fall_brs_cols[0] + falk_brs_top

    qr_cols[0] = torch.clamp(qr_cols[0] - falk_qr_top * dtcld / dend_safe[:, 0], min=0.0)
    nr_cols[0] = torch.clamp(nr_cols[0] - falk_nr_top * dtcld, min=0.0)
    qs_cols[0] = torch.clamp(qs_cols[0] - falk_qs_top * dtcld / dend_safe[:, 0], min=0.0)
    qg_cols[0] = torch.clamp(qg_cols[0] - falk_qg_top * dtcld / dend_safe[:, 0], min=0.0)
    brs_cols[0] = torch.clamp(brs_cols[0] - falk_brs_top * dtcld / dend_safe[:, 0], min=0.0)

    # ── Interior cells ─────────────────────────────────────────────────
    # 1:1 Fortran (module_mp_kdm6.F:1141-1173): falk(k) is computed from each cell's PRE-update
    # qrs(k) (F:1144) and STORED; the inflow from the cell above reuses that STORED falk(k+1)
    # (F:1148-1149/1159-1160/1165-1166/1171-1172), NOT a value recomputed from the already-
    # depleted neighbour. Carry the previous cell's stored falk (from its entry q) in falk_*_prev.
    # (The earlier port recomputed falk_above from the depleted qr_cols[k-1], under-advecting
    # interior mass ~1%/cell and attenuating/severing the fall-speed gradient — audit round-2.)
    falk_qr_prev, falk_nr_prev = falk_qr_top, falk_nr_top
    falk_qs_prev, falk_qg_prev, falk_brs_prev = falk_qs_top, falk_qg_top, falk_brs_top
    for k in range(1, K):
        # falk(k) from qr_cols[k] — still the ENTRY value here (cell k is updated only at the end
        # of this iteration; cells above touch only their own column), = Fortran pre-update qrs(k).
        falk_qr_k = dend[:, k] * qr_cols[k] * work1_qr[:, k] * falk_scale
        falk_nr_k = nr_cols[k] * workn_qr[:, k] * falk_scale
        falk_qs_k = dend[:, k] * qs_cols[k] * work1_qs[:, k] * falk_scale
        falk_qg_k = dend[:, k] * qg_cols[k] * work1_qg[:, k] * falk_scale
        falk_brs_k = dend[:, k] * brs_cols[k] * work1_qg[:, k] * falk_scale

        fall_qr_cols[k] = fall_qr_cols[k] + falk_qr_k
        fall_nr_cols[k] = fall_nr_cols[k] + falk_nr_k
        fall_qs_cols[k] = fall_qs_cols[k] + falk_qs_k
        fall_qg_cols[k] = fall_qg_cols[k] + falk_qg_k
        fall_brs_cols[k] = fall_brs_cols[k] + falk_brs_k

        # dqx_below (this cell's outflow, capped by its entry q)
        dqr_k = torch.minimum(falk_qr_k * dtcld / dend_safe[:, k], qr_cols[k])
        dnr_k = torch.minimum(falk_nr_k * dtcld, nr_cols[k])
        dqs_k = torch.minimum(falk_qs_k * dtcld / dend_safe[:, k], qs_cols[k])
        dqg_k = torch.minimum(falk_qg_k * dtcld / dend_safe[:, k], qg_cols[k])
        dbrs_k = torch.minimum(falk_brs_k * dtcld / dend_safe[:, k], brs_cols[k])

        # dqx_above (inflow from the cell above): STORED falk of the cell above (falk_*_prev,
        # from ITS entry q), capped by the cell-above's POST-update reservoir qr_cols[k-1] —
        # STEP-88 SEED class: Fortran F:1180-1205/F:1264-1269 evaluates
        # falk(k+1)*delz(k+1)/delz(k)*dtcld LEFT-TO-RIGHT in f32 (mirrors C++).
        dqr_above = torch.minimum(
            falk_qr_prev * delz[:, k - 1] / delz_safe[:, k] * dtcld / dend_safe[:, k], qr_cols[k - 1])
        dnr_above = torch.minimum(
            falk_nr_prev * delz[:, k - 1] / delz_safe[:, k] * dtcld, nr_cols[k - 1])
        dqs_above = torch.minimum(
            falk_qs_prev * delz[:, k - 1] / delz_safe[:, k] * dtcld / dend_safe[:, k], qs_cols[k - 1])
        dqg_above = torch.minimum(
            falk_qg_prev * delz[:, k - 1] / delz_safe[:, k] * dtcld / dend_safe[:, k], qg_cols[k - 1])
        dbrs_above = torch.minimum(
            falk_brs_prev * delz[:, k - 1] / delz_safe[:, k] * dtcld / dend_safe[:, k], brs_cols[k - 1])

        qr_cols[k] = torch.clamp(qr_cols[k] - dqr_k + dqr_above, min=0.0)
        nr_cols[k] = torch.clamp(nr_cols[k] - dnr_k + dnr_above, min=0.0)
        qs_cols[k] = torch.clamp(qs_cols[k] - dqs_k + dqs_above, min=0.0)
        qg_cols[k] = torch.clamp(qg_cols[k] - dqg_k + dqg_above, min=0.0)
        brs_cols[k] = torch.clamp(brs_cols[k] - dbrs_k + dbrs_above, min=0.0)

        # carry this cell's STORED falk (from its entry q) as the next cell's "above" inflow flux
        falk_qr_prev, falk_nr_prev = falk_qr_k, falk_nr_k
        falk_qs_prev, falk_qg_prev, falk_brs_prev = falk_qs_k, falk_qg_k, falk_brs_k

    # Stack columns back to (B, K) tensors
    qr = torch.stack(qr_cols, dim=-1)
    nr = torch.stack(nr_cols, dim=-1)
    qs = torch.stack(qs_cols, dim=-1)
    qg = torch.stack(qg_cols, dim=-1)
    brs = torch.stack(brs_cols, dim=-1)
    fall_qr = torch.stack(fall_qr_cols, dim=-1)
    fall_nr = torch.stack(fall_nr_cols, dim=-1)
    fall_qs = torch.stack(fall_qs_cols, dim=-1)
    fall_qg = torch.stack(fall_qg_cols, dim=-1)
    fall_brs = torch.stack(fall_brs_cols, dim=-1)

    return SubstepAdvectionOutputs(
        state=SubstepAdvectionState(qr=qr, nr=nr, qs=qs, qg=qg, brs=brs),
        fall_qr=fall_qr, fall_nr=fall_nr,
        fall_qs=fall_qs, fall_qg=fall_qg, fall_brs=fall_brs,
    )


# ─── Step E4: Ice substep (qi/ni) ────────────────────────────────────────────


class IceSubstepState(NamedTuple):
    qi: torch.Tensor
    ni: torch.Tensor


class IceSubstepOutputs(NamedTuple):
    state: IceSubstepState
    fall_qi: torch.Tensor
    fall_ni: torch.Tensor


def ice_substep_advection_torch(
    state: IceSubstepState,
    fall_qi_in: torch.Tensor,
    fall_ni_in: torch.Tensor,
    work1_qi: torch.Tensor,        # work1(:,:,4)/delz
    workn_qi: torch.Tensor,        # workn(:,:,2)/delz
    delz: torch.Tensor,
    dend: torch.Tensor,
    *,
    mstep: int = 1,                # legacy global divisor (used iff mstep_col is None)
    mstep_col: torch.Tensor | None = None,  # (B,) per-column int-valued divisor + gate
    n_current: int = 1,            # current substep index (1-indexed)
    dtcld: float,
    params: SubstepAdvectionParams,
) -> IceSubstepOutputs:
    """Fortran 1240-1271 — ice (qi/ni) sedimentation substep.

    E2와 동일 패턴이지만 ice species만. list-based chain으로 AD 보존.
    """
    K = state.qi.shape[-1]
    dend_safe = torch.clamp(dend, min=params.qcrmin)
    delz_safe = torch.clamp(delz, min=params.qcrmin)
    if mstep_col is not None:
        mstep_col_safe = torch.clamp(mstep_col.to(dend.dtype), min=1.0)
        gate = (mstep_col_safe >= float(n_current)).to(dend.dtype)
        falk_scale = gate / mstep_col_safe
    else:
        falk_scale = 1.0 / float(mstep)

    qi_cols = [state.qi[:, k] for k in range(K)]
    ni_cols = [state.ni[:, k] for k in range(K)]
    fall_qi_cols = [fall_qi_in[:, k] for k in range(K)]
    fall_ni_cols = [fall_ni_in[:, k] for k in range(K)]

    # Top cell
    falk_qi_top = dend[:, 0] * qi_cols[0] * work1_qi[:, 0] * falk_scale
    falk_ni_top = ni_cols[0] * workn_qi[:, 0] * falk_scale
    fall_qi_cols[0] = fall_qi_cols[0] + falk_qi_top
    fall_ni_cols[0] = fall_ni_cols[0] + falk_ni_top
    qi_cols[0] = torch.clamp(qi_cols[0] - falk_qi_top * dtcld / dend_safe[:, 0], min=0.0)
    ni_cols[0] = torch.clamp(ni_cols[0] - falk_ni_top * dtcld, min=0.0)

    # Interior — STORED-falk inflow, same Fortran fix as substep_advection_torch
    # (module_mp_kdm6.F:1228-1232): inflow uses the cell-above's falk from ITS entry q (carried
    # in falk_*_prev), not a recompute from the depleted neighbour. (audit round-2)
    falk_qi_prev, falk_ni_prev = falk_qi_top, falk_ni_top
    for k in range(1, K):
        falk_qi_k = dend[:, k] * qi_cols[k] * work1_qi[:, k] * falk_scale
        falk_ni_k = ni_cols[k] * workn_qi[:, k] * falk_scale
        fall_qi_cols[k] = fall_qi_cols[k] + falk_qi_k
        fall_ni_cols[k] = fall_ni_cols[k] + falk_ni_k

        dqi_k = torch.minimum(falk_qi_k * dtcld / dend_safe[:, k], qi_cols[k])
        dni_k = torch.minimum(falk_ni_k * dtcld, ni_cols[k])

        # inflow: STORED falk of the cell above (entry q), capped by its POST-update reservoir.
        dqi_above = torch.minimum(
            falk_qi_prev * delz[:, k - 1] / delz_safe[:, k] * dtcld / dend_safe[:, k], qi_cols[k - 1])
        dni_above = torch.minimum(
            falk_ni_prev * delz[:, k - 1] / delz_safe[:, k] * dtcld, ni_cols[k - 1])

        qi_cols[k] = torch.clamp(qi_cols[k] - dqi_k + dqi_above, min=0.0)
        ni_cols[k] = torch.clamp(ni_cols[k] - dni_k + dni_above, min=0.0)

        falk_qi_prev, falk_ni_prev = falk_qi_k, falk_ni_k  # carry stored falk to next cell

    return IceSubstepOutputs(
        state=IceSubstepState(qi=torch.stack(qi_cols, dim=-1),
                              ni=torch.stack(ni_cols, dim=-1)),
        fall_qi=torch.stack(fall_qi_cols, dim=-1),
        fall_ni=torch.stack(fall_ni_cols, dim=-1),
    )


# ─── Step E5: Surface accumulation ───────────────────────────────────────────


class SurfaceAccumOutputs(NamedTuple):
    rain_increment: torch.Tensor       # (B,) [mm] over dtcld
    snow_increment: torch.Tensor       # (B,)
    graupel_increment: torch.Tensor    # (B,)


def surface_accumulation_torch(
    fall_qr_bottom: torch.Tensor,   # (B,) — fall at kts (bottom layer)
    fall_qs_bottom: torch.Tensor,
    fall_qg_bottom: torch.Tensor,
    fall_qi_bottom: torch.Tensor,
    delz_bottom: torch.Tensor,      # (B,) — delz at kts
    *,
    dtcld: float,
) -> SurfaceAccumOutputs:
    """Fortran 1401-1450 — accumulate fall rates at kts to surface mm.

    rainncv increment = (fall_qr + fall_qs + fall_qg + fall_qi)·delz/denr·dtcld·1000 [mm]
    snowncv increment = (fall_qs + fall_qi)·delz/denr·dtcld·1000
    graupelncv increment = fall_qg·delz/denr·dtcld·1000

    Note: denr = 1000 kg/m³ (water density). Final unit: mm.
    """
    fallsum = fall_qr_bottom + fall_qs_bottom + fall_qg_bottom + fall_qi_bottom
    fallsum_qsi = fall_qs_bottom + fall_qi_bottom
    fallsum_qg = fall_qg_bottom

    factor = delz_bottom / c.DENR * dtcld * 1000.0
    rain_increment = torch.clamp(fallsum, min=0.0) * factor
    snow_increment = torch.clamp(fallsum_qsi, min=0.0) * factor
    graupel_increment = torch.clamp(fallsum_qg, min=0.0) * factor
    return SurfaceAccumOutputs(
        rain_increment=rain_increment,
        snow_increment=snow_increment,
        graupel_increment=graupel_increment,
    )


__all__ = [
    "SubstepAdvectionParams",
    "SubstepAdvectionState",
    "SubstepAdvectionOutputs",
    "IceSubstepState",
    "IceSubstepOutputs",
    "SurfaceAccumOutputs",
    "default_substep_advection_params",
    "normalize_work_by_delz_torch",
    "substep_advection_torch",
    "ice_substep_advection_torch",
    "surface_accumulation_torch",
]
