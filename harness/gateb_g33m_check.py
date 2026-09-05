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
import platform
import hashlib
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE / "g33_fortran"))
import numpy as np                      # noqa: E402
import g33_bundle_io as bio             # noqa: E402
import g33_fortran_bundle_io as fbio    # noqa: E402
import g33_verifier_identity as vid     # noqa: E402
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

# Only these tool verdicts can describe a decision-grade four-case load. An
# unattested mechanism candidate is deliberately a separate value and
# INVALID_EVIDENCE is an evidence failure, even when a caller supplies otherwise
# plausible metadata.
_DECISION_VERDICTS = frozenset(("PASS_MECHANISM", "FAIL", "INCONCLUSIVE"))


def _decision_grade(result: dict) -> bool:
    """Whether *result* satisfies the complete publication contract.

    The supersession bit is a produced projection of this predicate, not an
    independent claim. Keeping the conjunction here also gives the index reader a
    single contract to apply to artifacts written by older or alternate callers.
    """
    return bool(
        result.get("anchored") is True
        and result.get("attested") is True
        and result.get("decision_valid") is True
        and result.get("evidence_tier") == "decision"
        and result.get("verdict") in _DECISION_VERDICTS
        and not result.get("debug_only", False)
    )



def validate_result_index(index_path=None) -> dict:
    """Validate the result authority and every result it names.

    This is a small reader contract for the existing index, not a second result
    registry.  It checks that the pointer, artifact supersession fields, and
    on-disk result set agree before a gate result can be published.
    """
    default_evidence = _HERE / "evidence"
    path = Path(index_path) if index_path is not None else default_evidence / "RESULT_INDEX.json"
    evidence = path.parent if index_path is not None else default_evidence
    try:
        index = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read result index {path}: {exc}") from None
    if not isinstance(index, dict) or index.get("index_schema_version") != 1:
        raise ValueError("result index has unsupported schema")
    listed = index.get("superseded")
    if not isinstance(listed, list) or not all(isinstance(x, dict) for x in listed):
        raise ValueError("result index superseded list is malformed")
    refs = {}
    for row in listed:
        name, status = row.get("file"), row.get("status")
        if not isinstance(name, str) or not name or name in refs:
            raise ValueError(f"result index has duplicate/malformed file {name!r}")
        if status not in ("superseded", "withdrawn"):
            raise ValueError(f"result index has invalid retired status {status!r}")
        refs[name] = status
    current = index.get("current_decision_result")
    if current is not None:
        if not isinstance(current, str) or current in refs:
            raise ValueError("current_decision_result must be a distinct path or null")
        refs[current] = "current"
    actual = {p.relative_to(evidence).as_posix()
              for p in evidence.rglob("g33m_*_result.json")}
    if set(refs) != actual:
        raise ValueError(
            f"result index file set differs: missing={sorted(actual-set(refs))} "
            f"unlisted={sorted(set(refs)-actual)}")
    artifacts = {}
    valid = []
    for name, expected_status in refs.items():
        try:
            artifact = json.loads((evidence / name).read_text())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"{name} is unreadable: {exc}") from None
        sup = artifact.get("supersession")
        if not isinstance(sup, dict) or sup.get("status") != expected_status:
            raise ValueError(f"{name} supersession status disagrees with index")
        artifacts[name] = artifact
        is_valid = sup.get("valid_for_decision") is True
        if is_valid:
            if not _decision_grade(artifact):
                raise ValueError(
                    f"{name} is marked decision-valid without the complete "
                    "attested/anchored decision contract")
            valid.append(name)
        successor = sup.get("superseded_by")
        if successor is not None and successor not in actual:
            raise ValueError(f"{name} points to missing successor {successor!r}")
        if expected_status == "withdrawn":
            if not isinstance(sup.get("withdrawal_reason"), str) or not sup["withdrawal_reason"]:
                raise ValueError(f"withdrawn artifact {name} has no withdrawal reason")
            if is_valid:
                raise ValueError(f"withdrawn artifact {name} is decision-valid")
        elif expected_status == "superseded" and is_valid:
            raise ValueError(f"superseded artifact {name} is decision-valid")
        elif expected_status == "current":
            if not is_valid or successor is not None:
                raise ValueError(f"current artifact {name} is not a terminal valid result")
    # A withdrawn artifact may be the terminal historical successor only when its
    # own required reason explicitly says that no replacement exists. Otherwise a
    # superseded result pointing at withdrawn metadata is a broken successor link,
    # rather than a lineage closure. This preserves the checked-in v13 -> v14
    # history, whose withdrawal reason records that exact condition.
    for name, artifact in artifacts.items():
        successor = artifact["supersession"].get("superseded_by")
        if successor is not None and refs.get(successor) == "withdrawn":
            reason = artifacts[successor]["supersession"].get("withdrawal_reason", "")
            if "no replacement" not in reason.casefold():
                raise ValueError(
                    f"{name} points to withdrawn successor {successor!r} without "
                    "an explicit no-replacement reason")

    # Supersession is historical metadata while no result is promoted, so the
    # checked-in retired chain may terminate in a withdrawn artifact. It must still
    # be finite. Once a current result is published, every predecessor's lineage
    # must terminate at that current artifact; this prevents a current pointer from
    # coexisting with a retired/withdrawn successor branch.
    for name in artifacts:
        path = []
        cur = name
        while cur is not None:
            if cur in path:
                cycle = path[path.index(cur):] + [cur]
                raise ValueError(f"result supersession cycle: {' -> '.join(cycle)}")
            path.append(cur)
            successor = artifacts[cur]["supersession"].get("superseded_by")
            if successor is not None and successor not in artifacts:
                # This is also checked while reading each artifact; keeping the
                # guard here documents the graph traversal's closed-world contract.
                raise ValueError(f"{cur} points to missing successor {successor!r}")
            cur = successor
        if current is not None and path[-1] != current:
            raise ValueError(
                f"{name} supersession lineage terminates at {path[-1]!r}, "
                f"not current result {current!r}")
    if current is None:
        if valid:
            raise ValueError(f"index current pointer is null but valid artifacts exist: {valid}")
    elif valid != [current]:
        raise ValueError(f"index current pointer {current!r} disagrees with valid artifacts {valid}")
    return index


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
    ap.add_argument("--debug-only", action="store_true",
                    help="mark the artifact non-decisional, which is the ONLY way "
                         "to write one from a dirty tree. It is recorded in the "
                         "artifact, so a reader cannot mistake it for a decision.")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)

    try:
        validate_result_index()
    except ValueError as exc:
        print(f"refusing to run with invalid result index: {exc}", file=sys.stderr)
        return EXIT_USAGE

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
              "anchored": False, "decision_valid": False,
              "evidence_tier": "invalid",
              "provenance": _provenance(a, fbio.DECISION_PROTOCOL_VERSION),
              "debug_only": bool(a.debug_only),
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
    result["anchored"] = bool(loaded.anchored)
    # The field is produced here as a consequence of the load. The temporary true
    # lets `_decision_grade` check every condition without trusting a caller's
    # decision_valid claim.
    result["decision_valid"] = _decision_grade({
        **result,
        "decision_valid": True,
        "evidence_tier": "decision" if loaded.anchored else "debug",
    })
    result["evidence_tier"] = (
        "decision" if result["decision_valid"] else "debug")
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


def _git(*args) -> str:
    import subprocess
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          cwd=Path(__file__).resolve().parent.parent).stdout.strip()


def _provenance(a, protocol_version: int) -> dict:
    """The reproduction lineage, produced HERE rather than added afterwards.

    This block used to be attached by hand after the run. A field a tool does not
    produce cannot be gated by that tool, cannot be trusted to describe the run it
    sits in, and — as happened — can record `verifier_tree_dirty: true` on an
    artifact that is simultaneously marked decision-valid. SHAs are the authority;
    the input paths in `inputs` are local and informational.
    """
    return {
        # v3: verifier_semantics_sha256 and the operand-group counterfactual
        # became required parts of a current artifact, so the contract changed.
        "result_schema_version": 3,
        "decision_protocol_version": protocol_version,
        "producer_commit": a.expected_repo_commit,
        "verifier_commit": _git("rev-parse", "HEAD"),
        "verifier_tree_dirty": bool(_git("status", "--porcelain")),
        "cpp_root_manifest_sha256": a.expected_manifest_sha256,
        "fortran_legacy_manifest_sha256": a.expected_fortran_legacy_manifest_sha256,
        "fortran_conservative_manifest_sha256":
            a.expected_fortran_conservative_manifest_sha256,
        "gate_a_report_sha256": a.expected_gate_a_scope_report_sha256,
        "fixture_manifest_sha256": a.expected_fixture_manifest_sha256,
        # WHAT IT WAS DECIDED BY (owner review §3). The protocol version covers the
        # evidence contract; this covers the code that turns evidence into a
        # verdict. A comparator or activity-rule change moves the answer without
        # touching the protocol version, and without this the artifact stays
        # `current` while no longer describing what the tree would now conclude.
        "verifier_semantics_sha256": vid.semantics_sha256(),
        # The replay is NumPy f32/f64 arithmetic, so the same sources on a
        # different runtime are not self-evidently the same verifier.
        "verifier_runtime": {
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "numpy_version": np.__version__,
            "byteorder": sys.byteorder,
        },
    }


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
    # A DIRTY TREE CANNOT PRODUCE A DECISION ARTIFACT. `verifier_commit` is then a
    # commit the run was not made from, so checking it out does not reproduce the
    # result — which is the whole content of the provenance block. The v14 artifact
    # was written this way and marked decision-valid at the same time.
    prov = result.get("provenance", {})
    if prov.get("verifier_tree_dirty") and not result.get("debug_only"):
        raise SystemExit(
            "refusing to write a decision artifact from a DIRTY working tree: the "
            "recorded verifier_commit would not reproduce this result. Commit or "
            "stash first, or pass --debug-only to mark the artifact non-decisional.")
    # A recorded runtime and source digest are only useful if the writer enforces
    # them. Keep this check on attested, non-debug results so evidence failures and
    # the small unit-test writer remain readable forensic artifacts.
    if _decision_grade(result):
        runtime = prov.get("verifier_runtime", {})
        mismatch = vid.runtime_matches(runtime)
        if mismatch:
            raise SystemExit(
                "refusing to write a decision artifact under a verifier runtime "
                f"mismatch: {mismatch}")
        commit = prov.get("verifier_commit")
        expected_sha = vid.semantics_sha256_at(commit) if commit else None
        if not commit or expected_sha is None or expected_sha != prov.get("verifier_semantics_sha256"):
            raise SystemExit(
                "refusing to write a decision artifact whose verifier commit and "
                "semantics digest do not agree")
    # The evidence index requires `supersession` on every artifact and reads
    # `status` to enforce exactly-one-current. Nothing PRODUCED it: it was typed
    # onto each artifact by hand after the run, so a regeneration either lost the
    # field or reintroduced it from memory, and a hand-edited field in a decision
    # artifact is indistinguishable from a hand-edited verdict. Produced here, and
    # only the fields a fresh run can actually know: a run supersedes nothing and
    # is withdrawn by nothing. Retiring an artifact stays a deliberate edit of the
    # OLD file, which is the direction that should need a human.
    result.setdefault("supersession", {
        "status": "current",
        "superseded_by": None,
        "valid_for_decision": _decision_grade(result),
        "withdrawal_reason": None,
        "note": ("debug-only run: not valid for decision"
                 if result.get("debug_only")
                 else f"produced by {Path(__file__).name} at "
                      f"{prov.get('verifier_commit', 'unknown')[:12]} on "
                      f"{vid.VERIFIER_RUNTIME['python_implementation']} "
                      f"{prov.get('verifier_runtime', {}).get('python_version', '?')} "
                      f"/ numpy {vid.VERIFIER_RUNTIME['numpy_version']}, "
                      f"verifier semantics "
                      f"{prov.get('verifier_semantics_sha256', '?')[:16]}"),
    })
    # A caller supplied metadata block cannot turn an unattested candidate, evidence
    # failure, debug run, or non-decision tier into a publication. `setdefault` above
    # preserves an existing block for deliberate forensic fields, but the validity
    # bit is owned by this writer.
    result["supersession"]["valid_for_decision"] = bool(
        result["supersession"].get("valid_for_decision", False)
        and _decision_grade(result))
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(result, indent=2, sort_keys=True, default=str) + "\n")
    tmp.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
