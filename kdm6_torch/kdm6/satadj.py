"""
KDM6 saturation adjustment — Step B5.

원본: module_mp_kdm6.F: 2927-2943

Microphysics 끝에서 qv ↔ qc 1-step Clausius-Clapeyron 보정. latent heat
feedback (`xl²/(rv·cpm)·qs/t²` 항)으로 응결/증발이 t/q를 동시에 변경하는 effect를
1차 근사한다.

Algorithm (Fortran 직역):
    work1 = (max(q, qmin) - qs) / (1 + xl²/(rv·cpm) · qs/t²)
    if work1 > 0:        # supersaturation
        pcond = min(work1/dtcld, q/dtcld)        # cap by available qv
    elif qc > 0 and work1 < 0:   # subsaturation with available qc
        pcond = max(work1, -qc) / dtcld          # cap by available qc
    else:
        pcond = 0

Notes
-----
- nccond (cloud number transfer to CCN at complete evap)는 `state mutation`이므로
  rain_evap와 동일하게 caller가 처리. oracle은 pcond rate만 산출.
- saturation vapor pressure (qs1 자체) 계산은 별도 sub-step 또는 외부 진단.
  본 함수는 qs1을 placeholder input으로 받음.
- `conden`의 분모 `1 + xl²·qs/(rv·cpm·t²)`는 항상 > 1이라 division-by-zero 위험 없음.
"""
from __future__ import annotations

from typing import NamedTuple

import torch

from . import constants as c


# ─── physical constants (default values, kdm6init INPUT) ─────────────────────

DEFAULT_RV = 461.6  # J/kg/K, Fortran r_v (module_model_constants.F:22)


class SatAdjParams(NamedTuple):
    """saturation adjustment에 필요한 thermodynamic constant."""

    rv: float
    qmin: float


def default_satadj_params(*, rv: float = DEFAULT_RV) -> SatAdjParams:
    return SatAdjParams(rv=rv, qmin=c.EPS)  # Fortran qmin=epsilon=1e-15; q_eff=max(q,qmin) floor (F:2927). 1:1 fix #1 (satadj path).


def saturation_adjustment_torch(
    t: torch.Tensor,
    q: torch.Tensor,
    qc: torch.Tensor,
    qs1: torch.Tensor,    # saturation mixing ratio w.r.t. water (외부 진단)
    xl: torch.Tensor,     # latent heat of vaporization [J/kg] (외부 진단)
    cpm: torch.Tensor,    # moist heat capacity [J/kg/K] (외부 진단)
    *,
    params: SatAdjParams,
    dtcld: float,
) -> torch.Tensor:
    """Fortran 2927-2931 — saturation adjustment rate.

    Returns
    -------
    pcond : (B, K) tensor [kg/kg/s]. > 0이면 응결 (qv→qc), < 0이면 증발 (qc→qv).
    """
    qmin_t = torch.tensor(params.qmin, dtype=q.dtype, device=q.device)

    # work1 = (max(q, qmin) - qs1) / (1 + xl²·qs1/(rv·cpm·t²))   — Clausius-Clapeyron
    # 분모는 항상 > 1 (양수 보장). 단, t² 자체는 분모이므로 0 회피 위해 clamp.
    t_safe = torch.clamp(t, min=1.0)  # T > 1 K 가정 (대기 환경 100~400 K)
    # Fortran conden stmt-fn (module_mp_kdm6.F:781): denom = 1.+ d*d/(rv*e)*c/(a*a),
    # equal-precedence left-assoc => ((((xl*xl)/(rv*cpm))*qs1)/(t*t)). gfortran does
    # not reassociate division, so mirror that grouping (NOT (xl²·qs1)/(rv·cpm·t²))
    # to stay 1:1 with F:781 and with the C++ port (satadj.cpp:27).
    denom = 1.0 + xl * xl / (params.rv * cpm) * qs1 / (t_safe * t_safe)
    q_eff = torch.maximum(q, qmin_t)
    work1 = (q_eff - qs1) / denom

    # Branch on sign:
    #   work1 > 0  → super-saturated, condensation: pcond = min(work1/dtcld, q/dtcld)
    #   work1 < 0 AND qc > 0 → sub-saturated with available cloud: pcond = max(work1, -qc)/dtcld
    #   otherwise  → 0
    cond_path = torch.minimum(work1, torch.maximum(q, torch.zeros_like(q))) / dtcld
    evap_path = torch.maximum(work1, -qc) / dtcld

    is_super = work1 > 0
    is_sub_with_cloud = (work1 < 0) & (qc > 0)

    zero = torch.zeros_like(q)
    pcond = torch.where(
        is_super, cond_path,
        torch.where(is_sub_with_cloud, evap_path, zero)
    )
    return pcond


__all__ = [
    "SatAdjParams",
    "default_satadj_params",
    "saturation_adjustment_torch",
]
