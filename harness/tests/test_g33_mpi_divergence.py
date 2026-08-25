#!/usr/bin/env python3
"""The MPI divergence comparator, which produced evidence and had no tests.

`FINDING_mpi_repeatability_v1` is read off this module and nothing checked it.
Its contract is in its own first line -- two decompositions "compared without
flattering either" -- so the tests that matter are the ones that ask whether a
statistic can report agreement that is not there.

Everything here drives the functions with SYNTHETIC arrays through a minimal
netCDF-shaped stand-in, so it needs no forecast files and runs anywhere.
"""
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_mpi_divergence as md        # noqa: E402


class _Var:
    """A netCDF variable: indexable, with dtype/ndim/dimensions."""

    def __init__(self, arr, dims):
        self._a = np.asarray(arr)
        self.dimensions = dims
        self.dtype = self._a.dtype
        self.ndim = self._a.ndim
        self.shape = self._a.shape

    def __getitem__(self, k):
        return self._a[k]


class _Ds:
    """A netCDF dataset over {name: (array, dimensions)}."""

    def __init__(self, spec):
        self.variables = {k: _Var(v, dims) for k, (v, dims) in spec.items()}

    def __getitem__(self, k):
        return self.variables[k]


def _pair(x, y, dims=("Time", "south_north", "west_east")):
    times = (np.zeros((x.shape[0], 1), dtype="S1"), ("Time", "DateStrLen"))
    return (_Ds({"T": (x, dims), "Times": times}),
            _Ds({"T": (y, dims), "Times": times}))


# ── the defect: NaN read as agreement ────────────────────────────────────────

def test_a_field_that_went_nan_in_one_run_is_not_reported_as_agreeing():
    """`abs(nan - 1.0)` is `nan`, and `nan > 0` is False, so the old test
    counted zero differing cells for the one outcome this tool exists to catch."""
    x = np.ones((1, 4, 4), dtype="float32")
    y = x.copy()
    y[0, 0, :3] = np.nan
    a, b = _pair(x, y)
    s = md.field_stats(a, b, "T", 0)
    assert s["differing"] == 3, "a NaN asymmetry is a difference"
    assert s["differing_fraction"] == pytest.approx(3 / 16)


def test_the_two_statistics_agree_about_whether_a_field_differs():
    """`coverage` uses `array_equal` and `field_stats` counts cells. On NaN
    they disagreed: one called the field different, the other reported zero
    differing cells -- in the same report."""
    x = np.ones((1, 3, 3), dtype="float32")
    y = x.copy()
    y[0, 1, 1] = np.nan
    a, b = _pair(x, y)
    by_coverage = md.coverage(a, b)[0]["differing"] == 1
    by_cells = md.field_stats(a, b, "T", 0)["differing"] > 0
    assert by_coverage == by_cells == True    # noqa: E712


def test_the_nonfinite_census_says_which_side_broke():
    x = np.ones((1, 2, 2), dtype="float32")
    y = x.copy()
    y[0, 0, 0] = np.inf
    a, b = _pair(x, y)
    s = md.field_stats(a, b, "T", 0)
    assert s["nonfinite_a"] == 0 and s["nonfinite_b"] == 1


def test_a_single_nan_does_not_erase_the_size_of_every_other_difference():
    """Percentiles over an array containing NaN are NaN, which reports nothing
    about the cells that are fine and is not a magnitude."""
    x = np.zeros((1, 10, 10), dtype="float32")
    y = x.copy()
    y[0, 0, :] = 5.0          # a real, finite difference
    y[0, 1, 0] = np.nan       # and one broken cell
    a, b = _pair(x, y)
    s = md.field_stats(a, b, "T", 0)
    assert s["domain_p99"] is not None and np.isfinite(s["domain_p99"])
    assert s["conditional_median"] == pytest.approx(5.0)
    assert s["nonfinite_difference"] == 1


def test_all_nonfinite_reports_none_rather_than_a_fabricated_size():
    x = np.full((1, 2, 2), np.nan, dtype="float32")
    a, b = _pair(x, x.copy())
    s = md.field_stats(a, b, "T", 0)
    assert s["domain_p99"] is None and s["domain_mean_abs"] is None


# ── the statistics that were already right, pinned ───────────────────────────

def test_identical_fields_report_no_difference():
    x = np.arange(16, dtype="float32").reshape(1, 4, 4)
    a, b = _pair(x, x.copy())
    s = md.field_stats(a, b, "T", 0)
    assert s["differing"] == 0 and s["differing_fraction"] == 0.0


def test_conditional_and_unconditional_are_different_populations():
    """The distinction the module exists to make: p99 over differing cells is
    not the domain's p99."""
    x = np.zeros((1, 10, 10), dtype="float32")
    y = x.copy()
    y[0, 0, 0] = 100.0                     # 1 cell of 100 differs
    a, b = _pair(x, y)
    s = md.field_stats(a, b, "T", 0)
    # 99 of 100 cells agree, so the domain p99 lands in the interpolation
    # between the last agreeing cell and the one that differs: 1.0, not 100.
    assert s["domain_p99"] == pytest.approx(1.0)
    assert s["conditional_median"] == pytest.approx(100.0)
    assert s["domain_p99"] < s["conditional_median"] / 50


def test_the_signed_mean_separates_more_from_elsewhere():
    """`|dP|` cannot tell a domain that differs more from one that differs in
    different places; the signed mean can."""
    x = np.zeros((1, 2, 2), dtype="float32")
    more = x.copy(); more[0, 0, 0] = 4.0
    moved = x.copy(); moved[0, 0, 0] = 4.0; moved[0, 1, 1] = -4.0
    a, b = _pair(x, more)
    c, d = _pair(x, moved)
    assert md.field_stats(a, b, "T", 0)["signed_mean"] > 0
    assert md.field_stats(c, d, "T", 0)["signed_mean"] == pytest.approx(0.0)


def test_the_fixed_mask_holds_the_population_still():
    """Growth measured on cells that differ at the FIRST time, not on a support
    that grows between the two times compared."""
    x = np.zeros((1, 4, 4), dtype="float32")
    y = x.copy(); y[0, 0, :] = 2.0
    a, b = _pair(x, y)
    mask = np.zeros((4, 4), dtype=bool); mask[0, :] = True
    s = md.field_stats(a, b, "T", 0, mask=mask)
    assert s["fixed_mask_median"] == pytest.approx(2.0)


def test_coverage_names_the_fields_that_appear_and_vanish_between_frames():
    x = np.zeros((2, 3, 3), dtype="float32")
    y = x.copy()
    y[1] = 1.0                              # differs only at frame 1
    a, b = _pair(x, y)
    cov = md.coverage(a, b)
    assert cov[0]["differing"] == 0
    assert cov[1]["differing"] == 1 and cov[1]["new_since_previous"] == ["T"]
