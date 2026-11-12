import copy
import gzip
import json
import unittest
import f32_f64_diff as d

class ComparisonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.selected=json.loads((d.F32/'selected_full.json').read_text())
        cls.replay=json.loads((d.F32/'b1_replay.json').read_text())
        with gzip.open(d.F64,'rt') as f: cls.fp64=json.load(f)
        cls.result=d.analyze(cls.selected,cls.replay,cls.fp64,d.sha(d.F32/'selected_full.json'))
    def test_classification(self):
        s=self.result['summary']
        self.assertEqual((s['word_count'],s['rounded_equal_count'],s['rounded_mismatch_count']),(468,367,101))
        self.assertEqual((s['selected_activation_level_16'],s['adjacent_levels_15_17'],s['outside_levels_15_17']),(6,7,88))
        self.assertEqual(sum(s['mismatches_by_field'].values()),101)
        self.assertEqual(sum(s['mismatches_by_native_level'].values()),101)
        self.assertTrue(all(x['rounded_ulp_distance']>0 for x in self.result['mismatches']))
    def test_saved_result_matches_recomputed(self):
        with gzip.open(d.Path(d.__file__).with_suffix('.json.gz'),'rt') as f: saved=json.load(f)
        actual=copy.deepcopy(self.result)
        actual['source_files']={'selected_full_sha256':d.sha(d.F32/'selected_full.json'),'b1_replay_sha256':d.sha(d.F32/'b1_replay.json'),'baseline_probe_gzip_sha256':d.sha(d.F64)}
        self.assertEqual(saved,actual)
    def test_lineage_tamper_rejected(self):
        f=copy.deepcopy(self.fp64);f['source']['input_widened_f64_words'][0]='0000000000000000'
        with self.assertRaisesRegex(ValueError,'widened input'): d.analyze(self.selected,self.replay,f,d.SELECTED_SHA)
        r=copy.deepcopy(self.replay);r['actual_output_words_hex']['th'][0]='00000000'
        with self.assertRaisesRegex(ValueError,'baseline outputs'): d.analyze(self.selected,r,self.fp64,d.SELECTED_SHA)
    def test_ulp_order(self):
        self.assertEqual(d.ordered32('3f800001')-d.ordered32('3f800000'),1)
        self.assertEqual(d.ordered32('bf800000')-d.ordered32('bf800001'),1)
        self.assertEqual(d.ordered32('00000000')-d.ordered32('80000000'),1)

if __name__=='__main__':unittest.main()
