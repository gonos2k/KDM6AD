"""Departure against arrival, and the count that conflated two different events.

LOCAL ONLY (needs gfortran + the gitignored host reference tree). The numbers
this tool produces were published from a document before any tool existed, so the
binding test is that it reproduces them -- if the interface pairing is wrong, the
published figures do not come back.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_cap_interface as ci  # noqa: E402

REPO = ROOT.parent
BUILD = ROOT / "g33_fortran" / "refine_build.sh"
REF = REPO / "host" / "KIM-meso_v1.0" / "phys" / "module_mp_kdm6.F"

pytestmark = pytest.mark.skipif(
    shutil.which("gfortran") is None or not REF.is_file(),
    reason="local-only (needs gfortran + the gitignored host reference tree)",
)


@pytest.fixture(scope="module")
def stream(tmp_path_factory):
    out = tmp_path_factory.mktemp("cap") / "build"
    b = subprocess.run(["bash", str(BUILD), str(out),
                        "--fixture=g33_fixture_multisubcycle_v1",
                        "--algo=legacy", "--nflux"],
                       capture_output=True, text=True, cwd=REPO)
    assert b.returncode == 0, f"build failed:\n{b.stdout}\n{b.stderr}"
    r = subprocess.run([str(out / "g33_refine_driver"), "12", "rezero"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_the_cap_explains_the_whole_ice_mass_residual(stream):
    """The published figure: 100.00% on both ice columns. A wrong pairing gives
    some other percentage, so this is the test that the tool computes what the
    finding says it computes."""
    rows = ci.analysis(stream)["rows"]
    for col in ("2", "3"):
        assert rows[f"ice/{col}"]["explained"] == pytest.approx(1.0, abs=5e-5)


def test_the_main_chain_created_number_equals_the_measure_prediction(stream):
    """Ratio 1.0000 in all three columns -- the quantitative confirmation of the
    mechanism, on independently emitted per-interface transfers."""
    rows = ci.analysis(stream)["rows"]
    for col in ("1", "2", "3"):
        assert rows[f"main/{col}"]["created_over_predicted"] == \
            pytest.approx(1.0, abs=5e-4)


def test_the_ice_rows_are_cap_dominated_and_are_not_a_measure_measurement(stream):
    """-28.58 / -28.90: sign-flipped because the arrival is far below the
    uncapped value. The ice chain measures the cap, the main chain the measure."""
    rows = ci.analysis(stream)["rows"]
    assert rows["ice/2"]["created_over_predicted"] == pytest.approx(-28.58, abs=0.05)
    assert rows["ice/3"]["created_over_predicted"] == pytest.approx(-28.90, abs=0.05)


def test_the_binding_count_is_reported_PER_CHAIN_with_its_magnitude(stream):
    """The published claim was "39 of 255 interfaces, ALL in the ice chain". The
    ice count is exactly right; "all" was not. The main chain's departure and
    arrival differ at 23 interfaces too -- for a total interface term eight
    orders of magnitude smaller, which is WHY its residual stays at 1e-10.

    A bare count made those two the same event. The tool now reports the count
    beside the magnitude so they cannot be confused again."""
    a = ci.analysis(stream)
    assert a["total_interfaces"] == 255
    assert a["by_chain"]["ice"]["mass_departure_arrival_differ"] == 39
    assert a["by_chain"]["main"]["mass_departure_arrival_differ"] > 0, \
        "'all of them in the ice chain' would make this zero"
    assert a["by_chain"]["main"]["sum_abs_interface_term"] < \
        1e-6 * a["by_chain"]["ice"]["sum_abs_interface_term"]


def test_the_topmost_interface_is_included(stream):
    """The top cell is updated outside the interior loop, so CAPIN cannot see its
    departure; without TOPOUT the topmost interface is invisible and the residual
    would not close to 100%."""
    a = ci.analysis(stream)
    # K = 4 gives 3 interfaces per (column, chain, sub-step); dropping the top one
    # would give 2, so the count itself detects the omission.
    assert a["total_interfaces"] == 255


# ---- owner §2: "bit-for-bit" must be a raw-bit comparison, and it is SCOPED ---

@pytest.fixture(scope="module")
def variants(tmp_path_factory):
    """Both algorithms, same fixture, --nflux. Raw text, not parsed floats: the
    claim is about the stored patterns, so a float round-trip would be the wrong
    instrument."""
    out = {}
    for algo in ("legacy", "conservative"):
        d = tmp_path_factory.mktemp(algo) / "build"
        b = subprocess.run(["bash", str(BUILD), str(d),
                            "--fixture=g33_fixture_multisubcycle_v1",
                            f"--algo={algo}", "--nflux"],
                           capture_output=True, text=True, cwd=REPO)
        assert b.returncode == 0, f"{algo} build failed:\n{b.stdout}\n{b.stderr}"
        r = subprocess.run([str(d / "g33_refine_driver"), "12", "rezero", "3"],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        out[algo] = r.stdout
    return out


def _state(stream, field):
    return {(t[4], t[7], t[8]): t[10]
            for t in (l.split() for l in stream.splitlines())
            if len(t) > 10 and t[1] == "STAGE" and t[6] == field}


def _xfer(stream, idx):
    return {tuple(t[2:6]): t[7 + idx]
            for t in (l.split() for l in stream.splitlines())
            if len(t) > 8 and t[1] == "XFER"}


def test_the_MAIN_chain_is_raw_bit_identical_across_the_two_variants(variants):
    """The claim originally rested on two normalised residuals being equal, which
    is not a raw-bit comparison (owner §2). It is one now -- and it holds, which
    is WHY main/nr matches to the last digit rather than that being luck."""
    L, C = variants["legacy"], variants["conservative"]
    for field in ("nr", "qr"):
        a, b = _state(L, field), _state(C, field)
        assert a and a == b, f"main-chain {field} is not raw-bit identical"
    for idx in (0, 1):                      # dq then dn
        a, b = _xfer(L, idx), _xfer(C, idx)
        main = {k: v for k, v in a.items() if k[3] == "main"}
        assert main and all(b[k] == v for k, v in main.items())


def test_the_ICE_chain_is_NOT_identical_and_must_not_be(variants):
    """The conservative variant exists to fix the ice cap. If ice matched
    bit-for-bit the variant would not be doing anything, so this asserts the
    scope of the claim above rather than merely tolerating a difference."""
    L, C = variants["legacy"], variants["conservative"]
    for field in ("ni", "qi"):
        assert _state(L, field) != _state(C, field), \
            f"ice {field} is identical — the cap fix did nothing"
    ice = {k: v for k, v in _xfer(L, 1).items() if k[3] == "ice"}
    assert any(_xfer(C, 1)[k] != v for k, v in ice.items())


def test_the_MASS_and_NUMBER_caps_are_counted_separately(stream):
    """`cap_bound` compared only `dq`, so a figure quoted as "cap-bound
    interfaces" silently meant the MASS cap. They are not the same set, and the
    difference is the point (owner §10):

        ice   mass 39 / number 39 of 108
        main  mass 23 / number  0 of 147

    On the main chain the NUMBER departure and arrival never differ, which is
    exactly why its number result is a clean measure-mismatch measurement rather
    than a cap measurement. A single count could not say that."""
    a = ci.analysis(stream)
    ice, main = a["by_chain"]["ice"], a["by_chain"]["main"]
    assert ice["number_departure_arrival_differ"] == 39
    assert main["number_departure_arrival_differ"] == 0, \
        "the main chain's number cap must not bind — that is why its result is clean"
    assert main["mass_departure_arrival_differ"] > 0
    assert a["either_differ"] >= a["mass_departure_arrival_differ"]


def test_the_interface_term_is_reported_NET_and_GROSS(stream):
    """abs(net-per-column) understates activity when positive and negative
    interface terms cancel inside a column. On the main chain gross is ~3x net,
    so the single figure was hiding real cancellation; on ice the two agree,
    which says every term there has the same sign (owner P1-11.2)."""
    c = ci.analysis(stream)["by_chain"]
    for ch in ("main", "ice"):
        assert c[ch]["sum_abs_interface_term"] >= abs(c[ch]["net_interface_term"])
        assert c[ch]["max_abs_interface_term"] <= c[ch]["sum_abs_interface_term"]
    assert c["main"]["sum_abs_interface_term"] > \
        2 * abs(c["main"]["net_interface_term"]), "main should show cancellation"
    assert c["ice"]["sum_abs_interface_term"] == \
        pytest.approx(abs(c["ice"]["net_interface_term"]), rel=1e-9), \
        "ice terms are single-signed"


def test_the_throughput_follows_the_BASIS_it_is_divided_into(stream):
    """`physical` mode computed R(rho_d) but divided by throughput(rho_m) — a
    mixed-basis ratio (owner P1-11.1)."""
    import g33_defect_magnitude as dm
    op = ci.interfaces(stream, "operator")
    ph = ci.interfaces(stream, "physical")
    key = next(iter(op))
    assert ph[key]["number_transported"] < op[key]["number_transported"], \
        "rho_d < rho_m, so the dry throughput must be smaller"
    # and the magnitude analysis threads it
    src = (ROOT / "g33_defect_magnitude.py").read_text()
    assert "ci.interfaces(stream, basis)" in src


# ---- owner §16-3: the window endpoint, on a real stream ---------------------

def test_the_window_endpoints_parse_from_a_REAL_stream_and_bound_the_headline(
        variants):
    """`G33-MAGNITUDE-002` quotes R as a fraction of N(t_0). The denominator used
    to be the first sedimentation call's PRE-SED column, published as if it were
    the window's initial inventory -- other microphysics runs before that call,
    so the two are not the same quantity in general (owner §16-3).

    The window endpoints are read from this stream's own G33R INITIAL/STATE. On
    this fixture they coincide with the segment endpoints, which is a
    MEASUREMENT reported here, not a property of the kernel: a fixture with
    pre-sedimentation sources would separate them, and the analysis would then
    report `False` and the two denominators would differ.
    """
    import g33_defect_magnitude as dm

    rows = dm.analysis(variants["legacy"])["rows"]
    checked = 0
    for key, r in rows.items():
        if not r.get("usable"):
            continue
        assert r["window_initial_inventory"] is not None, \
            f"{key}: G33R INITIAL did not parse out of a real driver stream"
        assert r["segment_endpoints_are_window_endpoints"] is True, key
        # Hence, and only hence, the two denominators agree here.
        assert r["of_initial_inventory"] == pytest.approx(
            r["of_first_segment_pre"], rel=1e-6)
        checked += 1
    assert checked >= 3, f"only {checked} usable rows -- the fixture changed"


# ---- owner §16-4: the internal cap sink, measured rather than inferred ------

def test_the_phase_comes_from_the_ANCHORED_ARRAY_not_a_diagnostic(stream):
    """`main`'s CAPIN site is anchored on `qrs(i,k,1) = ... dqr ...` (F:1225),
    which is rain; `ice`'s on `qci(i,k,2) = ... dqi ...` (F:1289), cloud ice. So
    the phase of a destroyed parcel is known from where the record was emitted,
    not guessed from the surface fallout fraction."""
    assert ci.CHAIN_PHASE == {"main": "liquid", "ice": "ice"}
    phases = {s.phase for lst in ci.cap_sink(stream).values() for s in lst}
    assert phases <= {"liquid", "ice"}


def test_the_INFERRED_internal_destruction_is_NEGATIVE_which_a_cap_cannot_be(
        stream):
    """Why the direct measurement was needed. `outflow_split` computes
    `D_internal = water_out - P_bottom` from the fallout DIAGNOSTIC. A cap only
    destroys, so a negative D_internal is not a sink -- it is the diagnostic's
    own departure from the budget. On this fixture it is negative in every
    column, while the interface measurement is positive where the cap bites."""
    import g33_refine_analyze as ra

    run = ra.read_text(stream)
    sink = ci.cap_sink(stream)
    cells = {(k[2], k[3]) for k in run if k[0] == "state"}
    inferred_negative = measured_positive = 0
    for c in sorted({x for x, _ in cells}):
        ks = sorted(k for cc, k in cells if cc == c)
        if ra.outflow_split(run, c, ks)["D_internal"] < 0:
            inferred_negative += 1
        if sum(s.destroyed for s in sink.get(c, [])) > 1e-9:
            measured_positive += 1
    assert inferred_negative == 3, "all three columns infer a negative sink"
    assert measured_positive == 2, "two columns measure a real one"


def test_the_sink_is_a_LOWER_BOUND_and_the_shortfall_is_not_hypothetical(stream):
    """Only dqr (F:1225) and dqi (F:1289) carry a CAPIN anchor; dqs (F:1237) and
    dqg (F:1243) do not. If this fixture had no snow or graupel the gap would be
    academic -- it has both, so the measured sink is genuinely incomplete and
    must not be reported as the column's total internal destruction."""
    import g33_refine_analyze as ra

    run = ra.read_text(stream)
    cells = {(k[2], k[3]) for k in run if k[0] == "state"}
    present = set()
    for c in sorted({x for x, _ in cells}):
        ks = sorted(k for cc, k in cells if cc == c)
        for f in ci.UNINSTRUMENTED_SPECIES:
            if any(run[("initial", f, c, k)] or run[("state", f, c, k)]
                   for k in ks):
                present.add(f)
    assert present == set(ci.UNINSTRUMENTED_SPECIES), \
        "the caveat is vacuous unless the uninstrumented species are here"


def test_charging_the_sink_where_it_died_MOVES_the_enthalpy_residual(stream):
    """The point of §16-4. 48-58% of what the ledger called `H_precip_out` in
    columns 2 and 3 never precipitated. Recharging it at its own level and phase
    is worth 20.7% of column 2's residual and -5.2% of column 3's -- so it is a
    real term, and it does NOT close the residual (it makes column 2 worse)."""
    import g33_refine_analyze as ra

    a = ci.enthalpy_with_cap_sink(stream)
    before, after = a["all_charged_at_surface"], a["with_internal_cap_sink"]
    assert after[1]["residual"] == pytest.approx(before[1]["residual"], rel=1e-6)
    for c, lo, hi in ((2, 0.45, 0.60), (3, 0.40, 0.55)):
        assert lo < after[c]["cap_sink_share_of_column_loss"] < hi
        assert after[c]["residual"] != before[c]["residual"]
        assert after[c]["cap_sink_is_lower_bound"] is True
    # Direction, stated rather than left for a reader to assume favourable:
    assert abs(after[2]["residual"]) > abs(before[2]["residual"])
    assert abs(after[3]["residual"]) < abs(before[3]["residual"])


def test_BOTH_ledgers_reach_the_bundle_not_just_the_corrected_one(stream):
    """A correction nothing publishes is not a correction. It is registered as a
    bundle analysis -- and it carries the previous all-at-the-surface ledger
    beside it, so a reader can see what moved instead of finding every
    previously-quoted residual silently replaced."""
    import g33_refine_experiment as xp

    assert "internal_cap_enthalpy" in xp.ANALYSES
    a = xp.ANALYSES["internal_cap_enthalpy"][1](stream)
    assert set(a) >= {"with_internal_cap_sink", "all_charged_at_surface",
                      "instrumented_species", "uninstrumented_species"}
    assert a["uninstrumented_species"] == ["qs", "qg"]
    for c in (2, 3):
        assert a["with_internal_cap_sink"][c]["residual"] != \
            a["all_charged_at_surface"][c]["residual"]


# ---- owner §16-4 P0-1 / P1-1: event-time temperature, and signed vs gross ----

def test_the_sink_carries_THIS_CALLS_temperature_not_the_windows(stream):
    """The window-initial temperature is a different quantity: on column 3 it is
    1.77 K away by call 12, worth ~21 J/m2 against a ~28 J/m2 correction. The
    first version charged at window-initial and the column-3 figure was wrong by
    22% (owner P0-1)."""
    import g33_refine_analyze as ra

    run = ra.read_text(stream)
    off = [abs(s.t_up - ra._t(run, "initial", col, s.k_up))
           for col, rows in ci.cap_sink(stream).items() for s in rows]
    assert max(off) > 0.5, \
        "no sink sits more than 0.5 K from window-initial -- this fixture can " \
        "no longer tell the two temperatures apart, so the test is vacuous"


def test_the_attribution_is_a_BAND_because_annihilation_has_no_location(stream):
    """Mass destroyed between two levels did not die at either one. Charging at
    the departure level is a stated convention, so the arrival-level charge is
    reported beside it rather than the choice being invisible."""
    a = ci.enthalpy_with_cap_sink(stream)["with_internal_cap_sink"]
    for c in (2, 3):
        d = a[c]
        assert d["H_sink_at_departure_temperature"] != \
            d["H_sink_at_arrival_temperature"]
        assert d["H_sink_temperature_band"] == pytest.approx(
            abs(d["H_sink_at_departure_temperature"]
                - d["H_sink_at_arrival_temperature"]))
        # Big enough to matter: the band is a fifth to a quarter of the term.
        assert d["H_sink_temperature_band"] > 0.1 * abs(
            d["H_internal_cap_correction"])


def test_a_SIGNED_defect_is_not_a_SINK(stream):
    """`-mass_term` goes negative where an interface creates, so reporting it as
    "destroyed mass" produced column 1's impossible -1.7e-11 kg/m2 sink. It was
    in fact 1.7e-11 destroyed against 3.4e-11 created -- roundoff both ways,
    cancelling. Energy accounting takes the signed sum; the physical sentence
    takes the gross (owner P1-1)."""
    rows = ci.cap_sink(stream)[1]
    assert sum(s.signed for s in rows) < 0, "column 1's NET defect is negative"
    assert sum(s.destroyed for s in rows) > 0
    assert sum(s.created for s in rows) > 0, \
        "if nothing is created the net could not have gone negative"
    a = ci.enthalpy_with_cap_sink(stream)["with_internal_cap_sink"]
    assert a[1]["cap_sink_share_of_column_loss"] >= 0.0, \
        "a share of column loss computed from a signed defect can go negative"


def test_the_headline_share_is_unchanged_by_the_signed_gross_split(stream):
    """Columns 2 and 3 are effectively single-signed -- created is 6.8e-9 and
    5.4e-10 of destroyed -- so 57.81/48.02% stands. The API distinction is still
    required; it just does not move these two."""
    a = ci.enthalpy_with_cap_sink(stream)["with_internal_cap_sink"]
    for c, want in ((2, 0.5781), (3, 0.4802)):
        d = a[c]
        assert d["cap_sink_share_of_column_loss"] == pytest.approx(want, abs=5e-4)
        assert d["gross_created_mass"] / d["gross_destroyed_mass"] < 1e-7


# ---- owner P1-2 / P1-3: basis-consistent endpoints, fail-closed parsing ------

def test_the_window_inventory_follows_the_BASIS_it_is_asked_for(stream):
    """It used raw rho_m*dz whatever basis the caller worked in, so `physical`
    divided a DRY-air residual by a MOIST-air inventory -- the same mixed-basis
    defect g33_defect_magnitude warns about two lines above the call that had
    it, reintroduced (owner P1-2)."""
    import g33_matched_closure as mc

    op = mc.window_inventories(stream, "operator")
    ph = mc.window_inventories(stream, "physical")
    assert set(op) == set(ph) and op
    for k in op:
        if op[k][0]:
            assert ph[k][0] < op[k][0], \
                "dry-air mass is rho_m/(1+qv), so it must be strictly smaller"


def test_the_dry_air_layer_mass_is_HELD_over_the_window(stream):
    """Dry air does not leave the column during microphysics, so weighting each
    endpoint by its OWN qv would make a conserved quantity move. Both endpoints
    take the window-initial qv -- checked by giving the two endpoints different
    humidity and requiring the weight not to follow."""
    import g33_matched_closure as mc
    import g33_refine_analyze as ra

    real = mc.window_inventories(stream, "physical")
    run = ra.read_text(stream)
    patched = dict(run)
    for key in [k for k in run if k[0] == "state" and k[1] == "qv"]:
        patched[key] = run[key] * 2.0
    orig, ra.read_text = ra.read_text, lambda *a, **k: patched
    try:
        assert mc.window_inventories(stream, "physical") == real, \
            "the layer mass followed the FINAL qv, so dry mass is not held"
    finally:
        ra.read_text = orig


def test_a_stream_with_no_G33R_is_unavailable(stream):
    """Older G33N-only members legitimately have no endpoints."""
    import g33_matched_closure as mc

    assert mc.window_inventories(
        "\n".join(l for l in stream.splitlines()
                   if not l.startswith("G33R"))) == {}


def test_a_CORRUPT_G33R_raises_instead_of_reporting_no_endpoints(stream):
    """`except Exception: window = {}` could not tell "this member has no
    endpoints" from "this member is truncated, duplicated or NaN". The second is
    evidence corruption and reporting it as the first is the flattering
    direction (owner P1-3)."""
    import g33_matched_closure as mc
    import g33_refine_analyze as ra

    with pytest.raises(ra.RefineError):
        mc.window_inventories(stream.replace("G33R END", "", 1))
