#!/usr/bin/env python3
"""Read-only #580/#588 batch5 input and derivative-seed preflight.

This is not an EXECUTION_READY plan and cannot launch an ABI call.
"""
import gzip
import hashlib
import json
import math
from pathlib import Path
import struct

PLAN_SHA = '4d6a935c9d83d987a8a2149d58699b2812af565785d20c599cf9f49f05846b8a'
SELECTED_SHA = 'e3117d277a073042bbae648b87e7dd6661d14b600fc8245f6aeabc19fe715eae'
CONTRACT_SHA = 'f55dcc442868e83a6a7d1521e0ce9fd77dbc6f9ad9cacca27e8c18fd367ba2f7'
FIELDS = ('th','qv','qc','qr','qi','qs','qg','nccn','nc','ni','nr','bg','rho','pii','p','delz')
ZERO='0000000000000000';ONE='3ff0000000000000'
HERE=Path(__file__).resolve().parent
PRE=HERE.parent/'native_host_preflight_2026-11-12'
DEFAULT_PLAN=PRE/'plan.json.gz'
DEFAULT_SELECTED=HERE.parent/'native_host_column_f32_2026-11-11/raw/selected_full.json'
DEFAULT_CONTRACT=PRE/'field_contract.json'
CENTERS={'baseline':'4073ff66c0000000','lower':'4074002793cded6a','upper':'407400797f530c23'}

def need(ok, why):
    if not ok: raise ValueError(why)
def sha(raw): return hashlib.sha256(raw).hexdigest()
def f32(w): return struct.unpack('>f',bytes.fromhex(w))[0]
def f64(w): return struct.unpack('>d',bytes.fromhex(w))[0]
def w64(v): return struct.pack('>d',v).hex()
def words_sha(words): return sha(bytes.fromhex(''.join(words)))

def load_inputs(plan_path, selected_path, contract_path):
    plan_raw=Path(plan_path).read_bytes();selected_raw=Path(selected_path).read_bytes();contract_raw=Path(contract_path).read_bytes()
    need(sha(plan_raw)==PLAN_SHA and sha(selected_raw)==SELECTED_SHA and sha(contract_raw)==CONTRACT_SHA,'pinned plan/input/contract hash')
    plan=json.loads(gzip.decompress(plan_raw));selected=json.loads(selected_raw);contract=json.loads(contract_raw)
    need(plan['status']=='SPEC_ONLY' and plan['execution_receipt'] is None and plan['build_requirements']['instrumented_dso_sha256'] is None,'unmodified blocked plan')
    need(plan['controls']=={'shape':[1,39,1],'dt':20.0,'xland':2.0,'ncmin_land':10.0,'ncmin_sea':10.0,'physics_variant':'Legacy','dry_number':0,'threads':1},'controls')
    need(plan['limits']['calls_max']==100 and plan['limits']['wall_seconds_max']==900 and len(plan['calls'])==100,'budget')
    need([x['sequence'] for x in plan['calls']]==list(range(1,101)),'call sequences')
    need(contract['status']=='SPEC_ONLY' and len(contract['groups'])==7,'field contract')
    source=[w for field in FIELDS for w in selected['input_words_hex'][field]]
    need(len(source)==624 and all(len(selected['input_words_hex'][field])==39 for field in FIELDS),'selected shape')
    base=[f32(w) for w in source];need(all(map(math.isfinite,base)) and [struct.pack('>f',v).hex() for v in base]==source,'exact source widening')
    records=plan['inputs']; need(len(records)==45 and len({r['id'] for r in records})==45,'input identities')
    index={x['id']:x for x in records}; need(all(index[k]['words'][15]==v for k,v in CENTERS.items()),'center pin')
    for item in records:
        actual=base.copy();actual[15]=f64(CENTERS[item['center']]); direction=item['direction']
        if direction!='center':
            seed=plan['direction_seeds'][direction]; pos=FIELDS.index(seed['field'])*39+seed['level_zero_bottom_first'];actual[pos]=actual[pos]+item['multiple']*item['h']*f64(seed['scale_f64_word'])
        need([w64(v) for v in actual]==item['words'],'represented input mismatch: '+item['id'])
    need(len({tuple(x['words']) for x in records})==45,'input uniqueness')
    return plan, selected, contract

def seed_specs(plan):
    records=plan['inputs']; result={}
    for center, directions in (('baseline',('nc','th','qv')),('lower',('nc','pii','th','qv')),('upper',('nc','pii','th','qv'))):
        reference=next(x for x in records if x['id']==center)['words']
        for direction in directions:
            group=[x for x in records if x['center']==center and x['direction']==direction]
            for h in sorted({x['h'] for x in group}):
                matching={x['multiple']:x for x in group if x['h']==h};want={1,2} if direction=='nc' else {-1,1};need(set(matching)==want,'endpoint stencil')
                lo=reference if direction=='nc' else matching[-1]['words'];hi=matching[1]['words'];den=h if direction=='nc' else 2*h
                seed=[w64((f64(b)-f64(a))/den) for a,b in zip(lo,hi)];need(len(seed)==624 and all(math.isfinite(f64(w)) for w in seed),'effective seed')
                ident=f'{center}:{direction}:{h:.0e}';need(ident not in result,'duplicate effective seed')
                result[ident]={'id':ident,'center':center,'direction':direction,'step_id':format(h,'.0e'),'evaluation_input_words':reference,'effective_direction_words':seed,'seed_sha256':words_sha(seed)}
    need(len(result)==21,'effective seed inventory')
    nominal={}
    for name,seed in plan['direction_seeds'].items():
        values=[ZERO]*624;values[FIELDS.index(seed['field'])*39+seed['level_zero_bottom_first']]=seed['scale_f64_word'];nominal[name]=values
    need(set(nominal)=={'th','qv','nc','pii'},'nominal seeds')
    cotangent=[ZERO]*468;cotangent[FIELDS.index('nc')*39+15]=ONE
    return result,nominal,{'state:nc:15':cotangent}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--plan',default=DEFAULT_PLAN);p.add_argument('--selected',default=DEFAULT_SELECTED);p.add_argument('--contract',default=DEFAULT_CONTRACT);a=p.parse_args();plan,_,_=load_inputs(a.plan,a.selected,a.contract);effective,nominal,vjp=seed_specs(plan)
    print(json.dumps({'status':'BLOCKED_SPEC_ONLY','inputs':45,'calls':100,'effective_jvp_seeds':len(effective),'nominal_jvp_seeds':len(nominal),'named_vjp_seeds':list(vjp),'new_dso':'not identified','live_sidecar_api':'not defined','model_calls':0},indent=2))
