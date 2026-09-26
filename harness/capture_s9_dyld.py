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
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

TOOL_RELATIVE_PATH = "harness/capture_s9_dyld.py"


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


def _redacted_environment(env: dict[str, str]) -> dict[str, str]:
    result = {}
    for key, value in sorted(env.items()):
        if re.search(r"(TOKEN|SECRET|PASSWORD|API[_-]?KEY|PRIVATE[_-]?KEY)", key, re.I):
            result[key] = f"<redacted:sha256:{_sha(value.encode())}>"
        else:
            result[key] = value
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--executable", required=True, help="manifest-relative WRF executable")
    parser.add_argument("--executable-id", required=True, help="manifest artifact ID for the WRF executable")
    parser.add_argument("--library", required=True, help="manifest-relative installed KDM6 C ABI dylib")
    parser.add_argument("--library-id", required=True, help="manifest artifact ID for the installed dylib")
    parser.add_argument("--cwd", required=True, help="manifest-relative one-rank run directory")
    parser.add_argument("--launcher", type=Path, required=True, help="absolute path to the approved mpirun executable")
    parser.add_argument("--receipt", required=True, help="manifest-relative JSON receipt output")
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

    env = os.environ.copy()
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
    public_env = _redacted_environment(env)
    receipt = {
        "schema_version": "s9-dyld-capture/v1",
        "capture_tool_path": TOOL_RELATIVE_PATH,
        "capture_tool_sha256": tool_sha,
        "capture_argv": [TOOL_RELATIVE_PATH, *sys.argv[1:]],
        "process_argv": command,
        "launcher_sha256": _sha(launcher.read_bytes()),
        "process_cwd": cwd.relative_to(root).as_posix(),
        "process_environment": public_env,
        "process_environment_sha256": _environment_digest(public_env),
        "process_exit_code": child.returncode,
        "executable": {"artifact_id": args.executable_id, "path": executable.relative_to(root).as_posix(), "sha256": _sha(executable.read_bytes())},
        "loaded_library": {"artifact_id": args.library_id, "path": library.relative_to(root).as_posix(), "sha256": _sha(library.read_bytes())},
        "stdout_sha256": _sha(child.stdout),
        "stderr_sha256": _sha(child.stderr),
        "dyld_image_lines": loaded_lines,
    }
    receipt_path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
