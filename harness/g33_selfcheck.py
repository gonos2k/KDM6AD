#!/usr/bin/env python3
"""G3.3 self-check (§5a): shadow == actual == offline, on real containers.

Runs the instrumented substep chain (one FRESH PROCESS per algorithm) under a
sealed environment, then verifies from the EVIDENCE alone:

  1. container-set completeness — the files on disk are exactly the sealed
     run-index set, and every container reads fail-closed;
  2. shadow == actual — the diagnostic shadow ladder's final f32 equals the
     ACTUAL falk bits, per record (§5a shadow-fidelity);
  3. offline == shadow — an independent NumPy recomputation FROM THE DUMPED
     OPERANDS reproduces every FALK rung bit-for-bit (same IEEE ops, same
     promotion: f32*f32→f32, f32*f64→f64, one final f32 rounding);
  4. producer cross-checks — check_producer_flags per substep (gate law
     n<=mstep, mstep range, floor semantics against qcrmin).

The offline recomputation uses ONLY dumped payloads (q_before, dend_raw,
work1/workn, mstep_native, gate_native) — never the driver's fixture — so a
driver/fixture bug cannot vacuously agree with itself.

    python3 harness/g33_selfcheck.py [--driver /path/to/selfcheck_driver]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import shutil
import tempfile
import uuid
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g33_derived as gdv
import g33_dump as gd
import g33_expectation as ge
import g33_run_env as gre

B, K, MSTEPMAX, QCRMIN, DTCLD = 3, 4, 2, 1.0e-9, 20.0   # DTCLD matches selfcheck_driver.cpp

# Failure CLASSES by exit code — the discrimination a wrapped child cannot
# forge. Driver stdout/stderr is interpolated into failure messages, so child-
# controlled text can become the terminal line; the parent's exit code cannot.
# The kill gate accepts ONLY EXIT_FIDELITY.
EXIT_SKIP, EXIT_DRIVER, EXIT_EVIDENCE, EXIT_FIDELITY = 2, 3, 4, 5


def _die(code: int, msg: str):
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def _sched(algorithm: str) -> dict:
    return {"case_id": "selfcheck", "pair_id": "selfpair", "backend": "cpp",
            "algorithm": algorithm, "B": B, "K": K, "loops": 1,
            "mstepmax_main": [MSTEPMAX], "mstepmax_ice": [1],
            "species_scope": ["qr", "nr"], "qcrmin": QCRMIN, "dtcld": DTCLD,
            "instrumented_stages": ["substep_pre", "op", "substep_post"]}


def _payload(recs, **key):
    hits = [r for r in recs if all(r.get(k) == v for k, v in key.items())]
    if len(hits) != 1:
        _die(EXIT_EVIDENCE, f"FAIL: {len(hits)} records match {key} (want exactly 1)")
    return hits[0]


def _np(dtype, payload):
    kind = {"f32": ">f4", "f64": ">f8", "i32": ">i4", "u8": ">u1"}[dtype]
    return np.frombuffer(payload, dtype=kind).astype(
        {"f32": np.float32, "f64": np.float64,
         "i32": np.int32, "u8": np.uint8}[dtype])


def _bits(a, dt):
    # container payloads are BIG-endian per element; a native tobytes() would
    # compare LE bytes against BE payloads and fail on identical values
    return a.astype({"f32": ">f4", "f64": ">f8"}[dt]).tobytes()


def check_algorithm(driver: Path, algorithm: str, workdir: Path) -> dict:
    sched = _sched(algorithm)
    run_uuid = f"selfcheck-{algorithm}-{uuid.uuid4().hex[:12]}"
    env = gre.build_env(sched, workdir, binary=driver,
                        column_map=[[i, 0, i, i] for i in range(B)],
                        run_uuid=run_uuid, column_layout_id="selfcheck-3col")
    r = subprocess.run([str(driver), algorithm], env={**os.environ, **env},
                       capture_output=True, text=True)
    if r.returncode != 0:
        _die(EXIT_DRIVER, f"FAIL: driver rc={r.returncode}\n{r.stdout}{r.stderr}")

    # bind the comparator to the SEALED contract, not the module constants: a
    # drifted schedule would then be caught by the qcrmin/dtcld bit checks
    # rather than silently agreeing with a hardcoded fixture value.
    contract = json.loads((workdir / "run_contract.json").read_text())
    seal_qcrmin, seal_dtcld = contract["qcrmin"], contract["dtcld"]

    # 1. container-set completeness: exactly the sealed set, nothing else
    index = ge.run_index(sched)
    dump_dir = Path(env["KDM6_G33_DUMP_DIR"])
    on_disk = sorted(p.name for p in dump_dir.glob("*.g33"))
    expected = sorted(c["path"] for c in index["containers"])
    if on_disk != expected:
        _die(EXIT_EVIDENCE,
             f"FAIL container set:\n  disk    {on_disk}\n  sealed  {expected}")

    stats = {"containers": 0, "shadow_actual": 0, "offline_rungs": 0, "flags": 0}
    for c in index["containers"]:
        cont = gd.read_container(dump_dir / c["path"])       # fail-closed
        recs = cont["records"]
        n_sub = c["n"]
        stats["containers"] += 1

        pre = {r["field"]: (r["dtype"], r["payload"])
               for r in recs if r["stage"] == "substep_pre"}
        gdv.check_producer_flags(pre, n_sub, seal_qcrmin, seal_dtcld)
        stats["flags"] += 1

        dend = _np(*pre["dend_raw"]).reshape(B, K)
        w1 = _np(*pre["work1_qr"]).reshape(B, K)
        wn = _np(*pre["workn_qr"]).reshape(B, K)
        mstep = _np(*pre["mstep_native"])
        gate = _np(*pre["gate_native"])

        for k in range(K):
            for sp, op, before_op, before_f in (
                    ("qr", "QR_FALK", "QR_UPDATE", "q_before"),
                    ("nr", "NR_FALK", "NR_UPDATE", "n_before")):
                rec = lambda opid, f: _payload(recs, stage="op", k=k,
                                               species=sp, op_id=opid, field=f)
                entry = _np("f32", rec(before_op, before_f)["payload"])

                # offline FALK ladder from DUMPED operands, IEEE step by step
                if sp == "qr":
                    # overlay computes dend_col(k) * entry — operand order kept
                    s1 = dend[:, k] * entry                       # f32*f32 -> f32
                    s2 = s1 * w1[:, k]                            # f32*f64 -> f64
                    off = [("mul_dend_q", "f32", _bits(s1, "f32"))]
                else:
                    s2 = entry * wn[:, k]                         # f32*f64 -> f64
                    off = []
                s3 = s2 / mstep                                   # f64/f64 -> f64
                s4 = s3 * gate                                    # f64*f32 -> f64
                shadow = s4.astype(np.float32)                    # ONE rounding
                off += [("mul_work1" if sp == "qr" else "mul_workn", "f64", _bits(s2, "f64")),
                        ("div_mstep", "f64", _bits(s3, "f64")),
                        ("falk_precast", "f64", _bits(s4, "f64")),
                        ("shadow_falk_f32", "f32", _bits(shadow, "f32"))]
                for field, dt, want in off:
                    have = rec(op, field)
                    if have["dtype"] != dt or have["payload"] != want:
                        _die(EXIT_FIDELITY,
                             f"FAIL offline!=dumped: {algorithm} {c['container_id']} "
                             f"k={k} {sp} {op}.{field}")
                    stats["offline_rungs"] += 1

                # shadow == actual (§5a)
                sh = rec(op, "shadow_falk_f32")["payload"]
                ac = rec(op, "falk_f32")["payload"]
                if sh != ac:
                    _die(EXIT_FIDELITY,
                         f"FAIL shadow!=actual: {algorithm} {c['container_id']} "
                         f"k={k} {sp}")
                stats["shadow_actual"] += 1
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--driver", default="/tmp/g33_selfcheck_build/selfcheck_driver")
    a = ap.parse_args()
    driver = Path(a.driver)
    if not driver.is_file():
        print(f"SKIP: driver not built ({driver}) — run selfcheck_build.sh first")
        return EXIT_SKIP
    # Clean up ONLY on success. A failing run leaves its evidence directory in
    # place for forensics — the same reason build_env keeps a partial run
    # (auto-cleanup would destroy what a mismatch needs to be diagnosed from).
    # _die() exits without returning, so a failure never reaches the rmtree.
    root = Path(tempfile.mkdtemp(prefix="g33_selfcheck."))
    try:
        for algorithm in ("legacy", "conservative"):
            try:
                stats = check_algorithm(driver, algorithm, root / algorithm)
            except gd.G33Corruption as e:
                _die(EXIT_EVIDENCE, f"FAIL evidence: {algorithm}: {e}")
            print(f"{algorithm}: PASS — {stats['containers']} containers, "
                  f"{stats['shadow_actual']} shadow==actual, "
                  f"{stats['offline_rungs']} offline rungs bit-exact, "
                  f"{stats['flags']} producer cross-checks")
    except SystemExit as e:
        # ANY failure keeps the evidence and reports where — the forensic
        # contract must not depend on which failure class fired (the fidelity
        # path _die's from inside check_algorithm without root in scope).
        if e.code:
            print(f"(evidence preserved at {root})", file=sys.stderr)
        raise
    shutil.rmtree(root, ignore_errors=True)     # success only
    print("SELF-CHECK PASS: shadow == actual == offline, both algorithms")
    print("  (fixture: valid_metric + arithmetic_synthetic — branch coverage, "
          "NOT a meteorological representativeness claim)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
