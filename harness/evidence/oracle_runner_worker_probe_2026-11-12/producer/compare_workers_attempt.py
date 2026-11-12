#!/usr/bin/env python3
"""Run only the three slowest #584 normal-mode suites with one/two workers."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import sys
import time

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from harness import run_oracle_evidence_suites as runner

SUITES=['harness/evidence/native_nr16_vjp_fd_2026-11-06','harness/evidence/native_d1_coeres_upstream_cpp_ad_2026-11-10','harness/evidence/native_nc16_fd_expanded_2026-11-06']
HERE=Path(__file__).resolve().parent
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()

def evidence_hashes():
    result={}
    for suite in SUITES:
        for p in sorted((ROOT/suite).rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc':result[str(p.relative_to(ROOT))]=sha(p)
    return result

def outcomes(text,suite):
    segment=text.split(f'[normal] BEGIN {suite}\n',1)[1].split(f'\n[normal] END {suite}',1)[0]
    lines=[]
    for line in segment.splitlines():
        match=re.match(r'^(.*?) \.\.\. (ok|skipped .+|FAIL|ERROR)$',line)
        if match:lines.append({'test':match.group(1),'outcome':match.group(2)})
    return sorted(lines,key=lambda x:x['test'])

def main():
    for name in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OMP_THREAD_LIMIT'):os.environ[name]='1'
    os.environ.pop('PYTHONOPTIMIZE',None); registry=runner.REGISTRY;config=json.loads(registry.read_text()); hints=config['timing_hints_seconds']['normal']; allowed=config['allowed_skips']; assert all(s in runner.read_registry() for s in SUITES)
    files=evidence_hashes();pins={'runner':sha(ROOT/'harness/run_oracle_evidence_suites.py'),'registry':sha(registry),'python':sha(Path(sys.executable).resolve()),'experiment_script':sha(__file__),'suite_files':files}
    import torch,numpy
    versions={'python':sys.version,'executable':sys.executable,'platform':platform.platform(),'machine':platform.machine(),'torch':torch.__version__,'numpy':numpy.__version__}
    records=[]
    for workers in (1,2):
        result_path=HERE/f'workers_{workers}.json';log_path=HERE/f'workers_{workers}.log'; assert not result_path.exists() and not log_path.exists()
        t=time.monotonic()
        with log_path.open('w') as log,contextlib.redirect_stdout(log):
            success=runner.run(SUITES,'normal',result_path,workers=workers,hints=hints,allowed_skips=allowed)
        result=json.loads(result_path.read_text()); log=log_path.read_text();checks={s:outcomes(log,s) for s in SUITES}
        for row in result['suites']:
            assert len(checks[row['suite']])==row['tests'],(row['suite'],len(checks[row['suite']]),row['tests'])
        records.append({'workers':workers,'success':success,'outer_wall_seconds':time.monotonic()-t,'runner_result':result,'test_outcomes':checks,'result_sha256':sha(result_path),'log_sha256':sha(log_path)})
    assert pins['runner']==sha(ROOT/'harness/run_oracle_evidence_suites.py') and pins['registry']==sha(registry) and files==evidence_hashes(), 'sources changed during measurement'
    parity={s:records[0]['test_outcomes'][s]==records[1]['test_outcomes'][s] for s in SUITES}
    report={'schema':'kdm6.oracle_evidence_worker_comparison.v1','scope':'Only three #584 normal-mode slowest suites; local macOS, not hosted Ubuntu; sequential 1 then 2 workers; one sample each','suite_selection_basis':'#584 recorded normal timing hints: 62.651, 42.251, 33.663 seconds','threads':{'OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','OMP_THREAD_LIMIT':'1'},'toolchain':versions,'hashes':pins,'results':records,'test_outcome_parity_by_suite':parity,'limitations':'Single local sample per setting; timings include startup and contention, no hosted CI or full-suite performance claim.'}
    path=HERE/'worker_comparison.json';assert not path.exists();path.write_text(json.dumps(report,indent=2)+'\n');print('report',sha(path));print('parity',parity);print('wall',[(r['workers'],r['runner_result']['wall_seconds']) for r in records])
    if not all(parity.values()) or not all(r['success'] for r in records):raise SystemExit(1)
if __name__=='__main__':main()
