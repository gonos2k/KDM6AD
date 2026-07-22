#!/usr/bin/env python3
"""Run one standalone-Fortran G3.3-M case end-to-end and emit a decision-grade
run manifest.

Build provenance (fortran_build.sh -> provenance.json) pins the INPUTS; this
wrapper pins the RUN: it builds the instrumented (overlay + dump) driver, runs
it, parses the stdout with the STRICT FortranRun parser (so an incomplete or
malformed stream fails here, not silently downstream), and writes
run_manifest.json binding the build provenance to the actual fixture/parameter
identity, the stdout/stderr digests, the executable, the compiler binary, and
the repo + platform state.

    run_fortran_case.py --algo legacy|conservative --out <dir>

The Fortran leg is local-only; this manifest is what makes a local result
reproducible and auditable as C4 evidence.
"""
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
K, B = 4, 3   # the driver fixture dimensions (IM=3, KM=4)

sys.path.insert(0, HERE)
import g33_fortran_dump as fd  # noqa: E402


def _sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def _sha_path(path):
    with open(path, "rb") as f:
        return _sha_bytes(f.read())


def _git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          text=True).stdout.strip()


def main():
    ap = argparse.ArgumentParser(description="run a standalone-Fortran G3.3-M case")
    ap.add_argument("--algo", required=True, choices=["legacy", "conservative"])
    ap.add_argument("--out", required=True, help="fresh output dir (must not exist)")
    args = ap.parse_args()

    # BUILD the instrumented driver (overlay + dump macro) into args.out.
    r = subprocess.run(
        ["bash", os.path.join(HERE, "fortran_build.sh"), args.out,
         f"--algo={args.algo}", "--dump"],
        cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"build failed:\n{r.stdout}\n{r.stderr}")
    driver = os.path.join(args.out, "g33_fortran_driver")

    # RUN + capture; parse STRICTLY (fails on any incomplete/malformed stream).
    run = subprocess.run([driver], capture_output=True)
    if run.returncode != 0:
        raise SystemExit(f"driver crashed:\n{run.stderr.decode(errors='replace')}")
    stdout = run.stdout.decode()
    parsed = fd.parse_fortran_run(stdout, args.algo, K=K, B=B)

    build = json.load(open(os.path.join(args.out, "provenance.json")))
    manifest = {
        "schema_version": 1,
        "repo_commit": _git("rev-parse", "HEAD"),
        "repo_dirty": bool(_git("status", "--porcelain")),
        "algorithm": args.algo,
        "K": K, "B": B,
        "mstep_per_column": parsed.mstep,
        "fixture_sha256": parsed.fixture_sha256,
        "parameter_sha256": parsed.parameter_sha256,
        "stdout_sha256": _sha_bytes(run.stdout),
        "stderr_sha256": _sha_bytes(run.stderr),
        "executable_sha256": _sha_path(driver),
        "compiler_path": build["compiler_path"],
        "compiler_binary_sha256": _sha_path(build["compiler_path"]),
        "compiler_version": build["compiler_version"],
        "os": platform.platform(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "host_source_sha256": build["host_source_sha256"],
        "harness_source_sha256": build["harness_source_sha256"],
        "module_compiled_sha256": build["module_compiled_sha256"],
        "commands": build["commands"],
        "op_record_count": len(parsed.ops),
    }
    dst = os.path.join(args.out, "run_manifest.json")
    tmp = dst + ".tmp"
    with open(tmp, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    os.replace(tmp, dst)
    print(f"run OK ({args.algo}): {len(parsed.ops)} ops, fixture "
          f"{parsed.fixture_sha256[:12]} -> {dst}")


if __name__ == "__main__":
    main()
