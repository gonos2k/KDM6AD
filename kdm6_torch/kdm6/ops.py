"""
torch-safe operation idioms for KDM6 미분가능화.

선택된 전략 (권고안):
  [D1] safe_div_pos    = num / clamp(denom, min=EPS)   — 양수 분모 전용, EPS 아래 grad 0
  [D1b] safe_div_signed = sign-preserving |denom| floor — 부호 보존, 0 회피
  [D1c] safe_div = safe_div_pos alias                  — 하위호환 유지
  [D2] safe_sqrt   = sqrt(clamp(x, min=EPS))            — boundary subgradient 0
  [D3] safe_pow    = clamp(x, min=EPS).pow(y)           — 음수 base 보호
  [D4] clip_pos    = torch.clamp(x, min=0)              — Type B 수치 안정 stop-gradient
  [D5] smooth_minmod: eager 기본, smoothed는 별도 SMOOTH_EPS 폭 사용
  [D6] EPS = 1e-15                                      — Fortran qmin과 정합
  [D6b] SMOOTH_EPS = 1e-4                               — limiter sign-transition 폭

이 결정을 변경하려면 하나의 함수만 교체하면 됨 (모든 downstream import는 그대로).
"""
from __future__ import annotations

import torch

EPS: float = 1.0e-15  # [D6] Fortran qmin과 정합
SMOOTH_EPS: float = 1.0e-4  # [D6b] slope limiter sign-transition smoothing 폭


def safe_div_pos(num: torch.Tensor, denom: torch.Tensor) -> torch.Tensor:
    """[D1] 양수 분모 전용 안전 나눗셈.

    `denom < EPS` 구간은 `torch.clamp(..., min=EPS)`에 의해 gradient가 0이 된다.
    KDM6 bulk 경로처럼 분모가 물리적으로 양수여야 하는 경우에 사용한다.
    """
    return num / torch.clamp(denom, min=EPS)


def safe_div_signed(
    num: torch.Tensor,
    denom: torch.Tensor,
    floor: float = EPS,
) -> torch.Tensor:
    """[D1b] 부호 보존 분모-안전 나눗셈.

    `|denom| < floor`이면 `sign(denom) * floor`로 바꿔 0을 피하면서 부호를 보존한다.
    `denom == 0`은 양의 floor로 보정한다.
    """
    if floor <= 0.0:
        raise ValueError(f"floor must be > 0, got {floor!r}")
    floor_tensor = torch.as_tensor(floor, dtype=denom.dtype, device=denom.device)
    denom_sign = torch.where(denom != 0, torch.sign(denom), torch.ones_like(denom))
    denom_safe = torch.where(denom.abs() < floor_tensor, denom_sign * floor_tensor, denom)
    return num / denom_safe


def safe_div(num: torch.Tensor, denom: torch.Tensor) -> torch.Tensor:
    """[D1c] 하위호환 alias. 새 코드는 `safe_div_pos` 또는 `safe_div_signed`를 명시적으로 사용."""
    return safe_div_pos(num, denom)


def safe_sqrt(x: torch.Tensor) -> torch.Tensor:
    """[D2] 음수-안전 sqrt — clamp(min=EPS)."""
    return torch.sqrt(torch.clamp(x, min=EPS))


def safe_pow(x: torch.Tensor, y: float | torch.Tensor) -> torch.Tensor:
    """[D3] 음수 base 안전 power."""
    return torch.clamp(x, min=EPS).pow(y)


def clip_positive(x: torch.Tensor) -> torch.Tensor:
    """[D4] max(x, 0) — Type B 수치 안정. 음수 위치 grad=0 (ReLU 동작)."""
    return torch.clamp(x, min=0.0)


def smooth_minmod(
    a: torch.Tensor,
    b: torch.Tensor,
    mode: str = "eager",
    smooth_eps: float = SMOOTH_EPS,
) -> torch.Tensor:
    """[D5] PLM slope limiter.

    mode="eager"    : same-sign이면 작은 magnitude × sign, 다른 부호면 0 (표준 minmod)
    mode="smoothed" : tanh로 부호 일치 가중을 매끈화. smoothing이 실제로 보이려면
                      `smooth_eps`가 전형적 `|a*b|`보다 커야 한다.
    """
    if mode == "eager":
        same_sign = (a * b > 0).to(a.dtype)
        return same_sign * torch.sign(a) * torch.minimum(torch.abs(a), torch.abs(b))
    elif mode == "smoothed":
        if smooth_eps <= 0.0:
            raise ValueError(f"smooth_eps must be > 0, got {smooth_eps!r}")
        sgn_weight = 0.5 * (torch.tanh((a * b) / smooth_eps) + 1.0)
        return sgn_weight * torch.sign(a) * torch.minimum(torch.abs(a), torch.abs(b))
    else:
        raise ValueError(f"unknown mode: {mode!r} (expected 'eager' or 'smoothed')")


def isfinite_else(x: torch.Tensor, fallback: float = 0.0) -> torch.Tensor:
    """Fortran의 `if (ieee_is_nan(x) .or. .not. ieee_is_finite(x)) x = fallback` 대응.

    NaN 또는 inf 위치의 grad는 0으로 끊김 (stop-gradient 자연 동작).
    """
    return torch.where(
        torch.isfinite(x),
        x,
        torch.tensor(fallback, dtype=x.dtype, device=x.device),
    )
