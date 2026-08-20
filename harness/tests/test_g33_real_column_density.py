"""The defect coefficient over a real atmosphere, and the tool that reads it.

`eps_j = den(lower)/den(upper) - 1` is the fraction of number the legacy
transport metric over-delivers across one interface. It falls out of the
identity `g33_number_transport` establishes, and the transfer cancels -- so it
is a function of the density profile alone and needs no run, no corrected arm,
and no change to the frozen kernel.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_real_column_density as rcd  # noqa: E402

np = pytest.importorskip("numpy")
LC05 = ROOT.parent / "host" / "lc05_da_run" / "wrfinput_d01"


def _state(tmp_path, den_profile):
    """A minimal WRF-shaped file whose derived density is `den_profile`.

    Synthetic, so the TOOL's properties are tested where CI runs: `host/**` is
    private and gitignored, and a test that needs it is silent on every public
    checkout -- the distinction this campaign already drew for the pin
    verifier.
    """
    netCDF4 = pytest.importorskip("netCDF4")
    path = tmp_path / "wrfinput_synthetic"
    n = len(den_profile)
    with netCDF4.Dataset(str(path), "w") as d:
        d.createDimension("Time", 1)
        d.createDimension("bottom_top", n)
        d.createDimension("south_north", 1)
        d.createDimension("west_east", 1)
        dims = ("Time", "bottom_top", "south_north", "west_east")
        # Hold theta and qv fixed and put the whole profile in pressure, so
        # `den = p / (Rd T (1 + 0.608 qv))` is monotone in `p` and the
        # expected `eps` is exact rather than approximate.
        theta, qv = 300.0, 0.0
        press = np.array([rho * rcd.RD * theta for rho in den_profile])
        press = np.array([(p ** (1.0 / (1.0 - rcd.RD / rcd.CP)))
                          / (rcd.P0 ** (rcd.RD / rcd.CP / (1 - rcd.RD / rcd.CP)))
                          for p in press])
        for name, val in (("P", press), ("PB", np.zeros(n)),
                          ("T", np.full(n, theta - 300.0)),
                          ("QVAPOR", np.full(n, qv))):
            v = d.createVariable(name, "f8", dims)
            v[0, :, 0, 0] = val
    return path


def test_a_UNIFORM_density_profile_has_no_defect(tmp_path):
    """The closed form says a flat profile leaks nothing. If the tool cannot
    report zero there it cannot report anything."""
    got = rcd.profile(_state(tmp_path, [1.0] * 6))
    assert np.abs(got["eps"]).max() < 1e-12, got["eps"]


def test_a_DECREASING_profile_over_delivers(tmp_path):
    """Density falls with height, so the lower side of every interface is
    denser and the legacy metric delivers MORE number than left."""
    got = rcd.profile(_state(tmp_path, [1.2, 1.0, 0.8]))
    eps = got["eps"].ravel()
    assert (eps > 0).all(), eps
    assert abs(eps[0] - (1.2 / 1.0 - 1.0)) < 1e-9, eps
    assert abs(eps[1] - (1.0 / 0.8 - 1.0)) < 1e-9, eps


def test_an_INVERTED_profile_reverses_the_sign(tmp_path):
    """...and the sign follows the gradient, which is what makes this a
    property of the metric rather than of one atmosphere."""
    got = rcd.profile(_state(tmp_path, [0.8, 1.0, 1.2]))
    assert (got["eps"].ravel() < 0).all(), got["eps"]


@pytest.mark.skipif(not LC05.is_file(), reason="no LC05 state on this host")
def test_the_REAL_atmosphere_carries_the_coefficient():
    """The measurement the review asks for as external validity, run as a
    test. Bounds are deliberately loose -- this pins the ORDER, not a figure
    that would move with a different case."""
    got = rcd.report(LC05)
    assert got["columns"] > 10000, got["columns"]
    assert 0.05 < got["eps_median"] < 0.15, got
    assert got["eps_negative_fraction"] < 0.01, got
    # ...and it grows with height, which is the physical content: the
    # stratification the metric ignores is strongest aloft.
    lo = [r for r in got["by_level"] if r["p_mid_hpa"] > 900][0]
    hi = [r for r in got["by_level"] if r["p_mid_hpa"] < 150][0]
    assert hi["eps_median"] > 5 * lo["eps_median"], (lo, hi)
