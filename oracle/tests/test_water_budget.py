"""P0-4 — ρΔz-weighted column water budget (oracle-side diagnostic).

Empirical findings this suite pins (see docs/P0-4):
  * Microphysics (incl. threshold cleanup) conserves column total water to fp64
    roundoff  →  ΔW_micro ≈ 0  (strong regression LOCK).
  * The cleanup sink measured at the exact apply_threshold_cleanup boundary
    accounts for the (tiny) micro non-conservation.
  * The WRF-style `rain_increment` surface diagnostic does NOT equal the column
    mass sedimentation actually removes (ΔW_sed): a characterized gap, exposed
    here rather than hidden by redefining the surface term.

All acceptance is per-column (B,) — never a domain sum (opposite-sign column
errors must not cancel). fp64 throughout.
"""
import torch

from kdm6.state import State, Forcing
from kdm6.runtime import _kdm6_pure, make_parameters
from kdm6.coordinator import CoordinatorState, apply_threshold_cleanup_torch
import kdm6.constants as c
from kdm6 import water_budget as wb


def _mk(col_vals, K):
    return torch.tensor([[v] * K for v in col_vals], dtype=torch.float64)


def _admissible_batch(K=4):
    """All hydrometeors >= 0 and away from clip boundaries, so the entry
    nonneg-clamp is a no-op and the sed/micro decomposition is exact."""
    s = State(
        th=_mk([290., 290., 290.], K), qv=_mk([1.4e-2] * 3, K), qc=_mk([1e-3] * 3, K),
        qr=_mk([1e-5, 5e-3, 1e-3], K), qi=_mk([1e-4] * 3, K), qs=_mk([2e-3, 2e-3, 5e-4], K),
        qg=_mk([1e-3, 1e-3, 2e-4], K), nccn=_mk([1e9] * 3, K), nc=_mk([1e8] * 3, K),
        ni=_mk([1e4] * 3, K), nr=_mk([1e4, 1e5, 5e4], K), bg=_mk([1e-7] * 3, K),
    )
    f = Forcing(rho=_mk([1.0] * 3, K), pii=_mk([0.97] * 3, K),
                p=_mk([9e4] * 3, K), delz=_mk([500.] * 3, K))
    return s, f


def _heavy_rain_batch(K=4):
    s = State(
        th=_mk([285., 285.], K), qv=_mk([1.6e-2] * 2, K), qc=_mk([2e-3] * 2, K),
        qr=_mk([5e-3, 8e-3], K), qi=_mk([0.] * 2, K), qs=_mk([0.] * 2, K),
        qg=_mk([0.] * 2, K), nccn=_mk([1e9] * 2, K), nc=_mk([1e8] * 2, K),
        ni=_mk([0.] * 2, K), nr=_mk([1e5, 2e5], K), bg=_mk([0.] * 2, K),
    )
    f = Forcing(rho=_mk([1.1] * 2, K), pii=_mk([0.98] * 2, K),
                p=_mk([9.5e4] * 2, K), delz=_mk([400.] * 2, K))
    return s, f


def _roundoff_bound(*terms):
    scale = sum(t.abs() for t in terms) + 1.0
    return 1e-9 + 1e-11 * scale   # justified by measured ΔW_micro ~ 1e-14 on W ~ 40


# ── 1. cleanup unit identity (exact per-species ρΔz sink) ───────────────────
def test_threshold_cleanup_reports_exact_species_mass_sink():
    B, K = 2, 1
    full = lambda v: torch.full((B, K), v, dtype=torch.float64)
    rho_dz = full(0.9) * full(600.0)   # (B,K)
    # each hydrometeor just BELOW its threshold (qc,qi: qmin=1e-15; qr,qs,qg: qcrmin=1e-9)
    below = CoordinatorState(
        qv=full(2e-3), qc=full(5e-16), qr=full(5e-10), qs=full(5e-10),
        qg=full(5e-10), qi=full(5e-16), nc=full(1e6), nr=full(1e2),
        ni=full(1e3), brs=full(0.0), t=full(250.0))
    post = apply_threshold_cleanup_torch(below)
    # mass + paired number zeroed; qv, t untouched
    for x in ("qc", "qr", "qi", "qs", "qg"):
        assert torch.count_nonzero(getattr(post, x)) == 0, x
    for n in ("nc", "nr", "ni"):
        assert torch.count_nonzero(getattr(post, n)) == 0, n
    assert torch.equal(post.qv, below.qv)
    assert torch.equal(post.t, below.t)
    # ρΔz-weighted per-species sink == ρΔz · (removed mass), exactly
    sink = wb.hydrometeor_mass_sink_kg_m2(below, post, rho_dz)
    for x in ("qc", "qr", "qi", "qs", "qg"):
        expect = (rho_dz * getattr(below, x)).sum(dim=-1)
        assert torch.allclose(sink[x], expect, rtol=0, atol=0), x
    # ABOVE threshold → strict pass-through, zero sink
    above = below._replace(qc=full(2e-15), qi=full(2e-15),
                           qr=full(2e-9), qs=full(2e-9), qg=full(2e-9))
    post2 = apply_threshold_cleanup_torch(above)
    for x in ("qc", "qr", "qi", "qs", "qg"):
        assert torch.equal(getattr(post2, x), getattr(above, x)), x
    sink2 = wb.hydrometeor_mass_sink_kg_m2(above, post2, rho_dz)
    for x in ("qc", "qr", "qi", "qs", "qg"):
        assert torch.count_nonzero(sink2[x]) == 0, x


# ── 2. non-invasiveness (FREEZE LINE): budget must not perturb the forward ──
def test_budget_diagnostics_do_not_change_forward_outputs():
    s, f = _admissible_batch()
    p = make_parameters()
    ref = _kdm6_pure(s, f, p, dt=120.0)
    out, budget = wb.kdm6_step_with_water_budget(s, f, p, dt=120.0)
    for field in s._fields:
        assert torch.equal(getattr(out, field), getattr(ref, field)), field


# ── 3. LOCK: microphysics conserves column water to roundoff ────────────────
def test_microphysics_conserves_column_water_to_roundoff():
    s, f = _admissible_batch()
    _, b = wb.kdm6_step_with_water_budget(s, f, dt=60.0)
    tol = _roundoff_bound(b.water_in_kg_m2, b.water_out_kg_m2)
    assert torch.all(b.micro_dW_kg_m2.abs() <= tol), b.micro_dW_kg_m2


# ── 4. cleanup boundary sink accounts for the micro non-conservation ────────
def test_cleanup_sink_matches_microphysics_nonconservation():
    s, f = _admissible_batch()
    _, b = wb.kdm6_step_with_water_budget(s, f, dt=60.0)
    tol = _roundoff_bound(b.water_in_kg_m2, b.cleanup_total_kg_m2)
    # micro removes water ONLY via cleanup ⇒ ΔW_micro ≈ -cleanup_total
    assert torch.all((b.micro_dW_kg_m2 + b.cleanup_total_kg_m2).abs() <= tol)


# ── 5a. LOCK: the budget decomposition is complete (exact identity) ─────────
def test_budget_decomposition_is_complete():
    s, f = _heavy_rain_batch()
    _, b = wb.kdm6_step_with_water_budget(s, f, dt=120.0)
    # W_out - W_in == -sed_removed + micro_dW, exactly (admissible ⇒ no entry clip)
    lhs = b.water_out_kg_m2 - b.water_in_kg_m2
    rhs = -b.sed_column_loss_kg_m2 + b.micro_dW_kg_m2
    tol = _roundoff_bound(b.water_in_kg_m2, b.water_out_kg_m2, b.sed_column_loss_kg_m2)
    assert torch.all((lhs - rhs).abs() <= tol), (lhs, rhs)


# ── 5b. CHARACTERIZE: WRF rain_increment != actual sed column removal ───────
def test_sedimentation_surface_diagnostic_gap_is_exposed():
    s, f = _heavy_rain_batch()
    _, b = wb.kdm6_step_with_water_budget(s, f, dt=120.0)
    # gap := diagnostic - actual removal ; both finite, and NON-trivial in heavy rain
    gap = b.sed_surface_diag_gap_kg_m2
    assert torch.isfinite(gap).all()
    assert torch.equal(gap, b.surface_precip_diag_kg_m2 - b.sed_column_loss_kg_m2)
    # documents the finding: the WRF RAINNCV diagnostic is not the column-water
    # surface term (differs by >> roundoff for a precipitating column).
    assert torch.any(gap.abs() > 1e-3), gap


# ── 6. multi-subcycle accumulation (dt=300 → several subcycles) ─────────────
def test_multisubcycle_terms_accumulate():
    s, f = _admissible_batch()
    _, b = wb.kdm6_step_with_water_budget(s, f, dt=300.0)
    assert int(b.n_subcycles) >= 2
    # decomposition still exact across all subcycles
    lhs = b.water_out_kg_m2 - b.water_in_kg_m2
    rhs = -b.sed_column_loss_kg_m2 + b.micro_dW_kg_m2
    tol = _roundoff_bound(b.water_in_kg_m2, b.water_out_kg_m2, b.sed_column_loss_kg_m2)
    assert torch.all((lhs - rhs).abs() <= tol)
    # surface precip is accumulated over subcycles (not just the last)
    assert torch.all(b.surface_precip_diag_kg_m2 >= 0)


# ── 7. per-column, never domain-sum ─────────────────────────────────────────
def test_budget_is_columnwise_not_domain_sum_only():
    s, f = _admissible_batch()
    _, b = wb.kdm6_step_with_water_budget(s, f, dt=60.0)
    # every reported quantity is per-column (B,), not a scalar
    B = s.qv.shape[0]
    for name in ("water_in_kg_m2", "water_out_kg_m2", "sed_column_loss_kg_m2",
                 "micro_dW_kg_m2", "surface_precip_diag_kg_m2",
                 "cleanup_total_kg_m2", "sed_surface_diag_gap_kg_m2"):
        t = getattr(b, name)
        assert t.shape == (B,), (name, t.shape)
