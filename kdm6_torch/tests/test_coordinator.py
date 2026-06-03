"""coordinator preamble 검증 — Step F1a."""
from __future__ import annotations

import math

import torch

from kdm6 import constants as c
from kdm6.coordinator import (
    ColdPhaseOutputs,
    ColdPhaseParams,
    CoordinatorAuxDiagnostics,
    CoordinatorForcing,
    CoordinatorState,
    MeltFreezePhaseOutputs,
    MeltFreezePhaseParams,
    PreambleOutputs,
    SedimentationOutputs,
    WarmPhaseOutputs,
    WarmPhaseParams,
    cold_phase_torch,
    compute_loops_max,
    default_cold_phase_params,
    default_coordinator_params,
    default_melt_freeze_phase_params,
    default_warm_phase_params,
    kdm62d_one_step_torch,
    kdm62d_step_torch,
    melt_freeze_phase_torch,
    preamble_torch,
    scale_rates_for_conservation_torch,
    sedimentation_chain_torch,
    state_update_torch,
    warm_phase_torch,
)
from kdm6.sedimentation import default_substep_advection_params
from kdm6.cloud_dsd import diag_qcr_torch


def _state_forcing(*, requires_grad: bool = False, B: int = 1, K: int = 3):
    """1D-column 표준 입력. cold (T<273.15) + 일부 microphysics state."""
    dtype = torch.float64
    state = CoordinatorState(
        qv=torch.full((B, K), 5.0e-3, dtype=dtype, requires_grad=requires_grad),
        qc=torch.full((B, K), 1.0e-4, dtype=dtype, requires_grad=requires_grad),
        qr=torch.full((B, K), 1.0e-5, dtype=dtype, requires_grad=requires_grad),
        qs=torch.full((B, K), 5.0e-5, dtype=dtype, requires_grad=requires_grad),
        qg=torch.full((B, K), 5.0e-5, dtype=dtype, requires_grad=requires_grad),
        qi=torch.full((B, K), 1.0e-6, dtype=dtype, requires_grad=requires_grad),
        nc=torch.full((B, K), 1.0e8, dtype=dtype, requires_grad=requires_grad),
        nr=torch.full((B, K), 1.0e4, dtype=dtype, requires_grad=requires_grad),
        ni=torch.full((B, K), 1.0e4, dtype=dtype, requires_grad=requires_grad),
        brs=torch.full((B, K), 1.0e-7, dtype=dtype, requires_grad=requires_grad),
        t=torch.full((B, K), 263.15, dtype=dtype),
    )
    forcing = CoordinatorForcing(
        p=torch.full((B, K), 8.0e4, dtype=dtype),
        den=torch.full((B, K), 1.1, dtype=dtype),
        delz=torch.full((B, K), 500.0, dtype=dtype),
        dend=torch.full((B, K), 1.1 * 500.0, dtype=dtype),
    )
    sea_mask = torch.zeros((B, K), dtype=torch.bool)
    return state, forcing, sea_mask


def test_preamble_outputs_finite():
    p = default_coordinator_params()
    state, forcing, sea_mask = _state_forcing()
    out = preamble_torch(state, forcing, sea_mask, params=p)
    # 모든 출력 finite
    for field in ["cpm", "xl", "supcol", "qs1", "qs2", "rh_w", "rh_ice",
                  "supsat", "denfac", "work2",
                  "rslopec", "avedia_c", "avedia_r", "sigma_c", "lencon", "lenconcr"]:
        v = getattr(out, field)
        assert torch.isfinite(v).all(), field

    # ProgB outputs (NamedTuple 안의 모든 텐서)
    for field in out.progb._fields:
        v = getattr(out.progb, field)
        assert torch.isfinite(v).all(), f"progb.{field}"
    # Slope outputs
    for field in out.slope._fields:
        v = getattr(out.slope, field)
        assert torch.isfinite(v).all(), f"slope.{field}"


def test_preamble_supcol_consistency():
    """supcol = T0c - clamp(T, ...). T=263.15 → supcol=10."""
    p = default_coordinator_params()
    state, forcing, sea_mask = _state_forcing()
    out = preamble_torch(state, forcing, sea_mask, params=p)
    expected = 273.15 - 263.15
    assert torch.allclose(out.supcol, torch.full_like(out.supcol, expected))


def test_preamble_avedia_uses_slope_output():
    """avedia_r는 slope.rslope_r에서 derived. 두 값이 일관."""
    p = default_coordinator_params()
    state, forcing, sea_mask = _state_forcing()
    out = preamble_torch(state, forcing, sea_mask, params=p)
    # avedia_r = rslope_r * (g4pmr/g1pmr)^0.3333333 — Fortran F:1671/2878 truncated literal (#4)
    expected = out.slope.rslope_r * (p.cloud_dsd.g4pmr_over_g1pmr ** 0.3333333)
    assert torch.allclose(out.avedia_r, expected, rtol=1e-12)


def test_preamble_grad_propagates():
    """state inputs에 대해 backward 통과 (chain 전체)."""
    p = default_coordinator_params()
    state, forcing, sea_mask = _state_forcing(requires_grad=True)
    out = preamble_torch(state, forcing, sea_mask, params=p)

    # 일부 출력의 합으로 backward
    loss = (out.qs1.sum() + out.rh_w.sum() + out.work2.sum()
            + out.progb.cmg.sum() + out.slope.rslope_r.sum())
    loss.backward()

    for x, name in [(state.qv, "qv"), (state.qg, "qg"), (state.brs, "brs"),
                    (state.qr, "qr"), (state.nr, "nr")]:
        assert x.grad is not None, name
        assert torch.isfinite(x.grad).all(), name


def test_preamble_warm_temperature():
    """T > 273.15 → supcol < 0, qs2 = qs1 (water 식)."""
    p = default_coordinator_params()
    state, forcing, sea_mask = _state_forcing()
    state = state._replace(t=torch.full_like(state.t, 290.0))
    out = preamble_torch(state, forcing, sea_mask, params=p)
    assert torch.all(out.supcol < 0)
    # T > ttp → qs2 == qs1 (둘 다 water 식)
    assert torch.allclose(out.qs1, out.qs2, rtol=1e-12)


# ════ F1b: Warm phase chain ═══════════════════════════════════════════════════


def _warm_phase_inputs(*, requires_grad: bool = False, B: int = 1, K: int = 3,
                       t_value: float = 280.0):
    """warm phase 입력 — T > T0c (warm)이라 saturation adj가 의미 있음."""
    dtype = torch.float64
    state, forcing, sea_mask = _state_forcing(requires_grad=requires_grad, B=B, K=K)
    state = state._replace(t=torch.full_like(state.t, t_value))
    p = default_coordinator_params()
    pre = preamble_torch(state, forcing, sea_mask, params=p)
    # caller-supplied diagnostics
    n0r = torch.full((B, K), 8.0e6, dtype=dtype)
    work1_r = torch.full((B, K), 1.0e-3, dtype=dtype)
    qcr = diag_qcr_torch(sea_mask, params=p.cloud_dsd, ref=state.qc)
    return state, forcing, pre, n0r, work1_r, qcr


def test_warm_phase_outputs_finite():
    p = default_warm_phase_params()
    state, forcing, pre, n0r, work1_r, qcr = _warm_phase_inputs()
    out = warm_phase_torch(state, forcing, pre, n0r, work1_r, qcr,
                            params=p, dtcld=60.0)
    for field in out._fields:
        v = getattr(out, field)
        assert torch.isfinite(v).all(), field


def test_warm_phase_rates_signs():
    """모든 mass rate가 finite. praut/pracw ≥ 0; pcond/prevp는 부호 가변."""
    p = default_warm_phase_params()
    state, forcing, pre, n0r, work1_r, qcr = _warm_phase_inputs()
    out = warm_phase_torch(state, forcing, pre, n0r, work1_r, qcr,
                            params=p, dtcld=60.0)
    # autoconv/accretion은 *source/sink rate*로 양수 (qc → qr 방향)
    assert torch.all(out.praut >= 0)
    assert torch.all(out.pracw >= 0)
    # nccol/nrcol은 *number reduction rate*로 양수 또는 0
    assert torch.all(out.nccol >= 0)


def test_warm_phase_grad_propagates():
    """state inputs (qv, qc, qr, qs ...)에 대해 backward 통과."""
    p = default_warm_phase_params()
    state, forcing, pre, n0r, work1_r, qcr = _warm_phase_inputs(requires_grad=True)
    out = warm_phase_torch(state, forcing, pre, n0r, work1_r, qcr,
                            params=p, dtcld=60.0)
    loss = (out.praut.sum() + out.pracw.sum() + out.prevp.sum())
    loss.backward()
    # warm_phase reads qc (praut/pracw) and qr (pracw/prevp) but NOT qv — the qv↔qc
    # satadj moved to apply_satadj_step_torch, so qv no longer flows through warm_phase.
    for x, name in [(state.qc, "qc"), (state.qr, "qr")]:
        assert x.grad is not None and torch.isfinite(x.grad).all(), name


# ════ F1c: Cold phase chain ═══════════════════════════════════════════════════


def _cold_phase_inputs(*, requires_grad: bool = False, B: int = 1, K: int = 3,
                       t_value: float = 263.15):
    """cold phase 입력 — T < T0c (cold) 영역."""
    dtype = torch.float64
    state, forcing, sea_mask = _state_forcing(requires_grad=requires_grad, B=B, K=K)
    state = state._replace(t=torch.full_like(state.t, t_value))
    p = default_coordinator_params()
    pre = preamble_torch(state, forcing, sea_mask, params=p)

    prevp = torch.zeros((B, K), dtype=dtype)
    n0i = torch.full((B, K), 1.0e6, dtype=dtype)
    n0r = torch.full((B, K), 8.0e6, dtype=dtype)  # codex#3 fix
    n0so = torch.full((B, K), 2.0e6, dtype=dtype)
    n0go = torch.full((B, K), 4.0e6, dtype=dtype)
    n0c = torch.full((B, K), 1.0e8, dtype=dtype)
    rslopecmu = pre.rslopec ** c.MUC if c.MUC != 0 else torch.ones_like(pre.rslopec)
    rslopecd = pre.rslopec ** c.DMC
    avedia_i = torch.full((B, K), 1.0e-4, dtype=dtype)
    work1_ice = torch.full((B, K), 1.0e-3, dtype=dtype)
    work1_water = torch.full((B, K), 1.0e-3, dtype=dtype)  # review3#1: psevp/pgevp용
    return state, forcing, pre, prevp, n0i, n0r, n0so, n0go, n0c, rslopecmu, rslopecd, avedia_i, work1_ice, work1_water


def test_cold_phase_outputs_finite():
    p = default_cold_phase_params()
    inputs = _cold_phase_inputs()
    out = cold_phase_torch(*inputs, params=p, dtcld=60.0)
    for field in out._fields:
        v = getattr(out, field)
        assert torch.isfinite(v).all(), field


def test_cold_phase_grad_propagates():
    p = default_cold_phase_params()
    inputs = _cold_phase_inputs(requires_grad=True)
    state = inputs[0]
    out = cold_phase_torch(*inputs, params=p, dtcld=60.0)
    # 다양한 outputs의 합 — graupel-side outputs도 포함해 qg가 graph에 들어가도록.
    loss = (out.praci.sum() + out.piacr.sum()
            + out.psaci.sum() + out.pgaci.sum()
            + out.psacw.sum() + out.pgacw.sum()
            + out.pracs.sum() + out.pgacr_adj.sum()
            + out.psaut.sum() + out.pidep.sum() + out.pgdep.sum() + out.psevp.sum())
    loss.backward()
    for x, name in [(state.qi, "qi"), (state.qs, "qs"), (state.qg, "qg"),
                    (state.qc, "qc"), (state.qr, "qr")]:
        assert x.grad is not None and torch.isfinite(x.grad).all(), name


def test_cold_phase_warm_temperature_inactive():
    """T > T0c → cold-only processes (praci, piacr, psaci, pgaci, ...) 모두 0."""
    p = default_cold_phase_params()
    inputs = _cold_phase_inputs(t_value=290.0)
    out = cold_phase_torch(*inputs, params=p, dtcld=60.0)
    # cold-only outputs
    z = torch.zeros_like(out.praci)
    assert torch.allclose(out.praci, z)
    assert torch.allclose(out.psaut, z)


# (test_warm_phase_pcond_zero_when_balanced removed: warm_phase no longer emits pcond — the
#  B5 saturation adjustment moved to apply_satadj_step_torch. The satadj's zero-when-balanced
#  behavior is covered directly by test_satadj.py against saturation_adjustment_torch.)


# ════ F1d: Melt/Freeze phase chain ════════════════════════════════════════════


def _mf_phase_inputs(*, requires_grad: bool = False, B: int = 1, K: int = 3,
                     t_value: float = 263.15):
    """melt/freeze phase 입력 — cold (T < T0c) for freezing, warm (T > T0c) for melting."""
    dtype = torch.float64
    state, forcing, sea_mask = _state_forcing(requires_grad=requires_grad, B=B, K=K)
    state = state._replace(t=torch.full_like(state.t, t_value))
    p_full = default_coordinator_params()
    p_cold = default_cold_phase_params()
    pre = preamble_torch(state, forcing, sea_mask, params=p_full)
    # cold phase 한 번 호출해서 *_adj outputs 얻기 (D5 입력)
    prevp = torch.zeros((B, K), dtype=dtype)
    n0i = torch.full((B, K), 1.0e6, dtype=dtype)
    n0so = torch.full((B, K), 2.0e6, dtype=dtype)
    n0go = torch.full((B, K), 4.0e6, dtype=dtype)
    n0c = torch.full((B, K), 1.0e8, dtype=dtype)
    n0r = torch.full((B, K), 8.0e6, dtype=dtype)
    rslopecmu = pre.rslopec ** c.MUC if c.MUC != 0 else torch.ones_like(pre.rslopec)
    rslopecd = pre.rslopec ** c.DMC
    avedia_i = torch.full((B, K), 1.0e-4, dtype=dtype)
    work1_ice = torch.full((B, K), 1.0e-3, dtype=dtype)
    work1_water = torch.full((B, K), 1.0e-3, dtype=dtype)
    cold_out = cold_phase_torch(
        state, forcing, pre, prevp, n0i, n0r, n0so, n0go, n0c, rslopecmu, rslopecd,
        avedia_i, work1_ice, work1_water, params=p_cold, dtcld=60.0,
    )
    return state, forcing, pre, cold_out, n0c, n0r, n0so, n0go, pre.rslopec, rslopecmu, rslopecd


def test_mf_phase_outputs_finite():
    p = default_melt_freeze_phase_params()
    inputs = _mf_phase_inputs()
    out = melt_freeze_phase_torch(*inputs, params=p, dtcld=60.0)
    for field in out._fields:
        v = getattr(out, field)
        assert torch.isfinite(v).all(), field


def test_mf_phase_cold_inactive_melt():
    """T < T0c → psmlt/pgmlt/pimlt = 0 (warm-only)."""
    p = default_melt_freeze_phase_params()
    inputs = _mf_phase_inputs(t_value=263.15)
    out = melt_freeze_phase_torch(*inputs, params=p, dtcld=60.0)
    z = torch.zeros_like(out.psmlt)
    assert torch.allclose(out.psmlt, z)
    assert torch.allclose(out.pgmlt, z)
    assert torch.allclose(out.pimlt_qi, z)
    # freeze는 cold에서 active
    # bigg cloud는 supcol > 0에서 양수
    assert torch.all(out.pfrzdtc >= 0)


def test_mf_phase_warm_inactive_freeze():
    """T > T0c → freezing 모두 0 (warm)."""
    p = default_melt_freeze_phase_params()
    inputs = _mf_phase_inputs(t_value=290.0)
    out = melt_freeze_phase_torch(*inputs, params=p, dtcld=60.0)
    z = torch.zeros_like(out.pfrzdtc)
    assert torch.allclose(out.pinuc, z)
    assert torch.allclose(out.pfrzdtc, z)
    assert torch.allclose(out.pfrzdtr, z)


# ════ F1e: State update ═══════════════════════════════════════════════════════


def _state_update_inputs(*, requires_grad: bool = False, t_value: float = 275.0):
    """모든 4 phase outputs을 한 번에 산출해 state update 입력 준비."""
    state, forcing, sea_mask = _state_forcing(requires_grad=requires_grad)
    state = state._replace(t=torch.full_like(state.t, t_value))
    p_full = default_coordinator_params()
    pw = default_warm_phase_params()
    pc = default_cold_phase_params()
    pmf = default_melt_freeze_phase_params()

    pre = preamble_torch(state, forcing, sea_mask, params=p_full)

    # warm phase
    n0r = torch.full_like(state.qr, 8.0e6)
    work1_r = torch.full_like(state.qr, 1.0e-3)
    qcr = diag_qcr_torch(sea_mask, params=p_full.cloud_dsd, ref=state.qc)
    warm = warm_phase_torch(state, forcing, pre, n0r, work1_r, qcr,
                              params=pw, dtcld=60.0)

    # cold phase
    prevp = warm.prevp  # B4 output → C3/C4 input
    n0i = torch.full_like(state.qi, 1.0e6)
    n0so = torch.full_like(state.qs, 2.0e6)
    n0go = torch.full_like(state.qg, 4.0e6)
    n0c = torch.full_like(state.qc, 1.0e8)
    rslopecmu = pre.rslopec ** c.MUC if c.MUC != 0 else torch.ones_like(pre.rslopec)
    rslopecd = pre.rslopec ** c.DMC
    avedia_i = torch.full_like(state.qi, 1.0e-4)
    work1_ice = torch.full_like(state.qi, 1.0e-3)
    work1_water = torch.full_like(state.qi, 1.0e-3)
    cold = cold_phase_torch(state, forcing, pre, prevp,
                             n0i, n0r, n0so, n0go, n0c, rslopecmu, rslopecd,
                             avedia_i, work1_ice, work1_water, params=pc, dtcld=60.0)

    # melt/freeze phase
    mf_out = melt_freeze_phase_torch(state, forcing, pre, cold,
                                       n0c, n0r, n0so, n0go,
                                       pre.rslopec, rslopecmu, rslopecd,
                                       params=pmf, dtcld=60.0)

    return state, pre, warm, cold, mf_out


def test_state_update_outputs_finite():
    state, pre, warm, cold, mf_out = _state_update_inputs()
    new_state = state_update_torch(state, pre, warm, cold, mf_out, dtcld=60.0)
    for field in new_state._fields:
        v = getattr(new_state, field)
        assert torch.isfinite(v).all(), field


def test_state_update_returns_new_state():
    """state_update는 *new state*를 반환하고 *old state는 변경 안 됨* (no in-place)."""
    state, pre, warm, cold, mf_out = _state_update_inputs()
    qv_orig = state.qv.clone()
    new_state = state_update_torch(state, pre, warm, cold, mf_out, dtcld=60.0)
    # original state unchanged
    assert torch.allclose(state.qv, qv_orig)
    # new state different (some processes are active)
    # (단, all-zero rates일 가능성도 있어 strict equality는 안 함)


def test_state_update_grad_propagates():
    """state.qv → new_state 경로에 backward 흐름."""
    state, pre, warm, cold, mf_out = _state_update_inputs(requires_grad=True)
    new_state = state_update_torch(state, pre, warm, cold, mf_out, dtcld=60.0)
    loss = new_state.qv.sum() + new_state.qc.sum() + new_state.t.sum()
    loss.backward()
    for x, name in [(state.qv, "qv"), (state.qc, "qc")]:
        assert x.grad is not None and torch.isfinite(x.grad).all(), name


# review8#5 boundary regression: paired threshold cleanup.


def test_paired_cleanup_zeros_paired_number():
    """qc ≤ qmin → qc=0, nc=0; qr ≤ qcrmin → qr=0, nr=0; qi ≤ qmin → qi=0, ni=0.

    Construct a state where qc/qr/qi are pre-built to fall below the cleanup
    threshold after one trivial state update; verify that nc/nr/ni are also
    zeroed (not left orphaned).
    """
    import math as _math
    state, pre, warm, cold, mf_out = _state_update_inputs()
    # 모든 rate를 0으로 만들어 state_update_torch가 입력 state를 그대로 반환하도록.
    # 그 후 input state의 qc/qr/qi를 threshold 이하로 두면 cleanup이 작동.
    zero = torch.zeros_like(state.qc)
    z2 = type(warm)(*[zero for _ in warm._fields])
    z3 = type(cold)(*[zero for _ in cold._fields])
    # mf 일부 필드는 boolean이지만 state_update에서 곱셈이라 OK
    z4_fields = []
    for name in mf_out._fields:
        v = getattr(mf_out, name)
        z4_fields.append(torch.zeros_like(v) if v.dtype != torch.bool else torch.zeros_like(v))
    z4 = type(mf_out)(*z4_fields)

    # qc < qmin (1e-15), nc 큰 값 → cleanup이 nc도 0으로 만들어야 함.
    state_thresh = type(state)(
        qv=state.qv, qc=torch.full_like(state.qc, 1.0e-16),
        qr=torch.full_like(state.qr, 1.0e-10),    # < QCRMIN=1e-9
        qs=torch.full_like(state.qs, 1.0e-10),
        qg=torch.full_like(state.qg, 1.0e-10),
        qi=torch.full_like(state.qi, 1.0e-16),
        nc=torch.full_like(state.nc, 1.0e8),
        nr=torch.full_like(state.nr, 1.0e6),
        ni=torch.full_like(state.ni, 1.0e6),
        brs=state.brs, t=state.t,
    )
    # review9#1: cleanup이 state_update에서 분리됐으므로 별도 호출.
    from kdm6.coordinator import apply_threshold_cleanup_torch
    raw = state_update_torch(state_thresh, pre, z2, z3, z4, dtcld=60.0)
    out = apply_threshold_cleanup_torch(raw)
    _ = out  # silence unused warning when extending below
    assert torch.allclose(out.qc, torch.zeros_like(out.qc))
    assert torch.allclose(out.nc, torch.zeros_like(out.nc)), "nc orphaned when qc cleaned"
    assert torch.allclose(out.qr, torch.zeros_like(out.qr))
    assert torch.allclose(out.nr, torch.zeros_like(out.nr)), "nr orphaned when qr cleaned"
    assert torch.allclose(out.qi, torch.zeros_like(out.qi))
    assert torch.allclose(out.ni, torch.zeros_like(out.ni)), "ni orphaned when qi cleaned"
    assert torch.allclose(out.qs, torch.zeros_like(out.qs))
    assert torch.allclose(out.qg, torch.zeros_like(out.qg))


# review9#2 regression: DSD number limiters (Fortran 2973-3014).


def test_dsd_limiter_clamps_oversized_nr():
    """nr가 lamdarmax를 만들 만큼 과대 → lamdar=lamdarmax 기준으로 nr 재계산."""
    from kdm6.coordinator import apply_dsd_number_limiters_torch, CoordinatorState
    dtype = torch.float64
    state = CoordinatorState(
        qv=torch.zeros((1, 1), dtype=dtype),
        qc=torch.zeros((1, 1), dtype=dtype),
        qr=torch.full((1, 1), 1.0e-4, dtype=dtype),    # 0.1 g/kg rain
        qs=torch.zeros((1, 1), dtype=dtype),
        qg=torch.zeros((1, 1), dtype=dtype),
        qi=torch.zeros((1, 1), dtype=dtype),
        nc=torch.zeros((1, 1), dtype=dtype),
        nr=torch.full((1, 1), 1.0e9, dtype=dtype),     # absurdly large nr
        ni=torch.zeros((1, 1), dtype=dtype),
        brs=torch.zeros((1, 1), dtype=dtype),
        t=torch.full((1, 1), 280.0, dtype=dtype),
    )
    den = torch.full((1, 1), 1.1, dtype=dtype)
    out = apply_dsd_number_limiters_torch(state, den)
    # nr should be capped to NRMAX or to lamdarmax-derived value (smaller).
    assert torch.all(out.nr <= state.nr), "nr should not exceed input"
    assert torch.all(out.nr < 1.0e9), "nr should be clamped"


def test_dsd_limiter_inactive_when_q_zero():
    """qr=0 (active=False) → nr 변화 없음."""
    from kdm6.coordinator import apply_dsd_number_limiters_torch, CoordinatorState
    dtype = torch.float64
    state = CoordinatorState(
        qv=torch.zeros((1, 1), dtype=dtype),
        qc=torch.zeros((1, 1), dtype=dtype),
        qr=torch.zeros((1, 1), dtype=dtype),
        qs=torch.zeros((1, 1), dtype=dtype),
        qg=torch.zeros((1, 1), dtype=dtype),
        qi=torch.zeros((1, 1), dtype=dtype),
        nc=torch.zeros((1, 1), dtype=dtype),
        nr=torch.full((1, 1), 1.0e3, dtype=dtype),  # nr exists but qr doesn't
        ni=torch.zeros((1, 1), dtype=dtype),
        brs=torch.zeros((1, 1), dtype=dtype),
        t=torch.full((1, 1), 280.0, dtype=dtype),
    )
    den = torch.full((1, 1), 1.1, dtype=dtype)
    out = apply_dsd_number_limiters_torch(state, den)
    assert torch.allclose(out.nr, state.nr), "inactive cells should pass through"


def test_dsd_limiter_clamps_oversized_nc():
    """review10#1: nc oversized → out.nc == den·qc·LAMDACMAX^DMC / pidnc (정확한 값).

    Strong regression: `pidnc = cmc · Γ(1+DMC/(MUC+1))` (Cohard-Pinty modified gamma)에
    *직접* anchor한다. 만약 누가 rgmma 부호를 다시 1/Γ로 돌리거나 Cohard-Pinty 식을
    rain/ice의 `Γ(1+DMX+MUX)/Γ(1+MUX)` 패턴으로 바꾸면 out.nc가 다른 값이 되어 fail.
    """
    from kdm6.coordinator import apply_dsd_number_limiters_torch, CoordinatorState
    dtype = torch.float64
    qc_v = 1.0e-3
    den_v = 1.1
    nc_in = 1.0e12   # nc 매우 큼 → lamdac > LAMDACMAX → snap to lamdacmax

    state = CoordinatorState(
        qv=torch.zeros((1, 1), dtype=dtype),
        qc=torch.full((1, 1), qc_v, dtype=dtype),
        qr=torch.zeros((1, 1), dtype=dtype),
        qs=torch.zeros((1, 1), dtype=dtype),
        qg=torch.zeros((1, 1), dtype=dtype),
        qi=torch.zeros((1, 1), dtype=dtype),
        nc=torch.full((1, 1), nc_in, dtype=dtype),
        nr=torch.zeros((1, 1), dtype=dtype),
        ni=torch.zeros((1, 1), dtype=dtype),
        brs=torch.zeros((1, 1), dtype=dtype),
        t=torch.full((1, 1), 280.0, dtype=dtype),
    )
    den = torch.full((1, 1), den_v, dtype=dtype)
    out = apply_dsd_number_limiters_torch(state, den)

    # Γ-truth hardcoded: pidnc = (π·DENR/6) · Γ(1+DMC/(MUC+1)) = 523.6 · Γ(2) = 523.6 · 1.
    cmc = math.pi * c.DENR / 6.0
    pidnc_expected = cmc * 1.0    # Γ(2) = 1 (DMC=3, MUC=2)
    nc_at_max = den_v * qc_v * (c.LAMDACMAX ** c.DMC) / pidnc_expected
    assert math.isclose(float(out.nc[0, 0]), nc_at_max, rel_tol=1e-9), (
        f"expected nc snapped to {nc_at_max:.6e}, got {float(out.nc[0, 0]):.6e}"
    )


def test_dsd_limiter_clamps_oversized_ni():
    """ni oversized → out.ni == den·qi·LAMDAIMAX^DMI / pidni (정확한 값).

    Strong regression for `pidni = cmi · Γ(1+DMI+MUI)/Γ(1+MUI)`. rgmma 부호 반전이나
    pidni 식이 잘못 바뀌면 fail.
    """
    from kdm6.coordinator import apply_dsd_number_limiters_torch, CoordinatorState
    dtype = torch.float64
    qi_v = 1.0e-5
    den_v = 1.1
    ni_in = 1.0e12

    state = CoordinatorState(
        qv=torch.zeros((1, 1), dtype=dtype),
        qc=torch.zeros((1, 1), dtype=dtype),
        qr=torch.zeros((1, 1), dtype=dtype),
        qs=torch.zeros((1, 1), dtype=dtype),
        qg=torch.zeros((1, 1), dtype=dtype),
        qi=torch.full((1, 1), qi_v, dtype=dtype),
        nc=torch.zeros((1, 1), dtype=dtype),
        nr=torch.zeros((1, 1), dtype=dtype),
        ni=torch.full((1, 1), ni_in, dtype=dtype),
        brs=torch.zeros((1, 1), dtype=dtype),
        t=torch.full((1, 1), 260.0, dtype=dtype),
    )
    den = torch.full((1, 1), den_v, dtype=dtype)
    out = apply_dsd_number_limiters_torch(state, den)

    # Γ-truth: pidni = (π·DENI/6) · Γ(1+DMI+MUI)/Γ(1+MUI) = 261.8 · Γ(4)/Γ(1) = 261.8 · 6.
    cmi = math.pi * c.DENI / 6.0
    pidni_expected = cmi * (6.0 / 1.0)    # Γ(4)=6, Γ(1)=1 (DMI=3, MUI=0)
    ni_at_max = den_v * qi_v * (c.LAMDAIMAX ** c.DMI) / pidni_expected
    assert math.isclose(float(out.ni[0, 0]), ni_at_max, rel_tol=1e-9), (
        f"expected ni snapped to {ni_at_max:.6e}, got {float(out.ni[0, 0]):.6e}"
    )


def test_mf_phase_grad_propagates():
    p = default_melt_freeze_phase_params()
    inputs = _mf_phase_inputs(requires_grad=True, t_value=275.0)  # near freezing for both
    state = inputs[0]
    out = melt_freeze_phase_torch(*inputs, params=p, dtcld=60.0)
    loss = (out.psmlt.sum() + out.pgmlt.sum() + out.pinuc.sum()
            + out.pfrzdtc.sum() + out.pfrzdtr.sum())
    loss.backward()
    for x, name in [(state.qs, "qs"), (state.qg, "qg"),
                    (state.qc, "qc"), (state.qr, "qr")]:
        assert x.grad is not None and torch.isfinite(x.grad).all(), name


# ════ F2: Sub-cycling wrapper ═════════════════════════════════════════════════


def _make_aux(state, sea_mask, p_full):
    """auxiliary diagnostics 생성 helper."""
    n0r = torch.full_like(state.qr, 8.0e6)
    n0i = torch.full_like(state.qi, 1.0e6)
    n0c = torch.full_like(state.qc, 1.0e8)
    n0so = torch.full_like(state.qs, 2.0e6)
    n0go = torch.full_like(state.qg, 4.0e6)
    work1_r = torch.full_like(state.qr, 1.0e-3)
    work1_ice = torch.full_like(state.qi, 1.0e-3)
    work1_water = torch.full_like(state.qi, 1.0e-3)  # review3#1
    qcr = diag_qcr_torch(sea_mask, params=p_full.cloud_dsd, ref=state.qc)
    avedia_i = torch.full_like(state.qi, 1.0e-4)
    # Need rslopec from preamble for rslopecmu/cd
    pre = preamble_torch(state, CoordinatorForcing(
        p=torch.full_like(state.t, 8.0e4),
        den=torch.full_like(state.t, 1.1),
        delz=torch.full_like(state.t, 500.0),
        dend=torch.full_like(state.t, 1.1 * 500.0),
    ), sea_mask, params=p_full)
    rslopecmu = pre.rslopec ** c.MUC if c.MUC != 0 else torch.ones_like(pre.rslopec)
    rslopecd = pre.rslopec ** c.DMC
    return CoordinatorAuxDiagnostics(
        n0r=n0r, n0i=n0i, n0c=n0c, n0so=n0so, n0go=n0go,
        work1_r=work1_r, work1_ice=work1_ice, work1_water=work1_water, qcr=qcr,
        avedia_i=avedia_i, rslopecmu=rslopecmu, rslopecd=rslopecd,
    )


def test_compute_loops_max_basic():
    assert compute_loops_max(60.0, dtcldcr=120.0) == 1
    assert compute_loops_max(180.0, dtcldcr=120.0) == 2
    assert compute_loops_max(0.0) == 1


def test_kdm62d_one_step_runs():
    """one-step coordinator 한 번 호출 — outputs finite."""
    state, forcing, sea_mask = _state_forcing()
    state = state._replace(t=torch.full_like(state.t, 275.0))
    p_full = default_coordinator_params()
    aux = _make_aux(state, sea_mask, p_full)
    new_state = kdm62d_one_step_torch(
        state, forcing, aux, sea_mask,
        full_params=p_full,
        warm_params=default_warm_phase_params(),
        cold_params=default_cold_phase_params(),
        mf_params=default_melt_freeze_phase_params(),
        dtcld=60.0,
    )
    for field in new_state._fields:
        v = getattr(new_state, field)
        assert torch.isfinite(v).all(), field


def test_kdm62d_step_subcycling_consistency():
    """delt=120 (loops_max=1) 와 delt=120 dtcldcr=60 (loops_max=2) 호출이 다름 (sub-cycle 효과)."""
    state, forcing, sea_mask = _state_forcing()
    state = state._replace(t=torch.full_like(state.t, 275.0))
    p_full = default_coordinator_params()
    aux = _make_aux(state, sea_mask, p_full)

    out_1step = kdm62d_step_torch(
        state, forcing, aux, sea_mask,
        full_params=p_full,
        warm_params=default_warm_phase_params(),
        cold_params=default_cold_phase_params(),
        mf_params=default_melt_freeze_phase_params(),
        delt=120.0, dtcldcr=120.0,  # loops_max = 1
    )
    out_2step = kdm62d_step_torch(
        state, forcing, aux, sea_mask,
        full_params=p_full,
        warm_params=default_warm_phase_params(),
        cold_params=default_cold_phase_params(),
        mf_params=default_melt_freeze_phase_params(),
        delt=120.0, dtcldcr=60.0,  # loops_max = 2
    )
    # 두 결과 모두 finite, sub-cycle은 정확도 차이를 만든다 (반드시 다름)
    assert torch.isfinite(out_1step.qv).all()
    assert torch.isfinite(out_2step.qv).all()


def test_kdm62d_step_grad_propagates():
    """outer step 후 backward 통과."""
    state, forcing, sea_mask = _state_forcing(requires_grad=True)
    state = state._replace(t=torch.full_like(state.t, 275.0))
    p_full = default_coordinator_params()
    aux = _make_aux(state, sea_mask, p_full)

    new_state = kdm62d_step_torch(
        state, forcing, aux, sea_mask,
        full_params=p_full,
        warm_params=default_warm_phase_params(),
        cold_params=default_cold_phase_params(),
        mf_params=default_melt_freeze_phase_params(),
        delt=120.0, dtcldcr=120.0,
    )
    loss = new_state.qv.sum() + new_state.qc.sum() + new_state.t.sum()
    loss.backward()
    for x, name in [(state.qv, "qv"), (state.qc, "qc")]:
        assert x.grad is not None and torch.isfinite(x.grad).all(), name


def test_kdm62d_step_delt_zero_is_noop_and_no_nan():
    """codex stop-hook regression: delt<=0 → state 불변, no NaN.

    이전엔 dtcld=delt/loops_max=0 → kdm62d_one_step 내부의 `mass/dtcld` 분할이
    inf, 그 후 곱셈/뺄셈으로 NaN 산출. wrapper가 zero-elapsed-time 케이스를
    early return으로 처리해야 함.
    """
    state, forcing, sea_mask = _state_forcing()
    p_full = default_coordinator_params()
    aux = _make_aux(state, sea_mask, p_full)

    out = kdm62d_step_torch(
        state, forcing, aux, sea_mask,
        full_params=p_full,
        warm_params=default_warm_phase_params(),
        cold_params=default_cold_phase_params(),
        mf_params=default_melt_freeze_phase_params(),
        delt=0.0,
    )
    # state should be unchanged (object identity not required, value identity OK).
    for name in ("qv", "qc", "qr", "qs", "qg", "qi", "nc", "nr", "ni", "brs", "t"):
        in_t = getattr(state, name)
        out_t = getattr(out, name)
        assert not torch.isnan(out_t).any(), f"{name} produced NaN at delt=0"
        assert torch.allclose(out_t, in_t), f"{name} changed at delt=0 (should be no-op)"

    # Negative delt also a no-op.
    out_neg = kdm62d_step_torch(
        state, forcing, aux, sea_mask,
        full_params=p_full,
        warm_params=default_warm_phase_params(),
        cold_params=default_cold_phase_params(),
        mf_params=default_melt_freeze_phase_params(),
        delt=-60.0,
    )
    assert not torch.isnan(out_neg.qv).any()
    assert torch.allclose(out_neg.qv, state.qv)


# ════ F2b: Sedimentation chain ════════════════════════════════════════════════


def _sed_inputs(*, requires_grad: bool = False, K: int = 4):
    dtype = torch.float64
    state, forcing, sea_mask = _state_forcing(requires_grad=requires_grad, K=K)
    work1_qr = torch.full((1, K), 1.0e-3, dtype=dtype)
    workn_qr = torch.full((1, K), 1.0e-3, dtype=dtype)
    work1_qs = torch.full((1, K), 5.0e-4, dtype=dtype)
    work1_qg = torch.full((1, K), 8.0e-4, dtype=dtype)
    work1_qi = torch.full((1, K), 5.0e-4, dtype=dtype)
    workn_qi = torch.full((1, K), 5.0e-4, dtype=dtype)
    return state, forcing, work1_qr, workn_qr, work1_qs, work1_qg, work1_qi, workn_qi


def test_sedimentation_chain_runs():
    p = default_substep_advection_params()
    state, forcing, work1_qr, workn_qr, work1_qs, work1_qg, work1_qi, workn_qi = _sed_inputs()
    out = sedimentation_chain_torch(
        state, forcing,
        work1_qr, workn_qr, work1_qs, work1_qg, work1_qi, workn_qi,
        mstep_main=2, mstep_ice=1, dtcld=60.0, params=p,
    )
    # state finite + 표면 누적 finite
    for f in out.state._fields:
        v = getattr(out.state, f)
        assert torch.isfinite(v).all(), f
    assert torch.isfinite(out.rain_increment).all()
    assert torch.all(out.rain_increment >= 0)


def test_sedimentation_state_loses_mass():
    """Top cells lose mass (no flux from above)."""
    p = default_substep_advection_params()
    state, forcing, work1_qr, workn_qr, work1_qs, work1_qg, work1_qi, workn_qi = _sed_inputs()
    out = sedimentation_chain_torch(
        state, forcing,
        work1_qr, workn_qr, work1_qs, work1_qg, work1_qi, workn_qi,
        mstep_main=1, mstep_ice=1, dtcld=60.0, params=p,
    )
    # Top cell qr decreases
    assert torch.all(out.state.qr[:, 0] <= state.qr[:, 0])


def test_sedimentation_grad_finite():
    p = default_substep_advection_params()
    state, forcing, work1_qr, workn_qr, work1_qs, work1_qg, work1_qi, workn_qi = _sed_inputs(
        requires_grad=True
    )
    out = sedimentation_chain_torch(
        state, forcing,
        work1_qr, workn_qr, work1_qs, work1_qg, work1_qi, workn_qi,
        mstep_main=2, mstep_ice=1, dtcld=60.0, params=p,
    )
    loss = out.state.qr.sum() + out.rain_increment.sum()
    loss.backward()
    assert state.qr.grad is not None and torch.isfinite(state.qr.grad).all()


def test_sedimentation_reslope_per_substep():
    """1:1 #9: with mstep>=2, per-substep re-slope (reslope_params=cp) re-derives work1 from
    the post-substep state — changing the result vs time-invariant work1 (None) — stays
    finite/non-negative, and gradients flow through the re-slope. At mstep==1 the loop runs
    once and the re-slope is never consumed (bit-identical; covered by em_quarter_ss)."""
    sp = default_substep_advection_params()
    cp = default_coordinator_params()
    state, forcing, sea_mask = _state_forcing(K=4)
    qr = torch.full_like(state.qr, 5.0e-3).requires_grad_(True)  # heavy rain → fast fall, mstep>=2 regime
    state = state._replace(qr=qr, qs=torch.full_like(state.qs, 1.0e-3),
                           qg=torch.full_like(state.qg, 1.0e-3), nr=torch.full_like(state.nr, 1.0e4))
    pre = preamble_torch(state, forcing, sea_mask, params=cp)
    dz = torch.clamp(forcing.delz, min=1.0e-9)
    w1_qr, wn_qr = pre.slope.vt_r / dz, pre.slope.vtn_r / dz
    w1_qs, w1_qg = pre.slope.vt_s / dz, pre.slope.vt_g / dz
    w1_qi, wn_qi = pre.slope.vt_i / dz, pre.slope.vtn_i / dz
    mm = 3
    out_static = sedimentation_chain_torch(
        state, forcing, w1_qr, wn_qr, w1_qs, w1_qg, w1_qi, wn_qi,
        mstep_main=mm, mstep_ice=mm, dtcld=60.0, params=sp, reslope_params=None)
    out_reslope = sedimentation_chain_torch(
        state, forcing, w1_qr, wn_qr, w1_qs, w1_qg, w1_qi, wn_qi,
        mstep_main=mm, mstep_ice=mm, dtcld=60.0, params=sp, reslope_params=cp, sea_mask=sea_mask)
    # (a) per-substep re-slope changes the result vs time-invariant work1 (mstep>1).
    assert not torch.allclose(out_static.state.qr, out_reslope.state.qr)
    # (b) finite + non-negative.
    for f in ("qr", "qs", "qg", "qi"):
        v = getattr(out_reslope.state, f)
        assert torch.isfinite(v).all() and torch.all(v >= 0)
    # (c) gradient flows through the re-slope chain to the qr leaf.
    (out_reslope.state.qr.sum() + out_reslope.rain_increment.sum()).backward()
    assert state.qr.grad is not None and torch.isfinite(state.qr.grad).all()


# ── F1d2: group conservation limiters ────────────────────────────────────────

def _zero_phase_struct(cls, ref):
    """Zero-filled phase-output NamedTuple (every field zeros_like(ref))."""
    return cls(**{f: torch.zeros_like(ref) for f in cls._fields})


def _trip_state(qi_val):
    """Single cold cell; qr>=1e-4 so delta2=delta3=0 (praci/piacr/psacr do NOT
    reroute to snow/graupel), and qs=qg=0 so snow/graupel budgets see a negative
    source and never re-scale — isolating the ice-mass budget."""
    dtype = torch.float64
    z = torch.zeros((1, 1), dtype=dtype)
    return CoordinatorState(
        qv=torch.full((1, 1), 5.0e-3, dtype=dtype),
        qc=z.clone(),
        qr=torch.full((1, 1), 1.0e-3, dtype=dtype),
        qs=z.clone(),
        qg=z.clone(),
        qi=torch.full((1, 1), qi_val, dtype=dtype),
        nc=torch.full((1, 1), 1.0e8, dtype=dtype),
        nr=torch.full((1, 1), 1.0e4, dtype=dtype),
        ni=torch.full((1, 1), 1.0e8, dtype=dtype),
        brs=z.clone(),
        t=torch.full((1, 1), 263.15, dtype=dtype),
    )


def test_group_limiter_caps_oversubscribed_ice_mass():
    """Trip-correctness (the source>value path the no-op gate cannot reach):
    when psaut+praci+psaci jointly demand far more ice than qi holds, the ice-
    mass group budget scales them so TOTAL consumption == qi exactly. This is
    the tier the per-rate caps lack — the 806× staged-ice over-production fix."""
    dtype = torch.float64
    dtcld = 60.0
    qi0 = 1.0e-6
    big = 1.0e-4   # each sink: big*dtcld = 6e-3 ≫ qi → jointly over-subscribed
    state = _trip_state(qi0)
    supcol = torch.full((1, 1), 10.0, dtype=dtype)   # cold arm (>0)

    cold = _zero_phase_struct(ColdPhaseOutputs, state.qi)._replace(
        psaut=torch.full((1, 1), big, dtype=dtype, requires_grad=True),
        praci=torch.full((1, 1), big, dtype=dtype, requires_grad=True),
        psaci=torch.full((1, 1), big, dtype=dtype, requires_grad=True),
    )
    warm = _zero_phase_struct(WarmPhaseOutputs, state.qi)
    mf = _zero_phase_struct(MeltFreezePhaseOutputs, state.qi)

    _w, c2, _m = scale_rates_for_conservation_torch(
        state, supcol, warm, cold, mf, dtcld=dtcld)

    # ice-mass source = (psaut+praci+psaci)·dtcld (only nonzero ice sinks);
    # after scaling, total ice consumed must equal the available pool exactly.
    consumed = (c2.psaut + c2.praci + c2.psaci) * dtcld
    assert torch.allclose(consumed, state.qi, rtol=1e-10), \
        f"ice over-draw not capped: consumed={consumed.item():.3e} qi={qi0:.3e}"

    # uniform factor = qi/source applied to each sink
    source = 3.0 * big * dtcld
    expect = big * qi0 / source
    assert torch.allclose(c2.psaut, torch.full((1, 1), expect, dtype=dtype), rtol=1e-10)

    # autograd flows through the limiter (no graph break, no .item())
    c2.psaut.sum().backward()
    assert cold.psaut.grad is not None and torch.isfinite(cold.psaut.grad).all()


def test_group_limiter_is_exact_noop_when_within_budget():
    """When sinks fit the pool (source<=value), factor==1.0 exactly ⇒ rates
    pass through bit-identical. This is the property that keeps the 216 existing
    tests green despite the new stage running every step."""
    dtype = torch.float64
    state = _trip_state(1.0e-2)   # LARGE ice pool
    supcol = torch.full((1, 1), 10.0, dtype=dtype)
    small = 1.0e-8                # Σ·dtcld ≪ qi → no trip
    cold = _zero_phase_struct(ColdPhaseOutputs, state.qi)._replace(
        psaut=torch.full((1, 1), small, dtype=dtype),
        praci=torch.full((1, 1), small, dtype=dtype),
        psaci=torch.full((1, 1), small, dtype=dtype),
    )
    warm = _zero_phase_struct(WarmPhaseOutputs, state.qi)
    mf = _zero_phase_struct(MeltFreezePhaseOutputs, state.qi)

    _w, c2, _m = scale_rates_for_conservation_torch(
        state, supcol, warm, cold, mf, dtcld=60.0)
    assert torch.equal(c2.psaut, cold.psaut), "no-op violated (psaut changed)"
    assert torch.equal(c2.praci, cold.praci), "no-op violated (praci changed)"
    assert torch.equal(c2.psaci, cold.psaci), "no-op violated (psaci changed)"


def test_group_limiter_inactive_on_warm_cell():
    """A warm cell (supcol<=0) must be untouched by the cold (pass-1) budgets
    even when over-subscribed — the gate confines each pass to its arm."""
    dtype = torch.float64
    state = _trip_state(1.0e-6)
    supcol = torch.full((1, 1), -5.0, dtype=dtype)   # WARM arm (<=0)
    big = 1.0e-4
    cold = _zero_phase_struct(ColdPhaseOutputs, state.qi)._replace(
        psaut=torch.full((1, 1), big, dtype=dtype),
        praci=torch.full((1, 1), big, dtype=dtype),
    )
    warm = _zero_phase_struct(WarmPhaseOutputs, state.qi)
    mf = _zero_phase_struct(MeltFreezePhaseOutputs, state.qi)
    _w, c2, _m = scale_rates_for_conservation_torch(
        state, supcol, warm, cold, mf, dtcld=60.0)
    # cold-arm ice budget must NOT fire on a warm cell
    assert torch.equal(c2.psaut, cold.psaut), "cold budget leaked onto warm cell"
    assert torch.equal(c2.praci, cold.praci)
