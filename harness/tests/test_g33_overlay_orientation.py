"""Every whole-K tensor recorded by an overlay must reach the dump TOP-FIRST.

The Fortran side emits k = kte-k (top-first) for every stage; the C++ working
tensors are host-K (WRF bottom-first). A record that skips the flip lands each
column reversed in k, which reads downstream as a physics difference and is not
one -- it made the protocol-v9 four-leg run report the ProgB bundle as the first
divergence when, corrected, that bundle is bit-identical.

Nothing single-sided can see this: orientation is a relation between two
independently generated streams, and on a small fixture most blocks are constant
in k (empty columns, clamp-saturated values) and so cannot even distinguish the
two orders. So the invariant is enforced here, on the source, uniformly across
both translation units -- the convention has to hold in files written months
apart, which is why it is not hidden inside one TU's recorder class.
"""
import pathlib
import re

import pytest

OVERLAY_DIR = pathlib.Path(__file__).resolve().parents[1] / "g33_overlay"
OVERLAYS = ("runtime.cpp.overlay", "coordinator.cpp.overlay")

# Stages recorded per column (k = -1). They have no k axis to reverse.
COLUMN_STAGES = frozenset({"surface"})

# An operand is orientation-safe when it is one of:
#   flip_k(...)            -- flipped at the record site (the normal case)
#   <name>_pyc.<field>     -- an already-top-first copy; test_pyc_aggregates_are_
#                             all_flipped proves the aggregate earns the suffix
#   torch::full_like(...)  -- a broadcast scalar constant; no k structure at all
SAFE = (
    re.compile(r"^(?:\w+::)*flip_k\("),
    re.compile(r"^\w+_pyc\."),
    re.compile(r"^torch::full_like\("),
)

# `<name>_pyc` members assigned after construction, each derived from operands that
# are themselves already top-first. Listed rather than pattern-matched so a NEW
# reassignment fails here and gets read, instead of inheriting the suffix's promise.
REVIEWED_PYC_REASSIGNMENTS = {
    # preamble(cur_pyc, cf_pyc, ...) -- both arguments top-first, so its output is too.
    ("runtime.cpp.overlay", "cur_pyc.brs"): "pre_sed.progb.bg",
}


def _records(text):
    """Yield (stage, field, operand) for every G33_REC call, operands balanced."""
    for m in re.finditer(r'G33_REC\(\s*\w+\s*,\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*', text):
        i, depth = m.end(), 0
        while i < len(text):
            c = text[i]
            if c in "([{":
                depth += 1
            elif c in ")]}":
                if depth == 0:
                    break
                depth -= 1
            i += 1
        yield m.group(1), m.group(2), " ".join(text[m.end():i].split())


@pytest.mark.parametrize("name", OVERLAYS)
def test_whole_k_records_are_top_first(name):
    path = OVERLAY_DIR / name
    recs = list(_records(path.read_text()))
    assert recs, f"{name}: no G33_REC calls parsed -- the scanner has drifted"

    bad = [
        (stage, field, operand)
        for stage, field, operand in recs
        if stage not in COLUMN_STAGES
        and not any(p.match(operand) for p in SAFE)
    ]
    assert not bad, (
        f"{name}: {len(bad)} whole-K record(s) not top-first. Wrap the operand in "
        f"flip_k(...) -- host-K order reverses every column and reads as a physics "
        f"difference:\n"
        + "\n".join(f"  {s}.{f} <- {o}" for s, f, o in bad)
    )


def test_scanner_rejects_a_raw_host_k_operand():
    """The scanner must fail on the exact defect it exists to catch."""
    bad = list(_records(
        'G33_REC(g33, "micro_call_progb_aux", "rhox", pre2.progb.rhox);'))
    assert bad and not any(p.match(bad[0][2]) for p in SAFE)
    good = list(_records(
        'G33_REC(g33, "micro_call_progb_aux", "rhox", '
        'coord_g33ovl::flip_k(pre2.progb.rhox));'))
    assert good and any(p.match(good[0][2]) for p in SAFE)


@pytest.mark.parametrize("name", OVERLAYS)
def test_pyc_aggregates_are_all_flipped(name):
    """The `_pyc` suffix promises top-first; check the promise is actually kept."""
    text = (OVERLAY_DIR / name).read_text()
    seen = 0
    for m in re.finditer(r"\b\w+\s+(\w+_pyc)\s*\{([^}]*)\}", text):
        seen += 1
        members = [x.strip() for x in m.group(2).split(",") if x.strip()]
        assert members, f"{name}: {m.group(1)} aggregate parsed empty"
        unflipped = [x for x in members if not re.match(r"^(?:\w+::)*flip_k\(", x)]
        assert not unflipped, (
            f"{name}: {m.group(1)} claims top-first but these members are raw "
            f"host-K: {unflipped}")

    for m in re.finditer(r"\b(\w+_pyc\.\w+)\s*=\s*([^;]+);", text):
        key = (name, m.group(1))
        assert key in REVIEWED_PYC_REASSIGNMENTS, (
            f"{name}: {m.group(1)} is reassigned to `{' '.join(m.group(2).split())}` "
            f"after construction. Confirm the RHS is already top-first, then add it to "
            f"REVIEWED_PYC_REASSIGNMENTS -- the suffix alone does not make it so.")
        assert " ".join(m.group(2).split()) == REVIEWED_PYC_REASSIGNMENTS[key], (
            f"{name}: {m.group(1)} reassignment changed; re-confirm its orientation")

    if name == "runtime.cpp.overlay":
        assert seen >= 2, f"{name}: expected the cur_pyc/cf_pyc aggregates, found {seen}"


def test_both_overlays_define_the_same_flip():
    """One convention, spelled identically, in both TUs."""
    defs = {
        name: re.search(r"flip_k\s*=\s*\[\]\(.*?\{\s*return\s+(.*?);|"
                        r"flip_k\(const torch::Tensor& t\)\s*\{\s*return\s+(.*?);",
                        (OVERLAY_DIR / name).read_text())
        for name in OVERLAYS
    }
    bodies = set()
    for name, m in defs.items():
        assert m, f"{name}: no flip_k definition found"
        bodies.add((m.group(1) or m.group(2)).strip())
    assert bodies == {"torch::flip(t, {1})"}, (
        f"the two overlays flip differently: {bodies}")
