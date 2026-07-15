"""P0-4 — ρΔz-weighted column water-budget diagnostic (oracle-side, opt-in).

Column total water  W(x;f) = Σ_k ρ_k Δz_k (q_v+q_c+q_r+q_i+q_s+q_g)_k  [kg/m²].

The diagnostic decomposes a single ``kdm6_step`` into the two operators the driver
applies per sub-cycle. Closing it is an OPERATOR-DECOMPOSITION IDENTITY (a ledger
self-consistency check that no hook / sub-cycle was missed), NOT an independent
physical-conservation proof:

    W_out − W_in  =  ΔW_sed + ΔW_micro          (exact for admissible inputs)

The two independent scientific results are:
  * ΔW_micro ≈ 0 — microphysics (incl. threshold cleanup) conserves column water
    to fp64 roundoff. The cleanup sink, measured at the exact
    ``apply_threshold_cleanup`` boundary, accounts for that (tiny) non-conservation.
  * ``sed_column_loss`` (= −ΔW_sed, the operator-implied net column-water loss) and
    ``rain_increment`` (the WRF-facing total-fallout diagnostic) DISAGREE. Which side
    is at fault (RAINNCV under-report vs. a sedimentation clamp/cap) is unresolved —
    ``sed_surface_diag_gap`` characterizes it, pending P0-4b.

All quantities are per-column ``(B,)`` and detached (no autograd / no effect on the
forward path). The diagnostic is opt-in: the default ``kdm6_step`` path is unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass

import torch

MASS_FIELDS = ("qc", "qr", "qi", "qs", "qg")


def column_water_kg_m2(state, forcing) -> torch.Tensor:
    """Σ_k ρ_k Δz_k (qv+qc+qr+qi+qs+qg)_k, per column (B,). State/Forcing space."""
    rho_dz = forcing.rho * forcing.delz
    qt = state.qv + state.qc + state.qr + state.qi + state.qs + state.qg
    return (rho_dz * qt).sum(dim=-1)


def _column_water_coord(cs, cforcing) -> torch.Tensor:
    """Same measure in CoordinatorState/CoordinatorForcing space (den, delz)."""
    rho_dz = cforcing.den * cforcing.delz
    qt = cs.qv + cs.qc + cs.qr + cs.qi + cs.qs + cs.qg
    return (rho_dz * qt).sum(dim=-1)


def hydrometeor_mass_sink_kg_m2(pre, post, rho_dz) -> dict:
    """Per-species ρΔz-weighted mass removed (pre − post), each (B,). Works on any
    object exposing .qc/.qr/.qi/.qs/.qg (State or CoordinatorState). ``rho_dz`` is
    the per-level (B,K) weight ρ·Δz."""
    return {x: (rho_dz * (getattr(pre, x) - getattr(post, x))).sum(dim=-1)
            for x in MASS_FIELDS}


@dataclass(frozen=True)
class ColumnWaterBudget:
    water_in_kg_m2: torch.Tensor          # (B,)
    water_out_kg_m2: torch.Tensor         # (B,)
    sed_column_loss_kg_m2: torch.Tensor   # (B,) = −ΔW_sed, operator-implied net column-water loss
    micro_dW_kg_m2: torch.Tensor          # (B,) = ΔW_micro (≈0: microphysics conserves)
    surface_precip_diag_kg_m2: torch.Tensor  # (B,) = Σ rain_increment (WRF RAINNCV total-fallout diag)
    cleanup_by_species_kg_m2: dict        # species -> (B,)
    cleanup_total_kg_m2: torch.Tensor     # (B,) = Σ_species cleanup
    decomposition_residual_kg_m2: torch.Tensor  # (B,) = W_out−W_in+sed_column_loss−micro_dW (ledger self-consistency, ≈0)
    sed_surface_diag_gap_kg_m2: torch.Tensor  # (B,) = surface_precip_diag − sed_column_loss (unresolved, → P0-4b)
    n_subcycles: int


class _WaterBudgetLedger:
    """Mutable per-subcycle accumulator threaded through the (opt-in) forward path.
    All records are detached — the ledger never touches the autograd graph."""

    def __init__(self):
        self.sed_dW = None
        self.micro_dW = None
        self.surface = None
        self.cleanup = {x: None for x in MASS_FIELDS}
        self.n_subcycles = 0

    @staticmethod
    def _acc(cur, val):
        return val if cur is None else cur + val

    def add_sed(self, cs_before, cs_after, rain_increment, cforcing):
        dW = (_column_water_coord(cs_after, cforcing)
              - _column_water_coord(cs_before, cforcing)).detach()
        self.sed_dW = self._acc(self.sed_dW, dW)
        self.surface = self._acc(self.surface, rain_increment.detach())
        self.n_subcycles += 1

    def add_micro(self, cs_before, cs_after, cforcing):
        dW = (_column_water_coord(cs_after, cforcing)
              - _column_water_coord(cs_before, cforcing)).detach()
        self.micro_dW = self._acc(self.micro_dW, dW)

    def add_cleanup(self, cs_pre, cs_post, cforcing):
        """Exact per-species sink at the apply_threshold_cleanup boundary."""
        rho_dz = cforcing.den * cforcing.delz
        sink = hydrometeor_mass_sink_kg_m2(cs_pre, cs_post, rho_dz)
        for x in MASS_FIELDS:
            self.cleanup[x] = self._acc(self.cleanup[x], sink[x].detach())


def kdm6_step_with_water_budget(
    state, forcing, params=None, dt: float = 60.0, *,
    xland=None, ncmin_land: float = 0.0, ncmin_sea: float = 0.0, controls=None,
):
    """Run one ``_kdm6_pure`` step and return ``(State, ColumnWaterBudget)``.

    The returned state is byte-identical to ``_kdm6_pure(...)`` without a budget —
    the diagnostic only observes. See ColumnWaterBudget for the reported terms.
    """
    from .runtime import _kdm6_pure, make_parameters

    if params is None:
        params = make_parameters()
    ledger = _WaterBudgetLedger()
    win = column_water_kg_m2(state, forcing).detach()
    out = _kdm6_pure(state, forcing, params, dt, xland=xland,
                     ncmin_land=ncmin_land, ncmin_sea=ncmin_sea,
                     controls=controls, budget=ledger)
    wout = column_water_kg_m2(out, forcing).detach()

    z = torch.zeros_like(win)
    cleanup = {x: (ledger.cleanup[x] if ledger.cleanup[x] is not None else z)
               for x in MASS_FIELDS}
    cleanup_total = torch.stack([cleanup[x] for x in MASS_FIELDS]).sum(dim=0)
    surface = ledger.surface if ledger.surface is not None else z
    sed_dW = ledger.sed_dW if ledger.sed_dW is not None else z
    micro_dW = ledger.micro_dW if ledger.micro_dW is not None else z
    sed_column_loss = -sed_dW
    decomposition_residual = wout - win + sed_column_loss - micro_dW
    gap = surface - sed_column_loss

    return out, ColumnWaterBudget(
        water_in_kg_m2=win, water_out_kg_m2=wout,
        sed_column_loss_kg_m2=sed_column_loss, micro_dW_kg_m2=micro_dW,
        surface_precip_diag_kg_m2=surface,
        cleanup_by_species_kg_m2=cleanup, cleanup_total_kg_m2=cleanup_total,
        decomposition_residual_kg_m2=decomposition_residual,
        sed_surface_diag_gap_kg_m2=gap,
        n_subcycles=ledger.n_subcycles,
    )
