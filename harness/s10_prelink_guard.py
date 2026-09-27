"""Fail-closed prelink checks for the private S10 C-arm native experiment.

The guard runs after preprocessing/compilation and before the first link. It
does not build, link, or launch WRF. Private path bindings and executed command
records are supplied in a local receipt; the public plan contains only pins.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import stat
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_progb_czero_guard import (  # noqa: E402
    ZERO_QG_MACRO,
    strip_czero_capture,
    strip_macro_else,
)
from run_ss_case import (  # noqa: E402
    hash_resolved_inputs,
    replace_line,
    resolve_active_namelist_inputs,
    set_or_insert,
)


class PrelinkError(ValueError):
    """A prelink requirement failed; linking must not proceed."""


CONFIGURE_FAILURE_MARKERS = ("One of compilers testing failed!",)


_TOOLCHAIN_ENV_KEYS = (
    "PATH", "OMPI_FC", "OMPI_FCFLAGS", "OMPI_F90", "OMPI_F90FLAGS",
    "GCC_EXEC_PREFIX", "COMPILER_PATH", "LIBRARY_PATH", "CPATH",
    "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "LD_LIBRARY_PATH",
    "DYLD_LIBRARY_PATH", "FC", "F90", "FFLAGS", "FCFLAGS",
    "LDFLAGS", "CPPFLAGS", "SDKROOT", "MACOSX_DEPLOYMENT_TARGET",
    "DEVELOPER_DIR", "NETCDF", "NETCDF_C", "NETCDFPAR", "PNETCDF",
    "HDF5", "PHDF5", "ADIOS2", "NETCDF_classic", "HDF5_PATH",
    "ZLIB_PATH", "CURL_PATH", "JASPERLIB", "JASPERINC", "GPFS_PATH",
    "COMMLIB", "OMP", "WRF_OS", "WRF_MACH", "WRF_NMM_CORE",
    "WRFPLUS", "WRF_CHEM", "WRF_KPP", "WRF_DFI_RADAR", "WRF_CMAQ",
    "TERRAIN_AND_LANDUSE", "HOME", "TMPDIR", "TMP", "LANG", "LC_ALL",
    "LC_CTYPE", "TERM", "BASH_ENV", "ENV", "PYTHONPATH", "PYTHONHOME",
    "PYTHONWARNINGS", "PERL5LIB", "PERLLIB", "PERL5OPT", "CFLAGS", "CXX",
    "CXXFLAGS", "DYLD_FALLBACK_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES",
    "LD_PRELOAD", "MAKEFLAGS", "MFLAGS", "NETCDF4", "USENETCDFPAR",
    "GREP_OPTIONS", "WRF_EM_CORE", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
    "OMP_THREAD_LIMIT", "PKG_CONFIG_PATH", "PKG_CONFIG_LIBDIR", "CC",
    "CPP", "F77", "PERL", "PYTHON", "AR", "ARFLAGS", "RANLIB", "M4",
    "MAKE", "TFL", "CFL", "WRF_CORE", "MPI_HOME", "MPICH", "OMPI_HOME",
)


def tool_environment_snapshot(environment: Mapping[str, str] | None = None) -> dict[str, str | None]:
    source = os.environ if environment is None else environment
    return {name: source.get(name) for name in _TOOLCHAIN_ENV_KEYS}


def planned_tool_environment(plan: dict[str, Any]) -> dict[str, str]:
    """Return only allowlisted environment variables, with plan-pinned overrides."""
    environment = {name: value for name, value in tool_environment_snapshot().items()
                   if value is not None}
    configured = plan.get("toolchain", {}).get("configuration_environment", {})
    if not isinstance(configured, dict):
        raise PrelinkError("pinned configuration environment is malformed")
    for name, value in configured.items():
        if value is None:
            environment.pop(name, None)
        elif isinstance(value, str):
            environment[name] = value
        else:
            raise PrelinkError(f"configuration environment value is invalid: {name}")
    actual = tool_environment_snapshot(environment)
    digest = sha256_bytes(json.dumps(
        actual, sort_keys=True, separators=(",", ":")).encode())
    if digest != plan.get("toolchain", {}).get("environment_sha256"):
        raise PrelinkError("sanitized guarded environment differs from its plan pin")
    return environment


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_configure_success_stdout(stdout: str) -> None:
    """Reject configure's known compiler self-test failure, even with rc=0."""
    for marker in CONFIGURE_FAILURE_MARKERS:
        if marker in stdout:
            raise PrelinkError(f"WRF configure reported compiler failure: {marker}")


def validate_configure_failure_markers(plan: dict[str, Any]) -> list[str]:
    markers = plan.get("prelink_requirements", {}).get(
        "configure_failure_log_markers")
    if markers != list(CONFIGURE_FAILURE_MARKERS):
        raise PrelinkError("configure failure markers differ from the code-fixed WRF guard")
    return list(CONFIGURE_FAILURE_MARKERS)


def validate_sdkroot_resolution(plan: dict[str, Any], *,
                                environment: Mapping[str, str]) -> dict[str, str]:
    """Bind SDKROOT to the pinned xcrun output, SDK version, and settings file."""
    toolchain = plan.get("toolchain", {})
    configured = toolchain.get("configuration_environment", {})
    pin = toolchain.get("sdkroot_resolution")
    if not isinstance(configured, dict) or not isinstance(pin, dict):
        raise PrelinkError("Apple SDKROOT resolution pin is missing")
    expected_sdkroot = pin.get("sdkroot")
    if (not isinstance(expected_sdkroot, str) or not expected_sdkroot
            or configured.get("SDKROOT") != expected_sdkroot
            or environment.get("SDKROOT") != expected_sdkroot):
        raise PrelinkError("SDKROOT is unset or differs from the pinned configuration value")
    tools = toolchain.get("tools", {})
    xcrun = tools.get("xcrun")
    if not isinstance(xcrun, dict):
        raise PrelinkError("pinned xcrun tool is missing for SDKROOT resolution")
    xcrun_path = xcrun.get("path")
    path_argv = pin.get("path_argv")
    version_argv = pin.get("version_argv")
    if (not isinstance(xcrun_path, str) or not Path(xcrun_path).is_absolute()
            or pin.get("xcrun_path") != xcrun_path
            or path_argv != ["--show-sdk-path"]
            or version_argv != ["--sdk", "macosx", "--show-sdk-version"]):
        raise PrelinkError("SDKROOT xcrun argv/path differs from its pin")
    result = subprocess.run([xcrun_path, *path_argv], check=False,
                            capture_output=True, text=True, shell=False,
                            env=dict(environment))
    if result.returncode != 0 or result.stdout.strip() != expected_sdkroot:
        raise PrelinkError("xcrun --show-sdk-path differs from pinned SDKROOT")
    version = subprocess.run([xcrun_path, *version_argv], check=False,
                             capture_output=True, text=True, shell=False,
                             env=dict(environment))
    expected_version = pin.get("version")
    if version.returncode != 0 or version.stdout.strip() != expected_version:
        raise PrelinkError("xcrun SDK version differs from the pinned macOS SDK")
    settings_rel = pin.get("settings_relative_path")
    settings_sha = pin.get("settings_sha256")
    if settings_rel != "SDKSettings.json" or not isinstance(settings_sha, str):
        raise PrelinkError("SDKSettings path/hash pin is malformed")
    settings_path = Path(expected_sdkroot) / settings_rel
    if sha256_file(settings_path) != settings_sha:
        raise PrelinkError("pinned macOS SDKSettings.json hash changed")
    return {
        "sdkroot": expected_sdkroot,
        "sdk_version": expected_version,
        "sdk_settings_sha256": settings_sha,
    }


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _lexical_absolute(path: Path) -> Path:
    """Normalize ``.``/``..`` without following a symlink."""
    return Path(os.path.abspath(os.fspath(path)))


def _reject_symlink_components(path: Path) -> None:
    """Reject symlinks from the filesystem root through an existing path."""
    absolute = _lexical_absolute(path)
    for component in reversed((absolute, *absolute.parents)):
        try:
            component.lstat()
        except FileNotFoundError:
            continue
        if component.is_symlink() or not component.exists():
            # A dangling symlink also has lstat metadata while exists() is false.
            raise PrelinkError(f"symlink or dangling path component is forbidden: {component.name}")


def _require_regular_file(path: Path, label: str) -> None:
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise PrelinkError(f"{label} is missing or unreadable") from exc
    if not stat.S_ISREG(mode):
        raise PrelinkError(f"{label} must be a regular file")


def _require_regular_file_if_present(path: Path, label: str) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return
    except OSError as exc:
        raise PrelinkError(f"{label} target is unreadable") from exc
    if not stat.S_ISREG(mode):
        raise PrelinkError(f"{label} target must be a regular file when present")


def _require_exact_workspace_path(workspace: Path, candidate: Path,
                                  relative: str, label: str, *,
                                  target_must_be_absent: bool = False) -> Path:
    """Bind a path lexically under workspace and reject symlink traversal."""
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise PrelinkError(f"{label} relative path is unsafe")
    workspace_abs = _lexical_absolute(workspace)
    expected = workspace_abs / rel
    candidate_abs = _lexical_absolute(candidate)
    if candidate_abs != expected:
        raise PrelinkError(f"{label} path differs from the exact plan-pinned location")
    _reject_symlink_components(expected)
    if target_must_be_absent and os.path.lexists(expected):
        raise PrelinkError(f"{label} target must be absent before measurement")
    return expected


def _write_new_workspace_receipt(workspace: Path, relative: str, payload: bytes) -> None:
    """Create a new receipt through no-follow directory descriptors."""
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise PrelinkError("measurement receipt relative path is unsafe")
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise PrelinkError("platform lacks no-follow directory/file creation flags")
    flags_dir = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    flags_file = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    workspace_abs = _lexical_absolute(workspace)
    if not workspace_abs.is_absolute():
        raise PrelinkError("measurement workspace must be absolute")
    directory_fd = os.open(workspace_abs.anchor, flags_dir)
    try:
        # Open every absolute workspace component relative to the preceding
        # directory descriptor. O_NOFOLLOW on a single absolute open protects
        # only its final component and leaves ancestor swaps vulnerable.
        for component in (*workspace_abs.parts[1:], *rel.parts[:-1]):
            next_fd = os.open(component, flags_dir, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        receipt_fd = os.open(rel.parts[-1], flags_file, 0o600, dir_fd=directory_fd)
        with os.fdopen(receipt_fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(directory_fd)


def sha256_file(path: Path) -> str:
    try:
        return sha256_bytes(path.read_bytes())
    except OSError as exc:
        raise PrelinkError(f"required file unavailable: {path}: {exc}") from exc


def parse_json_bytes(payload: bytes, source: Path | str) -> dict[str, Any]:
    """Parse one immutable byte buffer; callers may hash the same bytes."""
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PrelinkError(f"cannot read JSON receipt {source}: {exc}") from exc
    if not isinstance(value, dict):
        raise PrelinkError(f"JSON receipt must be an object: {source}")
    return value


def read_hashed_json(path: Path) -> tuple[dict[str, Any], str]:
    """Read a JSON file once and return its parsed value and matching digest."""
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise PrelinkError(f"cannot read JSON receipt {path}: {exc}") from exc
    return parse_json_bytes(payload, path), sha256_bytes(payload)


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise PrelinkError(f"cannot read JSON receipt {path}: {exc}") from exc
    return parse_json_bytes(payload, path)


def require_s15_release(plan: dict[str, Any], release: dict[str, Any],
                        plan_sha256: str, release_sha256: str,
                        trusted_release_sha256: str) -> None:
    trusted = plan.get("trusted_s15_release", {})
    if not isinstance(trusted_release_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", trusted_release_sha256):
        raise PrelinkError("coordinator must provide a trusted S15 release receipt SHA-256")
    if release_sha256 != trusted_release_sha256:
        raise PrelinkError("coordinator S15 release receipt SHA-256 mismatch")
    snapshot_sha = trusted.get("empty_output_root_snapshot_sha256")
    if not isinstance(snapshot_sha, str) or len(snapshot_sha) != 64:
        raise PrelinkError("trusted empty-output-root snapshot SHA-256 is not pinned")
    expected = {
        "schema": "s10-s15-native-lane-release-v1",
        "owner": "S15",
        "status": "RELEASED_FOR_S10_PRELINK",
        "green_red_review": "APPROVED",
        "native_slot_released": True,
        "plan_sha256": plan_sha256,
        "s15_merge_commit": trusted.get("s15_merge_commit"),
        "evidence_manifest_path": trusted.get("evidence_manifest_path"),
        "evidence_manifest_sha256": trusted.get("evidence_manifest_sha256"),
        "s15_step2_merge_commit": trusted.get("s15_step2_merge_commit"),
        "s15_step2_evidence_manifest_path": trusted.get(
            "s15_step2_evidence_manifest_path"),
        "s15_step2_evidence_manifest_sha256": trusted.get(
            "s15_step2_evidence_manifest_sha256"),
        "empty_output_root_snapshot_sha256": snapshot_sha,
    }
    for key, value in expected.items():
        if release.get(key) != value:
            raise PrelinkError(
                f"S15 release receipt mismatch for {key}: expected {value!r}, "
                f"got {release.get(key)!r}"
            )


def create_empty_root_snapshot(output_root: Path, snapshot_path: Path) -> dict[str, Any]:
    """Record an independently reviewable empty-output-root observation.

    A coordinator release receipt must pin this exact snapshot file hash before
    `make_prelink_receipt` will accept execution evidence.
    """
    root = output_root.resolve()
    snapshot_resolved = snapshot_path.resolve()
    try:
        snapshot_resolved.relative_to(root)
    except ValueError:
        pass
    else:
        raise PrelinkError("empty-root snapshot must be stored outside the output root")
    require_fresh_output_root(output_root)
    nonce = secrets.token_hex(32)
    record = {
        "schema": "s10-empty-output-root-snapshot-v1",
        "root_path": str(output_root.resolve()),
        "observed_absent": not output_root.exists(),
        "observed_empty": True,
        "observed_file_count": 0,
        "nonce": nonce,
        "nonce_sha256": sha256_bytes(nonce.encode()),
    }
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    record["snapshot_sha256"] = sha256_file(snapshot_path)
    return record


def validate_prebuild_snapshot(snapshot_path: Path, expected_sha256: str,
                               output_root: Path, expected_snapshot_path: Path) -> dict[str, Any]:
    if _lexical_absolute(snapshot_path) != _lexical_absolute(expected_snapshot_path):
        raise PrelinkError("empty-root snapshot path differs from the plan-pinned external location")
    _reject_symlink_components(snapshot_path)
    _require_regular_file(snapshot_path, "empty-root snapshot")
    try:
        snapshot_path.resolve().relative_to(output_root.resolve())
    except ValueError:
        pass
    else:
        raise PrelinkError("empty-root snapshot cannot be stored inside the output root")
    snapshot, snapshot_sha256 = read_hashed_json(snapshot_path)
    if snapshot_sha256 != expected_sha256:
        raise PrelinkError("empty-output-root snapshot SHA is not coordinator-pinned")
    nonce = snapshot.get("nonce")
    if (snapshot.get("schema") != "s10-empty-output-root-snapshot-v1"
            or snapshot.get("root_path") != str(output_root.resolve())
            or snapshot.get("observed_absent") is not True
            or snapshot.get("observed_empty") is not True
            or snapshot.get("observed_file_count") != 0
            or not isinstance(nonce, str)
            or not re.fullmatch(r"[0-9a-f]{64}", nonce)
            or snapshot.get("nonce_sha256") != sha256_bytes(nonce.encode())):
        raise PrelinkError("empty-output-root snapshot fields or nonce are invalid")
    return snapshot


def require_resource_gate_approval(plan: dict[str, Any], approval: dict[str, Any], *,
                                   plan_sha256: str, estimate_sha256: str,
                                   snapshot_sha256: str,
                                   measurement_receipt_sha256: str,
                                   measured_free_bytes: int,
                                   measured_at_unix_ns: int,
                                   required_free_bytes: int,
                                   s15_release_sha256: str,
                                   configuration_ledger_sha256: str,
                                   configure_wrf_sha256: str,
                                   configuration_ledger_plan_sha256: str,
                                   approval_sha256: str,
                                   trusted_approval_sha256: str) -> None:
    if (not isinstance(trusted_approval_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", trusted_approval_sha256)):
        raise PrelinkError("coordinator resource-approval SHA-256 must be supplied out of band")
    if approval_sha256 != trusted_approval_sha256:
        raise PrelinkError("coordinator resource-approval SHA-256 mismatch")
    build_gate = plan.get("resource_gate", {}).get("build", {})
    required = {
        "schema": "s10-resource-gate-approval-v1",
        "owner": "coordinator",
        "status": "APPROVED_FOR_S10_BUILD",
        "plan_sha256": plan_sha256,
        "output_size_estimate_sha256": estimate_sha256,
        "empty_output_root_snapshot_sha256": snapshot_sha256,
        "resource_measurement_receipt_sha256": measurement_receipt_sha256,
        "measured_free_bytes": measured_free_bytes,
        "measured_at_unix_ns": measured_at_unix_ns,
        "required_free_bytes": required_free_bytes,
        "s15_release_receipt_sha256": s15_release_sha256,
        "configuration_ledger_sha256": configuration_ledger_sha256,
        "configure_wrf_sha256": configure_wrf_sha256,
        "configuration_ledger_plan_sha256": configuration_ledger_plan_sha256,
        "minimum_free_bytes": build_gate.get("minimum_free_bytes"),
        "safety_factor": build_gate.get("safety_factor"),
        "full_matrix_build_or_link_allowed": True,
    }
    for key, expected in required.items():
        if approval.get(key) != expected:
            raise PrelinkError(f"coordinator resource-approval receipt mismatch for {key}")


_BUILD_ESTIMATE_COMPONENTS = (
    "preprocessed_sources_bytes", "object_module_bytes", "linked_executable_bytes",
    "temporary_build_peak_bytes", "logging_off_input_copy_bytes",
    "logging_off_run_staging_bytes", "logging_off_run_output_bytes",
    "logging_off_log_bytes", "logging_on_input_copy_bytes",
    "logging_on_run_staging_bytes", "logging_on_run_output_bytes",
    "logging_on_log_bytes",
)


def validate_build_output_estimate(estimate: dict[str, Any]) -> tuple[int, dict[str, int]]:
    if estimate.get("schema") != "s10-build-output-estimate-v1":
        raise PrelinkError("output-size estimate schema mismatch")
    if estimate.get("logging_modes") != ["off", "on"]:
        raise PrelinkError("output-size estimate must cover logging off and on")
    if estimate.get("retention_strategy") in (None, "", "todo", "unknown", "n/a"):
        raise PrelinkError("output-size estimate lacks a reviewed retention strategy")
    variants = estimate.get("variants")
    expected_variants = {"mp37_B", "mp37_C", "mp237_B", "mp237_C"}
    if not isinstance(variants, dict) or set(variants) != expected_variants:
        raise PrelinkError("output-size estimate must cover all four B/C arms")
    arm_totals: dict[str, int] = {}
    for key, row in variants.items():
        components = row.get("components") if isinstance(row, dict) else None
        if not isinstance(components, dict) or set(components) != set(_BUILD_ESTIMATE_COMPONENTS):
            raise PrelinkError(f"output-size estimate components are incomplete for {key}")
        values = list(components.values())
        if any(not isinstance(value, int) or isinstance(value, bool) or value < 0
               for value in values):
            raise PrelinkError(f"output-size estimate component is invalid for {key}")
        if not any(components[name] > 0 for name in _BUILD_ESTIMATE_COMPONENTS):
            raise PrelinkError(f"output-size estimate has no bytes for {key}")
        arm_total = sum(values)
        if row.get("estimated_bytes") != arm_total:
            raise PrelinkError(f"output-size estimate subtotal is invalid for {key}")
        arm_totals[key] = arm_total
    shared = estimate.get("shared_staging_components")
    if (not isinstance(shared, dict)
            or set(shared) != {"selected_case_tree_copy_bytes", "shared_run_support_bytes"}):
        raise PrelinkError("output-size estimate lacks shared staged-case costs")
    shared_values = list(shared.values())
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0
           for value in shared_values):
        raise PrelinkError("shared staging estimate contains an invalid byte count")
    if shared.get("selected_case_tree_copy_bytes", 0) <= 0:
        raise PrelinkError("estimate must include a full selected-case staging copy")
    shared_total = sum(shared_values)
    if estimate.get("shared_staging_bytes") != shared_total:
        raise PrelinkError("shared staging subtotal is invalid")
    total = sum(arm_totals.values()) + shared_total
    if estimate.get("total_estimated_bytes") != total:
        raise PrelinkError("output-size estimate total does not equal all arms")
    peak = estimate.get("peak_concurrent_bytes")
    if not isinstance(peak, int) or isinstance(peak, bool) or peak <= 0 or peak > total:
        raise PrelinkError("output-size estimate peak concurrency is invalid")
    return total, arm_totals


_BUILD_PREPARATION_COMPONENTS = (
    "preprocessed_sources_bytes", "object_module_bytes", "linked_executable_bytes",
)
_BUILD_PREPARATION_MEASUREMENT_SCOPE = (
    "No subprocesses or static/tool/environment probes run in this phase. It validates the "
    "coordinator-trusted plan hash, pinned estimate and empty-root snapshot, absent output "
    "root, and fresh OS disk_usage only. The receipt is capacity-only and cannot authorize "
    "build or model execution."
)
_S10_BUILD_COMMON_CPP_DEFINES = (
    "KDM6_PROGB_VALIDITY_CAPTURE", "KDM6_PROGB_POLICY_MIDPOINT",
)
_S10_BUILD_GUARD_CPP_DEFINE = "KDM6_PROGB_ZERO_QG_DIV_GUARD"


def validate_build_preparation_estimate(estimate: dict[str, Any]) -> tuple[int, dict[str, int]]:
    """Validate a measurement-only estimate that excludes every model run."""
    if (estimate.get("schema") != "s10-build-preparation-estimate-v1"
            or estimate.get("status") != "PROPOSAL_ONLY_INCOMPLETE_COMMAND_INPUTS"
            or estimate.get("build_command_execution_allowed") is not False
            or estimate.get("model_run_components_included") is not False
            or estimate.get("logging_modes") != []):
        raise PrelinkError("build-preparation estimate must remain a run-free proposal")
    variants = estimate.get("variants")
    expected_variants = {"mp37_B", "mp37_C", "mp237_B", "mp237_C"}
    if not isinstance(variants, dict) or set(variants) != expected_variants:
        raise PrelinkError("build-preparation estimate must cover exactly four B/C arms")
    arm_totals: dict[str, int] = {}
    for key, row in variants.items():
        components = row.get("components") if isinstance(row, dict) else None
        if not isinstance(components, dict) or set(components) != set(
                _BUILD_PREPARATION_COMPONENTS):
            raise PrelinkError(f"build-preparation estimate components are incomplete for {key}")
        values = list(components.values())
        if any(not isinstance(value, int) or isinstance(value, bool) or value < 0
               for value in values):
            raise PrelinkError(f"build-preparation estimate contains invalid bytes for {key}")
        subtotal = sum(values)
        if row.get("estimated_bytes") != subtotal:
            raise PrelinkError(f"build-preparation estimate subtotal is invalid for {key}")
        arm_totals[key] = subtotal
    shared = estimate.get("shared_build_staging_components")
    if not isinstance(shared, dict) or set(shared) != {
            "private_kdm6_cmake_build_peak_bytes", "private_kdm6_library_install_bytes"}:
        raise PrelinkError("build-preparation estimate lacks private KDM library build staging")
    shared_values = list(shared.values())
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0
           for value in shared_values):
        raise PrelinkError("build-preparation shared staging has invalid byte counts")
    shared_total = sum(shared_values)
    if estimate.get("shared_build_staging_bytes") != shared_total:
        raise PrelinkError("build-preparation shared staging subtotal is invalid")
    total = sum(arm_totals.values()) + shared_total
    if (estimate.get("total_estimated_bytes") != total
            or estimate.get("peak_concurrent_bytes") != total):
        raise PrelinkError("build-preparation estimate total or peak is inconsistent")
    safety = estimate.get("safety_factor")
    reserve = estimate.get("reserve_free_bytes")
    minimum = estimate.get("minimum_free_bytes")
    if (not isinstance(safety, int) or isinstance(safety, bool) or safety < 1
            or not isinstance(reserve, int) or isinstance(reserve, bool)
            or not isinstance(minimum, int) or isinstance(minimum, bool)):
        raise PrelinkError("build-preparation estimate safety factor/reserve are malformed")
    expected_required = max(minimum, total * safety + reserve)
    if estimate.get("required_free_bytes") != expected_required:
        raise PrelinkError("build-preparation estimate required free-space total is inconsistent")
    missing = estimate.get("missing_link_inputs")
    if (not isinstance(missing, dict) or set(missing) != {
                "canonical_standard_objects", "private_libkdm6_c_dylib",
                "complete_configure_wrf_library_input_list", "complete_link_argv"}
            or missing.get("canonical_standard_objects") is not None
            or missing.get("private_libkdm6_c_dylib") is not None
            or missing.get("complete_configure_wrf_library_input_list") is not None
            or missing.get("complete_link_argv") is not None
            or estimate.get("approval_eligible") is not False):
        raise PrelinkError("build-preparation proposal must expose missing link inputs and remain unapproved")
    return total, arm_totals


def validate_build_preparation_command_plan(plan: dict[str, Any]) -> None:
    """Check the declared B/C outputs and macro delta; never authorize execution."""
    gate = plan.get("resource_gate", {})
    prep_gate = gate.get("build_preparation", {})
    run_gate = gate.get("model_runs", {})
    templates = plan.get("build_matrix", {}).get("build_command_templates", {})
    estimate_rel = prep_gate.get("estimate_relative_path")
    receipt_rel = prep_gate.get("measurement_only_receipt_relative_path")
    if (gate.get("status") != "BLOCKED_PENDING_ESTIMATE_AND_REVIEW"
            or gate.get("full_matrix_build_or_link_allowed") is not False
            or gate.get("build", {}).get("status") != "BLOCKED_PENDING_ESTIMATE_AND_REVIEW"
            or prep_gate.get("status") != "MEASUREMENT_ONLY_PROPOSAL"
            or prep_gate.get("measurement_only_allowed") is not True
            or prep_gate.get("measurement_only_receipt_relative_path") != "S10/build_preparation_measurement.json"
            or not isinstance(estimate_rel, str) or Path(estimate_rel).is_absolute()
            or ".." in Path(estimate_rel).parts
            or not isinstance(prep_gate.get("estimate_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", prep_gate["estimate_sha256"])
            or not isinstance(receipt_rel, str) or Path(receipt_rel).is_absolute()
            or ".." in Path(receipt_rel).parts
            or prep_gate.get("build_execution_allowed") is not False
            or prep_gate.get("preprocess_object_link_execution_supported") is not False
            or prep_gate.get("allowed_commands") != []
            or prep_gate.get("measurement_subprocess_scope")
            != _BUILD_PREPARATION_MEASUREMENT_SCOPE
            or run_gate.get("status") != "BLOCKED_PENDING_LOG_BOUND_AND_RETENTION"
            or run_gate.get("allowed") is not False):
        raise PrelinkError("build-preparation gate must stay measurement-only with build/run blocked")
    if (templates.get("schema") != "s10-standalone-build-command-plan-v1"
            or templates.get("status") != "DECLARED_UNEXECUTED_INCOMPLETE"
            or templates.get("shell") is not False
            or templates.get("build_executor_supported") is not False
            or templates.get("runner_execution_allowed") is not False):
        raise PrelinkError("build command declarations must remain standalone, incomplete and unexecuted")
    if templates.get("generic_make_execution_allowed") is not False:
        raise PrelinkError("generic Make execution is forbidden by the build command plan")
    arms = templates.get("arms")
    if not isinstance(arms, dict) or set(arms) != {"mp37_B", "mp37_C", "mp237_B", "mp237_C"}:
        raise PrelinkError("build command declarations must enumerate all four arms")
    common_defines = list(_S10_BUILD_COMMON_CPP_DEFINES)
    if (plan.get("build_matrix", {}).get("common_required_compile_macros")
            != common_defines
            or _S10_BUILD_GUARD_CPP_DEFINE in common_defines):
        raise PrelinkError("S10 common CPP define set/order is code-fixed and excludes the C guard")
    for key, row in arms.items():
        scheme, arm = key.split("_")
        source_pin = plan["host_source_pins"][scheme]
        expected_source_sha = (source_pin["macro_off_b_midpoint_sha256"]
                              if arm == "B" else source_pin["c_overlay_sha256"])
        expected_guard = arm == "C"
        if (row.get("source_sha256") != expected_source_sha
                or row.get("guard_macro_defined") is not expected_guard
                or row.get("common_preprocessor_defines") != common_defines
                or (_S10_BUILD_GUARD_CPP_DEFINE in row.get("common_preprocessor_defines", []))
                or (arm == "B" and row.get("guard_macro") is not None)
                or (arm == "C" and row.get("guard_macro") != _S10_BUILD_GUARD_CPP_DEFINE)):
            raise PrelinkError(f"build command macro/source pins are inconsistent for {key}")
        expected_paths = {
            "preprocessed_relative_path": source_pin["preprocessed_relative_path"].replace(
                "{B,C}", arm),
            "object_relative_path": source_pin["object_relative_path"].replace("{B,C}", arm),
            "module_output_relative_path": source_pin["module_output_relative_path"].replace(
                "{B,C}", arm),
            "executable_relative_path": source_pin["executable_relative_path"].replace(
                "{B,C}", arm),
        }
        if any(row.get(name) != value for name, value in expected_paths.items()):
            raise PrelinkError(f"build command output paths differ from arm plan for {key}")
        object_argv = row.get("object_command_argv")
        if (not isinstance(object_argv, list)
                or any(not isinstance(token, str) for token in object_argv)
                or any(object_argv.count(flag) != 1 for flag in ("-o", "-J", "-I"))
                or any(object_argv.index(flag) + 1 >= len(object_argv)
                       for flag in ("-o", "-J", "-I") if flag in object_argv)):
            raise PrelinkError(f"object command path options are malformed for {key}")
        if (row.get("object_working_directory_relative_path")
                != Path(row["object_relative_path"]).parent.as_posix()
                or object_argv[0] != "<pinned-mpif90>"
                or object_argv[object_argv.index("-o") + 1]
                != Path(row["object_relative_path"]).name
                or object_argv[object_argv.index("-J") + 1]
                != Path(row["module_output_relative_path"]).name
                or object_argv[object_argv.index("-I") + 1]
                != Path(row["module_output_relative_path"]).name
                or object_argv[-1] != Path(row["preprocessed_relative_path"]).name):
            raise PrelinkError(f"object command paths are not uniquely pinned for {key}")
        normalized_object_argv = list(object_argv)
        normalized_object_argv[0] = "<pinned-mpif90>"
        normalized_object_argv[normalized_object_argv.index("-o") + 1] = \
            "<arm-output>/module.o"
        normalized_object_argv[normalized_object_argv.index("-J") + 1] = \
            "<arm-output>/mod"
        normalized_object_argv[normalized_object_argv.index("-I") + 1] = \
            "<arm-output>/mod"
        normalized_object_argv[-1] = "<arm-output>/module.f90"
        if normalized_object_argv != templates.get("object_command_template", {}).get("argv"):
            raise PrelinkError(f"object command options drift from the pinned template for {key}")
        source_path = row.get("source_relative_path")
        if source_path is not None and (not isinstance(source_path, str)
                                        or source_path.startswith("/")
                                        or ".." in Path(source_path).parts):
            raise PrelinkError(f"build command source path is unsafe for {key}")
    expected_guard = _S10_BUILD_GUARD_CPP_DEFINE
    if (arms["mp37_B"].get("guard_macro_defined") is not False
            or arms["mp237_B"].get("guard_macro_defined") is not False
            or arms["mp37_C"].get("guard_macro") != expected_guard
            or arms["mp237_C"].get("guard_macro") != expected_guard):
        raise PrelinkError("build command declarations do not encode the exact one-factor guard delta")
    preprocessing = templates.get("preprocessing_command_stages")
    if (not isinstance(preprocessing, list)
            or [stage.get("tool") for stage in preprocessing]
            != ["sed", "cpp", "standard", "cpp"]
            or any(stage.get("shell") is not False for stage in preprocessing)):
        raise PrelinkError("preprocessing declaration must be four ordered shell-free stages")
    for stage in preprocessing:
        argv = stage.get("argv_template")
        if (not isinstance(argv, list) or not argv
                or any(not isinstance(token, str) or not token for token in argv)
                or any(token.lower() in ("make", "gmake") for token in argv)):
            raise PrelinkError("preprocessing command template is malformed or invokes Make")
    configure_wrf_cppflags = [
        "-DEM_CORE=", "-DNMM_CORE=", "-DNMM_MAX_DIM=2600", "-DDA_CORE=",
        "-DWRFPLUS=", "-DIWORDSIZE=4", "-DDWORDSIZE=8", "-DRWORDSIZE=4",
        "-DLWORDSIZE=4", "-DNONSTANDARD_SYSTEM_SUBR", "-DMACOS",
        "-DWRF_USE_CLM", "-DUSE_NETCDF4_FEATURES",
        "-DWRFIO_NCD_LARGE_FILE_SUPPORT", "-DKDM6_SUBSTEP_DUMP",
        "-DDM_PARALLEL", "-DNETCDF", "-DLANDREAD_STUB=1",
        "-DUSE_ALLOCATABLES", "-Dwrfmodel", "-DGRIB1", "-DINTIO",
        "-DKEEP_INT_AROUND", "-DLIMIT_ARGS", "-DBUILD_RRTMG_FAST=0",
        "-DBUILD_RRTMK=0", "-DBUILD_SBM_FAST=1", "-DSHOW_ALL_VARS_USED=0",
        "-DCONFIG_BUF_LEN=65536", "-DMAX_DOMAINS_F=21", "-DMAX_HISTORY=25",
        "-DNMM_NEST=", "-I.", "-traditional-cpp", "-DUSE_NETCDF4_FEATURES",
        "-DWRFIO_NCD_LARGE_FILE_SUPPORT",
    ]
    if (preprocessing[0].get("argv_template") != [
            "<pinned-sed>", "-e", "s/^\\!.*'.*//", "-e", "s/^ *\\!.*'.*//",
            "<arm-source>"]
            or preprocessing[0].get("stdout_relative_path_template") != "<arm-work>/module.G"
            or preprocessing[1].get("fixed_configure_wrf_cppflags_tokens")
            != configure_wrf_cppflags
            or preprocessing[1].get("argv_template") != [
                "<pinned-cpp>", "-P", "-nostdinc", "-xassembler-with-cpp",
                "-I<shadow-host>/inc", "<fixed-configure-wrf-cppflags-tokens>",
                "-DKDM6_PROGB_VALIDITY_CAPTURE", "-DKDM6_PROGB_POLICY_MIDPOINT",
                "<C-only-guard-token-if-defined>", "<arm-work>/module.G"]
            or preprocessing[1].get("fixed_configure_wrf_cppflags_tokens", []).count(
                f"-D{_S10_BUILD_GUARD_CPP_DEFINE}")
            or preprocessing[1].get("argv_template", []).count(
                f"-D{_S10_BUILD_GUARD_CPP_DEFINE}")
            or preprocessing[1].get("stdout_relative_path_template") != "<arm-work>/module.bb"
            or preprocessing[2].get("argv_template") != [
                "<pinned-standard.exe>", "<arm-work>/module.bb"]
            or preprocessing[2].get("stdout_handoff")
            != "direct-pipe-to-final-cpp; shell=false; subprocess tool identity still requires pin review"
            or preprocessing[3].get("argv_template") != [
                "<pinned-cpp>", "-P", "-nostdinc", "-xassembler-with-cpp",
                "-traditional-cpp", "-DUSE_NETCDF4_FEATURES",
                "-DWRFIO_NCD_LARGE_FILE_SUPPORT", "<arm-work>/module.bb"]
            or preprocessing[3].get("stdout_relative_path_template")
            != "<arm-output>/module.f90"):
        raise PrelinkError("preprocessing stages differ from the declared Make recipe templates")
    object_template = templates.get("object_command_template")
    if (not isinstance(object_template, dict)
            or object_template.get("tool") != "mpif90"
            or object_template.get("shell") is not False
            or object_template.get("generic_make_execution_allowed") is not False
            or object_template.get("common_b_c_tokens") is not True
            or object_template.get("guard_macro_in_object_argv") is not False
            or any(_S10_BUILD_GUARD_CPP_DEFINE in token
                   for token in object_template.get("argv", [])
                   if isinstance(token, str))
            or "-ffp-contract=off" not in object_template.get("argv", [])):
        raise PrelinkError("object command template lacks pinned strict flags or B/C parity")
    argv = object_template["argv"]
    for output_flag, path_fragment in (("-o", "<arm-output>/module.o"),
                                       ("-J", "<arm-output>/mod"),
                                       ("-I", "<arm-output>/mod")):
        if argv.count(output_flag) != 1 or argv[argv.index(output_flag) + 1] != path_fragment:
            raise PrelinkError(f"object command template must pin exactly one arm-local {output_flag}")
    link_inputs = templates.get("link_inputs")
    expected_archive = plan["build_matrix"]["link_input_archive"]
    if (templates.get("link_command_template") is not None
            or not isinstance(link_inputs, dict)
            or link_inputs.get("canonical_archive_relative_to_private_host")
            != expected_archive["path_relative_to_private_host"]
            or link_inputs.get("canonical_archive_sha256") != expected_archive["sha256"]
            or link_inputs.get("canonical_archive_copy_allowed") is not False
            or not isinstance(link_inputs.get("canonical_archive_absolute_path_policy"), str)
            or "absolute real path" not in link_inputs[
                "canonical_archive_absolute_path_policy"]
            or link_inputs.get("canonical_main_wrf_object") is not None
            or link_inputs.get("canonical_kdm6ad_exit_object") is not None
            or link_inputs.get("canonical_module_wrf_top_object") is not None
            or link_inputs.get("private_libkdm6_c_dylib") is not None
            or link_inputs.get("complete_configure_wrf_external_library_inputs") is not None
            or link_inputs.get("complete_link_argv") is not None):
        raise PrelinkError("link template must remain absent until every exact input is pinned")


def validate_guarded_configuration_run(plan: dict[str, Any], *,
                                       workspace: Path,
                                       shadow_host: Path) -> dict[str, str]:
    """Revalidate the guarded configure/apply ledger before any native build."""
    validate_configure_failure_markers(plan)
    requirements = plan["prelink_requirements"]
    ledger_path = workspace / requirements["configuration_execution_ledger_relative_path"]
    ledger, ledger_sha = read_hashed_json(ledger_path)
    expected_ledger_sha = requirements.get("configuration_execution_ledger_sha256")
    if (not isinstance(expected_ledger_sha, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_ledger_sha)
            or ledger_sha != expected_ledger_sha):
        raise PrelinkError("configure execution ledger differs from its final plan pin")
    parent_plan_sha = requirements.get("configuration_ledger_plan_sha256")
    expected_config_sha = requirements.get("generated_configure_wrf_sha256")
    if (not isinstance(parent_plan_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", parent_plan_sha)
            or not isinstance(expected_config_sha, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_config_sha)):
        raise PrelinkError("final plan lacks the configure-run parent plan or configure.wrf pin")
    if (ledger.get("schema") != "s10-guarded-configuration-ledger-v1"
            or ledger.get("status") != "COMPLETE"
            or ledger.get("plan_sha256") != parent_plan_sha
            or ledger.get("toolchain_sha256") != plan["toolchain"]["toolchain_sha256"]
            or ledger.get("tool_environment_sha256") != plan["toolchain"]["environment_sha256"]):
        raise PrelinkError("configure/apply ledger is not bound to its reviewed configuration plan")
    commands = ledger.get("commands")
    if (not isinstance(commands, list) or len(commands) != 2
            or [row.get("stage") for row in commands]
            != ["configure", "apply_kdm6ad_config"]):
        raise PrelinkError("guarded configuration ledger must contain configure then apply")
    expected_argv = {
        "configure": requirements.get("configuration_generation_command"),
        "apply_kdm6ad_config": requirements.get("configuration_apply_command"),
    }
    expected_stdin = {
        "configure": validate_configure_menu_pin(plan)["stdin_sha256"],
        "apply_kdm6ad_config": requirements.get("configuration_apply_stdin_sha256"),
    }
    stdin_capture_paths = requirements.get("configuration_stdin_capture_paths")
    log_capture_paths = requirements.get("configuration_log_capture_paths")
    if not isinstance(stdin_capture_paths, dict) or not isinstance(log_capture_paths, dict):
        raise PrelinkError("configure/apply stdin and log capture paths must be plan-pinned")
    expected_environment_sha = plan.get("toolchain", {}).get("environment_sha256")
    output_root = workspace / plan.get("clean_shadow", {}).get(
        "fresh_build_output_root", "S10/build-clean")
    capture_root = shadow_host.parent.parent / "configuration_capture"
    for row, stage, script_key in zip(
            commands, ("configure", "apply_kdm6ad_config"),
            ("configure", "apply_kdm6ad_config.sh")):
        if row.get("returncode") != 0:
            raise PrelinkError("guarded configure/apply command did not complete successfully")
        if row.get("configuration_pipeline_id") != ledger.get("configuration_pipeline_id"):
            raise PrelinkError("configure/apply row is not bound to the ledger pipeline")
        if row.get("output_root_absent_before") is not True \
                or row.get("output_root_absent_after") is not True:
            raise PrelinkError("configure/apply touched the native build output root")
        argv, _flags = _validate_tool_command(
            row, expected_name="bash", plan=plan, shadow_host=shadow_host,
            output_root=output_root, cwd_root=shadow_host,
            capture_root=capture_root, label=f"guarded configuration {stage}")
        if (not isinstance(expected_argv[stage], list)
                or argv != expected_argv[stage]
                or Path(row.get("cwd", "")).resolve() != shadow_host.resolve()):
            raise PrelinkError(f"guarded configuration {stage} argv or cwd differs from the plan")
        if row.get("environment_sha256") != expected_environment_sha:
            raise PrelinkError(f"guarded configuration {stage} environment differs from the plan")
        for capture_field, digest_field in (("stdout_path", "stdout_sha256"),
                                            ("stderr_path", "stderr_sha256")):
            capture_rel = log_capture_paths.get(stage, {}).get(
                capture_field.removesuffix("_path"))
            if not isinstance(capture_rel, str):
                raise PrelinkError(f"guarded configuration {stage} log path is not plan-pinned")
            expected_capture = (workspace / capture_rel).resolve()
            recorded_capture = Path(row[capture_field]).resolve()
            if recorded_capture != expected_capture:
                raise PrelinkError(f"guarded configuration {stage} {capture_field} differs from the plan")
            if sha256_file(recorded_capture) != row.get(digest_field):
                raise PrelinkError(f"guarded configuration {stage} {capture_field} hash mismatch")
        expected_stdin_sha = expected_stdin[stage]
        stdin_rel = stdin_capture_paths.get(stage)
        if (not isinstance(expected_stdin_sha, str)
                or not re.fullmatch(r"[0-9a-f]{64}", expected_stdin_sha)
                or not isinstance(stdin_rel, str)
                or row.get("stdin_sha256") != expected_stdin_sha):
            raise PrelinkError(f"guarded configuration {stage} stdin/options are not plan-pinned")
        expected_stdin_path = (shadow_host.parent.parent / stdin_rel).resolve()
        recorded_stdin_path = Path(row.get("stdin_path", "")).resolve()
        if (recorded_stdin_path != expected_stdin_path
                or sha256_file(recorded_stdin_path) != expected_stdin_sha):
            raise PrelinkError(f"guarded configuration {stage} stdin capture differs from its exact pin")
        base_sha = requirements["configuration_inputs_sha256"][script_key]
        shadow_sha = expected_configuration_source_sha256(plan, script_key, shadow=True)
        patch_record = requirements.get("shadow_configuration_source_patches", {}).get(script_key)
        patch_sha = patch_record.get("patch_sha256") if isinstance(patch_record, dict) else None
        if (row.get("script_sha256") != shadow_sha
                or row.get("canonical_script_sha256") != base_sha
                or row.get("script_patch_sha256") != patch_sha):
            raise PrelinkError("guarded configure/apply script hash differs from the plan")
        for capture_field, digest_field in (("stdout_path", "stdout_sha256"),
                                            ("stderr_path", "stderr_sha256")):
            if sha256_file(Path(row[capture_field])) != row.get(digest_field):
                raise PrelinkError(f"guarded configure/apply {capture_field} hash mismatch")
    configure_stdout = Path(commands[0]["stdout_path"]).read_text(encoding="utf-8")
    validate_configure_success_stdout(configure_stdout)
    if commands[-1].get("configure_wrf_sha256_after") != expected_config_sha \
            or sha256_file(shadow_host / "configure.wrf") != expected_config_sha:
        raise PrelinkError("guarded configure.wrf output differs from the reviewed final pin")

    snapshot_sha = plan["trusted_s15_release"]["empty_output_root_snapshot_sha256"]
    preflight_sha = ledger.get("configure_resource_preflight_receipt_sha256")
    preflight_path = workspace / plan["resource_gate"]["configure_only"][
        "preflight_receipt_relative_path"]
    if not isinstance(preflight_sha, str):
        raise PrelinkError("guarded configuration receipt preflight SHA mismatch")
    preflight, actual_preflight_sha = read_hashed_json(preflight_path)
    if actual_preflight_sha != preflight_sha:
        raise PrelinkError("guarded configuration receipt preflight SHA mismatch")
    if (preflight.get("schema") != "s10-resource-preflight-receipt-v1"
            or preflight.get("phase") != "configure"
            or preflight.get("status") != "ALLOW_CONFIGURE_ONLY"
            or preflight.get("plan_sha256") != parent_plan_sha
            or preflight.get("empty_output_root_snapshot_sha256") != snapshot_sha):
        raise PrelinkError("guarded configuration preflight receipt is not plan/snapshot bound")
    marker_rel = requirements.get("configuration_preflight_consumption_marker_relative_path")
    marker_path = workspace / marker_rel if isinstance(marker_rel, str) else None
    marker_sha = ledger.get("configuration_preflight_consumption_marker_sha256")
    if marker_path is None or not isinstance(marker_sha, str):
        raise PrelinkError("guarded configure one-shot marker is missing or changed")
    marker, actual_marker_sha = read_hashed_json(marker_path)
    if actual_marker_sha != marker_sha:
        raise PrelinkError("guarded configure one-shot marker is missing or changed")
    marker_nonce = marker.get("nonce")
    if (marker.get("schema") != "s10-configure-preflight-consumption-v1"
            or marker.get("status") != "CONSUMED"
            or marker.get("plan_sha256") != parent_plan_sha
            or marker.get("resource_preflight_receipt_sha256") != preflight_sha
            or marker.get("resource_preflight_nonce") != preflight.get("nonce")
            or marker.get("configuration_ledger_nonce") != ledger.get("nonce")
            or not isinstance(marker_nonce, str)
            or ledger.get("configuration_preflight_consumption_nonce") != marker_nonce
            or marker.get("pipeline_id") != ledger.get("configuration_pipeline_id")
            or marker.get("nonce_sha256") != sha256_bytes(marker_nonce.encode())):
        raise PrelinkError("guarded configure one-shot marker is not bound to the run ledger")
    return {
        "configuration_command_ledger_path": str(ledger_path.resolve()),
        "configuration_command_ledger_sha256": ledger_sha,
        "configuration_ledger_plan_sha256": parent_plan_sha,
        "configure_wrf_sha256": expected_config_sha,
        "configure_preflight_receipt_sha256": preflight_sha,
        "configure_consumption_marker_sha256": marker_sha,
    }


def validate_build_resource_preflight(plan: dict[str, Any], receipt: dict[str, Any], *,
                                      plan_sha256: str, snapshot_sha256: str,
                                      output_root: Path,
                                      trusted_approval_sha256: str) -> None:
    gate = plan.get("resource_gate", {})
    build = gate.get("build", {})
    if (gate.get("status") != "READY_PENDING_COORDINATOR_RELEASE"
            or gate.get("full_matrix_build_or_link_allowed") is not False
            or build.get("status") != "READY_PENDING_COORDINATOR_RELEASE"
            or build.get("prebuild_gate_receipt_required") is not True):
        raise PrelinkError("resource gate is blocked; preprocessing, compilation and linking are prohibited")
    if receipt.get("schema") != "s10-resource-preflight-receipt-v1" \
            or receipt.get("phase") != "build" \
            or receipt.get("status") != "READY_FOR_REVIEWED_BUILD":
        raise PrelinkError("resource preflight receipt is not an approved build-phase receipt")
    if receipt.get("plan_sha256") != plan_sha256:
        raise PrelinkError("resource preflight receipt is bound to a different plan")
    if receipt.get("empty_output_root_snapshot_sha256") != snapshot_sha256:
        raise PrelinkError("resource preflight receipt is bound to a different empty-root snapshot")
    if receipt.get("output_root_path") != str(output_root.resolve()):
        raise PrelinkError("resource preflight receipt names a different build output root")
    estimate_sha = build.get("output_size_estimate_sha256")
    if (not isinstance(estimate_sha, str) or len(estimate_sha) != 64
            or receipt.get("output_size_estimate_sha256") != estimate_sha):
        raise PrelinkError("resource preflight receipt lacks the plan-pinned output-size estimate")
    if receipt.get("coordinator_resource_approval_sha256") != trusted_approval_sha256:
        raise PrelinkError("resource preflight receipt lacks the trusted coordinator approval")
    if (receipt.get("configure_wrf_sha256")
            != plan["prelink_requirements"].get("generated_configure_wrf_sha256")
            or receipt.get("configuration_ledger_plan_sha256")
            != plan["prelink_requirements"].get("configuration_ledger_plan_sha256")
            or not isinstance(receipt.get("configuration_command_ledger_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", receipt[
                "configuration_command_ledger_sha256"])):
        raise PrelinkError("resource preflight is not bound to a guarded configure ledger and config SHA")
    measurement_sha = receipt.get("resource_measurement_receipt_sha256")
    if not isinstance(measurement_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", measurement_sha):
        raise PrelinkError("resource preflight receipt is not bound to its approved space measurement")
    estimated_total = build.get("estimated_total_bytes")
    safety_factor = build.get("safety_factor")
    reserve = build.get("reserve_free_bytes")
    minimum = build.get("minimum_free_bytes")
    if (not isinstance(estimated_total, int) or isinstance(estimated_total, bool)
            or not isinstance(safety_factor, int) or isinstance(safety_factor, bool)
            or not isinstance(reserve, int) or isinstance(reserve, bool)
            or not isinstance(minimum, int) or isinstance(minimum, bool)):
        raise PrelinkError("reviewed resource estimate and reserve are malformed")
    expected_required = max(minimum, estimated_total * safety_factor + reserve)
    if (receipt.get("estimated_total_bytes") != estimated_total
            or receipt.get("required_free_bytes") != expected_required):
        raise PrelinkError("resource preflight byte estimate or required reserve differs from the plan")
    required_free = receipt.get("required_free_bytes")
    observed_free = receipt.get("observed_free_bytes")
    if (not isinstance(required_free, int) or isinstance(required_free, bool)
            or not isinstance(observed_free, int) or isinstance(observed_free, bool)
            or observed_free < required_free):
        raise PrelinkError("resource preflight did not meet the pinned free-space requirement")
    timestamp = receipt.get("resource_measurement_observed_at_unix_ns")
    checked_at = receipt.get("resource_gate_checked_at_unix_ns")
    now = time.time_ns()
    max_age = build.get("prebuild_receipt_max_age_seconds")
    if (not isinstance(timestamp, int) or isinstance(timestamp, bool)
            or not isinstance(checked_at, int) or isinstance(checked_at, bool)
            or not isinstance(max_age, int) or isinstance(max_age, bool)
            or timestamp > checked_at or checked_at > now
            or checked_at - timestamp > max_age * 1_000_000_000):
        raise PrelinkError("build resource preflight did not use a fresh capacity measurement")
    nonce = receipt.get("nonce")
    if (not isinstance(nonce, str) or not re.fullmatch(r"[0-9a-f]{64}", nonce)
            or receipt.get("nonce_sha256") != sha256_bytes(nonce.encode())):
        raise PrelinkError("build resource preflight nonce is invalid")
    if receipt.get("free_space_probe_path") != str(output_root.parent.resolve()):
        raise PrelinkError("resource preflight free-space probe path is not the output filesystem")
    current_usage = shutil.disk_usage(output_root.parent)
    post_build_reserve = build.get("reserve_free_bytes")
    if (not isinstance(post_build_reserve, int) or isinstance(post_build_reserve, bool)
            or current_usage.free < post_build_reserve):
        raise PrelinkError("fresh prelink free space is below the reviewed post-build reserve")


def create_resource_preflight_receipt(
        plan: dict[str, Any], *, plan_sha256: str,
        workspace: Path, canonical_host: Path, shadow_host: Path,
        overlay_paths: dict[str, Path], output_root: Path,
        snapshot_path: Path, phase: str, receipt_path: Path,
        estimate_path: Path | None = None,
        approval: dict[str, Any] | None = None,
        approval_sha256: str | None = None,
        trusted_approval_sha256: str | None = None,
        s15_release: dict[str, Any] | None = None,
        s15_release_sha256: str | None = None,
        trusted_s15_release_sha256: str | None = None) -> dict[str, Any]:
    if phase not in ("configure", "measure", "build", "build-preparation-measure"):
        raise PrelinkError(
            "resource preflight phase must be configure, measure, build or build-preparation-measure")
    root_rel = plan["clean_shadow"]["fresh_build_output_root"]
    _require_exact_workspace_path(workspace, output_root, root_rel, "build output root")
    snapshot_sha = plan.get("trusted_s15_release", {}).get(
        "empty_output_root_snapshot_sha256")
    snapshot_rel = plan["clean_shadow"]["empty_root_snapshot_relative_path"]
    expected_snapshot = _require_exact_workspace_path(
        workspace, snapshot_path, snapshot_rel, "empty-root snapshot")
    snapshot = validate_prebuild_snapshot(
        snapshot_path, snapshot_sha, output_root, expected_snapshot)
    if os.path.lexists(output_root):
        raise PrelinkError("resource preflight requires the build output root to remain absent")
    if _is_relative_to(_lexical_absolute(receipt_path), _lexical_absolute(output_root)):
        raise PrelinkError("resource preflight receipt must be outside the build output root")
    if phase == "configure":
        receipt_rel = plan["resource_gate"]["configure_only"][
            "preflight_receipt_relative_path"]
    elif phase == "build-preparation-measure":
        receipt_rel = plan["resource_gate"]["build_preparation"][
            "measurement_only_receipt_relative_path"]
    elif phase == "measure":
        receipt_rel = plan["resource_gate"]["build"]["measurement_receipt_relative_path"]
    else:
        receipt_rel = plan["resource_gate"]["build"]["prebuild_gate_receipt_relative_path"]
    receipt_path = _require_exact_workspace_path(
        workspace, receipt_path, receipt_rel, "resource preflight receipt",
        target_must_be_absent=phase == "build-preparation-measure")
    if phase != "build-preparation-measure":
        _require_regular_file_if_present(receipt_path, "resource preflight receipt")
    if phase == "build-preparation-measure":
        prep_gate = plan.get("resource_gate", {}).get("build_preparation", {})
        if approval is not None or approval_sha256 is not None or trusted_approval_sha256 is not None \
                or s15_release is not None or s15_release_sha256 is not None \
                or trusted_s15_release_sha256 is not None:
            raise PrelinkError("measurement-only phase cannot consume a coordinator approval or release")

    gate = plan.get("resource_gate", {})
    if phase == "build" and (
            gate.get("status") != "READY_PENDING_COORDINATOR_RELEASE"
            or gate.get("full_matrix_build_or_link_allowed") is not False
            or gate.get("build", {}).get("status") != "READY_PENDING_COORDINATOR_RELEASE"):
        raise PrelinkError("resource gate is blocked; build preflight fails closed")
    if phase == "build-preparation-measure":
        validate_build_preparation_command_plan(plan)
    if phase == "configure" and gate.get("configure_only", {}).get("allowed") is not True:
        raise PrelinkError("configure-only resource allowance is not reviewed")
    if phase == "measure" and not gate.get("build", {}).get("output_size_estimate_sha256"):
        raise PrelinkError("build resource measurement requires a plan-pinned output-size estimate")

    # Capacity-only preparation has no compiler, SDK, patch, or WRF execution
    # semantics. Its trusted plan/estimate/snapshot and OS disk usage are the
    # complete measurement inputs. Configure/measure/build retain full tool and
    # static-source validation.
    if phase != "build-preparation-measure":
        environment = planned_tool_environment(plan)
        validate_static_pins(
            plan, workspace=workspace, canonical_host=canonical_host,
            shadow_host=shadow_host, overlay_paths=overlay_paths,
            environment=environment)

    usage = shutil.disk_usage(output_root.parent)
    measured_free = usage.free
    now = time.time_ns()
    required_free: int
    receipt_status: str
    estimated_bytes: int | None = None
    estimate_sha: str | None = None
    coordinator_approval_sha: str | None = None
    release_sha: str | None = None
    measurement_sha: str | None = None
    measurement_observed_at: int | None = None
    build_preparation_capacity_status: str | None = None
    if phase == "configure":
        configure_gate = gate.get("configure_only", {})
        if configure_gate.get("allowed") is not True:
            raise PrelinkError("configure-only resource allowance is not reviewed")
        if configure_gate.get("output_root_must_remain_absent") is not True:
            raise PrelinkError("configure-only phase must keep build output root absent")
        expected_capture_root = workspace / configure_gate.get(
            "capture_root_relative_to_workspace", "")
        if not _is_relative_to(receipt_path.resolve(), expected_capture_root.resolve()):
            raise PrelinkError("configure-only resource receipt must be stored in its capture root")
        max_transient = configure_gate.get("maximum_transient_bytes")
        min_free = configure_gate.get("minimum_free_bytes_after_reserve")
        if (not isinstance(max_transient, int) or isinstance(max_transient, bool)
                or not isinstance(min_free, int) or isinstance(min_free, bool)):
            raise PrelinkError("configure-only transient-space bound is not pinned")
        required_free = max_transient + min_free
        if measured_free < required_free:
            raise PrelinkError("fresh free space is below the configure-only reserve")
        receipt_status = "ALLOW_CONFIGURE_ONLY"
        allowed_commands = configure_gate.get("allowed_commands")
        if allowed_commands != ["./configure", "./apply_kdm6ad_config.sh"]:
            raise PrelinkError("configure-only command allowlist is not exact")
    elif phase == "build-preparation-measure":
        prep_gate = gate["build_preparation"]
        if estimate_path is None:
            raise PrelinkError("build-preparation estimate path is required")
        _require_exact_workspace_path(
            workspace, estimate_path, prep_gate.get("estimate_relative_path", ""),
            "build-preparation estimate")
        _require_regular_file(estimate_path, "build-preparation estimate")
        estimate, estimate_sha = read_hashed_json(estimate_path)
        if estimate_sha != prep_gate.get("estimate_sha256"):
            raise PrelinkError("build-preparation estimate SHA differs from the plan pin")
        estimated_bytes, _arm_totals = validate_build_preparation_estimate(estimate)
        if estimated_bytes != estimate.get("total_estimated_bytes"):
            raise PrelinkError("build-preparation estimate total is inconsistent")
        safety_factor = prep_gate.get("safety_factor")
        reserve = prep_gate.get("reserve_free_bytes")
        minimum = prep_gate.get("minimum_free_bytes")
        if (not isinstance(safety_factor, int) or isinstance(safety_factor, bool)
                or safety_factor < 1 or not isinstance(reserve, int)
                or isinstance(reserve, bool) or not isinstance(minimum, int)
                or isinstance(minimum, bool)):
            raise PrelinkError("build-preparation safety factor and reserve are malformed")
        if (estimate.get("safety_factor") != safety_factor
                or estimate.get("reserve_free_bytes") != reserve
                or estimate.get("minimum_free_bytes") != minimum):
            raise PrelinkError("build-preparation estimate safety/reserve differs from plan")
        required_free = max(minimum, estimated_bytes * safety_factor + reserve)
        if estimate.get("required_free_bytes") != required_free:
            raise PrelinkError("build-preparation required free-space total differs from plan")
        measurement_observed_at = now
        receipt_status = "MEASURED_BUILD_PREPARATION_CAPACITY_ONLY"
        build_preparation_capacity_status = (
            "INSUFFICIENT_FOR_PROPOSAL" if measured_free < required_free
            else "MEASURED_ONLY_INCOMPLETE_COMMAND_INPUTS")
    else:
        build_gate = gate.get("build", {})
        if estimate_path is None:
            raise PrelinkError("reviewed output-size estimate file is required")
        expected_estimate_path = workspace / build_gate.get(
            "output_size_estimate_relative_path", "")
        if estimate_path.resolve() != expected_estimate_path.resolve():
            raise PrelinkError("output-size estimate path differs from the plan")
        estimate, estimate_sha = read_hashed_json(estimate_path)
        if estimate_sha != build_gate.get("output_size_estimate_sha256"):
            raise PrelinkError("output-size estimate SHA differs from the reviewed plan")
        if estimate.get("schema") != "s10-build-output-estimate-v1":
            raise PrelinkError("output-size estimate schema mismatch")
        estimated_bytes, _arm_totals = validate_build_output_estimate(estimate)
        if estimated_bytes != build_gate.get("estimated_total_bytes"):
            raise PrelinkError("output-size estimate total differs from the reviewed plan")
        safety_factor = build_gate.get("safety_factor")
        reserve = build_gate.get("reserve_free_bytes")
        min_free = build_gate.get("minimum_free_bytes")
        if (not isinstance(safety_factor, int) or isinstance(safety_factor, bool)
                or safety_factor < 1 or not isinstance(reserve, int)
                or isinstance(reserve, bool) or not isinstance(min_free, int)
                or isinstance(min_free, bool)):
            raise PrelinkError("reviewed build free-space requirements are incomplete")
        required_free = max(min_free, estimated_bytes * safety_factor + reserve)
        if measured_free < required_free:
            raise PrelinkError("fresh free space is below the reviewed build-size requirement")
        if phase == "measure":
            if gate.get("status") != "READY_PENDING_COORDINATOR_RELEASE":
                raise PrelinkError("capacity measurement requires a reviewed, unapproved plan")
            expected_measurement_path = workspace / build_gate.get(
                "measurement_receipt_relative_path", "")
            if receipt_path.resolve() != expected_measurement_path.resolve():
                raise PrelinkError("capacity measurement receipt path differs from the plan")
            measurement_observed_at = now
            receipt_status = "MEASURED_BUILD_CAPACITY"
        else:
            if build_gate.get("status") != "READY_PENDING_COORDINATOR_RELEASE":
                raise PrelinkError("build resource gate approval is missing")
            if (s15_release is None or s15_release_sha256 is None
                    or trusted_s15_release_sha256 is None):
                raise PrelinkError("coordinator S15 lane release is required before any build stage")
            require_s15_release(plan, s15_release, plan_sha256,
                                s15_release_sha256, trusted_s15_release_sha256)
            configuration_run = validate_guarded_configuration_run(
                plan, workspace=workspace, shadow_host=shadow_host)
            measurement_path = workspace / build_gate.get(
                "measurement_receipt_relative_path", "")
            measurement, measurement_sha = read_hashed_json(measurement_path)
            if (measurement.get("schema") != "s10-resource-preflight-receipt-v1"
                    or measurement.get("phase") != "measure"
                    or measurement.get("status") != "MEASURED_BUILD_CAPACITY"
                    or measurement.get("plan_sha256") != plan_sha256
                    or measurement.get("empty_output_root_snapshot_sha256") != snapshot_sha
                    or measurement.get("output_size_estimate_sha256") != estimate_sha
                    or measurement.get("required_free_bytes") != required_free):
                raise PrelinkError("fresh capacity measurement receipt does not match this plan/estimate")
            measured_at = measurement.get("observed_at_unix_ns")
            measurement_observed_at = measured_at
            max_age = build_gate.get("prebuild_receipt_max_age_seconds")
            if (not isinstance(measured_at, int) or isinstance(measured_at, bool)
                    or not isinstance(max_age, int) or isinstance(max_age, bool)
                    or measured_at > now or now - measured_at > max_age * 1_000_000_000):
                raise PrelinkError("capacity measurement receipt is stale")
            if approval is None or approval_sha256 is None or trusted_approval_sha256 is None:
                raise PrelinkError("coordinator resource approval is required before any build stage")
            require_resource_gate_approval(
                plan, approval, plan_sha256=plan_sha256,
                estimate_sha256=estimate_sha, snapshot_sha256=snapshot_sha,
                measurement_receipt_sha256=measurement_sha,
                measured_free_bytes=measurement.get("observed_free_bytes"),
                measured_at_unix_ns=measured_at,
                required_free_bytes=required_free,
                s15_release_sha256=s15_release_sha256,
                configuration_ledger_sha256=configuration_run[
                    "configuration_command_ledger_sha256"],
                configure_wrf_sha256=configuration_run["configure_wrf_sha256"],
                configuration_ledger_plan_sha256=configuration_run[
                    "configuration_ledger_plan_sha256"],
                approval_sha256=approval_sha256,
                trusted_approval_sha256=trusted_approval_sha256)
            coordinator_approval_sha = approval_sha256
            release_sha = s15_release_sha256
            receipt_status = "READY_FOR_REVIEWED_BUILD"

    nonce = secrets.token_hex(32)
    result = {
        "schema": "s10-resource-preflight-receipt-v1",
        "phase": phase,
        "status": receipt_status,
        "plan_sha256": plan_sha256,
        "output_root_path": str(output_root.resolve()),
        "empty_output_root_snapshot_sha256": snapshot_sha,
        "empty_output_root_snapshot_nonce_sha256": snapshot["nonce_sha256"],
        "toolchain_sha256": (
            None if phase == "build-preparation-measure"
            else plan["toolchain"]["toolchain_sha256"]),
        "tool_environment_sha256": (
            None if phase == "build-preparation-measure"
            else plan["toolchain"]["environment_sha256"]),
        "free_space_probe_path": str(output_root.parent.resolve()),
        "free_space_total_bytes": usage.total,
        "free_space_used_bytes": usage.used,
        "observed_free_bytes": measured_free,
        "required_free_bytes": required_free,
        "observed_at_unix_ns": now,
        "resource_measurement_observed_at_unix_ns": measurement_observed_at,
        "resource_gate_checked_at_unix_ns": now if phase == "build" else None,
        "output_size_estimate_sha256": estimate_sha,
        "estimated_total_bytes": estimated_bytes,
        "resource_measurement_receipt_sha256": measurement_sha,
        "build_preparation_measurement_only": phase == "build-preparation-measure",
        "build_preparation_capacity_status": build_preparation_capacity_status,
        "static_pin_validation_completed": (
            False if phase == "build-preparation-measure" else None),
        "toolchain_validation_completed": (
            False if phase == "build-preparation-measure" else None),
        "environment_validation_completed": (
            False if phase == "build-preparation-measure" else None),
        "measurement_subprocess_scope": (
            plan["resource_gate"]["build_preparation"]["measurement_subprocess_scope"]
            if phase == "build-preparation-measure" else None),
        "wrf_preprocess_object_link_or_model_commands_launched": (
            False if phase == "build-preparation-measure" else None),
        "build_execution_allowed": False if phase == "build-preparation-measure" else None,
        "model_execution_allowed": False if phase == "build-preparation-measure" else None,
        "configuration_command_ledger_sha256": (
            configuration_run["configuration_command_ledger_sha256"]
            if phase == "build" else None),
        "configuration_ledger_plan_sha256": (
            configuration_run["configuration_ledger_plan_sha256"]
            if phase == "build" else None),
        "configure_wrf_sha256": (
            configuration_run["configure_wrf_sha256"] if phase == "build" else None),
        "coordinator_resource_approval_sha256": coordinator_approval_sha,
        "s15_release_receipt_sha256": release_sha,
        "allowed_commands": (
            gate["configure_only"]["allowed_commands"] if phase == "configure"
            else [] if phase in ("measure", "build-preparation-measure")
            else gate["build"]["allowed_build_stages"]
        ),
        "nonce": nonce,
        "nonce_sha256": sha256_bytes(nonce.encode()),
    }
    payload = (json.dumps(result, indent=2) + "\n").encode()
    if phase == "build-preparation-measure":
        _write_new_workspace_receipt(
            workspace, receipt_rel, payload)
    else:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_bytes(payload)
    return result


def _effective_namelist(pristine: str, mp: str) -> str:
    text = pristine
    for key, value in (
        ("run_days", "0"), ("run_hours", "0"), ("run_minutes", "0"),
        ("run_seconds", "20"), ("input_inname", '"wrfinput_d<domain>"'),
        ("bdy_inname", '"wrfbdy_d<domain>"'),
        ("auxinput24_inname", '"wrfchainp_d<domain>"'),
        ("history_interval", "0"), ("history_interval_s", "20"),
        ("frames_per_outfile", "1000"), ("mp_physics", mp),
        ("nio_tasks_per_group", "0"), ("nio_groups", "1"),
    ):
        text = replace_line(text, key, value)
    text = set_or_insert(text, "nproc_x", "1")
    return set_or_insert(text, "nproc_y", "1")


def validate_source_overlay(pin: dict[str, Any], *, scheme: str,
                            canonical_source: Path,
                            overlay_path: Path) -> dict[str, str]:
    if sha256_file(canonical_source) != pin["source_sha256"]:
        raise PrelinkError(f"canonical source hash changed for {scheme}")
    overlay = overlay_path.resolve()
    text = overlay.read_text(encoding="utf-8")
    overlay_sha = sha256_file(overlay)
    if overlay_sha != pin["c_overlay_sha256"]:
        raise PrelinkError(f"current C overlay hash changed for {scheme}")
    macro_off = strip_czero_capture(strip_macro_else(text, ZERO_QG_MACRO))
    macro_off_sha = sha256_bytes(macro_off.encode())
    if macro_off_sha != pin["macro_off_b_midpoint_sha256"]:
        raise PrelinkError(f"macro-off source is not the pinned B midpoint for {scheme}")
    return {
        "canonical_source": str(canonical_source.resolve()),
        "canonical_source_sha256": pin["source_sha256"],
        "c_overlay": str(overlay),
        "c_overlay_sha256": overlay_sha,
        "macro_off_b_midpoint_sha256": macro_off_sha,
    }


def validate_toolchain(plan: dict[str, Any], shadow_host: Path, *,
                       environment: Mapping[str, str] | None = None) -> dict[str, dict[str, str]]:
    toolchain = plan.get("toolchain", {})
    specs = toolchain.get("tools")
    if not isinstance(specs, dict) or not specs:
        raise PrelinkError("toolchain binary pins are missing")
    environment_snapshot = tool_environment_snapshot(environment)
    environment_sha = sha256_bytes(json.dumps(
        environment_snapshot, sort_keys=True, separators=(",", ":")).encode())
    if environment_sha != toolchain.get("environment_sha256"):
        raise PrelinkError("toolchain resolution environment differs from its pin")
    configured_environment = toolchain.get("configuration_environment", {})
    if not isinstance(configured_environment, dict):
        raise PrelinkError("pinned configuration environment is malformed")
    for name, expected in configured_environment.items():
        if name not in environment_snapshot or environment_snapshot[name] != expected:
            raise PrelinkError(f"configuration environment differs from its pin: {name}")
    canonical_fields = {"tools": specs, "environment_sha256": environment_sha}
    sdkroot_pin = toolchain.get("sdkroot_resolution")
    if "SDKROOT" in configured_environment:
        if not isinstance(sdkroot_pin, dict):
            raise PrelinkError("SDKROOT environment requires a toolchain resolution pin")
        canonical_fields["sdkroot_resolution"] = sdkroot_pin
    elif sdkroot_pin is not None:
        raise PrelinkError("SDKROOT resolution pin exists without a pinned SDKROOT environment")
    canonical = json.dumps(canonical_fields, sort_keys=True,
                           separators=(",", ":")).encode()
    if sha256_bytes(canonical) != toolchain.get("toolchain_sha256"):
        raise PrelinkError("pinned toolchain manifest digest is inconsistent")
    child_environment = (dict(environment) if environment is not None else {
        name: value for name, value in environment_snapshot.items()
        if value is not None
    })
    resolved: dict[str, dict[str, str]] = {}
    for name, spec in specs.items():
        if not isinstance(spec, dict):
            raise PrelinkError(f"toolchain record is malformed for {name}")
        if "path" in spec:
            path = Path(spec["path"])
        elif "path_relative_to_shadow_host" in spec:
            path = (shadow_host / spec["path_relative_to_shadow_host"]).resolve()
        else:
            raise PrelinkError(f"toolchain path is missing for {name}")
        digest = sha256_file(path)
        if digest != spec.get("sha256"):
            raise PrelinkError(f"toolchain binary hash changed for {name}: {path}")
        resolved[name] = {"path": str(path), "sha256": digest}
        version_argv = spec.get("version_argv")
        version_stdout = spec.get("version_stdout")
        if version_argv is not None or version_stdout is not None:
            if (not isinstance(version_argv, list) or not version_argv
                    or not isinstance(version_stdout, str)):
                raise PrelinkError(f"version probe pin is malformed for {name}")
    # No plan-selected executable is invoked until every binary path and digest
    # in the aggregate manifest has been validated.
    for name, spec in specs.items():
        path = Path(resolved[name]["path"])
        version_argv = spec.get("version_argv")
        version_stdout = spec.get("version_stdout")
        if version_argv is not None:
            result = subprocess.run(
                [str(path), *version_argv], check=True, capture_output=True,
                text=True, shell=False, env=child_environment)
            first_version_line = result.stdout.strip().splitlines()[0]
            if first_version_line != version_stdout:
                raise PrelinkError(f"pinned tool version output changed for {name}")
            resolved[name]["version_stdout"] = version_stdout
    for env_name, tool_name in (("NETCDF_C", "nc-config"), ("NETCDF", "nf-config")):
        if tool_name in resolved:
            root = environment_snapshot.get(env_name)
            expected_path = (Path(root) / "bin" / tool_name).resolve() if root else None
            if expected_path is None or Path(resolved[tool_name]["path"]).resolve() != expected_path:
                raise PrelinkError(f"{tool_name} is not resolved from pinned {env_name}")
    pinned_path = environment_snapshot.get("PATH")
    for executable in ("perl5", "m4", "python3"):
        if executable not in resolved:
            continue
        selected = shutil.which(executable, path=pinned_path)
        if (selected is None
                or Path(selected).resolve() != Path(resolved[executable]["path"]).resolve()):
            raise PrelinkError(f"configure helper {executable} is not the pinned PATH resolution")
    if {"mpif90", "gfortran", "ld"}.issubset(resolved):
        mpif90_command = subprocess.run(
            [resolved["mpif90"]["path"], "--showme:command"],
            check=True, capture_output=True, text=True,
            env=child_environment).stdout.strip()
        if mpif90_command != toolchain.get("mpif90_underlying_command"):
            raise PrelinkError("mpif90 resolved to an unexpected Fortran compiler")
        compiler_path = shutil.which(mpif90_command)
        if compiler_path is None or Path(compiler_path).resolve() != Path(resolved["gfortran"]["path"]).resolve():
            raise PrelinkError("mpif90's Fortran compiler path is not the pinned gfortran binary")
        reported_ld = subprocess.run(
            [resolved["gfortran"]["path"], "-print-prog-name=ld"],
            check=True, capture_output=True, text=True,
            env=child_environment).stdout.strip()
        if reported_ld != toolchain.get("linker_name_reported_by_gfortran"):
            raise PrelinkError("gfortran reported an unexpected linker name")
        for child, wrapper in (("as", "as_wrapper"), ("ld", "ld_wrapper")):
            reported = subprocess.run(
                [resolved["gfortran"]["path"], f"-print-prog-name={child}"],
                check=True, capture_output=True, text=True,
                env=child_environment).stdout.strip()
            wrapper_path = shutil.which(reported)
            if (wrapper_path is None or wrapper not in resolved
                    or Path(wrapper_path).resolve() != Path(resolved[wrapper]["path"]).resolve()):
                raise PrelinkError(f"gfortran's {child} wrapper is not the pinned executable")
            xcrun_path = resolved.get("xcrun", {}).get("path")
            actual_child = subprocess.run(
                [xcrun_path, "--find", child], check=True,
                capture_output=True, text=True, env=child_environment).stdout.strip() if xcrun_path else ""
            if (not actual_child or child not in resolved
                    or Path(actual_child).resolve() != Path(resolved[child]["path"]).resolve()):
                raise PrelinkError(f"xcrun's {child} subordinate binary is not pinned")
        for child in ("f951", "collect2"):
            reported = subprocess.run(
                [resolved["gfortran"]["path"], f"-print-prog-name={child}"],
                check=True, capture_output=True, text=True,
                env=child_environment).stdout.strip()
            if child not in resolved or Path(reported).resolve() != Path(resolved[child]["path"]).resolve():
                raise PrelinkError(f"gfortran's {child} subordinate binary is not pinned")
    if "SDKROOT" in configured_environment:
        sdk_environment = (dict(environment) if environment is not None else {
            name: value for name, value in environment_snapshot.items()
            if value is not None
        })
        sdkroot = validate_sdkroot_resolution(plan, environment=sdk_environment)
        resolved["sdkroot"] = sdkroot
    return resolved


def validate_configure_menu_pin(plan: dict[str, Any]) -> dict[str, Any]:
    """Require the configure menu bytes, menu choices, and both hashes to agree."""
    requirements = plan.get("prelink_requirements", {})
    menu = requirements.get("configure_menu_selection")
    if not isinstance(menu, dict):
        raise PrelinkError("configure menu selection pin is missing or malformed")
    architecture = menu.get("architecture_option")
    nesting = menu.get("nesting_option")
    if type(architecture) is not int or architecture != 35:
        raise PrelinkError("configure architecture option must be pinned integer 35")
    if type(nesting) is not int or nesting != 1:
        raise PrelinkError("configure nesting option must be pinned integer 1")
    stdin_text = menu.get("stdin_bytes")
    if not isinstance(stdin_text, str):
        raise PrelinkError("configure menu stdin bytes must be a text string")
    stdin_bytes = stdin_text.encode("utf-8")
    expected_bytes = f"{architecture}\n{nesting}\n".encode("ascii")
    if stdin_bytes != expected_bytes:
        raise PrelinkError("configure menu stdin bytes do not encode the pinned options")
    digest = sha256_bytes(stdin_bytes)
    nested_digest = menu.get("stdin_sha256")
    top_level_digest = requirements.get("configure_selection_stdin_sha256")
    if digest != nested_digest or digest != top_level_digest:
        raise PrelinkError(
            "configure menu stdin SHA must match both plan-pinned configure stdin hashes")
    return {
        "architecture_option": architecture,
        "nesting_option": nesting,
        "stdin_sha256": digest,
    }


def expected_configuration_source_sha256(plan: dict[str, Any], source_name: str, *,
                                         shadow: bool) -> str:
    requirements = plan.get("prelink_requirements", {})
    base = requirements.get("configuration_inputs_sha256", {}).get(source_name)
    overlays = requirements.get("shadow_configuration_source_patches", {})
    overlay = overlays.get(source_name) if isinstance(overlays, dict) else None
    if isinstance(overlay, dict) and shadow:
        result = overlay.get("shadow_sha256")
    else:
        result = base
    if not isinstance(result, str) or not re.fullmatch(r"[0-9a-f]{64}", result):
        raise PrelinkError(f"configuration source hash is missing or malformed: {source_name}")
    return result


def validate_single_file_configuration_patch(patch_bytes: bytes,
                                             expected_name: str) -> None:
    """Accept one exact-path unified diff, with no file creation/deletion or traversal."""
    try:
        lines = patch_bytes.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise PrelinkError("configuration patch is not UTF-8 text") from exc
    if len(lines) < 3 or lines[0] != f"--- original/{expected_name}" \
            or lines[1] != f"+++ patched/{expected_name}":
        raise PrelinkError("configuration patch headers do not name the single pinned hook")
    if (Path(lines[0][4:]).is_absolute() or Path(lines[1][4:]).is_absolute()
            or ".." in Path(lines[0][4:]).parts or ".." in Path(lines[1][4:]).parts):
        raise PrelinkError("configuration patch contains an absolute or traversing path")
    forbidden = (
        "diff --git ", "Index: ", "rename from ", "rename to ",
        "new file mode ", "deleted file mode ", "GIT binary patch", "Binary files ",
    )
    if any(line.startswith(forbidden) for line in lines):
        raise PrelinkError("configuration patch contains a rename, extra file, or binary section")

    hunk_pattern = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: .*)?$")
    hunk_count = 0
    old_ranges: list[tuple[int, int]] = []
    new_ranges: list[tuple[int, int]] = []
    old_seen = new_seen = 0
    for line in lines[2:]:
        match = hunk_pattern.match(line)
        if match:
            if hunk_count and (old_seen != old_ranges[-1][1] or new_seen != new_ranges[-1][1]):
                raise PrelinkError("configuration patch hunk line counts are inconsistent")
            old_start = int(match.group(1))
            old_count = int(match.group(2) or "1")
            new_start = int(match.group(3))
            new_count = int(match.group(4) or "1")
            old_ranges.append((old_start, old_count))
            new_ranges.append((new_start, new_count))
            if len(set(old_ranges)) != len(old_ranges) or len(set(new_ranges)) != len(new_ranges):
                raise PrelinkError("configuration patch contains duplicate hunks")
            if len(old_ranges) > 1:
                prev_old_start, prev_old_count = old_ranges[-2]
                prev_new_start, prev_new_count = new_ranges[-2]
                if (old_start < prev_old_start + prev_old_count
                        or new_start < prev_new_start + prev_new_count):
                    raise PrelinkError("configuration patch hunks overlap or are out of order")
            old_seen = new_seen = 0
            hunk_count += 1
            continue
        if hunk_count == 0:
            raise PrelinkError("configuration patch contains data before its first hunk")
        if line.startswith("\\ No newline at end of file"):
            continue
        if not line or line[0] not in " +-":
            raise PrelinkError("configuration patch contains an unsupported or extra file section")
        if line[0] in " -":
            old_seen += 1
        if line[0] in " +":
            new_seen += 1
        if old_seen > old_ranges[-1][1] or new_seen > new_ranges[-1][1]:
            raise PrelinkError("configuration patch hunk has more lines than declared")
    if hunk_count == 0 or old_seen != old_ranges[-1][1] or new_seen != new_ranges[-1][1]:
        raise PrelinkError("configuration patch hunk line counts are inconsistent")


def _verify_shadow_configuration_patch(plan: dict[str, Any], *, source_name: str,
                                       canonical_source: Path,
                                       shadow_source: Path,
                                       workspace: Path,
                                       environment: Mapping[str, str]) -> dict[str, str]:
    requirements = plan["prelink_requirements"]
    source_hashes = requirements["configuration_inputs_sha256"]
    overlay = requirements.get("shadow_configuration_source_patches", {}).get(source_name)
    if not isinstance(overlay, dict):
        raise PrelinkError(f"shadow configuration patch record is malformed: {source_name}")
    base_sha = source_hashes.get(source_name)
    if (not isinstance(base_sha, str) or overlay.get("canonical_sha256") != base_sha
            or sha256_file(canonical_source) != base_sha):
        raise PrelinkError(f"canonical configuration source differs from patch base: {source_name}")
    if canonical_source.is_symlink() or shadow_source.is_symlink():
        raise PrelinkError(f"configuration patch source must not be a symlink: {source_name}")
    relative_patch = overlay.get("patch_relative_path")
    if not isinstance(relative_patch, str) or not relative_patch:
        raise PrelinkError("private configuration patch path is missing")
    patch_path = (workspace / relative_patch).resolve()
    private_root = (workspace / "S10").resolve()
    if not _is_relative_to(patch_path, private_root):
        raise PrelinkError("private configuration patch escaped the S10 evidence root")
    patch_sha = overlay.get("patch_sha256")
    if not isinstance(patch_sha, str) or sha256_file(patch_path) != patch_sha:
        raise PrelinkError(f"private configuration patch hash differs from its plan pin: {source_name}")
    patch_tool_name = overlay.get("patch_tool_name")
    patch_argv = overlay.get("patch_argv")
    if patch_tool_name != "patch" or patch_argv != ["-s", "-p1"]:
        raise PrelinkError("configuration patch executable/argv is not the reviewed patch policy")
    patch_tool = plan.get("toolchain", {}).get("tools", {}).get("patch")
    if not isinstance(patch_tool, dict):
        raise PrelinkError("pinned patch utility is missing from the toolchain")
    patch_executable = Path(patch_tool.get("path", ""))
    if (not patch_executable.is_absolute()
            or sha256_file(patch_executable) != patch_tool.get("sha256")):
        raise PrelinkError("pinned patch utility path/hash is invalid")
    base_bytes = canonical_source.read_bytes()
    patch_bytes = patch_path.read_bytes()
    validate_single_file_configuration_patch(patch_bytes, source_name)
    expected_shadow_sha = overlay.get("shadow_sha256")
    if not isinstance(expected_shadow_sha, str):
        raise PrelinkError("patched shadow configuration hash is missing")
    with tempfile.TemporaryDirectory(prefix="s10-config-hook-patch-") as temp_dir:
        target = Path(temp_dir) / source_name
        target.write_bytes(base_bytes)
        result = subprocess.run(
            [str(patch_executable), *patch_argv], cwd=temp_dir,
            input=patch_bytes, capture_output=True, shell=False,
            env=dict(environment), check=False)
        if result.returncode != 0:
            raise PrelinkError(f"pinned patch did not apply to canonical source: {source_name}")
        temporary_files = list(Path(temp_dir).iterdir())
        if temporary_files != [target]:
            raise PrelinkError("configuration patch wrote unplanned temporary files")
        reconstructed = target.read_bytes()
    shadow_bytes = shadow_source.read_bytes()
    if (sha256_bytes(reconstructed) != expected_shadow_sha
            or reconstructed != shadow_bytes
            or sha256_file(shadow_source) != expected_shadow_sha):
        raise PrelinkError(f"shadow configuration source differs from exact patched bytes: {source_name}")
    return {
        "canonical_sha256": base_sha,
        "patch_sha256": patch_sha,
        "shadow_sha256": expected_shadow_sha,
    }


def validate_configuration_sources(plan: dict[str, Any], *,
                                   canonical_host: Path,
                                   shadow_host: Path,
                                   workspace: Path | None = None,
                                   environment: Mapping[str, str] | None = None) -> dict[str, str]:
    """Require canonical config inputs and any sole reviewed shadow patch to match."""
    requirements = plan["prelink_requirements"]
    hashes = requirements["configuration_inputs_sha256"]
    overlays = requirements.get("shadow_configuration_source_patches", {})
    if not isinstance(overlays, dict):
        raise PrelinkError("shadow configuration patch map is malformed")
    if set(overlays) - {"apply_kdm6ad_config.sh"}:
        raise PrelinkError("only apply_kdm6ad_config.sh may have a shadow patch overlay")
    checked: dict[str, str] = {}
    for rel, expected in hashes.items():
        if sha256_file(canonical_host / rel) != expected:
            raise PrelinkError(f"private host configuration source changed: {rel}")
        overlay = overlays.get(rel)
        if overlay is None:
            if sha256_file(shadow_host / rel) != expected:
                raise PrelinkError(f"disposable shadow configuration source changed: {rel}")
            checked[rel] = expected
        else:
            if workspace is None:
                raise PrelinkError("workspace is required to verify the pinned shadow source patch")
            if environment is None:
                environment = planned_tool_environment(plan)
            verified = _verify_shadow_configuration_patch(
                plan, source_name=rel,
                canonical_source=canonical_host / rel,
                shadow_source=shadow_host / rel,
                workspace=workspace, environment=environment)
            checked[rel] = verified["shadow_sha256"]
    if set(overlays) - set(hashes):
        raise PrelinkError("shadow configuration patch names an unpinned source")
    return checked


def validate_static_pins(plan: dict[str, Any], *, workspace: Path,
                         canonical_host: Path, shadow_host: Path,
                         overlay_paths: dict[str, Path],
                         environment: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Rehash current canonical sources, local overlays, config, inputs, and archive."""
    configure_menu = validate_configure_menu_pin(plan)
    validate_configure_failure_markers(plan)
    environment = planned_tool_environment(plan) if environment is None else environment
    pins = plan["host_source_pins"]
    sources: dict[str, Any] = {}
    for scheme in ("mp37", "mp237"):
        item = pins[scheme]
        canonical = canonical_host / item["source_relative_to_private_host"]
        sources[scheme] = validate_source_overlay(
            item, scheme=scheme, canonical_source=canonical,
            overlay_path=overlay_paths[scheme])

    trusted_s15 = plan.get("trusted_s15_release", {})
    manifest_path = workspace / trusted_s15.get("evidence_manifest_path", "")
    if sha256_file(manifest_path) != trusted_s15.get("evidence_manifest_sha256"):
        raise PrelinkError("merged S15 evidence manifest hash differs from the public pin")
    step2_manifest_path = workspace / trusted_s15.get("s15_step2_evidence_manifest_path", "")
    if sha256_file(step2_manifest_path) != trusted_s15.get(
            "s15_step2_evidence_manifest_sha256"):
        raise PrelinkError("merged S15 step-two evidence manifest hash differs from the public pin")
    for merge, label in (
        (trusted_s15.get("s15_merge_commit"), "S15 B20s"),
        (trusted_s15.get("s15_step2_merge_commit"), "S15 step-two"),
    ):
        ancestry = subprocess.run(
            ["git", "-C", str(workspace), "merge-base", "--is-ancestor", str(merge), "HEAD"],
            capture_output=True, text=True)
        if ancestry.returncode != 0:
            raise PrelinkError(f"worktree HEAD does not contain the pinned {label} merge")

    archive_pin = plan["build_matrix"]["link_input_archive"]
    archive = (canonical_host / archive_pin["path_relative_to_private_host"]).resolve()
    if sha256_file(archive) != archive_pin["sha256"]:
        raise PrelinkError("canonical libwrflib.a hash changed")
    if (shadow_host / "main/libwrflib.a").exists():
        raise PrelinkError("shadow archive exists; link must use the pinned canonical archive")

    toolchain = validate_toolchain(plan, shadow_host, environment=environment)
    # A shadow-only configuration patch launches the pinned patch binary. Check
    # the complete plan-bound toolchain manifest before any such subprocess.
    validate_configuration_sources(
        plan, canonical_host=canonical_host, shadow_host=shadow_host,
        workspace=workspace, environment=environment)

    nml_rel = Path(plan["prelink_requirements"]["selected_case_relative_path"]) / "namelist.input"
    nml_path = shadow_host / nml_rel
    pristine_bytes = nml_path.read_bytes()
    pristine_sha = sha256_bytes(pristine_bytes)
    if pristine_sha != plan["prelink_requirements"]["pristine_namelist_sha256"]:
        raise PrelinkError("pristine namelist hash changed")
    pristine = pristine_bytes.decode("utf-8")
    active_inputs: dict[str, Any] = {}
    for scheme, mp in (("mp37", "37"), ("mp237", "237")):
        effective = _effective_namelist(pristine, mp)
        effective_sha = sha256_bytes(effective.encode())
        if effective_sha != plan["prelink_requirements"]["effective_namelist_sha256"][scheme]:
            raise PrelinkError(f"effective namelist hash changed for {scheme}")
        specs = resolve_active_namelist_inputs(effective)
        identity = hash_resolved_inputs(nml_path.parent, specs)
        if not identity.get("complete"):
            raise PrelinkError(f"active input identity is incomplete for {scheme}")
        rows = {r["name"]: r.get("sha256") for r in identity["records"]}
        if rows != plan["prelink_requirements"]["active_input_sha256"]:
            raise PrelinkError(f"active input set or hash changed for {scheme}: {rows}")
        if identity.get("canonical_sha256") != plan["prelink_requirements"]["active_input_canonical_sha256"]:
            raise PrelinkError(f"canonical active-input digest changed for {scheme}")
        active_inputs[scheme] = {
            "effective_namelist_sha256": effective_sha,
            "active_input_canonical_sha256": identity["canonical_sha256"],
            "active_input_sha256": rows,
        }
    if sha256_file(workspace / "harness/run_ss_case.py") != plan["prelink_requirements"]["runner_sha256"]:
        raise PrelinkError("native run runner hash changed")
    return {
        "sources": sources,
        "configure_menu": configure_menu,
        "canonical_archive_path": str(archive),
        "canonical_archive_sha256": archive_pin["sha256"],
        "toolchain": toolchain,
        "toolchain_sha256": plan["toolchain"]["toolchain_sha256"],
        "tool_environment": tool_environment_snapshot(environment),
        "tool_environment_sha256": plan["toolchain"]["environment_sha256"],
        "pristine_namelist_sha256": pristine_sha,
        "active_inputs": active_inputs,
    }


def validate_clean_shadow(shadow_host: Path, output_root: Path, workspace: Path) -> None:
    if (shadow_host / "main/wrf.exe").exists():
        raise PrelinkError("stale shadow main/wrf.exe exists")
    if (shadow_host / "main/libwrflib.a").exists():
        raise PrelinkError("shadow libwrflib.a exists")
    stale_rsl = list(shadow_host.glob("rsl.*"))
    if stale_rsl:
        raise PrelinkError(f"stale root-level rsl log remains in shadow: {stale_rsl[0]}")
    stale_objects = [p for pattern in ("*.o", "*.mod", "*.smod")
                     for p in shadow_host.rglob(pattern)]
    if stale_objects:
        raise PrelinkError(f"stale object/module file remains in shadow: {stale_objects[0]}")
    generated_fortran = [p for p in shadow_host.rglob("*.f90")
                         if p.with_suffix(".F").exists()]
    if generated_fortran:
        raise PrelinkError(f"stale generated Fortran remains in shadow: {generated_fortran[0]}")
    # All build logs belong under the dedicated output root, never in the source tree.
    root_logs = [p for p in shadow_host.rglob("*.log")
                 if "external" not in p.relative_to(shadow_host).parts
                 and "var" not in p.relative_to(shadow_host).parts]
    if root_logs:
        raise PrelinkError(f"historical or redirected build logs remain in shadow: {root_logs[0]}")
    try:
        output_root.resolve().relative_to(workspace.resolve())
    except ValueError as exc:
        raise PrelinkError("dedicated build output root is outside the S10 worktree") from exc


def require_fresh_output_root(output_root: Path) -> None:
    if output_root.is_symlink():
        raise PrelinkError("fresh build output root must not be a symlink")
    if output_root.exists() and (not output_root.is_dir() or any(output_root.iterdir())):
        raise PrelinkError("fresh build output root must be absent or empty before preparation")


def validate_output_inventory(output_root: Path, inventory: list[dict[str, Any]],
                              workspace: Path) -> None:
    if not output_root.is_dir():
        raise PrelinkError("dedicated build output root is missing")
    expected: dict[Path, str] = {}
    if not isinstance(inventory, list):
        raise PrelinkError("complete build output inventory is missing")
    for row in inventory:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise PrelinkError("malformed build output inventory row")
        path = Path(row["path"])
        if not path.is_absolute():
            path = workspace / path
        if path.is_symlink():
            raise PrelinkError(f"build output inventory includes a symlink: {path}")
        path = path.resolve()
        try:
            path.relative_to(output_root.resolve())
        except ValueError as exc:
            raise PrelinkError(f"build output escaped its dedicated directory: {path}") from exc
        if path in expected or not isinstance(row.get("sha256"), str):
            raise PrelinkError(f"duplicate or unhashed build output: {path}")
        expected[path] = row["sha256"]
    actual: set[Path] = set()
    for path in output_root.rglob("*"):
        if path.is_symlink():
            raise PrelinkError(f"build output directory contains a symlink: {path}")
        if path.is_file():
            actual.add(path.resolve())
    if actual != set(expected):
        extra = sorted(str(path) for path in actual - set(expected))
        missing = sorted(str(path) for path in set(expected) - actual)
        raise PrelinkError(f"build output inventory differs (extra={extra[:2]}, missing={missing[:2]})")
    for path, digest in expected.items():
        if sha256_file(path) != digest:
            raise PrelinkError(f"build output hash mismatch: {path}")


def validate_archive_link(link_argv: list[str], *, archive_path: Path,
                          expected_sha256: str, recorded_path: str,
                          recorded_sha256: str) -> None:
    exact_path = str(archive_path.resolve())
    if recorded_path != exact_path:
        raise PrelinkError("link receipt archive path is not the pinned canonical archive")
    if recorded_sha256 != expected_sha256:
        raise PrelinkError("link receipt archive hash does not match the pinned archive")
    if link_argv.count(exact_path) != 1:
        raise PrelinkError("link argv must name the pinned canonical archive exactly once")
    if sha256_file(archive_path) != expected_sha256:
        raise PrelinkError("canonical archive changed immediately before link")


def _command(record: dict[str, Any], label: str) -> tuple[list[str], list[str]]:
    argv = record.get("argv")
    flags = record.get("flags")
    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x for x in argv):
        raise PrelinkError(f"{label} argv is missing or malformed")
    if not isinstance(flags, list) or not all(isinstance(x, str) for x in flags):
        raise PrelinkError(f"{label} flags are missing or malformed")
    if flags != _argv_option_tokens(argv):
        raise PrelinkError(f"{label} flag metadata is not an exhaustive record of argv options")
    return argv, flags


_OPTIONS_WITH_VALUE = {
    "-B", "-D", "-I", "-J", "-L", "-MF", "-MT", "-U", "-Xlinker",
    "-include", "-isysroot", "-isystem", "-o", "-x",
}


def _argv_option_tokens(argv: list[str]) -> list[str]:
    result: list[str] = []
    i = 1
    while i < len(argv):
        token = argv[i]
        if token.startswith("-"):
            result.append(token)
            if token in _OPTIONS_WITH_VALUE:
                if i + 1 >= len(argv):
                    raise PrelinkError(f"option lacks its argument: {token}")
                result.append(argv[i + 1])
                i += 1
        i += 1
    return result


def _macro_ops(argv: list[str]) -> tuple[list[tuple[str, str | None]], list[str]]:
    definitions: list[tuple[str, str | None]] = []
    undefinitions: list[str] = []
    i = 1
    while i < len(argv):
        token = argv[i]
        action = None
        body = ""
        if token in ("-D", "-U"):
            action = token[1]
            if i + 1 >= len(argv):
                raise PrelinkError(f"macro option lacks a name: {token}")
            body = argv[i + 1]
            i += 1
        elif token.startswith("-D") and len(token) > 2:
            action, body = "D", token[2:]
        elif token.startswith("-U") and len(token) > 2:
            action, body = "U", token[2:]
        if action:
            name, sep, value = body.partition("=")
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                raise PrelinkError(f"malformed macro option: {token} {body}")
            if action == "D":
                definitions.append((name, value if sep else None))
            else:
                undefinitions.append(name)
        i += 1
    return definitions, undefinitions


def _validate_macro_guard(commands: list[dict[str, Any]], arm: str, key: str) -> None:
    definitions: list[tuple[str, str | None, str]] = []
    undefinitions: list[tuple[str, str]] = []
    for row in commands:
        argv, _ = _command(row, f"{key} {row.get('stage', 'command')}")
        defs, undefs = _macro_ops(argv)
        definitions.extend((name, value, str(row.get("stage"))) for name, value in defs)
        undefinitions.extend((name, str(row.get("stage"))) for name in undefs)
    guard_defs = [rec for rec in definitions if rec[0] == ZERO_QG_MACRO]
    guard_undefs = [rec for rec in undefinitions if rec[0] == ZERO_QG_MACRO]
    if guard_undefs:
        raise PrelinkError(f"{key} uses -U for the guard macro")
    if arm == "B" and guard_defs:
        raise PrelinkError(f"{key} B preprocessing defines guard macro, including a zero-valued -D")
    if arm == "C" and guard_defs != [(ZERO_QG_MACRO, None, "wrf_cpp")]:
        raise PrelinkError(f"{key} C preprocessing must define the bare guard macro exactly once in wrf_cpp")
    required = {"KDM6_PROGB_VALIDITY_CAPTURE", "KDM6_PROGB_POLICY_MIDPOINT"}
    present = {name for name, _value, _stage in definitions}
    if not required.issubset(present):
        raise PrelinkError(f"{key} preprocessing omits capture or midpoint policy macro")


def _resolve_tool(plan: dict[str, Any], name: str, shadow_host: Path) -> dict[str, str]:
    spec = plan["toolchain"]["tools"][name]
    path = (Path(spec["path"]) if "path" in spec else
            (shadow_host / spec["path_relative_to_shadow_host"]).resolve())
    digest = sha256_file(path)
    if digest != spec["sha256"]:
        raise PrelinkError(f"pinned tool binary changed: {name} ({path})")
    return {"path": str(path), "sha256": digest}


def _response_file_refs(argv: list[str]) -> list[str]:
    """Find response files, allowing install-name tokens only as rpath values."""
    def is_install_name(token: str) -> bool:
        return any(token == prefix or token.startswith(prefix + "/")
                   for prefix in ("@rpath", "@loader_path", "@executable_path"))

    def is_response(token: str) -> bool:
        return token.startswith("@") and not is_install_name(token)

    found: list[str] = []
    previous_xlinker_arg: str | None = None
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == "-Xlinker" and i + 1 < len(argv):
            value = argv[i + 1]
            if is_response(value) or (value.startswith("@") and not
                                      (previous_xlinker_arg in ("-rpath", "--rpath")
                                       and is_install_name(value))):
                found.append(value)
            previous_xlinker_arg = value
            i += 2
            continue
        if token.startswith("-Wl,"):
            parts = token[4:].split(",")
            for index, part in enumerate(parts):
                if part.startswith("@"):
                    prior_is_rpath = index > 0 and parts[index - 1] in ("-rpath", "--rpath")
                    if is_response(part) or not (prior_is_rpath and is_install_name(part)):
                        found.append(part)
                elif part.startswith(("-rpath=", "--rpath=")):
                    value = part.split("=", 1)[1]
                    if value.startswith("@") and not is_install_name(value):
                        found.append(value)
            previous_xlinker_arg = None
            i += 1
            continue
        if token.startswith("@"):
            found.append(token)
        previous_xlinker_arg = None
        i += 1
    return found


def _validate_linker_forwarding(argv: list[str], label: str) -> None:
    """Allow only explicit Mach-O rpath forwarding; ban other -Wl escapes."""
    for token in argv:
        if not token.startswith("-Wl,"):
            continue
        parts = token[4:].split(",")
        index = 0
        while index < len(parts):
            option = parts[index]
            if option in ("-rpath", "--rpath"):
                if index + 1 >= len(parts):
                    raise PrelinkError(f"{label} forwarded rpath has no value")
                value = parts[index + 1]
                if not (value.startswith("/") or value.startswith(("@loader_path", "@rpath", "@executable_path"))):
                    raise PrelinkError(f"{label} forwarded rpath value is not an absolute/install path")
                index += 2
                continue
            if option.startswith(("-rpath=", "--rpath=")):
                value = option.split("=", 1)[1]
                if not (value.startswith("/") or value.startswith(("@loader_path", "@rpath", "@executable_path"))):
                    raise PrelinkError(f"{label} forwarded rpath value is not an absolute/install path")
                index += 1
                continue
            raise PrelinkError(f"{label} uses an unreviewed -Wl option: {option}")


def _validate_tool_command(record: dict[str, Any], *, expected_name: str,
                           plan: dict[str, Any], shadow_host: Path,
                           output_root: Path, label: str,
                           cwd_root: Path | None = None,
                           capture_root: Path | None = None) -> tuple[list[str], list[str]]:
    argv, flags = _command(record, label)
    response_files = _response_file_refs(argv)
    if response_files:
        raise PrelinkError(f"{label} response-file references are forbidden: {response_files[0]}")
    _validate_linker_forwarding(argv, label)
    forwarded_options = [token for token in argv
                         if token in ("-Wp", "-Xpreprocessor", "-Xclang",
                                      "-Xassembler", "-Xlinker")
                         or token.startswith(("-Wp,", "-Wp=", "-Xpreprocessor=",
                                              "-Xclang=", "-Xassembler=", "-Xlinker="))]
    if forwarded_options:
        raise PrelinkError(
            f"{label} forwarded compiler/linker options are forbidden: {forwarded_options[0]}"
        )
    tool = _resolve_tool(plan, expected_name, shadow_host)
    if (record.get("tool_name") != expected_name
            or record.get("tool_path") != tool["path"]
            or record.get("tool_sha256") != tool["sha256"]
            or argv[0] != tool["path"]):
        raise PrelinkError(f"{label} uses an alternate or unpinned tool binary")
    if record.get("shell") is not False:
        raise PrelinkError(f"{label} must be invoked without a shell")
    cwd = Path(record.get("cwd", ""))
    if not cwd.is_absolute():
        raise PrelinkError(f"{label} cwd must be absolute")
    try:
        cwd.resolve().relative_to((cwd_root or output_root).resolve())
    except ValueError as exc:
        raise PrelinkError(f"{label} cwd is outside the disposable output root") from exc
    for capture_field in ("stdout_path", "stderr_path"):
        capture_value = record.get(capture_field)
        if not isinstance(capture_value, str) or not capture_value:
            raise PrelinkError(f"{label} must record {capture_field} under the disposable root")
        capture = Path(capture_value)
        if not capture.is_absolute():
            capture = output_root / capture
        capture_path = capture.resolve()
        allowed_roots = [output_root.resolve()]
        if capture_root is not None:
            allowed_roots.append(capture_root.resolve())
        if not any(_is_relative_to(capture_path, root) for root in allowed_roots):
            raise PrelinkError(f"{label} {capture_field} escaped the disposable output root")
        if not capture.is_file():
            raise PrelinkError(f"{label} {capture_field} file is missing: {capture}")
    forbidden = {"-Ofast", "-ffast-math", "-ffp-contract=fast", "-ffp-contract=on"}
    if forbidden.intersection(argv):
        raise PrelinkError(f"{label} contains a forbidden non-legacy floating-point option")
    if "-i" in argv or "--in-place" in argv:
        raise PrelinkError(f"{label} may not edit an input file in place")
    if any(token == "-include" or token.startswith("-include")
           or token == "-imacros" or token.startswith("-imacros") for token in argv):
        raise PrelinkError(f"{label} may not inject unpinned macro/include files")
    return argv, flags


def _ensure_output_target(argv: list[str], *, expected: Path | None,
                          output_root: Path, require_output: bool, label: str,
                          arm_root: Path | None = None,
                          expected_module_dir: Path | None = None,
                          expected_depfile: Path | None = None) -> None:
    target_root = (arm_root or output_root).resolve()
    out_indices = [i for i, token in enumerate(argv) if token == "-o"]
    long_indices = [i for i, token in enumerate(argv)
                    if token == "--output" or token.startswith("--output=")]
    linker_outputs = [token for token in argv if token.startswith("-Wl,") and any(
        part == "-o" or part.startswith("-o") or part == "--output"
        or part.startswith("--output=") for part in token[4:].split(","))]
    xlinker_outputs = [i for i in range(len(argv) - 1)
                       if argv[i] == "-Xlinker" and argv[i + 1] in ("-o", "--output")]
    compact_outputs = [token for token in argv if token.startswith("-o") and token != "-o"
                       and not token.startswith("-O")]
    def is_map_option(token: str) -> bool:
        lowered = token.lower()
        return (lowered in ("-map", "--map")
                or lowered.startswith(("-map=", "--map=")))

    map_option = any(is_map_option(token) for token in argv)
    for index, token in enumerate(argv):
        if token.startswith("-Wl,"):
            map_option = map_option or any(is_map_option(part)
                                           for part in token[4:].split(","))
        if token == "-Xlinker" and index + 1 < len(argv):
            map_option = map_option or is_map_option(argv[index + 1])
    if map_option:
        raise PrelinkError(f"{label} linker map output options are forbidden")
    if len(out_indices) > 1 or long_indices or linker_outputs or xlinker_outputs or compact_outputs:
        raise PrelinkError(f"{label} has a duplicate or alternate output option")
    if (require_output and len(out_indices) != 1) or (not require_output and len(out_indices) > 1):
        raise PrelinkError(f"{label} must have exactly one -o output option")
    if out_indices:
        index = out_indices[0]
        if index + 1 >= len(argv):
            raise PrelinkError(f"{label} -o lacks an output path")
        target = Path(argv[index + 1])
        if not target.is_absolute() or expected is None or target.resolve() != expected.resolve():
            raise PrelinkError(f"{label} -o target differs from its planned output")
        try:
            target.resolve().relative_to(target_root)
        except ValueError as exc:
            raise PrelinkError(f"{label} output target escaped its arm directory") from exc

    def path_options(option: str) -> list[Path]:
        paths: list[Path] = []
        i = 0
        while i < len(argv):
            token = argv[i]
            raw: str | None = None
            if token == option:
                if i + 1 >= len(argv):
                    raise PrelinkError(f"{label} {option} lacks its output path")
                raw = argv[i + 1]
                i += 1
            elif token.startswith(option + "="):
                raw = token[len(option) + 1:]
            elif token.startswith(option) and len(token) > len(option):
                raw = token[len(option):]
            if raw is not None:
                path = Path(raw)
                if not raw or not path.is_absolute():
                    raise PrelinkError(f"{label} {option} output path must be absolute")
                try:
                    path.resolve().relative_to(target_root)
                except ValueError as exc:
                    raise PrelinkError(f"{label} {option} output escaped its arm directory") from exc
                paths.append(path.resolve())
            i += 1
        return paths

    module_dirs = path_options("-J")
    depfiles = path_options("-MF")
    if len(module_dirs) > 1:
        raise PrelinkError(f"{label} has duplicate -J module destinations")
    if len(depfiles) > 1:
        raise PrelinkError(f"{label} has duplicate -MF dependency destinations")
    if expected_module_dir is None and module_dirs:
        raise PrelinkError(f"{label} has an unplanned -J module destination")
    if expected_module_dir is not None and module_dirs != [expected_module_dir.resolve()]:
        raise PrelinkError(f"{label} -J destination is not the planned arm module directory")
    if expected_depfile is None and depfiles:
        raise PrelinkError(f"{label} has an unplanned -MF dependency destination")
    if expected_depfile is not None and depfiles != [expected_depfile.resolve()]:
        raise PrelinkError(f"{label} -MF destination is not the planned arm dependency file")


def _strip_guard_define(argv: list[str]) -> list[str]:
    result: list[str] = []
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == "-D" and i + 1 < len(argv) and argv[i + 1] == ZERO_QG_MACRO:
            i += 2
            continue
        if token == f"-D{ZERO_QG_MACRO}":
            i += 1
            continue
        result.append(token)
        i += 1
    return result


def _normalize_value(value: str | None, arm_root: Path) -> str | None:
    if value is None:
        return None
    return value.replace(str(arm_root.resolve()), "<S10_ARM_OUTPUT>")


def _command_signature(record: dict[str, Any], arm_root: Path, *,
                       strip_guard: bool = False) -> dict[str, Any]:
    argv = list(record["argv"])
    if strip_guard:
        argv = _strip_guard_define(argv)
    return {
        "stage": record.get("stage"),
        "tool_name": record.get("tool_name"),
        "tool_path": _normalize_value(record.get("tool_path"), arm_root),
        "tool_sha256": record.get("tool_sha256"),
        "argv": [_normalize_value(token, arm_root) for token in argv],
        "cwd": _normalize_value(record.get("cwd"), arm_root),
        "stdout_path": _normalize_value(record.get("stdout_path"), arm_root),
        "stderr_path": _normalize_value(record.get("stderr_path"), arm_root),
        "shell": record.get("shell"),
    }


def validate_normalized_command_pair(b_record: dict[str, Any], c_record: dict[str, Any], *,
                                     b_root: Path, c_root: Path,
                                     strip_guard: bool = False,
                                     label: str = "command") -> dict[str, Any]:
    b_signature = _command_signature(b_record, b_root)
    c_signature = _command_signature(c_record, c_root, strip_guard=strip_guard)
    if b_signature != c_signature:
        raise PrelinkError(f"B/C {label} argv differs beyond guard and arm output paths")
    return b_signature


def _configuration_command_signature(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "stage": record.get("stage"),
        "tool_name": record.get("tool_name"),
        "tool_path": record.get("tool_path"),
        "tool_sha256": record.get("tool_sha256"),
        "argv": record.get("argv"),
        "flags": record.get("flags"),
        "cwd": record.get("cwd"),
        "environment_sha256": record.get("environment_sha256"),
        "stdout_path": record.get("stdout_path"),
        "stdout_sha256": record.get("stdout_sha256"),
        "stderr_path": record.get("stderr_path"),
        "stderr_sha256": record.get("stderr_sha256"),
        "stdin_path": record.get("stdin_path"),
        "stdin_sha256": record.get("stdin_sha256"),
        "script_sha256": record.get("script_sha256"),
        "canonical_script_sha256": record.get("canonical_script_sha256"),
        "script_patch_sha256": record.get("script_patch_sha256"),
        "returncode": record.get("returncode"),
        "shell": record.get("shell"),
        "netcdf_tool_probes": record.get("netcdf_tool_probes"),
        "configure_wrf_sha256_after": record.get("configure_wrf_sha256_after"),
        "output_root_absent_before": record.get("output_root_absent_before"),
        "output_root_absent_after": record.get("output_root_absent_after"),
    }


def _validate_configuration_ledger(execution: dict[str, Any], plan: dict[str, Any], *,
                                   workspace: Path, plan_sha256: str,
                                   configure_sha256: str) -> None:
    ledger_rel = plan["prelink_requirements"].get(
        "configuration_execution_ledger_relative_path")
    if ledger_rel is None:
        return
    ledger_path = workspace / ledger_rel
    recorded_sha = execution.get("configuration_command_ledger_sha256")
    expected_ledger_sha = plan["prelink_requirements"].get(
        "configuration_execution_ledger_sha256")
    ledger, ledger_sha = read_hashed_json(ledger_path)
    if (not isinstance(expected_ledger_sha, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_ledger_sha)
            or recorded_sha != expected_ledger_sha
            or ledger_sha != recorded_sha):
        raise PrelinkError("configuration execution ledger is missing or differs from its final plan pin")
    ledger_nonce = ledger.get("nonce")
    if (ledger.get("schema") != "s10-guarded-configuration-ledger-v1"
            or ledger.get("plan_sha256") != plan_sha256
            or ledger.get("status") != "COMPLETE"
            or ledger.get("toolchain_sha256") != plan["toolchain"]["toolchain_sha256"]
            or ledger.get("tool_environment_sha256") != plan["toolchain"]["environment_sha256"]
            or not isinstance(ledger_nonce, str)
            or not re.fullmatch(r"[0-9a-f]{64}", ledger_nonce)
            or ledger.get("nonce_sha256") != sha256_bytes(ledger_nonce.encode())):
        raise PrelinkError("configuration execution ledger is not complete or plan-bound")
    recorded_ledger_path = execution.get("configuration_command_ledger_path")
    if Path(recorded_ledger_path or "").resolve() != ledger_path.resolve():
        raise PrelinkError("execution receipt ledger path differs from the plan-pinned path")
    expected_snapshot = plan["trusted_s15_release"]["empty_output_root_snapshot_sha256"]
    if ledger.get("empty_output_root_snapshot_sha256") != expected_snapshot:
        raise PrelinkError("configuration execution ledger is bound to a different snapshot")
    expected_commands = execution.get("configuration_commands")
    commands = ledger.get("commands")
    if not isinstance(commands, list) or not isinstance(expected_commands, list) \
            or len(commands) != 2 or len(expected_commands) != 2:
        raise PrelinkError("configuration ledger must record configure then apply")
    for recorded, expected in zip(commands, expected_commands):
        if (_configuration_command_signature(recorded)
                != _configuration_command_signature(expected)):
            raise PrelinkError("configuration execution receipt differs from guarded-command ledger")
        if (recorded.get("output_root_absent_before") is not True
                or recorded.get("output_root_absent_after") is not True):
            raise PrelinkError("configure-only command touched the WRF build output root")
        for output_name, digest_name in (("stdout_path", "stdout_sha256"),
                                         ("stderr_path", "stderr_sha256")):
            if sha256_file(Path(recorded[output_name])) != recorded.get(digest_name):
                raise PrelinkError(f"guarded configuration {output_name} hash differs")
    if commands[-1].get("configure_wrf_sha256_after") != configure_sha256:
        raise PrelinkError("configuration ledger final configure.wrf hash differs")
    expected_preflight_sha = execution.get("configuration_resource_preflight_receipt_sha256")
    if ledger.get("configure_resource_preflight_receipt_sha256") != expected_preflight_sha:
        raise PrelinkError("configuration ledger is not bound to its configure-only preflight receipt")
    preflight_path = workspace / plan["resource_gate"]["configure_only"][
        "preflight_receipt_relative_path"]
    if not isinstance(expected_preflight_sha, str):
        raise PrelinkError("configure-only resource preflight receipt digest is missing or changed")
    preflight, actual_preflight_sha = read_hashed_json(preflight_path)
    if actual_preflight_sha != expected_preflight_sha:
        raise PrelinkError("configure-only resource preflight receipt digest is missing or changed")
    if (preflight.get("schema") != "s10-resource-preflight-receipt-v1"
            or preflight.get("phase") != "configure"
            or preflight.get("status") != "ALLOW_CONFIGURE_ONLY"
            or preflight.get("plan_sha256") != plan_sha256
            or preflight.get("toolchain_sha256") != plan["toolchain"]["toolchain_sha256"]
            or preflight.get("tool_environment_sha256") != plan["toolchain"]["environment_sha256"]
            or preflight.get("empty_output_root_snapshot_sha256") != expected_snapshot
            or preflight.get("output_root_path") != ledger.get("output_root_path")
            or preflight.get("allowed_commands") != ["./configure", "./apply_kdm6ad_config.sh"]):
        raise PrelinkError("configure-only resource preflight receipt is not plan-bound")


def _validate_netcdf_config_probes(
        configure_record: dict[str, Any], plan: dict[str, Any],
        shadow_host: Path) -> None:
    policy = plan["prelink_requirements"].get("netcdf_config_invocation_policy")
    if not isinstance(policy, dict):
        return
    expected_tools = policy.get("invocations")
    if not isinstance(expected_tools, dict) or set(expected_tools) != {"nc-config", "nf-config"}:
        raise PrelinkError("pinned NetCDF config-tool invocation policy is incomplete")
    recorded = configure_record.get("netcdf_tool_probes")
    if not isinstance(recorded, dict) or set(recorded) != set(expected_tools):
        raise PrelinkError("configure receipt lacks the resolved NetCDF tool invocations")
    observed_output = ""
    for name, expected in expected_tools.items():
        tool_path = Path(expected["path"]).resolve()
        tool_sha = sha256_file(tool_path)
        if tool_sha != expected.get("sha256"):
            raise PrelinkError(f"pinned NetCDF config tool changed: {name}")
        if "/opt/local/" in str(tool_path):
            raise PrelinkError(f"mixed MacPorts NetCDF config tool is forbidden: {name}")
        row = recorded[name]
        if (not isinstance(row, dict)
                or row.get("probe_scope") != "post_config_pinned_tool_probes"
                or row.get("path") != str(tool_path)
                or row.get("sha256") != tool_sha
                or row.get("version") != expected.get("version")):
            raise PrelinkError(f"resolved NetCDF config tool identity mismatch: {name}")
        argv_outputs = expected.get("argv_outputs")
        commands = row.get("commands")
        if not isinstance(argv_outputs, dict) or not isinstance(commands, list):
            raise PrelinkError(f"NetCDF config invocation receipt is malformed: {name}")
        if len(commands) != len(argv_outputs):
            raise PrelinkError(f"NetCDF config invocation count differs from its pin: {name}")
        for invocation, (arguments, expected_stdout) in zip(commands, argv_outputs.items()):
            argv = [arguments]
            if (not isinstance(invocation, dict) or invocation.get("argv") != argv
                    or invocation.get("returncode") != 0):
                raise PrelinkError(f"NetCDF config argv differs from its pin: {name}")
            result = subprocess.run(
                [str(tool_path), *argv], check=True, capture_output=True,
                text=True, shell=False)
            stdout, stderr = result.stdout.strip(), result.stderr.strip()
            if (stdout != expected_stdout or invocation.get("stdout") != stdout
                    or invocation.get("stderr") != stderr):
                raise PrelinkError(f"NetCDF config output differs from its pinned invocation: {name}")
            observed_output += stdout + "\n" + stderr + "\n"
    forbidden = policy.get("forbidden_mixed_prefixes", [])
    if any(prefix and prefix in observed_output for prefix in forbidden):
        raise PrelinkError("NetCDF config invocation output mixes package prefixes")
    cfg_path = shadow_host / "configure.wrf"
    cfg_text = cfg_path.read_text(encoding="utf-8")
    for prefix in forbidden:
        if prefix and prefix in cfg_text:
            raise PrelinkError("generated configure.wrf mixes the forbidden NetCDF prefix")
    netcdf_root = policy["environment"]["NETCDF"]
    if f"NETCDFPATH      =    {netcdf_root}" not in cfg_text:
        raise PrelinkError("generated configure.wrf does not use the pinned NetCDF root")


def validate_arm_argv_parity(plan: dict[str, Any], execution: dict[str, Any], *,
                             workspace: Path) -> str:
    variants = execution["variants"]
    config_commands = execution.get("configuration_commands")
    if not isinstance(config_commands, list) or len(config_commands) != 2:
        raise PrelinkError("normalized argv digest requires both configure command records")
    payload: dict[str, Any] = {
        "configuration": [_configuration_command_signature(row) for row in config_commands],
        "configure_wrf_sha256": execution.get("configure_wrf_sha256"),
        "toolchain_sha256": execution.get("toolchain_sha256"),
        "environment_sha256": sha256_bytes(json.dumps(
            execution.get("tool_environment"), sort_keys=True,
            separators=(",", ":")).encode()),
        "resource_preflight_receipt_sha256": execution.get(
            "resource_preflight_receipt_sha256"),
    }
    for scheme in ("mp37", "mp237"):
        b, c = variants[f"{scheme}_B"], variants[f"{scheme}_C"]
        b_root = workspace / "S10/build-clean" / scheme / "B"
        c_root = workspace / "S10/build-clean" / scheme / "C"
        bpp, cpp = b["preprocess"]["commands"], c["preprocess"]["commands"]
        if len(bpp) != len(cpp):
            raise PrelinkError(f"{scheme} B/C preprocessing command counts differ")
        validate_preprocess_macro_delta(
            next(row["argv"] for row in bpp if row.get("stage") == "wrf_cpp"),
            next(row["argv"] for row in cpp if row.get("stage") == "wrf_cpp"),
        )
        for stage, (bcmd, ccmd) in enumerate(zip(bpp, cpp)):
            b_signature = validate_normalized_command_pair(
                bcmd, ccmd, b_root=b_root, c_root=c_root,
                strip_guard=bcmd.get("stage") == "wrf_cpp",
                label=f"{scheme} preprocessing stage {stage}")
            payload[f"{scheme}_preprocess_{stage}"] = b_signature
        for phase in ("object", "link"):
            b_signature = validate_normalized_command_pair(
                b[phase], c[phase], b_root=b_root, c_root=c_root,
                label=f"{scheme} {phase}")
            payload[f"{scheme}_{phase}"] = b_signature
    digest = sha256_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
    expected = plan["build_matrix"].get("normalized_argv_sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        raise PrelinkError("normalized WRF preprocess/object/link argv SHA-256 is not independently pinned")
    if digest != expected:
        raise PrelinkError("normalized WRF preprocess/object/link argv differs from reviewed pin")
    return digest


def _validate_configure_pipeline(execution: dict[str, Any], shadow_host: Path,
                                 output_root: Path, plan: dict[str, Any],
                                 configure_sha: str, *,
                                 plan_sha256: str | None = None,
                                 workspace: Path | None = None) -> None:
    validate_configure_failure_markers(plan)
    commands = execution.get("configuration_commands")
    if not isinstance(commands, list) or [r.get("stage") for r in commands if isinstance(r, dict)] != [
        "configure", "apply_kdm6ad_config"
    ]:
        raise PrelinkError("fresh configuration must record ./configure then ./apply_kdm6ad_config.sh")
    first, second = commands
    script_hashes = plan["prelink_requirements"]["configuration_inputs_sha256"]
    expected_argv = {
        "configure": plan["prelink_requirements"].get("configuration_generation_command"),
        "apply_kdm6ad_config": plan["prelink_requirements"].get("configuration_apply_command"),
    }
    expected_stdin = {
        "configure": plan["prelink_requirements"].get("configure_selection_stdin_sha256"),
        "apply_kdm6ad_config": plan["prelink_requirements"].get("configuration_apply_stdin_sha256"),
    }
    capture_root = shadow_host.parent.parent / "configuration_capture"
    stdin_capture_paths = plan["prelink_requirements"].get(
        "configuration_stdin_capture_paths")
    for stage, row, script_name in (
        ("configure", first, "configure"),
        ("apply_kdm6ad_config", second, "apply_kdm6ad_config.sh"),
    ):
        argv, _ = _validate_tool_command(
            row, expected_name="bash", plan=plan, shadow_host=shadow_host,
            output_root=output_root, cwd_root=shadow_host,
            capture_root=capture_root,
            label=f"configuration {stage}")
        if row.get("returncode") != 0:
            raise PrelinkError(f"configuration stage {stage} did not complete successfully")
        expected = expected_argv[stage]
        if not isinstance(expected, list) or argv != expected:
            raise PrelinkError(f"configuration stage {stage} argv differs from the plan pin")
        expected_input_sha = expected_stdin[stage]
        if (not isinstance(expected_input_sha, str) or len(expected_input_sha) != 64
                or row.get("stdin_sha256") != expected_input_sha):
            raise PrelinkError(f"configuration stage {stage} stdin/options are not plan-pinned")
        if isinstance(stdin_capture_paths, dict):
            capture_name = stdin_capture_paths.get(stage)
            expected_capture = (shadow_host.parent.parent / capture_name).resolve()
            stdin_path = Path(row.get("stdin_path", "")).resolve()
            if stdin_path != expected_capture or sha256_file(stdin_path) != expected_input_sha:
                raise PrelinkError(f"configuration stage {stage} stdin capture differs from its exact pin")
        expected_shadow_sha = expected_configuration_source_sha256(
            plan, script_name, shadow=True)
        patch_record = plan["prelink_requirements"].get(
            "shadow_configuration_source_patches", {}).get(script_name)
        expected_patch_sha = patch_record.get("patch_sha256") if isinstance(patch_record, dict) else None
        if (row.get("script_sha256") != expected_shadow_sha
                or row.get("canonical_script_sha256") != script_hashes[script_name]
                or row.get("script_patch_sha256") != expected_patch_sha):
            raise PrelinkError(f"configuration stage {stage} script hash mismatch")
        if sha256_file(shadow_host / script_name) != expected_shadow_sha:
            raise PrelinkError(f"configuration stage {stage} shadow script changed")
        _ensure_output_target(argv, expected=None, output_root=output_root,
                              require_output=False, label=f"configuration {stage}")
        for capture_field in ("stdout_path", "stderr_path"):
            capture_path = row.get(capture_field)
            if capture_path:
                capture = Path(capture_path)
                if not capture.is_absolute():
                    capture = output_root / capture
                if not (_is_relative_to(capture.resolve(), output_root.resolve())
                        or _is_relative_to(capture.resolve(), capture_root.resolve())):
                    raise PrelinkError(f"configuration {stage} {capture_field} escaped output root")
                hash_field = f"{capture_field.removesuffix('_path')}_sha256"
                if sha256_file(capture) != row.get(hash_field):
                    raise PrelinkError(f"configuration {stage} {capture_field} hash mismatch")
    configure_stdout_path = Path(first["stdout_path"])
    if not configure_stdout_path.is_absolute():
        configure_stdout_path = output_root / configure_stdout_path
    validate_configure_success_stdout(
        configure_stdout_path.read_text(encoding="utf-8"))
    expected_configure_sha = plan["prelink_requirements"].get("generated_configure_wrf_sha256")
    if not isinstance(expected_configure_sha, str) or len(expected_configure_sha) != 64:
        raise PrelinkError("fresh configure.wrf SHA-256 is not independently pinned in the plan")
    if configure_sha != expected_configure_sha or sha256_file(shadow_host / "configure.wrf") != expected_configure_sha:
        raise PrelinkError("fresh configure.wrf differs from the reviewed plan pin")
    if plan.get("prelink_requirements", {}).get("configuration_execution_ledger_relative_path"):
        if plan_sha256 is None or workspace is None:
            raise PrelinkError("guarded configuration ledger requires workspace and plan digest")
        _validate_configuration_ledger(
            execution, plan, workspace=workspace,
            plan_sha256=plan_sha256, configure_sha256=configure_sha)
    netcdf_policy = plan["prelink_requirements"].get("netcdf_config_invocation_policy")
    if isinstance(netcdf_policy, dict):
        _validate_netcdf_config_probes(first, plan, shadow_host)
        stdout_path = Path(first["stdout_path"])
        if not stdout_path.is_absolute():
            stdout_path = output_root / stdout_path
        configure_stdout = stdout_path.read_text(encoding="utf-8")
        netcdf_root = netcdf_policy["environment"]["NETCDF"]
        if f"Will use NETCDF in dir: {netcdf_root}" not in configure_stdout:
            raise PrelinkError("configure output does not confirm the pinned NETCDF root")
        for marker in netcdf_policy.get("configure_log_assertions", []):
            if marker not in configure_stdout:
                raise PrelinkError(f"configure output omits pinned NetCDF report: {marker}")


def _validate_preprocess_pipeline(pp: dict[str, Any], *, key: str,
                                  overlay: Path, output_root: Path,
                                  expected_output: Path, plan: dict[str, Any],
                                  shadow_host: Path, workspace: Path) -> tuple[list[str], Path]:
    commands = pp.get("commands")
    stages = ["comment_cleanup", "wrf_cpp", "standard", "final_cpp"]
    if not isinstance(commands, list) or [r.get("stage") for r in commands if isinstance(r, dict)] != stages:
        raise PrelinkError(f"{key} must record all four WRF preprocessing commands")
    previous_sha = sha256_file(overlay)
    final_output: Path | None = None
    macro_argv: list[str] = []
    tool_for_stage = {
        "comment_cleanup": "sed", "wrf_cpp": "cpp",
        "standard": "standard", "final_cpp": "cpp",
    }
    for stage, row in zip(stages, commands):
        argv, _flags = _validate_tool_command(
            row, expected_name=tool_for_stage[stage], plan=plan,
            shadow_host=shadow_host, output_root=output_root,
            label=f"{key} {stage}")
        if row.get("returncode") != 0:
            raise PrelinkError(f"{key} preprocessing stage {stage} failed")
        if row.get("input_sha256") != previous_sha:
            raise PrelinkError(f"{key} preprocessing input chain broke at {stage}")
        if stage == "comment_cleanup" and str(overlay) not in argv:
            raise PrelinkError(f"{key} first preprocessing command does not consume the pinned overlay")
        output_path = _check_file_record(row, "output_path", workspace)
        try:
            output_path.relative_to(output_root.resolve())
        except ValueError as exc:
            raise PrelinkError(f"{key} preprocessing output escaped clean build root: {output_path}") from exc
        _ensure_output_target(argv, expected=output_path, output_root=output_root,
                              require_output=False, label=f"{key} {stage}",
                              arm_root=output_root)
        previous_sha = row["output_path_sha256"]
        if stage == "wrf_cpp":
            macro_argv = argv
        final_output = output_path
    if final_output != expected_output.resolve() or pp.get("output_path") != str(final_output):
        raise PrelinkError(f"{key} final preprocessed source path mismatch")
    if pp.get("output_path_sha256") != previous_sha:
        raise PrelinkError(f"{key} final preprocessed source hash mismatch")
    return macro_argv, final_output


def validate_preprocess_macro_delta(b_argv: list[str], c_argv: list[str]) -> None:
    b_defs, b_undefs = _macro_ops(b_argv)
    c_defs, c_undefs = _macro_ops(c_argv)
    b_guard = [(name, value) for name, value in b_defs if name == ZERO_QG_MACRO]
    c_guard = [(name, value) for name, value in c_defs if name == ZERO_QG_MACRO]
    if b_guard:
        raise PrelinkError("B preprocessing defines the guard macro, including a zero-valued -D")
    if c_guard != [(ZERO_QG_MACRO, None)]:
        raise PrelinkError("C preprocessing must define the bare guard macro exactly once")
    if any(name == ZERO_QG_MACRO for name in b_undefs + c_undefs):
        raise PrelinkError("preprocessing may not undefine the zero-qg guard")
    required = {"KDM6_PROGB_VALIDITY_CAPTURE", "KDM6_PROGB_POLICY_MIDPOINT"}
    if not required.issubset({name for name, _ in b_defs}):
        raise PrelinkError("common B/C preprocessing omits capture or midpoint policy")


def _check_file_record(record: dict[str, Any], field: str, root: Path) -> Path:
    path_value = record.get(field)
    expected_sha = record.get(field + "_sha256")
    if not isinstance(path_value, str) or not path_value:
        raise PrelinkError(f"{field} path is missing")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise PrelinkError(f"{field} SHA-256 is missing")
    path = Path(path_value)
    if not path.is_absolute():
        path = root / path
    if sha256_file(path) != expected_sha:
        raise PrelinkError(f"{field} hash mismatch: {path}")
    return path.resolve()


def validate_execution(plan: dict[str, Any], execution: dict[str, Any], *,
                       plan_sha256: str,
                       snapshot_sha256: str,
                       resource_preflight_receipt: dict[str, Any],
                       resource_preflight_receipt_sha256: str,
                       trusted_resource_approval_sha256: str,
                       workspace: Path, canonical_host: Path,
                       shadow_host: Path, output_root: Path,
                       overlay_paths: dict[str, Path]) -> dict[str, Any]:
    if execution.get("schema") != "s10-czeroqg-prelink-execution-v1":
        raise PrelinkError("execution receipt schema mismatch")
    if execution.get("plan_sha256") != plan_sha256:
        raise PrelinkError("execution receipt is not bound to this plan")
    if execution.get("prebuild_output_root_snapshot_sha256") != snapshot_sha256:
        raise PrelinkError("execution receipt is not bound to the coordinator-pinned empty-root snapshot")
    expected_resource_path = plan.get("resource_gate", {}).get("build", {}).get(
        "prebuild_gate_receipt_relative_path")
    expected_resource_file = (workspace / expected_resource_path).resolve()
    recorded_resource_path = Path(execution.get("resource_preflight_receipt_path", ""))
    if not recorded_resource_path.is_absolute():
        recorded_resource_path = workspace / recorded_resource_path
    if (recorded_resource_path.resolve() != expected_resource_file
            or execution.get("resource_preflight_receipt_sha256")
            != resource_preflight_receipt_sha256):
        raise PrelinkError("execution receipt lacks the exact plan-pinned prebuild resource gate receipt")
    validate_build_resource_preflight(
        plan, resource_preflight_receipt, plan_sha256=plan_sha256,
        snapshot_sha256=snapshot_sha256, output_root=output_root,
        trusted_approval_sha256=trusted_resource_approval_sha256)
    configure_sha = execution.get("configure_wrf_sha256")
    configure_path = shadow_host / "configure.wrf"
    if not isinstance(configure_sha, str) or sha256_file(configure_path) != configure_sha:
        raise PrelinkError("fresh configure.wrf is missing or mismatched")
    if execution.get("toolchain_sha256") != plan["toolchain"]["toolchain_sha256"]:
        raise PrelinkError("execution toolchain digest is not pinned")
    if execution.get("tool_environment") != tool_environment_snapshot():
        raise PrelinkError("execution environment differs from the pinned compiler/tool resolution environment")
    recorded_environment = execution.get("tool_environment")
    if not isinstance(recorded_environment, dict):
        raise PrelinkError("execution receipt lacks the guarded environment snapshot")
    child_environment = {name: value for name, value in recorded_environment.items()
                         if isinstance(value, str)}
    validate_toolchain(plan, shadow_host, environment=child_environment)
    _validate_configure_pipeline(
        execution, shadow_host, output_root, plan, configure_sha,
        plan_sha256=plan_sha256, workspace=workspace)
    validate_clean_shadow(shadow_host, output_root, workspace)

    variants = execution.get("variants")
    if not isinstance(variants, dict):
        raise PrelinkError("execution receipt has no variant records")
    checked: dict[str, Any] = {}
    for scheme in ("mp37", "mp237"):
        pin = plan["host_source_pins"][scheme]
        pair = {}
        for arm in ("B", "C"):
            key = f"{scheme}_{arm}"
            row = variants.get(key)
            if not isinstance(row, dict):
                raise PrelinkError(f"execution record missing {key}")
            for bound_field in ("source_overlay_sha256", "runner_sha256", "configuration_sha256",
                                "toolchain_sha256", "active_input_canonical_sha256"):
                if not isinstance(row.get(bound_field), str) or len(row[bound_field]) != 64:
                    raise PrelinkError(f"{key} lacks bound {bound_field}")
            if row["toolchain_sha256"] != plan["toolchain"]["toolchain_sha256"]:
                raise PrelinkError(f"{key} toolchain digest is not the pinned binary set")
            if row["source_overlay_sha256"] != pin["c_overlay_sha256"]:
                raise PrelinkError(f"{key} source overlay hash mismatch")
            expected_overlay = overlay_paths[scheme].resolve()
            if Path(row.get("source_overlay_path", "")).resolve() != expected_overlay:
                raise PrelinkError(f"{key} source overlay path is not the receipt-bound source")
            if sha256_file(expected_overlay) != pin["c_overlay_sha256"]:
                raise PrelinkError(f"{key} source overlay changed after static verification")
            if row["runner_sha256"] != plan["prelink_requirements"]["runner_sha256"]:
                raise PrelinkError(f"{key} runner hash mismatch")
            expected_input = plan["prelink_requirements"]["active_input_canonical_sha256"]
            if row["active_input_canonical_sha256"] != expected_input:
                raise PrelinkError(f"{key} active input digest mismatch")
            if row.get("active_input_sha256") != plan["prelink_requirements"]["active_input_sha256"]:
                raise PrelinkError(f"{key} named active input hashes are not pinned")
            expected_nml = plan["prelink_requirements"]["effective_namelist_sha256"][scheme]
            if row.get("effective_namelist_sha256") != expected_nml:
                raise PrelinkError(f"{key} effective namelist hash mismatch")
            if row["configuration_sha256"] != configure_sha:
                raise PrelinkError(f"{key} configuration is not the generated configure.wrf")

            pp = row.get("preprocess")
            obj = row.get("object")
            link = row.get("link")
            if not all(isinstance(x, dict) for x in (pp, obj, link)):
                raise PrelinkError(f"{key} is missing preprocess/object/link records")
            arm_root = workspace / "S10/build-clean" / scheme / arm
            obj_argv, obj_flags = _validate_tool_command(
                obj, expected_name="mpif90", plan=plan, shadow_host=shadow_host,
                output_root=arm_root, label=f"{key} object")
            link_argv, link_flags = _validate_tool_command(
                link, expected_name="mpif90", plan=plan, shadow_host=shadow_host,
                output_root=arm_root, label=f"{key} link")
            if "-ffp-contract=off" not in obj_flags:
                raise PrelinkError(f"{key} object flags omit -ffp-contract=off")
            if "-ffp-contract=off" not in link_flags:
                raise PrelinkError(f"{key} link flags omit -ffp-contract=off")
            if obj_flags != row.get("compile_flags"):
                raise PrelinkError(f"{key} compile flags are not explicitly bound")
            expected_preprocessed = workspace / pin["preprocessed_relative_path"].replace("{B,C}", arm)
            pp_argv, preprocessed = _validate_preprocess_pipeline(
                pp, key=key, overlay=expected_overlay, output_root=arm_root,
                expected_output=expected_preprocessed, plan=plan,
                shadow_host=shadow_host, workspace=workspace)
            obj_path = _check_file_record(obj, "object_path", workspace)
            expected_object = workspace / pin["object_relative_path"].replace("{B,C}", arm)
            if obj_path != expected_object.resolve():
                raise PrelinkError(f"{key} object is outside its fresh target path")
            expected_module_dir = workspace / pin["module_output_relative_path"].replace("{B,C}", arm)
            if Path(obj.get("module_output_dir", "")).resolve() != expected_module_dir.resolve():
                raise PrelinkError(f"{key} module output directory is not arm-specific")
            if str(preprocessed) not in obj_argv or "-o" not in obj_argv or obj_argv[obj_argv.index("-o") + 1] != str(obj_path):
                raise PrelinkError(f"{key} object argv does not compile the pinned preprocessed source to its target")
            _ensure_output_target(obj_argv, expected=obj_path,
                                  output_root=arm_root, require_output=True,
                                  label=f"{key} object", arm_root=arm_root,
                                  expected_module_dir=expected_module_dir,
                                  expected_depfile=None)
            for path in (preprocessed, obj_path):
                try:
                    path.relative_to(arm_root.resolve())
                except ValueError as exc:
                    raise PrelinkError(f"{key} build artifact escaped the clean output root: {path}") from exc
            archive = (canonical_host / plan["build_matrix"]["link_input_archive"][
                "path_relative_to_private_host"]).resolve()
            validate_archive_link(
                link_argv,
                archive_path=archive,
                expected_sha256=plan["build_matrix"]["link_input_archive"]["sha256"],
                recorded_path=link.get("archive_path", ""),
                recorded_sha256=link.get("archive_sha256", ""),
            )
            if str(obj_path) not in link_argv:
                raise PrelinkError(f"{key} link argv does not consume its recorded shadow object")
            exe = Path(link.get("executable_path", ""))
            if not exe.is_absolute():
                exe = workspace / exe
            expected_exe = workspace / plan["host_source_pins"][scheme]["executable_relative_path"].replace("{B,C}", arm)
            if exe.resolve() != expected_exe.resolve():
                raise PrelinkError(f"{key} executable path is not the planned fresh output")
            if exe.exists():
                raise PrelinkError(f"{key} fresh executable path already exists")
            if link.get("executable_sha256") is not None:
                raise PrelinkError(f"{key} prelink receipt must not claim a linked executable hash")
            _ensure_output_target(link_argv, expected=exe,
                                  output_root=arm_root, require_output=True,
                                  label=f"{key} link", arm_root=arm_root)
            pair[arm] = {"preprocess_argv": pp_argv, "compile_flags": obj_flags,
                         "link_flags": link_flags, "preprocessed": str(preprocessed),
                         "object": str(obj_path), "planned_executable": str(exe.resolve())}
        if pair["B"]["compile_flags"] != pair["C"]["compile_flags"]:
            raise PrelinkError(f"{scheme} object compiler flags differ between B and C")
        if pair["B"]["link_flags"] != pair["C"]["link_flags"]:
            raise PrelinkError(f"{scheme} linker flags differ between B and C")
        b, c = variants[f"{scheme}_B"], variants[f"{scheme}_C"]
        for field in ("configuration_sha256", "toolchain_sha256", "active_input_canonical_sha256",
                      "effective_namelist_sha256", "source_overlay_sha256"):
            if b[field] != c[field]:
                raise PrelinkError(f"{scheme} B/C differ in shared {field}")
        checked[scheme] = pair
    argv_digest = validate_arm_argv_parity(plan, execution, workspace=workspace)
    if execution.get("normalized_argv_sha256") != argv_digest:
        raise PrelinkError("execution receipt normalized argv digest does not match computed commands")
    validate_output_inventory(output_root, execution.get("build_outputs"), workspace)
    return checked


def make_prelink_receipt(plan_path: Path, release_path: Path, execution_path: Path,
                         canonical_host: Path, shadow_host: Path, workspace: Path,
                         overlay_paths: dict[str, Path], snapshot_path: Path,
                         trusted_release_sha256: str,
                         trusted_resource_approval_sha256: str,
                         receipt_path: Path) -> dict[str, Any]:
    plan, plan_sha = read_hashed_json(plan_path)
    release, release_sha = read_hashed_json(release_path)
    execution, execution_sha = read_hashed_json(execution_path)
    require_s15_release(plan, release, plan_sha, release_sha, trusted_release_sha256)
    expected_snapshot_sha = plan["trusted_s15_release"]["empty_output_root_snapshot_sha256"]
    expected_snapshot_path = workspace / plan["clean_shadow"]["empty_root_snapshot_relative_path"]
    snapshot = validate_prebuild_snapshot(
        snapshot_path, expected_snapshot_sha,
        workspace / plan["clean_shadow"]["fresh_build_output_root"],
        expected_snapshot_path)
    resource_rel = plan["resource_gate"]["build"]["prebuild_gate_receipt_relative_path"]
    resource_path = workspace / resource_rel
    resource_receipt, resource_sha = read_hashed_json(resource_path)
    if execution.get("resource_preflight_receipt_sha256") != resource_sha:
        raise PrelinkError("execution receipt resource-gate digest does not match the prebuild receipt")
    build_gate = plan["resource_gate"]["build"]
    configuration_run = validate_guarded_configuration_run(
        plan, workspace=workspace, shadow_host=shadow_host)
    measurement_path = workspace / build_gate["measurement_receipt_relative_path"]
    measurement, measurement_sha = read_hashed_json(measurement_path)
    approval_path = workspace / build_gate["coordinator_approval_relative_path"]
    approval, approval_sha = read_hashed_json(approval_path)
    if approval_sha != trusted_resource_approval_sha256:
        raise PrelinkError("coordinator resource-approval receipt SHA mismatch")
    require_resource_gate_approval(
        plan, approval, plan_sha256=plan_sha,
        estimate_sha256=build_gate["output_size_estimate_sha256"],
        snapshot_sha256=expected_snapshot_sha,
        measurement_receipt_sha256=measurement_sha,
        measured_free_bytes=measurement.get("observed_free_bytes"),
        measured_at_unix_ns=measurement.get("observed_at_unix_ns"),
        required_free_bytes=measurement.get("required_free_bytes"),
        s15_release_sha256=release_sha,
        configuration_ledger_sha256=configuration_run[
            "configuration_command_ledger_sha256"],
        configure_wrf_sha256=configuration_run["configure_wrf_sha256"],
        configuration_ledger_plan_sha256=configuration_run[
            "configuration_ledger_plan_sha256"],
        approval_sha256=approval_sha,
        trusted_approval_sha256=trusted_resource_approval_sha256)
    if resource_receipt.get("resource_measurement_receipt_sha256") != measurement_sha:
        raise PrelinkError("build preflight receipt is bound to a different capacity measurement")
    validate_build_resource_preflight(
        plan, resource_receipt, plan_sha256=plan_sha,
        snapshot_sha256=expected_snapshot_sha,
        output_root=workspace / plan["clean_shadow"]["fresh_build_output_root"],
        trusted_approval_sha256=trusted_resource_approval_sha256)
    if resource_receipt.get("s15_release_receipt_sha256") != release_sha:
        raise PrelinkError("resource gate was cleared against a different S15 lane release receipt")
    if (resource_receipt.get("configuration_command_ledger_sha256")
            != configuration_run["configuration_command_ledger_sha256"]
            or resource_receipt.get("configure_wrf_sha256")
            != configuration_run["configure_wrf_sha256"]):
        raise PrelinkError("resource gate receipt is not bound to the guarded configure run")
    pins = validate_static_pins(plan, workspace=workspace,
                                canonical_host=canonical_host,
                                shadow_host=shadow_host,
                                overlay_paths=overlay_paths)
    output_root = workspace / plan["clean_shadow"]["fresh_build_output_root"]
    checked = validate_execution(plan, execution, plan_sha256=plan_sha,
                                 snapshot_sha256=expected_snapshot_sha,
                                 resource_preflight_receipt=resource_receipt,
                                 resource_preflight_receipt_sha256=resource_sha,
                                 trusted_resource_approval_sha256=trusted_resource_approval_sha256,
                                 workspace=workspace,
                                 canonical_host=canonical_host,
                                 shadow_host=shadow_host,
                                 output_root=output_root,
                                 overlay_paths=overlay_paths)
    record = {
        "schema": "s10-czeroqg-prelink-receipt-v1",
        "status": "READY_TO_LINK",
        "plan_sha256": plan_sha,
        "release_receipt_sha256": release_sha,
        "coordinator_trusted_release_sha256": trusted_release_sha256,
        "resource_preflight_receipt_sha256": resource_sha,
        "coordinator_trusted_resource_approval_sha256": trusted_resource_approval_sha256,
        "empty_output_root_snapshot_sha256": expected_snapshot_sha,
        "empty_output_root_snapshot_nonce_sha256": snapshot["nonce_sha256"],
        "execution_receipt_sha256": execution_sha,
        "static_pins": pins,
        "validated_variants": checked,
        "build_outputs": execution["build_outputs"],
        "native_link_performed": False,
        "executable_sha256": None,
        "stage1_discovery_keys": None,
        "final_event_log_sha256": None,
        "s10_status": "OPEN",
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def _overlay_args(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for raw in values:
        if "=" not in raw:
            raise PrelinkError("overlay must be SCHEME=PATH")
        scheme, path = raw.split("=", 1)
        result[scheme] = Path(path)
    if set(result) != {"mp37", "mp237"}:
        raise PrelinkError("supply exactly --overlay mp37=PATH and --overlay mp237=PATH")
    return result


def resource_preflight_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Fresh disk-space and coordinator gate before S10 configure/build stages")
    parser.add_argument("--phase", choices=(
        "configure", "measure", "build", "build-preparation-measure"), required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--trusted-plan-sha256", required=True,
                        help="coordinator-supplied plan hash verified before any plan-directed action")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--canonical-host", type=Path, required=True)
    parser.add_argument("--shadow-host", type=Path, required=True)
    parser.add_argument("--overlay", action="append", default=[])
    parser.add_argument("--estimate", type=Path)
    parser.add_argument("--resource-approval", type=Path)
    parser.add_argument("--trusted-resource-approval-sha256")
    parser.add_argument("--s15-release", type=Path)
    parser.add_argument("--trusted-s15-release-sha256")
    args = parser.parse_args(argv)
    try:
        try:
            plan_bytes = args.plan.read_bytes()
        except OSError as exc:
            raise PrelinkError(f"cannot read plan bytes: {exc}") from exc
        plan_sha = sha256_bytes(plan_bytes)
        if plan_sha != args.trusted_plan_sha256:
            raise PrelinkError("resource preflight plan SHA differs from coordinator-trusted pin")
        plan = parse_json_bytes(plan_bytes, args.plan)
        workspace = args.workspace.resolve()
        output_root = workspace / plan["clean_shadow"]["fresh_build_output_root"]
        snapshot_path = workspace / plan["clean_shadow"]["empty_root_snapshot_relative_path"]
        if args.phase == "configure":
            receipt_rel = plan["resource_gate"]["configure_only"][
                "preflight_receipt_relative_path"]
        elif args.phase == "build-preparation-measure":
            receipt_rel = plan["resource_gate"]["build_preparation"][
                "measurement_only_receipt_relative_path"]
        elif args.phase == "measure":
            receipt_rel = plan["resource_gate"]["build"][
                "measurement_receipt_relative_path"]
        else:
            receipt_rel = plan["resource_gate"]["build"][
                "prebuild_gate_receipt_relative_path"]
        if args.phase == "build":
            expected_approval = workspace / plan["resource_gate"]["build"][
                "coordinator_approval_relative_path"]
            if (args.resource_approval is None
                    or args.resource_approval.resolve() != expected_approval.resolve()):
                raise PrelinkError("coordinator resource approval path differs from the plan")
        if args.phase == "build-preparation-measure" and (
                args.resource_approval is not None or args.trusted_resource_approval_sha256 is not None
                or args.s15_release is not None or args.trusted_s15_release_sha256 is not None):
            raise PrelinkError("measurement-only phase does not accept coordinator approval or release inputs")
        if args.resource_approval:
            approval, approval_sha = read_hashed_json(args.resource_approval)
        else:
            approval, approval_sha = None, None
        if args.s15_release:
            s15_release, s15_release_sha = read_hashed_json(args.s15_release)
        else:
            s15_release, s15_release_sha = None, None
        result = create_resource_preflight_receipt(
            plan, plan_sha256=plan_sha, workspace=workspace,
            canonical_host=args.canonical_host, shadow_host=args.shadow_host,
            overlay_paths=_overlay_args(args.overlay), output_root=output_root,
            snapshot_path=snapshot_path, phase=args.phase,
            receipt_path=workspace / receipt_rel,
            estimate_path=args.estimate, approval=approval,
            approval_sha256=approval_sha,
            trusted_approval_sha256=args.trusted_resource_approval_sha256,
            s15_release=s15_release, s15_release_sha256=s15_release_sha,
            trusted_s15_release_sha256=args.trusted_s15_release_sha256,
        )
    except (PrelinkError, KeyError, TypeError, ValueError, OSError) as exc:
        print(f"RESOURCE PREFLIGHT BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "resource-preflight":
        return resource_preflight_main(sys.argv[2:])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--execution", type=Path, required=True)
    parser.add_argument("--canonical-host", type=Path, required=True)
    parser.add_argument("--shadow-host", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--overlay", action="append", default=[])
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--trusted-release-sha256", required=True,
                        help="coordinator-supplied receipt hash, kept outside the plan to avoid circular hashing")
    parser.add_argument("--trusted-resource-approval-sha256", required=True,
                        help="coordinator resource-approval hash supplied outside the plan")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = make_prelink_receipt(
            args.plan, args.release, args.execution, args.canonical_host,
            args.shadow_host, args.workspace, _overlay_args(args.overlay),
            args.snapshot, args.trusted_release_sha256,
            args.trusted_resource_approval_sha256, args.receipt,
        )
    except (PrelinkError, KeyError, TypeError, ValueError) as exc:
        print(f"PRELINK BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
