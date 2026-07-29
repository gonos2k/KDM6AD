#!/usr/bin/env python3
"""Gate B / G3.3-M four-case check — the executable decision gate.

Reads the four legs (legacy/conservative x Fortran/C++), re-verifies every one, and
writes a deterministic result.json. It produces a TOOL verdict; the four-case verdict
on real data is the owner's adjudication, so this never edits STATUS or any gate file.

    gateb_g33m_check.py --cpp-bundle DIR \\
        --fortran-legacy DIR --fortran-conservative DIR \\
        --expected-manifest-sha256 HEX --expected-repo-commit SHA \\
        --expected-fixture-id ID --expected-fixture-manifest-sha256 HEX \\
        --expected-fortran-legacy-manifest-sha256 HEX \\
        --expected-fortran-conservative-manifest-sha256 HEX \\
        --out result.json

All SIX anchors are required together: each pins one thing the bundle would
otherwise assert about itself. The Fortran arguments are run_fortran_abc.py --out
DIRECTORIES, not raw .g33f streams — a bare stream carries no build provenance to
verify.

The external anchors are REQUIRED by default: a bundle that rewrites its own manifest
and sidecars stays self-consistent, so a decision needs a value held outside it. They
may be relaxed with --allow-unattested for local debugging, which stamps the result
`attested: false` — such a result must not be used to close C4.

Exit codes
    0  PASS_MECHANISM     the tool's ceiling — NOT the protocol's PASS
    1  FAIL
    2  INCONCLUSIVE
    3  INVALID_EVIDENCE
    4  usage/IO
    5  UNATTESTED_MECHANISM_CANDIDATE   --allow-unattested; never shares 0

There is no bare PASS. The three verdict names are SHARED_SEED_CANDIDATE (internal),
PASS_MECHANISM (the tool's maximum) and PASS_C4 — the last reachable only by owner
adjudication over historical evidence this harness cannot hold.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE / "g33_fortran"))
import g33_bundle_io as bio             # noqa: E402
import g33_fortran_bundle_io as fbio    # noqa: E402
import g33_fourcase_comparator as cmp   # noqa: E402
import g33_fourcase_load as fcl  # noqa: E402
import g33_normalize as nz              # noqa: E402
import g33_dump as gd                   # noqa: E402

# PASS_MECHANISM, not PASS: the tool cannot reach the protocol's PASS, which also
# needs historical causality and downstream propagation. Exit 0 still means "the
# mechanism question came back clean", never "C4 may be released".
EXIT = {"PASS_MECHANISM": 0, "FAIL": 1, "INCONCLUSIVE": 2, "INVALID_EVIDENCE": 3,
        # A debug run must never share exit 0 with a decision. Automation that reads
        # only the return code would otherwise take one for the other.
        "UNATTESTED_MECHANISM_CANDIDATE": 5}
EXIT_USAGE = 4
#: A defect in this harness, not in the evidence. Distinct from INVALID_EVIDENCE so
#: an operator is not sent to audit a bundle that is fine.
EXIT_INTERNAL = 6




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
    ap.add_argument("--expected-fixture-manifest-sha256",
                    help="the fixture manifest BYTES, not just its name: the "
                         "verifier reads that JSON from its own working tree, so "
                         "the id alone anchors a string rather than the reviewed file")
    ap.add_argument("--expected-fortran-legacy-manifest-sha256",
                    help="external anchor for the legacy Fortran bundle")
    ap.add_argument("--expected-fortran-conservative-manifest-sha256",
                    help="external anchor for the conservative Fortran bundle")
    ap.add_argument("--expected-gate-a-scope-report-sha256", default=None,
                    help="external anchor for the Gate A report. Without it the "
                         "report is only self-consistent, and a self-consistent "
                         "report is exactly what a forgery produces.")
    ap.add_argument("--force", action="store_true",
                    help="replace an existing result.json. Off by default: a decision "
                         "artifact records one run, and overwriting loses the earlier "
                         "verdict without trace.")
    ap.add_argument("--gate-a-scope-report", type=Path, default=None,
                    help="check_cons_fortran_scope.py --json-out. Binds the "
                         "conservative leg's module to the source whose edits the "
                         "freeze-lift authorized: the toolchain check must ALLOW the "
                         "two legs to compile different modules, and allowing is not "
                         "authorizing.")
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
                    and a.expected_fixture_manifest_sha256
                    and a.expected_fortran_legacy_manifest_sha256
                    and a.expected_fortran_conservative_manifest_sha256)
    if not anchored and not a.allow_unattested:
        print("refusing to run without the external anchors for all four legs: "
              "--expected-manifest-sha256, --expected-repo-commit, "
              "--expected-fixture-id, --expected-fixture-manifest-sha256, "
              "--expected-fortran-legacy-manifest-sha256 and "
              "--expected-fortran-conservative-manifest-sha256 "
              "(or --allow-unattested for debugging)", file=sys.stderr)
        return EXIT_USAGE
    fixture_id = a.expected_fixture_id or bio.gfx.DEFAULT_FIXTURE_ID
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
    # ONE loader, shared with the evidence-artifact generator. Two loaders is how the
    # generator came to read the C++ bundle unanchored, parse Fortran stdout directly,
    # and compute its own first divergence from stages alone (owner P0-7).
    try:
        loaded = fcl.load_verified_fourcase(
            cpp_bundle=a.cpp_bundle, fortran_legacy=a.fortran_legacy,
            fortran_conservative=a.fortran_conservative,
            expected_manifest_sha256=a.expected_manifest_sha256,
            expected_repo_commit=a.expected_repo_commit,
            expected_fixture_id=a.expected_fixture_id,
            expected_fixture_manifest_sha256=a.expected_fixture_manifest_sha256,
            expected_fortran_legacy_manifest_sha256=(
                a.expected_fortran_legacy_manifest_sha256),
            expected_fortran_conservative_manifest_sha256=(
                a.expected_fortran_conservative_manifest_sha256),
            gate_a_scope_report=a.gate_a_scope_report,
            expected_gate_a_scope_report_sha256=(
                a.expected_gate_a_scope_report_sha256))
    except fcl.EVIDENCE_ERRORS as e:
        # EVIDENCE errors only. A blanket `except Exception` also turned a defect in
        # this harness into INVALID_EVIDENCE, which reads as "the bundle is bad" and
        # sends the reader to look at the wrong thing. Anything else exits 6.
        result["fixture_identity"] = {
            "fixture_id": authority["fixture_id"],
            "fixture_manifest_sha256": bio.gfx.manifest_sha256(authority),
            "fixture_sha256": bio.gfx.fixture_sha256(authority),
            "parameter_sha256": bio.gfx.parameter_sha256(authority),
            "fortran_parameter_sha256": bio.gfx.fortran_parameter_sha256(authority)}
        result.update(verdict="INVALID_EVIDENCE", reason=f"{type(e).__name__}: {e}")
        _write(a.out, result, force=a.force)
        return EXIT["INVALID_EVIDENCE"]
    result["fixture_identity"] = loaded.fixture_identity
    cpp_legs = loaded.cpp_legs

    # `attested` is what the LEGS reported, not what the caller asked for. Four legs
    # or the word overstates the check: the C++ side was externally anchored long
    # before the Fortran side had a bundle to anchor.
    result["attestation"] = loaded.attestation
    result["attested"] = loaded.attested
    # The decision API takes a TYPE, not four dicts: normalized runs carry no
    # attestation, and a verdict built from them would describe evidence nobody
    # anchored. An unattested debug load has no `evidence`, so it goes down a path
    # that cannot promote.
    result.update(loaded.verdict())
    result["scope"] = {
        "note": "A PASS_MECHANISM certifies only that the observed Fortran<->C++ "
                "difference did "
                "not originate in conservative-only arithmetic. It does not certify "
                "column-number (rho*dz*nr) conservation, multi-subcycle behaviour "
                "beyond this fixture's mstep range, or meteorological accuracy.",
        "mstep_range": {k: list(v.mstep_range or ()) for k, v in cpp_legs.items()},
    }
    _write(a.out, result, force=a.force)
    print(f"G3.3-M {result['verdict']}: {result['reason']}")
    return EXIT[result["verdict"]]


def _write(path: Path, result: dict, *, force: bool = False) -> None:
    """Deterministic, atomic, and no-clobber.

    A decision artifact is the record of one run. Overwriting an existing one in
    place loses the earlier verdict with no trace, and a partial write on
    interruption leaves a file that parses but describes nothing that happened.
    """
    if path.exists() and not force:
        raise SystemExit(
            f"refusing to overwrite an existing decision artifact: {path} "
            f"(move it aside, or pass --force to replace it deliberately)")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n")
    tmp.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
