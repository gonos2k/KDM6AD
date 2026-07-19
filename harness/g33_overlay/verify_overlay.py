#!/usr/bin/env python3
"""Prove the G3.3-M C++ overlay is a PURE #ifdef addition (protocol §5, §6, §10).

Three fail-closed checks, run before any diagnostic build:
  1. the canonical source still matches the pinned base SHA-256 (no drift — the
     overlay was derived from that exact file);
  2. preprocessing the overlay with KDM6_G33_OP_DUMP UNDEFINED reproduces the
     canonical file TEXTUALLY — so every added line lives inside #ifdef and the
     macro-off build cannot differ (not even in line numbers / debug metadata);
  3. the macro-ON projection still contains every canonical line IN ORDER (a
     strict superset). Check 2 alone is blind to a SUBSTITUTION that only takes
     effect when the macro IS defined — e.g. `#ifndef KDM6_G33_OP_DUMP … #else
     <different arithmetic> #endif` leaves the macro-off text identical while the
     instrumented build runs different physics. `#ifndef KDM6_G33_OP_DUMP` is now
     rejected outright, an `#else` on a G33 frame may contain directives only, and
     check 3 catches any deletion or reordering of a production line.
Exit 0 only if all three hold.

SCOPE — this proves configuration **A only** (macro undefined). It says NOTHING
about configurations B (macro defined, env unset) and C (macro defined, dumping):
executing the shadow ladder could in principle perturb results, so
`A_output == B_output == C_output` STILL REQUIRES the actual 3-way run (§10).
Do not cite this check as evidence that the instrumented build is non-invasive.
"""
from __future__ import annotations

import hashlib, sys, difflib
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PAIRS = [("libtorch/src/sedimentation.cpp", "sedimentation.cpp.overlay",
          "BASE_SHA256_sedimentation.cpp")]


class OverlayShape(Exception):
    """The overlay uses a construct that makes 'pure addition' unprovable."""


def _project(text: str, macro_on: bool) -> list[str]:
    """Project the overlay for KDM6_G33_OP_DUMP defined / undefined.

    REJECTS `#ifndef KDM6_G33_OP_DUMP`: with an `#else` it is a SUBSTITUTION —
    the macro-off text can equal the canonical while the macro-ON build runs
    DIFFERENT arithmetic, and the old check would still certify "pure #ifdef
    addition". An `#else` on an #ifdef frame is allowed only when its branch is
    preprocessor-directives-only (the no-op G33_REC #define), i.e. emits no code.
    """
    out, stack = [], []          # stack: (emitting, frame_is_g33, in_else)
    for i, ln in enumerate(text.splitlines(), 1):
        s = ln.strip()
        if s.startswith("#ifndef KDM6_G33_OP_DUMP"):
            raise OverlayShape(
                f"line {i}: '#ifndef KDM6_G33_OP_DUMP' is forbidden — with an "
                f"#else it substitutes code under the macro while leaving the "
                f"macro-off text identical, which this check cannot distinguish "
                f"from a pure addition")
        if s.startswith("#ifdef KDM6_G33_OP_DUMP"):
            stack.append([macro_on, True, False]); continue
        if s.startswith("#if"):                      # unrelated conditional
            stack.append([True, False, False]); continue
        if s == "#else" and stack:
            fr = stack[-1]
            fr[0] = not fr[0] if fr[1] else fr[0]
            fr[2] = True
            continue
        if s.startswith("#endif") and stack:
            stack.pop(); continue
        if stack and stack[-1][1] and stack[-1][2] and not s.startswith("#") and s:
            raise OverlayShape(
                f"line {i}: non-directive code in the #else of a "
                f"KDM6_G33_OP_DUMP frame — that is substitution, not addition")
        if all(fr[0] for fr in stack):
            out.append(ln)
    return out


def macro_off(text: str) -> list[str]:
    # the only macro-off residue outside #ifdef is the no-op G33_REC #define
    return [l for l in _project(text, macro_on=False)
            if not l.strip().startswith("#define G33_REC")]


def _is_subsequence(small: list[str], big: list[str]) -> int | None:
    """Return None if `small` appears in `big` in order, else the failing index."""
    it = iter(big)
    for idx, line in enumerate(small):
        for cand in it:
            if cand == line:
                break
        else:
            return idx
    return None


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
        overlay_text = (HERE / overlay_name).read_text()
        try:
            residue = macro_off(overlay_text)
            on_lines = _project(overlay_text, macro_on=True)
        except OverlayShape as e:
            print(f"FAIL {canon_rel}: {e}")
            rc = 1; continue
        if residue != canon.splitlines():
            print(f"FAIL {canon_rel}: macro-OFF overlay differs from canonical")
            print("\n".join(list(difflib.unified_diff(
                canon.splitlines(), residue, "canonical", "overlay-macro-off",
                lineterm="", n=1))[:30]))
            rc = 1; continue
        # The decisive check: every canonical line must still appear, IN ORDER,
        # in the macro-ON projection. Macro-off identity alone cannot see a
        # substitution that only takes effect when the macro IS defined; this
        # subsequence test proves the instrumented build only ADDS lines and
        # never removes or replaces a production line.
        bad = _is_subsequence(canon.splitlines(), on_lines)
        if bad is not None:
            print(f"FAIL {canon_rel}: macro-ON projection is not a superset of the "
                  f"canonical source — production line {bad + 1} is missing or "
                  f"reordered under instrumentation:\n  {canon.splitlines()[bad]!r}")
            rc = 1; continue
        print(f"OK {canon_rel}: base SHA pinned; macro-OFF TEXTUALLY IDENTICAL to "
              f"canonical; macro-ON is a strict in-order SUPERSET (pure addition, "
              f"no substitution)")
    if rc == 0:
        print("SCOPE: config A (macro-off) only — B/C output equality still requires "
              "the 3-way A/B/C run (§10); this is NOT a non-invasiveness certificate.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
