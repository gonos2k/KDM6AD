#!/usr/bin/env python3
"""Source-only mapping of narrow batch5 hook sites; no model is executed."""
import collections,hashlib,json,re
import validate_atomic_catalog_v2 as catalog_v2
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]/'libtorch'
CATALOG_SHA='8693991bfc5acd28d7b6d81362302b9e9fffbfe80200d0a00a8dfb37d6d555f5'
SOURCE_SHA={'runtime.cpp':'cd605c03d451969534dfdf70b5bf9f0fbb41b892fb732bf7a3e680a18d1fd0c1','coordinator.cpp':'9976046be2a70bf813f8626584857cf78bd42fe88b2518f8730ea08c3599fd42','thermo.cpp':'faa37cf6aa83591b10b0055a81bd5111aa2fe0c96dc1815a2ca44c5bc0260564','satadj.cpp':'ed22e020f4cc15cd2c8d9e8bfaaaa274e3da67eceaddbb66d824bc2d25e6c604','progb.cpp':'ffa1fc911ee126105dd48da4437a95ee4aeb4c9b239b114349359322b15ddb0c','sedimentation.cpp':'b1bd0926e1d006fb71270069fb04d5874ecd22fc9bdf951772911c348f451d56'}
# Curated source-node correspondences. A source hook is not an emitted record,
# verified graph path, derivative, or a complete requirement group.
EXACT={
 'temperature_latent_terms.site.01':'activation_applied.t_pp','temperature_latent_terms.site.02':'activation_applied.t_final',
 'nc_named_rate_terms.site.01':'nc_budget.dnc_rate_sum','nc_named_rate_terms.site.03':'nc_budget.dnc_amount',
 'nc_entry_pre_post.site.01':'entry.nc_post','nc_entry_pre_post.site.02':'entry.nccn_post',
 'nc_snap1.site.01':'nc_snap1.nc_before','nc_snap1.site.02':'nc_snap1.nc_candidate','nc_snap1.site.03':'nc_snap1.nc_selected',
 'nc_snap2.site.01':'nc_snap2.nc_before','nc_snap2.site.02':'nc_snap2.nc_candidate','nc_snap2.site.03':'nc_snap2.nc_selected',
 'nc_update_reclass.site.01':'nc_budget.dnc_rate_sum','nc_update_reclass.site.02':'nc_budget.dnc_amount','nc_update_reclass.site.03':'nc_budget.nc_before_final_clamp','nc_update_reclass.site.04':'reclass_rain.nc_after',
 'nc_cleanup_dsd.site.02':'cleanup.nc_after','nc_cleanup_dsd.site.03':'dsd_inner.nc_after_min_gate','nc_cleanup_dsd.site.04':'dsd.nc_after',
 'pii_to_temperature.site.01':'entry.t','cpm_xl.site.01':'entry.cpm','cpm_xl.site.02':'entry.xl','cpm_xl.site.05':'activation.cpm_safe',
 'water_saturation.site.01':'activation.qs1','water_saturation.site.02':'thermo_qs_water.t_safe','water_saturation.site.03':'thermo_qs_water.es_selected','water_saturation.site.04':'activation.sw_percent',
 'satadj_condensation.site.01':'activation_applied.qs1_pp','satadj_condensation.site.02':'satadj_inner.is_super','satadj_condensation.site.03':'satadj_inner.is_sub_with_cloud','satadj_condensation.site.04':'activation_applied.t_final',
 'activation_fraction_min.site.01':'activation.sw_ratio','activation_fraction_min.site.02':'activation.fraction_min','activation_fraction_min.operand.pow_inline':'activation.fraction_pow','activation_fraction_min.operand.one_inline':'activation.fraction_one',
 'rate_min_operands.site.01':'rate_cap.raw','rate_min_operands.site.02':'rate_cap.min_pre_sw','rate_min_operands.site.03':'rate_cap.ncact_after_sw','rate_min_operands.operand.raw_rate':'rate_cap.raw','rate_min_operands.operand.cap_inline':'rate_cap.cap','rate_min_operands.operand.min_before_sw':'rate_cap.min_pre_sw',
 'applied_activation_transfer.site.01':'activation_applied.nc_pp','applied_activation_transfer.site.02':'activation_applied.nccn_pp','applied_activation_transfer.site.04':'activation_applied.nccn_final',
 'water_before_after.supplement.entry_qv':'entry.qv',
 'progb_bg_volume.site.02':'progb.bg_den','progb_bg_volume.site.03':'progb.bg_candidate','progb_bg_volume.site.04':'progb.active',
 'total_rain_fnresult.site.01':'surface_candidates.fallsum','total_rain_fnresult.site.04':'fnresult.rain_increment',
 'surface_flux_candidates.site.02':'surface_candidates.fallsum',
}
for species in ('qr','nr','qs','qg','brs','qi','ni'):
    family='ice' if species in ('qi','ni') else 'main'
    group='transport_'+species
    for index,hook in ((1,'sed_'+family+'_top.'+species+'_falk_candidate'),
                       (2,'sed_'+family+'_interior.'+species+'_falk_candidate'),
                       (3,'sed_'+family+'_interior.'+species+'_out_limited_candidate'),
                       (4,'sed_'+family+'_interior.'+species+'_arrival_limited_candidate'),
                       (5,'sed_'+family+'_interior.'+species+'_state_after_candidate'),
                       (6,'sedimentation_gate.active_'+family)):
        EXACT[f'{group}.site.{index:02d}']=hook
    for phase in ('top','k'):
        stage='sed_'+family+('_top' if phase=='top' else '_interior')
        EXACT[f'{group}.supplement.fall_{phase}']=stage+'.'+species+'_fall_accumulator_candidate'

# Each v2 mask requirement is composite. These are observable hook fragments,
# never an assertion that the requested comparison or operands are complete.
HOOK_EXPECTED_EXPRESSIONS={'activation.cpm_safe': ['cpm_safe, false);'], 'activation.fraction_min': ['activated_fraction, false);'], 'activation.fraction_one': ['batch5_fraction_one, false);'], 'activation.fraction_pow': ['batch5_fraction_pow, false);'], 'activation.qs1': ['qs1, false);'], 'activation.sw_percent': ['sw_percent, false);'], 'activation.sw_ratio': ['sw_ratio, false);'], 'activation_applied.nc_pp': ['nc_pp, false);'], 'activation_applied.nccn_final': ['nccn_final, false);'], 'activation_applied.nccn_pp': ['nccn_pp, false);'], 'activation_applied.qs1_pp': ['qs1_pp, false);'], 'activation_applied.t_final': ['t_final, false);'], 'activation_applied.t_pp': ['t_pp, false);'], 'cleanup.nc_after': ['new_state.nc, false);'], 'dsd.nc_after': ['new_state.nc, false);'], 'dsd_inner.nc_after_min_gate': ['nc_new, false);'], 'entry.cpm': ['entry_cpm, false);'], 'entry.nc_post': ['cur.nc, false);'], 'entry.nccn_post': ['cur.nccn, false);'], 'entry.qv': ['cs.qv, false);'], 'entry.t': ['cs.t, false);'], 'entry.xl': ['entry_xl, false);'], 'fnresult.rain_increment': ['fn_out.rain_increment);', 'fn_out.rain_increment);'], 'nc_budget.dnc_amount': ['dnc_amount, false);'], 'nc_budget.dnc_rate_sum': ['dnc_rate_sum, false);'], 'nc_budget.nc_before_final_clamp': ['nc_new, false);'], 'nc_snap1.nc_before': ['nc_orig1, false);'], 'nc_snap1.nc_candidate': ['nc_snap1, false);'], 'nc_snap1.nc_selected': ['working1b.nc, false);'], 'nc_snap2.nc_before': ['nc_orig2, false);'], 'nc_snap2.nc_candidate': ['nc_snap2, false);'], 'nc_snap2.nc_selected': ['working.nc, false);'], 'progb.active': ['active, top);'], 'progb.bg_candidate': ['bg_new_op, top);'], 'progb.bg_den': ['bg_den, top);'], 'rate_cap.cap': ['batch5_rate_cap, false);'], 'rate_cap.min_pre_sw': ['ncact, false);'], 'rate_cap.ncact_after_sw': ['ncact, false);'], 'rate_cap.raw': ['ncact_raw, false);'], 'reclass_rain.nc_after': ['new_state.nc, false);'], 'satadj_inner.is_sub_with_cloud': ['is_sub_with_cloud, top);'], 'satadj_inner.is_super': ['is_super, top);'], 'sed_ice_interior.ni_arrival_limited_candidate': ['dni_above, k, K);'], 'sed_ice_interior.ni_falk_candidate': ['falk_ni_k, k, K);'], 'sed_ice_interior.ni_fall_accumulator_candidate': ['fall_ni_cols[k], k, K);'], 'sed_ice_interior.ni_out_limited_candidate': ['dni_k, k, K);'], 'sed_ice_interior.ni_state_after_candidate': ['ni_cols[k], k, K);'], 'sed_ice_interior.qi_arrival_limited_candidate': ['dqi_above, k, K);'], 'sed_ice_interior.qi_falk_candidate': ['falk_qi_k, k, K);'], 'sed_ice_interior.qi_fall_accumulator_candidate': ['fall_qi_cols[k], k, K);'], 'sed_ice_interior.qi_out_limited_candidate': ['dqi_k, k, K);'], 'sed_ice_interior.qi_state_after_candidate': ['qi_cols[k], k, K);'], 'sed_ice_top.ni_falk_candidate': ['falk_ni_top, k, K);'], 'sed_ice_top.ni_fall_accumulator_candidate': ['fall_ni_cols[k], k, K);'], 'sed_ice_top.qi_falk_candidate': ['falk_qi_top, k, K);'], 'sed_ice_top.qi_fall_accumulator_candidate': ['fall_qi_cols[k], k, K);'], 'sed_main_interior.brs_arrival_limited_candidate': ['dbrs_above, k, K);'], 'sed_main_interior.brs_falk_candidate': ['falk_brs_k, k, K);'], 'sed_main_interior.brs_fall_accumulator_candidate': ['fall_brs_cols[k], k, K);'], 'sed_main_interior.brs_out_limited_candidate': ['dbrs_k, k, K);'], 'sed_main_interior.brs_state_after_candidate': ['brs_cols[k], k, K);'], 'sed_main_interior.nr_arrival_limited_candidate': ['dnr_above, k, K);'], 'sed_main_interior.nr_falk_candidate': ['falk_nr_k, k, K);'], 'sed_main_interior.nr_fall_accumulator_candidate': ['fall_nr_cols[k], k, K);'], 'sed_main_interior.nr_out_limited_candidate': ['dnr_k, k, K);'], 'sed_main_interior.nr_state_after_candidate': ['nr_cols[k], k, K);'], 'sed_main_interior.qg_arrival_limited_candidate': ['dqg_above, k, K);'], 'sed_main_interior.qg_falk_candidate': ['falk_qg_k, k, K);'], 'sed_main_interior.qg_fall_accumulator_candidate': ['fall_qg_cols[k], k, K);'], 'sed_main_interior.qg_out_limited_candidate': ['dqg_k, k, K);'], 'sed_main_interior.qg_state_after_candidate': ['qg_cols[k], k, K);'], 'sed_main_interior.qr_arrival_limited_candidate': ['dqr_above, k, K);'], 'sed_main_interior.qr_falk_candidate': ['falk_qr_k, k, K);'], 'sed_main_interior.qr_fall_accumulator_candidate': ['fall_qr_cols[k], k, K);'], 'sed_main_interior.qr_out_limited_candidate': ['dqr_k, k, K);'], 'sed_main_interior.qr_state_after_candidate': ['qr_cols[k], k, K);'], 'sed_main_interior.qs_arrival_limited_candidate': ['dqs_above, k, K);'], 'sed_main_interior.qs_falk_candidate': ['falk_qs_k, k, K);'], 'sed_main_interior.qs_fall_accumulator_candidate': ['fall_qs_cols[k], k, K);'], 'sed_main_interior.qs_out_limited_candidate': ['dqs_k, k, K);'], 'sed_main_interior.qs_state_after_candidate': ['qs_cols[k], k, K);'], 'sed_main_top.brs_falk_candidate': ['falk_brs_top, k, K);'], 'sed_main_top.brs_fall_accumulator_candidate': ['fall_brs_cols[k], k, K);'], 'sed_main_top.nr_falk_candidate': ['falk_nr_top, k, K);'], 'sed_main_top.nr_fall_accumulator_candidate': ['fall_nr_cols[k], k, K);'], 'sed_main_top.qg_falk_candidate': ['falk_qg_top, k, K);'], 'sed_main_top.qg_fall_accumulator_candidate': ['fall_qg_cols[k], k, K);'], 'sed_main_top.qr_falk_candidate': ['falk_qr_top, k, K);'], 'sed_main_top.qr_fall_accumulator_candidate': ['fall_qr_cols[k], k, K);'], 'sed_main_top.qs_falk_candidate': ['falk_qs_top, k, K);'], 'sed_main_top.qs_fall_accumulator_candidate': ['fall_qs_cols[k], k, K);'], 'sedimentation_gate.active_ice': ['active_ice.squeeze(1));'], 'sedimentation_gate.active_main': ['active_main.squeeze(1));'], 'surface_candidates.fallsum': ['fallsum);'], 'thermo_qs_water.es_selected': ['es, batch5::top_first());'], 'thermo_qs_water.t_safe': ['t_safe, batch5::top_first());']}

MASK_HOOKS={
 'mask.entry_nc_floor':['entry.nc_pre','entry.nc_floor_lt','entry.nc_floor_eq'],
 'mask.entry_nccn_bounds':['entry.nccn_pre','entry.nccn_floor_lt','entry.nccn_floor_eq','entry.nccn_cap_gt','entry.nccn_cap_eq'],
 'mask.snap1_per_cell_gate':['nc_snap1.nc_before','nc_snap1.ncmin','nc_snap1.nc_ge_ncmin','nc_snap1.nc_eq_ncmin','nc_snap1.qc','nc_snap1_lambda.q_ge_threshold'],
 'mask.snap2_per_cell_gate':['nc_snap2.nc_before','nc_snap2.ncmin','nc_snap2.nc_ge_ncmin','nc_snap2.nc_eq_ncmin','nc_snap2.qc','nc_snap2_lambda.q_ge_threshold'],
 'mask.lambda_active':['nc_snap1_lambda.q_ge_threshold','nc_snap1_lambda.n_ge_threshold','nc_snap1_lambda.active','nc_snap2_lambda.q_ge_threshold','nc_snap2_lambda.n_ge_threshold','nc_snap2_lambda.active','nc_dsd_lambda.active'],
 'mask.lambda_bounds':['nc_snap1_lambda.lamda','nc_snap1_lambda.lamda_le_min','nc_snap1_lambda.lamda_ge_max','nc_snap1_lambda.lamda_eq_min_observed','nc_snap1_lambda.lamda_eq_max_observed','nc_snap1_lambda.too_small','nc_snap1_lambda.too_large'],
 'mask.dsd_ncmin':['dsd_inner.nc_input','dsd_inner.ncmin','dsd_inner.nc_ge_ncmin','dsd_inner.nc_eq_ncmin'],
 'mask.dsd_ncmax':['dsd_inner.nc_before_max_gate','dsd_inner.nc_gt_ncmax','dsd_inner.nc_eq_ncmax'],
 'mask.cleanup_qc':['cleanup_mask.qc','cleanup_mask.keep_qc','cleanup_mask.qc_eq_qmin'],
 'mask.temperature_floor':['thermo_qs_water.t_input','thermo_qs_water.t_lt_floor','thermo_qs_water.t_eq_floor'],
 'mask.water_es_cap':['thermo_qs_water.es_input','thermo_qs_water.es_cap','thermo_qs_water.es_lt_cap','thermo_qs_water.es_eq_cap','thermo_qs_water.es_gt_cap'],
 'mask.satadj_paths':['satadj_inner.work1','satadj_inner.qc_input','satadj_inner.is_super','satadj_inner.is_sub_with_cloud','satadj_inner.cloud_complete_evap'],
 'mask.safe_pow_floor':['activation.sw_ratio'],
 'mask.ncact_preclamp':['rate_cap.numerator','rate_cap.numerator_lt_zero','rate_cap.numerator_eq_zero'],
 'mask.nccn_cap_clamp':['activation.nccn_input','rate_cap.nccn_lt_zero','rate_cap.nccn_eq_zero','rate_cap.raw','rate_cap.cap','rate_cap.raw_lt_cap','rate_cap.raw_eq_cap','rate_cap.raw_gt_cap'],
 'mask.main_transport_gate':['sedimentation_gate.active_main','sedimentation_gate.mstep_main'],'mask.ice_transport_gate':['sedimentation_gate.active_ice','sedimentation_gate.mstep_ice'],
 'mask.warm_cold_gate':['nc_budget.supcol','nc_budget.cold_mask_numeric'],
 'mask.progb_density_gate':['progb.active','progb.bg_input','progb.bg_den','progb.zero_den','progb.rhox_op','progb.rhox_candidate','progb.bg_candidate','progb.bg_selected'],
}
MASK_GAPS={
 'mask.entry_nc_floor':'Greater-than outcome not directly emitted.',
 'mask.entry_nccn_bounds':'Full three-way comparisons for each bound and all source operands are not separately emitted.',
 'mask.snap1_per_cell_gate':'NCmin optional-absent reason and QC threshold equality not separately emitted.',
 'mask.snap2_per_cell_gate':'NCmin optional-absent reason and QC threshold equality not separately emitted.',
 'mask.lambda_active':'q/n threshold scalar words and equality outcomes are not emitted; DSD component mask fragments are incomplete in this list.',
 'mask.lambda_bounds':'Lambda threshold scalar words and all three labeled lambda call-site outcomes are not fully bound.',
 'mask.dsd_ncmin':'Raw threshold provenance and all lambda/quality conditions are separate; no derivative sidecar.',
 'mask.dsd_ncmax':'NCMAX scalar threshold is not emitted as an independent raw operand.',
 'mask.cleanup_qc':'qmin scalar threshold is not emitted as an independent raw operand.',
 'mask.temperature_floor':'1 K scalar and explicit greater-than outcome are not independently emitted.',
 'mask.water_es_cap':'Source comparisons are present, but dynamic invocation/orientation and runtime records remain unverified.',
 'mask.satadj_paths':'Condensation/evaporation cap comparison operands and all three-way ties are not emitted.',
 'mask.safe_pow_floor':'EPS threshold comparison is not directly emitted; sw_ratio alone is not the mask.',
 'mask.ncact_preclamp':'Explicit positive comparison and source-level independent JVP/VJP output are not emitted.',
 'mask.nccn_cap_clamp':'Explicit positive NCCN comparison and independent operand derivative output are not emitted.',
 'mask.main_transport_gate':'Actual gate is captured as a squeezed B-column view; dynamic runtime identity and inactive-state selection remain unverified.',
 'mask.ice_transport_gate':'Actual gate is captured as a squeezed B-column view; dynamic runtime identity and inactive-state selection remain unverified.',
 'mask.warm_cold_gate':'Only supcol and numeric cold_mask are hooked; proposed explicit three-way Boolean mask is not emitted.',
 'mask.progb_density_gate':'op_f32 and midpoint_trace are C++ controls not emitted as tensor masks; density bound comparisons and runtime identities remain unverified.',
}

def need(ok,why):
    if not ok:raise ValueError(why)
def sha(raw):return hashlib.sha256(raw).hexdigest()

def extract(sources):
    hooks={};literal=0;dynamic=[]
    pat=re.compile(r'batch5::(full|column|layer)\(\s*"([^\"]+)",\s*"([^\"]+)"\s*,\s*(.*)')
    dyn=re.compile(r'batch5::full\(label,\s*"([^\"]+)"\s*,\s*(.*)')
    for name,text in sources.items():
        in_target=[]
        for lineno,line in enumerate(text.splitlines(),1):
            token=line.strip()
            if token.startswith('#if'):
                if token=='#ifdef KDM6_BATCH5_RESEARCH_CAPTURE':in_target.append([True,True])
                elif token=='#ifndef KDM6_BATCH5_RESEARCH_CAPTURE':in_target.append([True,False])
                else:in_target.append([False,True])
            elif token.startswith('#else'):
                need(bool(in_target),'preprocessor else nesting')
                if in_target[-1][0]:in_target[-1][1]=not in_target[-1][1]
            elif token.startswith('#endif'):
                need(bool(in_target),'preprocessor nesting');in_target.pop()
            m=pat.search(line);d=dyn.search(line)
            if not m and not d:continue
            target=[active for is_target,active in in_target if is_target]
            need(bool(target) and all(target),'hook outside macro-enabled guard')
            if m:
                kind,stage,field,expression=m.groups();key=stage+'.'+field
                site={'file':'src/'+name,'line':lineno,'call':kind,'expression_tail':expression.strip(),'source_site_only':True}
                hooks.setdefault(key,[]).append(site);literal+=1
            else:dynamic.append((name,lineno,d.group(1),d.group(2).strip()))
        need(not in_target,'unbalanced preprocessor')
    need(literal==281 and len(dynamic)==17,'hook callsite inventory')
    need({k:len(v) for k,v in hooks.items() if len(v)>1}=={'fnresult.rain_increment':2},'repeated source site inventory')
    coord=sources['coordinator.cpp']; labels=('nc_snap1_lambda','nc_snap2_lambda','nc_dsd_lambda')
    for stage in labels:
        need(f'batch5::site("{stage}")' in coord,'dynamic callsite label')
        for name,line,field,expression in dynamic:
            key=stage+'.'+field;need(key not in hooks,'dynamic stage duplicate')
            hooks[key]=[{'file':'src/'+name,'line':line,'call':'full','expression_tail':expression,'source_site_only':True,'dynamic_site':stage}]
    need(len(hooks)==331,'expanded stage/field inventory')
    return hooks

def analyze(catalog,sources):
    need(catalog['schema']=='kdm6.native_host_atomic_capture_catalog.draft.v2' and catalog['status']=='DRAFT_BLOCKED','catalog schema')
    atoms=catalog['atoms'];masks=catalog['proposed_masks'];groups=catalog['groups']
    need(len(atoms)==191 and len({x['atomic_id'] for x in atoms})==191 and len(groups)==28 and len(masks)==19,'catalog inventory')
    hooks=extract(sources);ids={a['atomic_id'] for a in atoms};need(set(EXACT)<=ids,'mapping uses nonexistent atom')
    need(set(MASK_HOOKS)==set(MASK_GAPS)=={x['atomic_id'] for x in masks},'mask mapping inventory')
    for key in list(EXACT.values())+[x for values in MASK_HOOKS.values() for x in values]:need(key in hooks,'mapped source hook missing '+key)
    need(set(HOOK_EXPECTED_EXPRESSIONS)==set(EXACT.values()),'hook expression pin inventory')
    for key,expression in HOOK_EXPECTED_EXPRESSIONS.items():need([site['expression_tail'] for site in hooks[key]]==expression,'hook tensor expression differs '+key)
    mapped=[];missing=[]
    for atom in atoms:
        ident=atom['atomic_id'];entry={'atomic_id':ident,'requirement_id':atom['requirement_id'],'catalog_binding_status':atom['binding_status'],'catalog_source_site':atom['source_site']}
        if ident in EXACT:
            key=EXACT[ident]
            kind=('SQUEEZED_COLUMN_VIEW_OF_GATE' if ident.startswith('transport_') and ident.endswith('.site.06') else 'RETURNED_FNRESULT_MEMBER' if ident=='total_rain_fnresult.site.04' else 'CURATED_SOURCE_TENSOR_CORRESPONDENCE')
            entry.update(status='SOURCE_HOOK_IDENTIFIED_RUNTIME_UNVERIFIED',mapping_kind=kind,hook_id=key,hook=hooks[key]);mapped.append(entry)
        else:
            entry.update(status='NO_DIRECT_HOOK_PROVEN_BY_THIS_AUDIT',blocked_reason=atom['blocked_reason']);missing.append(entry)
    mask_rows=[{'atomic_id':m['atomic_id'],'source_hook_fragments':[{'hook_id':key,'sites':hooks[key]} for key in MASK_HOOKS[m['atomic_id']]],'status':'PARTIAL_SOURCE_FRAGMENTS_RUNTIME_UNVERIFIED' if MASK_HOOKS[m['atomic_id']] else 'NO_DIRECT_HOOK_PROVEN_BY_THIS_AUDIT','remaining_gap':MASK_GAPS[m['atomic_id']]} for m in masks]
    bygroup=[]
    for g in groups:
        count=sum(x['requirement_id']==g['group_id'] for x in mapped)
        total=sum(x['requirement_id']==g['group_id'] for x in mapped+missing)
        bygroup.append({'group_id':g['group_id'],'catalog_atoms':total,'source_hook_matches':count,'status':'BLOCKED_NOT_CERTIFIED'})
    return {'schema':'kdm6.batch5.source_hook_coverage.v1','status':'SOURCE_ONLY_BLOCKED','catalog_sha256':CATALOG_SHA,'source_sha256':SOURCE_SHA,'source_hook_callsites':298,'literal_stage_fields':280,'expanded_stage_fields':len(hooks),'hook_inventory':hooks,'atom_source_hook_matches':mapped,'atoms_without_direct_proven_hook':missing,'groups':bygroup,'proposed_masks':mask_rows,'limitations':'Curated source correspondences only. Macro-guarded hook text does not prove compilation, execution, field emission, actual tensor/gradient identity, branch coverage, derivative availability, unit validity or conservation. Main/ice gates are squeezed column views; sedimentation out/arrival and post-state nodes are candidates before the outer active-gate selection, not realized transfers. No group or mask requirement is certified complete. FnResult rain hooks do not create a packed AD ABI, graph derivative accessor or physical closure.','scientific_status':'INCONCLUSIVE','physical_unit_status':'INCONCLUSIVE'}

def load():
    parent_raw=(HERE/'atomic_catalog_draft.json').read_bytes();patch_raw=(HERE/'atomic_catalog_consumer_patch_v2.json').read_bytes()
    need(sha(parent_raw)==catalog_v2.V1_SHA and sha(patch_raw)==catalog_v2.PATCH_SHA,'catalog lineage SHA')
    parent=json.loads(parent_raw);catalog=catalog_v2.materialize(json.loads(patch_raw),parent)
    archive=(HERE.parent/'native_host_preflight_2026-11-12/field_contract_sources.zip').read_bytes()
    catalog_v2.validate(catalog,parent,archive)
    need(catalog_v2.V2_SHA==CATALOG_SHA,'materialized catalog SHA')
    sources={}
    for name,digest in SOURCE_SHA.items():
        data=(ROOT/'src'/name).read_bytes();need(sha(data)==digest,'source SHA '+name);sources[name]=data.decode()
    return analyze(catalog,sources)


def summary(result):
    return {'schema':'kdm6.batch5.source_hook_coverage.summary.v1','status':'SOURCE_ONLY_BLOCKED',
            'catalog_sha256':CATALOG_SHA,'source_sha256':SOURCE_SHA,
            'source_hook_callsites':result['source_hook_callsites'],
            'literal_stage_fields':result['literal_stage_fields'],
            'expanded_stage_fields':result['expanded_stage_fields'],
            'source_hook_match_atom_ids':[x['atomic_id'] for x in result['atom_source_hook_matches']],
            'unmapped_atom_ids':[x['atomic_id'] for x in result['atoms_without_direct_proven_hook']],
            'proposed_mask_ids':[x['atomic_id'] for x in result['proposed_masks']],
            'groups':result['groups'],
            'applied_transport_unresolved_ids':[x['atomic_id'] for x in result['atoms_without_direct_proven_hook'] if '.unresolved.' in x['atomic_id']],
            'mask_status':'all 19 PARTIAL_SOURCE_FRAGMENTS_RUNTIME_UNVERIFIED',
            'scope':'source hook text only; no runtime emission, graph derivative, applied budget or physical certification',
            'scientific_status':'INCONCLUSIVE','physical_unit_status':'INCONCLUSIVE'}


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--details-dir',type=Path,help='optionally write regenerated detailed JSON and Markdown')
    args=parser.parse_args();result=load()
    if args.details_dir:
        args.details_dir.mkdir(parents=True,exist_ok=True)
        (args.details_dir/'hook_coverage_details.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
        lines=['# Source-only hook coverage details','','All groups remain BLOCKED; source hook fragments are not emitted/runtime evidence.','','| Group | Matches / catalog atoms | Status |','| --- | ---: | --- |']
        lines.extend(f"| {g['group_id']} | {g['source_hook_matches']} / {g['catalog_atoms']} | {g['status']} |" for g in result['groups'])
        lines.extend(['','| Mask | Hook fragments | Remaining gap |','| --- | ---: | --- |'])
        lines.extend(f"| {m['atomic_id']} | {len(m['source_hook_fragments'])} | {m['remaining_gap']} |" for m in result['proposed_masks'])
        (args.details_dir/'hook_coverage_details.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(summary(result),indent=2,sort_keys=True))

if __name__=='__main__':main()
