#!/usr/bin/env python3
"""Explicit mechanism taxonomy for the G3.3-M op ladder (owner P0-5).

`fields(conservative) - fields(legacy)` on (op_id, field) is WRONG: it drops
role/species, treats a conservative-TOP `QR_OUTFLOW` (min-cap, a SHARED operation
legacy simply does not run at TOP) as conservative-only, and can never flag the
no-clamp `q_post` because legacy has that field name too — with a DIFFERENT
expression. So classification is by the ACTUAL operation, tagged explicitly.

At a FIRST cross-tree divergence the inputs are identical (upstream matched by
definition), so the divergence is in that rung's own arithmetic — and the rung's
mechanism tag decides attribution:

  SHARED_*        — same operation in both variants (falk chain, min-cap outflow,
                    the pre-clamp subtract, the surface species sum). A divergence
                    here is a mechanism common to both variants → PASS candidate.
  CONSERVATIVE_*  — the conservative-only arithmetic (ρΔz inflow, actual-rate fall
                    accumulator, no-clamp update). A first divergence here in the
                    conservative pair → FAIL.
  LEGACY_*        — legacy-only arithmetic (Δz-capped inflow, positivity clamp).

FAIL requires a CONSERVATIVE_* tag — NOT merely "present only in conservative":
a shared operation that legacy happens not to perform at some role is neither a
shared-rung PASS (legacy has no counterpart) nor conservative-only arithmetic, so
it is INCONCLUSIVE, decided by the comparator, not here.
"""

SHARED_FALK = "SHARED_FALK"
SHARED_OUTFLOW_CAP = "SHARED_OUTFLOW_CAP"
SHARED_UPDATE_SUBTRACT = "SHARED_UPDATE_SUBTRACT"
SHARED_SURFACE_SUM = "SHARED_SURFACE_SUM"
LEGACY_RAW_FALLACC = "LEGACY_RAW_FALLACC"
LEGACY_DZ_CAPPED_INFLOW = "LEGACY_DZ_CAPPED_INFLOW"
LEGACY_CLAMPED_UPDATE = "LEGACY_CLAMPED_UPDATE"
LEGACY_POSITIVITY_CLAMP = "LEGACY_POSITIVITY_CLAMP"
CONSERVATIVE_RATE_FALLACC = "CONSERVATIVE_RATE_FALLACC"
CONSERVATIVE_RHODZ_INFLOW = "CONSERVATIVE_RHODZ_INFLOW"
CONSERVATIVE_NO_CLAMP_UPDATE = "CONSERVATIVE_NO_CLAMP_UPDATE"

# op fields that are the shared pre-clamp subtraction (q_before - dq_out); the
# rest of UPDATE (q_plus_in_preclamp / q_post) carries the variant's inflow + clamp.
_SHARED_UPDATE_FIELDS = {"q_before", "n_before", "q_minus_out", "n_minus_out"}
_CLAMP_FIELDS = {"clamp_active"}


def mechanism(algorithm, op_id, field):
    """The mechanism tag of one rung. `algorithm` in {legacy, conservative}."""
    cons = algorithm == "conservative"
    family = op_id.split("_", 1)[1]        # FALK | OUTFLOW | FALLACC | INFLOW | UPDATE
    if family == "FALK":
        return SHARED_FALK
    if family == "OUTFLOW":
        return SHARED_OUTFLOW_CAP
    if family == "FALLACC":
        return CONSERVATIVE_RATE_FALLACC if cons else LEGACY_RAW_FALLACC
    if family == "INFLOW":
        return CONSERVATIVE_RHODZ_INFLOW if cons else LEGACY_DZ_CAPPED_INFLOW
    if family == "UPDATE":
        if field in _CLAMP_FIELDS:
            return LEGACY_POSITIVITY_CLAMP
        if field in _SHARED_UPDATE_FIELDS:
            return SHARED_UPDATE_SUBTRACT
        return CONSERVATIVE_NO_CLAMP_UPDATE if cons else LEGACY_CLAMPED_UPDATE
    raise KeyError(f"no mechanism for op family {family!r} ({op_id}.{field})")


def surface_mechanism(field):
    return SHARED_SURFACE_SUM


def is_shared(tag):
    return tag.startswith("SHARED_")


def is_conservative_only(tag):
    return tag.startswith("CONSERVATIVE_")


def is_legacy_only(tag):
    return tag.startswith("LEGACY_")
