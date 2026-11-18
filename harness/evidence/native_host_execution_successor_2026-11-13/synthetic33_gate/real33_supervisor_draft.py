"""REVIEW-ONLY wiring sketch. EXECUTION IS HARD-DISABLED.

No DSO load/model call is permitted from this module. The eventual supervisor
must use watchdog.py's direct-parent unreaped leader and group cleanup, and an
independent witness must audit actual loaded images and the entire journal.
"""
import math,os,pathlib
import fixture33
import selector_manifest_spec_v1 as selectors
from real33_contract import preflight
EXECUTION_ENABLED=False
CLEANUP_RESERVE_SECONDS=28

def deadline_bounds(started,wall_seconds,reserve_seconds):
    """Reserve full cleanup time within the externally pinned whole wall."""
    if type(started) not in (int,float) or not math.isfinite(started) or type(wall_seconds) not in (int,float) or not math.isfinite(wall_seconds) or type(reserve_seconds) is not int or reserve_seconds!=CLEANUP_RESERVE_SECONDS or not reserve_seconds<wall_seconds<=900:raise ValueError('invalid wall/cleanup budget')
    total=started+wall_seconds
    return {'execution_deadline':total-reserve_seconds,'total_deadline':total}


def prepare(outdir):
    contract=preflight();rows=fixture33.plan();target=pathlib.Path(outdir).resolve(strict=True)
    if len(rows)!=33 or any(x['state']!='UNSTARTED' for x in rows):raise RuntimeError('invalid fixed inventory')
    queries=selectors.query_budget(rows)
    if not fixture33.same_plan_exact(contract.get('calls')):raise RuntimeError('preflight plan mismatch')
    return {'status':'DRAFT_BLOCKED','scope':'synthetic; watchdog survival and no setsid escape assumed','output_dir':str(target),'contract':contract,'calls':rows,'limits':{'wall_seconds':900,'cleanup_reserve_seconds':CLEANUP_RESERVE_SECONDS,'rss_bytes':4*1024**3,'forwards':33,'graph_primal':queries['total']['graph_primal'],'jvp':queries['total']['jvp'],'vjp':queries['total']['vjp'],'query_per_fixture':queries['per_fixture'],'serialized_total_bytes':4*1024**3,'serialized_call_bytes':128*1024**2}}

def child_after_fork(ready_fd,release_fd,outdir,capability=None):
    # Real code is intentionally unreachable until a separate reviewed change.
    # When authorized, child establishes a new session; watchdog verifies
    # pid==pgid and writes ARMED before it releases this exact pipe.
    if not EXECUTION_ENABLED:raise RuntimeError('real worker release disabled')
    if capability is None:raise RuntimeError('one-shot watchdog capability required')
    nonce=(pathlib.Path(outdir)/'run_nonce').read_text()
    capability.verify_child(manifest_path=os.environ['RESEARCH_PRIVATE_MANIFEST'],approved_sha=os.environ['RESEARCH_MANIFEST_SHA256'],run_nonce=nonce,output_dir=outdir)
    os.setsid()
    os.set_inheritable(ready_fd,True);os.set_inheritable(release_fd,True)
    from real33_contract import preflight
    interpreter=preflight()['interpreter']
    env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','TMPDIR':'/tmp','LC_ALL':'C',
         'OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','OMP_THREAD_LIMIT':'1','OPENBLAS_NUM_THREADS':'1',
         'DYLD_PRINT_LIBRARIES':'1','PYTHONUNBUFFERED':'1',
         'RESEARCH_PRIVATE_MANIFEST':os.environ['RESEARCH_PRIVATE_MANIFEST'],'RESEARCH_MANIFEST_SHA256':os.environ['RESEARCH_MANIFEST_SHA256'],'RESEARCH_READY_FD':str(ready_fd),'RESEARCH_RELEASE_FD':str(release_fd),'RESEARCH_OUTDIR':str(outdir)}
    os.execve(interpreter,[interpreter,str(pathlib.Path(__file__).resolve().parent/'real33_entry.py')],env)
