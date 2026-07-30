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

# The COMMON, cross-backend BIT-COMPARABLE fields. Two carry a projection rather
# than a raw width match: `dtcld` is f32 in Fortran but f64 in C++
# (dtcld_effective), so the normalizer proves the C++ double is an EXACT f32
# round-trip and compares the f32 semantic bits — it multiplies the surface
# precipitation directly, so leaving it out left a conversion input unchecked.
# `surface_denr` (the unsealed rain-conversion constant) is emitted by both. Both
# normalizers project onto exactly this set, so the F↔C++ identity universes match.
#: THE COMPARISON BOUNDARIES, as versioned ids rather than mode words.
#:
#: A bare "kernel" names a driver mode; it does not say which contract that mode
#: implemented. Redefining what the kernel leg records — adding `p` to the forcings,
#: recording the call arguments before the entry clamp — would leave every earlier
#: bundle still claiming "kernel" and still comparing equal, so evidence produced
#: against the old contract would be admitted against the new one. The version is
#: what makes that a refusal instead of a silent mix.
#:
#: They live HERE, with the rest of the shared vocabulary, because both backends need
#: them: the comparator reaching into the Fortran parser for two strings made the
#: import graph depend on sys.path order, which passed under the full suite and failed
#: when the comparator's own tests ran alone.
KERNEL_ENTRY = "kdm62d_kernel_entry_v1"
WRAPPER_INPUT = "kdm6_wrapper_input_v1"
ENTRY_BOUNDARIES = (KERNEL_ENTRY, WRAPPER_INPUT)

_SEMANTIC_STAGE_FIELDS = {
    # WHAT THE KERNEL WAS ACTUALLY CALLED WITH, before its entry clamp (owner P0-3).
    # outer_pre_sed is recorded AFTER that clamp (F:822-839 / runtime.cpp), so on its
    # own it cannot separate "both backends were handed the same problem" from "they
    # were handed different problems and the clamp erased the difference". Same field
    # set as outer_pre_sed deliberately: the difference between the two snapshots IS
    # the clamp, readable without a third stage.
    "kernel_call_input": ["qr", "nr", "qv", "t", "qc", "qi", "qs", "qg",
                          "nc", "ni", "nccn", "brs", "p", "rho", "delz"],
    # WHAT kdm6init BUILT (owner P0-1.1) — the `I` in y = K(x; theta, I). Cross-tree
    # comparable because fconst.h reproduces the Fortran block f32-stepwise rather than
    # computing in double and demoting; the two differ by 1 ULP, which was measured as
    # the step-45 divergence seed, so this is exactly the kind of difference that must
    # not go unobserved.
    "kernel_init_constants": ["pi", "cmc", "cmr", "cmi", "g1pmc", "g3pmc", "g4pmc", "g6pmc", "g1pmr", "g2pmr", "g4pmr", "g7pmr", "g1pdrmr", "g1pmi", "g4pmi", "g1pdimi", "pidnc", "pidnr", "pidni", "pidn0s"],
    # AFTER THE ENTRY CLAMP. With kernel_call_input before it and outer_pre_sed after,
    # the clamp becomes a MEASURED interval instead of an inference: what differs from
    # kernel_call_input is the padding, what differs from outer_pre_sed is the rest of
    # the prologue — which is where ProgB_param rewrites brs (owner P0-3/P0-6).
    "kernel_after_entry_clamp": ["qr", "nr", "qv", "t", "qc", "qi", "qs", "qg",
                                "nc", "ni", "nccn", "brs", "p", "rho", "delz"],
    "outer_pre_sed": ["qr", "nr", "qv", "t", "qc", "qi", "qs", "qg",
                      "nc", "ni", "nccn", "brs", "p", "rho", "delz"],
    # The outer-loop CAUSAL BRIDGE (owner P0-C1). Both backends emit these, so a
    # divergence in what one loop hands the next is a comparator finding rather
    # than something only a human reading two dumps side by side would notice.
    "outer_post_sed": ["qr", "nr", "qv", "t", "qc", "qi", "qs", "qg",
                       "nc", "ni", "nccn", "brs"],
    "outer_post_micro": ["qr", "nr", "qv", "t", "qc", "qi", "qs", "qg",
                         "nc", "ni", "nccn", "brs"],
    "substep_pre": ["qr", "nr", "work1_qr", "workn_qr", "delz_safe", "dend_safe",
                    "dtcld", "gate", "mstep"],
    # OPERANDS only. The per-loop rain/snow/graupel increments are C++-only (the
    # Fortran overlay does not emit them), so they are NOT comparable here; they are
    # validated inside the C++ leg by the surface replay. The comparable OUTPUT is
    # the whole-step cumulative precipitation, in its own phase below — attaching
    # Fortran's cumulative PREC to the last loop's per-loop increment compared two
    # different physical quantities (sum_L dP_L against dP_last).
    "surface": ["bottom_fall_qr", "bottom_fall_qs", "bottom_fall_qg",
                "bottom_fall_qi", "bottom_fall_total", "delz_bottom", "surface_denr"],
    "final_output": ["rain_precip_cumulative", "snow_precip_cumulative",
                     "graupel_precip_cumulative"],
}


# Canonical dtype of every common semantic stage field (both backends must agree).
#
# DERIVED, not enumerated. This map used to name each stage in turn, so adding a stage
# to _SEMANTIC_STAGE_FIELDS left it absent here and the comparator reported "unknown
# <stage> field 'qv'" — a structural error about evidence that was in fact correct.
# Every stage is all-f32 except substep_pre, which carries the f64 work terms and the
# decoded integer mstep/gate; so f32 is the rule and substep_pre is the one exception.
_MIXED_DTYPE_STAGES = {
    "substep_pre": {"work1_qr": "f64", "workn_qr": "f64",
                    "gate": "u8", "mstep": "i32"},
}
_SEMANTIC_STAGE_DTYPE = {
    (stage, f): _MIXED_DTYPE_STAGES.get(stage, {}).get(f, "f32")
    for stage, fields in _SEMANTIC_STAGE_FIELDS.items() for f in fields}


def species_rank(species: str) -> int:
    return _SPECIES_ORDER.index(species)


def semantic_stage_field_dtype(stage: str, field: str) -> str:
    """Canonical dtype of a semantic stage field; KeyError if the field is not in
    the common schema (an unknown stage field must be rejected, not defaulted)."""
    return _SEMANTIC_STAGE_DTYPE[(stage, field)]


def semantic_stage_fields(stage: str) -> list[str]:
    return list(_SEMANTIC_STAGE_FIELDS[stage])


def stage_field_ordinal(stage: str, field: str) -> int:
    """Canonical index of a field within a stage; unknown fields sort last (stably
    by name) so a malformed record never silently steals the 'first divergence'."""
    fields = _SEMANTIC_STAGE_FIELDS[stage]
    return fields.index(field) if field in fields else len(fields)


def semantic_surface_fields() -> list[str]:
    return list(_SEMANTIC_STAGE_FIELDS["surface"])
