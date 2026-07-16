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
        self.sed_ledger = None   # [P0-4b] optional SedimentationLedger (attribution)

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


def _run_with_budget(state, forcing, params, dt, *, xland, ncmin_land, ncmin_sea,
                     controls, sed_ledger=None):
    from .runtime import _kdm6_pure, make_parameters

    if params is None:
        params = make_parameters()
    ledger = _WaterBudgetLedger()
    ledger.sed_ledger = sed_ledger
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

    budget = ColumnWaterBudget(
        water_in_kg_m2=win, water_out_kg_m2=wout,
        sed_column_loss_kg_m2=sed_column_loss, micro_dW_kg_m2=micro_dW,
        surface_precip_diag_kg_m2=surface,
        cleanup_by_species_kg_m2=cleanup, cleanup_total_kg_m2=cleanup_total,
        decomposition_residual_kg_m2=decomposition_residual,
        sed_surface_diag_gap_kg_m2=gap,
        n_subcycles=ledger.n_subcycles,
    )
    return out, budget


def kdm6_step_with_water_budget(
    state, forcing, params=None, dt: float = 60.0, *,
    xland=None, ncmin_land: float = 0.0, ncmin_sea: float = 0.0, controls=None,
):
    """Run one ``_kdm6_pure`` step and return ``(State, ColumnWaterBudget)``.

    The returned state is byte-identical to ``_kdm6_pure(...)`` without a budget —
    the diagnostic only observes. See ColumnWaterBudget for the reported terms.
    """
    return _run_with_budget(state, forcing, params, dt, xland=xland,
                            ncmin_land=ncmin_land, ncmin_sea=ncmin_sea,
                            controls=controls)


# ─── P0-4b: sedimentation gap attribution ────────────────────────────────────
#
# Attributes the gap between the operator-implied column loss L_s and the WRF
# fallout diagnostic P_s, per species / per column / per level, via the exact
# per-level bookkeeping  ρΔz(q_entry − q_post) = O − I − A  recorded inside the
# sedimentation substeps (O = outflow actually used in the update; I = inflow
# actually used; A = positivity-projection addition). Summing over levels:
#
#     L_s = O_bottom + ΣD − ΣA,      D_k = O_{k−1} − I_k   (interface defect)
#     P_s − L_s = B_s − ΣD + ΣA,     B_s = P_s − O_bottom  (bottom diag gap)
#
# Attribution only — the substep hooks are `if ledger is not None`-guarded and
# detached; the forward path is unchanged (torch.equal-verified in tests).

SED_SPECIES = ("qr", "qs", "qg", "qi")


@dataclass(frozen=True)
class SedimentationAttribution:
    # Independent measures (each dict value: (B,))
    column_loss_by_species_kg_m2: dict          # L_s = ΣρΔz(q_pre − q_post), state-based
    wrf_fallout_diag_by_species_kg_m2: dict     # P_s = Σ falk_s,bottom·Δz_bottom·dtcld
    gap_by_species_kg_m2: dict                  # P_s − L_s

    # Attribution terms (each (B,))
    bottom_actual_outflow_by_species_kg_m2: dict   # Σ O_bottom
    bottom_diag_gap_by_species_kg_m2: dict         # B_s = P_s − O_bottom
    interface_defect_by_species_kg_m2: dict        # ΣD (signed)
    positivity_projection_by_species_kg_m2: dict   # ΣA (≥0; top cell only, structurally)

    # Forensic detail (levels in the chain's K-order: 0 = top, K−1 = bottom)
    interface_defect_detail_kg_m2: dict         # (B, K−1) summed over substeps
    projection_detail_kg_m2: dict               # (B, K)   summed over substeps
    cap_flags: dict                             # f"{s}_{outflow_cap|inflow_cap|top_clamp}" -> (B,) counts
    worst_interface_index: dict                 # argmax_k |D detail| -> (B,) int64

    attributed_gap_kg_m2: torch.Tensor          # Σ_s (B_s − ΣD_s + ΣA_s)
    unattributed_residual_kg_m2: torch.Tensor   # Σ_s gap_s − attributed  (≈ fp64 floor)


class SedimentationLedger:
    """Per-substep accumulator fed by the sedimentation substep functions.
    All inputs are detached mass-weighted tensors; ``finalize()`` assembles a
    SedimentationAttribution."""

    def __init__(self):
        self._acc = {}

    def record(self, species, out_mass, in_mass, proj_mass, diag_inc, state_loss, flags):
        d = self._acc.setdefault(species, {"flags": {}})

        def _a(key, val):
            d[key] = val if key not in d else d[key] + val

        _a("out", out_mass)
        _a("in", in_mass)
        _a("proj", proj_mass)
        _a("diag", diag_inc)
        _a("loss", state_loss)
        for k, v in flags.items():
            d["flags"][k] = v if k not in d["flags"] else d["flags"][k] + v

    def finalize(self) -> SedimentationAttribution:
        if not self._acc:
            raise ValueError("SedimentationLedger: no sedimentation substep recorded")
        ref = next(iter(self._acc.values()))["out"]     # (B, K) shape/dtype reference
        B, K = ref.shape
        zBK = torch.zeros_like(ref)
        zB = torch.zeros(B, dtype=ref.dtype)
        zL = torch.zeros(B, dtype=torch.int64)

        loss, diag, gap = {}, {}, {}
        o_bot, b_gap, d_sum, a_sum = {}, {}, {}, {}
        d_det, a_det, flags, worst = {}, {}, {}, {}
        for s in SED_SPECIES:
            d = self._acc.get(s)
            out = d["out"] if d else zBK
            inn = d["in"] if d else zBK
            proj = d["proj"] if d else zBK
            loss[s] = d["loss"] if d else zB.clone()
            diag[s] = d["diag"] if d else zB.clone()
            o_bot[s] = out[:, -1]
            det = out[:, :-1] - inn[:, 1:]              # D_k = O_{k−1} − I_k, (B, K−1)
            d_det[s] = det
            d_sum[s] = det.sum(dim=-1) if K > 1 else zB.clone()
            a_det[s] = proj
            a_sum[s] = proj.sum(dim=-1)
            gap[s] = diag[s] - loss[s]
            b_gap[s] = diag[s] - o_bot[s]
            worst[s] = det.abs().argmax(dim=-1) if K > 1 else zL.clone()
            for k, v in (d["flags"] if d else {}).items():
                flags[f"{s}_{k}"] = v
            for k in ("outflow_cap", "inflow_cap", "top_clamp"):
                flags.setdefault(f"{s}_{k}", zL.clone())

        attributed = torch.stack(
            [b_gap[s] - d_sum[s] + a_sum[s] for s in SED_SPECIES]).sum(dim=0)
        total_gap = torch.stack([gap[s] for s in SED_SPECIES]).sum(dim=0)
        return SedimentationAttribution(
            column_loss_by_species_kg_m2=loss,
            wrf_fallout_diag_by_species_kg_m2=diag,
            gap_by_species_kg_m2=gap,
            bottom_actual_outflow_by_species_kg_m2=o_bot,
            bottom_diag_gap_by_species_kg_m2=b_gap,
            interface_defect_by_species_kg_m2=d_sum,
            positivity_projection_by_species_kg_m2=a_sum,
            interface_defect_detail_kg_m2=d_det,
            projection_detail_kg_m2=a_det,
            cap_flags=flags,
            worst_interface_index=worst,
            attributed_gap_kg_m2=attributed,
            unattributed_residual_kg_m2=total_gap - attributed,
        )


def kdm6_step_with_sed_attribution(
    state, forcing, params=None, dt: float = 60.0, *,
    xland=None, ncmin_land: float = 0.0, ncmin_sea: float = 0.0, controls=None,
):
    """Run one step and return ``(State, ColumnWaterBudget, SedimentationAttribution)``.

    Adds the P0-4b per-species sedimentation attribution on top of the P0-4
    budget. Diagnostics-only: the returned state is byte-identical to the
    plain ``_kdm6_pure`` path.
    """
    sed = SedimentationLedger()
    out, budget = _run_with_budget(state, forcing, params, dt, xland=xland,
                                   ncmin_land=ncmin_land, ncmin_sea=ncmin_sea,
                                   controls=controls, sed_ledger=sed)
    return out, budget, sed.finalize()
