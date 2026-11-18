#!/usr/bin/env python3
"""Synthetic call-mode relationships only; never execution or provenance proof."""
import hashlib,json,math,re,struct
import batch5_preflight as preflight

SCHEMA='kdm6.native_host_successor.call_modes.draft.v2'
SLOT_SCHEMA='kdm6.native_host_successor.same_call_rain.synthetic.v1'
HEX=re.compile(r'^[0-9a-f]{16}$')

def need(ok,why):
 if not ok:raise ValueError(why)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def vector(words,n):
 need(type(words) is list and len(words)==n,'raw word count')
 for w in words:
  need(type(w) is str and HEX.fullmatch(w) is not None and math.isfinite(struct.unpack('>d',bytes.fromhex(w))[0]),'finite raw f64 word')
 return words
def packed_sha(words):return sha(bytes.fromhex(''.join(words)))
def slot_sha(slot):return sha(json.dumps(slot,sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii'))

def validate(bundle):
 """Check self-reported synthetic identities and equalities; never attest origin.

 A fully rewritten, self-consistent fabricated slot is indistinguishable here;
 independently authenticated same-call assets/loader provenance are required.
 """
 need(type(bundle) is dict and set(bundle)=={'schema','status','origin','parent_plan_sha256','calls'},'bundle fields')
 need(bundle['schema']==SCHEMA and bundle['status']=='DRAFT_BLOCKED' and bundle['origin']=='SYNTHETIC_ONLY' and bundle['parent_plan_sha256']==preflight.PLAN_SHA,'synthetic draft identity')
 plan,_,_=preflight.load_inputs(preflight.DEFAULT_PLAN,preflight.DEFAULT_SELECTED,preflight.DEFAULT_CONTRACT);planned=plan['calls'];inputs={v['id']:v['words'] for v in plan['inputs']};rows=bundle['calls'];need(type(rows) is list and len(rows)==len(planned)==100,'call count')
 outputs={};status_counts={'completed':0,'skipped':0}
 for row,spec in zip(rows,planned):
  need(type(row) is dict and type(row.get('sequence')) is int and (row['sequence'],row.get('input_id'),row.get('mode'))==(spec['sequence'],spec['input_id'],spec['mode']),'canonical call identity/order')
  optional=spec['status']=='PLANNED_OPTIONAL'
  if row.get('status')=='skipped':
   need(optional and set(row)=={'sequence','input_id','mode','status','reason'} and type(row['reason']) is str and bool(row['reason'].strip()),'invalid skipped call');status_counts['skipped']+=1;continue
  need(row.get('status')=='completed' and type(row.get('return_code')) is int and row['return_code']==0,'required call incomplete/failed')
  mode=row['mode'];base={'sequence','input_id','mode','status','return_code','input_words','input_sha256','state_output_words','output_sha256'}
  if mode=='installed_value_optional':
   need(optional and set(row)==base|{'comparison_scope'} and row['comparison_scope']=='STATE_ONLY','installed call must be STATE_ONLY without rain')
  else:
   need(not optional and mode in ('capture_off_value','capture_on_value','center_joint_graph') and set(row)==base|{'rain_slot','rain_slot_sha256'},'instrumented call fields')
  inp=vector(row['input_words'],624);out=vector(row['state_output_words'],468);need(inp==inputs[row['input_id']] and row['input_sha256']==packed_sha(inp),'canonical input/hash');need(row['output_sha256']==packed_sha(out),'state output hash')
  if mode!='installed_value_optional':
   slot=row['rain_slot'];need(type(slot) is dict and set(slot)=={'schema','read_kind','sequence','input_id','mode','runtime_call','input_sha256','state_output_sha256','word','graph_flag'},'rain slot fields')
   expected={'schema':SLOT_SCHEMA,'read_kind':'SAME_CALL_RESULT_RAIN','sequence':row['sequence'],'input_id':row['input_id'],'mode':mode,'runtime_call':row['sequence'],'input_sha256':row['input_sha256'],'state_output_sha256':row['output_sha256']}
   need(all(type(slot[k]) is type(v) and slot[k]==v for k,v in expected.items()),'rain slot not bound to this call');vector([slot['word']],1);need(type(slot['graph_flag']) is int and slot['graph_flag'] in ((0,1) if mode=='center_joint_graph' else (0,)),'rain graph flag');need(row['rain_slot_sha256']==slot_sha(slot),'rain slot hash');outputs[(row['input_id'],mode)]=(out,slot['word'])
  else:outputs[(row['input_id'],mode)]=(out,None)
  status_counts['completed']+=1
 for input_id in inputs:
  need(outputs[(input_id,'capture_off_value')]==outputs[(input_id,'capture_on_value')],'off/on state or same-call rain mismatch')
 for (input_id,mode),(out,rain) in outputs.items():
  if mode=='center_joint_graph':need((out,rain)==outputs[(input_id,'capture_off_value')],'graph state or same-call rain mismatch')
  if mode=='installed_value_optional':need(out==outputs[(input_id,'capture_off_value')][0],'installed state mismatch')
 return {'schema':'kdm6.native_host_successor.call_modes.validation.v2','status':'DRAFT_BLOCKED','eligibility':'NOT_ELIGIBLE','origin':'SYNTHETIC_ONLY','planned_calls':100,'required_completed':93,'optional_completed':status_counts['completed']-93,'optional_skipped':status_counts['skipped'],'scope':'caller-supplied relationships only; no authenticated same-call provenance, DSO execution, units, physical or RTTOV claim'}
