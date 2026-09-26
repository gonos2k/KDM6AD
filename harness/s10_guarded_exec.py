"""Run only receipt-gated S10 configure commands; refuse unpinned build work.

This is the only certified command entry point for S10. Direct unmanaged shell
commands are outside the experiment evidence path. Configure/apply are bounded
to the disposable shadow. Preprocess/object/link commands stay unavailable until
a later reviewed plan contains exact command templates and trusted resource
receipts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import s10_prelink_guard as guard  # noqa: E402

_CONFIG_PIPELINE_TOKEN = object()


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise guard.PrelinkError(f"expected JSON object: {path}")
    return value


def _planned_environment(plan: dict[str, Any]) -> dict[str, str]:
    guard.validate_configure_failure_markers(plan)
    pinned_snapshot = guard.tool_environment_snapshot()
    environment = {name: value for name, value in pinned_snapshot.items()
                   if value is not None}
    config = plan.get("toolchain", {}).get("configuration_environment", {})
    if not isinstance(config, dict):
        raise guard.PrelinkError("configuration environment pin is malformed")
    for name, value in config.items():
        if value is None:
            environment.pop(name, None)
        elif isinstance(value, str):
            environment[name] = value
        else:
            raise guard.PrelinkError(f"configuration environment value is invalid: {name}")
    snapshot = guard.tool_environment_snapshot(environment)
    digest = _digest(json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode())
    if digest != plan.get("toolchain", {}).get("environment_sha256"):
        raise guard.PrelinkError("guarded command environment differs from the reviewed toolchain pin")
    if "sdkroot_resolution" in plan.get("toolchain", {}):
        guard.validate_sdkroot_resolution(plan, environment=environment)
    return environment


def _resolve_workspace_path(workspace: Path, relative: str) -> Path:
    path = (workspace / relative).resolve()
    try:
        path.relative_to(workspace.resolve())
    except ValueError as exc:
        raise guard.PrelinkError(f"planned capture escaped workspace: {relative}") from exc
    return path


def _verify_configure_preflight(plan: dict[str, Any], *, plan_sha256: str,
                                workspace: Path, output_root: Path,
                                snapshot_path: Path) -> tuple[dict[str, Any], str]:
    config_gate = plan["resource_gate"]["configure_only"]
    if config_gate.get("allowed") is not True:
        raise guard.PrelinkError("configure-only execution is not allowed by the reviewed plan")
    preflight_path = _resolve_workspace_path(
        workspace, config_gate["preflight_receipt_relative_path"])
    preflight_sha = guard.sha256_file(preflight_path)
    preflight = _read_json(preflight_path)
    expected_snapshot = plan["trusted_s15_release"]["empty_output_root_snapshot_sha256"]
    expected_snapshot_path = workspace / plan["clean_shadow"]["empty_root_snapshot_relative_path"]
    if preflight.get("schema") != "s10-resource-preflight-receipt-v1" \
            or preflight.get("phase") != "configure" \
            or preflight.get("status") != "ALLOW_CONFIGURE_ONLY" \
            or preflight.get("plan_sha256") != plan_sha256 \
            or preflight.get("toolchain_sha256") != plan["toolchain"]["toolchain_sha256"] \
            or preflight.get("tool_environment_sha256") != plan["toolchain"]["environment_sha256"] \
            or preflight.get("output_root_path") != str(output_root.resolve()) \
            or preflight.get("empty_output_root_snapshot_sha256") != expected_snapshot:
        raise guard.PrelinkError("configure-only preflight receipt is not bound to this plan/root")
    guard.validate_prebuild_snapshot(
        snapshot_path, expected_snapshot, output_root, expected_snapshot_path)
    if output_root.exists():
        raise guard.PrelinkError("configure-only command requires build-clean to remain absent")
    allowed = config_gate["allowed_commands"]
    if preflight.get("allowed_commands") != allowed:
        raise guard.PrelinkError("configure-only preflight receipt command allowlist differs")
    required_free = (config_gate["maximum_transient_bytes"]
                     + config_gate["minimum_free_bytes_after_reserve"])
    if preflight.get("required_free_bytes") != required_free:
        raise guard.PrelinkError("configure-only preflight receipt reserve differs from the plan")
    observed = preflight.get("observed_at_unix_ns")
    max_age = plan["prelink_requirements"].get(
        "configure_preflight_receipt_max_age_seconds")
    now = time.time_ns()
    if (not isinstance(observed, int) or isinstance(observed, bool)
            or not isinstance(max_age, int) or isinstance(max_age, bool)
            or observed > now or now - observed > max_age * 1_000_000_000):
        raise guard.PrelinkError("configure-only resource preflight is stale")
    if shutil_disk_usage(output_root).free < required_free:
        raise guard.PrelinkError("fresh free space is below the configure-only reserve")
    return preflight, preflight_sha


def shutil_disk_usage(output_root: Path):
    """Probe the same filesystem that will contain the fresh build root."""
    import shutil

    return shutil.disk_usage(output_root.parent)


def _netcdf_post_config_probes(plan: dict[str, Any]) -> dict[str, Any] | None:
    policy = plan["prelink_requirements"].get("netcdf_config_invocation_policy")
    if not isinstance(policy, dict):
        return None
    records: dict[str, Any] = {}
    for name, pin in policy["invocations"].items():
        tool = Path(pin["path"]).resolve()
        digest = guard.sha256_file(tool)
        if digest != pin["sha256"]:
            raise guard.PrelinkError(f"NetCDF config tool changed before configure: {name}")
        if "/opt/local/" in str(tool):
            raise guard.PrelinkError(f"MacPorts NetCDF tool is forbidden: {name}")
        commands = []
        for argument, expected_stdout in pin["argv_outputs"].items():
            result = subprocess.run(
                [str(tool), argument], check=False, capture_output=True,
                text=True, shell=False)
            row = {
                "argv": [argument],
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
            commands.append(row)
        records[name] = {
            "probe_scope": "post_config_pinned_tool_probes",
            "path": str(tool), "sha256": digest,
            "version": pin["version"], "commands": commands,
        }
    return records


def _ledger_path(plan: dict[str, Any], workspace: Path) -> Path:
    relative = plan["prelink_requirements"].get(
        "configuration_execution_ledger_relative_path")
    if not isinstance(relative, str) or not relative:
        raise guard.PrelinkError("guarded configuration ledger path is not plan-pinned")
    path = _resolve_workspace_path(workspace, relative)
    capture_root = (workspace / "S10/configuration_capture").resolve()
    if not path.is_relative_to(capture_root):
        raise guard.PrelinkError("guarded configuration ledger escaped its capture root")
    return path


def _load_or_start_ledger(path: Path, *, plan_sha256: str,
                          snapshot_sha256: str,
                          preflight_sha256: str,
                          toolchain_sha256: str,
                          tool_environment_sha256: str,
                          output_root: Path,
                          stage: str) -> dict[str, Any]:
    if path.exists():
        ledger = _read_json(path)
        if (ledger.get("schema") != "s10-guarded-configuration-ledger-v1"
                or ledger.get("plan_sha256") != plan_sha256
                or ledger.get("empty_output_root_snapshot_sha256") != snapshot_sha256
                or ledger.get("configure_resource_preflight_receipt_sha256") != preflight_sha256
                or ledger.get("toolchain_sha256") != toolchain_sha256
                or ledger.get("tool_environment_sha256") != tool_environment_sha256
                or ledger.get("output_root_path") != str(output_root.resolve())):
            raise guard.PrelinkError("existing guarded configuration ledger has a different identity")
        if stage == "configure" and ledger.get("commands"):
            raise guard.PrelinkError("configure was already invoked for this plan; refusing a duplicate run")
        if ledger.get("status") != "IN_PROGRESS":
            raise guard.PrelinkError("configuration ledger is not resumable")
        nonce = ledger.get("nonce")
        if (not isinstance(nonce, str) or _digest(nonce.encode()) != ledger.get("nonce_sha256")):
            raise guard.PrelinkError("configuration ledger nonce is invalid")
        commands = ledger.get("commands")
        if not isinstance(commands, list):
            raise guard.PrelinkError("configuration ledger command list is malformed")
    else:
        if stage != "configure":
            raise guard.PrelinkError("apply may run only after guarded configure")
        nonce = secrets.token_hex(32)
        ledger = {
            "schema": "s10-guarded-configuration-ledger-v1",
            "status": "IN_PROGRESS",
            "plan_sha256": plan_sha256,
            "empty_output_root_snapshot_sha256": snapshot_sha256,
            "configure_resource_preflight_receipt_sha256": preflight_sha256,
            "toolchain_sha256": toolchain_sha256,
            "tool_environment_sha256": tool_environment_sha256,
            "output_root_path": str(output_root.resolve()),
            "commands": [],
            "nonce": nonce,
            "nonce_sha256": _digest(nonce.encode()),
        }
    commands = ledger["commands"]
    if stage == "configure" and commands:
        raise guard.PrelinkError("configure was already invoked for this plan; refusing a duplicate run")
    if stage == "apply_kdm6ad_config":
        if (len(commands) != 1 or commands[0].get("stage") != "configure"
                or commands[0].get("returncode") != 0):
            raise guard.PrelinkError("apply may run only once after successful guarded configure")
    return ledger


def _write_ledger(path: Path, ledger: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    temporary.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return guard.sha256_file(path)


def _consume_configure_preflight(plan: dict[str, Any], *, plan_sha256: str,
                                 workspace: Path, preflight: dict[str, Any],
                                 preflight_sha256: str,
                                 ledger: dict[str, Any]) -> dict[str, Any]:
    relative = plan["prelink_requirements"].get(
        "configuration_preflight_consumption_marker_relative_path")
    if not isinstance(relative, str) or not relative:
        raise guard.PrelinkError("one-shot configure preflight marker path is not plan-pinned")
    marker_path = _resolve_workspace_path(workspace, relative)
    capture_root = (workspace / "S10/configuration_capture").resolve()
    if not marker_path.is_relative_to(capture_root):
        raise guard.PrelinkError("configure preflight consumption marker escaped its private capture root")
    if marker_path.exists():
        raise guard.PrelinkError("configure preflight nonce was already consumed; refusing retry")
    nonce = secrets.token_hex(32)
    pipeline_id = secrets.token_hex(32)
    payload = {
        "schema": "s10-configure-preflight-consumption-v1",
        "status": "CONSUMED",
        "plan_sha256": plan_sha256,
        "resource_preflight_receipt_sha256": preflight_sha256,
        "resource_preflight_nonce": preflight.get("nonce"),
        "configuration_ledger_nonce": ledger["nonce"],
        "pipeline_id": pipeline_id,
        "nonce": nonce,
        "nonce_sha256": _digest(nonce.encode()),
        "consumed_at_unix_ns": time.time_ns(),
    }
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(marker_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise guard.PrelinkError("configure preflight nonce was already consumed") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    marker_sha = guard.sha256_file(marker_path)
    ledger["configuration_preflight_consumption_marker_path"] = str(marker_path)
    ledger["configuration_preflight_consumption_marker_sha256"] = marker_sha
    ledger["configuration_preflight_consumption_nonce"] = nonce
    ledger["configuration_pipeline_id"] = pipeline_id
    return {
        "configuration_preflight_consumption_marker_path": str(marker_path),
        "configuration_preflight_consumption_marker_sha256": marker_sha,
        "configuration_preflight_consumption_nonce": nonce,
        "configuration_pipeline_id": pipeline_id,
    }


def _execute_config_command(*, stage: str, plan_path: Path,
                             trusted_plan_sha256: str,
                             workspace: Path, canonical_host: Path,
                             shadow_host: Path, overlay_paths: dict[str, Path],
                             pipeline_token: object,
                             expected_ledger_sha256: str | None = None,
                             consumption_marker: dict[str, Any] | None = None) -> dict[str, Any]:
    if pipeline_token is not _CONFIG_PIPELINE_TOKEN:
        raise guard.PrelinkError("configure/apply commands require the in-process pipeline")
    plan = _read_json(plan_path)
    plan_sha256 = guard.sha256_file(plan_path)
    if plan_sha256 != trusted_plan_sha256:
        raise guard.PrelinkError("guarded command plan SHA differs from the coordinator-reviewed pin")
    if stage not in ("configure", "apply_kdm6ad_config"):
        raise guard.PrelinkError(f"unsupported configuration pipeline stage: {stage}")

    environment = _planned_environment(plan)
    output_root = workspace / plan["clean_shadow"]["fresh_build_output_root"]
    snapshot_path = workspace / plan["clean_shadow"]["empty_root_snapshot_relative_path"]
    snapshot_sha = plan["trusted_s15_release"]["empty_output_root_snapshot_sha256"]
    guard.validate_prebuild_snapshot(
        snapshot_path, snapshot_sha, output_root,
        workspace / plan["clean_shadow"]["empty_root_snapshot_relative_path"])
    if output_root.exists():
        raise guard.PrelinkError("guarded configure/apply requires build-clean to remain absent")
    capture_gate = plan["resource_gate"]["configure_only"]
    required_free = (capture_gate["maximum_transient_bytes"]
                     + capture_gate["minimum_free_bytes_after_reserve"])
    if shutil_disk_usage(output_root).free < required_free:
        raise guard.PrelinkError("fresh free space is below the configure-only reserve")
    preflight, preflight_sha = _verify_configure_preflight(
        plan, plan_sha256=plan_sha256, workspace=workspace,
        output_root=output_root, snapshot_path=snapshot_path)
    guard.validate_static_pins(
        plan, workspace=workspace, canonical_host=canonical_host,
        shadow_host=shadow_host, overlay_paths=overlay_paths,
        environment=environment)
    guard.validate_clean_shadow(shadow_host, output_root, workspace)
    configure_wrf = shadow_host / "configure.wrf"

    config_commands = {
        "configure": ("configure", "./configure", "configure"),
        "apply_kdm6ad_config": (
            "apply_kdm6ad_config.sh", "./apply_kdm6ad_config.sh", "apply_kdm6ad_config"),
    }
    script_name, relative_argv, receipt_stage = config_commands[stage]
    plan_key = ("configuration_generation_command" if stage == "configure"
                else "configuration_apply_command")
    argv = plan["prelink_requirements"].get(plan_key)
    bash = Path(plan["toolchain"]["tools"]["bash"]["path"]).resolve()
    bash_sha = guard.sha256_file(bash)
    if (argv != [str(bash), relative_argv]
            or bash_sha != plan["toolchain"]["tools"]["bash"]["sha256"]):
        raise guard.PrelinkError("guarded configure command differs from its exact plan/tool pin")
    script_base_sha = plan["prelink_requirements"]["configuration_inputs_sha256"][script_name]
    script_sha = guard.expected_configuration_source_sha256(plan, script_name, shadow=True)
    patch_record = plan["prelink_requirements"].get(
        "shadow_configuration_source_patches", {}).get(script_name)
    script_patch_sha = patch_record.get("patch_sha256") if isinstance(patch_record, dict) else None
    if guard.sha256_file(shadow_host / script_name) != script_sha:
        raise guard.PrelinkError(f"guarded configuration script changed: {script_name}")
    stdin_rel = plan["prelink_requirements"]["configuration_stdin_capture_paths"][receipt_stage]
    stdin_path = _resolve_workspace_path(workspace / "S10", stdin_rel)
    stdin_sha = plan["prelink_requirements"][
        "configure_selection_stdin_sha256" if stage == "configure"
        else "configuration_apply_stdin_sha256"]
    if guard.sha256_file(stdin_path) != stdin_sha:
        raise guard.PrelinkError("guarded configuration stdin capture differs from its exact plan pin")
    captures = plan["prelink_requirements"]["configuration_log_capture_paths"][receipt_stage]
    stdout_path = _resolve_workspace_path(workspace, captures["stdout"])
    stderr_path = _resolve_workspace_path(workspace, captures["stderr"])
    capture_root = (workspace / "S10/configuration_capture").resolve()
    if not stdout_path.is_relative_to(capture_root) or not stderr_path.is_relative_to(capture_root):
        raise guard.PrelinkError("guarded configuration logs escaped the external capture root")
    if stdout_path.exists() or stderr_path.exists():
        raise guard.PrelinkError("guarded configuration log path already exists; refusing overwrite")
    ledger_path = _ledger_path(plan, workspace)
    ledger = _load_or_start_ledger(
        ledger_path, plan_sha256=plan_sha256,
        snapshot_sha256=snapshot_sha,
        preflight_sha256=preflight_sha,
        toolchain_sha256=plan["toolchain"]["toolchain_sha256"],
        tool_environment_sha256=plan["toolchain"]["environment_sha256"],
        output_root=output_root,
        stage=stage)
    if stage == "configure" and configure_wrf.exists():
        raise guard.PrelinkError("configure.wrf already exists; refusing to overwrite stale configuration")
    if stage == "configure":
        if consumption_marker is not None:
            raise guard.PrelinkError("configure pipeline received a reused preflight marker")
        consumption_marker = _consume_configure_preflight(
            plan, plan_sha256=plan_sha256, workspace=workspace,
            preflight=preflight, preflight_sha256=preflight_sha,
            ledger=ledger)
    if stage == "apply_kdm6ad_config":
        if not isinstance(consumption_marker, dict):
            raise guard.PrelinkError("apply requires the one-shot marker from this pipeline invocation")
        if (not isinstance(expected_ledger_sha256, str)
                or guard.sha256_file(ledger_path) != expected_ledger_sha256):
            raise guard.PrelinkError("apply lacks the configure ledger produced in this pipeline")
        marker_path = Path(consumption_marker["configuration_preflight_consumption_marker_path"])
        if (guard.sha256_file(marker_path)
                != consumption_marker["configuration_preflight_consumption_marker_sha256"]
                or ledger.get("configuration_preflight_consumption_marker_sha256")
                != consumption_marker["configuration_preflight_consumption_marker_sha256"]):
            raise guard.PrelinkError("apply marker differs from the in-process configure invocation")
        prior_sha = ledger["commands"][0].get("configure_wrf_sha256_after")
        if (not isinstance(prior_sha, str) or guard.sha256_file(configure_wrf) != prior_sha):
            raise guard.PrelinkError("configure.wrf changed since guarded ./configure")

    result = subprocess.run(
        argv, cwd=shadow_host, input=stdin_path.read_bytes(),
        capture_output=True, env=environment, shell=False, check=False)
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_bytes(result.stdout)
    stderr_path.write_bytes(result.stderr)
    configure_wrf_sha = guard.sha256_file(configure_wrf) if configure_wrf.is_file() else None
    row = {
        "stage": receipt_stage,
        "tool_name": "bash", "tool_path": str(bash), "tool_sha256": bash_sha,
        "script_sha256": script_sha,
        "canonical_script_sha256": script_base_sha,
        "script_patch_sha256": script_patch_sha,
        "argv": argv,
        "flags": guard._argv_option_tokens(argv), "cwd": str(shadow_host.resolve()),
        "environment_sha256": plan["toolchain"]["environment_sha256"],
        "shell": False, "returncode": result.returncode,
        "stdout_path": str(stdout_path), "stdout_sha256": guard.sha256_file(stdout_path),
        "stderr_path": str(stderr_path), "stderr_sha256": guard.sha256_file(stderr_path),
        "stdin_path": str(stdin_path), "stdin_sha256": stdin_sha,
        "netcdf_tool_probes": None,
        "configure_wrf_sha256_after": configure_wrf_sha,
        "output_root_absent_before": True,
        "output_root_absent_after": not output_root.exists(),
        "configuration_preflight_consumption_marker_sha256": ledger.get(
            "configuration_preflight_consumption_marker_sha256"),
        "configuration_preflight_consumption_nonce": ledger.get(
            "configuration_preflight_consumption_nonce"),
        "configuration_pipeline_id": ledger.get("configuration_pipeline_id"),
    }
    ledger["commands"].append(row)
    ledger["last_command_returncode"] = result.returncode
    ledger["last_configure_wrf_sha256"] = configure_wrf_sha
    ledger["status"] = "IN_PROGRESS" if result.returncode == 0 else "FAILED"
    _write_ledger(ledger_path, ledger)
    try:
        if stage == "configure" and result.returncode == 0:
            configure_stdout = result.stdout.decode(errors="replace")
            guard.validate_configure_success_stdout(configure_stdout)
            row["netcdf_tool_probes"] = _netcdf_post_config_probes(plan)
            ledger["commands"][-1]["netcdf_tool_probes"] = row[
                "netcdf_tool_probes"]
            _write_ledger(ledger_path, ledger)
        if (stage == "configure" and result.returncode == 0
                and row["netcdf_tool_probes"] is not None):
            guard._validate_netcdf_config_probes(row, plan, shadow_host)
            configure_stdout = result.stdout.decode(errors="replace")
            for marker in plan["prelink_requirements"][
                    "netcdf_config_invocation_policy"].get("configure_log_assertions", []):
                if marker not in configure_stdout:
                    raise guard.PrelinkError(f"configure output omits pinned NetCDF report: {marker}")
        guard.validate_prebuild_snapshot(
            snapshot_path, snapshot_sha, output_root,
            workspace / plan["clean_shadow"]["empty_root_snapshot_relative_path"])
        if output_root.exists():
            raise guard.PrelinkError("guarded configure/apply wrote into the build output root")
        if shutil_disk_usage(output_root).free < required_free:
            raise guard.PrelinkError("post-command free space fell below the configure-only reserve")
        guard.validate_clean_shadow(shadow_host, output_root, workspace)
        if result.returncode != 0:
            raise guard.PrelinkError(f"guarded {stage} exited with status {result.returncode}")
    except Exception as exc:
        ledger["status"] = "FAILED"
        ledger["failure"] = str(exc)
        _write_ledger(ledger_path, ledger)
        raise
    ledger["status"] = "COMPLETE" if stage == "apply_kdm6ad_config" else "IN_PROGRESS"
    ledger_sha = _write_ledger(ledger_path, ledger)
    return {
        **row,
        "configuration_command_ledger_path": str(ledger_path),
        "configuration_command_ledger_sha256": ledger_sha,
        "configuration_resource_preflight_receipt_sha256": preflight_sha,
        "configuration_preflight_consumption_marker_path": ledger.get(
            "configuration_preflight_consumption_marker_path"),
        "configuration_preflight_consumption_marker_sha256": ledger.get(
            "configuration_preflight_consumption_marker_sha256"),
        "configuration_preflight_consumption_nonce": ledger.get(
            "configuration_preflight_consumption_nonce"),
        "configuration_pipeline_id": ledger.get("configuration_pipeline_id"),
        "plan_sha256": plan_sha256,
    }


def execute_guarded_configuration_pipeline(*, plan_path: Path,
                                            trusted_plan_sha256: str,
                                            workspace: Path,
                                            canonical_host: Path,
                                            shadow_host: Path,
                                            overlay_paths: dict[str, Path]) -> dict[str, Any]:
    """Run configure and apply consecutively in one in-process invocation."""
    first = _execute_config_command(
        stage="configure", plan_path=plan_path,
        trusted_plan_sha256=trusted_plan_sha256, workspace=workspace,
        canonical_host=canonical_host, shadow_host=shadow_host,
        overlay_paths=overlay_paths, pipeline_token=_CONFIG_PIPELINE_TOKEN)
    second = _execute_config_command(
        stage="apply_kdm6ad_config", plan_path=plan_path,
        trusted_plan_sha256=trusted_plan_sha256, workspace=workspace,
        canonical_host=canonical_host, shadow_host=shadow_host,
        overlay_paths=overlay_paths, pipeline_token=_CONFIG_PIPELINE_TOKEN,
        expected_ledger_sha256=first["configuration_command_ledger_sha256"],
        consumption_marker={
            key: first[key] for key in (
                "configuration_preflight_consumption_marker_path",
                "configuration_preflight_consumption_marker_sha256",
                "configuration_preflight_consumption_nonce",
                "configuration_pipeline_id",
            )
        })
    plan = _read_json(plan_path)
    return {
        "schema": "s10-guarded-configuration-execution-v1",
        "plan_sha256": trusted_plan_sha256,
        "configuration_commands": [first, second],
        "configuration_command_ledger_path": second["configuration_command_ledger_path"],
        "configuration_command_ledger_sha256": second["configuration_command_ledger_sha256"],
        "configuration_resource_preflight_receipt_sha256": (
            second["configuration_resource_preflight_receipt_sha256"]),
        "configuration_preflight_consumption_marker_path": (
            second["configuration_preflight_consumption_marker_path"]),
        "configuration_preflight_consumption_marker_sha256": (
            second["configuration_preflight_consumption_marker_sha256"]),
        "configuration_preflight_consumption_nonce": (
            second["configuration_preflight_consumption_nonce"]),
        "configuration_pipeline_id": second["configuration_pipeline_id"],
        "configure_wrf_sha256": second["configure_wrf_sha256_after"],
        "toolchain_sha256": plan["toolchain"]["toolchain_sha256"],
        "tool_environment": guard.tool_environment_snapshot(
            _planned_environment(plan)),
    }


def execute_guarded_stage(*, stage: str, plan_path: Path,
                          trusted_plan_sha256: str,
                          workspace: Path, canonical_host: Path,
                          shadow_host: Path, overlay_paths: dict[str, Path],
                          build_command_key: str | None = None,
                          trusted_s15_release_sha256: str | None = None,
                          trusted_resource_approval_sha256: str | None = None) -> dict[str, Any]:
    if stage in ("configure", "apply_kdm6ad_config"):
        raise guard.PrelinkError(
            "configure/apply are only available through execute_guarded_configuration_pipeline")
    plan = _read_json(plan_path)
    plan_sha256 = guard.sha256_file(plan_path)
    if plan_sha256 != trusted_plan_sha256:
        raise guard.PrelinkError("guarded command plan SHA differs from the coordinator-reviewed pin")
    if stage not in ("preprocess", "object", "link"):
        raise guard.PrelinkError(f"unsupported S10 guarded stage: {stage}")
    gate = plan.get("resource_gate", {})
    if (gate.get("status") == "BLOCKED_PENDING_ESTIMATE_AND_REVIEW"
            or gate.get("full_matrix_build_or_link_allowed") is not True):
        raise guard.PrelinkError(
            f"resource gate is blocked; no {stage} command was launched")
    templates = plan.get("build_matrix", {}).get("guarded_command_templates")
    if not isinstance(templates, dict) or not build_command_key \
            or build_command_key not in templates:
        raise guard.PrelinkError(
            "build command templates are unsupported/unpinned; no subprocess was launched")
    raise guard.PrelinkError(
        "guarded build execution remains unsupported until an independently reviewed runner is added")


def _build_stage_cli_block(plan: dict[str, Any], stage: str,
                           command_key: str | None) -> None:
    gate = plan.get("resource_gate", {})
    if (gate.get("status") == "BLOCKED_PENDING_ESTIMATE_AND_REVIEW"
            or gate.get("full_matrix_build_or_link_allowed") is not True):
        raise guard.PrelinkError(
            f"resource gate is blocked; {stage} command was not launched")
    templates = plan.get("build_matrix", {}).get("guarded_command_templates")
    if not isinstance(templates, dict) or command_key not in templates:
        raise guard.PrelinkError("build argv templates are null/unreviewed; no command was launched")
    raise guard.PrelinkError(
        "S10 preprocess/object/link execution is unsupported by this guarded runner revision")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("configure-pipeline", "preprocess",
                                              "object", "link"), required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--trusted-plan-sha256", required=True,
                        help="plan digest delivered by the reviewing coordinator")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--canonical-host", type=Path, required=True)
    parser.add_argument("--shadow-host", type=Path, required=True)
    parser.add_argument("--overlay", action="append", default=[])
    parser.add_argument("--build-command-key")
    parser.add_argument("--trusted-s15-release-sha256")
    parser.add_argument("--trusted-resource-approval-sha256")
    args = parser.parse_args()
    try:
        plan = _read_json(args.plan)
        if args.stage in ("preprocess", "object", "link"):
            _build_stage_cli_block(plan, args.stage, args.build_command_key)
        command_args = {
            "plan_path": args.plan,
            "trusted_plan_sha256": args.trusted_plan_sha256,
            "workspace": args.workspace.resolve(),
            "canonical_host": args.canonical_host,
            "shadow_host": args.shadow_host,
            "overlay_paths": guard._overlay_args(args.overlay),
        }
        if args.stage == "configure-pipeline":
            result = execute_guarded_configuration_pipeline(**command_args)
        else:
            result = execute_guarded_stage(
                stage=args.stage, **command_args,
                build_command_key=args.build_command_key,
                trusted_s15_release_sha256=args.trusted_s15_release_sha256,
                trusted_resource_approval_sha256=args.trusted_resource_approval_sha256)
    except (guard.PrelinkError, KeyError, TypeError, ValueError, OSError) as exc:
        print(f"GUARDED S10 COMMAND BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
