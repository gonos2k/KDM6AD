#!/usr/bin/env python3
"""Prove the G3.3-M C++ overlay is a PURE #ifdef addition (protocol §5, §6, §10).

Four fail-closed checks, run before any diagnostic build:
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
     check 3 catches any deletion or reordering of a production line;
  4. a TRIPWIRE: no ADDED line may mutate a production value. Check 3 only proves
     nothing was DELETED — it is blind to an OVERRIDE, where the canonical line
     survives (so the subsequence still matches) and an added line reassigns it:
         auto falk_qr_top = (…canonical…);      // present -> check 3 passes
         #ifdef KDM6_G33_OP_DUMP
         falk_qr_top = <different arithmetic>;  // added line overrides it
         #endif
     It flags the mutation forms a text scan can see: plain/compound assignment,
     an assignment split across lines, `.at(i) = …`, torch IN-PLACE methods
     (trailing `_`, e.g. copy_/add_/zero_ — these mutate with no `=` at all and
     are the dominant torch idiom), swap/move onto a production value, and taking
     a mutable reference or address of one.
Exit 0 only if all four hold.

SCOPE — these are STATIC checks. Checks 1-3 are sound: the base is pinned, the
macro-off text is identical, and nothing is deleted or reordered. Check 4 is a
TRIPWIRE, not a proof — aliasing defeats any textual rule (a reference obtained
indirectly, a lambda capture by reference, or a helper that mutates its argument
is invisible in the text). NONE of this establishes non-invasiveness: added code
can still perturb state, tensor layout, or dispatch. Only the 3-way
`A_output == B_output == C_output` run (§10) can establish that. Never cite this
script as a non-invasiveness certificate.
"""
from __future__ import annotations

import hashlib, re, sys, difflib
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


_ASSIGN = re.compile(r"\b([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*(?:\+|-|\*|/)?=(?!=)")


def _assignment_targets(text: str) -> set:
    """Identifiers the text ASSIGNS TO (including `auto X = ...` declarations)."""
    return {m.group(1) for m in _ASSIGN.finditer(text)} - {"if", "for", "while", "return"}


def _added_lines(canon_lines: list[str], on_lines: list[str]) -> list[tuple]:
    """Lines present under macro-ON that the canonical subsequence does not consume."""
    out, ci = [], 0
    for i, line in enumerate(on_lines, 1):
        if ci < len(canon_lines) and line == canon_lines[ci]:
            ci += 1
        else:
            out.append((i, line))
    return out


def overriding_assignments(canon: str, on_lines: list[str]) -> list[tuple]:
    """TRIPWIRE for added code that mutates a production value.

    The subsequence test only proves nothing was DELETED. It cannot see an
    OVERRIDE, where the canonical line survives and an added line reassigns it:

        auto falk_qr_top = (…canonical…);   // still present -> subsequence passes
        #ifdef KDM6_G33_OP_DUMP
        falk_qr_top = <different arithmetic>;   // ADDED line silently overrides it
        #endif

    This catches the mutation forms that a text scan CAN see, on every added line:
      * plain and compound assignment            X = / X[k] += …
      * an assignment split across lines         X\\n    = …
      * `.at(i) = …`                             X.at(k) = …
      * torch IN-PLACE methods (trailing `_`)    X.copy_(…), X[k].add_(…), X.zero_()
        — these mutate with NO `=` at all and were previously invisible, which
        matters most here because that is the dominant torch mutation idiom
      * std::swap / std::move onto a production value
      * binding a mutable reference or address to a production value
        (auto& r = X;  auto* p = &X;) — the alias itself is the escape hatch

    LIMIT — this is a tripwire, NOT a proof. Aliasing defeats any textual rule:
    a reference obtained indirectly, a lambda capture by reference, or a helper
    that mutates its argument cannot be seen in the text. Only the 3-way
    A==B==C output equality (§10) can establish that the instrumented build did
    not perturb the computation.
    """
    targets = _assignment_targets(canon)
    added = _added_lines(canon.splitlines(), on_lines)
    bad = []

    def flag(lineno, name, line, why):
        bad.append((lineno, f"{name} ({why})", line.strip()))

    # join added lines pairwise so an assignment split across a newline is seen
    joined = [(ln, txt) for ln, txt in added]
    for idx, (lineno, line) in enumerate(joined):
        probe = line
        if idx + 1 < len(joined) and not line.rstrip().endswith(";"):
            probe = line.rstrip() + " " + joined[idx + 1][1].strip()
        for m in _ASSIGN.finditer(probe):
            if m.group(1) in targets:
                flag(lineno, m.group(1), line, "assignment")
        for t in targets:
            tq = re.escape(t)
            # X.at(i) = …
            if re.search(rf"\b{tq}\s*\.\s*at\s*\([^)]*\)\s*=(?!=)", probe):
                flag(lineno, t, line, ".at() assignment")
            # torch in-place method: trailing underscore, e.g. copy_/add_/zero_
            if re.search(rf"\b{tq}\s*(?:\[[^\]]*\])?\s*\.\s*[A-Za-z_]\w*_\s*\(", probe):
                flag(lineno, t, line, "in-place method")
            # std::swap / std::move onto a production value
            if re.search(rf"\b(?:swap|move)\s*\([^)]*\b{tq}\b", probe):
                flag(lineno, t, line, "swap/move")
            # mutable alias: auto& r = X;   auto* p = &X;
            if re.search(rf"&\s*[A-Za-z_]\w*\s*=\s*[^;]*\b{tq}\b", probe) or \
               re.search(rf"=\s*&\s*{tq}\b", probe):
                flag(lineno, t, line, "mutable alias")
    # de-duplicate (a line can trip several patterns for the same target)
    seen, out = set(), []
    for item in bad:
        if item[:2] not in seen:
            seen.add(item[:2]); out.append(item)
    return out


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
        # Check 4: no ADDED line may assign to a production value. Checks 2+3
        # cannot see an override (the canonical line stays, an added line
        # reassigns it), which is substitution in every sense that matters.
        overrides = overriding_assignments(canon, on_lines)
        if overrides:
            print(f"FAIL {canon_rel}: {len(overrides)} added line(s) MUTATE a "
                  f"production value — that overrides the canonical computation "
                  f"under instrumentation:")
            for ln, name, txt in overrides[:5]:
                print(f"  macro-ON line {ln}: assigns {name!r} -> {txt[:90]}")
            rc = 1; continue
        print(f"OK {canon_rel}: base SHA pinned; macro-OFF TEXTUALLY IDENTICAL to "
              f"canonical; macro-ON is a strict in-order SUPERSET; mutation "
              f"tripwire clean ({len(_assignment_targets(canon))} production "
              f"targets checked)")
    if rc == 0:
        print("SCOPE: static only. Checks 1-3 are sound (base pinned, macro-off "
              "identical, nothing deleted/reordered). Check 4 is a TRIPWIRE, not a "
              "proof — aliasing defeats any textual rule (an indirectly-obtained "
              "reference, a by-reference lambda capture, a helper that mutates its "
              "argument). NONE of this establishes non-invasiveness. Only the 3-way "
              "A==B==C output equality (§10) can. Never cite this as a "
              "non-invasiveness certificate.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
