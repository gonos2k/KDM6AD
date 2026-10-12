#!/usr/bin/env python3
"""Bind one Jul19 actual three-slot window before its single analysis attempt."""
import hashlib
import json
from pathlib import Path

PACKET = Path(__file__).resolve().parent
ROOT = PACKET.parents[2]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    old = json.loads((ROOT / 'harness/evidence/pr413_cloud_convergence_2026-10-12/PREDECLARED.json').read_text())
    observation_path = PACKET / 'OBSERVATIONS.json'
    observations = json.loads(observation_path.read_text())
    if (observations['schema'] != 'pr414_ami_window_observations_v1' or
            observations['status'] != 'DECODED_L1B_POINTS_ONLY' or
            observations['status_detail'] != 'READY_FOR_DECLARED_WINDOW_ADAPTER_ONLY' or
            observations['all_slots_pass_support_gate'] is not True):
        raise ValueError('completed real L1B points required')
    h = json.loads(Path(old['baseline_capture']).read_text())['effective_h_configuration']
    h.pop('fixture_case_dir')
    bindings = dict(old['bindings'])
    paths = list((ROOT / 'oracle/kdm6').rglob('*.py')) + list(PACKET.glob('*.py')) + [observation_path]
    # Producer receipt explicitly enumerates raw and compact data. No automatic
    # directory crawler or unbounded acquisition is part of this declaration.
    for path, expected in observations['bound_files'].items():
        if sha(path) != expected:
            raise ValueError('published decoded input digest mismatch: ' + path)
    paths += [Path(p) for p in observations['bound_files']]
    for path in paths:
        bindings[str(path.resolve())] = sha(path)
    plan = {'schema': 'pr414_three_slot_declaration_v1', 'base_main': 'f16645f1',
            'run_id': 'PR414_JUL19_0556_0606_0616_20261012_01',
            'runner_sha256': sha(PACKET / 'run_window.py'),
            'v4_driver_path': old['v4_driver_path'], 'intake_manifest': old['intake_manifest'],
            'intake_npz': old['intake_npz'], 'template_fixture': old['template_fixture'],
            'output_root': '/Users/yhlee/KDM6AD-k/host/research_evidence/pr414_ami_window_20261012/run-PR414_JUL19_0556_0606_0616_20261012_01',
            'observations': str(observation_path), 'bindings': bindings,
            'external_assets': old['external_assets'], 'h_fingerprint': h,
            'python_executable': old['environment']['python_executable'],
            'thread_environment': old['environment']['thread_environment'],
            'slots': [1, 31, 61], 'dt_s': 20.0, 'n_steps': 61, 'max_iter': 3,
            'optimizer_max_eval': 'Torch default nominal floor(1.25*3)=3; line search may exceed',
            'zero_control_original_background': True, 'one_initial_prior': True,
            'forcing_policy': 'same validated BG f0 held for all61 local transitions',
            'observations_policy': 'three actual AMI L1B scenes, 7 fixed channels each, sigma1K bias0 normalizedHuberDelta1',
            'temporal_observation_error_assumption': 'additive equal-scale21 channel-time Huber terms; temporal error independence/covariance not empirically calibrated',
            'automatic_retry': False, 'native_integrations': 0,
            'interpretation': 'Forecast-backed prescribed-forcing local KDM joint window through06:16; not saved host forecast later states or cycling. Nominal OBT filenames treated as modelUTC by research hypothesis, pixelUTC unverified. One bounded finite-budget attempt, not a strict convergence or atmospheric truth claim.'}
    with (PACKET / 'WINDOW_PREDECLARED.json').open('x') as stream:
        json.dump(plan, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print('DECLARED_NOT_EXECUTED')


if __name__ == '__main__':
    main()
