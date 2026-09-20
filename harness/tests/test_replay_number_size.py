"""Conditional moment identities and corruption controls, no live RTTOV."""
import json
import math
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from replay_number_size import DEFAULT, cloud_size, ideal_dry_radius, replay


@pytest.fixture
def evidence():
    return json.loads(DEFAULT.read_text())


def test_measured_size_mapping(evidence):
    result = replay(evidence)
    assert len(result['layers']) == 39
    assert not result['physical_number_contract_resolved']
    assert not result['accepted_observation_cost']


def test_density_representation_invariance():
    # Convert both moments by the same density: C/N is unchanged.
    q, n = 1e-4, 1e8
    reference = ideal_dry_radius(q, n)
    for density in (0.25, 0.5, 1.25):
        assert math.isclose(ideal_dry_radius(density*q, density*n), reference,
                            rel_tol=2e-15)
    # Eight times the particles at fixed water mass halves the ideal radius.
    assert math.isclose(ideal_dry_radius(q, 8*n), reference/2, rel_tol=2e-15)


def test_limits_can_hide_number_changes():
    assert cloud_size(0, 1e8, 1, 100)['diameter_um'] == 5.02
    first = cloud_size(1e-10, 1e8, 1, 100)
    second = cloud_size(1e-10, 2e8, 1, 100)
    assert first['raw_radius_um'] != second['raw_radius_um']
    assert first['diameter_um'] == second['diameter_um'] == 5.02


@pytest.mark.parametrize('fault', ['missing_layer', 'wrong_density', 'nan_number',
                                 'wrong_size', 'swapped_pressure', 'unit_claim',
                                 'missing_input', 'wrong_content'])
def test_corrupt_evidence_rejected(evidence, fault):
    if fault == 'missing_layer':
        evidence['rows'].pop()
    elif fault == 'wrong_density':
        evidence['rows'][24]['rho_d'] *= 2
    elif fault == 'nan_number':
        evidence['rows'][24]['nc'] = float('nan')
    elif fault == 'wrong_size':
        evidence['rows'][24]['diagnostics']['legacy']['diameter_um'] *= 2
    elif fault == 'swapped_pressure':
        evidence['rows'][0]['pressure_hpa'], evidence['rows'][1]['pressure_hpa'] = (
            evidence['rows'][1]['pressure_hpa'], evidence['rows'][0]['pressure_hpa'])
    elif fault == 'missing_input':
        del evidence['retained_input']['P_HALF']
    elif fault == 'wrong_content':
        evidence['retained_input']['HYDRO6']['tokens'][24] = '0.0'
    else:
        evidence['physical_number_contract_resolved'] = True
    with pytest.raises(AssertionError):
        replay(evidence)
