#!/usr/bin/env python3
"""Project a parsed backend run into the comparator's normalized event-run form.

The four-case comparator (g33_fourcase_comparator) consumes one variant-independent
run shape per backend/variant:

  {"algorithm": "legacy"|"conservative",
   "ops":    [ {n,col,k,role,species,op_id,field,dtype,bits,op_seq_id}, ... ],
   "stages": [ {stage,n,col,k,field,dtype,bits}, ... ]}

This module is the SINGLE place that maps each backend's native record shape onto
that form, so the comparator never sees Fortran- or C++-specific structure:

  * Fortran — a `FortranRun` (g33_fortran_dump.parse_fortran_run). ops carry the
    unique `scalar_seq_id`; stages are the whitelisted outer_pre_sed / substep_pre
    / surface only. Any other stage present is a scope error, surfaced loudly.
  * C++ — placeholder until PR#65B wires the container reader + native→canonical
    field projection + inactive-lane drop.
"""
from __future__ import annotations

_COMPARATOR_STAGES = ("outer_pre_sed", "substep_pre", "surface")


class NormalizeError(ValueError):
    """The backend run cannot be projected onto the comparator form."""


def from_fortran_run(run) -> dict:
    """FortranRun -> normalized run. op order authority is scalar_seq_id (unique)."""
    ops = [{"n": o.n, "col": o.col, "k": o.k, "role": o.cell_role,
            "species": o.species, "op_id": o.op_id, "field": o.field,
            "dtype": o.dtype, "bits": o.bits, "op_seq_id": o.scalar_seq_id}
           for o in run.ops]
    stages = []
    for (stage, n, field, col, k), (dtype, bits) in run.stages.items():
        if stage not in _COMPARATOR_STAGES:
            # The overlay is scoped to these three; anything else means the parsed
            # evidence is out of the comparator's contract — fail loud, don't drop.
            raise NormalizeError(f"fortran run has non-comparator stage {stage!r}")
        stages.append({"stage": stage, "n": n, "col": col, "k": k,
                       "field": field, "dtype": dtype, "bits": bits})
    return {"algorithm": run.algorithm, "ops": ops, "stages": stages}
