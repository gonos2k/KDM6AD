"""Darwin fake-only process-group watchdog; NOT AUTHORIZED TO RUN KDM OR DSOS.

The watchdog is the worker leader's direct parent and never reaps that PID
until group termination is complete. It cannot stop setsid escapes or survive
its own SIGKILL. No completion witness or model interface is implemented.
"""
import ctypes, errno, json, math, os, pathlib, select, signal, time, subprocess, hashlib, sys

ENABLE_REAL33=False
_CANCEL=[]
class WorkerExitedDuringSample(RuntimeError):pass
def _cancel(sig,frame): _CANCEL.append(sig)
def atomic(path,obj):
    path=pathlib.Path(path);tmp=path.with_name(path.name+'.tmp')
    with open(tmp,'x') as f:
        json.dump(obj,f,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)
    fd=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
def alive(pgid):
    try:os.killpg(pgid,0);return True
    except ProcessLookupError:return False
class ProcBSDInfo(ctypes.Structure):
    _fields_=[(name,ctypes.c_uint32) for name in ('flags','status','xstatus','pid','ppid','uid','gid','ruid','rgid','svuid','svgid','rfu')]+[('comm',ctypes.c_char*16),('name',ctypes.c_char*32)]+[(name,ctypes.c_uint32) for name in ('nfiles','pgid','pjobc','tdev','tpgid')]+[('nice',ctypes.c_int32),('start_sec',ctypes.c_uint64),('start_usec',ctypes.c_uint64)]
def process_start(pid):
    libc=ctypes.CDLL(None,use_errno=True); fn=libc.proc_pidinfo
    fn.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_uint64,ctypes.c_void_p,ctypes.c_int];fn.restype=ctypes.c_int
    obj=ProcBSDInfo(); n=fn(pid,3,0,ctypes.byref(obj),ctypes.sizeof(obj))
    if n!=ctypes.sizeof(obj) or obj.pid!=pid or not obj.start_sec: raise RuntimeError('supervisor identity unavailable')
    return (obj.start_sec,obj.start_usec)
def checked_rss_sample(reservation,sample,deadline):
    if time.monotonic()>=deadline or _CANCEL:raise RuntimeError('sample cancelled or deadline')
    before=reservation()
    if before[0]!='alive':raise WorkerExitedDuringSample('worker exited before RSS sample')
    rss=sample()
    if type(rss) is not int or rss<=0:raise RuntimeError('invalid nonpositive RSS sample')
    after=reservation()
    if after!=before:
        if after==('exited_reserved',before[1]):raise WorkerExitedDuringSample('worker exited during RSS sample')
        raise RuntimeError('worker identity changed during RSS sample')
    if time.monotonic()>=deadline or _CANCEL:raise RuntimeError('sample cancelled or deadline')
    return rss

def release_refusal(supervisor_pid,supervisor_start,life_fd,deadline):
    """Last observation before release; caller holds TERM/INT blocked."""
    if _CANCEL or signal.sigpending() & {signal.SIGTERM,signal.SIGINT}:return 'cancelled'
    if time.monotonic()>=deadline:return 'timeout'
    try:
        if process_start(supervisor_pid)!=tuple(supervisor_start):return 'supervisor_identity_changed'
        readable,_,_=select.select([life_fd],[],[],0)
        if readable:
            return 'supervisor_pipe_eof' if os.read(life_fd,1)==b'' else 'unexpected_liveness_data'
    except (OSError,RuntimeError,ValueError):return 'supervisor_unavailable'
    # Linearization point: signal, deadline and liveness have been observed.
    # Events after this observation are handled as post-release cancellation.
    if _CANCEL or signal.sigpending() & {signal.SIGTERM,signal.SIGINT}:return 'cancelled'
    if time.monotonic()>=deadline:return 'timeout'
    return None

def leader_exited(pid):
    # Darwin siginfo_t: si_pid is fourth 32-bit int. WNOWAIT preserves PID.
    libc=ctypes.CDLL(None,use_errno=True);libc.waitid.argtypes=[ctypes.c_int,ctypes.c_uint,ctypes.c_void_p,ctypes.c_int];libc.waitid.restype=ctypes.c_int
    buf=ctypes.create_string_buffer(512)
    if libc.waitid(os.P_PID,pid,buf,os.WEXITED|os.WNOWAIT|os.WNOHANG):raise OSError(ctypes.get_errno(),'waitid')
    return ctypes.c_int.from_buffer(buf,12).value==pid

def worker_reservation(pid,worker_start,deadline=None):
    """Reobserve WNOWAIT briefly if exit races the start-time lookup."""
    if leader_exited(pid):return ('exited_reserved',worker_start)
    try:current=process_start(pid)
    except (OSError,RuntimeError):
        # proc_pidinfo can stop reporting just before waitid exposes exit.
        # Preserve the child reservation, never infer exit from lookup failure,
        # and fail closed if the short observation window is exhausted.
        until=time.monotonic()+.5
        if deadline is not None:until=min(until,deadline)
        while True:
            if leader_exited(pid):return ('exited_reserved',worker_start)
            left=until-time.monotonic()
            if left<=0:raise
            time.sleep(min(.01,left))
    if current!=worker_start:raise RuntimeError('worker start changed')
    return ('alive',current)

def reapable(pid,deadline=None):
    limit=time.monotonic()+3.0
    if deadline is not None:limit=min(limit,deadline)
    deadline=limit
    while time.monotonic()<deadline:
        if leader_exited(pid):return
        time.sleep(.02)
    raise TimeoutError('leader exit unobserved; no reap')

def other_members(pid,timeout=10.0):
    report=subprocess.run(['/bin/ps','-A','-o','pid=,pgid=,stat='],capture_output=True,text=True,check=True,timeout=timeout)
    rows=[]
    for line in report.stdout.splitlines():
        if not line.strip():continue
        row=line.split()
        if len(row)!=3:raise ValueError('malformed process census')
        try:process,group=int(row[0]),int(row[1])
        except ValueError:raise ValueError('malformed process census')
        rows.append((process,group,row[2]))
    if not any(process==pid and group==pid for process,group,_ in rows):raise ValueError('leader missing from process census')
    return [(process,group,state) for process,group,state in rows if group==pid and process!=pid]

EPERM_RECHECK_SECONDS=1.0
EPERM_RECHECK_INTERVAL=.05

def cleanup(pid,record=None,members_check=None,whole_deadline=None):
    check_members=other_members if members_check is None else members_check
    errors=[]
    def checked_time():
        if whole_deadline is not None and time.monotonic()>=whole_deadline:raise TimeoutError('cleanup total deadline expired')
    def members_at(limit=None):
        bound=whole_deadline if limit is None else limit if whole_deadline is None else min(limit,whole_deadline)
        if bound is None:return check_members(pid)
        remaining=bound-time.monotonic()
        if remaining<=0:raise TimeoutError('cleanup census deadline expired')
        if members_check is None:return check_members(pid,timeout=min(10.,remaining))
        return check_members(pid,deadline=bound)
    def reap():
        checked_time()
        child,status=os.waitpid(pid,0)
        if record is not None:record.update(worker_reaped_pid=child,worker_wait_status=status)
    def reap_reconciled():
        try:
            reap()
        except (OSError,TimeoutError) as exc:
            errors.append('reconciled reap: '+repr(exc))
        return errors
    eperm_deadline=None
    def denied_but_exited_empty(exc,operation):
        nonlocal eperm_deadline
        if not isinstance(exc,PermissionError) and getattr(exc,'errno',None)!=errno.EPERM:
            errors.append(repr(exc));return False
        if eperm_deadline is None:
            eperm_deadline=time.monotonic()+EPERM_RECHECK_SECONDS
            if whole_deadline is not None:eperm_deadline=min(eperm_deadline,whole_deadline)
        observations=[]
        if record is not None:record.setdefault('eperm_observations',[]).append({'operation':operation,'attempts':observations})
        while True:
            remaining=eperm_deadline-time.monotonic()
            if remaining<=0 and observations:break
            if remaining<=0 and whole_deadline is not None:break
            sample={'leader_before':None,'members':None,'leader_after':None}
            try:
                sample['leader_before']=leader_exited(pid)
                members=members_at(eperm_deadline) if whole_deadline is not None or remaining>0 else (check_members(pid,timeout=.001) if members_check is None else check_members(pid,deadline=eperm_deadline))
                if not isinstance(members,(list,tuple)):raise ValueError('invalid group inventory')
                sample['members']=members
                sample['leader_after']=leader_exited(pid)
                if type(sample['leader_before']) is not bool or type(sample['leader_after']) is not bool:raise ValueError('invalid reservation state')
                observations.append(sample)
                if sample['leader_before'] and not members and sample['leader_after']:
                    return True
            except (OSError,subprocess.SubprocessError,ValueError,RuntimeError,TimeoutError) as check_error:
                sample['error']=repr(check_error);observations.append(sample)
                errors.append('EPERM recheck: '+repr(check_error));break
            remaining=eperm_deadline-time.monotonic()
            if remaining<=0:break
            time.sleep(min(EPERM_RECHECK_INTERVAL,remaining))
        errors.append('EPERM '+operation+' unresolved: '+repr(exc)+' observations='+repr(observations[-1:]));return False
    # A cleanly exited single-member group can yield killpg EPERM on Darwin.
    # Inspect the still-reserved group before any signal and never treat EPERM as absence.
    try:
        if leader_exited(pid):
            members=members_at()
            if not isinstance(members,(list,tuple)):raise ValueError('invalid group inventory')
            if not members and leader_exited(pid):
                reap();return []
    except (OSError,subprocess.SubprocessError,ValueError,RuntimeError) as e:
        errors.append(repr(e))  # Failure remains incomplete; still try to kill owned group.
    try:os.killpg(pid,signal.SIGTERM)
    except ProcessLookupError:pass
    except OSError as e:
        if denied_but_exited_empty(e,'SIGTERM') and not errors:
            return reap_reconciled()
    deadline=time.monotonic()+.3
    if whole_deadline is not None:deadline=min(deadline,whole_deadline)
    while time.monotonic()<deadline:
        try:
            if not alive(pid):break
        except OSError as e:
            if denied_but_exited_empty(e,'probe') and not errors:
                return reap_reconciled()
            break
        time.sleep(.02)
    try:os.killpg(pid,signal.SIGKILL)
    except ProcessLookupError:pass
    except OSError as e:
        if denied_but_exited_empty(e,'SIGKILL') and not errors:
            return reap_reconciled()
    # Keep the direct child unreaped while checking the owned group. Never probe
    # the numeric group ID after reap, when reuse could redirect the query.
    try:
        if whole_deadline is None:reapable(pid)
        else:reapable(pid,deadline=whole_deadline)
        until=time.monotonic()+2
        if whole_deadline is not None:until=min(until,whole_deadline)
        while True:
            members=members_at(until)
            if not isinstance(members,(list,tuple)):raise ValueError('invalid group inventory')
            if not members:break
            if time.monotonic()>=until:
                errors.append('residual group members: '+repr(members));break
            time.sleep(.02)
        if not errors:reap()
    except (OSError,subprocess.SubprocessError,ValueError,TimeoutError,RuntimeError) as e:errors.append(repr(e))
    return errors

def pre_ready_cleanup(pid, record=None, whole_deadline=None):
    """Freeze the unreaped direct child, then choose safe group or PID cleanup.

    A stop/exit observation uses WNOWAIT, preserving PID ownership. If group
    identity cannot be established, leave the child unreaped and report failure.
    Descendants that escaped the owned group are outside this contract.
    """
    try:
        try:os.kill(pid,signal.SIGSTOP)
        except ProcessLookupError:pass
        libc=ctypes.CDLL(None,use_errno=True)
        libc.waitid.argtypes=[ctypes.c_int,ctypes.c_uint,ctypes.c_void_p,ctypes.c_int];libc.waitid.restype=ctypes.c_int
        deadline=time.monotonic()+2.
        if whole_deadline is not None:deadline=min(deadline,whole_deadline)
        while True:
            buf=ctypes.create_string_buffer(512)
            if libc.waitid(os.P_PID,pid,buf,os.WEXITED|os.WSTOPPED|os.WNOWAIT|os.WNOHANG):
                raise OSError(ctypes.get_errno(),'pre-ready waitid')
            observed=ctypes.c_int.from_buffer(buf,12).value
            if observed==pid:break
            if observed!=0:raise RuntimeError('unexpected pre-ready child')
            if time.monotonic()>=deadline:raise TimeoutError('pre-ready stop/exit not observed')
            time.sleep(.02)
        group=os.getpgid(pid)
        if group==pid:
            return cleanup(pid,record) if whole_deadline is None else cleanup(pid,record,whole_deadline=whole_deadline)
        # The stopped, unreaped child has not formed its own group. Do not
        # signal the parent's group; only the owned child PID is targeted.
        try:os.kill(pid,signal.SIGKILL)
        except ProcessLookupError:pass
        if whole_deadline is None:reapable(pid)
        else:reapable(pid,deadline=whole_deadline)
        if whole_deadline is not None and time.monotonic()>=whole_deadline:raise TimeoutError('pre-ready cleanup total deadline expired')
        child,status=os.waitpid(pid,0)
        if record is not None:record.update(worker_reaped_pid=child,worker_wait_status=status)
        return []
    except (OSError,subprocess.SubprocessError,ValueError,TimeoutError,RuntimeError) as exc:
        return ['pre-ready cleanup unresolved: '+repr(exc)]


def validate_real_census_config(manifest_path,manifest_sha,package,inventory):
    """Bind provider arguments to the separately pinned private manifest."""
    if type(manifest_sha) is not str or len(manifest_sha)!=64 or any(c not in '0123456789abcdef' for c in manifest_sha):raise ValueError('independent manifest SHA required')
    path=pathlib.Path(manifest_path)
    if not path.is_absolute() or path.is_symlink() or not path.is_file() or path.stat().st_size>2*1024*1024:raise ValueError('private manifest path')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=manifest_sha:raise ValueError('private manifest SHA')
    def unique(pairs):
        data={}
        for key,value in pairs:
            if key in data:raise ValueError('duplicate manifest key')
            data[key]=value
        return data
    value=json.loads(raw,object_pairs_hook=unique)
    if value.get('schema')!='kdm6.synthetic33.private.v1' or value.get('status')!='REVIEWED_PINNED':raise ValueError('private manifest status')
    config=value.get('census_provider')
    if type(config) is not dict or set(config)!={'package','inventory','inventory_sha256'}:raise ValueError('missing census provider pins')
    if not isinstance(package,pathlib.Path) or not package.is_absolute() or package!=package.resolve(strict=True) or str(package)!=config['package']:raise ValueError('census package binding')
    if type(inventory) is not dict or not inventory or inventory!=config['inventory']:raise ValueError('census inventory binding')
    encoded=json.dumps(inventory,sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')
    if hashlib.sha256(encoded).hexdigest()!=config['inventory_sha256']:raise ValueError('census inventory SHA')
    return {'package':package,'inventory':dict(inventory),'manifest_sha256':manifest_sha}

def _valid_start_identity(value):
    return type(value) is tuple and len(value)==2 and all(type(x) is int for x in value) and value[0]>0 and 0<=value[1]<1000000


class RealLaunchCapability:
    """Process-local, one-shot consistency guard; not proof of independent approval."""
    def __init__(self,*,manifest_path,approved_sha,dso_sha256,run_nonce,supervisor_pid,supervisor_start,output_dir,package,inventory,deadline,execution_deadline):
        if type(supervisor_pid) is not int or supervisor_pid<=0 or supervisor_pid!=os.getpid():raise ValueError('issuer/supervisor PID')
        if not _valid_start_identity(supervisor_start) or process_start(supervisor_pid)!=supervisor_start:raise ValueError('supervisor start identity')
        if type(run_nonce) is not str or len(run_nonce)!=64 or any(c not in '0123456789abcdef' for c in run_nonce):raise ValueError('run nonce')
        if type(dso_sha256) is not str or len(dso_sha256)!=64 or any(c not in '0123456789abcdef' for c in dso_sha256):raise ValueError('DSO SHA')
        if type(deadline) not in (int,float) or not math.isfinite(deadline) or not 0<deadline-time.monotonic()<=900:raise ValueError('capability deadline')
        if type(execution_deadline) not in (int,float) or not math.isfinite(execution_deadline) or execution_deadline<=time.monotonic() or deadline-execution_deadline!=28:raise ValueError('capability execution/cleanup deadline')
        self.manifest_path=pathlib.Path(manifest_path)
        self.approved_sha=approved_sha;self.dso_sha256=dso_sha256;self.run_nonce=run_nonce
        self.supervisor_pid=supervisor_pid;self.supervisor_start=supervisor_start
        self.output_dir=pathlib.Path(output_dir);self.package=package;self.inventory=dict(inventory)
        self.deadline=deadline;self.execution_deadline=execution_deadline;self.state='ISSUED';self.watchdog_pid=None;self.watchdog_start=None;self.worker_pid=None;self.worker_start=None
        self._verify_pins()
    def _verify_pins(self):
        if time.monotonic()>=self.execution_deadline:raise RuntimeError('capability execution deadline expired')
        if not self.output_dir.is_absolute() or self.output_dir.is_symlink() or self.output_dir.resolve(strict=True)!=self.output_dir or not self.output_dir.is_dir():raise ValueError('capability output directory')
        nonce_file=self.output_dir/'run_nonce'
        if nonce_file.is_symlink() or not nonce_file.is_file() or nonce_file.stat().st_size!=64 or nonce_file.read_text()!=self.run_nonce:raise ValueError('nonce file binding')
        validate_real_census_config(self.manifest_path,self.approved_sha,self.package,self.inventory)
        raw=self.manifest_path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=self.approved_sha:raise ValueError('private manifest changed')
        doc=json.loads(raw)
        if doc.get('dso_sha256')!=self.dso_sha256:raise ValueError('manifest DSO binding')
        budgets=doc.get('budgets')
        if type(budgets) is not dict or type(budgets.get('cleanup_reserve_seconds')) is not int or budgets['cleanup_reserve_seconds']!=28:raise ValueError('manifest cleanup reserve')
        wall=budgets.get('wall_seconds')
        if type(wall) not in (int,float) or not math.isfinite(wall) or not 28<wall<=900 or self.deadline-time.monotonic()>wall:raise ValueError('manifest wall budget')
    def consume_pre_fork(self,*,supervisor_pid,supervisor_start,manifest_path,approved_sha,run_nonce,output_dir,package,inventory,deadline,total_deadline):
        if self.state!='ISSUED':raise RuntimeError('capability already consumed')
        self.state='PRE_FORK_REJECTED'
        if os.getppid()!=self.supervisor_pid or os.getpid()==self.supervisor_pid:raise RuntimeError('watchdog parent identity')
        if (supervisor_pid,supervisor_start,pathlib.Path(manifest_path),approved_sha,run_nonce,pathlib.Path(output_dir),package,inventory)!=(self.supervisor_pid,self.supervisor_start,self.manifest_path,self.approved_sha,self.run_nonce,self.output_dir,self.package,self.inventory):raise ValueError('capability binding')
        if type(deadline) not in (int,float) or not math.isfinite(deadline) or deadline!=self.execution_deadline or total_deadline!=self.deadline or deadline<=time.monotonic():raise ValueError('watchdog deadline binding')
        self._verify_pins()
        self.watchdog_pid=os.getpid();self.watchdog_start=process_start(self.watchdog_pid);self.state='PRE_FORK_CONSUMED'
    def check_worker_fork(self):
        if self.state!='PRE_FORK_CONSUMED' or self.watchdog_pid!=os.getpid():raise RuntimeError('capability fork state')
        if process_start(self.watchdog_pid)!=self.watchdog_start:raise RuntimeError('watchdog identity changed')
        self._verify_pins()
    def verify_child(self,*,manifest_path,approved_sha,run_nonce,output_dir):
        if self.state!='PRE_FORK_CONSUMED' or self.watchdog_pid!=os.getppid():raise RuntimeError('child capability identity')
        self.state='CHILD_REJECTED'
        if process_start(self.watchdog_pid)!=self.watchdog_start:raise RuntimeError('child watchdog identity changed')
        if (pathlib.Path(manifest_path),approved_sha,run_nonce,pathlib.Path(output_dir))!=(self.manifest_path,self.approved_sha,self.run_nonce,self.output_dir):raise ValueError('child capability binding')
        self._verify_pins();self.state='CHILD_CONSUMED'
    def arm(self,worker_pid,worker_start):
        if self.state!='PRE_FORK_CONSUMED' or self.watchdog_pid!=os.getpid():raise RuntimeError('capability arm state')
        self.state='ARM_REJECTED'
        if process_start(self.watchdog_pid)!=self.watchdog_start:raise RuntimeError('watchdog identity changed')
        if type(worker_pid) is not int or worker_pid<=0 or worker_pid in (self.watchdog_pid,self.supervisor_pid) or not _valid_start_identity(worker_start):raise ValueError('worker identity')
        if worker_reservation(worker_pid,worker_start,self.execution_deadline)!=('alive',worker_start):raise RuntimeError('worker reservation changed')
        self._verify_pins();self.worker_pid=worker_pid;self.worker_start=worker_start;self.state='ARMED'
    def consume_release(self,worker_pid,worker_start):
        if self.state!='ARMED' or self.watchdog_pid!=os.getpid():raise RuntimeError('capability release state')
        self.state='RELEASE_REJECTED'
        if process_start(self.watchdog_pid)!=self.watchdog_start:raise RuntimeError('watchdog identity changed')
        if (worker_pid,worker_start)!=(self.worker_pid,self.worker_start):raise RuntimeError('capability worker identity')
        self._verify_pins();self.state='RELEASE_CONSUMED'


def issue_real_capability(**kwargs):
    """Create a guard from separately approved inputs; never grants authorization."""
    return RealLaunchCapability(**kwargs)

def fake_plan():
    rows=[]
    for case in ('baseline','warm_vertical','ice_vertical'):
        slots=[('off',None),('on',None),('graph',None)]
        for direction in ('nc','th'):
            for step in (1,2):
                for sign in (-1,1):slots.append(('endpoint',[direction,step,sign]))
        for mode,detail in slots:
            ident={'seq':len(rows)+1,'fixture':case,'mode':mode,'detail':detail}
            digest=hashlib.sha256(json.dumps(ident,sort_keys=True).encode()).hexdigest()
            rows.append({**ident,'fake_input_sha256':digest,'state':'UNSTARTED'})
    return rows
def validate_fake_journal(rows,events):
    result=[dict(r) for r in rows];current=0
    for e in events:
        n=e.get('seq')
        if type(n) is not int or not 1<=n<=len(result):raise ValueError('journal sequence')
        row=result[n-1]
        if any(e.get(k)!=row[k] for k in ('seq','fixture','mode','detail','fake_input_sha256')):raise ValueError('journal identity')
        state=e.get('state')
        if state=='STARTED' and row['state']=='UNSTARTED' and n==current+1:current=n
        elif state in ('COMPLETED','FAILED') and row['state']=='STARTED' and n==current:pass
        else:raise ValueError('journal state/order')
        row['state']=state
    return result
def publish_fake_witness(candidate,witness,deadline):
    """Fake-only completion marker, never execution authorization."""
    mask={signal.SIGTERM,signal.SIGINT}; old=signal.pthread_sigmask(signal.SIG_BLOCK,mask)
    try:
        if _CANCEL or signal.sigpending() & mask or time.monotonic()>deadline:raise RuntimeError('cancelled or late')
        value=json.loads(pathlib.Path(candidate).read_text())
        if value.get('schema')!='FAKE_ONLY_NO_EXECUTION_AUTHORITY' or any(x['state']!='COMPLETED' for x in validate_fake_journal(fake_plan(),value['events'])):raise RuntimeError('incomplete fake journal')
        os.link(candidate,witness)
        if _CANCEL or signal.sigpending() & mask or time.monotonic()>deadline:
            os.unlink(witness);raise RuntimeError('cancelled or late during link')
        fd=os.open(pathlib.Path(witness).parent,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK,old)

def group_rss_kib(pid):
    r=subprocess.run(['/bin/ps','-A','-o','pid=,pgid=,rss='],capture_output=True,text=True,check=True,timeout=10.0)
    rows=[]
    for line in r.stdout.splitlines():
        if not line.strip():continue
        row=line.split()
        if len(row)!=3:raise ValueError('malformed RSS census')
        try:p,g,rss=map(int,row)
        except ValueError:raise ValueError('malformed RSS census')
        if p<=0 or g<=0 or rss<0:raise ValueError('invalid RSS census')
        rows.append((p,g,rss))
    if not any(p==pid and g==pid for p,g,_ in rows):raise ValueError('leader missing from RSS census')
    return sum(rss for p,g,rss in rows if g==pid)

def child(worker_ready,release,scenario,mock_outdir=None):
    os.setsid();signal.signal(signal.SIGTERM,signal.SIG_IGN)
    os.write(worker_ready,b'R');os.close(worker_ready)
    if scenario in ('fixture33_exec_mock',):
        raise RuntimeError('fixture33_exec_mock must exec before ready')
    if scenario in ('fixture33_mock','fixture33_stall'):
        sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
        import real33_worker as worker
        from test_real33_worker import FakeRunner
        worker.preflight=lambda:{'dso_path':'fake-only'}
        if scenario=='fixture33_stall':
            class StalledRunner(FakeRunner):
                def _call(self,*args,**kwargs):
                    signal.signal(signal.SIGTERM,signal.SIG_IGN)
                    while True:time.sleep(1)
            worker.Runner=StalledRunner
        else:worker.Runner=FakeRunner
        try:
            result=worker.run(release,mock_outdir);atomic(pathlib.Path(mock_outdir)/'worker_result.json',result)
        except BaseException:
            import traceback;traceback.print_exc();os._exit(2)
        os._exit(0)
    if os.read(release,1)!=b'G':os._exit(98)
    os.close(release)
    if scenario=='term_ignore_descendant':
        kid=os.fork()
        if kid==0:
            signal.signal(signal.SIGTERM,signal.SIG_IGN)
            while True:time.sleep(1)
    if scenario=='fast_exit':os._exit(0)
    if scenario=='leader_exits_first':
        kid=os.fork()
        if kid==0:
            signal.signal(signal.SIGTERM,signal.SIG_IGN)
            while True:time.sleep(1)
        os._exit(0)
    while True:time.sleep(1)

def supervise(supervisor_pid,supervisor_start,life_fd,release_fd,ready_fd,receipt_path,scenario,timeout=5,max_rss_kib=8*1024*1024,mock_outdir=None,manifest_path=None,manifest_sha=None,run_nonce=None,fake_ready_timeout=10.0,fake_post_release_timeout=None,use_fake_census_helper=False,fake_census_sampler=None,use_native_census_helper=False,native_census_package=None,native_census_manifest=None,real_capability=None,execution_deadline=None,total_deadline=None):
    if scenario not in ('term_ignore_descendant','leader_exits_first','fixture33_mock','fixture33_stall','fixture33_exec_mock','fixture33_real','fast_exit'):raise ValueError('fake scenarios only')
    if scenario=='fixture33_real' and use_fake_census_helper:raise ValueError('real path requires native census helper')
    if use_fake_census_helper and use_native_census_helper:raise ValueError('conflicting helper modes')
    if scenario=='fixture33_real' and (fake_ready_timeout!=10.0 or fake_post_release_timeout is not None):raise ValueError('fake-only timing override')
    if scenario=='fixture33_real' and not ENABLE_REAL33:raise RuntimeError('real33 disabled pending Red review')
    if scenario=='fixture33_real' and not use_native_census_helper:raise RuntimeError('real path requires pinned native census helper')
    if scenario=='fixture33_real' and type(real_capability) is not RealLaunchCapability:raise RuntimeError('one-shot real capability required')
    if scenario!='fixture33_real' and real_capability is not None:raise ValueError('real capability on fake path')
    if not 0<fake_ready_timeout<=15 or (fake_post_release_timeout is not None and not 0<fake_post_release_timeout<=2):raise ValueError('invalid fake timing')
    if scenario in ('fixture33_mock','fixture33_stall','fixture33_exec_mock','fixture33_real') and not mock_outdir:raise ValueError('fake output directory required')
    if type(timeout) not in (int,float) or not math.isfinite(timeout) or timeout<=0:raise ValueError('invalid watchdog timeout')
    started=time.monotonic();deadline=started+timeout;cleanup_deadline=None
    if scenario=='fixture33_real':
        if (type(execution_deadline) not in (int,float) or type(total_deadline) not in (int,float)
            or not math.isfinite(execution_deadline) or not math.isfinite(total_deadline)
            or execution_deadline!=real_capability.execution_deadline or total_deadline!=real_capability.deadline
            or execution_deadline<=started or total_deadline-execution_deadline!=28):raise ValueError('real execution/cleanup deadline binding')
        deadline=execution_deadline;cleanup_deadline=total_deadline
    elif execution_deadline is not None or total_deadline is not None:raise ValueError('real deadlines on fake path')
    reservation_deadline=[deadline]
    _CANCEL.clear()
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,_cancel)
    kq=select.kqueue();pid=None;group_ready=False;trace=None;helper=None;ar=aw=gr=gw=None;result={'status':'INCOMPLETE','scope':'fake only; no KDM, DSO or execution witness','reason':None,'worker_pid':None,'cleanup_errors':[],'released':False,'signals':[],'fake_33_call_inventory':fake_plan(),'peak_group_rss_kib':0}
    try:
        if scenario=='fixture33_real':
            sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
            import freeze33,fixture33
            freeze33.validate_frozen(manifest_path,manifest_sha)
            validate_real_census_config(manifest_path,manifest_sha,native_census_package,native_census_manifest)
            real_capability.consume_pre_fork(supervisor_pid=supervisor_pid,supervisor_start=tuple(supervisor_start),manifest_path=manifest_path,approved_sha=manifest_sha,run_nonce=run_nonce,output_dir=mock_outdir,package=native_census_package,inventory=native_census_manifest,deadline=deadline,total_deadline=cleanup_deadline)
            result.update(scope='synthetic research execution path; provider and provenance unverified until independent witness',manifest_sha256=manifest_sha,run_nonce=run_nonce,supervisor_pid=supervisor_pid,supervisor_start=list(supervisor_start),watchdog_pid=os.getpid(),watchdog_start=list(real_capability.watchdog_start),dyld_trace_enabled=True,actual_33_call_inventory=fixture33.plan())
        if process_start(supervisor_pid)!=tuple(supervisor_start):raise RuntimeError("stale supervisor identity")
        # Register before forking; disappearance/ESRCH fails closed.
        kq.control([select.kevent(supervisor_pid,filter=select.KQ_FILTER_PROC,flags=select.KQ_EV_ADD|select.KQ_EV_ENABLE|select.KQ_EV_ONESHOT,fflags=select.KQ_NOTE_EXIT),select.kevent(life_fd,filter=select.KQ_FILTER_READ,flags=select.KQ_EV_ADD|select.KQ_EV_ENABLE),select.kevent(release_fd,filter=select.KQ_FILTER_READ,flags=select.KQ_EV_ADD|select.KQ_EV_ENABLE)],0,0)
        if process_start(supervisor_pid)!=tuple(supervisor_start):raise RuntimeError("supervisor identity changed")
        if scenario in ('fixture33_exec_mock','fixture33_real'):
            sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
            from trace33 import Trace
            trace=Trace(mock_outdir)
        if scenario=='fixture33_real':
            # The helper must initialize and verify its pinned native provider
            # before a real worker exists; failure cannot release a worker.
            sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
            from census_helper import CensusHelper,native_sampler
            sampler=native_sampler(native_census_package,native_census_manifest)
            remaining=deadline-time.monotonic()
            if remaining<=0:raise RuntimeError('native helper deadline')
            helper=CensusHelper(sampler,startup_timeout=min(10.,remaining),helper_kind='native')
            result['census_helper_mode']='PINNED_NATIVE';result['census_helper_pid']=helper.pid;result['census_latencies_seconds']=[]
        ar,aw=os.pipe();gr,gw=os.pipe()
        if scenario=='fixture33_real':
            oldmask=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM,signal.SIGINT})
            try:
                refusal=release_refusal(supervisor_pid,supervisor_start,life_fd,deadline)
                if refusal:raise RuntimeError('worker fork refused: '+refusal)
                if helper is None or helper.closed or leader_exited(helper.pid):raise RuntimeError('native helper unavailable before worker fork')
                real_capability.check_worker_fork()
                if _CANCEL or signal.sigpending() & {signal.SIGTERM,signal.SIGINT} or time.monotonic()>=deadline:raise RuntimeError('worker fork cancelled or expired')
                pid=os.fork()
            finally:signal.pthread_sigmask(signal.SIG_SETMASK,oldmask)
        else:pid=os.fork()
        if pid==0:
            try:
                os.close(ar);os.close(gw);os.close(life_fd);os.close(release_fd);os.close(ready_fd);kq.close()
                if scenario=='fixture33_real':
                    trace.bind_child_stderr()
                    import real33_supervisor_draft
                    real33_supervisor_draft.child_after_fork(aw,gr,mock_outdir,real_capability)
                    os._exit(99)
                if scenario=='fixture33_exec_mock':
                    os.setsid();os.set_inheritable(aw,True);os.set_inheritable(gr,True);trace.bind_child_stderr()
                    interpreter=sys.executable
                    root=pathlib.Path(__file__).resolve().parent.parent
                    env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','TMPDIR':'/tmp','LC_ALL':'C','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','OMP_THREAD_LIMIT':'1','OPENBLAS_NUM_THREADS':'1','PYTHONUNBUFFERED':'1','DYLD_PRINT_LIBRARIES':'1','RESEARCH_READY_FD':str(aw),'RESEARCH_RELEASE_FD':str(gr),'RESEARCH_OUTDIR':str(mock_outdir),'RESEARCH_FAKE_ONLY':'1'}
                    os.execve(interpreter,[interpreter,str(root/'real33_entry.py')],env)
                child(aw,gr,scenario,mock_outdir);os._exit(99)
            except BaseException:
                os._exit(99)
        os.close(aw);aw=None
        os.close(gr);gr=None
        if trace is not None:trace.parent_after_fork()
        # Drain stderr while awaiting readiness so dyld cannot fill the pipe.
        ready_deadline=min(deadline,time.monotonic()+fake_ready_timeout);ready=False
        while time.monotonic()<ready_deadline:
            watched=[ar]+([trace.readfd] if trace is not None and not trace.eof else [])
            readable=select.select(watched,[],[],min(.05,max(0,ready_deadline-time.monotonic())))[0]
            if trace is not None and trace.readfd in readable:trace.drain()
            if ar in readable:ready=os.read(ar,1)==b'R';break
        if not ready or os.getpgid(pid)!=pid:raise RuntimeError('worker group identity/ready timeout')
        os.close(ar);ar=None;group_ready=True;result['worker_pid']=pid
        worker_start=process_start(pid)
        if scenario=='fixture33_real':result['worker_start']=list(worker_start)
        def reservation():
            return worker_reservation(pid,worker_start,reservation_deadline[0])
        def abort_worker():
            errors=[]
            for sig in (signal.SIGTERM,signal.SIGKILL):
                try:os.killpg(pid,sig)
                except ProcessLookupError:pass
                except OSError as exc:errors.append(repr(exc))
            if errors:raise RuntimeError('worker termination denied: '+repr(errors))
        if (use_fake_census_helper or use_native_census_helper) and helper is None:
            sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
            from census_helper import CensusHelper,native_sampler
            if use_native_census_helper:
                if native_census_package is None or native_census_manifest is None:raise RuntimeError('pinned provider required')
                sampler=native_sampler(native_census_package,native_census_manifest)
            else:
                if fake_census_sampler is None:raise RuntimeError('fake sampler required')
                sampler=fake_census_sampler
            helper=CensusHelper(sampler,helper_kind='native' if use_native_census_helper else 'fake')
            result['census_helper_mode']='PINNED_NATIVE' if use_native_census_helper else 'FAKE_ONLY'
            result['census_helper_pid']=helper.pid;result['census_latencies_seconds']=[]
        def take_rss_sample():
            def measure():
                if helper is not None:
                    sample_start=time.monotonic();sample=helper.sample(pid,reservation,abort_worker,deadline) if cleanup_deadline is None else helper.sample(pid,reservation,abort_worker,deadline,cleanup_deadline=cleanup_deadline)
                    result['census_latencies_seconds'].append(time.monotonic()-sample_start)
                    result['rss_policy']='SAMPLED_STOP_THRESHOLD'
                    return (sample['rss_bytes']+1023)//1024
                return group_rss_kib(pid)
            rss=checked_rss_sample(reservation,measure,deadline)
            result['peak_group_rss_kib']=max(result['peak_group_rss_kib'],rss)
            return rss
        kq.control([select.kevent(pid,filter=select.KQ_FILTER_PROC,flags=select.KQ_EV_ADD|select.KQ_EV_ENABLE|select.KQ_EV_ONESHOT,fflags=select.KQ_NOTE_EXIT)],0,0)
        result['initial_rss_kib']=take_rss_sample()
        if result['initial_rss_kib']>max_rss_kib:raise RuntimeError('initial RSS stop threshold exceeded')
        oldmask=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM,signal.SIGINT})
        try:refusal=release_refusal(supervisor_pid,supervisor_start,life_fd,deadline)
        finally:signal.pthread_sigmask(signal.SIG_SETMASK,oldmask)
        if refusal:
            result['reason']=refusal
            raise RuntimeError('initial sample before arm: '+refusal)
        if scenario=='fixture33_real':real_capability.arm(pid,worker_start)
        armed={'status':'ARMED_UNVERIFIED' if scenario=='fixture33_real' else 'ARMED_FAKE_ONLY','supervisor_pid':supervisor_pid,'supervisor_start':supervisor_start,'worker_pid':pid,'scope':result['scope'],'fake_33_call_inventory':result['fake_33_call_inventory'],'actual_33_call_inventory':result.get('actual_33_call_inventory'),'manifest_sha256':result.get('manifest_sha256'),'run_nonce':result.get('run_nonce'),'watchdog_pid':result.get('watchdog_pid')}
        if scenario=='fixture33_real':armed.update(worker_start=list(worker_start),watchdog_start=result['watchdog_start'])
        atomic(receipt_path,armed)
        os.write(ready_fd,b'R')
        while time.monotonic()<deadline:
            if trace is not None:trace.drain()
            if _CANCEL:result['reason']='cancelled';break
            events=kq.control(None,8,min(.05,max(0,deadline-time.monotonic())))
            # Death/liveness take precedence over simultaneous release.
            if any(e.filter==select.KQ_FILTER_PROC and e.ident==supervisor_pid for e in events):result['reason']='supervisor_exit';break
            if any(e.filter==select.KQ_FILTER_READ and e.ident==life_fd for e in events):
                if os.read(life_fd,1)==b'':result['reason']='supervisor_pipe_eof';break
                result['reason']='unexpected_liveness_data';break
            if any(e.filter==select.KQ_FILTER_PROC and e.ident==pid for e in events):result['reason']='worker_exit';break
            if any(e.filter==select.KQ_FILTER_READ and e.ident==release_fd for e in events):
                if result['released'] or os.read(release_fd,1)!=b'G':result['reason']='invalid_release';break
                oldmask=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGTERM,signal.SIGINT})
                try:
                    refusal=release_refusal(supervisor_pid,supervisor_start,life_fd,deadline)
                    if refusal:result['reason']=refusal
                    else:
                        if scenario=='fixture33_real':
                            if helper is None or helper.closed or leader_exited(helper.pid):raise RuntimeError('native helper unavailable before release')
                            if reservation()!=('alive',worker_start):raise RuntimeError('worker identity unavailable before release')
                            real_capability.consume_release(pid,worker_start)
                        os.write(gw,b'G');os.close(gw);gw=None;result['released']=True;os.write(ready_fd,b'G')
                finally:signal.pthread_sigmask(signal.SIG_SETMASK,oldmask)
                if refusal:break
                if fake_post_release_timeout is not None:deadline=min(deadline,time.monotonic()+fake_post_release_timeout)
                kq.control([select.kevent(release_fd,filter=select.KQ_FILTER_READ,flags=select.KQ_EV_DELETE)],0,0)
                continue
            if helper is not None and time.monotonic()<helper.next_sample:continue
            try:rss=take_rss_sample()
            except WorkerExitedDuringSample:
                if type(result.get('initial_rss_kib')) is not int or result['initial_rss_kib']<=0:raise
                result['reason']='worker_exit';break
            if rss>max_rss_kib:result['reason']='rss_limit';break
        else:result['reason']='timeout'
    except BaseException as exc:
        if result['reason'] is None:result['reason']='cancelled' if _CANCEL else ('timeout' if time.monotonic()>=deadline else 'error:'+repr(exc))
        result['error_detail']=repr(exc)
    finally:
        if cleanup_deadline is not None:reservation_deadline[0]=cleanup_deadline
        if pid is not None and group_ready:
            def helper_members(_pid,deadline=None):
                if helper is None or helper.closed:raise RuntimeError('census helper unavailable')
                # No more than one sample per second; cleanup remains bounded.
                delay=max(0,helper.next_sample-time.monotonic())
                if delay>1:raise RuntimeError('invalid cleanup sample rate')
                if deadline is not None and time.monotonic()+delay>=deadline:raise RuntimeError('cleanup census deadline')
                if delay:time.sleep(delay)
                sample_deadline=time.monotonic()+2.
                if deadline is not None:sample_deadline=min(sample_deadline,deadline)
                sample_start=time.monotonic();sample=helper.sample(pid,reservation,abort_worker,sample_deadline) if cleanup_deadline is None else helper.sample(pid,reservation,abort_worker,sample_deadline,cleanup_deadline=cleanup_deadline)
                result['census_latencies_seconds'].append(time.monotonic()-sample_start)
                return [member for member in sample['members'] if member!=pid]
            result['cleanup_errors']=cleanup(pid,result,helper_members if helper is not None else None,whole_deadline=cleanup_deadline)
        elif pid is not None:
            result['cleanup_errors']=pre_ready_cleanup(pid,result) if cleanup_deadline is None else pre_ready_cleanup(pid,result,whole_deadline=cleanup_deadline)
        if helper is not None:
            try:helper.close() if cleanup_deadline is None else helper.close(deadline=cleanup_deadline)
            except BaseException as exc:result['cleanup_errors'].append('helper:'+repr(exc))
        for fd in (ar,aw,gr,gw,ready_fd):
            if fd is not None:
                try:os.close(fd)
                except OSError:pass
        result['signals']=list(_CANCEL)
        if trace is not None:
            try:result['exclusive_trace']=trace.snapshot()
            except BaseException as exc:result['cleanup_errors'].append('trace:'+repr(exc))
            finally:trace.close()
        kq.close()
        # Final receipt is always INCOMPLETE; it grants no execution authority.
        atomic(str(receipt_path)+'.result',result)
    return result
