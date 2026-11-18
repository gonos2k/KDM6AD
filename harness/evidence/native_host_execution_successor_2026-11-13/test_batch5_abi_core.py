import copy,ctypes as C,pathlib,subprocess,sys,tempfile,threading,unittest
from unittest import mock
R=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(R));import batch5_preflight as preflight,batch5_abi_core as abi_core
import condition_abi_v2_reader as v2
ROOT=R.parent/'native_host_preflight_2026-11-12';SELECTED=R.parent/'native_host_column_f32_2026-11-11/raw/selected_full.json'

class Fn:
 def __init__(self,fn):self.fn=fn
 def __call__(self,*args):return self.fn(*args)
class FakeABI:
 def __init__(self,*,fail_step=False,fail_meta=False,fail_value=False,bad_count=False,fail_begin=False,fail_clear=False,nan_value=False,f32_nan=False,wrong_token=False,nan_jvp=False,duplicate=False,vjp_rc=False,vjp_nan=False,vjp_badmask=False,vjp_badfill=False,vjp_status=0,rain_rc=False,rain_nan=False,rain_flag_bad=False,rain_mismatch=False,off_extra=False,primal_rc=False,primal_nan=False,graph_flag=1,missing_rain=False,duplicate_rain=False,value_flag_one=False):
  self.events=[];self.fail_step=fail_step;self.fail_meta=fail_meta;self.fail_value=fail_value;self.bad_count=bad_count;self.fail_begin=fail_begin;self.fail_clear=fail_clear;self.nan_value=nan_value;self.f32_nan=f32_nan;self.wrong_token=wrong_token;self.nan_jvp=nan_jvp;self.duplicate=duplicate;self.vjp_rc=vjp_rc;self.vjp_nan=vjp_nan;self.vjp_badmask=vjp_badmask;self.vjp_badfill=vjp_badfill;self.vjp_status=vjp_status;self.rain_rc=rain_rc;self.rain_nan=rain_nan;self.rain_flag_bad=rain_flag_bad;self.rain_mismatch=rain_mismatch;self.off_extra=off_extra;self.primal_rc=primal_rc;self.primal_nan=primal_nan;self.graph_flag=graph_flag;self.missing_rain=missing_rain;self.duplicate_rain=duplicate_rain;self.value_flag_one=value_flag_one;self.active=None
  def step(*args):
   self.events.append('step');out=args[7];h=C.cast(args[8],C.POINTER(C.c_void_p))
   if self.fail_step:return -1
   for i in range(468):out[i]=0.0
   h[0]=C.c_void_p(123 if args[6]==0 else None);return 0
  def close(ptr):self.events.append('close');C.cast(ptr,C.POINTER(C.c_void_p))[0]=C.c_void_p();return 0
  def jvp(_h,s,f,out):
   for i in range(468):out[i]=s[i]
   return 0
  def vjp(_h,u,gs,gf):
   for i in range(468):gs[i]=u[i]
   for i in range(156):gf[i]=0
   return 0
  def begin(input_id,mode,seq):
   self.events.append(('begin',input_id,mode,seq))
   if self.fail_begin:return -1
   self.active=(input_id,mode,seq);return 0
  def count():
   self.events.append('count')
   if self.bad_count:return abi_core.MAX_RECORDS+1
   if self.active[1]==b'capture_off_value':return 1 if self.off_extra else 0
   return 2 if self.missing_rain else (4 if self.duplicate_rain else 3)
  def meta(index,ptr,size):
   self.events.append(('metadata',index))
   if self.fail_meta:return -1
   m=C.cast(ptr,C.POINTER(abi_core.Meta)).contents
   if m.abi_version!=1 or m.struct_size!=size:return -1
   if index in (2,3):
    m.input_id=self.active[0];m.mode=self.active[1];m.family=b'runtime_exit';m.scope=b'column';m.stage=b'fnresult';m.field=b'rain_increment';m.record_kind=b'value';m.derivative_mode=b'none';m.direction_id=b'none';m.seed_sha256=b'none';m.cotangent_id=b'none';m.runtime_call=self.active[2];m.one_step_call=1;m.outer_loop=0;m.substep_n=0;m.event_ordinal=1 if index==3 else 0;m.b_zero=0;m.k_zero=-1;m.native_level_bottom_first=-1;m.B=1;m.K=-1;return 0
   m.input_id=self.active[0];m.mode=self.active[1];m.family=b'microphysics';m.scope=b'layer';m.stage=b'synthetic';m.field=b'value' if index==0 or self.duplicate else b'condition';m.record_kind=b'value' if index==0 or self.duplicate else b'mask';m.derivative_mode=b'none';m.direction_id=b'none';m.seed_sha256=b'none';m.cotangent_id=b'none';m.runtime_call=self.active[2];m.one_step_call=1;m.outer_loop=0;m.substep_n=0;m.event_ordinal=0;m.b_zero=0;m.k_zero=23;m.native_level_bottom_first=16;m.B=1;m.K=39;return 0
  def val(index,bitsp,kindp):
   self.events.append(('value',index))
   if self.fail_value:return -1
   C.cast(bitsp,C.POINTER(C.c_uint64))[0]=(0x7fc00000 if self.f32_nan else (0x7ff8000000000000 if self.nan_value else 0x3ff0000000000000)) if index==0 else (1 if index==1 else (0x4008000000000000 if self.rain_mismatch else 0x4000000000000000));C.cast(kindp,C.POINTER(C.c_int))[0]=(1 if self.f32_nan else 2) if index==0 else (3 if index==1 else 2);return 0
  def token(handle,out):
   self.events.append(('token',handle.value))
   if handle.value!=123:return -1
   C.cast(out,C.POINTER(C.c_uint64))[0]=999 if self.wrong_token else 567;return 0
  def rain(handle,token,input_id,mode,seq,out,flag):
   self.events.append(('rain',input_id,mode,seq,token))
   if self.rain_rc or self.active!=(input_id,mode,seq):return -1
   if mode==b'center_joint_graph' and (not handle or handle.value!=123 or token!=567):return -1
   if mode!=b'center_joint_graph' and (handle is not None or token!=0):return -1
   C.cast(out,C.POINTER(C.c_uint64))[0]=0x7ff8000000000000 if self.rain_nan else 0x4000000000000000
   C.cast(flag,C.POINTER(C.c_int))[0]=2 if self.rain_flag_bad else (self.graph_flag if mode==b'center_joint_graph' else (1 if self.value_flag_one else 0));return 0
  def primal(handle,token,index,out,flag):
   self.events.append(('primal',handle.value,token,index))
   if self.primal_rc or handle.value!=123 or token!=567:return -1
   C.cast(out,C.POINTER(C.c_uint64))[0]=0x7ff8000000000000 if self.primal_nan else (0x4008000000000000 if index==2 and self.rain_mismatch else (0x4000000000000000 if index==2 else 0x3ff0000000000000))
   C.cast(flag,C.POINTER(C.c_int))[0]=2 if self.rain_flag_bad else self.graph_flag;return 0
  def intermediate(handle,token,index,seed,count,out,status):
   self.events.append(('intermediate',handle.value,token,index,count))
   if handle.value!=123 or token!=567 or count!=624:return -1
   C.cast(out,C.POINTER(C.c_double))[0]=float('nan') if self.nan_jvp else seed[15]
   C.cast(status,C.POINTER(C.c_int))[0]=0;return 0
  def intermediate_vjp(handle,token,index,cotangent,gradients,count,maskp,statusp):
   self.events.append(('intermediate_vjp',handle.value,token,index,cotangent,count))
   if handle.value!=123 or token!=567 or cotangent!=1.0 or count!=624:return -1
   addresses=(C.addressof(gradients),C.addressof(C.cast(maskp,C.POINTER(C.c_uint16)).contents),C.addressof(C.cast(statusp,C.POINTER(C.c_int)).contents))
   if len(set(addresses))!=3:return -1
   mask=0 if self.vjp_status in (1,2) else ((1<<0)|(1<<11)|(1<<12)|(1<<15))
   if self.vjp_badmask:mask=0 if self.vjp_status==0 else 1
   for i in range(624):gradients[i]=float(i+1) if mask & (1<<(i//39)) else 0.0
   gradients[0]=0.0
   if self.vjp_nan:gradients[0]=float('nan')
   if self.vjp_badfill:gradients[39]=1.0
   C.cast(maskp,C.POINTER(C.c_uint16))[0]=mask;C.cast(statusp,C.POINTER(C.c_int))[0]=self.vjp_status
   return -1 if self.vjp_rc else 0
  def clear():
   self.events.append('clear');self.active=None
   if self.fail_clear:raise RuntimeError('synthetic clear failure')
  self.kdm6_step_ad_c=Fn(step);self.kdm6_step_ad_state_forcing_c=Fn(step);self.kdm6_handle_closep_c=Fn(close);self.kdm6_handle_state_forcing_jvp_c=Fn(jvp);self.kdm6_handle_state_forcing_vjp_c=Fn(vjp);self.kdm6_batch5_begin_c=Fn(begin);self.kdm6_batch5_count_c=Fn(count);self.kdm6_batch5_metadata_c=Fn(meta);self.kdm6_batch5_value_word_c=Fn(val);self.kdm6_batch5_binding_token_c=Fn(token);self.kdm6_batch5_result_rain_c=Fn(rain);self.kdm6_batch5_graph_primal_c=Fn(primal);self.kdm6_batch5_intermediate_jvp_c=Fn(intermediate);self.kdm6_batch5_intermediate_vjp_c=Fn(intermediate_vjp);self.kdm6_batch5_clear_c=Fn(clear)

class FakeV2(FakeABI):
 def __init__(self,*,bad_identity=False,bad_phase=False,fail_raw=False):
  super().__init__();self.bad_identity=bad_identity;self.bad_phase=bad_phase;self.fail_raw=fail_raw
  def check(h,t):
   if self.active is None:raise RuntimeError('v2 called after clear')
   graph=self.active[1]==b'center_joint_graph'
   if graph and (not h or h.value!=123 or t!=567):raise RuntimeError('wrong graph binding')
   if not graph and (h is not None or t!=0):raise RuntimeError('wrong value binding')
  def count(h,t,p):
   check(h,t);self.events.append('v2_count');C.cast(p,C.POINTER(C.c_uint64))[0]=1;return 0
  def meta(h,t,i,p,size):
   check(h,t);self.events.append('v2_meta');m=C.cast(p,C.POINTER(v2.Meta)).contents
   if m.abi_version!=2 or m.struct_size!=size:return -1
   m.input_id=b'other' if self.bad_identity else self.active[0];m.mode=b'capture_on_value' if self.bad_phase else self.active[1];m.family=b'main';m.stage=b's';m.field=b'f';m.source_hook=b'h';m.context_epoch=7;m.runtime_call=self.active[2];m.one_step_call=1;m.outer_loop=1;m.substep_n=1;m.event_ordinal=0;m.causal_index=v2.NO_CAUSE;m.b_zero=0;m.k_zero=23;m.native_level_bottom_first=16;m.B=1;m.K=39;m.role=1;m.dtype=1;m.scope=1;m.reason=0;return 0
  def raw(h,t,i,p):
   check(h,t);self.events.append('v2_raw');C.cast(p,C.POINTER(C.c_uint64))[0]=1;return -1 if self.fail_raw else 0
  def verify(h,t,p):
   check(h,t);self.events.append('v2_verify');C.cast(p,C.POINTER(C.c_uint64))[0]=0;return 0
  self.kdm6_batch5_condition_v2_count_c=Fn(count);self.kdm6_batch5_condition_v2_meta_c=Fn(meta);self.kdm6_batch5_condition_v2_raw_c=Fn(raw);self.kdm6_batch5_condition_v2_verify_absences_c=Fn(verify)

class PreflightTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.plan,_,_=preflight.load_inputs(ROOT/'plan.json.gz',SELECTED,ROOT/'field_contract.json');cls.eff,cls.nom,cls.vjp=preflight.seed_specs(cls.plan);cls.center=next(v for v in cls.plan['inputs'] if v['id']=='baseline')
 def guard(self):return abi_core.InstrumentedSequence(ROOT/'plan.json.gz',SELECTED,ROOT/'field_contract.json')
 def words_for(self,call):return next(x['words'] for x in self.plan['inputs'] if x['id']==call['input_id'])
 def test_inputs_and_effective_seeds_match_receipt_contract(self):
  self.assertEqual(len(self.plan['inputs']),45);self.assertEqual(len(self.plan['calls']),100);self.assertEqual(len(self.eff),21)
  sys.path.insert(0,str(ROOT));import receipt_schema
  expected=receipt_schema.effective_seed_specs();self.assertEqual(set(self.eff),set(expected))
  for key,item in self.eff.items():self.assertEqual(item['effective_direction_words'],expected[key]['effective_direction_words'])
 def test_hash_mismatch_and_production_block(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'plan';p.write_bytes(b'wrong')
   with self.assertRaisesRegex(ValueError,'hash'):preflight.load_inputs(p,SELECTED,ROOT/'field_contract.json')
  with self.assertRaisesRegex(RuntimeError,'BLOCKED'):abi_core.run_registered()
 def test_synthetic_sidecar_sequence_and_copy(self):
  lib=FakeABI();guard=self.guard();off,on=self.plan['calls'][:2]
  v=abi_core._execute_bound(lib,off,self.center['words'],{},self.nom,self.vjp,'a'*64,sequence_guard=guard);self.assertEqual(lib.events,[('begin',b'baseline',b'capture_off_value',1),'step',('rain',b'baseline',b'capture_off_value',1,0),'count','clear']);self.assertEqual(v['dso_identity_status'],'CALLER_SUPPLIED_UNVERIFIED');self.assertNotIn('dso_sha256',v)
  lib.events.clear();v=abi_core._execute_bound(lib,on,self.center['words'],{},self.nom,self.vjp,'a'*64,sequence_guard=guard)
  self.assertEqual(lib.events,[('begin',b'baseline',b'capture_on_value',2),'step',('rain',b'baseline',b'capture_on_value',2,0),'count',('metadata',0),('value',0),('metadata',1),('value',1),('metadata',2),('value',2),'clear']);self.assertEqual([(x['dtype'],x['raw_hex']) for x in v['sidecar_records']],[('f64','3ff0000000000000'),('bool','1'),('f64','4000000000000000')]);self.assertEqual(guard.next_sequence,3)
 def test_sidecar_failure_clears_and_never_returns_partial(self):
  for options in ({'fail_step':True},{'fail_meta':True},{'fail_value':True},{'bad_count':True},{'nan_value':True},{'f32_nan':True}):
   lib=FakeABI(**options);guard=self.guard();guard.check(self.plan['calls'][0],self.words_for(self.plan['calls'][0]));guard.complete()
   with self.assertRaises(RuntimeError):abi_core._execute_bound(lib,self.plan['calls'][1],self.center['words'],{},self.nom,self.vjp,'a'*64,sequence_guard=guard)
   self.assertEqual(lib.events[-1],'clear');self.assertTrue(guard.poisoned)
 def test_begin_failure_does_not_clear_prior_context(self):
  lib=FakeABI(fail_begin=True);guard=self.guard();guard.check(self.plan['calls'][0],self.words_for(self.plan['calls'][0]));guard.complete()
  with self.assertRaisesRegex(RuntimeError,'begin failed'):abi_core._execute_bound(lib,self.plan['calls'][1],self.center['words'],{},self.nom,self.vjp,'a'*64,sequence_guard=guard)
  self.assertEqual(lib.events,[('begin',b'baseline',b'capture_on_value',2)]);self.assertTrue(guard.poisoned)
 def test_clear_failure_invalidates_sequence(self):
  lib=FakeABI(fail_clear=True);guard=self.guard();guard.check(self.plan['calls'][0],self.words_for(self.plan['calls'][0]));guard.complete()
  with self.assertRaisesRegex(RuntimeError,'clear failure'):abi_core._execute_bound(lib,self.plan['calls'][1],self.center['words'],{},self.nom,self.vjp,'a'*64,sequence_guard=guard)
  self.assertTrue(guard.poisoned);self.assertEqual(guard.next_sequence,2)
 def test_order_wrong_thread_and_restart_fail_closed(self):
  guard=self.guard()
  with self.assertRaisesRegex(RuntimeError,'order'):guard.check(self.plan['calls'][1],self.words_for(self.plan['calls'][1]))
  errors=[]
  def other():
   try:guard.check(self.plan['calls'][0],self.words_for(self.plan['calls'][0]))
   except RuntimeError as e:errors.append(str(e))
  t=threading.Thread(target=other);t.start();t.join();self.assertEqual(len(errors),1)
  with mock.patch.object(abi_core.os,'getpid',return_value=guard.pid+1):
   with self.assertRaisesRegex(RuntimeError,'restarted'):guard.check(self.plan['calls'][0],self.words_for(self.plan['calls'][0]))
  for call in self.plan['calls'][:93]:guard.check(call,self.words_for(call));guard.complete()
  self.assertEqual(guard.next_sequence,94)
 def test_wrong_id_and_rehashed_substitution_never_reach_step(self):
  lib=FakeABI();guard=self.guard();call=dict(self.plan['calls'][0]);call['input_id']='upper'
  with self.assertRaisesRegex(RuntimeError,'identity'):abi_core._execute_bound(lib,call,self.center['words'],{},self.nom,self.vjp,'a'*64,sequence_guard=guard)
  self.assertEqual(lib.events,[])
  guard=self.guard();call=dict(self.plan['calls'][0]);substituted=self.center['words'].copy();substituted[0]='0000000000000000';call['input_sha256']=preflight.words_sha(substituted)
  with self.assertRaisesRegex(RuntimeError,'624-word'):abi_core._execute_bound(lib,call,substituted,{},self.nom,self.vjp,'a'*64,sequence_guard=guard)
  self.assertEqual(lib.events,[]);self.assertTrue(guard.poisoned)
  with self.assertRaises(TypeError):guard._schedule[1]=('wrong','wrong',())
  with self.assertRaises(AttributeError):guard._schedule={}
 def test_explicit_optional_skip_follows_canonical_order(self):
  guard=self.guard()
  for call in self.plan['calls'][:93]:guard.check(call,self.words_for(call));guard.complete()
  bad=dict(self.plan['calls'][93]);bad['input_id']='wrong'
  with self.assertRaisesRegex(RuntimeError,'identity'):guard.skip_optional(bad)
  for call in self.plan['calls'][93:]:guard.skip_optional(call)
  self.assertEqual(guard.next_sequence,101)
 def test_synthetic_optional_installed_is_canonically_bound(self):
  guard=self.guard()
  for call in self.plan['calls'][:93]:guard.check(call,self.words_for(call));guard.complete()
  call=self.plan['calls'][93];lib=FakeABI()
  result=abi_core._execute_bound(lib,call,self.words_for(call),{},self.nom,self.vjp,'a'*64,sequence_guard=guard)
  self.assertEqual(lib.events,['step']);self.assertEqual(result['dso_identity_status'],'CALLER_SUPPLIED_UNVERIFIED');self.assertEqual(guard.next_sequence,95)
 def graph_setup(self):
  guard=self.guard()
  for c in self.plan['calls'][:90]:guard.check(c,self.words_for(c));guard.complete()
  call=self.plan['calls'][90];sub={k:v for k,v in self.eff.items() if v['center']=='baseline'}
  selector={'input_id':'baseline','mode':'center_joint_graph','runtime_call':91,'one_step_call':1,'outer_loop':0,'family':'microphysics','substep_n':0,'scope':'layer','b_zero':0,'k_zero':23,'native_level_bottom_first':16,'B':1,'K':39,'stage':'synthetic','field':'value','record_kind':'value','event_ordinal':0}
  return guard,call,sub,selector
 def test_v2_same_call_value_and_graph_lifecycle(self):
  guard=self.guard();off=self.plan['calls'][0];guard.check(off,self.words_for(off));guard.complete();call=self.plan['calls'][1];lib=FakeV2()
  result=abi_core._execute_bound(lib,call,self.center['words'],{},self.nom,self.vjp,'a'*64,sequence_guard=guard,require_condition_v2=True);asset=result['condition_v2_asset']
  self.assertEqual(asset['input_words'],self.center['words']);self.assertEqual(asset['state_output_words'],result['state_output_words']);self.assertEqual(asset['same_call_rain'],result['same_call_rain']);self.assertEqual(asset['capture']['records'][0]['context_epoch'],7);self.assertLess(lib.events.index('v2_raw'),lib.events.index('clear'));self.assertEqual(asset['dso_identity_status'],'CALLER_SUPPLIED_UNVERIFIED')
  guard,call,sub,_=self.graph_setup();lib=FakeV2();result=abi_core._execute_bound(lib,call,self.center['words'],sub,self.nom,self.vjp,'a'*64,sequence_guard=guard,require_condition_v2=True);asset=result['condition_v2_asset'];self.assertTrue(asset['capture']['graph_metadata_only']);self.assertIsNone(asset['capture']['records'][0]['raw_hex']);self.assertEqual(asset['graph_handle_token'],567);self.assertNotIn('v2_raw',lib.events);self.assertLess(lib.events.index('v2_meta'),lib.events.index('close'))
 def test_v2_reader_loads_from_file_without_import_path(self):
  script="""import importlib.util, pathlib, sys
p=pathlib.Path(sys.argv[1]); spec=importlib.util.spec_from_file_location('fixture_test',p/'test_batch5_abi_core.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
sys.path[:]=[x for x in sys.path if pathlib.Path(x or '.').resolve()!=p];sys.modules.pop('condition_abi_v2_reader',None)
t=m.PreflightTest();t.setUpClass();guard=t.guard();guard.check(t.plan['calls'][0],t.words_for(t.plan['calls'][0]));guard.complete();lib=m.FakeV2()
r=m.abi_core._execute_bound(lib,t.plan['calls'][1],t.center['words'],{},t.nom,t.vjp,'a'*64,sequence_guard=guard,require_condition_v2=True)
assert r['condition_v2_asset']['capture']['records'][0]['context_epoch']==7
"""
  with tempfile.TemporaryDirectory() as directory:
   subprocess.run([sys.executable,'-I','-c',script,str(R)],cwd=directory,check=True,env={'PATH':'/usr/bin:/bin'})
 def test_v2_failure_poison_clear_and_no_partial(self):
  for opts in ({'bad_identity':True},{'fail_raw':True}):
   guard=self.guard();guard.check(self.plan['calls'][0],self.words_for(self.plan['calls'][0]));guard.complete();lib=FakeV2(**opts)
   with self.assertRaises(RuntimeError):abi_core._execute_bound(lib,self.plan['calls'][1],self.center['words'],{},self.nom,self.vjp,'a'*64,sequence_guard=guard,require_condition_v2=True)
   self.assertTrue(guard.poisoned);self.assertEqual(lib.events[-1],'clear')
  guard,call,sub,_=self.graph_setup();lib=FakeV2(bad_phase=True)
  with self.assertRaises(RuntimeError):abi_core._execute_bound(lib,call,self.center['words'],sub,self.nom,self.vjp,'a'*64,sequence_guard=guard,require_condition_v2=True)
  self.assertTrue(guard.poisoned);self.assertEqual(lib.events[-2:],['close','clear'])
  guard=self.guard();guard.check(self.plan['calls'][0],self.words_for(self.plan['calls'][0]));guard.complete();lib=FakeABI()
  with self.assertRaises(AttributeError):abi_core._execute_bound(lib,self.plan['calls'][1],self.center['words'],{},self.nom,self.vjp,'a'*64,sequence_guard=guard,require_condition_v2=True)
  self.assertEqual(lib.events[-1],'clear');self.assertTrue(guard.poisoned)
 def test_graph_intermediate_jvp_uses_bound_token_and_pinned_seed(self):
  guard,call,sub,selector=self.graph_setup();lib=FakeABI();seed_id=next(k for k,v in sub.items() if v['direction']=='th')
  result=abi_core._execute_bound(lib,call,self.center['words'],sub,self.nom,self.vjp,'a'*64,sequence_guard=guard,intermediate_requests=[{'selector':selector,'seed_id':seed_id}])
  self.assertEqual(lib.events[:4],[('begin',b'baseline',b'center_joint_graph',91),'step',('token',123),'count']);self.assertNotIn(('value',0),lib.events);self.assertNotIn(('value',1),lib.events);self.assertEqual(lib.events[-2:],['close','clear'])
  row=result['intermediate_jvps'][0];self.assertEqual(row['handle_token'],567);self.assertEqual(row['status'],0);self.assertEqual(row['seed_sha256'],preflight.words_sha(sub[seed_id]['effective_direction_words']));self.assertEqual(result['selector_registry_status'],'CALLER_SUPPLIED_UNVERIFIED')
 def test_graph_failures_clear_close_and_poison_without_partial(self):
  for options in ({'wrong_token':True},{'nan_jvp':True},{'duplicate':True},{'fail_meta':True},{'bad_count':True}):
   guard,call,sub,selector=self.graph_setup();lib=FakeABI(**options);seed_id=next(k for k,v in sub.items() if v['direction']=='th')
   with self.assertRaises(RuntimeError):abi_core._execute_bound(lib,call,self.center['words'],sub,self.nom,self.vjp,'a'*64,sequence_guard=guard,intermediate_requests=[{'selector':selector,'seed_id':seed_id}])
   self.assertTrue(guard.poisoned);self.assertEqual(lib.events[-2:],['close','clear'])
 def test_missing_selector_and_rehashed_seed_are_rejected(self):
  guard,call,sub,selector=self.graph_setup();lib=FakeABI();seed_id=next(k for k,v in sub.items() if v['direction']=='th');selector['field']='missing'
  with self.assertRaisesRegex(RuntimeError,'missing or ambiguous'):abi_core._execute_bound(lib,call,self.center['words'],sub,self.nom,self.vjp,'a'*64,sequence_guard=guard,intermediate_requests=[{'selector':selector,'seed_id':seed_id}])
  self.assertEqual(lib.events[-2:],['close','clear'])
  guard,call,sub,selector=self.graph_setup();lib=FakeABI();bad=copy.deepcopy(sub);bad[seed_id]['effective_direction_words'][15]='0000000000000000';bad[seed_id]['seed_sha256']=preflight.words_sha(bad[seed_id]['effective_direction_words'])
  with self.assertRaisesRegex(RuntimeError,'canonical effective seed'):abi_core._execute_bound(lib,call,self.center['words'],bad,self.nom,self.vjp,'a'*64,sequence_guard=guard)
  self.assertEqual(lib.events,[]);self.assertTrue(guard.poisoned)
 def test_intermediate_scalar_vjp_is_distinct_from_final_state_vjp(self):
  guard,call,sub,selector=self.graph_setup();lib=FakeABI();request={'selector':selector,'cotangent_id':'intermediate_scalar:unit'}
  result=abi_core._execute_bound(lib,call,self.center['words'],sub,self.nom,self.vjp,'a'*64,sequence_guard=guard,intermediate_vjp_requests=[request])
  self.assertEqual(len(result['intermediate_vjps']),1);row=result['intermediate_vjps'][0];self.assertEqual(row['cotangent_word'],'3ff0000000000000');self.assertEqual(row['cotangent_sha256'],preflight.words_sha(['3ff0000000000000']));self.assertEqual(row['connected_field_mask'],(1<<0)|(1<<11)|(1<<12)|(1<<15));self.assertEqual(row['gradient_words'][0],'0000000000000000');self.assertEqual(row['gradient_sha256'],preflight.words_sha(row['gradient_words']));self.assertEqual(len(row['state_gradient_words']),468);self.assertEqual(len(row['forcing_gradient_words']),156);self.assertEqual(row['handle_token'],567);self.assertEqual(row['status'],0);self.assertEqual(len(result['vjps']['state:nc:15']['seed_words']),468);self.assertEqual(lib.events[-2:],['close','clear']);self.assertNotIn(('value',0),lib.events)
 def test_duplicate_intermediate_requests_rejected_before_abi(self):
  for kind in ('jvp','vjp'):
   guard,call,sub,selector=self.graph_setup();lib=FakeABI();seed_id=next(iter(sub))
   request={'selector':selector,'seed_id':seed_id} if kind=='jvp' else {'selector':selector,'cotangent_id':'intermediate_scalar:unit'}
   kwargs={'intermediate_requests':[request,copy.deepcopy(request)]} if kind=='jvp' else {'intermediate_vjp_requests':[request,copy.deepcopy(request)]}
   with self.assertRaisesRegex(RuntimeError,'duplicate intermediate'):abi_core._execute_bound(lib,call,self.center['words'],sub,self.nom,self.vjp,'a'*64,sequence_guard=guard,**kwargs)
   self.assertEqual(lib.events,[]);self.assertTrue(guard.poisoned)
 def test_distinct_seeds_share_primal(self):
  guard,call,sub,selector=self.graph_setup();lib=FakeABI();ids=list(sub)[:2]
  result=abi_core._execute_bound(lib,call,self.center['words'],sub,self.nom,self.vjp,'a'*64,sequence_guard=guard,intermediate_requests=[{'selector':selector,'seed_id':i} for i in ids])
  self.assertEqual(len(result['intermediate_jvps']),2);self.assertEqual(lib.events.count(('primal',123,567,0)),1);self.assertEqual(lib.events.count(('intermediate',123,567,0,624)),2)
 def test_intermediate_vjp_unconnected_status_is_explicit(self):
  for status in (1,2):
   guard,call,sub,selector=self.graph_setup();lib=FakeABI(vjp_status=status);r=abi_core._execute_bound(lib,call,self.center['words'],sub,self.nom,self.vjp,'a'*64,sequence_guard=guard,intermediate_vjp_requests=[{'selector':selector,'cotangent_id':'intermediate_scalar:unit'}]);row=r['intermediate_vjps'][0];self.assertEqual(row['status'],status);self.assertEqual(row['connected_field_mask'],0);self.assertEqual(set(row['gradient_words']),{'0000000000000000'})
 def test_intermediate_vjp_failures_cleanup_no_partial(self):
  for options in ({'wrong_token':True},{'vjp_rc':True},{'vjp_nan':True},{'vjp_badmask':True},{'vjp_status':1,'vjp_badmask':True},{'vjp_status':3},{'vjp_badfill':True}):
   guard,call,sub,selector=self.graph_setup();lib=FakeABI(**options)
   with self.assertRaises(RuntimeError):abi_core._execute_bound(lib,call,self.center['words'],sub,self.nom,self.vjp,'a'*64,sequence_guard=guard,intermediate_vjp_requests=[{'selector':selector,'cotangent_id':'intermediate_scalar:unit'}])
   self.assertTrue(guard.poisoned);self.assertEqual(lib.events[-2:],['close','clear'])
 def test_final_state_cotangent_cannot_be_used_for_intermediate(self):
  guard,call,sub,selector=self.graph_setup();lib=FakeABI()
  with self.assertRaisesRegex(RuntimeError,'unknown intermediate scalar cotangent'):abi_core._execute_bound(lib,call,self.center['words'],sub,self.nom,self.vjp,'a'*64,sequence_guard=guard,intermediate_vjp_requests=[{'selector':selector,'cotangent_id':'state:nc:15'}])
  self.assertEqual(lib.events,[]);self.assertTrue(guard.poisoned)
 def test_intermediate_vjp_missing_or_mask_selector_rejected(self):
  guard,call,sub,selector=self.graph_setup();lib=FakeABI();selector['field']='missing'
  with self.assertRaisesRegex(RuntimeError,'missing or ambiguous'):abi_core._execute_bound(lib,call,self.center['words'],sub,self.nom,self.vjp,'a'*64,sequence_guard=guard,intermediate_vjp_requests=[{'selector':selector,'cotangent_id':'intermediate_scalar:unit'}])
  self.assertEqual(lib.events[-2:],['close','clear']);self.assertTrue(guard.poisoned)
  guard,call,sub,selector=self.graph_setup();lib=FakeABI();selector['record_kind']='mask'
  with self.assertRaisesRegex(RuntimeError,'identify a value'):abi_core._execute_bound(lib,call,self.center['words'],sub,self.nom,self.vjp,'a'*64,sequence_guard=guard,intermediate_vjp_requests=[{'selector':selector,'cotangent_id':'intermediate_scalar:unit'}])
  self.assertEqual(lib.events,[])
 def test_a3_value_failures_are_poisoned_and_cleared(self):
  for mode,options in [('off',{'off_extra':True}),('off',{'rain_rc':True}),('off',{'rain_nan':True}),('off',{'rain_flag_bad':True}),('off',{'value_flag_one':True}),('on',{'rain_mismatch':True}),('on',{'duplicate_rain':True}),('on',{'missing_rain':True}),('on',{'rain_rc':True})]:
   guard=self.guard();lib=FakeABI(**options)
   if mode=='on':guard.check(self.plan['calls'][0],self.words_for(self.plan['calls'][0]));guard.complete()
   call=self.plan['calls'][0 if mode=='off' else 1]
   with self.assertRaises(RuntimeError):abi_core._execute_bound(lib,call,self.center['words'],{},self.nom,self.vjp,'a'*64,sequence_guard=guard)
   self.assertTrue(guard.poisoned);self.assertEqual(lib.events[-1],'clear')
 def test_a3_graph_primal_and_result_are_same_handle_before_derivatives(self):
  guard,call,sub,selector=self.graph_setup();lib=FakeABI(graph_flag=0);seed_id=next(k for k,v in sub.items() if v['direction']=='th')
  result=abi_core._execute_bound(lib,call,self.center['words'],sub,self.nom,self.vjp,'a'*64,sequence_guard=guard,intermediate_requests=[{'selector':selector,'seed_id':seed_id}],intermediate_vjp_requests=[{'selector':selector,'cotangent_id':'intermediate_scalar:unit'}])
  self.assertEqual(result['same_call_rain'],{'raw_hex':'4000000000000000','graph_flag':0});self.assertEqual(result['graph_fnresult_primal'],result['same_call_rain']);self.assertEqual(result['intermediate_jvps'][0]['primal']['graph_flag'],0);self.assertEqual(result['intermediate_vjps'][0]['primal'],result['intermediate_jvps'][0]['primal']);self.assertLess(lib.events.index(('primal',123,567,0)),lib.events.index(('intermediate',123,567,0,624)));self.assertEqual(lib.events.count(('primal',123,567,0)),1);self.assertEqual(lib.events.count(('primal',123,567,2)),1);self.assertEqual(lib.events.count(('rain',b'baseline',b'center_joint_graph',91,567)),1);self.assertEqual(lib.events[-2:],['close','clear'])
 def test_a3_graph_checkpoint_failures_close_clear_and_poison(self):
  for options in ({'rain_rc':True},{'rain_nan':True},{'rain_flag_bad':True},{'rain_mismatch':True},{'missing_rain':True},{'duplicate_rain':True},{'primal_rc':True},{'primal_nan':True}):
   guard,call,sub,selector=self.graph_setup();lib=FakeABI(**options)
   with self.assertRaises(RuntimeError):abi_core._execute_bound(lib,call,self.center['words'],sub,self.nom,self.vjp,'a'*64,sequence_guard=guard)
   self.assertTrue(guard.poisoned);self.assertEqual(lib.events[-2:],['close','clear'])
 def test_a3_cross_call_raw_comparison_and_installed_state_only(self):
  guard=self.guard();lib=FakeABI();off=abi_core._execute_bound(lib,self.plan['calls'][0],self.center['words'],{},self.nom,self.vjp,'a'*64,sequence_guard=guard);on=abi_core._execute_bound(lib,self.plan['calls'][1],self.center['words'],{},self.nom,self.vjp,'a'*64,sequence_guard=guard)
  for c in self.plan['calls'][2:90]:guard.check(c,self.words_for(c));guard.complete()
  sub={k:v for k,v in self.eff.items() if v['center']=='baseline'};graph=abi_core._execute_bound(lib,self.plan['calls'][90],self.center['words'],sub,self.nom,self.vjp,'a'*64,sequence_guard=guard)
  for c in self.plan['calls'][91:93]:guard.check(c,self.words_for(c));guard.complete()
  installed=abi_core._execute_bound(FakeABI(),self.plan['calls'][93],self.center['words'],{},self.nom,self.vjp,'b'*64,sequence_guard=guard)
  comparison=abi_core.compare_same_input_calls(off,on,graph=graph,installed=installed);self.assertEqual(comparison['installed'],'STATE_ONLY');self.assertEqual(abi_core.compare_same_input_calls(off,on)['installed'],'SKIPPED_NOT_SUPPLIED');self.assertFalse(comparison['execution_ready']);self.assertNotIn('same_call_rain',installed)
  bad=copy.deepcopy(on);bad['same_call_rain']['raw_hex']='4008000000000000'
  with self.assertRaises(RuntimeError):abi_core.compare_same_input_calls(off,bad,graph=graph,installed=installed)
  bad=copy.deepcopy(graph);bad['state_output_words'][0]='3ff0000000000000'
  with self.assertRaisesRegex(RuntimeError,'state mismatch'):abi_core.compare_same_input_calls(off,on,graph=bad,installed=installed)
  bad=copy.deepcopy(graph);bad['graph_metadata']=[]
  with self.assertRaisesRegex(RuntimeError,'FnResult rain record'):abi_core.compare_same_input_calls(off,on,graph=bad,installed=installed)
  bad=copy.deepcopy(installed);bad['same_call_rain']=copy.deepcopy(off['same_call_rain'])
  with self.assertRaisesRegex(RuntimeError,'state only'):abi_core.compare_same_input_calls(off,on,graph=graph,installed=bad)
 def test_synthetic_abi_graph(self):
  guard=self.guard()
  for c in self.plan['calls'][:90]:guard.check(c,self.words_for(c));guard.complete()
  call=self.plan['calls'][90];sub={k:v for k,v in self.eff.items() if v['center']=='baseline'}
  g=abi_core._execute_bound(FakeABI(),call,self.center['words'],sub,self.nom,self.vjp,'a'*64,sequence_guard=guard)
  self.assertEqual(len(g['effective_jvp_payloads']),5);self.assertEqual(len(g['nominal_jvps']),4);self.assertEqual(len(g['vjps']['state:nc:15']['forcing_words']),156);self.assertTrue(g['handle_null_after'])
if __name__=='__main__':unittest.main()
