#!/usr/bin/env python3
"""Strict, pure parser for the ABC driver's raw-bit output protocol.

The live A/B/C gate and the OFFLINE bundle verifier must hold the same stdout to
the same contract. A prefix check ("does it start with KDM6ABC") accepts a
truncated or malformed lane whose hash merely happens to match its sibling, so the
whole field universe — order, dtype, shape, element count, raw-bit word width and
finiteness — is validated here, once, for both callers.

Pure: no subprocess, no environment, no filesystem. (B, K) is an explicit argument
rather than a module-level case table, so a new case cannot be admitted by mutating
shared state.
"""
from __future__ import annotations

import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import g33_dump as gd  # noqa: E402

STATE_FIELDS = ("th", "qv", "qc", "qr", "qi", "qs", "qg",
                "nccn", "nc", "ni", "nr", "bg")
INCREMENT_FIELDS = ("rain_increment", "snow_increment", "graupel_increment")
EXPECTED_FIELDS = STATE_FIELDS + INCREMENT_FIELDS
_HEX = re.compile(r"^[0-9a-f]+$")


def parse_abc_output(raw: bytes, algorithm: str, case_name: str, B: int, K: int) -> dict:
    """Validate the driver's complete raw-bit protocol; reject empty/truncated data."""
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise gd.G33Corruption(f"ABC output is not ASCII: {exc}") from None
    lines = text.splitlines()
    if not lines or lines[0] != f"KDM6ABC 1 {algorithm} {case_name} {B} {K}":
        raise gd.G33Corruption("ABC output has a missing or wrong header")
    if lines[-1:] != ["END"]:
        raise gd.G33Corruption("ABC output has no terminal END marker")
    if len(lines) != len(EXPECTED_FIELDS) + 2:
        raise gd.G33Corruption(
            f"ABC output has {len(lines) - 2} fields, expected {len(EXPECTED_FIELDS)}")

    parsed: dict = {}
    for expected_name, line in zip(EXPECTED_FIELDS, lines[1:-1]):
        tok = line.split()
        if len(tok) < 7 or tok[0] != "FIELD" or tok[1] != expected_name:
            raise gd.G33Corruption(
                f"ABC field order/name mismatch: expected {expected_name!r}, got {line!r}")
        dtype = tok[2]
        if dtype not in ("f32", "f64"):
            raise gd.G33Corruption(f"ABC field {expected_name} has dtype {dtype!r}")
        try:
            ndim = int(tok[3])
        except ValueError:
            raise gd.G33Corruption(f"ABC field {expected_name} has invalid ndim") from None
        shape_start, shape_end = 4, 4 + ndim
        if ndim not in (1, 2) or len(tok) <= shape_end:
            raise gd.G33Corruption(f"ABC field {expected_name} has malformed shape")
        try:
            shape = tuple(int(v) for v in tok[shape_start:shape_end])
            numel = int(tok[shape_end])
        except ValueError:
            raise gd.G33Corruption(
                f"ABC field {expected_name} has non-integer shape/count") from None
        want_shape = (B, K) if expected_name in STATE_FIELDS else (B,)
        if shape != want_shape or numel != math.prod(shape):
            raise gd.G33Corruption(
                f"ABC field {expected_name} shape/count {(shape, numel)} != {want_shape}")
        words = tok[shape_end + 1:]
        width = 8 if dtype == "f32" else 16
        if len(words) != numel or any(
                len(w) != width or not _HEX.fullmatch(w) for w in words):
            raise gd.G33Corruption(
                f"ABC field {expected_name} has malformed raw-bit words")
        bits = [int(w, 16) for w in words]
        exponent = 23 if dtype == "f32" else 52
        mask = 0xff if dtype == "f32" else 0x7ff
        if any(((word >> exponent) & mask) == mask for word in bits):
            raise gd.G33Corruption(f"ABC field {expected_name} contains non-finite values")
        if expected_name in parsed:
            raise gd.G33Corruption(f"duplicate ABC field {expected_name}")
        parsed[expected_name] = {"dtype": dtype, "shape": shape, "bits": bits}
    return parsed
