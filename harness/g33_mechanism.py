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


# What a rung must satisfy in a GATE-INACTIVE column (gate==0, i.e. n > that
# column's mstep). The per-column gate is a terminal MULTIPLY at the end of the falk
# chain (s4 = s3 * gate_col), so only the rungs BEFORE that multiply are
# computed-then-discarded; every operand downstream is derived from falk (or from
# dq_out) and therefore has an exact no-op value the arithmetic guarantees:
#
#   IGNORE    pre-gate diagnostic — may differ across backends, excluded from the
#             verdict (the ONLY rungs that may be skipped in a dead lane)
#   ZERO      derived from falk / dq_out, so identically +-0
#   EQUAL_TO  a state rung that must still equal its own input (no transport)
#   FALSE     a branch flag that cannot fire without transport
#   CARRY     a state or metric input (q, delz, dend, src_metric...) — neither
#             skippable nor pinned; the DEFAULT, so a new field is never fail-open
IGNORE, ZERO, EQUAL_TO, FALSE, CARRY = "ignore", "zero", "equal_to", "false", "carry"


@dataclass(frozen=True)
class MechanismSpec:
    kind: str                        # one of the six above
    tag: str                         # variant-INDEPENDENT (drives PASS alignment)
    inactive: str = CARRY            # relation that must hold in a dead lane
    inactive_ref: str | None = None  # the field EQUAL_TO refers to
    # An ACTUAL transported quantity: in an ACTIVE lane sedimentation's valid domain
    # requires it to be finite AND non-negative.
    active_nonneg: bool = False


# ── ACTIVE-lane numerical domain (closed world, like the mechanism kinds) ────
# Every schema field declares the domain its value must occupy in an ACTIVE lane.
# A single `active_nonneg` boolean covered only the final transports, so a NaN or a
# negative value in an intermediate rung could reach the verdict and — if both pairs
# hit the same shared rung — even PASS.
POSITIVE_FINITE = "positive_finite"   # a grid metric: must be > 0
NONNEG_FINITE = "nonneg_finite"       # a mass/number/flux quantity: >= 0
SIGNED_FINITE = "signed_finite"       # may legitimately be negative (pre-clamp)
BOOL_BRANCH = "bool_branch"           # a branch flag: 0/1, recomputed from operands

_METRICS = ("delz_raw_src", "delz_safe_dst", "dend_safe_dst", "dend_safe_src",
            "src_metric", "dst_metric")
# pre-clamp rungs may be negative — that is exactly what the legacy clamp exists for
_SIGNED = ("q_minus_out", "n_minus_out", "q_plus_in_preclamp", "n_plus_in_preclamp")
_FLAGS = ("cap_active", "inflow_cap_active", "clamp_active")


def domain_rule(field: str) -> str:
    """The ACTIVE-lane domain of a field. Closed world: check_universe() proves every
    schema field is covered, so a new field cannot slip in unconstrained."""
    if field in _FLAGS:
        return BOOL_BRANCH
    if field in _METRICS:
        return POSITIVE_FINITE
    if field in _SIGNED:
        return SIGNED_FINITE
    return NONNEG_FINITE          # every remaining rung is a mass/number/flux


class TaxonomyHole(KeyError):
    """A schema field has no explicit mechanism entry — a fail-open must not exist."""


def _mass_or_number(species):     # LABEL only; kind is conservative either way
    return "MASS" if species == "qr" else "NUMBER"


def _classify(algo, role, species, op_id, field) -> MechanismSpec:
    cons = algo == "conservative"
    fam = op_id.split("_", 1)[1]        # FALK|OUTFLOW|FALLACC|INFLOW|UPDATE
    mn = _mass_or_number(species)
    q_before = "n_before" if species == "nr" else "q_before"
    q_minus = "n_minus_out" if species == "nr" else "q_minus_out"

    if fam == "FALK":
        if field in ("mul_dend_q", "mul_work1", "mul_workn", "div_mstep"):
            # computed BEFORE the terminal `* gate_col`, so a dead lane discards it
            return MechanismSpec(SHARED, f"FALK/{field}", IGNORE)
        if field in ("falk_precast", "shadow_falk_f32", "falk_f32"):
            # gate already applied -> an ACTUAL fall rate (0 in a dead lane)
            return MechanismSpec(SHARED, f"FALK/{field}", ZERO, active_nonneg=True)

    elif fam == "OUTFLOW":
        if field == "source_reservoir":                     # the state q itself
            return MechanismSpec(CAUSAL_CARRY, "CARRY/outflow_reservoir", CARRY)
        if field in ("dq_out", "dn_out"):                   # the transported amount
            return MechanismSpec(SHARED, f"OUTFLOW/{field}", ZERO, active_nonneg=True)
        if field in ("mul_dt", "outflow_pre_cap"):          # falk*dt, /dend -> 0
            return MechanismSpec(SHARED, f"OUTFLOW/{field}", ZERO)
        if field == "cap_active":
            # falk==0 -> outflow_pre_cap==0, and the reservoir is non-negative, so
            # the min-cap cannot bind in a dead lane.
            return MechanismSpec(SHARED, "OUTFLOW/cap_active", FALSE)

    elif fam == "FALLACC":
        if field == "fall_before":
            return MechanismSpec(CAUSAL_CARRY, "CARRY/fall_before", CARRY)
        if field in ("dq_out", "dn_out"):                   # carried outflow -> 0
            return MechanismSpec(CAUSAL_CARRY, "CARRY/fall_outflow", ZERO)
        if field == "mul_dend_safe":          # conservative qr: dq_out*dend -> 0
            return MechanismSpec(CONSERVATIVE, "CONS_MASS_RATE_ACCUMULATION", ZERO)
        if field == "fall_increment":         # legacy falk / conservative rate -> 0
            return (MechanismSpec(CONSERVATIVE, f"CONS_{mn}_RATE_ACCUMULATION", ZERO) if cons
                    else MechanismSpec(CAUSAL_CARRY, "CARRY/fall_increment_falk", ZERO))
        if field == "fall_after":
            # given matched fall_before + fall_increment this is fl32(a+b) — the SAME
            # accumulator add in both variants; unchanged when nothing fell.
            return MechanismSpec(SHARED, "FALLACC/accumulator_add", EQUAL_TO,
                                 "fall_before", active_nonneg=True)

    elif fam == "INFLOW":
        if field in ("stored_falk_prev", "stored_falk_nr_prev", "prev_out",
                     "prev_out_nr", "delz_raw_src", "delz_safe_dst", "dend_safe_dst",
                     "dend_safe_src", "source_reservoir", "src_metric", "dst_metric"):
            # states and grid metrics — a metric is NOT zero in a dead lane
            return MechanismSpec(CAUSAL_CARRY, "CARRY/inflow_input", CARRY)
        if not cons and field in ("mul_delz_src", "div_delz_dst", "mul_dt",
                                  "inflow_pre_cap", "inflow_final"):
            return MechanismSpec(LEGACY, "LEG_DZ_CAPPED_INFLOW", ZERO)
        if not cons and field == "inflow_cap_active":
            # the whole column is gated off, so the upstream fall (and hence the
            # inflow candidate) is 0 and the cap cannot bind.
            return MechanismSpec(LEGACY, "LEG_DZ_CAPPED_INFLOW", FALSE)
        if cons and field in ("mul_src", "mul_delz_src", "inflow_final"):
            # qr: rho*dz mass transport; nr: dz-only number transport.
            tag = "CONS_MASS_RHODZ_INFLOW" if species == "qr" else "CONS_NUMBER_DZ_INFLOW"
            return MechanismSpec(CONSERVATIVE, tag, ZERO)

    elif fam == "UPDATE":
        if field in ("q_before", "n_before"):
            return MechanismSpec(CAUSAL_CARRY, "CARRY/update_state_before", CARRY)
        if field in ("q_minus_out", "n_minus_out"):
            spec = ((CONSERVATIVE, "CONS_CAPPED_DEPLETION") if cons
                    else (LEGACY, "LEG_RAW_DEPLETION")) if role == "TOP" else \
                   (SHARED, "UPDATE/minus_capped_outflow")
            return MechanismSpec(spec[0], spec[1], EQUAL_TO, q_before)
        if field in ("q_plus_in_preclamp", "n_plus_in_preclamp"):
            kind, tag = ((CONSERVATIVE, f"CONS_{mn}_PLUS_INFLOW") if cons
                         else (LEGACY, "LEG_DZ_PLUS_INFLOW"))
            return MechanismSpec(kind, tag, EQUAL_TO, q_minus)
        if field == "clamp_active":
            # positivity clamp cannot fire when the state did not move
            return MechanismSpec(LEGACY, "LEG_POSITIVITY_CLAMP", FALSE)
        if field in ("q_post", "n_post"):           # the updated state itself
            kind, tag = ((CONSERVATIVE, f"CONS_{mn}_NOCLAMP_UPDATE") if cons
                         else (LEGACY, "LEG_CLAMPED_UPDATE"))
            return MechanismSpec(kind, tag, EQUAL_TO, q_before, active_nonneg=True)

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
    # Closed world: only in-schema (algorithm, role, species, op_id, field) tuples
    # have a mechanism. An out-of-schema combination (e.g. QR_OUTFLOW at a legacy
    # TOP cell that has no outflow) is a taxonomy hole, not a live-classified guess.
    try:
        return MECHANISMS[(algorithm, role, species, op_id, field)]
    except KeyError:
        raise TaxonomyHole(
            f"out-of-schema mechanism key: {(algorithm, role, species, op_id, field)}") from None


def check_universe():
    """Closed-world guard: the table covers exactly the schema universe, and a
    field outside it fails loudly (not a silent variant default)."""
    universe = set(_schema_universe())
    assert set(MECHANISMS) == universe, "mechanism table != schema universe"
    for _a, _r, _s, _o, field in universe:          # every field has a domain rule
        rule = domain_rule(field)
        assert rule in (POSITIVE_FINITE, NONNEG_FINITE, SIGNED_FINITE, BOOL_BRANCH), \
            f"{field} has no domain rule"
    try:
        _classify("legacy", "INTERIOR", "qr", "QR_FALK", "not_a_real_field")
    except TaxonomyHole:
        return
    raise AssertionError("taxonomy is fail-open: an unknown field did not raise")
