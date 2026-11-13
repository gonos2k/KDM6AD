import ctypes as C,pathlib,sys,tempfile,threading,unittest
from unittest import mock
R=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(R));import batch5_preflight as preflight,batch5_abi_core as abi_core
ROOT=R.parent/'native_host_preflight_2026-11-12';SELECTED=R.parent/'native_host_column_f32_2026-11-11/raw/selected_full.json'

class Fn:
 def __init__(self,fn):self.fn=fn
 def __call__(self,*args):return self.fn(*args)
class FakeABI:
 def __init__(self,*,fail_step=False,fail_meta=False,fail_value=False,bad_count=False,fail_begin=False,fail_clear=False,nan_value=False,f32_nan=False):
  self.events=[];self.fail_step=fail_step;self.fail_meta=fail_meta;self.fail_value=fail_value;self.bad_count=bad_count;self.fail_begin=fail_begin;self.fail_clear=fail_clear;self.nan_value=nan_value;self.f32_nan=f32_nan;self.active=None
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
  def count():self.events.append('count');return abi_core.MAX_RECORDS+1 if self.bad_count else 2
  def meta(index,ptr,size):
   self.events.append(('metadata',index))
   if self.fail_meta:return -1
   m=C.cast(ptr,C.POINTER(abi_core.Meta)).contents
   if m.abi_version!=1 or m.struct_size!=size:return -1
   m.input_id=self.active[0];m.mode=self.active[1];m.family=b'microphysics';m.scope=b'layer';m.stage=b'synthetic';m.field=b'value' if index==0 else b'condition';m.record_kind=b'value' if index==0 else b'mask';m.derivative_mode=b'none';m.direction_id=b'none';m.seed_sha256=b'none';m.cotangent_id=b'none';m.runtime_call=self.active[2];m.one_step_call=1;m.outer_loop=0;m.substep_n=0;m.event_ordinal=0;m.b_zero=0;m.k_zero=23;m.native_level_bottom_first=16;m.B=1;m.K=39;return 0
  def val(index,bitsp,kindp):
   self.events.append(('value',index))
   if self.fail_value:return -1
   C.cast(bitsp,C.POINTER(C.c_uint64))[0]=(0x7fc00000 if self.f32_nan else (0x7ff8000000000000 if self.nan_value else 0x3ff0000000000000)) if index==0 else 1;C.cast(kindp,C.POINTER(C.c_int))[0]=(1 if self.f32_nan else 2) if index==0 else 3;return 0
  def clear():
   self.events.append('clear');self.active=None
   if self.fail_clear:raise RuntimeError('synthetic clear failure')
  self.kdm6_step_ad_c=Fn(step);self.kdm6_step_ad_state_forcing_c=Fn(step);self.kdm6_handle_closep_c=Fn(close);self.kdm6_handle_state_forcing_jvp_c=Fn(jvp);self.kdm6_handle_state_forcing_vjp_c=Fn(vjp);self.kdm6_batch5_begin_c=Fn(begin);self.kdm6_batch5_count_c=Fn(count);self.kdm6_batch5_metadata_c=Fn(meta);self.kdm6_batch5_value_word_c=Fn(val);self.kdm6_batch5_clear_c=Fn(clear)

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
  v=abi_core._execute_bound(lib,off,self.center['words'],{},self.nom,self.vjp,'a'*64,sequence_guard=guard);self.assertEqual(lib.events,['step']);self.assertEqual(v['dso_identity_status'],'CALLER_SUPPLIED_UNVERIFIED');self.assertNotIn('dso_sha256',v)
  lib.events.clear();v=abi_core._execute_bound(lib,on,self.center['words'],{},self.nom,self.vjp,'a'*64,sequence_guard=guard)
  self.assertEqual(lib.events,[('begin',b'baseline',b'capture_on_value',2),'step','count',('metadata',0),('value',0),('metadata',1),('value',1),'clear']);self.assertEqual([(x['dtype'],x['raw_hex']) for x in v['sidecar_records']],[('f64','3ff0000000000000'),('bool','1')]);self.assertEqual(guard.next_sequence,3)
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
  call=dict(self.plan['calls'][0]);substituted=self.center['words'].copy();substituted[0]='0000000000000000';call['input_sha256']=preflight.words_sha(substituted)
  with self.assertRaisesRegex(RuntimeError,'624-word'):abi_core._execute_bound(lib,call,substituted,{},self.nom,self.vjp,'a'*64,sequence_guard=guard)
  self.assertEqual(lib.events,[])
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
 def test_synthetic_abi_graph(self):
  guard=self.guard()
  for c in self.plan['calls'][:90]:guard.check(c,self.words_for(c));guard.complete()
  call=self.plan['calls'][90];sub={k:v for k,v in self.eff.items() if v['center']=='baseline'}
  g=abi_core._execute_bound(FakeABI(),call,self.center['words'],sub,self.nom,self.vjp,'a'*64,sequence_guard=guard)
  self.assertEqual(len(g['effective_jvp_payloads']),5);self.assertEqual(len(g['nominal_jvps']),4);self.assertEqual(len(g['vjps']['state:nc:15']['forcing_words']),156);self.assertTrue(g['handle_null_after'])
if __name__=='__main__':unittest.main()
