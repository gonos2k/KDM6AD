#!/usr/bin/env python3
"""Gate B / G3.3-M four-case check — the executable decision gate.

Reads the four legs (legacy/conservative x Fortran/C++), re-verifies every one, and
writes a deterministic result.json. It produces a TOOL verdict; the four-case verdict
on real data is the owner's adjudication, so this never edits STATUS or any gate file.

    gateb_g33m_check.py --cpp-bundle DIR \\
        --fortran-legacy legacy.g33f --fortran-conservative conservative.g33f \\
        --expected-manifest-sha256 HEX --expected-repo-commit SHA \\
        --out result.json

The external anchors are REQUIRED by default: a bundle that rewrites its own manifest
and sidecars stays self-consistent, so a decision needs a value held outside it. They
may be relaxed with --allow-unattested for local debugging, which stamps the result
`attested: false` — such a result must not be used to close C4.

Exit codes:  0 PASS   1 FAIL   2 INCONCLUSIVE   3 INVALID_EVIDENCE   4 usage/IO
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE / "g33_fortran"))
import g33_bundle_io as bio             # noqa: E402
import g33_fortran_dump as fd           # noqa: E402
import g33_fortran_semantics as sem     # noqa: E402
import g33_fourcase_comparator as cmp   # noqa: E402
import g33_normalize as nz              # noqa: E402

EXIT = {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2, "INVALID_EVIDENCE": 3}
EXIT_USAGE = 4


def _load_fortran(path: Path, algorithm: str, K: int, B: int) -> dict:
    """Parse + fully validate one Fortran leg, then normalize it."""
    run = fd.parse_fortran_run(path.read_text(), algorithm, K, B)
    sem.verify_semantics(run)          # causal checks
    fd.verify_offline_replay(run)      # stored update vs its own operands
    return nz.from_fortran_run(run)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="G3.3-M four-case decision gate")
    ap.add_argument("--cpp-bundle", type=Path, required=True,
                    help="run_cpp_abc.py --out bundle (both algorithms)")
    ap.add_argument("--fortran-legacy", type=Path, required=True)
    ap.add_argument("--fortran-conservative", type=Path, required=True)
    ap.add_argument("--expected-manifest-sha256")
    ap.add_argument("--expected-repo-commit")
    ap.add_argument("--expected-fixture-id",
                    help="which fixture this run is supposed to be (registry id). "
                         "An anchor like the other two: a bundle checked against the "
                         "fixture it declares attests nothing.")
    ap.add_argument("--allow-unattested", action="store_true",
                    help="debug only; the result is stamped attested:false")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)

    anchored = bool(a.expected_manifest_sha256 and a.expected_repo_commit
                    and a.expected_fixture_id)
    if not anchored and not a.allow_unattested:
        print("refusing to run without --expected-manifest-sha256, "
              "--expected-repo-commit and --expected-fixture-id "
              "(or --allow-unattested for debugging)", file=sys.stderr)
        return EXIT_USAGE
    fixture_id = a.expected_fixture_id or bio.gfx.DEFAULT_FIXTURE_ID
    # (B, K) are a PROPERTY of the fixture. Taken as separate arguments they could
    # disagree with the fixture actually named — invisible while every fixture
    # happens to be 3x4.
    try:
        authority = bio.gfx.load_manifest(bio.gfx.spec(fixture_id).manifest)
    except (bio.gfx.UnknownFixture, ValueError) as e:
        print(f"unusable fixture id: {e}", file=sys.stderr)
        return EXIT_USAGE
    B, K = authority["B"], authority["K"]

    result = {"verdict": None, "reason": None, "attested": anchored,
              "inputs": {"cpp_bundle": str(a.cpp_bundle),
                         "fortran_legacy": str(a.fortran_legacy),
                         "fortran_conservative": str(a.fortran_conservative),
                         "expected_fixture_id": fixture_id, "B": B, "K": K}}
    try:
        bundle = bio.verify_cpp_bundle(
            a.cpp_bundle, expected_manifest_sha256=a.expected_manifest_sha256,
            expected_repo_commit=a.expected_repo_commit,
            expected_fixture_id=fixture_id)
        legs = {
            "legacy_cpp": nz.from_cpp_evidence(bundle["algorithms"]["legacy"],
                                               require_verdict_ready=anchored),
            "conservative_cpp": nz.from_cpp_evidence(bundle["algorithms"]["conservative"],
                                                     require_verdict_ready=anchored),
            "legacy_fortran": _load_fortran(a.fortran_legacy, "legacy", K, B),
            "conservative_fortran": _load_fortran(a.fortran_conservative,
                                                  "conservative", K, B),
        }
    except Exception as e:                       # every reader is fail-closed
        result.update(verdict="INVALID_EVIDENCE", reason=f"{type(e).__name__}: {e}")
        _write(a.out, result)
        return EXIT["INVALID_EVIDENCE"]

    verdict = cmp.adjudicate_verified(legs["legacy_fortran"], legs["legacy_cpp"],
                                      legs["conservative_fortran"], legs["conservative_cpp"])
    result.update(verdict)
    result["scope"] = {
        "note": "A PASS certifies only that the observed Fortran<->C++ difference did "
                "not originate in conservative-only arithmetic. It does not certify "
                "column-number (rho*dz*nr) conservation, multi-subcycle behaviour "
                "beyond this fixture's mstep range, or meteorological accuracy.",
        "mstep_range": {k: list(v.mstep_range or ())
                        for k, v in bundle["algorithms"].items()},
    }
    _write(a.out, result)
    print(f"G3.3-M {result['verdict']}: {result['reason']}")
    return EXIT[result["verdict"]]


def _write(path: Path, result: dict) -> None:
    """Deterministic: sorted keys, stable separators, trailing newline."""
    path.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
