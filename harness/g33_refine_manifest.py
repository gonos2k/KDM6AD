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


def identity_digest(man: dict) -> str:
    """The content address: a digest over everything except the diagnostics."""
    def strip(x):
        if isinstance(x, dict):
            return {k: strip(v) for k, v in x.items() if k not in DIAGNOSTIC_KEYS}
        if isinstance(x, list):
            return [strip(v) for v in x]
        return x
    return hashlib.sha256(
        json.dumps(strip(man), sort_keys=True).encode()).hexdigest()


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


def main(argv) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("outputs", type=Path)
    ap.add_argument("--module", type=Path, required=True)
    ap.add_argument("--fixture", type=Path, required=True)
    ap.add_argument("--compiler", required=True)
    ap.add_argument("--analyzer", type=Path, default=None)
    ap.add_argument("--build-provenance", type=Path, default=None,
                    help="build_provenance.json written by refine_build.sh")
    ap.add_argument("--finding", type=Path, action="append", default=[],
                    help="finding document drawing conclusions from these members")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    man = build(a.outputs, module=a.module, fixture=a.fixture,
                compiler=a.compiler, analyzer=a.analyzer,
                build_provenance=a.build_provenance, findings=a.finding)
    text = json.dumps(man, indent=2, sort_keys=True) + "\n"
    if a.out:
        a.out.write_text(text)
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


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

    for key in ("member_parsers", "producer_modules"):
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

    analyses = man.get("analyses")
    if man.get("instrumented") is True and not analyses:
        bad.append("instrumented=true requires a non-empty `analyses`")
    for i, a in enumerate(analyses or []):
        if not isinstance(a, dict) or not isinstance(a.get("file"), str) \
                or not _hexlen(a.get("sha256"), 64):
            bad.append(f"analyses[{i}] needs `file` and a 64-hex `sha256`")
    return bad
