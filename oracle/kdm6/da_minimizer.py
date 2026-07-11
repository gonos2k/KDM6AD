"""Strong-constraint 3D/4D-Var minimizer — diagonal-B CVT + L-BFGS (T1-4).

DA_REALTIME_PLAN §3 T1-4 (정밀 검토 재스코핑 반영):
  - strong-constraint(η=None): 제어변수는 창 초기상태 x0뿐.
  - **CVT(control-variable transform)** v = B^{-1/2}(x0 − xb), 즉 x0 = xb + σ_b ⊙ v.
    State 필드들이 ~10 자릿수 스팬(th~300 vs qr~1e-6)이라 raw x0 공간의 L-BFGS는
    악조건 — CVT 공간에서 J_b = ½‖v‖²이 되고 헤시안의 B-블록이 항등이 된다.
  - torch.optim.LBFGS(strong_wolfe): .grad는 autograd가 아니라 **창 adjoint에서
    수동 할당** — run_da_window(checkpoint/recompute)가 ∂J_obs/∂x0를 주고,
    체인룰로 ∂J/∂v = v + σ_b ⊙ adj_x0.

adjoint-method 경제성: L-BFGS 라인서치는 J 값과 기울기를 함께 요구한다.
run_da_window의 forward 스윕이 obs_adjoint(t, x_t)를 호출하는 바로 그 지점에서
J_obs 기여를 누적하면 **창 적분 1회 = (J, ∇J) 동시 산출** — 값 전용 재적분이 없다.

σ_b=0인 필드는 제어에서 제외된다(x0의 그 필드는 xb에 고정; 해당 v-슬라이스는
J_b에 의해 0으로 수렴). 관측 없는 창에서는 v→0, 즉 분석 = 배경 (테스트 불변식).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

import torch

from .da_cvt import (CvtSpec, _stack, _unstack, build_cvt_record, cvt_apply,
                     validate_cvt)
from .da_partition import (CHANNELS, PartitionSpec, apply_partition_chain,
                           build_partition_caps, build_partition_record,
                           chain_with_pullback, validate_partition)
from .da_window import WindowConfig, run_da_window
from .state import State, Forcing

_FIELDS = State._fields                     # 12필드 순서 고정


def _validate_state_shapes(state: State, ref: State, *, arg: str, ref_name: str) -> None:
    """Reject broadcastable-but-wrong State field shapes before CVT math."""
    for f in _FIELDS:
        got = tuple(getattr(state, f).shape)
        exp = tuple(getattr(ref, f).shape)
        if got != exp:
            raise ValueError(
                f"{arg}.{f} shape {got} != {ref_name}.{f} shape {exp} "
                "(silent broadcasting is forbidden)")


def cvt_to_state(xb: State, b_sigma: State, v: torch.Tensor,
                 spec: "CvtSpec | None" = None) -> State:
    """CVT 역변환 — spec=None(기본)은 선형 x0 = xb + σ_b ⊙ v. v: (12, B, K).

    spec 지정 시 필드별 하이브리드 add/mul 변환 (da_cvt.cvt_apply 참조)."""
    return cvt_apply(xb, b_sigma, v, spec)[0]


@dataclass
class MinimizeResult:
    x_analysis: State                    # 분석 초기상태 x0^a = xb + σ_b ⊙ v*
    v: torch.Tensor                      # 수렴한 제어벡터 (12, B, K)
    j_trace: list[float]                 # closure 호출별 J = J_b + J_obs
    jb_final: float
    jobs_final: float
    n_window_evals: int                  # 창 적분(forward+adjoint) 횟수
    grad_norm_final: float
    cvt: "dict | None" = None            # 감사 레코드 (spec 경로만; 레거시 None)
    w: "torch.Tensor | None" = None      # partition controls (n_ch, B, K), opt-in
    partition: "dict | None" = None      # partition audit record (da_partition)


def run_minimizer(
    xb: State,
    forcings: Sequence[Forcing],
    obs_eval: Callable[[int, State], "tuple[torch.Tensor, State] | None"],
    window_config: WindowConfig,
    b_sigma: State,
    *,
    max_iter: int = 20,
    history_size: int = 8,
    tolerance_grad: float = 1.0e-10,
    cvt: "CvtSpec | None" = None,
    partition: "PartitionSpec | None" = None,
    partition_forcing: "Forcing | None" = None,
) -> MinimizeResult:
    """J(v) = ½‖v‖² + Σ_t J_obs,t(x_t(v)) 를 CVT 공간에서 L-BFGS로 최소화.

    Parameters
    ----------
    obs_eval : callable (t, x_t) -> (j_t, adj_t) | None
        시각 t의 관측항: 스칼라 비용 j_t 와 covector ∂j_t/∂x_t (State).
        관측이 없으면 None. (run_da_window의 obs_adjoint 규약에 J-값 반환을
        추가한 형태 — 래퍼가 j_t를 누적하고 adj_t만 창으로 넘긴다.)
    b_sigma : State
        필드/셀별 배경오차 표준편차 σ_b (= diagonal B^{1/2}). 0 → 그 성분은
        제어에서 제외(배경 고정). cvt의 mul 필드에서는 log-공간 σ (무차원).
    cvt : CvtSpec | None
        None(기본) = 기존 선형 CVT, byte-identical 레거시 경로 (미검증 유지).
        spec 지정 = 필드별 add/mul 하이브리드 (da_cvt) — validate_cvt로
        fail-fast 검증 후, 체인룰은 ∂J/∂v = v + jac ⊙ adj_x0 (jac = ∂x0/∂v).
    partition : PartitionSpec | None
        None (default) = byte-identical legacy path. Spec given = compose the
        conserving signed partition stage P_w after the diagonal CVT
        (da_partition): x0 = P_w(D_v(xb)), J_b += ½‖w‖²; gradients via the
        local-autograd pullback — g_w = w + ∂J_obs/∂w and
        g_v = v + jac ⊙ adj_y where adj_y is the y-pullback through P.
    partition_forcing : Forcing | None
        t0 forcing for the partition latent terms (Exner pii). Defaults to
        forcings[0]; REQUIRED for a zero-step window (obs at t=0 only),
        which has no step forcings but is a valid legacy configuration.
    """
    _validate_state_shapes(b_sigma, xb, arg="b_sigma", ref_name="xb")
    if cvt is not None:
        validate_cvt(xb, b_sigma, cvt, window_config.active_fields)
    if partition is None and partition_forcing is not None:
        raise ValueError(
            "partition_forcing given without partition — a stray forcing "
            "would be silently ignored (config error)")
    sig = _stack(b_sigma)
    xb64 = _unstack(_stack(xb))                       # fp64 정규화 사본
    v = torch.zeros_like(sig, requires_grad=True)     # v=0 에서 시작 (x0 = xb)
    caps = w = None
    if partition is not None:
        # caps frozen from the background (v/w-independent B)
        caps = build_partition_caps(xb64, partition)
        validate_partition(caps, window_config.active_fields)
        if partition_forcing is None:
            if not len(forcings):
                raise ValueError(
                    "partition latent terms need the t0 forcing (Exner) — "
                    "pass partition_forcing for a zero-step window")
            partition_forcing = forcings[0]
        w = torch.zeros((len(CHANNELS),) + tuple(xb64.th.shape),
                        dtype=torch.float64, requires_grad=True)

    trace: list[float] = []
    counters = {"windows": 0}
    last = {"jb": 0.0, "jobs": 0.0, "gnorm": 0.0}

    def closure() -> torch.Tensor:
        # CVT 산술만 no_grad — run_da_window는 내부 backward 스윕에서 스스로
        # local-graph를 재구축하므로(grad 컨텍스트 자가 관리) 감싸면 안 된다.
        with torch.no_grad():
            y, jac = cvt_apply(xb64, b_sigma, v, cvt)
        if partition is None:
            x0, pullback = y, None
        else:
            x0, pullback = chain_with_pullback(y, partition_forcing, w, caps)
        jobs_acc: list[torch.Tensor] = []

        def obs_adjoint(t: int, x_t: State):
            out = obs_eval(t, x_t)
            if out is None:
                return None
            j_t, adj_t = out
            jobs_acc.append(torch.as_tensor(j_t, dtype=torch.float64).detach())
            return adj_t

        res = run_da_window(x0, forcings, obs_adjoint, window_config)
        counters["windows"] += 1

        with torch.no_grad():
            j_obs = (torch.stack(jobs_acc).sum() if jobs_acc
                     else torch.zeros((), dtype=torch.float64))
            j_b = 0.5 * (v * v).sum()
            if partition is None:
                # ∂J/∂v = v + jac ⊙ ∂J_obs/∂x0  (CVT 체인룰; 선형이면 jac = σ_b)
                grad = v.detach() + jac * _stack(res.adj_x0)
            else:
                adj_y, g_w_obs = pullback(res.adj_x0)  # local pullback through P
                grad = v.detach() + jac * adj_y
                w.grad = w.detach() + g_w_obs
                j_b = j_b + 0.5 * (w * w).sum()
            v.grad = grad                              # 수동 할당 (autograd 미사용)
            j = j_b + j_obs
            trace.append(float(j))
            last["jb"], last["jobs"] = float(j_b), float(j_obs)
            gsq = grad.pow(2).sum()
            if partition is not None:
                gsq = gsq + w.grad.pow(2).sum()
            last["gnorm"] = float(gsq.sqrt())
        return j

    opt = torch.optim.LBFGS(
        [v] if partition is None else [v, w],
        max_iter=max_iter, history_size=history_size,
        line_search_fn="strong_wolfe", tolerance_grad=tolerance_grad)
    opt.step(closure)

    with torch.no_grad():
        x_a, _ = cvt_apply(xb64, b_sigma, v, cvt)
        part_rec = None
        if partition is not None:
            # reconstruct the analysis with the COMPOSED decoder — cvt_apply
            # alone would drop the partition increments
            x_a = apply_partition_chain(x_a, partition_forcing, w.detach(),
                                        caps)
            part_rec = build_partition_record(partition, caps, w.detach())
        cvt_rec = (build_cvt_record(cvt, b_sigma, xb64, x_a)
                   if cvt is not None else None)
    return MinimizeResult(
        x_analysis=x_a, v=v.detach(), j_trace=trace,
        jb_final=last["jb"], jobs_final=last["jobs"],
        n_window_evals=counters["windows"], grad_norm_final=last["gnorm"],
        cvt=cvt_rec, w=None if w is None else w.detach(),
        partition=part_rec)
