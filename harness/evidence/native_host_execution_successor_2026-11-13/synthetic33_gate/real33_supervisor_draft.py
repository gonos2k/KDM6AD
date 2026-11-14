"""REVIEW-ONLY wiring sketch. EXECUTION IS HARD-DISABLED.

No DSO load/model call is permitted from this module. The eventual supervisor
must use watchdog.py's direct-parent unreaped leader and group cleanup, and an
independent witness must audit actual loaded images and the entire journal.
"""
import os,pathlib
import fixture33
from real33_contract import preflight
EXECUTION_ENABLED=False

def prepare(outdir):
    contract=preflight();rows=fixture33.plan();target=pathlib.Path(outdir).resolve(strict=True)
    if len(rows)!=33 or any(x['state']!='UNSTARTED' for x in rows):raise RuntimeError('invalid fixed inventory')
    return {'status':'DRAFT_BLOCKED','scope':'synthetic; watchdog survival and no setsid escape assumed','output_dir':str(target),'contract':contract,'calls':rows,'limits':{'wall_seconds':900,'rss_bytes':4*1024**3,'forwards':33,'graph_primal':3,'jvp':6,'vjp':3,'serialized_total_bytes':4*1024**3,'serialized_call_bytes':128*1024**2}}

def child_after_fork(ready_fd,release_fd,outdir):
    # Real code is intentionally unreachable until a separate reviewed change.
    # When authorized, child establishes a new session; watchdog verifies
    # pid==pgid and writes ARMED before it releases this exact pipe.
    if not EXECUTION_ENABLED:raise RuntimeError('real worker release disabled')
    os.setsid()
    os.set_inheritable(ready_fd,True);os.set_inheritable(release_fd,True)
    from real33_contract import preflight
    interpreter=preflight()['interpreter']
    env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','TMPDIR':'/tmp','LC_ALL':'C',
         'OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','OMP_THREAD_LIMIT':'1','OPENBLAS_NUM_THREADS':'1',
         'DYLD_PRINT_LIBRARIES':'1','PYTHONUNBUFFERED':'1',
         'RESEARCH_PRIVATE_MANIFEST':os.environ['RESEARCH_PRIVATE_MANIFEST'],'RESEARCH_MANIFEST_SHA256':os.environ['RESEARCH_MANIFEST_SHA256'],'RESEARCH_READY_FD':str(ready_fd),'RESEARCH_RELEASE_FD':str(release_fd),'RESEARCH_OUTDIR':str(outdir)}
    os.execve(interpreter,[interpreter,str(pathlib.Path(__file__).resolve().parent/'real33_entry.py')],env)
