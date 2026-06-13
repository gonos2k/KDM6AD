"""P6 — RttovObsOp custom autograd.Function + obs_adjoint_callback (설계 §9.1/§10/§14.3; 검증 M6).

비-torch RTTOV를 torch 그래프에 넣는 진입점. forward는 단일 runK(BT+K 캐시), backward는
채널 contraction `λ_profile = Σ_c K[c]·λ_BT[c]`를 in-process torch로 수행(runK는 seed 안 받음).
callback은 da_window의 `obs_adjoint(t, x_t)` 계약(detached state → covector 반환)을 구현한다.

STUB — 미구현. 아래는 설계 §14.3의 interface contract.
"""
from __future__ import annotations

import torch

from ..state import State

# obs operator에 RTTOV 입력 경로가 '없어야 정상'인 필드 → 0이 정답(동역학 VJP가 운반).
# nccn: BT 직접 경로 없음. nr/bg: RTTOV-14에 rain/graupel Deff item 없음(§9.1; rttype.py:94-98).
OBS_ZERO_OK = frozenset({"nccn", "nr", "bg"})


class RttovObsOp(torch.autograd.Function):
    """forward: runK 1회 → BT_hat(+ K-matrix를 ctx에 캐시). backward: K^T·λ_BT.

    입력 = 이미 RTTOV-unit인 torch 텐서들(model_to_rttov_tensors 산출, §14.3). forward는
    단위변환 안 함. K accessor(numpy)는 backward에서 torch로 올려 einsum(numpy×torch 혼합 금지).
    비-텐서(rin, config_hash, K)는 ctx.<attr>로 저장(save_for_backward 아님). backward는 forward
    입력 순서대로 grad 반환(RTTOV 무경로 입력은 None).
    """

    @staticmethod
    def forward(ctx, *rttov_tensors):  # noqa: D401
        raise NotImplementedError("P6 RttovObsOp.forward — 설계 §14.3, M5/M6")

    @staticmethod
    def backward(ctx, lambda_bt):
        raise NotImplementedError("P6 RttovObsOp.backward (K^T·λ_BT) — 설계 §9.1/§14.3")


def assemble_obs_covector(leaves: State, grads) -> State:
    """grad(None 허용) → 12-field State covector. 무경로 필드(OBS_ZERO_OK)는 0,
    그 외 None은 **구조적 단절(numpy break) → loud raise**(silent-zero 금지, §14.3).
    user-Deff-off는 여기서 못 잡음(connected-zero) → M5 getHydroDeffNK 비영 probe."""
    out = []
    for name, g in zip(State._fields, grads):
        if g is None:
            if name in OBS_ZERO_OK:
                g = torch.zeros_like(getattr(leaves, name))
            else:
                raise RuntimeError(
                    f"obs adjoint 구조적 단절: λ_{name}=None — model_to_rttov_tensors가 "
                    f"전부 torch여야 함(§14.3). silent-zero 금지.")
        out.append(g.detach())
    return State(*out)


def obs_adjoint_callback(t, x_t, *, schedule, forcing, cfg,
                         xland=None, ncmin_land=0.0, ncmin_sea=0.0):
    """da_window obs_adjoint(t, x_t) 구현 — detached x_t → covector ∂J_obs/∂x_t (또는 None).

    LOCAL autograd.grad로 닫는다(window backward·Handle.vjp 통과 안 함, §10/§14.3):
        leaves = fresh_requires_grad_leaves(x_t)
        rttov_tensors = model_to_rttov_tensors(leaves, forcing, cfg, xland, ncmin_*)  # 순수 torch
        BT_hat = RttovObsOp.apply(*rttov_tensors)
        J      = compute_obs_loss(BT_hat, obs, masks, sigma)                          # scalar
        grads  = torch.autograd.grad(J, tuple(leaves), allow_unused=True)             # materialize 금지
        return assemble_obs_covector(leaves, grads)
    """
    raise NotImplementedError("P6 obs_adjoint_callback — 설계 §10/§14.3, M6")
