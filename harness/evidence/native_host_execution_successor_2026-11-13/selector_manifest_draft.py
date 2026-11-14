#!/usr/bin/env python3
"""Source-only conservative entry selectors; never authorizes execution."""
import copy,functools,hashlib,json,math,re,struct
from producer_source_batch6 import hook_coverage_delta as batch6_delta, replay as batch6_replay
from pathlib import Path
import hook_coverage
import batch5_preflight

HERE=Path(__file__).resolve().parent
SUMMARY_SHA='cf706dd2af631a4da8fc20d7d9f5ef1da1aef186712a1e50bc273c6b10478e80'
DELTA_SHA='77fea0d04e9853d9593ac2fb526c227dd6fa1fb50e745490b8e08e8de3aa335a'
SOURCE_SNAPSHOT_SHA='3d06cc352895de7719a2fb3710cb12e949dbd56e98554009c9c5ce2e85aed9b2'
PATCH_SHA='65524b6fce5c6f57cd8c063cbd6b360710c0b3019780d3f4854001fab088a657'
SELECTED={
 'nc_entry_pre_post.site.01':'entry.nc_post',
 'nc_entry_pre_post.site.02':'entry.nccn_post',
 'pii_to_temperature.site.01':'entry.t',
 'water_before_after.supplement.entry_qv':'entry.qv',
 'cpm_xl.site.01':'entry.cpm',
 'cpm_xl.site.02':'entry.xl',
}
KEYS=('sequence','input_id','mode','runtime_call','one_step_call','outer_loop','substep_family','substep_n','scope','b_zero','k_zero','native_level_bottom_first','B','K','stage','field','event_ordinal','record_kind','derivative_mode','direction_id','seed_sha256','cotangent_id','availability','derivative_status','raw_hex')
HEX=re.compile(r'^[0-9a-f]{16}$')

def sha(raw):return hashlib.sha256(raw).hexdigest()
def need(ok,why):
 if not ok:raise ValueError(why)

ASSET_PINS={
 'validate_atomic_catalog.py':'2f5fe0a4a664acc5bddbded424168f90aaed6fe65366bde89e1afbaf6b98b55a',
 'validate_atomic_catalog_v2.py':'4f15a9ea47cd000e6eb8acde763d8b3a97f03466d5ce0a2682e77299d827e886',
 'hook_coverage.py':'36da92c1b4717ff58168400fee20ce67975904a877d1e0efdee72532bc76badf',
 'atomic_catalog_draft.json':'05d2291d1060ddee582c443d719035b8e4a84a1c8293c4385ed5208e60aa331d',
 'atomic_catalog_consumer_patch_v2.json':'692a6f44bb6de6335a5176a68300aec57b7922c29e82db028fec99716f3324c3',
 'producer_source/replay.py':'bb621554daab87441d39bea7a430c595c3b2939e40dc783f283c980d89ba9190',
 'producer_source/base_libtorch.tar.gz':'7ac32efbbe58dc2c6b4793dc40f0c22a3434d63b55026e2c629cfc936166041f',
 'producer_source/v5_changes.patch':'8788add86cfe01f678f27d90e24496b63cd30ce65cc5c2c8b4eee25244a9863d',
 'producer_source/source_manifest.json':'ad19651e4571f75e30b62668f4c3097b9c6018dae19ea4b653442830cafa1fef',
 'producer_source_batch6/replay.py':'6eec3ace4df9befb5ef95c103c0203c7c657225ea73ebdef33bab47c2675f261',
 'producer_source_batch6/hook_coverage_delta.py':'d8df6fbd8966cdfcc58f96ed73f2595fd676a36383adb1f59646e31882c686f4',
 'producer_source_batch6/hook_coverage_delta.json':DELTA_SHA,
 'producer_source_batch6/rain_checkpoint.patch':PATCH_SHA,
 'producer_source_batch6/source_snapshot.json':SOURCE_SNAPSHOT_SHA,
 'hook_coverage_summary.json':SUMMARY_SHA,
}

def source_audit():
 # Recheck every byte pin even on cache hits; cached reconstruction is copied.
 for name,digest in ASSET_PINS.items():need(sha((HERE/name).read_bytes())==digest,'source audit asset hash '+name)
 need(sha((HERE.parent/'native_host_preflight_2026-11-12/field_contract_sources.zip').read_bytes())=='663871cbb48154ea6c63a18991710e955bdec5d7ac5cda9d32bc0e0dd68c2347','field source archive hash')
 return copy.deepcopy(_source_audit_cached())

@functools.lru_cache(maxsize=1)
def _source_audit_cached():
 raw=(HERE/'hook_coverage_summary.json').read_bytes();need(sha(raw)==SUMMARY_SHA,'prior coverage summary hash');saved=json.loads(raw);coverage=hook_coverage.load();need(saved==hook_coverage.summary(coverage),'prior coverage summary reconstruction')
 root=HERE/'producer_source_batch6';delta_raw=(root/'hook_coverage_delta.json').read_bytes();need(sha(delta_raw)==DELTA_SHA and sha((root/'source_snapshot.json').read_bytes())==SOURCE_SNAPSHOT_SHA and sha((root/'rain_checkpoint.patch').read_bytes())==PATCH_SHA,'batch6 source/delta pins');delta=json.loads(delta_raw);need(delta==batch6_delta.run(),'batch6 delta replay mismatch')
 mapped={x['atomic_id']:x for x in coverage['atom_source_hook_matches']};new={x['atom_id']:x for x in delta['mapped']};need(len(mapped)==107 and len(new)==18 and not(set(mapped)&set(new)) and delta['updated_mapped_atoms']==125 and len(delta['remaining_unmapped_ids'])==66 and len(saved['proposed_mask_ids'])==19,'batch6 coverage inventory');need(len(saved['groups'])==28 and all(g['status']=='BLOCKED_NOT_CERTIFIED' for g in saved['groups']),'group blocked status')
 with batch6_replay.reconstructed_tree() as (tree,_):
  texts={name:(tree/'src'/name).read_text() for name in hook_coverage.SOURCE_SHA};known=set()
  for text in texts.values():
   for line in text.splitlines():
    hit=re.search(r'batch5::(?:full|column|layer)\(\s*"([^\"]+)",\s*"([^\"]+)"',line)
    if hit:known.add('.'.join(hit.groups()))
  for label in ('nc_snap1_lambda','nc_snap2_lambda','nc_dsd_lambda'):
   need('batch5::site("'+label+'")' in texts['coordinator.cpp'],'dynamic hook label')
   for field in re.findall(r'batch5::full\(label,\s*"([^\"]+)"',texts['coordinator.cpp']):known.add(label+'.'+field)
  need(set(coverage['hook_inventory'])<=known and len(known)==366,'current source hook inventory')
  need(all(x['hook_id'] in known for x in delta['mapped']),'delta hook absent in current source')
  runtime=texts['runtime.cpp'].splitlines();sites={}
  for ident,hook in SELECTED.items():
   field=hook.split('.',1)[1];prefix='batch5::full("entry", "'+field+'", '
   hits=[(i+1,line.strip()) for i,line in enumerate(runtime) if prefix in line];need(len(hits)==1 and hits[0][1].endswith(', false);'),'batch6 entry source site')
   sites[ident]={'file':'src/runtime.cpp','line':hits[0][0],'call':'full','expression_tail':hits[0][1].split(prefix,1)[1]}
 return saved,coverage,delta,mapped,new,known,sites

def construct():
 saved,coverage,delta,mapped,new,known,sites=source_audit();selectors=[]
 for atom,hook in sorted(SELECTED.items()):
  item=mapped[atom];need(item['hook_id']==hook and len(item['hook'])==1,'selector unique prior source site');site=sites[atom];need(site['expression_tail']==item['hook'][0]['expression_tail'],'current source expression changed')
  stage,field=hook.split('.');selectors.append({'atomic_id':atom,'hook_id':hook,'stage':stage,'field':field,'source_file':site['file'],'source_line':site['line'],'source_expression':site['expression_tail'],'scope':'layer','B':1,'K':39,'context':{'one_step_call':0,'outer_loop':0,'substep_family':'runtime','substep_n':0,'event_ordinal':0},'cardinality':'exactly one per k_zero 0..38 for each eligible capture_on_value call','active_rule':'required when the value-capture sidecar reaches this unconditional runtime-entry hook with planned B=1 K=39 dt=20','inactive_rule':'not a conditional branch; an omitted or inactive record is an error','status':'SOURCE_ONLY_RUNTIME_UNVERIFIED'})
 deferred=sorted((set(mapped)|set(new))-set(SELECTED));need(len(deferred)==119,'identified remainder')
 return {'schema':'kdm6.batch5.selector_manifest.draft.v1','status':'DRAFT_BLOCKED','scientific_status':'INCONCLUSIVE','physical_unit_status':'INCONCLUSIVE','coverage_summary_sha256':SUMMARY_SHA,'coverage_delta_sha256':DELTA_SHA,'batch6_source_snapshot_sha256':SOURCE_SNAPSHOT_SHA,'batch6_patch_sha256':PATCH_SHA,'materialized_catalog_sha256':saved['catalog_sha256'],'prior_source_sha256':saved['source_sha256'],'current_source_hook_count':len(known),'blocked_groups':[{'group_id':g['group_id'],'status':'BLOCKED_NOT_CERTIFIED'} for g in saved['groups']],'selectors':selectors,'graph_projection':{'status':'SPEC_ONLY_BLOCKED','reason':'sidecar emits forward value metadata and separate JVP/VJP payloads, not live_tangent rows; joined primal and derivative consumer is not implemented','accepts_records':False},'blocked_unmapped':[{'atomic_id':x,'status':'BLOCKED_NO_PROVEN_SOURCE_HOOK'} for x in sorted(delta['remaining_unmapped_ids'])],'blocked_partial_masks':[{'atomic_id':x,'status':'BLOCKED_PARTIAL_MASK'} for x in sorted(saved['proposed_mask_ids'])],'blocked_remaining_identified':[{'atomic_id':x,'status':'BLOCKED_NO_REVIEWED_SELECTOR'} for x in deferred],'identity_fields':list(KEYS),'projection_contract':'normalized synthetic value projection; adapter must map metadata family to substep_family, attach canonical call sequence and derivative_status none; not a claim this projection is emitted by the current producer','dynamic_rule':'No assumed microphysics or sedimentation substep counts; these six hooks execute before the outer loop. runtime_call is planned sequence only under the separately unverified single-process ordered-call contract.','scope':'synthetic projection validation only; no source hook proves actual runtime emission, graph derivative, physical budget or execution readiness'}

def validate(manifest,call,records,*,seed_id=None):
 need(manifest==construct(),'manifest differs from reconstructed draft');plan,_,_=batch5_preflight.load_inputs(batch5_preflight.DEFAULT_PLAN,batch5_preflight.DEFAULT_SELECTED,batch5_preflight.DEFAULT_CONTRACT);calls={x['sequence']:x for x in plan['calls']};need(type(call) is dict and set(call)=={'sequence','input_id','mode'},'call fields');seq=call['sequence'];need(type(seq) is int and seq in calls and (call['input_id'],call['mode'])==(calls[seq]['input_id'],calls[seq]['mode']),'wrong canonical call');mode=call['mode'];need(mode in ('capture_on_value','center_joint_graph'),'mode not eligible for this projection')
 if mode=='center_joint_graph':
  specs,_,_=batch5_preflight.seed_specs(plan);need(isinstance(seed_id,str) and seed_id in specs and specs[seed_id]['center']==call['input_id'],'wrong canonical graph seed');raise ValueError('graph projection SPEC_ONLY_BLOCKED: joined metadata/primal/derivative consumer not implemented')
 else:
  need(seed_id is None,'value call must not declare seed');seed_sha='none';kind='value';derivative='none';direction='none'
 need(type(records) is list and len(records)==len(SELECTED)*39,'projection cardinality');expected={(x['stage'],x['field'],k) for x in manifest['selectors'] for k in range(39)};seen=set();statuses=set()
 for row in records:
  need(type(row) is dict and set(row)==set(KEYS),'record fields');need(type(row['k_zero']) is int and 0<=row['k_zero']<39,'vertical identity');key=(row['stage'],row['field'],row['k_zero']);need(key in expected and key not in seen,'surplus or duplicate selector');seen.add(key)
  fixed={'sequence':seq,'input_id':call['input_id'],'mode':mode,'runtime_call':seq,'one_step_call':0,'outer_loop':0,'substep_family':'runtime','substep_n':0,'scope':'layer','b_zero':0,'native_level_bottom_first':39-row['k_zero'],'B':1,'K':39,'event_ordinal':0,'record_kind':kind,'derivative_mode':derivative,'direction_id':direction,'seed_sha256':seed_sha,'cotangent_id':'none','availability':'present'}
  need(all(type(row[k]) is type(v) and row[k]==v for k,v in fixed.items()),'record identity or seed');need(type(row['k_zero']) is int and 0<=row['k_zero']<39,'vertical identity')
  w=row['raw_hex'];need(isinstance(w,str) and HEX.fullmatch(w) is not None and math.isfinite(struct.unpack('>d',bytes.fromhex(w))[0]),'finite f64 word')
  need(row['derivative_status']=='none','value derivative status')
 need(seen==expected,'missing selector')
 return {'status':'DRAFT_BLOCKED','projection_valid':True,'records':len(records),'derivative_statuses':sorted(statuses),'execution_ready':False,'scientific_status':'INCONCLUSIVE','physical_unit_status':'INCONCLUSIVE'}

def normalize_v5_result(manifest,call,result):
 """Normalize actual value-only ABI helper records, then validate selected projection.

 This is caller-supplied synthetic/source-only validation, not execution evidence.
 Graph records require a future joined primal/derivative consumer and are blocked.
 """
 need(manifest==construct(),'manifest differs from reconstructed draft')
 plan,_,_=batch5_preflight.load_inputs(batch5_preflight.DEFAULT_PLAN,batch5_preflight.DEFAULT_SELECTED,batch5_preflight.DEFAULT_CONTRACT)
 calls={x['sequence']:x for x in plan['calls']};need(type(call) is dict and set(call)=={'sequence','input_id','mode'},'call fields');seq=call['sequence'];need(type(seq) is int and seq in calls and (call['input_id'],call['mode'])==(calls[seq]['input_id'],calls[seq]['mode']) and call['mode']=='capture_on_value','wrong canonical value call')
 inputs={x['id']:x['words'] for x in plan['inputs']};need(type(result) is dict and result.get('schema')=='kdm6.future_call_raw.v1' and (result.get('sequence'),result.get('input_id'),result.get('mode'))==(seq,call['input_id'],call['mode']),'ABI result identity');need(result.get('dso_identity_status')=='CALLER_SUPPLIED_UNVERIFIED' and type(result.get('return_code')) is int and result.get('return_code')==0 and result.get('handle_nonnull') is False and result.get('handle_null_after') is True,'ABI value status');need(result.get('input_words')==inputs[call['input_id']],'ABI input words')
 output=result.get('state_output_words');need(type(output) is list and len(output)==468 and all(isinstance(w,str) and HEX.fullmatch(w) is not None and math.isfinite(struct.unpack('>d',bytes.fromhex(w))[0]) for w in output),'ABI state output')
 rows=result.get('sidecar_records');need(type(rows) is list and rows,'sidecar records missing');_,_,_,_,_,known,_=source_audit();selected={(v['stage'],v['field']) for v in manifest['selectors']};projection=[];seen=set();ordinal_groups={}
 source_keys={'input_id','mode','family','scope','stage','field','record_kind','derivative_mode','direction_id','seed_sha256','cotangent_id','runtime_call','one_step_call','outer_loop','substep_n','event_ordinal','b_zero','k_zero','native_level_bottom_first','B','K','dtype','raw_hex'}
 identity=('input_id','mode','runtime_call','one_step_call','outer_loop','family','substep_n','scope','b_zero','k_zero','stage','field','record_kind')
 for row in rows:
  need(type(row) is dict and set(row)==source_keys,'source sidecar fields');need(all(type(row[k]) is int for k in ('runtime_call','one_step_call','outer_loop','substep_n','event_ordinal','b_zero','k_zero','native_level_bottom_first','B','K')),'source numeric identity type');need(isinstance(row['stage'],str) and isinstance(row['field'],str) and row['stage']+'.'+row['field'] in known,'unknown source hook');need((row['input_id'],row['mode'],row['runtime_call'],row['b_zero'],row['B'])==(call['input_id'],call['mode'],seq,0,1),'source call identity');need(all(row[k]=='none' for k in ('derivative_mode','direction_id','seed_sha256','cotangent_id')),'source derivative sentinel');need(row['record_kind'] in ('value','mask'),'source record kind')
  if row['scope']=='layer':need(type(row['k_zero']) is int and 0<=row['k_zero']<39 and row['native_level_bottom_first']==39-row['k_zero'] and row['K']==39,'source layer identity')
  elif row['scope']=='column':need((row['k_zero'],row['native_level_bottom_first'],row['K'])==(-1,-1,-1),'source column identity')
  else:raise ValueError('source scope')
  dtype=row['dtype'];w=row['raw_hex'];need((dtype=='bool' and w in ('0','1') and row['record_kind']=='mask') or (dtype in ('f32','f64') and row['record_kind']=='value' and isinstance(w,str) and re.fullmatch('[0-9a-f]{8}' if dtype=='f32' else '[0-9a-f]{16}',w) is not None and math.isfinite(struct.unpack('>f' if dtype=='f32' else '>d',bytes.fromhex(w))[0])),'source raw value')
  key=tuple(row[k] for k in identity);ordinal=row['event_ordinal'];need(type(ordinal) is int and ordinal>=0 and (key,ordinal) not in seen,'duplicate source identity');seen.add((key,ordinal));ordinal_groups.setdefault(key,set()).add(ordinal)
  if (row['stage'],row['field']) in selected:
   need(dtype=='f64' and row['record_kind']=='value','selected source dtype')
   projection.append({'sequence':seq,'input_id':row['input_id'],'mode':row['mode'],'runtime_call':row['runtime_call'],'one_step_call':row['one_step_call'],'outer_loop':row['outer_loop'],'substep_family':row['family'],'substep_n':row['substep_n'],'scope':row['scope'],'b_zero':row['b_zero'],'k_zero':row['k_zero'],'native_level_bottom_first':row['native_level_bottom_first'],'B':row['B'],'K':row['K'],'stage':row['stage'],'field':row['field'],'event_ordinal':ordinal,'record_kind':row['record_kind'],'derivative_mode':row['derivative_mode'],'direction_id':row['direction_id'],'seed_sha256':row['seed_sha256'],'cotangent_id':row['cotangent_id'],'availability':'present','derivative_status':'none','raw_hex':w})
 need(all(v==set(range(len(v))) for v in ordinal_groups.values()),'source event ordinal gap');verdict=validate(manifest,call,projection)
 return {'schema':'kdm6.batch5.selector_normalization.synthetic.v1','status':'DRAFT_BLOCKED','projection':projection,'projection_valid':verdict['projection_valid'],'source_records':len(rows),'selected_records':len(projection),'dso_provenance':'CALLER_SUPPLIED_UNVERIFIED','execution_ready':False,'scientific_status':'INCONCLUSIVE','physical_unit_status':'INCONCLUSIVE'}

if __name__=='__main__':
 print(json.dumps(construct(),indent=2,sort_keys=True))
