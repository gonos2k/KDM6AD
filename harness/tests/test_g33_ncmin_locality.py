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
        assert {"components_differing", "max_rel", "is_roundoff_scale", "by_field"} \
            <= set(r), tiles
        for f, d in r["by_field"].items():
            assert {"components", "max_rel", "max_ulps", "max_abs"} <= set(d), f


def test_the_partition_dependence_is_SIX_ORDERS_above_roundoff(drivers):
    """The measurement the owner's A/B/C decision needs. Accepting the partition
    dependence means accepting that cloud ice in an affected column is decided
    to O(1) by where the tile boundary falls -- not that it wobbles in the last
    bits."""
    a = nl.analysis(drivers["legacy"], FIXTURE)
    worst = a["partitions"]["2,1"]
    assert worst["components_differing"] == 31
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
    assert {t: r["components_differing"] for t, r in leg.items()} == \
        {t: r["components_differing"] for t, r in con.items()}
    assert {t: r["columns"] for t, r in leg.items()} == \
        {t: r["columns"] for t, r in con.items()}


def test_a_partition_whose_tiles_END_alike_shows_nothing(drivers):
    """The mechanism, as a prediction rather than a description: `ncmin` keeps
    the LAST column's threshold, so what matters is the surface type at each
    tile's `ite`. `(1, 2)` ends land/land like the whole domain."""
    assert nl.analysis(drivers["legacy"], FIXTURE)["partitions"]["1,2"][
        "components_differing"] == 0


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
    full = nl.read_records(nl.run(drivers["legacy"], (3,)), label="base")
    short = {k: v for k, v in full.items()
             if not (k[0] == "state" and k[1:] == list(
                 kk[1:] for kk in full if kk[0] == "state")[-1])}
    monkeypatch.setattr(nl, "read_records",
                        lambda t, label: full if label.endswith("3") else short)
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
    real = nl.read_records
    for drop in (3, 2):
        monkeypatch.setattr(nl, "read_records", lambda t, label, c=drop: {
            k: v for k, v in real(t, label=label).items() if k[2] != c})
        with pytest.raises(ra.RefineError, match="fixture declares"):
            nl.analysis(drivers["legacy"], FIXTURE)


def test_dropping_the_SEA_column_would_have_HIDDEN_a_partition(drivers,
                                                               monkeypatch):
    """Why this is not merely a tidiness check. Column 2 is the sea column, and
    `(1,1,1)` differs ONLY there -- so a run silently missing it reports that
    partition as clean. `(2,1)` survives because it also differs in column 1,
    which is exactly the trap: the tool would still look like it was working."""
    real = nl.read_records
    monkeypatch.setattr(nl, "read_records", lambda t, label: {
        k: v for k, v in real(t, label=label).items() if k[2] != 2})
    monkeypatch.setattr(nl, "_expect_universe", lambda *a, **k: None)
    p = nl.analysis(drivers["legacy"], FIXTURE)["partitions"]
    assert p["1,1,1"]["components_differing"] == 0, \
        "(1,1,1) differs only in the sea column"
    assert p["2,1"]["components_differing"] > 0, \
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
    with pytest.raises(Exception, match="no G33N records"):
        nl.analysis(str(d / "g33_refine_driver"), FIXTURE)


def test_the_nflux_overlay_does_not_move_the_numbers(drivers, tmp_path):
    """The measurement now needs an instrumented build, so the instrumentation
    must be shown non-invasive ON THIS FIXTURE rather than assumed from the
    A/B/C proof elsewhere.

    Over the PUBLISHED SCOPE, which is both algorithms and all four partitions
    -- the first version checked legacy and three partitions while the finding
    said "all four", claiming coverage it had not measured."""
    for algo in ("legacy", "conservative"):
        d = tmp_path / f"plain-{algo}"
        if not d.exists():
            b = subprocess.run(["bash", str(BUILD), str(d),
                                "--fixture=g33_fixture_boundary_mapping_v1",
                                f"--algo={algo}"], capture_output=True,
                               text=True, cwd=REPO)
            assert b.returncode == 0, b.stderr[-400:]
        plain = str(d / "g33_refine_driver")
        for tiles in ((3,), (1, 2), (2, 1), (1, 1, 1)):
            a = nl.read_state(nl.run(plain, tiles), label="plain")
            b = nl.read_state(nl.run(drivers[algo], tiles), label="nflux")
            assert a == b, f"{algo} {tiles}: --nflux moved the STATE records"


# ---- owner §11.1 / §11.3 / §11.4: what the numbers actually mean ------------

def test_144_is_state_COMPONENTS_not_grid_cells(drivers):
    """12 fields x 3 columns x 4 levels. The grid has TWELVE cells, so calling
    the 144 "cells" overstated the spatial extent twelvefold (owner §11.1)."""
    r = nl.analysis(drivers["legacy"], FIXTURE)["partitions"]["2,1"]
    assert r["components_total"] == 144
    assert r["grid_cells"] == 12
    assert r["components_total"] == len(ra.STATE_FIELDS) * r["grid_cells"]


def test_the_ABSOLUTE_difference_is_reported_beside_the_relative(drivers):
    """A ratio near 1 says the two runs disagree about a value, not that the
    value is large: `qi` reaches 0.9966 on a 6.6e-08 baseline (owner §11.3)."""
    d = nl.analysis(drivers["legacy"], FIXTURE)["partitions"]["2,1"]["by_field"]
    assert d["qi"]["max_rel"] > 0.99
    assert d["qi"]["max_abs"] < 1e-4, "the absolute qi difference is small"
    assert d["qi"]["max_abs_baseline"] < 1e-6, "on a near-zero baseline"


def test_the_COLUMN_INTEGRAL_is_what_makes_it_a_physical_statement(drivers):
    """Integrated under rho*dz, the defensible headline is column RAIN mass at
    21-26%, not cloud ice at 100%."""
    ci = nl.analysis(drivers["legacy"], FIXTURE)["partitions"]["2,1"][
        "column_integrated"]
    assert 0.20 < ci["1/qr"]["rel"] < 0.22
    assert 0.25 < ci["2/qr"]["rel"] < 0.27
    for c in (1, 2):
        assert 0.02 < ci[f"{c}/total_condensate"]["rel"] < 0.04


def test_the_ULP_metric_is_ORDER_PRESERVING_across_zero(drivers):
    """A raw signed-int32 difference is the representable-step distance only for
    same-sign positives -- it made +0.0 and -0.0 look 2^31 apart (owner
    §11.4)."""
    import struct

    def hx(v):
        return struct.pack(">f", v).hex().upper()

    assert nl._ulps(hx(0.0), hx(-0.0)) == 1
    assert nl._ulps(hx(1.0), hx(1.0)) == 0
    assert nl._ulps(hx(1.0), hx(struct.unpack(">f", struct.pack(">I", 0x3F800001))[0])) == 1
    assert nl._ulps(hx(-1.0), hx(struct.unpack(">f", struct.pack(">I", 0xBF800001))[0])) == 1
    # Monotonic: the ordering must be strictly increasing in the value.
    keys = [nl._ordered(hx(v)) for v in (-2.0, -1.0, -0.0, 0.0, 1.0, 2.0)]
    assert keys == sorted(keys)


# ---- owner P0-E1 / P0-S1: the gate reads the strict protocol, and the two ----
# ---- runs are proved to be the same atmosphere ------------------------------

def test_the_tile_gate_uses_the_STRICT_G33N_parser(drivers):
    """It scanned for the `G33N CALL_BEGIN` token. A valid G33R block plus two
    FORGED CALL_BEGIN lines -- no STREAM_BEGIN, no STREAM_END, no CALL_END, no
    records of any kind -- produced exactly the brackets asked for and passed
    the liveness gate, while `nt.calls()` rejects that stream on its first
    record (owner P0-E1)."""
    real = nl.run(drivers["legacy"], (3,))
    g33r = "\n".join(l for l in real.splitlines() if l.startswith("G33R"))
    forged = (g33r + "\nG33N CALL_BEGIN 1 1 1 1 2 4 42700000"
                     "\nG33N CALL_BEGIN 2 1 2 3 3 4 42700000\n")
    with pytest.raises(Exception):
        nl._expect_tiles_are_live(forged, (2, 1), "forged")
    # and the real streams still pass, so the gate is not simply refusing all
    for tiles in ((3,), (2, 1), (1, 1, 1)):
        nl._expect_tiles_are_live(nl.run(drivers["legacy"], tiles), tiles, "real")


def test_a_TRUNCATED_G33N_stream_is_refused(drivers):
    """The strict parser brings framing checks the token scan had none of."""
    text = nl.run(drivers["legacy"], (2, 1))
    for cut in ("G33N STREAM_END", "G33N CALL_END"):
        broken = text.replace(cut, "", 1)
        with pytest.raises(Exception):
            nl._expect_tiles_are_live(broken, (2, 1), cut)


def test_the_two_runs_are_proved_to_be_the_SAME_ATMOSPHERE(drivers):
    """Without this the analysis attributes every difference to `ncmin` having
    checked only the cell universe. A driver that transposed the column mapping
    would satisfy that, produce large differences, and read as a strong effect
    -- and "a large difference is suspicious" cannot separate the two, because a
    large difference is what this tool reports (owner P0-S1)."""
    base = nl.read_records(nl.run(drivers["legacy"], (3,)), label="base")
    got = nl.read_records(nl.run(drivers["legacy"], (2, 1)), label="got")
    nl._expect_same_inputs(base, got, "real")           # holds on real runs

    for cls, name in (("initial", "qr"), ("forcing", "rho")):
        key = next(k for k in base if k[0] == cls and k[1] == name)
        tampered = dict(got)
        tampered[key] = "DEADBEEF"
        with pytest.raises(ra.RefineError, match="same atmosphere"):
            nl._expect_same_inputs(base, tampered, "tampered")


def test_the_MECHANISM_predicts_which_columns_differ_and_it_holds(drivers):
    """The causal statement, in the form that can actually attribute. `ncmin`
    keeps the LAST column's threshold, so a column differs exactly when its
    tile ends on a surface type other than the whole domain's. Derived from the
    fixture's own XLAND_BITS -- land, sea, land -- and matched against
    observation for every partition."""
    assert nl.fixture_xland(FIXTURE) == {1: 1.0, 2: 2.0, 3: 1.0}
    a = nl.analysis(drivers["legacy"], FIXTURE)["partitions"]
    assert a["1,2"]["predicted_columns"] == []          # both tiles end on land
    assert a["1,1,1"]["predicted_columns"] == [2]       # the sea column alone
    assert a["2,1"]["predicted_columns"] == [1, 2]      # tile 1 ends on sea
    for tiles, r in a.items():
        assert r["prediction_holds"], \
            f"{tiles}: predicted {r['predicted_columns']}, saw {r['columns']}"


def test_the_prediction_can_come_out_WRONG():
    """A prediction that always matches is not a prediction. Feeding a surface
    map the fixture does not have must change the predicted set."""
    all_land = {1: 1.0, 2: 1.0, 3: 1.0}
    assert nl.predicted_columns((2, 1), all_land, 3) == set()
    assert nl.predicted_columns((2, 1), {1: 1.0, 2: 2.0, 3: 1.0}, 3) == {1, 2}
