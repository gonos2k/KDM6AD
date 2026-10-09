from pathlib import Path
import os, subprocess, signal, time, json, hashlib, shutil
ROOT=Path(__file__).resolve().parent
OLD=Path('/private/tmp/KDM6AD-review388389-resolution-20261008/graphify-out/review-local/exit_observer')
RUNNER=Path('/private/tmp/KDM6AD-viirs-observation-context-20261007/harness/run_ss_case.py')
WRF=Path('/private/tmp/KDM6AD-viirs-native-run-20261007/isolated_project/host/KIM-meso_v1.0/main/wrf.exe')
LIB=Path('/private/tmp/KDM6AD-viirs-native-run-20261007/isolated_project/libtorch/install/lib/libkdm6_c.2.0.0.dylib')
OBSERVER=OLD/'observer.dylib'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
pins={str(p):sha(p) for p in (RUNNER,WRF,LIB,OBSERVER)}
rows=[]
for label in ('without_observer','with_observer'):
    case=ROOT/label
    case.mkdir()
    for p in (OLD/'case40').iterdir():
        if p.name=='namelist.input':shutil.copy2(p,case/p.name)
        elif p.is_symlink(): (case/p.name).symlink_to(p.resolve())
    env=os.environ.copy();env.pop('DYLD_INSERT_LIBRARIES',None)
    for k in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OMP_THREAD_LIMIT','VECLIB_MAXIMUM_THREADS'):env[k]='1'
    if label=='with_observer':
        wrapper=case/'launcher';wrapper.mkdir()
        launch=wrapper/'mpirun'
        launch.write_text('#!/usr/bin/env python3\nimport os,sys\nos.execv("/opt/homebrew/bin/mpirun",["/opt/homebrew/bin/mpirun","-x",'+repr('DYLD_INSERT_LIBRARIES='+str(OBSERVER))+']+sys.argv[1:])\n')
        launch.chmod(0o755);env['PATH']=str(wrapper)+os.pathsep+env['PATH']
    cmd=['/opt/homebrew/bin/python3',str(RUNNER),'--case',str(case),'--mp','337','--minutes','0','--seconds','20','--history','0','--history-s','20','--np','1','--label','pr390_'+label]
    began=time.monotonic();deadline=False
    with (case/'outer.log').open('w') as out:
        proc=subprocess.Popen(cmd,env=env,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
        try:rc=proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            deadline=True;os.killpg(proc.pid,signal.SIGTERM)
            try:rc=proc.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);rc=proc.wait(timeout=5)
    markers=[]
    for p in case.rglob('*'):
        if p.is_file() and not p.is_symlink() and (p.suffix=='.stdout' or p.name.startswith('rsl.')):
            for line in p.read_text(errors='replace').splitlines():
                if any(s in line for s in ('KDM_EXIT_OBSERVER','SUCCESS COMPLETE WRF','STARTING WRF','Timing for main:','MPI_FINALIZE')):markers.append({'file':str(p.relative_to(case)),'line':line})
    rows.append({'label':label,'command':cmd,'deadline_seconds':60,'stopped_by_deadline':deadline,'outer_returncode':rc,'elapsed_seconds':time.monotonic()-began,'markers':markers,'case_path':str(case),'namelist_sha256_after':sha(case/'namelist.input'),'run_receipts':[str(p) for p in case.rglob('summary.json')]})
    receipt={'schema':'pr390_bounded_host_pair_v1','scope':'20 model seconds one rank/one thread, 60s wall per fresh case; not historical target reproduction','pins_before':pins,'pins_after':{p:sha(Path(p)) for p in pins},'attempts':rows,'historical_native_run_valid':False}
    (ROOT/'result.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'label':label,'rc':rc,'deadline':deadline,'marker_count':len(markers)}),flush=True)
