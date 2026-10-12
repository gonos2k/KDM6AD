#!/usr/bin/env python3
"""One zero-start eight-iteration-budget check of the unchanged PR414 window.

Reuse the immutable three-slot runner. Only its packet destination and declared
MAX_ITER value are supplied for this separate experiment; original guards, M/H,
initial prior, full-window VJP, accepted-point audit and storage remain intact.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

PACKET = Path(__file__).resolve().parent
ROOT = PACKET.parents[2]
OLD_PACKET = ROOT / 'harness/evidence/pr414_ami_window_2026-10-12'
OLD_PLAN = OLD_PACKET / 'WINDOW_PREDECLARED.json'
OLD_RUNNER = OLD_PACKET / 'run_window.py'
RUN_ID = 'PR415_JUL19_THREE_SLOT_8ITER_20261012_01'
MAX_ITER = 8
OUTPUT_ROOT = '/Users/yhlee/KDM6AD-k/host/research_evidence/pr415_window_finish_20261012/run-' + RUN_ID
INVARIANTS = ('v4_driver_path', 'intake_manifest', 'intake_npz', 'template_fixture',
              'observations', 'external_assets', 'h_fingerprint', 'python_executable',
              'thread_environment', 'slots', 'dt_s', 'n_steps',
              'zero_control_original_background', 'one_initial_prior', 'forcing_policy',
              'observations_policy', 'temporal_observation_error_assumption')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, obj):
    with Path(path).open('x') as stream:
        json.dump(obj, stream, indent=2, allow_nan=False)
        stream.write('\n')


def validate(plan, old):
    if (plan['run_id'] != RUN_ID or plan['max_iter'] != MAX_ITER or plan['output_root'] != OUTPUT_ROOT or
            plan['adapter_sha256'] != sha(__file__) or
            plan['original_plan_sha256'] != sha(OLD_PLAN) or
            plan['runner_sha256'] != sha(OLD_RUNNER)):
        raise ValueError('only the one declared PR415 original-background eight-budget experiment is supported')
    if any(plan[k] != old[k] for k in INVARIANTS):
        raise ValueError('same-problem inputs, operators, priors or time policy changed')
    for path, expected in old['bindings'].items():
        if plan['bindings'].get(path) != expected or sha(path) != expected:
            raise ValueError('original source/input changed; cannot re-pin as same problem: ' + path)
    for path, asset in old['external_assets'].items():
        if (sha(path) != asset['sha256'] or Path(path).stat().st_size != asset['bytes'] or
                str(Path(path).resolve()) != asset['resolved_path']):
            raise ValueError('original execution asset changed: ' + path)


def prepare_declaration():
    if (PACKET / 'WINDOW_PREDECLARED.json').exists():
        raise FileExistsError('declaration already exists; no overwrite')
    old = json.loads(OLD_PLAN.read_text())
    plan = {**old, 'schema': 'pr415_same_window_budget_declaration_v1', 'base_main': '238c52bf',
            'run_id': RUN_ID, 'max_iter': MAX_ITER,
            'output_root': OUTPUT_ROOT,
            'adapter_sha256': sha(__file__), 'original_plan_sha256': sha(OLD_PLAN),
            'optimizer_max_eval': 'unchanged Torch default nominal10; strong-Wolfe may exceed',
            'experiment_change': 'max_iter3 to8 only; destination/run identity/source declaration differ, zero-start original prior unchanged',
            'stop_policy': 'one bounded attempt; no automatic retry, budget escalation or tolerance relaxation',
            'interpretation': old['interpretation'] + ' Same-problem bounded budget check; convergence, sampled BT temporal response and accepted initial state changes reported separately.'}
    plan['bindings'] = dict(old['bindings'])
    extra = [Path(__file__), OLD_PLAN, OLD_PACKET / 'RESULT.json', OLD_PACKET / 'PREFLIGHT.json']
    old_result = json.loads((OLD_PACKET / 'RESULT.json').read_text())
    checkpoint = Path(old_result['checkpoint']['path'])
    if sha(checkpoint) != old_result['checkpoint']['sha256']:
        raise ValueError('old result/checkpoint changed')
    extra.append(checkpoint)
    for path in extra:
        plan['bindings'][str(path.resolve())] = sha(path)
    validate(plan, old)
    Path(OUTPUT_ROOT).parent.mkdir(mode=0o700, exist_ok=False)
    write(PACKET / 'WINDOW_PREDECLARED.json', plan)
    print('DECLARED_SAME_PROBLEM_EIGHT_BUDGET_NOT_EXECUTED')


def compare_prepared_context():
    current = json.loads((PACKET / 'PREFLIGHT.json').read_text())
    old = json.loads((OLD_PACKET / 'PREFLIGHT.json').read_text())
    a, b = current['fingerprint'], old['fingerprint']
    a['H'].pop('fixture_case_dir')
    b['H'].pop('fixture_case_dir')
    if a != b:
        raise ValueError('prepared background, forcing, H or per-slot observation signatures differ from PR414')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--declare', action='store_true')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.declare:
        if args.execute:
            raise ValueError('declaration cannot execute')
        prepare_declaration()
        return
    plan = json.loads((PACKET / 'WINDOW_PREDECLARED.json').read_text())
    old = json.loads(OLD_PLAN.read_text())
    validate(plan, old)
    if args.execute:
        compare_prepared_context()
    spec = importlib.util.spec_from_file_location('pr415_immutable_window_runner', OLD_RUNNER)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    if (runner.MAX_ITER != 3 or runner.SLOTS != (1, 31, 61) or
            runner.NSTEP != 61 or runner.DT != 20.0):
        raise ValueError('unexpected original three-slot runner contract')
    # Explicit destination/budget adapter; no original function or source edits.
    runner.PACKET = PACKET
    runner.MAX_ITER = MAX_ITER
    runner.main()
    if not args.execute:
        compare_prepared_context()
    else:
        result_path = Path(plan['output_root']) / 'RESULT.json'
        result = json.loads(result_path.read_text())
        write(Path(plan['output_root']) / 'DRIVER_RESULT.json', {
            'schema': 'pr415_same_problem_budget_result_v1', 'run_id': RUN_ID,
            'status': result['status'], 'original_runner_sha256': sha(OLD_RUNNER),
            'new_adapter_sha256': sha(__file__), 'plan_sha256': sha(PACKET / 'WINDOW_PREDECLARED.json'),
            'result_path': str(result_path), 'result_sha256': sha(result_path),
            'serialization_schema_reused': 'pr414_actual_local_window_v1',
            'scientific_change': 'optimizer budget only;61-step3-slot problem unchanged',
            'automatic_retry': False, 'native_integrations': 0, 'new_dates': 0})


if __name__ == '__main__':
    # The immutable runner parses the same --execute flag; --declare is handled
    # here and never passed through to its parser.
    main()
