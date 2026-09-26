from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import s10_guarded_exec as guarded  # noqa: E402
import s10_prelink_guard as guard  # noqa: E402


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


@pytest.fixture
def guarded_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    workspace = tmp_path / "workspace"
    shadow = workspace / "shadow"
    shadow.mkdir(parents=True)
    canonical = workspace / "canonical"
    canonical.mkdir()
    capture = workspace / "S10/configuration_capture"
    capture.mkdir(parents=True)

    bash = workspace / "bin/bash"
    bash.parent.mkdir()
    bash.write_bytes(b"synthetic bash pin\n")
    configure = b"synthetic configure source\n"
    apply = b"synthetic apply source\n"
    (shadow / "configure").write_bytes(configure)
    (shadow / "apply_kdm6ad_config.sh").write_bytes(apply)
    configure_stdin = b"35\n1\n"
    apply_stdin = b""
    (capture / "configure.stdin").write_bytes(configure_stdin)
    (capture / "apply_kdm6ad_config.stdin").write_bytes(apply_stdin)

    snapshot_sha = "a" * 64
    toolchain_sha = "b" * 64
    tool_environment_sha = "c" * 64
    plan = {
        "clean_shadow": {
            "fresh_build_output_root": "S10/build-clean",
            "empty_root_snapshot_relative_path": "S10/prebuild_output_root_snapshot.json",
        },
        "trusted_s15_release": {
            "empty_output_root_snapshot_sha256": snapshot_sha,
        },
        "resource_gate": {
            "configure_only": {
                "allowed": True,
                "allowed_commands": ["./configure", "./apply_kdm6ad_config.sh"],
                "maximum_transient_bytes": 10,
                "minimum_free_bytes_after_reserve": 20,
                "preflight_receipt_relative_path": (
                    "S10/configuration_capture/configure_resource_preflight.json"
                ),
            },
            "status": "BLOCKED_PENDING_ESTIMATE_AND_REVIEW",
            "full_matrix_build_or_link_allowed": False,
        },
        "prelink_requirements": {
            "configure_preflight_receipt_max_age_seconds": 3600,
            "configuration_execution_ledger_relative_path": (
                "S10/configuration_capture/command_ledger.json"
            ),
            "configuration_generation_command": [str(bash.resolve()), "./configure"],
            "configuration_apply_command": [
                str(bash.resolve()), "./apply_kdm6ad_config.sh"
            ],
            "configuration_inputs_sha256": {
                "configure": _sha(configure),
                "apply_kdm6ad_config.sh": _sha(apply),
            },
            "configuration_stdin_capture_paths": {
                "configure": "configuration_capture/configure.stdin",
                "apply_kdm6ad_config": "configuration_capture/apply_kdm6ad_config.stdin",
            },
            "configure_selection_stdin_sha256": _sha(configure_stdin),
            "configuration_apply_stdin_sha256": _sha(apply_stdin),
            "configuration_log_capture_paths": {
                "configure": {
                    "stdout": "S10/configuration_capture/configure.stdout",
                    "stderr": "S10/configuration_capture/configure.stderr",
                },
                "apply_kdm6ad_config": {
                    "stdout": "S10/configuration_capture/apply.stdout",
                    "stderr": "S10/configuration_capture/apply.stderr",
                },
            },
            "netcdf_config_invocation_policy": None,
        },
        "toolchain": {
            "tools": {"bash": {"path": str(bash.resolve()), "sha256": _sha(bash.read_bytes())}},
            "toolchain_sha256": toolchain_sha,
            "environment_sha256": tool_environment_sha,
        },
        "build_matrix": {"guarded_command_templates": None},
    }
    plan_path = workspace / "plan.json"
    _write_json(plan_path, plan)
    plan_sha = guard.sha256_file(plan_path)
    preflight = {
        "schema": "s10-resource-preflight-receipt-v1",
        "phase": "configure",
        "status": "ALLOW_CONFIGURE_ONLY",
        "plan_sha256": plan_sha,
        "toolchain_sha256": toolchain_sha,
        "tool_environment_sha256": tool_environment_sha,
        "output_root_path": str((workspace / "S10/build-clean").resolve()),
        "empty_output_root_snapshot_sha256": snapshot_sha,
        "allowed_commands": plan["resource_gate"]["configure_only"]["allowed_commands"],
        "required_free_bytes": 30,
        "observed_at_unix_ns": time.time_ns(),
    }
    _write_json(capture / "configure_resource_preflight.json", preflight)

    # Keep the real receipt, command, input, log and ledger checks; replace only
    # host/tool environment inspection that cannot be meaningful in this fixture.
    monkeypatch.setattr(guarded, "_planned_environment", lambda _plan: {"PATH": "/synthetic"})
    monkeypatch.setattr(guarded, "shutil_disk_usage", lambda _root: SimpleNamespace(free=10**12))
    monkeypatch.setattr(guard, "validate_prebuild_snapshot", lambda *args, **kwargs: None)
    monkeypatch.setattr(guard, "validate_static_pins", lambda *args, **kwargs: None)
    monkeypatch.setattr(guard, "validate_clean_shadow", lambda *args, **kwargs: None)
    calls: list[dict] = []

    def fake_run(argv, **kwargs):
        calls.append({"argv": list(argv), **kwargs})
        if argv[-1] == "./configure":
            (shadow / "configure.wrf").write_text("synthetic configuration\n")
        index = len(calls)
        return SimpleNamespace(returncode=0, stdout=f"out-{index}".encode(),
                               stderr=f"err-{index}".encode())

    monkeypatch.setattr(guarded.subprocess, "run", fake_run)
    return SimpleNamespace(
        workspace=workspace, shadow=shadow, canonical=canonical, plan=plan,
        plan_path=plan_path, plan_sha=plan_sha, calls=calls,
        capture=capture,
    )


def _execute(case, stage: str, *, plan_sha: str | None = None,
             build_command_key: str | None = None):
    return guarded.execute_guarded_stage(
        stage=stage, plan_path=case.plan_path,
        trusted_plan_sha256=plan_sha or case.plan_sha,
        workspace=case.workspace, canonical_host=case.canonical,
        shadow_host=case.shadow, overlay_paths={},
        build_command_key=build_command_key,
    )


def test_configure_then_apply_capture_exact_commands_and_resumable_ledger(guarded_case):
    case = guarded_case
    configure_row = _execute(case, "configure")
    apply_row = _execute(case, "apply_kdm6ad_config")

    assert [call["argv"] for call in case.calls] == [
        [case.plan["toolchain"]["tools"]["bash"]["path"], "./configure"],
        [case.plan["toolchain"]["tools"]["bash"]["path"], "./apply_kdm6ad_config.sh"],
    ]
    assert [call["cwd"] for call in case.calls] == [case.shadow, case.shadow]
    assert all(call["shell"] is False for call in case.calls)
    assert case.calls[0]["input"] == b"35\n1\n"
    assert case.calls[1]["input"] == b""

    ledger_path = Path(apply_row["configuration_command_ledger_path"])
    ledger = json.loads(ledger_path.read_text())
    assert ledger["status"] == "COMPLETE"
    assert [row["stage"] for row in ledger["commands"]] == [
        "configure", "apply_kdm6ad_config"
    ]
    assert ledger["plan_sha256"] == case.plan_sha
    assert ledger["configure_resource_preflight_receipt_sha256"] == guard.sha256_file(
        case.capture / "configure_resource_preflight.json"
    )
    assert configure_row["stdin_sha256"] == _sha(b"35\n1\n")
    assert ledger["commands"][0]["stdout_sha256"] == _sha(b"out-1")
    assert ledger["commands"][0]["stderr_sha256"] == _sha(b"err-1")
    assert ledger["commands"][1]["stdout_sha256"] == _sha(b"out-2")
    assert ledger["commands"][1]["stderr_sha256"] == _sha(b"err-2")
    assert apply_row["configuration_command_ledger_sha256"] == guard.sha256_file(ledger_path)


@pytest.mark.parametrize("reason", ["wrong_plan_pin", "stale_preflight"])
def test_wrong_plan_or_stale_preflight_is_rejected_before_subprocess(guarded_case, reason):
    case = guarded_case
    if reason == "wrong_plan_pin":
        with pytest.raises(guard.PrelinkError, match="plan SHA"):
            _execute(case, "configure", plan_sha="0" * 64)
    else:
        receipt_path = case.capture / "configure_resource_preflight.json"
        receipt = json.loads(receipt_path.read_text())
        receipt["observed_at_unix_ns"] = 1
        _write_json(receipt_path, receipt)
        with pytest.raises(guard.PrelinkError, match="preflight is stale"):
            _execute(case, "configure")
    assert case.calls == []
    assert not (case.capture / "command_ledger.json").exists()


def test_changed_shadow_configuration_source_is_rejected_before_subprocess(guarded_case):
    case = guarded_case
    (case.shadow / "configure").write_bytes(b"changed synthetic configure\n")
    with pytest.raises(guard.PrelinkError, match="script changed: configure"):
        _execute(case, "configure")
    assert case.calls == []
    assert not (case.capture / "command_ledger.json").exists()


@pytest.mark.parametrize("stage", ["preprocess", "object", "link"])
def test_build_stages_stay_blocked_before_subprocess_even_with_command_key(guarded_case, stage):
    case = guarded_case
    with pytest.raises(guard.PrelinkError, match="resource gate is blocked"):
        _execute(case, stage, build_command_key="synthetic-template")
    assert case.calls == []


def test_configure_retry_is_rejected_without_new_command(guarded_case):
    case = guarded_case
    _execute(case, "configure")
    # Remove synthetic logs to reach the independent ledger duplicate guard.
    (case.capture / "configure.stdout").unlink()
    (case.capture / "configure.stderr").unlink()
    with pytest.raises(guard.PrelinkError, match="already invoked"):
        _execute(case, "configure")
    assert len(case.calls) == 1


def test_preexisting_log_path_is_rejected_without_subprocess(guarded_case):
    case = guarded_case
    (case.capture / "configure.stdout").write_bytes(b"preserve me")
    with pytest.raises(guard.PrelinkError, match="log path already exists"):
        _execute(case, "configure")
    assert case.calls == []
    assert (case.capture / "configure.stdout").read_bytes() == b"preserve me"
