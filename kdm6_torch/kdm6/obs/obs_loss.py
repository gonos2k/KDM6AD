"""P? — 관측공간 loss (설계 §8; 수학 kdm6ad+da.md §4/§9.1).

`compute_obs_loss`는 **torch scalar J_obs**를 반환한다(BT_hat에 미분가능). λ_BT = ∂J_obs/∂BT_hat은
loss의 출력이 아니라 callback의 autograd가 만드는 cotangent다(§8 정정; runK는 seed 안 받음).
관측·RTTOV 양쪽 quality==0 (profile, channel)만 metric/grad에 포함; bias correction은 residual 시점.

solar(VIS/NIR 6채널)은 btrefl가 reflectance라 BT-residual 미정의 — IR 10채널 1차, solar 후속(§1.6).

STUB — 미구현.
"""
from __future__ import annotations


def compute_obs_loss(bt_hat, obs, masks, sigma):
    """BT residual + Huber ψ_δ + (cloud/phase) loss → **torch scalar J_obs**.
    (λ_BT는 반환하지 않는다 — autograd cotangent. §8.)"""
    raise NotImplementedError("obs loss — 설계 §8, kdm6ad+da.md §4/§9.1")
