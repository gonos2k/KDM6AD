"""전 도메인 t=0 all-sky dual CVT 분석 (v9) — J-부분공간, clear/cloudy 분할.

v8(교대 dual-estimation, 계획 ⑩)과의 차이: 창을 t=0 단일 슬롯로 줄이고
(all-sky dual 어댑터의 직접 민감도 — 계획 ⑪), 상태 CVT를 hybrid add/mul
전 물리량으로 건다. 제어는 J-부분공간(유효 관측 배정 + 경계 제외 컬럼)만:
비관측 컬럼은 prior가 v=0으로 pin하므로 부분공간 절단은 무손실이고 상태
텐서가 12×B_sub×K로 줄어든다 (전 도메인 65,988 → 수천).

파이프라인: frame + GK2A slot collocation → J-부분공간 → 구름/맑음 분할 →
동결 mask(배경 H) + 서명 → 결합 obs_eval(맑음: 배치 clear-sky, th/qv
covector; 구름: sharded all-sky, 7필드 covector) → run_dual_minimizer
(hybrid CVT) → O−B/O−A 보고. 손실은 두 파트 모두 σo=1K 순수 이차
(sharded_allsky 내부 관례와 동일) — 파트 간 가중 일관성.
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


def _quad_j_and_masked_bt(bt, y, mask):
    """σo=1K 순수 이차 파트 손실 (sharded_allsky 내부 관례와 동일 산식)."""
    return 0.5 * ((mask * (bt - y)) ** 2).sum()


_K_INDEX_MAX = 9999          # RTTOV K 출력 profile-index 4자리 한계 (case_writer 가드)


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
                             case_root: str, *, n_workers: int, pool):
    """동결 mask 결합 obs_eval — t=0 전용, ObsEvalResult 반환.

    동결 기준은 배경 H: 맑음 파트는 batched_clear_bt(xb), 구름 파트는
    sharded_allsky(xb, grad=False)의 rad_quality. covector는 맑음 th/qv +
    구름 12필드(all-sky 연결 7필드만 비영)를 부분공간 위치에 산개 합성.
    """
    nch = y_bt.shape[1]
    with torch.no_grad():
        _, rq_clear = _clear_bt_chunked(_take(xb_sub, clear_pos),
                                        _take(fc_sub, clear_pos),
                                        clear_cfg, nch)
        probe = sharded_allsky(xb_sub, fc_sub, cloudy_pos, y_bt,
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
    signature = h.hexdigest()

    counters = {"call": 0}

    def obs_eval(t: int, x_t: State):
        if t != 0:
            return None
        counters["call"] += 1
        out = sharded_allsky(x_t, fc_sub, cloudy_pos, y_bt, mask, xland_sub,
                             rttov_cfg, f"{case_root}/c{counters['call']}",
                             n_workers=n_workers, grad=True, pool=pool)
        x_cl, fc_cl = _take(x_t, clear_pos), _take(fc_sub, clear_pos)
        y_cl, m_cl = y_bt[clear_pos], mask[clear_pos]
        g_th = torch.zeros_like(x_cl.th)
        g_qv = torch.zeros_like(x_cl.qv)
        j_parts = []
        for sl in _clear_slices(x_cl.th.shape[0], nch):     # K-인덱스 4자리 청킹
            bt_c, _, leaves = batched_clear_bt(_take(x_cl, sl),
                                               _take(fc_cl, sl), clear_cfg)
            j_c = _quad_j_and_masked_bt(bt_c.to(torch.float64),
                                        y_cl[sl], m_cl[sl])
            gt, gq = torch.autograd.grad(j_c, [leaves.th, leaves.qv],
                                         allow_unused=False)
            g_th[sl], g_qv[sl] = gt, gq
            j_parts.append(float(j_c.detach()))
        adj = {f: torch.zeros_like(getattr(xb_sub, f)) for f in State._fields}
        for fi, f in enumerate(State._fields):
            adj[f][cloudy_pos] = out["adj"][fi]
        adj["th"][clear_pos] += g_th
        adj["qv"][clear_pos] += g_qv
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
                            channels: tuple = ()) -> dict:
    """v9 전 도메인 분석 1회 — JSON 직렬화 가능한 보고 dict 반환.

    grids: dict(p_lay, p_half, t_ref, q_ref) — RTTOV 픽스처 격자/기준 프로파일
    (테스트 헬퍼 또는 케이스 자산에서 공급; 모듈은 tests에 의존하지 않는다).
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
    rttov_cfg = dict(t_ref=t_ref.numpy(), q_ref=q_ref.numpy(),
                     p_lay=p_lay.numpy(), p_half=p_half.numpy(),
                     channels=tuple(channels), coef_id=coef_cloud,
                     oracle_root=str(Path(__file__).resolve().parents[1]))

    prior = default_param_prior(0.2)
    spec, b_sigma = make_default_cvt(xb)
    cfg = WindowConfig(dt=300.0)

    ctx = mp.get_context("spawn")
    pool = ctx.Pool(n_workers)
    try:
        obs_eval = make_fulldomain_obs_eval(
            xb, fc, y_bt, y_rq, xland, cloudy_pos, clear_pos,
            clear_cfg, rttov_cfg, case_root, n_workers=n_workers, pool=pool)
        res = run_dual_minimizer(xb, [fc], obs_eval, cfg, b_sigma, prior,
                                 max_iter=max_iter, cvt=spec)

        # O−B / O−A: 동결 mask로 동일 채널 집합 비교 (배경/분석 각 1회 H)
        mask = obs_eval.mask
        def _masked_abs_mean(x_state):
            with torch.no_grad():
                o = sharded_allsky(x_state, fc, cloudy_pos, y_bt,
                                   torch.zeros_like(y_bt), xland, rttov_cfg,
                                   f"{case_root}/rep", n_workers=n_workers,
                                   grad=False, pool=pool)
                bt = torch.zeros_like(y_bt)
                bt[cloudy_pos] = o["bt"]
                bt_cl, _ = _clear_bt_chunked(_take(x_state, clear_pos),
                                             _take(fc, clear_pos), clear_cfg,
                                             y_bt.shape[1])
                bt[clear_pos] = bt_cl
            return float((mask * (y_bt - bt)).abs().sum() / mask.sum())

        omb = _masked_abs_mean(xb)
        oma = _masked_abs_mean(res.x_analysis)
    finally:
        pool.close()
        pool.join()

    dnorm = {f: float((getattr(res.x_analysis, f) - getattr(xb, f)).norm())
             for f in State._fields}
    return dict(
        n_domain=int(fr.state.th.shape[0]), n_subspace=int(sub.numel()),
        n_cloudy=int(cloudy_pos.numel()), n_clear=int(clear_pos.numel()),
        n_valid=int(mask.sum()),
        caps=dict(max_cloudy=max_cloudy, max_clear=max_clear),
        j_trace=res.j_trace, omb=omb, oma=oma,
        theta=[float(t) for t in res.theta_analysis],
        increment_norms=dnorm, cvt=res.cvt,
        wall_s=time.time() - t0)
