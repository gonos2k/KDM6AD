#!/usr/bin/env python3
"""Accept the PR #378 fixed native-column checkout; no host or RTTOV run."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np

REVISION = "30931e52f99e38f9abcd6e7e3b8cd055227a5c23"
INPUT_SHA256 = "be0edb894d1ddc5996f925cf01d56d1d882b53d6ed0295566edac2cb60f31308"


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("source", "input", "library", "output"):
        parser.add_argument(f"--{key}", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=args.source, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=args.source, text=True)
    if revision != REVISION or dirty or sha(args.input) != INPUT_SHA256:
        raise ValueError("acceptance requires the clean pinned source and retained native input")
    args.output.mkdir(parents=True)
    script = args.source / "oracle/scripts/run_normalized_dry_column.py"
    env = dict(os.environ, OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", OMP_THREAD_LIMIT="1", VECLIB_MAXIMUM_THREADS="1")
    common = [sys.executable, str(script), "--input", str(args.input), "--library", str(args.library), "--time-index", "1"]
    cases = []

    def run(label, flags, expected, message=None):
        command = common + flags
        completed = subprocess.run(command, cwd=args.source, env=env, text=True, capture_output=True, timeout=300)
        (args.output / f"{label}.stdout.txt").write_text(completed.stdout)
        (args.output / f"{label}.stderr.txt").write_text(completed.stderr)
        if completed.returncode != expected or (message and message not in completed.stderr):
            raise RuntimeError(f"unexpected {label} outcome: {completed.returncode}: {completed.stderr}")
        cases.append(dict(label=label, command=command, returncode=completed.returncode, expected_stderr=message))

    for label in ("success_1", "success_2"):
        run(label, ["--i", "3", "--j", "272", "--output", str(args.output / label)], 0)
        result = json.loads((args.output / label / "result.json").read_text())
        if (result["status"] != "NUMERICAL_PASS" or result["source_dirty"]
                or result["input_sha256"] != INPUT_SHA256 or result["library_sha256"] != sha(args.library)):
            raise RuntimeError("native success result does not bind the declared acceptance inputs")
    with np.load(args.output / "success_1/arrays.npz", allow_pickle=False) as a, np.load(args.output / "success_2/arrays.npz", allow_pickle=False) as b:
        if a.files != b.files or any(a[k].dtype != b[k].dtype or a[k].shape != b[k].shape or a[k].tobytes() != b[k].tobytes() for k in a.files):
            raise RuntimeError("two clean command executions differ")
    before = sha(args.output / "success_1/arrays.npz")
    run("existing_output", ["--i", "3", "--j", "272", "--output", str(args.output / "success_1")], 1, "output directory already exists")
    if before != sha(args.output / "success_1/arrays.npz"):
        raise RuntimeError("rejected overwrite changed the retained success output")
    run("outside_column", ["--i", "234", "--j", "272", "--output", str(args.output / "outside_column")], 1, "outside the input frame")
    run("unsupported_clear", ["--i", "72", "--j", "156", "--output", str(args.output / "unsupported_clear")], 1, "requires a nonzero input ice profile")
    for label in ("outside_column", "unsupported_clear"):
        if (args.output / label).exists():
            raise RuntimeError("rejected input created a normal result directory")
    result = dict(source_revision=revision, source_dirty=False, input_sha256=INPUT_SHA256,
        library_sha256=sha(args.library), runner_sha256=sha(script), acceptance_source_sha256=sha(__file__),
        success_runs=2, array_content_raw_bit_equal=True, rejection_cases=3, cases=cases,
        physical_number_basis_resolved=False, accepted_observation_cost=False, operational_approval=False,
        scope="Installed-library native-column CLI only; no KDM host forecast, RTTOV, or KMA window executed.")
    (args.output / "acceptance.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print("Two native numerical passes, raw-bit repeatability, and three expected rejections.")


if __name__ == "__main__":
    main()
