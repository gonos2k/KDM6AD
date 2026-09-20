"""Reject incomplete noninterference evidence using the retained measured case."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from replay_extinction_layers import DEFAULT, replay


@pytest.fixture
def evidence():
    return json.loads(DEFAULT.read_text())


def test_retained_evidence_replays(evidence):
    result = replay(evidence)
    assert result['endpoint_masks_equal']
    assert not result['accepted_observation_cost']


@pytest.mark.parametrize('endpoint', range(5))
@pytest.mark.parametrize('missing', ['all', 'k/profiles_k.txt'])
def test_missing_endpoint_files_rejected(evidence, endpoint, missing):
    cases = list(evidence['build_and_noninterference']['manifest']['cases'].values())
    files = cases[endpoint]['raw_files']
    if missing == 'all':
        files.clear()
    else:
        del files[missing]
    with pytest.raises(AssertionError, match='Incomplete raw_files'):
        replay(evidence)


@pytest.mark.parametrize('missing', ['all', 'k/profiles_k.txt'])
def test_incomplete_declared_file_set_rejected(evidence, missing):
    files = evidence['build_and_noninterference']['compared_files']
    if missing == 'all':
        files.clear()
    else:
        files.remove(missing)
    with pytest.raises(AssertionError, match='Incomplete compared_files'):
        replay(evidence)
