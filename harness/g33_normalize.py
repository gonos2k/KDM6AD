#!/usr/bin/env python3
"""Project a parsed backend run into the comparator's normalized event-run form.

The four-case comparator (g33_fourcase_comparator) consumes one variant-independent
run shape per backend/variant:

  {"algorithm": "legacy"|"conservative",
   "ops":    [ {n,col,k,role,species,op_id,field,dtype,bits}, ... ],
   "stages": [ {stage,n,col,k,field,dtype,bits}, ... ]}

This module is the SINGLE place that maps each backend's native record shape onto
that form, projecting BOTH backends onto the common semantic schema
(g33_schema.semantic_stage_fields) so the F↔C++ identity universes match:

  * Fortran — a `FortranRun` (g33_fortran_dump.parse_fortran_run). Ops map directly;
    the whitelisted outer_pre_sed / substep_pre / surface stages are FILTERED to the
    semantic set (dropping the Fortran-only `dtcld`/`surface_denr`); the PREC family
    (1=rain, 2=snow, 3=graupel) projects onto the surface OUTPUT fields.
  * C++ — a verified bundle (g33_bundle_io.verify_cpp_evidence). Whole-tensor
    records are expanded to per-(col,k) scalars via the container column map; the
    C++-native substep_pre diagnostics are projected to the canonical set (the
    decoded mstep/gate, the shared state) and the rest dropped.

The comparator regenerates the canonical order from g33_schema, so no producer
sequence number is carried through.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import g33_schema as schema  # noqa: E402
import g33_derived as dv      # noqa: E402

_COMPARATOR_STAGES = ("outer_pre_sed", "substep_pre", "surface")
_PREC_FIELD = {1: "rain_increment", 2: "snow_increment", 3: "graupel_increment"}

# C++-native substep_pre field -> canonical semantic field. Everything not listed
# (dend_raw, *_floor_active, mstep_native/_input_native/_exact_integer, gate_native/
# _exact_01, active_mask, dtcld_effective, qcrmin_effective) is a diagnostic the
# comparator does not bit-compare cross-backend, and is dropped.
_CPP_SUBPRE = {
    "qr": "qr", "nr": "nr", "work1_qr": "work1_qr", "workn_qr": "workn_qr",
    "delz_safe": "delz_safe", "dend_safe": "dend_safe",
    "mstep_decoded_i32": "mstep", "gate_decoded_u8": "gate",
}
# Projecting the DECODED mstep/gate silently discards whether the native value was
# actually an exact integer / exact 0|1. A native mstep of 2.0000002 decodes to 2
# with mstep_exact_integer=0; the comparison would then look clean on a value the
# producer itself flagged inexact. These flags MUST all be 1 before we trust the
# decoded projection (owner P0-4).
_EXACT_FLAGS = ("mstep_exact_integer", "gate_exact_01")


class NormalizeError(ValueError):
    """The backend run cannot be projected onto the comparator form."""


def _semantic(stage, field):
    return field in schema.semantic_stage_fields(stage)


def from_fortran_run(run) -> dict:
    """FortranRun -> normalized run, projected onto the common semantic schema."""
    ops = [{"n": o.n, "col": o.col, "k": o.k, "role": o.cell_role,
            "species": o.species, "op_id": o.op_id, "field": o.field,
            "dtype": o.dtype, "bits": o.bits}
           for o in run.ops]
    stages = []
    for (stage, n, field, col, k), (dtype, bits) in run.stages.items():
        if stage not in _COMPARATOR_STAGES:
            raise NormalizeError(f"fortran run has non-comparator stage {stage!r}")
        if not _semantic(stage, field):          # drop dtcld / surface_denr / etc.
            continue
        stages.append({"stage": stage, "n": n, "col": col, "k": k,
                       "field": field, "dtype": dtype, "bits": bits})
    for (family, col), bits in run.precip.items():
        field = _PREC_FIELD.get(family)
        if field is None:
            raise NormalizeError(f"fortran run has unknown PREC family {family!r}")
        stages.append({"stage": "surface", "n": 0, "col": col, "k": -1,
                       "field": field, "dtype": "f32", "bits": bits})
    B = max((o["col"] for o in ops), default=0)
    K = max((o["k"] for o in ops), default=-1) + 1
    return {"algorithm": run.algorithm, "B": B, "K": K, "ops": ops, "stages": stages}


def _lane_to_col(column_index_map):
    """B_index (payload lane order) -> 1-based Fortran column. The map rows are
    [B_index, i, j, cpp_flat_index]; the Fortran column is the flat (i,j) lane, and
    for the fourcase layout that is cpp_flat_index+1 (verified against a bit-identical
    legacy F↔C++ comparison)."""
    out = {}
    for b_index, _i, _j, cpp_flat in column_index_map:
        out[b_index] = cpp_flat + 1
    return out


def _expand(record, B, K, lane_to_col):
    """Yield (col, k, dtype, bits) per element of a whole-tensor record. shape [B]
    is per-column (k=-1); shape [B,K] is per (column, level), B outer / K inner.
    The container declares canonical top-first k (k=0 top) — with the driver's
    fixture now loaded in host order (abc_driver to_host_order), the emitted
    tensors are already top-first, so the storage index IS the canonical k."""
    dtype, shape = record["dtype"], record["shape"]
    bits = dv._raw_bits(dtype, record["payload"])
    if shape == [B]:
        for b in range(B):
            yield lane_to_col[b], -1, dtype, bits[b]
    elif shape == [B, K]:
        for b in range(B):
            for k in range(K):
                yield lane_to_col[b], k, dtype, bits[b * K + k]
    else:
        raise NormalizeError(f"unexpected record shape {shape} for B={B} K={K}")


def from_cpp_evidence(evidence) -> dict:
    """A verified {contract, containers} (g33_bundle_io.verify_cpp_evidence) ->
    normalized run. Whole tensors are scalarized per (col,k); substep_pre natives
    are projected to the canonical set.

    Orientation is RESOLVED (PR#67A): with the driver loading the fixture in host
    order, the C++ tensors are genuinely top-first and legacy F↔C++ is bit-identical
    (see g33_fortran/CPP_BUNDLE_ORIENTATION.md). Columns, stage [B,K] and op streams
    all validate. Full verdict-readiness still awaits the offline evidence validator
    (independent record-completeness + root attestation, PR#67B) before adjudicate()
    is run on real bundles for a C4 verdict."""
    contract = evidence["contract"]
    algo = contract["schedule"]["algorithm"] if "schedule" in contract else contract.get("algorithm")
    ops, stages = [], []
    bk = set()
    for cid, c in evidence["containers"].items():
        h = c["header"]
        if h.get("canonical_k_order") != "top-first":
            raise NormalizeError(f"container {cid} k-order {h.get('canonical_k_order')!r} "
                                 f"is not top-first — orientation unproven")
        B, K = h["B"], h["K"]
        bk.add((B, K))
        lane_to_col = _lane_to_col(h["column_index_map"])
        for r in c["records"]:
            stage = r["stage"]
            if stage == "op":
                col_k = list(_expand(r, B, K, lane_to_col))
                for col, k, dtype, bits in col_k:
                    ops.append({"n": r["n"], "col": col, "k": r["k"],
                                "role": r["cell_role"], "species": r["species"],
                                "op_id": r["op_id"], "field": r["field"],
                                "dtype": dtype, "bits": bits})
            elif stage in _COMPARATOR_STAGES:
                field = r["field"]
                if stage == "substep_pre":
                    if r["field"] in _EXACT_FLAGS:      # P0-4: decoded value is only
                        vals = dv.unpack_values(r["dtype"], r["payload"])  # trustworthy
                        if any(int(v) != 1 for v in vals):                 # if exact
                            raise NormalizeError(
                                f"{r['field']} not all-exact in {cid}: {vals}")
                    field = _CPP_SUBPRE.get(field)
                    if field is None:            # C++-only diagnostic — dropped
                        continue
                if not _semantic(stage, field):
                    continue
                for col, k, dtype, bits in _expand(r, B, K, lane_to_col):
                    stages.append({"stage": stage, "n": (r["n"] if stage == "substep_pre" else 0),
                                   "col": col, "k": k, "field": field,
                                   "dtype": dtype, "bits": bits})
            # op-less non-comparator stages (outer_post_*) are simply not emitted
    if len(bk) != 1:
        raise NormalizeError(f"containers disagree on (B,K): {sorted(bk)}")
    B, K = bk.pop()
    return {"algorithm": algo, "B": B, "K": K, "ops": ops, "stages": stages}
