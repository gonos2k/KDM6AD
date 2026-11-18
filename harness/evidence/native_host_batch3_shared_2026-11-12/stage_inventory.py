#!/usr/bin/env python3
"""Inventory the pinned f64 B=1 value capture; no model execution."""

from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path

import stage_compare

HERE = Path(__file__).resolve().parent
CAPTURE = HERE / "raw/stage_compare_f64_baseline.csv.gz"
GZIP_SHA = "e84e020e8c4c219d9e93c3165c5e42cae8f53db1ec8b4fbc7826f6b6609c5649"
CSV_SHA = "49d60ae156212acdf987577ec271f4b5a56a318b5a9ff4829c36419397e29aba"
SAVED = HERE / "stage_inventory.json"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def inventory():
    raw = CAPTURE.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == GZIP_SHA, "baseline gzip SHA-256")
    require(
        hashlib.sha256(gzip.decompress(raw)).hexdigest() == CSV_SHA,
        "baseline CSV SHA-256",
    )
    rows = stage_compare.capture(raw)
    stages = defaultdict(lambda: defaultdict(Counter))
    substeps = defaultdict(set)
    levels = defaultdict(set)
    for row in rows:
        stages[row["stage"]][row["field"]][row["dtype"]] += 1
        substeps[row["stage"]].add(int(row["substep"]))
        levels[row["stage"]].add(int(row["k_zero"]))
    result = {}
    for stage in sorted(stages):
        fields = {
            name: dict(sorted(counts.items()))
            for name, counts in sorted(stages[stage].items())
        }
        result[stage] = {
            "row_count": sum(sum(counts.values()) for counts in fields.values()),
            "field_count": len(fields),
            "fields_by_dtype_count": fields,
            "substeps": sorted(substeps[stage]),
            "k_zero_values": sorted(levels[stage]),
        }
    require(
        len(result) == 51 and sum(x["row_count"] for x in result.values()) == 19656,
        "inventory count",
    )
    # Exact field labels absent from this capture. These are capture-coverage
    # observations, not assertions about absent mathematical dependencies.
    probes = {
        "sedimentation_mass_departure_arrival": [
            ("ice_sedimentation_n1", "applied_out_qi"),
            ("ice_sedimentation_n1", "applied_in_qi"),
            ("fd_main", "applied_out_qr"),
            ("fd_main", "applied_in_qr"),
            ("fd_main", "applied_out_qg"),
            ("fd_main", "applied_in_qg"),
        ],
        "sedimentation_number_all_substeps": [
            ("ice_sedimentation_n2", "applied_out_ni"),
            ("ice_sedimentation_n2", "applied_in_ni"),
            ("fd_main", "applied_out_nr"),
            ("fd_main", "applied_in_nr"),
        ],
        "named_process_applied_mass": [
            ("fd_state_update", "qv_before"),
            ("fd_state_update", "qv_after"),
            ("fd_state_update", "qc_before"),
            ("fd_state_update", "qc_after"),
            ("fd_state_update", "applied_praut"),
            ("fd_state_update", "applied_pracw"),
        ],
        "heat_budget": [
            ("fd_state_update", "temperature_before"),
            ("fd_state_update", "temperature_after"),
            ("fd_state_update", "xlwork2"),
            ("fd_satadj_inner", "pcond"),
            ("fd_satadj_inner", "temperature_after"),
        ],
        "graupel_volume_budget": [
            ("fd_state_update", "brs_before"),
            ("fd_state_update", "brs_after"),
            ("fd_state_update", "dbrs_cold_sum"),
            ("fd_state_update", "dbrs_warm_sum"),
            ("fd_main", "applied_out_brs"),
            ("fd_main", "applied_in_brs"),
        ],
        "precipitation_components_and_applied_export": [
            ("runtime_full_exit", "rain_increment"),
            ("runtime_full_exit", "snow_increment"),
            ("runtime_full_exit", "graupel_increment"),
            ("fd_main", "applied_surface_qr"),
        ],
    }
    gaps = {
        ledger: [
            {"stage": stage, "field": field}
            for stage, field in pairs
            if field not in stages.get(stage, {})
        ]
        for ledger, pairs in probes.items()
    }
    return {
        "schema": "kdm6.native_host_f64_stage_inventory.v1",
        "scope": "one isolated B=1 value-only f64 baseline capture; field presence is not a complete causal graph or a physical budget",
        "capture_gzip_sha256": GZIP_SHA,
        "capture_csv_sha256": CSV_SHA,
        "rows": len(rows),
        "stages_count": len(result),
        "vertical_order": "top first; native level = 39 - k_zero",
        "stage_records": result,
        "ledger_exact_label_gaps": gaps,
        "gaps_scope": "Exact stage/field labels are absent from these captured records; equivalent operands, inferred quantities, other calls and uninstrumented operators are not ruled out.",
    }


def verify():
    computed = inventory()
    require(json.loads(SAVED.read_text()) == computed, "saved inventory mismatch")
    return computed


if __name__ == "__main__":
    result = verify()
    print(
        f"Verified {result['stages_count']} stages and {result['rows']} captured rows; no model executed"
    )
