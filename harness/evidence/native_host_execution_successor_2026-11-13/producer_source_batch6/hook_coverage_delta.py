"""Conservative source-site delta; no model execution or coverage certification."""
import hashlib
import json
import re
from pathlib import Path
try:
    from . import replay
except ImportError:
    import replay
HERE = Path(__file__).resolve().parent
SUMMARY_SHA = 'cf706dd2af631a4da8fc20d7d9f5ef1da1aef186712a1e50bc273c6b10478e80'
CATALOG_SHA = '05d2291d1060ddee582c443d719035b8e4a84a1c8293c4385ed5208e60aa331d'
MAP = {
'phase_change_heat.site.03':('a5_heat','xlf','xlf'),
'phase_change_heat.supplement.cpm_safe':('a5_heat','cpm_safe','cpm_safe'),
'phase_change_heat.supplement.xlf':('a5_heat','xlf','xlf'),
'phase_change_heat.supplement.dep_sum':('a5_heat','dep_sum_c','dep_sum_c'),
'phase_change_heat.supplement.frz_sum':('a5_heat','frz_sum_c','frz_sum_c'),
'phase_change_heat.supplement.cold_heat':('a5_heat','xlwork2_cold','xlwork2_cold'),
'phase_change_heat.supplement.vap_sum':('a5_heat','vap_sum_w','vap_sum_w'),
'phase_change_heat.supplement.warm_heat':('a5_heat','xlwork2_warm','xlwork2_warm'),
'phase_change_heat.supplement.selected_heat':('a5_heat','xlwork2_selected','xlwork2'),
'phase_change_heat.supplement.melt_coefficient':('a5_heat','coef_melt','coef_melt'),
'phase_change_heat.supplement.temperature_final':('a5_heat','t_new','t_new'),
'progb_bg_volume.supplement.brs_acc_entry':('a5_brs','after_freeze','brs_acc'),
'progb_bg_volume.supplement.brs_melt':('a5_brs','after_melt','brs_acc'),
'progb_bg_volume.supplement.brs_cold':('a5_brs','after_cold','brs_acc'),
'progb_bg_volume.supplement.brs_warm':('a5_brs','after_warm','brs_acc'),
'progb_bg_volume.supplement.brs_clamp':('a5_brs','after_fmax','brs_new'),
'water_named_rate_apply.site.02':('a5_satadj','pcact_raw','pcact_raw'),
'water_named_rate_apply.site.03':('a5_satadj','qv_final','qv_final'),
}

def need(ok, message):
    if not ok: raise ValueError(message)

def run():
    summary_raw = (HERE.parent/'hook_coverage_summary.json').read_bytes()
    catalog_raw = (HERE.parent/'atomic_catalog_draft.json').read_bytes()
    need(hashlib.sha256(summary_raw).hexdigest()==SUMMARY_SHA, 'parent coverage SHA')
    need(hashlib.sha256(catalog_raw).hexdigest()==CATALOG_SHA, 'catalog SHA')
    prior=json.loads(summary_raw); atoms={x['atomic_id']:x for x in json.loads(catalog_raw)['atoms']}
    missing=set(prior['unmapped_atom_ids']); need(len(missing)==84 and set(MAP)<=missing, 'previous inventory')
    with replay.reconstructed_tree() as (root,_): text=(root/'src/coordinator.cpp').read_text()
    blocks=re.findall(r'#ifdef KDM6_BATCH5_RESEARCH_CAPTURE // A5_HOOK_BEGIN\n(.*?)#endif // A5_HOOK_END',text,re.S)
    need(len(blocks)==7,'A5 guard inventory')
    found=re.findall(r'batch5::full\("(a5_[^"]+)", "([^"]+)", ([^,]+), false\);','\n'.join(blocks))
    need(len(found)==35 and len(set(found))==35 and len({x[:2] for x in found})==35,'A5 hook inventory')
    rows=[]
    for ident,hook in MAP.items():
        need(hook in found,'missing source hook '+ident)
        anchor=atoms[ident]['source_line_exact'].strip()
        need(anchor in text,'source producer missing '+ident)
        rows.append({'atom_id':ident,'hook_id':'.'.join(hook[:2]),'tensor':hook[2], 'source_expression':anchor})
    return {'schema':'kdm6.batch6.hook_coverage_delta.v1','status':'SOURCE_ONLY_BLOCKED',
            'catalog_atoms':191,'prior_mapped':107,'prior_unmapped':84,'new_hook_calls':35,
            'new_mapped_atoms':len(rows),'updated_mapped_atoms':107+len(rows),
            'remaining_unmapped_atoms':len(missing-set(MAP)), 'mapped':rows,
            'remaining_unmapped_ids':sorted(missing-set(MAP)),
            'limits':'Source correspondence only; execution, emitted records, derivative connectivity, physical units and conservation remain unverified; no group is certified complete.',
            'scientific_status':'INCONCLUSIVE','physical_unit_status':'INCONCLUSIVE'}

if __name__=='__main__': print(json.dumps(run(),indent=2,sort_keys=True))
