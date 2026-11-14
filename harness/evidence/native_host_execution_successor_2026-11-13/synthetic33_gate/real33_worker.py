"""Research draft. Never run until independent supervisor and Red authorize it."""
import hashlib,json,math,os,pathlib
import fixture33 as f
from fixture_plan import FIELDS,K,CENTER,perturb,raw_words
from graph_runner import Runner,as_double,near
from real33_contract import preflight

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
        off=invoke(case,'capture_off_value',x,dirs[0]);on=invoke(case,'capture_on_value',x,dirs[0]);graph=invoke(case,'center_joint_graph',x,dirs,on['selector'])
        if (off['out'],off['rain'])!=(on['out'],on['rain']) or (graph['out'],graph['rain'])!=(on['out'],on['rain']) or graph['primal']!=on['primal']:raise RuntimeError('same-input raw parity')
        per=[]
        for index,name in enumerate(f.DIRECTIONS):
            j,dot=graph['jvps'][index],graph['dots'][index]
            directional_status='UNRESOLVED' if graph['jvp_statuses'][index]!=0 or graph['vjp_status']!=0 or abs(j)<1e-8 else ('NUMERIC_MISMATCH' if not near(j,dot) else 'LOCAL_CONSISTENT')
            coordinate=FIELDS.index(name)*K+CENTER
            for h in f.H:
                xm=perturb(x,dirs[index],-h);xp=perturb(x,dirs[index],h);gap=xp[coordinate]-xm[coordinate]
                if not math.isfinite(gap) or gap<=0 or any(raw_words([xm[i]])!=raw_words([x[i]]) or raw_words([xp[i]])!=raw_words([x[i]]) for i in range(624) if i!=coordinate):raise RuntimeError('invalid represented direction')
                minus=invoke(case,'capture_on_value',xm,dirs[index],on['selector']);plus=invoke(case,'capture_on_value',xp,dirs[index],on['selector'])
                crossing=minus['conditions']!=on['conditions'] or plus['conditions']!=on['conditions']
                fd=(as_double(plus['primal'])-as_double(minus['primal']))/gap*dirs[index][coordinate]
                if not math.isfinite(fd):raise RuntimeError('nonfinite FD')
                status='BRANCH_CROSSING' if crossing else ('UNRESOLVED' if any(r.get('unverified_absence',False) for r in (on,minus,plus)) else directional_status)
                if not crossing and abs(fd)<1e-8:status='UNRESOLVED'
                elif not crossing and status=='LOCAL_CONSISTENT' and not near(fd,j):status='NUMERIC_MISMATCH'
                per.append({'direction':name,'h':h,'represented_gap':gap,'fd':fd,'jvp':j,'vjp_dot':dot,'status':status})
        results.append({'fixture':case,'status':'INCONCLUSIVE','scope':'partial recorded conditions; graph masks and complete census unverified','derivatives':per})
    if seq!=33:raise RuntimeError('incomplete schedule')
    return {'status':'INCONCLUSIVE','calls':seq,'asset_bytes':total,'results':results,'scope':'synthetic only; no native, physical conservation or execution-readiness claim'}
