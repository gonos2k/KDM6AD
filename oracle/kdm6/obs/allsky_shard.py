"""all-sky 관측연산자의 프로세스 샤딩 — 전 도메인 실행의 병렬 축.

배경: all-sky 0.56 s/컬럼은 RTTOV 산란 계산 자체(배칭 레버 ~1.3× 실측)라
프로세스 병렬화가 유일한 스케일 축이다. da_parallel(창 샤딩)과 동일 규약:
spawn-안전 모듈-레벨 워커, 워커당 torch 단일스레드, 명시적 컬럼 계약.

워커는 자기 샤드의 구름 컬럼들에 대해 단일컬럼 all-sky(H, 선택적 adjoint)를
수행하고 (j, adj, bt, rq)를 반환한다. 맑음 컬럼(배치 clear-sky)은 호출측
메인 프로세스 몫이다 (전체의 ~10% 비용).

결정론: 컬럼별 계산이 독립이고 f64 합산이 컬럼 내로 국한되므로 샤딩 결과는
직렬 루프와 bitwise 동일해야 한다 — 게이트 테스트로 고정.
"""
from __future__ import annotations

import os

import numpy as np
import torch

_F64 = dict(dtype=torch.float64)


def _allsky_columns_worker(args: dict) -> dict:
    """spawn-안전 워커: 샤드의 구름 컬럼들에 대한 all-sky H (+adjoint).

    args (전부 numpy/기본형 — spawn pickling):
      state (12, n, K) · forcing (4, n, K) · xland (n,) · y_bt (n, nch) ·
      mask (n, nch) [동결 QC] · t_ref/q_ref/p_lay/p_half (RTTOV 격자) ·
      case_root · worker_id · grad · channels/coef_id
    """
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    torch.set_num_threads(1)
    import sys
    sys.path.insert(0, args["oracle_root"])
    sys.path.insert(0, args["oracle_root"] + "/tests")
    from kdm6.da_driver import _blend_above_model_top
    from kdm6.obs.model_profile_builder import (RttovProfileConfig,
                                                model_to_rttov_tensors)
    from kdm6.obs.rttov_case_writer import make_live_run_k
    from kdm6.obs.rttov_input_builder import RttovInputConfig
    from kdm6.obs.rttov_obs_operator import RttovObsOp
    from kdm6.state import Forcing, State

    st = torch.as_tensor(args["state"], **_F64)          # (12, n, K)
    fc = torch.as_tensor(args["forcing"], **_F64)        # (4, n, K)
    xland = torch.as_tensor(args["xland"], **_F64)
    y_bt = torch.as_tensor(args["y_bt"], **_F64)
    mask = torch.as_tensor(args["mask"], **_F64)
    t_ref = torch.as_tensor(args["t_ref"], **_F64)
    q_ref = torch.as_tensor(args["q_ref"], **_F64)
    pcfg = RttovProfileConfig(
        gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
        rttov_layer_pressure=torch.as_tensor(args["p_lay"], **_F64),
        rttov_level_pressure=torch.as_tensor(args["p_half"], **_F64), cloud=True)
    icfg = RttovInputConfig(coef_id=args["coef_id"], channels=tuple(args["channels"]))
    n, nch = y_bt.shape
    K = st.shape[2]
    grad = bool(args["grad"])

    j_cols = np.zeros(n)                     # 컬럼별 j — 합산은 부모가 고정 순서로
    adj = np.zeros((12, n, K)) if grad else None
    bt_out = np.zeros((n, nch))
    rq_out = np.ones((n, nch))
    for i in range(n):
        leaves = State(*(torch.flip(st[f, i], [-1]).detach().clone()
                         .requires_grad_(grad) for f in range(12)))
        fcol = Forcing(rho=torch.flip(fc[0, i], [-1]), pii=torch.flip(fc[1, i], [-1]),
                       p=torch.flip(fc[2, i], [-1]) / 100.0,
                       delz=torch.flip(fc[3, i], [-1]))
        prof = model_to_rttov_tensors(leaves, fcol, pcfg, xland=xland[i])
        p_top = fcol.p[0].reshape(1)
        tl = _blend_above_model_top(prof.t_lay.unsqueeze(0), t_ref, prof.p_lay,
                                    p_top, octaves=1.0).squeeze(0)
        ql = _blend_above_model_top(prof.q_lay.unsqueeze(0), q_ref, prof.p_lay,
                                    p_top, octaves=4.0).squeeze(0)
        above = (prof.p_lay < p_top).double().detach()
        case_dir = f"{args['case_root']}/w{args['worker_id']}_{i}"
        try:
            bt_i, rq_i = RttovObsOp.apply(
                make_live_run_k(case_dir),
                icfg, tl, ql, None, prof.p_half,
                prof.clw * (1 - above), prof.ciw * (1 - above),
                prof.deff_liq, prof.deff_ice, prof.cfrac)
        finally:
            # 디스크 고갈 방지 — 실패 경로 포함(finally; 재검토 #6): K는
            # forward에서 ctx.k_dict로 파싱 완료라 케이스(~14MB)는 즉시 삭제
            # 가능 (실측: 20만 케이스 = 107GB → /tmp 고갈·크래시).
            import shutil
            shutil.rmtree(case_dir, ignore_errors=True)
        bt_v = bt_i.reshape(-1).to(torch.float64)
        bt_out[i] = bt_v.detach().numpy()
        rq_out[i] = rq_i.reshape(-1).numpy()
        if grad:
            r = mask[i] * (bt_v - y_bt[i])
            delta = args.get("huber_delta")
            if delta is None:                      # 구계약: σo=1K 순수 이차
                j_i = 0.5 * (r ** 2).sum()
            else:                                  # Huber — 대형 departure 완화
                from kdm6.obs.obs_loss import _huber
                j_i = _huber(r, float(delta)).sum()
            j_i.backward()
            j_cols[i] = float(j_i.detach())
            # connected-field sever 검사 (재검토 #9): all-sky 연산자에 직접
            # 연결되는 필드의 None grad는 구조적 그래프 단절 — 조용한 0 대신
            # 거부. (qr/qg/nccn/nr/bg는 직접 경로 없음 — 0 허용.)
            _CONNECTED = (0, 1, 2, 4, 5, 8, 9)   # th qv qc qi qs nc ni
            if float(mask[i].sum()) > 0:
                for f in _CONNECTED:
                    if leaves[f].grad is None:
                        raise RuntimeError(
                            f"connected field index {f} has None grad at column "
                            f"{i} — structural graph sever in the all-sky path "
                            "(silent zero would corrupt the adjoint)")
            for f in range(12):
                g = leaves[f].grad
                if g is not None:
                    adj[f, i] = torch.flip(g, [-1]).numpy()
    out = dict(j_cols=j_cols, bt=bt_out, rq=rq_out)
    if grad:
        out["adj"] = adj
    return out


def sharded_allsky(state: "State", forcing: "Forcing", cidx: torch.Tensor,
                   y_bt: torch.Tensor, mask: torch.Tensor,
                   xland: torch.Tensor, rttov_cfg: dict, case_root: str,
                   *, n_workers: int = 8, grad: bool = True,
                   huber_delta: "float | None" = None,
                   pool=None) -> dict:
    """구름 컬럼 집합 cidx의 all-sky H(+adjoint)를 n_workers로 샤딩.

    반환 dict: j(float), bt (n,nch), rq (n,nch), adj (12,n,K; grad시) — 순서는
    cidx 순. rttov_cfg: t_ref/q_ref/p_lay/p_half(np), channels, coef_id,
    oracle_root. pool을 주면 재사용(스폰 비용 상각), 아니면 1회용 생성.
    """
    import multiprocessing as mp

    n = int(cidx.numel())
    st = torch.stack(list(state))[:, cidx].numpy()          # (12, n, K)
    fc = torch.stack(list(forcing))[:, cidx].numpy()
    chunks = np.array_split(np.arange(n), n_workers)
    jobs = []
    for w, ch in enumerate(chunks):
        if len(ch) == 0:
            continue
        jobs.append(dict(rttov_cfg, state=st[:, ch], forcing=fc[:, ch],
                         xland=xland[cidx][ch].numpy(),
                         y_bt=y_bt[cidx][ch].numpy(), mask=mask[cidx][ch].numpy(),
                         case_root=case_root, worker_id=w, grad=grad,
                         huber_delta=huber_delta))
    own = pool is None
    if own:
        ctx = mp.get_context("spawn")
        pool = ctx.Pool(n_workers)
    try:
        outs = pool.map(_allsky_columns_worker, jobs)
    finally:
        if own:
            pool.close(); pool.join()
    nch = y_bt.shape[1]
    K = st.shape[2]
    bt = np.zeros((n, nch)); rq = np.ones((n, nch))
    adj = np.zeros((12, n, K)) if grad else None
    j_cols = np.zeros(n)
    for out, ch in zip(outs, [c for c in chunks if len(c)]):
        bt[ch] = out["bt"]; rq[ch] = out["rq"]; j_cols[ch] = out["j_cols"]
        if grad:
            adj[:, ch] = out["adj"]
    # 결정론적 합산 (Codex D5): 컬럼 고정 순서 fsum — 워커 수와 무관한 J
    import math
    j = math.fsum(j_cols.tolist())
    return dict(j=j, bt=torch.as_tensor(bt, **_F64),
                rq=torch.as_tensor(rq, **_F64),
                adj=None if not grad else torch.as_tensor(adj, **_F64))
