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
