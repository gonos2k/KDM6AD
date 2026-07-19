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
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g33_expectation as ge


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_head(repo: Path) -> str:
    r = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"cannot resolve producer commit: {r.stderr.strip()}")
    return r.stdout.strip()


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
        "KDM6_G33_PRODUCER_COMMIT": _git_head(Path(repo or Path(__file__).parent.parent)),
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
        print(f"export {k}={json.dumps(v)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
