"""Replay compact S10 A/B events; private artifacts are optional verification.

The public path checks code-pinned event/package receipts without requiring
local model binaries or histories. ``--verify-private`` additionally reopens
the retained local artifacts. Neither mode approves either physics policy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from replay_progb_validity import (
    PROGB_CALL_CONTEXTS,
    RHO_CONSUMER_ID_CONTRACT,
    parse_event_lines,
    validate_events,
)

SHAPE_WIDTH = 19  # 8 integer keys/flags, then 11 defined REAL values.
VOLUME_WIDTH = 13  # 8 integer keys/action, then 5 REAL values.
SELECTED_I = (113, 115)
LEVELS = range(1, 40)
RHO_MID_F32 = struct.unpack(">f", struct.pack(">f", 400.0))[0]

# Captured event payload anchors from the four retained native shadow runs.
# These are code constants, independent of the mutable JSON evidence manifest.
NATIVE_CAPTURE_GOLDENS: dict[tuple[str, str], dict[str, Any]] = {
    ("mp37", "retention"): {
        "payload_sha256": "53ccfead2fe0a3db2ee02088840a5bb47ad2b8d2dbfc5eb180e53b0ce9d33224",
        "event_count": 6924,
        "tag_counts": {"S10CMG": 624, "S10DIAG": 78, "S10PB": 624, "S10RHO": 212,
                       "S10SCAN": 1974, "S10SHAPE": 631, "S10SLP": 624,
                       "S10TRACE": 763, "S10TRS": 763, "S10VOL": 631},
        "rho_key_sha256": "745fc1c0b9c9ff392f1e88c32c0e6f82b9d8030c8ca9963de5ed66aa6b7b64ed",
        "rho_row_count": 212,
    },
    ("mp37", "midpoint"): {
        "payload_sha256": "295c8471873539d6197a3484cf949ec41ecd9cdb5bde118e692b61d444d050fa",
        "event_count": 6812,
        "tag_counts": {"S10CMG": 624, "S10DIAG": 78, "S10PB": 624, "S10RHO": 212,
                       "S10SCAN": 1974, "S10SHAPE": 631, "S10SLP": 624,
                       "S10TRACE": 707, "S10TRS": 707, "S10VOL": 631},
        "rho_key_sha256": "745fc1c0b9c9ff392f1e88c32c0e6f82b9d8030c8ca9963de5ed66aa6b7b64ed",
        "rho_row_count": 212,
    },
    ("mp237", "retention"): {
        "payload_sha256": "6b23c49c636dedf3fb9009b72a59a45dcfd137423e7123123d0b2d73965d52c6",
        "event_count": 6940,
        "tag_counts": {"S10CMG": 624, "S10DIAG": 78, "S10PB": 624, "S10RHO": 212,
                       "S10SCAN": 1974, "S10SHAPE": 631, "S10SLP": 624,
                       "S10TRACE": 771, "S10TRS": 771, "S10VOL": 631},
        "rho_key_sha256": "745fc1c0b9c9ff392f1e88c32c0e6f82b9d8030c8ca9963de5ed66aa6b7b64ed",
        "rho_row_count": 212,
    },
    ("mp237", "midpoint"): {
        "payload_sha256": "e9a80474569c4b6026c3d3407ac426c72eaacffb867986c8288000152461e9b6",
        "event_count": 6820,
        "tag_counts": {"S10CMG": 624, "S10DIAG": 78, "S10PB": 624, "S10RHO": 212,
                       "S10SCAN": 1974, "S10SHAPE": 631, "S10SLP": 624,
                       "S10TRACE": 711, "S10TRS": 711, "S10VOL": 631},
        "rho_key_sha256": "745fc1c0b9c9ff392f1e88c32c0e6f82b9d8030c8ca9963de5ed66aa6b7b64ed",
        "rho_row_count": 212,
    },
}
NATIVE_REPLAY_PACKAGE_SHA256 = "3a8a9b2d425c290419b8e7dc38412b4c4dad535db9c74bc28c9079cfbaf4941c"


def _event_payload(raw: bytes) -> tuple[list[str], bytes, Counter[str]]:
    lines = raw.decode("utf-8").splitlines()
    events = [line for line in lines if line.split() and line.split()[0].startswith("S10")]
    payload = ("\n".join(events) + ("\n" if events else "")).encode("utf-8")
    counts = Counter(line.split()[0] for line in events)
    return lines, payload, counts


def _rho_key_sha256(events: list[str]) -> tuple[int, str]:
    keys = []
    for line_no, line in enumerate(events, 1):
        fields = line.split()
        if not fields or fields[0] != "S10RHO":
            continue
        if len(fields) != 11:
            raise ValueError(f"event line {line_no}: malformed S10RHO key width")
        try:
            key = tuple(int(value, 10) for value in fields[1:9])
        except ValueError as exc:
            raise ValueError(f"event line {line_no}: malformed S10RHO key") from exc
        keys.append(key)
    if len(set(keys)) != len(keys):
        raise ValueError("S10RHO event stream contains duplicate consumer keys")
    serialized = "\n".join(" ".join(map(str, key)) for key in sorted(keys))
    if keys:
        serialized += "\n"
    return len(keys), hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def validate_capture_integrity(raw: bytes, manifest: dict[str, Any],
                               scheme: str, policy: str, *,
                               verify_raw_sha: bool = False) -> list[str]:
    """Check code-pinned event completeness before any semantic replay."""
    key = (scheme, policy)
    if key not in NATIVE_CAPTURE_GOLDENS:
        raise ValueError(f"no code-pinned native capture for {scheme}/{policy}")
    matching = [arm for arm in manifest.get("arms", [])
                if arm.get("scheme") == scheme and arm.get("policy") == policy]
    if len(matching) != 1:
        raise ValueError(f"manifest must contain one {scheme}/{policy} arm")
    stream = matching[0].get("event_stream")
    if not isinstance(stream, dict):
        raise ValueError("manifest is missing event_stream receipt")
    if verify_raw_sha and hashlib.sha256(raw).hexdigest() != stream.get("sha256"):
        raise ValueError("raw event file SHA-256 differs from manifest")

    lines, payload, counts = _event_payload(raw)
    expected = NATIVE_CAPTURE_GOLDENS[key]
    payload_sha = hashlib.sha256(payload).hexdigest()
    tag_counts = dict(sorted(counts.items()))
    rho_count, rho_sha = _rho_key_sha256([line for line in lines
                                          if line.split() and line.split()[0].startswith("S10")])
    actual = {"payload_sha256": payload_sha, "event_count": len(payload.decode().splitlines()),
              "tag_counts": tag_counts, "rho_key_sha256": rho_sha,
              "rho_row_count": rho_count}
    if not verify_raw_sha and raw != payload:
        raise ValueError("public event fixture contains bytes outside the captured S10 payload")
    manifest_fields = {
        "payload_sha256": "event_payload_sha256",
        "event_count": "event_record_count",
        "tag_counts": "event_record_counts",
        "rho_key_sha256": "rho_key_sha256",
        "rho_row_count": "rho_row_count",
    }
    for field, expected_value in expected.items():
        if actual[field] != expected_value:
            raise ValueError(f"raw event payload {field} differs from code-pinned {scheme}/{policy} golden")
        if stream.get(manifest_fields[field]) != expected_value:
            raise ValueError(f"manifest event_stream {field} differs from code-pinned {scheme}/{policy} golden")
    return lines


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def validate_replay_package(manifest: dict[str, Any], plan: dict[str, Any],
                            scheme: str, policy: str,
                            events_path: Path | None = None, *,
                            verify_artifacts: bool = False) -> tuple[dict[str, Any], bytes]:
    """Check public receipts; optionally reopen every retained private artifact."""
    package = manifest.get("replay_package")
    plan_package = plan.get("replay_package")
    if not isinstance(package, dict) or package != plan_package:
        raise ValueError("native-results and run-plan replay_package receipts differ")
    package_sha = _canonical_sha256(package)
    if (package_sha != NATIVE_REPLAY_PACKAGE_SHA256 or
            manifest.get("replay_package_sha256") != NATIVE_REPLAY_PACKAGE_SHA256 or
            plan.get("replay_package_sha256") != NATIVE_REPLAY_PACKAGE_SHA256):
        raise ValueError("replay_package differs from the code-pinned four-arm run receipt")

    package_arms = package.get("arms", {})
    expected_arm_keys = {"mp37/retention", "mp37/midpoint",
                         "mp237/retention", "mp237/midpoint"}
    if set(package_arms) != expected_arm_keys:
        raise ValueError("replay_package does not contain the fixed four-arm universe")
    if plan.get("run_controls") != package.get("run_controls") or \
            plan.get("common_inputs") != package.get("common_inputs"):
        raise ValueError("run plan controls or retained inputs differ from replay_package")
    plan_arms = plan.get("arms", [])
    result_arms = manifest.get("arms", [])
    if len(plan_arms) != 4 or len(result_arms) != 4:
        raise ValueError("native-results and run plan must each contain four arms")

    expected_flat_runs = []
    for arm_key in sorted(expected_arm_keys):
        arm = package_arms[arm_key]
        for mode in ("control", "capture"):
            run = arm["runs"][mode]
            expected_flat_runs.append({
                "scheme": arm["scheme"], "policy": arm["policy"], "mode": mode,
                "run_id": run["run_id"], "run_path": run["run_path"],
                "experiment_valid": run["experiment_valid"],
                "history_path": run["history_path"], "history_sha256": run["history_sha256"],
                "stdout_path": run["event_path"],
                "executable_sha256": run["executable_sha256"],
                "run_identity_path": run["run_identity_path"],
            })
    flat_runs = manifest.get("runs")
    if not isinstance(flat_runs, list) or len(flat_runs) != 8:
        raise ValueError("native-results flat run receipt must contain eight records")
    if sorted(flat_runs, key=lambda r: (r.get("scheme"), r.get("policy"), r.get("mode"))) != \
            sorted(expected_flat_runs,
                   key=lambda r: (r.get("scheme"), r.get("policy"), r.get("mode"))):
        raise ValueError("native-results flat run list differs from the code-pinned replay package")

    for arm_key in sorted(expected_arm_keys):
        arm = package_arms[arm_key]
        scheme_name, policy_name = arm_key.split("/", 1)
        plan_matches = [x for x in plan_arms
                        if x.get("scheme") == scheme_name and x.get("policy") == policy_name]
        result_matches = [x for x in result_arms
                          if x.get("scheme") == scheme_name and x.get("policy") == policy_name]
        if len(plan_matches) != 1 or len(result_matches) != 1:
            raise ValueError(f"missing/duplicate plan or result arm {arm_key}")
        plan_arm, result_arm = plan_matches[0], result_matches[0]

        expected_plan = {
            "scheme": arm["scheme"], "mp_physics": arm["mp_physics"],
            "policy": arm["policy"], "executable_path": arm["executable_path"],
            "executable_sha256": arm["executable_sha256"],
        }
        for field, expected_value in expected_plan.items():
            if plan_arm.get(field) != expected_value:
                raise ValueError(f"run plan {arm_key} {field} differs from replay_package")
        for mode in ("control", "capture"):
            run = arm["runs"][mode]
            plan_run = plan_arm.get(mode, {})
            result_run = result_arm.get(mode, {})
            for field, expected_value in {
                "case_path": run["case_path"],
                "effective_namelist_sha256": arm["effective_namelist_sha256"],
                "executable_sha256": arm["executable_sha256"],
                "input_sha256": arm["input_sha256"],
                "logging_env": run["logging_env"],
            }.items():
                if plan_run.get(field) != expected_value:
                    raise ValueError(f"run plan {arm_key}/{mode} {field} differs from replay_package")
            for field in ("run_id", "run_path", "history_path", "history_sha256",
                          "executable_sha256", "experiment_valid"):
                if result_run.get(field) != run[field]:
                    raise ValueError(f"native result {arm_key}/{mode} {field} differs from replay_package")
            if run["run_id"] != Path(run["run_path"]).name:
                raise ValueError(f"run ID/path mismatch for {arm_key}/{mode}")
            if not run["experiment_valid"].get("experiment_valid") or \
                    run["experiment_valid"].get("exit_code") != 0 or \
                    run["experiment_valid"].get("actual_proc_grid") != "1x1":
                raise ValueError(f"invalid native run receipt for {arm_key}/{mode}")
            if mode == "capture" and result_run.get("stdout_path") != run.get("event_path"):
                raise ValueError(f"capture event path mismatch for {arm_key}")

            if verify_artifacts:
                case = Path(run["case_path"])
                exe = Path(arm["executable_path"])
                if hashlib.sha256(exe.read_bytes()).hexdigest() != arm["executable_sha256"]:
                    raise ValueError(f"executable file hash mismatch for {arm_key}")
                nml = case / "s10_policy_effective_namelist.input"
                if hashlib.sha256(nml.read_bytes()).hexdigest() != arm["effective_namelist_sha256"]:
                    raise ValueError(f"effective namelist hash mismatch for {arm_key}/{mode}")
                for name, expected_hash in arm["input_sha256"].items():
                    if hashlib.sha256((case / name).read_bytes()).hexdigest() != expected_hash:
                        raise ValueError(f"input hash mismatch for {arm_key}/{mode}/{name}")
                history = Path(run["history_path"])
                if hashlib.sha256(history.read_bytes()).hexdigest() != run["history_sha256"]:
                    raise ValueError(f"history file hash mismatch for {arm_key}/{mode}")
                run_dir = Path(run["run_path"])
                if (run_dir / "namelist.input").read_bytes() != nml.read_bytes():
                    raise ValueError(f"executed namelist differs from the predeclared namelist for {arm_key}/{mode}")
                actual_inputs = json.loads((run_dir / "input_sha256.json").read_text(encoding="utf-8"))
                actual_input_records = {
                    row["name"]: row["sha256"] for row in actual_inputs.get("records", [])
                    if row.get("domain") == "d01"
                }
                if (not actual_inputs.get("complete") or
                        actual_input_records != arm["input_sha256"]):
                    raise ValueError(f"run input receipt mismatch for {arm_key}/{mode}")
                exe_receipt = (run_dir / "wrf_exe_sha256").read_text().splitlines()
                if len(exe_receipt) < 4 or exe_receipt[0].strip() != arm["executable_sha256"] or \
                        "before " + arm["executable_sha256"] != exe_receipt[1].strip() or \
                        "after  " + arm["executable_sha256"] != exe_receipt[2].strip() or \
                        exe_receipt[3].strip() != "stable yes":
                    raise ValueError(f"run executable receipt mismatch for {arm_key}/{mode}")
                actual_validity = json.loads((run_dir / "experiment_valid.json").read_text(encoding="utf-8"))
                if actual_validity != run["experiment_valid"]:
                    raise ValueError(f"run validity receipt mismatch for {arm_key}/{mode}")
                if Path(run["run_identity_path"]).resolve() != (run_dir / "run_identity.json").resolve():
                    raise ValueError(f"run identity path mismatch for {arm_key}/{mode}")
                identity = json.loads(Path(run["run_identity_path"]).read_text(encoding="utf-8"))
                controls = identity.get("controls", {})
                expected_seconds = package["run_controls"]["seconds"]
                expected_scheme = str(arm["mp_physics"])
                if (identity.get("scheme") != expected_scheme or
                        identity.get("actual_proc_grid") != "1x1" or
                        identity.get("exit_code") != 0 or
                        not identity.get("experiment_valid") or
                        controls.get("minutes") != package["run_controls"]["minutes"] or
                        controls.get("seconds") != expected_seconds or
                        controls.get("np") != 1 or
                        controls.get("fixed_dt") is not False or
                        controls.get("history") != 0 or
                        controls.get("history_s") != 20 or
                        controls.get("radt") is not None or
                        controls.get("runner_sha256") != run["runner_sha256"]):
                    raise ValueError(f"run identity contract mismatch for {arm_key}/{mode}")

        strict = arm["strict_pair_receipt"]
        if (strict.get("status") != "PASS" or strict.get("variables_total") != 254 or
                strict.get("numeric_variables") != 253 or strict.get("exact_Times") is not True or
                strict.get("bitwise_matches") != 254 or strict.get("differences") != 0):
            raise ValueError(f"strict history receipt is not the pinned within-arm pass for {arm_key}")
        if result_arm.get("within_arm_history_comparison") != strict:
            raise ValueError(f"strict history receipt mismatch for {arm_key}")
        event_golden = arm["event_stream"]
        result_event = result_arm.get("event_stream", {})
        for field in ("path", "sha256", "event_payload_sha256", "event_payload_count",
                      "event_record_count", "counts", "event_record_counts",
                      "rho_key_sha256", "rho_row_count", "event_payload_path"):
            if result_event.get(field) != event_golden.get(field):
                raise ValueError(f"native result {arm_key} event_stream {field} differs from replay_package")

    selected_key = f"{scheme}/{policy}"
    selected = package_arms[selected_key]
    if verify_artifacts:
        if events_path is None:
            raise ValueError("--verify-private requires the captured raw event file")
        expected_events_path = Path(selected["runs"]["capture"]["event_path"]).resolve()
        if events_path.resolve() != expected_events_path:
            raise ValueError("event file path is not the code-pinned private capture run")
        raw = events_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != selected["event_stream"]["sha256"]:
            raise ValueError("capture event file SHA-256 differs from replay_package")
    else:
        public_path = Path(selected["event_stream"]["event_payload_path"])
        if not public_path.is_absolute():
            public_path = Path(__file__).resolve().parents[1] / public_path
        if events_path is not None and events_path.resolve() != public_path.resolve():
            raise ValueError("public event fixture path differs from replay_package")
        raw = public_path.read_bytes()
    return package, raw


def _f32(value: float) -> float:
    return struct.unpack(">f", struct.pack(">f", value))[0]


def _parse_numeric(rows: Iterable[str], tag: str, width: int) -> list[dict[str, Any]]:
    parsed = []
    for line_no, line in enumerate(rows, 1):
        fields = line.split()
        if not fields or fields[0] != tag:
            continue
        if len(fields) != width + 1:
            raise ValueError(f"line {line_no}: {tag} width {len(fields)-1}; expected {width}")
        try:
            ints = [int(x, 10) for x in fields[1:9]]
            floats = [float(x) for x in fields[9:]]
        except ValueError as exc:
            raise ValueError(f"line {line_no}: malformed {tag} numeric payload") from exc
        if not all(math.isfinite(x) for x in floats):
            raise ValueError(f"line {line_no}: {tag} contains a non-finite value")
        parsed.append({"ints": ints, "reals": floats, "line": line_no})
    return parsed


def _replay_event_rows(lines: list[str], policy: str) -> dict[str, Any]:
    if policy not in {"retention", "midpoint"}:
        raise ValueError("policy must be retention or midpoint")
    base = parse_event_lines(lines)
    base_result = validate_events(base)
    shapes = _parse_numeric(lines, "S10SHAPE", SHAPE_WIDTH)
    volumes = _parse_numeric(lines, "S10VOL", VOLUME_WIDTH)
    if not shapes or not volumes:
        raise ValueError("policy capture is missing S10SHAPE or S10VOL rows")

    shape_by_key: dict[tuple[int, ...], dict[str, Any]] = {}
    for row in shapes:
        key = tuple(row["ints"][:7])
        if key in shape_by_key:
            raise ValueError(f"duplicate S10SHAPE cell/call key {key}")
        shape_by_key[key] = row
    expected_selected = {
        (*call, i, k)
        for call in PROGB_CALL_CONTEXTS
        for i in SELECTED_I
        for k in LEVELS
    }
    actual_selected = {
        key for key in shape_by_key
        if key[:2] == (1, 73) and key[5] in SELECTED_I
    }
    if actual_selected != expected_selected:
        raise ValueError(f"S10SHAPE selected census mismatch: missing="
                         f"{len(expected_selected-actual_selected)}, extra="
                         f"{len(actual_selected-expected_selected)}")

    # The fixed positive-trace witness is sampled after every ProgB/slope call on
    # latitude 2. The per-call S10SCAN census supplies its independent call schedule.
    scan_calls = {
        tuple(row["values"][:5]) for row in base
        if row["tag"] == "S10SCAN" and row["values"][1] == 2
    }
    expected_trace_shapes = {(*call, 142, 17) for call in scan_calls}
    actual_trace_shapes = {
        key for key in shape_by_key if key[1] == 2 and key[5:] == (142, 17)
    }
    if actual_trace_shapes != expected_trace_shapes:
        raise ValueError(f"S10SHAPE trace census mismatch: missing="
                         f"{len(expected_trace_shapes-actual_trace_shapes)}, extra="
                         f"{len(actual_trace_shapes-expected_trace_shapes)}")

    volume_by_key: dict[tuple[int, ...], dict[str, Any]] = {}
    action_counts: Counter[str] = Counter()
    for row in volumes:
        ints, reals = row["ints"], row["reals"]
        key, action = tuple(ints[:7]), ints[7]
        if key in volume_by_key:
            raise ValueError(f"duplicate S10VOL cell/call key {key}")
        if action not in (0, 1, 2, 3):
            raise ValueError(f"S10VOL unknown action code {action}")
        qg, before, after, delta, rhox = reals
        if not math.isclose(delta, _f32(after-before), rel_tol=0., abs_tol=1e-30):
            raise ValueError(f"S10VOL delta differs from the stored brs change at {key}")
        if action == 0:
            if not (100. <= rhox <= 900.):
                raise ValueError(f"active density projection outside clamp at {key}")
            if not math.isclose(after, _f32(qg/rhox), rel_tol=2e-7, abs_tol=1e-30):
                raise ValueError(f"active brs projection is not qg/rhox at {key}")
        elif action == 1:
            if policy != "midpoint" or qg <= 0. or rhox != RHO_MID_F32:
                raise ValueError(f"invalid midpoint-trace correction at {key}")
            if not math.isclose(after, _f32(qg/RHO_MID_F32), rel_tol=2e-7, abs_tol=1e-30):
                raise ValueError(f"midpoint brs correction is not qg/rho_mid at {key}")
        elif action == 2:
            if policy != "midpoint" or qg != 0. or after != 0. or rhox != 0.:
                raise ValueError(f"invalid zero-qg volume cleanup at {key}")
        elif action == 3:
            if policy != "retention" or after != before or delta != 0.:
                raise ValueError(f"invalid retained inactive brs row at {key}")
        volume_by_key[key] = row
        action_counts[str(action)] += 1

    if set(volume_by_key) != set(shape_by_key):
        raise ValueError(f"S10VOL/S10SHAPE key mismatch: missing-volume="
                         f"{len(set(shape_by_key)-set(volume_by_key))}, missing-shape="
                         f"{len(set(volume_by_key)-set(shape_by_key))}")
    for key, row in shape_by_key.items():
        qg, brs, rhox = row["reals"][:3]
        volume = volume_by_key[key]["reals"]
        if qg != volume[0] or brs != volume[2] or rhox != volume[4]:
            raise ValueError(f"S10SHAPE differs from same-call S10VOL state at {key}")

    # Direct rhox readers are paired to their same-call shape snapshot. The
    # pre-ProgB max reader is non-dividing; the four process readers divide by rho.
    rhox_rows = [row["values"] for row in base if row["tag"] == "S10RHO"]
    for values in rhox_rows:
        key = tuple(values[:7])
        if key not in shape_by_key:
            raise ValueError(f"S10RHO lacks a call-aligned shape snapshot {key}")
        qg, rhox = shape_by_key[key]["reals"][0], shape_by_key[key]["reals"][2]
        consumer_id = str(values[7])
        if consumer_id not in RHO_CONSUMER_ID_CONTRACT:
            raise ValueError(f"unknown S10RHO consumer ID {consumer_id}")
        reached = values[9] == 1
        assigned = values[8] == 1
        if reached and consumer_id != "3027" and policy == "midpoint" and not assigned:
            raise ValueError(f"midpoint reached rhox divider without a current-call producer: {key}")
        if reached and consumer_id != "3027" and (qg <= 0. or rhox <= 0.):
            raise ValueError(f"reached rhox division consumer has no positive density: {key} "
                             f"(qg={qg}, rhox={rhox})")
    # A's false current-call assignment bit can still read the defined INOUT seed
    # or last value. B's per-call zero/fallback initializes each current output.
    if policy == "midpoint":
        if any(row["values"][7] != 1 for row in base if row["tag"] == "S10CMG"):
            raise ValueError("midpoint arm reached cmg test without a defined per-call output")

    return {
        "schema": "s10-policy-event-replay-v1",
        "policy": policy,
        "policy_approved": False,
        "base_flag_counts": base_result["records"],
        "shape_rows": len(shapes),
        "volume_rows": len(volumes),
        "volume_actions": dict(action_counts),
        "rhox_consumer_rows": len(rhox_rows),
        "rhox_positive_denominator_checks_passed": True,
        "defined_output_values_only": True,
        "physical_policy": "OPEN",
    }


def replay_events(manifest: dict[str, Any], plan: dict[str, Any],
                  scheme: str, policy: str, events_path: Path | None = None, *,
                  verify_private: bool = False) -> dict[str, Any]:
    """Trusted entry point: verify the pinned package and payload before replay."""
    _, raw = validate_replay_package(manifest, plan, scheme, policy, events_path,
                                     verify_artifacts=verify_private)
    lines = validate_capture_integrity(raw, manifest, scheme, policy,
                                       verify_raw_sha=verify_private)
    result = _replay_event_rows(lines, policy)
    result["scheme"] = scheme
    result["replay_package_integrity_passed"] = True
    result["capture_integrity_passed"] = True
    result["artifact_verification_scope"] = (
        "PRIVATE_ARTIFACTS_VERIFIED" if verify_private else "RECORDED_RECEIPTS_ONLY")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=Path,
                        help="compact checked-in event payload (default) or private raw RSL with --verify-private")
    parser.add_argument("--manifest", type=Path, required=True,
                        help="native S10 results manifest containing the capture receipt")
    parser.add_argument("--plan", type=Path, required=True,
                        help="predeclared S10 run plan used by the native results receipt")
    parser.add_argument("--scheme", choices=("mp37", "mp237"), required=True)
    parser.add_argument("--policy", choices=("retention", "midpoint"), required=True)
    parser.add_argument("--verify-private", action="store_true",
                        help="also reopen the eight retained local histories/executables/inputs/receipts")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    scope = "PRIVATE_ARTIFACTS_VERIFIED" if args.verify_private else "RECORDED_RECEIPTS_ONLY"
    try:
        result = replay_events(manifest, plan, args.scheme, args.policy, args.events,
                               verify_private=args.verify_private)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "schema": "s10-policy-replay-failure-v1",
            "scheme": args.scheme,
            "policy": args.policy,
            "policy_approved": False,
            "physical_policy": "OPEN",
            "artifact_verification_scope": scope,
            "fail_closed": True,
            "error": str(exc),
        }
        payload = json.dumps(result, indent=2) + "\n"
        if args.out:
            args.out.write_text(payload)
        else:
            print(payload, end="")
        raise SystemExit(1)
    result["capture_integrity_golden"] = f"{args.scheme}/{args.policy}"
    payload = json.dumps(result, indent=2) + "\n"
    if args.out:
        args.out.write_text(payload)
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
