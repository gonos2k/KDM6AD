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
                            f"--algo={algo}"], capture_output=True, text=True,
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
    real = nl.state
    full = real(drivers["legacy"], (3,))
    short = {k: v for k, v in list(full.items())[:-1]}
    monkeypatch.setattr(nl, "state",
                        lambda d, t: full if tuple(t) == (3,) else short)
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
    real = nl.state
    for drop in (3, 2):
        monkeypatch.setattr(nl, "state", lambda d, t, c=drop: {
            k: v for k, v in real(d, t).items() if k[1] != c})
        with pytest.raises(ra.RefineError, match="fixture declares"):
            nl.analysis(drivers["legacy"], FIXTURE)


def test_dropping_the_SEA_column_would_have_HIDDEN_a_partition(drivers,
                                                               monkeypatch):
    """Why this is not merely a tidiness check. Column 2 is the sea column, and
    `(1,1,1)` differs ONLY there -- so a run silently missing it reports that
    partition as clean. `(2,1)` survives because it also differs in column 1,
    which is exactly the trap: the tool would still look like it was working."""
    real = nl.state
    monkeypatch.setattr(nl, "state", lambda d, t: {
        k: v for k, v in real(d, t).items() if k[1] != 2})
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
