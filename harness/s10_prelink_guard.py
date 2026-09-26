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
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

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
    "TERRAIN_AND_LANDUSE",
)


def tool_environment_snapshot() -> dict[str, str | None]:
    return {name: os.environ.get(name) for name in _TOOLCHAIN_ENV_KEYS}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def sha256_file(path: Path) -> str:
    try:
        return sha256_bytes(path.read_bytes())
    except OSError as exc:
        raise PrelinkError(f"required file unavailable: {path}: {exc}") from exc


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PrelinkError(f"cannot read JSON receipt {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PrelinkError(f"JSON receipt must be an object: {path}")
    return value


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
    if snapshot_path.resolve() != expected_snapshot_path.resolve():
        raise PrelinkError("empty-root snapshot path differs from the plan-pinned external location")
    try:
        snapshot_path.resolve().relative_to(output_root.resolve())
    except ValueError:
        pass
    else:
        raise PrelinkError("empty-root snapshot cannot be stored inside the output root")
    if sha256_file(snapshot_path) != expected_sha256:
        raise PrelinkError("empty-output-root snapshot SHA is not coordinator-pinned")
    snapshot = load_json(snapshot_path)
    nonce = snapshot.get("nonce")
    if (snapshot.get("schema") != "s10-empty-output-root-snapshot-v1"
            or snapshot.get("root_path") != str(output_root.resolve())
            or snapshot.get("observed_empty") is not True
            or snapshot.get("observed_file_count") != 0
            or not isinstance(nonce, str)
            or not re.fullmatch(r"[0-9a-f]{64}", nonce)
            or snapshot.get("nonce_sha256") != sha256_bytes(nonce.encode())):
        raise PrelinkError("empty-output-root snapshot fields or nonce are invalid")
    return snapshot


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


def validate_toolchain(plan: dict[str, Any], shadow_host: Path) -> dict[str, dict[str, str]]:
    toolchain = plan.get("toolchain", {})
    specs = toolchain.get("tools")
    if not isinstance(specs, dict) or not specs:
        raise PrelinkError("toolchain binary pins are missing")
    environment = tool_environment_snapshot()
    environment_sha = sha256_bytes(json.dumps(
        environment, sort_keys=True, separators=(",", ":")).encode())
    if environment_sha != toolchain.get("environment_sha256"):
        raise PrelinkError("toolchain resolution environment differs from its pin")
    configured_environment = toolchain.get("configuration_environment", {})
    if not isinstance(configured_environment, dict):
        raise PrelinkError("pinned configuration environment is malformed")
    for name, expected in configured_environment.items():
        if name not in environment or environment[name] != expected:
            raise PrelinkError(f"configuration environment differs from its pin: {name}")
    canonical = json.dumps({"tools": specs, "environment_sha256": environment_sha},
                           sort_keys=True, separators=(",", ":")).encode()
    if sha256_bytes(canonical) != toolchain.get("toolchain_sha256"):
        raise PrelinkError("pinned toolchain manifest digest is inconsistent")
    resolved: dict[str, dict[str, str]] = {}
    for name, spec in specs.items():
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
            result = subprocess.run(
                [str(path), *version_argv], check=True, capture_output=True,
                text=True, shell=False)
            if result.stdout.strip() != version_stdout:
                raise PrelinkError(f"pinned tool version output changed for {name}")
            resolved[name]["version_stdout"] = version_stdout
    for env_name, tool_name in (("NETCDF_C", "nc-config"), ("NETCDF", "nf-config")):
        if tool_name in resolved:
            root = environment.get(env_name)
            expected_path = (Path(root) / "bin" / tool_name).resolve() if root else None
            if expected_path is None or Path(resolved[tool_name]["path"]).resolve() != expected_path:
                raise PrelinkError(f"{tool_name} is not resolved from pinned {env_name}")
    if {"mpif90", "gfortran", "ld"}.issubset(resolved):
        mpif90_command = subprocess.run(
            [resolved["mpif90"]["path"], "--showme:command"],
            check=True, capture_output=True, text=True).stdout.strip()
        if mpif90_command != toolchain.get("mpif90_underlying_command"):
            raise PrelinkError("mpif90 resolved to an unexpected Fortran compiler")
        compiler_path = shutil.which(mpif90_command)
        if compiler_path is None or Path(compiler_path).resolve() != Path(resolved["gfortran"]["path"]).resolve():
            raise PrelinkError("mpif90's Fortran compiler path is not the pinned gfortran binary")
        reported_ld = subprocess.run(
            [resolved["gfortran"]["path"], "-print-prog-name=ld"],
            check=True, capture_output=True, text=True).stdout.strip()
        if reported_ld != toolchain.get("linker_name_reported_by_gfortran"):
            raise PrelinkError("gfortran reported an unexpected linker name")
        for child, wrapper in (("as", "as_wrapper"), ("ld", "ld_wrapper")):
            reported = subprocess.run(
                [resolved["gfortran"]["path"], f"-print-prog-name={child}"],
                check=True, capture_output=True, text=True).stdout.strip()
            wrapper_path = shutil.which(reported)
            if (wrapper_path is None or wrapper not in resolved
                    or Path(wrapper_path).resolve() != Path(resolved[wrapper]["path"]).resolve()):
                raise PrelinkError(f"gfortran's {child} wrapper is not the pinned executable")
            xcrun_path = resolved.get("xcrun", {}).get("path")
            actual_child = subprocess.run(
                [xcrun_path, "--find", child], check=True,
                capture_output=True, text=True).stdout.strip() if xcrun_path else ""
            if (not actual_child or child not in resolved
                    or Path(actual_child).resolve() != Path(resolved[child]["path"]).resolve()):
                raise PrelinkError(f"xcrun's {child} subordinate binary is not pinned")
        for child in ("f951", "collect2"):
            reported = subprocess.run(
                [resolved["gfortran"]["path"], f"-print-prog-name={child}"],
                check=True, capture_output=True, text=True).stdout.strip()
            if child not in resolved or Path(reported).resolve() != Path(resolved[child]["path"]).resolve():
                raise PrelinkError(f"gfortran's {child} subordinate binary is not pinned")
    return resolved


def validate_static_pins(plan: dict[str, Any], *, workspace: Path,
                         canonical_host: Path, shadow_host: Path,
                         overlay_paths: dict[str, Path]) -> dict[str, Any]:
    """Rehash current canonical sources, local overlays, config, inputs, and archive."""
    pins = plan["host_source_pins"]
    sources: dict[str, Any] = {}
    for scheme in ("mp37", "mp237"):
        item = pins[scheme]
        canonical = canonical_host / item["source_relative_to_private_host"]
        sources[scheme] = validate_source_overlay(
            item, scheme=scheme, canonical_source=canonical,
            overlay_path=overlay_paths[scheme])

    for rel, expected in plan["prelink_requirements"]["configuration_inputs_sha256"].items():
        if sha256_file(canonical_host / rel) != expected:
            raise PrelinkError(f"private host configuration source changed: {rel}")

    trusted_s15 = plan.get("trusted_s15_release", {})
    manifest_path = workspace / trusted_s15.get("evidence_manifest_path", "")
    if sha256_file(manifest_path) != trusted_s15.get("evidence_manifest_sha256"):
        raise PrelinkError("merged S15 evidence manifest hash differs from the public pin")
    merge = trusted_s15.get("s15_merge_commit")
    ancestry = subprocess.run(
        ["git", "-C", str(workspace), "merge-base", "--is-ancestor", str(merge), "HEAD"],
        capture_output=True, text=True)
    if ancestry.returncode != 0:
        raise PrelinkError("worktree HEAD does not contain the pinned S15 B20s merge")

    archive_pin = plan["build_matrix"]["link_input_archive"]
    archive = (canonical_host / archive_pin["path_relative_to_private_host"]).resolve()
    if sha256_file(archive) != archive_pin["sha256"]:
        raise PrelinkError("canonical libwrflib.a hash changed")
    if (shadow_host / "main/libwrflib.a").exists():
        raise PrelinkError("shadow archive exists; link must use the pinned canonical archive")

    toolchain = validate_toolchain(plan, shadow_host)

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
        "canonical_archive_path": str(archive),
        "canonical_archive_sha256": archive_pin["sha256"],
        "toolchain": toolchain,
        "toolchain_sha256": plan["toolchain"]["toolchain_sha256"],
        "tool_environment": tool_environment_snapshot(),
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
        "stdout_path": record.get("stdout_path"),
        "stderr_path": record.get("stderr_path"),
        "stdin_path": record.get("stdin_path"),
        "stdin_sha256": record.get("stdin_sha256"),
        "script_sha256": record.get("script_sha256"),
        "returncode": record.get("returncode"),
        "shell": record.get("shell"),
        "netcdf_tool_invocations": record.get("netcdf_tool_invocations"),
    }


def _validate_netcdf_config_invocations(
        configure_record: dict[str, Any], plan: dict[str, Any],
        shadow_host: Path) -> None:
    policy = plan["prelink_requirements"].get("netcdf_config_invocation_policy")
    if not isinstance(policy, dict):
        return
    expected_tools = policy.get("invocations")
    if not isinstance(expected_tools, dict) or set(expected_tools) != {"nc-config", "nf-config"}:
        raise PrelinkError("pinned NetCDF config-tool invocation policy is incomplete")
    recorded = configure_record.get("netcdf_tool_invocations")
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
        if (not isinstance(row, dict) or row.get("path") != str(tool_path)
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
                                 configure_sha: str) -> None:
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
        if row.get("script_sha256") != script_hashes[script_name]:
            raise PrelinkError(f"configuration stage {stage} script hash mismatch")
        if sha256_file(shadow_host / script_name) != script_hashes[script_name]:
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
    expected_configure_sha = plan["prelink_requirements"].get("generated_configure_wrf_sha256")
    if not isinstance(expected_configure_sha, str) or len(expected_configure_sha) != 64:
        raise PrelinkError("fresh configure.wrf SHA-256 is not independently pinned in the plan")
    if configure_sha != expected_configure_sha or sha256_file(shadow_host / "configure.wrf") != expected_configure_sha:
        raise PrelinkError("fresh configure.wrf differs from the reviewed plan pin")
    netcdf_policy = plan["prelink_requirements"].get("netcdf_config_invocation_policy")
    if isinstance(netcdf_policy, dict):
        _validate_netcdf_config_invocations(first, plan, shadow_host)
        stdout_path = Path(first["stdout_path"])
        if not stdout_path.is_absolute():
            stdout_path = output_root / stdout_path
        configure_stdout = stdout_path.read_text(encoding="utf-8")
        netcdf_root = netcdf_policy["environment"]["NETCDF"]
        if f"Will use NETCDF in dir: {netcdf_root}" not in configure_stdout:
            raise PrelinkError("configure output does not confirm the pinned NETCDF root")


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
                       workspace: Path, canonical_host: Path,
                       shadow_host: Path, output_root: Path,
                       overlay_paths: dict[str, Path]) -> dict[str, Any]:
    if execution.get("schema") != "s10-czeroqg-prelink-execution-v1":
        raise PrelinkError("execution receipt schema mismatch")
    if execution.get("plan_sha256") != plan_sha256:
        raise PrelinkError("execution receipt is not bound to this plan")
    if execution.get("prebuild_output_root_snapshot_sha256") != snapshot_sha256:
        raise PrelinkError("execution receipt is not bound to the coordinator-pinned empty-root snapshot")
    configure_sha = execution.get("configure_wrf_sha256")
    configure_path = shadow_host / "configure.wrf"
    if not isinstance(configure_sha, str) or sha256_file(configure_path) != configure_sha:
        raise PrelinkError("fresh configure.wrf is missing or mismatched")
    if execution.get("toolchain_sha256") != plan["toolchain"]["toolchain_sha256"]:
        raise PrelinkError("execution toolchain digest is not pinned")
    if execution.get("tool_environment") != tool_environment_snapshot():
        raise PrelinkError("execution environment differs from the pinned compiler/tool resolution environment")
    validate_toolchain(plan, shadow_host)
    _validate_configure_pipeline(execution, shadow_host, output_root, plan, configure_sha)
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
                         receipt_path: Path) -> dict[str, Any]:
    plan = load_json(plan_path)
    release = load_json(release_path)
    execution = load_json(execution_path)
    plan_sha = sha256_file(plan_path)
    release_sha = sha256_file(release_path)
    require_s15_release(plan, release, plan_sha, release_sha, trusted_release_sha256)
    expected_snapshot_sha = plan["trusted_s15_release"]["empty_output_root_snapshot_sha256"]
    expected_snapshot_path = workspace / plan["clean_shadow"]["empty_root_snapshot_relative_path"]
    snapshot = validate_prebuild_snapshot(
        snapshot_path, expected_snapshot_sha,
        workspace / plan["clean_shadow"]["fresh_build_output_root"],
        expected_snapshot_path)
    pins = validate_static_pins(plan, workspace=workspace,
                                canonical_host=canonical_host,
                                shadow_host=shadow_host,
                                overlay_paths=overlay_paths)
    output_root = workspace / plan["clean_shadow"]["fresh_build_output_root"]
    checked = validate_execution(plan, execution, plan_sha256=plan_sha,
                                 snapshot_sha256=expected_snapshot_sha,
                                 workspace=workspace,
                                 canonical_host=canonical_host,
                                 shadow_host=shadow_host,
                                 output_root=output_root,
                                 overlay_paths=overlay_paths)
    record = {
        "schema": "s10-czeroqg-prelink-receipt-v1",
        "status": "READY_TO_LINK",
        "plan_sha256": plan_sha,
        "release_receipt_sha256": sha256_file(release_path),
        "coordinator_trusted_release_sha256": trusted_release_sha256,
        "empty_output_root_snapshot_sha256": expected_snapshot_sha,
        "empty_output_root_snapshot_nonce_sha256": snapshot["nonce_sha256"],
        "execution_receipt_sha256": sha256_file(execution_path),
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


def main() -> int:
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
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = make_prelink_receipt(
            args.plan, args.release, args.execution, args.canonical_host,
            args.shadow_host, args.workspace, _overlay_args(args.overlay),
            args.snapshot, args.trusted_release_sha256, args.receipt,
        )
    except (PrelinkError, KeyError, TypeError, ValueError) as exc:
        print(f"PRELINK BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
