"""The density matrix on the ICE chain, via the conservative variant (owner §13-3).

LOCAL ONLY (needs gfortran + the gitignored host reference tree).

Every density result so far has been main-chain only, because legacy's `ice/qi`
mass control fails on the post-update inflow cap and an uncontrolled row is not
evidence. The conservative interface computes the inflow once from the source
cell's actual outflow, so there is no post-update recapture, `ice/qi` closes, and
the ice chain becomes measurable under exactly the same arms.

This extends the fixture comparison to another chain, species pair and
algorithm, while sharing the driver, parser and diagnostic apparatus.
"""
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_matched_closure as mc  # noqa: E402
import g33_metric_trajectory as mt  # noqa: E402

REPO = ROOT.parent
BUILD = ROOT / "g33_fortran" / "refine_build.sh"
REF = REPO / "host" / "KIM-meso_v1.0" / "phys" / "module_mp_kdm6.F"

pytestmark = pytest.mark.skipif(
    shutil.which("gfortran") is None or not REF.is_file(),
    reason="local-only (needs gfortran + the gitignored host reference tree)",
)

ARMS = ("as-is", "uniform", "inverted", "x2", "offset+", "offset-")


@pytest.fixture(scope="module")
def driver(tmp_path_factory):
    out = tmp_path_factory.mktemp("ice") / "build"
    b = subprocess.run(["bash", str(BUILD), str(out),
                        "--fixture=g33_fixture_multisubcycle_v1",
                        "--algo=conservative", "--nflux"],
                       capture_output=True, text=True, cwd=REPO)
    assert b.returncode == 0, f"build failed:\n{b.stdout}\n{b.stderr}"
    return str(out / "g33_refine_driver")


@pytest.fixture(scope="module")
def rows(driver):
    out = {}
    for arm in ARMS:
        r = subprocess.run([driver, "12", "rezero", "3", arm],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        out[arm] = mc.analysis(r.stdout)
    return out


def test_the_ice_mass_control_CLOSES_in_every_arm(rows):
    """The premise. In legacy it fails at -269%/-384% and every ice row is
    excluded; if it did not close here, none of the results below would be
    evidence either."""
    for arm, a in rows.items():
        for col in (2, 3):
            r = a[f"ice/qi/{col}"]
            assert r["usable"], f"{arm} ice/qi col {col}: {r['reason']}"


def test_flattening_the_density_removes_the_ICE_number_creation(rows):
    base = rows["as-is"]
    for col in (2, 3):
        assert abs(rows["uniform"][f"ice/ni/{col}"]["residual"]) < \
            1e-4 * abs(base[f"ice/ni/{col}"]["residual"])


def test_inverting_flips_and_doubling_doubles_on_the_ICE_chain(rows):
    """+6.28%/+7.06% goes to -7.03%/-7.93% inverted and +11.91%/+13.27% doubled:
    the same structure the main chain shows, on a chain governed by mstep_i."""
    base = rows["as-is"]
    for col in (2, 3):
        b = base[f"ice/ni/{col}"]["residual"]
        assert rows["inverted"][f"ice/ni/{col}"]["residual"] / b == \
            pytest.approx(-1, abs=0.05)
        assert rows["x2"][f"ice/ni/{col}"]["residual"] / b == \
            pytest.approx(2, abs=0.10)


def test_an_OFFSET_barely_moves_the_ICE_residual(rows):
    """Magnitude against gradient, on ice: +/-10% absolute density moves the
    residual by at most ~6% while doubling the gradient doubles it."""
    base = rows["as-is"]
    for arm in ("offset+", "offset-"):
        for col in (2, 3):
            ratio = rows[arm][f"ice/ni/{col}"]["residual"] / \
                base[f"ice/ni/{col}"]["residual"]
            assert abs(ratio - 1.0) < 0.10


def test_ice_counterfactual_ratios_on_the_sampled_baseline(driver):
    """The fixture's matched baseline transfers give the ideal profile ratios,
    allowing for f32 profile rounding. Unmatched pairs need not scale this way.
    """
    a = mt.analysis(driver, 12, chain="ice")
    want = {"uniform": 0.0, "inverted": -1.0, "x2": 2.0,
            "offset+": 1.0, "offset-": 1.0}
    seen = 0
    for arm, cols in a["arms"].items():
        for r in cols.values():
            if not r["comparable"] or r["metric_over_baseline"] is None:
                continue
            assert r["metric_over_baseline"] == pytest.approx(want[arm], abs=1e-6)
            seen += 1
    assert seen >= 8, f"only {seen} comparable ice rows"


# ---- owner §5: the number-cap gate, and proof that it can fail ---------------

def test_conservative_ice_arrivals_match_applied_f32_arithmetic(driver):
    """Equal layer thickness does not undo the rounding in (dn*dz)/dz.

    Archived CAPIN contained dn twice and falsely implied zero mismatch.
    Verify all actual arrivals bitwise against the conservative update, then
    pin the one rounded mismatch in this fixture instead of widening a zero
    tolerance. This checks producer meaning as well as the diagnostic sum.
    """
    def f32(value):
        return struct.unpack("f", struct.pack("f", value))[0]

    streams = {}
    a = mt.analysis(driver, 12, chain="ice", keep=streams)
    seen, nonzero = 0, {}
    for arm, cols in a["arms"].items():
        terms = mt.interface_terms(streams[arm], "ice")
        for col, r in cols.items():
            if not r["comparable"]:
                continue
            for key, row in terms[col].items():
                expected_in = f32(f32(row["dn_out"] * row["dz_up"]) / row["dz_lo"])
                assert struct.pack("f", row["dn_in"]) == struct.pack("f", expected_in), (arm, col, key)
                seen += 1
            if r["number_cap_term"]:
                nonzero[(arm, col)] = r["number_cap_term"]
                assert not r["measure_only"]
    assert seen == 540  # five perturbed profiles, three columns, 36 interfaces
    assert nonzero == pytest.approx({("inverted", 2): -0.05458984465803951}, abs=1e-12)


@pytest.fixture(scope="module")
def legacy_driver(tmp_path_factory):
    out = tmp_path_factory.mktemp("legacy") / "build"
    b = subprocess.run(["bash", str(BUILD), str(out),
                        "--fixture=g33_fixture_multisubcycle_v1",
                        "--algo=legacy", "--nflux"],
                       capture_output=True, text=True, cwd=REPO)
    assert b.returncode == 0, f"build failed:\n{b.stdout}\n{b.stderr}"
    return str(out / "g33_refine_driver")


def test_the_gate_FIRES_on_legacy_ice_where_the_cap_binds(legacy_driver):
    """A gate that never reports False proves nothing. On LEGACY ice the number
    cap binds at 39 of 108 interfaces, and there the cap term does not merely
    appear — it DOMINATES the metric term by an order of magnitude or more.
    That is the quantitative reason legacy ice is excluded, where before there
    was only "its mass control fails"."""
    a = mt.analysis(legacy_driver, 12, chain="ice")
    fired = [r for cols in a["arms"].values() for r in cols.values()
             if r.get("comparable") and not r["measure_only"]]
    assert fired, "measure_only never went False — the gate is vacuous"
    dominated = [r for r in fired
                 if abs(r["number_cap_term"]) > 5 * abs(r["density_contribution"])]
    assert dominated, "expected the cap term to dominate the metric term"
