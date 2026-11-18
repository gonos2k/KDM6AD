import copy
import importlib.util
from pathlib import Path
import unittest
from unittest import mock
p=Path(__file__).with_name('replay.py');spec=importlib.util.spec_from_file_location('host_f64_replay',p);r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.br,cls.rr,cls.cr,cls.base,cls.bound,cls.interior=r.assets()
        cls.mod,cls.selected=r.parent();cls.by=r.check_boundary(cls.bound)
    def test_complete(self): self.assertEqual(r.replay(),r.read(r.HERE/'results.json'))
    def test_trace_mutations(self):
        for kind in ('nonfinite','arithmetic','mask','output'):
            d=copy.deepcopy(self.bound);e=d['events'][0]
            if kind=='nonfinite':e['output_words'][0]='7ff8000000000000'
            if kind=='arithmetic':e['trace']['sw_percent']['raw_hex']='3ff0000000000000'
            if kind=='mask':e['trace']['sw_positive']['raw_hex']='0'
            if kind=='output':e['output_words'][8*39+15]='0000000000000000'
            with self.subTest(kind=kind),self.assertRaises(ValueError):r.check_boundary(d)
    def test_schedule_and_boundary_mutation(self):
        d=copy.deepcopy(self.bound);d['events'][0],d['events'][1]=d['events'][1],d['events'][0]
        with self.assertRaisesRegex(ValueError,'schedule'):r.check_schedule(d,self.by,self.base)
        d=copy.deepcopy(self.bound);d['boundaries'][0]['lower_word']='4074005089907cc5'
        with self.assertRaises(ValueError):r.check_boundary(d)
    def test_full_captured_mask_stability(self):
        by=copy.deepcopy(self.by)
        word=self.bound['centers'][0]['probes'][0]['word']
        item=by[word]['trace']['cloud_complete_evap']
        item['raw_hex']='1' if item['raw_hex']=='0' else '0'
        with self.assertRaisesRegex(ValueError,'sampled selected masks'):
            r.check_schedule(self.bound,by,self.base)

    def test_interior_mutations(self):
        for kind in ('jvp_nan','denominator','fd_output','mask'):
            d=copy.deepcopy(self.interior);c=d['centers'][1]
            if kind=='jvp_nan':c['graph']['jvp_words'][0]='7ff0000000000000'
            if kind=='denominator':c['differences'][2]['denominator']=1.
            if kind=='fd_output':c['differences'][2]['upper']['output_words'][0]='0000000000000000'
            if kind=='mask':c['differences'][2]['upper_masks']['sw_positive']['raw_hex']='0'
            with self.subTest(kind=kind),self.assertRaises(ValueError):r.check_interior(d,self.bound,self.by)
    def test_fd_step_inventory_rejects_repeated_smallest(self):
        d=copy.deepcopy(self.interior)
        d['centers'][1]['differences']=[copy.deepcopy(d['centers'][1]['differences'][2]) for _ in range(3)]
        with self.assertRaisesRegex(ValueError,'FD steps'):
            r.check_interior(d,self.bound,self.by)
    def test_operator_ignores_live_coordinator(self):
        original=Path.read_text
        def guarded(path,*args,**kwargs):
            if str(path).endswith('libtorch/src/coordinator.cpp'):
                raise AssertionError('live source must not be read')
            return original(path,*args,**kwargs)
        with mock.patch.object(Path,'read_text',guarded): r.check_operator()

    def test_archive_receipt_mutation(self):
        d=copy.deepcopy(self.rr);d['independent_parity_calls'][0]['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'archive member SHA'):r.check_zip(d,self.cr,self.by)

if __name__=='__main__':unittest.main()
