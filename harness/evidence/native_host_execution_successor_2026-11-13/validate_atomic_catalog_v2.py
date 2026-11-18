#!/usr/bin/env python3
"""Materialize and validate the compact correction to the pinned source catalog."""
import copy,hashlib,io,json,re,zipfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
PARENT=HERE.parent/'native_host_preflight_2026-11-12'
V1_SHA='05d2291d1060ddee582c443d719035b8e4a84a1c8293c4385ed5208e60aa331d'
V2_SHA='8693991bfc5acd28d7b6d81362302b9e9fffbfe80200d0a00a8dfb37d6d555f5'
PATCH_SHA='692a6f44bb6de6335a5176a68300aec57b7922c29e82db028fec99716f3324c3'
ARCHIVE_SHA='663871cbb48154ea6c63a18991710e955bdec5d7ac5cda9d32bc0e0dd68c2347'
C='libtorch/src/coordinator.cpp'
CONTEXT_RULE='Move each v1 atom consumer to context_location/context_relation/context_evidence; clear consumer except verified_source_uses. Move each proposed-mask consumer text to context_text; clear consumer.'
EDGES={
 'phase_change_heat.supplement.dep_sum':{'producer_line':2492,'consumer_line':2496,'symbol':'dep_sum_c','kind':'RHS_USE','anchor':'auto xlwork2_cold = -xls * dep_sum_c - pre.xl * warm.prevp - xlf * frz_sum_c;','source_use':'same-function explicit RHS use; source-level only'},
 'phase_change_heat.supplement.temperature_final':{'producer_line':2506,'consumer_line':2540,'symbol':'t_new','kind':'RETURN_MEMBER','anchor':'t_new,','source_use':'same-function CoordinatorState aggregate return; source-level only'},
}

def need(ok,why):
    if not ok:raise ValueError(why)
def sha(raw):return hashlib.sha256(raw).hexdigest()

def materialize(patch,v1):
    parent_bytes=(HERE/'atomic_catalog_draft.json').read_bytes()
    need(sha(parent_bytes)==V1_SHA and v1==json.loads(parent_bytes),'pinned parent object')
    need(set(patch)=={'schema','parent_v1_sha256','source_archive_sha256','materialized_v2_sha256','materialized_schema','status','scope','consumer_summary','context_rule','verified_source_uses'},'patch keys')
    need(patch['schema']=='kdm6.native_host_atomic_catalog_consumer_patch.v2' and patch['parent_v1_sha256']==V1_SHA and patch['source_archive_sha256']==ARCHIVE_SHA and patch['materialized_v2_sha256']==V2_SHA and patch['materialized_schema']=='kdm6.native_host_atomic_capture_catalog.draft.v2' and patch['status']=='DRAFT_BLOCKED' and patch['context_rule']==CONTEXT_RULE,'patch policy')
    expected={ident:{'location':{'file':C,'line':spec['consumer_line'],'anchor':spec['anchor']},'symbol':spec['symbol'],'kind':spec['kind'],'source_use':spec['source_use']} for ident,spec in EDGES.items()}
    need(patch['verified_source_uses']==expected and patch['consumer_summary']=={'verified_source_uses':2,'context_only_unverified':189,'proposed_masks_unverified':19,'limitations':'Only exact intra-function source uses explicitly checked; no executed graph, capture, derivative or physical claim.'},'patch consumers')
    v2=copy.deepcopy(v1)
    v2.update({'schema':patch['materialized_schema'],'status':patch['status'],'scope':patch['scope'],'parent_v1_sha256':V1_SHA,'consumer_summary':patch['consumer_summary']})
    for atom in v2['atoms']:
        old=atom.pop('consumer')
        atom['context_location']=old['location'];atom['context_relation']=old['relation'];atom['context_evidence']=old['evidence']
        atom['consumer']=patch['verified_source_uses'].get(atom['atomic_id'])
        atom['consumer_status']='VERIFIED_SOURCE_USE' if atom['consumer'] is not None else 'UNVERIFIED'
    for mask in v2['proposed_masks']:
        mask['context_text']=mask.pop('consumer');mask['context_location']=None;mask['consumer']=None;mask['consumer_status']='UNVERIFIED'
    raw=(json.dumps(v2,indent=2,sort_keys=True)+'\n').encode()
    need(sha(raw)==V2_SHA,'materialized v2 SHA')
    return v2

def validate(v2,v1,archive):
    parent_bytes=(HERE/'atomic_catalog_draft.json').read_bytes()
    need(sha(parent_bytes)==V1_SHA and v1==json.loads(parent_bytes),'pinned parent object')
    patch_bytes=(HERE/'atomic_catalog_consumer_patch_v2.json').read_bytes()
    need(sha(patch_bytes)==PATCH_SHA,'patch SHA')
    canonical_v2=materialize(json.loads(patch_bytes),v1)
    need(v2['schema']=='kdm6.native_host_atomic_capture_catalog.draft.v2' and v2['status']=='DRAFT_BLOCKED' and v2['scientific_status']==v2['physical_unit_status']=='INCONCLUSIVE','v2 status')
    need(v2['parent_v1_sha256']==V1_SHA and v2['source_archive_sha256']==v1['source_archive_sha256']==ARCHIVE_SHA and sha(archive)==ARCHIVE_SHA,'parent/archive pins')
    for key in ('groups','identity','source_sha256','parent_contract_sha256','ordering_scope','provenance_warning'):
        need(v2[key]==v1[key],'v1 preserved: '+key)
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        names=z.namelist();need(len(names)==len(set(names))==10 and set(names)==set(v1['source_sha256']),'source inventory')
        sources={}
        for name in names:
            raw=z.read(name);need(sha(raw)==v1['source_sha256'][name] and name.startswith('libtorch/'),'source SHA')
            sources[name]=raw.decode().splitlines()
    old={a['atomic_id']:a for a in v1['atoms']};new={a['atomic_id']:a for a in v2['atoms']}
    need(len(old)==len(new)==191 and len(v2['atoms'])==191 and set(old)==set(new),'atomic inventory')
    verified=[]
    for ident,a in new.items():
        source=old[ident];previous=source['consumer']
        for key,value in source.items():
            if key!='consumer':need(a.get(key)==value,'v1 atom changed '+ident+' '+key)
        need(a['context_location']==previous['location'] and a['context_relation']==previous['relation'] and a['context_evidence']==previous['evidence'],'context differs from v1 '+ident)
        site=a['source_site'];name,line=site['file'],site['line'];need(name in sources and type(line) is int and 1<=line<=len(sources[name]) and site['anchor'] in sources[name][line-1] and a['source_line_exact']==sources[name][line-1].strip(),'source site '+ident)
        if ident not in EDGES:
            need(a['consumer_status']=='UNVERIFIED' and a['consumer'] is None,'unsupported consumer '+ident)
            continue
        spec=EDGES[ident];consumer=a['consumer'];expected={'location':{'file':C,'line':spec['consumer_line'],'anchor':spec['anchor']},'symbol':spec['symbol'],'kind':spec['kind'],'source_use':spec['source_use']}
        need(a['consumer_status']=='VERIFIED_SOURCE_USE' and consumer==expected,'verified consumer mismatch '+ident)
        need(name==C and line==spec['producer_line'] and line<spec['consumer_line'],'consumer must follow producer '+ident)
        lines=sources[C];producer=lines[line-1].split('//',1)[0];use=lines[spec['consumer_line']-1].split('//',1)[0]
        need(re.search(r'\bauto\s+'+re.escape(spec['symbol'])+r'\s*=',producer) is not None and spec['anchor'] in use,'verified source expression '+ident)
        need('CoordinatorState state_update(' in '\n'.join(lines[2090:2112]) and line>2106 and spec['consumer_line']<2542,'same source function boundary')
        if spec['kind']=='RHS_USE':
            need('=' in use and re.search(r'\b'+re.escape(spec['symbol'])+r'\b',use.split('=',1)[1]) is not None,'source RHS use')
        else:
            need('return CoordinatorState{' in '\n'.join(lines[2515:spec['consumer_line']-1]) and use.strip()=='t_new,','aggregate return use')
        verified.append(ident)
    need(set(verified)==set(EDGES),'verified edge inventory')
    old_masks={x['atomic_id']:x for x in v1['proposed_masks']};new_masks={x['atomic_id']:x for x in v2['proposed_masks']}
    need(len(old_masks)==len(new_masks)==19 and len(v2['proposed_masks'])==19 and set(old_masks)==set(new_masks),'mask inventory')
    for ident,m in new_masks.items():
        source=old_masks[ident]
        for key,value in source.items():
            if key!='consumer':need(m.get(key)==value,'v1 mask changed '+ident)
        need(m['context_text']==source['consumer'] and m['context_location'] is None and m['consumer'] is None and m['consumer_status']=='UNVERIFIED','mask context/consumer')
    need(v2['consumer_summary']=={'verified_source_uses':2,'context_only_unverified':189,'proposed_masks_unverified':19,'limitations':'Only exact intra-function source uses explicitly checked; no executed graph, capture, derivative or physical claim.'},'consumer summary')
    need(v2==canonical_v2,'pinned v2 object')
    return {'status':'DRAFT_BLOCKED','atoms':191,'groups':28,'masks':19,'verified_source_consumers':len(verified),'context_only_atoms':len(new)-len(verified),'scientific_status':'INCONCLUSIVE','physical_unit_status':'INCONCLUSIVE'}

def main():
    a=(HERE/'atomic_catalog_consumer_patch_v2.json').read_bytes();need(sha(a)==PATCH_SHA,'patch SHA')
    b=(HERE/'atomic_catalog_draft.json').read_bytes();need(sha(b)==V1_SHA,'v1 SHA')
    v1=json.loads(b);v2=materialize(json.loads(a),v1)
    print(json.dumps(validate(v2,v1,(PARENT/'field_contract_sources.zip').read_bytes()),indent=2,sort_keys=True))
if __name__=='__main__':main()
