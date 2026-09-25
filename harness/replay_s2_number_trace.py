"""Replay the source-ordered, fixed-column mp37 rain-number trace for system gate S2.

The replayer validates recorded Fortran REAL(4)/REAL(8) bits and applied
transport operands. It reports operator and conditional number measures without
choosing the stored QNR physical basis.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from collections import defaultdict
from pathlib import Path
from typing import Any


SCHEMA = "s2-native-number-v1"
SOURCE_SCHEMA = "s2-mp37-number-capture-source-v1"
CELL = {"host_j": 153, "host_i": 144}
SOURCE_SHA256 = "fc0a72d33a5e61803fea56eb9118018039c6da8b5775813032b4861a2bd66eb5"
INPUT_SHA256 = "5a9ae8da992028dbf3a2a7652eb61532c1efab2acea7ea0e393e4cac8fd4c970"
EXPECTED_CAPTURE_RECORDS = 1257
EXPECTED_STEPS = (1, 2)
EXPECTED_TRANSPORT_STEPS = (1, 2)
EXPECTED_INTERNAL_FACE_LEVELS = tuple(range(1, 39))
EXPECTED_TOP_LEVEL = 39
EXPECTED_SOURCE_EVENT_LEVELS = {
    "NR_SNOW_MELT_PRE": {1: (13, 14, 15), 2: (14, 15)},
    "NR_SNOW_MELT_POST": {1: (13, 14, 15), 2: (14, 15)},
    "NR_GRAUPEL_MELT_PRE": {2: (15,)},
    "NR_GRAUPEL_MELT_POST": {2: (15,)},
    "NR_FREEZE_PRE": {2: (16,)},
    "NR_FREEZE_POST": {2: (16,)},
}
FULL_LEVELS = tuple(range(1, 40))
WARM_LEVELS = tuple(range(16, 40))
COLD_LEVELS = tuple(range(1, 16))
EXPECTED_EVENT_CENSUS = {
    # tag: (outer loop, substep, {step: expected levels}); pinned from the
    # retained input's two-call instrumentation schedule, independently of the
    # values subsequently replayed from the capture.
    "DSD_FINAL_GATE": (1, 0, {1: FULL_LEVELS, 2: FULL_LEVELS}),
    "DSD_FINAL_POST": (1, 0, {1: (1, 2, 3, 5, 12, 13, 15),
                              2: (1, 2, 3, 4, 5, 11, 12, 13, 14, 15)}),
    "DSD_FINAL_RAW": (1, 0, {1: (13, 14, 15), 2: (12, 13, 14, 15, 16)}),
    "DSD_POSTFREEZE_GATE": (1, 0, {1: FULL_LEVELS, 2: FULL_LEVELS}),
    "DSD_POSTFREEZE_POST": (1, 0, {2: tuple(range(1, 17))}),
    "DSD_POSTFREEZE_RAW": (1, 0, {1: (13, 14, 15), 2: (12, 13, 14, 15, 16)}),
    "DSD_PRE_GATE": (1, 0, {1: FULL_LEVELS, 2: FULL_LEVELS}),
    "DSD_PRE_POST": (1, 0, {2: tuple(range(1, 17))}),
    "DSD_PRE_RAW": (1, 0, {1: (13, 14, 15), 2: (12, 13, 14, 15, 16)}),
    "HOST_ENTRY": (0, 0, {1: FULL_LEVELS, 2: FULL_LEVELS}),
    "HOST_RETURN": (0, 0, {1: FULL_LEVELS, 2: FULL_LEVELS}),
    "KERNEL_ENTRY": (0, 0, {1: FULL_LEVELS, 2: FULL_LEVELS}),
    "KERNEL_RETURN": (0, 0, {1: FULL_LEVELS, 2: FULL_LEVELS}),
    "NRAUT_GATE": (1, 0, {1: FULL_LEVELS, 2: FULL_LEVELS}),
    "NR_FACE_POST": (1, 1, {1: tuple(range(1, 39)), 2: tuple(range(1, 39))}),
    "NR_FACE_PRE": (1, 1, {1: tuple(range(1, 39)), 2: tuple(range(1, 39))}),
    "NR_FREEZE_POST": (1, 0, {2: (16,)}),
    "NR_FREEZE_PRE": (1, 0, {2: (16,)}),
    "NR_GRAUPEL_MELT_POST": (1, 0, {2: (15,)}),
    "NR_GRAUPEL_MELT_PRE": (1, 0, {2: (15,)}),
    "NR_LIMIT_COLD_POST": (1, 0, {1: COLD_LEVELS, 2: COLD_LEVELS}),
    "NR_LIMIT_COLD_PRE": (1, 0, {1: COLD_LEVELS, 2: COLD_LEVELS}),
    "NR_LIMIT_POST": (1, 0, {1: WARM_LEVELS, 2: WARM_LEVELS}),
    "NR_LIMIT_PRE": (1, 0, {1: WARM_LEVELS, 2: WARM_LEVELS}),
    "NR_MAX_GATE": (1, 0, {1: FULL_LEVELS, 2: FULL_LEVELS}),
    "NR_SNOW_MELT_POST": (1, 0, {1: (13, 14, 15), 2: (14, 15)}),
    "NR_SNOW_MELT_PRE": (1, 0, {1: (13, 14, 15), 2: (14, 15)}),
    "NR_TOP_POST": (1, 1, {1: (39,), 2: (39,)}),
    "NR_TOP_PRE": (1, 1, {1: (39,), 2: (39,)}),
    "NR_UPDATE_COLD_POST": (1, 0, {1: COLD_LEVELS, 2: COLD_LEVELS}),
    "NR_UPDATE_COLD_PRE": (1, 0, {1: COLD_LEVELS, 2: COLD_LEVELS}),
    "NR_UPDATE_WARM_POST": (1, 0, {1: WARM_LEVELS, 2: WARM_LEVELS}),
    "NR_UPDATE_WARM_PRE": (1, 0, {1: WARM_LEVELS, 2: WARM_LEVELS}),
}


class TraceError(ValueError):
    """The capture or evidence manifest does not prove the declared S2 path."""


def f32(value: float) -> float:
    return struct.unpack(">f", struct.pack(">f", float(value)))[0]


def f32_add(a: float, b: float) -> float:
    return f32(f32(a) + f32(b))


def f32_sub(a: float, b: float) -> float:
    return f32(f32(a) - f32(b))


def f32_mul(a: float, b: float) -> float:
    return f32(f32(a) * f32(b))


def f32_div(a: float, b: float) -> float:
    return f32(f32(a) / f32(b))


def _hex_f32(token: str) -> float:
    if len(token) != 8:
        raise TraceError(f"REAL(4) bit token must have 8 hex digits: {token!r}")
    value = struct.unpack(">f", int(token, 16).to_bytes(4, "big"))[0]
    if not math.isfinite(value):
        raise TraceError(f"non-finite REAL(4) event value: {token}")
    return value


def _hex_f64(token: str) -> float:
    if len(token) != 16:
        raise TraceError(f"REAL(8) bit token must have 16 hex digits: {token!r}")
    value = struct.unpack(">d", int(token, 16).to_bytes(8, "big"))[0]
    if not math.isfinite(value):
        raise TraceError(f"non-finite REAL(8) event value: {token}")
    return value


def parse_capture(text: str, tags: dict[str, dict[str, list[str]]]) -> list[dict[str, Any]]:
    """Decode fixed-width hex stdout records emitted by instrument_s2_native_number.py."""
    rows: list[dict[str, Any]] = []
    unique: set[tuple[Any, ...]] = set()
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.startswith("S2NR "):
            continue
        parts = line.split()
        if len(parts) < 8 or parts[0] != "S2NR":
            raise TraceError(f"malformed S2 record at line {line_number}")
        tag = parts[1]
        schema = tags.get(tag)
        if schema is None:
            raise TraceError(f"undeclared event tag {tag!r} at line {line_number}")
        try:
            step, host_j, host_i, outer_loop, substep, level = map(int, parts[2:8])
        except ValueError as exc:
            raise TraceError(f"bad coordinates at S2 line {line_number}") from exc
        if (host_j, host_i) != (CELL["host_j"], CELL["host_i"]):
            raise TraceError(f"event escaped the fixed cell at line {line_number}")
        if step not in EXPECTED_STEPS or level < 1 or outer_loop < 0 or substep < 0:
            raise TraceError(f"invalid step/loop/level at S2 line {line_number}")
        flags = list(schema.get("flags", []))
        real32 = list(schema.get("real32", []))
        integer32 = list(schema.get("integer32", []))
        real64 = list(schema.get("real64", []))
        order = list(schema.get("value_order", []))
        if not order:
            order = ([{"kind": "f32", "expr": x} for x in real32]
                     + [{"kind": "f64", "expr": x} for x in real64])
        expected = 8 + len(flags) + len(order)
        if len(parts) != expected:
            raise TraceError(
                f"{tag} line {line_number}: expected {expected} tokens, got {len(parts)}")
        cursor = 8
        flag_values = [int(x) for x in parts[cursor:cursor + len(flags)]]
        if any(x not in (0, 1) for x in flag_values):
            raise TraceError(f"non-boolean branch flag in {tag} line {line_number}")
        cursor += len(flags)
        f32_values: dict[str, float] = {}
        f32_bits: dict[str, str] = {}
        f64_values: dict[str, float] = {}
        f64_bits: dict[str, str] = {}
        int32_values: dict[str, int] = {}
        int32_bits: dict[str, str] = {}
        for item in order:
            token = parts[cursor].upper()
            cursor += 1
            name = item["expr"]
            kind = item["kind"]
            if kind == "f32":
                f32_values[name] = _hex_f32(token)
                f32_bits[name] = token
            elif kind == "i32":
                if len(token) != 8:
                    raise TraceError(f"INTEGER(4) bit token must have 8 hex digits: {token!r}")
                raw = int(token, 16)
                int32_values[name] = raw if raw < (1 << 31) else raw - (1 << 32)
                int32_bits[name] = token
            elif kind == "f64":
                f64_values[name] = _hex_f64(token)
                f64_bits[name] = token
            else:
                raise TraceError(f"unsupported S2 field kind {kind!r}")
        if set(f32_values) != set(real32) or set(f64_values) != set(real64) \
                or set(int32_values) != set(integer32):
            raise TraceError(f"{tag} field order/types disagree with its manifest")
        key = (tag, step, host_j, host_i, outer_loop, substep, level)
        if key in unique:
            raise TraceError(f"duplicate event record {key}")
        unique.add(key)
        rows.append({
            "key": key,
            "tag": tag,
            "step": step,
            "host_j": host_j,
            "host_i": host_i,
            "outer_loop": outer_loop,
            "substep": substep,
            "level": level,
            "flags": dict(zip(flags, flag_values)),
            "f32": f32_values,
            "f32_bits": f32_bits,
            "f64": f64_values,
            "f64_bits": f64_bits,
            "i32": int32_values,
            "i32_bits": int32_bits,
        })
    if not rows:
        raise TraceError("capture has no S2NR records")
    return rows


def _by_tag(rows: list[dict[str, Any]], tag: str) -> dict[tuple[int, int], dict[str, Any]]:
    out: dict[tuple[int, int], dict[str, Any]] = {}
    for row in rows:
        if row["tag"] != tag:
            continue
        key = (row["step"], row["level"])
        if key in out:
            raise TraceError(f"multiple {tag} records at step/level {key}; narrow key lost loop")
        out[key] = row
    return out


def _verify_event_census(rows: list[dict[str, Any]]) -> None:
    """Require the code-pinned tag/step/level universe for this capture."""
    actual_tags = {row["tag"] for row in rows}
    expected_tags = set(EXPECTED_EVENT_CENSUS)
    if actual_tags != expected_tags:
        raise TraceError(
            f"capture tag census differs; missing={sorted(expected_tags - actual_tags)}, "
            f"extra={sorted(actual_tags - expected_tags)}")
    for tag, (outer, substep, schedule) in EXPECTED_EVENT_CENSUS.items():
        expected = {
            (step, CELL["host_j"], CELL["host_i"], outer, substep, level)
            for step, levels in schedule.items() for level in levels
        }
        actual = {row["key"][1:] for row in rows if row["tag"] == tag}
        if actual != expected:
            raise TraceError(
                f"{tag} event-key census differs; missing={sorted(expected - actual)}, "
                f"extra={sorted(actual - expected)}")


def _verify_copy_pair(rows: list[dict[str, Any]], left: str, right: str,
                      left_field: str, right_field: str) -> int:
    a = _by_tag(rows, left)
    b = _by_tag(rows, right)
    if not a or set(a) != set(b):
        raise TraceError(f"{left}/{right} event-key sets differ")
    for key in a:
        if a[key]["f32_bits"][left_field] != b[key]["f32_bits"][right_field]:
            raise TraceError(f"{left}->{right} bit mismatch at step/level {key}")
    return len(a)


def _verify_boundary_chain(rows: list[dict[str, Any]]) -> dict[str, int]:
    host_in = {row["key"][1:]: row for row in rows if row["tag"] == "HOST_ENTRY"}
    local_in = {row["key"][1:]: row for row in rows if row["tag"] == "KERNEL_ENTRY"}
    local_out = {row["key"][1:]: row for row in rows if row["tag"] == "KERNEL_RETURN"}
    host_out = {row["key"][1:]: row for row in rows if row["tag"] == "HOST_RETURN"}
    for name, a, b in (("host->kernel", host_in, local_in),
                       ("kernel->host", local_out, host_out)):
        if not a or set(a) != set(b):
            raise TraceError(f"{name} event-key sets are empty or differ")
    entry_map = (("qr(i,k,j)", "qrs(i,k,1)"),
                 ("qc(i,k,j)", "qci(i,k,1)"),
                 ("q(i,k,j)", "q(i,k)"),
                 ("den(i,k,j)", "den(i,k)"),
                 ("delz(i,k,j)", "delz(i,k)"))
    return_map = (("qr(i,k,j)", "qrs(i,k,1)"),
                  ("qc(i,k,j)", "qci(i,k,1)"),
                  ("q(i,k,j)", "q(i,k,j)"),
                  ("den(i,k,j)", "den(i,k,j)"),
                  ("delz(i,k,j)", "delz(i,k,j)"))
    for key, h in host_in.items():
        k = local_in[key]
        local_nr = max(h["f32"]["nr(i,k,j)"], 0.0)
        if struct.pack(">f", f32(local_nr)).hex().upper() != k["f32_bits"]["nrs(i,k,1)"]:
            raise TraceError(f"host nr entry normalization differs at {key}")
        for host_field, local_field in entry_map:
            if h["f32_bits"][host_field] != k["f32_bits"][local_field]:
                raise TraceError(f"host/kernel entry {host_field} differs at {key}")
    for key, k in local_out.items():
        h = host_out[key]
        if k["f32_bits"]["nrs(i,k,1)"] != h["f32_bits"]["nr(i,k,j)"]:
            raise TraceError(f"kernel nr return copy differs at {key}")
        for host_field, local_field in return_map:
            if h["f32_bits"][host_field] != k["f32_bits"][local_field]:
                raise TraceError(f"kernel/host return {host_field} differs at {key}")
    steps = sorted({key[0] for key in host_in})
    if len(steps) < 2:
        raise TraceError("the 40s S2 trace needs two KDM6 entry/return calls")
    for step in steps:
        levels = sorted(key[5] for key in host_in if key[0] == step)
        if levels != list(range(1, 40)):
            raise TraceError(f"host entry step {step} does not cover all 39 levels")
    return {"steps": len(steps), "host_entry_layers": len(host_in),
            "host_return_layers": len(host_out)}


def _verify_history_returns(rows: list[dict[str, Any]],
                            frames: list[dict[str, Any]]) -> int:
    by_time = {row.get("time_seconds"): row for row in frames}
    if set(by_time) != {20, 40}:
        raise TraceError("selected QNR history return must cover 20 s and 40 s")
    host_return = {(row["step"], row["level"]): row for row in rows
                   if row["tag"] == "HOST_RETURN"}
    for step, time_seconds in ((1, 20), (2, 40)):
        row = host_return.get((step, 13))
        if row is None:
            raise TraceError(f"missing host-return QNR at step {step}, K13")
        expected = row["f32_bits"]["nr(i,k,j)"]
        observed = by_time[time_seconds].get("qnr_f32_bits")
        if observed != expected:
            raise TraceError(f"mp37 host-return QNR differs from saved history at {time_seconds}s")
    return 2


def _verify_budget_updates(rows: list[dict[str, Any]]) -> dict[str, int]:
    checked: dict[str, int] = {}
    specs = (
        ("warm", "NR_UPDATE_WARM_PRE", "NR_UPDATE_WARM_POST",
         ("nraut(i,k)", "nrcol(i,k)", "niacr(i,k)",
          "nraci(i,k)", "nsacr(i,k)", "ngacr(i,k)"), (1, -1, -1, -1, -1, -1)),
        ("cold", "NR_UPDATE_COLD_PRE", "NR_UPDATE_COLD_POST",
         ("nraut(i,k)", "nrcol(i,k)", "nseml(i,k)", "ngeml(i,k)"),
         (1, -1, 1, 1)),
    )
    for label, pre_tag, post_tag, fields, signs in specs:
        pre = {row["key"][1:]: row for row in rows if row["tag"] == pre_tag}
        post = {row["key"][1:]: row for row in rows if row["tag"] == post_tag}
        if set(pre) != set(post):
            raise TraceError(f"{pre_tag}/{post_tag} event-key sets differ")
        for key, p in pre.items():
            q = post[key]
            inc = p["f32"][fields[0]]
            for field, sign in zip(fields[1:], signs[1:]):
                inc = f32_add(inc, p["f32"][field]) if sign > 0 else f32_sub(inc, p["f32"][field])
            inc = f32_mul(inc, p["f32"]["dtcld"])
            expected = max(f32_add(p["f32"]["nrs(i,k,1)"], inc), 0.0)
            actual_bits = q["f32_bits"]["nrs(i,k,1)"]
            expected_bits = struct.pack(">f", f32(expected)).hex().upper()
            if actual_bits != expected_bits:
                raise TraceError(f"{label} source-ordered QNR update differs at {key}")
        checked[label] = len(pre)
    return checked


def _verify_nr_caps(rows: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    families = (
        ("warm", "NR_LIMIT_PRE", "NR_LIMIT_POST",
         ("nraut(i,k)", "nraci(i,k)", "nrcol(i,k)", "niacr(i,k)",
          "nsacr(i,k)", "ngacr(i,k)"), (-1, 1, 1, 1, 1, 1)),
        ("cold", "NR_LIMIT_COLD_PRE", "NR_LIMIT_COLD_POST",
         ("nraut(i,k)", "nrcol(i,k)", "nseml(i,k)", "ngeml(i,k)"),
         (-1, 1, -1, -1)),
    )
    for label, pre_tag, post_tag, rates, signs in families:
        pre = {row["key"][1:]: row for row in rows if row["tag"] == pre_tag}
        post = {row["key"][1:]: row for row in rows if row["tag"] == post_tag}
        if set(pre) != set(post):
            raise TraceError(f"{pre_tag}/{post_tag} event-key sets differ")
        bound = 0
        for key, p in pre.items():
            value = max(p["f32"]["nrmin"], p["f32"]["nrs(i,k,1)"])
            if struct.pack(">f", f32(value)).hex().upper() != p["f32_bits"]["value"].upper():
                raise TraceError(f"{label} QNR donor threshold value differs at {key}")
            source = f32(-p["f32"][rates[0]])
            for field, sign in zip(rates[1:], signs[1:]):
                source = f32_add(source, p["f32"][field]) if sign > 0 else f32_sub(source, p["f32"][field])
            source = f32_mul(source, p["f32"]["dtcld"])
            if struct.pack(">f", source).hex().upper() != p["f32_bits"]["source"].upper():
                raise TraceError(f"{label} QNR donor source differs at {key}")
            is_bound = source > value
            flag_expr = "source.gt.value"
            if bool(p["flags"].get(flag_expr, -1)) != is_bound:
                raise TraceError(f"{label} source/value cap branch differs at {key}")
            q = post[key]
            if is_bound:
                bound += 1
                factor = f32_div(value, source)
            else:
                factor = 1.0
            for rate in rates:
                expected = f32_mul(p["f32"][rate], factor) if is_bound else p["f32"][rate]
                if struct.pack(">f", f32(expected)).hex().upper() != q["f32_bits"][rate].upper():
                    raise TraceError(f"{label} limited rate {rate} differs at {key}")
        out[label] = bound
    return out


def _verify_nraut(rows: list[dict[str, Any]]) -> dict[str, int]:
    base = {row["key"][1:]: row for row in rows if row["tag"] == "NRAUT_BASE"}
    dsd = {row["key"][1:]: row for row in rows if row["tag"] == "NRAUT_DSD_BRANCH"}
    cap = {row["key"][1:]: row for row in rows if row["tag"] == "NRAUT_DONOR_CAP"}
    if set(base) != set(dsd) or set(base) != set(cap):
        raise TraceError("NRAUT base/DSD/donor-cap event sets differ")
    gate = {(row["step"], row["level"], row["outer_loop"], row["substep"]): row
            for row in rows if row["tag"] == "NRAUT_GATE"}
    for key, b in base.items():
        step, j, i, loop, sub, level = key
        g = gate.get((step, level, loop, sub))
        if g is None:
            raise TraceError(f"missing NRAUT gate for event {key}")
        qci = g["f32"]["qci(i,k,1)"]
        qcr = g["f32"]["qcr(i,k)"]
        nci = g["f32"]["nci(i,k,1)"]
        ncmin = g["f32"]["ncmin"]
        if bool(g["flags"]["qci(i,k,1).gt.qcr(i,k)"]) != (qci > qcr):
            raise TraceError(f"NRAUT qci/qcr gate differs at {key}")
        if bool(g["flags"]["nci(i,k,1).gt.ncmin"]) != (nci > ncmin):
            raise TraceError(f"NRAUT nci/ncmin gate differs at {key}")
        expected_base = f32_mul(f32_mul(3.5e9, b["f32"]["den(i,k)"]),
                                b["f32"]["praut(i,k)"])
        if struct.pack(">f", expected_base).hex().upper() != b["f32_bits"]["nraut(i,k)"]:
            raise TraceError(f"NRAUT base formula differs at {key}")
        d = dsd[key]
        if bool(d["flags"]["qrs(i,k,1).gt.lenconcr"]):
            expected_dsd = f32_mul(f32_div(d["f32"]["nrs(i,k,1)"],
                                           d["f32"]["qrs(i,k,1)"]),
                                   d["f32"]["praut(i,k)"])
        else:
            expected_dsd = expected_base
        if struct.pack(">f", expected_dsd).hex().upper() != d["f32_bits"]["nraut(i,k)"]:
            raise TraceError(f"NRAUT DSD branch expression differs at {key}")
        c = cap[key]
        donor = f32_div(c["f32"]["nci(i,k,1)"], c["f32"]["dtcld"])
        expected_cap = min(expected_dsd, donor)
        if struct.pack(">f", f32(expected_cap)).hex().upper() != c["f32_bits"]["nraut(i,k)"]:
            raise TraceError(f"NRAUT donor cap differs at {key}")
    return {"gate_records": len(gate), "autoconversion_records": len(base),
            "positive_rate_records": sum(1 for r in cap.values()
                                          if r["f32"]["nraut(i,k)"] > 0.0)}


def _verify_dsd_gates(rows: list[dict[str, Any]]) -> dict[str, int]:
    checked: dict[str, int] = {}
    for tag in ("DSD_PRE_GATE", "DSD_POSTFREEZE_GATE", "DSD_FINAL_GATE"):
        selected = [row for row in rows if row["tag"] == tag]
        if not selected:
            raise TraceError(f"missing executed DSD gate: {tag}")
        expected_keys = {
            (step, CELL["host_j"], CELL["host_i"], 1, 0, level)
            for step in EXPECTED_STEPS for level in range(1, 40)
        }
        actual_keys = {row["key"][1:] for row in selected}
        if actual_keys != expected_keys:
            raise TraceError(
                f"{tag} event-key census differs; missing={sorted(expected_keys - actual_keys)}, "
                f"extra={sorted(actual_keys - expected_keys)}")
        for row in selected:
            v = row["f32"]
            expected = (v["qrs(i,k,1)"] >= v["qcrmin"]
                        and v["nrs(i,k,1)"] >= v["nrmin"])
            if bool(row["flags"]["qrs(i,k,1).ge.qcrmin .and. nrs(i,k,1).ge.nrmin"]) != expected:
                raise TraceError(f"{tag} threshold branch differs at {row['key']}")
        checked[tag] = len(selected)
    return checked


def _verify_rain_number_sources(rows: list[dict[str, Any]]) -> dict[str, Any]:
    for tag, steps in EXPECTED_SOURCE_EVENT_LEVELS.items():
        expected = {
            (step, CELL["host_j"], CELL["host_i"], 1, 0, level)
            for step, levels in steps.items() for level in levels
        }
        actual = {row["key"][1:] for row in rows if row["tag"] == tag}
        if actual != expected:
            raise TraceError(
                f"{tag} event-key census differs; missing={sorted(expected - actual)}, "
                f"extra={sorted(actual - expected)}")
    positive: dict[str, list[dict[str, Any]]] = {"snow_melt": [], "graupel_melt": [],
                                                "rain_freeze_sink": []}
    pairs = (
        ("snow_melt", "NR_SNOW_MELT_PRE", "NR_SNOW_MELT_POST",
         "qrs(i,k,2)", "sfac", "psmlt(i,k)", "qcrmin"),
        ("graupel_melt", "NR_GRAUPEL_MELT_PRE", "NR_GRAUPEL_MELT_POST",
         "qrs(i,k,3)", "gfac", "pgmlt(i,k)", "qcrmin"),
    )
    for name, pre_tag, post_tag, reservoir, coef, mass_delta, threshold in pairs:
        pre = {row["key"][1:]: row for row in rows if row["tag"] == pre_tag}
        post = {row["key"][1:]: row for row in rows if row["tag"] == post_tag}
        if set(pre) != set(post):
            raise TraceError(f"{pre_tag}/{post_tag} event-key sets differ")
        for key, p in pre.items():
            v = p["f32"]
            if not v[reservoir] > v[threshold]:
                raise TraceError(f"{name} number DSD floor gate was not active at {key}")
            # nrs = nrs - factor * applied mass-melt tendency, each REAL(4).
            expected = f32_sub(v["nrs(i,k,1)"],
                               f32_mul(v[coef], v[mass_delta]))
            actual = post[key]["f32_bits"]["nrs(i,k,1)"]
            if struct.pack(">f", expected).hex().upper() != actual:
                raise TraceError(f"{name} applied number producer differs at {key}")
            delta = post[key]["f32"]["nrs(i,k,1)"] - v["nrs(i,k,1)"]
            if delta > 0:
                positive[name].append({"step": p["step"], "level": p["level"],
                                       "applied_nr_increment": delta,
                                       "applied_mass_melt_rate": v[mass_delta],
                                       "number_factor": v[coef],
                                       "reservoir_above_qcrmin": v[reservoir]})
    # The freezing sink is promoted to REAL(8) before the store back to REAL(4).
    pre = {row["key"][1:]: row for row in rows if row["tag"] == "NR_FREEZE_PRE"}
    post = {row["key"][1:]: row for row in rows if row["tag"] == "NR_FREEZE_POST"}
    if set(pre) != set(post):
        raise TraceError("NR_FREEZE_PRE/POST event-key sets differ")
    for key, p in pre.items():
        expected = f32(float(p["f32"]["nrs(i,k,1)"]) - p["f64"]["nfrzdtr"])
        actual = post[key]["f32_bits"]["nrs(i,k,1)"]
        if struct.pack(">f", expected).hex().upper() != actual:
            raise TraceError(f"direct rain-freeze number sink differs at {key}")
        delta = post[key]["f32"]["nrs(i,k,1)"] - p["f32"]["nrs(i,k,1)"]
        if delta < 0:
            positive["rain_freeze_sink"].append({"step": p["step"], "level": p["level"],
                                                 "applied_nr_decrement": -delta})
    if not any(positive.values()):
        raise TraceError("the selected mp37 call contains no measured rain-number source/sink")
    return {"positive_source_or_sink_counts": {k: len(v) for k, v in positive.items()},
            "events": positive}


def _conditional_threshold_maps(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map thresholds at the predeclared active K13 profile without changing execution."""
    host = {(row["step"], row["level"]): row for row in rows
            if row["tag"] == "HOST_ENTRY"}
    maps: list[dict[str, Any]] = []
    # K13 was selected from prior native applied-number evidence before this
    # rerun; all 39 levels remain in the transport ledger.
    for step in sorted({row["step"] for row in rows if row["tag"] == "HOST_ENTRY"}):
        key = (step, 13)
        source = host.get(key)
        if source is None:
            raise TraceError(f"predeclared K13 lacks a host-entry record at {key}")
        h = source["f32"]
        rho_d = h["den(i,k,j)"] / (1.0 + h["q(i,k,j)"])
        entry_nr = h["nr(i,k,j)"]
        dsd = next((row for row in rows
                    if row["tag"] == "DSD_PRE_GATE" and row["step"] == step
                    and row["level"] == 13), None)
        maximum = next((row for row in rows
                        if row["tag"] == "NR_MAX_GATE" and row["step"] == step
                        and row["level"] == 13), None)
        autoconv = next((row for row in rows
                         if row["tag"] == "NRAUT_GATE" and row["step"] == step
                         and row["level"] == 13), None)
        if not (dsd and maximum and autoconv):
            raise TraceError(f"predeclared K13 threshold records are incomplete at {key}")
        dv, mv, av = dsd["f32"], maximum["f32"], autoconv["f32"]
        expected_nrmax_gate = mv["nrs(i,k,1)"] > mv["nrmax"]
        if bool(maximum["flags"]["nrs(i,k,1).gt.nrmax"]) != expected_nrmax_gate:
            raise TraceError(f"K13 nrmax threshold branch differs at {key}")
        item = {"step": step, "level": 13,
                "rho_m_at_host_entry": h["den(i,k,j)"],
                "qv_at_host_entry": h["q(i,k,j)"],
                "rho_d_conditional": rho_d,
                "raw_host_nr": entry_nr,
                "number_at_volume_basis_if_host_is_dry_kg": rho_d * entry_nr,
                "nrmin_raw": dv["nrmin"],
                "nrmin_volume_threshold_if_host_is_dry_kg":
                    rho_d * dv["nrmin"],
                "nrmax_raw": mv["nrmax"],
                "nrmax_volume_threshold_if_host_is_dry_kg":
                    rho_d * mv["nrmax"],
                "ncmin_raw": av["ncmin"],
                "ncmin_volume_threshold_if_host_is_dry_kg":
                    rho_d * av["ncmin"],
                "qcrmin_raw_mixing_ratio": dv["qcrmin"],
                "qcrmin_volume_mass_threshold_if_dry_mixing_ratio":
                    rho_d * dv["qcrmin"],
                "dsd_gate_flags": dsd["flags"],
                "nrmax_gate_flags": maximum["flags"],
                "nraut_gate_flags": autoconv["flags"],
                "basis_choice": "conditional diagnostic only; no source field was rescaled"}
        maps.append(item)
    if not maps:
        raise TraceError("no threshold/basis mappings were captured")
    return maps


def _focus_path(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize the input-predeclared K13 producer-to-transport path."""
    def one(tag: str, step: int, level: int) -> dict[str, Any]:
        found = [r for r in rows if r["tag"] == tag and r["step"] == step
                 and r["level"] == level]
        if not found:
            raise TraceError(f"missing predeclared K13 trace event {tag} at step {step}")
        return found[0]

    entry1 = one("HOST_ENTRY", 1, 13)["f32"]
    entry2 = one("HOST_ENTRY", 2, 13)["f32"]
    return1 = one("HOST_RETURN", 1, 13)["f32"]
    return2 = one("HOST_RETURN", 2, 13)["f32"]
    melt_pre = one("NR_SNOW_MELT_PRE", 1, 13)
    melt_post = one("NR_SNOW_MELT_POST", 1, 13)
    dsd_gate = one("DSD_PRE_GATE", 2, 13)
    dsd_raw = one("DSD_PRE_RAW", 2, 13)
    auto = one("NRAUT_GATE", 2, 13)
    upper_k14 = one("NR_FACE_PRE", 2, 14)["f32"]
    lower_k13 = one("NR_FACE_PRE", 2, 13)["f32"]
    upper_k13 = lower_k13
    lower_k12 = one("NR_FACE_PRE", 2, 12)["f32"]
    if not dsd_gate["flags"].get("qrs(i,k,1).ge.qcrmin .and. nrs(i,k,1).ge.nrmin"):
        raise TraceError("predeclared K13 active rain DSD gate did not execute")
    source_increment = (melt_post["f32"]["nrs(i,k,1)"]
                        - melt_pre["f32"]["nrs(i,k,1)"])
    if source_increment <= 0:
        raise TraceError("predeclared K13 has no positive measured rain-number source")
    out14 = upper_k14["dnr(i,k)"]
    in13 = lower_k13["dnr(i,k+1)"]
    out13 = upper_k13["dnr(i,k)"]
    in12 = lower_k12["dnr(i,k+1)"]
    if out14 <= 0 or in13 <= 0 or out13 <= 0 or in12 <= 0:
        raise TraceError("predeclared K13 face lacks applied outflow and inflow")
    return {
        "selected_level": 13,
        "step1_host_entry_qnr": entry1["nr(i,k,j)"],
        "step1_snow_melt_number_increment": source_increment,
        "step1_snow_dsd_number_factor": melt_pre["f32"]["sfac"],
        "step1_snow_mass_melt_amount": melt_pre["f32"]["psmlt(i,k)"],
        "step1_host_return_qnr": return1["nr(i,k,j)"],
        "step2_host_entry_qnr": entry2["nr(i,k,j)"],
        "step2_active_rain_dsd_gate": dsd_gate["flags"]["qrs(i,k,1).ge.qcrmin .and. nrs(i,k,1).ge.nrmin"],
        "step2_rain_lambda": dsd_raw["f32"]["lamdr_tmp(i,k)"],
        "step2_rain_n0r": dsd_raw["f64"]["n0r(i,k)"],
        "step2_autoconversion_gate_flags": auto["flags"],
        "step2_face_k14_to_k13": {
            "number_departure": out14, "number_arrival": in13,
            "mass_departure": upper_k14["dqr(i,k)"],
            "mass_arrival": lower_k13["dqr(i,k+1)"],
            "upper_dz": upper_k14["delz(i,k)"],
            "lower_dz": lower_k13["delz(i,k)"],
            "upper_rho_m": upper_k14["den(i,k)"],
            "lower_rho_m": lower_k13["den(i,k)"],
            "upper_qv": upper_k14["q(i,k)"],
            "lower_qv": lower_k13["q(i,k)"],
        },
        "step2_face_k13_to_k12": {
            "number_departure": out13, "number_arrival": in12,
            "mass_departure": upper_k13["dqr(i,k)"],
            "mass_arrival": lower_k12["dqr(i,k+1)"],
            "upper_dz": upper_k13["delz(i,k)"],
            "lower_dz": lower_k12["delz(i,k)"],
            "upper_rho_m": upper_k13["den(i,k)"],
            "lower_rho_m": lower_k12["den(i,k)"],
            "upper_qv": upper_k13["q(i,k)"],
            "lower_qv": lower_k12["q(i,k)"],
        },
        "step2_mstep": one("NR_FACE_PRE", 2, 13)["i32"]["mstep(i)"],
        "step2_host_return_qnr": return2["nr(i,k,j)"],
        "between_call_entry_minus_prior_return":
            entry2["nr(i,k,j)"] - return1["nr(i,k,j)"],
        "intercall_dynamics_number_budget_measured": False,
        "physical_basis_resolved": False,
    }


def _verify_transport(rows: list[dict[str, Any]]) -> dict[str, Any]:
    top_pre = {row["key"][1:]: row for row in rows if row["tag"] == "NR_TOP_PRE"}
    top_post = {row["key"][1:]: row for row in rows if row["tag"] == "NR_TOP_POST"}
    face_pre = {row["key"][1:]: row for row in rows if row["tag"] == "NR_FACE_PRE"}
    face_post = {row["key"][1:]: row for row in rows if row["tag"] == "NR_FACE_POST"}
    expected_faces = {
        (step, CELL["host_j"], CELL["host_i"], 1, 1, level)
        for step in EXPECTED_TRANSPORT_STEPS
        for level in EXPECTED_INTERNAL_FACE_LEVELS
    }
    expected_top = {
        (step, CELL["host_j"], CELL["host_i"], 1, 1, EXPECTED_TOP_LEVEL)
        for step in EXPECTED_TRANSPORT_STEPS
    }
    for tag, actual, expected in (
            ("NR_FACE_PRE", face_pre, expected_faces),
            ("NR_FACE_POST", face_post,
             {(step, j, i, loop, sub, level)
              for step, j, i, loop, sub, level in expected_faces}),
            ("NR_TOP_PRE", top_pre, expected_top),
            ("NR_TOP_POST", top_post,
             {(step, j, i, loop, sub, level)
              for step, j, i, loop, sub, level in expected_top})):
        if set(actual) != expected:
            missing = sorted(expected - set(actual))
            extra = sorted(set(actual) - expected)
            raise TraceError(f"{tag} event-key census differs; missing={missing}, extra={extra}")
    if not top_pre or set(top_pre) != set(top_post) or set(face_pre) != set(face_post):
        raise TraceError("rain sedimentation PRE/POST event sets are empty or unpaired")
    nonzero_out: list[tuple[int, int, float]] = []
    replayed_face_rows = 0
    for key, p in face_pre.items():
        q = face_post[key]
        f = p["f32"]
        mstep = p["i32"].get("mstep(i)")
        if mstep is None or mstep < 1:
            raise TraceError(f"invalid integer mstep at {key}")
        # Fortran source order: falkn(k)*dt, then min with current reservoir.
        offer_out = f32_mul(f["falkn(i,k,1)"], f["dtcld"])
        expect_out = min(offer_out, f["nrs(i,k,1)"])
        # Inflow source order: falkn(up)*dz(up)/dz(low)*dt, capped by
        # the upper cell's already-updated QNR reservoir.
        offer_in = f32_mul(f32_div(
            f32_mul(f["falkn(i,k+1,1)"], f["delz(i,k+1)"]),
            f["delz(i,k)"]), f["dtcld"])
        expect_in = min(offer_in, f["nrs(i,k+1,1)"])
        for name, expected in (("dnr(i,k)", expect_out), ("dnr(i,k+1)", expect_in)):
            if struct.pack(">f", f32(expected)).hex().upper() != p["f32_bits"][name]:
                raise TraceError(f"rain applied number cap {name} differs at {key}")
        expected_state = max(f32_add(f32_sub(f["nrs(i,k,1)"], expect_out), expect_in), 0.0)
        expected_qr_out = min(f32_div(f32_mul(f["falk(i,k,1)"], f["dtcld"]),
                                       f["dend(i,k)"]), f["qrs(i,k,1)"])
        expected_qr_in_offer = f32_div(f32_mul(
            f32_div(f32_mul(f["falk(i,k+1,1)"], f["delz(i,k+1)"]),
                    f["delz(i,k)"]), f["dtcld"]), f["dend(i,k)"])
        expected_qr_in = min(expected_qr_in_offer, f["qrs(i,k+1,1)"])
        expected_qr = max(f32_add(f32_sub(f["qrs(i,k,1)"], expected_qr_out),
                                  expected_qr_in), 0.0)
        for name, expected in (("nrs(i,k,1)", expected_state),
                               ("qrs(i,k,1)", expected_qr)):
            if struct.pack(">f", f32(expected)).hex().upper() != q["f32_bits"][name]:
                raise TraceError(f"rain applied state {name} differs at {key}")
        if expect_out > 0:
            nonzero_out.append((p["step"], p["level"], expect_out))
        replayed_face_rows += 1
    nonzero_top = []
    for key, p in top_pre.items():
        q = top_post[key]
        f = p["f32"]
        mstep = p["i32"].get("mstep(i)")
        if mstep is None or mstep < 1:
            raise TraceError(f"invalid top integer mstep at {key}")
        offer_n = f32_mul(f["falkn(i,k,1)"], f["dtcld"])
        depart_n = min(offer_n, f["nrs(i,k,1)"])
        expected_n = max(f32_sub(f["nrs(i,k,1)"], offer_n), 0.0)
        offer_q = f32_div(f32_mul(f["falk(i,k,1)"], f["dtcld"]), f["dend(i,k)"])
        expected_q = max(f32_sub(f["qrs(i,k,1)"], offer_q), 0.0)
        for name, expected in (("nrs(i,k,1)", expected_n),
                               ("qrs(i,k,1)", expected_q)):
            if struct.pack(">f", f32(expected)).hex().upper() != q["f32_bits"][name]:
                raise TraceError(f"top-cell rain state {name} differs at {key}")
        if depart_n > 0:
            nonzero_top.append((p["step"], p["level"], depart_n))
    active = sorted(nonzero_out + nonzero_top)
    if not active:
        raise TraceError("no nonzero applied rain-number departure in the selected mp37 path")
    return {"face_rows_replayed": replayed_face_rows,
            "top_rows_replayed": len(top_pre),
            "mstep_values": sorted({row["i32"]["mstep(i)"] for row in rows
                                    if row["tag"] in ("NR_FACE_PRE", "NR_TOP_PRE")}),
            "nonzero_departures": len(active),
            "first_nonzero_departure": list(active[0])}


def _conditional_column_measures(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compute source-weighted rain mass and conditional number ledgers per substep."""
    face_pre = {row["key"][1:]: row for row in rows if row["tag"] == "NR_FACE_PRE"}
    face_post = {row["key"][1:]: row for row in rows if row["tag"] == "NR_FACE_POST"}
    top_pre = {row["key"][1:]: row for row in rows if row["tag"] == "NR_TOP_PRE"}
    top_post = {row["key"][1:]: row for row in rows if row["tag"] == "NR_TOP_POST"}
    groups: dict[tuple[int, int, int], dict[int, dict[str, Any]]] = defaultdict(dict)
    for key, row in face_pre.items():
        step, _j, _i, loop, sub, level = key
        groups[(step, loop, sub)][level] = {"pre": row, "post": face_post[key]}
    for key, row in top_pre.items():
        step, _j, _i, loop, sub, level = key
        groups[(step, loop, sub)][level] = {"pre": row, "post": top_post[key], "top": True}
    output: list[dict[str, Any]] = []
    for (step, loop, sub), layers in sorted(groups.items()):
        levels = sorted(layers)
        if len(levels) < 2 or levels != list(range(levels[0], levels[-1] + 1)):
            raise TraceError(f"rain column layer set is incomplete at {(step, loop, sub)}")
        top_k = levels[-1]

        def state(k: int) -> dict[str, float]:
            pair = layers[k]
            r = pair["pre"]["f32"]
            if pair.get("top"):
                return {"nr0": r["nrs(i,k,1)"], "nr1": pair["post"]["f32"]["nrs(i,k,1)"],
                        "qr0": r["qrs(i,k,1)"], "qr1": pair["post"]["f32"]["qrs(i,k,1)"],
                        "rho_m": r["den(i,k)"], "qv": r["q(i,k)"], "dz": r["delz(i,k)"]}
            return {"nr0": r["nrs(i,k,1)"], "nr1": pair["post"]["f32"]["nrs(i,k,1)"],
                    "qr0": r["qrs(i,k,1)"], "qr1": pair["post"]["f32"]["qrs(i,k,1)"],
                    "rho_m": r["den(i,k)"], "qv": r["q(i,k)"], "dz": r["delz(i,k)"]}

        profile = {k: state(k) for k in levels}
        for v in profile.values():
            v["rho_d"] = v["rho_m"] / (1.0 + v["qv"])
        number_weights = {
            "dz_volume": lambda x: x["dz"],
            "rho_m_operator": lambda x: x["rho_m"] * x["dz"],
            "rho_d_conditional": lambda x: x["rho_d"] * x["dz"],
        }
        mass_weights = {
            "rho_m_operator": lambda x: x["rho_m"] * x["dz"],
            "rho_d_conditional": lambda x: x["rho_d"] * x["dz"],
        }
        number_mismatch = {name: 0.0 for name in number_weights}
        mass_mismatch = {name: 0.0 for name in mass_weights}
        number_throughput = {name: 0.0 for name in number_weights}
        mass_throughput = {name: 0.0 for name in mass_weights}
        face_count = 0
        for lower in levels[:-1]:
            upper = lower + 1
            pre = layers[lower]["pre"]["f32"]
            upper_cell = profile[upper]
            if upper == top_k:
                upper_record = layers[upper]["pre"]["f32"]
                nr_offer = f32_mul(upper_record["falkn(i,k,1)"], upper_record["dtcld"])
                qr_offer = f32_div(f32_mul(upper_record["falk(i,k,1)"], upper_record["dtcld"]),
                                   upper_record["dend(i,k)"])
                nr_out = min(nr_offer, upper_cell["nr0"])
                qr_out = min(qr_offer, upper_cell["qr0"])
            else:
                upper_record = layers[upper]["pre"]["f32"]
                nr_out = upper_record["dnr(i,k)"]
                qr_out = upper_record["dqr(i,k)"]
            nr_in = pre["dnr(i,k+1)"]
            qr_in = pre["dqr(i,k+1)"]
            for name, weight in number_weights.items():
                number_mismatch[name] += (weight(profile[lower]) * nr_in
                                          - weight(upper_cell) * nr_out)
                number_throughput[name] += weight(upper_cell) * nr_out
            for name, weight in mass_weights.items():
                mass_mismatch[name] += (weight(profile[lower]) * qr_in
                                        - weight(upper_cell) * qr_out)
                mass_throughput[name] += weight(upper_cell) * qr_out
            face_count += 1
        bottom = levels[0]
        bottom_record = layers[bottom]["pre"]["f32"]
        bottom_nr = bottom_record["dnr(i,k)"]
        bottom_qr = bottom_record["dqr(i,k)"]
        inventories: dict[str, Any] = {}
        for name, weight in number_weights.items():
            delta = sum(weight(profile[k]) * (profile[k]["nr1"] - profile[k]["nr0"])
                        for k in levels)
            bottom_export = weight(profile[bottom]) * bottom_nr
            closure = delta - number_mismatch[name] + bottom_export
            inventories[name] = {"delta": delta, "interface_mismatch": number_mismatch[name],
                                 "bottom_export": bottom_export, "ledger_closure": closure,
                                 "transported_departure": number_throughput[name] + bottom_export}
        mass_inventories: dict[str, Any] = {}
        for name, weight in mass_weights.items():
            delta = sum(weight(profile[k]) * (profile[k]["qr1"] - profile[k]["qr0"])
                        for k in levels)
            bottom_export = weight(profile[bottom]) * bottom_qr
            closure = delta - mass_mismatch[name] + bottom_export
            mass_inventories[name] = {"delta": delta, "interface_mismatch": mass_mismatch[name],
                                      "bottom_export": bottom_export,
                                      "ledger_closure": closure,
                                      "transported_departure": mass_throughput[name] + bottom_export}
        output.append({"step": step, "outer_loop": loop, "substep": sub,
                       "levels": len(levels), "internal_faces": face_count,
                       "number_measures": inventories,
                       "mass_measures": mass_inventories,
                       "basis_resolved": False})
    return output


def replay(document: dict[str, Any], capture_text: str) -> dict[str, Any]:
    if document.get("schema") != SCHEMA:
        raise TraceError(f"unexpected evidence schema {document.get('schema')!r}")
    if document.get("physical_number_basis_resolved") is not False:
        raise TraceError("S2 evidence must preserve the unresolved physical number basis")
    if document.get("scope", {}).get("mp_physics") != 37:
        raise TraceError("S2 must be an mp37 KDM6 trace")
    if document.get("scope", {}).get("host_i") != CELL["host_i"] or \
            document.get("scope", {}).get("host_j") != CELL["host_j"]:
        raise TraceError("S2 selection differs from its input-selected cell")
    if document.get("source", {}).get("canonical_source_sha256") != SOURCE_SHA256:
        raise TraceError("canonical mp37 source SHA256 does not match the pinned source")
    if document.get("input_identity", {}).get("wrfinput_sha256") != INPUT_SHA256:
        raise TraceError("retained input SHA256 does not match the pinned 5 km file")
    if document.get("noninterference", {}).get("common_numeric_fields_raw_bit_equal") is not True:
        raise TraceError("control/capture raw-bit noninterference has not passed")
    if document.get("noninterference", {}).get("run_seconds") != 40:
        raise TraceError("the active QNR transfer trace requires the predeclared 40 s horizon")
    frames = document.get("noninterference", {}).get("frames", [])
    if [row.get("frame") for row in frames] != [0, 1, 2]:
        raise TraceError("noninterference evidence must cover the saved 0/20/40 s frames")
    for row in frames:
        if (row.get("returncode") != 0 or row.get("common_numeric") != 253
                or row.get("bitwise_match") != 253
                or row.get("common_numeric") != 253
                or row.get("common_variables") != 254
                or row.get("times_exact") is not True
                or row.get("different") != 0
                or row.get("unsupported_or_skipped") != 0
                or row.get("result") != "STRICT BITWISE PASS"):
            raise TraceError(f"noninterference frame record failed: {row}")
    capture_hash = hashlib.sha256(capture_text.encode()).hexdigest()
    if document.get("capture_sha256") != capture_hash:
        raise TraceError("capture payload SHA256 does not match the evidence manifest")
    observed_records = sum(line.startswith("S2NR ") for line in capture_text.splitlines())
    if (document.get("capture_payload_lines") != EXPECTED_CAPTURE_RECORDS
            or observed_records != EXPECTED_CAPTURE_RECORDS):
        raise TraceError(
            f"capture record census differs from pinned {EXPECTED_CAPTURE_RECORDS}: "
            f"manifest={document.get('capture_payload_lines')}, observed={observed_records}")
    schema = document.get("capture_source", {})
    if schema.get("schema") != SOURCE_SCHEMA or schema.get("stripped_exact") is not True:
        raise TraceError("instrumented source lacks its exact-stripping source proof")
    rows = parse_capture(capture_text, schema.get("tags", {}))
    _verify_event_census(rows)
    boundary = _verify_boundary_chain(rows)
    history_return_checks = _verify_history_returns(
        rows, document.get("history_return", []))
    dsd = _verify_dsd_gates(rows)
    nraut = _verify_nraut(rows)
    caps = _verify_nr_caps(rows)
    updates = _verify_budget_updates(rows)
    transport = _verify_transport(rows)
    number_sources = _verify_rain_number_sources(rows)
    conditional_measures = _conditional_column_measures(rows)
    threshold_maps = _conditional_threshold_maps(rows)
    focus = _focus_path(rows)
    return {
        "schema": "s2-number-replay-v1",
        "capture_records": len(rows),
        "host_kernel_boundary": boundary,
        "history_return_checks": history_return_checks,
        "dsd_gate_records": dsd,
        "nraut": nraut,
        "number_floor_caps_active": caps,
        "source_ordered_rain_number_updates": updates,
        "measured_rain_number_sources": number_sources,
        "rain_applied_transport": transport,
        "conditional_column_measures": conditional_measures,
        "conditional_threshold_maps": threshold_maps,
        "focus_path": focus,
        "physical_number_basis_resolved": False,
        "number_measures": ["dz*n [conditional volume-basis interpretation]",
                            "rho_m*dz*n [operator measure]",
                            "rho_d*dz*n [conditional dry-mass interpretation]"],
        "mass_measures": ["rho_m*dz*q [operator measure]",
                          "rho_d*dz*q [conditional dry-mass interpretation]"],
        "threshold_maps_are_conditional_only": True,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--evidence", type=Path, required=True)
    ap.add_argument("--capture", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    result = replay(json.loads(args.evidence.read_text()), args.capture.read_text())
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
