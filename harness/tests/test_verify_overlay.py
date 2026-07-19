#!/usr/bin/env python3
"""Regression tests for the G3.3-M overlay verifier (harness/g33_overlay/verify_overlay.py).

The verifier is what stands between "the instrumented build only ADDS diagnostics"
and "the instrumented build quietly computes different physics". It reached its
current form by repeatedly being bypassed, so every bypass that was ever found is
pinned here:

  macro-off identity      -> bypassed by `#ifndef KDM6_G33_OP_DUMP … #else …`
  + subsequence check     -> bypassed by an OVERRIDE (canonical line kept, an
                             added line reassigns it)
  + assignment rule       -> bypassed by torch in-place methods, `.at(k) =`,
                             swap/move, aliases, multi-line assignment
  + receiver-based rule   -> bypassed by CHAINED accessors: `.at(k).copy_()`

Each test states the attack it encodes so a future simplification cannot quietly
reopen one.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1] / "g33_overlay"
REPO = Path(__file__).resolve().parents[2]

_spec = importlib.util.spec_from_file_location("verify_overlay", HERE / "verify_overlay.py")
v = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v)

CANON = (REPO / "libtorch/src/sedimentation.cpp").read_text()
BASE = CANON.splitlines()


def _mutates(line: str):
    """Findings for a macro-ON projection = canonical + one added line."""
    return v.overriding_assignments(CANON, BASE + [line])


# ── the real overlay must stay clean (no false positives) ────────────────────
def test_real_overlay_passes_all_four_checks():
    assert v.main() == 0


def test_real_overlay_has_no_mutation_findings():
    overlay = (HERE / "sedimentation.cpp.overlay").read_text()
    on = v._project(overlay, macro_on=True)
    assert v.overriding_assignments(CANON, on) == []


def test_comments_and_reads_are_not_flagged():
    assert _mutates("        // falk_qr_top = note about qr_cols[k]") == []
    assert _mutates("        auto s1 = dend_col(k) * g33_q_entry;") == []
    assert _mutates('        G33_REC(g33, "op", "TOP", 0, "qr", "QR_FALK", "f", s1);') == []
    assert _mutates("        auto tmp = qr_cols[k].clone();") == []   # clone is NOT in-place


# ── shape attacks (checks 2 and 3) ───────────────────────────────────────────
def test_ifndef_substitution_rejected():
    # macro-off text stays identical while macro-ON runs different arithmetic
    src = "int a = 1;\n#ifndef KDM6_G33_OP_DUMP\nint y = 2;\n#else\nint y = 999;\n#endif\n"
    with pytest.raises(v.OverlayShape, match="ifndef"):
        v.macro_off(src)


def test_code_in_else_of_g33_frame_rejected():
    src = "#ifdef KDM6_G33_OP_DUMP\nint y = 999;\n#else\nint y = 2;\n#endif\n"
    with pytest.raises(v.OverlayShape, match="substitution"):
        v.macro_off(src)


_SUB = "int y = 999;"


@pytest.mark.parametrize("src,why", [
    (f"#ifndef KDM6_G33_OP_DUMP\nint y=2;\n#else\n{_SUB}\n#endif\n", "plain"),
    (f"#  ifndef KDM6_G33_OP_DUMP\nint y=2;\n#else\n{_SUB}\n#endif\n", "spaces after #"),
    (f"#\tifndef KDM6_G33_OP_DUMP\nint y=2;\n#else\n{_SUB}\n#endif\n", "tab after #"),
    (f"#ifndef  KDM6_G33_OP_DUMP  // note\nint y=2;\n#else\n{_SUB}\n#endif\n", "trailing comment"),
    (f"#if defined(KDM6_G33_OP_DUMP)\n{_SUB}\n#else\nint y=2;\n#endif\n", "#if defined()"),
    (f"#if !defined(KDM6_G33_OP_DUMP)\nint y=2;\n#else\n{_SUB}\n#endif\n", "#if !defined()"),
    (f"#  ifdef KDM6_G33_OP_DUMP\n{_SUB}\n#  else\nint y=2;\n#  endif\n", "spaced ifdef/else code"),
    (f"#ifdef KDM6_G33_OP_DUMP\n{_SUB}\n#else // macro off\nint y=2;\n#endif\n", "#else + comment"),
])
def test_directive_parsing_cannot_be_evaded_by_whitespace_or_comments(src, why):
    # The C preprocessor allows arbitrary whitespace between `#` and the directive
    # and a trailing comment. Prefix matching (`startswith("#ifndef …")`,
    # `s == "#else"`) failed OPEN: `#  ifndef KDM6_G33_OP_DUMP` slipped past the
    # ban that closes the substitution attack, and `#else // note` was not seen as
    # an #else at all, corrupting frame tracking.
    with pytest.raises(v.OverlayShape):
        v.macro_off(src)


def test_spaced_directives_still_work_for_benign_overlays():
    src = ("#  ifdef KDM6_G33_OP_DUMP\n#  define X real\n#  else\n"
           "#  define X noop\n#  endif\nint a = 1;\n")
    assert "int a = 1;" in v.macro_off(src)


def test_directive_only_else_is_allowed():
    src = ("#ifdef KDM6_G33_OP_DUMP\n#define X(a) real(a)\n#else\n"
           "#define X(a) do{}while(0)\n#endif\nint a = 1;\n")
    assert "int a = 1;" in v.macro_off(src)


def test_deletion_under_macro_on_is_caught_by_subsequence():
    canon = ["int a = 1;", "int keep = 2;", "int b = 3;"]
    assert v._is_subsequence(canon, ["int a = 1;", "int b = 3;"]) == 1
    assert v._is_subsequence(canon, canon + ["added;"]) is None


# ── mutation attacks (check 4) — every historical bypass ─────────────────────
@pytest.mark.parametrize("attack", [
    "        falk_qr_top = bogus;",                       # plain override
    "        fall_qr_cols[k] += bogus;",                  # compound assignment
    "        qr_cols.at(k) = bogus;",                     # parenthesised subscript
    "        qr_cols[k].copy_(bogus);",                   # torch in-place, no '='
    "        fall_qr_cols[k].add_(bogus);",               # in-place on accumulator
    "        qr_cols.at(k).copy_(bogus);",                # CHAINED accessor + in-place
    "        qr_cols.select(-1, k).zero_();",             # chained select
    "        fall_qr_cols[k].t().add_(bogus);",           # chained transpose
    "        qr_cols.at(k).slice(0, 1).mul_(2.0);",       # deep chain
    "        qr_cols.at(k).data()[0] = bogus;",           # chained accessor assignment
    "        std::swap(qr_cols[k], bogus);",              # mutation without assignment
    "        auto& r = qr_cols[k];",                      # mutable reference alias
    "        auto* p = &falk_qr_top;",                    # address-of alias
])
def test_mutation_of_production_value_is_flagged(attack):
    found = _mutates(attack)
    assert found, f"tripwire missed: {attack.strip()}"


@pytest.mark.parametrize("lines", [
    ["        falk_qr_top", "            = bogus;"],                  # split plain
    ["        fall_qr_cols[k]", "            += bogus;"],             # split COMPOUND
    ["        fall_qr_cols[k]", "            -= bogus;"],
    ["        qr_cols[k]", "            .copy_(bogus);"],             # split IN-PLACE
    ["        qr_cols", "            .at(k).zero_();"],               # split + chained
    ["        qr_cols[k]", "            +=", "            bogus;"],   # three-line split
])
def test_mutation_split_across_lines_is_flagged(lines):
    # The receiver sits on one line and the operator on the next, so a per-line
    # scan sees an empty LHS. An earlier version joined lines only when the
    # continuation began with `=`, which missed every compound/in-place split.
    assert v.overriding_assignments(CANON, BASE + lines), f"missed split: {lines}"


def test_line_join_does_not_splice_unrelated_regions():
    # the join must stop at `;` and at a non-adjacent line, or it manufactures
    # false positives (this shape previously tripped on the parameter name `k`)
    assert v.overriding_assignments(CANON, BASE + [
        "    private:",
        "        static std::string f(const char* k) { const char* v = getenv(k); return v; }",
    ]) == []


@pytest.mark.parametrize("cpp", [
    '        auto s = std::string("//"); qr_cols[k] = bogus;',
    '        auto u = "http://x"; qr_cols[k].copy_(b);',
    "        char c = '/'; qr_cols[k] = bogus;",
    '        auto s = "a\\"//b"; qr_cols[k] = bogus;',      # escaped quote, // INSIDE the string
])
def test_comment_stripping_is_string_literal_aware(cpp):
    # A naive `line.find("//")` truncates at a `//` inside a STRING LITERAL and
    # discards everything after it — so appending a URL or a "//" literal in front
    # of a mutation hid the mutation completely.
    assert v.overriding_assignments(CANON, BASE + [cpp]), f"literal-hidden mutation missed: {cpp}"


@pytest.mark.parametrize("cpp", [
    '        auto s = R"(http://x)"; qr_cols[k] = bogus;',
    '        auto s = R"(a"b//c)"; qr_cols[k] = bogus;',      # QUOTE inside the raw text
    '        auto s = R"tag(a"b//c)tag"; qr_cols[k] = bogus;',  # custom delimiter
    '        auto s = LR"(a"b//c)"; qr_cols[k] = bogus;',     # encoding prefix
    '        auto s = R"(a"b)"; qr_cols[k].copy_(b);',        # then an in-place mutation
])
def test_raw_string_literals_do_not_hide_mutations(cpp):
    # A RAW string parsed as an ordinary one closes early at the `"` inside its
    # text; the following `//` then reads as a comment and the rest of the line —
    # the mutation — is discarded. R"delim( … )delim" must be lexed properly.
    assert v.overriding_assignments(CANON, BASE + [cpp]), f"raw-string-hidden mutation missed: {cpp}"


@pytest.mark.parametrize("cpp", [
    '        auto s = "a"; // qr_cols[k] = bogus;',          # genuinely commented out
    "        /* qr_cols[k] = x */ auto t = 1;",              # block comment
    '        auto s = "qr_cols[k] = bogus";',                # inside a string: not code
    '        auto s = R"(qr_cols[k] = bogus)";',             # inside a raw string
])
def test_code_that_is_not_executed_is_not_flagged(cpp):
    assert v.overriding_assignments(CANON, BASE + [cpp]) == []


@pytest.mark.parametrize("cpp", [
    "        if (c) { qr_cols[k] = bogus; }",                # inside a braced block
    "        [&]{ qr_cols[k] = bogus; }();",                 # inside a lambda
    "        for (qr_cols[k] = bogus;;) break;",             # in a for-init
    "        (void)0, qr_cols[k] = bogus;",                  # after a comma operator
    "        qr_cols[idx(k)] = bogus;",                      # call-expression subscript
    "        qr_cols[k]=bogus;",                             # no spaces
])
def test_mutation_in_awkward_syntactic_positions_is_flagged(cpp):
    assert v.overriding_assignments(CANON, BASE + [cpp]), f"missed: {cpp}"


@pytest.mark.parametrize("lines", [
    ['        auto s = R"x(', '        )x" ; qr_cols[k] = bogus;'],
    ['        auto s = R"(', '        )" ; qr_cols[k].copy_(b);'],
    ['        /* open', '        end */ qr_cols[k] = bogus;'],
])
def test_multiline_literal_state_is_carried_across_lines(lines):
    # A per-line lexer forgets it is inside a multi-line raw string, so the
    # terminator line looks like it OPENS a string; with literal content blanked,
    # everything after — the mutation — vanished unseen.
    assert v.overriding_assignments(CANON, BASE + lines), f"multi-line bypass: {lines}"


@pytest.mark.parametrize("lines", [
    ['        auto s = R"(', '        qr_cols[k] = bogus;', '        )";'],
    ['        /* c', '        qr_cols[k] = bogus;', '        */'],
])
def test_mutation_inside_a_multiline_literal_or_comment_is_not_flagged(lines):
    # the same state tracking must not flag text that is string content or a
    # comment body — it never executes
    assert v.overriding_assignments(CANON, BASE + lines) == []


def test_unterminated_raw_string_at_eof_is_a_hard_error():
    # previously asserted to be "clean" on the reasoning that the remainder is
    # string content. With state carried across lines that is no longer decidable
    # locally: an unterminated raw string at EOF is invalid C++, and treating it
    # as content would blank everything after it unchecked.
    with pytest.raises(v.OverlayShape, match="unterminated"):
        v._clean_lines(['        auto s = R"(abc  qr_cols[k] = bogus;'])


def test_unterminated_ordinary_literal_is_a_hard_error():
    # a C++ string/char literal cannot span a line; leaving one open would blank
    # the rest of the line unchecked, so it must raise rather than pass
    with pytest.raises(v.OverlayShape, match="unterminated"):
        v._clean_lines(['        auto s = "oops ; qr_cols[k] = bogus;'])


def test_targets_are_derived_from_canonical_not_hardcoded():
    t = v._assignment_targets(CANON)
    assert {"qr_cols", "falk_qr_top", "fall_qr_cols"} <= t
    assert len(t) > 50            # the real file assigns many production values


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
