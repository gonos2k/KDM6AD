"""Synthetic evidence postcheck draft; does not load a DSO or run a worker."""
import hashlib,json,os,pathlib,re,signal,time,math
import fixture33
from real33_contract import sha
MAX_CALL=128*1024**2;MAX_TOTAL=4*1024**3

def checked_journal(directory,slots):
    root=pathlib.Path(directory);events=[json.loads(line) for line in (root/'calls.jsonl').read_text().splitlines()]
    if len(slots)!=33 or len(events)!=66:raise ValueError('journal incomplete')
    total=0;assets=[]
    for i,slot in enumerate(slots,1):
        a,b=events[2*(i-1):2*i]
        keys=('seq','fixture','mode','direction','offset','input_sha256')
        if any(a.get(k)!=slot[k] or b.get(k)!=slot[k] for k in keys) or a.get('state')!='STARTED' or b.get('state')!='COMPLETED':raise ValueError('journal identity or state')
        path=root/f'call_{i:02}.json';data=path.read_bytes();total+=len(data)
        if len(data)>MAX_CALL or total>MAX_TOTAL or b.get('bytes')!=len(data) or b.get('asset_sha256')!=hashlib.sha256(data).hexdigest():raise ValueError('call asset size/hash')
        obj=json.loads(data)
        if obj.get('slot')!={k:slot[k] for k in keys} or hashlib.sha256(bytes.fromhex(obj['input_words'])).hexdigest()!=slot['input_sha256']:raise ValueError('call asset identity')
        assets.append(obj)
    return total,assets

def checked_results(assets):
    """Validate per-call shape/status only; scientific replay remains separate."""
    query={'graph_primal':0,'jvp':0,'vjp':0}
    for obj in assets:
        slot=obj['slot'];r=obj['result'];mode=slot['mode']
        if not isinstance(r,dict) or not isinstance(r.get('out'),str) or len(bytes.fromhex(r['out']))!=468*8 or type(r.get('rain')) is not int or not 0<=r['rain']<2**64:raise ValueError('invalid output schema')
        if mode!='capture_off_value' and (not isinstance(r.get('selector'),list) or type(r.get('primal')) is not int):raise ValueError('invalid selected scalar schema')
        if mode=='capture_on_value' and not isinstance(r.get('conditions'),list):raise ValueError('invalid condition schema')
        if mode=='center_joint_graph':
            grad=r.get('grad_words');jvp=r.get('jvps');dots=r.get('dots')
            if not isinstance(grad,list) or len(grad)!=624 or any(not isinstance(x,str) or len(bytes.fromhex(x))!=8 for x in grad) or not isinstance(jvp,list) or len(jvp)!=2 or not isinstance(dots,list) or len(dots)!=2 or type(r.get('mask')) is not int or not 0<=r['mask']<2**16 or r.get('graph_flag') not in (0,1) or r.get('vjp_status') not in (0,1,2) or type(r.get('jvp_statuses')) is not list or len(r['jvp_statuses'])!=2 or any(v not in (0,1,2) for v in r['jvp_statuses']):raise ValueError('invalid graph payload schema')
            query['graph_primal']+=1;query['jvp']+=2;query['vjp']+=1
    return query

def checked_loader(log,allowed,required,worker_pid,system_baseline):
    """Strict Darwin dyld trace; system-cache UUID evidence is not a file hash."""
    if type(worker_pid) is not int or worker_pid<=0 or type(system_baseline) is not dict:raise ValueError('loader trace identity')
    image=re.compile(r'^dyld\[(\d+)\]: <([0-9A-F-]+)> (/.+)$')
    status=re.compile(r'^dyld\[(\d+)\]: move (?:loaded to delayed|delayed to loaded): (\S+)$')
    loaded=set();cache=[];status_count=0
    for line in pathlib.Path(log).read_text(errors='strict').splitlines():
        m=image.fullmatch(line)
        if m:
            if int(m.group(1))!=worker_pid:raise ValueError('loader PID mismatch')
            uuid,path=m.group(2),m.group(3);resolved=str(pathlib.Path(path).resolve())
            if resolved in allowed:
                if sha(resolved)!=allowed[resolved]:raise ValueError('loaded image hash')
                loaded.add(resolved)
            elif path in system_baseline and system_baseline[path]==uuid and path.startswith(('/usr/lib/','/System/Library/')):
                cache.append({'path':path,'uuid':uuid})
            else:raise ValueError('unapproved loaded image or cache UUID')
        else:
            m=status.fullmatch(line)
            if not m or int(m.group(1))!=worker_pid:raise ValueError('unclassified dyld line')
            status_count+=1
    if len(loaded)<5 or not set(required)<=loaded:raise ValueError('missing required loaded image')
    return {'hashed':sorted(loaded),'system_cache':cache,'classified_status_lines':status_count,'dependency_closure':'PARTIAL'}

def validate(directory,watchdog_result,elapsed_seconds,slots,allowed,required,loader_log,system_baseline):
    if watchdog_result.get('status')!='INCOMPLETE' or watchdog_result.get('reason')!='worker_exit' or watchdog_result.get('cleanup_errors') or watchdog_result.get('signals') or watchdog_result.get('worker_wait_status')!=0:raise ValueError('worker/watcher failure')
    rss=watchdog_result.get('peak_group_rss_kib')
    if type(elapsed_seconds) not in (int,float) or not math.isfinite(elapsed_seconds) or not 0<=elapsed_seconds<=900 or type(rss) is not int or not 0<rss<=4*1024**2 or watchdog_result.get('released') is not True or watchdog_result.get('worker_reaped_pid')!=watchdog_result.get('worker_pid') or type(watchdog_result.get('worker_pid')) is not int:raise ValueError('resource/worker identity')
    if slots!=fixture33.plan():raise ValueError('slot plan mismatch')
    n,assets=checked_journal(directory,slots);queries=checked_results(assets);loaded=checked_loader(loader_log,allowed,required,watchdog_result['worker_pid'],system_baseline)
    worker=json.loads((pathlib.Path(directory)/'worker_result.json').read_text())
    if worker.get('status')!='INCONCLUSIVE' or worker.get('calls')!=33 or worker.get('asset_bytes')!=n:raise ValueError('worker result')
    return {'status':'EXECUTION_COMPLETED_ASSETS_ONLY','scientific_status':'INCONCLUSIVE','scope':'synthetic assets only; FD/JVP/VJP correctness requires separate replay; contingent on watchdog survival and no setsid escape','forwards':33,'asset_bytes':n,'loaded':loaded,'queries':queries}

def publish_fake_only(path,payload,deadline):
    # Executable integration remains disabled pending Red; fake tests only.
    if payload.get('test_only') is not True:raise RuntimeError('real witness disabled')
    target=pathlib.Path(path);tmp=target.with_name('.'+target.name+'.tmp');mask={signal.SIGINT,signal.SIGTERM}
    with open(tmp,'x') as f:json.dump(payload,f,sort_keys=True);f.flush();os.fsync(f.fileno())
    old=signal.pthread_sigmask(signal.SIG_BLOCK,mask)
    try:
        if signal.sigpending() & mask or time.monotonic()>deadline:raise RuntimeError('cancelled/deadline')
        os.link(tmp,target)
        if signal.sigpending() & mask or time.monotonic()>deadline:
            os.unlink(target)
            fd=os.open(target.parent,os.O_RDONLY)
            try:os.fsync(fd)
            finally:os.close(fd)
            raise RuntimeError('cancelled/deadline during publish')
        fd=os.open(target.parent,os.O_RDONLY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK,old)
        try:os.unlink(tmp)
        except FileNotFoundError:pass

def validate_pinned(directory,watchdog_result,elapsed_seconds,manifest_path,independent_sha256,loader_log):
    """Source-only draft: bind expected images and slots to independently pinned bytes."""
    import freeze33
    freeze33.validate_frozen(manifest_path,independent_sha256)
    manifest=json.loads(pathlib.Path(manifest_path).read_text())
    if watchdog_result.get('manifest_sha256')!=independent_sha256 or watchdog_result.get('dyld_trace_enabled') is not True:raise ValueError('watchdog manifest/trace binding')
    # The manifest must name canonical absolute DSO explicitly; no caller
    # chooses a weaker required subset. Additional observed images fail closed.
    approved=manifest.get('approved_loaded_images')
    required=manifest.get('required_loaded_images')
    if type(approved) is not dict or type(required) is not list:raise ValueError('missing independently reviewed actual-image pins')
    torch=manifest['torch_prior_pins']
    if not set(torch)<=set(required) or not set(required)<=set(approved) or sum(v==manifest['dso_sha256'] for v in approved.values())!=1:raise ValueError('DSO/Torch required image downgrade')
    dso_paths=[p for p,v in approved.items() if v==manifest['dso_sha256']]
    if not set(dso_paths)<=set(required) or any(approved[p]!=h for p,h in torch.items()):raise ValueError('DSO/Torch image pin mismatch')
    system=manifest.get('system_cache_baseline',{});minimum=manifest.get('loader_status_line_count')
    if len(system)<596 or type(minimum) is not int or minimum<866:raise ValueError('downgraded loader baseline')
    result=validate(directory,watchdog_result,elapsed_seconds,manifest['slots'],approved,required,loader_log,system)
    trace=result['loaded'];observed={(x['path'],x['uuid']) for x in trace['system_cache']}
    if not set(system.items())<=observed or trace['classified_status_lines']<minimum:raise ValueError('truncated baseline trace')
    result['loader_scope']='trusted pinned-worker stderr; cache UUID/path baseline and later lazy closure partial'
    return result
