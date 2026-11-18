import copy,struct,unittest
import successor_call_modes_v2_draft as m

class CallModesDraftTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.plan,_,_=m.preflight.load_inputs(m.preflight.DEFAULT_PLAN,m.preflight.DEFAULT_SELECTED,m.preflight.DEFAULT_CONTRACT);cls.inputs={x['id']:x['words'] for x in cls.plan['inputs']}
 def bundle(self,all_installed=False):
  rows=[];ids=list(self.inputs);index={name:i for i,name in enumerate(ids)}
  for c in self.plan['calls']:
   row={'sequence':c['sequence'],'input_id':c['input_id'],'mode':c['mode']}
   if c['status']=='PLANNED_OPTIONAL' and not all_installed and c['sequence']%2:
    row.update(status='skipped',reason='synthetic optional omission');rows.append(row);continue
   inp=self.inputs[c['input_id']];word=struct.pack('>d',float(index[c['input_id']]+1)).hex();out=[word]*468
   row.update(status='completed',return_code=0,input_words=inp.copy(),input_sha256=m.packed_sha(inp),state_output_words=out,output_sha256=m.packed_sha(out))
   if c['mode']=='installed_value_optional':row['comparison_scope']='STATE_ONLY'
   else:
    slot={'schema':m.SLOT_SCHEMA,'read_kind':'SAME_CALL_RESULT_RAIN','sequence':c['sequence'],'input_id':c['input_id'],'mode':c['mode'],'runtime_call':c['sequence'],'input_sha256':row['input_sha256'],'state_output_sha256':row['output_sha256'],'word':struct.pack('>d',index[c['input_id']]+.25).hex(),'graph_flag':1 if c['mode']=='center_joint_graph' else 0};row['rain_slot']=slot;row['rain_slot_sha256']=m.slot_sha(slot)
   rows.append(row)
  return {'schema':m.SCHEMA,'status':'DRAFT_BLOCKED','origin':'SYNTHETIC_ONLY','parent_plan_sha256':m.preflight.PLAN_SHA,'calls':rows}
 def test_full_synthetic_only_never_eligible(self):
  for flag in (False,True):
   result=m.validate(self.bundle(flag));self.assertEqual(result['required_completed'],93);self.assertEqual(result['optional_completed']+result['optional_skipped'],7);self.assertEqual(result['status'],'DRAFT_BLOCKED');self.assertEqual(result['eligibility'],'NOT_ELIGIBLE')
 def test_borrowed_rehashed_rain_rejected(self):
  b=self.bundle();b['calls'][1]['rain_slot']=copy.deepcopy(b['calls'][0]['rain_slot']);b['calls'][1]['rain_slot_sha256']=m.slot_sha(b['calls'][1]['rain_slot'])
  with self.assertRaisesRegex(ValueError,'bound to this call'):m.validate(b)
 def test_rehashed_foreign_input_and_call_rejected(self):
  b=self.bundle();b['calls'][0]['input_words'][0]='0000000000000000';b['calls'][0]['input_sha256']=m.packed_sha(b['calls'][0]['input_words'])
  with self.assertRaisesRegex(ValueError,'canonical input'):m.validate(b)
  b=self.bundle();b['calls'][0]['input_id']='upper'
  with self.assertRaisesRegex(ValueError,'canonical call'):m.validate(b)
 def test_installed_cannot_claim_rain_even_null(self):
  b=self.bundle(True);row=b['calls'][93];row['rain_slot']=None
  with self.assertRaisesRegex(ValueError,'STATE_ONLY'):m.validate(b)
  b=self.bundle(True);b['calls'][93]['comparison_scope']='RAIN_EQUAL'
  with self.assertRaisesRegex(ValueError,'STATE_ONLY'):m.validate(b)
 def test_missing_duplicate_extra_and_required_skip(self):
  for mutate in ('missing','duplicate','extra','skip'):
   b=self.bundle()
   if mutate=='missing':b['calls'].pop()
   elif mutate=='duplicate':b['calls'][1]=copy.deepcopy(b['calls'][0])
   elif mutate=='extra':b['calls'].append(copy.deepcopy(b['calls'][0]))
   else:b['calls'][0]={'sequence':1,'input_id':'baseline','mode':'capture_off_value','status':'skipped','reason':'no'}
   with self.assertRaises(ValueError):m.validate(b)
 def test_raw_equality_and_finiteness(self):
  b=self.bundle();b['calls'][1]['rain_slot']['word']='4000000000000000';b['calls'][1]['rain_slot_sha256']=m.slot_sha(b['calls'][1]['rain_slot'])
  with self.assertRaisesRegex(ValueError,'state or same-call rain'):m.validate(b)
  b=self.bundle();b['calls'][0]['rain_slot']['word']='7ff8000000000000';b['calls'][0]['rain_slot_sha256']=m.slot_sha(b['calls'][0]['rain_slot'])
  with self.assertRaisesRegex(ValueError,'finite raw'):m.validate(b)
 def test_graph_and_installed_state_only_parity(self):
  b=self.bundle(True);g=b['calls'][90];g['state_output_words'][0]='4000000000000000';g['output_sha256']=m.packed_sha(g['state_output_words']);g['rain_slot']['state_output_sha256']=g['output_sha256'];g['rain_slot_sha256']=m.slot_sha(g['rain_slot'])
  with self.assertRaisesRegex(ValueError,'graph state'):m.validate(b)
  b=self.bundle(True);installed=b['calls'][93];installed['state_output_words'][0]='4000000000000000';installed['output_sha256']=m.packed_sha(installed['state_output_words'])
  with self.assertRaisesRegex(ValueError,'installed state'):m.validate(b)
 def test_missing_slot_and_wrong_state_hash_rejected(self):
  b=self.bundle();del b['calls'][0]['rain_slot']
  with self.assertRaisesRegex(ValueError,'instrumented call fields'):m.validate(b)
  b=self.bundle();b['calls'][0]['output_sha256']='0'*64
  with self.assertRaisesRegex(ValueError,'state output hash'):m.validate(b)
 def test_hash_and_scope_cannot_be_promoted(self):
  b=self.bundle();b['calls'][0]['rain_slot_sha256']='0'*64
  with self.assertRaisesRegex(ValueError,'rain slot hash'):m.validate(b)
  b=self.bundle();b['status']='EXECUTION_READY'
  with self.assertRaisesRegex(ValueError,'synthetic draft'):m.validate(b)

if __name__=='__main__':unittest.main()
