#!/usr/bin/env python3
"""Replay the seven-run G4 identity, held-out profile, and census evidence.

This validates recorded run identities and complete rank-owned SELECT/CONSUME
censuses. It does not rerun NetCDF physics or derive native mstep from velocity.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from native_execution_contract import parse_census_row, validate_census
from run_ss_case import _namelist_assignments, canonical_input_sha256

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "harness/evidence/native_execution_2026-09-24.json"
SCHEMA = "native-execution-generalization-v1"
I_BOUNDS = (2, 233)
J_BOUNDS = (2, 281)
TIMES = {
    1: "2025-07-19_00:00:00",
    2: "2025-07-19_00:00:20",
    3: "2025-07-19_00:00:40",
}
HELDOUT_RUNS = ("serial", "x-capture", "y-capture", "restart")
HELDOUT_FIELDS = (
    "QCLOUD",
    "QRAIN",
    "QICE",
    "QSNOW",
    "QGRAUP",
    "QNCLOUD",
    "QNRAIN",
    "QNICE",
    "QVAPOR",
    "T",
    "P",
    "PB",
)
MASS_SELECTION_FIELDS = {
    "QCLOUD": "qc",
    "QRAIN": "qr",
    "QICE": "qi",
    "QSNOW": "qs",
    "QGRAUP": "qg",
}
NUMBER_FIELDS = ("QNCLOUD", "QNRAIN", "QNICE")
ORDINARY_INPUTS = {
    ("init", "d01", "wrfinput_d01"),
    ("boundary", "d01", "wrfbdy_d01"),
    ("auxinput24", "d01", "wrfchainp_d01"),
}
RESTART_INPUTS = {
    ("restart", "d01", "wrfrst_d01_2025-07-19_00:00:20"),
    ("boundary", "d01", "wrfbdy_d01"),
    ("auxinput24", "d01", "wrfchainp_d01"),
}

# These schedules and territories are fixed from the launch configuration, not
# recovered from census rows or the evidence's summary counts.
CASE_SPECS: dict[str, dict[str, Any]] = {
    "serial": dict(
        grid="1x1",
        ranks=1,
        steps=(1, 2),
        patches={0: (1, 235, 1, 283)},
        territories={0: (2, 233, 2, 281)},
        capture=True,
    ),
    "x-control": dict(
        grid="2x1",
        ranks=2,
        steps=(1, 2),
        patches={0: (1, 117, 1, 283), 1: (118, 235, 1, 283)},
        territories=None,
        capture=False,
    ),
    "x-capture": dict(
        grid="2x1",
        ranks=2,
        steps=(1, 2),
        patches={0: (1, 117, 1, 283), 1: (118, 235, 1, 283)},
        territories={0: (2, 117, 2, 281), 1: (118, 233, 2, 281)},
        capture=True,
    ),
    "y-control": dict(
        grid="1x2",
        ranks=2,
        steps=(1, 2),
        patches={0: (1, 235, 1, 141), 1: (1, 235, 142, 283)},
        territories=None,
        capture=False,
    ),
    "y-capture": dict(
        grid="1x2",
        ranks=2,
        steps=(1, 2),
        patches={0: (1, 235, 1, 141), 1: (1, 235, 142, 283)},
        territories={0: (2, 233, 2, 141), 1: (2, 233, 142, 281)},
        capture=True,
    ),
    "restart": dict(
        grid="1x1",
        ranks=1,
        steps=(2,),
        patches={0: (1, 235, 1, 283)},
        territories={0: (2, 233, 2, 281)},
        capture=True,
    ),
    "restart-control": dict(
        grid="1x1",
        ranks=1,
        steps=(2,),
        patches={0: (1, 235, 1, 283)},
        territories=None,
        capture=False,
    ),
}

CASE_FILES = {
    "serial": ((0, "native_execution_serial_rank0_2026-09-24.txt.gz"),),
    "x-capture": (
        (0, "native_execution_x-capture_rank0_2026-09-24.txt.gz"),
        (1, "native_execution_x-capture_rank1_2026-09-24.txt.gz"),
    ),
    "y-capture": (
        (0, "native_execution_y-capture_rank0_2026-09-24.txt.gz"),
        (1, "native_execution_y-capture_rank1_2026-09-24.txt.gz"),
    ),
    "restart": ((0, "native_execution_restart_rank0_2026-09-24.txt.gz"),),
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _history_times(steps: tuple[int, ...]) -> list[str]:
    return [TIMES[step] for step in range(min(steps), max(steps) + 2)]


def _input_identity_valid(identity: dict[str, Any], case: str) -> None:
    _require(identity.get("complete") is True, "input identity is incomplete")
    _require(identity.get("declared") is True, "input identity is undeclared")
    _require(bool(identity.get("canonical_sha256")), "missing canonical input hash")
    records = identity.get("records")
    _require(
        isinstance(records, list) and records, "input identity has no file records"
    )
    expected = (
        RESTART_INPUTS if case in ("restart", "restart-control") else ORDINARY_INPUTS
    )
    actual = {
        (record.get("kind"), record.get("domain"), record.get("name"))
        for record in records
    }
    _require(
        len(records) == len(expected) and actual == expected,
        f"{case}: active input record set is incomplete or unexpected",
    )
    for record in records:
        digest = record.get("sha256")
        _require(
            isinstance(digest, str)
            and len(digest) == 64
            and all(c in "0123456789abcdef" for c in digest),
            "invalid input SHA256",
        )
        _require(record.get("status") == "ok", "input file identity status is not ok")
        _require(
            record.get("status_after") == "ok",
            "input file could not be rechecked after run",
        )
        _require(record.get("stable") is True, "input file changed during capture")
        _require(
            record.get("sha256")
            == record.get("sha256_before")
            == record.get("sha256_after"),
            "input file hash changed or is inconsistent",
        )
    _require(
        canonical_input_sha256(identity) == identity["canonical_sha256"],
        f"{case}: canonical input digest does not match its complete records",
    )


def _executable_digest(recorded: str) -> str:
    lines = recorded.splitlines()
    if len(lines) < 4:
        raise ValueError("executable identity lacks before/after proof")
    digest = lines[0].strip()
    _require(lines[1].strip() == f"before {digest}", "executable before hash mismatch")
    _require(lines[2].strip() == f"after  {digest}", "executable after hash mismatch")
    _require(lines[3].strip() == "stable yes", "executable was not stable")
    return digest


def _run_identity(entry: dict[str, Any]) -> dict[str, Any]:
    embedded = entry.get("run_identity")
    _require(isinstance(embedded, dict), "run_identity metadata missing from evidence")
    return embedded


def validate_metadata(data: dict[str, Any]) -> dict[str, Any]:
    """Validate fixed run schedule, provenance flags, comparisons, and profiles."""
    if not __debug__:
        raise RuntimeError("assertions must remain enabled")
    _require(data.get("schema") == SCHEMA, "wrong evidence schema")
    runs = data.get("runs")
    _require(
        isinstance(runs, dict) and set(runs) == set(CASE_SPECS),
        "missing or unexpected run case",
    )
    _require(
        set(data.get("heldout", {})) == set(HELDOUT_RUNS),
        "missing or unexpected held-out run",
    )

    for flag in (
        "operational_fix_applied",
        "physical_number_basis_resolved",
        "accepted_observation_cost",
        "mp337_abi_measured",
        "independent_radiative_accuracy",
    ):
        _require(
            data.get("scope", {}).get(flag) is False,
            f"scope approval flag must remain false: {flag}",
        )
    acceptance = data.get("acceptance", {})
    _require(
        acceptance.get("record_ownership_and_consumption") is True,
        "census gate not recorded true",
    )
    _require(
        acceptance.get("within_configuration_noninterference") is True,
        "noninterference gate not true",
    )
    for flag in (
        "all_decompositions_bitwise_equal",
        "restart_trajectory_bitwise_equal",
        "operational_adoption",
        "physical_number_basis_resolved",
        "accepted_observation_cost",
    ):
        _require(acceptance.get(flag) is False, f"unsupported acceptance flag: {flag}")

    run_ids: dict[str, dict[str, Any]] = {}
    for case, spec in CASE_SPECS.items():
        entry = runs[case]
        _require(
            entry.get("rank_count") == spec["ranks"], f"{case}: rank count mismatch"
        )
        _require(
            entry.get("proc_grid") == spec["grid"], f"{case}: processor grid mismatch"
        )
        _require(
            entry.get("expected_steps") == list(spec["steps"]),
            f"{case}: step schedule mismatch",
        )
        _require(
            entry.get("times") == _history_times(spec["steps"]),
            f"{case}: history times mismatch",
        )
        _require(
            entry.get("configured_patches")
            == {str(k): list(v) for k, v in spec["patches"].items()},
            f"{case}: configured patch map mismatch",
        )
        valid = entry.get("run_valid", {})
        _require(
            valid.get("experiment_valid") is True
            and valid.get("model_completed") is True,
            f"{case}: run was not valid and completed",
        )
        _require(
            valid.get("exit_code") == 0
            and valid.get("actual_proc_grid") == spec["grid"],
            f"{case}: run exit code or actual grid mismatch",
        )
        _require(
            valid.get("requested_proc_grid") == spec["grid"],
            f"{case}: requested grid mismatch",
        )
        _require(
            valid.get("active_input_identity_complete") is True,
            f"{case}: active input identity incomplete",
        )
        identity = entry.get("input_identity", {})
        _input_identity_valid(identity, case)

        files = entry.get("raw_census", [])
        _require(isinstance(files, list), f"{case}: malformed raw-census manifest")
        if spec["capture"]:
            expected_files = CASE_FILES[case]
            _require(
                {(x.get("rank"), x.get("file")) for x in files} == set(expected_files)
                and len(files) == len(expected_files),
                f"{case}: missing or unexpected census rank file",
            )
            _require(
                entry.get("owned_territories")
                == {str(k): list(v) for k, v in spec["territories"].items()},
                f"{case}: ownership territory mismatch",
            )
            _require(
                entry.get("census", {}).get("steps") == list(spec["steps"]),
                f"{case}: recorded census schedule mismatch",
            )
            _require(
                entry.get("census", {}).get("i_bounds") == list(I_BOUNDS)
                and entry.get("census", {}).get("j_bounds") == list(J_BOUNDS),
                f"{case}: recorded census domain mismatch",
            )
        else:
            _require(
                not files and "census" not in entry,
                f"{case}: control run should not contain census records",
            )
            _require(
                "owned_territories" not in entry,
                f"{case}: control should not declare captured ownership",
            )

        run_id = _run_identity(entry)
        _require(
            run_id.get("experiment_valid") is True and run_id.get("exit_code") == 0,
            f"{case}: run identity validity mismatch",
        )
        _require(
            run_id.get("actual_proc_grid") == spec["grid"]
            and run_id.get("requested_proc_grid") == spec["grid"],
            f"{case}: run identity grid mismatch",
        )
        controls = run_id.get("controls", {})
        _require(
            controls.get("input_canonical_sha256") == identity["canonical_sha256"],
            f"{case}: run identity input hash mismatch",
        )
        _require(
            controls.get("np") == spec["ranks"]
            and controls.get("seconds") == 20 * len(spec["steps"]),
            f"{case}: run duration/rank controls mismatch",
        )
        _require(
            controls.get("fixed_dt") is True and controls.get("history_s") == 20,
            f"{case}: timestep/history controls mismatch",
        )
        _require(
            bool(entry.get("effective_namelist_sha256")),
            f"{case}: effective namelist hash missing",
        )
        run_ids[case] = run_id

    # A paired logging control is not enough: decomposition arms must share
    # the same initial/boundary inputs as serial, and restart keeps its forcing.
    selection_proof = data.get("selection_validation", {})
    _require(
        selection_proof.get("selection_recomputed_equal") is True
        and selection_proof.get("recorded_input_has_no_masked_hydrometeor_cells")
        is True,
        "selection validation facts changed",
    )
    _require(
        selection_proof.get("original_selector_sha256")
        == data["selection"]["selector_sha256"],
        "original selector proof mismatch",
    )
    # Pin the recorded revision of this fixed post-run validation, not future
    # versions of the reusable selector. Its bytes are not reopened here.
    _require(
        selection_proof.get("final_selector_sha256")
        == "4952078c757c1208b1ac8a90e919f25a32f565cc3048937b10a07f5467d4fae8",
        "recorded selector validation revision changed",
    )
    serial_identity = runs["serial"]["input_identity"]
    serial_files = {
        (r["kind"], r["domain"], r["name"]): r["sha256"]
        for r in serial_identity["records"]
    }
    _require(
        serial_files[("init", "d01", "wrfinput_d01")]
        == data["selection"]["model_input_sha256"],
        "selector input differs from native initial file",
    )
    for case, entry in runs.items():
        identity = entry["input_identity"]
        if case not in ("restart", "restart-control"):
            _require(
                identity["canonical_sha256"] == serial_identity["canonical_sha256"],
                "decomposition input differs from serial",
            )
        for r in identity["records"]:
            if r["kind"] in ("boundary", "auxinput24"):
                _require(
                    r["sha256"] == serial_files[(r["kind"], r["domain"], r["name"])],
                    "shared boundary/aux input differs",
                )
        text = entry.get("effective_namelist_text")
        _require(
            isinstance(text, str)
            and hashlib.sha256(text.encode()).hexdigest()
            == entry["effective_namelist_sha256"],
            "effective namelist text/hash mismatch",
        )
        without_grid = "\n".join(
            line
            for line in text.splitlines()
            if "nproc_x" not in line and "nproc_y" not in line
        )
        _require(
            hashlib.sha256(without_grid.encode()).hexdigest()
            == run_ids[case]["controls"]["namelist_without_grid_sha256"],
            "namelist excluding grid digest mismatch",
        )
    baseline = _namelist_assignments(runs["serial"]["effective_namelist_text"])
    for case, entry in runs.items():
        actual = _namelist_assignments(entry["effective_namelist_text"])
        changes = {
            k: actual.get(k)
            for k in baseline.keys() | actual.keys()
            if actual.get(k) != baseline.get(k)
        }
        expected = {}
        if case.startswith("x-"):
            expected = {"nproc_x": ["2"], "restart_interval_s": ["0"]}
        elif case.startswith("y-"):
            expected = {"nproc_y": ["2"], "restart_interval_s": ["0"]}
        elif case.startswith("restart"):
            expected = {
                "restart": [".true."],
                "start_second": ["20"],
                "restart_interval_s": ["0"],
                "run_seconds": ["20"],
                "write_hist_at_0h_rst": [".true."],
            }
        _require(changes == expected, "unplanned namelist difference across runs")

    source = data.get("source", {})
    _require(
        source.get("source_sha256")
        == data.get("source_manifest", {}).get("capture_sha256"),
        "capture source hash disagrees with source manifest",
    )
    expected_executable = source.get("executable_sha256")
    _require(bool(expected_executable), "common executable hash missing")
    for case, entry in runs.items():
        _require(
            _executable_digest(entry.get("executable_sha256", ""))
            == expected_executable,
            f"{case}: executable differs from the common native binary",
        )

    # Capture/control pairs share the exact input manifest, executable and
    # namelist excluding processor-grid fields; capture adds logs only.
    for control, capture in (
        ("x-control", "x-capture"),
        ("y-control", "y-capture"),
        ("restart-control", "restart"),
    ):
        left, right = runs[control], runs[capture]
        _require(
            left["input_identity"] == right["input_identity"],
            f"{control}/{capture}: input identities differ",
        )
        _require(
            left["executable_sha256"] == right["executable_sha256"],
            f"{control}/{capture}: executable differs",
        )
        _require(
            left["selection_sha256"] == right["selection_sha256"],
            f"{control}/{capture}: selector differs",
        )
        left_controls, right_controls = (
            run_ids[control]["controls"],
            run_ids[capture]["controls"],
        )
        _require(
            left_controls.get("namelist_without_grid_sha256")
            == right_controls.get("namelist_without_grid_sha256"),
            f"{control}/{capture}: namelist excluding grid differs",
        )
        _require(
            left_controls.get("input_canonical_sha256")
            == right_controls.get("input_canonical_sha256"),
            f"{control}/{capture}: canonical inputs differ",
        )
        _require(
            left.get("effective_namelist_sha256")
            == right.get("effective_namelist_sha256"),
            f"{control}/{capture}: effective namelist differs",
        )

    # Same-configuration histories are the noninterference controls. Different
    # decompositions and restarted continuation remain explicitly unequal.
    for control, capture, comparison in (
        ("x-control", "x-capture", "x_noninterference"),
        ("y-control", "y-capture", "y_noninterference"),
        ("restart-control", "restart", "restart_noninterference"),
    ):
        _require(
            runs[control]["history_sha256"] == runs[capture]["history_sha256"],
            f"{control}/{capture}: history hashes differ",
        )
        _assert_equal_frames(
            data["comparisons"].get(comparison),
            expected_times=runs[capture]["times"],
            label=comparison,
        )

    _assert_equal_frames(
        data["comparisons"].get("retained_normalized_to_serial"),
        expected_times=runs["serial"]["times"],
        label="retained baseline",
    )
    _assert_equal_frames(
        data["comparisons"].get("serial_to_x"),
        expected_times=runs["serial"]["times"],
        label="serial/x decomposition comparison",
        expect_equal=(True, False, False),
        expected_difference_counts=(0, 28, 71),
    )
    _assert_equal_frames(
        data["comparisons"].get("serial_to_y"),
        expected_times=runs["serial"]["times"],
        label="serial/y decomposition comparison",
    )
    _assert_equal_frames(
        data["comparisons"].get("continuous_to_restart"),
        expected_times=[TIMES[2], TIMES[3]],
        label="continuous/restart comparison",
        expect_equal=(False, False),
        expected_difference_counts=(7, 60),
    )

    profile_summary = _validate_heldout(data["heldout"], data.get("selection", {}))
    checkpoint_summary = _validate_checkpoint_metadata(data)
    return {
        "run_cases": len(runs),
        "census_capture_cases": sum(spec["capture"] for spec in CASE_SPECS.values()),
        "within_configuration_pairs": 3,
        "heldout_profiles": profile_summary,
        "checkpoint": checkpoint_summary,
        "all_decompositions_bitwise_equal": False,
        "restart_trajectory_bitwise_equal": False,
        "number_basis_resolved": False,
        "observation_cost_accepted": False,
    }


def _assert_equal_frames(
    frames: Any,
    *,
    expected_times: list[str],
    label: str,
    expect_equal: tuple[bool, ...] | None = None,
    expected_difference_counts: tuple[int, ...] | None = None,
) -> None:
    _require(
        isinstance(frames, list) and [x.get("time") for x in frames] == expected_times,
        f"{label}: comparison times or frame count mismatch",
    )
    if expect_equal is None:
        expect_equal = tuple(True for _ in frames)
    _require(
        len(expect_equal) == len(frames), f"{label}: comparison expectations malformed"
    )
    for index, (frame, same) in enumerate(zip(frames, expect_equal)):
        _require(
            frame.get("checked_numeric_fields") == 253,
            f"{label}: numeric field count mismatch",
        )
        _require(
            frame.get("raw_bit_equal") is same,
            f"{label}: equality classification mismatch at {index}",
        )
        differences = frame.get("different_fields")
        _require(isinstance(differences, list), f"{label}: difference list malformed")
        names = [x.get("name") for x in differences]
        _require(
            all(isinstance(name, str) and name for name in names)
            and len(names) == len(set(names)),
            f"{label}: differing-field names must be unique",
        )
        _require(
            (not differences) if same else bool(differences),
            f"{label}: equality flag contradicts difference list",
        )
        if expected_difference_counts is not None:
            _require(
                len(differences) == expected_difference_counts[index],
                f"{label}: differing-field count mismatch at {index}",
            )


def _validate_heldout(heldout: dict[str, Any], selection: dict[str, Any]) -> int:
    selected = {
        row["category"]: row
        for row in selection.get("categories", [])
        if row.get("selected") is not None
    }
    _require(
        len(selected) == 5,
        "held-out selection must contain five preselected categories",
    )
    expected_times = {
        "serial": [TIMES[1], TIMES[2], TIMES[3]],
        "x-capture": [TIMES[1], TIMES[2], TIMES[3]],
        "y-capture": [TIMES[1], TIMES[2], TIMES[3]],
        "restart": [TIMES[2], TIMES[3]],
    }
    by_run: dict[str, dict[tuple[str, str], dict[str, Any]]] = {}
    n_profiles = 0
    for run in HELDOUT_RUNS:
        rows = heldout[run]
        _require(
            len(rows) == 5 * len(expected_times[run]),
            f"{run}: held-out row count mismatch",
        )
        lookup = {}
        for row in rows:
            category, timestamp = row["category"], row["time"]
            key = category, timestamp
            _require(
                category in selected and key not in lookup,
                f"{run}: duplicate/unknown profile key",
            )
            _require(
                row["i"] == selected[category]["selected"]["i"]
                and row["j"] == selected[category]["selected"]["j"],
                f"{run}: profile coordinate differs from frozen selection",
            )
            values = row.get("values", {})
            _require(
                set(values) == set(HELDOUT_FIELDS) | {"RAINNC"},
                f"{run}: profile fields mismatch",
            )
            for field in HELDOUT_FIELDS:
                vector = values[field]
                _require(
                    isinstance(vector, list) and len(vector) == 39,
                    f"{run}: {field} profile is not 39 levels",
                )
            _require(
                isinstance(values["RAINNC"], (int, float)),
                f"{run}: RAINNC must be scalar",
            )
            lookup[key] = row
            n_profiles += 1
        _require(
            {time for _category, time in lookup} == set(expected_times[run]),
            f"{run}: held-out history frames mismatch",
        )
        for timestamp in expected_times[run]:
            _require(
                {category for category, time in lookup if time == timestamp}
                == set(selected),
                f"{run}: incomplete selected category frame at {timestamp}",
            )
        by_run[run] = lookup

    # The recorded time-zero held-out condensates agree with the frozen input
    # vectors; the initial number fields are zero before host initialization.
    for run in ("serial", "x-capture", "y-capture"):
        for category, selected_row in selected.items():
            values = by_run[run][category, TIMES[1]]["values"]
            profile = selected_row["input_profiles"]
            for field, source in MASS_SELECTION_FIELDS.items():
                _require(
                    values[field] == profile[source],
                    f"{run}: t0 {field} differs from frozen input",
                )
            for field in NUMBER_FIELDS:
                _require(
                    all(value == 0 for value in values[field]),
                    f"{run}: initial {field} is nonzero",
                )

    # The 5 selected profiles at each common frame remain bit-identical across
    # both MPI layouts, even though the full-domain x-layout comparison differs.
    for run in ("x-capture", "y-capture"):
        for timestamp in expected_times[run]:
            for category in selected:
                _require(
                    by_run[run][category, timestamp]["values"]
                    == by_run["serial"][category, timestamp]["values"],
                    f"{run}: selected profile differs from serial at {timestamp}/{category}",
                )

    # Restart begins from the recorded 20-s checkpoint; its selected profiles
    # at 20 s must match the uninterrupted serial frame at that same time.
    for category in selected:
        _require(
            by_run["restart"][category, TIMES[2]]["values"]
            == by_run["serial"][category, TIMES[2]]["values"],
            f"restart: selected profile at checkpoint time differs for {category}",
        )
    restart_differences = sum(
        by_run["restart"][category, TIMES[3]]["values"]
        != by_run["serial"][category, TIMES[3]]["values"]
        for category in selected
    )
    _require(
        restart_differences == 5,
        "restart continuation must expose the five selected-profile differences",
    )
    return {
        "records": n_profiles,
        "selected_profiles": len(selected),
        "mpi_layout_frames_bitwise_equal": True,
        "restart_checkpoint_frame_bitwise_equal": True,
        "restart_continuation_profiles_different_at_40s": restart_differences,
    }


def _validate_checkpoint_metadata(data: dict[str, Any]) -> dict[str, Any]:
    checkpoint = data.get("checkpoint", {})
    restart = data["runs"]["restart"]
    record = restart["input_identity"]["records"][0]
    expected_name = "wrfrst_d01_2025-07-19_00:00:20"
    _require(
        checkpoint.get("times") == [TIMES[2]], "checkpoint time is not the 20-s frame"
    )
    _require(
        checkpoint.get("parent_run") == "serial"
        and checkpoint.get("child_run") == "restart",
        "checkpoint parent/child attribution mismatch",
    )
    _require(
        record.get("kind") == "restart" and record.get("name") == expected_name,
        "restart input is not the selected 20-s checkpoint",
    )
    boundary_times = checkpoint.get("boundary_times", [])
    _require(
        isinstance(boundary_times, list) and len(boundary_times) >= 2,
        "boundary interval metadata missing",
    )
    dates = [datetime.strptime(t, "%Y-%m-%d_%H:%M:%S") for t in boundary_times]
    _require(
        all(a < b for a, b in zip(dates, dates[1:])), "boundary times not increasing"
    )
    begin = datetime.strptime(TIMES[2], "%Y-%m-%d_%H:%M:%S")
    end = datetime.strptime(TIMES[3], "%Y-%m-%d_%H:%M:%S")
    _require(
        any(a <= begin and end < b for a, b in zip(dates, dates[1:])),
        "boundary interval does not bracket restart window",
    )
    # Immutable metadata receipt for this checkpoint. This checks consistency,
    # not independent reconstruction of private NetCDF alarm state.
    alarm_digest = hashlib.sha256(
        json.dumps(
            checkpoint.get("attributes"), sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    _require(
        alarm_digest
        == "4b8c667c8fd9c449aacdfce13123456c5777edf29650d420391884a777deb40a",
        "checkpoint alarm metadata receipt changed",
    )
    digest = checkpoint.get("sha256")
    _require(bool(digest), "checkpoint hash missing")
    _require(
        record.get("sha256")
        == record.get("sha256_before")
        == record.get("sha256_after")
        == digest
        and record.get("stable") is True,
        "checkpoint hash before/after mismatch",
    )
    return {"time": TIMES[2], "sha256": digest, "bytes_reopened": False}


def _archive_rows(
    *,
    path: Path,
    rank: int,
    metadata: dict[str, Any],
) -> Iterable[str]:
    if not path.is_file():
        raise ValueError(f"census file missing: {path.name}")
    if _sha256_file(path) != metadata.get("gzip_sha256"):
        raise ValueError(f"compressed census hash mismatch: {path.name}")
    raw_hash = hashlib.sha256()
    count = 0
    try:
        with gzip.open(path, "rb") as stream:
            for raw_line in stream:
                raw_hash.update(raw_line)
                count += 1
                try:
                    text = raw_line.decode("ascii").strip()
                except UnicodeDecodeError as exc:
                    raise ValueError(f"non-ASCII census line: {path.name}") from exc
                if not text:
                    raise ValueError(f"blank census row: {path.name}")
                event = parse_census_row(text)
                if event is None or event.rank != rank:
                    raise ValueError(f"row rank differs from archive rank: {path.name}")
                yield text
    except (gzip.BadGzipFile, EOFError, OSError) as exc:
        raise ValueError(f"corrupt gzip census archive: {path.name}") from exc
    if count != metadata.get("records"):
        raise ValueError(f"record count mismatch: {path.name}")
    if raw_hash.hexdigest() != metadata.get("raw_sha256"):
        raise ValueError(f"uncompressed census hash mismatch: {path.name}")


def replay(
    data: dict[str, Any] | None = None,
    *,
    evidence_dir: Path = EVIDENCE.parent,
) -> dict[str, Any]:
    """Validate recorded run proof and replay all four capture census schedules."""
    if data is None:
        data = json.loads(EVIDENCE.read_text())
    metadata = validate_metadata(data)
    results = {}
    for case, spec in CASE_SPECS.items():
        if not spec["capture"]:
            continue
        manifest = data["runs"][case]["raw_census"]
        by_rank = {row["rank"]: row for row in manifest}
        records = (
            row
            for rank, name in CASE_FILES[case]
            for row in _archive_rows(
                path=evidence_dir / name,
                rank=rank,
                metadata=by_rank[rank],
            )
        )
        output = validate_census(
            records,
            steps=spec["steps"],
            i_bounds=I_BOUNDS,
            j_bounds=J_BOUNDS,
            rank_count=spec["ranks"],
            rank_territories=spec["territories"],
        )
        _require(
            output["min_selected_mstep"] == output["max_selected_mstep"] == 1,
            f"{case}: expected the recorded all-one mstep selection",
        )
        declared = data["runs"][case]["census"]
        for key in (
            "selected_columns",
            "consumer_rows",
            "min_selected_mstep",
            "max_selected_mstep",
            "rank_count",
            "steps",
            "i_bounds",
            "j_bounds",
        ):
            _require(
                output[key] == declared.get(key),
                f"{case}: declared census summary mismatch: {key}",
            )
        results[case] = output

    checkpoint = _validate_checkpoint_metadata(data)
    return {
        "schema": "native-execution-replay-v1",
        "scope": "recorded run identities, selected profiles, and complete census only",
        "metadata": metadata,
        "census": results,
        "checkpoint": checkpoint,
        "same_physics_across_decompositions": False,
        "restart_equals_continuous_trajectory": False,
        "mstep_independently_recomputed": False,
        "netcdf_reopened": False,
        "operational_adoption": False,
    }


if __name__ == "__main__":
    print(json.dumps(replay(), indent=2, sort_keys=True))
