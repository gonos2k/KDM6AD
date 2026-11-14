"""Darwin fake-only process-group watchdog; NOT AUTHORIZED TO RUN KDM OR DSOS.

The watchdog is the worker leader's direct parent and never reaps that PID
until group termination is complete. It cannot stop setsid escapes or survive
its own SIGKILL. No completion witness or model interface is implemented.
"""
import ctypes, json, os, pathlib, select, signal, time, subprocess, hashlib, sys

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

def reapable(pid):
    deadline=time.monotonic()+3.0
    while time.monotonic()<deadline:
        if leader_exited(pid):return
        time.sleep(.02)
    raise TimeoutError('leader exit unobserved; no reap')

def other_members(pid):
    report=subprocess.run(['/bin/ps','-A','-o','pid=,pgid=,stat='],capture_output=True,text=True,check=True,timeout=10.0)
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

def cleanup(pid,record=None,members_check=None):
    check_members=other_members if members_check is None else members_check
    errors=[]
    def reap():
        child,status=os.waitpid(pid,0)
        if record is not None:record.update(worker_reaped_pid=child,worker_wait_status=status)
    # A cleanly exited single-member group can yield killpg EPERM on Darwin.
    # Inspect the still-reserved group before any signal and never treat EPERM as absence.
    try:
        if leader_exited(pid) and not check_members(pid):
            reap();return []
    except (OSError,subprocess.SubprocessError,ValueError,RuntimeError) as e:
        errors.append(repr(e))  # Failure remains incomplete; still try to kill owned group.
    try:os.killpg(pid,signal.SIGTERM)
    except ProcessLookupError:pass
    except OSError as e:errors.append(repr(e))
    deadline=time.monotonic()+.3
    while time.monotonic()<deadline:
        try:
            if not alive(pid):break
        except OSError as e:
            errors.append(repr(e));break
        time.sleep(.02)
    try:os.killpg(pid,signal.SIGKILL)
    except ProcessLookupError:pass
    except OSError as e:errors.append(repr(e))
    # Keep the direct child unreaped while checking the owned group. Never probe
    # the numeric group ID after reap, when reuse could redirect the query.
    try:
        reapable(pid)
        until=time.monotonic()+2
        while True:
            members=check_members(pid)
            if not members:break
            if time.monotonic()>=until:
                errors.append('residual group members: '+repr(members));break
            time.sleep(.02)
        if not errors:reap()
    except (OSError,subprocess.SubprocessError,ValueError,TimeoutError,RuntimeError) as e:errors.append(repr(e))
    return errors

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

def supervise(supervisor_pid,supervisor_start,life_fd,release_fd,ready_fd,receipt_path,scenario,timeout=5,max_rss_kib=8*1024*1024,mock_outdir=None,manifest_path=None,manifest_sha=None,run_nonce=None,fake_ready_timeout=10.0,fake_post_release_timeout=None,use_fake_census_helper=False,fake_census_sampler=None,use_native_census_helper=False,native_census_package=None,native_census_manifest=None):
    if scenario not in ('term_ignore_descendant','leader_exits_first','fixture33_mock','fixture33_stall','fixture33_exec_mock','fixture33_real','fast_exit'):raise ValueError('fake scenarios only')
    if scenario=='fixture33_real' and (use_fake_census_helper or use_native_census_helper):raise ValueError('census helper integration is fake-scope only')
    if use_fake_census_helper and use_native_census_helper:raise ValueError('conflicting helper modes')
    if scenario=='fixture33_real' and (fake_ready_timeout!=10.0 or fake_post_release_timeout is not None):raise ValueError('fake-only timing override')
    if scenario=='fixture33_real' and not ENABLE_REAL33:raise RuntimeError('real33 disabled pending Red review')
    if not 0<fake_ready_timeout<=15 or (fake_post_release_timeout is not None and not 0<fake_post_release_timeout<=2):raise ValueError('invalid fake timing')
    if scenario in ('fixture33_mock','fixture33_stall','fixture33_exec_mock','fixture33_real') and not mock_outdir:raise ValueError('fake output directory required')
    started=time.monotonic();deadline=started+timeout
    _CANCEL.clear()
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,_cancel)
    kq=select.kqueue();pid=None;group_ready=False;trace=None;helper=None;result={'status':'INCOMPLETE','scope':'fake only; no KDM, DSO or execution witness','reason':None,'worker_pid':None,'cleanup_errors':[],'released':False,'signals':[],'fake_33_call_inventory':fake_plan(),'peak_group_rss_kib':0}
    try:
        if scenario=='fixture33_real':
            sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
            import freeze33,fixture33
            freeze33.validate_frozen(manifest_path,manifest_sha)
            result.update(manifest_sha256=manifest_sha,run_nonce=run_nonce,watchdog_pid=os.getpid(),dyld_trace_enabled=True,actual_33_call_inventory=fixture33.plan())
        if process_start(supervisor_pid)!=tuple(supervisor_start):raise RuntimeError("stale supervisor identity")
        # Register before forking; disappearance/ESRCH fails closed.
        kq.control([select.kevent(supervisor_pid,filter=select.KQ_FILTER_PROC,flags=select.KQ_EV_ADD|select.KQ_EV_ENABLE|select.KQ_EV_ONESHOT,fflags=select.KQ_NOTE_EXIT),select.kevent(life_fd,filter=select.KQ_FILTER_READ,flags=select.KQ_EV_ADD|select.KQ_EV_ENABLE),select.kevent(release_fd,filter=select.KQ_FILTER_READ,flags=select.KQ_EV_ADD|select.KQ_EV_ENABLE)],0,0)
        if process_start(supervisor_pid)!=tuple(supervisor_start):raise RuntimeError("supervisor identity changed")
        if scenario in ('fixture33_exec_mock','fixture33_real'):
            sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
            from trace33 import Trace
            trace=Trace(mock_outdir)
        ar,aw=os.pipe();gr,gw=os.pipe();pid=os.fork()
        if pid==0:
            os.close(ar);os.close(gw);os.close(life_fd);os.close(release_fd);os.close(ready_fd);kq.close()
            if scenario=='fixture33_real':
                trace.bind_child_stderr()
                import real33_supervisor_draft
                real33_supervisor_draft.child_after_fork(aw,gr,mock_outdir)
                os._exit(99)
            if scenario=='fixture33_exec_mock':
                os.setsid();os.set_inheritable(aw,True);os.set_inheritable(gr,True);trace.bind_child_stderr()
                interpreter=sys.executable
                root=pathlib.Path(__file__).resolve().parent.parent
                env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','TMPDIR':'/tmp','LC_ALL':'C','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','OMP_THREAD_LIMIT':'1','OPENBLAS_NUM_THREADS':'1','PYTHONUNBUFFERED':'1','DYLD_PRINT_LIBRARIES':'1','RESEARCH_READY_FD':str(aw),'RESEARCH_RELEASE_FD':str(gr),'RESEARCH_OUTDIR':str(mock_outdir),'RESEARCH_FAKE_ONLY':'1'}
                os.execve(interpreter,[interpreter,str(root/'real33_entry.py')],env)
            child(aw,gr,scenario,mock_outdir);os._exit(99)
        os.close(aw);os.close(gr)
        if trace is not None:trace.parent_after_fork()
        # Drain stderr while awaiting readiness so dyld cannot fill the pipe.
        ready_deadline=min(deadline,time.monotonic()+fake_ready_timeout);ready=False
        while time.monotonic()<ready_deadline:
            watched=[ar]+([trace.readfd] if trace is not None and not trace.eof else [])
            readable=select.select(watched,[],[],min(.05,max(0,ready_deadline-time.monotonic())))[0]
            if trace is not None and trace.readfd in readable:trace.drain()
            if ar in readable:ready=os.read(ar,1)==b'R';break
        if not ready or os.getpgid(pid)!=pid:raise RuntimeError('worker group identity/ready timeout')
        os.close(ar);group_ready=True;result['worker_pid']=pid
        worker_start=process_start(pid)
        def reservation():
            if leader_exited(pid):return ('exited_reserved',worker_start)
            current=process_start(pid)
            if current!=worker_start:raise RuntimeError('worker start changed')
            return ('alive',current)
        def abort_worker():
            errors=[]
            for sig in (signal.SIGTERM,signal.SIGKILL):
                try:os.killpg(pid,sig)
                except ProcessLookupError:pass
                except OSError as exc:errors.append(repr(exc))
            if errors:raise RuntimeError('worker termination denied: '+repr(errors))
        if use_fake_census_helper or use_native_census_helper:
            sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
            from census_helper import CensusHelper,native_sampler
            if use_native_census_helper:
                if native_census_package is None or native_census_manifest is None:raise RuntimeError('pinned provider required')
                sampler=native_sampler(native_census_package,native_census_manifest)
            else:
                if fake_census_sampler is None:raise RuntimeError('fake sampler required')
                sampler=fake_census_sampler
            helper=CensusHelper(sampler)
            result['census_helper_pid']=helper.pid;result['census_latencies_seconds']=[]
        def take_rss_sample():
            def measure():
                if helper is not None:
                    sample_start=time.monotonic();sample=helper.sample(pid,reservation,abort_worker,deadline)
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
        atomic(receipt_path,{'status':'ARMED_FAKE_ONLY','supervisor_pid':supervisor_pid,'supervisor_start':supervisor_start,'worker_pid':pid,'scope':result['scope'],'fake_33_call_inventory':result['fake_33_call_inventory'],'actual_33_call_inventory':result.get('actual_33_call_inventory'),'manifest_sha256':result.get('manifest_sha256'),'run_nonce':result.get('run_nonce'),'watchdog_pid':result.get('watchdog_pid')})
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
                        os.write(gw,b'G');os.close(gw);result['released']=True;os.write(ready_fd,b'G')
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
        if pid is not None and group_ready:
            def helper_members(_pid):
                if helper is None or helper.closed:raise RuntimeError('census helper unavailable')
                # No more than one sample per second; cleanup remains bounded.
                delay=max(0,helper.next_sample-time.monotonic())
                if delay>1:raise RuntimeError('invalid cleanup sample rate')
                if delay:time.sleep(delay)
                sample_start=time.monotonic();sample=helper.sample(pid,reservation,abort_worker,time.monotonic()+2.)
                result['census_latencies_seconds'].append(time.monotonic()-sample_start)
                return [member for member in sample['members'] if member!=pid]
            result['cleanup_errors']=cleanup(pid,result,helper_members if helper is not None else None)
        elif pid is not None:
            try:os.kill(pid,signal.SIGKILL)
            except ProcessLookupError:pass
            try:os.waitpid(pid,0)
            except ChildProcessError:pass
        if helper is not None:
            try:helper.close()
            except BaseException as exc:result['cleanup_errors'].append('helper:'+repr(exc))
        try:os.close(ready_fd)
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
