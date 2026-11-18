import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

import replay


class ColumnTest(unittest.TestCase):
    def setUp(self):
        self.selected = replay.load_packet()
        raw = replay.HERE / 'raw'
        self.b1 = json.loads((raw / 'b1_replay.json').read_text())
        self.activation = json.loads((raw / 'activation_summary.json').read_text())
        self.th_stop = json.loads((raw / 'th_search_stop.json').read_text())
        self.calls = json.loads((raw / 'activation_calls.json').read_text())
        self.parent = json.loads((replay.HERE.parent / 'native_host_tile_abi_2026-11-11/raw/selected_column.json').read_text())

    def test_public_packet(self):
        actual = replay.validate_column(self.selected, self.b1, self.parent)
        replay.validate_activation(self.activation, actual)
        self.assertEqual(replay.validate_th_search_stop(self.th_stop, self.selected, self.activation), 13)

    def test_th_stop_rejects_missing_or_changed_probe(self):
        for change, message in (
            (lambda d: d['samples'].pop(11), 'sample inventory'),
            (lambda d: d['samples'][-1]['trace']['ncact_raw_eq_nccn_rate_cap'].__setitem__('raw_hex', '1'), 'comparison mask'),
            (lambda d: d['samples'][-1]['trace']['ncact_raw'].__setitem__('raw_hex', '4a989680'), 'source-order'),
            (lambda d: d['stop'].__setitem__('boundaries_recorded', 1), 'stop decision'),
        ):
            data = copy.deepcopy(self.th_stop)
            change(data)
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                replay.validate_th_search_stop(data, self.selected, self.activation)

    def test_saved_public_summary_contract(self):
        actual = replay.public_summary()
        saved = json.loads((replay.HERE / 'results.json').read_text())
        self.assertEqual(actual, saved)
        self.assertEqual(actual['scientific_status'], 'INCONCLUSIVE')
        self.assertEqual(actual['physical_unit_status'], 'INCONCLUSIVE')

    def test_b1_changed_word_and_field_order(self):
        b1 = copy.deepcopy(self.b1)
        b1['actual_output_words_hex']['qv'][2] = '00000000'
        with self.assertRaisesRegex(ValueError, 'output mismatch'):
            replay.validate_column(self.selected, b1, self.parent)
        selected = copy.deepcopy(self.selected)
        selected['input_words_hex']['th'], selected['input_words_hex']['qv'] = selected['input_words_hex']['qv'], selected['input_words_hex']['th']
        with self.assertRaisesRegex(ValueError, 'parent input'):
            replay.validate_column(selected, self.b1, self.parent)

    def test_each_activation_call_and_input_are_checked(self):
        actual = replay.validate_column(self.selected, self.b1, self.parent)
        for label in ('installed', 'capture_off', 'capture_on'):
            calls = copy.deepcopy(self.calls)
            calls['calls'][label]['output_words_hex']['th'][0] = '00000000'
            with self.subTest(label=label), self.assertRaisesRegex(ValueError, 'activation call output mismatch'):
                replay.validate_activation_calls(calls, self.selected, actual, self.activation)
        calls = copy.deepcopy(self.calls)
        calls['input_words_hex']['qv'][1] = '00000000'
        with self.assertRaisesRegex(ValueError, 'activation input mismatch'):
            replay.validate_activation_calls(calls, self.selected, actual, self.activation)

    def test_activation_operand_and_gate_mutation(self):
        actual = replay.validate_column(self.selected, self.b1, self.parent)
        for name, changed in [('sw_percent', '3f528b39'), ('sw_positive', '0'), ('nc_final', '00000000')]:
            trace = copy.deepcopy(self.activation)
            trace['trace'][name]['raw_hex'] = changed
            with self.subTest(name=name), self.assertRaises(ValueError):
                replay.validate_activation(trace, actual)

    def test_nonfinite_and_bad_time(self):
        selected = copy.deepcopy(self.selected)
        selected['input_words_hex']['qv'][1] = '7f800000'
        with self.assertRaisesRegex(ValueError, 'input qv words'):
            replay.validate_column(selected, self.b1, self.parent)
        selected = copy.deepcopy(self.selected)
        selected['model_start'] = '2025-07-19_00:00:40'
        with self.assertRaisesRegex(ValueError, 'case and time'):
            replay.validate_column(selected, self.b1, self.parent)

    def test_asset_tampering(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'packet'
            shutil.copytree(replay.HERE, root)
            (root / 'raw/selected_full.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'asset SHA-256'):
                replay.load_packet(root)

    @unittest.skipUnless(os.environ.get('PRIVATE_TILE_PATH') and os.environ.get('PRIVATE_DSO_PATH'),
                         'PRIVATE_TILE_PATH and PRIVATE_DSO_PATH required for private full-tile check')
    def test_private_tile_and_dso(self):
        replay.validate_private(os.environ['PRIVATE_TILE_PATH'], os.environ['PRIVATE_DSO_PATH'], self.selected)


if __name__ == '__main__':
    unittest.main()
