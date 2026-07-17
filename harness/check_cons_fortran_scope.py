#!/usr/bin/env python3
"""Gate A scope checker — conservative-interface Fortran variant (C4).

Verifies that the host-tree ``module_mp_kdm6_cons.F`` is a byte-identical
copy of the legacy ``module_mp_kdm6.F`` except for

  (1) whole-word renames (module_mp_kdm6 -> module_mp_kdm6_cons,
      kdm6 -> kdm6_cons, kdm6init -> kdm6init_cons), and
  (2) the EXACT pinned sedimentation-interface edits recorded in the
      manifest (the ONLY authorized physics delta of the
      conservative-interface-v1 freeze-lift).

It additionally verifies

  (3) the raw ice-velocity handoff blocks are byte-identical in both files
      (the qi-dominant pathway is explicitly OUT of scope), and
  (4) the legacy modules on this host match the pinned sha256 manifest
      (module_mp_kdm6.F and, if given, the legacy wrapper
      module_mp_kdm6ad.F — both are never-modify files).

Any difference outside the pinned edits FAILS the check. A JSON scope
report is always emitted.

Usage:
  python3 harness/check_cons_fortran_scope.py \
      --legacy  <host>/phys/module_mp_kdm6.F \
      --cons    <host>/phys/module_mp_kdm6_cons.F \
      --legacy-wrapper <host>/phys/module_mp_kdm6ad.F \
      [--manifest harness/cons_fortran_scope_manifest.json] \
      [--json-out scope_report.json]
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sys
from pathlib import Path

# Whole-word rename map, cons -> legacy (longest first: the shorter patterns
# cannot match inside the longer replacements because '_' is a word char).
RENAMES_CONS_TO_LEGACY = [
    (r"\bmodule_mp_kdm6_cons\b", "module_mp_kdm6"),
    (r"\bkdm6init_cons\b", "kdm6init"),
    (r"\bkdm6_cons\b", "kdm6"),
]

# Diff clusters separated by fewer equal lines than this are merged into one
# logical edit block (the pinned physics edits interleave short equal runs).
CLUSTER_GAP = 10


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_cons(text: str) -> str:
    for pat, rep in RENAMES_CONS_TO_LEGACY:
        text = re.sub(pat, rep, text)
    return text


def cluster_diff(legacy_lines: list[str], cons_lines: list[str]):
    """Diff and merge nearby non-equal opcodes into logical edit clusters.

    Returns a list of dicts: {legacy_span, cons_span, old, new} with 1-based
    inclusive spans ([a, a-1] denotes a pure insertion point after line a-1).
    """
    sm = difflib.SequenceMatcher(None, legacy_lines, cons_lines, autojunk=False)
    ops = [op for op in sm.get_opcodes() if op[0] != "equal"]
    clusters = []
    for op in ops:
        _, i1, i2, j1, j2 = op
        if clusters and i1 - clusters[-1]["i2"] < CLUSTER_GAP:
            clusters[-1]["i2"] = i2
            clusters[-1]["j2"] = j2
        else:
            clusters.append({"i1": i1, "i2": i2, "j1": j1, "j2": j2})
    out = []
    for c in clusters:
        out.append(
            {
                "legacy_span": [c["i1"] + 1, c["i2"]],
                "cons_span": [c["j1"] + 1, c["j2"]],
                "old": legacy_lines[c["i1"]:c["i2"]],
                "new": cons_lines[c["j1"]:c["j2"]],
            }
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--legacy", required=True, type=Path,
                    help="legacy module_mp_kdm6.F (never-modify reference)")
    ap.add_argument("--cons", required=True, type=Path,
                    help="corrected module_mp_kdm6_cons.F under check")
    ap.add_argument("--legacy-wrapper", type=Path, default=None,
                    help="legacy module_mp_kdm6ad.F (sha pin only)")
    ap.add_argument("--manifest", type=Path,
                    default=Path(__file__).with_name("cons_fortran_scope_manifest.json"))
    ap.add_argument("--json-out", type=Path, default=None)
    args = ap.parse_args()

    manifest = json.loads(args.manifest.read_text())
    report = {
        "checker": "check_cons_fortran_scope",
        "legacy": str(args.legacy),
        "cons": str(args.cons),
        "manifest": str(args.manifest),
        "pass": False,
        "failures": [],
        "sha256": {},
        "clusters": [],
        "handoff_blocks": [],
    }

    def fail(msg: str) -> None:
        report["failures"].append(msg)

    # ── (4) legacy sha pins ──────────────────────────────────────────────────
    legacy_sha = sha256_file(args.legacy)
    report["sha256"]["module_mp_kdm6.F"] = legacy_sha
    if legacy_sha != manifest["legacy_sha256"]["module_mp_kdm6.F"]:
        fail("legacy module_mp_kdm6.F sha256 does not match the pinned manifest")
    if args.legacy_wrapper is not None:
        wrap_sha = sha256_file(args.legacy_wrapper)
        report["sha256"]["module_mp_kdm6ad.F"] = wrap_sha
        if wrap_sha != manifest["legacy_sha256"]["module_mp_kdm6ad.F"]:
            fail("legacy module_mp_kdm6ad.F sha256 does not match the pinned manifest")

    legacy_text = args.legacy.read_text()
    cons_text = args.cons.read_text()
    cons_norm = normalize_cons(cons_text)
    report["sha256"]["module_mp_kdm6_cons.F"] = sha256_file(args.cons)

    # ── (1)+(2) rename-normalized diff must equal the pinned edit set ───────
    clusters = cluster_diff(legacy_text.split("\n"), cons_norm.split("\n"))
    allowed = manifest["allowed_edits"]
    n = max(len(clusters), len(allowed))
    for idx in range(n):
        got = clusters[idx] if idx < len(clusters) else None
        want = allowed[idx] if idx < len(allowed) else None
        entry = {
            "name": want["name"] if want else "UNEXPECTED-EDIT",
            "legacy_span": got["legacy_span"] if got else None,
            "cons_span": got["cons_span"] if got else None,
            "n_old": len(got["old"]) if got else 0,
            "n_new": len(got["new"]) if got else 0,
            "match": False,
        }
        if got is None:
            fail(f"pinned edit missing from cons file: {want['name']}")
        elif want is None:
            fail(f"edit outside the allowed set at legacy lines {got['legacy_span']}")
        elif got["old"] != want["old"] or got["new"] != want["new"]:
            fail(f"edit content drifted from the pinned manifest: {want['name']} "
                 f"(legacy lines {got['legacy_span']})")
        else:
            entry["match"] = True
        report["clusters"].append(entry)

    # ── (3) raw ice-velocity handoff blocks byte-identical ──────────────────
    for blk in manifest["handoff_blocks"]:
        text = "\n".join(blk["lines"])
        in_legacy = legacy_text.count(text)
        in_cons = cons_text.count(text)
        ok = in_legacy == blk["expect_count"] and in_cons == blk["expect_count"]
        report["handoff_blocks"].append(
            {"name": blk["name"], "count_legacy": in_legacy,
             "count_cons": in_cons, "expect": blk["expect_count"], "match": ok}
        )
        if not ok:
            fail(f"raw ice-velocity handoff block not byte-identical: {blk['name']}")

    report["pass"] = not report["failures"]

    out = json.dumps(report, indent=2)
    if args.json_out:
        args.json_out.write_text(out + "\n")
    print(out)
    print(f"\ncheck_cons_fortran_scope: {'PASS' if report['pass'] else 'FAIL'}",
          file=sys.stderr)
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
