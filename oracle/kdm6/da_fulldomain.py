"""전 도메인 all-sky dual CVT 분석 — J-부분공간, clear/cloudy 분할.

상태 CVT는 hybrid add/mul 전 물리량(계획 ⑪), 제어는 J-부분공간(유효 관측
배정 + 경계 제외 컬럼)만: 비관측 컬럼은 prior가 v=0으로 pin하므로 부분공간
절단은 무손실이고 상태 텐서가 12×B_sub×K로 줄어든다 (65,988 → 수천).

기본 구성 (P0 검토 반영):
- obs_time=1: 관측 슬롯이 M(미세물리 1스텝) 뒤 — 관측항이 M을 관통해
  θ·결합 기울기가 활성 (obs_time=0은 3D-Var형 직접 조정으로 퇴화; v9/v9.1의
  j_theta≡0 실측이 그 증거).
- huber_delta=3K: 양 파트 관측손실 Huber — 순수 이차 + 무상한 mul-CVT
  결합의 비물리 증분 유인 제거 (v9.1 qi ratio 4e11 실측의 처방).
- pseudo_rh 옵션: 모델-맑음/관측-구름 컬럼에 da_regime2 동결 부트스트랩
  합성 (3중 gate로 기울기가 닫힌 regime-2의 생성 경로).

파이프라인: frame + GK2A slot collocation → J-부분공간 → 구름/맑음 분할 →
동결 mask(배경 슬롯 시각 H) + 서명 → 결합 obs_eval(맑음: 배치 clear-sky,
th/qv covector; 구름: sharded all-sky, 7필드 covector; 선택적 pseudo-RH) →
run_dual_minimizer(hybrid CVT) → 슬롯 시각 O−B/O−A + 4-regime 층화 보고.
"""
from __future__ import annotations

import hashlib
import math
import time
from pathlib import Path

import torch

from .da_cvt import make_default_cvt
from .da_driver import OsseObsConfig, batched_clear_bt
from .da_dual import ObsEvalResult, default_param_prior, run_dual_minimizer
from .da_window import WindowConfig
from .obs.allsky_shard import sharded_allsky
from .state import Forcing, State

_F64 = dict(dtype=torch.float64)
ALLSKY_FIELDS = ("th", "qv", "qc", "qi", "qs", "nc", "ni")
_K_INDEX_MAX = 9999          # RTTOV K 출력 profile-index 4자리 한계 (case_writer 가드)
IR105_COL = 12               # CLEAN_IR 채널 배열 내 ir105 위치 (LC05 게이트 관례)
OBS_CLOUD_BT = 270.0         # 관측 구름 판정: ir105 BT < 270K (LC05 게이트 관례)
REGIME_NAMES = {1: "clear_clear", 2: "clear_cloudy",
                3: "cloudy_cloudy", 4: "cloudy_clear"}


def _take(s, idx):
    """State/Forcing 컬럼 부분집합."""
    return type(s)(*(f[idx] for f in s))


def select_subspace(fr, co, *, boundary: int = 10, qtot_min: float = 1.0e-5,
                    max_cloudy: "int | None" = None,
                    max_clear: "int | None" = None):
    """J-부분공간(경계 제외 + 유효채널 보유) → (sub_idx, cloudy_pos, clear_pos).

    반환 인덱스 규약: sub_idx는 전 도메인 컬럼 번호, cloudy/clear_pos는
    부분공간 내 위치 (구름 먼저). max_*는 스모크/예산 캡 — 캡 적용 시 보고
    dict에 기록되므로 침묵 절단이 아니다.
    """
    nx, ny = int(fr.meta["nx"]), int(fr.meta["ny"])
    b = torch.arange(fr.state.th.shape[0])
    i, j = b % nx, b // nx
    interior = ((i >= boundary) & (i < nx - boundary)
                & (j >= boundary) & (j < ny - boundary))
    has_obs = (co.obs_quality == 0).any(dim=1)
    jset = torch.where(interior & has_obs)[0]
    qtot = (fr.state.qc + fr.state.qi + fr.state.qs).sum(-1)
    cm = qtot[jset] > qtot_min
    cloudy, clear = jset[cm], jset[~cm]
    if max_cloudy is not None:
        cloudy = cloudy[:max_cloudy]
    if max_clear is not None:
        clear = clear[:max_clear]
    sub = torch.cat([cloudy, clear])
    return (sub, torch.arange(len(cloudy)),
            torch.arange(len(cloudy), len(sub)))


def _part_loss(bt, y, mask, delta: "float | None"):
    """Partition loss — delta=None: sigma_o=1K pure quadratic (legacy
    contract), delta>0: Huber (P0-3).

    A pure quadratic rewards fitting huge innovations (cloud displacement
    etc.) without bound, which combined with the unbounded mul-CVT drives
    unphysical increments (v9.1 measured qi ratio 4e11 — caught by the
    ratio_minmax audit). Huber turns the incentive linear beyond |r|>delta.

    Masked (invalid) channel residuals are REPLACED with zero before the
    loss is applied — 0*NaN = NaN, so multiplicative masking alone lets a
    non-finite obs/model value at a flagged channel poison j (same
    replace-before-_huber discipline as compute_obs_loss)."""
    if delta is not None and not (math.isfinite(delta) and delta > 0.0):
        # delta=0 silently zeroes the obs cost AND its gradient; negative
        # delta allows negative cost (same validation as compute_obs_loss).
        raise ValueError(f"huber_delta must be None or finite > 0 "
                         f"(got {delta!r})")
    r = torch.where(mask > 0, mask * (bt - y), torch.zeros_like(bt))
    if delta is None:
        return 0.5 * (r * r).sum()
    from .obs.obs_loss import _huber
    return _huber(r, float(delta)).sum()


def check_obs_time_alignment(obs_time: int, dt: float, *,
                             obs_offset_s: float,
                             time_tolerance_s: float) -> None:
    """Enforce |obs_time*dt - obs_offset_s| <= time_tolerance_s.

    obs_offset_s is the obs valid time minus the frame valid time (seconds).
    The slot state x_{obs_time} is valid at t0 + obs_time*dt; comparing a
    displaced observation silently biases the innovation (review #1 — the
    LC05 fixture pairs a 00:00 UTC obs with the 00:05 slot at the defaults,
    which passes only because the tolerance says so, explicitly)."""
    err = abs(obs_time * dt - obs_offset_s)
    if err > time_tolerance_s:
        raise ValueError(
            f"obs valid time offset {obs_offset_s:g}s vs slot time "
            f"{obs_time * dt:g}s differ by {err:g}s > tolerance "
            f"{time_tolerance_s:g}s — align obs_time/dt with the obs slot "
            "or state the tolerance explicitly")


def validate_pseudo_qv_overlap(sigma_qv: torch.Tensor, cols: torch.Tensor,
                               levels: torch.Tensor) -> None:
    """Reject pseudo-RH columns whose selected levels are all outside the
    CVT-controlled qv levels (sigma_qv == 0 there => exactly zero gradient,
    i.e. the bootstrap silently does nothing — review #5)."""
    active = (sigma_qv[cols] > 0) & levels
    dead = ~active.any(dim=1)
    if bool(dead.any()):
        raise ValueError(
            f"pseudo-RH columns {cols[dead].tolist()} have no CVT-controlled "
            "qv level in their target band (sigma_qv == 0 there) — extend "
            "qv_levels (builder) or drop those columns")


def select_regime2_positions(y_bt, y_rq, clear_pos, *,
                             ir_col: int = IR105_COL,
                             bt_cloud: float = OBS_CLOUD_BT) -> torch.Tensor:
    """모델-맑음(clear_pos) ∧ 관측-구름(ir 유효 & BT<bt_cloud) 부분공간 위치.

    pseudo-RH 부트스트랩(da_regime2)의 동결 C2 선정 — 배경·관측만 사용
    (v-독립)."""
    obs_cloudy = (y_rq[:, ir_col] == 0) & (y_bt[:, ir_col] < bt_cloud)
    keep = torch.zeros(y_bt.shape[0], dtype=torch.bool)
    keep[clear_pos] = True
    return torch.where(obs_cloudy & keep)[0]


def classify_regimes(n_sub: int, y_bt, mask, cloudy_pos, *,
                     ir_col: int = IR105_COL,
                     bt_cloud: float = OBS_CLOUD_BT) -> torch.Tensor:
    """모델/관측 구름 4-regime 코드 (B_sub,) — 1:맑음/맑음 2:맑음/구름
    3:구름/구름 4:구름/맑음, 0:ir 채널 무효(분류 불가).

    모델 구름 = select_subspace의 qtot 분할(cloudy_pos), 관측 구름 =
    동결 mask 유효한 ir105 BT < bt_cloud. 보정 방향성 검토의 층화 축:
    (2)는 생성 불가 regime(ε=0 구조 + cfrac gate)이라 th/qv aliasing 감시,
    (4)는 mul 제거 방향(Δq<0) 확인이 목적.
    """
    model_cloudy = torch.zeros(n_sub, dtype=torch.bool)
    model_cloudy[cloudy_pos] = True
    valid = mask[:, ir_col] > 0
    obs_cloudy = y_bt[:, ir_col] < bt_cloud
    code = torch.zeros(n_sub, dtype=torch.int64)
    code[valid & ~model_cloudy & ~obs_cloudy] = 1
    code[valid & ~model_cloudy & obs_cloudy] = 2
    code[valid & model_cloudy & obs_cloudy] = 3
    code[valid & model_cloudy & ~obs_cloudy] = 4
    return code


def _clear_slices(n: int, nch: int):
    """clear 배치 H의 nprof×nch ≤ 9999 청킹 (v8 실측 함정의 구조적 회피)."""
    step = max(1, _K_INDEX_MAX // max(1, nch))
    return [torch.arange(a, min(a + step, n)) for a in range(0, n, step)]


def _clear_bt_chunked(x_cl: State, fc_cl: Forcing, cfg: OsseObsConfig, nch: int):
    """청킹된 clear-sky BT/rq (no-grad 용도 — 동결 프로브·보고)."""
    bts, rqs = [], []
    for sl in _clear_slices(x_cl.th.shape[0], nch):
        bt, rq, _ = batched_clear_bt(_take(x_cl, sl), _take(fc_cl, sl), cfg)
        bts.append(bt.to(torch.float64))
        rqs.append(rq)
    return torch.cat(bts), torch.cat(rqs)


def make_fulldomain_obs_eval(xb_sub: State, fc_sub: Forcing, y_bt, y_rq,
                             xland_sub, cloudy_pos, clear_pos,
                             clear_cfg: OsseObsConfig, rttov_cfg: dict,
                             case_root: str, *, n_workers: int, pool,
                             obs_time: int = 1,
                             huber_delta: "float | None" = 3.0,
                             x_slot_bg: "State | None" = None,
                             pseudo: "dict | None" = None):
    """동결 mask 결합 obs_eval — 슬롯 t=obs_time, ObsEvalResult 반환.

    동결 기준은 배경 '슬롯 시각' 상태 x_slot_bg(기본 xb_sub — obs_time=0일 때):
    맑음 파트는 batched_clear_bt, 구름 파트는 sharded_allsky(grad=False)의
    rad_quality. covector는 맑음 th/qv + 구름 12필드(all-sky 연결 7필드만
    비영)를 부분공간 위치에 산개 합성. obs_time≥1이면 관측항이 M(미세물리)을
    관통해 θ·전 필드 결합 기울기가 살아난다 (P0-1). huber_delta는 양 파트
    공통 (P0-3). pseudo = dict(cols, target, levels, sigma_p) — regime-2
    부트스트랩 항 합성 (P0-2; 동결 구성은 서명에 합성).
    """
    from .da_regime2 import pseudo_rh_term

    nch = y_bt.shape[1]
    x_probe = xb_sub if x_slot_bg is None else x_slot_bg
    with torch.no_grad():
        _, rq_clear = _clear_bt_chunked(_take(x_probe, clear_pos),
                                        _take(fc_sub, clear_pos),
                                        clear_cfg, nch)
        probe = sharded_allsky(x_probe, fc_sub, cloudy_pos, y_bt,
                               torch.zeros_like(y_bt), xland_sub, rttov_cfg,
                               f"{case_root}/probe", n_workers=n_workers,
                               grad=False, pool=pool)
    mask = torch.zeros_like(y_bt)
    mask[cloudy_pos] = ((y_rq[cloudy_pos] == 0) & (probe["rq"] == 0)).to(torch.float64)
    mask[clear_pos] = ((y_rq[clear_pos] == 0) & (rq_clear == 0)).to(torch.float64)
    n_valid = int(mask.sum())
    h = hashlib.sha256()
    h.update(mask.numpy().tobytes())
    h.update(cloudy_pos.numpy().tobytes() + clear_pos.numpy().tobytes())
    h.update(f"|{clear_cfg.input_cfg.coef_id}|{rttov_cfg['coef_id']}|".encode())
    h.update(f"|t={obs_time}|huber={huber_delta}|".encode())
    if pseudo is not None:
        h.update(b"|pseudo|" + pseudo["cols"].to(torch.int64).numpy().tobytes()
                 + pseudo["target"].to(torch.float64).numpy().tobytes()
                 + pseudo["levels"].to(torch.uint8).numpy().tobytes()
                 + f"|{float(pseudo['sigma_p']).hex()}".encode())
        n_valid += int(pseudo["levels"].sum())
    signature = h.hexdigest()

    counters = {"call": 0}

    def obs_eval(t: int, x_t: State):
        if t != obs_time:
            return None
        counters["call"] += 1
        out = sharded_allsky(x_t, fc_sub, cloudy_pos, y_bt, mask, xland_sub,
                             rttov_cfg, f"{case_root}/c{counters['call']}",
                             n_workers=n_workers, grad=True,
                             huber_delta=huber_delta, pool=pool)
        x_cl, fc_cl = _take(x_t, clear_pos), _take(fc_sub, clear_pos)
        y_cl, m_cl = y_bt[clear_pos], mask[clear_pos]
        g_th = torch.zeros_like(x_cl.th)
        g_qv = torch.zeros_like(x_cl.qv)
        j_parts = []
        for sl in _clear_slices(x_cl.th.shape[0], nch):     # K-인덱스 4자리 청킹
            bt_c, _, leaves = batched_clear_bt(_take(x_cl, sl),
                                               _take(fc_cl, sl), clear_cfg)
            j_c = _part_loss(bt_c.to(torch.float64), y_cl[sl], m_cl[sl],
                             huber_delta)
            gt, gq = torch.autograd.grad(j_c, [leaves.th, leaves.qv],
                                         allow_unused=False)
            g_th[sl], g_qv[sl] = gt, gq
            j_parts.append(float(j_c.detach()))
        adj = {f: torch.zeros_like(getattr(xb_sub, f)) for f in State._fields}
        for fi, f in enumerate(State._fields):
            adj[f][cloudy_pos] = out["adj"][fi]
        adj["th"][clear_pos] += g_th
        adj["qv"][clear_pos] += g_qv
        if pseudo is not None:                              # regime-2 부트스트랩
            j_p, adj_p = pseudo_rh_term(x_t, pseudo["cols"], pseudo["target"],
                                        sigma_p=pseudo["sigma_p"],
                                        levels=pseudo["levels"])
            adj["qv"] = adj["qv"] + adj_p.qv
            j_parts.append(float(j_p))
        j = math.fsum([float(out["j"])] + j_parts)
        return ObsEvalResult(j=j, adj=State(**adj), n_valid=n_valid,
                             signature=signature)

    obs_eval.connected_fields = ALLSKY_FIELDS
    obs_eval.mask = mask                      # O−B/O−A 보고 재사용 (동결본)
    return obs_eval


def run_fulldomain_analysis(fr, co, grids: dict, case_root: str, *,
                            boundary: int = 10, n_workers: int = 8,
                            max_iter: int = 3,
                            max_cloudy: "int | None" = None,
                            max_clear: "int | None" = None,
                            coef_clear: str = "ami_501_test",
                            coef_cloud: str = "ami_cloud",
                            channels: tuple = (),
                            obs_time: int = 1,
                            dt: float = 300.0,
                            obs_offset_s: float = 0.0,
                            time_tolerance_s: float = 300.0,
                            ncmin_land: float = 0.0,
                            ncmin_sea: float = 0.0,
                            huber_delta: "float | None" = 3.0,
                            pseudo_rh: bool = False,
                            pseudo_sigma_p: float = 2.0e-4,
                            save_fields: "str | None" = None) -> dict:
    """전 도메인 분석 1회 — JSON 직렬화 가능한 보고 dict 반환.

    grids: dict(p_lay, p_half, t_ref, q_ref) — RTTOV 픽스처 격자/기준 프로파일
    (테스트 헬퍼 또는 케이스 자산에서 공급; 모듈은 tests에 의존하지 않는다).
    obs_time=1(기본): 관측이 M(미세물리 1스텝)을 관통 — θ·결합 기울기 활성
    (P0-1; obs_time=0은 3D-Var형 직접 조정으로 퇴화, θ는 prior에 pin).
    huber_delta: 양 파트 관측손실의 Huber δ[K] (P0-3; None=구계약 순수 이차).
    pseudo_rh=True: 모델-맑음/관측-구름 컬럼에 동결 pseudo-RH 부트스트랩
    합성 (P0-2; da_regime2 — 구름정상 온도매칭 층, 상전이-인지 동결 목표).
    save_fields: npz 경로 — 영상화/후속 분석용 배경·분석 필드 + bt/regime.
    """
    from .obs.model_profile_builder import RttovProfileConfig
    from .obs.rttov_case_writer import make_live_run_k
    from .obs.rttov_input_builder import RttovInputConfig
    import multiprocessing as mp
    import numpy as np

    t0 = time.time()
    sub, cloudy_pos, clear_pos = select_subspace(
        fr, co, boundary=boundary, max_cloudy=max_cloudy, max_clear=max_clear)
    xb = _take(fr.state, sub)
    fc = _take(fr.forcing, sub)
    xland = fr.xland[sub]
    y_bt, y_rq = co.bt[sub], co.obs_quality[sub]

    p_lay = torch.as_tensor(np.asarray(grids["p_lay"], dtype=float), **_F64)
    p_half = torch.as_tensor(np.asarray(grids["p_half"], dtype=float), **_F64)
    t_ref = torch.as_tensor(np.asarray(grids["t_ref"], dtype=float), **_F64)
    q_ref = torch.as_tensor(np.asarray(grids["q_ref"], dtype=float), **_F64)
    clear_cfg = OsseObsConfig(
        run_k=make_live_run_k(f"{case_root}/clear"),
        profile_cfg=RttovProfileConfig(
            gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
            rttov_layer_pressure=p_lay, rttov_level_pressure=p_half),
        input_cfg=RttovInputConfig(coef_id=coef_clear, channels=channels),
        obs_sigma=1.0, t_ref=t_ref, q_ref=q_ref)
    # M and H must see the SAME land/sea and activation-minimum settings —
    # a mismatch makes microphysics activation and RTTOV Deff inconsistent
    # (review #2). ncmin values are pass-through so both sides agree.
    rttov_cfg = dict(t_ref=t_ref.numpy(), q_ref=q_ref.numpy(),
                     p_lay=p_lay.numpy(), p_half=p_half.numpy(),
                     channels=tuple(channels), coef_id=coef_cloud,
                     ncmin_land=ncmin_land, ncmin_sea=ncmin_sea,
                     oracle_root=str(Path(__file__).resolve().parents[1]))

    prior = default_param_prior(0.2)
    cfg = WindowConfig(dt=dt, xland=xland,
                       ncmin_land=ncmin_land, ncmin_sea=ncmin_sea)
    if obs_time not in (0, 1):
        raise ValueError(f"obs_time must be 0 or 1 (got {obs_time}) — the "
                         "driver runs a single-step window")
    check_obs_time_alignment(obs_time, dt, obs_offset_s=obs_offset_s,
                             time_tolerance_s=time_tolerance_s)  # review #1

    import dataclasses

    def _slot_state(x_state, params=None):
        """State at the obs slot time — one M step via the forward-only
        collector (run_da_window pays the VJP sweep and manages its own
        grad contexts, so it must NOT be wrapped in no_grad — same probe
        discipline as the frozen adapter). params selects theta: None keeps
        theta_b; pass theta_a for analysis-consistent O-A (review #3)."""
        if obs_time == 0:
            return x_state
        from .da_window import collect_window_trajectory
        cfg_p = cfg if params is None else dataclasses.replace(cfg,
                                                               params=params)
        return collect_window_trajectory(x_state, [fc], cfg_p,
                                         {obs_time})[obs_time]

    x_slot_bg = _slot_state(xb)
    pseudo = None
    n_pseudo_cols = 0
    if pseudo_rh:
        from .da_regime2 import cloud_top_levels, frozen_saturation_target
        r2 = select_regime2_positions(y_bt, y_rq, clear_pos)
        n_pseudo_cols = int(r2.numel())
        if n_pseudo_cols:
            # Route regime-2 columns through the ALL-SKY part: once M creates
            # condensate, cfrac flips live and the BT term takes over the
            # amount refinement — with clear-sky H that path never exists
            # (review #4). Frozen targets/levels come from the slot-time
            # background state (the obs applies to x_slot, not x0).
            keep = torch.ones(y_bt.shape[0], dtype=torch.bool)
            keep[r2] = False
            cloudy_pos = torch.cat([cloudy_pos, r2])
            clear_pos = clear_pos[keep[clear_pos]]
            pseudo = dict(cols=r2,
                          target=frozen_saturation_target(x_slot_bg, fc, r2),
                          levels=cloud_top_levels(x_slot_bg, fc, r2,
                                                  y_bt[r2, IR105_COL]),
                          sigma_p=pseudo_sigma_p)

    # Upper-level cloud tops need qv control above the clear-sky default of
    # 12 levels; otherwise the pseudo gradient is exactly zero there
    # (review #5 — validated below, fail-fast).
    spec, b_sigma = make_default_cvt(
        xb, qv_levels=(xb.th.shape[1] if pseudo is not None else 12))
    if pseudo is not None:
        validate_pseudo_qv_overlap(b_sigma.qv, pseudo["cols"],
                                   pseudo["levels"])

    ctx = mp.get_context("spawn")
    pool = ctx.Pool(n_workers)
    try:
        obs_eval = make_fulldomain_obs_eval(
            xb, fc, y_bt, y_rq, xland, cloudy_pos, clear_pos,
            clear_cfg, rttov_cfg, case_root, n_workers=n_workers, pool=pool,
            obs_time=obs_time, huber_delta=huber_delta,
            x_slot_bg=x_slot_bg, pseudo=pseudo)
        res = run_dual_minimizer(xb, [fc], obs_eval, cfg, b_sigma, prior,
                                 max_iter=max_iter, cvt=spec)

        # O-B / O-A on the frozen mask at the obs slot time. O-A must use the
        # OPTIMIZED theta_a — H(M(x_a; theta_b)) is not the analysis pair and
        # disagrees with the joint objective (review #3).
        mask = obs_eval.mask
        def _h_bt(x_state, params=None):
            x_slot = _slot_state(x_state, params=params)
            with torch.no_grad():
                o = sharded_allsky(x_slot, fc, cloudy_pos, y_bt,
                                   torch.zeros_like(y_bt), xland, rttov_cfg,
                                   f"{case_root}/rep", n_workers=n_workers,
                                   grad=False, pool=pool)
                bt = torch.zeros_like(y_bt)
                bt[cloudy_pos] = o["bt"]
                bt_cl, _ = _clear_bt_chunked(_take(x_slot, clear_pos),
                                             _take(fc, clear_pos), clear_cfg,
                                             y_bt.shape[1])
                bt[clear_pos] = bt_cl
            return bt

        bt_b = _h_bt(xb)
        bt_a = _h_bt(res.x_analysis, params=res.theta_analysis)
    finally:
        pool.close()
        pool.join()

    def _masked_abs_mean(bt, rows=None):
        m = mask if rows is None else mask[rows]
        r = (y_bt - bt) if rows is None else (y_bt[rows] - bt[rows])
        return float((m * r).abs().sum() / m.sum()) if float(m.sum()) else 0.0

    omb, oma = _masked_abs_mean(bt_b), _masked_abs_mean(bt_a)

    # 모델/관측 구름 4-regime 층화 — 보정 방향성 감사
    code = classify_regimes(int(sub.numel()), y_bt, mask, cloudy_pos)
    dqtot = ((res.x_analysis.qc + res.x_analysis.qi + res.x_analysis.qs)
             - (xb.qc + xb.qi + xb.qs)).sum(-1)
    regimes = {}
    for c, name in REGIME_NAMES.items():
        rows = torch.where(code == c)[0]
        regimes[name] = dict(
            n=int(rows.numel()),
            omb=_masked_abs_mean(bt_b, rows), oma=_masked_abs_mean(bt_a, rows),
            dqtot_mean=(float(dqtot[rows].mean()) if rows.numel() else 0.0),
            dth_mean=(float((res.x_analysis.th - xb.th)[rows].mean())
                      if rows.numel() else 0.0))

    if save_fields is not None:
        np.savez_compressed(
            save_fields, sub_idx=sub.numpy(),
            nx=int(fr.meta["nx"]), ny=int(fr.meta["ny"]),
            n_cloudy=int(cloudy_pos.numel()), mask=mask.numpy(),
            y_bt=y_bt.numpy(), bt_b=bt_b.numpy(), bt_a=bt_a.numpy(),
            regime=code.numpy(),
            **{f"xb_{f}": getattr(xb, f).numpy() for f in State._fields},
            **{f"xa_{f}": getattr(res.x_analysis, f).numpy()
               for f in State._fields})

    dnorm = {f: float((getattr(res.x_analysis, f) - getattr(xb, f)).norm())
             for f in State._fields}
    return dict(
        n_domain=int(fr.state.th.shape[0]), n_subspace=int(sub.numel()),
        n_cloudy=int(cloudy_pos.numel()), n_clear=int(clear_pos.numel()),
        n_valid=int(mask.sum()),
        caps=dict(max_cloudy=max_cloudy, max_clear=max_clear),
        obs_time=obs_time, dt=dt, obs_offset_s=obs_offset_s,
        time_tolerance_s=time_tolerance_s, huber_delta=huber_delta,
        ncmin_land=ncmin_land, ncmin_sea=ncmin_sea,
        n_pseudo_cols=n_pseudo_cols,
        grad_theta_norm_final=res.grad_theta_norm_final,
        j_trace=res.j_trace, omb=omb, oma=oma, regimes=regimes,
        theta=[float(t) for t in res.theta_analysis],
        increment_norms=dnorm, cvt=res.cvt,
        wall_s=time.time() - t0)
