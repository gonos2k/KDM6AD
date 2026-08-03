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

SCHEMA = "refinement_experiment_v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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
          findings=()) -> dict:
    paths = sorted(outputs.glob("n*.txt"))
    members = [_member(p) for p in paths]
    # One experiment, not several (owner P0-2). Every cross-member check the
    # analyzer applies before it will produce a table is applied before the
    # manifest will claim one is reproducible: same record universe, one
    # algorithm and mode, one integration horizon, no repeated step.
    # Keyed by nsplit, so `n3.rezero.txt` beside `n3.carry.txt` would collapse to
    # one entry and the cross-member checks -- including the mode check -- would
    # run on whichever survived (owner §7.3).
    ns = [int(_NAME.match(p.name).group(1)) for p in paths]
    if len(ns) != len(set(ns)):
        dup = sorted({n for n in ns if ns.count(n) > 1})
        raise ra.RefineError(
            f"bundle contains more than one member for nsplit {dup} — a chain has "
            f"one member per step, and keying by nsplit would hide the others")
    runs = {n: ra.read(p, nsplit=n) for n, p in zip(ns, paths)}
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
