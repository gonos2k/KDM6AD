import copy
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest import mock

path=Path(__file__).with_name('replay.py')
spec=importlib.util.spec_from_file_location('boundary_replay',path)
r=importlib.util.module_from_spec(spec); spec.loader.exec_module(r)


class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent=r.parent_module()
        cls.selected=cls.parent.load_packet()
        cls.sweep=r.read_sweep()
        cls.terminals=r.read(r.HERE/'raw/terminal_calls.json')
        cls.events=r.validate_sweep(cls.sweep,cls.selected,cls.parent)

    def test_complete(self):
        with mock.patch.dict(os.environ, {k:v for k,v in os.environ.items() if not k.startswith('PRIVATE_')}, clear=True):
            summary=r.replay()
        summary['private_reexecution']='SKIPPED'
        self.assertEqual(summary, r.read(r.HERE/'results.json'))

    @unittest.skipUnless(all(os.environ.get(k) for k in ('PRIVATE_F32_RUNNER','PRIVATE_F32_INPUT','PRIVATE_INSTALLED_DSO','PRIVATE_CAPTURE_DSO')), 'private runner, input and DSOs unavailable')
    def test_private_reexecution(self):
        self.assertEqual(r.private_reexecution(self.parent,self.selected,self.events),'PASSED')

    def test_event_mutations(self):
        for mutation in ('nonfinite','arithmetic','output_link','guard','schedule','boundary'):
            d=copy.deepcopy(self.sweep)
            if mutation=='nonfinite': d['events'][1]['state_output_f32_words'][0][0]='7fc00000'
            if mutation=='arithmetic': d['events'][1]['trace']['sw_percent']['raw_hex']='3f800000'
            if mutation=='output_link': d['events'][1]['state_output_f32_words'][8][15]='00000000'
            if mutation=='guard': d['events'][1]['trace']['cloud_complete_evap']['raw_hex']='1'
            if mutation=='schedule': d['events'][1],d['events'][2]=d['events'][2],d['events'][1]
            if mutation=='boundary': d['boundaries'][0]['lower']='43a00284'
            with self.subTest(mutation=mutation), self.assertRaises((ValueError,KeyError)):
                r.validate_sweep(d,self.selected,self.parent)

    def test_terminal_mutations(self):
        for mutation in ('state','forcing','output','hash','control'):
            d=copy.deepcopy(self.terminals); item=d['calls'][0]; c=item['call']
            if mutation=='state': c['source_state_f32_words'][16]='00000000'
            if mutation=='forcing': c['source_forcing_f32_words'][0]='00000000'
            if mutation=='output': c['rhog_output_f32_words'][0]='00000001'
            if mutation=='hash': item['loader_stderr_sha256']='0'*64
            if mutation=='control': c['dt_s']=21
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                r.validate_terminals(d,self.events,self.selected,self.parent)

    def test_private_paths_fail_closed(self):
        with mock.patch.dict('os.environ', {'PRIVATE_F32_RUNNER':'/nonexistent'}, clear=True):
            with self.assertRaisesRegex(ValueError, 'set all four'):
                r.private_reexecution(self.parent,self.selected,self.events)

    def test_capture_trace_mismatch(self):
        altered=copy.deepcopy(self.events)
        altered['43a00285']['trace']['qv_input']['raw_hex']='3f800000'
        with self.assertRaisesRegex(ValueError,'capture trace mismatch'):
            r.validate_terminals(self.terminals,altered,self.selected,self.parent)


if __name__=='__main__': unittest.main()
