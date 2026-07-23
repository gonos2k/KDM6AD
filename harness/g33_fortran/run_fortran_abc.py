#!/usr/bin/env python3
"""Run the full Fortran A/B/C for one algorithm and persist a decision-grade
evidence bundle (owner P0: A/B/C must survive as immutable artifacts, not vanish
with a pytest tempdir).

  A = canonical module
  B = generated overlay, dump macro OFF
  C = same generated overlay, dump macro ON

Verifies A==B==C raw-bit (final state + precip), A and B emit zero op records, C
is strict-parseable + offline-replay-clean + bound to the shared fixture, then
writes to <out>:
    {A,B,C}/stdout.g33f, {A,B,C}/stderr.txt         (raw streams)
    C/normalized_ops.json                            (parsed op ladder)
    C/run_manifest.json                              (the instrumented run)
    abc_manifest.json                                (the A/B/C adjudication)
sha256(stdout.g33f) is re-checkable against the manifest.

    run_fortran_abc.py --algo legacy|conservative --out <fresh_dir>
"""
import argparse
import dataclasses
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
import g33_fortran_dump as fd          # noqa: E402
import g33_fixture_v1 as fixture       # noqa: E402


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _sha_path(p):
    with open(p, "rb") as f:
        return _sha(f.read())


def _git(*a):
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True,
                          text=True, check=False).stdout.strip()


def _build_run(sub, algo, flags):
    r = subprocess.run(["bash", os.path.join(HERE, "fortran_build.sh"), sub,
                        f"--algo={algo}", *flags], cwd=ROOT,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"build failed ({flags}):\n{r.stdout}\n{r.stderr}")
    exe = os.path.join(sub, "g33_fortran_driver")
    run = subprocess.run([exe], capture_output=True)
    if run.returncode != 0:
        raise SystemExit(f"driver crashed ({flags}):\n{run.stderr.decode('replace')}")
    return exe, run.stdout, run.stderr


def _write(path, data):
    tmp = path + ".tmp"
    mode = "wb" if isinstance(data, bytes) else "w"
    with open(tmp, mode) as f:
        f.write(data)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--algo", required=True, choices=["legacy", "conservative"])
    ap.add_argument("--out", required=True, help="fresh output directory")
    args = ap.parse_args()

    authority = fixture.load_manifest()
    B, K = authority["B"], authority["K"]
    os.makedirs(args.out)
    cases = {"A": [], "B": ["--overlay"], "C": ["--dump"]}
    out = {}
    for name, flags in cases.items():
        sub = os.path.join(args.out, name)
        exe, so, se = _build_run(sub, args.algo, flags)
        _write(os.path.join(sub, "stdout.g33f"), so)
        _write(os.path.join(sub, "stderr.txt"), se)
        out[name] = {"exe": exe, "stdout": so, "stderr": se}

    # A/B/C all go through the SAME strict parser (A/B in noninstrumented mode:
    # zero MSTEP/OP but the same bracketed, exact-universe, finite, domain-valid
    # inputs/state) — a malformed A/B stream can no longer masquerade as a clean
    # non-invasiveness result.
    runs = {n: fd.parse_fortran_run(
        out[n]["stdout"].decode(), args.algo, K=K, B=B,
        evidence_mode="instrumented" if n == "C" else "noninstrumented")
        for n in cases}
    abc_equal = (runs["A"].state == runs["B"].state == runs["C"].state
                 and runs["A"].precip == runs["B"].precip == runs["C"].precip)
    if not abc_equal:
        raise SystemExit("A/B/C final state or precip differ — NOT non-invasive")

    parsed = runs["C"]
    fd.verify_offline_replay(parsed)
    if parsed.fixture_sha256 != fixture.fixture_sha256(authority):
        raise SystemExit("C FIXIN differs from the shared authority")
    if parsed.parameter_sha256 != fixture.parameter_sha256(authority):
        raise SystemExit("C common PARAM differs from the shared authority")
    if parsed.local_parameter_sha256 != fixture.fortran_parameter_sha256(authority):
        raise SystemExit("C ccn0/scale_h differ from the authority")

    # Bind A/B/C BUILD provenance into the root, and enforce the cross-build
    # invariants that make A/B/C the same numerical problem (owner P0-4):
    prov = {n: json.load(open(os.path.join(args.out, n, "provenance.json")))
            for n in cases}
    _hw = {"f32": 8, "f64": 16, "u8": 2}
    if prov["A"]["module_compiled_sha256"] != prov["A"]["module_canonical_sha256"]:
        raise SystemExit("A did not compile the canonical module")
    if prov["B"]["module_compiled_sha256"] != prov["C"]["module_compiled_sha256"]:
        raise SystemExit("B and C did not compile the same generated overlay")
    for field in ("module_canonical_sha256", "compiler_binary_sha256",
                  "host_source_sha256", "harness_source_sha256"):
        if not (prov["A"][field] == prov["B"][field] == prov["C"][field]):
            raise SystemExit(f"A/B/C differ in {field}")

    # normalized_ops is a DEBUG cache, not the authority (the comparator re-reads
    # C/stdout.g33f); bits are dtype-width hex (JSON decimals lose f64 precision).
    def _op_json(o):
        d = dataclasses.asdict(o)
        d["bits"] = f"{o.bits:0{_hw[o.dtype]}x}"
        return d
    norm = json.dumps([_op_json(o) for o in parsed.ops], indent=1).encode()
    _write(os.path.join(args.out, "C", "normalized_ops.json"), norm)

    build = prov["C"]
    manifest = {
        "schema_version": 2,
        "algorithm": args.algo,
        "repo_commit": _git("rev-parse", "HEAD"),
        "repo_dirty": bool(_git("status", "--porcelain")),
        "fixture_id": authority["fixture_id"],
        "fixture_manifest_sha256": fixture.manifest_sha256(authority),
        "fixture_sha256": parsed.fixture_sha256,
        "parameter_sha256": parsed.parameter_sha256,
        "fortran_parameter_sha256": parsed.local_parameter_sha256,
        "abc_equal": abc_equal,
        "mstep_per_column": parsed.mstep,
        "op_record_count": len(parsed.ops),
        "executable_sha256": {n: _sha_path(out[n]["exe"]) for n in cases},
        "stdout_sha256": {n: _sha(out[n]["stdout"]) for n in cases},
        "stderr_sha256": {n: _sha(out[n]["stderr"]) for n in cases},
        "build_provenance_sha256": {n: _sha_path(
            os.path.join(args.out, n, "provenance.json")) for n in cases},
        "normalized_ops_sha256": _sha(norm),
        "normalized_ops_source_stdout_sha256": _sha(out["C"]["stdout"]),
        "module_canonical_sha256": build["module_canonical_sha256"],
        "module_compiled_sha256": {"A": prov["A"]["module_compiled_sha256"],
                                   "BC": prov["C"]["module_compiled_sha256"]},
        "compiler_path": build["compiler_path"],
        "compiler_binary_sha256": build["compiler_binary_sha256"],
        "compiler_version": build["compiler_version"],
        "os": platform.platform(), "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "host_source_sha256": build["host_source_sha256"],
        "harness_source_sha256": build["harness_source_sha256"],
    }
    _write(os.path.join(args.out, "abc_manifest.json"),
           json.dumps(manifest, indent=2, sort_keys=True))
    print(f"A/B/C bundle OK ({args.algo}): {len(parsed.ops)} ops, "
          f"A==B==C={abc_equal} -> {args.out}/abc_manifest.json")


if __name__ == "__main__":
    main()
