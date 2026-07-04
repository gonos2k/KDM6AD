#!/usr/bin/env python3
"""Summarise RTTOV test profile pressure grids for KDM6AD bridge design."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DERIVATION_POLICY = "log_midpoint_between_half_levels_with_arithmetic_fallback_for_nonpositive_bounds"


def read_pressure_vector(path: str | Path) -> list[float]:
    """Read a one-value-per-line RTTOV pressure vector."""
    values: list[float] = []
    path = Path(path)
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            values.append(float(stripped.replace("D", "E").replace("d", "e")))
        except ValueError as exc:
            raise ValueError(f"invalid pressure in {path} line {line_number}: {stripped}") from exc
    return values


def derive_full_level_pressure_from_half_levels(half_levels: list[float]) -> list[float]:
    """Derive layer/full-level pressure from bounding half-level pressures.

    RTTOV v14 profile input uses half-level pressures as mandatory input and full
    levels/layers for T/Q. For design summaries we derive a reproducible center
    pressure for every layer. Positive-pressure layers use a log-pressure
    midpoint; layers touching a nonpositive bound, notably top=0 hPa, use an
    arithmetic midpoint as a safe finite fallback.
    """
    if len(half_levels) < 2:
        raise ValueError("at least two half levels are required")
    full: list[float] = []
    previous = half_levels[0]
    for current in half_levels[1:]:
        if current < previous:
            raise ValueError("half-level pressure must be monotonically non-decreasing")
        if previous > 0.0 and current > 0.0:
            full.append(math.exp((math.log(previous) + math.log(current)) / 2.0))
        else:
            full.append((previous + current) / 2.0)
        previous = current
    return full


def _ordering(values: list[float]) -> str:
    if all(b >= a for a, b in zip(values, values[1:])):
        return "top_to_surface_increasing_pressure"
    if all(b <= a for a, b in zip(values, values[1:])):
        return "surface_to_top_decreasing_pressure"
    return "non_monotonic"


def build_pressure_grid_summary(profiles_root: str | Path) -> dict[str, Any]:
    """Build pressure-grid summary for RTTOV test profiles."""
    root = Path(profiles_root)
    if not root.is_dir():
        raise ValueError(f"profiles root does not exist or is not a directory: {root}")

    profiles = []
    for profile_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        p_half_path = profile_dir / "atm" / "p_half.txt"
        if not p_half_path.exists():
            continue
        p_half = read_pressure_vector(p_half_path)
        p_full_derived = derive_full_level_pressure_from_half_levels(p_half)
        p_path = profile_dir / "atm" / "p.txt"
        provided = read_pressure_vector(p_path) if p_path.exists() else []
        profiles.append(
            {
                "profile_id": profile_dir.name,
                "half_level_count": len(p_half),
                "derived_full_level_count": len(p_full_derived),
                "provided_full_level_count": len(provided),
                "half_pressure_min_hpa": min(p_half),
                "half_pressure_max_hpa": max(p_half),
                "derived_full_pressure_min_hpa": min(p_full_derived),
                "derived_full_pressure_max_hpa": max(p_full_derived),
                "half_pressure_first_hpa": p_half[0],
                "half_pressure_last_hpa": p_half[-1],
                "derived_full_pressure_first_hpa": p_full_derived[0],
                "derived_full_pressure_last_hpa": p_full_derived[-1],
                "half_level_ordering": _ordering(p_half),
                "p_half_path": str(p_half_path),
                "p_path": str(p_path) if p_path.exists() else None,
            }
        )

    if not profiles:
        raise ValueError(f"no profiles with atm/p_half.txt found under {root}")

    ordering_counts = Counter(row["half_level_ordering"] for row in profiles)
    vertical_ordering = ordering_counts.most_common(1)[0][0] if len(ordering_counts) == 1 else "mixed"

    return {
        "metadata": {
            "source": "rttov-test-profile-pressure-grid",
            "science_status": "fixture-pressure-grid-observed",
            "reference_case": "GK2A AMI ami/501 RTTOV14 test profiles",
            "purpose": "Freeze target pressure-grid facts before KDM6AD-to-RTTOV vertical interpolation design.",
        },
        "profiles_root": str(root),
        "profiles_checked": [row["profile_id"] for row in profiles],
        "vertical_ordering": vertical_ordering,
        "full_level_derivation_policy": DERIVATION_POLICY,
        "half_level_count_counts": dict(sorted(Counter(str(row["half_level_count"]) for row in profiles).items())),
        "derived_full_level_count_counts": dict(sorted(Counter(str(row["derived_full_level_count"]) for row in profiles).items())),
        "provided_full_level_count_counts": dict(sorted(Counter(str(row["provided_full_level_count"]) for row in profiles).items())),
        "bridge_implication": "KDM6AD K levels must be mapped onto 69 RTTOV layer/full-level T/Q values bounded by 70 top-to-surface increasing-pressure half levels.",
        "profiles": profiles,
    }


def write_pressure_grid_summary(profiles_root: str | Path, output_path: str | Path) -> dict[str, Any]:
    """Write pressure-grid summary JSON."""
    summary = build_pressure_grid_summary(profiles_root)
    Path(output_path).write_text(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarise RTTOV test profile pressure grids")
    parser.add_argument("profiles_root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    write_pressure_grid_summary(args.profiles_root, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
