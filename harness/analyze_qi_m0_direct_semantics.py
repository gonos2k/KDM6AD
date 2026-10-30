#!/usr/bin/env python3
"""Validate saved direct-call receipt semantics and historical chunk losses offline.

Hash pins bind the reviewed public packet, not the unavailable private execution.
This script reads the baseline, two packed arrays and the saved chunk archive only.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import tarfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / 'harness/evidence/native_qi_postmicro_direct_m0_2026-10-30'
BASE = ROOT / 'harness/evidence/native_full_physics_observation_2026-10-25/native_full_physics_observation_baseline.npz'
PINS = {
    'baseline': 'c919f13c3ceb4defec42e43e0b60ad71d22d10f57a9454f6f880f98ec1bf9144',
    'archive': '736779e7084bccc0a4348eb62cbd0eacf753173a48146a37657e92e65f88df77',
    'control': '055e0222eda193bb8942f3890684d5f2389ec578eb0450330e05adce38ad074e',
    'alpha025': '1d8bbe792f4efbe087e5cb139f40151997241ad796a96aeef3af91ddddacaad9',
}
N, Z = 65988, 377342


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def checked(path, pin):
    raw = path.read_bytes()
    require(digest(raw) == PINS[pin], f'{pin}: SHA-256 mismatch')
    return raw


def arrays(raw):
    with np.load(io.BytesIO(raw), allow_pickle=False) as z:
        return {k: np.array(z[k], copy=True) for k in z.files}


def validate_receipt(receipt, capture, start, stop):
    """Check identities actually claimed by the direct-call receipt."""
    rr = receipt['rttov_receipt']
    indices = capture['flat_indices']
    profile = capture['profile_valid']
    require(indices.dtype == np.int32 and np.array_equal(indices, np.arange(start, stop, dtype=np.int32)), 'capture index mismatch')
    require(profile.dtype == np.bool_ and profile.shape == (stop - start,), 'profile schema mismatch')
    expected = indices[profile].tolist()
    ids = rr['source_flat_indices']
    require(isinstance(ids, list) and all(type(x) is int for x in ids), 'source index type mismatch')
    require(ids == expected and len(ids) == len(set(ids)) and all(start <= x < stop for x in ids), 'source index identity mismatch')
    require(type(rr['nprofiles']) is int and rr['nprofiles'] == len(ids), 'profile count mismatch')
    require(rr['channels'] == list(range(10, 17)) and rr['bt_coordinate'] == 'kma_v3_0', 'channel or coordinate mismatch')
    require(rr['per_profile_geometry_surface'] is True, 'geometry/surface mode mismatch')
    flags = rr['driver_flags']
    require(flags['case_do_direct'] is True and flags['case_do_k'] is False, 'case driver flags mismatch')
    require(rr['K_recovered'] == 0 and rr['direct_calls'] == 1 and rr['K_calls'] == 0 and rr['mode'] == 'direct', 'direct receipt counts mismatch')
    require(receipt['direct_calls'] == 1 and receipt['K_calls'] == 0, 'result counts mismatch')


def chunk_loss(bt, obs, mask):
    channels = []
    for c in range(7):
        terms = []
        for row in range(len(bt)):
            if mask[row, c]:
                r = float(bt[row, c]) - float(obs[row, c])
                terms.append(0.5 * r * r if abs(r) <= 1.0 else abs(r) - 0.5)
        channels.append(math.fsum(terms))
    return math.fsum(channels)


def run():
    base = arrays(checked(BASE, 'baseline'))
    obs, mask = base['obs_bt_k'], base['m0_mask']
    require(obs.shape == mask.shape == (N, 7) and obs.dtype == np.float64 and mask.dtype == np.bool_ and int(mask.sum()) == Z, 'baseline schema mismatch')
    require(np.array_equal(base['flat_index'], np.arange(N)) and np.array_equal(base['channel_id'], np.arange(10, 17)), 'baseline order mismatch')
    archive_raw = checked(PACKET / 'data/chunk_artifacts.tar.gz', 'archive')
    results = {}
    with tarfile.open(fileobj=io.BytesIO(archive_raw), mode='r:gz') as tar:
        names = {f'{case}/{x}' for case in ('control', 'alpha025') for x in ('binding.json', 'summary.json')}
        names |= {f'{case}/chunks/chunk_{i:03d}/{x}' for case in ('control', 'alpha025') for i in range(129) for x in ('attempt.json', 'result.json', 'result.npz')}
        members = tar.getmembers()
        require(len(members) == len(names) == 778 and {m.name for m in members} == names, 'archive inventory mismatch')
        require(all(m.isfile() and 0 <= m.size <= 2_000_000 for m in members) and sum(m.size for m in members) <= 100_000_000, 'archive bounds mismatch')
        content = {m.name: tar.extractfile(m).read() for m in members}
    for case in ('control', 'alpha025'):
        packed = arrays(checked(PACKET / f'data/{case}.npz', case))
        require(packed['obs_bt_k'].dtype == obs.dtype and packed['obs_bt_k'].tobytes() == obs.tobytes() and np.array_equal(packed['m0_mask'], mask), f'{case}: fixed observations differ')
        binding_raw = content[f'{case}/binding.json']
        binding = json.loads(binding_raw)
        summary = json.loads(content[f'{case}/summary.json'])
        binding_hash = digest(binding_raw)
        require(binding['case'] == case and binding['chunks'] == 129 and binding['support_cells'] == Z and binding['with_k'] is False and binding['host_steps'] == binding['KDM_calls'] == 0, f'{case}: binding mismatch')
        require(summary['binding_sha256'] == binding_hash and summary['status'] == 'DIRECT_FIXED_M0_COMPLETE' and summary['support_cells'] == Z and summary['completed_chunk_receipts'] == summary['direct_calls_recorded_in_completed_receipts'] == 129 and summary['K_calls'] == 0 and summary['huber_delta_K'] == summary['sigma_K'] == 1.0 and summary['bias_K'] == 0.0, f'{case}: summary mismatch')
        sums = []
        for i in range(129):
            start, stop = i * 512, min((i + 1) * 512, N)
            prefix = f'{case}/chunks/chunk_{i:03d}/'
            attempt = json.loads(content[prefix + 'attempt.json'])
            result = json.loads(content[prefix + 'result.json'])
            capture_raw = content[prefix + 'result.npz']
            capture = arrays(capture_raw)
            require(attempt['chunk'] == result['chunk'] == i and attempt['flat_range'] == [start, stop] and attempt['with_k'] is False and attempt['binding_sha256'] == result['binding_sha256'] == binding_hash and result['capture_sha256'] == digest(capture_raw), f'{case}/{i}: hash or attempt mismatch')
            validate_receipt(result, capture, start, stop)
            for src, dst in (('bt', 'bt_k'), ('quality', 'model_quality'), ('valid', 'actual_valid_mask'), ('profile_valid', 'profile_valid')):
                a, b = capture[src], packed[dst][start:stop]
                require(a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes(), f'{case}/{i}: {src} differs from packed')
            bt, quality, valid, profile = (capture[x] for x in ('bt', 'quality', 'valid', 'profile_valid'))
            shape = (stop - start, 7)
            require(bt.shape == quality.shape == valid.shape == shape and bt.dtype == np.float64 and quality.dtype == np.int32 and valid.dtype == np.bool_, f'{case}/{i}: capture schema mismatch')
            m = mask[start:stop]
            require(np.all(valid[m]) and np.all(quality[m] == 0) and np.all(profile[:, None] | ~m) and np.isfinite(bt[m]).all() and np.isfinite(obs[start:stop][m]).all(), f'{case}/{i}: supported data invalid')
            sums.append(chunk_loss(bt, obs[start:stop], m))
        numerator = math.fsum(sums)
        require(sums == summary['chunk_numerators'] and numerator == summary['numerator'] and numerator / Z == summary['cost'], f'{case}: historical objective mismatch')
        results[case] = {'chunk_numerators_verified': len(sums), 'numerator': numerator, 'cost': numerator / Z}
    return {'status': 'PASSED', 'cases': results, 'receipts_verified': 258, 'support_cells': Z, 'model_calls': 0, 'scope': 'offline receipt semantics and saved arithmetic; private execution not independently verified'}


if __name__ == '__main__':
    print(json.dumps(run(), sort_keys=True, allow_nan=False))
