#!/usr/bin/env python3
"""Project a parsed backend run into the comparator's normalized event-run form.

The four-case comparator (g33_fourcase_comparator) consumes one variant-independent
run shape per backend/variant:

  {"algorithm": "legacy"|"conservative",
   "ops":    [ {n,col,k,role,species,op_id,field,dtype,bits,op_seq_id}, ... ],
   "stages": [ {stage,n,col,k,field,dtype,bits}, ... ]}

This module is the SINGLE place that maps each backend's native record shape onto
that form, so the comparator never sees Fortran- or C++-specific structure:

  * Fortran — a `FortranRun` (g33_fortran_dump.parse_fortran_run). Ops and the
    whitelisted outer_pre_sed / substep_pre / surface stages map directly; the PREC
    family (1=rain, 2=snow, 3=graupel) projects onto the common surface OUTPUT
    fields rain/snow/graupel_increment so the comparator closes the output
    postcondition, not just the surface operands. Any other stage present is a
    scope error, surfaced loudly.
  * C++ — placeholder until the container reader + native→canonical field
    projection + inactive-lane drop land (PR#66B).

The comparator regenerates the canonical order from g33_schema, so no producer
sequence number is carried through.
"""
from __future__ import annotations

_COMPARATOR_STAGES = ("outer_pre_sed", "substep_pre", "surface")
_PREC_FIELD = {1: "rain_increment", 2: "snow_increment", 3: "graupel_increment"}


class NormalizeError(ValueError):
    """The backend run cannot be projected onto the comparator form."""


def from_fortran_run(run) -> dict:
    """FortranRun -> normalized run. Canonical order is re-derived downstream."""
    ops = [{"n": o.n, "col": o.col, "k": o.k, "role": o.cell_role,
            "species": o.species, "op_id": o.op_id, "field": o.field,
            "dtype": o.dtype, "bits": o.bits}
           for o in run.ops]
    stages = []
    for (stage, n, field, col, k), (dtype, bits) in run.stages.items():
        if stage not in _COMPARATOR_STAGES:
            # The overlay is scoped to these three; anything else means the parsed
            # evidence is out of the comparator's contract — fail loud, don't drop.
            raise NormalizeError(f"fortran run has non-comparator stage {stage!r}")
        stages.append({"stage": stage, "n": n, "col": col, "k": k,
                       "field": field, "dtype": dtype, "bits": bits})
    for (family, col), bits in run.precip.items():
        field = _PREC_FIELD.get(family)
        if field is None:
            raise NormalizeError(f"fortran run has unknown PREC family {family!r}")
        stages.append({"stage": "surface", "n": 0, "col": col, "k": -1,
                       "field": field, "dtype": "f32", "bits": bits})
    return {"algorithm": run.algorithm, "ops": ops, "stages": stages}
