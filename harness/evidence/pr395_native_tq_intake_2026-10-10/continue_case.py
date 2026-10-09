#!/usr/bin/env python3
"""Wait for this already-running native case, then execute its gated intake once.

This is a single-case continuation, not a model launcher. It never terminates
or restarts WRF. The completion marker is written by run_ss_case after output
archival. Intake and analysis independently validate their inputs. No retry is
performed after a consumer failure.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[3]
PYTHON = Path('/private/tmp/KDM6AD-research-rc-20261007/env/bin/python')
RUN = Path('/private/tmp/KDM6AD-pr393-target-preparation-20261009/case_nominal/runs/'
           'mp337_viirs_norm2_dry1_055540_055800_358min_hist0_20261010_052612_p99148')
PACKET = Path(__file__).resolve().parent
# Earlier waiting jobs were withdrawn before any consumer ran for the
# gradient-preservation follow-up and independent team audit. WRF was untouched.
JOB = ROOT / 'graphify-out/pr395-case-continuation-v4'
CONSUMERS = (PACKET / 'intake_native_tq.py', PACKET / 'run_analysis.py',
             ROOT / 'harness/evidence/pr395_tq_state_capture_2026-10-10/capture_tq_state.py',
             ROOT / 'harness/evidence/pr395_observation_matchup_2026-10-10/RECEIPT.json',
             PACKET / 'diagnose_saved_state.py')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(name: str, status: str, **fields) -> None:
    payload = {'status': status, 'utc': dt.datetime.now(dt.timezone.utc).isoformat(),
               'run_dir': str(RUN), **fields}
    with (JOB / name).open('x') as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write('\n')


def main() -> int:
    JOB.mkdir(parents=True, exist_ok=True)
    fd = os.open(JOB / 'CLAIMED_ONCE', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    pinned = {str(p): digest(p) for p in CONSUMERS}
    record('START.json', 'WAITING_FOR_NATIVE_COMPLETION', pid=os.getpid(),
           consumer_sha256=pinned, python=str(PYTHON), wrf_relaunched=False)
    while not (RUN / 'exit_code').is_file():
        time.sleep(30)
    # The runner writes this marker last, after the completion JSON and archive.
    time.sleep(1)
    completion = json.loads((RUN / 'experiment_valid.json').read_text())
    if ((RUN / 'exit_code').read_text().strip() != '0'
            or completion.get('experiment_valid') is not True
            or completion.get('model_completed') is not True):
        record('FINISH.json', 'STOPPED_NATIVE_INVALID', native_completion=completion,
               H_or_analysis_started=False)
        return 1
    if pinned != {str(p): digest(p) for p in CONSUMERS}:
        record('FINISH.json', 'STOPPED_CONSUMER_SOURCE_CHANGED', H_or_analysis_started=False)
        return 1
    env = dict(os.environ, OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
               OMP_THREAD_LIMIT='1', VECLIB_MAXIMUM_THREADS='1')
    commands = ([str(PYTHON), str(CONSUMERS[0]), '--run-dir', str(RUN)],
                [str(PYTHON), str(CONSUMERS[1])])
    results = []
    for index, command in enumerate(commands):
        if pinned != {str(p): digest(p) for p in CONSUMERS}:
            record('FINISH.json', 'STOPPED_CONSUMER_SOURCE_CHANGED', commands=results,
                   automatic_retry=False)
            return 1
        with (JOB / f'consumer_{index}.log').open('xb') as log:
            result = subprocess.run(command, cwd=ROOT, env=env, stdout=log,
                                    stderr=subprocess.STDOUT, check=False)
        results.append({'argv': command, 'returncode': result.returncode})
        if result.returncode != 0:
            record('FINISH.json', 'STOPPED_CONSUMER_FAILURE', commands=results,
                   automatic_retry=False)
            return 1
    # The one-shot analysis claim contains the exact unique receipt token.
    claim = json.loads((ROOT / 'graphify-out/pr395-native-tq-analysis-2026-10-10/'
                        'RUN_STARTED_ONCE.json').read_text())
    capture_receipt = ROOT / ('harness/evidence/pr395_tq_state_capture_2026-10-10/'
                              f'RESULT_{claim["run_token"]}.json')
    if pinned != {str(p): digest(p) for p in CONSUMERS}:
        record('FINISH.json', 'STOPPED_CONSUMER_SOURCE_CHANGED', commands=results,
               automatic_retry=False)
        return 1
    command = [str(PYTHON), str(CONSUMERS[4]), '--capture-receipt', str(capture_receipt),
               '--output', str(ROOT / 'graphify-out/pr396-saved-state-diagnostic/private/DIAGNOSTIC.json')]
    with (JOB / 'consumer_2.log').open('xb') as log:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=log,
                                stderr=subprocess.STDOUT, check=False)
    results.append({'argv': command, 'returncode': result.returncode,
                    'additional_model_or_rttov_calls': 0})
    if result.returncode != 0:
        record('FINISH.json', 'ANALYSIS_RETURNED_DIAGNOSTIC_FAILED', commands=results,
               automatic_retry=False, accepted_analysis_receipt_preserved=True)
        return 1
    record('FINISH.json', 'CONSUMERS_RETURNED', commands=results,
           scientific_acceptance=False, automatic_retry=False)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
