#!/usr/bin/env python3
"""Capture one-rank WRF dyld output as a structured, hash-bound receipt.

This tool is intentionally not run by the S9 source-lineage planning workflow.
Use it only in the later, authorized native-loader observation slot.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath

TOOL_RELATIVE_PATH = "harness/capture_s9_dyld.py"
ENV_ALLOWLIST = (
    "PATH", "DYLD_PRINT_LIBRARIES", "DYLD_PRINT_RPATHS", "DYLD_LIBRARY_PATH",
    "DYLD_FALLBACK_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH",
    "DYLD_FALLBACK_FRAMEWORK_PATH", "DYLD_INSERT_LIBRARIES", "SDKROOT",
    "MACOSX_DEPLOYMENT_TARGET", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
    "OMP_THREAD_LIMIT",
)
PATH_ENV_KEYS = {
    "PATH",
    "DYLD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH",
    "DYLD_FALLBACK_FRAMEWORK_PATH", "DYLD_INSERT_LIBRARIES", "SDKROOT",
}


def _relative(root: Path, value: str) -> Path:
    rel = PurePosixPath(value)
    if rel.is_absolute() or ".." in rel.parts or "\\" in value:
        raise ValueError(f"path must be relative to --root: {value}")
    return root.joinpath(*rel.parts)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _environment_digest(env: dict[str, str]) -> str:
    payload = b"\0".join(f"{key}={env[key]}".encode() for key in sorted(env))
    return _sha(payload)


def _public_environment(env: dict[str, str]) -> dict[str, str]:
    """Serialize only loader/thread controls; path-valued settings become hashes."""
    result = {}
    for key in ENV_ALLOWLIST:
        if key not in env:
            continue
        value = env[key]
        result[key] = f"<redacted-path-sha256:{_sha(value.encode())}>" if key in PATH_ENV_KEYS else value
    return result


def _public_capture_argv(manifest_id: str, executable_id: str, library_id: str) -> list[str]:
    return [
        TOOL_RELATIVE_PATH,
        "--root", "<BUILD_ROOT>", "--manifest-id", manifest_id,
        "--executable", "<WRF_EXE>", "--executable-id", executable_id,
        "--library", "<INSTALLED_KDM6_C_ABI_DYLIB>", "--library-id", library_id,
        "--cwd", "<RUN_DIR>", "--launcher", "<MPI_LAUNCHER>",
        "--receipt", "<PUBLIC_CAPTURE_RECEIPT>",
        "--private-receipt", "<PRIVATE_RAW_RECEIPT>",
        "--stdout", "<PRIVATE_STDOUT>", "--stderr", "<PRIVATE_STDERR>",
    ]


def _public_process_argv() -> list[str]:
    return ["<MPI_LAUNCHER>", "-n", "1", "<WRF_EXE>"]


def _public_dyld_lines(lines: list[str]) -> list[str]:
    return ["dyld: loaded <INSTALLED_KDM6_C_ABI_DYLIB>" for line in lines if "dyld[" in line and "libkdm6_c" in line]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest-id", required=True)
    parser.add_argument("--executable", required=True, help="manifest-relative WRF executable")
    parser.add_argument("--executable-id", required=True, help="manifest artifact ID for the WRF executable")
    parser.add_argument("--library", required=True, help="manifest-relative installed KDM6 C ABI dylib")
    parser.add_argument("--library-id", required=True, help="manifest artifact ID for the installed dylib")
    parser.add_argument("--cwd", required=True, help="manifest-relative one-rank run directory")
    parser.add_argument("--launcher", type=Path, required=True, help="absolute path to the approved mpirun executable")
    parser.add_argument("--receipt", required=True, help="manifest-relative JSON receipt output")
    parser.add_argument("--private-receipt", required=True, help="ignored host/ path for raw path-bearing capture JSON")
    parser.add_argument("--stdout", required=True, help="manifest-relative child stdout output")
    parser.add_argument("--stderr", required=True, help="manifest-relative child stderr output")
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    executable = _relative(root, args.executable).resolve(strict=True)
    library = _relative(root, args.library).resolve(strict=True)
    cwd = _relative(root, args.cwd).resolve(strict=True)
    launcher = args.launcher.resolve(strict=True)
    if launcher.name != "mpirun" or not os.access(launcher, os.X_OK):
        parser.error("--launcher must be an executable named mpirun")
    if not executable.is_file() or not library.is_file() or not cwd.is_dir():
        parser.error("executable/library/cwd does not identify the requested files and run directory")

    env = {key: os.environ[key] for key in ENV_ALLOWLIST if key in os.environ}
    env["DYLD_PRINT_LIBRARIES"] = "1"
    env["DYLD_PRINT_RPATHS"] = "1"
    env["OMP_NUM_THREADS"] = "1"
    env["MKL_NUM_THREADS"] = "1"
    env["OMP_THREAD_LIMIT"] = "1"
    command = [str(launcher), "-n", "1", str(executable)]
    child = subprocess.run(command, cwd=cwd, env=env, capture_output=True, check=False)
    stdout_path = _relative(root, args.stdout)
    stderr_path = _relative(root, args.stderr)
    receipt_path = _relative(root, args.receipt)
    private_receipt_path = _relative(root, args.private_receipt)
    if not any(path.is_relative_to(root / "host") for path in (stdout_path, stderr_path, private_receipt_path)):
        parser.error("raw stdout/stderr/private receipt outputs must be inside ignored host/")
    if private_receipt_path != _relative(root, f"host/s9-captures/{args.manifest_id}.raw.json"):
        parser.error("private receipt must use host/s9-captures/<manifest-id>.raw.json")
    if private_receipt_path != _relative(root, f"host/s9-captures/{args.manifest_id}.raw.json"):
        parser.error("private receipt must use host/s9-captures/<manifest-id>.raw.json")
    if receipt_path.is_relative_to(root / "host"):
        parser.error("public receipt projection must be outside ignored host/")
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path.write_bytes(child.stdout)
    stderr_path.write_bytes(child.stderr)

    loaded_lines = []
    expected_loaded_path = str(library)
    for line in (child.stdout + b"\n" + child.stderr).decode("utf-8", errors="replace").splitlines():
        if "dyld[" in line and "libkdm6_c" in line:
            loaded_lines.append(line)
    if not any(expected_loaded_path in line for line in loaded_lines):
        print("capture failed: dyld output did not name the exact installed library path", file=sys.stderr)
    tool_path = root / TOOL_RELATIVE_PATH
    tool_sha = _sha(tool_path.read_bytes())
    public_env = _public_environment(env)
    raw_receipt = {
        "schema_version": "s9-dyld-raw-capture/v1",
        "manifest_id": args.manifest_id,
        "capture_tool_sha256": tool_sha,
        "raw_capture_argv": [sys.executable, str(Path(sys.argv[0]).resolve()), *sys.argv[1:]],
        "raw_process_argv": command,
        "raw_process_cwd": str(cwd),
        "raw_process_environment": env,
        "process_exit_code": child.returncode,
        "raw_executable_path": str(executable),
        "raw_executable_sha256": _sha(executable.read_bytes()),
        "raw_loaded_library_path": str(library),
        "raw_loaded_library_sha256": _sha(library.read_bytes()),
        "raw_stdout_path": str(stdout_path),
        "raw_stderr_path": str(stderr_path),
        "stdout_sha256": _sha(child.stdout),
        "stderr_sha256": _sha(child.stderr),
        "dyld_image_lines": loaded_lines,
    }
    raw_bytes = (json.dumps(raw_receipt, sort_keys=True, indent=2) + "\n").encode()
    private_receipt_path.parent.mkdir(parents=True, exist_ok=True)
    private_receipt_path.write_bytes(raw_bytes)
    receipt = {
        "schema_version": "s9-dyld-capture/v1",
        "capture_tool_path": TOOL_RELATIVE_PATH,
        "capture_tool_sha256": tool_sha,
        "capture_argv": _public_capture_argv(args.manifest_id, args.executable_id, args.library_id),
        "manifest_id": args.manifest_id,
        "process_argv": _public_process_argv(),
        "launcher_sha256": _sha(launcher.read_bytes()),
        "process_cwd": "<RUN_DIR>",
        "process_environment": public_env,
        "process_environment_sha256": _environment_digest(public_env),
        "process_exit_code": child.returncode,
        "executable": {"artifact_id": args.executable_id, "path": executable.relative_to(root).as_posix(), "sha256": _sha(executable.read_bytes())},
        "loaded_library": {"artifact_id": args.library_id, "path": library.relative_to(root).as_posix(), "sha256": _sha(library.read_bytes())},
        "stdout_sha256": _sha(child.stdout),
        "stderr_sha256": _sha(child.stderr),
        "dyld_image_lines": _public_dyld_lines(loaded_lines),
        "private_receipt_sha256": _sha(raw_bytes),
    }
    receipt_path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
