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
import g33_fortran_bundle_io as fbio    # noqa: E402
import g33_fortran_dump as fd           # noqa: E402
import g33_fortran_semantics as sem     # noqa: E402
import g33_fourcase_comparator as cmp   # noqa: E402
import g33_normalize as nz              # noqa: E402

EXIT = {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2, "INVALID_EVIDENCE": 3}
EXIT_USAGE = 4


def _load_fortran(bundle: Path, algorithm: str, *, manifest_sha, commit,
                  fixture_id, anchored: bool) -> tuple:
    """Re-verify one Fortran A/B/C bundle, then normalize its instrumented lane.

    Returns (VerifiedFortranLeg, normalized run). The leg is what carries the
    attestation state; the normalized run is what the comparator sees."""
    leg = fbio.verify_fortran_bundle(
        bundle, algorithm, expected_manifest_sha256=manifest_sha,
        expected_repo_commit=commit, expected_fixture_id=fixture_id)
    if anchored and not leg.verdict_ready:
        raise fbio.FortranBundleError(
            f"{algorithm} Fortran leg is not verdict_ready "
            f"(bundle_verified={leg.bundle_verified} "
            f"manifest={leg.external_manifest_attested} "
            f"commit={leg.source_commit_attested} "
            f"fixture={leg.fixture_attested} clean={leg.repo_clean})")
    return leg, nz.from_fortran_run(leg.run)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="G3.3-M four-case decision gate")
    ap.add_argument("--cpp-bundle", type=Path, required=True,
                    help="run_cpp_abc.py --out bundle (both algorithms)")
    ap.add_argument("--fortran-legacy", type=Path, required=True,
                    metavar="BUNDLE_DIR",
                    help="run_fortran_abc.py --out directory (not a raw .g33f): the "
                         "stream alone carries no compiler, source or fixture binding")
    ap.add_argument("--fortran-conservative", type=Path, required=True,
                    metavar="BUNDLE_DIR")
    ap.add_argument("--expected-fortran-legacy-manifest-sha256",
                    help="external anchor for the legacy Fortran bundle")
    ap.add_argument("--expected-fortran-conservative-manifest-sha256",
                    help="external anchor for the conservative Fortran bundle")
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

    # ALL FOUR legs, or the word "attested" overstates what was checked.
    anchored = bool(a.expected_manifest_sha256 and a.expected_repo_commit
                    and a.expected_fixture_id
                    and a.expected_fortran_legacy_manifest_sha256
                    and a.expected_fortran_conservative_manifest_sha256)
    if not anchored and not a.allow_unattested:
        print("refusing to run without the external anchors for all four legs: "
              "--expected-manifest-sha256, --expected-repo-commit, "
              "--expected-fixture-id, "
              "--expected-fortran-legacy-manifest-sha256 and "
              "--expected-fortran-conservative-manifest-sha256 "
              "(or --allow-unattested for debugging)", file=sys.stderr)
        return EXIT_USAGE
    fixture_id = a.expected_fixture_id or bio.gfx.DEFAULT_FIXTURE_ID
    # (B, K) are a PROPERTY of the fixture. Taken as separate arguments they could
    # disagree with the fixture actually named — invisible while every fixture
    # happens to be 3x4.
    try:
        _, authority = bio.gfx.load_fixture(fixture_id)
    except (bio.gfx.UnknownFixture, ValueError) as e:
        print(f"unusable fixture id: {e}", file=sys.stderr)
        return EXIT_USAGE
    B, K = authority["B"], authority["K"]

    result = {"verdict": None, "reason": None, "attested": False,
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
        }
        fortran_legs = {}
        for algo, bundle, sha in (
                ("legacy", a.fortran_legacy,
                 a.expected_fortran_legacy_manifest_sha256),
                ("conservative", a.fortran_conservative,
                 a.expected_fortran_conservative_manifest_sha256)):
            fortran_legs[algo], legs[f"{algo}_fortran"] = _load_fortran(
                bundle, algo, manifest_sha=sha,
                commit=a.expected_repo_commit, fixture_id=a.expected_fixture_id,
                anchored=anchored)
    except Exception as e:                       # every reader is fail-closed
        result.update(verdict="INVALID_EVIDENCE", reason=f"{type(e).__name__}: {e}")
        _write(a.out, result)
        return EXIT["INVALID_EVIDENCE"]

    # `attested` is what the LEGS reported, not what the caller asked for. Four legs
    # or the word overstates the check: the C++ side was externally anchored long
    # before the Fortran side had a bundle to anchor.
    per_leg = {f"{algo}_cpp": bundle["algorithms"][algo] for algo in ("legacy",
                                                                     "conservative")}
    per_leg.update({f"{algo}_fortran": leg for algo, leg in fortran_legs.items()})
    result["attestation"] = {
        name: {"verdict_ready": bool(leg.verdict_ready),
               "external_manifest": bool(leg.external_manifest_attested),
               "source_commit": bool(leg.source_commit_attested),
               "fixture": bool(leg.fixture_attested)}
        for name, leg in sorted(per_leg.items())}
    result["attested"] = all(leg.verdict_ready for leg in per_leg.values())

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
