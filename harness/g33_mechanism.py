#!/usr/bin/env python3
"""Closed-world, role/species/expression-aware mechanism taxonomy for the G3.3-M
op ladder.

At a FIRST cross-tree divergence the inputs are identical (upstream matched), so
the divergence is in that rung's own step, and its MechanismSpec.kind decides
attribution:

  causal_carry   — a value carried bit-for-bit from an EARLIER instrumented event
                   (a reservoir, an above-cell flux, the pre-update state, the qr
                   seed reaching the surface, the accumulator's prior value). If it
                   differs while its source matched, the evidence is internally
                   INCONSISTENT -> INVALID_EVIDENCE.
  external_input — a value from OUTSIDE the instrumented ladder (a grid metric, a
                   baked constant) whose cross-tree equality is a fixture/parameter
                   precondition, not a ladder result. A first difference here means
                   the two runs did not solve the same problem -> INCONCLUSIVE until
                   a bundle preflight seals it.
  shared         — an operation identical in both variants (the falk chain, the
                   min-cap outflow, the INTERIOR/BOTTOM capped-outflow subtraction,
                   the fall accumulator ADD, the species sum, the rain conversion).
                   Both pairs diverging at the SAME shared rung -> PASS.
  legacy /       — variant-specific arithmetic (the capped-vs-raw TOP depletion, the
  conservative     Δz-capped vs ρΔz/Δz inflow, the rate accumulator, the clamp, the
                   clamped-vs-noclamp update). A conservative-pair first divergence
                   in `conservative` arithmetic -> FAIL.
  out_of_scope   — a species outside the qr/nr first scope (snow/ice/graupel fall,
                   snow/graupel precip output) with no instrumented provenance
                   here -> INCONCLUSIVE.

CLOSED WORLD: the mechanism of every schema field is enumerated EXPLICITLY below.
A new schema field with no entry raises at import (check_universe / the module-load
build), so a taxonomy hole fails CI instead of silently defaulting to a variant
result — the fail-open that let earlier false PASS/FAIL through.

Role matters (TOP q_minus_out is legacy RAW vs conservative CAPPED depletion; only
INTERIOR/BOTTOM subtract the same capped outflow). Species matters for the LABEL:
conservative qr transports mass by ρΔz, conservative nr transports number by Δz —
naming the nr path "ρΔz" would misstate the physics in a decision document.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import g33_schema as schema  # noqa: E402

(CAUSAL_CARRY, EXTERNAL_INPUT, SHARED, LEGACY, CONSERVATIVE, OUT_OF_SCOPE) = (
    "causal_carry", "external_input", "shared", "legacy", "conservative", "out_of_scope")


@dataclass(frozen=True)
class MechanismSpec:
    kind: str        # one of the six above
    tag: str         # variant-INDEPENDENT for shared rungs (drives PASS alignment)


class TaxonomyHole(KeyError):
    """A schema field has no explicit mechanism entry — a fail-open must not exist."""


def _mass_or_number(species):     # LABEL only; kind is conservative either way
    return "MASS" if species == "qr" else "NUMBER"


def _classify(algo, role, species, op_id, field) -> MechanismSpec:
    cons = algo == "conservative"
    fam = op_id.split("_", 1)[1]        # FALK|OUTFLOW|FALLACC|INFLOW|UPDATE
    mn = _mass_or_number(species)

    if fam == "FALK":
        if field in ("mul_dend_q", "mul_workn", "mul_work1", "div_mstep",
                     "falk_precast", "shadow_falk_f32", "falk_f32"):
            return MechanismSpec(SHARED, f"FALK/{field}")

    elif fam == "OUTFLOW":
        if field == "source_reservoir":
            return MechanismSpec(CAUSAL_CARRY, "CARRY/outflow_reservoir")
        if field in ("mul_dt", "outflow_pre_cap", "cap_active", "dq_out", "dn_out"):
            return MechanismSpec(SHARED, f"OUTFLOW/{field}")

    elif fam == "FALLACC":
        if field == "fall_before":
            return MechanismSpec(CAUSAL_CARRY, "CARRY/fall_before")
        if field in ("dq_out", "dn_out"):
            return MechanismSpec(CAUSAL_CARRY, "CARRY/fall_outflow")
        if field == "mul_dend_safe":          # conservative qr only
            return MechanismSpec(CONSERVATIVE, "CONS_MASS_RATE_ACCUMULATION")
        if field == "fall_increment":
            # legacy increment is the shared falk carry; conservative is the rate.
            return (MechanismSpec(CONSERVATIVE, f"CONS_{mn}_RATE_ACCUMULATION") if cons
                    else MechanismSpec(CAUSAL_CARRY, "CARRY/fall_increment_falk"))
        if field == "fall_after":
            # P0-1: given matched fall_before + fall_increment, this is fl32(a+b) —
            # the SAME accumulator add in both variants, not a variant result.
            return MechanismSpec(SHARED, "FALLACC/accumulator_add")

    elif fam == "INFLOW":
        if field in ("stored_falk_prev", "stored_falk_nr_prev", "prev_out",
                     "prev_out_nr", "delz_raw_src", "delz_safe_dst", "dend_safe_dst",
                     "dend_safe_src", "source_reservoir"):
            return MechanismSpec(CAUSAL_CARRY, "CARRY/inflow_input")
        if not cons and field in ("mul_delz_src", "div_delz_dst", "mul_dt",
                                  "inflow_pre_cap", "inflow_cap_active", "inflow_final"):
            return MechanismSpec(LEGACY, "LEG_DZ_CAPPED_INFLOW")
        if cons and field in ("src_metric", "dst_metric", "mul_src",
                              "mul_delz_src", "inflow_final"):
            # qr: ρΔz mass transport; nr: Δz-only number transport (P0-2).
            tag = "CONS_MASS_RHODZ_INFLOW" if species == "qr" else "CONS_NUMBER_DZ_INFLOW"
            return MechanismSpec(CONSERVATIVE, tag)

    elif fam == "UPDATE":
        if field in ("q_before", "n_before"):
            return MechanismSpec(CAUSAL_CARRY, "CARRY/update_state_before")
        if field in ("q_minus_out", "n_minus_out"):
            if role == "TOP":                # legacy RAW vs conservative CAPPED
                return (MechanismSpec(CONSERVATIVE, "CONS_CAPPED_DEPLETION") if cons
                        else MechanismSpec(LEGACY, "LEG_RAW_DEPLETION"))
            return MechanismSpec(SHARED, "UPDATE/minus_capped_outflow")
        if field in ("q_plus_in_preclamp", "n_plus_in_preclamp"):
            return (MechanismSpec(CONSERVATIVE, f"CONS_{mn}_PLUS_INFLOW") if cons
                    else MechanismSpec(LEGACY, "LEG_DZ_PLUS_INFLOW"))
        if field == "clamp_active":
            return MechanismSpec(LEGACY, "LEG_POSITIVITY_CLAMP")
        if field in ("q_post", "n_post"):
            return (MechanismSpec(CONSERVATIVE, f"CONS_{mn}_NOCLAMP_UPDATE") if cons
                    else MechanismSpec(LEGACY, "LEG_CLAMPED_UPDATE"))

    raise TaxonomyHole(f"no mechanism entry for {algo}/{role}/{species} {op_id}.{field}")


# Surface field taxonomy — a COMMON semantic schema across backends. Fortran PREC
# family 1/2/3 and C++ rain/snow/graupel_increment both project onto these names.
_SURFACE = {
    "bottom_fall_qr": (CAUSAL_CARRY, "CARRY/surface_qr"),
    "bottom_fall_qs": (OUT_OF_SCOPE, "OOS/surface_qs"),
    "bottom_fall_qg": (OUT_OF_SCOPE, "OOS/surface_qg"),
    "bottom_fall_qi": (OUT_OF_SCOPE, "OOS/surface_qi"),
    "bottom_fall_total": (SHARED, "SURFACE/species_sum"),
    "delz_bottom": (EXTERNAL_INPUT, "EXTERNAL/delz_bottom"),
    "surface_denr": (EXTERNAL_INPUT, "EXTERNAL/surface_denr"),
    "rain_increment": (SHARED, "SURFACE/rain_conversion"),
    "snow_increment": (OUT_OF_SCOPE, "OOS/snow_increment"),
    "graupel_increment": (OUT_OF_SCOPE, "OOS/graupel_increment"),
}


def surface_mechanism(field) -> MechanismSpec:
    try:
        return MechanismSpec(*_SURFACE[field])
    except KeyError:
        raise TaxonomyHole(f"no surface mechanism entry for {field!r}") from None


# Build the closed-world table at import: any schema field _classify does not
# explicitly enumerate raises here, so the module cannot load with a hole.
def _schema_universe():
    for algo in ("legacy", "conservative"):
        for role in ("TOP", "INTERIOR", "BOTTOM"):
            for sp in ("qr", "nr"):
                for op_id in schema.ops_for_species(algo, role, sp):
                    for f, _ in schema.op_fields(algo, role, op_id):
                        yield algo, role, sp, op_id, f


MECHANISMS = {key: _classify(*key) for key in _schema_universe()}


def mechanism(algorithm, role, species, op_id, field) -> MechanismSpec:
    try:
        return MECHANISMS[(algorithm, role, species, op_id, field)]
    except KeyError:
        # Not in the pre-built table -> an out-of-schema field. Classify live so the
        # hole raises TaxonomyHole rather than a bare KeyError the caller misreads.
        return _classify(algorithm, role, species, op_id, field)


def check_universe():
    """Closed-world guard: the table covers exactly the schema universe, and a
    field outside it fails loudly (not a silent variant default)."""
    universe = set(_schema_universe())
    assert set(MECHANISMS) == universe, "mechanism table != schema universe"
    try:
        _classify("legacy", "INTERIOR", "qr", "QR_FALK", "not_a_real_field")
    except TaxonomyHole:
        return
    raise AssertionError("taxonomy is fail-open: an unknown field did not raise")
