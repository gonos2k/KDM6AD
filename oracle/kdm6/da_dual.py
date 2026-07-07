"""상태+파라미터 결합(dual) 4D-Var — mainline API (적대 검토 blocker-1/4의 승격).

검토 판정("dual estimation은 스크래치 데모+문서일 뿐 재현 가능한 코드 경로가
아니다")에 대한 응답으로, 데모 스크립트의 결합 최소화를 정식 API로 승격한다:

  J(v_x, v_θ) = ½‖v_x‖² + ½‖v_θ‖² + Σ_t J_obs,t( M(x_b + σ_x⊙v_x, θ(v_θ)) )

파라미터 CVT 는 **log-공간** (검토 결함-4 처방):

  θ_i = θb_i · exp(σ_log,i · v_θ,i)      → 양수성 자동 보장, prior = ½‖v_θ‖²
  ∂J/∂v_θ,i = v_θ,i + σ_log,i · θ_i · ∂J/∂θ_i     (dθ/dv_θ = σ_log·θ 체인)

(데모의 상대-선형 θ = θb(1+σv)는 큰 |v|에서 음수 θ 가능 — log-CVT로 대체.)

mask-게이밍 방어 (검토 blocker-2): obs_eval 이 (j, adj, n_valid) 3-튜플을
반환하면 n_valid(유효 관측항 수)를 trace에 기록하고, **클로저 간 변화 시 즉시
RuntimeError** — 루프-내 QC 이동을 구조적으로 금지한다. QC mask 자체의 동결은
obs_eval 작성자의 책임이며(H(x_b)에서 1회 평가), 이 게이트가 위반을 잡는다.

all-sky cfrac 한계 (검토 blocker-3, 명시적 제한): 현 all-sky 경로의 cfrac는
detached 이진 게이트 — 값은 문턱을 넘나들지만 gradient는 0이다. 본 API로
all-sky θ-추정을 할 때는 **cfrac-regime fixed** 해석 제한이 걸리며, 문턱 인접
거동이 의심되면 결과를 기각해야 한다 (smooth-cfrac 경로는 별도 실험 항목).

j_trace 는 dict 목록(total/j_state/j_theta/j_obs/n_valid) — JSON 직렬화 가능
(machine-readable run artifact, 검토 권고 5).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

import torch

from .da_minimizer import _stack, cvt_to_state
from .da_window import WindowConfig, run_da_window
from .runtime import Parameters, make_parameters
from .state import Forcing, State

_F64 = dict(dtype=torch.float64)
PNAMES = ("peaut", "ncrk1", "ncrk2", "eccbrk")


@dataclass(frozen=True)
class ParamPrior:
    """파라미터 배경(θ_b)과 log-공간 표준편차.

    sigma_log[i]=0 → 그 파라미터는 제어에서 제외(θ=θb 고정; exp(0)=1).
    sigma_log ≈ 0.2 는 "±20% 1σ" 에 해당 (exp(±0.2) ≈ ×1.22 / ×0.82).
    """
    theta_b: torch.Tensor                  # (4,) f64 — PNAMES 순서
    sigma_log: torch.Tensor                # (4,) f64, ≥ 0

    def __post_init__(self):
        if self.theta_b.shape != (4,) or self.sigma_log.shape != (4,):
            raise ValueError("theta_b/sigma_log must be shape (4,) in PNAMES order")
        if not bool(torch.isfinite(self.theta_b).all()):
            raise ValueError("theta_b must be finite (NaN/Inf pass sign checks)")
        if not bool(torch.isfinite(self.sigma_log).all()):
            raise ValueError("sigma_log must be finite")
        if bool((self.theta_b <= 0).any()):
            raise ValueError("theta_b must be positive (log-CVT domain)")
        if bool((self.sigma_log < 0).any()):
            raise ValueError("sigma_log must be >= 0")


def default_param_prior(sigma_log: float = 0.2,
                        active: tuple = PNAMES) -> ParamPrior:
    """기본 prior: 현행 상수 θ_b + 활성 파라미터에 동일 σ_log."""
    unknown = set(active) - set(PNAMES)
    if unknown:
        raise ValueError(
            f"unknown parameter names in active: {sorted(unknown)} — a typo here "
            "silently pins every parameter to theta_b (sigma_log=0)")
    base = make_parameters()
    tb = torch.stack([getattr(base, n).to(torch.float64) for n in PNAMES])
    sl = torch.tensor([sigma_log if n in active else 0.0 for n in PNAMES], **_F64)
    return ParamPrior(theta_b=tb, sigma_log=sl)


def params_from_vtheta(prior: ParamPrior, v_theta: torch.Tensor,
                       *, live: bool = False) -> Parameters:
    """θ_i = θb_i · exp(σ_i · v_θ,i) — live=True면 leaf(grad용)로 생성."""
    theta = prior.theta_b * torch.exp(prior.sigma_log * v_theta)
    if not bool(torch.isfinite(theta).all()):
        # log-CVT는 양수성은 보장하지만 finite는 아님 — L-BFGS 라인서치의 큰
        # 시도 스텝에서 exp 오버플로 가능 (재검토 #5)
        raise FloatingPointError(
            f"theta(v_theta) became non-finite (v_theta={v_theta.tolist()}); "
            "reduce sigma_log or bound v_theta")
    leaves = []
    for i in range(4):
        t = theta[i].detach().clone()
        if live and float(prior.sigma_log[i]) > 0.0:
            t.requires_grad_(True)
        leaves.append(t)
    return Parameters(*leaves)


@dataclass
class DualMinimizeResult:
    x_analysis: State
    theta_analysis: Parameters
    v_state: torch.Tensor
    v_theta: torch.Tensor
    # closure-평가 trace — L-BFGS strong-Wolfe의 라인서치 시도점 평가도 포함
    # (accepted-iterate 궤적이 아님; 수렴 플롯에는 마지막 값과 감소 여부만 신뢰)
    j_trace: list                          # [{total, j_state, j_theta, j_obs, n_valid}]
    jb_final: float
    jtheta_final: float
    jobs_final: float
    n_window_evals: int
    grad_norm_final: float
    grad_theta_norm_final: float


def run_dual_minimizer(
    xb: State,
    forcings: Sequence[Forcing],
    obs_eval: Callable[[int, State], "tuple | None"],
    window_config: WindowConfig,
    b_sigma: State,
    param_prior: ParamPrior,
    *,
    max_iter: int = 20,
    history_size: int = 8,
    tolerance_grad: float = 1.0e-10,
    require_signature: bool = True,
) -> DualMinimizeResult:
    """결합 J(v_x, v_θ) 를 단일 L-BFGS 로 최소화 (모듈 docstring 참조).

    obs_eval: (t, x_t) -> (j_t, adj_t, n_valid_t[, signature_t]) | None.
    **2-튜플은 거부된다** (재검토 blocker-1: 기존 상태의존-mask obs_eval을 그대로
    꽂으면 게이밍 방어가 전부 우회됨 — dual에서는 n_valid 필수). signature_t
    (예: mask의 sha256, all-sky면 cfrac-regime 해시 결합)를 주면 **동일-개수
    치환 게이밍**(어려운 항을 빼고 쉬운 항을 넣어 n_valid 유지)도 잡는다
    (blocker-2). 표준 clear-sky 경로는 make_dual_frozen_obs_eval 어댑터 사용.
    """
    sig_x = _stack(b_sigma)
    v_x = torch.zeros_like(sig_x, requires_grad=True)
    v_th = torch.zeros(4, **_F64, requires_grad=True)

    trace: list = []
    counters = {"windows": 0}
    last = {"jb": 0.0, "jth": 0.0, "jobs": 0.0, "gx": 0.0, "gth": 0.0}
    frozen_n_valid: dict = {}

    def closure() -> torch.Tensor:
        with torch.no_grad():
            x0 = cvt_to_state(xb, b_sigma, v_x)
        params_live = params_from_vtheta(param_prior, v_th.detach(), live=True)
        any_active = bool((param_prior.sigma_log > 0).any())
        import dataclasses as _dc
        cfg_i = _dc.replace(window_config, params=params_live,
                            param_grads=any_active)

        jobs_acc: list = []
        n_valid_acc: dict = {}

        def obs_adjoint(t: int, x_t: State):
            out = obs_eval(t, x_t)
            if out is None:
                return None
            if len(out) == 2:
                raise RuntimeError(
                    "dual minimizer requires obs_eval to return "
                    "(j, adj, n_valid[, signature]) — a 2-tuple obs_eval "
                    "bypasses the mask-gaming defenses (use "
                    "make_dual_frozen_obs_eval for the clear-sky path)")
            if len(out) == 4:
                j_t, adj_t, n_valid, sig = out
            else:
                if require_signature:
                    raise RuntimeError(
                        "production dual obs_eval must return a valid/regime "
                        "signature (4th element) — without it same-count mask "
                        "substitution is undetectable; pass "
                        "require_signature=False only for synthetic tests")
                j_t, adj_t, n_valid = out
                sig = None
            n_valid_acc[t] = (int(n_valid), sig)
            frozen = frozen_n_valid.get(t)
            if frozen is not None:
                if frozen[0] != int(n_valid):
                    raise RuntimeError(
                        f"n_valid changed during minimization at t={t}: "
                        f"{frozen[0]} -> {int(n_valid)} — the QC mask is moving "
                        "inside the loop (mask-gaming risk). Freeze the mask at "
                        "H(x_b) in obs_eval (outer-loop QC).")
                if frozen[1] != sig:
                    raise RuntimeError(
                        f"valid/regime signature changed during minimization at "
                        f"t={t} — same-count mask substitution or cfrac-regime "
                        "drift (mask-gaming variant). Freeze the mask AND the "
                        "operator regime before minimizing.")
            jobs_acc.append(torch.as_tensor(j_t, dtype=torch.float64).detach())
            return adj_t

        res = run_da_window(x0, forcings, obs_adjoint, cfg_i)
        counters["windows"] += 1
        # 우회 봉쇄 (stop-review): n_valid 감소 대신 슬롯 자체를 None으로
        # 사라지게 하면 항 전체가 조용히 J에서 탈락한다 — 보고 슬롯 집합의
        # 변화(소멸·신규 모두)도 게이밍으로 간주해 거부한다.
        if counters["windows"] == 1:
            frozen_n_valid.update(n_valid_acc)
        else:
            missing = set(frozen_n_valid) - set(n_valid_acc)
            appeared = set(n_valid_acc) - set(frozen_n_valid)
            if missing or appeared:
                raise RuntimeError(
                    f"observation slots changed during minimization "
                    f"(disappeared: {sorted(missing)}, appeared: {sorted(appeared)}) "
                    "— a slot returning None mid-loop drops its whole J term "
                    "silently (mask-gaming bypass). Slots must be stable; freeze "
                    "the obs set before minimizing.")

        with torch.no_grad():
            j_obs = (torch.stack(jobs_acc).sum() if jobs_acc
                     else torch.zeros((), **_F64))
            j_b = 0.5 * (v_x * v_x).sum()
            j_th = 0.5 * (v_th * v_th).sum()
            g_x = v_x.detach() + sig_x * _stack(res.adj_x0)
            # ∂J/∂v_θ = v_θ + σ_log · θ · ∂J/∂θ  (θ = θb·exp(σv) 체인)
            gp = torch.zeros(4, **_F64)
            if res.grad_params is not None:
                for i, n in enumerate(PNAMES):          # 비활성(σ=0)은 키 부재 → 0
                    if n in res.grad_params:
                        gp[i] = res.grad_params[n].to(torch.float64)
            theta_now = torch.stack([params_live[i].detach() for i in range(4)])
            g_th = v_th.detach() + param_prior.sigma_log * theta_now * gp
            for name, tt_ in (("j_obs", j_obs), ("g_x", g_x), ("g_th", g_th)):
                if not bool(torch.isfinite(tt_).all()):
                    raise FloatingPointError(
                        f"{name} became non-finite in the dual closure — "
                        "corrupted loss/gradient must not reach L-BFGS")
            v_x.grad = g_x
            v_th.grad = g_th
            j = j_b + j_th + j_obs
            trace.append(dict(total=float(j), j_state=float(j_b),
                              j_theta=float(j_th), j_obs=float(j_obs),
                              n_valid={k: v[0] for k, v in n_valid_acc.items()} or None))
            last.update(jb=float(j_b), jth=float(j_th), jobs=float(j_obs),
                        gx=float(g_x.norm()), gth=float(g_th.norm()))
        return j

    opt = torch.optim.LBFGS(
        [v_x, v_th], max_iter=max_iter, history_size=history_size,
        line_search_fn="strong_wolfe", tolerance_grad=tolerance_grad)
    opt.step(closure)

    with torch.no_grad():
        x_a = cvt_to_state(xb, b_sigma, v_x)
        theta_a = params_from_vtheta(param_prior, v_th.detach(), live=False)
    return DualMinimizeResult(
        x_analysis=x_a, theta_analysis=theta_a,
        v_state=v_x.detach(), v_theta=v_th.detach(), j_trace=trace,
        jb_final=last["jb"], jtheta_final=last["jth"], jobs_final=last["jobs"],
        n_window_evals=counters["windows"],
        grad_norm_final=last["gx"], grad_theta_norm_final=last["gth"])


def make_dual_frozen_obs_eval(xb: State, forcings: Sequence[Forcing],
                              y_by_time: dict, obs_cfg,
                              window_config: WindowConfig,
                              param_prior: ParamPrior) -> Callable:
    """clear-sky 표준 dual obs_eval — 동결 QC + n_valid + mask 서명.

    동결 기준은 **θ_b 배경 궤적**: run_da_window 자체를 no-op adjoint 프로브로
    사용해 (η/η_pre·cloud-gate 등 궤적 의미론 보존) M(x_b→t; θ_b)의 슬롯 상태를
    채취하고, 거기서 rad_quality를 평가해 mask = (관측 quality==0) ∧ (배경
    rad_quality==0) 를 동결한다. θ_b는 **param_prior에서** 취한다 (재검토 #3:
    window_config.params와 prior.theta_b의 조용한 불일치 차단 — 프로브 params를
    prior 기준으로 강제 주입).

    손실은 compute_obs_loss (Huber + full-shape/bias/sigma/masked-NaN 방어,
    재검토 blocker-1) — 수제 quadratic이 우회하던 안전장치 복원. gradient는
    clear-sky connected 필드(th/qv)에 대해 autograd.grad(allow_unused=False) —
    구조적 그래프 단절을 조용한 0 대신 거부 (blocker-2).

    y_by_time: {t: (y_bt (B,nch), y_rq (B,nch)[, bias])} — superob 권장.
    반환 obs_eval: (j, adj, n_valid, sha256(mask)).
    """
    import dataclasses
    import hashlib
    from .da_driver import batched_clear_bt
    from .obs.obs_loss import compute_obs_loss

    traj = {}

    def _probe(tt, x_t):
        if tt in y_by_time:
            traj[tt] = State(*(f.detach().clone() for f in x_t))
        return None

    theta_b_params = params_from_vtheta(param_prior, torch.zeros(4, **_F64),
                                        live=False)
    probe_cfg = dataclasses.replace(window_config, params=theta_b_params,
                                    param_grads=False)
    run_da_window(xb, forcings, _probe, probe_cfg)
    missing = set(y_by_time) - set(traj)
    if missing:
        raise ValueError(
            f"obs times {sorted(missing)} not visited by the window trajectory "
            f"(T={len(forcings)}) — check y_by_time step indices")

    frozen: dict = {}
    for t, entry in y_by_time.items():
        y_bt, y_rq = entry[0], entry[1]
        with torch.no_grad():
            _, rad_q, _ = batched_clear_bt(traj[t],
                                           forcings[min(t, len(forcings) - 1)],
                                           obs_cfg)
        m = ((y_rq == 0) & (rad_q.to(torch.float64) == 0)).double()
        sig = hashlib.sha256(m.cpu().numpy().tobytes()).hexdigest()
        frozen[t] = (m, int(m.sum()), sig)

    def obs_eval(t, x_t):
        if t not in frozen:
            return None
        entry = y_by_time[t]
        y_bt = entry[0]
        bias = entry[2] if len(entry) > 2 else None
        mask, n_valid, sig = frozen[t]
        bt, _, leaves = batched_clear_bt(x_t, forcings[min(t, len(forcings) - 1)],
                                         obs_cfg)
        obs = {"bt": y_bt}
        if bias is not None:
            obs["bias"] = bias
        j = compute_obs_loss(bt.to(torch.float64), obs, mask,
                             sigma=obs_cfg.obs_sigma)
        zeros = torch.zeros_like(leaves.th)
        if n_valid > 0:
            # clear-sky connected 필드는 th/qv — None grad는 구조적 단절
            g_th, g_qv = torch.autograd.grad(j, [leaves.th, leaves.qv],
                                             allow_unused=False)
        else:
            g_th, g_qv = zeros, zeros
        adj = State(th=g_th, qv=g_qv, qc=zeros, qr=zeros, qi=zeros, qs=zeros,
                    qg=zeros, nccn=zeros, nc=zeros, ni=zeros, nr=zeros, bg=zeros)
        return float(j.detach()), adj, n_valid, sig

    return obs_eval
