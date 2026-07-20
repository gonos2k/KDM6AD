#!/usr/bin/env python3
"""Build the environment a G3.3-M diagnostic run needs, and seal what it points at.

The overlay refuses to run on a partial configuration, and each tightening added
another required variable — schema dir, sealed digests, op-seq windows. Nothing
produced them: the documented invocation still named three variables while the
producer required eleven, so no diagnostic run could start at all. This is the
other half of that contract.

Everything the overlay is told is derived here from one schedule, so the
declaration the producer checks itself against and the expectation the comparator
uses afterwards cannot drift apart — they are the same object, sealed once.

    env = build_env(schedule, outdir, binary=..., column_map=..., run_uuid=...)
    subprocess.run([...], env={**os.environ, **env})

As a CLI it prints shell exports:

    python3 harness/g33_run_env.py --schedule s.json --outdir /tmp/g33 \
        --binary libkdm6ad.dylib --column-map map.json --run-uuid $(uuidgen)
"""
from __future__ import annotations

import argparse
import hashlib
import os
import json
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g33_dump as gd
import g33_expectation as ge


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_head(repo: Path) -> str:
    """HEAD, and only if HEAD actually describes the working tree.

    A dirty tree means the recorded commit does not describe the source that was
    compiled, so stamping it onto the evidence claims a provenance that does not
    hold. Refuse rather than record a commit the run did not come from.
    """
    r = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"cannot resolve producer commit: {r.stderr.strip()}")
    d = subprocess.run(["git", "-C", str(repo), "status", "--porcelain",
                        "--untracked-files=no"], capture_output=True, text=True)
    if d.returncode:
        raise RuntimeError(f"cannot determine tree state: {d.stderr.strip()}")
    if d.stdout.strip():
        raise RuntimeError(
            "refusing to stamp evidence with a commit that does not describe the "
            "tree: " + ", ".join(l[3:] for l in d.stdout.strip().splitlines()[:5]))
    return r.stdout.strip()


# Everything the DIAGNOSTIC dylib is compiled from. The first two are the whole
# point: the instrumented translation unit and the container writer are what an
# instrumentation change actually edits, so a guard that watched only the
# canonical tree passed the most likely staleness in this workflow — edit the
# overlay, forget to rebuild, and the evidence carries a commit whose overlay is
# not the one inside the binary.
#
# Deliberately NOT listed: verify_overlay.py, BASE_SHA256_*, test_g33_writer.cpp.
# None of them is compiled into the dylib, and a guard that fires on edits which
# cannot affect the artifact gets switched off by whoever hits it.
_BUILD_INPUTS = (
    "harness/g33_overlay/sedimentation.cpp.overlay",
    "harness/g33_overlay/g33_op_dump.h",
    "harness/g33_overlay/g33_op_trace.h",
    "libtorch/src",
    "libtorch/include",
    "libtorch/CMakeLists.txt",
)


def _check_binary_not_stale(binary: Path, repo: Path) -> None:
    """Refuse a binary older than any input the diagnostic build compiles.

    PRODUCER_COMMIT and BINARY_SHA256 are two independent facts; nothing makes
    them describe the same artifact. A dylib built days ago still gets stamped
    with today's HEAD, and the digest — being a real hash of a real file — looks
    like proof. This does not BIND them (only the runtime dladdr check in P0-5
    establishes that the process loaded this file); it rejects the case where
    they provably disagree.
    """
    # -z + BINARY output. Whitespace-splitting fragmented a path with a space
    # into tokens that exist nowhere, so is_file() skipped them and that build
    # input silently LEFT the guard. The first fix kept text=True, which implies
    # universal-newline translation: a '\r' in a filename came back as '\n',
    # the path no longer existed, and the same fail-open survived one layer
    # down. Bytes end-to-end — NUL split, os.fsdecode per path (surrogateescape
    # round-trips arbitrary filename bytes) — leaves no translation step to
    # lose a file through.
    r = subprocess.run(["git", "-C", str(repo), "ls-files", "-z", *_BUILD_INPUTS],
                       capture_output=True)
    if r.returncode:
        return                                  # not a checkout we can reason about
    newest, newest_src = 0.0, None
    for rel in map(os.fsdecode, filter(None, r.stdout.split(b"\0"))):
        f = repo / rel
        if f.is_file() and f.stat().st_mtime > newest:
            newest, newest_src = f.stat().st_mtime, rel
    if newest_src and binary.stat().st_mtime < newest:
        raise RuntimeError(
            f"binary {binary.name} is older than {newest_src} — it was not built "
            f"from the tree this run would stamp onto the evidence")


def build_env(schedule: dict, outdir, *, binary, column_map, run_uuid,
              column_layout_id, repo=None) -> dict:
    """Seal the descriptors and return the complete overlay environment.

    binary is hashed HERE rather than taken as a string: a caller-supplied digest
    attests to nothing about the artifact the run actually loads. (Confirming
    that the loaded dylib is this file is a separate check — see P0-5 — but a
    digest of a real file on disk is the floor, not a value typed into an export.)
    """
    outdir = Path(outdir)
    binary = Path(binary)
    if not binary.is_file():
        raise FileNotFoundError(f"binary not found: {binary}")
    if not run_uuid:
        raise ValueError("run_uuid is required — it ties containers to one run")
    for _nm, _v in (("run_uuid", run_uuid), ("case_id", schedule["case_id"]),
                    ("pair_id", schedule["pair_id"]),
                    ("column_layout_id", column_layout_id)):
        gd._require_safe_id(_nm, _v)
    qcrmin = schedule.get("qcrmin")
    if not isinstance(qcrmin, float) or not qcrmin > 0:
        raise ValueError(
            "schedule must declare qcrmin (positive float) — the floor authority "
            "compares raw operands against THIS threshold (owner review §2.2), "
            "and a threshold rediscovered per call site is not a contract")
    # Same validator the reader/writer share. Without this, a malformed map is
    # only caught when the overlay opens its first container — deep inside the
    # physics run, after the whole setup cost has been paid.
    gd._validate_column_map(column_map, int(schedule["B"]))

    _repo = Path(repo or Path(__file__).parent.parent)
    _check_binary_not_stale(binary, _repo)

    schema_dir = outdir / "schema"
    dump_dir = outdir / "dump"
    dump_dir.mkdir(parents=True, exist_ok=True)

    shas = ge.write_descriptors(schedule, schema_dir)
    index = ge.run_index(schedule)

    env = {
        "KDM6_G33_DUMP_DIR": str(dump_dir),
        "KDM6_G33_CASE_ID": schedule["case_id"],
        "KDM6_G33_PAIR_ID": schedule["pair_id"],
        "KDM6_G33_RUN_UUID": run_uuid,
        "KDM6_G33_PRODUCER_COMMIT": _git_head(_repo),
        "KDM6_G33_BINARY_SHA256": _sha256_file(binary),
        "KDM6_G33_COLUMN_LAYOUT_ID": column_layout_id,
        "KDM6_G33_COLUMN_MAP": json.dumps(column_map, separators=(",", ":")),
        "KDM6_G33_OP_SEQ_MAP": ge.op_seq_map(index),
        "KDM6_G33_SCHEMA_DIR": str(schema_dir),
        "KDM6_G33_SCHEMA_SHA256": ge.schema_sha_map(shas),
    }
    missing = [k for k, v in env.items() if not v]
    if missing:
        raise ValueError(f"refusing to emit an environment with empty {missing}")

    # P0-6: the run contract is a PERSISTED artifact, not eleven environment
    # variables that die with the shell. Without it, reconstructing what a run
    # was sealed against (container set, windows, descriptor digests, threshold,
    # binary identity) requires having saved the environment separately — which
    # nobody does. Written before the env is handed out, no-clobber: one
    # contract per run, and an outdir reused across runs must fail loudly
    # rather than silently mixing two runs' evidence.
    contract = {
        "format": "KDG33-RUN-CONTRACT",
        "version": 1,
        "run_uuid": run_uuid,
        "case_id": schedule["case_id"],
        "pair_id": schedule["pair_id"],
        "producer_commit": env["KDM6_G33_PRODUCER_COMMIT"],
        "binary_path": str(binary),
        "binary_sha256": env["KDM6_G33_BINARY_SHA256"],
        "column_layout_id": column_layout_id,
        "column_map": column_map,
        "qcrmin": qcrmin,
        "schedule": schedule,
        "schedule_sha256": hashlib.sha256(
            json.dumps(schedule, sort_keys=True).encode()).hexdigest(),
        "containers": [
            {**{k: c[k] for k in ("container_id", "outer_loop", "chain", "n",
                                  "first_op_seq_id", "last_op_seq_id",
                                  "record_count", "path")},
             "descriptor_sha256": shas[c["container_id"]]}
            for c in index["containers"]
        ],
    }
    contract_path = outdir / "run_contract.json"
    if contract_path.exists():
        raise FileExistsError(
            f"{contract_path} already exists — one contract per run; refusing "
            f"to overwrite another run's seal")
    body = json.dumps(contract, sort_keys=True, indent=1).encode()
    contract_path.write_bytes(body)
    (outdir / "run_contract.sha256").write_text(
        hashlib.sha256(body).hexdigest() + "  run_contract.json\n")
    return env


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--schedule", required=True, help="schedule JSON")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--binary", required=True, help="the dylib the run will load")
    ap.add_argument("--column-map", required=True, help="declared column map JSON")
    ap.add_argument("--column-layout-id", required=True)
    ap.add_argument("--run-uuid", required=True)
    a = ap.parse_args()

    env = build_env(json.loads(Path(a.schedule).read_text()), a.outdir,
                    binary=a.binary,
                    column_map=json.loads(Path(a.column_map).read_text()),
                    run_uuid=a.run_uuid, column_layout_id=a.column_layout_id)
    for k, v in env.items():
        # shlex.quote, not json.dumps: a JSON string is DOUBLE quoted, and inside
        # double quotes a shell still expands $(...), backticks and backslashes.
        # `--run-uuid '$(...)'` would execute on eval. Single-quoted output does
        # not expand anything.
        print(f"export {k}={shlex.quote(v)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
