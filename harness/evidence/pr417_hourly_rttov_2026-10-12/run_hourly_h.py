#!/usr/bin/env python3
"""Exactly two value-only actual all-sky H calls; no observation fit, M or optimizer."""
import hashlib
import importlib.util
import json
import multiprocessing as mp
import os
from pathlib import Path
import sys

PACKET = Path(__file__).resolve().parent
ROOT = PACKET.parents[2]
sys.path.insert(0, str(ROOT / 'oracle'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, obj):
    with Path(path).open('x') as stream:
        json.dump(obj, stream, indent=2, allow_nan=False)
        stream.write('\n')


def check(plan):
    for path, digest in plan['bindings'].items():
        if sha(path) != digest:
            raise ValueError('bound input/source changed: ' + path)
    for path, asset in plan['external_assets'].items():
        if (sha(path) != asset['sha256'] or Path(path).stat().st_size != asset['bytes'] or
                str(Path(path).resolve()) != asset['resolved_path']):
            raise ValueError('H asset changed: ' + path)
    for path, digest in plan['fixture_hashes'].items():
        if sha(path) != digest:
            raise ValueError('prepared fixture changed: ' + path)


def main():
    plan_path = PACKET / 'PLAN.json'
    plan_sha = sha(plan_path)
    plan = json.loads(plan_path.read_text())
    if (plan['time_indices'] != [6, 7] or plan['max_logical_H_calls'] != 2 or
            plan['runner_sha256'] != sha(__file__)):
        raise ValueError('only the declared two-snapshot H comparison is supported')
    if (not __debug__ or os.environ.get('PYTHONOPTIMIZE') != '0' or
            sys.executable != plan['python_executable'] or any(os.environ.get(k) != '1' for k in plan['thread_environment'])):
        raise ValueError('declared interpreter/assertions/single-thread environment required')
    check(plan)
    import numpy as np
    import torch
    from kdm6.obs.allsky_shard import sharded_allsky
    torch.set_num_threads(1)
    if str(torch.__version__) != '2.13.0':
        raise ValueError('declared Torch version changed')
    spec = importlib.util.spec_from_file_location('pr417_prepared_inputs', PACKET/'prepare_hourly_h.py')
    prep = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prep)
    output = Path(plan['output_root'])
    output.mkdir(mode=0o700, exist_ok=False)
    write(output/'H_STARTED_ONCE.json', {'plan_sha256': plan_sha, 'logical_H_max': 2, 'M_optimizer_calls': 0})
    events = []
    try:
        with mp.get_context('spawn').Pool(1) as pool:
            for time_index in (6, 7):
                ctx = prep.load_context(plan_path, time_index)
                # Placeholder is interface shape only. Its returned dummy cost
                # is deliberately ignored; no observation, residual or fit metric.
                target = torch.zeros((1, 7), dtype=torch.float64)
                gate = torch.ones_like(target)
                event = {'time_index': time_index, 'returned': False, 'grad_requested': False}
                events.append(event)
                out = sharded_allsky(ctx['state'], ctx['forcing'], torch.tensor([0]), target, gate,
                                     ctx['xland'], ctx['rttov_cfg'], str(output/f'H_{time_index:02d}'),
                                     n_workers=1, grad=False, huber_delta=1.0, obs_sigma=1.0, obs_bias=0.0, pool=pool)
                bt = out['bt'].detach().numpy()
                rq = out['rq'].detach().numpy()
                event.update(returned=True, BT_K=bt.tolist(), rad_quality=rq.tolist())
                write(output/f'H_{time_index:02d}.json', event)
                if bt.shape != (1, 7) or rq.shape != (1, 7) or not np.isfinite(bt).all() or np.any(rq != 0):
                    raise ValueError('fixed seven-channel forward-quality domain lost; no channel removal/retry')
                print(json.dumps(event), flush=True)
        check(plan)
        if sha(plan_path) != plan_sha:
            raise ValueError('plan changed during H calls')
        delta = np.asarray(events[1]['BT_K']) - np.asarray(events[0]['BT_K'])
        result = {'schema': 'pr417_historical_hourly_H_v1', 'status': 'RETURNED_TWO_ACTUAL_VALUE_ONLY_H',
                  'plan_sha256': plan_sha, 'channels': list(range(10, 17)), 'logical_H_calls': 2,
                  'internal_RTTOV_direct_K_calls': None, 'M_native_optimizer_calls': 0,
                  'events': events, 'BT_delta_07_minus_06_K': delta.tolist(),
                  'dummy_cost_discarded': True, 'observation_fit_or_temporal_reproduction_assessed': False,
                  'retained_case_same_problem_comparison': False, 'new_dates': 0,
                  'interpretation': 'Joint historical snapshot state/pressure/density/surface response under declared common H rules; not isolated microphysics or observed temporal fit.'}
        write(output/'RESULT.json', result)
        write(PACKET/'RESULT.json', result)
        print(result['status'], flush=True)
    except Exception as exc:
        write(output/'FAILED.json', {'status': 'FAILED_NO_RETRY', 'error': repr(exc), 'events': events})
        raise


if __name__ == '__main__':
    main()
