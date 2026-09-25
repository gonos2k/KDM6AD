"""Fixed-case arithmetic replay for the 10-minute normalized-mp237 census.

The independently declared 30-step/64,960-column schedule lives in code,
not in the received metadata. This verifies the public compressed event log
and recorded provenance consistency; it does not reopen private NetCDF or
independently rerun the native host.
"""

from __future__ import annotations

import json
from pathlib import Path

from streaming_ice_census import CensusPlan, replay_file


EVIDENCE_NAME = "native_ice_multistep_10min_2026-09-25.json"
LOG_NAME = "native_ice_census_10min_rank0_2026-09-25.txt.xz"
PLAN = CensusPlan(tuple(range(1, 31)), (2, 233), (2, 281), 0)
EXPECTED_COLUMNS = 30 * 280 * 232
ARCHIVE_SHA256 = "7f35dd1ccc4cc61ecb68198350472f44014fb7d0735d4483c6cf4756b2f5ffb6"
RAW_SHA256 = "f1c78e2275bde538aa55db902dd3633d4f3b0e7c8ee8ec406fc85f22a1ffb4c9"
EXECUTABLE_SHA256 = "799e389e4a5ae3e032607cb4bba59d881184d74798e90e63ee77f426381d6e3c"
NORMALIZED_SOURCE_SHA256 = "405f543447b4185847d9615827b478e7b6c90064ca02b7226e4acfa7502a63c8"
CAPTURE_SOURCE_SHA256 = "d362bc846b30119cc0b4f14f2e5088f9ab7c3e40205dde641aba83fb5a75e5d2"
RUNNER_SHA256 = "175ade71058672b957d565ef88ffd7925bc7d74dfe559c36aaec61fa8de0d96e"
INPUT_SHA256 = "12e132ecefa9e0f7e0a0bd67d57353ec3a7ec113ab1b43121474340293125fdf"
HISTORY_SHA256 = "f1a45c7b8293994ce17fb6a7c1699f454dbb9e03f3a46cae3c269eac7efaf963"
NAMELIST_SHA256 = "2078469623770e6a8b9a7a86b6a456ea3f8f8ef26c67c59acea07d4adab4eaa2"
TIMES = ["2025-07-19_00:00:00", "2025-07-19_00:10:00"]
RUN_IDS = {
    "control": "mp237_s4-control_10min_hist10_1x1_20260925_120250_p1878",
    "capture": "mp237_s4-capture_10min_hist10_1x1_20260925_120747_p5313",
}
CAMPAIGN_IDS = {
    "control": "f7c4160a600c6578a8eefe3e20e7305b0d57f1b946d80f0fd9f956ba4992565b",
    "capture": "92d68dd81dd777ee587f020013a6df0ac29981f791631260c931b7f863b2a5e4",
}


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def validate_metadata(data: dict) -> None:
    _require(data.get("schema") == "native-ice-multistep-search-v1", "wrong schema")
    plan = data.get("run_plan", {})
    for key, expected in {
        "outer_steps": 30, "model_dt_seconds": 20, "horizon_seconds": 600,
        "history_interval_seconds": 600, "restart_interval_minutes": 999,
        "mpi_ranks": 1, "threads_per_rank": 1,
        "owned_i_1_based": [2, 233], "owned_j_1_based": [2, 281],
        "input_case": "retained canonical 5 km SS",
        "candidate_policy": "all owned columns; no posthoc success selection",
    }.items():
        actual = plan.get(key)
        _require(type(actual) is type(expected) and actual == expected,
                 f"fixed run plan changed: {key}")
    baseline = data.get("baseline", {})
    for key, expected in (
        ("executable_sha256", EXECUTABLE_SHA256),
        ("normalized_source_sha256", NORMALIZED_SOURCE_SHA256),
        ("instrumented_source_sha256", CAPTURE_SOURCE_SHA256),
    ):
        _require(baseline.get(key) == expected, f"baseline source/executable changed: {key}")
    runs = data.get("runs", {})
    _require(isinstance(runs, dict) and set(runs) == {"control", "capture"},
             "missing or unexpected native run")
    for name, run in runs.items():
        _require(run.get("run_id") == RUN_IDS[name]
                 and run.get("campaign_id") == CAMPAIGN_IDS[name],
                 f"{name}: recorded run identity changed")
        _require(run.get("experiment_valid") is True
                 and run.get("model_completed") is True
                 and type(run.get("exit_code")) is int and run.get("exit_code") == 0
                 and run.get("actual_proc_grid") == "1x1",
                 f"{name}: incomplete or wrong-grid native run")
        for key, expected in (
            ("canonical_input_sha256", INPUT_SHA256),
            ("wrf_executable_sha256", EXECUTABLE_SHA256),
            ("runner_sha256", RUNNER_SHA256),
            ("history_sha256", HISTORY_SHA256),
            ("effective_namelist_sha256", NAMELIST_SHA256),
            ("history_times", TIMES),
        ):
            _require(run.get(key) == expected, f"{name}: recorded {key} changed")
    noninterference = data.get("noninterference", {})
    for key in ("same_input_identity", "same_executable", "same_history_sha256",
                "times_equal", "raw_numeric_field_byte_equal"):
        _require(noninterference.get(key) is True,
                 f"noninterference fact missing: {key}")
    _require(type(noninterference.get("numeric_field_count")) is int
             and noninterference.get("numeric_field_count") == 253,
             "noninterference field universe changed")
    census = data.get("census", {})
    _require(census.get("file") == LOG_NAME
             and census.get("compressed_sha256") == ARCHIVE_SHA256
             and census.get("raw_sha256") == RAW_SHA256,
             "fixed public census file/hash changed")
    expected_audit = {
        "selected_rows": EXPECTED_COLUMNS,
        "consumed_rows": EXPECTED_COLUMNS,
        "expected_columns": EXPECTED_COLUMNS,
        "multistep_selected": 0,
        "maximum_mstep": 1,
        "mstep_histogram": {"1": EXPECTED_COLUMNS},
        "first_multistep": None,
    }
    _require(census.get("audit") == expected_audit,
             "recorded complete negative census changed")
    scope = data.get("scope", {})
    _require(scope.get("actual_native_run") is True
             and scope.get("native_mstep_ge_2_measured") is False
             and scope.get("active_ice_multistep_witness") is False
             and scope.get("physical_number_basis_resolved") is False
             and scope.get("operational_transport_p1_closed") is False
             and type(scope.get("rttov_runs")) is int
             and scope.get("rttov_runs") == 0,
             "unsupported scientific acceptance claim")


def replay(evidence_dir: Path | None = None) -> dict[str, object]:
    directory = evidence_dir or Path(__file__).resolve().parent / "evidence"
    data = json.loads((directory / EVIDENCE_NAME).read_text())
    validate_metadata(data)
    result = replay_file(directory / LOG_NAME, PLAN)
    _require(result["file_sha256"] == ARCHIVE_SHA256,
             "public census archive changed")
    _require(result["audit"]["selected_rows"] == EXPECTED_COLUMNS
             and result["audit"]["consumed_rows"] == EXPECTED_COLUMNS
             and result["audit"]["multistep_selected"] == 0
             and result["audit"]["maximum_mstep"] == 1
             and result["audit"]["first_multistep"] is None,
             "executed census differs from bounded negative report")
    return {
        "schema": "native-ice-multistep-10min-replay-v1",
        "scope": "public event arithmetic and recorded run identities only",
        "selected_rows": EXPECTED_COLUMNS,
        "consumed_rows": EXPECTED_COLUMNS,
        "multistep_selected": 0,
        "native_mstep_ge_2_certified": False,
        "operational_transport_p1_closed": False,
        "netcdf_reopened": False,
    }


if __name__ == "__main__":
    print(json.dumps(replay(), indent=2, sort_keys=True))
