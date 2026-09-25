"""Coarse means, stochastic averages and analysis corrections carry distinct meaning."""

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from resolution_stochastic_contract import (  # noqa: E402
    ExternalCorrection, MomentClaim, audit_coarse_radius_moment,
    check_external_correction, check_realization_exchange,
    require_carried_third_moment,
)


def _radii():
    return np.array([1., 3.]), np.array([.5, .5])


IDS = ("member-0", "member-1")


def test_average_radius_loses_the_cubic_moment_without_retained_data():
    radii, weights = _radii()
    result = audit_coarse_radius_moment(radii, weights, MomentClaim(2., None, "none"))
    assert result.fine_mean_radius_um == 2.
    assert result.cube_of_mean_um3 == 8.
    assert result.fine_third_moment_um3 == 14.
    assert result.lost_third_moment_um3 == 6.
    assert not result.third_moment_carried
    with pytest.raises(ValueError, match="needs retained moment"):
        require_carried_third_moment(radii, weights, MomentClaim(2., None, "none"))


def test_retained_or_named_closure_moment_must_match_fine_distribution():
    radii, weights = _radii()
    for claim in (MomentClaim(2., 14., "retained"),
                  MomentClaim(2., 14., "declared_closure", "closure-v1")):
        result = audit_coarse_radius_moment(radii, weights, claim)
        assert require_carried_third_moment(radii, weights, claim) == result
    with pytest.raises(ValueError, match="does not represent"):
        audit_coarse_radius_moment(radii, weights, MomentClaim(2., 8., "retained"))
    with pytest.raises(ValueError, match="named closure"):
        audit_coarse_radius_moment(radii, weights,
                                   MomentClaim(2., 14., "declared_closure"))


def test_weighted_distribution_is_not_a_hardcoded_two_radius_example():
    radii, _ = _radii()
    weights = np.array([.25, .75])
    result = audit_coarse_radius_moment(
        radii, weights, MomentClaim(2.5, 20.5, "retained"))
    assert result.cube_of_mean_um3 == 15.625
    assert result.fine_third_moment_um3 == 20.5
    with pytest.raises(ValueError, match="sum to one"):
        audit_coarse_radius_moment(radii, np.array([.25, .5]),
                                   MomentClaim(2.5, None, "none"))


def test_ensemble_mean_balance_cannot_hide_unpaired_realizations():
    outgoing = np.array([1., -1.])
    incoming = np.array([0., 0.])
    assert outgoing.mean() == incoming.mean() == 0.
    with pytest.raises(ValueError, match="unpaired"):
        check_realization_exchange(outgoing, incoming, expected_ids=IDS,
                                   outgoing_ids=IDS, incoming_ids=IDS)
    result = check_realization_exchange(outgoing, outgoing.copy(),
                                        expected_ids=IDS, outgoing_ids=IDS,
                                        incoming_ids=IDS)
    assert result.realizations == 2
    assert result.mean_outgoing == result.mean_incoming == 0.
    with pytest.raises(ValueError, match="identities"):
        check_realization_exchange(outgoing, outgoing.copy(), expected_ids=IDS,
                                   outgoing_ids=IDS, incoming_ids=IDS[::-1])


def test_analysis_and_ml_corrections_are_explicit_external_ledger_terms():
    before = np.array([2., 3.])
    after = np.array([3., 3.])
    measure = np.array([2., 1.])
    for kind in ("analysis", "ml"):
        assert check_external_correction(
            before, after, measure, ExternalCorrection(kind, "kg", 2.)) == 2.
    with pytest.raises(ValueError, match="does not explain"):
        check_external_correction(before, after, measure,
                                  ExternalCorrection("analysis", "kg", 0.))
    with pytest.raises(ValueError, match="declare analysis or ML"):
        check_external_correction(before, after, measure,
                                  ExternalCorrection("physics", "kg", 2.))


def test_invalid_radii_realizations_and_corrections_are_rejected():
    radii, weights = _radii()
    with pytest.raises(ValueError, match="unmasked float64"):
        audit_coarse_radius_moment(radii.astype(np.float32), weights,
                                   MomentClaim(2., None, "none"))
    with pytest.raises(ValueError, match="positive radii"):
        audit_coarse_radius_moment(np.array([0., 3.]), weights,
                                   MomentClaim(1.5, None, "none"))
    with pytest.raises(ValueError, match="underflowed"):
        audit_coarse_radius_moment(np.array([1e-200, 1e-200]), weights,
                                   MomentClaim(1e-200, 0., "retained"))
    with pytest.raises(ValueError, match="overflowed"):
        audit_coarse_radius_moment(np.array([1e200, 1e200]), weights,
                                   MomentClaim(1e200, None, "none"))
    with pytest.raises(ValueError, match="realization sets differ"):
        check_realization_exchange(np.array([1., 2.]), np.array([1.]),
                                   expected_ids=IDS, outgoing_ids=IDS,
                                   incoming_ids=IDS[:1])
    with pytest.raises(ValueError, match="finite real"):
        check_external_correction(np.array([0.]), np.array([0.]), np.array([1.]),
                                  ExternalCorrection("ml", "kg", math.nan))
