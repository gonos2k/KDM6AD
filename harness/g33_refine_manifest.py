#!/usr/bin/env python3
"""Provenance for a refinement experiment, under its own schema.

Owner review §9. The refinement build deliberately wrote no provenance so a
refinement run could not be mistaken for a decision artifact. That was the wrong
correction: with no provenance the table is not independently reproducible either
-- which commit, which module, which compiler and flags, which fixture, which
output files, which analyzer.

The fix is a DIFFERENT schema, not the absence of one. `artifact_type` and
`decision_eligible` are the first two fields and `decision_eligible` is a constant
`False` with no parameter that sets it, so the distinction from a decision
artifact is structural rather than a matter of where the file was written.

Deliberately NOT reusing the decision provenance builder: sharing it would mean
one edit could make an experiment look decision-grade, which is the confusion the
separation exists to prevent.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

SCHEMA = "refinement_experiment_v1"
DTCLDCR = 120.0

_BEGIN = re.compile(r"^G33R BEGIN nsplit\s+(\d+)\s+(carry|rezero)\s+(\S+)"
                    r"(?:\s+delt\s+(\S+)\s+loops\s+(\d+)\s+dtcld\s+(\S+))?")


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _git(*a) -> str:
    return subprocess.run(("git",) + a, capture_output=True,
                          text=True).stdout.strip()


def _member(path: Path) -> dict:
    """One member, described by what the run itself reported.

    delt/loops/dtcld are read from the stream rather than recomputed from N: the
    point of the §9 correction is that the kernel picks its own step, so a
    manifest that derived it would restate the assumption the experiment exists to
    check.
    """
    first = next((ln for ln in path.read_text().splitlines()
                  if ln.startswith("G33R BEGIN")), "")
    m = _BEGIN.match(first.strip())
    if not m:
        raise SystemExit(f"{path}: no parseable G33R BEGIN")
    out = {"file": path.name, "output_sha256": sha256(path),
           "nsplit": int(m.group(1)), "mode": m.group(2),
           "algorithm": m.group(3)}
    if m.group(5) is not None:
        out |= {"delt": float(m.group(4)), "loops": int(m.group(5)),
                "dtcld": float(m.group(6))}
    return out


def build(outputs: Path, *, module: Path, fixture: Path, compiler: str,
          compile_commands=(), analyzer: Path | None = None) -> dict:
    members = [_member(p) for p in sorted(outputs.glob("n*.txt"))]
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
        "compiler": compiler,
        "compile_commands": list(compile_commands),
        "analyzer_sha256": sha256(analyzer) if analyzer else None,
        "members": members,
    }
    # Recorded, not asserted. A sweep that does not halve dtcld is still a run
    # worth keeping -- the N=1/N=3 policy control is exactly such a sweep -- but
    # whether it refines should be a property a reader can see rather than infer.
    man["is_refinement_chain"] = (
        len(steps) > 1 and all(s is not None for s in steps)
        and all(abs(a - 2 * b) < 1e-9
                for a, b in zip(sorted(steps, reverse=True),
                                sorted(steps, reverse=True)[1:])))
    return man


def main(argv) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("outputs", type=Path)
    ap.add_argument("--module", type=Path, required=True)
    ap.add_argument("--fixture", type=Path, required=True)
    ap.add_argument("--compiler", required=True)
    ap.add_argument("--analyzer", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    man = build(a.outputs, module=a.module, fixture=a.fixture,
                compiler=a.compiler, analyzer=a.analyzer)
    text = json.dumps(man, indent=2, sort_keys=True) + "\n"
    if a.out:
        a.out.write_text(text)
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
