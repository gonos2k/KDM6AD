#!/usr/bin/env python3
"""Decompose the saved PR #483 direct costs on the original M0; no model calls.

All contributions use the common domain cell normalizer. Gross increases and
reductions are signed and are classified independently at cell/profile grain.
The official chunked objective is replayed separately from regrouped deltas.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / 'harness/evidence/native_qi_postmicro_direct_m0_2026-10-30'
BASE = ROOT / 'harness/evidence/native_full_physics_observation_2026-10-25/native_full_physics_observation_baseline.npz'
HASHES = {
    'baseline': 'c919f13c3ceb4defec42e43e0b60ad71d22d10f57a9454f6f880f98ec1bf9144',
    'control': '055e0222eda193bb8942f3890684d5f2389ec578eb0450330e05adce38ad074e',
    'alpha025': '1d8bbe792f4efbe087e5cb139f40151997241ad796a96aeef3af91ddddacaad9',
}
PUBLISHED = {'baseline': 11.007963317242059, 'control': 11.008295588872157,
             'alpha025': 11.007331464977474}
N, WIDTH, HEIGHT, Z = 65988, 234, 282, 377342


def fsum(values: np.ndarray) -> float:
    return math.fsum(float(v) for v in np.ravel(values))


def gross(values: np.ndarray, normalizer: int) -> dict:
    return {'increase': fsum(values[values > 0]) / normalizer,
            'decrease': fsum(values[values < 0]) / normalizer,
            'positive_count': int(np.count_nonzero(values > 0)),
            'negative_count': int(np.count_nonzero(values < 0)),
            'zero_count': int(np.count_nonzero(values == 0))}


def geometry(width: int, height: int) -> dict[str, np.ndarray]:
    idx = np.arange(width * height)
    i, j = idx % width + 1, idx // width + 1
    edge_i, edge_j = (i == 1) | (i == width), (j == 1) | (j == height)
    return {'corners': edge_i & edge_j, 'west': (i == 1) & ~edge_j,
            'east': (i == width) & ~edge_j, 'south': (j == 1) & ~edge_i,
            'north': (j == height) & ~edge_i, 'interior': ~edge_i & ~edge_j}


def huber(bt: np.ndarray, obs: np.ndarray, mask: np.ndarray) -> np.ndarray:
    # Calculate only supported cells: outside support may contain placeholders.
    result = np.zeros(bt.shape, dtype=np.float64)
    residual = bt[mask] - obs[mask]
    magnitude = np.abs(residual)
    result[mask] = np.where(magnitude <= 1, 0.5 * residual * residual, magnitude - 0.5)
    return result


def comparison(x: np.ndarray, y: np.ndarray, lx: np.ndarray, ly: np.ndarray,
               mask: np.ndarray, costs: tuple[float, float], top: int,
               width: int = WIDTH, height: int = HEIGHT) -> dict:
    z = int(mask.sum())
    delta = lx - ly
    profile = np.array([fsum(row) for row in delta])
    bits = (x.view(np.uint64) != y.view(np.uint64)) & mask
    changed = bits.any(axis=1)
    bt_change = np.zeros_like(x)
    bt_change[mask] = np.abs(x[mask] - y[mask])
    buckets = {}
    for name, sel in geometry(width, height).items():
        buckets[name] = {'supported_profiles': int(np.count_nonzero(mask[sel].any(axis=1))),
                         'supported_cells': int(mask[sel].sum()),
                         'changed_profiles': int(np.count_nonzero(changed & sel)),
                         'changed_cells': int(bits[sel].sum()),
                         'cost_delta': fsum(delta[sel]) / z,
                         'cellwise_gross': gross(delta[sel][mask[sel]], z),
                         'profilewise_gross': gross(profile[sel & mask.any(axis=1)], z)}
    channel = {str(k + 10): fsum(delta[:, k]) / z for k in range(mask.shape[1])}
    ordered = sorted(np.flatnonzero(changed), key=lambda row: (-abs(profile[row]), int(row)))[:top]
    profiles = [{'flat_index': int(row), 'i': int(row % width + 1),
                 'j': int(row // width + 1), 'cost_delta': float(profile[row] / z),
                 'loss_delta_numerator': float(profile[row]),
                 'channel_loss_delta_numerator': [float(v) for v in delta[row]],
                 'channel_bt_delta_K': [float(x[row, k] - y[row, k]) if mask[row, k] else None
                                        for k in range(mask.shape[1])],
                 'supported_channels': [int(k + 10) for k in np.flatnonzero(mask[row])]}
                for row in ordered]
    direct = fsum(delta) / z
    aggregate = costs[0] - costs[1]
    return {'changed_profiles': int(changed.sum()), 'changed_cells': int(bits.sum()),
            'strict_abs_bt_thresholds_K': {
                str(threshold): {'cells': int(np.count_nonzero(mask & (bt_change > threshold))),
                                 'profiles': int(np.count_nonzero((mask & (bt_change > threshold)).any(axis=1)))}
                for threshold in (0.01, 0.1, 1.0)},
            'cellwise_gross': gross(delta[mask], z),
            'profilewise_gross': gross(profile[mask.any(axis=1)], z),
            'channel_cost_delta': channel, 'geometry': buckets,
            'top_changed_profiles_by_abs_cost_delta': profiles,
            'regrouped_cell_delta': direct,
            'official_aggregate_cost_subtraction': aggregate,
            'roundoff_gap_regrouped_minus_aggregate': direct - aggregate,
            'geometry_sum_minus_regrouped': math.fsum(v['cost_delta'] for v in buckets.values()) - direct,
            'channel_sum_minus_regrouped': math.fsum(channel.values()) - direct}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--top', type=int, default=20, help='number of changed profiles per comparison')
    args = parser.parse_args()
    if args.top < 0:
        parser.error('--top must be nonnegative')
    spec = importlib.util.spec_from_file_location('qi_m0_replay', PACKET / 'replay.py')
    if spec is None or spec.loader is None:
        raise RuntimeError('cannot load packet arithmetic replay')
    replay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(replay)
    paths = {'control': PACKET / 'data/control.npz', 'alpha025': PACKET / 'data/alpha025.npz'}
    checked = replay.replay(BASE, paths['control'], HASHES['control'], paths['alpha025'], HASHES['alpha025'])
    arrays = {key: replay.read_npz(path, HASHES[key]) for key, path in [('baseline', BASE), *paths.items()]}
    b = arrays['baseline']
    mask, obs = b['m0_mask'], b['obs_bt_k']
    if mask.shape != (N, 7) or obs.dtype != np.float64 or b['baseline_bt_kma_v3_0'].dtype != np.float64:
        raise ValueError('baseline dtype or shape differs')
    if not np.all(mask == mask[:, :1]) or int(mask.any(axis=1).sum()) != 53906:
        raise ValueError('baseline profile support differs')
    bt = {'baseline': b['baseline_bt_kma_v3_0'],
          'control': arrays['control']['bt_k'], 'alpha025': arrays['alpha025']['bt_k']}
    costs = {'baseline': checked['baseline_cost'],
             **{name: checked['cases'][name]['cost'] for name in paths}}
    if costs != PUBLISHED:
        raise ValueError('published aggregate costs differ')
    losses = {name: huber(value, obs, mask) for name, value in bt.items()}
    pairs = [('control', 'baseline'), ('alpha025', 'baseline'), ('alpha025', 'control')]
    out = {'schema': 'kdm6.qi_m0_cost_decomposition.v1', 'input_sha256': HASHES,
           'support': {'profiles': 53906, 'cells': Z, 'grid_width': WIDTH, 'grid_height': HEIGHT},
           'costs': costs, 'comparisons': {
               f'{a}_minus_{b}': comparison(bt[a], bt[b], losses[a], losses[b], mask,
                                             (costs[a], costs[b]), args.top)
               for a, b in pairs},
           'method': 'f64 Huber delta=1, bias=0, scale=1; signed differences divided by original M0 cell count; geometry disjoint',
           'scope': 'saved direct arrays, no model calls; no causal or physical budget attribution'}
    print(json.dumps(out, sort_keys=True, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
