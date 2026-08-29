#!/usr/bin/env python3
"""Synthetic-array smoke tests on `g33_number_basis`: the real functions, no
reference tree. `ruff --select F821,F822,F823` in CI is the name check."""
import sys
import types
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_number_basis as nb           # noqa: E402


# ── the function itself, on synthetic arrays ─────────────────────────────────

class _Var:
    def __init__(self, a):
        self._a = np.asarray(a)
        self.shape = self._a.shape

    def __getitem__(self, k):
        return self._a[k]


class _Ds:
    def __init__(self, spec):
        self.variables = dict(spec)

    def __getitem__(self, k):
        return self.variables[k]


def _fake_state(monkeypatch, number, legacy_dry, armn_dry, mass):
    """Drive the function without netCDF4 or a forecast file."""
    ds = _Ds({"QNRAIN": _Var(np.asarray(number)[None, ...])})
    fake = types.SimpleNamespace(Dataset=lambda _path: ds)
    monkeypatch.setitem(sys.modules, "netCDF4", fake)
    monkeypatch.setattr(nb, "profile", lambda *a, **k: {
        "dry_layer_mass_upper": np.asarray(mass),
        "legacy_moist": np.asarray(legacy_dry),
        "legacy_dry": np.asarray(legacy_dry),
        "armn_dry": np.asarray(armn_dry),
    })


def test_it_runs_at_all_on_a_populated_column(monkeypatch):
    """It did not: `NameError: name 'keep' is not defined`, on every state whose
    number population is non-empty."""
    K = 5
    _fake_state(monkeypatch,
                number=np.full((K, 1, 1), 2.0),
                legacy_dry=np.full((K - 1, 1, 1), 0.10),
                armn_dry=np.full((K - 1, 1, 1), 0.02),
                mass=np.full((K - 1, 1, 1), 3.0))
    out = nb.where_the_number_is(Path("synthetic"))
    assert out["armn_residual_fraction"]["median"] == pytest.approx(0.2)
    assert out["armn_residual_fraction"]["valid_interfaces"] == 4


def test_an_empty_number_population_returns_early(monkeypatch):
    K = 5
    _fake_state(monkeypatch,
                number=np.zeros((K, 1, 1)),
                legacy_dry=np.full((K - 1, 1, 1), 0.10),
                armn_dry=np.full((K - 1, 1, 1), 0.02),
                mass=np.full((K - 1, 1, 1), 3.0))
    assert nb.where_the_number_is(Path("synthetic")).get("empty") is True


def test_a_nonfinite_interface_is_excluded_and_counted(monkeypatch):
    """The census must be over the population it describes -- which is the
    defect that produced the NameError in the first place."""
    K = 5
    legacy = np.full((K - 1, 1, 1), 0.10)
    legacy[0] = np.nan
    _fake_state(monkeypatch,
                number=np.full((K, 1, 1), 2.0),
                legacy_dry=legacy,
                armn_dry=np.full((K - 1, 1, 1), 0.02),
                mass=np.full((K - 1, 1, 1), 3.0))
    out = nb.where_the_number_is(Path("synthetic"))
    r = out["armn_residual_fraction"]
    assert r["population_interfaces"] == 4
    assert r["valid_interfaces"] == 3
    assert r["nonfinite_excluded"] == 1
    assert np.isfinite(r["median"])


def test_every_population_reports_what_it_dropped(monkeypatch):
    K = 4
    armn = np.full((K - 1, 1, 1), 0.02)
    armn[1] = np.inf
    _fake_state(monkeypatch,
                number=np.full((K, 1, 1), 2.0),
                legacy_dry=np.full((K - 1, 1, 1), 0.10),
                armn_dry=armn,
                mass=np.full((K - 1, 1, 1), 3.0))
    out = nb.where_the_number_is(Path("synthetic"))
    assert out["nonfinite_interfaces"] == 1
    for name, pop in out["populations"].items():
        assert pop["population_interfaces"] >= pop["valid_interfaces"], name
        assert pop["nonfinite_excluded"] == 1, name


def test_an_upper_populated_front_is_not_thrown_away_as_empty(monkeypatch):
    """`upper_populated` exists because an interface whose UPPER cell carries
    number and whose lower cell is empty is transport-active -- sedimentation
    moves number downward. Returning `empty` on `occupied_pair` alone discarded
    exactly those, which is the front the second population was added to see."""
    K = 5
    n = np.zeros((K, 1, 1))
    n[3:] = 2.0                        # loaded above, empty below: a front
    _fake_state(monkeypatch, number=n,
                legacy_dry=np.full((K - 1, 1, 1), 0.10),
                armn_dry=np.full((K - 1, 1, 1), 0.02),
                mass=np.full((K - 1, 1, 1), 3.0))
    out = nb.where_the_number_is(Path("synthetic"))
    assert out.get("empty") is not True, "the front was discarded as empty"
    assert out["populations"]["upper_populated"]["valid_interfaces"] > 0
    assert out["populations"]["occupied_pair"]["valid_interfaces"] >= 0


def test_a_genuinely_empty_field_still_returns_empty(monkeypatch):
    """Widening the early return must not remove it."""
    K = 5
    _fake_state(monkeypatch, number=np.zeros((K, 1, 1)),
                legacy_dry=np.full((K - 1, 1, 1), 0.10),
                armn_dry=np.full((K - 1, 1, 1), 0.02),
                mass=np.full((K - 1, 1, 1), 3.0))
    assert nb.where_the_number_is(Path("synthetic")).get("empty") is True


def test_a_nonfinite_number_cell_is_counted_not_silently_dropped(monkeypatch):
    """`n > 0` is False at a NaN, so a broken number cell used to leave every
    population without appearing in any census (owner review 6.2)."""
    K = 5
    n = np.full((K, 1, 1), 2.0)
    n[2] = np.nan
    _fake_state(monkeypatch, number=n,
                legacy_dry=np.full((K - 1, 1, 1), 0.10),
                armn_dry=np.full((K - 1, 1, 1), 0.02),
                mass=np.full((K - 1, 1, 1), 3.0))
    out = nb.where_the_number_is(Path("synthetic"))
    assert out["nonfinite_number_interfaces"] == 2      # k=2 bounds two interfaces
    assert out["nonfinite_interfaces"] >= 2


def test_negative_number_cells_are_reported(monkeypatch):
    """The real ten-minute forecast carries 97 negative QNRAIN cells. A number
    concentration below zero is not a measurement; it should be visible."""
    K = 4
    n = np.full((K, 1, 1), 2.0)
    n[1] = -1.0
    _fake_state(monkeypatch, number=n,
                legacy_dry=np.full((K - 1, 1, 1), 0.10),
                armn_dry=np.full((K - 1, 1, 1), 0.02),
                mass=np.full((K - 1, 1, 1), 3.0))
    assert nb.where_the_number_is(Path("synthetic"))["negative_number_cells"] == 1


def test_a_zero_legacy_denominator_leaves_the_ratio(monkeypatch):
    """Flooring it at 1e-300 turned an interface with no legacy defect into an
    enormous finite ratio and put it in the median (owner review 6.3)."""
    K = 4
    legacy = np.full((K - 1, 1, 1), 0.10)
    legacy[0] = 0.0
    _fake_state(monkeypatch, number=np.full((K, 1, 1), 2.0),
                legacy_dry=legacy, armn_dry=np.full((K - 1, 1, 1), 0.02),
                mass=np.full((K - 1, 1, 1), 3.0))
    out = nb.where_the_number_is(Path("synthetic"))
    pop = out["populations"]["occupied_pair"]
    assert pop["zero_legacy_denominator"] == 1
    assert pop["ratio_interfaces"] == pop["valid_interfaces"] - 1
    assert pop["median"] == pytest.approx(0.2)     # not 2e+298


def test_an_empty_ratio_population_is_a_verdict_not_an_IndexError(monkeypatch):
    """`valid.any()` was asked and `ratio.any()` was not. A column whose every
    valid interface has `legacy_dry == 0` reached `np.median` on an empty array
    and raised `IndexError: cannot do a non-empty take from an empty axes`
    (owner review 9). The two populations are different sizes and only one of
    them can carry a median."""
    K = 4
    _fake_state(monkeypatch, number=np.full((K, 1, 1), 2.0),
                legacy_dry=np.zeros((K - 1, 1, 1)),
                armn_dry=np.full((K - 1, 1, 1), 0.02),
                mass=np.full((K - 1, 1, 1), 3.0))
    out = nb.where_the_number_is(Path("synthetic"))
    for name, pop in out["populations"].items():
        assert pop["ratio_interfaces"] == 0, name
        assert pop.get("empty_ratio") is True, name
        assert "median" not in pop, f"{name} reported a median over nothing"
    r = out["armn_residual_fraction"]
    assert r["ratio_interfaces"] == 0 and r.get("empty_ratio") is True
    assert "median" not in r


def test_a_partly_zero_denominator_still_reports_over_what_is_left(monkeypatch):
    """The guard must not swallow a population that has SOME usable ratios."""
    K = 4
    legacy = np.full((K - 1, 1, 1), 0.10)
    legacy[0] = 0.0
    _fake_state(monkeypatch, number=np.full((K, 1, 1), 2.0),
                legacy_dry=legacy, armn_dry=np.full((K - 1, 1, 1), 0.02),
                mass=np.full((K - 1, 1, 1), 3.0))
    pop = nb.where_the_number_is(Path("synthetic"))["populations"]["occupied_pair"]
    assert pop["zero_legacy_denominator"] == 1
    assert pop["ratio_interfaces"] == pop["valid_interfaces"] - 1
    assert pop["median"] == pytest.approx(0.2)
    assert "empty_ratio" not in pop
