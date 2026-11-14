import copy,importlib.util,json,unittest
from pathlib import Path
p=Path(__file__).with_name('hook_coverage.py');spec=importlib.util.spec_from_file_location('hook_coverage',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class HookCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parent=json.loads((m.HERE/'atomic_catalog_draft.json').read_bytes());patch=json.loads((m.HERE/'atomic_catalog_consumer_patch_v2.json').read_bytes())
        cls.catalog=m.catalog_v2.materialize(patch,parent)
        with m.source_replay.reconstructed_tree() as (root,_):
            cls.sources={name:(root/'src'/name).read_text() for name in m.SOURCE_SHA}
    def test_pinned_source_summary_and_blockers(self):
        result=m.load();summary=m.summary(result)
        self.assertEqual(summary,json.loads((m.HERE/'hook_coverage_summary.json').read_bytes()))
        self.assertEqual((result['source_hook_callsites'],result['literal_stage_fields'],result['expanded_stage_fields']),(298,280,331))
        self.assertEqual((len(summary['source_hook_match_atom_ids']),len(summary['unmapped_atom_ids']),len(summary['proposed_mask_ids']),len(summary['applied_transport_unresolved_ids'])),(107,84,19,21))
        self.assertTrue(all(g['status']=='BLOCKED_NOT_CERTIFIED' for g in result['groups']))
        self.assertTrue(all(x['status']=='PARTIAL_SOURCE_FRAGMENTS_RUNTIME_UNVERIFIED' for x in result['proposed_masks']))
    def test_transport_candidates_and_fnresult_duplicates(self):
        r=m.analyze(self.catalog,self.sources);self.assertEqual(len(r['hook_inventory']['fnresult.rain_increment']),2)
        for species in ('qr','nr','qs','qg','brs','qi','ni'):
            for kind in ('realized_departure','realized_arrival','actual_bottom_export'):
                self.assertIn(f'transport_{species}.unresolved.{kind}',{a['atomic_id'] for a in r['atoms_without_direct_proven_hook']})
            a=next(x for x in r['atom_source_hook_matches'] if x['atomic_id']==f'transport_{species}.site.06')
            self.assertEqual(a['mapping_kind'],'SQUEEZED_COLUMN_VIEW_OF_GATE');self.assertIn('.squeeze(1)',a['hook'][0]['expression_tail'])
    def test_rehashed_wrong_hook_tensor_rejected(self):
        sources=dict(self.sources);old='batch5::full("rate_cap", "raw", ncact_raw, false);';new='batch5::full("rate_cap", "raw", batch5_rate_cap, false);'
        self.assertIn(old,sources['coordinator.cpp']);sources['coordinator.cpp']=sources['coordinator.cpp'].replace(old,new,1)
        m.sha(sources['coordinator.cpp'].encode())
        with self.assertRaisesRegex(ValueError,'hook tensor expression differs'):m.analyze(self.catalog,sources)
    def test_hook_in_disabled_macro_branch_rejected(self):
        sources=dict(self.sources);s=sources['runtime.cpp'];at=s.index('batch5::full("entry", "th"');guard=s.rfind('#ifdef KDM6_BATCH5_RESEARCH_CAPTURE',0,at)
        sources['runtime.cpp']=s[:guard]+s[guard:].replace('#ifdef KDM6_BATCH5_RESEARCH_CAPTURE','#ifndef KDM6_BATCH5_RESEARCH_CAPTURE',1)
        with self.assertRaisesRegex(ValueError,'macro-enabled guard'):m.analyze(self.catalog,sources)
    def test_removed_hook_and_mask_rejected(self):
        sources=dict(self.sources);sources['satadj.cpp']=sources['satadj.cpp'].replace('batch5::full("satadj_inner", "work1", work1, top);','',1)
        with self.assertRaisesRegex(ValueError,'hook callsite inventory'):m.analyze(self.catalog,sources)
        catalog=copy.deepcopy(self.catalog);catalog['proposed_masks'][0]['atomic_id']='mask.fake'
        with self.assertRaisesRegex(ValueError,'mask mapping inventory'):m.analyze(catalog,self.sources)

if __name__=='__main__':unittest.main()
