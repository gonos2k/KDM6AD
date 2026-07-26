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
from typing import NamedTuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import g33_derived as gdv      # noqa: E402
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


class LaneKey(NamedTuple):
    """The (outer_loop, chain, n, col) a gate applies to. A NAMED type rather than a
    tuple slice of the event identity: a change to the identity layout would
    silently produce a wrong lane key, and this is what selects which differences
    the verdict may ignore."""
    outer_loop: int
    chain: str
    n: int
    col: int


class GateSemanticsError(gd.G33Corruption):
    """A gate/lane invariant the arithmetic itself guarantees was violated."""


# Producer branch flags are a DEBUGGING AID, never the authority: the branch is
# recomputed here from the raw operands the producer itself dumped. `min` is a
# 4-state relation (LEFT/RIGHT/TIE/UNORDERED), so a boolean cannot express a TIE
# (both backends agree by different semantics) or a NaN (both `<` are false, which a
# boolean silently reports as "not capped").
_BRANCH_MIN = {          # flag -> (left operand, right operand); cap binds on RIGHT
    "cap_active": ("outflow_pre_cap", "source_reservoir"),
    "inflow_cap_active": ("inflow_pre_cap", "source_reservoir"),
}
# clamp_active is a SIGN test on the pre-clamp value (q_plus_in_preclamp where the
# cell has inflow, else q_minus_out at TOP).
_CLAMP_OPERANDS = ("q_plus_in_preclamp", "n_plus_in_preclamp",
                   "q_minus_out", "n_minus_out")


def _check_branch(op_id, field, rec, fields, lane, k, active):
    """Recompute a branch from its operands and hold the producer flag to it."""
    flag = int(rec["bits"])
    if flag not in (0, 1):
        raise GateSemanticsError(f"{op_id}.{field} flag {flag} is not 0/1 at {lane} k={k}")
    if field in _BRANCH_MIN:
        ln, rn = _BRANCH_MIN[field]
        left, right = fields.get(ln), fields.get(rn)
        if left is None or right is None:
            raise GateSemanticsError(
                f"{op_id}.{field} cannot be recomputed: missing {ln}/{rn}")
        branch = gdv.classify_min_bits(left["dtype"], int(left["bits"]), int(right["bits"]))
        expected = int(branch == gd.BRANCH_RIGHT_SELECTED)   # cap binds when reservoir < candidate
    else:                                                    # clamp: preclamp < 0
        src = next((fields[f] for f in _CLAMP_OPERANDS if f in fields), None)
        if src is None:
            raise GateSemanticsError(f"{op_id}.{field} cannot be recomputed: no pre-clamp operand")
        value = gdv.value_from_bits(src["dtype"], int(src["bits"]))
        branch = gd.BRANCH_UNORDERED if value != value else (
            gd.BRANCH_RIGHT_SELECTED if value < 0.0 else gd.BRANCH_LEFT_SELECTED)
        expected = int(branch == gd.BRANCH_RIGHT_SELECTED)
    if branch == gd.BRANCH_UNORDERED:
        if active:
            raise GateSemanticsError(
                f"{op_id}.{field} is UNORDERED (NaN operand) in ACTIVE lane {lane} k={k}")
        return branch          # a dead branch may carry NaN; recorded, not judged
    if flag != expected:
        raise GateSemanticsError(
            f"{op_id}.{field}={flag} contradicts its own operands (branch={branch}) "
            f"at {lane} k={k} — the producer flag is not authoritative")
    return branch


_MSTEP_RANGE = (1, 100)          # the algorithmic sub-cycle contract


def _signed_i32(bits):
    return bits - (1 << 32) if bits >= (1 << 31) else bits


def _sign_ok(bits, dtype):
    """Non-negative: the sign bit is clear, or the value is an exact -0."""
    if dtype not in _EXP:                       # integer/flag dtypes carry no sign bit
        return True
    sign_bit = 63 if dtype == "f64" else 31
    return _is_zero(bits, dtype) or not (bits >> sign_bit) & 1


def validate_gate_semantics(run: dict, mech) -> dict:
    """Independent per-run gate contract. Returns the active mask
    {LaneKey: bool}; raises GateSemanticsError on a violation.

    * COVERAGE: every (loop, chain, n, col) that has ops must have exactly one
      substep_pre gate AND one mstep record — the mask is never defaulted.
    * GATE LAW: gate == (n <= mstep) for that column. Without this a run could
      declare a well-formed 0/1 gate that its own mstep contradicts, and the
      comparator would then discard that lane's pre-gate differences as "dead".
    * NO-OP: where gate==0 each rung must satisfy its MechanismSpec.inactive
      relation (ZERO / EQUAL_TO its input / FALSE), so a gated-off column that
      transported anything — even transiently, with the final state coincidentally
      restored — is caught. (The gate is a multiply, so `s3 * 0` is 0 only for
      finite s3; ZERO therefore also catches non-finite leakage.)
    * DOMAIN: where gate==1 every actual transport must be finite and non-negative.
    """
    algo = run["algorithm"]
    gates, msteps = {}, {}
    for s in run["stages"]:
        if s["stage"] != "substep_pre":
            continue
        key = LaneKey(s["loop"], s["chain"], s["n"], s["col"])
        if s["field"] == "gate":
            if key in gates:
                raise GateSemanticsError(f"duplicate gate record for {key}")
            gates[key] = int(s["bits"])
        elif s["field"] == "mstep":
            if key in msteps:
                raise GateSemanticsError(f"duplicate mstep record for {key}")
            # raw i32 BITS, so 0xFFFFFFFF is -1 and must not read as 4294967295
            msteps[key] = _signed_i32(int(s["bits"]))

    groups: dict = {}
    for o in run["ops"]:
        lane = LaneKey(o["loop"], o["chain"], o["n"], o["col"])
        groups.setdefault(tuple(lane) + (o["k"], o["species"], o["op_id"]), {})[o["field"]] = o
    # COVERAGE. The two producers have DIFFERENT op topologies and both are valid:
    # Fortran emits op records only for ACTIVE columns, while C++ writes a whole [B]
    # payload per substep and therefore also carries inactive lanes. So the rule is
    # not "op lanes == gate lanes" but:
    #   * every op lane must have a gate (nothing unexplained), and
    #   * every ACTIVE lane must have ops (an active column must transport).
    # A gate-only INACTIVE lane is the legitimate Fortran shape; an inactive lane
    # that does carry ops is the legitimate C++ shape, checked by the no-op rules.
    op_lanes = {LaneKey(*g[:4]) for g in groups}
    if set(gates) != set(msteps):
        raise GateSemanticsError("gate and mstep lane coverage differ")
    orphan = op_lanes - set(gates)
    if orphan:
        raise GateSemanticsError(f"{len(orphan)} op lane(s) without a gate record")
    for key, g in gates.items():
        if g not in (0, 1):
            raise GateSemanticsError(f"gate bits {g} are not 0/1 at {key}")
        n, mstep = key.n, msteps[key]
        if not (_MSTEP_RANGE[0] <= mstep <= _MSTEP_RANGE[1]):
            raise GateSemanticsError(f"mstep {mstep} outside {_MSTEP_RANGE} at {key}")
        if g != int(n <= mstep):
            raise GateSemanticsError(
                f"gate law violated at {key}: gate={g} but n={n}, mstep={mstep}")
        if g == 1 and key not in op_lanes:
            raise GateSemanticsError(f"ACTIVE lane {key} carries no op records")

    branches: dict = {}
    for key, fields in groups.items():
        lane, k, species = LaneKey(*key[:4]), key[4], key[5]
        op_id = key[6]
        active = gates[lane] == 1
        for field, rec in fields.items():
            spec = mech.mechanism(algo, rec["role"], species, op_id, field)
            bits, dtype = int(rec["bits"]), rec["dtype"]
            rule = mech.domain_rule(field)
            if rule == mech.BOOL_BRANCH:
                branches[(key, field)] = _check_branch(
                    op_id, field, rec, fields, lane, k, active)
                continue
            if active:
                if not _is_finite(bits, dtype):
                    raise GateSemanticsError(
                        f"non-finite {op_id}.{field} in ACTIVE lane {lane} k={k}")
                if rule in (mech.NONNEG_FINITE, mech.POSITIVE_FINITE) and not _sign_ok(bits, dtype):
                    raise GateSemanticsError(
                        f"negative {op_id}.{field} in ACTIVE lane {lane} k={k} "
                        f"— outside sedimentation's valid domain")
                if rule == mech.POSITIVE_FINITE and _is_zero(bits, dtype):
                    raise GateSemanticsError(
                        f"{op_id}.{field} is zero in ACTIVE lane {lane} k={k} "
                        f"— a grid metric must be strictly positive")
                continue
            if spec.inactive == mech.ZERO:
                if not _is_zero(bits, dtype):
                    raise GateSemanticsError(
                        f"{op_id}.{field} is non-zero in INACTIVE lane {lane} k={k} "
                        f"— a gated-off column produced transport")
            elif spec.inactive == mech.EQUAL_TO:
                ref = fields.get(spec.inactive_ref)
                if ref is None:      # fail-closed: the relation cannot be checked
                    raise GateSemanticsError(
                        f"{op_id}.{field} needs reference {spec.inactive_ref} to "
                        f"prove the INACTIVE lane {lane} k={k} moved nothing")
                if int(ref["bits"]) != bits:
                    raise GateSemanticsError(
                        f"{op_id}.{field} != {spec.inactive_ref} in INACTIVE lane "
                        f"{lane} k={k} — a gated-off column moved state")
            elif spec.inactive == mech.FALSE:
                if bits != 0:
                    raise GateSemanticsError(
                        f"{op_id}.{field} fired in INACTIVE lane {lane} k={k}")
    # Surface and whole-step outputs get the same numeric domain as the ladder. Left
    # unchecked, a negative or non-finite C++ surface value would surface as an
    # out-of-scope or external-input DIVERGENCE — a scientific verdict on corrupt
    # evidence, when the honest answer is INVALID_EVIDENCE.
    for s in run["stages"]:
        if s["stage"] not in ("surface", "final_output"):
            continue
        field, bits, dtype = s["field"], int(s["bits"]), s["dtype"]
        rule = mech.surface_domain_rule(field)
        where = f"{s['stage']}.{field} loop{s['loop']} col{s['col']}"
        if not _is_finite(bits, dtype):
            raise GateSemanticsError(f"non-finite {where}")
        if not _sign_ok(bits, dtype):
            raise GateSemanticsError(
                f"negative {where} — outside the precipitation domain")
        if rule == mech.POSITIVE_FINITE and _is_zero(bits, dtype):
            raise GateSemanticsError(f"{where} is zero — must be strictly positive")
    return {lane: (g == 1) for lane, g in gates.items()}
