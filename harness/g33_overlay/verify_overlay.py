#!/usr/bin/env python3
"""Prove the G3.3-M C++ overlay is a PURE #ifdef addition (protocol §5, §6, §10).

Two fail-closed checks, run before any diagnostic build:
  1. the canonical source still matches the pinned base SHA-256 (no drift — the
     overlay was derived from that exact file);
  2. preprocessing the overlay with KDM6_G33_OP_DUMP UNDEFINED reproduces the
     canonical file TEXTUALLY — so every added line lives inside #ifdef and the
     macro-off build cannot differ (not even in line numbers / debug metadata).
Exit 0 only if both hold.

SCOPE — this proves configuration **A only** (macro undefined). It says NOTHING
about configurations B (macro defined, env unset) and C (macro defined, dumping):
executing the shadow ladder could in principle perturb results, so
`A_output == B_output == C_output` STILL REQUIRES the actual 3-way run (§10).
Do not cite this check as evidence that the instrumented build is non-invasive.
"""
import hashlib, sys, difflib
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PAIRS = [("libtorch/src/sedimentation.cpp", "sedimentation.cpp.overlay",
          "BASE_SHA256_sedimentation.cpp")]


def macro_off(text: str) -> list[str]:
    out, stack = [], []
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("#ifdef KDM6_G33_OP_DUMP"):
            stack.append("skip"); continue
        if s.startswith("#ifndef KDM6_G33_OP_DUMP"):
            stack.append("take"); continue
        if s == "#else" and stack:
            stack[-1] = "take" if stack[-1] == "skip" else "skip"; continue
        if s.startswith("#endif") and stack:
            stack.pop(); continue
        if all(x == "take" for x in stack):
            out.append(ln)
    # the only macro-off residue outside #ifdef is the no-op G33_REC #define
    return [l for l in out if not l.strip().startswith("#define G33_REC")]


def main() -> int:
    rc = 0
    for canon_rel, overlay_name, sha_name in PAIRS:
        canon_p = REPO / canon_rel
        canon = canon_p.read_text()
        pinned = (HERE / sha_name).read_text().strip()
        actual = hashlib.sha256(canon.encode()).hexdigest()
        if actual != pinned:
            print(f"FAIL {canon_rel}: canonical drifted from the pinned base\n"
                  f"  pinned={pinned}\n  actual={actual}\n"
                  f"  -> re-derive the overlay against the new canonical before building")
            rc = 1; continue
        residue = macro_off((HERE / overlay_name).read_text())
        if residue != canon.splitlines():
            print(f"FAIL {canon_rel}: macro-OFF overlay differs from canonical")
            print("\n".join(list(difflib.unified_diff(
                canon.splitlines(), residue, "canonical", "overlay-macro-off",
                lineterm="", n=1))[:30]))
            rc = 1; continue
        print(f"OK {canon_rel}: base SHA pinned + macro-OFF overlay TEXTUALLY IDENTICAL "
              f"(pure #ifdef addition)")
    if rc == 0:
        print("SCOPE: config A (macro-off) only — B/C output equality still requires "
              "the 3-way A/B/C run (§10); this is NOT a non-invasiveness certificate.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
