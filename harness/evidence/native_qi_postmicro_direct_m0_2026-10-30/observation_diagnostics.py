"""Describe fixed-M0 BT changes without attributing them to a process."""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'native_full_physics_observation_2026-10-25/native_full_physics_observation_baseline.npz'
BASE_SHA = 'c919f13c3ceb4defec42e43e0b60ad71d22d10f57a9454f6f880f98ec1bf9144'
TARGETS = {'ice_boundary': (1, 168), 'qnc_guard': (221, 63)}
IR105_CHANNEL_INDEX = 3


def _read(path: Path, expected: str) -> dict[str, np.ndarray]:
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != expected:
        raise ValueError(f'observation input hash differs: {path.name}')
    with np.load(BytesIO(raw), allow_pickle=False) as archive:
        return {name: np.array(archive[name], copy=True) for name in archive.files}


def build(packed_hashes: dict[str, str]) -> dict:
    if set(packed_hashes) != {'control', 'alpha025'}:
        raise ValueError('case inventory differs')
    baseline = _read(BASE, BASE_SHA)
    mask = baseline['m0_mask']
    obs = baseline['obs_bt_k']
    original = baseline['baseline_bt_kma_v3_0']
    if (mask.shape != obs.shape or obs.shape != original.shape or
            mask.shape != (65988, 7) or mask.dtype != np.bool_ or
            obs.dtype != original.dtype or obs.dtype != np.float64 or
            int(mask.sum()) != 377342):
        raise ValueError('original observation/M0 schema differs')
    values = {'original_control': original}
    cases = {}
    for case in ('control', 'alpha025'):
        data = _read(HERE / 'data' / f'{case}.npz', packed_hashes[case])
        bt = data['bt_k']
        if bt.shape != original.shape or bt.dtype != np.float64:
            raise ValueError(f'{case} BT dtype/shape differs')
        values[f'pilot_{case}'] = bt
        different = (bt.view(np.uint64) != original.view(np.uint64)) & mask
        cases[case] = {
            'changed_M0_profiles_vs_original_control': int(np.count_nonzero(different.any(axis=1))),
            'changed_M0_channel_cells_vs_original_control': int(np.count_nonzero(different)),
            'max_abs_supported_BT_change_K_vs_original_control': float(np.max(np.abs(bt[mask] - original[mask]))),
        }
    compared = (values['pilot_alpha025'].view(np.uint64) !=
                values['pilot_control'].view(np.uint64)) & mask
    targets = {}
    for name, (i, j) in TARGETS.items():
        index = (j - 1) * 234 + i - 1
        if not mask[index].all() or baseline['flat_index'][index] != index:
            raise ValueError(f'{name} is not the full seven-channel M0 target')
        observation = float(obs[index, IR105_CHANNEL_INDEX])
        target = {
            'native_ij_1based': [i, j],
            'flat_index_zero_based': index,
            'channel_id': int(baseline['channel_id'][IR105_CHANNEL_INDEX]),
            'IR105_obs_BT_K': observation,
        }
        for key, bt in values.items():
            simulated = float(bt[index, IR105_CHANNEL_INDEX])
            target[key] = {'IR105_sim_BT_K': simulated,
                           'IR105_sim_minus_obs_K': simulated - observation}
        targets[name] = target
    return {
        'schema': 'kdm6.native_qi_postmicro_direct_observation_diagnostics.v1',
        'baseline_sha256': BASE_SHA,
        'packed_sha256': dict(packed_hashes),
        'original_M0_profiles': 53906,
        'original_M0_channel_cells': 377342,
        'cases': cases,
        'alpha_minus_pilot_control_changed_M0_profiles': int(np.count_nonzero(compared.any(axis=1))),
        'alpha_minus_pilot_control_changed_M0_channel_cells': int(np.count_nonzero(compared)),
        'targets': targets,
        'model_calls': {'host': 0, 'KDM6': 0, 'RTTOV': 0, 'optimizer': 0},
        'scope': 'saved direct BT comparison on original fixed support; no process attribution',
    }


def main() -> None:
    producer = json.loads((HERE / 'data/producer_receipts.json').read_text())
    result = build(producer['packed_sha256'])
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
