#!/usr/bin/env python3
"""Bounded, read-only IC/BC lineage inventory; reads headers and Times only.

No raw model acquisition, preprocessing, native integration or radiation call.
Files in the same directory are candidates, never inferred parent inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import netCDF4


def record(path: Path) -> dict:
    stat = path.stat()
    return {
        "path": str(path),
        "resolved": str(path.resolve()),
        "symlink": path.is_symlink(),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def header(path: Path) -> dict:
    result = record(path)
    attrs = (
        "TITLE",
        "SIMULATION_START_DATE",
        "START_DATE",
        "DX",
        "DY",
        "CEN_LAT",
        "CEN_LON",
        "MAP_PROJ",
    )
    with netCDF4.Dataset(path) as ds:
        result["attributes"] = {
            key: ds.getncattr(key).item()
            if hasattr(ds.getncattr(key), "item")
            else ds.getncattr(key)
            for key in attrs
            if key in ds.ncattrs()
        }
        result["dimensions"] = {key: len(value) for key, value in ds.dimensions.items()}
        times = netCDF4.chartostring(ds.variables["Times"][:])
        result["times"] = [str(value) for value in times.reshape(-1)]
    result["whole_file_hash"] = "NOT_COMPUTED; metadata and Times only"
    return result


def lineage_differences(ic: dict, met: dict) -> list[str]:
    """Necessary date/grid checks, not a sufficient provenance proof."""
    issues = []
    if met["times"][0][:10] != ic["times"][0][:10]:
        issues.append("INITIAL_DATE_DIFFERS")
    for key in ("west_east", "south_north"):
        if ic["dimensions"][key] != met["dimensions"][key]:
            issues.append(f"GRID_DIMENSION_DIFFERS:{key}")
    for key in ("DX", "DY", "CEN_LAT", "CEN_LON", "MAP_PROJ"):
        if ic["attributes"].get(key) != met["attributes"].get(key):
            issues.append(f"GRID_ATTRIBUTE_DIFFERS:{key}")
    return issues


def inspect(source_dir: Path, link_dir: Path) -> dict:
    ic = header(link_dir / "wrfinput_d01")
    bc = header(link_dir / "wrfbdy_d01")
    candidates = []
    for path in sorted(source_dir.glob("met_em.d01.*.nc")):
        candidate = header(path)
        candidate["differences_from_current_ic"] = lineage_differences(ic, candidate)
        candidate["lineage_status"] = (
            "NOT_CURRENT_IC_PARENT_DATE_GRID_MISMATCH"
            if candidate["differences_from_current_ic"]
            else "DATE_GRID_MATCH_ONLY_PARENTAGE_UNVERIFIED"
        )
        candidates.append(candidate)
    names = ("namelist.wps", "Vtable", "ungrib.log", "metgrid.log", "real.log")
    namelists = []
    pattern = r"(?im)^\s*((?:start|end)_(?:year|month|day|hour)|e_we|e_sn|e_vert|dx|dy)\s*=\s*([^!\n]+)"
    for name in ("namelist.input", "namelist.input.codex_dyn_parity_backup"):
        path = source_dir / name
        if path.exists():
            data = record(path)
            raw = path.read_bytes()
            data["sha256"] = hashlib.sha256(raw).hexdigest()
            data["selected_assignments"] = dict(re.findall(pattern, raw.decode()))
            data["role"] = (
                "FORECAST_CONTEXT; original REAL_EM preprocessing association unverified"
            )
            namelists.append(data)
    return {
        "scope": "Top-level original SS directory and canonical IC/BC symlinks only",
        "ic": ic,
        "bc": bc,
        "met_em_candidates": candidates,
        "missing_preprocessing_evidence": [
            name for name in names if not (source_dir / name).exists()
        ],
        "namelists": namelists,
        "real_executable": record(source_dir / "real.exe")
        if (source_dir / "real.exe").exists()
        else None,
        "conclusion": "RAW_METEOROLOGICAL_PROVIDER_AND_ORIGINAL_PREPROCESSING_LINEAGE_UNVERIFIED",
        "independent_native_cases": "NOT_ESTABLISHED_BY_THIS_INVENTORY",
        "limits": [
            "No whole-device archive absence claim",
            "No meteorological arrays read",
            "REAL_EM label and executable presence do not identify the original provider or executed build",
            "Other-date met_em files are not independent native IC/BC or approved liquid-cloud events",
        ],
        "calls": {"native": 0, "preprocessing": 0, "M": 0, "H": 0, "optimizer": 0},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--link-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.source_dir, args.link_dir)
    result["audit_source_sha256"] = hashlib.sha256(
        Path(__file__).read_bytes()
    ).hexdigest()
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "met_em_count": len(result["met_em_candidates"]),
                "conclusion": result["conclusion"],
            }
        )
    )


if __name__ == "__main__":
    main()
