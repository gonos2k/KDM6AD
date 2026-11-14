"""Bounded experimental consumer; DO NOT run without source review and a run receipt."""
import ctypes as C
import math
import hashlib
import json
import os
import struct
import selector_manifest_spec_v1 as selectors
from fixture_plan import fixture, direction, perturb, TARGET_TOP, schedule, raw_words

U64=C.c_uint64; I=C.c_int; D=C.c_double; V=C.c_void_p
class Meta(C.Structure):
    _fields_=[('abi_version',C.c_uint32),('struct_size',C.c_uint32)]+[(n,C.c_char*s) for n,s in [('input_id',128),('mode',32),('family',32),('scope',16),('stage',64),('field',64),('record_kind',16),('derivative_mode',16),('direction_id',128),('seed_sha256',65),('cotangent_id',128)]]+[(n,U64) for n in ('runtime_call','one_step_call','outer_loop','substep_n','event_ordinal')]+[(n,C.c_int64) for n in ('b_zero','k_zero','native_level_bottom_first','B','K')]
class Cond(C.Structure):
    _fields_=[('abi_version',C.c_uint32),('struct_size',C.c_uint32)]+[(n,C.c_char*s) for n,s in [('input_id',128),('mode',32),('family',32),('stage',64),('field',64),('source_hook',128)]]+[(n,U64) for n in ('context_epoch','runtime_call','one_step_call','outer_loop','substep_n','event_ordinal','causal_index')]+[(n,C.c_int64) for n in ('b_zero','k_zero','native_level_bottom_first','B','K')]+[(n,C.c_uint32) for n in ('role','dtype','scope','reason')]
def identity(m):
    return (m.family,m.stage,m.field,m.one_step_call,m.outer_loop,m.substep_n,m.event_ordinal,m.b_zero,m.k_zero,m.native_level_bottom_first,m.B,m.K)
def metadata_dict(m):
    """Copy full selector metadata before sidecar clear."""
    strings=('input_id','mode','family','scope','stage','field','record_kind')
    numbers=('runtime_call','one_step_call','outer_loop','substep_n','event_ordinal','b_zero','k_zero','native_level_bottom_first','B','K')
    return {**{k:getattr(m,k).decode('ascii') for k in strings},**{k:int(getattr(m,k)) for k in numbers}}
def condition_key(m):
    return (m.family,m.stage,m.field,m.source_hook,m.one_step_call,m.outer_loop,m.substep_n,m.event_ordinal,m.b_zero,m.k_zero,m.native_level_bottom_first,m.B,m.K,m.role,m.dtype,m.scope,m.reason)
def word(x): return struct.pack('=d',x)
def near(a,b,rtol=1e-5,atol=1e-8): return abs(a-b)<=atol+rtol*max(abs(a),abs(b))
def query_graph_selector(d,h,token,n,vectors,counts):
    if getattr(d,'FAKE_ONLY_NO_CDLL',False) is not True:raise RuntimeError('real graph query is hard-disabled')
    primal=U64(0x7ff8000000000000);flag=I(-1);grad=(D*624)(*([float('nan')]*624));mask=C.c_uint16();vs=I(-1)
    counts['graph_primal']+=1
    if d.kdm6_batch5_graph_primal_c(h,token,n,C.byref(primal),C.byref(flag)) or flag.value not in (0,1) or primal.value==0x7ff8000000000000 or not math.isfinite(as_double(primal.value)): raise RuntimeError('graph primal')
    counts['vjp']+=1
    if d.kdm6_batch5_intermediate_vjp_c(h,token,n,1.,grad,624,C.byref(mask),C.byref(vs)): raise RuntimeError('VJP ABI')
    if vs.value not in (0,1,2) or not all(math.isfinite(g) for g in grad): raise RuntimeError('invalid/nonfinite VJP')
    js=[];dots=[];statuses=[]
    for vector in vectors:
        j=D(float('nan'));status=I(-1);seed=(D*624)(*vector)
        counts['jvp']+=1
        if d.kdm6_batch5_intermediate_jvp_c(h,token,n,seed,624,C.byref(j),C.byref(status)) or status.value not in (0,1,2) or not math.isfinite(j.value): raise RuntimeError('JVP ABI/status')
        active={i//39 for i,x in enumerate(vector) if x!=0}
        statuses.append(status.value if status.value!=0 or all(mask.value & (1<<i) for i in active) else 2)
        js.append(j.value);dots.append(sum(a*b for a,b in zip(grad,vector)))
    return {'status':'SPEC_ONLY','graph_flag':flag.value,'primal':primal.value,'jvps':js,'dots':dots,'jvp_statuses':statuses,'vjp_status':vs.value,'mask':mask.value,'grad_words':[word(x).hex() for x in grad]}
def query_graph_set(d,h,token,requests,vectors,counts=None):
    if getattr(d,'FAKE_ONLY_NO_CDLL',False) is not True:raise RuntimeError('real graph query is hard-disabled')
    if len(requests)>3 or len(vectors)!=2:raise RuntimeError('graph query budget')
    if counts is None:counts={'graph_primal':0,'jvp':0,'vjp':0}
    return {name:{'identity':key,**query_graph_selector(d,h,token,n,vectors,counts)} for name,key,n in requests}
def release_capture(d,h):
    try:
        if h and (d.kdm6_handle_closep_c(C.byref(h))!=0 or h.value): raise RuntimeError('handle close')
    finally:
        d.kdm6_batch5_clear_c()
class Runner:
    def __init__(self, path):
        raise RuntimeError('real DSO loading is hard-disabled')
        self.d=C.CDLL(path); self.calls=0
        sig={
          'kdm6_batch5_begin_c':([C.c_char_p,C.c_char_p,U64],I),
          'kdm6_step_ad_state_forcing_c':([C.POINTER(D),C.POINTER(D),I,I,I,D,I,C.POINTER(D),C.POINTER(V),C.POINTER(C.c_float),D,D,C.c_uint32,C.c_int64],I),
          'kdm6_batch5_count_c':([],U64), 'kdm6_batch5_metadata_c':([U64,C.POINTER(Meta),C.c_size_t],I),
          'kdm6_batch5_value_word_c':([U64,C.POINTER(U64),C.POINTER(I)],I),
          'kdm6_batch5_binding_token_c':([V,C.POINTER(U64)],I),
          'kdm6_batch5_graph_primal_c':([V,U64,U64,C.POINTER(U64),C.POINTER(I)],I),
          'kdm6_batch5_intermediate_jvp_c':([V,U64,U64,C.POINTER(D),C.c_size_t,C.POINTER(D),C.POINTER(I)],I),
          'kdm6_batch5_intermediate_vjp_c':([V,U64,U64,D,C.POINTER(D),C.c_size_t,C.POINTER(C.c_uint16),C.POINTER(I)],I),
          'kdm6_batch5_result_rain_c':([V,U64,C.c_char_p,C.c_char_p,U64,C.POINTER(U64),C.POINTER(I)],I),
          'kdm6_batch5_condition_v2_count_c':([V,U64,C.POINTER(U64)],I),
          'kdm6_batch5_condition_v2_meta_c':([V,U64,U64,C.POINTER(Cond),C.c_size_t],I),
          'kdm6_batch5_condition_v2_raw_c':([V,U64,U64,C.POINTER(U64)],I),
          'kdm6_handle_closep_c':([C.POINTER(V)],I), 'kdm6_batch5_clear_c':([],None)}
        for name,(args,ret) in sig.items():
            f=getattr(self.d,name);f.argtypes=args;f.restype=ret
    def call(self,case,mode,x,v,selected=None):
        if self.calls>=35: raise RuntimeError('forward budget exhausted')
        journal=os.environ.get('BATCH6_SYNTHETIC_JOURNAL')
        if not journal: raise RuntimeError('launcher journal required')
        expected_case,expected_mode,offset=schedule()[self.calls]
        expected=perturb(fixture(expected_case),direction(expected_case),offset)
        if (case,mode)!=(expected_case,expected_mode) or raw_words(x)!=raw_words(expected): raise RuntimeError('call differs from fixed schedule')
        self.calls+=1; seq=self.calls
        event={'seq':seq,'case':case,'mode':mode,'offset':offset,'input_sha256':hashlib.sha256(raw_words(x)).hexdigest()}
        def append(state):
            with open(journal,'a',encoding='ascii') as stream:
                stream.write(json.dumps({**event,'state':state},sort_keys=True)+'\n'); stream.flush(); os.fsync(stream.fileno())
        append('STARTED')
        try: result=self._call(case,mode,x,v,selected,seq)
        except BaseException:
            append('FAILED'); raise
        append('COMPLETED'); return result
    def _call(self,case,mode,x,v,selected,seq):
        raise RuntimeError('real ABI calls are hard-disabled')
        d=self.d; h=V(); token=U64(); name=case.encode(); modeb=mode.encode()
        arr=(D*624)(*x); orig=bytes(arr); out=(D*468)(*([float('nan')]*468)); land=C.c_float(2)
        if d.kdm6_batch5_begin_c(name,modeb,seq)!=0: raise RuntimeError('begin')
        try:
            forcing=C.cast(C.byref(arr,468*C.sizeof(D)),C.POINTER(D))
            rc=d.kdm6_step_ad_state_forcing_c(arr,forcing,1,39,1,20.,int(mode!='center_joint_graph'),out,C.byref(h),C.byref(land),10.,10.,0,0)
            if rc or bool(h.value)!=(mode=='center_joint_graph') or bytes(arr)!=orig or not all(math.isfinite(a) for a in out): raise RuntimeError('forward/handle/input/output')
            if h and d.kdm6_batch5_binding_token_c(h,C.byref(token)): raise RuntimeError('binding')
            rain=U64(0x7ff8000000000000); flag=I(-1)
            if d.kdm6_batch5_result_rain_c(h,token,name,modeb,seq,C.byref(rain),C.byref(flag)) or rain.value==0x7ff8000000000000 or flag.value not in (0,1) or (not h and flag.value!=0): raise RuntimeError('rain')
            if not math.isfinite(struct.unpack('=d',struct.pack('=Q',rain.value))[0]): raise RuntimeError('rain nonfinite')
            result={'out':bytes(out),'rain':rain.value}
            if mode=='capture_off_value':
                off_count=U64(0xffffffffffffffff)
                if d.kdm6_batch5_count_c()!=0 or d.kdm6_batch5_condition_v2_count_c(None,0,C.byref(off_count))==0 or off_count.value!=0xffffffffffffffff: raise RuntimeError('off record access')
                return result
            metadata=[]
            v1_count=d.kdm6_batch5_count_c()
            if not 0<v1_count<=300000: raise RuntimeError('v1 record limit')
            for n in range(v1_count):
                m=Meta();m.abi_version=1;m.struct_size=C.sizeof(m)
                if d.kdm6_batch5_metadata_c(n,C.byref(m),C.sizeof(m)): raise RuntimeError('metadata')
                if m.abi_version!=1 or m.struct_size!=C.sizeof(m) or m.input_id!=name or m.mode!=modeb or m.runtime_call!=seq: raise RuntimeError('v1 identity')
                if m.scope==b'layer' and (m.B!=1 or m.K!=39 or m.b_zero!=0 or not 0<=m.k_zero<39 or m.native_level_bottom_first!=39-m.k_zero): raise RuntimeError('v1 layer scope')
                if m.scope==b'column' and (m.B!=1 or m.K!=-1 or m.b_zero!=0 or m.k_zero!=-1 or m.native_level_bottom_first!=-1): raise RuntimeError('v1 column scope')
                if m.scope not in (b'layer',b'column'): raise RuntimeError('unknown v1 scope')
                metadata.append(metadata_dict(m))
            result['selectors']={}
            call={'input_id':case,'mode':mode,'runtime_call':seq}
            vectors=v if len(v)==2 and all(isinstance(item,list) and len(item)==624 for item in v) else [v]
            graph_requests=[]
            for selector in selectors.SELECTORS:
                match=selectors.resolve(metadata,selector,call)
                if match['status']!='SPEC_ONLY':
                    result['selectors'][selector]={'status':'INCONCLUSIVE','reason':match['reason']};continue
                n=match['record_index'];key={k:val for k,val in match['identity'].items() if k not in ('input_id','mode','runtime_call')}
                if selected is not None and selected.get(selector)!=key:
                    result['selectors'][selector]={'status':'INCONCLUSIVE','reason':'selector identity mismatch'};continue
                if h:
                    graph_requests.append((selector,key,n))
                else:
                    primal=U64(0x7ff8000000000000);kind=I(-1)
                    if d.kdm6_batch5_value_word_c(n,C.byref(primal),C.byref(kind)) or kind.value!=2 or primal.value==0x7ff8000000000000 or not math.isfinite(as_double(primal.value)): raise RuntimeError('value scalar')
                    result['selectors'][selector]={'status':'SPEC_ONLY','identity':key,'primal':primal.value}
            if h:
                counts={'graph_primal':0,'jvp':0,'vjp':0}
                result['selectors'].update(query_graph_set(d,h,token,graph_requests,vectors,counts))
                result['query_counts']=counts
            if not h:
                count=U64(0xffffffffffffffff); conditions={}; operands={}; unverified_absence=False
                if d.kdm6_batch5_condition_v2_count_c(None,0,C.byref(count)): raise RuntimeError('condition count')
                if not 0<count.value<=150000: raise RuntimeError('v2 record limit')
                epoch=None; ordinals={}
                for i in range(count.value):
                    m=Cond();m.abi_version=2;m.struct_size=C.sizeof(m)
                    if d.kdm6_batch5_condition_v2_meta_c(None,0,i,C.byref(m),C.sizeof(m)): raise RuntimeError('condition meta')
                    if m.abi_version!=2 or m.struct_size!=C.sizeof(m) or m.input_id!=name or m.mode!=modeb or m.runtime_call!=seq or not m.context_epoch: raise RuntimeError('v2 identity')
                    if epoch is None: epoch=m.context_epoch
                    if m.context_epoch!=epoch: raise RuntimeError('mixed context epochs')
                    if m.scope==1 and (m.B!=1 or m.K!=39 or m.b_zero!=0 or not 0<=m.k_zero<39 or m.native_level_bottom_first!=39-m.k_zero): raise RuntimeError('v2 layer scope')
                    if m.scope==2 and (m.B!=1 or m.K!=-1 or m.b_zero!=0 or m.k_zero!=-1 or m.native_level_bottom_first!=-1): raise RuntimeError('v2 column scope')
                    if m.scope==3 and (m.B!=-1 or m.K!=-1 or m.b_zero!=-1 or m.k_zero!=-1 or m.native_level_bottom_first!=-1): raise RuntimeError('v2 scalar scope')
                    if m.scope not in (1,2,3) or m.role not in (1,2,3,4,5) or m.dtype not in (1,2,3,4,5): raise RuntimeError('v2 type')
                    ordinal_key=(m.one_step_call,m.outer_loop,m.family,m.substep_n,m.scope,m.b_zero,m.k_zero,m.B,m.K,m.stage,m.field,m.source_hook,m.role)
                    expected=ordinals.get(ordinal_key,0)
                    if m.event_ordinal!=expected: raise RuntimeError('duplicate or noncontiguous event ordinal')
                    ordinals[ordinal_key]=expected+1
                    if m.role in (1,2) and m.dtype!=1: raise RuntimeError('predicate dtype')
                    if m.role==3 and m.dtype not in (2,3): raise RuntimeError('operand dtype')
                    if m.role==4 and (m.scope!=3 or m.dtype not in (1,2,3,4)): raise RuntimeError('control type')
                    if m.role==5:
                        if m.dtype!=5 or m.reason not in (1,2,3):raise RuntimeError('invalid absence metadata')
                        key=condition_key(m)
                        if key in conditions:raise RuntimeError('duplicate absence')
                        conditions[key]=(m.reason,m.causal_index);unverified_absence=True;continue
                    if m.reason!=0: raise RuntimeError('unexpected inactive reason')
                    if m.role in (1,2) or (m.stage==b'sedimentation_schedule' and m.role==4) or (m.stage==b'nc_snap1' and m.field in (b'nc_before',b'ncmin') and m.role==3):
                        key=condition_key(m); raw=U64(0xffffffffffffffff)
                        bucket=operands if m.role==3 else conditions
                        if key in bucket or d.kdm6_batch5_condition_v2_raw_c(None,0,i,C.byref(raw)) or raw.value==0xffffffffffffffff: raise RuntimeError('condition duplicate/raw')
                        if m.dtype==1 and raw.value not in (0,1): raise RuntimeError('invalid bool')
                        if m.dtype==2 and raw.value>>32: raise RuntimeError('invalid f32 raw width')
                        if m.dtype==2 and not math.isfinite(struct.unpack('=f',struct.pack('=I',raw.value & 0xffffffff))[0]): raise RuntimeError('nonfinite f32')
                        if m.dtype==3 and not math.isfinite(as_double(raw.value)): raise RuntimeError('nonfinite f64')
                        bucket[key]=raw.value
                if not conditions: raise RuntimeError('no conditions')
                if not {b'mstepmax_main',b'mstepmax_ice'} <= {k[2] for k in conditions if k[1]==b'sedimentation_schedule' and k[13]==4}: raise RuntimeError('missing schedule controls')
                result['conditions']=conditions; result['operands']=operands; result['unverified_absence']=unverified_absence
            return result
        finally:
            release_capture(d,h)
def as_double(bits): return struct.unpack('=d',struct.pack('=Q',bits))[0]
def evaluate_case(*args,**kwargs):
    """Retired 35-call prototype; real33_worker owns the fixed 33-slot plan."""
    raise RuntimeError('obsolete 35-call evaluator is disabled')


def verify_candidate_boundary(low,high):
    """Require same-identity consumed gate plus captured operands on opposite sides."""
    def rows(result):
        c=result['_center_records']; found={}
        for key, raw in c['conditions'].items():
            if key[1]==b'nc_snap1' and key[2]==b'nc_ge_ncmin' and key[9]==TARGET_TOP and key[13]==1:
                ident=(key[0],)+key[4:13]
                if ident in found: raise RuntimeError('ambiguous boundary gate')
                found[ident]={'gate':raw}
        for key, raw in c['operands'].items():
            if key[1]==b'nc_snap1' and key[2] in (b'nc_before',b'ncmin') and key[9]==TARGET_TOP:
                ident=(key[0],)+key[4:13]
                if ident in found:
                    name=key[2].decode()
                    if name in found[ident] or key[14]!=3: raise RuntimeError('ambiguous/non-f64 boundary operand')
                    found[ident][name]=as_double(raw)
        return found
    a,b=rows(low),rows(high)
    for ident in sorted(a.keys() & b.keys()):
        x,y=a[ident],b[ident]
        if set(x)==set(y)=={'gate','nc_before','ncmin'} and x['gate']==0 and y['gate']==1 and x['nc_before']<x['ncmin'] and y['nc_before']>=y['ncmin']:
            return {'identity':[str(z) for z in ident], 'low':x, 'high':y}
    raise RuntimeError('INCONCLUSIVE: candidate inputs did not demonstrate captured boundary')
