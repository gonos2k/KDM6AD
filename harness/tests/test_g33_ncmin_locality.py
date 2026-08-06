"""How much the scalar `ncmin` costs, not how many cells it touches.

LOCAL ONLY (needs gfortran + the gitignored host reference tree).
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_ncmin_locality as nl  # noqa: E402
import g33_refine_analyze as ra  # noqa: E402

FIXTURE = "g33_fixture_boundary_mapping_v1"

REPO = ROOT.parent
BUILD = ROOT / "g33_fortran" / "refine_build.sh"
REF = REPO / "host" / "KIM-meso_v1.0" / "phys" / "module_mp_kdm6.F"

pytestmark = pytest.mark.skipif(
    shutil.which("gfortran") is None or not REF.is_file(),
    reason="local-only (needs gfortran + the gitignored host reference tree)",
)


@pytest.fixture(scope="module")
def drivers(tmp_path_factory):
    out = {}
    for algo in ("legacy", "conservative"):
        d = tmp_path_factory.mktemp(f"ncmin-{algo}") / "build"
        b = subprocess.run(["bash", str(BUILD), str(d),
                            "--fixture=g33_fixture_boundary_mapping_v1",
                            f"--algo={algo}", "--nflux"],
                           capture_output=True, text=True,
                           cwd=REPO)
        assert b.returncode == 0, f"{algo} build failed:\n{b.stdout}\n{b.stderr}"
        out[algo] = str(d / "g33_refine_driver")
    return out


def test_the_partitions_are_every_CONTIGUOUS_split_not_just_even_ones():
    """`(1, 2)` differs in zero cells because both tiles end on land, so a gate
    that only tried even splits would pass while the operator was arbitrarily
    non-local. Exhaustiveness is what makes the zero row informative."""
    assert set(nl.compositions(3)) == {(3,), (1, 2), (2, 1), (1, 1, 1)}
    assert sum(sum(c) == 3 for c in nl.compositions(3)) == 4


def test_the_difference_is_reported_as_a_SIZE_not_only_a_COUNT(drivers):
    """The finding said "31 / 144 cells" and called it "a whole-state
    difference, not a rounding one". That was a count and an assertion: a count
    cannot separate a roundoff-scale difference from a dominating one."""
    a = nl.analysis(drivers["legacy"], FIXTURE)
    for tiles, r in a["partitions"].items():
        assert {"cells_differing", "max_rel", "is_roundoff_scale", "by_field"} \
            <= set(r), tiles
        for f, d in r["by_field"].items():
            assert {"cells", "max_rel", "max_ulps"} <= set(d), f


def test_the_partition_dependence_is_SIX_ORDERS_above_roundoff(drivers):
    """The measurement the owner's A/B/C decision needs. Accepting the partition
    dependence means accepting that cloud ice in an affected column is decided
    to O(1) by where the tile boundary falls -- not that it wobbles in the last
    bits."""
    a = nl.analysis(drivers["legacy"], FIXTURE)
    worst = a["partitions"]["2,1"]
    assert worst["cells_differing"] == 31
    assert worst["by_field"]["qi"]["max_rel"] > 0.9, \
        "cloud ice differs by ~100%, not by rounding"
    assert worst["max_rel"] / a["f32_eps"] > 1e6
    assert worst["is_roundoff_scale"] is False


def test_the_roundoff_verdict_can_come_out_TRUE(drivers, monkeypatch):
    """A verdict that is only ever False is not a verdict. Widening the
    threshold past the observed difference must flip it, or the check is
    reporting a constant."""
    a = nl.analysis(drivers["legacy"], FIXTURE)
    assert a["partitions"]["2,1"]["is_roundoff_scale"] is False
    monkeypatch.setattr(nl, "F32_EPS", 1.0)
    assert nl.analysis(drivers["legacy"], FIXTURE)["partitions"]["2,1"][
        "is_roundoff_scale"] is True


def test_ALL_TWELVE_prognostics_move_not_a_single_diagnostic(drivers):
    """A defect confined to one field could be argued as a diagnostic quirk.
    Every prognostic the stream carries moves in the affected columns."""
    fields = set(nl.analysis(drivers["legacy"], FIXTURE)["partitions"]["2,1"]["by_field"])
    assert len(fields) == 12, sorted(fields)


def test_the_CONSERVATIVE_interface_does_not_fix_it(drivers):
    """The finding argues from source that the two variants share this code.
    Measured rather than trusted -- and it means the P0-4b work does not touch
    this, so it stays open on its own terms."""
    leg = nl.analysis(drivers["legacy"], FIXTURE)["partitions"]
    con = nl.analysis(drivers["conservative"], FIXTURE)["partitions"]
    assert {t: r["cells_differing"] for t, r in leg.items()} == \
        {t: r["cells_differing"] for t, r in con.items()}
    assert {t: r["columns"] for t, r in leg.items()} == \
        {t: r["columns"] for t, r in con.items()}


def test_a_partition_whose_tiles_END_alike_shows_nothing(drivers):
    """The mechanism, as a prediction rather than a description: `ncmin` keeps
    the LAST column's threshold, so what matters is the surface type at each
    tile's `ite`. `(1, 2)` ends land/land like the whole domain."""
    assert nl.analysis(drivers["legacy"], FIXTURE)["partitions"]["1,2"][
        "cells_differing"] == 0


# ---- the analyzer must not accept an incomplete run as a clean one ----------

def _stream(drivers, tiles=(3,)):
    return subprocess.run([drivers["legacy"], "1", "rezero",
                           ",".join(map(str, tiles))],
                          capture_output=True, text=True).stdout


def test_an_EMPTY_run_is_refused_not_read_as_column_local(drivers):
    """The defect this section exists for. The first version parsed the lines
    itself, so a driver emitting nothing gave an empty dict, every partition
    then showed zero cells differing, and the report printed "identical
    gating" -- a completely broken run reading as the strongest possible pass."""
    with pytest.raises(ra.RefineError):
        nl.read_state("", label="empty")


def test_a_TRUNCATED_run_is_refused(drivers):
    """A run killed part way has no END. It would otherwise contribute whatever
    cells it managed to emit, and a short BASELINE reports FEWER differences --
    the flattering direction."""
    with pytest.raises(ra.RefineError):
        nl.read_state(_stream(drivers).replace("G33R END", "", 1),
                      label="truncated")


def test_a_DUPLICATE_record_is_refused(drivers):
    """A dict comprehension keeps the last write silently. The strict parser
    rejects the second record instead."""
    text = _stream(drivers)
    line = next(l for l in text.splitlines() if l.startswith("G33R STATE"))
    with pytest.raises(ra.RefineError):
        nl.read_state(text.replace(line, line + "\n" + line, 1), label="dup")


def test_a_partition_whose_CELL_UNIVERSE_differs_is_refused(drivers,
                                                            monkeypatch):
    """"How many cells differ" counted over whatever both happened to carry
    would silently compare a subset."""
    full = nl.read_state(nl.run(drivers["legacy"], (3,)), label="base")
    short = {k: v for k, v in list(full.items())[:-1]}
    monkeypatch.setattr(nl, "read_state",
                        lambda t, label: full if "3" == label[-1] else short)
    with pytest.raises(ra.RefineError):
        nl.analysis(drivers["legacy"], FIXTURE)


def test_the_strict_parser_is_REUSED_not_reimplemented():
    """The repeated defect in this repo is a new tool re-deriving a weaker set
    of checks beside the strict parser that already has them."""
    src = (ROOT / "g33_ncmin_locality.py").read_text()
    assert "ra.read_text(text, nsplit=1, label=label)" in src


def test_a_COMMONLY_reduced_universe_is_refused(drivers, monkeypatch):
    """Comparing a partition against the baseline only asks whether they agree
    with EACH OTHER, and a run that drops a column agrees with itself perfectly.
    With column 3 gone everywhere the tool reported `31/96` and a shrunken
    denominator as a normal result. Only a figure from OUTSIDE the run catches
    that, so it comes from the fixture source."""
    real = nl.read_state
    for drop in (3, 2):
        monkeypatch.setattr(nl, "read_state", lambda t, label, c=drop: {
            k: v for k, v in real(t, label=label).items() if k[1] != c})
        with pytest.raises(ra.RefineError, match="fixture declares"):
            nl.analysis(drivers["legacy"], FIXTURE)


def test_dropping_the_SEA_column_would_have_HIDDEN_a_partition(drivers,
                                                               monkeypatch):
    """Why this is not merely a tidiness check. Column 2 is the sea column, and
    `(1,1,1)` differs ONLY there -- so a run silently missing it reports that
    partition as clean. `(2,1)` survives because it also differs in column 1,
    which is exactly the trap: the tool would still look like it was working."""
    real = nl.read_state
    monkeypatch.setattr(nl, "read_state", lambda t, label: {
        k: v for k, v in real(t, label=label).items() if k[1] != 2})
    monkeypatch.setattr(nl, "_expect_universe", lambda *a, **k: None)
    p = nl.analysis(drivers["legacy"], FIXTURE)["partitions"]
    assert p["1,1,1"]["cells_differing"] == 0, \
        "(1,1,1) differs only in the sea column"
    assert p["2,1"]["cells_differing"] > 0, \
        "(2,1) still differs in column 1 -- the tool would look fine"


def test_the_expected_universe_comes_from_the_FIXTURE_not_the_run():
    """`fixture_dims` reads B and K from the fixture source, which the driver's
    output cannot influence. Shared with the bundle producer rather than
    re-derived beside it."""
    from g33_refine_experiment import fixture_dims, fixture_width

    assert fixture_dims(FIXTURE) == (3, 4)
    assert fixture_width(FIXTURE) == fixture_dims(FIXTURE)[0]


def test_a_SHIFTED_level_axis_is_refused(drivers):
    """Levels were checked by COUNT alone, so an axis shifted off its origin
    passed -- `{10,11,12,13}` has four entries too. The emitter writes
    `emit_fld(name, i, KM-k, ...)` over `k = 1..KM`, so the protocol's levels
    are `0..K-1` and that is checked as a SET, like the columns beside it."""
    full = nl.read_state(nl.run(drivers["legacy"], (3,)), label="base")
    for shift in (1, 10):
        moved = {(f, c, k + shift): v for (f, c, k), v in full.items()}
        with pytest.raises(ra.RefineError, match="levels"):
            nl._expect_universe(moved, 3, 4, f"shift+{shift}")


def test_a_REVERSED_axis_is_NOT_a_universe_property(drivers):
    """Stated rather than implied. `{0,1,2,3}` reversed is the same set, so no
    universe check can see it. It does not pass silently either: a reversal in
    one run and not the other makes nearly every cell differ, so it surfaces as
    an implausibly large result rather than a clean one."""
    full = nl.read_state(nl.run(drivers["legacy"], (3,)), label="base")
    flipped = {(f, c, 3 - k): v for (f, c, k), v in full.items()}
    nl._expect_universe(flipped, 3, 4, "reversed")       # accepted, by design
    differ = sum(full[k] != flipped[k] for k in full)
    assert differ > 0.8 * len(full), \
        "a reversal must be conspicuous in the comparison even though the " \
        "universe check cannot see it"


def test_the_intact_universe_is_accepted(drivers):
    """A gate that refused everything would also pass the tests above."""
    nl._expect_universe(nl.read_state(nl.run(drivers["legacy"], (3,)), label="base"), 3, 4, "intact")


def test_a_driver_that_VALIDATES_and_then_IGNORES_the_tiles_is_refused(drivers):
    """The control this replaced ran an INVALID spec and required a refusal --
    which only proves the argument is parsed and validated. Validation lives in
    the argument parser and use lives in the tile loop, so a driver that
    validated the spec and then called the kernel over the whole domain passed
    it. Every partition would equal the baseline, the tool would report zero
    differences everywhere, and that reads as "the operator is column-local".

    `G33N CALL_BEGIN` is written from INSIDE the tile loop with the very bounds
    handed to `kdm62D`, so the question is answered rather than approximated."""
    whole = nl.run(drivers["legacy"], (3,))          # always the whole domain
    for tiles in ((1, 1, 1), (2, 1)):
        with pytest.raises(ra.RefineError, match="not reaching the partitioning"):
            nl._expect_tiles_are_live(whole, tiles, f"tiles={tiles}")


def test_the_real_driver_calls_the_kernel_over_what_was_ASKED(drivers):
    """A gate that refused everything would also pass the test above."""
    for tiles in ((3,), (1, 2), (2, 1), (1, 1, 1)):
        text = nl.run(drivers["legacy"], tiles)
        nl._expect_tiles_are_live(text, tiles, f"tiles={tiles}")
        want, i = [], 0
        for t in tiles:
            want.append((i + 1, i + t))
            i += t
        assert nl.tile_brackets(text) == want


def test_a_build_that_cannot_answer_the_question_is_REFUSED(tmp_path):
    """Without `--nflux` nothing in the stream says which decomposition ran --
    `G33R BEGIN` carries nsplit, mode, algorithm and dtcld, not the tiles. The
    tool refuses rather than skipping the check, because "I could not verify
    this" must not read as "verified"."""
    d = tmp_path / "plain"
    b = subprocess.run(["bash", str(BUILD), str(d),
                        "--fixture=g33_fixture_boundary_mapping_v1",
                        "--algo=legacy"], capture_output=True, text=True, cwd=REPO)
    assert b.returncode == 0, b.stderr[-400:]
    with pytest.raises(ra.RefineError, match="--nflux"):
        nl.analysis(str(d / "g33_refine_driver"), FIXTURE)


def test_the_nflux_overlay_does_not_move_the_numbers(drivers, tmp_path):
    """The measurement now needs an instrumented build, so the instrumentation
    must be shown non-invasive ON THIS FIXTURE rather than assumed from the
    A/B/C proof elsewhere."""
    d = tmp_path / "plain"
    if not d.exists():
        subprocess.run(["bash", str(BUILD), str(d),
                        "--fixture=g33_fixture_boundary_mapping_v1",
                        "--algo=legacy"], capture_output=True, text=True, cwd=REPO)
    plain = str(d / "g33_refine_driver")
    for tiles in ((3,), (1, 1, 1), (2, 1)):
        a = nl.read_state(nl.run(plain, tiles), label="plain")
        b = nl.read_state(nl.run(drivers["legacy"], tiles), label="nflux")
        assert a == b, f"{tiles}: --nflux moved the STATE records"
