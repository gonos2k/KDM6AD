import copy,hashlib,importlib.util,json,unittest
from pathlib import Path
p=Path(__file__).with_name('validate_atomic_catalog_v2.py');spec=importlib.util.spec_from_file_location('atomic_v2',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class CatalogV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v1=json.loads((m.HERE/'atomic_catalog_draft.json').read_bytes())
        cls.patch=json.loads((m.HERE/'atomic_catalog_consumer_patch_v2.json').read_bytes())
        cls.v2=m.materialize(cls.patch,cls.v1)
        cls.archive=(m.PARENT/'field_contract_sources.zip').read_bytes()
    def check_mutation(self,d,pattern):
        # Even a replacement catalog whose bytes have a fresh digest must fail the semantic validator.
        hashlib.sha256(json.dumps(d,sort_keys=True).encode()).hexdigest()
        with self.assertRaisesRegex(ValueError,pattern):m.validate(d,self.v1,self.archive)
    def test_pinned_source_use_and_context(self):
        result=m.validate(self.v2,self.v1,self.archive);self.assertEqual((result['verified_source_consumers'],result['context_only_atoms'],result['masks']),(2,189,19))
        atoms={x['atomic_id']:x for x in self.v2['atoms']}
        self.assertEqual(atoms['phase_change_heat.supplement.dep_sum']['consumer']['location']['line'],2496)
        self.assertEqual(atoms['phase_change_heat.supplement.temperature_final']['consumer']['location']['line'],2540)
        self.assertTrue(all(x['consumer'] is None for x in self.v2['proposed_masks']))
    def test_patch_cannot_claim_extra_consumer(self):
        patch=copy.deepcopy(self.patch)
        patch['verified_source_uses']['temperature_latent_terms.site.01']={'kind':'RHS_USE'}
        with self.assertRaisesRegex(ValueError,'patch consumers'):
            m.materialize(patch,self.v1)
    def test_direct_validator_rejects_unsupported_scope_claim(self):
        child=copy.deepcopy(self.v2)
        child['scope']='All fields executed and derivatives validated'
        with self.assertRaisesRegex(ValueError,'pinned v2 object'):
            m.validate(child,self.v1,self.archive)
    def test_rehashed_wrong_context_rejected(self):
        d=copy.deepcopy(self.v2);d['atoms'][0]['context_location']['line']+=1;self.check_mutation(d,'context differs')
    def test_rehashed_parent_and_matching_context_rejected(self):
        parent=copy.deepcopy(self.v1);child=copy.deepcopy(self.v2)
        ident='temperature_latent_terms.site.01'
        old=next(x for x in parent['atoms'] if x['atomic_id']==ident)
        new=next(x for x in child['atoms'] if x['atomic_id']==ident)
        old['consumer']['relation']='fabricated context'
        new['context_relation']='fabricated context'
        with self.assertRaisesRegex(ValueError,'pinned parent object'):
            m.validate(child,parent,self.archive)
    def test_rehashed_backward_consumer_rejected(self):
        d=copy.deepcopy(self.v2);a=next(x for x in d['atoms'] if x['atomic_id']=='phase_change_heat.supplement.dep_sum');a['consumer']['location']['line']=2474;a['consumer']['location']['anchor']='auto xlf = xls - pre.xl;';self.check_mutation(d,'verified consumer mismatch')
    def test_false_consumer_or_semantic_relabel_rejected(self):
        d=copy.deepcopy(self.v2);a=next(x for x in d['atoms'] if x['consumer_status']=='UNVERIFIED');a['consumer_status']='VERIFIED_SOURCE_USE';a['consumer']={'location':a['context_location']};self.check_mutation(d,'unsupported consumer')
    def test_blocked_status_and_parent_preserved(self):
        d=copy.deepcopy(self.v2);d['atoms'][0]['record_availability']['live_tangent']='AVAILABLE';self.check_mutation(d,'v1 atom changed')
        d=copy.deepcopy(self.v2);d['groups'][0]['status']='READY';self.check_mutation(d,'v1 preserved')
if __name__=='__main__':unittest.main()
