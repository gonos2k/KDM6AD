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
from .da_partition import PartitionSpec
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


QTOT_MIN = 1.0e-5            # model-cloud condensate threshold [kg/kg summed]


def select_membership(fr, co, *, boundary: int = 10) -> torch.Tensor:
    """J-subspace membership: interior columns with at least one valid
    channel. Returns full-domain column indices.

    The cloudy/clear PHYSICAL partition is computed later from the slot-time
    background state (review #3) — membership itself is time-independent."""
    nx, ny = int(fr.meta["nx"]), int(fr.meta["ny"])
    b = torch.arange(fr.state.th.shape[0])
    i, j = b % nx, b // nx
    interior = ((i >= boundary) & (i < nx - boundary)
                & (j >= boundary) & (j < ny - boundary))
    has_obs = (co.obs_quality == 0).any(dim=1)
    return torch.where(interior & has_obs)[0]


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


def parse_utc_s(s: str) -> float:
    """Parse a UTC time string to epoch seconds.

    Accepts the two in-repo formats: GK2A slot stamps (yyyymmddHHMM, from
    read_ko_slot filenames) and WRF Times (YYYY-MM-DD_HH:MM:SS)."""
    from datetime import datetime, timezone
    for fmt in ("%Y%m%d%H%M", "%Y-%m-%d_%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).replace(
                tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    raise ValueError(f"unrecognized UTC time string {s!r} — expected "
                     "yyyymmddHHMM (GK2A stamp) or YYYY-MM-DD_HH:MM:SS "
                     "(WRF Times)")


def derive_obs_offset_s(obs_valid_time: str, frame_valid_time: str) -> float:
    """Obs valid time minus frame valid time [s], both from the DATA —
    the alignment check must not depend on caller-typed numbers (review #1)."""
    return parse_utc_s(obs_valid_time) - parse_utc_s(frame_valid_time)


def check_obs_time_alignment(obs_time: int, dt: float, *,
                             obs_offset_s: float,
                             time_tolerance_s: float) -> None:
    """Enforce |obs_time*dt - obs_offset_s| <= time_tolerance_s.

    obs_offset_s is the obs valid time minus the frame valid time (seconds).
    The slot state x_{obs_time} is valid at t0 + obs_time*dt; comparing a
    displaced observation silently biases the innovation (review #1 — the
    LC05 fixture pairs a 00:00 UTC obs with the 00:05 slot at the defaults,
    which passes only because the tolerance says so, explicitly)."""
    # NaN comparisons are False, so non-finite inputs would fail OPEN here
    # (Codex) — validate before comparing.
    if not (math.isfinite(dt) and dt > 0.0):
        raise ValueError(f"dt must be finite and > 0 (got {dt!r})")
    if not math.isfinite(obs_offset_s):
        raise ValueError(f"obs_offset_s must be finite (got {obs_offset_s!r})")
    if not (math.isfinite(time_tolerance_s) and time_tolerance_s >= 0.0):
        raise ValueError(f"time_tolerance_s must be finite and >= 0 "
                         f"(got {time_tolerance_s!r})")
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


def evaluate_artifact_gates(rep: dict) -> dict:
    """Acceptance gates for an evidence artifact — ENFORCED, not advisory.

    A run whose slot-time state exploded, whose J did not descend, or whose
    diagnostics went non-finite must be rejected (runner exits nonzero); a
    reported-but-unenforced pathology produces passing-looking artifacts.
    Returns {gate_name: bool, ..., "accepted": bool}."""
    jt = [d["total"] for d in rep["j_trace"]]
    gates = dict(
        j_descended=(len(jt) >= 2 and jt[-1] < jt[0]
                     and all(math.isfinite(v) for v in jt)),
        oma_le_omb=(math.isfinite(rep["oma"]) and math.isfinite(rep["omb"])
                    and rep["oma"] <= rep["omb"]),
        pathology_t0_empty=(rep["pathology_t0"] == {}),
        pathology_slot_empty=(rep["pathology_slot"] == {}),
        no_nonfinite_t0=(rep["nonfinite_fields_t0"] == []),
        no_nonfinite_slot=(rep["nonfinite_fields_slot"] == []),
        finite_diagnostics=math.isfinite(rep["grad_theta_norm_final"]),
    )
    # Conserving-artifact gates — FAIL-CLOSED (reviewer P1): once a report
    # declares itself conserving (flag or artifact_role), ALL conserving
    # gates are generated unconditionally, and a missing/None/malformed
    # evidence field evaluates to False — a regression that drops a field
    # must never shrink the gate set into a silent pass. Legacy reports
    # (no conserving markers/keys) keep their gate set unchanged.
    conserving = (rep.get("conserving") is True
                  or rep.get("artifact_role") == "conserving_stress")
    if conserving or rep.get("water_budget") is not None:
        gates["pw_conserved"] = _gate_pw_conserved(rep)
    if conserving or "n_audit_evals" in rep:
        gates["final_audited"] = _gate_final_audited(rep)
    if conserving:
        gates["conserving_contract"] = _gate_conserving_contract(rep)
    gates["accepted"] = all(gates.values())
    return gates


def _is_finite_number(x) -> bool:
    return (isinstance(x, (int, float)) and not isinstance(x, bool)
            and math.isfinite(x))


def _gate_pw_conserved(rep: dict) -> bool:
    """P_w stage total-water error (unweighted vertical level sum) at the
    roundoff floor. False on any missing/malformed field (fail-closed)."""
    wb = rep.get("water_budget")
    if not isinstance(wb, dict):
        return False
    err = wb.get("pw_stage_err_max")
    return _is_finite_number(err) and err < 1.0e-12


def _gate_final_audited(rep: dict) -> bool:
    """The report's finals come from exactly one authoritative audit closure
    and are internally consistent: trace length = optimizer evals + 1 audit,
    the trace tail equals the sum of the final J components exactly, and
    every final/gradient diagnostic is finite. False on any missing or
    malformed field (fail-closed)."""
    try:
        jt = rep["j_trace"]
        total = jt[-1]["total"]
        finals = [rep["jb_final"], rep["jtheta_final"], rep["jobs_final"],
                  rep["grad_theta_norm_final"]]
        if rep.get("grad_w_norm_final") is not None:
            finals.append(rep["grad_w_norm_final"])
        return (rep["n_audit_evals"] == 1
                and len(jt) == rep["n_window_evals"] + 1
                and all(_is_finite_number(v) for v in finals)
                and _is_finite_number(total)
                and rep["jb_final"] + rep["jtheta_final"]
                + rep["jobs_final"] == total)
    except (KeyError, TypeError, IndexError):
        return False


def _gate_conserving_contract(rep: dict) -> bool:
    """The conserving contract held in the recorded configuration: the
    partition ran under the v2 (dimensionless-w) schema and every mass
    hydrometeor diagonal control was OFF. False on missing/malformed
    records (fail-closed)."""
    try:
        if rep["partition"]["spec"]["version"] != 2:
            return False
        nc = rep["cvt"]["n_controlled"]
        return all(nc[f] == 0 for f in ("qc", "qr", "qi", "qs", "qg"))
    except (KeyError, TypeError):
        return False


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
    """Model/obs cloud 4-regime codes (B_sub,) — 1: clear/clear,
    2: clear/cloudy, 3: cloudy/cloudy, 4: cloudy/clear; 0: ir channel
    invalid (unclassifiable).

    Model cloud = the PHYSICAL slot-time condensate partition (pass
    model_cloudy_pos, NOT the all-sky routing set which absorbs regime-2
    columns — review #2). Obs cloud = frozen-mask-valid ir105 BT < bt_cloud.
    Stratification axes for the directionality audit: (2) watches th/qv
    aliasing (creation-gated regime), (4) checks the removal direction.
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
    """Chunked clear-sky BT/rq (no-grad use — frozen probe and report).

    An empty clear partition (all-cloudy / all-regime2 scene) returns
    (0, nch) tensors without touching RTTOV — review #6."""
    if x_cl.th.shape[0] == 0:
        return (torch.zeros((0, nch), **_F64), torch.ones((0, nch), **_F64))
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
                            obs_offset_s: "float | None" = None,
                            time_tolerance_s: float = 60.0,
                            ncmin_land: float = 100.0,
                            ncmin_sea: float = 10.0,
                            qv_levels: int = 12,
                            huber_delta: "float | None" = 3.0,
                            pseudo_rh: bool = False,
                            pseudo_sigma_p: float = 2.0e-4,
                            conserving: bool = False,
                            save_fields: "str | None" = None) -> dict:
    """전 도메인 분석 1회 — JSON 직렬화 가능한 보고 dict 반환.

    grids: dict(p_lay, p_half, t_ref, q_ref) — RTTOV 픽스처 격자/기준 프로파일
    (테스트 헬퍼 또는 케이스 자산에서 공급; 모듈은 tests에 의존하지 않는다).
    obs_time=1(기본): 관측이 M(미세물리 1스텝)을 관통 — θ·결합 기울기 활성
    (P0-1; obs_time=0은 3D-Var형 직접 조정으로 퇴화, θ는 prior에 pin).
    huber_delta: 양 파트 관측손실의 Huber δ[K] (P0-3; None=구계약 순수 이차).
    pseudo_rh=True: 모델-맑음/관측-구름 컬럼에 동결 pseudo-RH 부트스트랩
    합성 (P0-2; da_regime2 — 구름정상 온도매칭 층, 상전이-인지 동결 목표).
    conserving=True: P1-1 conserving CVT — mass-hydro diagonal sigma zeroed,
    species move only through the signed partition channels (da_partition);
    the report separates the P_w-stage water error (roundoff) from the
    deliberate qv-diagonal total-water change, and finals come from the
    single authoritative audit closure.
    save_fields: npz 경로 — 영상화/후속 분석용 배경·분석 필드 + bt/regime.
    """
    from .obs.model_profile_builder import RttovProfileConfig
    from .obs.rttov_case_writer import make_live_run_k
    from .obs.rttov_input_builder import RttovInputConfig
    import multiprocessing as mp
    import numpy as np

    t0 = time.time()
    jset = select_membership(fr, co, boundary=boundary)
    if jset.numel() == 0:
        raise ValueError("empty J-subspace — no interior column carries a "
                         "valid observation channel")
    xb = _take(fr.state, jset)
    fc = _take(fr.forcing, jset)
    xland = fr.xland[jset]
    y_bt, y_rq = co.bt[jset], co.obs_quality[jset]

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
    if obs_time not in (0, 1):
        raise ValueError(f"obs_time must be 0 or 1 (got {obs_time}) — the "
                         "driver runs a single-step window")
    for name, v in (("ncmin_land", ncmin_land), ("ncmin_sea", ncmin_sea)):
        if not (math.isfinite(v) and v >= 0.0):
            raise ValueError(f"{name} must be finite and >= 0 (got {v!r})")
    # WRF contract: xland in {1 (land), 2 (water)} — anything else would be
    # silently binarized by the <1.5 threshold (e.g. -999 fill values).
    if not bool(((xland == 1.0) | (xland == 2.0)).all()):
        raise ValueError("xland must be WRF {1, 2} (land/water) — got values "
                         "outside the contract (fill values? wrong field?)")
    for name, v in (("max_cloudy", max_cloudy), ("max_clear", max_clear)):
        if v is not None and (isinstance(v, bool) or not isinstance(v, int)
                              or v < 0):
            raise ValueError(f"{name} must be None or a plain int >= 0 "
                             f"(got {v!r}) — negative values are Python "
                             "slices, not caps")
    # qv_levels means "lowest N levels"; N > K naturally selects all levels
    # (the builder's k < qv_levels mask) — only the type/sign is enforced.
    if (isinstance(qv_levels, bool) or not isinstance(qv_levels, int)
            or qv_levels < 0):
        raise ValueError(f"qv_levels must be a plain int >= 0 "
                         f"(got {qv_levels!r})")
    # Valid-time alignment (review #1): the offset comes from the DATA
    # (GK2A slot stamp vs WRF Times); an explicit obs_offset_s overrides.
    # A displacement beyond the tolerance is a time-representativeness
    # decision the caller must state (larger tolerance), never a default.
    obs_vt = getattr(co, "valid_time_utc", None)
    frame_vt = fr.meta.get("valid_time_utc")
    derived = (derive_obs_offset_s(obs_vt, frame_vt)
               if obs_vt is not None and frame_vt is not None else None)
    if obs_offset_s is None:
        if derived is None:
            raise ValueError(
                "cannot derive the obs-frame time offset: obs valid_time_utc "
                f"({obs_vt!r}) or frame valid_time_utc ({frame_vt!r}) missing "
                "— pass obs_offset_s explicitly")
        obs_offset_s = derived
        offset_source = "data"
    else:
        # An explicit override that contradicts the data timestamps is a
        # configuration error, not a preference — fail closed.
        if derived is not None and obs_offset_s != derived:
            raise ValueError(
                f"explicit obs_offset_s={obs_offset_s:g}s contradicts the "
                f"data-derived offset {derived:g}s "
                f"({obs_vt!r} vs {frame_vt!r}) — drop the override")
        offset_source = "explicit"
    check_obs_time_alignment(obs_time, dt, obs_offset_s=obs_offset_s,
                             time_tolerance_s=time_tolerance_s)

    import dataclasses

    def _forward_to_slot(x_state, fc_, cfg_, params=None):
        """State at the obs slot time — one M step via the forward-only
        collector (run_da_window pays the VJP sweep and manages its own
        grad contexts, so it must NOT be wrapped in no_grad — same probe
        discipline as the frozen adapter). params selects theta: None keeps
        theta_b; pass theta_a for analysis-consistent O-A (review #3)."""
        if obs_time == 0:
            return x_state
        from .da_window import collect_window_trajectory
        cfg_p = cfg_ if params is None else dataclasses.replace(
            cfg_, params=params)
        return collect_window_trajectory(x_state, [fc_], cfg_p,
                                         {obs_time})[obs_time]

    # PHYSICAL model-cloud partition from the SLOT-TIME background state —
    # the observation applies to x_slot = M(x0), so cloud created/destroyed
    # within the step must classify and route accordingly (review #3).
    cfg = WindowConfig(dt=dt, xland=xland,
                       ncmin_land=ncmin_land, ncmin_sea=ncmin_sea)
    x_slot_bg = _forward_to_slot(xb, fc, cfg)
    qtot_slot = (x_slot_bg.qc + x_slot_bg.qi + x_slot_bg.qs).sum(-1)
    mc = torch.where(qtot_slot > QTOT_MIN)[0]
    cl = torch.where(qtot_slot <= QTOT_MIN)[0]
    n_mc_precap, n_cl_precap = int(mc.numel()), int(cl.numel())
    if max_cloudy is not None:
        mc = mc[:max_cloudy]
    if max_clear is not None:
        cl = cl[:max_clear]
    keep = torch.cat([mc, cl])
    if keep.numel() == 0:
        raise ValueError(
            "empty working subspace after the caps "
            f"(max_cloudy={max_cloudy}, max_clear={max_clear}; "
            f"partition {n_mc_precap} cloudy / {n_cl_precap} clear "
            "before caps) — nothing to minimize")
    xb, fc, xland = _take(xb, keep), _take(fc, keep), xland[keep]
    x_slot_bg = _take(x_slot_bg, keep)
    y_bt, y_rq = y_bt[keep], y_rq[keep]
    model_cloudy_pos = torch.arange(mc.numel())
    model_clear_pos = torch.arange(mc.numel(), keep.numel())
    cfg = WindowConfig(dt=dt, xland=xland,
                       ncmin_land=ncmin_land, ncmin_sea=ncmin_sea)

    def _slot_state(x_state, params=None):
        return _forward_to_slot(x_state, fc, cfg, params=params)

    # Operator ROUTING set is distinct from the physical classification
    # (review #2): regime-2 columns go through all-sky H so that M-created
    # condensate flips cfrac live and the BT term can refine — but they stay
    # model-clear for the 4-regime report.
    pseudo = None
    r2 = torch.empty(0, dtype=torch.int64)
    if pseudo_rh:
        from .da_regime2 import cloud_top_levels, frozen_saturation_target
        r2 = select_regime2_positions(y_bt, y_rq, model_clear_pos)
        if r2.numel():
            pseudo = dict(cols=r2,
                          target=frozen_saturation_target(x_slot_bg, fc, r2),
                          levels=cloud_top_levels(x_slot_bg, fc, r2,
                                                  y_bt[r2, IR105_COL]),
                          sigma_p=pseudo_sigma_p)
    allsky_pos = torch.cat([model_cloudy_pos, r2])
    in_r2 = torch.zeros(keep.numel(), dtype=torch.bool)
    in_r2[r2] = True
    clear_op_pos = model_clear_pos[~in_r2[model_clear_pos]]

    # B support is fixed a priori by the caller (qv_levels) — NOT switched by
    # the observed cloud (observation-dependent B is forbidden, review #8).
    # The overlap validation fail-fasts when the pseudo band falls outside.
    spec, b_sigma = make_default_cvt(
        xb, qv_levels=qv_levels,
        sigma_overrides=({"qc": 0.0, "qi": 0.0, "qs": 0.0}
                         if conserving else None))
    pspec = PartitionSpec() if conserving else None
    if pseudo is not None:
        validate_pseudo_qv_overlap(b_sigma.qv, pseudo["cols"],
                                   pseudo["levels"])

    ctx = mp.get_context("spawn")
    pool = ctx.Pool(n_workers)
    try:
        obs_eval = make_fulldomain_obs_eval(
            xb, fc, y_bt, y_rq, xland, allsky_pos, clear_op_pos,
            clear_cfg, rttov_cfg, case_root, n_workers=n_workers, pool=pool,
            obs_time=obs_time, huber_delta=huber_delta,
            x_slot_bg=x_slot_bg, pseudo=pseudo)
        res = run_dual_minimizer(xb, [fc], obs_eval, cfg, b_sigma, prior,
                                 max_iter=max_iter, cvt=spec,
                                 partition=pspec)

        # O-B / O-A on the frozen mask at the obs slot time. O-A must use the
        # OPTIMIZED theta_a — H(M(x_a; theta_b)) is not the analysis pair and
        # disagrees with the joint objective (review #3).
        mask = obs_eval.mask
        def _h_bt(x_slot):
            with torch.no_grad():
                o = sharded_allsky(x_slot, fc, allsky_pos, y_bt,
                                   torch.zeros_like(y_bt), xland, rttov_cfg,
                                   f"{case_root}/rep", n_workers=n_workers,
                                   grad=False, pool=pool)
                bt = torch.zeros_like(y_bt)
                bt[allsky_pos] = o["bt"]
                bt_cl, _ = _clear_bt_chunked(_take(x_slot, clear_op_pos),
                                             _take(fc, clear_op_pos),
                                             clear_cfg, y_bt.shape[1])
                bt[clear_op_pos] = bt_cl
            return bt

        # Slot-time analysis state uses the OPTIMIZED theta_a — otherwise the
        # reported O-A is H(M(x_a; theta_b)), not the analysis pair (review
        # #3). The slot states are kept for slot-time increment reporting.
        x_slot_a = _slot_state(res.x_analysis, params=res.theta_analysis)
        bt_b, bt_a = _h_bt(x_slot_bg), _h_bt(x_slot_a)
    finally:
        pool.close()
        pool.join()

    def _masked_abs_mean(bt, rows=None):
        m = mask if rows is None else mask[rows]
        r = (y_bt - bt) if rows is None else (y_bt[rows] - bt[rows])
        return float((m * r).abs().sum() / m.sum()) if float(m.sum()) else 0.0

    omb, oma = _masked_abs_mean(bt_b), _masked_abs_mean(bt_a)

    # 4-regime stratification uses the PHYSICAL model-cloud set — the all-sky
    # ROUTING set (which absorbs regime-2 columns) must not leak into the
    # classification (review #2). Increments are reported at BOTH times:
    # t0 (control increments) and the slot time (what the obs actually saw —
    # pseudo-created condensate only exists at the slot, review #4).
    sub = jset[keep]
    code = classify_regimes(int(sub.numel()), y_bt, mask, model_cloudy_pos)
    # the 4-regime table covers only IR105-classifiable profiles; the
    # unclassified remainder still contributes other-channel radiances to
    # the GLOBAL O-B/O-A (reviewer caveat 3) — report the coverage honestly
    n_unclassified = int((code == 0).sum())
    dqtot_slot = ((x_slot_a.qc + x_slot_a.qi + x_slot_a.qs)
                  - (x_slot_bg.qc + x_slot_bg.qi + x_slot_bg.qs)).sum(-1)
    regimes = {}
    for c, name in REGIME_NAMES.items():
        rows = torch.where(code == c)[0]
        regimes[name] = dict(
            n=int(rows.numel()),
            omb=_masked_abs_mean(bt_b, rows), oma=_masked_abs_mean(bt_a, rows),
            dqtot_slot_mean=(float(dqtot_slot[rows].mean())
                             if rows.numel() else 0.0),
            dth_t0_mean=(float((res.x_analysis.th - xb.th)[rows].mean())
                         if rows.numel() else 0.0),
            dth_slot_mean=(float((x_slot_a.th - x_slot_bg.th)[rows].mean())
                           if rows.numel() else 0.0))

    if save_fields is not None:
        np.savez_compressed(
            save_fields, sub_idx=sub.numpy(),
            nx=int(fr.meta["nx"]), ny=int(fr.meta["ny"]),
            n_model_cloudy=int(model_cloudy_pos.numel()),
            n_allsky=int(allsky_pos.numel()), mask=mask.numpy(),
            y_bt=y_bt.numpy(), bt_b=bt_b.numpy(), bt_a=bt_a.numpy(),
            regime=code.numpy(),
            theta_b=np.array([float(t) for t in prior.theta_b]),
            theta_a=np.array([float(t) for t in res.theta_analysis]),
            **{f"xb_{f}": getattr(xb, f).numpy() for f in State._fields},
            **{f"xa_{f}": getattr(res.x_analysis, f).numpy()
               for f in State._fields},
            **{f"xslot_b_{f}": getattr(x_slot_bg, f).numpy()
               for f in State._fields},
            **{f"xslot_a_{f}": getattr(x_slot_a, f).numpy()
               for f in State._fields})

    dnorm = {f: float((getattr(res.x_analysis, f) - getattr(xb, f)).norm())
             for f in State._fields}
    dnorm_slot = {f: float((getattr(x_slot_a, f)
                            - getattr(x_slot_bg, f)).norm())
                  for f in State._fields}

    # Physical plausibility gates (P0-3): BOTH the analysis initial state
    # AND the slot state the observation actually saw — a slot-time
    # explosion created by M would otherwise pass unseen (re-review #7).
    _HYDRO = ("qc", "qr", "qi", "qs", "qg")

    def _hydro_audit(state):
        minmax = {f: [float(getattr(state, f).min()),
                      float(getattr(state, f).max())] for f in _HYDRO}
        pathology = {f: dict(max=mm[1],
                             n_over=int((getattr(state, f) > 0.05).sum()))
                     for f, mm in minmax.items() if mm[1] > 0.05}
        nonfinite = [f for f in State._fields
                     if not bool(torch.isfinite(getattr(state, f)).all())]
        return minmax, pathology, nonfinite

    hydro_minmax_t0, pathology_t0, nonfinite_t0 = _hydro_audit(res.x_analysis)
    hydro_minmax_slot, pathology_slot, nonfinite_slot = _hydro_audit(x_slot_a)

    # Conserving water budget: separate the P_w-stage error (roundoff by
    # construction) from the DELIBERATE qv-diagonal total-water change —
    # column-integral (sum over K) per column, reviewer-mandated split.
    water_budget = None
    if conserving:
        from .da_cvt import cvt_apply

        def _tw(s):
            return (s.qv + s.qc + s.qr + s.qi + s.qs + s.qg).sum(-1)
        with torch.no_grad():
            y_diag, _ = cvt_apply(xb, b_sigma, res.v_state, spec)
            dtw = _tw(y_diag) - _tw(xb)
            water_budget = dict(
                # unweighted vertical LEVEL SUM of q_t per column — NOT a
                # pressure-weighted column water path (reviewer caveat 5;
                # a dp/g-weighted kg/m^2 variant is roadmap)
                definition="unweighted_vertical_level_sum",
                pw_stage_err_max=float(
                    (_tw(res.x_analysis) - _tw(y_diag)).abs().max()),
                dtw_qv_diag_max=float(dtw.abs().max()),
                dtw_qv_diag_mean=float(dtw.mean()),
                dtw_qv_diag_mean_abs=float(dtw.abs().mean()))

    return dict(
        n_domain=int(fr.state.th.shape[0]), n_subspace=int(sub.numel()),
        n_model_cloudy=int(model_cloudy_pos.numel()),
        n_allsky_routed=int(allsky_pos.numel()),
        n_regime2=int(r2.numel()), n_clear_operator=int(clear_op_pos.numel()),
        n_valid=int(mask.sum()),
        caps=dict(max_cloudy=max_cloudy, max_clear=max_clear),
        obs_time=obs_time, dt=dt, obs_offset_s=obs_offset_s,
        obs_valid_time_utc=obs_vt, frame_valid_time_utc=frame_vt,
        offset_source=offset_source,
        time_tolerance_s=time_tolerance_s, huber_delta=huber_delta,
        ncmin_land=ncmin_land, ncmin_sea=ncmin_sea, qv_levels=qv_levels,
        grad_theta_norm_final=res.grad_theta_norm_final,
        jb_final=res.jb_final, jtheta_final=res.jtheta_final,
        jobs_final=res.jobs_final,
        n_window_evals=res.n_window_evals, n_audit_evals=res.n_audit_evals,
        conserving=conserving, partition=res.partition,
        grad_w_norm_final=res.grad_w_norm_final, water_budget=water_budget,
        j_trace=res.j_trace, omb=omb, oma=oma, regimes=regimes,
        n_unclassified_ir105=n_unclassified,
        regime_coverage=(float((int(sub.numel()) - n_unclassified)
                               / int(sub.numel())) if sub.numel() else 0.0),
        theta=[float(t) for t in res.theta_analysis],
        theta_b=[float(t) for t in prior.theta_b],
        increment_norms=dnorm, increment_norms_slot=dnorm_slot,
        hydro_minmax_t0=hydro_minmax_t0, hydro_minmax_slot=hydro_minmax_slot,
        pathology_t0=pathology_t0, pathology_slot=pathology_slot,
        nonfinite_fields_t0=nonfinite_t0, nonfinite_fields_slot=nonfinite_slot,
        cvt=res.cvt,
        wall_s=time.time() - t0)
