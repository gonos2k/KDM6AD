from __future__ import annotations

import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import s10_prelink_guard as guard  # noqa: E402
import s10_guarded_exec as guarded_exec  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "evidence/s10_czeroqg_prelink_plan_2026-09-26.json"
ESTIMATE_PATH = ROOT / "evidence/s10_build_preparation_estimate_2026-09-27.json"


def _plan() -> dict:
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def test_build_preparation_template_declares_outputs_but_no_fake_link_inputs():
    plan = _plan()
    guard.validate_build_preparation_command_plan(plan)
    commands = plan["build_matrix"]["build_command_templates"]
    assert commands["runner_execution_allowed"] is False
    assert commands["link_command_template"] is None
    assert commands["link_inputs"]["canonical_archive_sha256"] == plan[
        "build_matrix"]["link_input_archive"]["sha256"]
    for key in ("canonical_main_wrf_object", "canonical_kdm6ad_exit_object",
                "canonical_module_wrf_top_object", "private_libkdm6_c_dylib",
                "complete_configure_wrf_external_library_inputs", "complete_link_argv"):
        assert commands["link_inputs"][key] is None
    assert commands["link_inputs"]["canonical_archive_absolute_path_policy"].startswith(
        "A future guarded runner must resolve")
    assert commands["arms"]["mp37_B"]["source_relative_path"] is None
    assert commands["arms"]["mp237_B"]["source_relative_path"] is None
    assert commands["arms"]["mp37_B"]["source_materialization_required"] is True
    assert plan["resource_gate"]["status"] == "BLOCKED_PENDING_ESTIMATE_AND_REVIEW"
    assert plan["resource_gate"]["full_matrix_build_or_link_allowed"] is False
    assert plan["resource_gate"]["model_runs"]["allowed"] is False


@pytest.mark.parametrize("mutation", ["wrong_schema", "run_components", "arm_total",
                                       "bool_bytes", "complete_link_inputs"])
def test_build_preparation_estimate_rejects_incomplete_or_run_entangled_data(mutation: str):
    estimate = json.loads(ESTIMATE_PATH.read_text(encoding="utf-8"))
    if mutation == "wrong_schema":
        estimate["schema"] = "s10-build-output-estimate-v1"
    elif mutation == "run_components":
        estimate["model_run_components_included"] = True
    elif mutation == "arm_total":
        estimate["variants"]["mp37_B"]["estimated_bytes"] += 1
    elif mutation == "bool_bytes":
        estimate["variants"]["mp37_B"]["components"]["object_module_bytes"] = True
    elif mutation == "complete_link_inputs":
        estimate["missing_link_inputs"]["private_libkdm6_c_dylib"] = "unverified"
    with pytest.raises(guard.PrelinkError):
        guard.validate_build_preparation_estimate(estimate)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
            ("aggregate_ready", "measurement-only with build/run blocked"),
            ("run_allowed", "measurement-only with build/run blocked"),
            ("build_gate_ready", "measurement-only with build/run blocked"),
        ("measurement_disabled", "measurement-only"),
        ("estimate_sha_malformed", "measurement-only"),
        ("common_macro_guard_drift", "common CPP define set/order"),
        ("guard_macro_in_fixed_cppflags", "preprocessing stages differ"),
        ("guard_macro_in_cpp_template", "preprocessing stages differ"),
        ("guard_macro_in_object_argv", "object command template lacks"),
        ("b_guard_name_present", "macro/source pins"),
        ("make_allowed", "generic Make"),
        ("b_guard_on", "macro/source pins"),
        ("c_guard_off", "macro/source pins"),
        ("duplicate_object_output", "object command path options"),
        ("cross_arm_module_path", "object command path"),
        ("source_path_escape", "unsafe for mp37_B"),
        ("complete_link_argv_fake", "link template must remain absent"),
        ("fake_missing_object", "link template must remain absent"),
        ("shell_preprocess", "four ordered shell-free stages"),
    ],
)
def test_build_preparation_plan_mutations_fail_closed(mutation: str, message: str):
    plan = _plan()
    commands = plan["build_matrix"]["build_command_templates"]
    if mutation == "aggregate_ready":
        plan["resource_gate"]["status"] = "READY_PENDING_COORDINATOR_RELEASE"
    elif mutation == "run_allowed":
        plan["resource_gate"]["model_runs"]["allowed"] = True
    elif mutation == "build_gate_ready":
        plan["resource_gate"]["build"]["status"] = "READY_PENDING_COORDINATOR_RELEASE"
    elif mutation == "measurement_disabled":
        plan["resource_gate"]["build_preparation"]["measurement_only_allowed"] = False
    elif mutation == "estimate_sha_malformed":
        plan["resource_gate"]["build_preparation"]["estimate_sha256"] = "not-a-hash"
    elif mutation == "common_macro_guard_drift":
        macros = plan["build_matrix"]["common_required_compile_macros"] + [
            "KDM6_PROGB_ZERO_QG_DIV_GUARD"]
        plan["build_matrix"]["common_required_compile_macros"] = macros
        for arm in commands["arms"].values():
            arm["common_preprocessor_defines"] = macros
    elif mutation == "guard_macro_in_fixed_cppflags":
        commands["preprocessing_command_stages"][1][
            "fixed_configure_wrf_cppflags_tokens"].append(
                "-DKDM6_PROGB_ZERO_QG_DIV_GUARD")
    elif mutation == "guard_macro_in_cpp_template":
        commands["preprocessing_command_stages"][1]["argv_template"].insert(
            -1, "-DKDM6_PROGB_ZERO_QG_DIV_GUARD")
    elif mutation == "guard_macro_in_object_argv":
        template = commands["object_command_template"]
        template["guard_macro_in_object_argv"] = True
        template["argv"].insert(-1, "-DKDM6_PROGB_ZERO_QG_DIV_GUARD")
        for arm in commands["arms"].values():
            arm["object_command_argv"].insert(-1, "-DKDM6_PROGB_ZERO_QG_DIV_GUARD")
    elif mutation == "b_guard_name_present":
        commands["arms"]["mp37_B"]["guard_macro"] = "KDM6_PROGB_ZERO_QG_DIV_GUARD"
    elif mutation == "make_allowed":
        commands["generic_make_execution_allowed"] = True
    elif mutation == "b_guard_on":
        commands["arms"]["mp37_B"]["guard_macro_defined"] = True
    elif mutation == "c_guard_off":
        commands["arms"]["mp237_C"]["guard_macro_defined"] = False
    elif mutation == "duplicate_object_output":
        commands["arms"]["mp37_B"]["object_command_argv"].extend(["-o", "elsewhere.o"])
    elif mutation == "cross_arm_module_path":
        argv = commands["arms"]["mp37_C"]["object_command_argv"]
        argv[argv.index("-J") + 1] = "../mp37/B/mod"
    elif mutation == "source_path_escape":
        commands["arms"]["mp37_B"]["source_relative_path"] = "../../canonical/module.F"
    elif mutation == "complete_link_argv_fake":
        commands["link_command_template"] = ["<pinned-mpif90>", "-o", "wrf.exe"]
    elif mutation == "fake_missing_object":
        commands["link_inputs"]["canonical_main_wrf_object"] = "main/wrf.o"
    elif mutation == "shell_preprocess":
        commands["preprocessing_command_stages"][2]["shell"] = True
    with pytest.raises(guard.PrelinkError, match=message):
        guard.validate_build_preparation_command_plan(plan)


def _measurement_fixture(tmp_path: Path) -> tuple[dict, Path, Path, Path, Path]:
    plan = _plan()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output_root = workspace / plan["clean_shadow"]["fresh_build_output_root"]
    snapshot_path = workspace / plan["clean_shadow"]["empty_root_snapshot_relative_path"]
    snapshot = guard.create_empty_root_snapshot(output_root, snapshot_path)
    plan["trusted_s15_release"]["empty_output_root_snapshot_sha256"] = \
        snapshot["snapshot_sha256"]
    estimate_path = workspace / plan["resource_gate"]["build_preparation"][
        "estimate_relative_path"]
    estimate_path.parent.mkdir(parents=True)
    estimate_path.write_bytes(ESTIMATE_PATH.read_bytes())
    receipt_path = workspace / plan["resource_gate"]["build_preparation"][
        "measurement_only_receipt_relative_path"]
    return plan, workspace, output_root, snapshot_path, receipt_path


def test_build_preparation_measurement_is_receipt_only_and_run_free(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    plan, workspace, output_root, snapshot_path, receipt_path = _measurement_fixture(tmp_path)
    static_pin_calls = []
    monkeypatch.setattr(guard, "planned_tool_environment", lambda _plan: {})
    monkeypatch.setattr(guard, "validate_static_pins",
                        lambda *args, **kwargs: static_pin_calls.append((args, kwargs)) or {})
    monkeypatch.setattr(guard.shutil, "disk_usage", lambda _path: SimpleNamespace(
        total=100 * 1024**3, used=40 * 1024**3, free=60 * 1024**3))
    estimate_path = workspace / plan["resource_gate"]["build_preparation"][
        "estimate_relative_path"]
    receipt = guard.create_resource_preflight_receipt(
        plan, plan_sha256="a" * 64, workspace=workspace,
        canonical_host=workspace / "canonical", shadow_host=workspace / "shadow",
        overlay_paths={"mp37": workspace / "mp37", "mp237": workspace / "mp237"},
        output_root=output_root, snapshot_path=snapshot_path,
        phase="build-preparation-measure", receipt_path=receipt_path,
        estimate_path=estimate_path)

    assert len(static_pin_calls) == 1
    assert receipt["status"] == "MEASURED_BUILD_PREPARATION_CAPACITY_ONLY"
    assert receipt["build_preparation_measurement_only"] is True
    assert receipt["build_preparation_capacity_status"] == "MEASURED_ONLY_INCOMPLETE_COMMAND_INPUTS"
    assert receipt["build_execution_allowed"] is False
    assert receipt["model_execution_allowed"] is False
    assert receipt["allowed_commands"] == []
    assert receipt["coordinator_resource_approval_sha256"] is None
    assert receipt["s15_release_receipt_sha256"] is None
    assert not output_root.exists()

    with pytest.raises(guard.PrelinkError, match="resource gate is blocked"):
        guard.validate_build_resource_preflight(
            plan, receipt, plan_sha256="a" * 64,
            snapshot_sha256=plan["trusted_s15_release"][
                "empty_output_root_snapshot_sha256"],
            output_root=output_root, trusted_approval_sha256="b" * 64)
    with pytest.raises(guard.PrelinkError, match="resource gate is blocked"):
        guard.create_resource_preflight_receipt(
            plan, plan_sha256="a" * 64, workspace=workspace,
            canonical_host=workspace / "canonical", shadow_host=workspace / "shadow",
            overlay_paths={"mp37": workspace / "mp37", "mp237": workspace / "mp237"},
            output_root=output_root, snapshot_path=snapshot_path,
            phase="build", receipt_path=workspace / plan["resource_gate"]["build"][
                "prebuild_gate_receipt_relative_path"])


def test_build_preparation_cli_writes_measurement_receipt_without_wrf_commands(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    plan, workspace, output_root, _snapshot_path, receipt_path = _measurement_fixture(tmp_path)
    plan_path = workspace / "plan.json"
    plan_path.write_text(json.dumps(plan, sort_keys=True), encoding="utf-8")
    estimate_path = workspace / plan["resource_gate"]["build_preparation"][
        "estimate_relative_path"]
    plan_sha = guard.sha256_file(plan_path)
    static_pin_calls = []
    subprocess_calls = []
    monkeypatch.setattr(guard, "planned_tool_environment", lambda _plan: {})
    monkeypatch.setattr(guard, "validate_static_pins",
                        lambda *args, **kwargs: static_pin_calls.append(True) or {})
    monkeypatch.setattr(guard.subprocess, "run",
                        lambda *args, **kwargs: subprocess_calls.append(args) or None)
    monkeypatch.setattr(guard.shutil, "disk_usage", lambda _path: SimpleNamespace(
        total=100 * 1024**3, used=40 * 1024**3, free=60 * 1024**3))

    cli_args = [
        "--phase", "build-preparation-measure",
        "--plan", str(plan_path),
        "--trusted-plan-sha256", plan_sha,
        "--workspace", str(workspace),
        "--canonical-host", str(workspace / "canonical"),
        "--shadow-host", str(workspace / "shadow"),
        "--overlay", f"mp37={workspace / 'mp37-overlay'}",
        "--overlay", f"mp237={workspace / 'mp237-overlay'}",
        "--estimate", str(estimate_path),
    ]
    wrong_pin_args = list(cli_args)
    wrong_pin_args[wrong_pin_args.index(plan_sha)] = "0" * 64
    wrong_pin_result = guard.resource_preflight_main(wrong_pin_args)
    wrong_pin_output = capsys.readouterr()
    assert wrong_pin_result == 2
    assert "coordinator-trusted pin" in wrong_pin_output.err
    assert static_pin_calls == []
    assert subprocess_calls == []
    assert not receipt_path.exists()

    exit_code = guard.resource_preflight_main(cli_args)
    result = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert result["phase"] == "build-preparation-measure"
    assert result["allowed_commands"] == []
    assert result["build_execution_allowed"] is False
    assert result["model_execution_allowed"] is False
    assert result["status"] == "MEASURED_BUILD_PREPARATION_CAPACITY_ONLY"
    assert result["static_pin_validation_completed"] is True
    assert result["measurement_subprocess_scope"] == plan["resource_gate"][
        "build_preparation"]["measurement_subprocess_scope"]
    assert result["wrf_preprocess_object_link_or_model_commands_launched"] is False
    assert len(static_pin_calls) == 1
    assert subprocess_calls == []
    assert receipt_path.is_file()
    assert not output_root.exists()

    receipt_path.unlink()
    blocked = guard.resource_preflight_main([
        "--phase", "build-preparation-measure",
        "--plan", str(plan_path),
        "--trusted-plan-sha256", plan_sha,
        "--workspace", str(workspace),
        "--canonical-host", str(workspace / "canonical"),
        "--shadow-host", str(workspace / "shadow"),
        "--overlay", f"mp37={workspace / 'mp37-overlay'}",
        "--overlay", f"mp237={workspace / 'mp237-overlay'}",
        "--estimate", str(estimate_path),
        "--resource-approval", str(workspace / "approval.json"),
        "--trusted-resource-approval-sha256", "d" * 64,
    ])
    assert blocked == 2
    assert not receipt_path.exists()
    assert len(static_pin_calls) == 1
    assert subprocess_calls == []


def test_build_preparation_measurement_reports_low_capacity_without_authorizing(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    plan, workspace, output_root, snapshot_path, receipt_path = _measurement_fixture(tmp_path)
    monkeypatch.setattr(guard, "planned_tool_environment", lambda _plan: {})
    monkeypatch.setattr(guard, "validate_static_pins", lambda *args, **kwargs: {})
    estimate = json.loads((workspace / plan["resource_gate"]["build_preparation"][
        "estimate_relative_path"]).read_text())
    required = estimate["total_estimated_bytes"] * plan["resource_gate"][
        "build_preparation"]["safety_factor"] + plan["resource_gate"][
            "build_preparation"]["reserve_free_bytes"]
    monkeypatch.setattr(guard.shutil, "disk_usage", lambda _path: SimpleNamespace(
        total=required, used=required - 1, free=1))
    receipt = guard.create_resource_preflight_receipt(
        plan, plan_sha256="c" * 64, workspace=workspace,
        canonical_host=workspace / "canonical", shadow_host=workspace / "shadow",
        overlay_paths={"mp37": workspace / "mp37", "mp237": workspace / "mp237"},
        output_root=output_root, snapshot_path=snapshot_path,
        phase="build-preparation-measure", receipt_path=receipt_path,
        estimate_path=workspace / plan["resource_gate"]["build_preparation"][
            "estimate_relative_path"])
    assert receipt["build_preparation_capacity_status"] == "INSUFFICIENT_FOR_PROPOSAL"
    assert receipt["allowed_commands"] == []
    assert receipt["build_execution_allowed"] is False
    assert not output_root.exists()


@pytest.mark.parametrize("stage", ["preprocess", "object", "link"])
def test_build_measurement_does_not_open_guarded_build_execution(
        tmp_path: Path, stage: str):
    plan_path = tmp_path / "plan.json"
    plan = _plan()
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(guard.PrelinkError, match="resource gate is blocked"):
        guarded_exec._build_stage_cli_block(plan, stage, "mp37_B")
