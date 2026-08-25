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
    assert s["finite_domain_p99"] is not None and np.isfinite(s["finite_domain_p99"])
    assert s["conditional_median"] == pytest.approx(5.0)
    assert s["finiteness_differing"] == 1 and s["common_nonfinite"] == 0


def test_all_nonfinite_reports_none_rather_than_a_fabricated_size():
    x = np.full((1, 2, 2), np.nan, dtype="float32")
    a, b = _pair(x, x.copy())
    s = md.field_stats(a, b, "T", 0)
    assert s["finite_domain_p99"] is None and s["finite_domain_mean_abs"] is None


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
    assert s["finite_domain_p99"] == pytest.approx(1.0)
    assert s["conditional_median"] == pytest.approx(100.0)
    assert s["finite_domain_p99"] < s["conditional_median"] / 50


def test_the_signed_mean_separates_more_from_elsewhere():
    """`|dP|` cannot tell a domain that differs more from one that differs in
    different places; the signed mean can."""
    x = np.zeros((1, 2, 2), dtype="float32")
    more = x.copy(); more[0, 0, 0] = 4.0
    moved = x.copy(); moved[0, 0, 0] = 4.0; moved[0, 1, 1] = -4.0
    a, b = _pair(x, more)
    c, d = _pair(x, moved)
    assert md.field_stats(a, b, "T", 0)["finite_signed_mean"] > 0
    assert md.field_stats(c, d, "T", 0)["finite_signed_mean"] == pytest.approx(0.0)


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


# ── the same hole in the sibling function ────────────────────────────────────

def test_a_nan_column_is_not_counted_as_below_every_precipitation_threshold():
    """`abs(nan) > thr` is False, so a column that went NaN silently counted as
    NOT exceeding -- the exceedance fractions understated with no census."""
    x = np.zeros((1, 10, 10), dtype="float32")
    y = x.copy()
    y[0, 0, :5] = 1.0            # 5 columns really exceed 0.1 mm
    y[0, 1, :2] = np.nan         # 2 columns are broken
    a, b = _pair(x, y, dims=("Time", "south_north", "west_east"))
    s = md.precipitation(a, b, 0, name="T")
    assert s["nonfinite_columns"] == 2, "the census must say they exist"
    assert s["columns_over_0.1mm"] == 5
    # the denominator is the finite population, and it is stated
    assert s["fraction_over_0.1mm"] == pytest.approx(5 / 98)
    assert np.isfinite(s["signed_gridcell_mean_mm"])


def test_precipitation_reports_none_rather_than_nan_when_nothing_is_finite():
    x = np.full((1, 3, 3), np.nan, dtype="float32")
    a, b = _pair(x, x.copy())
    s = md.precipitation(a, b, 0, name="T")
    assert s["signed_gridcell_mean_mm"] is None
    assert s["cancellation_ratio"] is None
    assert s["nonfinite_columns"] == 9


def test_the_cancellation_ratio_separates_more_rain_from_rain_elsewhere():
    """The statistic the function exists for, pinned: same gross, different net."""
    x = np.zeros((1, 2, 2), dtype="float32")
    more = x.copy(); more[0, 0, 0] = 2.0; more[0, 0, 1] = 2.0
    moved = x.copy(); moved[0, 0, 0] = 2.0; moved[0, 1, 1] = -2.0
    a, b = _pair(x, more)
    c, d = _pair(x, moved)
    assert md.precipitation(a, b, 0, name="T")["cancellation_ratio"] == pytest.approx(1.0)
    assert md.precipitation(c, d, 0, name="T")["cancellation_ratio"] == pytest.approx(0.0)


def test_reflectivity_is_immune_by_construction_and_says_so():
    """Its physical screen is `x >= lo & x <= hi`, and NaN fails every
    comparison, so NaN lands in `outside_physical` instead of being counted as
    agreement. Pinned because that is why it needed no change."""
    x = np.full((1, 4, 4), 25.0, dtype="float32")
    y = x.copy()
    y[0, 0, :3] = np.nan
    a, b = _pair(x, y)
    s = md.reflectivity(a, b, 0, name="T")
    assert s["outside_physical"] == 3
    assert s["physical_fraction"] == pytest.approx(13 / 16)
    assert np.isfinite(s["screened_p99_dbz"])


def test_the_precipitation_fix_is_a_noop_on_finite_data():
    """It must not move a published number where there was no NaN."""
    rng = np.random.default_rng(4242)
    for _ in range(50):
        x = rng.normal(size=(1, 8, 8)).astype("float32")
        y = (x + rng.normal(size=x.shape).astype("float32") * 1e-3)
        a, b = _pair(x, y)
        s = md.precipitation(a, b, 0, name="T")
        d = y[0].astype("float64") - x[0].astype("float64")
        assert s["signed_gridcell_mean_mm"] == pytest.approx(float(d.mean()))
        assert s["columns_over_0.001mm"] == int((np.abs(d) > 1e-3).sum())
        assert s["nonfinite_columns"] == 0


def test_the_three_ways_to_differ_partition_the_count():
    """"they disagree numerically", "one of them broke" and "both broke in the
    same place" are three findings, and `differing` alone is none of them."""
    x = np.zeros((1, 4, 4), dtype="float32")
    y = x.copy()
    y[0, 0, 0] = 1.0            # a finite disagreement
    y[0, 1, 0] = np.nan         # one side broke
    x[0, 2, 0] = np.nan
    y[0, 2, 0] = np.nan         # both broke, same cell
    a, b = _pair(x, y)
    s = md.field_stats(a, b, "T", 0)
    assert s["finite_value_differing"] == 1
    assert s["finiteness_differing"] == 1
    assert s["common_nonfinite"] == 1
    assert (s["finite_value_differing"] + s["finiteness_differing"]
            + s["common_nonfinite"]) == s["differing"]


def test_the_magnitude_keys_say_which_population_they_are_over():
    x = np.zeros((1, 4, 4), dtype="float32")
    y = x.copy(); y[0, 0, 0] = np.nan
    a, b = _pair(x, y)
    s = md.field_stats(a, b, "T", 0)
    assert "domain_p99" not in s and "finite_domain_p99" in s


# ── the fixed mask needs the finite mask too ─────────────────────────────────

def test_a_cell_that_went_nonfinite_later_does_not_erase_the_held_population():
    """The fixed mask is chosen at the FIRST time and followed, so it can hold a
    cell that breaks later. One of those made the median and the p99 NaN."""
    x = np.zeros((1, 4, 4), dtype="float32")
    y = x.copy()
    y[0, 0, :] = 3.0
    y[0, 0, 0] = np.nan
    a, b = _pair(x, y)
    mask = np.zeros((4, 4), dtype=bool)
    mask[0, :] = True                      # the row held from the first time
    s = md.field_stats(a, b, "T", 0, mask=mask)
    assert s["fixed_mask_cells"] == 4
    assert s["fixed_mask_finite_cells"] == 3
    assert s["fixed_mask_nonfinite_cells"] == 1
    assert s["fixed_mask_median"] == pytest.approx(3.0)


def test_a_wholly_nonfinite_fixed_mask_reports_none_not_a_number():
    x = np.zeros((1, 3, 3), dtype="float32")
    y = x.copy(); y[0, 0, :] = np.nan
    a, b = _pair(x, y)
    mask = np.zeros((3, 3), dtype=bool); mask[0, :] = True
    s = md.field_stats(a, b, "T", 0, mask=mask)
    assert s["fixed_mask_median"] is None and s["fixed_mask_finite_cells"] == 0


# ── the two files must be the same experiment ────────────────────────────────

def test_a_field_present_in_only_one_run_is_refused_not_skipped():
    """`coverage` walked A's fields alone, so a field only B has was never
    compared and its absence read as agreement."""
    x = np.zeros((1, 2, 2), dtype="float32")
    dims = ("Time", "south_north", "west_east")
    times = (np.zeros((1, 1), dtype="S1"), ("Time", "DateStrLen"))
    a = md.__dict__ and _Ds({"T": (x, dims), "Times": times})
    b = _Ds({"T": (x, dims), "QVAPOR": (x, dims), "Times": times})
    with pytest.raises(SystemExit) as e:
        md.comparable(a, b)
    assert "QVAPOR" in str(e.value)


def test_two_runs_on_different_grids_are_refused():
    dims = ("Time", "south_north", "west_east")
    times = (np.zeros((1, 1), dtype="S1"), ("Time", "DateStrLen"))
    a = _Ds({"T": (np.zeros((1, 2, 2), dtype="float32"), dims), "Times": times})
    b = _Ds({"T": (np.zeros((1, 3, 3), dtype="float32"), dims), "Times": times})
    with pytest.raises(SystemExit) as e:
        md.comparable(a, b)
    assert "shape" in str(e.value)


def test_two_runs_with_different_time_axes_are_refused():
    dims = ("Time", "south_north", "west_east")
    x = np.zeros((1, 2, 2), dtype="float32")
    a = _Ds({"T": (x, dims), "Times": (np.zeros((1, 1), dtype="S1"),
                                       ("Time", "DateStrLen"))})
    b = _Ds({"T": (x, dims), "Times": (np.ones((1, 1), dtype="S1"),
                                       ("Time", "DateStrLen"))})
    with pytest.raises(SystemExit) as e:
        md.comparable(a, b)
    assert "time axes differ" in str(e.value)


def test_the_same_experiment_is_accepted():
    x = np.zeros((1, 2, 2), dtype="float32")
    a, b = _pair(x, x.copy())
    md.comparable(a, b)
