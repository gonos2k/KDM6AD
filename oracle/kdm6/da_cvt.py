"""필드별 하이브리드 CVT — add(선형) / mul(delta-form log) + 대각 Jacobian.

CVT 일반화의 단일 진실 원천. 필드 i의 모드에 따라:

  add:  x0 = xb + σ·v                     jac = σ            (σ 절대 단위)
  mul:  x0 = xb + (xb+ε)·expm1(σ·v)       jac = σ·(xb+ε)·exp(σ·v)   (σ log-공간)

mul은 ε=0에서 xb·exp(σv)와 수학적으로 동일: xb>0 셀의 양수성이 구조적으로
보장되고, xb=0 셀은 x0=0으로 자기-배제된다. 항등식(torch.equal 정밀도로
테스트 고정; xb=−0.0 셀은 −0.0+0.0=+0.0 IEEE 합산 규칙으로 부호 비트만 바뀔
수 있고 이는 레거시 선형 경로와 동일): expm1(±0)=±0, exp(±0)=1 →
v=0 ⇒ x0==xb, σ=0 성분 ⇒ 임의 v에 배경 고정 + jac=0 ⇒ 기울기 행 = v 행
⇒ L-BFGS가 그 행을 영원히 0으로 유지(zero-row 불변).

정직한 fp64 하계: expm1은 u ≲ −37에서 정확히 −1로 반올림되므로 참 하계는
x0 ≥ −ε − 4·U64·(xb+ε) (엄격한 x0 > −ε가 아님). 물리적으로 무시 가능하며
모델 entry clamp가 흡수한다.

ε>0 opt-in: 0-배경 셀의 생성/완전 제거를 대칭 비용 (ln((q+ε)/ε))²/(2σ²)로
허용하고 jac ≥ σ·ε로 제거 방향 기울기를 유지한다. 단, 현행 frozen all-sky
H에서는 clear 셀 생성 기울기가 도달 불가(cfrac detached gate,
model_profile_builder)이므로 합성 관측/외부루프 재선형화 용도로만 유효 —
기본은 ε=0 (순수 log).

q–n 퇴화 주의: 대각 B에서는 radiance를 크기 이동(q/n 비율)으로도 맞출 수
있다 — 잠정 완화는 n-필드 σ를 q보다 조임(0.3 vs 0.5) + record의 ratio_minmax
감사. 다변량 q–n 균형은 범위 밖(로드맵).
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

import torch

from .constants import NCCN_MAX, NCCN_MIN
from .state import State

_FIELDS = State._fields                     # 12필드 순서 고정
U64 = 2.220446049250313e-16                 # fp64 unit roundoff
NI_ENTRY_MAX = 1.0e6                        # runtime.py entry clamp: ni ∈ [0, 1e6]
_ENTRY_BOUNDS = {"ni": (0.0, NI_ENTRY_MAX), "nccn": (NCCN_MIN, NCCN_MAX)}
_HEADROOM_SIGMAS = 3.0                      # clamp까지 3σ 여유 요구 (validate V4)
_SIGMA_LOG_MAX = 2.0                        # mul σ 상한 — 절대단위 σ 오인 방지


def _stack(s: State) -> torch.Tensor:
    """State → (12, B, K) fp64 텐서."""
    return torch.stack([getattr(s, f).to(torch.float64) for f in _FIELDS])


def _unstack(t: torch.Tensor) -> State:
    return State(**{f: t[i] for i, f in enumerate(_FIELDS)})


@dataclass(frozen=True)
class CvtSpec:
    """필드별 CVT 계열 — State._fields 순서 12개 (모듈 docstring 참조)."""
    mode: tuple                             # 12 × "add" | "mul"
    eps: tuple                              # 12 × float, finite, ≥ 0; add ⇒ 0

    def __post_init__(self):
        if len(self.mode) != 12 or len(self.eps) != 12:
            raise ValueError("mode/eps must have length 12 (State._fields order)")
        for f, m, e in zip(_FIELDS, self.mode, self.eps):
            if m not in ("add", "mul"):
                raise ValueError(f"{f}: mode must be 'add'|'mul' (got {m!r})")
            if not math.isfinite(e) or e < 0:
                raise ValueError(f"{f}: eps must be finite and >= 0 (got {e!r})")
            if m == "add" and e != 0.0:
                raise ValueError(f"{f}: eps > 0 requires mode 'mul'")
        # −0.0/int 정규화 — 동치 spec은 동일 fingerprint 여야 함
        object.__setattr__(self, "eps",
                           tuple(float(e) + 0.0 for e in self.eps))

    def as_dict(self) -> dict:
        return {"version": 1,
                "mode": {f: m for f, m in zip(_FIELDS, self.mode)},
                "eps": {f: float(e) for f, e in zip(_FIELDS, self.eps)}}

    @staticmethod
    def from_dict(d: dict) -> "CvtSpec":
        if d.get("version") != 1:
            raise ValueError(f"unsupported CvtSpec version {d.get('version')!r}"
                             " (expected 1)")
        if set(d["mode"]) != set(_FIELDS) or set(d["eps"]) != set(_FIELDS):
            raise ValueError("mode/eps keys must be exactly State._fields")
        return CvtSpec(mode=tuple(d["mode"][f] for f in _FIELDS),
                       eps=tuple(float(d["eps"][f]) for f in _FIELDS))

    def fingerprint(self) -> str:
        """이름-결합 sha256 — 필드 순서 재배열/모드 변경/ε 변경에 민감."""
        payload = "cvt-v1|" + "|".join(
            f"{f}:{m}:{float(e).hex()}"
            for f, m, e in zip(_FIELDS, self.mode, self.eps))
        return hashlib.sha256(payload.encode()).hexdigest()


CVT_LINEAR = CvtSpec(mode=("add",) * 12, eps=(0.0,) * 12)


def cvt_apply(xb: State, b_sigma: State, v: torch.Tensor,
              spec: "CvtSpec | None" = None) -> "tuple[State, torch.Tensor]":
    """CVT forward와 대각 Jacobian ∂x0/∂v를 한 번의 평가로 (lockstep — 드리프트 불가).

    spec=None — 레거시 경로, byte-identity 계약: 기존 선형 CVT 표현식 그대로,
    검증·finite 가드 없음. 이 분기를 재구성하지 말 것.
    spec 경로 — 필드별 루프(torch.where 미사용: where-backward 0·inf NaN 함정
    회피 + add 행의 불필요한 exp 생략), 비유한 x0/jac은 FloatingPointError.
    """
    xs, sig = _stack(xb), _stack(b_sigma)
    if spec is None:
        return _unstack(xs + sig * v), sig

    rows, jrows = [], []
    for i, (m, e) in enumerate(zip(spec.mode, spec.eps)):
        if m == "add":
            rows.append(xs[i] + sig[i] * v[i])
            jrows.append(sig[i])
        else:
            u = sig[i] * v[i]
            base = xs[i] + e
            rows.append(xs[i] + base * torch.expm1(u))
            jrows.append(sig[i] * base * torch.exp(u))
    x = torch.stack(rows)
    jac = torch.stack(jrows)
    if not bool(torch.isfinite(x).all() and torch.isfinite(jac).all()):
        raise FloatingPointError(
            "cvt_apply produced non-finite x0/jac (exp overflow in a mul "
            "field?) — reduce sigma or bound v")
    return _unstack(x), jac


def validate_cvt(xb: State, b_sigma: State, spec: CvtSpec,
                 active_fields: "tuple | None" = None) -> None:
    """위험 구성 fail-fast — spec 경로 전용 (cvt=None 레거시는 미검증 유지).

    V2  σ finite & ≥ 0
    V2b mul 필드 σ ≤ 2 (절대단위 σ를 mul 필드에 넘긴 실수 방지)
    V3  mul 필드: xb+ε ≤ 0 인 셀은 σ=0 이어야 함 (음수 배경 부호역전과
        ε=0·xb=0 퇴화 pin 거부 — 기존 'σ=0 at q=0' 규칙의 강제화)
    V4  entry clamp headroom(ni/nccn): 3σ 지점의 참 변환값이 clamp 경계를
        넘는 셀은 σ=0. mul의 참 3σ 값은 (xb+ε)e^{±3σ} − ε, add는 xb ± 3σ.
        (경계 밖 교차는 j_b > 4.5/셀 비용 + plateau에서 adj=0 → prior 복원으로
        자가 치유되지만, 그 DOF를 '제어됨'으로 기록하는 것 자체가 거짓)
    V5  active_fields 지정 시 σ>0 필드는 반드시 포함 — 불일치는 창 adjoint가
        조용히 0이 되어 prior가 v=0으로 pin하는 것과 구분 불가
    """
    for i, f in enumerate(_FIELDS):
        sig = getattr(b_sigma, f).to(torch.float64)
        xbf = getattr(xb, f).to(torch.float64)
        if not bool(torch.isfinite(sig).all()):
            raise ValueError(f"b_sigma.{f} must be finite")
        if bool((sig < 0).any()):
            raise ValueError(f"b_sigma.{f} must be >= 0")
        e = float(spec.eps[i])
        if spec.mode[i] != "mul":
            if f in _ENTRY_BOUNDS:            # V4 (add): xb ± 3σ, σ 절대 단위
                lo, hi = _ENTRY_BOUNDS[f]
                head = _HEADROOM_SIGMAS * sig
                bad = (sig > 0) & ((xbf + head >= hi) | (xbf - head <= lo))
                if bool(bad.any()):
                    raise ValueError(
                        f"b_sigma.{f} > 0 within {_HEADROOM_SIGMAS:g}-sigma of "
                        f"an entry clamp bound [{lo:g}, {hi:g}] "
                        f"({int(bad.sum())} cells) — zero sigma there")
            continue
        if bool((sig > _SIGMA_LOG_MAX).any()):
            raise ValueError(
                f"b_sigma.{f} > {_SIGMA_LOG_MAX} — 'mul' fields take a "
                "log-space sigma (absolute-units sigma passed by mistake?)")
        bad = (sig > 0) & (xbf + e <= 0)
        if bool(bad.any()):
            raise ValueError(
                f"b_sigma.{f} > 0 where xb + eps <= 0 ({int(bad.sum())} cells)"
                " — a mul control needs positive background (or eps > 0)")
        if f in _ENTRY_BOUNDS:
            lo, hi = _ENTRY_BOUNDS[f]
            head = _HEADROOM_SIGMAS * sig
            # 참 3σ 변환값: (xb+ε)e^{±3σ} − ε (−ε 누락은 ε만큼 반보수적)
            over = (sig > 0) & ((xbf + e) * torch.exp(head) - e >= hi)
            if bool(over.any()):
                raise ValueError(
                    f"b_sigma.{f} > 0 within {_HEADROOM_SIGMAS:g}-sigma of the "
                    f"entry clamp upper bound {hi:g} ({int(over.sum())} cells)"
                    " — zero sigma there (make_default_cvt does this)")
            if lo > 0:
                under = (sig > 0) & ((xbf + e) * torch.exp(-head) - e <= lo)
                if bool(under.any()):
                    raise ValueError(
                        f"b_sigma.{f} > 0 within {_HEADROOM_SIGMAS:g}-sigma of "
                        f"the entry clamp lower bound {lo:g} "
                        f"({int(under.sum())} cells) — zero sigma there")
    if active_fields is not None:
        dead = [f for f in _FIELDS
                if f not in active_fields
                and bool((getattr(b_sigma, f) > 0).any())]
        if dead:
            raise ValueError(
                f"b_sigma > 0 for fields not in active_fields: {dead} — their "
                "window adjoint is zero-masked, so the prior would silently "
                "pin v=0 while the field is recorded as controlled")


def make_default_cvt(xb: State, *,
                     th_sigma: float = 0.8, qv_sigma: float = 0.08,
                     qv_levels: int = 12, q_hydro_sigma: float = 0.5,
                     n_hydro_sigma: float = 0.3, enable_indirect: bool = False,
                     sigma_overrides: "dict | None" = None,
                     eps_overrides: "dict | None" = None,
                     ) -> "tuple[CvtSpec, State]":
    """권고 기본값 빌더 — 반환 직전 validate_cvt를 호출하므로 산출물은 항상
    검증 통과 상태다 (V3/V4 zeroing 내장 + 범위 밖 override는 여기서 거부).

    σ 기본값은 검증된 기후학이 아니라 문서화된 출발점이다(record에 기록됨).
    qv_levels의 k는 State (B,K)의 마지막 축 인덱스, k=0 = 최하층(WRF bottom-up).
    qr/qg/nr는 관측 직접 민감도가 없어(M^T 경유만 — t≥1 관측 필요) 기본 제외,
    enable_indirect=True로 opt-in. nccn/bg 기본 제외 — sigma_overrides로 opt-in
    (bg는 어떤 관측 경로에도 없음 — 필요해지면 θ-식 파라미터 CVT로 승격이 옳다).
    직접 H 민감도 주의: qc/qi/qs/nc/ni의 '직접' 민감도는 all-sky 연산자 경유다
    — clear-sky 전용 obs 구성에서는 이들도 M^T 경유(t≥1 관측 필요)로만 제어된다.
    """
    so = dict(sigma_overrides or {})
    eo = dict(eps_overrides or {})
    unknown = (set(so) | set(eo)) - set(_FIELDS)
    if unknown:
        raise ValueError(
            f"unknown field names in overrides: {sorted(unknown)} — a typo "
            "here silently pins the intended field to background")
    base = {"th": th_sigma, "qv": qv_sigma,
            "qc": q_hydro_sigma, "qi": q_hydro_sigma, "qs": q_hydro_sigma,
            "qr": q_hydro_sigma if enable_indirect else 0.0,
            "qg": q_hydro_sigma if enable_indirect else 0.0,
            "nc": n_hydro_sigma, "ni": n_hydro_sigma,
            "nr": n_hydro_sigma if enable_indirect else 0.0,
            "nccn": 0.0, "bg": 0.0}
    base.update(so)
    mode = tuple("add" if f == "th" else "mul" for f in _FIELDS)
    spec = CvtSpec(mode=mode,
                   eps=tuple(float(eo.get(f, 0.0)) for f in _FIELDS))

    # 원시 σ 값을 per-cell zeroing보다 먼저 검증 — clamp 필드에서 무효 값
    # (NaN/음수/절대단위 오인)이 V3/V4 마스크에 소독되어 '조용한 전-셀 pin'으로
    # 위장되는 것을 차단 (정상 σ의 headroom zeroing과 구성 오류를 구분)
    for i, f in enumerate(_FIELDS):
        v = float(base[f])
        if not math.isfinite(v) or v < 0:
            raise ValueError(f"{f}: sigma must be finite and >= 0 (got {v!r})")
        if mode[i] == "mul" and v > _SIGMA_LOG_MAX:
            raise ValueError(
                f"{f}: sigma {v} > {_SIGMA_LOG_MAX} — 'mul' fields take a "
                "log-space sigma (absolute-units sigma passed by mistake?)")

    sigs = {}
    for i, f in enumerate(_FIELDS):
        xbf = getattr(xb, f).to(torch.float64)
        s = torch.full_like(xbf, float(base[f]))
        if f == "qv":
            k = torch.arange(xbf.shape[-1], device=xbf.device)
            s = torch.where(k < qv_levels, s, torch.zeros_like(s))
        if mode[i] == "mul":
            e = spec.eps[i]
            zero = torch.zeros_like(s)
            s = torch.where(xbf + e > 0, s, zero)                       # V3
            if f in _ENTRY_BOUNDS:                                      # V4
                lo, hi = _ENTRY_BOUNDS[f]
                head = _HEADROOM_SIGMAS * s
                s = torch.where((xbf + e) * torch.exp(head) - e < hi, s, zero)
                if lo > 0:
                    s = torch.where((xbf + e) * torch.exp(-head) - e > lo,
                                    s, zero)
        sigs[f] = s
    b_sigma = State(**sigs)
    validate_cvt(xb, b_sigma, spec)         # by-construction 보증을 실검사로
    return spec, b_sigma


def build_cvt_record(spec: CvtSpec, b_sigma: State, xb: State,
                     x_a: State) -> dict:
    """JSON 직렬화 가능한 감사 레코드 (spec 경로 전용 — 레거시는 record=None).

    b_sigma 자체는 저장하지 않는다: sha는 검증 전용이며, 재현은 호출자가 보관한
    b_sigma + spec round-trip(CvtSpec.from_dict)으로 한다.
      n_controlled  σ>0 셀 수 — 정직한 DOF 집계 (빌더 zeroing 반영)
      n_created     mul: xb≤0 → x_a>0 셀 수 (ε=0이면 항상 0)
      ratio_minmax  mul: xb>0 셀의 x_a/xb 최소·최대 — 크기이동/제거깊이 감사
      min_analysis  mul: x_a 최솟값 — −ε 하계(clamp 폐기량) 감사
    """
    with torch.no_grad():
        h = hashlib.sha256()
        for f in _FIELDS:
            t = getattr(b_sigma, f).detach().to(torch.float64).contiguous()
            h.update(f"{f}|{tuple(t.shape)}|".encode())
            h.update(t.cpu().numpy().tobytes())
        rec = {"spec": spec.as_dict(), "spec_sha256": spec.fingerprint(),
               "b_sigma_sha256": h.hexdigest(),
               "n_controlled": {}, "n_created": {}, "ratio_minmax": {},
               "min_analysis": {}}
        for i, f in enumerate(_FIELDS):
            sig = getattr(b_sigma, f)
            xbf = getattr(xb, f).detach().to(torch.float64)
            xaf = getattr(x_a, f).detach().to(torch.float64)
            rec["n_controlled"][f] = int((sig > 0).sum())
            if spec.mode[i] != "mul":
                continue
            rec["n_created"][f] = int(((xbf <= 0) & (xaf > 0)).sum())
            pos = xbf > 0
            if bool(pos.any()):
                r = xaf[pos] / xbf[pos]
                rec["ratio_minmax"][f] = [float(r.min()), float(r.max())]
            rec["min_analysis"][f] = float(xaf.min())
    return rec
