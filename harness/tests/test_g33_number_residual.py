"""Portable counterexamples for accounting from parsed CAPIN/TOPOUT operands.

These test interface pairing and aggregation, not a new transport algorithm.
The stream parser's completeness/format tests live in test_g33_number_transport.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import g33_cap_interface as ci


def _captured(monkeypatch, rows, chain="main"):
    """Each row: upper/lower density, thickness, actual departure and arrival."""
    call = {"loops": {1}, "outer_pre_sed": {}, "mstep": {}, "topout": {}, "capin": {}}
    for col, (ru, rl, zu, zl, departure, arrival) in enumerate(rows, 1):
        call["outer_pre_sed"][(1, col, 0)] = {"rho": ru, "delz": zu}
        call["outer_pre_sed"][(1, col, 1)] = {"rho": rl, "delz": zl}
        call["mstep"][(1, chain, col)] = 1
        call["topout"][(1, 1, col, chain, 0)] = (0., departure)
        call["capin"][(1, 1, col, chain, 1)] = (0., 0., 0., arrival)
    monkeypatch.setattr(ci.nt, "calls", lambda stream: [call])
    return ci.interfaces("synthetic parsed records")


@pytest.mark.parametrize("chain", ["main", "ice"])
def test_post_update_inflow_cap_reverses_the_density_proxy_sign(monkeypatch, chain):
    # Top n=1 loses .75; the updated .25 caps the inflow below. Bottom loses 0.
    row = _captured(monkeypatch, [(1., 2., 1., 1., .75, .25)], chain)[(chain, 1)]
    assert row["number_predicted"] == .75
    assert row["number_transfer_mismatch"] == -1.
    assert row["number_created"] == -.25
    assert row["number_transported"] == .75
    before, after = 1. * 1., 1. * .25 + 2. * .25
    assert row["number_created"] == after - before
    assert row["number_created"] == (row["number_predicted"]
                                      + row["number_transfer_mismatch"])


def test_thickness_scaled_arrival_has_no_transfer_mismatch(monkeypatch):
    row = _captured(monkeypatch, [(1., 2., 2., 1., .25, .5)])[("main", 1)]
    assert row["number_transfer_mismatch"] == 0.
    assert row["number_created"] == row["number_predicted"] == .5


def test_pairing_uses_each_upper_cells_departure_not_the_top_repeated(monkeypatch):
    _captured(monkeypatch, [(1., 2., 1., 1., .75, .25)])
    call = ci.nt.calls("")[0]
    call["outer_pre_sed"][(1, 1, 2)] = {"rho": 3., "delz": 1.}
    call["capin"][(1, 1, 1, "main", 1)] = (0., 0., .1, .25)
    call["capin"][(1, 1, 1, "main", 2)] = (0., 0., 0., .05)
    row = ci.interfaces("")[("main", 1)]
    assert row["interfaces"] == 2
    assert row["number_created"] == pytest.approx(-.25 + 3*.05 - 2*.1)
    assert row["number_transported"] == pytest.approx(.75 + 2*.1)
    assert row["number_created"] == pytest.approx(
        row["number_predicted"] + row["number_transfer_mismatch"])


@pytest.mark.parametrize("departures, expected", [((1., 100.), .099108910891),
                                                 ((100., 1.), .010891089109)])
def test_clipping_frequency_does_not_bound_a_weighted_ratio(monkeypatch, departures, expected):
    # Before clipping, two equal departures see contrasts 1% and 10%: 5.5%.
    # Clipping just one departure changes the weights, increasing OR decreasing it.
    rows = _captured(monkeypatch, [
        (1., 1.01, 1., 1., departures[0], departures[0]),
        (1., 1.10, 1., 1., departures[1], departures[1]),
    ])
    residual = sum(r["number_created"] for r in rows.values())
    actual_departure = sum(r["number_transported"] for r in rows.values())
    assert residual / actual_departure == pytest.approx(expected)
    assert (.01 * 100 + .10 * 100) / 200 == pytest.approx(.055)
