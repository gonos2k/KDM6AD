#!/usr/bin/env python3
"""Read-only arithmetic replay of completed direct-RTTOV packed arrays.

No model, host, RTTOV, or optimizer is invoked. See README for the proposed
packed schema and provenance requirements; this does not certify the producer.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path

import numpy as np

N = 65988
CHANNELS = np.arange(10, 17)
Z = 377342
BASELINE_SHA = 'c919f13c3ceb4defec42e43e0b60ad71d22d10f57a9454f6f880f98ec1bf9144'
BASELINE_COST = 11.007963317242059
BASELINE_NUM = 4153766.894054753


def read_npz(path: Path, expected_sha: str) -> dict[str, np.ndarray]:
    if len(expected_sha) != 64 or any(c not in '0123456789abcdef' for c in expected_sha):
        raise ValueError('expected SHA-256 must be 64 lowercase hex characters')
    raw = path.read_bytes()
    actual = sha256(raw).hexdigest()
    if actual != expected_sha:
        raise ValueError(f'{path}: SHA-256 mismatch: {actual}')
    with np.load(BytesIO(raw), allow_pickle=False) as data:
        return {name: np.array(data[name], copy=True) for name in data.files}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def coordinates(data: dict[str, np.ndarray]) -> None:
    for name, dtype, shape in (
        ('flat_index', np.int32, (N,)),
        ('channel_id', np.int16, (7,)),
        ('chunk_index', np.uint8, (N,)),
        ('chunk_local_row', np.uint16, (N,)),
    ):
        require(data[name].dtype == dtype and data[name].shape == shape,
                f'{name} dtype/shape mismatch')
    require(np.array_equal(data['flat_index'], np.arange(N)), 'flat coverage/order mismatch')
    require(np.array_equal(data['channel_id'], CHANNELS), 'channel order mismatch')
    require(np.array_equal(data['chunk_index'], np.arange(N) // 512), 'B512 chunk coverage mismatch')
    require(np.array_equal(data['chunk_local_row'], np.arange(N) % 512), 'B512 local row mismatch')


def objective(bt: np.ndarray, obs: np.ndarray, mask: np.ndarray) -> tuple[float, float]:
    chunks = []
    for chunk in range(129):
        start, stop = chunk * 512, min((chunk + 1) * 512, N)
        channels = []
        for channel in range(7):
            terms = []
            for row in range(start, stop):
                if mask[row, channel]:
                    r = float(bt[row, channel]) - float(obs[row, channel])
                    terms.append(0.5 * r * r if abs(r) <= 1.0 else abs(r) - 0.5)
            channels.append(math.fsum(terms))
        chunks.append(math.fsum(channels))
    numerator = math.fsum(chunks)
    return numerator, numerator / Z


def replay(baseline_path: Path, control_path: Path, control_sha: str,
           alpha_path: Path, alpha_sha: str) -> dict:
    base = read_npz(baseline_path, BASELINE_SHA)
    coordinates(base)
    obs, mask, bt = base['obs_bt_k'], base['m0_mask'], base['baseline_bt_kma_v3_0']
    require(obs.shape == mask.shape == bt.shape == (N, 7), 'baseline shape mismatch')
    require(mask.dtype == np.bool_, 'baseline M0 must be boolean')
    require(int(mask.sum()) == Z, 'baseline M0 count mismatch')
    require(np.isfinite(obs[mask]).all() and np.isfinite(bt[mask]).all(), 'baseline supported values nonfinite')
    numerator, cost = objective(bt, obs, mask)
    require(numerator == BASELINE_NUM and cost == BASELINE_COST, 'baseline objective mismatch')
    cases = {}
    for name, path, digest in [('control', control_path, control_sha), ('alpha025', alpha_path, alpha_sha)]:
        data = read_npz(path, digest)
        coordinates(data)
        # Repeat the original observation and mask in the packed output so a
        # mismatched pairing cannot be hidden by applying M0 after the fact.
        require(data['obs_bt_k'].dtype == obs.dtype and data['obs_bt_k'].shape == obs.shape
                and data['obs_bt_k'].tobytes() == obs.tobytes(), f'{name}: observation bytes differ')
        require(data['m0_mask'].dtype == mask.dtype and np.array_equal(data['m0_mask'], mask), f'{name}: M0 differs')
        trial_bt, quality, valid = data['bt_k'], data['model_quality'], data['profile_valid']
        actual_valid = data['actual_valid_mask']
        require(trial_bt.shape == (N, 7) and trial_bt.dtype == np.dtype('float64'), f'{name}: BT contract mismatch')
        require(quality.shape == (N, 7) and quality.dtype == np.dtype('int32'), f'{name}: quality contract mismatch')
        require(valid.shape == (N,) and valid.dtype == np.bool_, f'{name}: profile_valid contract mismatch')
        require(actual_valid.shape == (N, 7) and actual_valid.dtype == np.bool_, f'{name}: actual_valid_mask contract mismatch')
        require(np.all(valid[:, None] | ~mask), f'{name}: invalid profile on M0')
        require(np.all(actual_valid[mask]), f'{name}: actual validity missing on M0')
        require(np.all(quality[mask] == 0), f'{name}: nonzero quality on M0')
        require(np.isfinite(trial_bt[mask]).all(), f'{name}: nonfinite BT on M0')
        trial_num, trial_cost = objective(trial_bt, obs, mask)
        cases[name] = {'sha256': digest, 'huber_numerator': trial_num, 'cost': trial_cost,
                       'cost_minus_original_baseline': trial_cost - cost}
    return {'status': 'OFFLINE_REPLAY_PASSED', 'baseline_sha256': BASELINE_SHA,
            'support_cells': Z, 'blocks': 129, 'baseline_huber_numerator': numerator,
            'baseline_cost': cost, 'cases': cases,
            'alpha025_minus_control_cost': cases['alpha025']['cost'] - cases['control']['cost'],
            'model_calls_in_replay': 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--control', required=True, type=Path)
    parser.add_argument('--control-sha256', required=True)
    parser.add_argument('--alpha025', required=True, type=Path)
    parser.add_argument('--alpha025-sha256', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(replay(args.baseline, args.control, args.control_sha256,
                                args.alpha025, args.alpha025_sha256), sort_keys=True, allow_nan=False))
    except Exception as exc:
        print(json.dumps({'status': 'OFFLINE_REPLAY_FAILED', 'error': f'{type(exc).__name__}: {exc}'}))
        raise


if __name__ == '__main__':
    main()
