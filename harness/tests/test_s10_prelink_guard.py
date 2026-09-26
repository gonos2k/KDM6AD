from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from s10_prelink_guard import (  # noqa: E402
    PrelinkError,
    _argv_option_tokens,
    _ensure_output_target,
    _validate_configure_pipeline,
    _validate_netcdf_config_invocations,
    _validate_preprocess_pipeline,
    _validate_tool_command,
    _response_file_refs,
    create_resource_preflight_receipt,
    create_empty_root_snapshot,
    require_fresh_output_root,
    require_s15_release,
    sha256_bytes,
    validate_archive_link,
    validate_clean_shadow,
    validate_configuration_sources,
    validate_normalized_command_pair,
    validate_output_inventory,
    validate_prebuild_snapshot,
    validate_preprocess_macro_delta,
    validate_source_overlay,
    tool_environment_snapshot,
    validate_build_output_estimate,
    validate_build_resource_preflight,
    validate_toolchain,
)


def _release(plan: dict, plan_sha: str, snapshot_sha: str) -> dict:
    trusted = plan["trusted_s15_release"]
    return {
        "schema": "s10-s15-native-lane-release-v1",
        "owner": "S15",
        "status": "RELEASED_FOR_S10_PRELINK",
        "green_red_review": "APPROVED",
        "native_slot_released": True,
        "plan_sha256": plan_sha,
        "s15_merge_commit": trusted["s15_merge_commit"],
        "evidence_manifest_path": trusted["evidence_manifest_path"],
        "evidence_manifest_sha256": trusted["evidence_manifest_sha256"],
        "s15_step2_merge_commit": trusted["s15_step2_merge_commit"],
        "s15_step2_evidence_manifest_path": trusted["s15_step2_evidence_manifest_path"],
        "s15_step2_evidence_manifest_sha256": trusted["s15_step2_evidence_manifest_sha256"],
        "empty_output_root_snapshot_sha256": snapshot_sha,
    }


def test_s15_release_requires_coordinator_pinned_receipt_and_evidence():
    plan = {
        "trusted_s15_release": {
            "s15_merge_commit": "1" * 40,
            "evidence_manifest_path": "harness/evidence/S15.json",
            "evidence_manifest_sha256": "2" * 64,
            "s15_step2_merge_commit": "3" * 40,
            "s15_step2_evidence_manifest_path": "harness/evidence/S15_step2.json",
            "s15_step2_evidence_manifest_sha256": "4" * 64,
            "empty_output_root_snapshot_sha256": "3" * 64,
        }
    }
    plan_sha = sha256_bytes(json.dumps(plan, sort_keys=True, separators=(",", ":")).encode())
    fake = _release(plan, plan_sha, "3" * 64)
    external_trust_sha = "4" * 64
    assert "coordinator_release_receipt_sha256" not in plan["trusted_s15_release"]
    require_s15_release(plan, fake, plan_sha, external_trust_sha, external_trust_sha)
    # The coordinator hash is an out-of-plan trust root, so using it cannot
    # change the plan digest embedded in the release record.
    plan_sha_after_external_input = sha256_bytes(
        json.dumps(plan, sort_keys=True, separators=(",", ":")).encode())
    assert plan_sha_after_external_input == plan_sha
    with pytest.raises(PrelinkError, match="SHA-256 mismatch"):
        require_s15_release(plan, fake, plan_sha, "5" * 64, external_trust_sha)
    with pytest.raises(PrelinkError, match="plan_sha256"):
        require_s15_release(plan, fake, "6" * 64, external_trust_sha, external_trust_sha)


def test_guard_macro_parser_catches_zero_and_split_definitions():
    common = ["/usr/bin/cpp", "-DKDM6_PROGB_VALIDITY_CAPTURE",
              "-DKDM6_PROGB_POLICY_MIDPOINT", "-I", "inc"]
    validate_preprocess_macro_delta(
        common, common + ["-DKDM6_PROGB_ZERO_QG_DIV_GUARD"])
    for forbidden_b in (
        common + ["-DKDM6_PROGB_ZERO_QG_DIV_GUARD=0"],
        common + ["-D", "KDM6_PROGB_ZERO_QG_DIV_GUARD"],
        common + ["-D", "KDM6_PROGB_ZERO_QG_DIV_GUARD=0"],
    ):
        with pytest.raises(PrelinkError, match="B preprocessing defines"):
            validate_preprocess_macro_delta(forbidden_b, common)
    with pytest.raises(PrelinkError, match="bare guard"):
        validate_preprocess_macro_delta(
            common, common + ["-DKDM6_PROGB_ZERO_QG_DIV_GUARD=0"])
    with pytest.raises(PrelinkError, match="undefine"):
        validate_preprocess_macro_delta(
            common + ["-U", "KDM6_PROGB_ZERO_QG_DIV_GUARD"],
            common + ["-DKDM6_PROGB_ZERO_QG_DIV_GUARD"])


def test_normalized_argv_allows_only_guard_and_arm_paths(tmp_path: Path):
    b_root = tmp_path / "S10/build-clean/mp37/B"
    c_root = tmp_path / "S10/build-clean/mp37/C"
    tool = "/opt/homebrew/bin/mpif90"
    b = {
        "stage": "object", "tool_name": "mpif90", "tool_path": tool,
        "tool_sha256": "1" * 64, "cwd": str(b_root),
        "argv": [tool, "-ffp-contract=off", "-o", str(b_root / "module.o"),
                 str(b_root / "module.f90")], "shell": False,
    }
    c = {**b, "cwd": str(c_root), "argv": [
        tool, "-ffp-contract=off", "-o", str(c_root / "module.o"),
        str(c_root / "module.f90")],
    }
    validate_normalized_command_pair(b, c, b_root=b_root, c_root=c_root,
                                     label="object")
    hidden_define = {**c, "argv": [*c["argv"], "-DOTHER"]}
    with pytest.raises(PrelinkError, match="differs beyond"):
        validate_normalized_command_pair(b, hidden_define, b_root=b_root,
                                         c_root=c_root, label="WRF cpp")
    fast_math = {**c, "argv": [tool, "-ffp-contract=off", "-ffast-math",
                               "-o", str(c_root / "module.o"),
                               str(c_root / "module.f90")]}
    with pytest.raises(PrelinkError, match="differs beyond"):
        validate_normalized_command_pair(b, fast_math, b_root=b_root,
                                         c_root=c_root, label="object")
    alternate = {**c, "tool_path": "/tmp/other-mpif90",
                 "argv": ["/tmp/other-mpif90", *c["argv"][1:]]}
    with pytest.raises(PrelinkError, match="differs beyond"):
        validate_normalized_command_pair(b, alternate, b_root=b_root,
                                         c_root=c_root, label="link")

    b_cpp = {**b, "stage": "wrf_cpp", "argv": [
        "/usr/bin/cpp", "-DKDM6_PROGB_VALIDITY_CAPTURE",
        "-DKDM6_PROGB_POLICY_MIDPOINT", "-I", "inc", str(b_root / "input.G")],
        "tool_name": "cpp", "tool_path": "/usr/bin/cpp"}
    c_cpp = {**b_cpp, "argv": [
        "/usr/bin/cpp", "-DKDM6_PROGB_VALIDITY_CAPTURE",
        "-DKDM6_PROGB_POLICY_MIDPOINT", "-DKDM6_PROGB_ZERO_QG_DIV_GUARD",
        "-I", "inc", str(c_root / "input.G")], "cwd": str(c_root)}
    validate_preprocess_macro_delta(b_cpp["argv"], c_cpp["argv"])
    validate_normalized_command_pair(b_cpp, c_cpp, b_root=b_root, c_root=c_root,
                                     strip_guard=True, label="wrf_cpp")
    c_cpp["argv"].insert(-2, "-DOTHER")
    with pytest.raises(PrelinkError, match="differs beyond"):
        validate_normalized_command_pair(b_cpp, c_cpp, b_root=b_root,
                                         c_root=c_root, strip_guard=True,
                                         label="wrf_cpp")


def test_pinned_tool_identity_and_exhaustive_flag_record(tmp_path: Path):
    tool = tmp_path / "bin" / "mpif90"
    tool.parent.mkdir()
    tool.write_bytes(b"pinned compiler wrapper")
    tool.chmod(0o755)
    digest = hashlib.sha256(tool.read_bytes()).hexdigest()
    plan = {"toolchain": {"tools": {"mpif90": {"path": str(tool), "sha256": digest}}}}
    output = tmp_path / "output"
    output.mkdir()
    stdout = output / "compile.stdout"
    stderr = output / "compile.stderr"
    stdout.write_text("")
    stderr.write_text("")
    argv = [str(tool), "-O2", "-ffp-contract=off", "-c", "src.f90"]
    record = {
        "tool_name": "mpif90", "tool_path": str(tool), "tool_sha256": digest,
        "argv": argv, "flags": _argv_option_tokens(argv),
        "cwd": str(output), "shell": False,
        "stdout_path": str(stdout), "stderr_path": str(stderr),
    }
    checked_argv, _ = _validate_tool_command(
        record, expected_name="mpif90", plan=plan, shadow_host=tmp_path,
        output_root=output, label="compile")
    assert checked_argv == argv
    changed_metadata = {**record, "flags": ["-O2", "-ffp-contract=off"]}
    with pytest.raises(PrelinkError, match="exhaustive"):
        _validate_tool_command(changed_metadata, expected_name="mpif90", plan=plan,
                               shadow_host=tmp_path, output_root=output, label="compile")
    alternate = {**record, "tool_path": "/tmp/alternate-mpif90",
                 "argv": ["/tmp/alternate-mpif90", *argv[1:]]}
    with pytest.raises(PrelinkError, match="alternate or unpinned"):
        _validate_tool_command(alternate, expected_name="mpif90", plan=plan,
                               shadow_host=tmp_path, output_root=output, label="compile")
    for injected in ("-imacros", "-include"):
        injected_argv = [str(tool), "-O2", injected, "/tmp/guard_defs.h",
                         "-ffp-contract=off", "-c", "src.f90"]
        injected_record = {**record, "argv": injected_argv,
                           "flags": _argv_option_tokens(injected_argv)}
        with pytest.raises(PrelinkError, match="inject unpinned"):
            _validate_tool_command(injected_record, expected_name="mpif90", plan=plan,
                                   shadow_host=tmp_path, output_root=output,
                                   label="compile")


def test_tool_environment_snapshot_covers_apple_sdk_resolution_inputs():
    environment = tool_environment_snapshot()
    for name in ("SDKROOT", "MACOSX_DEPLOYMENT_TARGET", "DEVELOPER_DIR", "PATH",
                 "GCC_EXEC_PREFIX", "COMPILER_PATH", "LIBRARY_PATH", "NETCDF",
                 "NETCDF_C", "NETCDFPAR", "PNETCDF", "HDF5", "PHDF5"):
        assert name in environment


def test_configuration_source_pins_cover_shadow_configure_inputs(tmp_path: Path):
    canonical = tmp_path / "canonical"
    shadow = tmp_path / "shadow"
    for host in (canonical, shadow):
        (host / "arch").mkdir(parents=True)
        (host / "phys").mkdir()
        (host / "configure").write_text("configure-v1\n")
        (host / "arch/Config.pl").write_text("menu-v1\n")
        (host / "arch/configure.defaults").write_text("options-v1\n")
        (host / "phys/Makefile").write_text("make-v1\n")
    inputs = ("configure", "arch/Config.pl", "arch/configure.defaults", "phys/Makefile")
    pins = {name: hashlib.sha256((canonical / name).read_bytes()).hexdigest()
            for name in inputs}
    plan = {"prelink_requirements": {"configuration_inputs_sha256": pins}}
    validate_configuration_sources(plan, canonical_host=canonical, shadow_host=shadow)
    (shadow / "arch/configure.defaults").write_text("mutated-menu-v1\n")
    with pytest.raises(PrelinkError, match="disposable shadow configuration source changed: arch/configure.defaults"):
        validate_configuration_sources(plan, canonical_host=canonical, shadow_host=shadow)


def _resource_plan(workspace: Path, snapshot_sha: str, *, approved: bool = False):
    estimate = {
        "schema": "s10-build-output-estimate-v1",
        "logging_modes": ["off", "on"],
        "retention_strategy": "reviewed sequential arms with all result evidence retained",
        "shared_staging_components": {
            "selected_case_tree_copy_bytes": 1000,
            "shared_run_support_bytes": 0,
        },
        "shared_staging_bytes": 1000,
        "variants": {},
    }
    component_names = (
        "preprocessed_sources_bytes", "object_module_bytes", "linked_executable_bytes",
        "temporary_build_peak_bytes", "logging_off_input_copy_bytes",
        "logging_off_run_staging_bytes", "logging_off_run_output_bytes",
        "logging_off_log_bytes", "logging_on_input_copy_bytes",
        "logging_on_run_staging_bytes", "logging_on_run_output_bytes",
        "logging_on_log_bytes",
    )
    for name in ("mp37_B", "mp37_C", "mp237_B", "mp237_C"):
        components = {key: 100 for key in component_names}
        estimate["variants"][name] = {
            "components": components,
            "estimated_bytes": sum(components.values()),
        }
    estimate["total_estimated_bytes"] = estimate["shared_staging_bytes"] + sum(
        row["estimated_bytes"] for row in estimate["variants"].values())
    estimate["peak_concurrent_bytes"] = 2400
    estimate_path = workspace / "S10/build_output_estimate.json"
    estimate_path.parent.mkdir(parents=True, exist_ok=True)
    estimate_path.write_text(json.dumps(estimate, indent=2) + "\n")
    estimate_sha = hashlib.sha256(estimate_path.read_bytes()).hexdigest()
    snapshot_sha256 = snapshot_sha
    plan = {
        "clean_shadow": {
            "fresh_build_output_root": "S10/build-clean",
            "empty_root_snapshot_relative_path": "S10/prebuild_output_root_snapshot.json",
        },
        "trusted_s15_release": {
            "s15_merge_commit": "1" * 40,
            "evidence_manifest_path": "harness/evidence/S15.json",
            "evidence_manifest_sha256": "2" * 64,
            "s15_step2_merge_commit": "3" * 40,
            "s15_step2_evidence_manifest_path": "harness/evidence/S15_step2.json",
            "s15_step2_evidence_manifest_sha256": "4" * 64,
            "empty_output_root_snapshot_sha256": snapshot_sha256,
        },
        "resource_gate": {
            "status": "READY_PENDING_COORDINATOR_RELEASE" if approved
            else "BLOCKED_PENDING_ESTIMATE_AND_REVIEW",
            "full_matrix_build_or_link_allowed": False,
            "configure_only": {
                "allowed": True,
                "allowed_commands": ["./configure", "./apply_kdm6ad_config.sh"],
                "maximum_transient_bytes": 512 * 1024 * 1024,
                "minimum_free_bytes_after_reserve": 2 * 1024 * 1024 * 1024,
                "output_root_must_remain_absent": True,
                "capture_root_relative_to_workspace": "S10/configuration_capture",
                "preflight_receipt_relative_path": "S10/configuration_capture/configure_resource_preflight.json",
            },
            "build": {
                "status": "READY_PENDING_COORDINATOR_RELEASE" if approved
                else "BLOCKED_PENDING_ESTIMATE_AND_REVIEW",
                "prebuild_gate_receipt_required": True,
                "prebuild_gate_receipt_relative_path": "S10/build_resource_preflight.json",
                "measurement_receipt_relative_path": "S10/build_resource_measurement.json",
                "coordinator_approval_relative_path": "S10/coordinator_resource_approval.json",
                "output_size_estimate_relative_path": "S10/build_output_estimate.json",
                "output_size_estimate_sha256": estimate_sha,
                "estimated_total_bytes": estimate["total_estimated_bytes"],
                "safety_factor": 2,
                "reserve_free_bytes": 500,
                "minimum_free_bytes": 1000,
                "prebuild_receipt_max_age_seconds": 3600,
                "coordinator_resource_approval_required": True,
                "s15_release_receipt_required": True,
                "allowed_build_stages": ["preprocessing", "object_compilation", "link"],
            },
        },
    }
    plan_bytes = json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
    return plan, estimate, estimate_path, hashlib.sha256(plan_bytes).hexdigest()


def test_build_resource_gate_fails_closed_while_plan_is_blocked(tmp_path: Path,
                                                                monkeypatch):
    workspace = tmp_path
    output_root = workspace / "S10/build-clean"
    snapshot_path = workspace / "S10/prebuild_output_root_snapshot.json"
    snapshot_path.parent.mkdir(parents=True)
    snapshot = create_empty_root_snapshot(output_root, snapshot_path)
    plan, _, _, plan_sha = _resource_plan(workspace, snapshot["snapshot_sha256"])
    with pytest.raises(PrelinkError, match="resource gate is blocked"):
        create_resource_preflight_receipt(
            plan, plan_sha256=plan_sha, workspace=workspace,
            canonical_host=workspace / "canonical", shadow_host=workspace / "shadow",
            overlay_paths={}, output_root=output_root, snapshot_path=snapshot_path,
            phase="build", receipt_path=workspace / "S10/build_resource_preflight.json")


def test_prelink_rejects_fabricated_build_receipt_while_plan_is_blocked(tmp_path: Path):
    workspace = tmp_path
    output_root = workspace / "S10/build-clean"
    snapshot_path = workspace / "S10/prebuild_output_root_snapshot.json"
    snapshot_path.parent.mkdir(parents=True)
    snapshot = create_empty_root_snapshot(output_root, snapshot_path)
    plan, _, _, plan_sha = _resource_plan(workspace, snapshot["snapshot_sha256"])
    fabricated = {
        "schema": "s10-resource-preflight-receipt-v1",
        "phase": "build",
        "status": "READY_FOR_REVIEWED_BUILD",
    }
    with pytest.raises(PrelinkError, match="resource gate is blocked"):
        validate_build_resource_preflight(
            plan, fabricated, plan_sha256=plan_sha,
            snapshot_sha256=snapshot["snapshot_sha256"], output_root=output_root,
            trusted_approval_sha256="f" * 64)


def test_configure_only_resource_gate_is_bounded_and_keeps_build_root_absent(
        tmp_path: Path, monkeypatch):
    import s10_prelink_guard as guard_module

    monkeypatch.setattr(guard_module, "validate_static_pins", lambda *a, **k: {})
    monkeypatch.setattr(guard_module.shutil, "disk_usage", lambda _path: SimpleNamespace(
        total=10 * 1024**3, used=7 * 1024**3, free=3 * 1024**3))
    workspace = tmp_path
    output_root = workspace / "S10/build-clean"
    snapshot_path = workspace / "S10/prebuild_output_root_snapshot.json"
    snapshot_path.parent.mkdir(parents=True)
    snapshot = create_empty_root_snapshot(output_root, snapshot_path)
    plan, _, _, plan_sha = _resource_plan(workspace, snapshot["snapshot_sha256"])
    receipt_path = workspace / plan["resource_gate"]["configure_only"][
        "preflight_receipt_relative_path"]
    receipt = create_resource_preflight_receipt(
        plan, plan_sha256=plan_sha, workspace=workspace,
        canonical_host=workspace / "canonical", shadow_host=workspace / "shadow",
        overlay_paths={}, output_root=output_root, snapshot_path=snapshot_path,
        phase="configure", receipt_path=receipt_path,
    )
    assert receipt["status"] == "ALLOW_CONFIGURE_ONLY"
    assert receipt["allowed_commands"] == ["./configure", "./apply_kdm6ad_config.sh"]
    assert receipt["required_free_bytes"] == 512 * 1024 * 1024 + 2 * 1024 * 1024 * 1024
    assert not output_root.exists()
    monkeypatch.setattr(guard_module.shutil, "disk_usage", lambda _path: SimpleNamespace(
        total=10 * 1024**3, used=10 * 1024**3 - receipt["required_free_bytes"] + 1,
        free=receipt["required_free_bytes"] - 1))
    with pytest.raises(PrelinkError, match="below the configure-only reserve"):
        create_resource_preflight_receipt(
            plan, plan_sha256=plan_sha, workspace=workspace,
            canonical_host=workspace / "canonical", shadow_host=workspace / "shadow",
            overlay_paths={}, output_root=output_root, snapshot_path=snapshot_path,
            phase="configure", receipt_path=receipt_path)
    output_root.mkdir()
    with pytest.raises(PrelinkError, match="output root to remain absent"):
        create_resource_preflight_receipt(
            plan, plan_sha256=plan_sha, workspace=workspace,
            canonical_host=workspace / "canonical", shadow_host=workspace / "shadow",
            overlay_paths={}, output_root=output_root, snapshot_path=snapshot_path,
            phase="configure", receipt_path=receipt_path)


def test_build_output_estimate_requires_all_arms_and_both_logging_modes(tmp_path: Path):
    _, estimate, _, _ = _resource_plan(tmp_path, "a" * 64)
    total, arms = validate_build_output_estimate(estimate)
    assert set(arms) == {"mp37_B", "mp37_C", "mp237_B", "mp237_C"}
    assert total == estimate["total_estimated_bytes"]
    estimate["logging_modes"] = ["off"]
    with pytest.raises(PrelinkError, match="logging off and on"):
        validate_build_output_estimate(estimate)
    estimate["logging_modes"] = ["off", "on"]
    del estimate["variants"]["mp37_C"]["components"]["logging_on_run_output_bytes"]
    with pytest.raises(PrelinkError, match="components are incomplete"):
        validate_build_output_estimate(estimate)


def test_resource_preflight_requires_coordinator_release_and_approval(tmp_path: Path,
                                                                     monkeypatch):
    import s10_prelink_guard as guard_module

    monkeypatch.setattr(guard_module, "validate_static_pins", lambda *a, **k: {})
    monkeypatch.setattr(guard_module.shutil, "disk_usage", lambda _path: SimpleNamespace(
        total=100_000, used=80_000, free=20_000))
    monkeypatch.setattr(guard_module.time, "time_ns", lambda: 10_000_000_000)
    workspace = tmp_path
    output_root = workspace / "S10/build-clean"
    snapshot_path = workspace / "S10/prebuild_output_root_snapshot.json"
    snapshot_path.parent.mkdir(parents=True)
    snapshot = create_empty_root_snapshot(output_root, snapshot_path)
    plan, estimate, estimate_path, plan_sha = _resource_plan(
        workspace, snapshot["snapshot_sha256"], approved=True)
    estimate_sha = hashlib.sha256(estimate_path.read_bytes()).hexdigest()
    measurement_path = workspace / plan["resource_gate"]["build"][
        "measurement_receipt_relative_path"]
    measurement = create_resource_preflight_receipt(
        plan, plan_sha256=plan_sha, workspace=workspace,
        canonical_host=workspace / "canonical", shadow_host=workspace / "shadow",
        overlay_paths={}, output_root=output_root, snapshot_path=snapshot_path,
        phase="measure", receipt_path=measurement_path,
        estimate_path=estimate_path)
    release = _release(plan, plan_sha, snapshot["snapshot_sha256"])
    approval = {
        "schema": "s10-resource-gate-approval-v1",
        "owner": "coordinator",
        "status": "APPROVED_FOR_S10_BUILD",
        "plan_sha256": plan_sha,
        "output_size_estimate_sha256": estimate_sha,
        "empty_output_root_snapshot_sha256": snapshot["snapshot_sha256"],
        "resource_measurement_receipt_sha256": hashlib.sha256(
            measurement_path.read_bytes()).hexdigest(),
        "measured_free_bytes": measurement["observed_free_bytes"],
        "measured_at_unix_ns": measurement["observed_at_unix_ns"],
        "required_free_bytes": measurement["required_free_bytes"],
        "s15_release_receipt_sha256": "4" * 64,
        "minimum_free_bytes": 1000,
        "safety_factor": 2,
        "full_matrix_build_or_link_allowed": True,
    }
    approval_sha = "5" * 64
    release_sha = "4" * 64
    receipt = create_resource_preflight_receipt(
        plan, plan_sha256=plan_sha, workspace=workspace,
        canonical_host=workspace / "canonical", shadow_host=workspace / "shadow",
        overlay_paths={}, output_root=output_root, snapshot_path=snapshot_path,
        phase="build", receipt_path=workspace / "S10/build_resource_preflight.json",
        estimate_path=estimate_path, approval=approval,
        approval_sha256=approval_sha, trusted_approval_sha256=approval_sha,
        s15_release=release, s15_release_sha256=release_sha,
        trusted_s15_release_sha256=release_sha)
    assert receipt["status"] == "READY_FOR_REVIEWED_BUILD"
    validate_build_resource_preflight(
        plan, receipt, plan_sha256=plan_sha,
        snapshot_sha256=snapshot["snapshot_sha256"], output_root=output_root,
        trusted_approval_sha256=approval_sha)
    with pytest.raises(PrelinkError, match="coordinator S15 release receipt SHA-256 mismatch"):
        create_resource_preflight_receipt(
            plan, plan_sha256=plan_sha, workspace=workspace,
            canonical_host=workspace / "canonical", shadow_host=workspace / "shadow",
            overlay_paths={}, output_root=output_root, snapshot_path=snapshot_path,
            phase="build", receipt_path=workspace / "S10/build_resource_preflight.json",
            estimate_path=estimate_path, approval=approval,
            approval_sha256=approval_sha, trusted_approval_sha256=approval_sha,
            s15_release=release, s15_release_sha256=release_sha,
            trusted_s15_release_sha256="6" * 64)
    wrong_measurement = {**approval,
                         "resource_measurement_receipt_sha256": "0" * 64}
    with pytest.raises(PrelinkError, match="receipt mismatch for resource_measurement_receipt_sha256"):
        create_resource_preflight_receipt(
            plan, plan_sha256=plan_sha, workspace=workspace,
            canonical_host=workspace / "canonical", shadow_host=workspace / "shadow",
            overlay_paths={}, output_root=output_root, snapshot_path=snapshot_path,
            phase="build", receipt_path=workspace / "S10/build_resource_preflight.json",
            estimate_path=estimate_path, approval=wrong_measurement,
            approval_sha256=approval_sha, trusted_approval_sha256=approval_sha,
            s15_release=release, s15_release_sha256=release_sha,
            trusted_s15_release_sha256=release_sha)
    stale = {**receipt, "resource_measurement_observed_at_unix_ns":
             receipt["resource_gate_checked_at_unix_ns"] - 3601 * 1_000_000_000}
    with pytest.raises(PrelinkError, match="fresh capacity measurement"):
        validate_build_resource_preflight(
            plan, stale, plan_sha256=plan_sha,
            snapshot_sha256=snapshot["snapshot_sha256"], output_root=output_root,
            trusted_approval_sha256=approval_sha)
    monkeypatch.setattr(guard_module.shutil, "disk_usage", lambda _path: SimpleNamespace(
        total=100_000, used=99_900, free=100))
    with pytest.raises(PrelinkError, match="below the reviewed build-size requirement"):
        create_resource_preflight_receipt(
            plan, plan_sha256=plan_sha, workspace=workspace,
            canonical_host=workspace / "canonical", shadow_host=workspace / "shadow",
            overlay_paths={}, output_root=output_root, snapshot_path=snapshot_path,
            phase="build", receipt_path=workspace / "S10/build_resource_preflight.json",
            estimate_path=estimate_path, approval=approval,
            approval_sha256=approval_sha, trusted_approval_sha256=approval_sha,
            s15_release=release, s15_release_sha256=release_sha,
            trusted_s15_release_sha256=release_sha)


def test_netcdf_toolchain_roots_paths_hashes_and_versions_are_pinned(tmp_path: Path,
                                                                     monkeypatch):
    root = tmp_path / "homebrew-netcdf"
    bin_dir = root / "bin"
    bin_dir.mkdir(parents=True)
    tools = {}
    for name, version, output in (
        ("nc-config", "netCDF 4.9.3", "nc-config output"),
        ("nf-config", "4.6.2", "nf-config output"),
    ):
        tool = bin_dir / name
        tool.write_text(f"#!/bin/sh\nprintf '%s\\n' '{version}'\n")
        tool.chmod(0o755)
        tools[name] = {
            "path": str(tool),
            "sha256": hashlib.sha256(tool.read_bytes()).hexdigest(),
            "version_argv": ["--version"],
            "version_stdout": version,
        }
    monkeypatch.setenv("NETCDF", str(root))
    monkeypatch.setenv("NETCDF_C", str(root))
    environment = tool_environment_snapshot()
    environment_sha = sha256_bytes(json.dumps(
        environment, sort_keys=True, separators=(",", ":")).encode())
    plan = {"toolchain": {
        "tools": tools,
        "configuration_environment": {"NETCDF": str(root), "NETCDF_C": str(root)},
        "environment_sha256": environment_sha,
        "toolchain_sha256": sha256_bytes(json.dumps(
            {"tools": tools, "environment_sha256": environment_sha},
            sort_keys=True, separators=(",", ":")).encode()),
    }}
    resolved = validate_toolchain(plan, tmp_path)
    assert resolved["nc-config"]["version_stdout"] == "netCDF 4.9.3"
    assert resolved["nf-config"]["version_stdout"] == "4.6.2"

    monkeypatch.setenv("NETCDF", str(tmp_path / "macports"))
    with pytest.raises(PrelinkError, match="resolution environment differs"):
        validate_toolchain(plan, tmp_path)
    monkeypatch.setenv("NETCDF", str(root))

    wrong_version = json.loads(json.dumps(plan))
    wrong_version["toolchain"]["tools"]["nf-config"]["version_stdout"] = "4.5.0"
    wrong_version["toolchain"]["toolchain_sha256"] = sha256_bytes(json.dumps(
        {"tools": wrong_version["toolchain"]["tools"],
         "environment_sha256": environment_sha},
        sort_keys=True, separators=(",", ":")).encode())
    with pytest.raises(PrelinkError, match="version output changed for nf-config"):
        validate_toolchain(wrong_version, tmp_path)

    altered = json.loads(json.dumps(plan))
    macports_tool = tmp_path / "macports" / "bin" / "nf-config"
    macports_tool.parent.mkdir(parents=True)
    macports_tool.write_bytes((bin_dir / "nf-config").read_bytes())
    macports_tool.chmod(0o755)
    altered["toolchain"]["tools"]["nf-config"]["path"] = str(macports_tool)
    altered_tools = altered["toolchain"]["tools"]
    altered["toolchain"]["toolchain_sha256"] = sha256_bytes(json.dumps(
        {"tools": altered_tools, "environment_sha256": environment_sha},
        sort_keys=True, separators=(",", ":")).encode())
    with pytest.raises(PrelinkError, match="not resolved from pinned NETCDF"):
        validate_toolchain(altered, tmp_path)


def test_netcdf_config_receipt_replays_pinned_homebrew_invocations(tmp_path: Path):
    root = tmp_path / "netcdf"
    bin_dir = root / "bin"
    bin_dir.mkdir(parents=True)
    tool_rows = {}
    records = {}
    for name, version, outputs in (
        ("nc-config", "netCDF 4.9.3", {
            "--version": "netCDF 4.9.3", "--libs": "-L/netcdf/lib -lnetcdf",
            "--has-nc4": "yes", "--has-pnetcdf": "no"}),
        ("nf-config", "4.6.2", {
            "--has-nc4": "yes", "--flibs": "-L/netcdf/lib -lnetcdff -lnetcdf"}),
    ):
        tool = bin_dir / name
        cases = " ".join(
            f"{arg}) printf '%s\\n' '{value}' ;;" for arg, value in outputs.items())
        tool.write_text(f"#!/bin/sh\ncase \"$1\" in {cases} *) exit 2 ;; esac\n")
        tool.chmod(0o755)
        digest = hashlib.sha256(tool.read_bytes()).hexdigest()
        tool_rows[name] = {"path": str(tool), "sha256": digest,
                           "version": version, "argv_outputs": outputs}
        commands = []
        for argument, output in outputs.items():
            commands.append({"argv": [argument], "returncode": 0,
                             "stdout": output, "stderr": ""})
        records[name] = {"path": str(tool), "sha256": digest,
                         "version": version, "commands": commands}
    (tmp_path / "configure.wrf").write_text(
        f"NETCDFPATH      =    {root}\n")
    plan = {"prelink_requirements": {"netcdf_config_invocation_policy": {
        "environment": {"NETCDF": str(root), "NETCDF_C": str(root)},
        "invocations": tool_rows,
        "forbidden_mixed_prefixes": ["/macports/"],
    }}}
    _validate_netcdf_config_invocations(
        {"netcdf_tool_invocations": records}, plan, tmp_path)
    records["nf-config"]["commands"][0]["argv"] = ["--version"]
    with pytest.raises(PrelinkError, match="argv differs from its pin"):
        _validate_netcdf_config_invocations(
            {"netcdf_tool_invocations": records}, plan, tmp_path)
    records["nf-config"]["commands"][0]["argv"] = ["--has-nc4"]
    records["nc-config"]["commands"][1]["stdout"] = "-L/opt/local/lib -lnetcdf"
    with pytest.raises(PrelinkError, match="output differs from its pinned invocation"):
        _validate_netcdf_config_invocations(
            {"netcdf_tool_invocations": records}, plan, tmp_path)
    records["nc-config"]["commands"][1]["stdout"] = "-L/netcdf/lib -lnetcdf"
    records["nf-config"]["path"] = "/opt/local/bin/nf-config"
    with pytest.raises(PrelinkError, match="identity mismatch"):
        _validate_netcdf_config_invocations(
            {"netcdf_tool_invocations": records}, plan, tmp_path)


def test_response_file_escapes_are_rejected_in_direct_wl_and_xlinker_args(tmp_path: Path):
    tool = tmp_path / "bin" / "gfortran"
    tool.parent.mkdir()
    tool.write_bytes(b"pinned wrapper")
    tool.chmod(0o755)
    digest = hashlib.sha256(tool.read_bytes()).hexdigest()
    plan = {"toolchain": {"tools": {"gfortran": {"path": str(tool), "sha256": digest}}}}
    output = tmp_path / "out"
    output.mkdir()
    stdout = output / "stdout"
    stdout.write_text("")
    stderr = output / "stderr"
    stderr.write_text("")
    response = tmp_path / "args.rsp"
    response.write_text("-o /outside/wrf.exe -map /outside/mapfile\n")
    rpath_response_dir = output / "@rpath"
    rpath_response_dir.mkdir()
    (rpath_response_dir / "args.rsp").write_text("-o /outside/wrf.exe -map /outside/mapfile\n")
    refs = [
        ["@" + str(response)],
        ["@rpath/args.rsp"],
        ["-Wl,@" + str(response)],
        ["-Wl,@loader_path/args.rsp"],
        ["-Xlinker", "@" + str(response)],
        ["-Xlinker", "@loader_path/args.rsp"],
    ]
    for ref in refs:
        b_argv = [str(tool), "-ffp-contract=off", *ref]
        c_argv = list(b_argv)
        assert b_argv == c_argv  # B/C argv equality cannot make the hidden response safe.
        record = {
            "tool_name": "gfortran", "tool_path": str(tool), "tool_sha256": digest,
            "argv": b_argv, "flags": _argv_option_tokens(b_argv),
            "cwd": str(output), "shell": False,
            "stdout_path": str(stdout), "stderr_path": str(stderr),
        }
        with pytest.raises(PrelinkError, match="response-file references are forbidden"):
            _validate_tool_command(record, expected_name="gfortran", plan=plan,
                                   shadow_host=tmp_path, output_root=output,
                                   label="link")
    valid_rpath_argv = [str(tool), "-Wl,-rpath,@loader_path/../lib"]
    assert not _response_file_refs(valid_rpath_argv)
    valid_rpath_record = {
        "tool_name": "gfortran", "tool_path": str(tool), "tool_sha256": digest,
        "argv": valid_rpath_argv, "flags": _argv_option_tokens(valid_rpath_argv),
        "cwd": str(output), "shell": False,
        "stdout_path": str(stdout), "stderr_path": str(stderr),
    }
    _validate_tool_command(valid_rpath_record, expected_name="gfortran", plan=plan,
                           shadow_host=tmp_path, output_root=output,
                           label="link")


def test_preprocessor_forwarding_cannot_hide_guard_definitions(tmp_path: Path):
    tool = tmp_path / "bin" / "cpp"
    tool.parent.mkdir()
    tool.write_bytes(b"pinned cpp")
    tool.chmod(0o755)
    digest = hashlib.sha256(tool.read_bytes()).hexdigest()
    plan = {"toolchain": {"tools": {"cpp": {"path": str(tool), "sha256": digest}}}}
    output = tmp_path / "out"
    output.mkdir()
    stdout = output / "cpp.stdout"
    stdout.write_text("")
    stderr = output / "cpp.stderr"
    stderr.write_text("")
    hidden_forms = (
        ["-Wp,-DKDM6_PROGB_ZERO_QG_DIV_GUARD=0"],
        ["-Wp", "-DKDM6_PROGB_ZERO_QG_DIV_GUARD=0"],
        ["-Xpreprocessor", "-DKDM6_PROGB_ZERO_QG_DIV_GUARD=0"],
        ["-Xpreprocessor=-DKDM6_PROGB_ZERO_QG_DIV_GUARD=0"],
    )
    for hidden in hidden_forms:
        b_argv = [str(tool), "-P", *hidden]
        c_argv = list(b_argv)
        assert b_argv == c_argv
        record = {
            "tool_name": "cpp", "tool_path": str(tool), "tool_sha256": digest,
            "argv": b_argv, "flags": _argv_option_tokens(b_argv),
            "cwd": str(output), "shell": False,
            "stdout_path": str(stdout), "stderr_path": str(stderr),
        }
        with pytest.raises(PrelinkError, match="forwarded compiler/linker options are forbidden"):
            _validate_tool_command(record, expected_name="cpp", plan=plan,
                                   shadow_host=tmp_path, output_root=output,
                                   label="WRF cpp")


def test_output_guard_rejects_duplicate_or_redirected_o(tmp_path: Path):
    output = tmp_path / "build"
    output.mkdir()
    target = output / "wrf.exe"
    canonical_exe = tmp_path / "canonical-host" / "wrf.exe"
    base = ["/opt/homebrew/bin/mpif90", "object.o", "-o", str(target)]
    _ensure_output_target(base, expected=target, output_root=output,
                          require_output=True, label="link")
    with pytest.raises(PrelinkError, match="duplicate or alternate"):
        _ensure_output_target([*base, "-o", str(canonical_exe)],
                              expected=target, output_root=output,
                              require_output=True, label="link")
    with pytest.raises(PrelinkError, match="target differs"):
        _ensure_output_target(["mpif90", "-o", str(canonical_exe)],
                              expected=target, output_root=output,
                              require_output=True, label="link")
    with pytest.raises(PrelinkError, match="alternate output"):
        _ensure_output_target(["mpif90", "-Wl,-o,/tmp/wrf.exe"], expected=target,
                              output_root=output, require_output=True, label="link")
    for map_argv in (
        ["mpif90", "-Wl,-Map=/tmp/outside.map", "-o", str(target)],
        ["mpif90", "-Wl,-Map,/tmp/outside.map", "-o", str(target)],
        ["mpif90", "-Xlinker", "-Map", "-Xlinker", "/tmp/outside.map",
         "-o", str(target)],
        ["mpif90", "-Xlinker", "-Map=/tmp/outside.map", "-o", str(target)],
        ["mpif90", "-map", "/tmp/outside.map", "-o", str(target)],
        ["mpif90", "-Wl,-map,/tmp/outside.map", "-o", str(target)],
        ["mpif90", "-Wl,-map=/tmp/outside.map", "-o", str(target)],
        ["mpif90", "-Xlinker", "-map", "-Xlinker", "/tmp/outside.map",
         "-o", str(target)],
    ):
        with pytest.raises(PrelinkError, match="linker map output"):
            _ensure_output_target(map_argv, expected=target, output_root=output,
                                  require_output=True, label="link")


def test_module_and_dependency_outputs_are_unique_and_arm_local(tmp_path: Path):
    build = tmp_path / "S10/build-clean"
    arm_b = build / "mp37/B"
    arm_c = build / "mp37/C"
    module_dir = arm_b / "mod"
    depfile = arm_b / "module.d"
    object_path = arm_b / "module.o"
    base = ["mpif90", "-o", str(object_path), "-J", str(module_dir)]
    _ensure_output_target(base, expected=object_path, output_root=build,
                          arm_root=arm_b, require_output=True,
                          expected_module_dir=module_dir, label="object")
    with pytest.raises(PrelinkError, match="duplicate -J"):
        _ensure_output_target(base + ["-J", str(module_dir)], expected=object_path,
                              output_root=build, arm_root=arm_b, require_output=True,
                              expected_module_dir=module_dir, label="object")
    with pytest.raises(PrelinkError, match="escaped its arm directory"):
        _ensure_output_target(["mpif90", "-o", str(object_path), "-J", str(arm_c / "mod")],
                              expected=object_path, output_root=build, arm_root=arm_b,
                              require_output=True, expected_module_dir=module_dir,
                              label="object")
    dep_argv = [*base, "-MF", str(depfile)]
    _ensure_output_target(dep_argv, expected=object_path, output_root=build,
                          arm_root=arm_b, require_output=True,
                          expected_module_dir=module_dir, expected_depfile=depfile,
                          label="object")
    with pytest.raises(PrelinkError, match="duplicate -MF"):
        _ensure_output_target(dep_argv + ["-MF", str(depfile)], expected=object_path,
                              output_root=build, arm_root=arm_b, require_output=True,
                              expected_module_dir=module_dir, expected_depfile=depfile,
                              label="object")
    with pytest.raises(PrelinkError, match="escaped its arm directory"):
        _ensure_output_target([*base, "-MF", str(arm_c / "module.d")],
                              expected=object_path, output_root=build, arm_root=arm_b,
                              require_output=True, expected_module_dir=module_dir,
                              expected_depfile=depfile, label="object")


def test_fresh_root_and_nonce_snapshot_are_pinned(tmp_path: Path):
    output = tmp_path / "S10" / "build-clean"
    require_fresh_output_root(output)
    snapshot_file = tmp_path / "private" / "empty_root.json"
    snapshot = create_empty_root_snapshot(output, snapshot_file)
    checked = validate_prebuild_snapshot(snapshot_file, snapshot["snapshot_sha256"],
                                         output, snapshot_file)
    assert checked["observed_file_count"] == 0
    assert len(checked["nonce"]) == 64
    (output / "stale.o").parent.mkdir(parents=True)
    (output / "stale.o").write_bytes(b"stale")
    with pytest.raises(PrelinkError, match="nonce"):
        altered = json.loads(snapshot_file.read_text())
        altered["nonce"] = "f" * 64
        snapshot_file.write_text(json.dumps(altered))
        validate_prebuild_snapshot(snapshot_file,
                                   hashlib.sha256(snapshot_file.read_bytes()).hexdigest(),
                                   output, snapshot_file)
    with pytest.raises(PrelinkError, match="plan-pinned external location"):
        validate_prebuild_snapshot(snapshot_file,
                                   hashlib.sha256(snapshot_file.read_bytes()).hexdigest(),
                                   output, tmp_path / "other.json")


def test_nonempty_output_root_cannot_receive_fresh_snapshot(tmp_path: Path):
    output = tmp_path / "S10" / "build-clean"
    output.mkdir(parents=True)
    (output / "stale.o").write_bytes(b"stale")
    with pytest.raises(PrelinkError, match="absent or empty"):
        create_empty_root_snapshot(output, tmp_path / "snapshot.json")


def test_snapshot_path_inside_output_root_is_rejected(tmp_path: Path):
    output = tmp_path / "S10" / "build-clean"
    with pytest.raises(PrelinkError, match="outside the output root"):
        create_empty_root_snapshot(output, output / "snapshot.json")


def test_clean_shadow_rejects_stale_exe_rsl_logs_modules_and_generated_f90(tmp_path: Path):
    workspace = tmp_path / "work"
    shadow = workspace / "S10" / "shadow_host"
    output = workspace / "S10" / "build-clean"
    (shadow / "main").mkdir(parents=True)
    validate_clean_shadow(shadow, output, workspace)
    stale_cases = [
        (shadow / "main" / "wrf.exe", b"old", "stale shadow main/wrf.exe"),
        (shadow / "rsl.error.0000", b"old", "rsl log"),
        (shadow / "phys" / "module.o", b"old", "object/module"),
        (shadow / "phys" / "module.mod", b"old", "object/module"),
    ]
    for path, content, error in stale_cases:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        with pytest.raises(PrelinkError, match=error):
            validate_clean_shadow(shadow, output, workspace)
        path.unlink()
    (shadow / "phys" / "stale.F").write_text("Fortran source")
    (shadow / "phys" / "stale.f90").write_text("generated output")
    with pytest.raises(PrelinkError, match="generated Fortran"):
        validate_clean_shadow(shadow, output, workspace)


def test_link_must_name_canonical_archive_once_and_match_its_hash(tmp_path: Path):
    archive = tmp_path / "canonical" / "main" / "libwrflib.a"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"pinned archive")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    argv = ["mpif90", "object.o", str(archive.resolve()), "-o", "fresh.exe"]
    validate_archive_link(argv, archive_path=archive, expected_sha256=digest,
                          recorded_path=str(archive.resolve()), recorded_sha256=digest)
    with pytest.raises(PrelinkError, match="exactly once"):
        validate_archive_link(argv + [str(archive.resolve())], archive_path=archive,
                              expected_sha256=digest, recorded_path=str(archive.resolve()),
                              recorded_sha256=digest)
    with pytest.raises(PrelinkError, match="path is not the pinned"):
        validate_archive_link(argv, archive_path=archive, expected_sha256=digest,
                              recorded_path=str(tmp_path / "shadow" / "libwrflib.a"),
                              recorded_sha256=digest)


def test_source_overlay_and_macro_off_identity_are_rehashed(tmp_path: Path):
    canonical = tmp_path / "module_mp_kdm6.F"
    canonical.write_text("B midpoint bytes\n")
    b_source = canonical.read_bytes()
    overlay = tmp_path / "module_mp_kdm6_C.F"
    overlay.write_text(
        "#ifdef KDM6_PROGB_ZERO_QG_DIV_GUARD\nC guard\n#else\n"
        "B midpoint bytes\n#endif\n"
    )
    pin = {
        "source_sha256": hashlib.sha256(b_source).hexdigest(),
        "c_overlay_sha256": hashlib.sha256(overlay.read_bytes()).hexdigest(),
        "macro_off_b_midpoint_sha256": hashlib.sha256(b_source).hexdigest(),
    }
    checked = validate_source_overlay(pin, scheme="mp37", canonical_source=canonical,
                                      overlay_path=overlay)
    assert checked["macro_off_b_midpoint_sha256"] == pin["source_sha256"]
    overlay.write_text(overlay.read_text() + "! mutation\n")
    with pytest.raises(PrelinkError, match="overlay hash changed"):
        validate_source_overlay(pin, scheme="mp37", canonical_source=canonical,
                                overlay_path=overlay)


def test_preprocessing_pipeline_pins_tools_args_and_hash_chain(tmp_path: Path):
    workspace = tmp_path / "work"
    shadow = workspace / "S10/shadow_host"
    output_root = workspace / "S10/build-clean"
    arm_root = output_root / "mp37/B"
    (shadow / "tools").mkdir(parents=True)
    arm_root.mkdir(parents=True)
    overlay = workspace / "module_mp_kdm6_C.F"
    overlay.write_text("source\n")
    specs = {}
    for name, relative in (("sed", "bin/sed"), ("cpp", "bin/cpp"),
                           ("standard", "tools/standard.exe")):
        path = shadow / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"{name} pinned tool".encode())
        path.chmod(0o755)
        specs[name] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    plan = {"toolchain": {"tools": specs}}
    stages = ["comment_cleanup", "wrf_cpp", "standard", "final_cpp"]
    input_sha = hashlib.sha256(overlay.read_bytes()).hexdigest()
    commands = []
    outputs = [arm_root / name for name in ("clean.G", "first.bb", "standard.bb", "module.f90")]
    args = [
        [specs["sed"]["path"], "-e", "s/^!.*'//", str(overlay.resolve())],
        [specs["cpp"]["path"], "-P", "-DKDM6_PROGB_VALIDITY_CAPTURE",
         "-DKDM6_PROGB_POLICY_MIDPOINT", "-I", str(shadow / "inc"), str(outputs[0])],
        [specs["standard"]["path"], str(outputs[1])],
        [specs["cpp"]["path"], "-P", "-traditional-cpp", str(outputs[2])],
    ]
    names = ["sed", "cpp", "standard", "cpp"]
    for stage, name, argv, output in zip(stages, names, args, outputs):
        output.write_text(f"{stage} output\n")
        output_sha = hashlib.sha256(output.read_bytes()).hexdigest()
        stdout = arm_root / f"{stage}.stdout"
        stderr = arm_root / f"{stage}.stderr"
        stdout.write_text("")
        stderr.write_text("")
        commands.append({
            "stage": stage,
            "tool_name": name,
            "tool_path": specs[name]["path"],
            "tool_sha256": specs[name]["sha256"],
            "argv": argv,
            "flags": _argv_option_tokens(argv),
            "cwd": str(arm_root),
            "shell": False,
            "stdout_path": str(stdout), "stderr_path": str(stderr),
            "returncode": 0,
            "input_sha256": input_sha,
            "output_path": str(output),
            "output_path_sha256": output_sha,
        })
        input_sha = output_sha
    pp = {"commands": commands, "output_path": str(outputs[-1]),
          "output_path_sha256": input_sha}
    macro_argv, final = _validate_preprocess_pipeline(
        pp, key="mp37_B", overlay=overlay, output_root=output_root,
        expected_output=outputs[-1], plan=plan, shadow_host=shadow, workspace=workspace)
    assert macro_argv == args[1]
    assert final == outputs[-1].resolve()
    commands[2]["argv"] = [str(shadow / "tools/alternate-standard.exe"), str(outputs[1])]
    commands[2]["tool_path"] = commands[2]["argv"][0]
    with pytest.raises(PrelinkError, match="alternate or unpinned"):
        _validate_preprocess_pipeline(
            pp, key="mp37_B", overlay=overlay, output_root=output_root,
            expected_output=outputs[-1], plan=plan, shadow_host=shadow, workspace=workspace)


def test_configure_command_stdin_and_generated_config_are_plan_pinned(tmp_path: Path):
    shadow = tmp_path / "S10" / "shadow_host" / "KIM-meso_v1.0"
    output = tmp_path / "S10" / "build"
    capture_root = tmp_path / "S10" / "configuration_capture"
    shadow.mkdir(parents=True)
    output.mkdir()
    capture_root.mkdir()
    configure = shadow / "configure"
    apply_script = shadow / "apply_kdm6ad_config.sh"
    configure.write_text("configure script\n")
    apply_script.write_text("apply script\n")
    configure_wrf = shadow / "configure.wrf"
    configure_wrf.write_text("generated config\n")
    stdout = output / "configure.stdout"
    stdout.write_text("")
    stderr = output / "configure.stderr"
    stderr.write_text("")
    apply_stdout = output / "apply.stdout"
    apply_stdout.write_text("")
    apply_stderr = output / "apply.stderr"
    apply_stderr.write_text("")
    configure_stdin = capture_root / "configure.stdin"
    configure_stdin.write_bytes(b"x\n")
    apply_stdin = capture_root / "apply_kdm6ad_config.stdin"
    apply_stdin.write_bytes(b"")
    bash = Path("/bin/bash")
    bash_sha = hashlib.sha256(bash.read_bytes()).hexdigest()
    configure_sha = hashlib.sha256(configure.read_bytes()).hexdigest()
    apply_sha = hashlib.sha256(apply_script.read_bytes()).hexdigest()
    generated_sha = hashlib.sha256(configure_wrf.read_bytes()).hexdigest()
    stdin_sha = hashlib.sha256(b"x\n").hexdigest()
    empty_sha = hashlib.sha256(b"").hexdigest()
    plan = {
        "toolchain": {"tools": {"bash": {"path": str(bash), "sha256": bash_sha}}},
        "prelink_requirements": {
            "configuration_inputs_sha256": {
                "configure": configure_sha,
                "apply_kdm6ad_config.sh": apply_sha,
            },
            "configuration_generation_command": [str(bash), "./configure"],
            "configuration_apply_command": [str(bash), "./apply_kdm6ad_config.sh"],
            "configure_selection_stdin_sha256": stdin_sha,
            "configuration_apply_stdin_sha256": empty_sha,
            "configuration_stdin_capture_paths": {
                "configure": "configuration_capture/configure.stdin",
                "apply_kdm6ad_config": "configuration_capture/apply_kdm6ad_config.stdin",
            },
            "generated_configure_wrf_sha256": generated_sha,
        },
    }
    def command(stage, script_sha, argv, stdin_hash, out, err):
        return {
            "stage": stage, "tool_name": "bash", "tool_path": str(bash),
            "tool_sha256": bash_sha, "script_sha256": script_sha,
            "argv": argv, "flags": _argv_option_tokens(argv),
            "cwd": str(shadow), "shell": False, "returncode": 0,
            "stdin_sha256": stdin_hash,
            "stdin_path": str(configure_stdin if stage == "configure" else apply_stdin),
            "stdout_path": str(out), "stderr_path": str(err),
        }
    commands = [
        command("configure", configure_sha,
                [str(bash), "./configure"], stdin_sha, stdout, stderr),
        command("apply_kdm6ad_config", apply_sha,
                [str(bash), "./apply_kdm6ad_config.sh"], empty_sha, apply_stdout, apply_stderr),
    ]
    execution = {"configuration_commands": commands}
    _validate_configure_pipeline(execution, shadow, output, plan, generated_sha)
    mutation = {**commands[0], "argv": [str(bash), "./configure", "--alternate-menu"]}
    mutation["flags"] = _argv_option_tokens(mutation["argv"])
    execution["configuration_commands"] = [mutation, commands[1]]
    with pytest.raises(PrelinkError, match="argv differs from the plan pin"):
        _validate_configure_pipeline(execution, shadow, output, plan, generated_sha)
    altered_stdin = {**commands[0], "stdin_sha256": "b" * 64}
    execution["configuration_commands"] = [altered_stdin, commands[1]]
    with pytest.raises(PrelinkError, match="stdin/options are not plan-pinned"):
        _validate_configure_pipeline(execution, shadow, output, plan, generated_sha)
    altered_stdin_path = {**commands[0], "stdin_path": str(tmp_path / "outside.stdin")}
    execution["configuration_commands"] = [altered_stdin_path, commands[1]]
    with pytest.raises(PrelinkError, match="stdin capture differs"):
        _validate_configure_pipeline(execution, shadow, output, plan, generated_sha)
    execution["configuration_commands"] = commands
    configure_wrf.write_text("mutated config\n")
    with pytest.raises(PrelinkError, match="configure.wrf differs from the reviewed plan pin"):
        _validate_configure_pipeline(execution, shadow, output, plan, generated_sha)


def test_configure_pipeline_requires_resolved_netcdf_tool_receipt(tmp_path: Path):
    s10 = tmp_path / "S10"
    shadow = s10 / "shadow_host" / "KIM-meso_v1.0"
    output = s10 / "build"
    captures = s10 / "configuration_capture"
    shadow.mkdir(parents=True)
    output.mkdir()
    captures.mkdir()
    configure = shadow / "configure"
    apply_script = shadow / "apply_kdm6ad_config.sh"
    configure.write_text("configure source\n")
    apply_script.write_text("apply source\n")
    netcdf_root = tmp_path / "homebrew-netcdf"
    bindir = netcdf_root / "bin"
    bindir.mkdir(parents=True)
    netcdf_tools = {}
    netcdf_receipt = {}
    for name, version, outputs in (
        ("nc-config", "netCDF 4.9.3", {
            "--version": "netCDF 4.9.3", "--libs": "-L/netcdf/lib -lnetcdf",
            "--has-nc4": "yes", "--has-pnetcdf": "no"}),
        ("nf-config", "4.6.2", {
            "--has-nc4": "yes", "--flibs": "-L/netcdf/lib -lnetcdff -lnetcdf"}),
    ):
        tool = bindir / name
        cases = " ".join(
            f"{argument}) printf '%s\\n' '{value}' ;;"
            for argument, value in outputs.items())
        tool.write_text(f"#!/bin/sh\ncase \"$1\" in {cases} *) exit 2 ;; esac\n")
        tool.chmod(0o755)
        digest = hashlib.sha256(tool.read_bytes()).hexdigest()
        netcdf_tools[name] = {
            "path": str(tool), "sha256": digest,
            "version": version, "argv_outputs": outputs,
        }
        netcdf_receipt[name] = {
            "path": str(tool), "sha256": digest, "version": version,
            "commands": [
                {"argv": [argument], "returncode": 0,
                 "stdout": value, "stderr": ""}
                for argument, value in outputs.items()
            ],
        }
    configure_wrf = shadow / "configure.wrf"
    configure_wrf.write_text(f"NETCDFPATH      =    {netcdf_root}\n")
    stdout = output / "configure.stdout"
    stdout.write_text(
        f"Will use NETCDF in dir: {netcdf_root}\n"
        "Enabled NetCDF-4/HDF-5: yes\nNetCDF built with PnetCDF: no\n")
    stderr = output / "configure.stderr"
    stderr.write_text("")
    apply_stdout = output / "apply.stdout"
    apply_stdout.write_text("")
    apply_stderr = output / "apply.stderr"
    apply_stderr.write_text("")
    configure_stdin = captures / "configure.stdin"
    configure_stdin.write_bytes(b"35\n1\n")
    apply_stdin = captures / "apply_kdm6ad_config.stdin"
    apply_stdin.write_bytes(b"")
    bash = Path("/bin/bash")
    bash_sha = hashlib.sha256(bash.read_bytes()).hexdigest()
    configure_sha = hashlib.sha256(configure.read_bytes()).hexdigest()
    apply_sha = hashlib.sha256(apply_script.read_bytes()).hexdigest()
    config_sha = hashlib.sha256(configure_wrf.read_bytes()).hexdigest()
    stdin_sha = hashlib.sha256(configure_stdin.read_bytes()).hexdigest()
    empty_sha = hashlib.sha256(b"").hexdigest()

    def command(stage, script_sha, stdin_path, stdin_hash, out, err):
        argv = [str(bash), "./configure" if stage == "configure"
                else "./apply_kdm6ad_config.sh"]
        row = {
            "stage": stage, "tool_name": "bash", "tool_path": str(bash),
            "tool_sha256": bash_sha, "script_sha256": script_sha,
            "argv": argv, "flags": _argv_option_tokens(argv),
            "cwd": str(shadow), "shell": False, "returncode": 0,
            "stdin_sha256": stdin_hash, "stdin_path": str(stdin_path),
            "stdout_path": str(out), "stderr_path": str(err),
        }
        if stage == "configure":
            row["netcdf_tool_invocations"] = netcdf_receipt
        return row

    commands = [
        command("configure", configure_sha, configure_stdin, stdin_sha, stdout, stderr),
        command("apply_kdm6ad_config", apply_sha, apply_stdin, empty_sha,
                apply_stdout, apply_stderr),
    ]
    policy = {
        "environment": {"NETCDF": str(netcdf_root), "NETCDF_C": str(netcdf_root)},
        "invocations": netcdf_tools,
        "forbidden_mixed_prefixes": ["/macports/"],
        "configure_log_assertions": [
            "Enabled NetCDF-4/HDF-5: yes",
            "NetCDF built with PnetCDF: no",
        ],
    }
    plan = {
        "toolchain": {"tools": {"bash": {"path": str(bash), "sha256": bash_sha}}},
        "prelink_requirements": {
            "configuration_inputs_sha256": {
                "configure": configure_sha,
                "apply_kdm6ad_config.sh": apply_sha,
            },
            "configuration_generation_command": [str(bash), "./configure"],
            "configuration_apply_command": [str(bash), "./apply_kdm6ad_config.sh"],
            "configure_selection_stdin_sha256": stdin_sha,
            "configuration_apply_stdin_sha256": empty_sha,
            "configuration_stdin_capture_paths": {
                "configure": "configuration_capture/configure.stdin",
                "apply_kdm6ad_config": "configuration_capture/apply_kdm6ad_config.stdin",
            },
            "generated_configure_wrf_sha256": config_sha,
            "netcdf_config_invocation_policy": policy,
        },
    }
    execution = {"configuration_commands": commands}
    _validate_configure_pipeline(execution, shadow, output, plan, config_sha)
    commands[0]["netcdf_tool_invocations"]["nf-config"]["commands"][1]["stdout"] = "-L/opt/local/lib"
    with pytest.raises(PrelinkError, match="output differs from its pinned invocation"):
        _validate_configure_pipeline(execution, shadow, output, plan, config_sha)


def test_prelink_output_inventory_rejects_unrecorded_files(tmp_path: Path):
    workspace = tmp_path / "work"
    output_root = workspace / "S10" / "build-clean"
    output_root.mkdir(parents=True)
    artifact = output_root / "module.o"
    artifact.write_bytes(b"object")
    row = {"path": str(artifact), "sha256": hashlib.sha256(b"object").hexdigest()}
    validate_output_inventory(output_root, [row], workspace)
    (output_root / "stale.o").write_bytes(b"stale")
    with pytest.raises(PrelinkError, match="inventory differs"):
        validate_output_inventory(output_root, [row], workspace)
