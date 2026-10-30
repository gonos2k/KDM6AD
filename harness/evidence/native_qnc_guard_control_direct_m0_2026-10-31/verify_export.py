#!/usr/bin/env python3
"""Verify completed QNC-guard Control receipts and optionally export them offline.

Run only after the producer has stopped and finalized summary.json. No model calls.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import tarfile
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PREVIOUS = REPO / 'harness/evidence/native_qi_postmicro_direct_m0_2026-10-30'
BASE = REPO / 'harness/evidence/native_full_physics_observation_2026-10-25/native_full_physics_observation_baseline.npz'
RUNNER_SHA = 'bdd80f465509bf7d5f0a935cfdb4f3823a4a03950dc54f890d54b47e0ae0e760'
CHECKPOINT_SHA = '950bc5d67dc8cf4980091ecac19a9b7b1ba94756e83d9bd101180e55863c0bb6'
TREE_SHA = '1ef3cc94d90465cea370c0974445f1d54b8de3192d33d2f5438464de41c0609f'
ARCHIVE_SHA = '736779e7084bccc0a4348eb62cbd0eacf753173a48146a37657e92e65f88df77'
ON_SHA = '35ddd709eaf5d6ab1aebe9271202259011ec1cb0a9f3e1e03fff791590701fc7'
OFF_SHA = '69d1735feb976539f7706131a0345c35a3c27ec1c8e04b99c5c1b218b88b0393'
N, Z = 65988, 377342


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(8 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def read_json(path):
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def replay_module():
    path = PREVIOUS / 'replay.py'
    require(digest(path) == 'f126c44a3cf7e0eaca4f9ca76a901f0e329c79be72beb50d96ce6a3ebdbef0f6', 'historical replay source mismatch')
    spec = importlib.util.spec_from_file_location('historical_m0_replay', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify(folder):
    historical_archive = PREVIOUS / 'data/chunk_artifacts.tar.gz'
    require(digest(historical_archive) == ARCHIVE_SHA, 'historical archive hash mismatch')
    require(digest(HERE / 'executed_sources/run_control_direct.py.txt') == RUNNER_SHA, 'runner snapshot hash mismatch')
    replay = replay_module()
    base = replay.read_npz(BASE, replay.BASELINE_SHA)
    replay.coordinates(base)
    mask, obs, old_bt = base['m0_mask'], base['obs_bt_k'], base['baseline_bt_kma_v3_0']
    require(mask.dtype == np.bool_ and mask.shape == obs.shape == old_bt.shape == (N, 7), 'baseline shape/type mismatch')
    require(int(mask.sum()) == Z and int(np.any(mask, axis=1).sum()) == 53906, 'baseline M0 support differs')
    require(np.isfinite(obs[mask]).all() and np.isfinite(old_bt[mask]).all(), 'baseline nonfinite')
    old_num, old_cost = replay.objective(old_bt, obs, mask)
    require(old_num == replay.BASELINE_NUM and old_cost == replay.BASELINE_COST, 'baseline arithmetic mismatch')
    binding, bh = read_json(folder / 'binding.json')
    summary, sh = read_json(folder / 'summary.json')
    required = {'schema':'kdm6.qnc_guard_control_full_m0_direct.v1', 'case':'control',
                'checkpoint_sha256':CHECKPOINT_SHA, 'runner_sha256':RUNNER_SHA,
                'source_tree_sha256':TREE_SHA, 'source_tree_files':517,
                'host_trace_on_result_sha256':ON_SHA, 'host_trace_off_result_sha256':OFF_SHA,
                'historical_archive_sha256':ARCHIVE_SHA,
                'historical_preflight_sha256':'b3f2bc237c580209b986a3486562dd1757f381b6ef3604a8731185e11d13ff1a',
                'historical_runtime_and_assets_match':True, 'support_cells':Z, 'chunks':129,
                'with_k':False, 'host_steps':0, 'KDM_calls':0,
                'raw_number_physical_unit_certification':False}
    for k, value in required.items():
        require(k in binding and type(binding[k]) is type(value) and binding[k] == value, f'binding {k} mismatch')
    expected_pins = {
        '58d23f72be7ae717b20d0d60b53f908c2ecf28bd1c973756a1d4c7e4f0ec7c8d',
        '2c337fc2b484efd9565334e2731cde8b3a4e40322cf2e534b904712382dece7b',
        '590ce005e02de301b921901aa91fe324411c34bb4215c1f7c7186cce67098033',
        'b489a65427fd2b23408b9687d46c875de1622601ecb28df6628e9a5d3983cc52',
        '84a20ae7d337c0c10aec6dd872ae75af75400822f809888a0b35656d3cd12663',
        replay.BASELINE_SHA,
        '115bdf2b8db76b69852fe5262c01723d198660dc9be9f7361a0ed1023671ba14',
        '602ca5c676014d6f14b94682053b5ba249af3a6f0ce34e3af92e01199c51e0cb',
        '74b2ce806988761d1e162cd432e271faa4ce4bfac10817a4810e5a70ecb16fa5',
        'b3f2bc237c580209b986a3486562dd1757f381b6ef3604a8731185e11d13ff1a'}
    require(len(binding['source_pins']) == len(expected_pins) and set(binding['source_pins'].values()) == expected_pins, 'source pin set differs')
    with tarfile.open(historical_archive, 'r:gz') as tar:
        historical = json.load(tar.extractfile('control/binding.json'))
    require(binding['runtime'] == historical['runtime'], 'historical runtime differs')
    assets, old_assets = copy.deepcopy(binding['rt_assets']), copy.deepcopy(historical['rt_assets'])
    assets['kma_calibration'].pop('path'); old_assets['kma_calibration'].pop('path')
    require(assets == old_assets, 'historical RTTOV assets differ')
    require(binding['source_tree_sha256'] == historical['source_tree_sha256'] and binding['source_tree_files'] == historical['source_tree_files'], 'historical code tree differs')
    for k, v in {'status':'DIRECT_FIXED_M0_COMPLETE', 'binding_sha256':bh, 'support_cells':Z,
                 'completed_chunk_receipts':129, 'direct_calls_recorded_in_completed_receipts':129,
                 'K_calls':0, 'huber_delta_K':1.0, 'sigma_K':1.0, 'bias_K':0.0,
                 'original_baseline_cost':old_cost}.items():
        require(k in summary and summary[k] == v, f'summary {k} mismatch')
    root = folder / 'chunks'
    require({p.name for p in root.iterdir()} == {f'chunk_{i:03d}' for i in range(129)}, 'chunk set differs')
    chunk_sums = []
    for i in range(129):
        d = root / f'chunk_{i:03d}'
        start, stop = i * 512, min((i + 1) * 512, N)
        require(d.is_dir() and not (d / 'failure.json').exists(), f'chunk {i}: failure or missing')
        attempt, _ = read_json(d / 'attempt.json')
        result, _ = read_json(d / 'result.json')
        require(attempt == {'binding_sha256':bh, 'chunk':i, 'flat_range':[start,stop], 'with_k':False}, f'chunk {i}: attempt mismatch')
        require(result['binding_sha256'] == bh and result['chunk'] == i and result['direct_calls'] == 1 and result['K_calls'] == 0, f'chunk {i}: result mismatch')
        rt = result['rttov_receipt']
        require(rt['mode'] == 'direct' and rt['direct_calls'] == 1 and rt['K_calls'] == 0, f'chunk {i}: RTTOV receipt mismatch')
        capture = d / 'result.npz'
        require(digest(capture) == result['capture_sha256'], f'chunk {i}: capture hash mismatch')
        with np.load(capture, allow_pickle=False) as z:
            require(set(z.files) == {'flat_indices','bt','quality','valid','profile_valid'}, f'chunk {i}: capture keys mismatch')
            x = {k: np.array(z[k], copy=True) for k in z.files}
        shape = (stop-start, 7)
        for k, dtype, s in [('flat_indices',np.int32,(stop-start,)), ('bt',np.float64,shape), ('quality',np.int32,shape), ('valid',np.bool_,shape), ('profile_valid',np.bool_,(stop-start,))]:
            require(x[k].dtype == dtype and x[k].shape == s, f'chunk {i}: {k} dtype/shape mismatch')
        require(np.array_equal(x['flat_indices'], np.arange(start,stop,dtype=np.int32)), f'chunk {i}: flat order mismatch')
        ids = rt['source_flat_indices']
        require(isinstance(ids, list) and all(type(value) is int for value in ids)
                and ids == x['flat_indices'][x['profile_valid']].tolist()
                and len(ids) == len(set(ids)) and all(start <= value < stop for value in ids),
                f'chunk {i}: source index identity mismatch')
        require(type(rt['nprofiles']) is int and rt['nprofiles'] == len(ids), f'chunk {i}: profile count mismatch')
        require(rt['channels'] == list(range(10, 17)) and rt['bt_coordinate'] == 'kma_v3_0', f'chunk {i}: channel or coordinate mismatch')
        require(rt['per_profile_geometry_surface'] is True, f'chunk {i}: geometry/surface mismatch')
        flags = rt['driver_flags']
        require(flags['case_do_direct'] is True and flags['case_do_k'] is False, f'chunk {i}: case driver flags mismatch')
        require(type(rt['K_recovered']) is int and rt['K_recovered'] == 0, f'chunk {i}: K recovery mismatch')
        m = mask[start:stop]
        require(np.all(x['valid'][m]) and np.all(x['profile_valid'][:,None] | ~m) and np.all(x['quality'][m] == 0) and np.isfinite(x['bt'][m]).all(), f'chunk {i}: fixed M0 support lost')
        sums = []
        for c in range(7):
            terms = (float(x['bt'][j,c])-float(obs[start+j,c]) for j in np.flatnonzero(m[:,c]))
            sums.append(math.fsum(0.5*v*v if abs(v) <= 1.0 else abs(v)-0.5 for v in terms))
        chunk_sums.append(math.fsum(sums))
    numerator = math.fsum(chunk_sums)
    cost = numerator / Z
    require(summary['chunk_numerators'] == chunk_sums and summary['numerator'] == numerator and summary['cost'] == cost and summary['cost_minus_original_baseline'] == cost-old_cost, 'summary arithmetic mismatch')
    return {'status':'OFFLINE_VERIFIED', 'binding_sha256':bh, 'summary_sha256':sh, 'checkpoint_sha256':CHECKPOINT_SHA, 'support_profiles':53906, 'support_cells':Z, 'blocks':129, 'baseline_cost':old_cost, 'control_huber_numerator':numerator, 'control_cost':cost, 'control_minus_baseline':cost-old_cost, 'model_calls_in_verifier':0}


def export(folder, destination):
    # Refuse incomplete runs before creating any output. Copy only compact evidence.
    result = verify(folder)
    binding, _ = read_json(folder / 'binding.json')
    for name, expected in binding['source_pins'].items():
        require(digest(Path(name)) == expected, f'private source pin changed: {name}')
    private_root = folder.parent.parent
    require(digest(private_root / 'run_control_direct.py') == RUNNER_SHA, 'private runner changed')
    host_runs = private_root.parent / 'native_qi_outflow_terms_20261030/runs/v1'
    for trace, expected in (('on', ON_SHA), ('off', OFF_SHA)):
        host_file = host_runs / f'control_qi_outflow_v2_{trace}_guardon/run_result.json'
        host, actual = read_json(host_file)
        require(actual == expected and host['status'] == 'PASS' and host['guard_mode'] == 'on'
                and host['trace_mode'] == trace and host['native_host_steps_completed'] == 1
                and host['ack']['byte_identical'] and host['checkpoint_sha256'] == CHECKPOINT_SHA,
                f'private host {trace} receipt differs')
        plan_file = host_file.parent / 'experiment_plan.json'
        plan, plan_sha = read_json(plan_file)
        require(plan_sha == host['plan_sha256'] and plan['source_case'] == 'control'
                and plan['guard_mode'] == 'on' and plan['trace_mode'] == trace
                and host['controller_sha256'] == 'b489a65427fd2b23408b9687d46c875de1622601ecb28df6628e9a5d3983cc52',
                f'private host {trace} plan/controller differs')
        build = private_root.parent / 'native_qi_outflow_terms_20261030/build/host_qi_outflow_v2/private_build_receipt.json'
        require(digest(build) == plan['build_receipt_sha256'], 'private build receipt differs')
        if trace == 'on':
            require(digest(Path(host['retained_checkpoint_path'])) == CHECKPOINT_SHA, 'private checkpoint differs')
    paths = [Path(name) for name in binding['source_pins'] if name.endswith('/harness/native_checkpoint_observation.py')]
    require(len(paths) == 1, 'cannot locate original source tree')
    repo = paths[0].parent.parent
    files = sorted(p for p in [*repo.glob('harness/*.py'), *repo.glob('oracle/**/*.py'),
                                *repo.glob('oracle/kdm6/obs/data/**/*')]
                   if p.is_file() and '__pycache__' not in p.parts)
    h = hashlib.sha256()
    for path in files:
        h.update(path.relative_to(repo).as_posix().encode() + b'\0' + digest(path).encode() + b'\n')
    require((len(files), h.hexdigest()) == (517, TREE_SHA), 'private source tree differs')
    require(not destination.exists(), 'destination already exists')
    destination.mkdir(parents=True, exist_ok=False)
    try:
        for name in ('binding.json','summary.json'):
            shutil.copyfile(folder / name, destination / name)
        for i in range(129):
            source = folder / 'chunks' / f'chunk_{i:03d}'
            target = destination / 'chunks' / source.name
            target.mkdir(parents=True)
            for name in ('attempt.json','result.json','result.npz'):
                shutil.copyfile(source / name, target / name)
        require(verify(destination) == result, 'copied evidence differs')
        copied_files = [Path('binding.json'), Path('summary.json')] + [
            Path('chunks') / f'chunk_{i:03d}' / name for i in range(129)
            for name in ('attempt.json', 'result.json', 'result.npz')]
        for name in copied_files:
            require(digest(folder / name) == digest(destination / name), f'copied bytes differ: {name}')
    except BaseException:
        # Preserve partial export for inspection; never overwrite it on retry.
        raise
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('completed_control', type=Path, help='completed control directory or exported copy')
    p.add_argument('--export', type=Path, help='new destination directory; refuses overwrite')
    args = p.parse_args()
    result = export(args.completed_control, args.export) if args.export else verify(args.completed_control)
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
