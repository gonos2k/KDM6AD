#!/usr/bin/env python3
"""KDM6AD-to-RTTOV14 variable mapping design table.

This module records the first explicit bridge design between KDM6AD internal
microphysics state variables and RTTOV14 profile/scattering inputs. It is not a
physical conversion implementation: it classifies which KDM6AD variables are
compatible with the current GK2A AMI clear-sky RTTOV14 baseline and which require
cloud/scattering coefficient support plus a separate vertical/profile bridge.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

REQUIRED_KEYS = {
    "kdm6_namespace",
    "kdm6_variable",
    "rttov_profile_variable",
    "rttov_candidate_kind",
    "bridge_status",
    "vertical_unit",
    "notes",
}

VALID_BRIDGE_STATUSES = {
    "clear_sky_baseline_compatible",
    "requires_scattering_or_cloud_bridge",
    "diagnostic_only_until_composed_operator",
}

VALID_CANDIDATE_KINDS = {
    "thermodynamic",
    "gas",
    "hydrometeor",
    "number_concentration",
    "diagnostic",
}

KDM6AD_RTTOV_MAPPING: list[dict[str, str]] = [
    {
        "kdm6_namespace": "KDM6AD",
        "kdm6_variable": "qv",
        "rttov_profile_variable": "Q",
        "rttov_candidate_kind": "gas",
        "bridge_status": "clear_sky_baseline_compatible",
        "vertical_unit": "kg kg-1 mixing ratio; RTTOV humidity convention must be confirmed per profile source",
        "notes": "Water vapour can connect to RTTOV14 clear-sky humidity Jacobians, especially GK2A AMI channels 8-10. Requires vertical-grid and humidity-unit normalization before science comparison.",
    },
    {
        "kdm6_namespace": "KDM6AD",
        "kdm6_variable": "t",
        "rttov_profile_variable": "T",
        "rttov_candidate_kind": "thermodynamic",
        "bridge_status": "clear_sky_baseline_compatible",
        "vertical_unit": "K on KDM6 vertical grid; interpolate/regrid to RTTOV profile levels",
        "notes": "Temperature is the safest first composed-operator path for thermal GK2A AMI channels 7 and 11-16, after vertical-grid mapping is explicit.",
    },
    {
        "kdm6_namespace": "KDM6AD",
        "kdm6_variable": "qc",
        "rttov_profile_variable": "cloud_liquid_water_candidate",
        "rttov_candidate_kind": "hydrometeor",
        "bridge_status": "requires_scattering_or_cloud_bridge",
        "vertical_unit": "kg kg-1 hydrometeor mixing ratio; RTTOV cloud input convention/coefficient dependent",
        "notes": "Cloud liquid is not comparable to the current clear-sky ami/501 O3+CO2 baseline. Needs hydrotable/MFASIS or cloud optical-property bridge.",
    },
    {
        "kdm6_namespace": "KDM6AD",
        "kdm6_variable": "qr",
        "rttov_profile_variable": "rain_water_candidate",
        "rttov_candidate_kind": "hydrometeor",
        "bridge_status": "requires_scattering_or_cloud_bridge",
        "vertical_unit": "kg kg-1 hydrometeor mixing ratio; scattering convention/coefficient dependent",
        "notes": "Rain affects all-sky/scattering paths and cannot be validated against clear-sky profiles_k directly.",
    },
    {
        "kdm6_namespace": "KDM6AD",
        "kdm6_variable": "qs",
        "rttov_profile_variable": "snow_candidate",
        "rttov_candidate_kind": "hydrometeor",
        "bridge_status": "requires_scattering_or_cloud_bridge",
        "vertical_unit": "kg kg-1 hydrometeor mixing ratio; scattering convention/coefficient dependent",
        "notes": "Snow requires RTTOV14 cloud/scattering setup and hydrometeor optical-property mapping.",
    },
    {
        "kdm6_namespace": "KDM6AD",
        "kdm6_variable": "qg",
        "rttov_profile_variable": "graupel_candidate",
        "rttov_candidate_kind": "hydrometeor",
        "bridge_status": "requires_scattering_or_cloud_bridge",
        "vertical_unit": "kg kg-1 hydrometeor mixing ratio; scattering convention/coefficient dependent",
        "notes": "Graupel/hail-like category needs explicit RTTOV hydrometeor category mapping before use.",
    },
    {
        "kdm6_namespace": "KDM6AD",
        "kdm6_variable": "qi",
        "rttov_profile_variable": "cloud_ice_candidate",
        "rttov_candidate_kind": "hydrometeor",
        "bridge_status": "requires_scattering_or_cloud_bridge",
        "vertical_unit": "kg kg-1 hydrometeor mixing ratio; RTTOV ice cloud convention/coefficient dependent",
        "notes": "Cloud ice is potentially relevant to IR/VIS all-sky channels but requires hydrotable/cloud optical-property mapping.",
    },
    {
        "kdm6_namespace": "KDM6AD",
        "kdm6_variable": "nc",
        "rttov_profile_variable": "cloud_droplet_number_candidate",
        "rttov_candidate_kind": "number_concentration",
        "bridge_status": "diagnostic_only_until_composed_operator",
        "vertical_unit": "number concentration; KDM6 and RTTOV cloud optics conventions must be reconciled",
        "notes": "Number concentration may affect cloud optical properties indirectly, not a direct clear-sky RTTOV profile_k variable.",
    },
    {
        "kdm6_namespace": "KDM6AD",
        "kdm6_variable": "nr",
        "rttov_profile_variable": "rain_number_candidate",
        "rttov_candidate_kind": "number_concentration",
        "bridge_status": "diagnostic_only_until_composed_operator",
        "vertical_unit": "number concentration; scattering/particle-size bridge required",
        "notes": "Rain number concentration must feed a particle-size/optical-property bridge before RTTOV comparison.",
    },
    {
        "kdm6_namespace": "KDM6AD",
        "kdm6_variable": "ni",
        "rttov_profile_variable": "ice_number_candidate",
        "rttov_candidate_kind": "number_concentration",
        "bridge_status": "diagnostic_only_until_composed_operator",
        "vertical_unit": "number concentration; scattering/particle-size bridge required",
        "notes": "Ice number concentration is useful for a future microphysics-to-optics bridge, not direct profiles_k validation.",
    },
]


def validate_mapping_table(table: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    """Validate and normalize the KDM6AD-to-RTTOV mapping table."""
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for row_index, row in enumerate(table):
        missing = REQUIRED_KEYS - set(row)
        if missing:
            raise ValueError(f"mapping row {row_index} missing required keys: {sorted(missing)}")
        normalized = {key: str(row[key]) for key in REQUIRED_KEYS}
        variable = normalized["kdm6_variable"]
        if variable in seen:
            raise ValueError(f"duplicate kdm6_variable in mapping table: {variable}")
        seen.add(variable)
        if normalized["bridge_status"] not in VALID_BRIDGE_STATUSES:
            raise ValueError(f"invalid bridge_status for {variable}: {normalized['bridge_status']}")
        if normalized["rttov_candidate_kind"] not in VALID_CANDIDATE_KINDS:
            raise ValueError(f"invalid rttov_candidate_kind for {variable}: {normalized['rttov_candidate_kind']}")
        rows.append({key: normalized[key] for key in sorted(REQUIRED_KEYS)})
    return sorted(rows, key=lambda row: row["kdm6_variable"])


def build_mapping_summary(table: Iterable[dict[str, Any]] = KDM6AD_RTTOV_MAPPING) -> dict[str, Any]:
    """Build a machine-readable mapping summary for docs and later bridge code."""
    rows = validate_mapping_table(table)
    status_counts = Counter(row["bridge_status"] for row in rows)
    kind_counts = Counter(row["rttov_candidate_kind"] for row in rows)
    return {
        "metadata": {
            "source": "kdm6ad-rttov-mapping",
            "science_status": "mapping-design-only",
            "purpose": "Separate KDM6AD internal variables that can enter the current RTTOV14 clear-sky GK2A AMI baseline from variables that require cloud/scattering or optical-property bridges.",
            "current_clear_sky_baseline": "GK2A AMI ami/501 O3+CO2, no hydrometeor/scattering comparison",
        },
        "counts_by_bridge_status": dict(sorted(status_counts.items())),
        "counts_by_candidate_kind": dict(sorted(kind_counts.items())),
        "clear_sky_baseline_variables": [
            row["kdm6_variable"] for row in rows if row["bridge_status"] == "clear_sky_baseline_compatible"
        ],
        "rows": rows,
    }


def write_mapping_summary(output_path: str | Path, table: Iterable[dict[str, Any]] = KDM6AD_RTTOV_MAPPING) -> dict[str, Any]:
    """Write the mapping summary as sorted JSON."""
    summary = build_mapping_summary(table)
    Path(output_path).write_text(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Write KDM6AD-to-RTTOV14 variable mapping summary JSON")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    write_mapping_summary(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
