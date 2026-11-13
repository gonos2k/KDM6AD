#!/usr/bin/env python3
"""Prepared C ABI mechanics. Registered/model execution remains blocked.

The batch5 sidecar graph path is synthetic-tested only. Claimed DSO hashes
and caller-provided selectors are not independent provenance. The low-level helper is exercised solely with a synthetic fake.
"""
import ctypes as C
import math
import os
import struct
import threading
from types import MappingProxyType
from batch5_preflight import words_sha, load_inputs, seed_specs

D=C.c_double; HANDLE=C.c_void_p; PD=C.POINTER(D); PH=C.POINTER(HANDLE)
STATE=468; FORCING=156; MAX_RECORDS=2_000_000; META_VERSION=1
SELECTOR_FIELDS=('input_id','mode','runtime_call','one_step_call','outer_loop','family','substep_n','scope','b_zero','k_zero','native_level_bottom_first','B','K','stage','field','record_kind','event_ordinal')

class Meta(C.Structure):
    _fields_=[('abi_version',C.c_uint32),('struct_size',C.c_uint32),
              ('input_id',C.c_char*128),('mode',C.c_char*32),('family',C.c_char*32),('scope',C.c_char*16),('stage',C.c_char*64),('field',C.c_char*64),
              ('record_kind',C.c_char*16),('derivative_mode',C.c_char*16),('direction_id',C.c_char*128),('seed_sha256',C.c_char*65),('cotangent_id',C.c_char*128),
              ('runtime_call',C.c_uint64),('one_step_call',C.c_uint64),('outer_loop',C.c_uint64),('substep_n',C.c_uint64),('event_ordinal',C.c_uint64),
              ('b_zero',C.c_int64),('k_zero',C.c_int64),('native_level_bottom_first',C.c_int64),('B',C.c_int64),('K',C.c_int64)]

class InstrumentedSequence:
    """Immutable #588 input/order snapshot, confined to one process and thread."""
    __slots__=('pid','thread','next_sequence','poisoned','_schedule','_effective','_nominal','_cotangents')
    def __setattr__(self,name,value):
        if name in ('_schedule','_effective','_nominal','_cotangents') and hasattr(self,name):raise AttributeError('canonical snapshot is immutable')
        object.__setattr__(self,name,value)
    def __init__(self,plan_path,selected_path,contract_path):
        plan,_,_=load_inputs(plan_path,selected_path,contract_path)
        inputs={x['id']:tuple(x['words']) for x in plan['inputs']}
        schedule={c['sequence']:(c['input_id'],c['mode'],inputs[c['input_id']]) for c in plan['calls']}
        if set(schedule)!=set(range(1,101)):raise ValueError('canonical sequence inventory')
        self._schedule=MappingProxyType(schedule)
        effective,nominal,cotangents=seed_specs(plan)
        self._effective=MappingProxyType({k:(v['center'],v['direction'],v['step_id'],tuple(v['evaluation_input_words']),tuple(v['effective_direction_words'])) for k,v in effective.items()})
        self._nominal=MappingProxyType({k:tuple(v) for k,v in nominal.items()})
        self._cotangents=MappingProxyType({k:tuple(v) for k,v in cotangents.items()})
        self.pid=os.getpid();self.thread=threading.get_ident();self.next_sequence=1;self.poisoned=False
    def check(self,call,input_words):
        if self.poisoned or os.getpid()!=self.pid or threading.get_ident()!=self.thread:raise RuntimeError('instrumented sequence invalid, restarted or wrong thread')
        seq=call.get('sequence');mode=call.get('mode');input_id=call.get('input_id')
        if type(seq) is not int or seq!=self.next_sequence or seq not in self._schedule:raise RuntimeError('instrumented sequence/order mismatch')
        expected_id,expected_mode,expected_words=self._schedule[seq]
        if (input_id,mode)!=(expected_id,expected_mode):raise RuntimeError('canonical call identity mismatch')
        if tuple(input_words)!=expected_words:raise RuntimeError('canonical 624-word input mismatch')
    def check_graph_seeds(self,call,effective,nominal,cotangents):
        expected={k:v for k,v in self._effective.items() if v[0]==call['input_id']}
        if set(effective)!=set(expected) or set(nominal)!=set(self._nominal) or set(cotangents)!=set(self._cotangents):raise RuntimeError('canonical graph seed inventory mismatch')
        for ident,(center,direction,step,evaluation,seed) in expected.items():
            item=effective[ident]
            if (item.get('id'),item.get('center'),item.get('direction'),item.get('step_id'))!=(ident,center,direction,step) or tuple(item.get('evaluation_input_words',()))!=evaluation or tuple(item.get('effective_direction_words',()))!=seed or item.get('seed_sha256')!=words_sha(seed):raise RuntimeError('canonical effective seed mismatch')
        if any(tuple(nominal[k])!=v for k,v in self._nominal.items()) or any(tuple(cotangents[k])!=v for k,v in self._cotangents.items()):raise RuntimeError('canonical nominal/cotangent seed mismatch')
    def effective_seed(self,ident,center):
        if ident not in self._effective or self._effective[ident][0]!=center:raise RuntimeError('unknown canonical effective seed')
        return self._effective[ident][4]
    def complete(self):self.next_sequence+=1
    def fail(self):self.poisoned=True
    def skip_optional(self,call):
        if self.poisoned or os.getpid()!=self.pid or threading.get_ident()!=self.thread:raise RuntimeError('instrumented sequence invalid, restarted or wrong thread')
        seq=call.get('sequence')
        if type(seq) is not int or seq!=self.next_sequence or seq not in range(94,101):raise RuntimeError('only next optional call may be skipped')
        expected_id,expected_mode,_=self._schedule[seq]
        if (call.get('input_id'),call.get('mode'))!=(expected_id,expected_mode):raise RuntimeError('canonical call identity mismatch')
        self.complete()

def decode(word):return struct.unpack('>d',bytes.fromhex(word))[0]
def encode(value):return struct.pack('>d',value).hex()
def vector(words,count):
    if len(words)!=count or any(not isinstance(w,str) or len(w)!=16 for w in words):raise ValueError('invalid packed vector')
    values=[decode(w) for w in words]
    if not all(map(math.isfinite,values)):raise ValueError('nonfinite input')
    return (D*count)(*values)

def bind(lib, installed=False):
    base=[PD,PD,C.c_int,C.c_int,C.c_int,D,C.c_int,PD,PH,C.POINTER(C.c_float),D,D]
    step=lib.kdm6_step_ad_c if installed else lib.kdm6_step_ad_state_forcing_c
    step.argtypes=base if installed else base+[C.c_uint32,C.c_int64];step.restype=C.c_int
    close=lib.kdm6_handle_closep_c;close.argtypes=[PH];close.restype=C.c_int
    if not installed:
        jvp=lib.kdm6_handle_state_forcing_jvp_c;jvp.argtypes=[HANDLE,PD,PD,PD];jvp.restype=C.c_int
        vjp=lib.kdm6_handle_state_forcing_vjp_c;vjp.argtypes=[HANDLE,PD,PD,PD];vjp.restype=C.c_int
    return step,close

def bind_sidecar(lib):
    begin=lib.kdm6_batch5_begin_c;begin.argtypes=[C.c_char_p,C.c_char_p,C.c_uint64];begin.restype=C.c_int
    count=lib.kdm6_batch5_count_c;count.argtypes=[];count.restype=C.c_uint64
    meta=lib.kdm6_batch5_metadata_c;meta.argtypes=[C.c_uint64,C.POINTER(Meta),C.c_size_t];meta.restype=C.c_int
    value=lib.kdm6_batch5_value_word_c;value.argtypes=[C.c_uint64,C.POINTER(C.c_uint64),C.POINTER(C.c_int)];value.restype=C.c_int
    clear=lib.kdm6_batch5_clear_c;clear.argtypes=[];clear.restype=None
    return begin,count,meta,value,clear

def bind_graph_sidecar(lib):
    token=lib.kdm6_batch5_binding_token_c;token.argtypes=[HANDLE,C.POINTER(C.c_uint64)];token.restype=C.c_int
    jvp=lib.kdm6_batch5_intermediate_jvp_c;jvp.argtypes=[HANDLE,C.c_uint64,C.c_uint64,PD,C.c_size_t,PD,C.POINTER(C.c_int)];jvp.restype=C.c_int
    return token,jvp

def bind_intermediate_vjp(lib):
    vjp=lib.kdm6_batch5_intermediate_vjp_c
    vjp.argtypes=[HANDLE,C.c_uint64,C.c_uint64,D,PD,C.c_size_t,C.POINTER(C.c_uint16),C.POINTER(C.c_int)]
    vjp.restype=C.c_int
    return vjp

def _copy_records(call,count,meta,value,max_records):
    if type(max_records) is not int or not 1<=max_records<=MAX_RECORDS:raise RuntimeError('sidecar limit outside bounds')
    n=count()
    if n<1 or n>max_records:raise RuntimeError('sidecar count outside bounds')
    records=[]; ordinals={}
    for i in range(n):
        m=Meta();m.abi_version=META_VERSION;m.struct_size=C.sizeof(Meta)
        if meta(i,C.byref(m),C.sizeof(Meta))!=0:raise RuntimeError('sidecar metadata copy failed')
        if m.abi_version!=META_VERSION or m.struct_size!=C.sizeof(Meta):raise RuntimeError('sidecar metadata ABI mismatch')
        row={k:getattr(m,k).decode('ascii') for k in ('input_id','mode','family','scope','stage','field','record_kind','derivative_mode','direction_id','seed_sha256','cotangent_id')}
        row.update({k:getattr(m,k) for k in ('runtime_call','one_step_call','outer_loop','substep_n','event_ordinal','b_zero','k_zero','native_level_bottom_first','B','K')})
        if row['input_id']!=call['input_id'] or row['mode']!=call['mode'] or row['runtime_call']!=call['sequence'] or row['b_zero']!=0 or row['B']!=1:raise RuntimeError('sidecar call identity mismatch')
        if row['scope']=='layer':
            if row['K']!=39 or not 0<=row['k_zero']<39 or row['native_level_bottom_first']!=39-row['k_zero']:raise RuntimeError('sidecar layer identity mismatch')
        elif row['scope']=='column':
            if (row['k_zero'],row['native_level_bottom_first'],row['K'])!=(-1,-1,-1):raise RuntimeError('sidecar column identity mismatch')
        else:raise RuntimeError('unknown sidecar scope')
        if any(row[k]!='none' for k in ('derivative_mode','direction_id','seed_sha256','cotangent_id')):raise RuntimeError('sidecar derivative identity in value-only mode')
        if call['mode']=='capture_on_value':
            bits=C.c_uint64();kind=C.c_int()
            if value(i,C.byref(bits),C.byref(kind))!=0:raise RuntimeError('sidecar value copy failed')
            if kind.value==1 and bits.value<=0xffffffff:row.update(dtype='f32',raw_hex=f'{bits.value:08x}')
            elif kind.value==2:row.update(dtype='f64',raw_hex=f'{bits.value:016x}')
            elif kind.value==3 and bits.value in (0,1):row.update(dtype='bool',raw_hex=str(bits.value))
            else:raise RuntimeError('unsupported sidecar value kind')
            if kind.value in (1,2):
                decoded=struct.unpack('>f' if kind.value==1 else '>d',bytes.fromhex(row['raw_hex']))[0]
                if not math.isfinite(decoded):raise RuntimeError('nonfinite sidecar value')
            if row['record_kind']!=('mask' if kind.value==3 else 'value'):raise RuntimeError('sidecar record kind mismatch')
        elif call['mode']=='center_joint_graph':
            if row['record_kind'] not in ('value','mask'):raise RuntimeError('unsupported graph record kind')
        else:raise RuntimeError('sidecar metadata mode mismatch')
        key=tuple(row[k] for k in ('input_id','mode','runtime_call','one_step_call','outer_loop','family','substep_n','scope','b_zero','k_zero','stage','field','record_kind'))
        expected=ordinals.get(key,0)
        if row['event_ordinal']!=expected:raise RuntimeError('sidecar event ordinal mismatch')
        ordinals[key]=expected+1;records.append(row)
    return records

def _execute_bound(lib,call,input_words,effective,nominal,cotangents,dso_sha256,*,sequence_guard=None,max_records=MAX_RECORDS,intermediate_requests=None,intermediate_vjp_requests=None):
    """Synthetic-tested mechanics only; caller-supplied DSO hash is unverified.

    For instrumented sequences 1..93 a guard must persist on the same thread and
    process, without skipped/retried calls; any failure poisons it. Sidecar v1
    is copied only in capture_on_value mode, then cleared even on step/copy error.
    """
    mode=call['mode'];installed=mode=='installed_value_optional';graph=mode=='center_joint_graph';capture=mode=='capture_on_value'
    if mode not in ('capture_off_value','capture_on_value','center_joint_graph','installed_value_optional'):raise ValueError('unsupported call mode')
    if not isinstance(sequence_guard,InstrumentedSequence):raise RuntimeError('persistent canonical sequence guard required')
    try:
        sequence_guard.check(call,input_words)
        requests=[] if intermediate_requests is None else intermediate_requests
        vjp_requests=[] if intermediate_vjp_requests is None else intermediate_vjp_requests
        if type(requests) is not list or type(vjp_requests) is not list or ((requests or vjp_requests) and not graph):raise RuntimeError('intermediate requests require graph mode')
        if graph:
            sequence_guard.check_graph_seeds(call,effective,nominal,cotangents)
            effective={k:{'id':k,'center':v[0],'direction':v[1],'step_id':v[2],'evaluation_input_words':v[3],'effective_direction_words':v[4],'seed_sha256':words_sha(v[4])} for k,v in sequence_guard._effective.items() if v[0]==call['input_id']}
            nominal=dict(sequence_guard._nominal);cotangents=dict(sequence_guard._cotangents)
            for request in requests:
                if type(request) is not dict or set(request)!={'selector','seed_id'} or type(request['selector']) is not dict or set(request['selector'])!=set(SELECTOR_FIELDS):raise RuntimeError('full intermediate selector required')
                if request['selector']['record_kind']!='value':raise RuntimeError('intermediate selector must identify a value')
                sequence_guard.effective_seed(request['seed_id'],call['input_id'])
            for request in vjp_requests:
                if type(request) is not dict or set(request)!={'selector','cotangent_id'} or type(request['selector']) is not dict or set(request['selector'])!=set(SELECTOR_FIELDS):raise RuntimeError('full intermediate VJP selector required')
                if request['selector']['record_kind']!='value':raise RuntimeError('intermediate VJP selector must identify a value')
                if request['cotangent_id']!='intermediate_scalar:unit':raise RuntimeError('unknown intermediate scalar cotangent')
    except BaseException:
        sequence_guard.fail()
        raise
    begun=False;h=HANDLE();result=None;close_attempted=False;success=False
    try:
        step,close=bind(lib,installed);state=vector(input_words[:STATE],STATE);forcing=vector(input_words[STATE:],FORCING);out=(D*STATE)(*[float('nan')]*STATE);xland=C.c_float(2)
        if capture or graph:
            begin,count,meta,value,clear=bind_sidecar(lib)
            if begin(call['input_id'].encode('ascii'),mode.encode('ascii'),call['sequence'])!=0:raise RuntimeError('sidecar begin failed')
            begun=True
        args=[state,forcing,1,39,1,20.0,0 if graph else 1,out,C.byref(h),C.byref(xland),10.0,10.0]
        rc=step(*args,*([] if installed else [0,0]));had=bool(h.value)
        if rc!=0 or had!=graph:raise RuntimeError('forward status/handle mismatch')
        if not all(math.isfinite(v) for v in out):raise RuntimeError('nonfinite state output')
        result={'schema':'kdm6.future_call_raw.v1','sequence':call['sequence'],'input_id':call['input_id'],'mode':mode,'claimed_dso_sha256':dso_sha256,'dso_identity_status':'CALLER_SUPPLIED_UNVERIFIED','input_words':input_words,'return_code':rc,'handle_nonnull':had,'state_output_words':[encode(v) for v in out]}
        if capture:result['sidecar_records']=_copy_records(call,count,meta,value,max_records)
        if graph:
            token_fn,intermediate_jvp=bind_graph_sidecar(lib);token=C.c_uint64()
            if token_fn(h,C.byref(token))!=0 or token.value==0:raise RuntimeError('graph handle binding token failed')
            metadata=_copy_records(call,count,meta,None,max_records);result['graph_metadata']=metadata;result['graph_binding_token']=token.value;result['selector_registry_status']='CALLER_SUPPLIED_UNVERIFIED';result['intermediate_jvps']=[]
            for request in requests:
                matches=[i for i,row in enumerate(metadata) if all(type(row[k]) is type(request['selector'][k]) and row[k]==request['selector'][k] for k in SELECTOR_FIELDS)]
                if len(matches)!=1:raise RuntimeError('intermediate selector missing or ambiguous')
                seed=sequence_guard.effective_seed(request['seed_id'],call['input_id']); tangent=D(float('nan'));status=C.c_int(-1)
                irc=intermediate_jvp(h,token.value,matches[0],vector(seed,624),624,C.byref(tangent),C.byref(status))
                if irc!=0 or status.value not in (0,1,2) or not math.isfinite(tangent.value):raise RuntimeError('intermediate JVP failed or nonfinite')
                result['intermediate_jvps'].append({'selector':dict(request['selector']),'record_index':matches[0],'seed_id':request['seed_id'],'seed_sha256':words_sha(seed),'handle_token':token.value,'return_code':irc,'status':status.value,'output_f64_word':encode(tangent.value)})
            result['intermediate_vjps']=[]
            if vjp_requests:
                intermediate_vjp=bind_intermediate_vjp(lib)
                for request in vjp_requests:
                    matches=[i for i,row in enumerate(metadata) if all(type(row[k]) is type(request['selector'][k]) and row[k]==request['selector'][k] for k in SELECTOR_FIELDS)]
                    if len(matches)!=1:raise RuntimeError('intermediate VJP selector missing or ambiguous')
                    gradients=(D*624)(*[float('nan')]*624);mask=C.c_uint16(0);status=C.c_int(-1)
                    vrc=intermediate_vjp(h,token.value,matches[0],1.0,gradients,624,C.byref(mask),C.byref(status))
                    if vrc!=0 or status.value not in (0,1,2) or not all(math.isfinite(v) for v in gradients):raise RuntimeError('intermediate VJP failed or nonfinite')
                    if (status.value==0 and mask.value==0) or (status.value in (1,2) and mask.value!=0):raise RuntimeError('intermediate VJP status/mask mismatch')
                    words=[encode(v) for v in gradients]
                    for field in range(16):
                        if not (mask.value & (1<<field)) and any(w!='0000000000000000' for w in words[field*39:(field+1)*39]):raise RuntimeError('undefined intermediate VJP slot is not positive zero')
                    result['intermediate_vjps'].append({'selector':dict(request['selector']),'record_index':matches[0],'cotangent_id':'intermediate_scalar:unit','cotangent_word':'3ff0000000000000','cotangent_sha256':words_sha(['3ff0000000000000']),'handle_token':token.value,'return_code':vrc,'status':status.value,'connected_field_mask':mask.value,'gradient_words':words,'gradient_sha256':words_sha(words),'state_gradient_words':words[:STATE],'forcing_gradient_words':words[STATE:]})
            handle_id=f"graph:{call['sequence']}:{call['input_id']}";result['graph_handle_id']=handle_id;outputs={};payloads={}
            for ident,entry in effective.items():
                seed=entry['effective_direction_words'];tan=(D*STATE)(*[float('nan')]*STATE);jrc=lib.kdm6_handle_state_forcing_jvp_c(h,vector(seed[:STATE],STATE),vector(seed[STATE:],FORCING),tan);jwords=[encode(v) for v in tan]
                if jrc!=0 or not all(math.isfinite(v) for v in tan):raise RuntimeError('effective JVP failed: '+ident)
                outputs[ident]=words_sha(jwords);payloads[ident]={'schema':'kdm6.effective_jvp_payload.v1','id':ident,'center':entry['center'],'direction':entry['direction'],'step_id':entry['step_id'],'jvp_return_code':jrc,'graph_handle_id':handle_id,'graph_sequence':call['sequence'],'evaluation_input_words':input_words,'effective_direction_words':seed,'seed_sha256':words_sha(seed),'graph_forward_output_words':result['state_output_words'],'jvp_output_words':jwords,'jvp_output_sha256':words_sha(jwords)}
            result['effective_jvp_output_sha256']=outputs;result['effective_jvp_payloads']=payloads;result['nominal_jvps']={}
            for ident,seed in nominal.items():
                tan=(D*STATE)(*[float('nan')]*STATE);jrc=lib.kdm6_handle_state_forcing_jvp_c(h,vector(seed[:STATE],STATE),vector(seed[STATE:],FORCING),tan);values=[encode(v) for v in tan]
                if jrc!=0 or not all(math.isfinite(v) for v in tan):raise RuntimeError('nominal JVP failed: '+ident)
                result['nominal_jvps'][ident]={'rc':jrc,'seed_words':seed,'seed_sha256':words_sha(seed),'output_words':values}
            result['vjps']={}
            for ident,seed in cotangents.items():
                gs=(D*STATE)(*[float('nan')]*STATE);gf=(D*FORCING)(*[float('nan')]*FORCING);vrc=lib.kdm6_handle_state_forcing_vjp_c(h,vector(seed,STATE),gs,gf)
                if vrc!=0 or not all(math.isfinite(v) for v in gs) or not all(math.isfinite(v) for v in gf):raise RuntimeError('VJP failed: '+ident)
                result['vjps'][ident]={'rc':vrc,'seed_words':seed,'seed_sha256':words_sha(seed),'state_words':[encode(v) for v in gs],'forcing_words':[encode(v) for v in gf]}
        close_rc=None
        if h.value:
            close_attempted=True;close_rc=close(C.byref(h))
        if close_rc not in (None,0) or h.value:raise RuntimeError('handle close failed')
        result['close_rc']=close_rc;result['handle_null_after']=not bool(h.value)
        success=True
        return result
    except BaseException:
        sequence_guard.fail()
        raise
    finally:
        try:
            try:
                if h.value and not close_attempted:
                    close_attempted=True
                    if close(C.byref(h))!=0 or h.value:raise RuntimeError('handle close failed during cleanup')
            finally:
                if begun:clear()
        except BaseException:
            sequence_guard.fail()
            raise
        if success:sequence_guard.complete()

def run_registered(*_args, **_kwargs):
    raise RuntimeError('BLOCKED: no committed EXECUTION_READY successor, new DSO, live sidecar ABI or reviewed atomic field catalog')

if __name__=='__main__':run_registered()
