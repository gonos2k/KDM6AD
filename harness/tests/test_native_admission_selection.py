from pathlib import Path

import numpy as np
import pytest

from harness.select_native_admission import read_tile, select

ROOT = Path(__file__).resolve().parents[1] / 'evidence/native_admission_census_2026-10-02'
FILES = sorted(ROOT.glob('*.tsv'))


def test_actual_input_census_selects_before_outputs():
    result = select(FILES)
    assert len(result['records']) == 4
    assert sum(r['counts'][-1] for r in result['records'] if r['step'] == 1) == 0
    assert sum(r['counts'][-1] for r in result['records'] if r['step'] == 2) == 2
    chosen = result['selected']
    assert chosen['step'] == 2
    assert (chosen['best']['i'], chosen['best']['j']) == (142, 50)
    saved = np.load(ROOT.parent / 'native_selected_input_2026-10-02.npz')
    assert saved['state'].tobytes() == chosen['best']['state'].tobytes()
    assert saved['forcing'].tobytes() == chosen['best']['forcing'].tobytes()
    assert float(saved['xland']) == chosen['best']['xland'] == 2.


def test_missing_or_duplicate_tile_never_becomes_a_smaller_domain():
    with pytest.raises(ValueError, match='complete, unique'):
        select(FILES[:-1])
    with pytest.raises(ValueError, match='complete, unique'):
        select(FILES[:-1] + [FILES[0]])


def test_mutated_moment_pair_is_rejected(tmp_path):
    src = ROOT / 'step_0002_i_0002_j_0002.tsv'
    lines = src.read_text().splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith('STATE_IN 3 1 '))
    lines[index] = 'STATE_IN 3 1 1e-3'  # qcloud>0 while cloud number remains zero
    path = tmp_path / 'pair.tsv'; path.write_text('\n'.join(lines) + '\n')
    with pytest.raises(ValueError, match='strict pair'):
        read_tile(path)


def test_native_input_score_is_verified_from_the_saved_profile(tmp_path):
    src = ROOT / 'step_0002_i_0002_j_0002.tsv'
    lines = src.read_text().splitlines()
    parts = lines[5].split()
    assert parts[0] == 'best'
    parts[3] = '0.5'
    lines[5] = ' '.join(parts)
    path = tmp_path / 'score.tsv'; path.write_text('\n'.join(lines) + '\n')
    with pytest.raises(ValueError, match='score'):
        read_tile(path)
