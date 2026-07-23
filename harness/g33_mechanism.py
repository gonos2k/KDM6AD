#!/usr/bin/env python3
"""Role/species/expression-aware mechanism taxonomy for the G3.3-M op ladder.

At a FIRST cross-tree divergence the inputs are identical (upstream matched), so
the divergence is in that rung's own step — and its MechanismSpec.kind decides
attribution. The earlier taxonomy was too coarse and could flip PASS/FAIL:

  input           — a state/carry value (reservoir, above-cell flux, pre-update
                    state, the qr seed reaching the surface). It cannot be the
                    genuine first mechanism divergence: if it differs while its
                    source matched, the evidence is INCONSISTENT -> INVALID_EVIDENCE.
  shared          — an operation identical in both variants (falk chain, min-cap
                    outflow, the INTERIOR capped depletion, the surface species
                    sum). Both pairs diverging at the SAME shared rung -> PASS.
  legacy /        — variant-specific arithmetic. A conservative-pair first
  conservative      divergence in `conservative` arithmetic (ρΔz inflow, rate
                    accumulator, no-clamp update, the capped-vs-raw TOP depletion)
                    -> FAIL.
  out_of_scope    — a species outside the qr/nr first scope (snow/ice/graupel
                    surface fall) whose upstream provenance is not instrumented
                    -> INCONCLUSIVE.

Role matters: TOP `q_minus_out` is legacy RAW depletion (q - falk·dt/ρ, clamped
after) vs conservative CAPPED depletion (q - min(...)); INTERIOR/BOTTOM subtract
the SAME capped outflow in both, so only there is it shared.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import g33_schema as schema  # noqa: E402

INPUT, SHARED, LEGACY, CONSERVATIVE, OUT_OF_SCOPE = (
    "input", "shared", "legacy", "conservative", "out_of_scope")


@dataclass(frozen=True)
class MechanismSpec:
    kind: str        # one of the five above
    tag: str         # variant-INDEPENDENT for shared rungs (drives PASS alignment)


def _variant(algo, tag_base):
    return MechanismSpec(CONSERVATIVE if algo == "conservative" else LEGACY,
                         f"{'CONS' if algo == 'conservative' else 'LEG'}_{tag_base}")


_INFLOW_CARRIES = {"stored_falk_prev", "stored_falk_nr_prev", "prev_out",
                   "prev_out_nr", "delz_raw_src", "delz_safe_dst", "dend_safe_dst",
                   "dend_safe_src", "source_reservoir"}


def mechanism(algorithm, role, species, op_id, field) -> MechanismSpec:
    cons = algorithm == "conservative"
    family = op_id.split("_", 1)[1]        # FALK|OUTFLOW|FALLACC|INFLOW|UPDATE
    if family == "FALK":
        return MechanismSpec(SHARED, f"FALK_{field}")
    if family == "OUTFLOW":
        if field == "source_reservoir":
            return MechanismSpec(INPUT, "OUTFLOW_reservoir")
        return MechanismSpec(SHARED, f"OUTFLOW_{field}")
    if family == "FALLACC":
        if field == "fall_before":
            return MechanismSpec(INPUT, "FALLACC_carry_before")
        if field in ("dq_out", "dn_out"):
            return MechanismSpec(INPUT, "FALLACC_carry_outflow")
        if field in ("mul_dend_safe", "fall_increment"):
            # legacy fall_increment is the shared falk carry; conservative is rate.
            return (MechanismSpec(CONSERVATIVE, f"CONS_FALLACC_{field}") if cons
                    else MechanismSpec(INPUT, "FALLACC_carry_falk"))
        # fall_after — the variant-specific accumulator result.
        return _variant(algorithm, "FALLACC_result")
    if family == "INFLOW":
        if field in _INFLOW_CARRIES:
            return MechanismSpec(INPUT, "INFLOW_carry")
        return _variant(algorithm, "INFLOW_rhodz" if cons else "INFLOW_dzcap")
    if family == "UPDATE":
        if field in ("q_before", "n_before"):
            return MechanismSpec(INPUT, "UPDATE_state_before")
        if field in ("q_minus_out", "n_minus_out"):
            if role == "TOP":                # legacy RAW vs conservative CAPPED
                return _variant(algorithm, "UPDATE_depletion")
            return MechanismSpec(SHARED, "UPDATE_minus_capped_outflow")
        if field in ("q_plus_in_preclamp", "n_plus_in_preclamp"):
            return _variant(algorithm, "UPDATE_plus_inflow")
        if field == "clamp_active":
            return MechanismSpec(LEGACY, "LEG_UPDATE_positivity_clamp")
        # q_post / n_post — legacy clamped vs conservative no-clamp.
        return _variant(algorithm, "UPDATE_result")
    raise KeyError(f"no mechanism for {op_id}.{field}")


_OUT_OF_SCOPE_SURFACE = {"bottom_fall_qs", "bottom_fall_qg", "bottom_fall_qi"}


def surface_mechanism(field) -> MechanismSpec:
    if field == "bottom_fall_qr":
        return MechanismSpec(INPUT, "SURFACE_carry_qr")
    if field in _OUT_OF_SCOPE_SURFACE:
        return MechanismSpec(OUT_OF_SCOPE, f"SURFACE_{field}")
    if field in ("delz_bottom", "surface_denr"):
        return MechanismSpec(INPUT, "SURFACE_input")
    if field == "bottom_fall_total":
        return MechanismSpec(SHARED, "SURFACE_species_sum")
    raise KeyError(f"no surface mechanism for {field}")


def check_universe():
    """Every schema op field (both variants, all roles) must map to a spec —
    a missing or crashing mapping is a taxonomy hole. Called by a test."""
    for algo in ("legacy", "conservative"):
        for role in ("TOP", "INTERIOR", "BOTTOM"):
            for sp in ("qr", "nr"):
                for op_id in schema.ops_for_species(algo, role, sp):
                    for f, _ in schema.op_fields(algo, role, op_id):
                        mechanism(algo, role, sp, op_id, f)   # raises on a hole
