"""P2 — model column → RTTOV-unit torch tensors (설계 §5, §14.3-units; 검증 M2).

★ 전 경로 **순수 torch·leaves로부터 미분가능**이어야 한다(grad 전파 계약, §14.3). 한 단계라도
numpy면 leaves→RttovObsOp 경로가 끊긴다.

stage (model_to_rttov_tensors):
  gas/T : extract(T=th·pii, qv) → qv→Q ppmv-moist(torch, ∂Q/∂qv 해석식) → log-pressure 보간
          (상수 torch 행렬 W). RTTOV-14 AMI는 layer-based(profile.py): T/Q/content는 **layers**,
          PHalf는 **levels**, Nlayers=Nlevels−1. grid count는 **hard-code 금지 — fixture/coef에서
          derive**(rttov_profile_pressure_grid). ami/501 fixture=nlayers 69/nlevels 70(p.txt 69줄,
          p_half.txt 70줄)이나 입력마다 다름(GFS=nlevels 70). **coef predictor 54L은 별개**(RTTOV
          내부 보간 grid — user profile 아님).
  cloud : rttov_cloud_profile(bridge §6)가 이미 g/m³·µm emit → 그대로 + reff→Deff ×2
          (content 재변환 금지 — bridge가 단위 source of truth)

reference 공식/상수: `_rttov_reference/humidity_unit_conversion.py`(∂Q/∂qv),
`_rttov_reference/rttov_profile_pressure_grid.py`(W). scalar이므로 직접 호출 금지 — torch 재구현.

STUB — 미구현.
"""
from __future__ import annotations


def model_to_rttov_tensors(leaves, forcing, cfg, xland=None,
                           ncmin_land=0.0, ncmin_sea=0.0):
    """leaves(State, requires_grad) → RTTOV 단위/grid torch 텐서 tuple.

    반환 순서 = RttovObsOp.apply 입력 순서(§14.3): T_lay, Q_lay, clw, ciw, rain, snow,
    graupel, deff_liq, deff_ice, skin, t2m, q2m, … (모두 RTTOV unit, layer/level grid).
    GasUnits=2(ppmv_wet), MmrHydro=False(g/m³), reff→Deff ×2 (§14.5).
    """
    raise NotImplementedError("P2 profile builder — 설계 §5/§14.3-units, M2")
