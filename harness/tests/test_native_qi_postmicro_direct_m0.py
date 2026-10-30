"""False-acceptance checks for the fixed-M0 direct observation packet."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest


PACKET = Path(__file__).resolve().parents[1] / 'evidence/native_qi_postmicro_direct_m0_2026-10-30'
BASELINE = PACKET.parent / 'native_full_physics_observation_2026-10-25/native_full_physics_observation_baseline.npz'
SPEC = importlib.util.spec_from_file_location('qi_direct_arithmetic', PACKET / 'replay.py')
assert SPEC is not None and SPEC.loader is not None
REPLAY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPLAY)
DIAG_SPEC = importlib.util.spec_from_file_location('qi_direct_diagnostics', PACKET / 'observation_diagnostics.py')
assert DIAG_SPEC is not None and DIAG_SPEC.loader is not None
DIAG = importlib.util.module_from_spec(DIAG_SPEC)
DIAG_SPEC.loader.exec_module(DIAG)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_published_fixed_support_costs() -> None:
    result = REPLAY.replay(BASELINE, PACKET / 'data/control.npz',
                           _sha(PACKET / 'data/control.npz'),
                           PACKET / 'data/alpha025.npz',
                           _sha(PACKET / 'data/alpha025.npz'))
    assert result['support_cells'] == 377342
    assert result['baseline_cost'] == 11.007963317242059
    assert result['cases']['control']['cost'] == 11.008295588872157
    assert result['cases']['alpha025']['cost'] == 11.007331464977474
    assert result['alpha025_minus_control_cost'] == -0.0009641238946827002
    assert result['model_calls_in_replay'] == 0


def test_official_packet_replay_checks_chunk_receipts() -> None:
    result = subprocess.run(
        [sys.executable, str(PACKET / 'packet_replay.py')],
        check=True, capture_output=True, text=True,
    )
    row = json.loads(result.stdout)
    assert row['status'] == 'PACKET_REPLAY_PASSED'
    assert row['chunk_artifacts'] == 778
    assert row['support_cells'] == 377342
    assert row['model_calls_in_replay'] == 0


def test_false_direct_validity_on_m0_is_rejected(tmp_path: Path) -> None:
    with np.load(PACKET / 'data/alpha025.npz', allow_pickle=False) as archive:
        data = {name: np.array(archive[name], copy=True) for name in archive.files}
    row, channel = np.argwhere(data['m0_mask'])[0]
    data['actual_valid_mask'][row, channel] = False
    changed = tmp_path / 'invalid.npz'
    np.savez_compressed(changed, **data)
    with pytest.raises(ValueError, match='actual validity missing on M0'):
        REPLAY.replay(BASELINE, PACKET / 'data/control.npz',
                      _sha(PACKET / 'data/control.npz'), changed, _sha(changed))


def test_wrong_bt_precision_is_rejected(tmp_path: Path) -> None:
    with np.load(PACKET / 'data/alpha025.npz', allow_pickle=False) as archive:
        data = {name: np.array(archive[name], copy=True) for name in archive.files}
    data['bt_k'] = data['bt_k'].astype(np.float32)
    changed = tmp_path / 'f32.npz'
    np.savez_compressed(changed, **data)
    with pytest.raises(ValueError, match='BT contract mismatch'):
        REPLAY.replay(BASELINE, PACKET / 'data/control.npz',
                      _sha(PACKET / 'data/control.npz'), changed, _sha(changed))


def test_published_bt_diagnostics_keep_comparison_baselines_distinct() -> None:
    producer = json.loads((PACKET / 'data/producer_receipts.json').read_text())
    result = DIAG.build(producer['packed_sha256'])
    expected = json.loads((PACKET / 'observation_diagnostics.json').read_text())
    assert result == expected
    assert result['cases']['control']['changed_M0_profiles_vs_original_control'] == 11
    assert result['cases']['alpha025']['changed_M0_profiles_vs_original_control'] == 48257
    ice = result['targets']['ice_boundary']
    assert ice['original_control']['IR105_sim_BT_K'] == ice['pilot_alpha025']['IR105_sim_BT_K']
    qnc = result['targets']['qnc_guard']
    assert qnc['original_control']['IR105_sim_BT_K'] != qnc['pilot_control']['IR105_sim_BT_K']
