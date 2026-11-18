#!/usr/bin/env python3
"""Verify the archived narrow worker comparison without claiming a speedup."""
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST_SHA = '47b88317ee4049675ce997e592c99d96849fc6dca90b8e65ba2a0abdd3807bee'
SUITES = (
    'harness/evidence/native_nr16_vjp_fd_2026-11-06',
    'harness/evidence/native_d1_coeres_upstream_cpp_ad_2026-11-10',
    'harness/evidence/native_nc16_fd_expanded_2026-11-06',
)


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def check_record(receipt, one, logs):
    need(receipt['schema'] == 'kdm6.oracle_runner_worker_probe.nonpass.v1'
         and receipt['scientific_status'] == 'INCONCLUSIVE', 'nonpass receipt')
    need(receipt['one_worker']['wall_seconds'] == 409.722
         and (receipt['one_worker']['tests'], receipt['one_worker']['passed'], receipt['one_worker']['skipped']) == (25, 25, 0),
         'one-worker summary')
    need(one['success'] is True and one['expected'] == 3 and one['mode'] == 'normal'
         and [x['suite'] for x in one['suites']] == list(SUITES)
         and all(x['status'] == 'pass' for x in one['suites'])
         and one['totals']['tests'] == one['totals']['passed_in_successful_suites'] == 25
         and one['totals']['skipped'] == 0, 'one-worker result')
    need(one['wall_seconds'] == receipt['one_worker']['wall_seconds']
         and one['suites'] == receipt['one_worker']['suites'], 'one-worker result/receipt link')
    two = receipt['two_worker']
    need(two['status'] == 'incomplete' and two['total_wall_seconds'] == 'unavailable'
         and two['outcome_parity'] == 'unresolved'
         and '300s timeout' in two[SUITES[0].split('/')[-1]], 'two-worker nonpass scope')
    for path in ('workers_1.log.gz', 'workers_2.log.gz'):
        raw = logs[path]
        need(sha(raw) == receipt['artifacts'][path]['uncompressed_sha256'], 'uncompressed log SHA')
    need('[normal] summary expected=3 completed=3 tests=25 passed=25 skipped=0 failed_suites=0'
         in logs['workers_1.log.gz'].decode(), 'one-worker log summary')
    second = logs['workers_2.log.gz'].decode()
    for suite in SUITES[1:]:
        need(f'[normal] {suite}: pass' in second, 'two-worker completed suite')
    need('[normal] summary expected=3' not in second, 'no completed two-worker summary')
    return {
        'schema': 'kdm6.oracle_runner_worker_probe_public_replay.v1',
        'one_worker': {'tests': 25, 'passed': 25, 'skipped': 0, 'wall_seconds': 409.722},
        'two_worker': 'INCOMPLETE: two suites passed, third timed out; cleanup EPERM recorded in receipt, not archived log',
        'speedup_status': 'INCONCLUSIVE',
    }


def verify(root=HERE):
    manifest_raw = (root / 'manifest.json').read_bytes()
    need(sha(manifest_raw) == MANIFEST_SHA, 'manifest SHA')
    manifest = json.loads(manifest_raw)
    need(manifest['schema'] == 'kdm6.oracle_runner_worker_probe_packet.v1'
         and set(manifest['files']) == ({f'raw/{name}' for name in ('receipt.json', 'workers_1.json', 'workers_1.log.gz', 'workers_2.log.gz')}
                                      | {'producer/compare_workers_attempt.py'}),
         'manifest inventory')
    for name, digest in manifest['files'].items():
        need(sha((root / name).read_bytes()) == digest, 'asset SHA: ' + name)
    receipt = json.loads((root / 'raw/receipt.json').read_bytes())
    need(receipt['source_and_toolchain_hashes_observed_after_run']['experiment_script_snapshot_sha256']
         == manifest['files']['producer/compare_workers_attempt.py']
         and receipt['source_snapshot_note'] == 'Experiment script snapshot was retained after the failed comparison; its hash was checked after execution, not at call entry.',
         'post-run source snapshot')
    for name, data in receipt['artifacts'].items():
        need(sha((root / 'raw' / name).read_bytes()) == data['sha256'], 'receipt asset SHA')
    one = json.loads((root / 'raw/workers_1.json').read_bytes())
    logs = {name: gzip.decompress((root / 'raw' / name).read_bytes())
            for name in ('workers_1.log.gz', 'workers_2.log.gz')}
    return check_record(receipt, one, logs)


if __name__ == '__main__':
    print(json.dumps(verify(), indent=2, sort_keys=True))
