"""The departure from -1 and +2, decomposed rather than attributed (owner §7).

LOCAL ONLY (needs gfortran + the gitignored host reference tree): the split needs
four real driver runs, because the metric counterfactual pairs each arm's density
gap with the BASELINE run's transfers.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_metric_trajectory as mt  # noqa: E402

REPO = ROOT.parent
BUILD = ROOT / "g33_fortran" / "refine_build.sh"
REF = REPO / "host" / "KIM-meso_v1.0" / "phys" / "module_mp_kdm6.F"

pytestmark = pytest.mark.skipif(
    shutil.which("gfortran") is None or not REF.is_file(),
    reason="local-only (needs gfortran + the gitignored host reference tree)",
)


@pytest.fixture(scope="module")
def driver(tmp_path_factory):
    out = tmp_path_factory.mktemp("mt") / "build"
    b = subprocess.run(["bash", str(BUILD), str(out),
                        "--fixture=g33_fixture_multisubcycle_v1",
                        "--algo=legacy", "--nflux"],
                       capture_output=True, text=True, cwd=REPO)
    assert b.returncode == 0, f"build failed:\n{b.stdout}\n{b.stderr}"
    return str(out / "g33_refine_driver")


@pytest.fixture(scope="module")
def result(driver):
    return mt.analysis(driver, 12)


def test_the_metric_term_follows_profile_scaling_with_f32_rounding(result):
    """Ideal profile ratios hold up to f32 forcing arithmetic on this fixture.
    The density-term decomposition remains an identity for the actual profile.
    """
    # +1 for the offsets: a constant added to every level cancels out of
    # (rho_below - rho_above) exactly, so the metric term is untouched while the
    # absolute density moves by 10%.
    want = {"uniform": 0.0, "inverted": -1.0, "x2": 2.0,
            "offset+": 1.0, "offset-": 1.0}
    for arm, cols in result["arms"].items():
        for col, r in cols.items():
            if not r["comparable"] or r["metric_over_baseline"] is None:
                continue
            # Exact in 11 of 12 rows; `offset+` column 2 carries 5.8e-7, which
            # is f32 roundoff on the offset addition itself -- the profile is
            # applied in single precision, so (rho+C)_below - (rho+C)_above is
            # not always bit-identical to rho_below - rho_above.
            assert r["metric_over_baseline"] == pytest.approx(want[arm], abs=1e-6)


def test_the_whole_departure_is_the_TRAJECTORY_term(result):
    """metric + trajectory == actual identically, so the 1-4% departure is not
    attributed to any named mechanism -- it is what is left after the measure
    scaling is removed."""
    for cols in result["arms"].values():
        for r in cols.values():
            if not r["comparable"]:
                continue
            assert r["metric"] + r["trajectory"] == pytest.approx(r["actual"],
                                                                 rel=1e-12)


def test_the_trajectory_response_is_a_FEW_PERCENT_of_the_metric_term(result):
    """The measured size of the thing that was once attributed to fall speed."""
    got = [r["trajectory_over_metric"] for cols in result["arms"].values()
           for r in cols.values()
           if r.get("comparable") and r.get("trajectory_over_metric") is not None]
    assert got and all(0 < g < 0.07 for g in got), got


def test_a_column_whose_SCHEDULE_moved_is_refused_not_zipped(result):
    """`inverted` drops column 3's mstep from 3 to 2 in call 1 -- density sets the
    fall speed and mstep is derived from it. There is then no one-to-one
    interface correspondence, and zipping the two lists would pair unrelated
    interfaces and produce a confident wrong number."""
    r = result["arms"]["inverted"][3]
    assert r["comparable"] is False
    assert "sub-step schedule" in r["reason"]


def test_uniform_kills_BOTH_terms(result):
    """The sampled legacy MAIN fixture has matched number transfers.
    Its flat profile gives zero full residual; this is not true for a general
    independently capped pair (covered by the portable offset counterexample).
    """
    for r in result["arms"]["uniform"].values():
        assert r["metric"] == pytest.approx(0.0, abs=1e-6)
        assert r["trajectory"] == pytest.approx(0.0, abs=1e-6)


def test_an_OFFSET_leaves_the_metric_term_exactly_alone(result):
    """On this matched-transfer legacy main fixture the baseline offset term
    vanishes in exact arithmetic. f32 profile arithmetic remains in the check.
    With unmatched transfers an offset also changes the counterfactual residual.
    """
    for arm in ("offset+", "offset-"):
        for r in result["arms"][arm].values():
            if not r["comparable"]:
                continue
            assert r["metric_over_baseline"] == pytest.approx(1.0, abs=1e-6)


def test_magnitude_moves_the_residual_far_less_than_gradient_does(result):
    """Compare these two perturbation sizes on the sampled legacy main fixture."""
    offs = [abs(r["actual_over_baseline"] - 1.0)
            for arm in ("offset+", "offset-")
            for r in result["arms"][arm].values() if r["comparable"]]
    x2 = [abs(r["actual_over_baseline"] - 1.0)
          for r in result["arms"]["x2"].values() if r["comparable"]]
    assert max(offs) < 0.10 and min(x2) > 0.9


# ---- owner P0-1: interfaces correspond by IDENTITY, not by count -------------

def test_equal_counts_with_DIFFERENT_interfaces_are_refused():
    """The hole: `decompose` paired the two arms by list position whenever the
    lengths matched. A baseline with mstep 2 then 1 and an arm with 1 then 2 have
    the same total and describe different interfaces — element 2 of one call
    would be paired against element 1 of another.

    Not hypothetical: the immediately preceding density control merged calls
    under a key identical across them, compared only the last, and missed a real
    mstep 3->2 change. Same class of mistake, one layer up."""
    # (call, loop, substep, upper, lower) -> (drho, dz, dn)
    cell = lambda dn: {"drho": 0.2, "rho_up": 1., "dz_up": 150.0, "dn_out": dn,
                       "rho_lo": 1.2, "dz_lo": 150.0, "dn_in": dn}
    base = {1: {(1, 1, 1, 0, 1): cell(1.0), (1, 1, 2, 0, 1): cell(2.0),
                (2, 1, 1, 0, 1): cell(3.0)}}
    arm = {1: {(1, 1, 1, 0, 1): cell(1.0), (2, 1, 1, 0, 1): cell(2.0),
               (2, 1, 2, 0, 1): cell(3.0)}}
    assert len(base[1]) == len(arm[1]), "the counts must match for this to bite"
    got = mt.decompose(base, arm)[1]
    assert got["comparable"] is False
    assert "interface universes differ" in got["reason"]


def test_an_identical_universe_decomposes():
    """The control for the test above."""
    mk = lambda drho, dn: {"drho": drho, "rho_up": 1.2-drho, "dz_up": 150.0, "dn_out": dn,
                           "rho_lo": 1.2, "dz_lo": 150.0, "dn_in": dn}
    base = {1: {(1, 1, 1, 0, 1): mk(0.2, 1.0), (1, 1, 2, 0, 1): mk(0.2, 2.0)}}
    arm = {1: {(1, 1, 1, 0, 1): mk(0.4, 1.5), (1, 1, 2, 0, 1): mk(0.4, 2.5)}}
    got = mt.decompose(base, arm)[1]
    assert got["comparable"] is True
    # metric uses the ARM's drho with the BASELINE's dn
    assert got["metric"] == pytest.approx(0.4 * 150.0 * (1.0 + 2.0))


def test_interface_terms_preserve_every_call_identity(driver):
    """Later calls must not overwrite earlier records with the same local key."""
    stream = subprocess.check_output([driver, "12", "rezero", "3"], text=True)
    for rows in mt.interface_terms(stream).values():
        assert {key[0] for key in rows} == set(range(1, 13))
        assert all(len(key) == 5 and key[4] == key[3] + 1 for key in rows)


# ---- owner §4 / §13.1: the chain reaches the raw runs, and the arm is enforced

def test_a_stream_declaring_the_WRONG_arm_is_refused(tmp_path):
    """Recording requested-vs-declared in the JSON and leaving a reviewer to
    notice the mismatch is not a check: a stream that ran the wrong forcing
    would still be published, and every number derived from it attributed to an
    arm it is not (owner §13.1)."""
    fake = tmp_path / "drv"
    fake.write_text(
        "#!/bin/sh\n"
        "echo 'G33N STREAM_BEGIN 4 1 1 1 legacy rezero "
        "mstep,mstepi,nflux,xfer,capin,topout as-is'\n"
        "echo 'G33N STREAM_END'\n")
    fake.chmod(0o755)
    with pytest.raises(SystemExit, match="declares 'as-is'|refusing to attribute"):
        mt.analysis(str(fake), 1)


def test_a_supplied_baseline_declaring_the_wrong_arm_is_refused(tmp_path):
    with pytest.raises(SystemExit, match="baseline stream declares"):
        mt.analysis("unused", 1, baseline_stream=(
            "G33N STREAM_BEGIN 4 1 1 1 legacy rezero "
            "mstep,mstepi,nflux,xfer,capin,topout uniform\nG33N STREAM_END\n"))


def test_the_baseline_can_be_the_BUNDLE_MEMBER_rather_than_a_re_run(result):
    """Re-running the baseline meant the decomposition compared against a stream
    nobody kept — the published member and the analysis baseline were only
    *probably* identical. The producer now passes the stored member."""
    assert result["baseline"] == "re-run", "this fixture calls analysis() directly"
    src = (ROOT / "g33_refine_experiment.py").read_text()
    assert "baseline_stream=member.read_text()" in src


def test_the_raw_arm_streams_are_handed_back_for_preservation(driver):
    """Without `keep`, the six runs existed only inside the function and the
    evidence chain stopped at a derived JSON."""
    keep = {}
    mt.analysis(driver, 12, keep=keep)
    assert set(keep) == set(mt.ARMS)
    assert all(t.startswith("G33N STREAM_BEGIN") for t in keep.values())


# ---- owner §5: the THIRD term, computed rather than assumed zero -------------

def test_the_three_terms_are_an_exact_identity(result):
    """R_full = R_metric + R_number_cap, per interface, by construction:

        R_full    = rho_lo*dz_lo*dn_in - rho_up*dz_up*dn_out
        R_measure = (rho_lo - rho_up)*dz_up*dn_out
        R_ncap    = rho_lo*(dz_lo*dn_in - dz_up*dn_out)

    The density accounting term uses this arm's transfers. The separate
    counterfactual fixes both baseline transfers under the arm's weights.
    Check both identities under diagnostic rounding, without conflating them.
    """
    for cols in result["arms"].values():
        for r in cols.values():
            if not r["comparable"]:
                continue
            assert r["density_contribution"] + r["number_cap_term"] == pytest.approx(
                r["full_interface_residual"], rel=1e-9, abs=1e-6)
            assert r["actual"] == r["full_interface_residual"]
            assert r["weight_effect"] + r["trajectory"] == pytest.approx(
                r["residual_change"], rel=1e-9, abs=1e-6)


def test_metric_only_is_a_CONCLUSION_not_an_assumption(result):
    """Publish the net transfer mismatch instead of assuming it vanishes.
    This field alone does not certify cap inactivity at every interface.
    """
    for cols in result["arms"].values():
        for r in cols.values():
            if not r["comparable"]:
                continue
            assert "measure_only" in r and "number_cap_term" in r
