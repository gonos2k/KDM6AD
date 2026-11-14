"""Synthetic evidence postcheck draft; does not load a DSO or run a worker."""
import hashlib,json,os,pathlib,re,signal,time,math,struct
import fixture33
import selector_manifest_spec_v1 as selectors
from real33_contract import sha,validate_dso_binding
MAX_CALL=128*1024**2;MAX_TOTAL=4*1024**3

def checked_condition_rows(rows, *, operand):
    if rows=={}:rows=[]
    if type(rows) is not list:raise ValueError('condition rows')
    seen=set()
    for row in rows:
        if type(row) is not dict or set(row)!={'identity','raw'}:raise ValueError('condition row')
        key=row['identity'];raw=row['raw']
        if type(key) is not list or len(key)!=17 or any(type(x) is not str or re.fullmatch('[0-9a-f]+',x) is None or len(x)%2 for x in key[:4]) or any(type(x) is not int for x in key[4:]):raise ValueError('condition identity')
        ident=tuple(key)
        if ident in seen:raise ValueError('duplicate condition identity')
        seen.add(ident)
        role,dtype,scope,reason=key[13:17]
        b,k,level,B,K=key[8:13]
        if any(not 0<=v<2**64 for v in key[4:8]) or not ((scope==1 and (B,K,b)==(1,39,0) and 0<=k<39 and level==39-k) or (scope==2 and (B,K,b,k,level)==(1,-1,0,-1,-1)) or (scope==3 and (B,K,b,k,level)==(-1,-1,-1,-1,-1))):raise ValueError('condition coordinates')
        if role==5:
            if operand or dtype!=5 or scope not in (1,2) or reason not in (1,2,3) or type(raw) is not list or len(raw)!=2 or any(type(x) is not int for x in raw) or raw[0]!=reason or not 0<=raw[1]<2**64:raise ValueError('absence row')
        else:
            if not ((role in (1,2) and dtype==1 and scope in (1,2)) or (role==3 and dtype in (2,3) and scope in (1,2)) or (role==4 and dtype in (1,2,3,4) and scope==3)) or reason!=0 or (role==3)!=operand or type(raw) is not int or not 0<=raw<2**64:raise ValueError('condition raw')
            if dtype==1 and raw not in (0,1):raise ValueError('condition boolean')
            if dtype==2 and (raw>=2**32 or not math.isfinite(struct.unpack('=f',struct.pack('=I',raw))[0])):raise ValueError('condition f32')
            if dtype==3 and not math.isfinite(struct.unpack('=d',struct.pack('=Q',raw))[0]):raise ValueError('condition f64')

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
        if obj.get('schema')!='kdm6.synthetic33.call_asset.v2' or obj.get('slot')!={k:slot[k] for k in keys} or hashlib.sha256(bytes.fromhex(obj['input_words'])).hexdigest()!=slot['input_sha256']:raise ValueError('call asset identity')
        assets.append(obj)
    return total,assets

def checked_results(assets):
    """Validate serialized v2 call payloads; never certify scientific replay."""
    query={'graph_primal':0,'jvp':0,'vjp':0}
    for obj in assets:
        slot=obj['slot'];r=obj['result'];mode=slot['mode']
        if not isinstance(r,dict) or not isinstance(r.get('out'),str) or len(bytes.fromhex(r['out']))!=468*8 or type(r.get('rain')) is not int or not 0<=r['rain']<2**64:raise ValueError('invalid output schema')
        if not all(math.isfinite(v[0]) for v in struct.iter_unpack('=d',bytes.fromhex(r['out']))) or not math.isfinite(struct.unpack('=d',struct.pack('=Q',r['rain']))[0]):raise ValueError('nonfinite output or rain')
        if mode=='capture_off_value':
            if set(r)!={'out','rain'}:raise ValueError('unexpected capture-off payload')
            continue
        expected_keys={'out','rain','selectors','conditions','operands','unverified_absence'} if mode=='capture_on_value' else {'out','rain','selectors','query_counts'} if mode=='center_joint_graph' else None
        if expected_keys is None or set(r)!=expected_keys:raise ValueError('unexpected v2 result fields')
        actual=r.get('selectors')
        if type(actual) is not dict or set(actual)!=set(selectors.SELECTORS):raise ValueError('selector inventory')
        if mode=='capture_on_value' and (type(r.get('conditions')) is not list or not r['conditions'] or not (type(r.get('operands')) is list or r.get('operands')=={}) or type(r.get('unverified_absence')) is not bool):raise ValueError('invalid condition schema')
        if mode=='capture_on_value':
            checked_condition_rows(r['conditions'],operand=False);checked_condition_rows(r['operands'],operand=True)
            if r['unverified_absence'] != any(row['identity'][13]==5 for row in r['conditions']):raise ValueError('absence flag mismatch')
        successes=0
        for name,entry in actual.items():
            if type(entry) is not dict:raise ValueError('selector schema')
            if entry.get('status')=='INCONCLUSIVE':
                if set(entry)!={'status','reason'} or entry['reason'] not in ('missing or ambiguous full selector','selector identity mismatch'):raise ValueError('invalid inconclusive selector')
                continue
            if entry.get('status')!='SPEC_ONLY':raise ValueError('unknown selector status')
            ident={**selectors.SELECTORS[name],**selectors.LAYER,'record_kind':'value'}
            observed=entry.get('identity')
            if type(observed) is not dict or set(observed)!=set(ident) or any(type(observed[k]) is not type(v) or observed[k]!=v for k,v in ident.items()) or type(entry.get('primal')) is not int or not 0<=entry['primal']<2**64 or not math.isfinite(struct.unpack('=d',struct.pack('=Q',entry['primal']))[0]):raise ValueError('invalid selector identity or primal')
            successes+=1
            if mode=='capture_on_value':
                if set(entry)!={'status','identity','primal'}:raise ValueError('value selector schema')
            elif mode=='center_joint_graph':
                if set(entry)!={'status','identity','primal','graph_flag','jvps','dots','jvp_statuses','vjp_status','mask','grad_words'}:raise ValueError('graph selector schema')
                grad=entry['grad_words'];jvp=entry['jvps'];dots=entry['dots']
                if type(grad) is not list or len(grad)!=624 or any(type(x) is not str or re.fullmatch('[0-9a-f]{16}',x) is None for x in grad) or type(jvp) is not list or len(jvp)!=2 or type(dots) is not list or len(dots)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in jvp+dots) or type(entry['mask']) is not int or not 0<=entry['mask']<2**16 or type(entry['graph_flag']) is not int or entry['graph_flag'] not in (0,1) or type(entry['vjp_status']) is not int or entry['vjp_status'] not in (0,1,2) or type(entry['jvp_statuses']) is not list or len(entry['jvp_statuses'])!=2 or any(type(v) is not int or v not in (0,1,2) for v in entry['jvp_statuses']):raise ValueError('invalid graph payload schema')
                if not all(math.isfinite(struct.unpack('=d',bytes.fromhex(x))[0]) for x in grad):raise ValueError('nonfinite graph gradient')
                if entry['graph_flag']==0 and (entry['vjp_status']!=1 or entry['mask']!=0 or entry['jvp_statuses']!=[1,1] or any(x!='0000000000000000' for x in grad) or any(struct.pack('=d',x)!=b'\0'*8 for x in jvp+dots)):raise ValueError('inconsistent disconnected graph')
                if entry['graph_flag']==1 and not ((entry['vjp_status']==0 and entry['mask']!=0) or (entry['vjp_status']==2 and entry['mask']==0)):raise ValueError('inconsistent connected graph status')
                if entry['graph_flag']==1 and entry['vjp_status']==2 and (entry['jvp_statuses']!=[2,2] or any(struct.pack('=d',x)!=b'\0'*8 for x in jvp+dots)):raise ValueError('inconsistent unconnected graph')
                if entry['graph_flag']==1 and 1 in entry['jvp_statuses']:raise ValueError('inconsistent graph JVP status')
                if entry['graph_flag']==1:
                    expected=[]
                    for direction in fixture33.DIRECTIONS:
                        vector=fixture33.direction(direction);active={i//39 for i,v in enumerate(vector) if v!=0}
                        if len(active)!=1:raise ValueError('ambiguous fixed seed')
                        expected.append(0 if entry['mask'] & (1<<next(iter(active))) else 2)
                    if entry['jvp_statuses']!=expected:raise ValueError('JVP direction connectivity')
                    if any(status==2 and (jvp[i]!=0.0 or dots[i]!=0.0) for i,status in enumerate(expected)):raise ValueError('nonzero unconnected direction')
                if any(grad[i]!='0000000000000000' for i in range(624) if not entry['mask'] & (1 << (i//39))):raise ValueError('nonzero undefined gradient')
            else:raise ValueError('unknown mode')
        if mode=='center_joint_graph':
            counts=entry_counts={'graph_primal':successes,'jvp':2*successes,'vjp':successes}
            supplied=r.get('query_counts')
            if type(supplied) is not dict or set(supplied)!=set(entry_counts) or any(type(supplied[k]) is not int or supplied[k]!=v for k,v in entry_counts.items()):raise ValueError('graph query counts')
            for k,v in counts.items():query[k]+=v
    if query['graph_primal']>9 or query['jvp']>18 or query['vjp']>9:raise ValueError('graph query budget')
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
    validate_dso_binding(manifest)
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
