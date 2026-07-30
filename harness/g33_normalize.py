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
    common semantic set (`dtcld` and `surface_denr` are both kept — see g33_schema);
    the PREC family (1=rain, 2=snow, 3=graupel) is the WHOLE-STEP accumulator, so it
    projects onto `final_output`, not onto a loop's surface stage.
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
import struct                # noqa: E402

import numpy as np           # noqa: E402
import g33_schema as schema  # noqa: E402
import g33_derived as dv      # noqa: E402

#: The bridge stages (outer_post_sed / outer_post_micro) are compared like any other
#: snapshot: both backends emit them, so a divergence in the carry between outer loops
#: is a comparator finding rather than something only a human reading two dumps could
#: notice (owner P0-C1).
_COMPARATOR_STAGES = ("kernel_call_input", "kernel_init_constants",
                      "kernel_after_entry_clamp",
                      "outer_pre_sed", "substep_pre",
                      "surface",
                      "outer_post_sed", "micro_call_aux",
                      "outer_post_micro")
# Fortran PREC is the WHOLE-STEP cumulative precipitation (rainncv accumulates over
# every outer loop), not one loop's increment.
_PREC_FIELD = {1: "rain_precip_cumulative", 2: "snow_precip_cumulative",
               3: "graupel_precip_cumulative"}
_CPP_INCREMENT = {"rain_increment": "rain_precip_cumulative",
                  "snow_increment": "snow_precip_cumulative",
                  "graupel_increment": "graupel_precip_cumulative"}

# C++-native substep_pre field -> canonical semantic field. Everything not listed
# (dend_raw, *_floor_active, mstep_native/_input_native/_exact_integer, gate_native/
# _exact_01, active_mask, qcrmin_effective) is a diagnostic the comparator does not
# bit-compare cross-backend, and is dropped.
_CPP_SUBPRE = {
    "qr": "qr", "nr": "nr", "work1_qr": "work1_qr", "workn_qr": "workn_qr",
    "delz_safe": "delz_safe", "dend_safe": "dend_safe",
    "mstep_decoded_i32": "mstep", "gate_decoded_u8": "gate",
    "dtcld_effective": "dtcld",          # f64 -> exact-f32 semantic projection
}


# The decoded mstep/gate are trustworthy only because g33_bundle_io.verify_cpp_evidence
# has already RECOMPUTED their exactness (+ floor/dtcld) from the raw native operands
# via g33_derived.check_producer_flags — this module only projects, it does not
# re-validate (owner architecture note).


class NormalizeError(ValueError):
    """The backend run cannot be projected onto the comparator form."""


def _f32_of(bits):
    return np.float32(struct.unpack(">f", struct.pack(">I", bits & 0xFFFFFFFF))[0])


def _f32_bits(value):
    return struct.unpack(">I", struct.pack(">f", np.float32(value)))[0]


def _f64_bits_to_semantic_f32(bits):
    """The C++ dtcld is stored as a double but is semantically the f32 timestep the
    Fortran carries. Project it to f32 bits, refusing anything that is not an EXACT
    round-trip — a double not representable in f32 would make the two backends'
    'same' dtcld incomparable rather than equal."""
    (value,) = struct.unpack(">d", struct.pack(">Q", bits))
    if struct.unpack(">f", struct.pack(">f", value))[0] != value:
        raise NormalizeError(f"dtcld {value!r} is not an exact f32 round-trip")
    return struct.unpack(">I", struct.pack(">f", value))[0]


def _semantic(stage, field):
    return field in schema.semantic_stage_fields(stage)


def _entry_boundary(run) -> str:
    """The boundary this run declared. NO DEFAULT (owner P0-3.4).

    SedimentationIdentity.of() stopped defaulting a missing boundary to the wrapper, but
    the normalizer still did — so the contract was enforced at one end and quietly
    supplied at the other, and a run reaching the decision path through here would have
    arrived carrying a boundary it never declared.

    A stream from before the boundary existed is a wrapper run by construction, and the
    PARSER still defaults on that basis; that is the right place for it, because the
    parser can see the protocol version and this cannot.
    """
    boundary = getattr(run, "entry_boundary", None)
    if boundary not in schema.ENTRY_BOUNDARIES:
        raise NormalizeError(
            f"the run declares no usable comparison boundary ({boundary!r}); a decision "
            f"cannot assume which function the leg entered")
    return boundary


def from_fortran_run(run) -> dict:
    """FortranRun -> normalized run, projected onto the common semantic schema."""
    ops = [{"loop": o.loop, "chain": o.chain, "n": o.n, "col": o.col, "k": o.k,
            "role": o.cell_role, "species": o.species, "op_id": o.op_id,
            "field": o.field, "dtype": o.dtype, "bits": o.bits}
           for o in run.ops]
    # The stage key carries (outer_loop, chain): real values from a protocol-v2
    # stream, derived ones from v1 (which does not transmit them and is emitted only
    # for a single main-chain outer loop).
    stages = []
    for (loop, chain, stage, n, field, col, k), (dtype, bits) in run.stages.items():
        if stage not in _COMPARATOR_STAGES:
            raise NormalizeError(f"fortran run has non-comparator stage {stage!r}")
        if not _semantic(stage, field):          # drop dtcld / surface_denr / etc.
            continue
        stages.append({"loop": loop, "chain": chain, "stage": stage,
                       "n": n, "col": col, "k": k,
                       "field": field, "dtype": dtype, "bits": bits})
    # The cumulative precipitation is a WHOLE-STEP output, so it goes in its own
    # phase rather than being attached to the last loop's surface increment.
    for (family, col), bits in run.precip.items():
        field = _PREC_FIELD.get(family)
        if field is None:
            raise NormalizeError(f"fortran run has unknown PREC family {family!r}")
        stages.append({"loop": 0, "chain": "-", "stage": "final_output",
                       "n": 0, "col": col, "k": -1, "field": field, "dtype": "f32",
                       "bits": bits})
    B = max((o["col"] for o in ops), default=0)
    K = max((o["k"] for o in ops), default=-1) + 1
    # The identity of the PROBLEM this leg solved, at two levels (owner P0-C2).
    # `local_parameter_sha256` covers ccn0/scale_h, which only the Fortran backend
    # has: it was previously dropped here so that four-way equality could succeed,
    # which silently discarded a precondition rather than checking it at the level
    # where it applies. It now travels as a BACKEND-LOCAL key, compared between the
    # two Fortran legs instead of against C++.
    problem = {"fixture_sha256": run.fixture_sha256,
               "parameter_sha256": run.parameter_sha256, "B": B, "K": K,
               "local_parameter_sha256": run.local_parameter_sha256,
               # WHAT THE KERNEL WAS INITIALISED WITH (owner P0-4). Backend-LOCAL, like
               # ccn0/scale_h: the C++ side has no kdm6init, it has its own parameter
               # builders, so this is compared between the two FORTRAN legs rather than
               # across trees. Two legs can agree on every call ARGUMENT and still solve
               # different problems, because kdm6init builds module-level derived
               # constants kdm62D then reads.
               "initialization_digest": getattr(run, "initialization_digest", None),
               # WHICH boundary. The wrapper path additionally applies kdm6's
               # height-dependent CCN profile, which the C++ port has no counterpart
               # for — so a wrapper leg and a kernel leg are answers to different
               # questions, and comparing them is a category error the same way two
               # fixtures would be (owner: kernel gate vs wrapper contract).
               "entry_boundary": _entry_boundary(run)}
    return {"algorithm": run.algorithm, "backend": "fortran", "B": B, "K": K,
            "ops": ops, "stages": stages, "problem": problem}


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
    # a verified leg is deep-frozen, so `shape` arrives as a tuple, not a list
    dtype, shape = record["dtype"], tuple(record["shape"])
    bits = dv._raw_bits(dtype, record["payload"])
    if shape == (B,):
        for b in range(B):
            yield lane_to_col[b], -1, dtype, bits[b]
    elif shape == (B, K):
        for b in range(B):
            for k in range(K):
                yield lane_to_col[b], k, dtype, bits[b * K + k]
    else:
        raise NormalizeError(f"unexpected record shape {shape} for B={B} K={K}")


def from_cpp_evidence(evidence, *, require_verdict_ready: bool = True) -> dict:
    """A verified {contract, containers} (g33_bundle_io.verify_cpp_evidence) ->
    normalized run. Whole tensors are scalarized per (col,k); substep_pre natives
    are projected to the canonical set.

    Accepts ONLY a root-attested VerifiedCppLeg (g33_bundle_io.verify_cpp_bundle) —
    a leg from verify_cpp_evidence alone (root_attested=False) is refused, so the
    normalizer cannot be fed evidence that skipped the root attestation. Columns, the
    top-first [B,K] stage orientation, and the op stream are all validated; the
    remaining C4-verdict gate is a real multi-subcycle fixture (this fixture is
    mstep=1, so bit-identical F↔C++ is the correct INCONCLUSIVE)."""
    if not getattr(evidence, "root_attested", False):
        raise NormalizeError("requires a root-attested VerifiedCppLeg "
                             "(run g33_bundle_io.verify_cpp_bundle)")
    if require_verdict_ready and not evidence.verdict_ready:
        raise NormalizeError(
            "leg is not verdict_ready: internal verification passed but the EXTERNAL "
            "anchors are missing (expected_manifest_sha256 / expected_repo_commit). "
            "A bundle that rewrites its own manifest stays self-consistent, so a C4 "
            "verdict needs an anchor held outside it. Pass require_verdict_ready=False "
            "only for local debugging.")
    contract = evidence.contract
    algo = contract["schedule"]["algorithm"] if "schedule" in contract else contract.get("algorithm")
    ops, stages = [], []
    increments: dict = {}          # (family, col) -> {outer_loop: bits}, PRESERVED
    raw_metrics: dict = {}         # stage key -> raw (pre-floor) metric bits
    lane_maps: set = set()         # every container must agree on lane -> column
    bk = set()
    for cid, c in evidence.containers.items():
        h = c["header"]
        if h.get("canonical_k_order") != "top-first":
            raise NormalizeError(f"container {cid} k-order {h.get('canonical_k_order')!r} "
                                 f"is not top-first — orientation unproven")
        B, K = h["B"], h["K"]
        bk.add((B, K))
        lane_to_col = _lane_to_col(h["column_index_map"])
        lane_maps.add(tuple(sorted(lane_to_col.items())))
        for r in c["records"]:
            stage = r["stage"]
            if stage == "op":
                col_k = list(_expand(r, B, K, lane_to_col))
                for col, k, dtype, bits in col_k:
                    ops.append({"loop": r["outer_loop"], "chain": r["chain"],
                                "n": r["n"], "col": col, "k": r["k"],
                                "role": r["cell_role"], "species": r["species"],
                                "op_id": r["op_id"], "field": r["field"],
                                "dtype": dtype, "bits": bits})
            elif stage == "substep_pre" and r["field"] in ("dend_raw", "delz_raw"):
                # Kept OUT of `stages`: the reference Fortran has no metric floor, so
                # it emits no raw/safe distinction and a comparable record here would
                # have no counterpart. The replay uses them to prove safe == raw.
                for col, k, _dtype, bits in _expand(r, B, K, lane_to_col):
                    raw_metrics[(r["outer_loop"], r["chain"],
                                 r["n"], col, k, r["field"])] = bits
            elif stage == "surface" and r["field"] in _CPP_INCREMENT:
                # C++ dumps a PER-LOOP increment. Keep every one: collapsing them to a
                # sum here would let two loops' errors cancel, or a 1-ULP error be
                # absorbed by a larger total, with nothing ever checking the loop.
                for col, _k, _dt, bits in _expand(r, B, K, lane_to_col):
                    increments.setdefault((_CPP_INCREMENT[r["field"]], col),
                                          {})[r["outer_loop"]] = bits
            elif stage in _COMPARATOR_STAGES:
                field = r["field"]
                if stage == "substep_pre":
                    field = _CPP_SUBPRE.get(field)
                    if field is None:            # C++-only diagnostic — dropped
                        continue
                if not _semantic(stage, field):
                    continue
                for col, k, dtype, bits in _expand(r, B, K, lane_to_col):
                    if field == "dtcld":
                        dtype, bits = "f32", _f64_bits_to_semantic_f32(bits)
                    stages.append({"loop": r["outer_loop"], "chain": r["chain"],
                                   "stage": stage,
                                   "n": (r["n"] if stage == "substep_pre" else 0),
                                   "col": col, "k": k, "field": field,
                                   "dtype": dtype, "bits": bits})
            # op-less non-comparator stages (outer_post_*) are simply not emitted
    if len(bk) != 1:
        raise NormalizeError(f"containers disagree on (B,K): {sorted(bk)}")
    B, K = bk.pop()
    if len(lane_maps) != 1:
        raise NormalizeError("containers disagree on the column_index_map")
    # final_output is what the run RETURNED (the FnResult the runtime accumulated),
    # not a value the harness re-derived. The replay separately requires each per-loop
    # increment to equal its own operands AND their fold to equal this, so the whole
    # output path is gated instead of just its endpoint.
    if evidence.actual_final_output is None:
        raise NormalizeError("leg carries no actual_final_output — the returned "
                             "precipitation was never captured, so the output path "
                             "cannot be verified")
    for family, per_lane in sorted(evidence.actual_final_output.items()):
        if len(per_lane) != B:
            raise NormalizeError(f"actual {family} output has {len(per_lane)} lanes, "
                                 f"expected B={B}")
        for lane, bits in enumerate(per_lane):
            stages.append({"loop": 0, "chain": "-", "stage": "final_output", "n": 0,
                           "col": lane_to_col[lane], "k": -1,
                           "field": f"{family}_precip_cumulative",
                           "dtype": "f32", "bits": bits})

    # The C++ port IS the kernel: it implements kdm62D and has no counterpart to
    # kdm6's preprocessing, so `kernel` is a structural fact about the port rather
    # than a property of this run. Declaring it is what makes the four-way boundary
    # check load-bearing — with C++ silent, a Fortran wrapper leg and a Fortran
    # kernel leg would both compare equal against it, which is the mismatch that
    # produced the nccn divergence in the first place.
    problem = dict(getattr(evidence, "problem", None) or {}, B=B, K=K,
                   entry_boundary=schema.KERNEL_ENTRY)
    # (family, loop, col) -> the increment the producer actually emitted for that loop
    per_loop = {(fld.replace("_precip_cumulative", ""), loop, col): bits
                for (fld, col), by_loop in increments.items()
                for loop, bits in by_loop.items()}
    return {"algorithm": algo, "backend": "cpp", "B": B, "K": K, "ops": ops,
            "stages": stages, "raw_metrics": raw_metrics,
            "surface_increments": per_loop, "problem": problem}
