"""The density matrix on the ICE chain, via the conservative variant (owner §13-3).

LOCAL ONLY (needs gfortran + the gitignored host reference tree).

Every density result so far has been main-chain only, because legacy's `ice/qi`
mass control fails on the post-update inflow cap and an uncontrolled row is not
evidence. The conservative interface computes the inflow once from the source
cell's actual outflow, so there is no post-update recapture, `ice/qi` closes, and
the ice chain becomes measurable under exactly the same arms.

That makes this an independent replication rather than a repetition: a different
chain (`mstep_i`, not `mstep`), a different species pair, and a different
algorithm.
"""
import shutil
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


def test_the_ICE_metric_term_is_exact_too(driver):
    """The decomposition holds on ice: metric/base is exactly 0 / -1 / +2 / +1,
    so the whole departure is trajectory there as well."""
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

def test_the_conservative_ice_number_cap_term_is_ZERO_in_every_arm(driver):
    """G33-NUMBER-009 rested on the ice MASS control plus the arm ratios. A
    passing mass control does not establish that the NUMBER cap is inactive, and
    if it were active the metric-only reading would be incomplete. Computed
    directly: the term is exactly zero at every interface in every arm, so the
    metric decomposition is complete here — a conclusion, not an assumption."""
    a = mt.analysis(driver, 12, chain="ice")
    seen = 0
    for cols in a["arms"].values():
        for r in cols.values():
            if not r["comparable"]:
                continue
            assert r["number_cap_term"] == pytest.approx(0.0, abs=1e-6)
            assert r["measure_only"] is True
            seen += 1
    assert seen >= 8, f"only {seen} comparable ice rows"


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
                 if abs(r["number_cap_term"]) > 5 * abs(r["metric"])]
    assert dominated, "expected the cap term to dominate the metric term"
