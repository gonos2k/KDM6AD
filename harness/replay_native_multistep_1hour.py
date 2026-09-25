"""Fixed public replay of the 3,600-second normalized-mp237 ice census.

This checks a complete independently declared event schedule and published
identity receipts. It does not reopen private native NetCDF or infer physical
number units, active ice flux, or correctness of a nonexistent second substep.
"""

from __future__ import annotations

import hashlib
import json
import lzma
from pathlib import Path

from replay_native_multistep_10min import (
    CAPTURE_SOURCE_SHA256, EXECUTABLE_SHA256, INPUT_SHA256,
    NORMALIZED_SOURCE_SHA256, RUNNER_SHA256,
)
from streaming_ice_census import CensusPlan, replay_file


EVIDENCE_NAME = "native_ice_multistep_1hour_2026-09-25.json"
LOG_NAME = "native_ice_census_1hour_rank0_2026-09-25.txt.xz"
PLAN_NAME = "native_ice_1hour_plan_2026-09-25.json"
ADDENDUM_NAME = "native_ice_1hour_control_addendum_2026-09-25.json"
PLAN = CensusPlan(tuple(range(1, 181)), (2, 233), (2, 281), 0)
EXPECTED_COLUMNS = 180 * 280 * 232
ARCHIVE_SHA256 = "f7a4d6666f69b8f217eb5e6c4307f4441dabb46ad9d86e00a0985f432b33c4ad"
RAW_SHA256 = "6ab8eba23cb7234cf330a92418ea95e8205dc10b8e1dfac5fb28fd8933657ef1"
PLAN_SHA256 = "af350b25a75eb373a172d4b4e06ac58404b9c86b0a0ab360b8fb50cc03d51bf3"
ADDENDUM_SHA256 = "81067f39145123ff9ac00f6aea9e46b324b258a183bca0728ab5d20e7e6b7cc4"
HISTORY_SHA256 = "ddf3931dd7bd514d43455b4c83540e00e0cc14c258cbeab40148dbd4e17c639c"
NAMELIST_SHA256 = "a78e448d4db0588c1f5e1b339fa5cbd72deb92d6cca09eef942e0159667ce72c"
TEN_MINUTE_RAW_SHA256 = "f1c78e2275bde538aa55db902dd3633d4f3b0e7c8ee8ec406fc85f22a1ffb4c9"
TEN_MINUTE_RAW_BYTES = 91_065_600
TIMES = ["2025-07-19_00:00:00", "2025-07-19_01:00:00"]
RUN_IDS = {
    "control": "mp237_s4-hour-control_60min_hist60_1x1_20260925_125324_p69506",
    "capture": "mp237_s4-hour-capture_60min_hist60_1x1_20260925_122729_p44174",
}
CAMPAIGN_IDS = {
    "control": "844c90090e9423582a60207984eee9304db920bf2e52d990ccf5475ecb557c15",
    "capture": "a1c3ace40ed2286d925fd9f570a3a7fd1fe604ca5242b95823e0c9496f64a6b7",
}


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_metadata(data: dict) -> None:
    _require(data.get("schema") == "native-ice-multistep-1hour-search-v1",
             "wrong evidence schema")
    plan = data.get("run_plan", {})
    for key, expected in {
        "input_case": "retained canonical 5 km SS",
        "outer_steps": 180, "model_dt_seconds": 20, "horizon_seconds": 3600,
        "history_interval_seconds": 3600, "restart_interval_minutes": 999,
        "mpi_ranks": 1, "threads_per_rank": 1,
        "owned_i_1_based": [2, 233], "owned_j_1_based": [2, 281],
        "candidate_policy": "all owned columns; no posthoc success selection",
        "plan_file": PLAN_NAME, "plan_sha256": PLAN_SHA256,
        "control_addendum_file": ADDENDUM_NAME,
        "control_addendum_sha256": ADDENDUM_SHA256,
    }.items():
        actual = plan.get(key)
        _require(type(actual) is type(expected) and actual == expected,
                 f"fixed one-hour plan changed: {key}")
    baseline = data.get("baseline", {})
    for key, expected in (
        ("executable_sha256", EXECUTABLE_SHA256),
        ("normalized_source_sha256", NORMALIZED_SOURCE_SHA256),
        ("instrumented_source_sha256", CAPTURE_SOURCE_SHA256),
    ):
        _require(baseline.get(key) == expected, f"source/executable changed: {key}")
    runs = data.get("runs", {})
    _require(isinstance(runs, dict) and set(runs) == {"control", "capture"},
             "incomplete control/capture run set")
    for name, run in runs.items():
        _require(run.get("run_id") == RUN_IDS[name]
                 and run.get("campaign_id") == CAMPAIGN_IDS[name],
                 f"{name}: run identity changed")
        _require(run.get("experiment_valid") is True
                 and run.get("model_completed") is True
                 and type(run.get("exit_code")) is int and run.get("exit_code") == 0
                 and run.get("actual_proc_grid") == "1x1",
                 f"{name}: incomplete or wrong-grid run")
        for key, expected in (
            ("canonical_input_sha256", INPUT_SHA256),
            ("wrf_executable_sha256", EXECUTABLE_SHA256),
            ("runner_sha256", RUNNER_SHA256),
            ("effective_namelist_sha256", NAMELIST_SHA256),
            ("history_sha256", HISTORY_SHA256),
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
             "public hour census identity changed")
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
             "recorded complete negative hour census changed")
    _require(census.get("first_10min_raw_prefix_matches_600s_log") is True
             and census.get("first_10min_initial_history_raw_equal") is True,
             "first-ten-minute continuity fact missing")
    terminal = data.get("terminal_ice_snapshot", {})
    for key, expected in (("qice_positive_cells", 240111),
                          ("qnice_positive_cells", 341804),
                          ("qice_and_qnice_positive_cells", 238956)):
        _require(type(terminal.get(key)) is int and terminal.get(key) == expected,
                 f"terminal ice snapshot changed: {key}")
    scope = data.get("scope", {})
    _require(scope.get("actual_native_run") is True
             and scope.get("native_mstep_ge_2_measured") is False
             and scope.get("active_ice_multistep_witness") is False
             and scope.get("physical_number_basis_resolved") is False
             and scope.get("operational_transport_p1_closed") is False
             and type(scope.get("rttov_runs")) is int and scope.get("rttov_runs") == 0,
             "unsupported scientific acceptance claim")


def _first_ten_minute_sha(path: Path) -> str:
    digest = hashlib.sha256()
    remaining = TEN_MINUTE_RAW_BYTES
    with lzma.open(path, "rb") as stream:
        while remaining:
            chunk = stream.read(min(8 * 1024 * 1024, remaining))
            if not chunk:
                raise ValueError("hour archive is shorter than 600-second census")
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.hexdigest()


def replay(evidence_dir: Path | None = None) -> dict[str, object]:
    directory = evidence_dir or Path(__file__).resolve().parent / "evidence"
    data = json.loads((directory / EVIDENCE_NAME).read_text())
    validate_metadata(data)
    _require(_sha(directory / PLAN_NAME) == PLAN_SHA256
             and _sha(directory / ADDENDUM_NAME) == ADDENDUM_SHA256,
             "published plan/addendum changed")
    path = directory / LOG_NAME
    result = replay_file(path, PLAN)
    _require(result["file_sha256"] == ARCHIVE_SHA256,
             "public hour census archive changed")
    audit = result["audit"]
    _require(audit["selected_rows"] == EXPECTED_COLUMNS
             and audit["consumed_rows"] == EXPECTED_COLUMNS
             and audit["mstep_histogram"] == {1: EXPECTED_COLUMNS}
             and audit["first_multistep"] is None,
             "hour census does not match fixed all-one schedule")
    _require(_first_ten_minute_sha(path) == TEN_MINUTE_RAW_SHA256,
             "hour's first 600 s changed from the shorter census")
    return {
        "schema": "native-ice-multistep-1hour-replay-v1",
        "scope": "public event and plan arithmetic plus recorded native run facts only",
        "selected_rows": EXPECTED_COLUMNS,
        "consumed_rows": EXPECTED_COLUMNS,
        "multistep_selected": 0,
        "control_capture_history_recorded_equal": True,
        "native_mstep_ge_2_certified": False,
        "operational_transport_p1_closed": False,
        "netcdf_reopened": False,
    }


if __name__ == "__main__":
    print(json.dumps(replay(), indent=2, sort_keys=True))
