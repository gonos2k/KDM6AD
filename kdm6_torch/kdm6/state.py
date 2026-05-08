"""
KDM6 state vector — (B, K) 배치 텐서 layout.

선택된 전략 (권고안):
  [D7]  배치 layout = flatten (B = im*jm, K = kme - kms + 1)
  [D8]  state container = NamedTuple (불변, autograd 친화)
  [D9]  requires_grad 정책 = mode (i) 모든 prognostic on by default;
                              호출 시 인자로 다른 모드 가능
  [D10] NaN gate = optional (default off; nan_gate=True로 강제 재현)
  [D11] clip_neg = optional blanket clamp (default off; strict/dev 우선)
"""
from __future__ import annotations

from typing import Callable, NamedTuple
import torch

from .ops import isfinite_else, clip_positive

DEFAULT_DTYPE = torch.float64

# KDM6 prognostic 필드 순서 — Fortran 호출 시그니처와 정합
PROG_FIELDS = ("th", "qv", "qc", "qr", "qi", "qs", "qg", "nccn", "nc", "ni", "nr", "bg")
FORCING_FIELDS = ("rho", "pii", "p", "delz")


class State(NamedTuple):
    """[D8] KDM6 prognostic state. 모든 텐서 shape (B, K), dtype float64."""
    th: torch.Tensor
    qv: torch.Tensor
    qc: torch.Tensor
    qr: torch.Tensor
    qi: torch.Tensor
    qs: torch.Tensor
    qg: torch.Tensor
    nccn: torch.Tensor
    nc: torch.Tensor
    ni: torch.Tensor
    nr: torch.Tensor
    bg: torch.Tensor


class Forcing(NamedTuple):
    """수치 forcing — 보통 미분 대상 아님."""
    rho: torch.Tensor
    pii: torch.Tensor
    p: torch.Tensor
    delz: torch.Tensor


def map_state(state: State, fn: Callable[[torch.Tensor], torch.Tensor]) -> State:
    """Apply `fn` to every field and return a new State."""
    return State(*(fn(x) for x in state))


def zeros_like_state(state: State) -> State:
    """Return a zero State matching `state` field shapes, dtype, and device."""
    return map_state(state, torch.zeros_like)


def state_dot(a: State, b: State) -> torch.Tensor:
    """Sum elementwise field products across the full state, returning a scalar."""
    total = torch.zeros((), dtype=a.th.dtype, device=a.th.device)
    for a_field, b_field in zip(a, b):
        total = total + (a_field * b_field).sum()
    return total


def replace_state(state: State, **updates: torch.Tensor) -> State:
    """Return a new State with a partial field-wise update applied."""
    return state._replace(**updates)


def _flatten_3d_to_2d(arr_3d: torch.Tensor, im: int, kme: int, jme: int) -> torch.Tensor:
    """[D7] (im, kme, jme) Fortran-style → (B=im*jme, K=kme).

    Fortran의 (i,k,j) 인덱싱: i fastest. → permute (i,j,k) 후 flatten (i,j)→B.
    """
    assert arr_3d.shape == (im, kme, jme), f"expected (im={im}, kme={kme}, jme={jme}), got {arr_3d.shape}"
    return arr_3d.permute(0, 2, 1).reshape(im * jme, kme)


def _unflatten_2d_to_3d(arr_2d: torch.Tensor, im: int, jme: int) -> torch.Tensor:
    """(B=im*jme, K) → (im, kme, jme). _flatten_3d_to_2d의 역."""
    B, kme = arr_2d.shape
    assert B == im * jme
    return arr_2d.reshape(im, jme, kme).permute(0, 2, 1).contiguous()


def from_fortran_arrays(
    *,
    th: torch.Tensor,
    qv: torch.Tensor,
    qc: torch.Tensor,
    qr: torch.Tensor,
    qi: torch.Tensor,
    qs: torch.Tensor,
    qg: torch.Tensor,
    nccn: torch.Tensor,
    nc: torch.Tensor,
    ni: torch.Tensor,
    nr: torch.Tensor,
    bg: torch.Tensor,
    im: int,
    kme: int,
    jme: int,
    requires_grad: bool = True,
    nan_gate: bool = False,
    clip_neg: bool = False,
) -> State:
    """Fortran-style (im, kme, jme) 텐서 12개 → (B=im*jme, K=kme) State.

    [D9]  requires_grad=True (default mode i): 모든 prognostic에 grad on
    [D10] nan_gate=True : isfinite_else(., 0)로 NaN/inf 제거 (운영 모드)
                  False : 그대로 통과 (dev/strict 모드 — NaN이 있으면 backward에서 폭발)
    clip_neg=False : 기본은 입력을 그대로 유지해 upstream 음수/이상치를 숨기지 않음
    clip_neg=True  : `th`를 제외한 모든 prognostic에 blanket `max(., 0)` 적용
                     (수치 guard 용도; field-specific Fortran entry 처리와는 다름)

    Notes
    -----
    `bg`(graupel volume mixing ratio)는 Park-Lim 2024 도입. 기존 forward에서는 0으로
    초기화되어 있을 수 있음 — 그래도 그대로 받음.
    `nccn`은 KDM6 첫 timestep에 land/sea + scale_h profile로 초기화됨; 본 함수는
    그 초기화 단계가 *끝난 후* 의 상태를 받는다고 가정.
    """
    # 1. cast + flatten
    raw = dict(th=th, qv=qv, qc=qc, qr=qr, qi=qi, qs=qs, qg=qg,
               nccn=nccn, nc=nc, ni=ni, nr=nr, bg=bg)
    flat: dict[str, torch.Tensor] = {}
    for name, t in raw.items():
        t = t.to(DEFAULT_DTYPE)
        t = _flatten_3d_to_2d(t, im, kme, jme)
        if nan_gate:
            t = isfinite_else(t, fallback=0.0)
        if clip_neg and name != "th":  # strict default는 off; enabled 시 blanket guard
            t = clip_positive(t)
        if requires_grad:
            t = t.detach().clone().requires_grad_(True)
        flat[name] = t
    return State(**flat)


def to_fortran_arrays(state: State, im: int, jme: int) -> dict[str, torch.Tensor]:
    """State → Fortran-style (im, kme, jme) 텐서 dict.

    backward 후 호스트 모델로 갱신값 또는 grad을 돌려보낼 때 사용.
    """
    return {name: _unflatten_2d_to_3d(getattr(state, name), im, jme) for name in PROG_FIELDS}
