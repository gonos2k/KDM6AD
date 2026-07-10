"""상태+파라미터 결합(dual) 4D-Var — mainline API (적대 검토 blocker-1/4의 승격).

검토 판정("dual estimation은 스크래치 데모+문서일 뿐 재현 가능한 코드 경로가
아니다")에 대한 응답으로, 데모 스크립트의 결합 최소화를 정식 API로 승격한다:

  J(v_x, v_θ) = ½‖v_x‖² + ½‖v_θ‖² + Σ_t J_obs,t( M(x_b + σ_x⊙v_x, θ(v_θ)) )

파라미터 CVT 는 **log-공간** (검토 결함-4 처방):

  θ_i = θb_i · exp(σ_log,i · v_θ,i)      → 양수성 자동 보장, prior = ½‖v_θ‖²
  ∂J/∂v_θ,i = v_θ,i + σ_log,i · θ_i · ∂J/∂θ_i     (dθ/dv_θ = σ_log·θ 체인)

(데모의 상대-선형 θ = θb(1+σv)는 큰 |v|에서 음수 θ 가능 — log-CVT로 대체.)

mask-게이밍 방어: production obs_eval 은 ObsEvalResult(또는 (j, adj,
n_valid, signature) 4-튜플)가 필수 — n_valid(유효 항 수)·signature(mask/regime
정체 해시)·보고-슬롯 집합이 첫 클로저에서 동결되고, 이후 변화는 즉시
RuntimeError (루프-내 QC 이동·동일-개수 치환·슬롯 소멸 전부 구조적 금지).
서명 없는 3-튜플은 require_signature=False(합성 테스트 전용)에서만 허용.
QC mask 자체의 동결 기준은 **θ_b 배경 궤적 M(x_b→t; θ_b)** 이며(표준 어댑터
make_dual_frozen_obs_eval), 이 게이트들이 위반을 잡는다.

all-sky cfrac 한계 (검토 blocker-3, 명시적 제한): 현 all-sky 경로의 cfrac는
detached 이진 게이트 — 값은 문턱을 넘나들지만 gradient는 0이다. 본 API로
all-sky θ-추정을 할 때는 **cfrac-regime fixed** 해석 제한이 걸리며, 문턱 인접
거동이 의심되면 결과를 기각해야 한다 (smooth-cfrac 경로는 별도 실험 항목).

j_trace 는 dict 목록(total/j_state/j_theta/j_obs/n_valid) — JSON 직렬화 가능
(machine-readable run artifact, 검토 권고 5).
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, fields, is_dataclass
from typing import Callable, Optional, Sequence

import torch

from .da_cvt import CvtSpec, build_cvt_record, cvt_apply, validate_cvt
from .da_minimizer import _stack, _validate_state_shapes
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


@dataclass(frozen=True)
class ObsGatePolicy:
    """dual 관측 게이트 정책 — 어댑터·최소화기가 **같은 객체**를 공유해
    opt-in 상태의 이중 분산을 막는다. DualMinimizeResult.policy에 기록됨."""
    require_signature: bool = True
    allow_zero_valid_slots: bool = False
    require_obs_slots: bool = True
    # production 기본은 ObsEvalResult만 — 튜플 반환은 명시 opt-in (인덱스
    # 실수 방지; 합성 테스트 전용)
    allow_tuple_returns: bool = False

    def __post_init__(self):
        for name in ("require_signature", "allow_zero_valid_slots",
                     "require_obs_slots", "allow_tuple_returns"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be bool")

    def as_dict(self) -> dict:
        return dict(require_signature=self.require_signature,
                    allow_zero_valid_slots=self.allow_zero_valid_slots,
                    require_obs_slots=self.require_obs_slots,
                    allow_tuple_returns=self.allow_tuple_returns)


@dataclass(frozen=True)
class ObsEvalResult:
    """obs_eval의 표준 반환형. signature는 str만 (bytes 정규화는 튜플 호환
    경로 전용 — 타입 계약과 런타임 허용 범위 일치, 재검토 M3)."""
    j: "torch.Tensor | float"
    adj: State
    n_valid: int
    signature: str

    def __post_init__(self):
        if not isinstance(self.signature, str) or not self.signature:
            raise TypeError("ObsEvalResult.signature must be a non-empty str")
        if isinstance(self.n_valid, bool) or not isinstance(self.n_valid, int):
            raise TypeError("ObsEvalResult.n_valid must be a plain int")
        if self.n_valid < 0:
            raise ValueError("ObsEvalResult.n_valid must be >= 0")


@dataclass(frozen=True)
class _FrozenObsSlot:
    """Frozen observation contract for one reported time slot.

    Tensors are detached clones made at adapter construction time. Grouping them
    by name keeps the frozen mask/obs/bias/sigma contract auditable without
    reintroducing tuple-index coupling inside the production adapter. sigma is a
    detached scalar/per-channel/full-field tensor accepted by compute_obs_loss
    broadcast rules.
    """
    mask: torch.Tensor
    n_valid: int
    signature: str
    y_bt: torch.Tensor
    bias: "torch.Tensor | None"
    sigma: torch.Tensor

    def __post_init__(self):
        if not isinstance(self.signature, str) or not self.signature:
            raise TypeError("_FrozenObsSlot.signature must be a non-empty str")
        if isinstance(self.n_valid, bool) or not isinstance(self.n_valid, int):
            raise TypeError("_FrozenObsSlot.n_valid must be a plain int")
        if self.n_valid < 0:
            raise ValueError("_FrozenObsSlot.n_valid must be >= 0")
        if tuple(self.mask.shape) != tuple(self.y_bt.shape):
            raise ValueError(
                "_FrozenObsSlot mask and y_bt shape mismatch: "
                f"{tuple(self.mask.shape)} != {tuple(self.y_bt.shape)}")
        if self.bias is not None:
            try:
                bias_shape = torch.broadcast_shapes(self.bias.shape, self.y_bt.shape)
            except RuntimeError:
                bias_shape = None
            if bias_shape != tuple(self.y_bt.shape):
                raise ValueError(
                    "_FrozenObsSlot bias does not broadcast to y_bt: "
                    f"{tuple(self.bias.shape)} -> {tuple(self.y_bt.shape)}")


def _freeze_obs_cfg_value(value):
    """Best-effort construction-time freeze for obs operator config fields."""
    if isinstance(value, torch.Tensor):
        return value.detach().clone()
    if is_dataclass(value) and not isinstance(value, type):
        return type(value)(**{f.name: _freeze_obs_cfg_value(getattr(value, f.name))
                             for f in fields(value)})
    if hasattr(value, "_fields") and isinstance(value, tuple):
        return type(value)(*(_freeze_obs_cfg_value(v) for v in value))
    if isinstance(value, tuple):
        return tuple(_freeze_obs_cfg_value(v) for v in value)
    if isinstance(value, list):
        return tuple(_freeze_obs_cfg_value(v) for v in value)
    if isinstance(value, dict):
        return {copy.deepcopy(k): _freeze_obs_cfg_value(v) for k, v in value.items()}
    if callable(value):
        return _FrozenCallable(
            value, _freeze_obs_cfg_value(getattr(value, "solar_channels", None)))
    return copy.deepcopy(value)


def _freeze_obs_cfg(obs_cfg):
    """Freeze the observation operator config used by the dual adapter.

    Supported production shapes are dataclass, namedtuple, and attribute-only
    objects. Tensor fields are detached/cloned; sequence and dict fields are
    recursively copied. Generic descriptors/properties are intentionally not
    evaluated here — keep production obs configs data-only/fail-explicit.
    """
    if is_dataclass(obs_cfg) and not isinstance(obs_cfg, type):
        return type(obs_cfg)(**{f.name: _freeze_obs_cfg_value(getattr(obs_cfg, f.name))
                               for f in fields(obs_cfg)})
    if hasattr(obs_cfg, "_fields") and isinstance(obs_cfg, tuple):
        return type(obs_cfg)(*(_freeze_obs_cfg_value(v) for v in obs_cfg))
    attrs = {k: _freeze_obs_cfg_value(v)
             for k, v in vars(type(obs_cfg)).items()
             if not k.startswith("_") and not callable(v)}
    attrs.update({k: _freeze_obs_cfg_value(v) for k, v in vars(obs_cfg).items()
                  if not k.startswith("_")})
    return type(f"Frozen{type(obs_cfg).__name__}", (), attrs)()


def _fingerprint_obj(value):
    """Stable value summary for the obs-operator fields that define H(x)."""
    if isinstance(value, torch.Tensor):
        v = value.detach().to(torch.float64).cpu()
        return ("tensor", tuple(v.shape), str(v.dtype), v.numpy().tobytes().hex())
    if is_dataclass(value) and not isinstance(value, type):
        return (type(value).__name__, tuple((f.name, _fingerprint_obj(getattr(value, f.name)))
                                           for f in fields(value)))
    if hasattr(value, "_fields") and isinstance(value, tuple):
        return (type(value).__name__, tuple((name, _fingerprint_obj(getattr(value, name)))
                                           for name in value._fields))
    if isinstance(value, (tuple, list)):
        return tuple(_fingerprint_obj(v) for v in value)
    if isinstance(value, dict):
        return tuple(sorted((repr(k), _fingerprint_obj(v)) for k, v in value.items()))
    return value


def _obs_cfg_fingerprint(obs_cfg) -> str:
    """Digest the dual-relevant operator identity used by batched_clear_bt."""
    import hashlib
    fields_to_hash = (
        "profile_cfg", "input_cfg", "t_ref", "q_ref",
        "t_blend_octaves", "q_blend_octaves")
    payload = tuple((name, _fingerprint_obj(getattr(obs_cfg, name, None)))
                    for name in fields_to_hash)
    run_k = getattr(obs_cfg, "run_k", None)
    run_k_solar = getattr(run_k, "solar_channels", None)
    payload += (("run_k.solar_channels", _fingerprint_obj(run_k_solar)),)
    return hashlib.sha256(repr(payload).encode()).hexdigest()


@dataclass(frozen=True)
class _FrozenCallable:
    fn: object
    solar_channels: object = None

    def __call__(self, *args, **kwargs):
        return self.fn(*args, **kwargs)


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
    policy: dict = None                    # 게이트 opt-in 상태 (감사, 재검토 M1)
    cvt: "dict | None" = None              # CVT 감사 레코드 (spec 경로만)


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
    allow_zero_valid_slots: bool = False,
    require_obs_slots: bool = True,
    policy: "ObsGatePolicy | None" = None,
    cvt: "CvtSpec | None" = None,
) -> DualMinimizeResult:
    """결합 J(v_x, v_θ) 를 단일 L-BFGS 로 최소화 (모듈 docstring 참조).

    obs_eval: (t, x_t) -> (j_t, adj_t, n_valid_t[, signature_t]) | None.
    **2-튜플은 거부된다** (재검토 blocker-1: 기존 상태의존-mask obs_eval을 그대로
    꽂으면 게이밍 방어가 전부 우회됨 — dual에서는 n_valid 필수). signature_t
    (예: mask의 sha256, all-sky면 cfrac-regime 해시 결합)를 주면 **동일-개수
    치환 게이밍**(어려운 항을 빼고 쉬운 항을 넣어 n_valid 유지)도 잡는다
    (blocker-2). 표준 clear-sky 경로는 make_dual_frozen_obs_eval 어댑터 사용.

    cvt: None(기본) = 기존 선형 상태-CVT, byte-identical 레거시 경로.
    spec 지정 = 필드별 add/mul 하이브리드 (da_cvt) — 체인룰이
    ∂J/∂v_x = v_x + jac ⊙ adj_x0 로 바뀐다 (jac = ∂x0/∂v_x, 매 closure 재평가).
    obs_eval 서명은 **v-독립**(θ_b/배경 궤적 동결)이어야 한다 — live-state
    regime을 해시하는 어댑터는 어떤 상태 CVT와도 양립 불가 (서명 게이트는
    obs-구성 드리프트를 잡는 것이지 분석 증분을 잡는 게 아니다). obs_eval에
    connected_fields 속성(직접 H-민감 필드 tuple)이 있으면 t=0 단독 슬롯
    구성에서 확정 기울기-0 필드의 σ>0 지정을 거부한다 (V7).
    """
    if policy is None:
        policy = ObsGatePolicy(require_signature=require_signature,
                               allow_zero_valid_slots=allow_zero_valid_slots,
                               require_obs_slots=require_obs_slots)
    elif (require_signature, allow_zero_valid_slots, require_obs_slots) != (True, False, True):
        raise ValueError(
            "pass gate options through ObsGatePolicy OR legacy kwargs, not both "
            "— conflicting double specification would be silently ignored")
    _validate_state_shapes(b_sigma, xb, arg="b_sigma", ref_name="xb")
    if cvt is not None:
        validate_cvt(xb, b_sigma, cvt, window_config.active_fields)
    _connected = getattr(obs_eval, "connected_fields", None)
    _sigma_pos = (tuple(f for f in State._fields
                        if bool((getattr(b_sigma, f) > 0).any()))
                  if cvt is not None else ())
    sig_x = _stack(b_sigma)
    v_x = torch.zeros_like(sig_x, requires_grad=True)
    v_th = torch.zeros(4, **_F64, requires_grad=True)

    trace: list = []
    counters = {"windows": 0}
    last = {"jb": 0.0, "jth": 0.0, "jobs": 0.0, "gx": 0.0, "gth": 0.0}
    frozen_n_valid: dict = {}

    def closure() -> torch.Tensor:
        with torch.no_grad():
            x0, jac_x = cvt_apply(xb, b_sigma, v_x, cvt)
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
            if isinstance(out, ObsEvalResult):
                out = (out.j, out.adj, out.n_valid, out.signature)
            elif not policy.allow_tuple_returns:
                raise TypeError(
                    "production dual obs_eval must return ObsEvalResult — "
                    "tuple returns are error-prone; opt in via "
                    "ObsGatePolicy(allow_tuple_returns=True) for synthetic tests")
            elif not counters.get("warned_tuple"):
                counters["warned_tuple"] = True          # 호출당 1회 (라인서치 반복 소음 방지)
                import warnings
                warnings.warn("tuple obs_eval returns are deprecated — return "
                              "ObsEvalResult", DeprecationWarning, stacklevel=2)
            if len(out) == 2:
                raise RuntimeError(
                    "dual minimizer requires obs_eval to return "
                    "(j, adj, n_valid[, signature]) — a 2-tuple obs_eval "
                    "bypasses the mask-gaming defenses (use "
                    "make_dual_frozen_obs_eval for the clear-sky path)")
            if len(out) == 4:
                j_t, adj_t, n_valid, sig = out
                if policy.require_signature:
                    # blocker: (…, None)/빈 문자열 서명은 "서명 있음"으로 위장해
                    # 동일-개수 치환 방어를 사실상 끈다 — 비어있지 않은
                    # str/bytes 강제
                    if not isinstance(sig, (str, bytes)) or len(sig) == 0:
                        raise RuntimeError(
                            "production dual obs_eval must return a NON-EMPTY "
                            "str/bytes valid/regime signature (got "
                            f"{type(sig).__name__}: {sig!r})")
                if isinstance(sig, bytes):
                    sig = sig.hex()          # trace JSON 직렬화 보장 (재검토 H1)
            else:
                if policy.require_signature:
                    raise RuntimeError(
                        "production dual obs_eval must return a valid/regime "
                        "signature (4th element) — without it same-count mask "
                        "substitution is undetectable; pass "
                        "require_signature=False only for synthetic tests")
                j_t, adj_t, n_valid = out
                sig = None
            # n_valid 엄격 검증 (재검토 H2): bool은 int 서브클래스, float은 조용한
            # truncation, 음수는 zero-valid 게이트 우회 — 전부 거부
            if isinstance(n_valid, bool) or not isinstance(n_valid, int):
                raise TypeError(
                    f"n_valid must be a plain int (got {type(n_valid).__name__})")
            if n_valid < 0:
                raise ValueError(f"n_valid must be >= 0 (got {n_valid})")
            n_valid_acc[t] = (n_valid, sig)
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
            j_tensor = torch.as_tensor(j_t, dtype=torch.float64)
            if j_tensor.ndim != 0:
                raise ValueError(
                    f"obs_eval j must be scalar; got shape {tuple(j_tensor.shape)}")
            if not bool(torch.isfinite(j_tensor)):
                raise FloatingPointError("obs_eval j is non-finite")
            jobs_acc.append(j_tensor.detach())
            return adj_t

        res = run_da_window(x0, forcings, obs_adjoint, cfg_i)
        counters["windows"] += 1
        # 우회 봉쇄 (stop-review): n_valid 감소 대신 슬롯 자체를 None으로
        # 사라지게 하면 항 전체가 조용히 J에서 탈락한다 — 보고 슬롯 집합의
        # 변화(소멸·신규 모두)도 게이밍으로 간주해 거부한다.
        if counters["windows"] == 1:
            # H1: 슬롯이 하나도 보고되지 않는 것도 "prior-only 성공" 위장 —
            # 관측시각 인덱스 불일치·y_by_time 연결 오류가 조용히 성공처럼 보임
            if policy.require_obs_slots and not n_valid_acc:
                raise RuntimeError(
                    "no observation slots reported in the first closure — "
                    "likely an obs-time index mismatch; pass "
                    "require_obs_slots=False only for deliberate no-obs runs")
            # zero-valid 슬롯 거부를 최소화기 레벨로 (stop-review: 어댑터만의
            # 거부는 커스텀 obs_eval로 우회 가능) — 보고는 하되 유효 항이 0인
            # 슬롯은 "prior-only 성공" 위장 경로이므로 기본 거부
            if not policy.allow_zero_valid_slots:
                empty = [tt for tt, (nv, _) in n_valid_acc.items() if nv == 0]
                if empty:
                    raise RuntimeError(
                        f"obs slots {sorted(empty)} report n_valid=0 — an "
                        "all-masked slot disguises configuration errors as a "
                        "prior-only success; pass allow_zero_valid_slots=True "
                        "only if these slots are expected empty")
            frozen_n_valid.update(n_valid_acc)
            # V7 (spec 경로 전용): 기울기-보유(n_valid>0) 슬롯이 전부 t=0이면
            # M^T 결합이 없어 직접 H-민감(connected) 밖 필드의 adj_x0가 확정 0
            # — prior가 v=0으로 pin하면서 '제어됨'으로 기록되는 위장 구성을
            # 거부. 기울기-보유 t≥1 슬롯이 있으면 모든 필드가 M^T-도달 가능
            # (유효 0개 슬롯은 J에 기여하지 않으므로 증거로 세지 않는다).
            if cvt is not None and _connected is not None:
                bearing = [t for t, (nv, _) in frozen_n_valid.items()
                           if nv > 0]
                dead = ([f for f in _sigma_pos if f not in _connected]
                        if bearing and all(t == 0 for t in bearing) else [])
                if dead:
                    raise ValueError(
                        f"b_sigma > 0 for fields {dead} with only t=0 obs "
                        f"slots and connected_fields={_connected} — their "
                        "gradient is guaranteed exact-zero (no M^T coupling); "
                        "zero their sigma or add a t>=1 observation")
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
            # ∂J/∂v_x = v_x + jac ⊙ ∂J/∂x0 (선형이면 jac = σ_b — 기존과 동일)
            g_x = v_x.detach() + jac_x * _stack(res.adj_x0)
            # ∂J/∂v_θ = v_θ + σ_log · θ · ∂J/∂θ  (θ = θb·exp(σv) 체인)
            gp = torch.zeros(4, **_F64)
            if res.grad_params is not None:
                for i, n in enumerate(PNAMES):          # 비활성(σ=0)은 키 부재 → 0
                    if n in res.grad_params:
                        gp[i] = res.grad_params[n].to(torch.float64)
            theta_now = torch.stack([params_live[i].detach() for i in range(4)])
            g_th = v_th.detach() + param_prior.sigma_log * theta_now * gp
            j = j_b + j_th + j_obs
            for name, tt_ in (("j_state", j_b), ("j_theta", j_th),
                              ("j_obs", j_obs), ("j_total", j),
                              ("g_x", g_x), ("g_th", g_th)):
                if not bool(torch.isfinite(tt_).all()):
                    raise FloatingPointError(
                        f"{name} became non-finite in the dual closure — "
                        "corrupted loss/gradient must not reach L-BFGS")
            v_x.grad = g_x
            v_th.grad = g_th
            trace.append(dict(total=float(j), j_state=float(j_b),
                              j_theta=float(j_th), j_obs=float(j_obs),
                              n_valid={k: v[0] for k, v in n_valid_acc.items()} or None,
                              signature={k: v[1] for k, v in n_valid_acc.items()} or None))
            last.update(jb=float(j_b), jth=float(j_th), jobs=float(j_obs),
                        gx=float(g_x.norm()), gth=float(g_th.norm()))
        return j

    opt = torch.optim.LBFGS(
        [v_x, v_th], max_iter=max_iter, history_size=history_size,
        line_search_fn="strong_wolfe", tolerance_grad=tolerance_grad)
    opt.step(closure)

    with torch.no_grad():
        x_a, _ = cvt_apply(xb, b_sigma, v_x, cvt)
        theta_a = params_from_vtheta(param_prior, v_th.detach(), live=False)
        cvt_rec = (build_cvt_record(cvt, b_sigma, xb, x_a)
                   if cvt is not None else None)
    return DualMinimizeResult(
        x_analysis=x_a, theta_analysis=theta_a,
        v_state=v_x.detach(), v_theta=v_th.detach(), j_trace=trace,
        jb_final=last["jb"], jtheta_final=last["jth"], jobs_final=last["jobs"],
        n_window_evals=counters["windows"],
        grad_norm_final=last["gx"], grad_theta_norm_final=last["gth"],
        policy=policy.as_dict(), cvt=cvt_rec)


def make_dual_frozen_obs_eval(xb: State, forcings: Sequence[Forcing],
                              y_by_time: dict, obs_cfg,
                              window_config: WindowConfig,
                              param_prior: ParamPrior, *,
                              allow_zero_valid_slots: bool = False,
                              policy: "ObsGatePolicy | None" = None) -> Callable:
    """clear-sky 표준 dual obs_eval — 동결 QC + n_valid + mask 서명.

    동결 기준은 **θ_b 배경 궤적**: collect_window_trajectory(전방-전용,
    run_da_window와 bitwise 동일 forward 의미론 — η/η_pre 포함)로 M(x_b→t; θ_b)
    슬롯 상태를 채취하고, 거기서 rad_quality를 평가해 mask = (관측 quality==0)
    ∧ (배경 rad_quality==0) 를 동결한다. θ_b는 **param_prior에서** 취한다 (재검토 #3:
    window_config.params와 prior.theta_b의 조용한 불일치 차단 — 프로브 params를
    prior 기준으로 강제 주입).

    손실은 compute_obs_loss (Huber + full-shape/bias/sigma/masked-NaN 방어,
    재검토 blocker-1) — 수제 quadratic이 우회하던 안전장치 복원. gradient는
    clear-sky connected 필드(th/qv)에 대해 autograd.grad(allow_unused=False) —
    구조적 그래프 단절을 조용한 0 대신 거부 (blocker-2).

    y_by_time: {t: (y_bt (B,nch), y_rq (B,nch)[, bias])} — superob 권장.
    반환 obs_eval: ObsEvalResult(j, adj, n_valid, sha256(t|shape|dtype|mask)).
    """
    import dataclasses
    import hashlib
    from .da_driver import batched_clear_bt
    from .da_window import collect_window_trajectory
    from .obs.obs_loss import compute_obs_loss

    # H3: policy/legacy kwarg 동시 지정 충돌 거부 (최소화기와 동일 규율)
    if policy is not None:
        if allow_zero_valid_slots is not False:
            raise ValueError(
                "pass zero-valid policy through ObsGatePolicy OR the legacy "
                "kwarg, not both — silent double specification forbidden")
        allow_zero_valid_slots = policy.allow_zero_valid_slots
    obs_cfg_f = _freeze_obs_cfg(obs_cfg)
    operator_fingerprint = _obs_cfg_fingerprint(obs_cfg_f)
    obs_sigma_f = torch.as_tensor(obs_cfg_f.obs_sigma, dtype=torch.float64).detach().clone()
    T_win = len(forcings)
    for t, entry in y_by_time.items():
        # H2: 시각 키는 plain int 스텝 인덱스 — bool은 int 서브클래스, float은
        # 수집기 int() 캐스팅과 어댑터 조회 키가 어긋나 KeyError 계열 혼란
        if isinstance(t, bool) or not isinstance(t, int):
            raise TypeError(f"obs time key must be a plain int step index; got {t!r}")
        if t < 0 or t > T_win:
            raise ValueError(f"obs time {t} outside window [0, {T_win}]")
        if len(entry) not in (2, 3):                    # 초과 원소 침묵 무시 금지
            raise ValueError(
                f"y_by_time[{t}] must be (y_bt, y_rq[, bias]) — got "
                f"{len(entry)} elements")

    theta_b_params = params_from_vtheta(param_prior, torch.zeros(4, **_F64),
                                        live=False)
    probe_cfg = dataclasses.replace(window_config, params=theta_b_params,
                                    param_grads=False)
    # forward-전용 수집기 (재검토 H2): run_da_window 프로브는 전 스텝 VJP
    # 비용을 낸다 — 동일 forward 의미론(bitwise 게이트 고정), backward 없음
    try:
        traj = collect_window_trajectory(xb, forcings, probe_cfg,
                                         set(y_by_time))
    except ValueError as e:
        raise ValueError(
            f"{e} — check y_by_time step indices (T={len(forcings)})") from e

    frozen: dict = {}
    for t, entry in y_by_time.items():
        y_bt, y_rq = entry[0], entry[1]
        with torch.no_grad():
            _, rad_q, _ = batched_clear_bt(traj[t],
                                           forcings[min(t, len(forcings) - 1)],
                                           obs_cfg_f)
        # shape 엄격 검증 (재검토 H1): [nch]·[B,1] 등이 broadcasting으로 조용히
        # [B,nch] mask가 되는 경로 차단 — superob 규약은 full-shape (B,nch)
        for nm, arr in (("y_bt", y_bt), ("y_rq", y_rq)):
            if tuple(arr.shape) != tuple(rad_q.shape):
                raise ValueError(
                    f"{nm} shape {tuple(arr.shape)} != H(x) rad_quality "
                    f"{tuple(rad_q.shape)} at t={t} — pass the full [B,nch] "
                    "field (silent broadcast is forbidden)")
        # y_rq는 superob quality flag의 동결본이다. keep-mask/weight가 아니므로
        # 0은 사용 가능, nonzero는 플래그됨(RTTOV/obs 관례)으로 해석한다.
        # NaN/Inf와 음수만 설정 오류로 거부한다.
        y_rq_f = torch.as_tensor(y_rq, dtype=torch.float64).detach().clone()
        if not bool(torch.isfinite(y_rq_f).all()):
            raise ValueError(f"y_rq at t={t} must be finite")
        if bool((y_rq_f < 0.0).any()):
            raise ValueError(f"y_rq at t={t} must be non-negative quality flags")
        m = ((y_rq_f == 0) & (rad_q.to(torch.float64) == 0)).double()
        n_valid = int(m.sum())
        if n_valid == 0 and not allow_zero_valid_slots:
            # zero-valid 슬롯의 조용한 no-op은 설정 오류(채널 매핑·단위·계수)를
            # "관측 없는 성공"으로 위장시킨다 (재검토 H3) — 명시적 opt-in만 허용
            raise RuntimeError(
                f"frozen mask has zero valid obs at t={t} — likely a channel/"
                "unit/coefficient misconfiguration; pass "
                "allow_zero_valid_slots=True only if this slot is expected empty")
        # H1: 관측값·bias도 생성 시점에 동결(clone) — 외부 in-place 수정이
        # 서명은 그대로 둔 채 목적함수를 바꾸는 경로 차단; obs_hash를 서명에
        # 합성해 관측 정체까지 고정. y_rq는 계산상 binary usable/flagged로만
        # 해석하지만, 원본 quality-code bytes도 감사용 signature에는 보존한다.
        entry = y_by_time[t]
        y_bt_f = torch.as_tensor(entry[0], dtype=torch.float64).detach().clone()
        bias_f = (None if len(entry) < 3 or entry[2] is None
                  else torch.as_tensor(entry[2], dtype=torch.float64).detach().clone())
        payload = (f"t={t}|shape={tuple(m.shape)}|dtype={m.dtype}|".encode()
                   + m.cpu().numpy().tobytes()
                   + b"|obs|" + y_bt_f.cpu().numpy().tobytes()
                   + b"|y_rq|" + y_rq_f.cpu().numpy().tobytes()
                   + (f"|sigma_shape={tuple(obs_sigma_f.shape)}|"
                      f"sigma_dtype={obs_sigma_f.dtype}|".encode())
                   + obs_sigma_f.cpu().numpy().tobytes()
                   + b"|operator|" + operator_fingerprint.encode()
                   + (b"" if bias_f is None
                      else b"|bias|" + bias_f.cpu().numpy().tobytes()))
        sig = hashlib.sha256(payload).hexdigest()
        frozen[t] = _FrozenObsSlot(mask=m, n_valid=n_valid, signature=sig,
                                   y_bt=y_bt_f, bias=bias_f, sigma=obs_sigma_f)

    def obs_eval(t, x_t):
        slot = frozen.get(t)
        if slot is None:
            return None
        bt, _, leaves = batched_clear_bt(x_t, forcings[min(t, len(forcings) - 1)],
                                         obs_cfg_f)
        obs = {"bt": slot.y_bt}
        if slot.bias is not None:
            obs["bias"] = slot.bias
        j = compute_obs_loss(bt.to(torch.float64), obs, slot.mask,
                             sigma=slot.sigma)
        zeros = torch.zeros_like(leaves.th)
        if slot.n_valid > 0:
            # clear-sky connected 필드는 th/qv — None grad는 구조적 단절
            g_th, g_qv = torch.autograd.grad(j, [leaves.th, leaves.qv],
                                             allow_unused=False)
        else:
            g_th, g_qv = zeros, zeros
        adj = State(th=g_th, qv=g_qv, qc=zeros, qr=zeros, qi=zeros, qs=zeros,
                    qg=zeros, nccn=zeros, nc=zeros, ni=zeros, nr=zeros, bg=zeros)
        return ObsEvalResult(j=float(j.detach()), adj=adj,
                             n_valid=slot.n_valid, signature=slot.signature)

    # 직접 H-민감 필드 표기 — run_dual_minimizer V7 (t=0 단독 슬롯 검사) 소비.
    # 서명은 여기서 θ_b/배경 궤적에 동결되어 v-독립이다 — 상태 CVT 종류와
    # 무관하게 유효한 계약 (live-state regime 해시는 어떤 CVT와도 양립 불가).
    obs_eval.connected_fields = ("th", "qv")
    return obs_eval
