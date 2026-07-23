#!/usr/bin/env python3
"""PUBLIC schema facade for the G3.3-M op-provenance vocabulary.

The authoritative definitions live in `g33_expectation` (the independent
expectation-manifest generator). Several of its functions are spelled with a
leading underscore because they were only ever called from inside that module.
The Fortran overlay generator, the strict evidence parser, and the four-case
comparator ALL need those same definitions — reaching into the private names
from three consumers is how a schema and its producers drift apart silently.

This module is the STABLE public surface: the op templates, the per-op field
lists (name + dtype), the canonical cell-role, and the canonical ORDINALS that
put every record into the single total order first-divergence depends on. It
adds nothing new — it only re-exports and names the ordering the manifest
already assigns, so consumers never have to guess it.
"""
from __future__ import annotations

import g33_expectation as _ge

# Re-exports whose names are already public + stable in g33_expectation.
expected_records = _ge.expected_records
record_key = _ge.record_key
expected_key_counts = _ge.expected_key_counts
completeness_diff = _ge.completeness_diff
run_index = _ge.run_index
write_descriptors = _ge.write_descriptors


def cell_role(k: int, K: int) -> str:
    """Canonical top-first role: k=0 TOP, k=K-1 BOTTOM, else INTERIOR."""
    return _ge._cell_role(k, K)


def ops_for_species(algorithm: str, role: str, species: str) -> list[str]:
    """Ordered op_ids for one (algorithm, role, species) — canonical op order."""
    return _ge._ops_for_species(algorithm, role, species)


def op_fields(algorithm: str, role: str, op_id: str) -> list[tuple[str, str]]:
    """Ordered (field, dtype) rungs of one op — canonical field order."""
    return _ge._op_fields(algorithm, role, op_id)


def op_ordinal(algorithm: str, role: str, species: str, op_id: str) -> int:
    """Index of op_id within its species' op sequence (0-based)."""
    return ops_for_species(algorithm, role, species).index(op_id)


def field_ordinal(algorithm: str, role: str, op_id: str, field: str) -> int:
    """Index of `field` within its op's field sequence (0-based)."""
    return [f for f, _ in op_fields(algorithm, role, op_id)].index(field)


def field_dtype(algorithm: str, role: str, op_id: str, field: str) -> str:
    for f, dt in op_fields(algorithm, role, op_id):
        if f == field:
            return dt
    raise KeyError(f"{op_id}.{field} not in schema for {algorithm}/{role}")


# ── SINGLE ORDERING AUTHORITY ────────────────────────────────────────────────
# The comparator, the Fortran parser and the C++ normalizer must all take the
# canonical total order from HERE — duplicating it (as an ad-hoc _SPECIES_RANK or
# _SURFACE_ORDER in the comparator) is exactly how the surface-output field set
# drifted. Species order is g33_expectation's chain schedule (main then ice); the
# stage/surface orders are the COMMON semantic projection target both backends map
# onto (Fortran canonical names / C++ native fields projected to these).
_SPECIES_ORDER = [s for chain in ("main", "ice") for s in _ge._CHAIN_SPECIES[chain]]

# The COMMON, cross-backend BIT-COMPARABLE fields only. Two exclusions are
# deliberate: `dtcld` is f32 in Fortran but f64 in C++ (dtcld_effective) — a raw
# bit-compare across widths is meaningless, and any dtcld effect on the ladder is
# caught by the ops themselves; `surface_denr` is a Fortran-only external constant
# with no C++ counterpart. Both backends' normalizers project onto exactly this
# set, so the F↔C++ identity universes match.
_SEMANTIC_STAGE_FIELDS = {
    "outer_pre_sed": ["qr", "nr", "qv", "t", "rho", "delz"],
    "substep_pre": ["qr", "nr", "work1_qr", "workn_qr", "delz_safe", "dend_safe",
                    "gate", "mstep"],
    "surface": ["bottom_fall_qr", "bottom_fall_qs", "bottom_fall_qg",
                "bottom_fall_qi", "bottom_fall_total", "delz_bottom",
                "rain_increment", "snow_increment", "graupel_increment"],
}


def species_rank(species: str) -> int:
    return _SPECIES_ORDER.index(species)


def semantic_stage_fields(stage: str) -> list[str]:
    return list(_SEMANTIC_STAGE_FIELDS[stage])


def stage_field_ordinal(stage: str, field: str) -> int:
    """Canonical index of a field within a stage; unknown fields sort last (stably
    by name) so a malformed record never silently steals the 'first divergence'."""
    fields = _SEMANTIC_STAGE_FIELDS[stage]
    return fields.index(field) if field in fields else len(fields)


def semantic_surface_fields() -> list[str]:
    return list(_SEMANTIC_STAGE_FIELDS["surface"])
