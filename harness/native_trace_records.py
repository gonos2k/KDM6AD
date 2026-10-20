"""Strict parser and step validator for the opt-in MP137 trace stream.

Trace values are serialized as their IEEE-754 binary32 hexadecimal bit patterns;
this module preserves those bits and never parses rounded decimal floats. The
stream is a selected-column, value-only trace for first-order forward
causality review; it is not a JVP/VJP, derivative, or AD validation artifact.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import re
from typing import Mapping

import numpy as np


TRACE_MAGIC = "# KDM6AD_NATIVE_TRACE_V1"
TRACE_FIELDS: Mapping[str, tuple[str, ...]] = {
    "MP_INPUT": (
        "dt", "TH", "Q", "QC", "QR", "QI", "QS", "QG", "NN", "NC",
        "NI", "NR", "BG", "DEN", "PII", "P", "DELZ",
    ),
    "MP_OUTPUT": (
        "dt", "TH", "Q", "QC", "QR", "QI", "QS", "QG", "NN", "NC",
        "NI", "NR", "BG", "RHOG",
    ),
    "FINISH_PRE": (
        "dt", "H_PRE", "QV_PRE", "TH_PLUS", "QV_PLUS", "QVTEN", "MP_RAW",
        "MP_CLIPPED", "T_NEW_PRE", "T0", "ALPHA", "MP_TEND_LIM",
    ),
    "FINISH_POST": (
        "dt", "T_NEW_AFTER", "T0", "H_RATE", "QV_RATE", "QC_RATE", "TH_PHY_M_T0",
    ),
}
_UINT = re.compile(r"[0-9]+\Z")
_HEX32 = re.compile(r"[0-9A-Fa-f]{8}\Z")


@dataclass(frozen=True)
class TraceRecord:
    kind: str
    step: int
    i: int
    k: int
    j: int
    bits: tuple[int, ...]

    @property
    def fields(self) -> tuple[str, ...]:
        return TRACE_FIELDS[self.kind]

    @property
    def values(self) -> np.ndarray:
        """Read-only float32 view of the recorded IEEE bits."""
        result = np.asarray(self.bits, dtype=np.uint32).view(np.float32)
        result.setflags(write=False)
        return result

    def value(self, field: str) -> np.float32:
        try:
            index = self.fields.index(field)
        except ValueError as exc:
            raise KeyError(f"{field!r} is not a {self.kind} field") from exc
        return self.values[index]


def _parse_uint(token: str, label: str, line_number: int) -> int:
    if not _UINT.fullmatch(token):
        raise ValueError(f"line {line_number}: {label} must be an unsigned decimal integer")
    return int(token, 10)


def read_native_trace(path: str | Path) -> dict[tuple[str, int, int, int, int], TraceRecord]:
    """Parse a complete trace file, preserving every value's 32 raw bits.

    Record key order is ``(kind, step, i, k, j)``. Blank lines and comments
    after the required magic header are ignored; malformed data records fail
    closed.
    """
    source = Path(path)
    try:
        lines = source.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"cannot read ASCII native trace {source}: {exc}") from exc
    if not lines or not (
        lines[0] == TRACE_MAGIC
        or (lines[0].startswith(TRACE_MAGIC) and lines[0][len(TRACE_MAGIC)].isspace())
    ):
        raise ValueError("native trace is missing its KDM6AD_NATIVE_TRACE_V1 header")

    records: dict[tuple[str, int, int, int, int], TraceRecord] = {}
    for line_number, line in enumerate(lines[1:], start=2):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        tokens = stripped.split()
        if len(tokens) < 6:
            raise ValueError(f"line {line_number}: truncated trace record")
        kind = tokens[0]
        if kind not in TRACE_FIELDS:
            raise ValueError(f"line {line_number}: unknown trace kind {kind!r}")
        step, i, k, j, count = (
            _parse_uint(token, label, line_number)
            for token, label in zip(tokens[1:6], ("step", "i", "k", "j", "count"))
        )
        if step < 1 or i < 1 or k < 1 or j < 1:
            raise ValueError(f"line {line_number}: step and native indices must be positive")
        expected_count = len(TRACE_FIELDS[kind])
        if count != expected_count or len(tokens) != 6 + count:
            raise ValueError(
                f"line {line_number}: {kind} requires {expected_count} values, got count={count} "
                f"and {len(tokens) - 6} token(s)"
            )
        value_bits: list[int] = []
        for token in tokens[6:]:
            if not _HEX32.fullmatch(token):
                raise ValueError(f"line {line_number}: float32 value must be exactly eight hex digits")
            value_bits.append(int(token, 16))
        record = TraceRecord(kind, step, i, k, j, tuple(value_bits))
        if not np.isfinite(record.values).all():
            raise ValueError(f"line {line_number}: nonfinite float32 trace value")
        key = (kind, step, i, k, j)
        if key in records:
            raise ValueError(f"line {line_number}: duplicate trace key {key}")
        records[key] = record
    if not records:
        raise ValueError("native trace contains a header but no records")
    return records


def _float32_bits(value: float) -> int:
    converted = np.float32(value)
    if not np.isfinite(converted):
        raise ValueError("dt must be finite when represented as float32")
    if converted <= 0.0:
        raise ValueError("dt must remain positive when represented as float32")
    return int(np.asarray([converted], dtype=np.float32).view(np.uint32)[0])


def _validate_trace(
    path: str | Path,
    *,
    steps: tuple[int, ...],
    i: int,
    j: int,
    levels: int,
    dt: float,
) -> dict[tuple[str, int, int, int, int], TraceRecord]:
    if type(i) is not int or type(j) is not int or type(levels) is not int:
        raise ValueError("native i/j and level count must be integers")
    if i < 1 or j < 1 or levels < 1:
        raise ValueError("native i/j and level count must be positive")
    if isinstance(dt, bool) or not isinstance(dt, (int, float, np.integer, np.floating)):
        raise ValueError("dt must be a real scalar")
    if not math.isfinite(float(dt)) or float(dt) <= 0.0:
        raise ValueError("dt must be finite and positive")
    expected_dt = _float32_bits(float(dt))

    records = read_native_trace(path)
    expected = {
        (kind, step, i, k, j)
        for kind in TRACE_FIELDS
        for step in steps
        for k in range(1, levels + 1)
    }
    actual = set(records)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise ValueError(f"trace record inventory mismatch: missing={missing}, unexpected={unexpected}")
    bad_dt = [key for key, record in records.items() if record.bits[0] != expected_dt]
    if bad_dt:
        raise ValueError(f"trace dt bits differ from requested float32 dt at {sorted(bad_dt)}")
    return records


def validate_step_trace(
    path: str | Path,
    *,
    step: int,
    i: int,
    j: int,
    levels: int,
    dt: float,
) -> dict[tuple[str, int, int, int, int], TraceRecord]:
    """Require exactly the four expected trace kinds for one step/column.

    Every level 1..``levels`` must have exactly one MP input/output and finish
    pre/post record. Unexpected columns, steps, or levels are refused. The dt
    field is checked by raw float32 bits in every row. Passing this structural
    check establishes complete records for one selected-column forward step,
    not causal interpretation or derivative correctness.
    """
    if type(step) is not int or step < 1:
        raise ValueError("step must be a positive integer")
    return _validate_trace(path, steps=(step,), i=i, j=j, levels=levels, dt=dt)


def validate_window_trace(
    path: str | Path,
    *,
    steps: tuple[int, ...],
    i: int,
    j: int,
    levels: int,
    dt: float,
) -> dict[tuple[str, int, int, int, int], TraceRecord]:
    """Require exact selected-column records across a consecutive step window.

    This validates trace completeness only. It does not establish a causal
    interpretation, physical budget, or derivative/AD correctness.
    """
    if not isinstance(steps, tuple) or not steps:
        raise ValueError("steps must be a nonempty tuple of positive integers")
    if any(type(step) is not int or step < 1 for step in steps):
        raise ValueError("steps must be a nonempty tuple of positive integers")
    if steps != tuple(range(steps[0], steps[0] + len(steps))):
        raise ValueError("window steps must be unique and consecutive")
    return _validate_trace(path, steps=steps, i=i, j=j, levels=levels, dt=dt)
