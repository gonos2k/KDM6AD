#!/usr/bin/env python3
"""Shared, independent logical-completeness validation for G3.3-M C evidence.

The container reader (g33_dump) checks each container's structure/payload; the
INDEPENDENT question — does the evidence carry exactly the record universe the
sealed schedule demands, tiled contiguously — was previously answered only inside
the live A/B/C checker. An offline bundle reader that skips it can be handed a set
of internally-valid containers that omit whole stages (e.g. an empty outer_pre or
surface) and still pass. This module is the single source both the live gate and
the offline reader call, so they cannot drift.
"""
from __future__ import annotations

import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import g33_dump as gd          # noqa: E402
import g33_expectation as ge   # noqa: E402

_INDEX_KEYS = ("container_id", "outer_loop", "chain", "n", "first_op_seq_id",
               "last_op_seq_id", "record_count", "path")


def record_with_header_identity(record: dict, header: dict) -> dict:
    """Normalize header-scoped run identity into a logical record; a record that
    repeats one of those fields must not contradict the header."""
    identity = {name: header[name] for name in ("case_id", "pair_id", "backend")}
    for name, value in identity.items():
        if name in record and record[name] != value:
            raise gd.G33Corruption(
                f"record {name}={record[name]!r} conflicts with header {value!r}")
    return {**identity, **record}


def validate_container_index(schedule: dict, contract_containers) -> None:
    """The sealed container table must equal an INDEPENDENT run_index(schedule)."""
    generated = ge.run_index(schedule)["containers"]
    try:
        actual = [{k: c[k] for k in _INDEX_KEYS} for c in contract_containers]
    except (KeyError, TypeError) as e:
        raise gd.G33Corruption(f"contract container table malformed: {e!r}") from None
    if actual != generated:
        raise gd.G33Corruption(
            "sealed container table differs from independent run_index()")


def validate_logical_completeness(schedule: dict, parsed_containers) -> list[dict]:
    """The union of all records must be the EXACT expected multiset for the
    schedule, with global op_seq_id tiling 0..N-1. Returns the logical records."""
    logical: list[dict] = []
    for c in parsed_containers:
        header = c["header"]
        for record in c["records"]:
            logical.append(record_with_header_identity(record, header))
    diff = ge.completeness_diff(logical, schedule)
    if any(diff.values()):
        raise gd.G33Corruption(
            "logical record multiset differs: "
            f"missing={sum(diff['missing'].values())} "
            f"extra={sum(diff['extra'].values())} "
            f"duplicated={sum(diff['duplicated'].values())}")
    op_seq = sorted(int(r["op_seq_id"]) for r in logical)
    if op_seq != list(range(len(logical))):
        raise gd.G33Corruption("global op_seq does not tile 0..N-1 exactly")
    return logical


def validate_evidence(schedule: dict, contract_containers, parsed_containers) -> list[dict]:
    """Full independent completeness gate: container table + record multiset +
    op_seq tiling. Raises gd.G33Corruption on any gap. Returns logical records."""
    validate_container_index(schedule, contract_containers)
    return validate_logical_completeness(schedule, parsed_containers)


# ── gate semantics on a NORMALIZED run (backend-agnostic) ────────────────────
_ZERO_MASK = {"f32": 0x7FFFFFFF, "f64": 0x7FFFFFFFFFFFFFFF}
_EXP = {"f32": (23, 0xFF), "f64": (52, 0x7FF)}


def _is_zero(bits, dtype):          # ±0 both count as "no transport"
    return (bits & _ZERO_MASK.get(dtype, 0xFF)) == 0


def _is_finite(bits, dtype):
    if dtype not in _EXP:           # integer/flag dtypes are always finite
        return True
    shift, mask = _EXP[dtype]
    return ((bits >> shift) & mask) != mask


class GateSemanticsError(gd.G33Corruption):
    """A gate/lane invariant the arithmetic itself guarantees was violated."""


def validate_gate_semantics(run: dict, mech) -> dict:
    """Independent per-run gate contract. Returns the active mask
    {(loop, chain, n, col): bool}; raises GateSemanticsError on a violation.

    * COVERAGE (P0-2): every (loop, chain, n, col) that has ops must have exactly
      one substep_pre gate record — the active mask is never defaulted.
    * NO-OP (P0-1): where gate==0 the column transports nothing, so every ACTUAL
      quantity must hold its no-op value — falk/dq_out/dn_out are ±0, the fall
      accumulator and the state are unchanged. (Because the gate is a terminal
      multiply, `s3 * 0` is 0 only when s3 is finite, so this also catches a
      non-finite value leaking out of a dead lane.)
    * FINITE (P0-7): where gate==1 every ACTUAL quantity must be finite.
    """
    algo = run["algorithm"]
    gates: dict = {}
    for s in run["stages"]:
        if s["stage"] == "substep_pre" and s["field"] == "gate":
            key = (s["loop"], s["chain"], s["n"], s["col"])
            if key in gates:
                raise GateSemanticsError(f"duplicate gate record for {key}")
            gates[key] = int(s["bits"])

    groups: dict = {}
    for o in run["ops"]:
        lane = (o["loop"], o["chain"], o["n"], o["col"])
        groups.setdefault(lane + (o["k"], o["species"], o["op_id"]), {})[o["field"]] = o
    op_lanes = {g[:4] for g in groups}
    if op_lanes != set(gates):
        raise GateSemanticsError(
            f"gate coverage mismatch: {len(op_lanes - set(gates))} op lane(s) without a "
            f"gate, {len(set(gates) - op_lanes)} gate(s) without ops")
    if any(g not in (0, 1) for g in gates.values()):
        raise GateSemanticsError("gate bits are not 0/1")

    for key, fields in groups.items():
        lane, k, species, op_id = key[:4], key[4], key[5], key[6]
        active = gates[lane] == 1
        for field, rec in fields.items():
            spec = mech.mechanism(algo, rec["role"], species, op_id, field)
            if not spec.actual_transport:
                continue
            bits, dtype = int(rec["bits"]), rec["dtype"]
            if active:
                if not _is_finite(bits, dtype):
                    raise GateSemanticsError(
                        f"non-finite {op_id}.{field} in ACTIVE lane {lane} k={k}")
                continue
            if field in ("fall_after", "q_post", "n_post"):
                before = {"fall_after": "fall_before", "q_post": "q_before",
                          "n_post": "n_before"}[field]
                if before in fields and int(fields[before]["bits"]) != bits:
                    raise GateSemanticsError(
                        f"{op_id}.{field} changed in INACTIVE lane {lane} k={k} "
                        f"— a gated-off column transported state")
            elif not _is_zero(bits, dtype):
                raise GateSemanticsError(
                    f"{op_id}.{field} is non-zero in INACTIVE lane {lane} k={k} "
                    f"— a gated-off column produced transport")
    return {lane: (g == 1) for lane, g in gates.items()}
