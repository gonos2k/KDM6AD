"""Portable counterexamples for accounting from parsed CAPIN/TOPOUT operands.

These test interface pairing and aggregation, not a new transport algorithm.
The stream parser's completeness/format tests live in test_g33_number_transport.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import g33_cap_interface as ci
import test_g33_number_transport as stream_fixture


def _captured(monkeypatch, rows, chain="main"):
    """Each row: upper/lower density, thickness, actual departure and arrival."""
    call = {"loops": {1}, "outer_pre_sed": {}, "mstep": {}, "topout": {}, "capin": {},
            "features": {"capin", "topout"}, "algorithm": "legacy"}
    for col, (ru, rl, zu, zl, departure, arrival) in enumerate(rows, 1):
        call["outer_pre_sed"][(1, col, 0)] = {"rho": ru, "delz": zu}
        call["outer_pre_sed"][(1, col, 1)] = {"rho": rl, "delz": zl}
        for ch in ("main", "ice"):
            call["mstep"][(1, ch, col)] = int(ch == chain)
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


def _stream(algorithm="legacy", *, applied=False):
    features = stream_fixture._FEATS + (",capin_applied" if applied else "")
    return stream_fixture._stream(stream_fixture._ext(), feats=features).replace(
        "legacy rezero", f"{algorithm} rezero")


def test_interface_analysis_requires_captured_transfers():
    stream = stream_fixture._stream(stream_fixture._call(1))
    with pytest.raises(ci.nt.StreamError, match="requires features.*capin.*topout"):
        ci.interfaces(stream)


@pytest.mark.parametrize("algorithm", ["conservative", "cons_nmass", "cons_lncmin",
                                      "cons_nmasslncmin"])
def test_archived_conservative_raw_arrivals_cannot_be_read_as_applied(algorithm):
    with pytest.raises(ci.nt.StreamError, match="lacks capin_applied"):
        ci.interfaces(_stream(algorithm))


def test_unknown_basis_or_algorithm_is_refused():
    with pytest.raises(ValueError, match="unknown basis"):
        ci.interfaces(_stream(), basis="typo")
    with pytest.raises(ValueError, match="not a registered arm"):
        ci.interfaces(_stream("cons"))


def test_capin_applied_requires_its_record_families():
    stream = stream_fixture._stream(stream_fixture._call(1),
                                   feats="mstep,mstepi,nflux,capin_applied")
    with pytest.raises(ci.nt.StreamError, match="requires capin and topout"):
        ci.nt.calls(stream)


@pytest.mark.parametrize("applied", [False, True])
def test_legacy_records_remain_readable(applied):
    rows = ci.interfaces(_stream(applied=applied))
    assert set(rows) == {("main", 1), ("ice", 1)}
    assert all(r["interfaces"] == 1 and r["number_created"] == 0 for r in rows.values())


def test_conservative_applied_arrival_closes_on_unequal_layers():
    # Source thickness=2, destination=1; raw outflow=2, applied arrival=4.
    # Both densities=1. The parser and analyzer must retain destination units.
    stream = _stream("conservative", applied=True).replace(
        "outer_pre_sed 0 delz 1 0 f32 3F800000",
        "outer_pre_sed 0 delz 1 0 f32 40000000")
    stream = stream.replace("f32 3F800000 3F800000 40000000 40000000",
                            "f32 3F800000 40000000 40000000 40800000")
    rows = ci.interfaces(stream)
    for row in rows.values():
        assert row["number_transported"] == 4.
        assert row["number_created"] == row["number_transfer_mismatch"] == 0.
        assert row["mass_interface_term"] == 0.


@pytest.mark.parametrize("algorithm", ["conservative", "cons_nmass", "cons_lncmin",
                                      "cons_nmasslncmin"])
def test_conservative_producer_emits_the_update_operand(algorithm):
    from g33_fortran import g33_fortran_bindings as bindings
    for anchor, chain, own_q, in_q, own_n, in_n in bindings.CAP_SITES[algorithm]:
        suffix = "r" if chain == "main" else "i"
        assert in_q == f"dq{suffix}(i,k+1)*src_metric/dst_metric"
        # The actual anchored number update contains exactly the emitted operand.
        assert anchor.strip() == "+" + in_n
        assert own_q == f"dq{suffix}(i,k)"
        assert own_n == f"dn{suffix}(i,k)"


@pytest.mark.parametrize("basis", ["operator", "physical"])
def test_paired_residual_matches_independent_endpoint_and_surface_ledger(basis):
    from test_g33_dual_ledger import _stream as ledger_stream
    stream = ledger_stream([.00002, .0015, .008, .018])
    paired = ci.interfaces(stream, basis)[("main", 1)]
    ledger = ci.mc.closures(stream, basis)[("main", "nr", 1)]
    assert paired["number_created"] == pytest.approx(ledger["residual"], rel=1e-12)
    assert paired["number_transported"] > 0
