"""OSSE 민감도 사이클 드라이버 — Tier 0 조립 (docs/DA_REALTIME_PLAN.md).

조각들을 하나의 사이클로 결합한다:
  frame(io.read_wrfout_frame) → mstep 샤드(da_shard) → 3h 창 adjoint(da_window)
  + 배치 clear-sky RTTOV obs(T1-5 배치 builder, runK 1회/관측시각) → WindowResult
  = 민감도 산물 (adj_x0 = ∂J/∂x0).

배치 obs closure는 기존 단일-컬럼 obs_adjoint_callback의 local-closure 패턴을
따른다(detached leaves → builder → RttovObsOp → loss → autograd.grad; 창 backward
비관통 — design 10/14.3). WRF↔RTTOV 격자 변환이 이 모듈의 소관:
  - K축 flip (WRF bottom-up ↔ RTTOV TOA-first ascending-p)
  - Pa → hPa (픽스처 그리드 단위)
  - 공유 canonical 픽스처 layer grid로 배치 보간 (T1-5 계약)

OSSE 구성: 진실 x0로 창을 돌려 관측시각 BT를 '관측' y로 기록(무기울기) →
배경 x0_b(섭동)로 같은 창을 돌려 innovation 기반 J와 ∂J/∂x0를 얻는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import torch

from .da_window import WindowConfig, WindowResult, run_da_window
from .state import State, Forcing

_F64 = dict(dtype=torch.float64)


def _flip(t: torch.Tensor) -> torch.Tensor:
    """WRF K(bottom-up) ↔ RTTOV(TOA-first) — 마지막 축 반전 (autograd 관통)."""
    return torch.flip(t, dims=(-1,))


@dataclass
class OsseObsConfig:
    """배치 clear-sky BT 관측항 구성."""
    run_k: object                       # make_live_run_k(case_dir) 등
    profile_cfg: object                 # RttovProfileConfig (공유 fixture 그리드)
    input_cfg: object                   # RttovInputConfig (coef, channels)
    obs_sigma: float = 1.0              # 관측오차 σo [K]
    # 모델-상단 위 기준 프로파일 (표준 NWP-위성 관행): NWP 모델 상단(SS 케이스
    # ~60 hPa)보다 위의 타깃 레이어를 no-extrapolation 클램프(상수 연장)로 두면
    # 중간권까지 비물리 상수 T/Q가 되어 RTTOV regression limits가 프로파일을
    # 플래그한다(rad_quality != 0 → mask 전멸, 실측). 픽스처 기준 T/Q로 상단을
    # 채우고 모델 상단 부근 한 옥타브(log-p)를 선형 블렌드한다. 기준층은
    # 상수(무기울기) — 모델이 정보를 갖지 않는 영역이므로 옳다.
    t_ref: "torch.Tensor | None" = None     # (nlay_target,) 기준 T
    q_ref: "torch.Tensor | None" = None     # (nlay_target,) 기준 Q [ppmv moist]
    # 블렌드 폭 (옥타브, log2-p): 모델 가중 1이 되는 지점 = p_top·2^octaves.
    # Q 기본 4.0 = SS 케이스 실측(옥타브 스윕 2/3 → 여전히 플래그, 4 → 전 채널
    # 깨끗): 이상화 케이스의 수분 바닥(~41 ppmv)이 성층권-상부대류권 레벨별
    # WV 한계를 넘는다(이분 실측: Q가 위반 필드, T는 깨끗). oct=4에서도 WV
    # 채널 피크(350–500 hPa)는 모델 가중 0.64–0.76 유지. 실관측(비이상화)
    # 프레임에선 더 좁혀도 될 것.
    t_blend_octaves: float = 1.0
    q_blend_octaves: float = 4.0


def _blend_above_model_top(x_lay: torch.Tensor, x_ref: torch.Tensor,
                           p_lay: torch.Tensor, p_top_col: torch.Tensor,
                           octaves: float = 1.0) -> torch.Tensor:
    """모델 상단 위 = 기준, [p_top, 2^octaves·p_top] 구간은 log-p 선형 블렌드.

    x_lay (B, n), x_ref (n,), p_lay (n,), p_top_col (B,) → (B, n).
    w=1(모델) ← p ≥ 2^octaves·p_top;  w=0(기준) ← p ≤ p_top. w는 상수(no_grad).
    """
    with torch.no_grad():
        lp = torch.log(p_lay)[None, :]                    # (1, n)
        lt = torch.log(p_top_col)[:, None]                # (B, 1)
        denom = octaves * torch.log(torch.tensor(2.0, dtype=p_lay.dtype))
        w = ((lp - lt) / denom).clamp(0.0, 1.0)
    return w * x_lay + (1.0 - w) * x_ref[None, :]


def batched_clear_bt(x_t: State, forcing: Forcing, obs_cfg: OsseObsConfig):
    """B-컬럼 상태의 clear-sky BT를 runK 1회로 계산 (leaves에 grad 연결).

    반환: (bt (B,nch), rad_quality, leaves(State; th/qv requires_grad)).
    """
    from .obs.model_profile_builder import model_to_rttov_tensors
    from .obs.rttov_input_builder import pack_rttov_input  # noqa: F401 (계약 문서화)
    from .obs.rttov_obs_operator import RttovObsOp

    leaves = State(*(f.detach().clone().to(torch.float64) for f in x_t))
    leaves = leaves._replace(th=leaves.th.requires_grad_(True),
                             qv=leaves.qv.requires_grad_(True))
    # WRF → RTTOV: K flip + Pa→hPa. clear-sky builder는 th·pii(→T), qv, p만 소비.
    flip_forcing = Forcing(rho=_flip(forcing.rho), pii=_flip(forcing.pii),
                           p=_flip(forcing.p) / 100.0, delz=_flip(forcing.delz))
    flip_leaves = State(*(_flip(f) for f in leaves))
    prof = model_to_rttov_tensors(flip_leaves, flip_forcing, obs_cfg.profile_cfg)
    t_lay, q_lay = prof.t_lay, prof.q_lay
    if obs_cfg.t_ref is not None:
        p_top_col = flip_forcing.p[:, 0]                  # 컬럼별 모델 상단 [hPa]
        t_lay = _blend_above_model_top(t_lay, obs_cfg.t_ref, prof.p_lay, p_top_col,
                                       octaves=obs_cfg.t_blend_octaves)
        q_lay = _blend_above_model_top(q_lay, obs_cfg.q_ref, prof.p_lay, p_top_col,
                                       octaves=obs_cfg.q_blend_octaves)
    bt, rad_quality = RttovObsOp.apply(
        obs_cfg.run_k, obs_cfg.input_cfg,
        t_lay, q_lay, prof.p_lay, prof.p_half)
    return bt, rad_quality, leaves


def make_truth_bt_recorder(forcings: Sequence[Forcing], obs_times: set,
                           obs_cfg: OsseObsConfig, store: dict):
    """진실 창 forward에서 관측시각 BT를 기록하는 obs_adjoint (covector 없음)."""
    def obs_adjoint(t: int, x_t: State):
        if t not in obs_times:
            return None
        f = forcings[t] if t < len(forcings) else forcings[-1]
        with torch.no_grad():
            bt, rad_quality, _ = batched_clear_bt(x_t, f, obs_cfg)
        store[t] = (torch.as_tensor(bt, **_F64).clone(),
                    torch.as_tensor(rad_quality).clone())
        return None
    return obs_adjoint


def make_innovation_obs_adjoint(forcings: Sequence[Forcing], y_by_time: dict,
                                obs_cfg: OsseObsConfig, j_acc: list):
    """innovation 기반 obs_adjoint: J_t 누적 + covector 반환 (배치, runK 1회/시각)."""
    from .obs.rttov_obs_operator import _build_mask
    from .obs.obs_loss import compute_obs_loss

    def obs_adjoint(t: int, x_t: State):
        if t not in y_by_time:
            return None
        f = forcings[t] if t < len(forcings) else forcings[-1]
        y_bt, y_rq = y_by_time[t]
        bt, rad_quality, leaves = batched_clear_bt(x_t, f, obs_cfg)
        # 양측 QC 결합 (Codex stop-review): 진실측에서 플래그된 채널의 y는 무효
        # 관측 — obs_quality 슬롯(0=사용가능, rad_quality와 동일 게이트)으로
        # 전달해 mask = (배경측 quality==0) AND (진실측 quality==0)이 되게 한다.
        # 한쪽만 보면 플래그된 y가 innovation에 들어가 J/gradient가 오염된다.
        obs = {"bt": y_bt, "obs_quality": y_rq}
        mask = _build_mask(obs, rad_quality)
        j = compute_obs_loss(bt, obs, mask, sigma=obs_cfg.obs_sigma)
        g_th, g_qv = torch.autograd.grad(j, [leaves.th, leaves.qv])
        j_acc.append(float(j.detach()))
        zeros = torch.zeros_like(leaves.th)
        return State(th=g_th, qv=g_qv, qc=zeros, qr=zeros, qi=zeros, qs=zeros,
                     qg=zeros, nccn=zeros, nc=zeros, ni=zeros, nr=zeros, bg=zeros)
    return obs_adjoint


@dataclass
class OsseReport:
    j_obs: float                        # Σ_t J_t (배경 창)
    n_obs_times: int
    window: WindowResult                # adj_x0 = 민감도 산물
    adj_norms: dict = field(default_factory=dict)   # 필드별 ‖∂J/∂x0‖
    top_th: list = field(default_factory=list)      # |∂J/∂th0| 상위 (b,k,val)


def run_osse_sensitivity(x_truth: State, x_background: State,
                         forcings: Sequence[Forcing], obs_times: Sequence[int],
                         window_cfg: WindowConfig, obs_cfg: OsseObsConfig,
                         *, top_k: int = 5) -> OsseReport:
    """OSSE 민감도 사이클 1회: 진실→y 기록, 배경→innovation adjoint."""
    obs_set = set(int(t) for t in obs_times)
    y_store: dict = {}
    run_da_window(x_truth, forcings,
                  make_truth_bt_recorder(forcings, obs_set, obs_cfg, y_store),
                  window_cfg)
    if set(y_store) != obs_set:
        raise RuntimeError(f"truth BT recorded at {sorted(y_store)} != requested "
                           f"{sorted(obs_set)}")

    j_acc: list = []
    res = run_da_window(x_background, forcings,
                        make_innovation_obs_adjoint(forcings, y_store, obs_cfg, j_acc),
                        window_cfg)

    adj_norms = {k: float(getattr(res.adj_x0, k).norm())
                 for k in State._fields}
    g = res.adj_x0.th.abs()
    flat_idx = torch.argsort(g.reshape(-1), descending=True)[:top_k]
    B, K = g.shape
    top_th = [(int(i) // K, int(i) % K, float(g.reshape(-1)[i])) for i in flat_idx]
    return OsseReport(j_obs=float(sum(j_acc)), n_obs_times=len(j_acc),
                      window=res, adj_norms=adj_norms, top_th=top_th)
