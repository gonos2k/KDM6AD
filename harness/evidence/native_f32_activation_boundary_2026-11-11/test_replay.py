import copy
import importlib.util
import json
import math
import shutil
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('f32_replay', Path(__file__).with_name('replay.py'))
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state, cls.forcing = replay.parent_words()

    def call(self):
        return dict(schema='kdm6.native_f32_activation_probe_call.v1', axis='baseline',
                    override_word='', rc=0, value_only=1, handle_null=True,
                    shape=[1, 39, 1], dt_s=20, xland=2, ncmin_land=10, ncmin_sea=10,
                    source_state_f32_words=self.state.copy(), source_forcing_f32_words=self.forcing.copy(),
                    state_output_f32_words=[['00000000'] * 39 for _ in range(12)],
                    precip_increment_f32_words=['00000000'] * 3, rhog_output_f32_words=['00000000'] * 39)

    def test_full_replay_and_saved_contract(self):
        actual = replay.replay()
        saved = json.loads((replay.HERE / 'results.json').read_text())
        self.assertEqual(actual, saved)
        self.assertEqual(actual['sweep']['events'], 36)
        self.assertEqual(actual['terminal']['calls'], 12)
        self.assertEqual(actual['scientific_status'], 'INCONCLUSIVE')
        self.assertEqual(actual['physical_unit_status'], 'INCONCLUSIVE')

    def test_inputs_and_lattice(self):
        call = self.call()
        replay.validate_call(call, self.state, self.forcing)
        call['axis'], call['override_word'] = 'th16', '439ff7a3'
        call['source_state_f32_words'][15] = '439ff7a3'
        replay.validate_call(call, self.state, self.forcing, 'th16', '439ff7a3')
        call['source_state_f32_words'][16] = '439ff7a3'
        with self.assertRaises(ValueError):
            replay.validate_call(call, self.state, self.forcing, 'th16', '439ff7a3')

    def test_rejects_input_control_and_word_mutations(self):
        for mutation in ('state', 'forcing', 'control', 'word', 'nan', 'inf'):
            call = self.call()
            if mutation == 'state': call['source_state_f32_words'][0] = '00000000'
            if mutation == 'forcing': call['source_forcing_f32_words'][0] = '00000000'
            if mutation == 'control': call['dt_s'] = 21
            if mutation == 'word': call['rhog_output_f32_words'][0] = '0'
            if mutation == 'nan': call['state_output_f32_words'][0][0] = '7fc00000'
            if mutation == 'inf': call['precip_increment_f32_words'][0] = '7f800000'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                replay.validate_call(call, self.state, self.forcing)

    def test_baseline_recomputes_parity(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            names = ('installed_baseline.json', 'private_baseline_capture_off.json', 'private_baseline_capture_on.json')
            call = self.call()
            for name in names: (directory / name).write_text(json.dumps(call))
            self.assertEqual(replay.baseline(directory)['baseline_arrays_equal']['state_output_f32_words'], 468)
            altered = copy.deepcopy(call)
            altered['state_output_f32_words'][11][38] = '00000001'
            (directory / names[2]).write_text(json.dumps(altered))
            with self.assertRaisesRegex(ValueError, 'baseline parity'):
                replay.baseline(directory)

    def test_sweep_mutations(self):
        path = replay.HERE / 'raw/sweep/sweep.json'
        if not path.exists():
            self.skipTest('archived sweep not packaged')
        data = json.loads(path.read_bytes())
        self.assertEqual(replay.validate_sweep(data)['boundaries'], 4)
        for mutation in ('nan', 'infinite_trace', 'wrong_boundary'):
            altered = copy.deepcopy(data)
            if mutation == 'nan': altered['events'][0]['rhog_output_f32_words'][0] = '7fc00000'
            if mutation == 'infinite_trace': altered['events'][0]['trace']['sw_percent']['raw_hex'] = '7f800000'
            if mutation == 'wrong_boundary': altered['boundaries'][0]['upper_predicate'] = altered['boundaries'][0]['lower_predicate']
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                replay.validate_sweep(altered)

    def test_source_order_f32_mutations(self):
        path = replay.HERE / 'raw/sweep/sweep.json'
        data = json.loads(path.read_bytes())
        for field in ('sw_ratio', 'ncact_preclamp_fma'):
            altered = copy.deepcopy(data)
            item = altered['events'][0]['trace'][field]
            item['raw_hex'] = f"{int(item['raw_hex'], 16) + 1:08x}"
            with self.subTest(field=field), self.assertRaisesRegex(ValueError,
                                                                     'source-order f32: ' + field):
                replay.validate_sweep(altered)

    def test_pow_diagnostic_rejects_runtime_expected_plus_five_ulps(self):
        data = json.loads((replay.HERE / 'raw/sweep/sweep.json').read_bytes())
        trace = data['events'][0]['trace']
        ratio = replay.as_f32(trace['sw_ratio']['raw_hex'])
        expected = replay.round_f32(math.pow(
            max(ratio, replay.round_f32(1.0e-15)), replay.round_f32(0.6)))
        trace['activation_fraction_pow']['raw_hex'] = f"{int(replay.f32_word(expected), 16) + 5:08x}"
        with self.assertRaisesRegex(ValueError, 'independent safe_pow f32 within 4 ULP'):
            replay.validate_sweep(data)

    def test_repeated_baseline_input_requires_identical_f32_trace(self):
        data = json.loads((replay.HERE / 'raw/sweep/sweep.json').read_bytes())
        state, _ = replay.parent_words()
        row = next(e for e in data['events']
                   if e['axis'] == 'qv16' and e['word'] == state[39 + 15])
        item = row['trace']['activation_fraction_pow']
        item['raw_hex'] = f"{int(item['raw_hex'], 16) + 1:08x}"
        with self.assertRaisesRegex(ValueError, 'repeated full input observation'):
            replay.validate_sweep(data)

    def test_nonterminal_nc_trace_cannot_drift_from_output(self):
        data = json.loads((replay.HERE / 'raw/sweep/sweep.json').read_bytes())
        row = next(e for e in data['events']
                   if e['axis'] == 'th16' and e['word'] == '439ff9b7')
        row['trace']['nc_final']['raw_hex'] = '3f800000'
        with self.assertRaisesRegex(ValueError, 'source-order f32: nc_final'):
            replay.validate_sweep(data)

    def test_terminal_raw_mutation_fails(self):
        raw = replay.HERE / 'raw/sweep'
        if not (raw / 'terminal_calls/receipt.json').exists():
            self.skipTest('terminal calls not packaged')
        self.assertEqual(replay.terminal_calls()['calls'], 12)
        with tempfile.TemporaryDirectory() as tmp:
            packet = Path(tmp)
            shutil.copytree(raw, packet / 'raw/sweep')
            target = packet / 'raw/sweep/terminal_calls/th16_439ff9f0_installed.json'
            payload = bytearray(target.read_bytes())
            payload[-2] ^= 1
            target.write_bytes(payload)
            with self.assertRaisesRegex(ValueError, 'terminal call SHA'):
                replay.terminal_calls(packet)

    def test_parent_digest_pinned(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'input.bin'
            payload = bytearray(replay.PARENT.read_bytes())
            payload[100] ^= 1
            path.write_bytes(payload)
            with self.assertRaisesRegex(ValueError, 'parent input SHA'):
                replay.parent_words(path)


if __name__ == '__main__':
    unittest.main()
