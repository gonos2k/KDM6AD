import copy
import importlib.util
import gzip
import json
from pathlib import Path
import unittest

p=Path(__file__).with_name('full_output_fd.py')
spec=importlib.util.spec_from_file_location('full_output_fd',p)
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

class FullOutputFDTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.data=r.load_parent()
    def test_saved_output(self):
        result=r.derive(self.data)
        self.assertEqual(result,json.loads(gzip.decompress(p.with_name('full_output_fd.json.gz').read_bytes())))
        self.assertEqual(r.encode(result),p.with_name('full_output_fd.json.gz').read_bytes())
        self.assertEqual(len(result['rows']),2*3*468)
        self.assertTrue(all(sum(s['signal_counts'].values())==468 for s in result['summaries']))
    def test_declared_field_scales(self):
        self.assertEqual(r.validate_scales(), (1., 1e-3, 1e-3, 1e-3, 1e-3, 1e-3, 1e-3, 1e8, 1e8, 1e6, 1e6, 1e-6))
        result=r.derive(self.data)
        self.assertEqual(result['field_scale_source_sha256'],r.SCALE_SOURCE_SHA)
        for row in result['rows']:
            self.assertEqual(row['field_scale'],result['field_scales'][row['field']])
            self.assertEqual(row['field_scaled_absolute_derivative_error'],row['absolute_derivative_error']/row['field_scale'])
            self.assertEqual(row['field_scaled_absolute_output_residual'],abs(row['output_residual'])/row['field_scale'])

    def test_denominator_mutation_rejected(self):
        d=copy.deepcopy(self.data);d['centers'][0]['differences'][0]['denominator']=1.
        with self.assertRaisesRegex(ValueError,'denominator'):r.derive(d)
    def test_nonfinite_output_rejected(self):
        d=copy.deepcopy(self.data);d['centers'][0]['differences'][0]['upper']['output_words'][0]='7ff8000000000000'
        with self.assertRaises(ValueError):r.derive(d)
    def test_zero_and_unresolved_are_separate(self):
        rows=r.derive(self.data)['rows']
        self.assertTrue(any(x['signal']=='equal_words_zero_jvp' for x in rows))
        index=next(x['packed_index'] for x in rows if x['center']=='lower' and x['h_requested']==0.001 and x['signal']=='equal_words_zero_jvp')
        altered=copy.deepcopy(self.data)
        altered['centers'][0]['graph']['jvp_words'][index]=r.w(1.0)
        synthetic=r.derive(altered)['rows']
        self.assertTrue(any(x['signal']=='equal_words_nonzero_jvp' for x in synthetic))
        self.assertTrue(any(x['signal']=='distinct_words' for x in rows))

if __name__=='__main__':unittest.main()
