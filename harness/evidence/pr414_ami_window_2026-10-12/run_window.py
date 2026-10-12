#!/usr/bin/env python3
"""One declared real AMI three-slot local held-forcing window (not host cycling).

Snapshots/numpy conversions below are value-only receipt/checkpoint boundaries.
Production KDM VJP, RTTOV K and the dual minimizer remain unchanged.
"""
import argparse
import copy
from datetime import datetime, timedelta
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
SLOTS = (1, 31, 61)
DT = 20.0
NSTEP = 61
MAX_ITER = 3


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path, obj):
    with Path(path).open('x') as stream:
        json.dump(obj, stream, indent=2, allow_nan=False)
        stream.write('\n')


def check_bindings(plan):
    for path, digest in plan['bindings'].items():
        if sha(path) != digest:
            raise ValueError('input/source changed: ' + path)
    for path, asset in plan['external_assets'].items():
        if (str(Path(path).resolve()) != asset['resolved_path'] or
                Path(path).stat().st_size != asset['bytes'] or sha(path) != asset['sha256']):
            raise ValueError('execution asset changed: ' + path)


def context(plan, prepare=False):
    driver = load(plan['v4_driver_path'], 'pr414_v4_builder')
    intake = driver.load_module(driver.INTAKE_SOURCE, 'pr414_v4_intake')
    manifest, arrays = intake.load_bound_intake(Path(plan['intake_manifest']), Path(plan['intake_npz']))
    legacy = driver.load_module(driver.LEGACY_DRIVER, 'pr414_fixture_builder')
    output = Path(plan['output_root'])
    fixture = output / 'rttov_fixture'
    if prepare:
        output.mkdir(mode=0o700, exist_ok=False)
        legacy._prepare_fixture_copy(Path(plan['template_fixture']), fixture, arrays)
    ctx = driver.build_inputs(manifest, arrays, fixture, Path(plan['template_fixture']), legacy)
    observations = json.loads(Path(plan['observations']).read_text())
    # Scene-specific geometry is checked during preparation. All three pixels
    # share one navigation grid/point; require exact agreement, not an assumption.
    return driver, legacy, ctx, observations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    plan_path = PACKET / 'WINDOW_PREDECLARED.json'
    plan_sha = sha(plan_path)
    plan = json.loads(plan_path.read_text())
    if (sys.executable != plan['python_executable'] or not __debug__ or
            os.environ.get('PYTHONOPTIMIZE') != '0' or any(
                os.environ.get(k) != '1' for k in plan['thread_environment'])):
        raise ValueError('exact declared Python, assertions and single-thread environment required')
    import numpy as np
    import torch
    from kdm6.state import State
    from kdm6.da_cvt import make_default_cvt, cvt_apply
    from kdm6.da_dual import run_dual_minimizer, default_param_prior, ObsEvalResult
    from kdm6.obs.allsky_shard import sharded_allsky
    torch.set_num_threads(1)
    if str(torch.__version__) != '2.13.0':
        raise ValueError('pinned Torch version required')
    check_bindings(plan)
    if (plan['slots'] != list(SLOTS) or plan['n_steps'] != NSTEP or
            plan['dt_s'] != DT or plan['max_iter'] != MAX_ITER or
            plan['runner_sha256'] != sha(__file__)):
        raise ValueError('declaration differs from this bounded window')
    _, _, ctx, observations = context(plan, prepare=not args.execute)
    # Concrete observation schema supplied by the unchanged L1B reader wrapper.
    if observations['time_assumption'] != 'NOMINAL_FILENAME_TIME_AS_MODEL_UTC_RESEARCH_MODE':
        raise ValueError('unrecognized observation time hypothesis')
    slots = observations['slots']
    if len(slots) != 3:
        raise ValueError('exactly three real scenes required')
    targets = {}
    configs = {}
    signatures = {}
    original = json.loads(Path(plan['intake_manifest']).read_text())['observation']
    for t, scene in zip(SLOTS, slots):
        if scene['analysis_channel_ids'] != list(range(10, 17)) or scene['scene_date'] != '2025-07-19':
            raise ValueError('scene date or channel order differs')
        if scene['pixel_utc'] is not None or scene['pixel_utc_time_verified'] is not False:
            raise ValueError('this declared nominal-time experiment cannot relabel actual pixel UTC')
        if scene['time_assumption'] != observations['time_assumption']:
            raise ValueError('slot nominal-time assumption differs')
        expected_time = datetime(2025, 7, 19, 5, 55, 40) + timedelta(seconds=t * DT)
        if scene['nominal_slot_obt'] != expected_time.strftime('%Y%m%d%H%M'):
            raise ValueError('scene nominal slot differs from local model schedule')
        if scene['step_index'] != t:
            raise ValueError('observation step ordering differs')
        point = scene['nearest_pixel']
        for name in ('row', 'column', 'latitude_deg', 'longitude_deg'):
            if point[name] != original['nearest_pixel'][name]:
                raise ValueError('navigation changed; this bounded shared-geometry window rejects it')
        if scene['reader_geos'] != original['reader_geos']:
            raise ValueError('scene navigation projection changed')
        target = torch.tensor(scene['y_bt_K'], dtype=torch.float64).reshape(1, 7)
        dqf = np.asarray(scene['reader_dqf'])
        if not torch.isfinite(target).all() or dqf.shape != (7,) or np.any(dqf != 0):
            raise ValueError('all seven source channels must be finite/quality0')
        targets[t] = target
        configs[t] = copy.deepcopy(ctx['rttov_cfg'])
        signatures[t] = hashlib.sha256(json.dumps({
            'step': t, 'target': scene['y_bt_K'], 'channels': list(range(10, 17)),
            'mask': [1] * 7, 'H': plan['h_fingerprint'], 'observation_sha': sha(plan['observations'])
        }, sort_keys=True).encode()).hexdigest()
    capture = load(ROOT / 'harness/evidence/pr395_tq_state_capture_2026-10-10/capture_tq_state.py', 'pr414_capture_primitives')
    h_now = capture._public_h_config_summary(ctx['rttov_cfg'])
    h_now.pop('fixture_case_dir')
    if h_now != plan['h_fingerprint']:
        raise ValueError('H auxiliary inputs differ from bound initial native background')
    files = {str(p): sha(p) for p in (Path(plan['output_root']) / 'rttov_fixture').rglob('*') if p.is_file()}
    fingerprint = {'initial_state': capture.state_sha256(ctx['xb']),
                   'forcing': capture.forcing_sha256(ctx['forcing']),
                   'H': capture._public_h_config_summary(ctx['rttov_cfg']),
                   'signatures': {str(t): s for t, s in signatures.items()}}
    preflight = PACKET / 'PREFLIGHT.json'
    if not args.execute:
        write(preflight, {'status': 'PREPARED_NO_ANALYSIS', 'plan_sha256': sha(plan_path),
                          'fingerprint': fingerprint, 'fixture_hashes': files,
                          'torch_version': str(torch.__version__), 'analysis_executed': False})
        print('PREPARED_NO_ANALYSIS', flush=True)
        return
    pre = json.loads(preflight.read_text())
    if (pre['status'] != 'PREPARED_NO_ANALYSIS' or pre['analysis_executed'] is not False or
            pre['plan_sha256'] != plan_sha or pre['fingerprint'] != fingerprint or
            pre['fixture_hashes'] != files):
        raise ValueError('prepared context drift')
    output = Path(plan['output_root'])
    write(output / 'RUN_STARTED_ONCE.json', {'run_id': plan['run_id'], 'plan_sha256': sha(plan_path), 'preflight_sha256': sha(preflight)})
    cvt, b_sigma = make_default_cvt(ctx['xb'], th_sigma=0.8, qv_sigma=0.08, qv_levels=12,
                                   sigma_overrides={f: 0.0 for f in State._fields if f not in ('th', 'qv')})
    prior = default_param_prior(active=())
    events = []
    baseline_states, last_states = {}, {}
    mask = torch.ones((1, 7), dtype=torch.float64)
    observation = {}
    original_factory = torch.optim.LBFGS
    def arr(x):
        return x.detach().cpu().numpy().copy()
    try:
        with mp.get_context('spawn').Pool(1) as pool:
            def observe(t, x):
                if t not in targets:
                    return None
                event = {'call': len(events) + 1, 'step_index': t, 'returned': False}
                events.append(event)
                out = sharded_allsky(x, ctx['forcing'], torch.tensor([0]), targets[t], mask,
                                     ctx['xland'], configs[t], str(output / 'h_cases' / f'call{len(events):03d}'),
                                     n_workers=1, grad=True, huber_delta=1.0, obs_sigma=1.0,
                                     obs_bias=0.0, pool=pool)
                bt, rq = arr(out['bt']), arr(out['rq'])
                if bt.shape != (1, 7) or not np.isfinite(bt).all() or rq.shape != (1, 7) or not np.isfinite(rq).all() or np.any(rq != 0):
                    raise RuntimeError(f'fixed seven-channel model quality lost at step {t}')
                residual = bt - arr(targets[t])
                independent = float(np.where(abs(residual) <= 1, 0.5 * residual ** 2, abs(residual) - 0.5).sum())
                if not np.isclose(independent, float(out['j']), atol=1e-10, rtol=1e-12):
                    raise RuntimeError('per-slot independent objective mismatch')
                event.update(returned=True, BT_K=bt[0].tolist(), rad_quality=rq[0].tolist(),
                             J_o=float(out['j']), signature=signatures[t], n_valid=7)
                snapshot = {f: arr(getattr(x, f)) for f in State._fields}
                baseline_states.setdefault(t, snapshot)
                last_states[t] = snapshot
                print(json.dumps(event), flush=True)
                return ObsEvalResult(float(out['j']), State(*(out['adj'][i] for i in range(12))), 7, signatures[t])
            observe.connected_fields = ('th', 'qv', 'qc', 'qi', 'qs', 'nc', 'ni')
            observe.normalized_dry = True
            torch.optim.LBFGS = capture._observe_existing_lbfgs(original_factory, observation)
            result = run_dual_minimizer(ctx['xb'], (ctx['forcing'],) * NSTEP, observe,
                                        ctx['window_config'], b_sigma, prior, max_iter=MAX_ITER, cvt=cvt)
        if observation['constructor_calls'] != 1 or observation['step_calls'] != 1:
            raise RuntimeError('expected exactly one optimizer construction and step')
        params = observation['optimizer'].param_groups[0]['params']
        gradient = arr(params[0].grad)
        parameter_gradient = arr(params[1].grad)
        rederived, _ = cvt_apply(ctx['xb'], b_sigma, result.v_state, cvt)
        if any(not torch.equal(getattr(rederived, f), getattr(result.x_analysis, f)) for f in State._fields):
            raise RuntimeError('accepted initial state differs from exact CVT reconstruction')
        if len(events) != 3 * (result.n_window_evals + result.n_audit_evals):
            raise RuntimeError('window/audit callback count mismatch')
        first, final = events[:3], events[-3:]
        if result.j_trace[0]['j_state'] != 0 or result.j_trace[0]['j_theta'] != 0:
            raise RuntimeError('first trajectory was not original zero-control background')
        if [e['step_index'] for e in final] != list(SLOTS) or result.n_audit_evals != 1:
            raise RuntimeError('final audit did not cover all slots')
        if not np.isclose(sum(e['J_o'] for e in first), result.j_trace[0]['j_obs'], atol=1e-10, rtol=1e-12):
            raise RuntimeError('initial observation objective mismatch')
        jb = 0.5 * float((arr(result.v_state) ** 2).sum())
        jo = sum(e['J_o'] for e in final)
        if not np.isclose(jo, result.jobs_final, rtol=1e-12, atol=1e-10) or not np.isclose(jb, result.jb_final):
            raise RuntimeError('final objective mismatch')
        if np.any(arr(result.v_theta) != 0) or np.any(parameter_gradient != 0):
            raise RuntimeError('inactive physical controls changed')
        if not np.isfinite(gradient).all() or not np.isclose(np.linalg.norm(gradient), result.grad_norm_final):
            raise RuntimeError('full gradient mismatch')
        payload = {'control__v_state': arr(result.v_state), 'control__v_theta': arr(result.v_theta),
                   'control__gradient_state': gradient, 'control__gradient_parameters': parameter_gradient}
        for prefix, state in [('background_initial', ctx['xb']), ('accepted_initial', result.x_analysis), ('b_sigma', b_sigma), ('forcing', ctx['forcing'])]:
            for f in state._fields:
                payload[prefix + '__' + f] = arr(getattr(state, f))
        for label, snapshots in [('background_slot', baseline_states), ('accepted_slot', last_states)]:
            for t, values in snapshots.items():
                for f, value in values.items():
                    payload[f'{label}_{t}__{f}'] = value
        for label, evs in [('background', first), ('accepted', final)]:
            for e in evs:
                payload[f'{label}_{e["step_index"]}__bt'] = np.array(e['BT_K'])
                payload[f'{label}_{e["step_index"]}__rq'] = np.array(e['rad_quality'])
        for t in SLOTS:
            payload[f'observations_{t}__y_bt'] = arr(targets[t])
            payload[f'observations_{t}__mask'] = arr(mask)
        payload['fixed_optical_rho_d'] = np.asarray(ctx['rttov_cfg']['rho_d']).copy()
        payload['p_lay'] = np.asarray(ctx['rttov_cfg']['p_lay']).copy()
        payload['p_half'] = np.asarray(ctx['rttov_cfg']['p_half']).copy()
        checkpoint = output / 'private' / 'accepted_window.npz'
        checkpoint.parent.mkdir(mode=0o700)
        checkpoint_sha = capture.write_private_npz_atomic(checkpoint, payload)
        check_bindings(plan)
        if sha(plan_path) != plan_sha:
            raise ValueError('declaration changed during run')
        if any(sha(p) != h for p, h in files.items()):
            raise ValueError('fixture changed after analysis')
        summary = {'schema': 'pr414_actual_local_window_v1', 'status': 'RETURNED_AUDITED_WINDOW', 'run_id': plan['run_id'],
                   'plan_sha256': sha(plan_path), 'slots': list(SLOTS), 'n_steps': NSTEP,
                   'observations': slots, 'shared_effective_H': fingerprint['H'],
                   'native_integrations': 0, 'new_observation_dates': 0, 'full_host_cycling': False,
                   'initial_J_o': sum(e['J_o'] for e in first), 'final_J_o': jo, 'final_J_b': jb,
                   'final_J': jo + jb, 'gradient_Linf': float(np.max(abs(gradient))),
                   'gradient_L2': float(np.linalg.norm(gradient)), 'strict_gradient_converged': bool(np.max(abs(gradient)) <= 1e-10),
                   'termination_reason': 'UNKNOWN', 'optimizer': observation['step_state'],
                   'window_evaluations': result.n_window_evals, 'audit_evaluations': result.n_audit_evals,
                   'logical_H_calls': len(events), 'internal_RTTOV_calls': None,
                   'trace': capture._jsonable(result.j_trace), 'baseline': first, 'accepted': final,
                   'events': events, 'objective_audit': 'CROSSCHECKED_ALL_THREE_SLOTS',
                   'checkpoint': {'path': str(checkpoint), 'sha256': checkpoint_sha, 'array_keys': sorted(payload)},
                   'active_controls': {f: int((getattr(b_sigma, f) > 0).sum()) for f in State._fields},
                   'interpretation': plan['interpretation']}
        write(output / 'RESULT.json', summary)
        print(json.dumps({k: summary[k] for k in ('status', 'initial_J_o', 'final_J', 'gradient_Linf')}), flush=True)
    except Exception as exc:
        write(output / 'FAILED.json', {'status': 'FAILED_NO_RETRY', 'error': repr(exc), 'events': events})
        raise
    finally:
        torch.optim.LBFGS = original_factory


if __name__ == '__main__':
    main()
