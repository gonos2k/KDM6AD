"""
KDM6 PyTorch runtime — 슬롯 47 진입점 + autograd handle.

이 모듈은 *아키텍처 골격*. 실제 물리 계산은 slope/core/sedimentation 모듈이 차면
`kdm6_fn(...)` 안에서 호출된다. 본 파일이 담당하는 것:

  1. 입력 state·forcing·params 준비 (state.from_fortran_arrays + Parameters 처리)
  2. dynamic graph 빌드용 pure function `kdm6_fn(state, forcing, params, dt) → State`
  3. JVP / VJP / Jacobian 추출용 `Handle` 클래스
  4. DA-친화 entry point `kdm6_step(...)` — Fortran-side에서 호출하는 함수

설계 결정은 wiki/concepts/pytorch-autograd-integration.md 참조 (G1-G7).

──────────────────────────────────────────────────────────────────────
현재 상태:
  - 인터페이스 시그니처 + TODO 마커만 존재 (slope/core/sedimentation 미구현)
  - kdm6_step 호출하면 NotImplementedError
  - 본 파일이 의미있게 동작하려면 slope.py 먼저 필요
──────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, NamedTuple
import torch

from .state import State, Forcing, from_fortran_arrays, to_fortran_arrays
from . import constants as c


# ─── Parameters: opt-in differentiable model parameters ────────────────────────

class Parameters(NamedTuple):
    """[G4] torch.func-friendly 모델 파라미터 pytree.

    각 필드는 constants.py와 1:1 대응하는 leaf tensor다. 기본 생성은
    `make_parameters()`를 사용한다.
    """

    peaut: torch.Tensor
    ncrk1: torch.Tensor
    ncrk2: torch.Tensor
    eccbrk: torch.Tensor


def _mkparam(
    value: float,
    *,
    device: torch.device | str,
    dtype: torch.dtype,
    requires_grad: bool,
) -> torch.Tensor:
    t = torch.tensor(value, device=device, dtype=dtype)
    if requires_grad:
        t = t.detach().clone().requires_grad_(True)
    return t


def make_parameters(
    *,
    all_grad: bool = False,
    peaut_grad: bool = False,
    ncrk_grad: bool = False,
    device: torch.device | str = "cpu",
    dtype: torch.dtype = torch.float64,
) -> Parameters:
    """[G4] `Parameters` 생성 helper.

    기본값은 모든 파라미터 frozen이며, 보정 실험에서 필요한 항목만 grad를 켠다.
    """
    # TODO: 나머지 collection efficiency, lamdaR-MAX/MIN 등 추가
    # 우선 PEAUT가 가장 자주 튜닝되는 표면이라 이것부터 노출
    return Parameters(
        peaut=_mkparam(c.PEAUT, device=device, dtype=dtype, requires_grad=peaut_grad or all_grad),
        ncrk1=_mkparam(c.NCRK1, device=device, dtype=dtype, requires_grad=ncrk_grad or all_grad),
        ncrk2=_mkparam(c.NCRK2, device=device, dtype=dtype, requires_grad=ncrk_grad or all_grad),
        eccbrk=_mkparam(c.ECCBRK, device=device, dtype=dtype, requires_grad=all_grad),
    )


# ─── Handle: JVP / VJP / Jacobian 추출 인터페이스 ──────────────────────────────

@dataclass
class Handle:
    """[G3] kdm6_step 호출의 *autograd 결과 핸들*.

    내부에 `state_in`, `state_out`, `forcing`, `params`, `dt`와 future derivative
    extraction에 필요한 `pullback` 또는 `func`를 보존한다. 사용 후 `close()`로
    참조를 해제해 graph가 GC되도록 하는 것을 권장한다.

    지원 연산:
      - vjp(u): J^T @ u — DA adjoint (4D-Var)
      - jvp(v): J @ v   — DA tangent (EnKF perturbation)
      - jacobian(rows, cols): 부분 Jacobian 행렬 — 진단·디버깅
      - param_grad(scalar): 임의 스칼라 손실에 대한 ∂L/∂params

    Notes
    -----
    `value_only=True`로 생성된 Handle은 derivative API를 지원하지 않는다.
    `close()` 호출 후 derivative API는 `RuntimeError`를 발생시킨다.
    """
    state_in: State | None
    state_out: State | None
    forcing: Forcing | None
    params: Parameters | None
    dt: float | None
    pullback: Callable[..., object] | None = None
    func: Callable[[State, Forcing, Parameters, float], State] | None = None
    value_only: bool = False
    closed: bool = False

    def close(self) -> None:
        """Release tensor references so the autograd graph can be garbage-collected."""
        self.state_in = None
        self.state_out = None
        self.forcing = None
        self.params = None
        self.dt = None
        self.pullback = None
        self.func = None
        self.closed = True

    def _ensure_derivative_ready(self) -> None:
        if self.closed:
            raise RuntimeError("Handle is closed")
        if self.value_only:
            raise RuntimeError("Handle is value-only")
        if (
            self.state_in is None
            or self.state_out is None
            or self.forcing is None
            or self.params is None
            or self.dt is None
        ):
            raise RuntimeError("Handle is missing derivative context")
        if self.pullback is None and self.func is None:
            raise RuntimeError("Handle is missing derivative context")

    def vjp(self, u: State) -> State:
        """[G3] J^T @ u — adjoint 연산.

        Parameters
        ----------
        u : State
            state_out 공간의 covector (e.g., 관측-모델 잔차)

        Returns
        -------
        state_in_grad : State
            ∂(u · state_out) / ∂state_in
        """
        self._ensure_derivative_ready()
        raise NotImplementedError("[G3] VJP — implement after core kdm6_step works")

    def jvp(self, v: State) -> State:
        """[G3] J @ v — tangent linear 연산.

        Note: 일반적으로 vjp보다 비싸 (forward-mode가 활용되면 cheaper); 본 메서드는
        후행 도입을 위한 placeholder. torch.func.jvp 활용 예정.
        """
        self._ensure_derivative_ready()
        raise NotImplementedError("[G3] JVP — implement after core kdm6_step works")

    def jacobian(
        self,
        rows: tuple[str, ...] | None = None,
        cols: tuple[str, ...] | None = None,
    ) -> dict[tuple[str, str], torch.Tensor]:
        """[G3] 부분 Jacobian 추출.

        Parameters
        ----------
        rows : 출력 필드 이름 tuple (e.g., ("qc", "qr")); None이면 전체
        cols : 입력 필드 이름 tuple (e.g., ("qv", "th")); None이면 전체

        Returns
        -------
        dict (out_field, in_field) → tensor (B, K_out, K_in)
        """
        self._ensure_derivative_ready()
        raise NotImplementedError("[G3] Jacobian — implement using torch.func.jacrev")

    def param_grad(self, scalar_loss: torch.Tensor) -> dict[str, torch.Tensor]:
        """[G4] 파라미터 grad — 임의 스칼라 loss에 대한 ∂L/∂params."""
        self._ensure_derivative_ready()
        raise NotImplementedError("[G4] param_grad — uses torch.autograd.grad")


# ─── Pure function: 단일 KDM6 호출의 *autograd-friendly* 형태 ──────────────────

def _kdm6_pure(
    state: State,
    forcing: Forcing,
    params: Parameters,
    dt: float,
) -> State:
    """[G1] One-step KDM6 — autograd dynamic graph가 통과할 pure function.

    이 함수가 본 프로젝트의 *모든* 미분가능 물리. slope/core/sedimentation의 합.

    Pipeline (구현 예정):
      1. slope.compute_slopes(state, forcing) → slopes
      2. core.kdm62D_microphysics(state, slopes, forcing, params, dt) → tendencies
      3. sedimentation.nislfv_plm(state, tendencies, forcing, dt) → state_after_fall
      4. core.bookkeeping(state_after_fall) → final state

    Returns
    -------
    State : 한 step 적분 후 갱신된 state. 모든 텐서는 state.* 입력에 대한 graph 보존.

    Note
    ----
    `forcing`은 typically grad off (수치 forcing은 미분 대상 아님).
    `params`는 `Parameters`의 grad 정책에 따름.
    `state`는 보통 grad on (DA observation operator 입력).
    """
    raise NotImplementedError(
        "[G1] _kdm6_pure — to be implemented after slope.py / core.py / sedimentation.py"
    )


kdm6_fn = _kdm6_pure


# ─── Public entry point: kdm6_step ─────────────────────────────────────────────

def kdm6_step(
    state: State,
    forcing: Forcing,
    params: Parameters | None = None,
    dt: float = 60.0,
    value_only: bool = False,
) -> tuple[State, Handle]:
    """[G3] 슬롯 47 진입점 — Fortran forward와 *동반 구동*되어 derivative 정보 산출.

    Parameters
    ----------
    state : State
        prognostic state, (B, K) 텐서들 with requires_grad as configured
    forcing : Forcing
        rho, pii, p, delz — 보통 grad off
    params : Parameters, optional
        모델 파라미터 텐서들. None이면 디폴트(frozen).
    dt : float
        timestep [s]. KDM6 내부에서 DTCLDCR=120s 단위 sub-cycling.
    value_only : bool, default False
        True이면 `torch.no_grad()`로 forward 값만 계산한다. False이면 full graph를
        유지한 Handle을 반환한다.

    Returns
    -------
    state_out : State
        갱신된 state. *forward 정합* 검증용으로 슬롯 37 출력과 비교.
    handle : Handle
        VJP/JVP/Jacobian/param_grad 추출 인터페이스.

    Notes
    -----
    [G2] 본 함수의 출력 state는 production state 갱신에 *사용하지 않음* (Fortran
         슬롯 37이 그 역할). 본 함수의 일차 산출은 derivative 그 자체.
    [G6] 메모리: per-step graph만 보존. timestep 간 chain은 하지 않음.
         dt를 외부 model의 dt와 일치시켜 호출하면 자연스럽게 graph 분리됨.
    forward-mode vs reverse-mode 선택은 `torch.func.{jvp,vjp,jacrev,jacfwd}`를
    `kdm6_fn`에 직접 적용해 제어한다.
    """
    if params is None:
        params = make_parameters()

    if value_only:
        with torch.no_grad():
            state_out = kdm6_fn(state, forcing, params, dt)
        return state_out, Handle(
            state_in=state,
            state_out=state_out,
            forcing=forcing,
            params=params,
            dt=dt,
            pullback=None,
            func=None,
            value_only=True,
        )

    # build dynamic graph
    state_out = kdm6_fn(state, forcing, params, dt)
    handle = Handle(
        state_in=state,
        state_out=state_out,
        forcing=forcing,
        params=params,
        dt=dt,
        pullback=None,
        func=kdm6_fn,
    )
    return state_out, handle


# ─── Verification helper: forward 정합 ─────────────────────────────────────────

def compare_to_fortran(
    state_in_dict: dict[str, torch.Tensor],
    fortran_state_out_dict: dict[str, torch.Tensor],
    forcing_dict: dict[str, torch.Tensor],
    *,
    im: int,
    kme: int,
    jme: int,
    dt: float,
    rtol: float = 1e-8,
    atol: float = 1e-12,
) -> dict[str, dict[str, float]]:
    """[T4] 슬롯 37(Fortran) 출력과 슬롯 47(PyTorch) 출력의 정합 검증.

    Returns
    -------
    per-field metrics (max abs error, max rel error, allclose pass/fail).
    rtol/atol은 사용자 지정 forward 정합 허용 오차.
    """
    raise NotImplementedError(
        "[T4] compare_to_fortran — implement after _kdm6_pure works. "
        "Default tolerance to be confirmed by user (concept/pytorch-autograd-integration.md §9)"
    )
