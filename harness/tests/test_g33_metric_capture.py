"""Portable producer/consumer contract tests for the trajectory analysis."""
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import g33_cap_interface as ci
import g33_metric_trajectory as mt
from test_g33_number_residual import _stream
from test_g33_number_transport import _call, _stream as core_stream


@pytest.mark.parametrize("reader", [ci.interfaces, mt.interface_terms])
@pytest.mark.parametrize("algorithm", ["conservative", "cons_nmass", "cons_lncmin",
                                      "cons_nmasslncmin"])
def test_every_arrival_consumer_rejects_unscaled_conservative_archives(reader, algorithm):
    with pytest.raises(ci.nt.StreamError, match="lacks capin_applied"):
        reader(_stream(algorithm))


@pytest.mark.parametrize("reader", [ci.interfaces, mt.interface_terms])
def test_every_arrival_consumer_requires_capture(reader):
    with pytest.raises(ci.nt.StreamError, match="requires features"):
        reader(core_stream(_call(1)))


@pytest.mark.parametrize("algorithm,applied", [("legacy", False), ("conservative", True)])
@pytest.mark.parametrize("chain", ["main", "ice"])
def test_trajectory_full_residual_matches_interface_analyzer(algorithm, applied, chain):
    stream = _stream(algorithm, applied=applied).replace(
        "outer_pre_sed 0 delz 1 0 f32 3F800000",
        "outer_pre_sed 0 delz 1 0 f32 40000000")
    # Top thickness 2, lower thickness 1: applied arrival doubles departure.
    stream = stream.replace("f32 3F800000 3F800000 40000000 40000000",
                            "f32 3F800000 40000000 40000000 40800000")
    terms = mt.interface_terms(stream, chain)
    result = mt.decompose(terms, terms)[1]
    assert result["full_interface_residual"] == 0.
    assert result["full_interface_residual"] == ci.interfaces(stream)[(chain, 1)]["number_created"]


def test_trajectory_chain_typo_is_refused():
    with pytest.raises(ValueError, match="unknown sedimentation chain"):
        mt.interface_terms(_stream(), "rain")


def test_density_counterfactual_rejects_changed_geometry():
    base = mt.interface_terms(_stream())
    arm = copy.deepcopy(base)
    next(iter(arm[1].values()))["dz_lo"] *= 2
    result = mt.decompose(base, arm)[1]
    assert not result["comparable"] and "geometry differs" in result["reason"]


@pytest.mark.parametrize("missing_from", ["base", "arm"])
def test_decomposition_keeps_an_unmatched_column_visible(missing_from):
    terms = mt.interface_terms(_stream())
    base, arm = ({} if missing_from == "base" else terms,
                 {} if missing_from == "arm" else terms)
    result = mt.decompose(base, arm)[1]
    assert not result["comparable"] and "interface universes differ" in result["reason"]


def test_decomposition_does_not_silently_omit_an_unknown_arrival():
    terms = mt.interface_terms(_stream())
    next(iter(terms[1].values()))["dn_in"] = None
    with pytest.raises(ValueError, match="requires every applied arrival"):
        mt.decompose(terms, terms)


def test_cancelled_net_mismatch_keeps_its_gross_magnitude():
    row = {"drho": 1., "rho_up": 1., "dz_up": 1., "dn_out": 1.,
           "rho_lo": 2., "dz_lo": 1., "dn_in": 1.5}
    terms = {1: {(1, 1, 1, 0, 1): row,
                 (1, 1, 2, 0, 1): dict(row, dn_in=.5)}}
    result = mt.decompose(terms, terms)[1]
    assert result["measure_only"]  # net agreement, not absence of local mismatch
    assert result["number_cap_term"] == 0.
    assert result["sum_abs_number_transfer_mismatch"] == 2.


def test_equal_thickness_keeps_the_measured_one_ulp_arrival_mismatch():
    # Actual f32 conservative ice interface: inverted, call 2, column 2.
    row = {"drho": -0.029999971389770508, "rho_up": 0.8899999856948853, "dz_up": 65.,
           "dn_out": 16224.173828125, "rho_lo": 0.8600000143051147,
           "dz_lo": 65., "dn_in": 16224.1728515625}
    terms = {2: {(2, 1, 1, 1, 2): row}}
    result = mt.decompose(terms, terms)[2]
    assert result["number_cap_term"] == pytest.approx(-0.05458984465803951, abs=1e-12)
    assert result["sum_abs_number_transfer_mismatch"] == -result["number_cap_term"]
    assert not result["measure_only"]


def test_zero_baseline_report_is_defined_and_distinguishes_full_residual(monkeypatch, capsys):
    terms = mt.interface_terms(_stream())  # flat density, zero density denominator
    rows = mt.decompose(terms, terms)
    monkeypatch.setattr(mt, "analysis", lambda *a, **k: {"arms": {"as-is": rows}})
    mt.report("unused", 1)
    printed = capsys.readouterr().out
    assert "actual/base=undefined" in printed and "mismatch=" in printed and "full=" in printed
    assert "Their sum is the measured residual identically" not in printed


def test_uniform_density_offset_changes_only_weights_of_fixed_transfer_pair():
    row = {"drho": 1., "rho_up": 1., "rho_lo": 2., "dz_up": 1., "dz_lo": 1.,
           "dn_out": .75, "dn_in": .25}
    key = (1, 1, 1, 0, 1)
    base = {1: {key: row}}
    arm = {1: {key: dict(row, rho_up=2., rho_lo=3.)}}
    r = mt.decompose(base, arm)[1]
    assert r["baseline"] == -.25
    assert r["actual"] == r["metric"] == r["full_interface_residual"] == -.75
    assert r["weight_effect"] == r["residual_change"] == -.50
    assert r["trajectory"] == 0.
    assert r["density_contribution"] == .75
    assert r["number_cap_term"] == -1.5


def test_changed_arrival_is_a_transport_response_even_with_same_departure():
    row = {"drho": 1., "rho_up": 1., "rho_lo": 2., "dz_up": 1., "dz_lo": 1.,
           "dn_out": .75, "dn_in": .25}
    key = (1, 1, 1, 0, 1)
    base = {1: {key: row}}
    arm = {1: {key: dict(row, dn_in=.5)}}
    r = mt.decompose(base, arm)[1]
    assert r["weight_effect"] == 0.
    assert r["trajectory"] == r["residual_change"] == .5
    assert r["actual"] == .25


def test_full_residual_uses_original_density_not_a_rounded_difference():
    # In binary64, 1 - 2**-54 rounds to 1. Recovering rho_up from that
    # difference would turn the measured small departure into a false zero.
    row = {"rho_up": 2.**-54, "rho_lo": 1., "drho": 1. - 2.**-54,
           "dz_up": 1., "dz_lo": 1., "dn_out": 1., "dn_in": 0.}
    terms = {1: {(1, 1, 1, 0, 1): row}}
    r = mt.decompose(terms, terms)[1]
    assert r["actual"] == -2.**-54
    assert r["weight_effect"] == r["trajectory"] == 0.


def test_cli_reports_and_saves_the_same_analysis_without_rerunning(monkeypatch, tmp_path):
    seen = []
    result = {"quantity": "full_interface_residual", "arms": {}}

    def analyze(*args):
        seen.append(args)
        return result

    monkeypatch.setattr(mt, "analysis", analyze)
    path = tmp_path / "result.json"
    assert mt.main(["unused", "12", str(path)]) == 0
    assert seen == [("unused", 12)]
    assert json.loads(path.read_text()) == result
