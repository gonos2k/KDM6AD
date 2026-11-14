import copy
import hashlib
import importlib.util
import json
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import MagicMock, patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('condition_receipt_bridge_v3', HERE / 'condition_receipt_bridge_v3.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def row(name, sequence, role=1, cause=m.NO_CAUSE):
    return {'input_id': name, 'mode': 'capture_on_value', 'family': 'main', 'stage': 's',
            'field': 'f', 'source_hook': 'hook', 'context_epoch': 1, 'runtime_call': sequence,
            'one_step_call': 1, 'outer_loop': 1, 'substep_n': 1, 'event_ordinal': 0,
            'causal_index': cause, 'b_zero': 0, 'k_zero': 0, 'native_level_bottom_first': 39,
            'B': 1, 'K': 39, 'role': role, 'dtype': 1 if role == 1 else 5,
            'scope': 1, 'reason': 0 if role == 1 else 1,
            'raw_hex': '0000000000000000' if role == 1 else None}


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.plan = {'inputs': [], 'calls': []}
        self.receipt = {'build': {'new_instrumented_dso_sha256': 'a' * 64}, 'calls': []}
        self.assets = {}
        self.results = {}
        self.envelope = {'schema': m.SCHEMA, 'status': 'SPEC_ONLY', 'plan_gzip_sha256': m.rs.PLAN_GZ_SHA, 'calls': []}
        for i in range(45):
            ident = f'input{i}'
            words = ['0000000000000000'] * 624
            self.plan['inputs'].append({'id': ident, 'words': words})
            self.plan['calls'].append({'input_id': ident, 'sequence': i + 1, 'mode': 'capture_on_value'})
            item = {'schema': m.ASSET_SCHEMA, 'input_id': ident, 'sequence': i + 1,
                    'mode': 'capture_on_value', 'input_words': words, 'dso_sha256': 'a' * 64,
                    'reader': {'status': 'SPEC_ONLY_BLOCKED', 'graph_metadata_only': False,
                               'records': [row(ident, i + 1), row(ident, i + 1, 5, 0)]}}
            self.add(i, item)

    def add(self, i, item):
        path = f'copy{i}.json'
        ident = f'input{i}'
        sequence = i + 1
        rain = {'raw_hex': '4000000000000000', 'graph_flag': 0}
        output = ['0000000000000000'] * 468
        same = {'schema': 'kdm6.condition_v2_same_call.unverified.v1', 'status': 'SPEC_ONLY_BLOCKED',
                'sequence': sequence, 'input_id': ident, 'mode': 'capture_on_value',
                'input_words': item['input_words'], 'state_output_words': output, 'same_call_rain': rain,
                'claimed_dso_sha256': 'a' * 64, 'dso_identity_status': 'CALLER_SUPPLIED_UNVERIFIED',
                'graph_handle_token': None, 'capture': item['reader']}
        rainrow = {'input_id': ident, 'mode': 'capture_on_value', 'runtime_call': sequence, 'scope': 'column',
                   'stage': 'fnresult', 'field': 'rain_increment', 'record_kind': 'value', 'b_zero': 0,
                   'k_zero': -1, 'native_level_bottom_first': -1, 'B': 1, 'K': -1, 'dtype': 'f64', 'raw_hex': rain['raw_hex']}
        result = {'schema': 'kdm6.future_call_raw.v1', 'sequence': sequence, 'input_id': ident,
                  'mode': 'capture_on_value', 'input_words': item['input_words'], 'state_output_words': output,
                  'claimed_dso_sha256': 'a' * 64, 'dso_identity_status': 'CALLER_SUPPLIED_UNVERIFIED',
                  'return_code': 0, 'handle_nonnull': False, 'handle_null_after': True, 'close_rc': None,
                  'same_call_rain': rain, 'rain_unit_status': 'UNAPPROVED', 'rain_provenance': 'SAME_CALL_CONTEXT_UNVERIFIED',
                  'sidecar_records': [rainrow], 'condition_v2_asset': same,
                  'condition_v2_asset_sha256': hashlib.sha256(m.canonical_bytes(same)).hexdigest()}
        call = {'input_id': ident, 'sequence': sequence, 'mode': 'capture_on_value'}
        packed = m.serialize_same_call(result, call, item['input_words'], 'a' * 64, path)
        self.results[i] = result
        self.assets[path] = packed['bytes']
        output_path = f'output{i}.json'
        payload = {'input_words': item['input_words'], 'state_output_words': output, 'dso_sha256': 'a' * 64}
        data = m.canonical_bytes(payload)
        self.assets[output_path] = data
        receipt_call = {**call, 'status': 'completed', 'output_asset': {'path': output_path, 'sha256': hashlib.sha256(data).hexdigest()}}
        if i < len(self.receipt['calls']):
            self.receipt['calls'][i] = receipt_call
            self.envelope['calls'][i] = packed['entry']
        else:
            self.receipt['calls'].append(receipt_call)
            self.envelope['calls'].append(packed['entry'])

    def join(self):
        with patch.object(m.rs, 'validate'), patch.object(m.rs, 'load_plan', return_value=(self.plan, {})):
            return m.join(self.receipt, self.assets, self.envelope)

    def test_join_is_ordered_and_never_eligible(self):
        result = self.join()
        self.assertEqual(result['eligibility'], 'NOT_ELIGIBLE')
        self.assertEqual(len(result['calls']), 45)
        self.assertEqual(result['calls'][0]['records'][1]['causal_index'], 0)
        self.assertEqual(result['status'], 'SPEC_ONLY')

    def test_identity_order_and_input_mutations_rejected(self):
        self.envelope['calls'][0], self.envelope['calls'][1] = self.envelope['calls'][1], self.envelope['calls'][0]
        with self.assertRaises(ValueError):
            self.join()
        self.envelope['calls'].reverse()
        self.setUp()
        item = json.loads(self.assets['copy0.json'])
        item['input_words'][0] = '3ff0000000000000'
        self.add(0, item)
        with self.assertRaisesRegex(ValueError, 'input words'):
            self.join()

    def test_causal_mutations_rejected(self):
        for mutation in ('forward', 'truth', 'context'):
            self.setUp()
            item = json.loads(self.assets['copy0.json'])
            rows = item['reader']['records']
            if mutation == 'forward':
                rows[1]['causal_index'] = 1
            elif mutation == 'truth':
                rows[0]['raw_hex'] = '0000000000000001'
            else:
                rows[1]['k_zero'] = 1
                rows[1]['native_level_bottom_first'] = 38
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.add(0, item)

    def test_hypothetical_projection_preserves_order_and_is_vetoed(self):
        joined = self.join()
        selected = joined['calls'][0]
        consumer = SimpleNamespace(SCHEMA='draft', add_conditions=MagicMock(return_value={'hypothetical': True}))
        fake_spec = SimpleNamespace(loader=SimpleNamespace(exec_module=lambda module: None))
        bindings = {'center': 'input0', 'samples': {}}
        site = {'id': 'x', 'stage': 's', 'field': 'f', 'source_hook': 'hook',
                'family': 'main', 'scope': 'layer', 'role': 'consumed_bool', 'dtype': 'bool'}
        with patch.object(m, 'join', return_value=joined), \
             patch('importlib.util.spec_from_file_location', return_value=fake_spec), \
             patch('importlib.util.module_from_spec', return_value=consumer):
            with self.assertRaisesRegex(ValueError, 'UNRESOLVED: independent per-call provenance'):
                m.project_gate_input(self.receipt, self.assets, self.envelope, {}, bindings,
                                     {'sites': [site]}, {'input0': []})
        captured = consumer.add_conditions.call_args.args[2]['input0']['capture']['records']
        self.assertEqual(captured[1]['causal_index'], 0)
        self.assertEqual(captured[0]['raw'], False)
        self.assertEqual(selected['records'][1]['causal_index'], 0)
        consumer.add_conditions.side_effect = ValueError('UNRESOLVED: v2 call-to-payload provenance not independently verified')
        with patch.object(m, 'join', return_value=joined), \
             patch('importlib.util.spec_from_file_location', return_value=fake_spec), \
             patch('importlib.util.module_from_spec', return_value=consumer):
            with self.assertRaisesRegex(ValueError, 'UNRESOLVED: v2 call-to-payload'):
                m.project_gate_input(self.receipt, self.assets, self.envelope, {}, bindings,
                                     {'sites': [site]}, {'input0': []})

    def test_mixed_phases_join_but_projection_is_unsupported(self):
        item = json.loads(self.assets['copy0.json'])
        extra = row('input0', 1)
        extra['one_step_call'] = 0
        item['reader']['records'].insert(0, extra)
        item['reader']['records'][2]['causal_index'] = 1
        self.add(0, item)
        joined = self.join()
        self.assertEqual([r['one_step_call'] for r in joined['calls'][0]['records']], [0, 1, 1])
        self.assertEqual(joined['calls'][0]['records'][2]['causal_index'], 1)
        bindings = {'center': 'input0', 'samples': {}}
        with patch.object(m, 'join', return_value=joined):
            with self.assertRaisesRegex(ValueError, 'UNSUPPORTED: mixed one_step_call'):
                m.project_gate_input(self.receipt, self.assets, self.envelope, {}, bindings,
                                     {'sites': []}, {'input0': []})

    def test_fake_executor_same_call_serializes_and_joins(self):
        executor_spec = importlib.util.spec_from_file_location('batch5_fake_test_bridge', HERE / 'test_batch5_abi_core.py')
        fake = importlib.util.module_from_spec(executor_spec)
        executor_spec.loader.exec_module(fake)
        fixture = fake.PreflightTest()
        fixture.setUpClass()
        guard = fixture.guard()
        guard.check(fixture.plan['calls'][0], fixture.words_for(fixture.plan['calls'][0]))
        guard.complete()
        call = fixture.plan['calls'][1]
        result = fake.abi_core._execute_bound(fake.FakeV2(), call, fixture.center['words'], {}, fixture.nom,
                                               fixture.vjp, 'a' * 64, sequence_guard=guard,
                                               require_condition_v2=True)
        packed = m.serialize_same_call(result, call, fixture.center['words'], 'a' * 64, 'actual.json')
        self.assets['actual.json'] = packed['bytes']
        self.envelope['calls'][0] = packed['entry']
        self.plan['calls'][0] = call
        self.plan['inputs'][0] = {'id': call['input_id'], 'words': fixture.center['words']}
        output_payload = {'input_words': result['input_words'], 'state_output_words': result['state_output_words'],
                          'dso_sha256': 'a' * 64}
        output_bytes = m.canonical_bytes(output_payload)
        self.assets['actual-output.json'] = output_bytes
        self.receipt['calls'][0] = {**call, 'status': 'completed', 'output_asset': {
            'path': 'actual-output.json', 'sha256': hashlib.sha256(output_bytes).hexdigest()}}
        joined = self.join()
        self.assertEqual(joined['eligibility'], 'NOT_ELIGIBLE')
        self.assertEqual(joined['calls'][0]['records'], result['condition_v2_asset']['capture']['records'])
        self.assertEqual(len(result['input_words']), 624)
        self.assertEqual(len(result['state_output_words']), 468)
        self.assertEqual(result['same_call_rain']['raw_hex'], '4000000000000000')
        borrowed = copy.deepcopy(result)
        borrowed['same_call_rain']['raw_hex'] = '4008000000000000'
        with self.assertRaises(ValueError):
            m.serialize_same_call(borrowed, call, fixture.center['words'], 'a' * 64, 'actual.json')
        swapped = json.loads(packed['bytes'])
        swapped['reader'] = json.loads(self.assets['copy1.json'])['reader']
        raw = m.canonical_bytes(swapped)
        self.assets['actual.json'] = raw
        self.envelope['calls'][0]['asset']['sha256'] = hashlib.sha256(raw).hexdigest()
        with self.assertRaises(ValueError):
            self.join()

    def test_executor_and_nested_copy_mismatches_rejected(self):
        call = self.plan['calls'][0]
        for field in ('input_words', 'state_output_words', 'same_call_rain', 'reader', 'dso'):
            result = copy.deepcopy(self.results[0])
            if field == 'input_words':
                result['input_words'][0] = '3ff0000000000000'
            elif field == 'state_output_words':
                result['state_output_words'][0] = '3ff0000000000000'
            elif field == 'same_call_rain':
                result['same_call_rain']['raw_hex'] = '4008000000000000'
            elif field == 'reader':
                result['condition_v2_asset']['capture']['records'][0]['raw_hex'] = '0000000000000001'
            else:
                result['claimed_dso_sha256'] = 'b' * 64
            with self.subTest(field=field), self.assertRaises(ValueError):
                m.serialize_same_call(result, call, self.plan['inputs'][0]['words'], 'a' * 64, 'copy0.json')

    def test_rehashed_outer_raw_swap_and_borrowed_rain_rejected(self):
        for mutation in ('reader', 'rain'):
            self.setUp()
            item = json.loads(self.assets['copy0.json'])
            if mutation == 'reader':
                item['reader'] = json.loads(self.assets['copy1.json'])['reader']
            else:
                item['same_call_rain']['raw_hex'] = '4008000000000000'
                item['same_call_asset']['same_call_rain']['raw_hex'] = '4008000000000000'
                item['same_call_asset_sha256'] = hashlib.sha256(m.canonical_bytes(item['same_call_asset'])).hexdigest()
            raw = m.canonical_bytes(item)
            self.assets['copy0.json'] = raw
            self.envelope['calls'][0]['asset']['sha256'] = hashlib.sha256(raw).hexdigest()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.join()

    def test_asset_hash_and_missing_inventory_rejected(self):
        original = copy.deepcopy(self.envelope)
        self.assets['copy0.json'] += b' '
        with self.assertRaises(ValueError):
            self.join()
        self.setUp()
        self.envelope['calls'].pop()
        with self.assertRaises(ValueError):
            self.join()
        self.assertEqual(len(original['calls']), 45)


if __name__ == '__main__':
    unittest.main()
