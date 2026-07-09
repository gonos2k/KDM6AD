#!/usr/bin/env python3
"""Parse RTTOV rttov_test ASCII block outputs.

The RTTOV test suite writes Fortran-like blocks such as::

    RADIANCE%TOTAL = (
      1.0 2.0
    )

and K-profile blocks such as::

    PROFILES_K(   2)%T = (
      ...
    )

This module intentionally keeps raw RTTOV keys intact so downstream comparison
code can choose its own naming convention without losing RTTOV provenance.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable

_FLOAT_RE = re.compile(r"[+-]?(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:[EeDd][+-]?\d+)?")
_BLOCK_START_RE = re.compile(r"^(?P<key>.+?)\s*=\s*\(\s*$")


def parse_rttov_ascii_blocks(path: str | Path) -> dict[str, list[float]]:
    """Return ``{raw_rttov_key: flat_float_values}`` from an RTTOV ASCII file."""
    blocks: dict[str, list[float]] = {}
    current_key: str | None = None
    current_values: list[float] = []

    for raw_line in Path(path).read_text().splitlines():
        line = raw_line.rstrip()
        if current_key is None:
            match = _BLOCK_START_RE.match(line)
            if match:
                key = match.group("key").rstrip()
                if not key:
                    continue
                current_key = key
                current_values = []
            continue

        if line.strip() == ")":
            if current_key in blocks:
                raise ValueError(
                    f"duplicate RTTOV ASCII block: {current_key!r} -- refusing to "
                    "overwrite an earlier block with the same key.")
            blocks[current_key] = current_values
            current_key = None
            current_values = []
            continue

        current_values.extend(_parse_floats(line))

    if current_key is not None:
        raise ValueError(f"unterminated RTTOV ASCII block: {current_key}")

    return blocks


def _parse_floats(line: str) -> list[float]:
    return [float(token.replace("D", "E").replace("d", "e")) for token in _FLOAT_RE.findall(line)]


def reshape_flat(values: list[float], nprofiles: int, nchannels: int) -> list[list[float]]:
    """Reshape a profile-major/channel-minor flat RTTOV array."""
    expected = nprofiles * nchannels
    if len(values) != expected:
        raise ValueError(f"cannot reshape {len(values)} values to ({nprofiles}, {nchannels}); expected {expected}")
    return [values[i * nchannels : (i + 1) * nchannels] for i in range(nprofiles)]


def summarize_values(values: Iterable[float]) -> dict[str, float | int | None]:
    vals = list(values)
    if not vals:
        return {"count": 0, "min": None, "max": None, "nonzero": 0}
    return {
        "count": len(vals),
        "min": min(vals),
        "max": max(vals),
        "nonzero": sum(1 for value in vals if value != 0.0),
    }


def summarize_file(path: str | Path) -> dict[str, dict[str, float | int | None]]:
    return {key: summarize_values(values) for key, values in parse_rttov_ascii_blocks(path).items()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse/summarize RTTOV rttov_test ASCII block output")
    parser.add_argument("path", type=Path)
    parser.add_argument("--json", action="store_true", help="print parsed values as JSON instead of summaries")
    args = parser.parse_args()

    data = parse_rttov_ascii_blocks(args.path)
    payload = data if args.json else {key: summarize_values(values) for key, values in data.items()}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
