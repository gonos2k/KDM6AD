import copy,ctypes as C,json,math,pathlib,sys,unittest
from unittest import mock
HERE=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));import selector_manifest_draft as m
import batch5_abi_core as core
import test_batch5_abi_core as fake

class SelectorDraftTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.manifest=m.construct();cls.saved=json.loads((HERE/'selector_manifest_draft.json').read_text());cls.plan,_,_=m.batch5_preflight.load_inputs(m.batch5_preflight.DEFAULT_PLAN,m.batch5_preflight.DEFAULT_SELECTED,m.batch5_preflight.DEFAULT_CONTRACT);cls.effective,_,_=m.batch5_preflight.seed_specs(cls.plan)
 def records(self,graph=False):
  call={'sequence':91,'input_id':'baseline','mode':'center_joint_graph'} if graph else {'sequence':2,'input_id':'baseline','mode':'capture_on_value'};seed='baseline:th:1e-05' if graph else None;sd=self.effective[seed]['seed_sha256'] if graph else 'none';out=[]
  for selector in self.manifest['selectors']:
   for k in range(39):out.append({'sequence':call['sequence'],'input_id':call['input_id'],'mode':call['mode'],'runtime_call':call['sequence'],'one_step_call':0,'outer_loop':0,'substep_family':'runtime','substep_n':0,'scope':'layer','b_zero':0,'k_zero':k,'native_level_bottom_first':39-k,'B':1,'K':39,'stage':selector['stage'],'field':selector['field'],'event_ordinal':0,'record_kind':'live_tangent' if graph else 'value','derivative_mode':'jvp' if graph else 'none','direction_id':seed if graph else 'none','seed_sha256':sd,'cotangent_id':'none','availability':'present','derivative_status':'CONNECTED' if graph else 'none','raw_hex':'3ff0000000000000'})
  return call,seed,out
 def test_source_scope_and_exact_stored_manifest(self):
  self.assertEqual(self.saved,self.manifest);self.assertEqual(len(self.manifest['selectors']),6);self.assertEqual(len(self.manifest['blocked_unmapped']),66);self.assertEqual(len(self.manifest['blocked_partial_masks']),19);self.assertEqual(len(self.manifest['blocked_remaining_identified']),119);self.assertEqual(self.manifest['status'],'DRAFT_BLOCKED');self.assertEqual(len(self.manifest['blocked_groups']),28);self.assertTrue(all(x['status']=='BLOCKED_NOT_CERTIFIED' for x in self.manifest['blocked_groups']));self.assertEqual(self.manifest['current_source_hook_count'],366)
  self.assertEqual({x['hook_id'] for x in self.manifest['selectors']},{'entry.t','entry.qv','entry.nc_post','entry.nccn_post','entry.cpm','entry.xl'})
 def test_complete_value_and_graph_are_still_blocked(self):
  call,seed,rows=self.records(False);result=m.validate(self.manifest,call,rows,seed_id=seed);self.assertEqual(result['records'],234);self.assertFalse(result['execution_ready']);self.assertEqual(result['status'],'DRAFT_BLOCKED')
  call,seed,rows=self.records(True)
  with self.assertRaisesRegex(ValueError,'graph projection SPEC_ONLY_BLOCKED'):m.validate(self.manifest,call,rows,seed_id=seed)
 def test_missing_duplicate_and_surplus_rejected(self):
  call,seed,rows=self.records()
  for bad in (rows[:-1],rows[:-1]+[copy.deepcopy(rows[0])],rows+[copy.deepcopy(rows[0])]):
   with self.assertRaises(ValueError):m.validate(self.manifest,call,bad,seed_id=seed)
  bad=copy.deepcopy(rows);bad[-1]['field']='unknown'
  with self.assertRaises(ValueError):m.validate(self.manifest,call,bad,seed_id=seed)
 def test_wrong_call_and_seed_rejected(self):
  call,seed,rows=self.records(True);bad=dict(call,input_id='upper')
  with self.assertRaisesRegex(ValueError,'canonical call'):m.validate(self.manifest,bad,rows,seed_id=seed)
  with self.assertRaisesRegex(ValueError,'graph seed'):m.validate(self.manifest,call,rows,seed_id='upper:th:1e-05')
  call,seed,rows=self.records(False);bad=copy.deepcopy(rows);bad[0]['seed_sha256']='0'*64
  with self.assertRaisesRegex(ValueError,'identity or seed'):m.validate(self.manifest,call,bad,seed_id=seed)
 def test_runtime_identity_inactive_and_nonfinite_rejected(self):
  call,seed,rows=self.records()
  for field,value in [('runtime_call',3),('one_step_call',1),('native_level_bottom_first',1),('availability','inactive'),('raw_hex','7ff8000000000000')]:
   bad=copy.deepcopy(rows);bad[0][field]=value
   with self.assertRaises(ValueError):m.validate(self.manifest,call,bad,seed_id=seed)
 def test_graph_metadata_cannot_be_invented_as_live_rows(self):
  call,seed,rows=self.records(True);rows[0]['derivative_status']='UNCONNECTED';rows[0]['raw_hex']='0000000000000000'
  with self.assertRaisesRegex(ValueError,'graph projection SPEC_ONLY_BLOCKED'):m.validate(self.manifest,call,rows,seed_id=seed)
 def test_normalizes_actual_fake_abi_helper_records(self):
  selected=[(x['stage'],x['field'],k) for x in self.manifest['selectors'] for k in range(39)];selected.append(('entry','th',0));selected.append(('a5_heat','xlf',0));selected.append(('fnresult','rain_increment',-1))
  class FullFake(fake.FakeABI):
   def __init__(self):
    super().__init__()
    self.kdm6_batch5_count_c=fake.Fn(lambda:0 if self.active[1]==b'capture_off_value' else len(selected))
    def metadata(index,ptr,size):
     q=C.cast(ptr,C.POINTER(core.Meta)).contents
     if q.abi_version!=1 or q.struct_size!=size:return -1
     stage,field,k=selected[index];q.input_id=self.active[0];q.mode=self.active[1];q.family=b'runtime_exit' if k<0 else b'runtime';q.scope=b'column' if k<0 else b'layer';q.stage=stage.encode();q.field=field.encode();q.record_kind=b'value';q.derivative_mode=b'none';q.direction_id=b'none';q.seed_sha256=b'none';q.cotangent_id=b'none';q.runtime_call=self.active[2];q.one_step_call=1 if k<0 else 0;q.outer_loop=0;q.substep_n=0;q.event_ordinal=0;q.b_zero=0;q.k_zero=k;q.native_level_bottom_first=-1 if k<0 else 39-k;q.B=1;q.K=-1 if k<0 else 39;return 0
    def value(index,word,kind):C.cast(word,C.POINTER(C.c_uint64))[0]=0x4000000000000000 if selected[index][0]=='fnresult' else 0x3ff0000000000000;C.cast(kind,C.POINTER(C.c_int))[0]=2;return 0
    self.kdm6_batch5_metadata_c=fake.Fn(metadata);self.kdm6_batch5_value_word_c=fake.Fn(value)
  guard=core.InstrumentedSequence(m.batch5_preflight.DEFAULT_PLAN,m.batch5_preflight.DEFAULT_SELECTED,m.batch5_preflight.DEFAULT_CONTRACT);inp=next(x['words'] for x in self.plan['inputs'] if x['id']=='baseline');effective,nominal,vjp=m.batch5_preflight.seed_specs(self.plan);lib=FullFake()
  core._execute_bound(lib,self.plan['calls'][0],inp,{},nominal,vjp,'a'*64,sequence_guard=guard)
  raw=core._execute_bound(lib,self.plan['calls'][1],inp,{},nominal,vjp,'a'*64,sequence_guard=guard)
  call={'sequence':2,'input_id':'baseline','mode':'capture_on_value'};result=m.normalize_v5_result(self.manifest,call,raw)
  self.assertEqual((result['source_records'],result['selected_records']),(237,234));self.assertEqual(result['status'],'DRAFT_BLOCKED');self.assertFalse(result['execution_ready']);self.assertEqual(result['dso_provenance'],'CALLER_SUPPLIED_UNVERIFIED')
  bad=copy.deepcopy(raw);bad['sidecar_records'][-1]['field']='invented'
  with self.assertRaisesRegex(ValueError,'unknown source hook'):m.normalize_v5_result(self.manifest,call,bad)
  bad=copy.deepcopy(raw);bad['sidecar_records'][0]['runtime_call']=1
  with self.assertRaisesRegex(ValueError,'source call identity'):m.normalize_v5_result(self.manifest,call,bad)
  bad=copy.deepcopy(raw);bad['sidecar_records'].append(copy.deepcopy(bad['sidecar_records'][0]))
  with self.assertRaisesRegex(ValueError,'duplicate source identity'):m.normalize_v5_result(self.manifest,call,bad)
 def test_cached_replay_rechecks_batch6_source_pins(self):
  m.source_audit()
  with mock.patch.dict(m.ASSET_PINS,{'producer_source_batch6/source_snapshot.json':'0'*64}):
   with self.assertRaisesRegex(ValueError,'source audit asset hash'):m.source_audit()
  altered=m.source_audit();altered[5].clear()
  self.assertEqual(len(m.source_audit()[5]),366)
 def test_manifest_mutation_rejected(self):
  call,seed,rows=self.records();bad=copy.deepcopy(self.manifest);bad['status']='EXECUTION_READY'
  with self.assertRaisesRegex(ValueError,'manifest differs'):m.validate(bad,call,rows,seed_id=seed)

if __name__=='__main__':unittest.main()
