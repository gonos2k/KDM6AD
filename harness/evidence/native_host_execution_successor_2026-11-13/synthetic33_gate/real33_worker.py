"""Research draft. Never run until independent supervisor and Red authorize it."""
import hashlib,json,math,os,pathlib
import fixture33 as f
from fixture_plan import FIELDS,K,CENTER,perturb,raw_words
from graph_runner import Runner,as_double,near
from real33_contract import preflight
from selector_manifest_spec_v1 import SELECTORS

def encode(v):
    if isinstance(v,bytes):return v.hex()
    if isinstance(v,tuple):return [encode(x) for x in v]
    if isinstance(v,list):return [encode(x) for x in v]
    if isinstance(v,dict):
        if all(isinstance(k,str) for k in v):return {k:encode(x) for k,x in v.items()}
        return [{'identity':encode(k),'raw':encode(x)} for k,x in sorted(v.items())]
    return v

def append(path,event):
    with open(path,'a',encoding='ascii') as stream:
        stream.write(json.dumps(event,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n');stream.flush();os.fsync(stream.fileno())

def run(release_fd,outdir):
    if getattr(Runner,'FAKE_ONLY_NO_CDLL',False) is not True:raise RuntimeError('real worker is hard-disabled')
    outdir=pathlib.Path(outdir).resolve(strict=True)
    if os.read(release_fd,1)!=b'G':raise RuntimeError('watchdog release required')
    os.close(release_fd)
    # This is the first point after release at which the DSO may be loaded.
    contract=preflight();r=Runner(contract['dso_path']);plan=f.plan();journal=outdir/'calls.jsonl';total=0;results=[];seq=0
    def invoke(case,mode,x,v,selected=None):
        nonlocal seq,total
        if seq>=33:raise RuntimeError('forward budget exhausted')
        slot=plan[seq];event={k:slot[k] for k in ('seq','fixture','mode','direction','offset','input_sha256')}
        if (case,mode)!=(slot['fixture'],slot['mode']) or hashlib.sha256(raw_words(x)).hexdigest()!=slot['input_sha256']:raise RuntimeError('plan/input mismatch')
        seq+=1;append(journal,{**event,'state':'STARTED'})
        try:
            result=r._call(case,mode,x,v,selected,seq)
            payload=json.dumps({'slot':event,'input_words':raw_words(x).hex(),'result':encode(result)},sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')
            if len(payload)>128*1024*1024 or total+len(payload)>4*1024**3:raise RuntimeError('serialized byte cap')
            target=outdir/f'call_{seq:02}.json';tmp=outdir/f'.call_{seq:02}.tmp'
            with open(tmp,'xb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
            os.link(tmp,target);os.unlink(tmp);fd=os.open(outdir,os.O_RDONLY)
            try:os.fsync(fd)
            finally:os.close(fd)
            total+=len(payload);append(journal,{**event,'state':'COMPLETED','asset_sha256':hashlib.sha256(payload).hexdigest(),'bytes':len(payload)})
            return result
        except BaseException:
            append(journal,{**event,'state':'FAILED'});raise
    for case in f.CASES:
        x=f.center(case);dirs=[f.direction(name) for name in f.DIRECTIONS]
        off=invoke(case,'capture_off_value',x,dirs[0]);on=invoke(case,'capture_on_value',x,dirs[0])
        selected={name:entry['identity'] for name,entry in on['selectors'].items() if entry['status']=='SPEC_ONLY'}
        graph=invoke(case,'center_joint_graph',x,dirs,selected)
        if (off['out'],off['rain'])!=(on['out'],on['rain']) or (graph['out'],graph['rain'])!=(on['out'],on['rain']):raise RuntimeError('same-input raw parity')
        for selector in SELECTORS:
            a=on['selectors'][selector];b=graph['selectors'][selector]
            if a['status']=='SPEC_ONLY' and b['status']=='SPEC_ONLY' and a['primal']!=b['primal']:raise RuntimeError('same-input raw parity')
        per=[]
        for index,name in enumerate(f.DIRECTIONS):
            coordinate=FIELDS.index(name)*K+CENTER
            by_selector={selector:[] for selector in SELECTORS}
            for h in f.H:
                xm=perturb(x,dirs[index],-h);xp=perturb(x,dirs[index],h);gap=xp[coordinate]-xm[coordinate]
                if not math.isfinite(gap) or gap<=0 or any(raw_words([xm[i]])!=raw_words([x[i]]) or raw_words([xp[i]])!=raw_words([x[i]]) for i in range(624) if i!=coordinate):raise RuntimeError('invalid represented direction')
                minus=invoke(case,'capture_on_value',xm,dirs[index],selected);plus=invoke(case,'capture_on_value',xp,dirs[index],selected)
                have_conditions=all(isinstance(r.get('conditions'),dict) and bool(r['conditions']) for r in (on,minus,plus))
                crossing=have_conditions and (minus['conditions']!=on['conditions'] or plus['conditions']!=on['conditions'])
                incomplete=any(r.get('unverified_absence',False) or not r.get('conditions') for r in (on,minus,plus))
                branch='CROSS' if crossing else ('INCOMPLETE' if incomplete else 'STABLE')
                for selector in SELECTORS:
                    entries=[r['selectors'][selector] for r in (on,graph,minus,plus)]
                    valid=all(e['status']=='SPEC_ONLY' for e in entries)
                    if entries[1]['status']=='SPEC_ONLY':
                        j,dot=entries[1]['jvps'][index],entries[1]['dots'][index]
                        js,vs=entries[1]['jvp_statuses'][index],entries[1]['vjp_status']
                        duality='UNCONNECTED' if entries[1]['graph_flag']!=1 or js!=0 or vs!=0 else ('CONSISTENT' if near(j,dot) else 'MISMATCH')
                    else:
                        j=dot=js=vs=None;duality='UNCONNECTED'
                    if valid:
                        fd=(as_double(entries[3]['primal'])-as_double(entries[2]['primal']))/gap*dirs[index][coordinate]
                        if not math.isfinite(fd):fd=None
                    else:
                        fd=None
                    fd_signal='UNAVAILABLE' if fd is None else ('UNDER_RESOLUTION' if abs(fd)<1e-8 else 'RESOLVED')
                    status='NUMERIC_MISMATCH' if duality=='MISMATCH' else ('BRANCH_CROSSING' if branch=='CROSS' else ('UNRESOLVED' if branch=='INCOMPLETE' or duality=='UNCONNECTED' or fd_signal!='RESOLVED' or abs(j)<1e-8 else ('LOCAL_CONSISTENT' if near(fd,j) else 'NUMERIC_MISMATCH')))
                    record={'selector':selector,'direction':name,'h':h,'represented_gap':gap,'fd':fd,'jvp':j,'vjp_dot':dot,'jvp_status':js,'vjp_status':vs,'ad_duality':duality,'fd_signal':fd_signal,'recorded_branch_schedule':branch,'two_step_stability':'UNKNOWN','status':status,'selector_status':'SPEC_ONLY' if valid and duality!='UNCONNECTED' and fd_signal=='RESOLVED' else 'INCONCLUSIVE'}
                    per.append(record);by_selector[selector].append(record)
            for direction_results in by_selector.values():
                if len(direction_results)==2 and all(v['fd_signal']=='RESOLVED' and v['recorded_branch_schedule']=='STABLE' for v in direction_results):
                    stability='STABLE' if near(direction_results[0]['fd'],direction_results[1]['fd']) else 'UNSTABLE'
                    for v in direction_results:v['two_step_stability']=stability
        results.append({'fixture':case,'status':'INCONCLUSIVE','scope':'partial recorded conditions; graph masks and complete census unverified','derivatives':per})
    if seq!=33:raise RuntimeError('incomplete schedule')
    return {'status':'INCONCLUSIVE','calls':seq,'asset_bytes':total,'results':results,'scope':'synthetic only; no native, physical conservation or execution-readiness claim'}
