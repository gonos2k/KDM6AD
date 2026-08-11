#!/usr/bin/env python3
"""Provenance for a refinement experiment, under its own schema (§9).

Writing NO provenance -- the first attempt -- made the experiment irreproducible.
The fix is a DIFFERENT schema, not the absence of one: `decision_eligible` is a
constant False with no parameter that sets it, so the distinction from a decision
artifact is structural, not a matter of where the file was written.

Deliberately not sharing the decision provenance builder: one edit there could
make an experiment look decision-grade.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g33_refine_analyze as ra   # noqa: E402

#: v2 REQUIRES the commit+blob pin blocks and a non-empty member list. Under v1
#: those were optional metadata, so deleting them downgraded a new bundle to the
#: legacy contract and the checker reported rather than failed -- a contract you
#: can opt out of by omission is not a contract (owner P0-E2).
SCHEMA = "refinement_experiment_v2"


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


#: Manifest keys that record WHERE a run happened, not WHAT was built. They are
#: kept in the document and excluded from the content address, so two runs of the
#: same experiment in different temp directories address the same bundle
#: (owner §10.3).
DIAGNOSTIC_KEYS = ("diagnostic",)

#: Build artifacts whose RAW digest is PAYLOAD, not identity.
#:
#: Both files embed the output directory, which is a fresh temporary path every
#: run. Stripping `diagnostic` KEYS inside the manifest did nothing for them,
#: because a file digest is just a string field -- so two identical experiments
#: produced different addresses and "an identical rerun reuses the bundle" held
#: only under fake provenance, which is exactly the property the content address
#: exists to provide (owner P0-1). Measured: two real builds of the same
#: experiment in different tmpdirs differed in these two entries and NOTHING
#: else, `g33_refine_driver` included.
#:
#: Their science content still reaches identity -- `build_provenance` is carried
#: as an object with its diagnostic keys stripped -- and their integrity is
#: still checked, because the evidence chain verifies every build_artifacts
#: digest. Payload, not identity.
LOCATION_DEPENDENT_ARTIFACTS = frozenset({"build_provenance.json",
                                          "commands.txt"})

#: Also not identity: the producer REFUSES to run when any byte that will run
#: differs from HEAD, so a dirty tree here can only mean unrelated files were
#: modified. Letting an edited README change the experiment's address
#: contradicts the producer's own rule for what makes a run the same run.
NON_IDENTITY_KEYS = ("tree_dirty",)


def identity_digest(man: dict) -> str:
    """The content address: a digest over everything except the diagnostics."""
    def strip(x):
        if isinstance(x, dict):
            return {k: strip(v) for k, v in x.items()
                    if k not in DIAGNOSTIC_KEYS and k not in NON_IDENTITY_KEYS}
        if isinstance(x, list):
            return [strip(v) for v in x]
        return x
    m = strip(man)
    if "build_artifacts" in m:
        m["build_artifacts"] = [
            {k: v for k, v in a.items()
             if not (k == "sha256"
                     and a.get("file") in LOCATION_DEPENDENT_ARTIFACTS)}
            for a in m["build_artifacts"]]
    return hashlib.sha256(
        json.dumps(m, sort_keys=True).encode()).hexdigest()


def _git(*a) -> str:
    return subprocess.run(("git",) + a, capture_output=True,
                          text=True).stdout.strip()


_NAME = re.compile(r"^n(\d+)\.(carry|rezero)\.txt$")


def _member(path: Path) -> dict:
    """One member, via the analyzer's STRICT parser (owner §9).

    Reading only the BEGIN line would admit a truncated, duplicated or ragged
    member into the manifest -- exactly what the strict reader exists to reject,
    and the manifest is what says the table is reproducible. delt/loops/dtcld are
    READ from the stream, not recomputed from N: deriving them would restate the
    assumption the experiment exists to check.
    """
    # The FILENAME is bound to the stream: `read(nsplit=)` refuses a member whose
    # BEGIN disagrees with what it is called, and the mode in the name must be the
    # mode it ran. A mislabelled member is how two experiments become one table.
    m = _NAME.match(path.name)
    if not m:
        raise ra.RefineError(f"{path.name}: not n<N>.<carry|rezero>.txt")
    r = ra.read(path, nsplit=int(m.group(1)))   # raises on anything malformed
    if r[("meta", "mode")] != m.group(2):
        raise ra.RefineError(
            f"{path.name}: filename says mode {m.group(2)}, stream says "
            f"{r[('meta', 'mode')]}")
    out = {"file": path.name, "output_sha256": sha256(path),
           "nsplit": r[("meta", "nsplit")], "mode": r[("meta", "mode")],
           "algorithm": r[("meta", "algorithm")]}
    for k in ("delt", "loops", "dtcld"):
        if ("meta", k) in r:
            out[k] = r[("meta", k)]
    return out


def build(outputs: Path, *, module: Path, fixture: Path, compiler: str,
          analyzer: Path | None = None, build_provenance: Path | None = None,
          findings=(), member_reader=None) -> dict:
    """`member_reader` describes one output file, defaulting to the G33R reader.

    The f64 instrument arm emits no G33R at all, so it supplies the G33P reader
    instead. The hook exists because an f64 member IS a different artifact -- not
    because the contract is negotiable: both readers are strict, and the
    G33R-shaped cross-member checks below are skipped only when the members are
    not G33R (owner priority 2).
    """
    read_member = member_reader or _member
    paths = sorted(outputs.glob("n*.txt"))
    members = [read_member(p) for p in paths]
    # One experiment, not several (owner P0-2). Every cross-member check the
    # analyzer applies before it will produce a table is applied before the
    # manifest will claim one is reproducible: same record universe, one
    # algorithm and mode, one integration horizon, no repeated step.
    # Keyed by nsplit, so `n3.rezero.txt` beside `n3.carry.txt` would collapse to
    # one entry and the cross-member checks -- including the mode check -- would
    # run on whichever survived (owner §7.3).
    ns = [int(_NAME.match(p.name).group(1)) for p in paths]
    # Regardless of the reader: two members for one nsplit collapse to one
    # entry whichever parser read them (owner §8.4).
    if len(ns) != len(set(ns)):
        dup = sorted({n for n in ns if ns.count(n) > 1})
        raise ra.RefineError(
            f"bundle contains more than one member for nsplit {dup} — a chain has "
            f"one member per step, and keying by nsplit would hide the others")
    runs = ({} if member_reader is not None
            else {n: ra.read(p, nsplit=n) for n, p in zip(ns, paths)})
    if len(runs) > 1:
        ra.require_same_universe(runs)
    steps = [m.get("dtcld") for m in members]
    man = {
        "artifact_type": "refinement_experiment",
        # A CONSTANT. No argument sets it, so no invocation can produce an
        # experiment manifest that claims decision eligibility.
        "decision_eligible": False,
        "schema": SCHEMA,
        "repo_commit": _git("rev-parse", "HEAD"),
        "tree_dirty": bool(_git("status", "--porcelain")),
        "module_sha256": sha256(module),
        "module_path": str(module),
        "fixture_sha256": sha256(fixture),
        "fixture_path": str(fixture),
        # A human label. The compiler that actually ran is in build_provenance,
        # by digest -- two hosts print this same string and produce different
        # numbers. `null` there means the build recorded nothing, which is a
        # different statement from an empty command list.
        "compiler": compiler,
        "build_provenance": (json.loads(build_provenance.read_text())
                             if build_provenance and build_provenance.exists()
                             else None),
        "analyzer_sha256": sha256(analyzer) if analyzer else None,
        # The documents that draw conclusions from these members. A finding that
        # cites a table nobody can tie to the run it came from is unreviewable.
        "findings": [{"path": str(f), "sha256": sha256(f)} for f in findings],
        "members": members,
    }
    # Recorded, not asserted. A sweep that does not halve dtcld is still a run
    # worth keeping -- the N=1/N=3 policy control is exactly such a sweep -- but
    # whether it refines should be a property a reader can see rather than infer.
    #
    # Ordered by ACTUAL step, not by N: N = 1,2,3 run 100, 150, 100 s, so an
    # N-ordered chain need not be step-ordered and sorting the VALUES alone would
    # call an arbitrary bag of members a chain as long as the numbers happened to
    # halve (owner P0-2).
    by_step = [m["dtcld"] for m in sorted(members, key=lambda m: -m.get("dtcld", 0))
               ] if all(s is not None for s in steps) else []
    man["is_refinement_chain"] = (
        len(by_step) > 1
        and all(abs(a - 2 * b) < 1e-9 for a, b in zip(by_step, by_step[1:])))
    # The provenance must describe THESE sources, not some other build's.
    bp = man["build_provenance"]
    if bp:
        for field in ("module_sha256", "fixture_sha256"):
            if bp.get(field) != man[field]:
                raise ra.RefineError(
                    f"build_provenance.{field} does not match the {field} this "
                    f"manifest records — the provenance is from a different build")
    return man


#: NO standalone CLI (owner P0-3). `build()` produces the CORE of a manifest;
#: the v2-required blocks -- `instrumented`, `arm`, `precision`,
#: `member_parsers`, `producer_modules`, `tracked_build_inputs`, `analyses` --
#: are added by `g33_refine_experiment.produce()`, which then validates and
#: publishes atomically.
#:
#: A CLI here emitted that core, stamped it `refinement_experiment_v2`, and
#: exited. Worse, `validate()` was defined BELOW the `__main__` block, so the
#: entry point could not have called it even if it wanted to: the one path that
#: skipped validation was the one a person could run by hand.
#:
#: The producer is the only way to make a bundle. Anything else is a draft.


#: What a v2 manifest must satisfy, in one place. The producer calls it before
#: publishing and the evidence checker calls it before believing anything, so a
#: bundle cannot be valid to one and invalid to the other (owner P0-2).
_ARMS = ("reference", "probe", "f64")
_PRECISIONS = ("f32", "f64")
KNOWN_SCHEMAS = ("refinement_experiment_v1", "refinement_experiment_v2")


def _hexlen(v, n) -> bool:
    return isinstance(v, str) and len(v) == n and \
        all(c in "0123456789abcdef" for c in v.lower())


def validate(man: dict) -> list:
    """Everything wrong with this manifest, as a list of sentences.

    Empty means valid. Truthiness was the whole check before: `[{}]` counted as
    a pin block, so a v2 bundle could carry two empty dicts, be reported
    `analyzer-unpinned` -- a PASSING state kept for legacy bundles -- and check
    out clean. `instrumented` was not required, so deleting the key deleted the
    `analyses` requirement with it: the same "lower the contract by omission"
    defect the schema bump was meant to close.
    """
    if not isinstance(man, dict):
        return [f"top level is {type(man).__name__}, not an object"]
    bad = []
    if man.get("artifact_type") != "refinement_experiment":
        bad.append(f"artifact_type {man.get('artifact_type')!r} is not "
                   f"'refinement_experiment'")
    schema = man.get("schema")
    if schema not in KNOWN_SCHEMAS:
        return bad + [f"unknown schema {schema!r}"]
    if schema != "refinement_experiment_v2":
        return bad                       # v1 predates every field below
    if man.get("decision_eligible") is not False:
        bad.append("decision_eligible must be False: a refinement experiment is "
                   "never decision evidence")
    if not isinstance(man.get("instrumented"), bool):
        bad.append("instrumented must be present and boolean -- deleting it "
                   "deletes the `analyses` requirement with it")
    if man.get("arm") not in _ARMS:
        bad.append(f"arm {man.get('arm')!r} is not one of {_ARMS}")
    if man.get("precision") not in _PRECISIONS:
        bad.append(f"precision {man.get('precision')!r} is not one of "
                   f"{_PRECISIONS}")
    if not isinstance(man.get("build_provenance"), dict) or \
            not man["build_provenance"]:
        bad.append("build_provenance must be a non-empty object")

    members = man.get("members")
    if not isinstance(members, list) or not members:
        bad.append("members must be a non-empty list")
    else:
        for i, m in enumerate(members):
            if not isinstance(m, dict) or not isinstance(m.get("file"), str) \
                    or not _hexlen(m.get("output_sha256"), 64):
                bad.append(f"members[{i}] needs `file` and a 64-hex "
                           f"`output_sha256`")

    arts = man.get("build_artifacts")
    if not isinstance(arts, list) or not arts:
        bad.append("build_artifacts must be a non-empty list: the driver binary "
                   "and its provenance ARE published in the bundle")
    else:
        for i, a in enumerate(arts):
            if not isinstance(a, dict) or not isinstance(a.get("file"), str) \
                    or not _hexlen(a.get("sha256"), 64):
                bad.append(f"build_artifacts[{i}] needs `file` and a 64-hex "
                           f"`sha256`")
        if not any(isinstance(a, dict) and a.get("file") == "g33_refine_driver"
                   for a in arts):
            bad.append("build_artifacts must include g33_refine_driver -- the "
                       "binary that produced these numbers")
        else:
            # The manifest states the executable digest TWICE, in
            # build_artifacts and inside build_provenance, and nothing compared
            # them. Two statements about the same binary that are never checked
            # against each other are one statement and one decoration
            # (owner §8.4).
            got = {a.get("file"): a.get("sha256") for a in arts}
            want = (man.get("build_provenance") or {}).get("executable_sha256")
            if want and got.get("g33_refine_driver") != want:
                bad.append(
                    f"build_artifacts records g33_refine_driver as "
                    f"{str(got.get('g33_refine_driver'))[:12]} but "
                    f"build_provenance says {str(want)[:12]} -- the bundle "
                    f"names two different binaries")
    # An `--nflux` bundle must carry the instrumented analyses, not merely a
    # non-empty `analyses`: one arm_stream satisfied that while carrying none
    # of them (owner §8.3).
    if man.get("instrumented") is True:
        kinds = {a.get("analysis") for a in (man.get("analyses") or [])
                 if isinstance(a, dict)}
        absent = [k for k in REQUIRED_WHEN_INSTRUMENTED if k not in kinds]
        if absent:
            bad.append(f"instrumented bundle is missing the analyses that make "
                       f"it instrumented: {absent}")
    for key in ("member_parsers", "producer_modules", "tracked_build_inputs"):
        block = man.get(key)
        if not isinstance(block, list) or not block:
            bad.append(f"{key} must be a non-empty list")
            continue
        for i, e in enumerate(block):
            if not isinstance(e, dict):
                bad.append(f"{key}[{i}] is {type(e).__name__}, not an object")
            elif not (isinstance(e.get("path"), str)
                      and _hexlen(e.get("content_sha256"), 64)
                      and _hexlen(e.get("commit"), 40)
                      and _hexlen(e.get("blob_sha"), 40)):
                bad.append(f"{key}[{i}] is not a complete pin: it needs `path`, "
                           f"a 64-hex `content_sha256`, and 40-hex `commit` and "
                           f"`blob_sha`")

    # arm and precision are not independent: an f64 arm at f32 precision, or the
    # reverse, describes a run that cannot exist.
    if man.get("arm") == "f64" and man.get("precision") != "f64":
        bad.append("arm=f64 requires precision=f64")
    if man.get("arm") in ("reference", "probe") and man.get("precision") != "f32":
        bad.append(f"arm={man.get('arm')} requires precision=f32")

    analyses = man.get("analyses")
    if man.get("instrumented") is True and not analyses:
        bad.append("instrumented=true requires a non-empty `analyses`")
    nsplits = {m.get("nsplit") for m in (members if isinstance(members, list) else [])
               if isinstance(m, dict)}
    bad += _analysis_violations(analyses or [], nsplits)

    # Every published file must live INSIDE the bundle. The producer generates
    # safe basenames, but this validator claims to judge an arbitrary v2
    # manifest, so a `../outside.txt` must not be one it accepts.
    seen = set()
    for label, block in (("members", members), ("analyses", analyses),
                        ("build_artifacts", arts)):
        for i, e in enumerate(block if isinstance(block, list) else []):
            f = e.get("file") if isinstance(e, dict) else None
            if not isinstance(f, str):
                continue
            if f != Path(f).name or f in ("", ".", ".."):
                bad.append(f"{label}[{i}].file {f!r} is not a plain basename")
            elif f in seen:
                bad.append(f"{label}[{i}].file {f!r} is declared twice")
            else:
                seen.add(f)
    return bad


#: `analyses[]` holds two different artifacts. A derived table is only as good
#: as the analyzer that produced it; a raw arm stream is only as good as the
#: command that produced it. Requiring `{file, sha256}` of both let a derived
#: JSON ship with NO analyzer, which the checker then reported as
#: `analyzer-unpinned` -- a passing state kept for legacy bundles (owner P0-4).
#: The density profiles an `arm_stream` entry may declare. A DIFFERENT
#: namespace from the manifest-level `arm` (reference|probe|f64): that one says
#: which precision arm the bundle is, this one says which density control the
#: raw stream was run under.
_RHO_ARMS = ("as-is", "uniform", "inverted", "x2", "offset+", "offset-")

#: The driver's second argument. It error-stops on anything else, so a `ran`
#: block naming something else describes a run that could not have happened.
_CARRY_MODES = ("carry", "rezero")

#: The driver reads NSPLIT into a Fortran default INTEGER, so the read fails
#: above int32 and it error-stops. MEASURED against the real binary:
#:
#:   2147483647  accepted
#:   2147483648  ERROR STOP NSPLIT must be a positive integer
#:
#: "Positive integer" alone therefore admits identities the driver rejects
#: (Codex). Python ints are unbounded; the run this describes is not.
_MAX_NSPLIT = 2 ** 31 - 1

#: The derived analyses a v2 bundle may carry. Declared here rather than
#: imported, because the producer imports THIS module; a test asserts the two
#: agree, so drift is a failure rather than a silently widened union.
#: Without it any `analysis` string that was not "arm_stream" was accepted as a
#: derived analysis, so a typo shipped as a new kind (owner §8.2).
DERIVED_ANALYSES = ("matched_closure", "cap_interface", "extension_protocol",
                    "dual_ledger", "defect_magnitude", "internal_cap_enthalpy",
                    "metric_trajectory")

#: Analyses that run the DRIVER over several configurations rather than
#: reading one member stream. They analyse the bundle's own binary, so the
#: bundle is where they belong -- but they have no single member to key on,
#: which is why the derived variant's `nsplit` cannot describe them and a third
#: tag is needed. `g33_ncmin_locality` is (driver, fixture) and runs the driver
#: once per decomposition; the derived contract is (stream, basis) per member.
MULTI_RUN_ANALYSES = ("ncmin_locality",)

#: What an `--nflux` bundle must actually contain. `instrumented: true` with a
#: single arm_stream satisfied "analyses is non-empty" while carrying none of
#: the instrumented analyses (owner §8.3).
REQUIRED_WHEN_INSTRUMENTED = ("matched_closure", "cap_interface",
                              "extension_protocol", "dual_ledger",
                              "defect_magnitude", "internal_cap_enthalpy")

_DERIVED_FIELDS = ("analysis", "nsplit", "analyzer", "analyzer_sha256",
                   "analyzer_commit", "analyzer_blob_sha")
_ARM_FIELDS = ("analysis", "nsplit", "arm", "runtime_argv")


def _analysis_violations(analyses, member_nsplits) -> list:
    bad = []
    for i, a in enumerate(analyses):
        if not isinstance(a, dict) or not isinstance(a.get("file"), str) \
                or not _hexlen(a.get("sha256"), 64):
            bad.append(f"analyses[{i}] needs `file` and a 64-hex `sha256`")
            continue
        kind = a.get("analysis")
        if not isinstance(kind, str):
            bad.append(f"analyses[{i}] declares no `analysis` kind")
            continue
        want = (_ARM_FIELDS if kind == "arm_stream"
                else () if kind in MULTI_RUN_ANALYSES else _DERIVED_FIELDS)
        missing = [k for k in want if not a.get(k)]
        if missing:
            bad.append(f"analyses[{i}] ({kind}) is missing {missing}")
        if kind == "arm_stream":
            if a.get("arm") not in _RHO_ARMS:
                bad.append(f"analyses[{i}] arm {a.get('arm')!r} is not one of "
                           f"{_RHO_ARMS}")
            argv = a.get("runtime_argv")
            if not isinstance(argv, list) or not all(isinstance(x, str)
                                                     for x in argv):
                bad.append(f"analyses[{i}] runtime_argv must be a list of str")
            elif len(argv) < 4:
                bad.append(f"analyses[{i}] runtime_argv {argv} is too short to "
                           f"say which run it was")
            else:
                # The argv is what RAN; the fields are what the manifest SAYS.
                # Recording both without comparing them lets an entry describe a
                # different run than the one it names (owner §8.1).
                if argv[0] != str(a.get("nsplit")):
                    bad.append(f"analyses[{i}] runtime_argv nsplit {argv[0]!r} "
                               f"contradicts nsplit {a.get('nsplit')!r}")
                if argv[3] != a.get("arm"):
                    bad.append(f"analyses[{i}] runtime_argv arm {argv[3]!r} "
                               f"contradicts arm {a.get('arm')!r}")
        elif kind in MULTI_RUN_ANALYSES:
            # Keyed on the FIXTURE and the decompositions it ran, not on a
            # member: there is no single stream this concluded from.
            if not isinstance(a.get("fixture"), str) or not a["fixture"]:
                bad.append(f"analyses[{i}] ({kind}) needs the `fixture` it ran")
            d = a.get("decompositions")
            if not isinstance(d, list) or not d or not all(
                    isinstance(x, list) and x and all(isinstance(v, int) and v > 0
                                                      for v in x) for x in d):
                bad.append(f"analyses[{i}] ({kind}) needs `decompositions` as a "
                           f"non-empty list of positive-int lists")
            elif len({tuple(x) for x in d}) != len(d):
                bad.append(f"analyses[{i}] ({kind}) repeats a decomposition")
            # The parameters the analysis DROVE THE BINARY AT. Without them
            # the entry reads as though it shared the bundle's nsplit/mode,
            # and it does not: this analysis chooses its own (Codex).
            ran = a.get("ran")
            if not isinstance(ran, dict) or not all(
                    k in ran for k in ("nsplit", "carry", "rho",
                                       "decompositions")):
                bad.append(f"analyses[{i}] ({kind}) needs `ran` with nsplit, "
                           f"carry, rho and decompositions")
            # TYPED, not merely present. Checking only that the keys exist
            # accepted nsplit="twelve", nsplit=0, carry="banana" and
            # rho="purple" -- a run identity that cannot describe any run the
            # driver would accept (Codex). These are the driver's own
            # vocabularies: it error-stops on anything else.
            elif not isinstance(ran["nsplit"], int) or isinstance(
                    ran["nsplit"], bool) or not 1 <= ran["nsplit"] <= _MAX_NSPLIT:
                bad.append(f"analyses[{i}] ({kind}) ran.nsplit "
                           f"{ran['nsplit']!r} is not a positive integer the "
                           f"driver accepts (1..{_MAX_NSPLIT})")
            elif ran["carry"] not in _CARRY_MODES:
                bad.append(f"analyses[{i}] ({kind}) ran.carry "
                           f"{ran['carry']!r} is not one of {_CARRY_MODES}")
            elif ran["rho"] not in _RHO_ARMS:
                bad.append(f"analyses[{i}] ({kind}) ran.rho {ran['rho']!r} "
                           f"is not one of {_RHO_ARMS}")
            elif ran["decompositions"] != a.get("decompositions"):
                bad.append(f"analyses[{i}] ({kind}) decompositions disagree "
                           f"with `ran` -- one of them is not what executed")
            for k in ("analyzer", "analyzer_sha256", "analyzer_commit",
                      "analyzer_blob_sha"):
                if not a.get(k):
                    bad.append(f"analyses[{i}] ({kind}) is missing {k}")
        else:
            if kind not in DERIVED_ANALYSES:
                bad.append(f"analyses[{i}] unknown derived analysis {kind!r} "
                           f"(known: {sorted(DERIVED_ANALYSES)})")
            if a.get("analyzer_commit") and not _hexlen(a["analyzer_commit"], 40):
                bad.append(f"analyses[{i}] analyzer_commit is not a 40-hex sha")
            if a.get("analyzer_blob_sha") and not _hexlen(a["analyzer_blob_sha"], 40):
                bad.append(f"analyses[{i}] analyzer_blob_sha is not a 40-hex sha")
            if a.get("analyzer_sha256") and not _hexlen(a["analyzer_sha256"], 64):
                bad.append(f"analyses[{i}] analyzer_sha256 is not a 64-hex sha")
        # An analysis of a member the bundle does not carry describes nothing.
        # A multi-run analysis reads no member, so it has no nsplit to check.
        if kind in MULTI_RUN_ANALYSES:
            pass
        elif member_nsplits and a.get("nsplit") not in member_nsplits:
            bad.append(f"analyses[{i}] nsplit {a.get('nsplit')!r} is not among "
                       f"the members {sorted(member_nsplits)}")
    return bad
