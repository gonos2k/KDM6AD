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
            "configure_failure_log_markers": list(guard.CONFIGURE_FAILURE_MARKERS),
            "configuration_execution_ledger_relative_path": (
                "S10/configuration_capture/command_ledger.json"
            ),
            "configuration_preflight_consumption_marker_relative_path": (
                "S10/configuration_capture/configure_preflight_consumed.json"
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
    returncodes = [0, 0]
    marker_path = capture / "configure_preflight_consumed.json"

    def fake_run(argv, **kwargs):
        calls.append({"argv": list(argv), "marker_exists_before": marker_path.exists(), **kwargs})
        if argv[-1] == "./configure":
            (shadow / "configure.wrf").write_text("synthetic configuration\n")
        index = len(calls)
        return SimpleNamespace(
            returncode=returncodes[index - 1] if index <= len(returncodes) else 0,
            stdout=f"out-{index}".encode(),
            stderr=f"err-{index}".encode(),
        )

    monkeypatch.setattr(guarded.subprocess, "run", fake_run)
    return SimpleNamespace(
        workspace=workspace, shadow=shadow, canonical=canonical, plan=plan,
        plan_path=plan_path, plan_sha=plan_sha, calls=calls,
        capture=capture, returncodes=returncodes, marker_path=marker_path,
    )


def _execute(case, stage: str, *, plan_sha: str | None = None,
             build_command_key: str | None = None):
    if stage == "configure-pipeline":
        return guarded.execute_guarded_configuration_pipeline(
            plan_path=case.plan_path,
            trusted_plan_sha256=plan_sha or case.plan_sha,
            workspace=case.workspace, canonical_host=case.canonical,
            shadow_host=case.shadow, overlay_paths={},
        )
    return guarded.execute_guarded_stage(
        stage=stage, plan_path=case.plan_path,
        trusted_plan_sha256=plan_sha or case.plan_sha,
        workspace=case.workspace, canonical_host=case.canonical,
        shadow_host=case.shadow, overlay_paths={},
        build_command_key=build_command_key,
    )


def test_configure_pipeline_runs_exact_commands_and_persists_ledger(guarded_case):
    case = guarded_case
    result = _execute(case, "configure-pipeline")

    assert [call["argv"] for call in case.calls] == [
        [case.plan["toolchain"]["tools"]["bash"]["path"], "./configure"],
        [case.plan["toolchain"]["tools"]["bash"]["path"], "./apply_kdm6ad_config.sh"],
    ]
    assert [call["cwd"] for call in case.calls] == [case.shadow, case.shadow]
    assert all(call["shell"] is False for call in case.calls)
    assert len(case.calls) == 2
    assert all(call["marker_exists_before"] for call in case.calls)
    assert case.calls[0]["input"] == b"35\n1\n"
    assert case.calls[1]["input"] == b""

    ledger_path = case.capture / "command_ledger.json"
    ledger = json.loads(ledger_path.read_text())
    assert ledger["status"] == "COMPLETE"
    assert [row["stage"] for row in ledger["commands"]] == [
        "configure", "apply_kdm6ad_config"
    ]
    assert ledger["plan_sha256"] == case.plan_sha
    assert ledger["configure_resource_preflight_receipt_sha256"] == guard.sha256_file(
        case.capture / "configure_resource_preflight.json"
    )
    assert ledger["commands"][0]["stdout_sha256"] == _sha(b"out-1")
    assert ledger["commands"][0]["stderr_sha256"] == _sha(b"err-1")
    assert ledger["commands"][1]["stdout_sha256"] == _sha(b"out-2")
    assert ledger["commands"][1]["stderr_sha256"] == _sha(b"err-2")
    assert ledger["commands"][0]["stdin_sha256"] == _sha(b"35\n1\n")
    assert ledger["commands"][1]["stdin_sha256"] == _sha(b"")
    assert ledger["commands"][0]["environment_sha256"] == case.plan["toolchain"][
        "environment_sha256"
    ]
    assert ledger["toolchain_sha256"] == case.plan["toolchain"]["toolchain_sha256"]
    assert ledger["tool_environment_sha256"] == case.plan["toolchain"]["environment_sha256"]
    assert ledger["nonce_sha256"] == _sha(ledger["nonce"].encode())
    marker_sha = guard.sha256_file(case.marker_path)
    assert result["configuration_preflight_consumption_marker_path"] == str(
        case.marker_path
    )
    assert result["configuration_preflight_consumption_marker_sha256"] == marker_sha
    assert ledger["configuration_preflight_consumption_marker_sha256"] == marker_sha
    assert ledger["configuration_preflight_consumption_nonce"] == result[
        "configuration_preflight_consumption_nonce"
    ]


def test_configure_pipeline_rejects_internal_compiler_failure_marker_with_rc0(
    guarded_case, monkeypatch: pytest.MonkeyPatch,
):
    case = guarded_case

    def fake_configure_failure(argv, **kwargs):
        case.calls.append({"argv": list(argv), "marker_exists_before": case.marker_path.exists(), **kwargs})
        assert argv[-1] == "./configure"
        (case.shadow / "configure.wrf").write_text("synthetic configuration\n")
        return SimpleNamespace(
            returncode=0,
            stdout=b"One of compilers testing failed!\n",
            stderr=b"",
        )

    monkeypatch.setattr(guarded.subprocess, "run", fake_configure_failure)
    with pytest.raises(guard.PrelinkError, match="WRF configure reported compiler failure"):
        _execute(case, "configure-pipeline")

    assert len(case.calls) == 1
    assert case.calls[0]["marker_exists_before"] is True
    assert case.calls[0]["shell"] is False
    ledger = json.loads((case.capture / "command_ledger.json").read_text())
    assert ledger["status"] == "FAILED"
    assert ledger["commands"][0]["returncode"] == 0
    assert (case.capture / "configure_preflight_consumed.json").is_file()
    assert not (case.capture / "apply.stdout").exists()
    assert not (case.capture / "apply.stderr").exists()


def test_standalone_apply_is_rejected_before_subprocess(guarded_case):
    case = guarded_case
    with pytest.raises(
        guard.PrelinkError, match="pipeline|standalone|unsupported|not allowed"
    ):
        _execute(case, "apply_kdm6ad_config")
    assert case.calls == []


def test_forged_ledger_and_configure_wrf_cannot_authorize_standalone_apply(guarded_case):
    case = guarded_case
    configure_wrf = case.shadow / "configure.wrf"
    configure_wrf.write_bytes(b"forged configuration\n")
    ledger = {
        "schema": "s10-guarded-configuration-ledger-v1",
        "status": "IN_PROGRESS",
        "plan_sha256": case.plan_sha,
        "empty_output_root_snapshot_sha256": case.plan["trusted_s15_release"][
            "empty_output_root_snapshot_sha256"
        ],
        "configure_resource_preflight_receipt_sha256": guard.sha256_file(
            case.capture / "configure_resource_preflight.json"
        ),
        "toolchain_sha256": case.plan["toolchain"]["toolchain_sha256"],
        "tool_environment_sha256": case.plan["toolchain"]["environment_sha256"],
        "output_root_path": str((case.workspace / "S10/build-clean").resolve()),
        "commands": [{
            "stage": "configure",
            "returncode": 0,
            "configure_wrf_sha256_after": _sha(configure_wrf.read_bytes()),
        }],
        "nonce": "forged but self-consistent",
        "nonce_sha256": _sha(b"forged but self-consistent"),
    }
    _write_json(case.capture / "command_ledger.json", ledger)
    with pytest.raises(
        guard.PrelinkError, match="pipeline|standalone|unsupported|not allowed"
    ):
        _execute(case, "apply_kdm6ad_config")
    with pytest.raises(
        guard.PrelinkError,
        match="already invoked|ledger|configure.wrf|pipeline|forged|not resumable",
    ):
        _execute(case, "configure-pipeline")
    assert case.calls == []


def test_failed_configure_does_not_launch_apply(guarded_case):
    case = guarded_case
    case.returncodes[0] = 1
    with pytest.raises(guard.PrelinkError, match="exited with status 1"):
        _execute(case, "configure-pipeline")
    assert len(case.calls) == 1
    assert case.calls[0]["argv"][-1] == "./configure"
    assert case.marker_path.is_file()


def test_failed_configure_consumes_preflight_for_same_plan_retry(guarded_case):
    case = guarded_case
    case.returncodes[0] = 1
    with pytest.raises(guard.PrelinkError, match="exited with status 1"):
        _execute(case, "configure-pipeline")
    for name in ("command_ledger.json", "configure.stdout", "configure.stderr"):
        (case.capture / name).unlink(missing_ok=True)
    (case.shadow / "configure.wrf").unlink(missing_ok=True)

    with pytest.raises(guard.PrelinkError, match="consum|used|marker"):
        _execute(case, "configure-pipeline")
    assert len(case.calls) == 1


@pytest.mark.parametrize("reason", ["wrong_plan_pin", "stale_preflight"])
def test_wrong_plan_or_stale_preflight_is_rejected_before_subprocess(guarded_case, reason):
    case = guarded_case
    if reason == "wrong_plan_pin":
        with pytest.raises(guard.PrelinkError, match="plan SHA"):
            _execute(case, "configure-pipeline", plan_sha="0" * 64)
    else:
        receipt_path = case.capture / "configure_resource_preflight.json"
        receipt = json.loads(receipt_path.read_text())
        receipt["observed_at_unix_ns"] = 1
        _write_json(receipt_path, receipt)
        with pytest.raises(guard.PrelinkError, match="preflight is stale"):
            _execute(case, "configure-pipeline")
    assert case.calls == []
    assert not (case.capture / "command_ledger.json").exists()


def test_changed_shadow_configuration_source_is_rejected_before_subprocess(guarded_case):
    case = guarded_case
    (case.shadow / "configure").write_bytes(b"changed synthetic configure\n")
    with pytest.raises(guard.PrelinkError, match="script changed: configure"):
        _execute(case, "configure-pipeline")
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
    _execute(case, "configure-pipeline")
    # Remove synthetic logs to reach the independent ledger duplicate guard.
    (case.capture / "configure.stdout").unlink()
    (case.capture / "configure.stderr").unlink()
    (case.capture / "apply.stdout").unlink()
    (case.capture / "apply.stderr").unlink()
    with pytest.raises(
        guard.PrelinkError, match="already invoked|configure.wrf|ledger|not resumable"
    ):
        _execute(case, "configure-pipeline")
    assert len(case.calls) == 2


def test_deleting_workspace_ledger_logs_and_configure_wrf_does_not_reauthorize_pipeline(
    guarded_case,
):
    case = guarded_case
    _execute(case, "configure-pipeline")
    for name in (
        "command_ledger.json", "configure.stdout", "configure.stderr",
        "apply.stdout", "apply.stderr",
    ):
        (case.capture / name).unlink()
    (case.shadow / "configure.wrf").unlink()

    with pytest.raises(guard.PrelinkError):
        _execute(case, "configure-pipeline")
    assert len(case.calls) == 2


def test_preexisting_log_path_is_rejected_without_subprocess(guarded_case):
    case = guarded_case
    (case.capture / "configure.stdout").write_bytes(b"preserve me")
    with pytest.raises(guard.PrelinkError, match="log path already exists"):
        _execute(case, "configure-pipeline")
    assert case.calls == []
    assert (case.capture / "configure.stdout").read_bytes() == b"preserve me"


def _cli_argv(case, stage: str) -> list[str]:
    return [
        "s10_guarded_exec.py", "--stage", stage,
        "--plan", str(case.plan_path),
        "--trusted-plan-sha256", case.plan_sha,
        "--workspace", str(case.workspace),
        "--canonical-host", str(case.canonical),
        "--shadow-host", str(case.shadow),
        "--overlay", f"mp37={case.workspace / 'overlay-mp37.json'}",
        "--overlay", f"mp237={case.workspace / 'overlay-mp237.json'}",
    ]


def test_cli_dispatches_configure_pipeline_to_single_pipeline_entrypoint(
    guarded_case, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
):
    case = guarded_case
    observed: list[dict] = []

    def pipeline(**kwargs):
        observed.append(kwargs)
        return {"schema": "synthetic-pipeline-result"}

    monkeypatch.setattr(guarded, "execute_guarded_configuration_pipeline", pipeline)
    monkeypatch.setattr(guarded.sys, "argv", _cli_argv(case, "configure-pipeline"))

    assert guarded.main() == 0
    assert observed == [{
        "plan_path": case.plan_path,
        "trusted_plan_sha256": case.plan_sha,
        "workspace": case.workspace.resolve(),
        "canonical_host": case.canonical,
        "shadow_host": case.shadow,
        "overlay_paths": {
            "mp37": case.workspace / "overlay-mp37.json",
            "mp237": case.workspace / "overlay-mp237.json",
        },
    }]
    assert json.loads(capsys.readouterr().out) == {"schema": "synthetic-pipeline-result"}
    assert case.calls == []


@pytest.mark.parametrize("stage", ["configure", "apply_kdm6ad_config"])
def test_cli_rejects_standalone_configure_and_apply_before_subprocess(
    guarded_case, monkeypatch: pytest.MonkeyPatch, stage: str,
):
    case = guarded_case
    monkeypatch.setattr(guarded.sys, "argv", _cli_argv(case, stage))
    with pytest.raises(SystemExit) as error:
        guarded.main()
    assert error.value.code == 2
    assert case.calls == []


@pytest.mark.parametrize("stage", ["preprocess", "object", "link"])
def test_cli_keeps_build_commands_blocked_before_subprocess(
    guarded_case, monkeypatch: pytest.MonkeyPatch, stage: str,
):
    case = guarded_case
    monkeypatch.setattr(guarded.sys, "argv", _cli_argv(case, stage))
    assert guarded.main() == 2
    assert case.calls == []
