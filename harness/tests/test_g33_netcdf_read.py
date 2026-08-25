#!/usr/bin/env python3
"""The reader refuses a mask rather than dropping it (owner review 7.4)."""
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_netcdf_read as nr           # noqa: E402


class _Var:
    name = "TESTVAR"

    def __init__(self, a):
        self._a = a

    def __getitem__(self, k):
        return self._a[k] if k is not Ellipsis else self._a


def test_an_unmasked_variable_reads_with_a_full_census():
    v = _Var(np.ma.asarray(np.arange(6.0).reshape(2, 3)))
    r = nr.read_numeric(v)
    assert r["total_count"] == 6 and r["masked_count"] == 0
    assert r["finite_count"] == 6 and r["nonfinite_count"] == 0


def test_a_masked_variable_is_refused_rather_than_silently_unmasked():
    """`np.asarray` on a MaskedArray drops the mask, and the fill value then
    passes as data."""
    a = np.ma.masked_array(np.arange(6.0).reshape(2, 3),
                           mask=[[True, False, False], [False, False, False]])
    with pytest.raises(ValueError) as e:
        nr.read_numeric(_Var(a))
    assert "1 of 6" in str(e.value) and "masked" in str(e.value)


def test_a_mask_can_be_admitted_deliberately_and_becomes_nan():
    a = np.ma.masked_array(np.arange(4.0), mask=[True, False, False, False])
    r = nr.read_numeric(_Var(a), allow_masked=True)
    assert np.isnan(r["data"][0]) and r["masked_count"] == 1
    assert r["finite_count"] == 3 and r["nonfinite_count"] == 1


def test_a_nonfinite_value_is_counted_without_being_masked():
    a = np.ma.asarray(np.array([1.0, np.nan, np.inf, 4.0]))
    r = nr.read_numeric(_Var(a))
    assert r["masked_count"] == 0 and r["nonfinite_count"] == 2
