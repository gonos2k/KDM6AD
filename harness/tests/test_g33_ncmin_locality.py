"""How much the scalar `ncmin` costs, not how many cells it touches.

LOCAL ONLY (needs gfortran + the gitignored host reference tree).
"""
import contextlib
import io
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
    assert "ra.read_text(text, nsplit=nsplit, label=label)" in src


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
    """Integrated over the column, the defensible headline is RAIN mass at
    21-26%, not cloud ice at 100%. Reported under BOTH bases, because the first
    version called the operator integral "the only physical form" -- and the
    mixing ratios are per DRY-air kg (owner §7.1)."""
    both = nl.analysis(drivers["legacy"], FIXTURE)["partitions"]["2,1"][
        "column_integrated"]
    assert set(both) == {"operator", "physical"}
    for basis, ci in both.items():
        assert 0.20 < ci["1/qr"]["rel"] < 0.22, basis
        assert 0.25 < ci["2/qr"]["rel"] < 0.27, basis
        for c in (1, 2):
            assert 0.02 < ci[f"{c}/total_condensate"]["rel"] < 0.04, basis


def test_the_two_bases_agree_on_ratio_and_differ_on_mass(drivers):
    """Necessarily so: both runs share the window-initial qv, so the 1+qv weight
    cancels in the ratio, while the absolute masses differ by that factor. This
    is what turns "the headline does not depend on the basis" from a hope into a
    measurement."""
    both = nl.analysis(drivers["legacy"], FIXTURE)["partitions"]["2,1"][
        "column_integrated"]
    for row in ("1/qr", "2/qr", "1/total_condensate"):
        o, p = both["operator"][row], both["physical"][row]
        assert o["rel"] == pytest.approx(p["rel"], rel=1e-9), row
        assert p["abs"] < o["abs"], f"{row}: rho_d < rho_m, so the mass is smaller"
        assert 1.0 < o["abs"] / p["abs"] < 1.01, row


def test_the_prediction_requires_the_GATE_TO_BE_ACTIVE(drivers):
    """"A differing tile-end surface type makes every column in that tile
    differ" holds only where the two candidate thresholds can behave
    differently. `ncmin` is a gate AND a floor (`max(ncmin, nci)`,
    F:2736/2750/2888), and they agree where the number exceeds BOTH."""
    import g33_refine_analyze as ra_

    land, sea = nl.fixture_ncmin(FIXTURE)
    assert (land, sea) == (1.0e8, 2.5e7)
    run = ra_.read_text(nl.run(drivers["legacy"], (3,)), nsplit=1)
    # nc runs 4.0e7..5.04e7, between the thresholds, so the gate is active
    # everywhere -- which is WHY the prediction is exact on this fixture.
    assert all(nl.threshold_can_matter(run, c, (land, sea)) for c in (1, 2, 3))
    # And a column whose numbers exceeded both would be excluded.
    assert not nl.threshold_can_matter(run, 1, (1.0, 1.0))


def test_causal_attribution_is_a_SEPARATE_verdict(drivers):
    """A partition whose observed columns miss the prediction used to be
    recorded as an ordinary row (owner §7.3)."""
    for r in nl.analysis(drivers["legacy"], FIXTURE)["partitions"].values():
        assert r["measurement_valid"] is True
        assert r["causal_attribution_valid"] is True


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


# ---- owner §12-5: the direct-sum oracle, without touching the kernel --------

def test_the_PER_COLUMN_run_IS_the_direct_sum_oracle(drivers):
    """Running each column as its own tile makes `ncmin` that column's own
    threshold, so `(1,)*B` is `M_local(X) = (+)_i M_i(X_i; xland_i)` -- the
    answer a corrected operator would have to reproduce. It needs no change to
    the kernel: the oracle is a DECOMPOSITION, not a variant."""
    o = nl.local_oracle(drivers["legacy"], FIXTURE)
    assert o["oracle"] == "1,1,1"
    assert o["partitions"]["1,1,1"]["is_the_oracle"] is True
    assert o["partitions"]["1,1,1"]["components_differing"] == 0


def test_the_WHOLE_DOMAIN_run_departs_from_the_local_answer(drivers):
    """The number that matters operationally: production runs whole tiles, not
    one column each. Measuring partitions against EACH OTHER only says they
    disagree; measuring them against the local answer says how far the shipped
    configuration is from column-locality."""
    p = nl.local_oracle(drivers["legacy"], FIXTURE)["partitions"]
    whole = p["3"]
    assert whole["components_differing"] == 16
    assert whole["columns"] == [2], "the sea column is the one gated wrongly"
    for basis in ("operator", "physical"):
        d = whole["column_integrated"][basis]["2/qr"]
        assert 0.20 < d["rel"] < 0.22, f"{basis}: {d['rel']}"
        # DIRECTION, not just size (owner §9.4). A test on |rel| passes just as
        # well if a future change flips the sign, and the published sentence WAS
        # backwards: gating the sea column on ncmin_land raises the droplet
        # floor, suppresses autoconversion, and rains LESS.
        assert d["signed_rel"] < 0, (
            f"{basis}: the whole-domain run must rain LESS than the per-column "
            f"answer, not more")


def test_the_two_directions_are_OPPOSITE_and_both_asserted(drivers):
    """`(3,)` puts the sea column on the land threshold and rains less; `(2,1)`
    puts the land column on the sea threshold and rains more. A single |rel|
    assertion cannot tell those apart."""
    p = nl.local_oracle(drivers["legacy"], FIXTURE)["partitions"]
    assert p["3"]["column_integrated"]["operator"]["2/qr"]["signed_rel"] < 0
    assert p["2,1"]["column_integrated"]["operator"]["1/qr"]["signed_rel"] > 0


def test_the_bases_agree_because_the_humidity_weight_is_UNIFORM(drivers):
    """Not by an identity: `a_k = 1/(1+qv(t0))` sits INSIDE the column sum, so a
    common factor cancels and a level-dependent one does not (owner §9.2). On
    this fixture the vertical spread is exactly zero, which is why the two bases
    agree -- a property of the fixture, measured."""
    spread = nl.humidity_weight_spread(nl.run(drivers["legacy"], (3,)))
    assert set(spread) == {1, 2, 3}
    assert all(v == 0.0 for v in spread.values()), spread


def test_WHICH_column_is_wrong_depends_on_the_decomposition(drivers):
    """`(2,1)` ends its first tile on sea, so column 1 takes the sea threshold;
    `(3,)` and `(1,2)` end on land, so column 2 takes the land one. Every
    decomposition except per-column is wrong SOMEWHERE."""
    p = nl.local_oracle(drivers["legacy"], FIXTURE)["partitions"]
    assert p["3"]["columns"] == [2]
    assert p["1,2"]["columns"] == [2]
    assert p["2,1"]["columns"] == [1]
    assert all(r["components_differing"] > 0
               for k, r in p.items() if not r["is_the_oracle"])


def test_the_operator_is_otherwise_COLUMN_LOCAL(drivers):
    """What licenses attributing the departure to `ncmin` alone: `(1,2)` differs
    from the whole domain in ZERO components even though the decomposition
    changed, so nothing but the `ncmin` gate responds to tiling here."""
    a = nl.analysis(drivers["legacy"], FIXTURE)["partitions"]
    assert a["1,2"]["components_differing"] == 0


def test_the_REPORT_carries_the_direction_and_the_caveats(drivers, capsys):
    """A correction that lives only in a finding is not in the artifact. The
    report printed an unsigned `20.72%`, so anyone running the tool saw a
    magnitude with no direction -- which is how the published sentence came to
    say "too much" when the run makes LESS (owner §9.4). The two withdrawn
    framings must appear where the numbers do."""
    nl.report(drivers["legacy"], FIXTURE)
    out = capsys.readouterr().out
    assert "-20.72%" in out, "the whole-domain departure must print its SIGN"
    assert "+20.67%" in out, "and the opposite-signed one must too"
    assert "does NOT stand for a production run" in out
    assert "property of the fixture, not a law" in out
    assert "0.000e+00" in out, "the humidity-weight spread that explains it"


def test_BOTH_SIGNS_get_their_OWN_mechanism_not_one_global_sentence(drivers,
                                                                    capsys):
    """The report derived the mechanism correctly and then printed it ONCE, from
    the WHOLE-DOMAIN gating, under a table carrying both signs. A reader applying
    it to the `+20.67%` row got the physics backwards, because there the affected
    column is gated at the LOWER threshold, not the higher one (Codex). Deriving
    the sentence is not enough if it is attached to the wrong row."""
    nl.report(drivers["legacy"], FIXTURE)
    out = capsys.readouterr().out
    assert "col 2: gated at 1e+08, not its own 2.5e+07" in out
    assert "HIGHER droplet floor" in out and "LESS rain" in out
    assert "col 1: gated at 2.5e+07, not its own 1e+08" in out
    assert "LOWER droplet floor" in out and "MORE rain" in out


def test_the_MECHANISM_is_derived_from_the_thresholds_not_hardcoded(monkeypatch):
    """It read "a tile ending on land gates a sea column at the HIGHER floor,
    which suppresses autoconversion" -- true only while ncmin_land > ncmin_sea.
    On a fixture with the reverse ordering the report printed the physics
    backwards: the same class of error as the sign this session corrected, one
    level up (Codex)."""
    monkeypatch.setattr(nl, "fixture_ncmin", lambda f: (1.0e8, 2.5e7))
    assert "HIGHER" in nl.mechanism_for((3,), FIXTURE, 2)

    monkeypatch.setattr(nl, "fixture_ncmin", lambda f: (2.5e7, 1.0e8))
    lo = nl.mechanism_for((3,), FIXTURE, 2)
    assert "LOWER" in lo and "freer" in lo and "MORE rain" in lo


def test_a_stream_with_no_INITIAL_qv_is_REFUSED_not_silently_accepted(drivers):
    """Two defects met here. The report had a "NOT MEASURABLE" branch for a
    stream carrying no INITIAL qv -- unreachable, because the physical column
    integral above it died on a raw KeyError first (Codex). And the
    same-atmosphere contract compared two EMPTY sets of initial records and
    passed, so the guarantee evaporated exactly where it could not be checked.
    Both now refuse, by name."""
    text = "\n".join(l for l in nl.run(drivers["legacy"], (3,)).splitlines()
                      if not l.startswith("G33R INITIAL")) + "\n"
    records = nl.read_records(text, label="a")

    with pytest.raises(ra.RefineError, match="vacuous"):
        nl._expect_same_inputs(records, records, "x")

    with pytest.raises(ra.RefineError, match="WINDOW-INITIAL qv"):
        nl.column_integrated(text, text, "physical")


def test_the_operator_basis_still_works_without_INITIAL_qv(drivers):
    """The refusal is scoped to the basis that needs it: rho_m*dz does not."""
    text = "\n".join(l for l in nl.run(drivers["legacy"], (3,)).splitlines()
                      if not l.startswith("G33R INITIAL")) + "\n"
    # Same stream twice: the operator basis completes and finds no difference,
    # where the physical basis refuses for want of qv.
    assert nl.column_integrated(text, text, "operator") == {}


@pytest.mark.parametrize("arm", ["legacy", "conservative"])
def test_basis_AGREEMENT_is_MEASURED_not_asserted(drivers, arm):
    """The report printed the operator basis and then claimed the physical basis
    gives the same relative figures -- an unverified claim standing next to the
    numbers that would settle it (Codex). `local_oracle` computes BOTH, so the
    comparison costs nothing. Measuring it immediately showed the claim was true
    for a subtler reason than stated: the gap floors at summation roundoff, not
    zero, because a_k cancels algebraically while the two sums reorder.

    BOTH ARMS. The first version tested only legacy, so a tolerance fitted to
    legacy's 0.89 eps shipped while conservative sat at 1.03 eps and was
    misclassified (Codex)."""
    o = nl.local_oracle(drivers[arm], FIXTURE)
    gap = nl.basis_gap(o)
    scale = max(v["rel"] for r in o["partitions"].values()
                for v in r["column_integrated"]["operator"].values())
    assert gap > 0.0, ("exactly 0.0 would mean the two bases are not really "
                       "being computed differently")
    assert -__import__("math").log10(gap / scale) >= nl.SANITY_DIGITS


@pytest.mark.parametrize("arm", ["legacy", "conservative"])
def test_the_VERDICT_rests_on_an_EXACT_property_not_a_TOLERANCE(drivers, arm):
    """Three versions of this check tried to CLASSIFY with a threshold. First a
    bare f64 eps, fitted to legacy's one measurement, which then misclassified
    the conservative arm. Then `levels * eps`, which sounds derived but is not a
    valid bound for this quantity: `rel = |y-x|/|x|` contains a SUBTRACTION, and
    the k*eps summation bound is against sum|x_i| -- it says nothing about
    cancellation in y-x (Codex).

    The question has an EXACT answer, so no tolerance is needed at all: a_k is
    vertically constant or it is not. Both arms give exactly 0.0, which is why
    no threshold could sit safely between them."""
    base = nl.run(drivers[arm], (nl.fixture_dims(FIXTURE)[0],))
    assert nl.weight_is_uniform(base) is True
    assert set(nl.humidity_weight_spread(base).values()) == {0.0}, \
        "exactly zero, not merely small -- the verdict rests on this"
    assert not hasattr(nl, "basis_tolerance"), \
        "the invalid error bound must not come back"


def test_a_NON_UNIFORM_weight_is_reported_as_a_REAL_disagreement(drivers,
                                                                 monkeypatch,
                                                                 capsys):
    """The branch that says the figures are basis-specific must be reachable,
    and it must not be the roundoff residual that decides it."""
    monkeypatch.setattr(nl, "humidity_weight_spread",
                        lambda text: {1: 0.0, 2: 4.2e-3, 3: 0.0})
    nl.report(drivers["legacy"], FIXTURE)
    out = capsys.readouterr().out
    assert "It is NOT uniform" in out
    assert "must not be quoted without" in out


def test_a_departure_present_in_ONE_basis_only_counts_as_DISAGREEMENT():
    """It was recorded on one measure and not the other, which is precisely a
    disagreement -- skipping the unmatched key would hide it."""
    lopsided = {"partitions": {"3": {"column_integrated": {
        "operator": {"2/qr": {"rel": 0.2072}}, "physical": {}}}}}
    assert nl.basis_gap(lopsided) == 0.2072


@pytest.mark.parametrize("arm", ["legacy", "conservative"])
def test_the_RESIDUAL_is_labelled_an_OBSERVATION_not_a_BOUND(drivers, capsys,
                                                             arm):
    """Every earlier version of this section made a claim it could not support:
    that the bases agree (never compared), then that a fitted eps bounded the
    gap, then that `levels * eps` did. What the report may honestly say is the
    exact precondition plus the observed residual.

    Both arms, because testing only legacy is what shipped the fitted bound."""
    nl.report(drivers[arm], FIXTURE)
    out = capsys.readouterr().out
    assert "EXACTLY uniform in every column" in out
    assert "significant digits" in out
    assert "No\n  error bound is claimed" in out, (
        "the residual must be labelled an OBSERVATION -- two earlier versions "
        "presented a fabricated tolerance as a derived bound")
    assert "It is NOT uniform" not in out


def test_the_MECHANISM_REFUSES_to_contradict_the_measurement(monkeypatch):
    """`mechanism_for` is called only for columns the run measured as MOVING. If
    the thresholds say the column is gated at its own value, `ncmin` does not
    explain it, and printing "unaffected" would put the derived explanation in
    direct contradiction with the table above it. Refuse instead."""
    monkeypatch.setattr(nl, "fixture_ncmin", lambda f: (1.0e8, 1.0e8))
    with pytest.raises(ra.RefineError, match="does not explain this column"):
        nl.mechanism_for((3,), FIXTURE, 2)


def test_an_UNKNOWN_surface_type_has_no_known_threshold(monkeypatch):
    """`by_type[xland[...]]` would have raised a bare KeyError."""
    monkeypatch.setattr(nl, "fixture_xland", lambda f: {1: 1.0, 2: 3.0, 3: 1.0})
    with pytest.raises(ra.RefineError, match="only land=1.0 / sea=2.0"):
        nl.imposed_threshold((3,), FIXTURE, 2)


def test_the_SANITY_GUARD_fires_and_before_the_reassurance(drivers,
                                                            monkeypatch):
    """The guard decides nothing about the verdict, but it must not be
    decorative: a_k exactly uniform means the two bases are ALGEBRAICALLY EQUAL,
    so a residual far above roundoff means the integrals are not computing the
    same quantity. And it is checked BEFORE the paragraph telling the reader the
    bases agree by construction -- printing that and then raising would leave
    the reassurance in the log above the failure."""
    monkeypatch.setattr(nl, "basis_gap", lambda o: 1.0e-3)
    buf = io.StringIO()
    with pytest.raises(ra.RefineError, match="not computing the same quantity"):
        with contextlib.redirect_stdout(buf):
            nl.report(drivers["legacy"], FIXTURE)
    assert "agree by construction" not in buf.getvalue()


def _oracle(operator, physical):
    return {"partitions": {"3": {"column_integrated": {
        "operator": operator, "physical": physical}}}}


@pytest.mark.parametrize("operator,physical", [
    ({}, {"2/qr": {"rel": 0.2072}}),
    ({"2/qr": {"rel": 0.2072}}, {}),
])
def test_a_ONE_SIDED_departure_cannot_certify_as_INFINITE_agreement(operator,
                                                                     physical):
    """The worst disagreement available -- one basis records a 20.7% departure
    and the other records none -- certified as perfect agreement. `scale` was
    taken from the OPERATOR basis alone, so it was 0.0 in exactly the case where
    the operator saw nothing, and the division was then skipped for `inf`
    (Codex). The guard has to fire hardest precisely here."""
    o = _oracle(operator, physical)
    gap = nl.basis_gap(o)
    assert gap == 0.2072
    assert nl.agreement_digits(o, gap) == 0.0 < nl.SANITY_DIGITS


def test_INFINITY_means_EXACTLY_equal_and_nothing_else():
    """`gap and scale` treated a zero SCALE the same as a zero GAP."""
    agreed = _oracle({"2/qr": {"rel": 0.2072}}, {"2/qr": {"rel": 0.2072}})
    assert nl.basis_gap(agreed) == 0.0
    assert nl.agreement_digits(agreed, 0.0) == float("inf")
    assert nl.agreement_digits(_oracle({}, {}), 0.0) == float("inf")


def test_a_RESIDUAL_with_NO_departure_anywhere_is_a_CONTRADICTION():
    """If the bases differ by something while neither recorded any departure,
    the residual and the figures it is measured against disagree about whether
    anything happened. Refuse rather than divide by zero or call it infinite."""
    with pytest.raises(ra.RefineError, match="whether anything happened"):
        nl.agreement_digits(_oracle({}, {}), 1.0e-3)


# ---- the mechanism as a LAW over the decomposition space (owner priority 10) -

@pytest.mark.parametrize("arm", ["legacy", "conservative"])
def test_the_answer_is_a_FUNCTION_of_the_imposed_threshold_vector(drivers, arm):
    """What licenses reading a synthetic result as a statement about real
    decompositions. From the reference source: `ncmin` is a plain local (F:812,
    not SAVE, not module-level) so it cannot outlive one kdm62D call, and the
    loop that sets it (F:876-883) has no body but the assignment, so
    `slmsk(ite)` wins. The answer should therefore depend on the imposed
    threshold vector and nothing else -- byte-identical WITHIN a class,
    different ACROSS."""
    law = nl.class_law(drivers[arm], FIXTURE)
    assert law["within"], "no within-class pair -- the law would be untested"
    assert all(w["identical"] for w in law["within"])
    assert all(x["differing"] > 0 for x in law["across"])
    assert law["holds"] is True


def test_the_CLASSES_are_what_the_thresholds_say_they_are():
    """(1,2) and (3,) both end every tile on land, so they must share a class --
    which is why the `(1,2)` row differs from the whole domain in ZERO
    components, a prediction the measurement already confirmed."""
    cls = nl.equivalence_classes(FIXTURE)
    members = {tuple(sorted(v)) for v in cls.values()}
    assert ((1, 2), (3,)) in members or ((3,), (1, 2)) in members
    assert len(cls) == 3, cls


def test_the_LAW_can_come_out_FALSE(drivers, monkeypatch):
    """A law that cannot be violated is not being tested. Merge two classes that
    genuinely differ and the within-class identity must fail."""
    monkeypatch.setattr(nl, "threshold_vector", lambda tiles, fixture: (1.0,))
    law = nl.class_law(drivers["legacy"], FIXTURE)
    assert len(law["classes"]) == 1
    assert not all(w["identical"] for w in law["within"])
    assert law["holds"] is False


def test_a_FALSIFIED_law_is_REFUSED_not_reported_as_held(drivers, monkeypatch):
    """The report printed "Held on every pair" UNCONDITIONALLY, directly under
    rows reading `byte-identical = False` (Codex). Refused now, and refused
    BEFORE the sentence claiming it held -- a failure must not be preceded by
    its own reassurance."""
    monkeypatch.setattr(nl, "threshold_vector", lambda tiles, fixture: (1.0,))
    buf = io.StringIO()
    with pytest.raises(ra.RefineError, match="FALSIFIED"):
        with contextlib.redirect_stdout(buf):
            nl.report(drivers["legacy"], FIXTURE)
    assert "Held on every pair" not in buf.getvalue()


def test_a_driver_that_IGNORES_the_tile_spec_is_REFUSED(drivers, monkeypatch):
    """The severe one. This law's CONFIRMING outcome is identity, so a driver
    that validated the tile spec and then ran the whole domain would make every
    partition identical -- the strongest possible confirmation, produced by a
    completely broken run. `class_law` read the streams directly and applied
    none of the gates `local_oracle` does (Codex)."""
    whole = nl.run(drivers["legacy"], (3,))
    monkeypatch.setattr(nl, "run", lambda driver, tiles: whole)
    with pytest.raises(ra.RefineError, match="the kernel was called over"):
        nl.class_law(drivers["legacy"], FIXTURE)


def test_the_law_check_APPLIES_THE_SAME_GATES_as_the_oracle():
    """Not a new weaker reader beside the strict one -- the repeated defect in
    this repo, and the reason the check above was possible."""
    src = (ROOT / "g33_ncmin_locality.py").read_text()
    body = src[src.index("def class_law("):src.index("def weight_is_uniform(")]
    for gate in ("_expect_tiles_are_live", "_expect_same_inputs",
                 "_expect_universe"):
        assert gate in body, f"class_law skips {gate}"


def test_the_report_states_the_LIMIT_of_the_evidence(drivers, capsys):
    """Width 3 yields exactly ONE within-class pair. The report must say the
    data is consistent with the law rather than a strong test of it, or a
    reader takes a one-pair confirmation for a proven law."""
    nl.report(drivers["legacy"], FIXTURE)
    out = capsys.readouterr().out
    assert "CONSISTENT with the law rather" in out
    assert "than a strong test of it" in out
    assert "geometry of the decomposition, not more physics" in out


# ---- the CONTROL: no threshold variation must mean no tiling dependence -----

@pytest.fixture(scope="module")
def uniform_driver(tmp_path_factory):
    """`multisubcycle_v1` is all-land AND has ncmin_land == ncmin_sea == 10."""
    d = tmp_path_factory.mktemp("ncmin-uniform") / "build"
    b = subprocess.run(["bash", str(BUILD), str(d),
                        "--fixture=g33_fixture_multisubcycle_v1",
                        "--algo=legacy", "--nflux"],
                       capture_output=True, text=True, cwd=REPO)
    assert b.returncode == 0, f"build failed:\n{b.stdout}\n{b.stderr}"
    return str(d / "g33_refine_driver")


UNIFORM = "g33_fixture_multisubcycle_v1"


def test_the_control_fixture_really_IS_degenerate():
    """Both degeneracies at once, so the control cannot separate them: the
    domain is all-land AND the two thresholds are equal. Stated rather than
    glossed -- it means this fixture shows what happens when the threshold
    VECTOR is constant, not specifically what `xland` does."""
    land, sea = nl.fixture_ncmin(UNIFORM)
    assert land == sea == 10
    assert set(nl.fixture_xland(UNIFORM).values()) == {1.0}
    land_b, sea_b = nl.fixture_ncmin(FIXTURE)
    assert land_b != sea_b, "the boundary fixture must still vary"


def test_a_CONSTANT_threshold_vector_means_NO_tiling_dependence(uniform_driver):
    """SUPPORTING evidence, NOT the attribution.

    The commit that added this claimed it licensed reading the 20.72% as an
    `ncmin` cost rather than a tiling cost. It does not, and the reason is
    measurable: on this fixture ncmin = 10 against nc ~ 1e8, so the gate binds
    in 0 of 12 cells. A null result under an INERT gate is evidence that the
    gate is inert (Codex). A second tiling-dependent mechanism exercised only
    by the boundary fixture's regime would not show here.

    What it does establish is narrower and still worth having: on THIS
    atmosphere, with the threshold vector constant, the operator is
    column-local across every decomposition."""
    law = nl.class_law(uniform_driver, UNIFORM)
    assert len(law["classes"]) == 1, "an all-land domain has one threshold class"
    assert law["within_pairs"] == 3
    assert all(w["identical"] for w in law["within"])
    assert not law["across"], "nothing to compare across -- that is the point"
    assert law["holds"] is True


def test_the_control_would_CATCH_a_second_non_local_mechanism(uniform_driver,
                                                              monkeypatch):
    """If the operator had another tiling-dependent path, the control fails --
    which is what makes it a control and not a formality."""
    real = nl.read_records
    seen = {"n": 0}

    def perturbed(text, *, label):
        got = dict(real(text, label=label))
        seen["n"] += 1
        if seen["n"] == 3:                      # one partition answers differently
            k = next(k for k in sorted(got) if k[0] == "state")
            got[k] = "DEADBEEF"
        return got

    monkeypatch.setattr(nl, "read_records", perturbed)
    law = nl.class_law(uniform_driver, UNIFORM)
    assert not law["holds"]


def test_the_control_fixture_gate_is_INERT_so_it_cannot_carry_attribution(
        uniform_driver, drivers):
    """Measured, because the previous commit asserted the opposite. `ncmin = 10`
    against nc ~ 1e8 means the gate never binds on the control fixture, so its
    null result cannot rule out a second tiling-dependent mechanism (Codex)."""
    inert = nl.gate_activity(nl.run(uniform_driver, (3,)), UNIFORM)
    assert sum(v["binding"] for v in inert.values()) == 0, \
        "if this ever binds, the control gets stronger -- update the claim"

    active = nl.gate_activity(nl.run(drivers["legacy"], (3,)), FIXTURE)
    assert sum(v["binding"] for v in active.values()) > 0, \
        "the boundary fixture must actually exercise the gate"


def test_the_ATTRIBUTION_rests_on_a_SAME_ATMOSPHERE_control(drivers):
    """The control that does carry it, on the atmosphere the figures come from.

    `(1,2)` and `(3,)` share a threshold vector but are genuinely different
    decompositions -- two kernel calls over (1,1) and (2,3) versus one over
    (1,3), verified live. Same atmosphere, gate ACTIVE, decomposition changed,
    output byte-identical in all 144 components. That is what licenses reading
    the departure as an `ncmin` cost rather than a tiling cost."""
    a_t, b_t = nl.run(drivers["legacy"], (1, 2)), nl.run(drivers["legacy"], (3,))
    nl._expect_tiles_are_live(a_t, (1, 2), "a")
    nl._expect_tiles_are_live(b_t, (3,), "b")
    assert nl.tile_brackets(a_t) == [(1, 1), (2, 3)]
    assert nl.tile_brackets(b_t) == [(1, 3)]
    assert nl.threshold_vector((1, 2), FIXTURE) == nl.threshold_vector((3,), FIXTURE)
    assert sum(v["binding"] for v in nl.gate_activity(b_t, FIXTURE).values()) > 0
    assert nl.read_state(a_t, label="a") == nl.read_state(b_t, label="b")


def test_the_report_PRINTS_the_gate_activity(drivers, capsys):
    """So a future reader cannot repeat this error on a fixture where the gate
    is inert."""
    nl.report(drivers["legacy"], FIXTURE)
    out = capsys.readouterr().out
    assert "gate BINDS in 8/12 cells" in out
    assert "under an INERT gate is evidence of the gate being inert" in out


# ---- the attribution control, replicated across trajectories ---------------

@pytest.mark.parametrize("arm", ["legacy", "conservative"])
def test_the_control_HOLDS_on_every_trajectory(drivers, arm):
    """One confirming pair is an anecdote. Replicated over every density
    profile the driver offers, both aux-carry arms and three sub-step counts:
    36 independent trajectories, all on the atmosphere the published figures
    come from, with the gate active."""
    rep = nl.control_replication(drivers[arm], FIXTURE)
    assert rep["trajectories"] == 36
    assert rep["within_identical"] == 36
    assert rep["across_differing"] == 36
    assert rep["holds"] is True


def test_BOTH_directions_are_required(drivers):
    """36 identical results are also what trajectories insensitive to
    EVERYTHING would produce. The across-class direction is what separates a
    strong control from a vacuous one, so it is part of the verdict."""
    rep = nl.control_replication(drivers["legacy"], FIXTURE)
    assert rep["across_pair"] is not None
    assert rep["across_differing"] == rep["trajectories"]


def test_the_control_verdict_can_come_out_FALSE(drivers, monkeypatch):
    """Perturb one trajectory's state and the control must fail."""
    real, seen = nl.read_state, {"n": 0}

    def perturbed(text, *, label, nsplit=1):
        got = dict(real(text, label=label, nsplit=nsplit))
        seen["n"] += 1
        if seen["n"] == 2:
            got[sorted(got)[0]] = "DEADBEEF"
        return got

    monkeypatch.setattr(nl, "read_state", perturbed)
    assert nl.control_replication(drivers["legacy"], FIXTURE)["holds"] is False


def test_a_fixture_with_NO_within_class_pair_is_REFUSED(drivers, monkeypatch):
    """The control cannot be formed there, and reporting one anyway would be a
    verdict with nothing behind it."""
    monkeypatch.setattr(nl, "threshold_vector",
                        lambda tiles, fixture: tuple(tiles))
    with pytest.raises(ra.RefineError, match="cannot be formed"):
        nl.control_replication(drivers["legacy"], FIXTURE)


def test_the_report_states_the_REPLICATION(drivers, capsys):
    nl.report(drivers["legacy"], FIXTURE)
    out = capsys.readouterr().out
    assert "replicated over 36 trajectories" in out
    assert "agree bit-for-bit in 36/36" in out
    assert "not just trajectories insensitive to everything" in out


def test_a_ONE_CLASS_fixture_cannot_form_a_TWO_DIRECTIONAL_control(
        uniform_driver):
    """`holds` was True with ZERO across-class checks, and the report printed
    "The across-class pair differs in 0/36 -- both directions" (Codex).
    Self-contradictory on its face, and the same shape as the vacuous
    same-atmosphere contract: a guarantee evaporating exactly where it could
    not be checked.

    An all-land fixture has one threshold class, so there IS no across-class
    pair. That is a control that cannot be formed, not a control that passed."""
    with pytest.raises(ra.RefineError, match="only one\n *direction|one "
                                             "direction"):
        nl.control_replication(uniform_driver, UNIFORM)


def test_NEITHER_half_of_the_verdict_can_be_excused(drivers, monkeypatch):
    """Both counts must reach the full trajectory set. Neither may be waived
    for being unavailable -- unavailable is what made the first version pass."""
    rep = nl.control_replication(drivers["legacy"], FIXTURE)
    assert rep["within_identical"] == rep["trajectories"]
    assert rep["across_differing"] == rep["trajectories"]
    src = (ROOT / "g33_ncmin_locality.py").read_text()
    body = src[src.index("def control_replication("):src.index("def tile_brackets(")]
    assert "across is None" not in body, \
        "a missing across-class pair must be refused, never treated as satisfied"
