"""Regime-2 (모델 맑음 / 관측 구름) — 동결 pseudo-RH 부트스트랩.

3중 gate — CVT(V3: σ=0 at xb=0), H(cfrac detached), M(satadj 과포화 분기,
미포화에서 ∂pcond/∂qv ≡ 0) — 로 기울기가 완전히 닫힌 regime-2 컬럼에,
관측 슬롯 시각의 상태에 대한 매끄러운 습도 pseudo-obs를 합성한다:

  j_p = ½ Σ_{c∈cols, k∈levels} (clamp(q* − qv_t, min=0) / σ_p)²

목표 q*는 frozen_saturation_target의 **배경-동결·상전이-인지·과녁-너머**
상수다 (판정 패널 수정 3건 반영): live qsat(T)의 냉각-보상 채널을 제거해
기울기는 qv 행에만 걸리고(covector 자명 일관), 과녁이 gate '너머'라
정지점이 설계상 포화 위다. 부족분 hinge(단측)라 과포화에는 0 — 과잉
가습을 밀지 않는다. qv가 포화를 넘는 순간 satadj(온난)/빙정 핵생성(한랭,
RH_ice>1.08)이 응결수를 만들고 cfrac(live-value)이 flip, BT 항의 기울기가
활성화되어 구름량 정련을 이어받는다 — 운영 구름분석의 pseudo-RH 주입
(cloud initialization)의 미분가능 구현. 시험: test_da_regime2
(T-R2a 음성 대조 / T-R2b 부트스트랩 / T-R2c 실관측).

동결 규율: cols/levels는 호출자가 배경에서 동결해 넘긴다 (v-독립 —
dual 어댑터 합성 시 C2/k* 선정·서명 합성도 배경 기준).
"""
from __future__ import annotations

import torch

from . import thermo
from .state import State

_F64 = dict(dtype=torch.float64)


T_FREEZE = 273.15
RH_ICE_NUCL = 1.08           # 빙정 핵생성 문턱 (cold.py rh_ice > 1.08 게이트)
DELTA_OVERSHOOT = 0.02       # 목표 과녁의 과포화 여유 — gate 위가 아닌 너머


def frozen_saturation_target(xb_sub: State, forcing, cols: torch.Tensor, *,
                             delta: float = DELTA_OVERSHOOT,
                             rh_ice: float = RH_ICE_NUCL,
                             thermo_params=None) -> torch.Tensor:
    """배경-동결 상전이-인지 포화 목표 q* (n_cols, K) — v-독립 상수.

    판정 패널 수정 3건의 구현:
    ① 과녁을 gate '너머'로: q* = (1+δ)·qs_eff — 정지점이 구조적으로 포화 위
      (δ=0 목표는 hinge 기울기가 gate에서 소멸해 교차가 라인서치 운에 의존).
    ② 배경 T로 동결: 목표가 상수 → ∂j_p/∂th ≡ 0 — live qsat(T)의
      냉각-보상(aliasing 증폭) 채널 제거 + covector 자명 일관.
    ③ 상전이 인지: T_bg < 273.15K에서 qs_eff = min(qs_water, rh_ice·qs_ice)
      (냉구름의 생성 gate는 빙정 핵생성 — 물-포화 목표는 과대 가습).
    """
    tp = thermo_params or thermo.default_thermo_params()
    with torch.no_grad():
        t_bg = (xb_sub.th * forcing.pii)[cols]
        p = forcing.p[cols]
        qs_w = thermo.compute_qs_water(t_bg, p, params=tp)
        qs_i = thermo.compute_qs_ice(t_bg, p, params=tp)
        qs_eff = torch.where(t_bg < T_FREEZE,
                             torch.minimum(qs_w, rh_ice * qs_i), qs_w)
        return ((1.0 + delta) * qs_eff).detach()


def pseudo_rh_term(x_t: State, cols: torch.Tensor, target: torch.Tensor,
                   *, sigma_p: float,
                   levels: "torch.Tensor | None" = None):
    """슬롯 시각 상태 x_t의 pseudo 습도 항 — (j_p, covector State) 반환.

    target: frozen_saturation_target의 동결 상수 (n_cols, K). covector는
    ∂j_p/∂x_t = −deficit/σ_p² (qv 행만 비영; 목표 상수라 th 행은 정확히 0)
    — 창 M^T가 x0로 수송한다. 부족분 hinge 제곱은 C¹ (교차점 kink 없음).
    """
    import math as _math
    if not (_math.isfinite(sigma_p) and sigma_p > 0.0):
        raise ValueError(f"sigma_p must be finite and > 0 (got {sigma_p!r})")
    lv_qv = x_t.qv[cols].detach().clone().requires_grad_(True)
    deficit = torch.clamp(target - lv_qv, min=0.0)
    if levels is not None:
        if levels.dtype == torch.bool:              # 컬럼별 층 mask (n_cols, K)
            deficit = deficit * levels.to(deficit.dtype)
        else:                                       # 공통 K-인덱스 목록
            sel = torch.zeros_like(deficit)
            sel[:, levels] = 1.0
            deficit = deficit * sel
    j = 0.5 * ((deficit / sigma_p) ** 2).sum()
    (g_qv,) = torch.autograd.grad(j, [lv_qv])
    zeros = torch.zeros_like(x_t.th)
    adj_qv = zeros.clone()
    adj_qv[cols] = g_qv
    adj = State(**{f: zeros for f in State._fields})._replace(qv=adj_qv)
    return j.detach(), adj


def _reject_duplicates(name: str, t: "torch.Tensor | None") -> None:
    """중복 인덱스 fail-fast — j에는 셀이 이중 계상되는데 비누적 scatter는
    마지막 쓰기만 남겨 covector ≠ ∇j (adjoint 정확성 위반) + n_valid 과대."""
    if t is not None and t.dtype != torch.bool \
            and int(t.numel()) != int(torch.unique(t).numel()):
        raise ValueError(
            f"{name} has duplicate entries — pseudo cells would be "
            "double-counted in j while the covector scatter drops all but "
            "the last write (adj != grad j); pass unique indices")


def wrap_obs_eval_with_pseudo_rh(base_obs_eval, *, t_obs: int,
                                 cols: torch.Tensor, target: torch.Tensor,
                                 sigma_p: float,
                                 levels: "torch.Tensor | None" = None):
    """run_minimizer 규약 obs_eval에 동결-목표 pseudo 항 합성 — (j, adj) 합산.

    base가 None을 반환하는 슬롯이라도 pseudo는 t_obs에서 항상 활성
    (regime-2 컬럼은 BT mask가 전멸해도 부트스트랩은 유효해야 한다).
    """
    _reject_duplicates("cols", cols)
    _reject_duplicates("levels", levels)

    def obs_eval(t: int, x_t: State):
        out = base_obs_eval(t, x_t)
        if t != t_obs:
            return out
        j_p, adj_p = pseudo_rh_term(x_t, cols, target, sigma_p=sigma_p,
                                    levels=levels)
        if out is None:
            return j_p, adj_p
        j, adj = out
        j_sum = torch.as_tensor(j, **_F64) + j_p
        return j_sum, State(*(a + b for a, b in zip(adj, adj_p)))
    return obs_eval


def cloud_top_levels(xb_sub: State, forcing, cols: torch.Tensor,
                     bt_obs: torch.Tensor, *, band: int = 1) -> torch.Tensor:
    """동결 층 지정 — 불투명 구름 가정의 구름-정상 온도 매칭 (설계 v1).

    k*(c) = argmin_k |T_bg(c,k) − BT_obs(c)|; 반환은 (len(cols), K) bool
    mask로 k* ± band 층. 배경에서 1회 계산해 동결 (v-독립).
    """
    t_bg = (xb_sub.th * forcing.pii)[cols]                    # (n, K)
    k_star = (t_bg - bt_obs[:, None]).abs().argmin(dim=1)     # (n,)
    K = t_bg.shape[1]
    k = torch.arange(K)[None, :]
    return (k >= (k_star[:, None] - band)) & (k <= (k_star[:, None] + band))


def wrap_dual_obs_eval_with_pseudo_rh(base_obs_eval, *, t_obs: int,
                                      cols: torch.Tensor,
                                      target: torch.Tensor, sigma_p: float,
                                      levels: "torch.Tensor | None" = None):
    """dual(ObsEvalResult) 규약 합성 — anti-gaming 계약 유지.

    n_valid에 pseudo 항 수(동결 상수)를 가산하고, signature에 동결 구성
    (cols/levels/target/σ_p/t_obs) 해시를 합성한다 — 동일-개수 치환 방어
    유지. base의 connected_fields 태그 승계 (pseudo는 qv 행만 — 양 모드
    모두 connected ⊆ 유지).
    """
    import hashlib

    from .da_dual import ObsEvalResult

    _reject_duplicates("cols", cols)
    _reject_duplicates("levels", levels)
    h = hashlib.sha256(b"pseudo-rh-v1.1|")
    h.update(cols.to(torch.int64).numpy().tobytes())
    h.update(target.to(torch.float64).numpy().tobytes())
    if levels is not None:
        h.update(levels.to(torch.uint8).numpy().tobytes()
                 if levels.dtype == torch.bool
                 else levels.to(torch.int64).numpy().tobytes())
    h.update(f"|{float(sigma_p).hex()}|{t_obs}".encode())
    pseudo_sig = h.hexdigest()
    if levels is None:
        n_pseudo = None                              # 전층 — K는 첫 호출에서
    elif levels.dtype == torch.bool:
        n_pseudo = int(levels.sum())                 # 컬럼별 mask의 활성 셀 수
    else:
        n_pseudo = int(cols.numel()) * int(levels.numel())   # 인덱스 목록

    def obs_eval(t: int, x_t: State):
        out = base_obs_eval(t, x_t)
        if t != t_obs:
            return out
        j_p, adj_p = pseudo_rh_term(x_t, cols, target, sigma_p=sigma_p,
                                    levels=levels)
        n_p = (n_pseudo if n_pseudo is not None
               else int(cols.numel()) * x_t.th.shape[1])
        if out is None:
            raise RuntimeError(
                f"pseudo-RH slot t={t_obs} has no base obs term — the dual "
                "contract needs the base adapter to own this slot (frozen "
                "mask/signature); align t_obs with a y_by_time slot")
        return ObsEvalResult(
            j=float(out.j + float(j_p)),
            adj=State(*(a + b for a, b in zip(out.adj, adj_p))),
            n_valid=out.n_valid + n_p,
            signature=f"{out.signature}|{pseudo_sig}")
    # pseudo가 qv에 '직접' 민감도를 부여하므로 합성 태그에 qv를 보장 —
    # base 태그에 없으면 V7이 σ_qv>0을 거짓 사망 판정할 수 있다 (Codex 지적)
    base_conn = getattr(base_obs_eval, "connected_fields", None)
    if base_conn is not None and "qv" not in base_conn:
        base_conn = tuple(base_conn) + ("qv",)
    obs_eval.connected_fields = base_conn
    return obs_eval
