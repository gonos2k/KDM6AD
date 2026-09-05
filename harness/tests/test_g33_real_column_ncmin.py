"""How much of a real domain the scalar `ncmin` mis-thresholds.

`ncmin` is a scalar set inside the column loop, so the LAST column of a tile
decides the threshold for all of it. Which columns are affected is a function
of geography and tiling alone -- no run, no corrected arm, no frozen code.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_real_column_ncmin as rcn  # noqa: E402

np = pytest.importorskip("numpy")
LC05 = ROOT.parent / "host" / "lc05_da_run" / "wrfinput_d01"


def test_a_UNIFORM_surface_is_never_mis_thresholded():
    """All land, or all sea, and the last column agrees with every other one.
    A tool that cannot report zero there cannot report anything."""
    for kind in (1, 2):
        xl = np.full((4, 6), kind, dtype="int32")
        for tiles in (1, 2, 3):
            assert (rcn.imposed(xl, tiles) == xl).all(), (kind, tiles)


def test_the_LAST_column_of_each_tile_is_the_one_that_decides():
    """The mechanism itself, on a hand-checkable row: land land sea, cut
    once, so the first tile is decided by a land column and the second by a
    sea one."""
    xl = np.array([[1, 1, 2, 2, 1, 1]], dtype="int32")
    assert list(rcn.imposed(xl, 1)[0]) == [1] * 6          # last is land
    assert list(rcn.imposed(xl, 2)[0]) == [2, 2, 2, 1, 1, 1]
    assert list(rcn.imposed(xl, 3)[0]) == [1, 1, 2, 2, 1, 1]   # each pair pure


def test_the_AFFECTED_SET_MOVES_with_the_decomposition():
    """The property that makes this non-locality rather than merely a wrong
    threshold: if the same columns were wrong under every tiling the operator
    would still be a function of the state. They are not."""
    # `[1, 2, 2, 1]` cut once: uncut, every column takes the LAST column's
    # land; cut in half, the first tile ends on sea. An alternating pattern
    # will not do it -- every tile then ends on the same type and the two
    # tilings agree, which is a property of that pattern, not of the defect.
    xl = np.array([[1, 2, 2, 1]], dtype="int32")
    assert list(rcn.imposed(xl, 1)[0]) == [1, 1, 1, 1]
    assert list(rcn.imposed(xl, 2)[0]) == [2, 2, 1, 1]


def test_report_rejects_masked_or_out_of_domain_xland(tmp_path):
    netCDF4 = pytest.importorskip("netCDF4")
    path = tmp_path / "xland.nc"
    with netCDF4.Dataset(str(path), "w") as d:
        d.createDimension("Time", 1)
        d.createDimension("south_north", 1)
        d.createDimension("west_east", 2)
        v = d.createVariable("XLAND", "f8",
                             ("Time", "south_north", "west_east"),
                             fill_value=-9999.0)
        v[0] = np.ma.array([[1.0, 2.0]], mask=[[False, True]])
    with pytest.raises(ValueError, match="masked"):
        rcn.report(path, tilings=(1, 2))

    with netCDF4.Dataset(str(path), "r+") as d:
        d["XLAND"][0] = [[1.0, 3.0]]
    with pytest.raises(ValueError, match="must be 1 .* or 2"):
        rcn.report(path, tilings=(1, 2))


@pytest.mark.skipif(not LC05.is_file(), reason="no LC05 state on this host")
def test_the_REAL_domain_is_substantially_exposed():
    """The measurement the review asks for as external validity for the
    `ncmin` mechanism, run as a test. Loose bounds: this pins the ORDER, not
    a figure that would move with another domain."""
    got = rcn.report(LC05)
    assert got["columns"] > 10000, got["columns"]
    single = [r for r in got["by_tiling"] if r["tiles"] == 1][0]
    assert single["mis_thresholded"] > 0.2, got["by_tiling"]
    # ...and finer tiling helps, because a shorter sweep means the last
    # column speaks for fewer others.
    fine = [r for r in got["by_tiling"] if r["tiles"] == 8][0]
    assert fine["mis_thresholded"] < single["mis_thresholded"], got["by_tiling"]
    # The decisive one: the imposed threshold DEPENDS on the decomposition.
    assert max(p["columns_disagreeing"] for p in got["decomposition_pairs"]) > 0.2, got
    assert got["correct_under_all"] < 0.75, got
