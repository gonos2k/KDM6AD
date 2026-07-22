#!/usr/bin/env python3
"""Build, run and strictly bind one local Fortran case to the shared fixture."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "harness"))
import g33_fortran_dump as fd  # noqa: E402
import g33_fixture_v1 as fixture  # noqa: E402


def _sha_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _sha_path(path: str) -> str:
    with open(path, "rb") as f:
        return _sha_bytes(f.read())


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          text=True, check=False).stdout.strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--algo", required=True, choices=["legacy", "conservative"])
    ap.add_argument("--out", required=True, help="fresh output directory")
    args = ap.parse_args()

    authority = fixture.load_manifest()
    B, K = authority["B"], authority["K"]
    build_run = subprocess.run(
        ["bash", os.path.join(HERE, "fortran_build.sh"), args.out,
         f"--algo={args.algo}", "--dump"], cwd=ROOT, capture_output=True, text=True)
    if build_run.returncode != 0:
        raise SystemExit(f"build failed:\n{build_run.stdout}\n{build_run.stderr}")
    driver = os.path.join(args.out, "g33_fortran_driver")
    run = subprocess.run([driver], capture_output=True)
    if run.returncode != 0:
        raise SystemExit(f"driver crashed:\n{run.stderr.decode(errors='replace')}")
    stdout = run.stdout.decode("ascii")
    parsed = fd.parse_fortran_run(stdout, args.algo, K=K, B=B)
    if parsed.fixture_sha256 != fixture.fixture_sha256(authority):
        raise SystemExit("Fortran FIXIN differs from the shared raw-bit authority")
    if parsed.parameter_sha256 != fixture.parameter_sha256(authority):
        raise SystemExit("Fortran common PARAM values differ from the shared authority")
    fd.verify_offline_replay(parsed)

    with open(os.path.join(args.out, "provenance.json"), encoding="utf-8") as f:
        build = json.load(f)
    manifest = {
        "schema_version": 2,
        "repo_commit": _git("rev-parse", "HEAD"),
        "repo_dirty": bool(_git("status", "--porcelain")),
        "algorithm": args.algo,
        "fixture_id": authority["fixture_id"],
        "science_role": authority["science_role"],
        "fixture_manifest_sha256": fixture.manifest_sha256(authority),
        "fixture_sha256": parsed.fixture_sha256,
        "parameter_sha256": parsed.parameter_sha256,
        "fortran_parameter_sha256": fixture.fortran_parameter_sha256(authority),
        "K": K, "B": B, "mstep_per_column": parsed.mstep,
        "stdout_sha256": _sha_bytes(run.stdout),
        "stderr_sha256": _sha_bytes(run.stderr),
        "executable_sha256": _sha_path(driver),
        "compiler_path": build["compiler_path"],
        "compiler_binary_sha256": build["compiler_binary_sha256"],
        "compiler_version": build["compiler_version"],
        "os": platform.platform(), "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "host_source_sha256": build["host_source_sha256"],
        "harness_source_sha256": build["harness_source_sha256"],
        "module_compiled_sha256": build["module_compiled_sha256"],
        "commands": build["commands"], "op_record_count": len(parsed.ops),
    }
    dst = os.path.join(args.out, "run_manifest.json")
    tmp = dst + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    os.replace(tmp, dst)
    print(f"run OK ({args.algo}): {len(parsed.ops)} ops, shared fixture "
          f"{parsed.fixture_sha256[:12]} -> {dst}")


if __name__ == "__main__":
    main()
