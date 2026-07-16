"""P0-4b — sedimentation gap attribution (oracle-side diagnostic).

Attributes the measured discrepancy between the operator-implied column loss
L_s and the WRF fallout diagnostic P_s, per species / per column / per level:

    P_s − L_s  =  B_s − ΣD_s + ΣA_s          (acceptance identity)

with, in ρΔz mass units,
    O_{s,k}  actual outflow used in the update  (top cell: the RAW uncapped
             subtraction; interior: the entry-capped min),
    I_{s,k}  actual inflow used (stored-falk flux capped by the cell-above's
             POST-update reservoir),
    D_{s,k}  = O_{s,k−1} − I_{s,k}   interface defect,
    A_{s,k}  positivity-projection addition (top cell only, structurally),
    B_s      = P_s − O_{s,bottom}    bottom diagnostic discrepancy,
and the independent state-based loss L_s = Σ_k ρΔz (q_pre − q_post).

Exact per-level identity the implementation must satisfy by construction:
    ρΔz(q_entry − q_post) = O − I − A   →   L_s = O_bottom + ΣD − ΣA.

All acceptance is per-column (B,) — never a domain sum. fp64 throughout.
Attribution only: no forward-path change (diagnostics-on output stays
torch.equal to the plain path).
"""
import torch

from kdm6.sedimentation import (
    SubstepAdvectionState, IceSubstepState,
    substep_advection_torch, ice_substep_advection_torch,
    default_substep_advection_params,
)
from kdm6.state import State, Forcing
from kdm6.runtime import _kdm6_pure, make_parameters
from kdm6 import water_budget as wb


def _full(B, K, v):
    return torch.full((B, K), float(v), dtype=torch.float64)


def _main_state(B, K, qr=0.0, qs=0.0, qg=0.0, nr=0.0):
    z = torch.zeros((B, K), dtype=torch.float64)
    return SubstepAdvectionState(qr=_full(B, K, qr), nr=_full(B, K, nr),
                                 qs=_full(B, K, qs), qg=_full(B, K, qg), brs=z.clone())


def _run_main(state, w1_qr, delz, dend, dtcld, ledger, w1_qs=None, w1_qg=None):
    B, K = state.qr.shape
    z = torch.zeros((B, K), dtype=torch.float64)
    if w1_qs is None:
        w1_qs = torch.zeros_like(w1_qr)
    if w1_qg is None:
        w1_qg = torch.zeros_like(w1_qr)
    return substep_advection_torch(
        state, z.clone(), z.clone(), z.clone(), z.clone(), z.clone(),
        w1_qr, torch.zeros_like(w1_qr), w1_qs, w1_qg,
        delz, dend, mstep=1, dtcld=dtcld,
        params=default_substep_advection_params(), ledger=ledger)


def _tol(*terms):
    scale = sum(t.abs() for t in terms) + 1.0
    return 1e-10 + 1e-12 * scale


def _assert_identity(att, s, *, tol_terms=()):
    """P_s − L_s == B_s − ΣD_s + ΣA_s, per column."""
    P = att.wrf_fallout_diag_by_species_kg_m2[s]
    L = att.column_loss_by_species_kg_m2[s]
    B = att.bottom_diag_gap_by_species_kg_m2[s]
    D = att.interface_defect_by_species_kg_m2[s]
    A = att.positivity_projection_by_species_kg_m2[s]
    lhs = P - L
    rhs = B - D + A
    tol = _tol(P, L, B, D, A, *tol_terms)
    assert torch.all((lhs - rhs).abs() <= tol), (s, lhs, rhs)


# ── T1. single layer, no cap: L = O_bottom = P ──────────────────────────────
def test_t1_single_layer_uncapped_identity():
    B, K = 2, 1
    q, rho, dz, w1, dt = 1e-3, 1.0, 500.0, 0.001, 60.0   # CFL = 0.06
    st = _main_state(B, K, qr=q)
    led = wb.SedimentationLedger()
    _run_main(st, _full(B, K, w1), _full(B, K, dz), _full(B, K, rho), dt, led)
    att = led.finalize()
    expect = rho * dz * q * (w1 * dt)                     # 0.03 kg/m²
    for name in ("column_loss_by_species_kg_m2",
                 "bottom_actual_outflow_by_species_kg_m2",
                 "wrf_fallout_diag_by_species_kg_m2"):
        got = getattr(att, name)["qr"]
        assert torch.allclose(got, torch.full((B,), expect, dtype=torch.float64),
                              rtol=1e-12, atol=0), (name, got)
    _assert_identity(att, "qr")
    assert torch.all(att.gap_by_species_kg_m2["qr"].abs() <= _tol(att.gap_by_species_kg_m2["qr"]))


# ── T2. single layer, cap binds: gap == A_top (diag > loss), B == 0 ─────────
def test_t2_single_layer_capped_gap_is_projection():
    B, K = 1, 1
    q, rho, dz, w1, dt = 1e-3, 1.0, 500.0, 0.03, 60.0    # CFL = 1.8 > 1
    st = _main_state(B, K, qr=q)
    led = wb.SedimentationLedger()
    _run_main(st, _full(B, K, w1), _full(B, K, dz), _full(B, K, rho), dt, led)
    att = led.finalize()
    L = att.column_loss_by_species_kg_m2["qr"]
    P = att.wrf_fallout_diag_by_species_kg_m2["qr"]
    A = att.positivity_projection_by_species_kg_m2["qr"]
    Bt = att.bottom_diag_gap_by_species_kg_m2["qr"]
    assert torch.allclose(L, torch.tensor([rho * dz * q], dtype=torch.float64), rtol=1e-12)      # all mass lost
    assert torch.allclose(P, torch.tensor([rho * dz * q * w1 * dt], dtype=torch.float64), rtol=1e-12)  # uncapped diag
    assert torch.all(P > L)                              # diag over-reports
    assert torch.allclose(P - L, A, rtol=1e-10, atol=1e-14)   # entire gap = projection
    assert torch.all(Bt.abs() <= _tol(P))                # bottom==top subtracts RAW → B≈0
    assert torch.all(att.interface_defect_by_species_kg_m2["qr"].abs() == 0)
    _assert_identity(att, "qr")


# ── T3. two layers, uniform metric, no caps: D ≈ 0 ──────────────────────────
def test_t3_two_layer_uncapped_interface_conservative():
    B, K = 1, 2
    st = _main_state(B, K, qr=1e-3)
    led = wb.SedimentationLedger()
    _run_main(st, _full(B, K, 0.001), _full(B, K, 500.0), _full(B, K, 1.0), 60.0, led)
    att = led.finalize()
    D = att.interface_defect_detail_kg_m2["qr"]
    assert D.shape == (B, K - 1)
    assert torch.all(D.abs() <= _tol(att.column_loss_by_species_kg_m2["qr"]))
    _assert_identity(att, "qr")


# ── T4. two layers, post-update reservoir cap binds: D > 0 explains the gap ─
def test_t4_interface_cap_produces_positive_defect():
    B, K = 1, 2
    q_top, q_bot = 1e-3, 1e-6
    rho, dz, dt = 1.0, 500.0, 60.0
    w1 = _full(B, K, 0.015)                              # CFL = 0.9 (top drains hard)
    st = SubstepAdvectionState(qr=torch.tensor([[q_top, q_bot]], dtype=torch.float64),
                               nr=torch.zeros(1, 2, dtype=torch.float64),
                               qs=torch.zeros(1, 2, dtype=torch.float64),
                               qg=torch.zeros(1, 2, dtype=torch.float64),
                               brs=torch.zeros(1, 2, dtype=torch.float64))
    led = wb.SedimentationLedger()
    _run_main(st, w1, _full(B, K, dz), _full(B, K, rho), dt, led)
    att = led.finalize()
    D = att.interface_defect_by_species_kg_m2["qr"]
    # hand value: raw_top = 0.9e-3 leaves; inflow capped by post_top = 0.1e-3
    expect_D = rho * dz * (0.9e-3 - 0.1e-3)              # 0.4 kg/m²
    assert torch.allclose(D, torch.tensor([expect_D], dtype=torch.float64), rtol=1e-10), D
    # interior projection is structurally zero
    assert torch.all(att.projection_detail_kg_m2["qr"][:, 1:] == 0)
    # the defect dominates the gap
    _assert_identity(att, "qr")
    gap = att.gap_by_species_kg_m2["qr"]
    assert torch.all(gap < 0)                            # loss > diag
    assert torch.all(D > 0.9 * gap.abs())
    # cap flags recorded
    assert int(att.cap_flags["qr_inflow_cap"].sum()) >= 1
    assert int(att.worst_interface_index["qr"][0]) == 0


# ── T5. variable rho / delz, no caps: interface still conservative ──────────
def test_t5_variable_metric_uncapped_conservative():
    B, K = 1, 2
    delz = torch.tensor([[300.0, 700.0]], dtype=torch.float64)
    dend = torch.tensor([[0.7, 1.2]], dtype=torch.float64)
    st = _main_state(B, K, qr=1e-3)
    led = wb.SedimentationLedger()
    _run_main(st, _full(B, K, 0.001), delz, dend, 60.0, led)
    att = led.finalize()
    assert torch.all(att.interface_defect_by_species_kg_m2["qr"].abs()
                     <= _tol(att.column_loss_by_species_kg_m2["qr"]))
    _assert_identity(att, "qr")


# ── T6. projection is recorded exactly where the raw update goes negative ───
def test_t6_projection_recorded_exactly():
    B, K = 1, 1
    q, rho, dz, w1, dt = 2e-3, 0.9, 400.0, 0.05, 60.0    # CFL = 3.0
    st = _main_state(B, K, qr=q)
    led = wb.SedimentationLedger()
    _run_main(st, _full(B, K, w1), _full(B, K, dz), _full(B, K, rho), dt, led)
    att = led.finalize()
    raw = q * w1 * dt                                     # uncapped subtraction
    expect_A = rho * dz * (raw - q)
    A = att.positivity_projection_by_species_kg_m2["qr"]
    assert torch.allclose(A, torch.tensor([expect_A], dtype=torch.float64), rtol=1e-12), A
    assert int(att.cap_flags["qr_top_clamp"].sum()) == 1


# ── T7. species isolation: qs, qg (main), qi (ice chain), then mixed ────────
def test_t7_species_isolation_and_ice():
    B, K = 1, 2
    dz, rho, dt = 500.0, 1.0, 60.0
    for s in ("qs", "qg"):
        st = _main_state(B, K, **{s: 1e-3})
        led = wb.SedimentationLedger()
        kw = {"w1_qs": _full(B, K, 0.001)} if s == "qs" else {"w1_qg": _full(B, K, 0.001)}
        _run_main(st, torch.zeros(B, K, dtype=torch.float64), _full(B, K, dz), _full(B, K, rho), dt, led, **kw)
        att = led.finalize()
        assert torch.all(att.column_loss_by_species_kg_m2[s] > 0), s
        _assert_identity(att, s)
        for other in ("qr", "qs", "qg", "qi"):
            if other != s:
                assert torch.all(att.column_loss_by_species_kg_m2[other] == 0), (s, other)
    # qi via the separate ice chain
    led = wb.SedimentationLedger()
    ice = IceSubstepState(qi=_full(B, K, 1e-4), ni=_full(B, K, 1e3))
    z = torch.zeros(B, K, dtype=torch.float64)
    ice_substep_advection_torch(
        ice, z.clone(), z.clone(), _full(B, K, 0.001), torch.zeros(B, K, dtype=torch.float64),
        _full(B, K, dz), _full(B, K, rho), mstep=1, dtcld=dt,
        params=default_substep_advection_params(), ledger=led)
    att = led.finalize()
    assert torch.all(att.column_loss_by_species_kg_m2["qi"] > 0)
    _assert_identity(att, "qi")
    # mixed all four through the FULL step (heavy mixed batch)
    _, _, att = wb.kdm6_step_with_sed_attribution(*_mixed_batch(), dt=120.0)
    for s in ("qr", "qs", "qg", "qi"):
        _assert_identity(att, s)


# ── helpers for full-step cases ──────────────────────────────────────────────
def _mk(cv, K):
    return torch.tensor([[v] * K for v in cv], dtype=torch.float64)


def _mixed_batch(K=4):
    s = State(th=_mk([285., 285.], K), qv=_mk([1.6e-2] * 2, K), qc=_mk([2e-3] * 2, K),
              qr=_mk([5e-3, 8e-3], K), qi=_mk([1e-4] * 2, K), qs=_mk([2e-3] * 2, K),
              qg=_mk([1e-3] * 2, K), nccn=_mk([1e9] * 2, K), nc=_mk([1e8] * 2, K),
              ni=_mk([1e4] * 2, K), nr=_mk([1e5, 2e5], K), bg=_mk([1e-7] * 2, K))
    f = Forcing(rho=_mk([1.1] * 2, K), pii=_mk([0.98] * 2, K),
                p=_mk([9.5e4] * 2, K), delz=_mk([400.] * 2, K))
    return s, f


def _heavy_rain_batch(K=4):
    s = State(th=_mk([285., 285.], K), qv=_mk([1.6e-2] * 2, K), qc=_mk([2e-3] * 2, K),
              qr=_mk([5e-3, 8e-3], K), qi=_mk([0.] * 2, K), qs=_mk([0.] * 2, K),
              qg=_mk([0.] * 2, K), nccn=_mk([1e9] * 2, K), nc=_mk([1e8] * 2, K),
              ni=_mk([0.] * 2, K), nr=_mk([1e5, 2e5], K), bg=_mk([0.] * 2, K))
    f = Forcing(rho=_mk([1.1] * 2, K), pii=_mk([0.98] * 2, K),
                p=_mk([9.5e4] * 2, K), delz=_mk([400.] * 2, K))
    return s, f


# ── T8. mstep and KDM subcycles both active; totals tie out to the budget ───
def test_t8_multisubcycle_and_mstep_accumulate():
    s, f = _mixed_batch()
    out, budget, att = wb.kdm6_step_with_sed_attribution(s, f, dt=300.0)
    assert int(budget.n_subcycles) >= 2
    for sp in ("qr", "qs", "qg", "qi"):
        _assert_identity(att, sp, tol_terms=(budget.water_in_kg_m2,))
    # totals reconcile with the P0-4 budget (independent measurements)
    P_tot = torch.stack([att.wrf_fallout_diag_by_species_kg_m2[sp]
                         for sp in ("qr", "qs", "qg", "qi")]).sum(dim=0)
    L_tot = torch.stack([att.column_loss_by_species_kg_m2[sp]
                         for sp in ("qr", "qs", "qg", "qi")]).sum(dim=0)
    tol = _tol(P_tot, budget.surface_precip_diag_kg_m2)
    assert torch.all((P_tot - budget.surface_precip_diag_kg_m2).abs() <= tol)
    tol = _tol(L_tot, budget.sed_column_loss_kg_m2)
    assert torch.all((L_tot - budget.sed_column_loss_kg_m2).abs() <= tol)


# ── T9. heavy-rain regression: the P0-4 gap fully attributed ────────────────
def test_t9_heavy_rain_gap_fully_attributed():
    s, f = _heavy_rain_batch()
    out, budget, att = wb.kdm6_step_with_sed_attribution(s, f, dt=120.0)
    # the P0-4 measured gap (kg/m²)
    G = budget.sed_surface_diag_gap_kg_m2
    assert torch.allclose(G, torch.tensor([-4.8012, -6.0181], dtype=torch.float64),
                          rtol=0, atol=2e-3), G
    # attribution closes to the fp64 floor, per column
    tol = _tol(G, budget.water_in_kg_m2, att.attributed_gap_kg_m2)
    assert torch.all(att.unattributed_residual_kg_m2.abs() <= tol), \
        att.unattributed_residual_kg_m2
    assert torch.all((G - att.attributed_gap_kg_m2).abs() <= tol)


# ── non-invasiveness: attribution ON must not change the forward outputs ────
def test_sed_attribution_does_not_change_forward_outputs():
    s, f = _heavy_rain_batch()
    p = make_parameters()
    ref = _kdm6_pure(s, f, p, dt=120.0)
    out, _, _ = wb.kdm6_step_with_sed_attribution(s, f, p, dt=120.0)
    for field in s._fields:
        assert torch.equal(getattr(out, field), getattr(ref, field)), field


# ── dt<=0 no-op contract: wrapper must not break, attribution all-zero ───────
def test_dt_nonpositive_noop_returns_zero_attribution():
    s, f = _heavy_rain_batch()
    for dt in (0.0, -60.0):
        out, budget, att = wb.kdm6_step_with_sed_attribution(s, f, dt=dt)
        # bit-exact no-op (the hardened _kdm6_pure contract)
        for field in s._fields:
            assert torch.equal(getattr(out, field), getattr(s, field)), (dt, field)
        B, K = s.qr.shape
        for sp in ("qr", "qs", "qg", "qi"):
            assert torch.count_nonzero(att.gap_by_species_kg_m2[sp]) == 0, (dt, sp)
            assert torch.count_nonzero(att.column_loss_by_species_kg_m2[sp]) == 0
            assert att.interface_defect_detail_kg_m2[sp].shape == (B, K - 1)
            assert att.projection_detail_kg_m2[sp].shape == (B, K)
        assert torch.count_nonzero(att.attributed_gap_kg_m2) == 0
        assert torch.count_nonzero(att.unattributed_residual_kg_m2) == 0
        assert torch.count_nonzero(budget.sed_surface_diag_gap_kg_m2) == 0
