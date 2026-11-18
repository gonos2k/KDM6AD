import copy
import hashlib
import importlib.util
from pathlib import Path
import unittest

import selector_manifest_spec_v1 as m


class SelectorProposalTests(unittest.TestCase):
    def test_budget_and_phase_are_predeclared(self):
        p = m.proposed_manifest()
        self.assertEqual(p['budget']['forwards'], 33)
        self.assertEqual((p['budget']['graph_primal'], p['budget']['intermediate_jvp'], p['budget']['intermediate_vjp']), (9, 18, 9))
        self.assertEqual(len(p['selectors']), 3)
        self.assertEqual(p['selectors']['a7_main_selected.qr_state']['one_step_call'], 0)
        self.assertEqual(p['selectors']['nc_snap1.nc_before']['one_step_call'], 1)
        self.assertEqual(p['eligibility'], 'NOT_ELIGIBLE')

    def test_full_identity_unique_and_inconclusive(self):
        call = {'input_id': 'baseline', 'mode': 'center_joint_graph', 'runtime_call': 3}
        for name, spec in m.SELECTORS.items():
            row = {**spec, **m.LAYER, **call, 'record_kind': 'value'}
            with self.subTest(name=name):
                self.assertEqual(m.resolve([row], name, call)['status'], 'SPEC_ONLY')
                self.assertEqual(m.resolve([], name, call)['status'], 'INCONCLUSIVE')
                self.assertEqual(m.resolve([row, copy.deepcopy(row)], name, call)['status'], 'INCONCLUSIVE')
                for key in ('one_step_call', 'outer_loop', 'substep_n', 'event_ordinal', 'k_zero', 'native_level_bottom_first', 'runtime_call'):
                    bad = dict(row)
                    bad[key] += 1
                    self.assertEqual(m.resolve([bad], name, call)['status'], 'INCONCLUSIVE')
                bad = dict(row)
                bad['mode'] = 'capture_off_value'
                self.assertEqual(m.resolve([bad], name, call)['status'], 'INCONCLUSIVE')

    def test_pinned_source_contains_requested_nodes(self):
        layers = Path(__file__).resolve().parent.parent / 'producer_source_batch6_layers'
        self.assertEqual(hashlib.sha256((layers / 'a7_ledger_snapshot.json').read_bytes()).hexdigest(), m.SOURCE_SNAPSHOT_SHA256)
        spec = importlib.util.spec_from_file_location('selector_test_layers', layers / 'replay.py')
        replay = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(replay)
        with replay.reconstructed_tree() as (root, _):
            coordinator = (root / 'src/coordinator.cpp').read_text()
            capture = (root / 'src/batch5_capture.cpp').read_text()
            self.assertIn('batch5::full("nc_snap1", "nc_before", nc_orig1, false)', coordinator)
            self.assertIn('batch5::full("a5_satadj", "qc_final", qc_final, false)', coordinator)
            self.assertIn('batch5::full("a7_main_selected", "qr_state", adv_state.qr, true)', coordinator)
            self.assertIn('auto storage_k=top_first?k:K-1-k;', capture)
            self.assertIn('ctx.one_step_call=++ctx.observed_one_steps;', capture)

    def test_no_boolean_in_integer_identity(self):
        call = {'input_id': 'baseline', 'mode': 'center_joint_graph', 'runtime_call': 1}
        row = {**m.SELECTORS['nc_snap1.nc_before'], **m.LAYER, **call, 'record_kind': 'value'}
        row['one_step_call'] = True
        self.assertEqual(m.resolve([row], 'nc_snap1.nc_before', call)['status'], 'INCONCLUSIVE')


if __name__ == '__main__':
    unittest.main()
