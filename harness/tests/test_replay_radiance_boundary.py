"""Public operand replay and corruption controls; no live RTTOV dependency."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from replay_radiance_boundary import DEFAULT, replay


@pytest.fixture
def evidence():
    return json.loads(DEFAULT.read_text())


def test_measured_contractions_replay(evidence):
    result = replay(evidence)
    assert len(result['comparisons']) == 18
    assert not result['accepted_observation_cost']
    # Seven channels have zero post-cap extinction contribution at each width.
    assert sum(r['contributions'][0] == 0 for r in result['comparisons']) == 14


@pytest.mark.parametrize('fault', ['missing_layer', 'missing_file', 'nonfinite',
                                   'wrong_contribution', 'missing_endpoint', 'nonzero_temperature'])
def test_corrupt_boundary_evidence_rejected(evidence, fault):
    if fault == 'missing_layer':
        evidence['baseline_rows'].pop()
    elif fault == 'missing_file':
        del evidence['cases']['accretion-alpha0']['raw_files']['k/profiles_k.txt']
    elif fault == 'nonfinite':
        evidence['baseline_rows'][0][5] = float('nan')
    elif fault == 'wrong_contribution':
        evidence['summary']['0.03'][0]['parts'][1] *= -1
    elif fault == 'nonzero_temperature':
        evidence['retained_profile_tangents']['values']['T'][0] = 1.0
    else:
        del evidence['cases']['accretion-plus-0.1']
    with pytest.raises(AssertionError):
        replay(evidence)
