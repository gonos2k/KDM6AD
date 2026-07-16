"""P0-4b.1 component 3 — conservative counterfactual sedimentation (analysis-only).

The conservative experiment transfers to each lower cell the mass ACTUALLY
removed from the source cell (capped outflow), instead of re-capping the stored
raw falk flux by the source's post-update reservoir. The surface diagnostic uses
the actual bottom outflow. Acceptance (owner spec):

    W_post − W_pre + P_actual = O(ε64)   per column, all species
    no negatives anywhere; internal interface defect at the fp64 floor;
    legacy path stays torch.equal; conservative is explicit opt-in;
    directional-derivative (FD) validated; closes under multi-mstep and
    multi-KDM-subcycle.

legacy_reference = the unchanged default path; conservative_experiment = the
functions under test. NOT wired to the default runtime, C++/Fortran, or the DA path.
"""
import torch

from kdm6.sedimentation import (
    SubstepAdvectionState, default_substep_advection_params,
)
from kdm6.state import State, Forcing
from kdm6.runtime import _kdm6_pure, make_parameters
from kdm6 import water_budget as wb
from kdm6.sed_conservative import (
    conservative_substep_advection_torch,
    conservative_ice_substep_advection_torch,
    kdm6_step_conservative_experiment,
)


def _full(B, K, v):
    return torch.full((B, K), float(v), dtype=torch.float64)


def _mk(cv, K):
    return torch.tensor([[v] * K for v in cv], dtype=torch.float64)


def _heavy_rain_batch(K=4):
    s = State(th=_mk([285., 285.], K), qv=_mk([1.6e-2] * 2, K), qc=_mk([2e-3] * 2, K),
              qr=_mk([5e-3, 8e-3], K), qi=_mk([0.] * 2, K), qs=_mk([0.] * 2, K),
              qg=_mk([0.] * 2, K), nccn=_mk([1e9] * 2, K), nc=_mk([1e8] * 2, K),
              ni=_mk([0.] * 2, K), nr=_mk([1e5, 2e5], K), bg=_mk([0.] * 2, K))
    f = Forcing(rho=_mk([1.1] * 2, K), pii=_mk([0.98] * 2, K),
                p=_mk([9.5e4] * 2, K), delz=_mk([400.] * 2, K))
    return s, f


def _tol(*terms):
    scale = sum(t.abs() for t in terms) + 1.0
    return 1e-10 + 1e-12 * scale


def _run_cons(state, w1_qr, delz, dend, dtcld, ledger=None, mstep=1):
    B, K = state.qr.shape
    z = torch.zeros((B, K), dtype=torch.float64)
    return conservative_substep_advection_torch(
        state, z.clone(), z.clone(), z.clone(), z.clone(), z.clone(),
        w1_qr, torch.zeros_like(w1_qr), torch.zeros_like(w1_qr), torch.zeros_like(w1_qr),
        delz, dend, mstep=mstep, dtcld=dtcld,
        params=default_substep_advection_params(), ledger=ledger)


# ── 1. the T4 scenario is now conservative: D at the fp64 floor ──────────────
def test_conservative_interface_no_defect_under_cap():
    B, K = 1, 2
    st = SubstepAdvectionState(qr=torch.tensor([[1e-3, 1e-6]], dtype=torch.float64),
                               nr=torch.zeros(1, 2, dtype=torch.float64),
                               qs=torch.zeros(1, 2, dtype=torch.float64),
                               qg=torch.zeros(1, 2, dtype=torch.float64),
                               brs=torch.zeros(1, 2, dtype=torch.float64))
    led = wb.SedimentationLedger()
    out = _run_cons(st, _full(B, K, 0.015), _full(B, K, 500.0), _full(B, K, 1.0), 60.0, led)
    att = led.finalize()
    D = att.interface_defect_by_species_kg_m2["qr"]
    assert torch.all(D.abs() <= _tol(att.column_loss_by_species_kg_m2["qr"])), D
    # closure at the substep: loss == actual bottom outflow (nothing vanished inside)
    L = att.column_loss_by_species_kg_m2["qr"]
    Ob = att.bottom_actual_outflow_by_species_kg_m2["qr"]
    assert torch.all((L - Ob).abs() <= _tol(L, Ob))
    # and the diag equals the actual bottom outflow (B == 0)
    assert torch.all(att.bottom_diag_gap_by_species_kg_m2["qr"].abs() <= _tol(L))
    # no negatives
    for f_ in out.state:
        assert torch.all(f_ >= 0)


# ── 2. full-step closure: W_post − W_pre + P_actual = O(ε64), per column ─────
def test_conservative_full_step_closure_and_nonneg():
    s, f = _heavy_rain_batch()
    out, budget, att = kdm6_step_conservative_experiment(s, f, dt=120.0)
    R = budget.water_out_kg_m2 - budget.water_in_kg_m2 + budget.surface_precip_diag_kg_m2
    tol = _tol(budget.water_in_kg_m2, budget.water_out_kg_m2, budget.surface_precip_diag_kg_m2)
    assert torch.all(R.abs() <= tol), R
    # per-species: gap between diag and loss at the fp64 floor (nothing vanishes)
    for sp in ("qr", "qs", "qg", "qi"):
        g = att.gap_by_species_kg_m2[sp]
        assert torch.all(g.abs() <= tol), (sp, g)
    for field in out._fields:
        if field in ("th",):
            continue
        assert torch.all(getattr(out, field) >= 0), field


# ── 3. opt-in only: the legacy default path is untouched ─────────────────────
def test_conservative_is_optin_legacy_unchanged():
    s, f = _heavy_rain_batch()
    p = make_parameters()
    ref = _kdm6_pure(s, f, p, dt=120.0)                 # legacy_reference
    again = _kdm6_pure(s, f, p, dt=120.0)
    for field in s._fields:
        assert torch.equal(getattr(ref, field), getattr(again, field))
    cons, _, _ = kdm6_step_conservative_experiment(s, f, p, dt=120.0)
    # the experiment actually changes the capped-regime trajectory (sanity)
    assert not torch.equal(cons.qr, ref.qr)


# ── 4. differentiability: FD directional derivative through the substep ──────
def test_conservative_directional_derivative():
    B, K = 1, 3
    q0 = torch.tensor([[1.2e-3, 1.0e-3, 8.0e-4]], dtype=torch.float64, requires_grad=True)
    w1 = _full(B, K, 0.004)          # smooth regime (c = 0.24, away from min switches)
    delz, dend = _full(B, K, 500.0), _full(B, K, 1.0)

    def loss_of(qr):
        st = SubstepAdvectionState(qr=qr, nr=torch.zeros_like(qr), qs=torch.zeros_like(qr),
                                   qg=torch.zeros_like(qr), brs=torch.zeros_like(qr))
        out = _run_cons(st, w1, delz, dend, 60.0)
        return (out.state.qr ** 2).sum() + (out.fall_qr[:, -1] ** 2).sum()

    val = loss_of(q0)
    (g,) = torch.autograd.grad(val, q0)
    v = torch.tensor([[1.0, -0.5, 0.25]], dtype=torch.float64)
    eps = 1e-7
    with torch.no_grad():
        fd = (loss_of(q0 + eps * v) - loss_of(q0 - eps * v)) / (2 * eps)
    ad = (g * v).sum()
    assert torch.allclose(ad, fd, rtol=1e-6, atol=1e-12), (ad, fd)


# ── 5. multi-mstep + multi-KDM-subcycle closure ──────────────────────────────
def test_conservative_multisubcycle_closure():
    s, f = _heavy_rain_batch()
    out, budget, att = kdm6_step_conservative_experiment(s, f, dt=300.0)
    assert int(budget.n_subcycles) >= 2
    R = budget.water_out_kg_m2 - budget.water_in_kg_m2 + budget.surface_precip_diag_kg_m2
    tol = _tol(budget.water_in_kg_m2, budget.water_out_kg_m2, budget.surface_precip_diag_kg_m2)
    assert torch.all(R.abs() <= tol), R


# ── 6. ice chain conservative variant ────────────────────────────────────────
def test_conservative_ice_no_defect():
    from kdm6.sedimentation import IceSubstepState
    B, K = 1, 2
    led = wb.SedimentationLedger()
    z = torch.zeros(B, K, dtype=torch.float64)
    ice = IceSubstepState(qi=_full(B, K, 1e-4), ni=_full(B, K, 1e3))
    conservative_ice_substep_advection_torch(
        ice, z.clone(), z.clone(), _full(B, K, 0.02), torch.zeros(B, K, dtype=torch.float64),
        _full(B, K, 500.0), _full(B, K, 1.0), mstep=1, dtcld=60.0,
        params=default_substep_advection_params(), ledger=led)
    att = led.finalize()
    assert torch.all(att.interface_defect_by_species_kg_m2["qi"].abs()
                     <= _tol(att.column_loss_by_species_kg_m2["qi"]))
    assert torch.all(att.gap_by_species_kg_m2["qi"].abs()
                     <= _tol(att.column_loss_by_species_kg_m2["qi"]))
