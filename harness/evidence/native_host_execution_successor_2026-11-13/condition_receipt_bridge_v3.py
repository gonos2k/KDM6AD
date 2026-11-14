"""SPEC_ONLY join of serialized v2-reader copies to the pinned prospective plan.

Hashes and caller-supplied mappings establish internal consistency only. They do
not authenticate execution, source coverage, model inputs, or scientific claims.
"""
import copy
import hashlib
import json
import math
import re
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREFLIGHT = HERE.parent / 'native_host_preflight_2026-11-12'
if str(PREFLIGHT) not in sys.path:
    sys.path.insert(0, str(PREFLIGHT))
import receipt_schema as rs  # noqa: E402

if Path(rs.__file__).resolve() != PREFLIGHT / 'receipt_schema.py':
    raise RuntimeError('preflight module identity')

SCHEMA = 'kdm6.condition_receipt_bridge.v3'
ASSET_SCHEMA = 'kdm6.condition_reader_copy.v2'
MAX_ASSET_BYTES = 32 * 1024 * 1024
MAX_RECORDS_PER_CALL = 200_000
MAX_TOTAL_RECORDS = 1_000_000
NO_CAUSE = (1 << 64) - 1
ROW_KEYS = {'input_id', 'mode', 'family', 'stage', 'field', 'source_hook',
            'context_epoch', 'runtime_call', 'one_step_call', 'outer_loop', 'substep_n',
            'event_ordinal', 'causal_index', 'b_zero', 'k_zero', 'native_level_bottom_first',
            'B', 'K', 'role', 'dtype', 'scope', 'reason', 'raw_hex'}
CONTEXT = ('input_id', 'mode', 'context_epoch', 'runtime_call', 'one_step_call',
           'outer_loop', 'family', 'substep_n', 'scope', 'b_zero', 'k_zero',
           'native_level_bottom_first', 'B', 'K', 'event_ordinal')


def need(ok, message):
    if not ok:
        raise ValueError(message)


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def checked_records(rows, ident, sequence):
    """Check the value reader's ordered output including causal indices."""
    need(type(rows) is list and len(rows) <= MAX_RECORDS_PER_CALL, 'record bound')
    epoch = None
    ordinals = {}
    for index, row in enumerate(rows):
        need(type(row) is dict and set(row) == ROW_KEYS, 'record fields')
        need(all(type(row[k]) is str and row[k] and len(row[k]) <= 127 and row[k].isascii()
                 for k in ('input_id', 'mode', 'family', 'stage', 'field', 'source_hook')), 'record labels')
        need(all(type(row[k]) is int for k in ROW_KEYS - {'input_id', 'mode', 'family', 'stage', 'field', 'source_hook', 'raw_hex'}), 'record integers')
        need((row['input_id'], row['mode'], row['runtime_call']) == (ident, 'capture_on_value', sequence)
             and row['context_epoch'] > 0 and row['one_step_call'] >= 0
             and row['outer_loop'] >= 0 and row['substep_n'] >= 0, 'record identity')
        if epoch is None:
            epoch = row['context_epoch']
        need(row['context_epoch'] == epoch, 'mixed epoch')
        scope = row['scope']
        coords = (row['B'], row['K'], row['b_zero'], row['k_zero'], row['native_level_bottom_first'])
        need((scope == 1 and coords[:3] == (1, 39, 0) and 0 <= coords[3] < 39 and coords[4] == 39 - coords[3])
             or (scope == 2 and coords == (1, -1, 0, -1, -1))
             or (scope == 3 and coords == (-1, -1, -1, -1, -1)), 'record coordinates')
        role, dtype = row['role'], row['dtype']
        need(role in (1, 2, 3, 4, 5) and dtype in (1, 2, 3, 4, 5)
             and ((role == 4 and scope == 3) or (role != 4 and scope in (1, 2))), 'role/scope')
        key = tuple(row[k] for k in ('runtime_call', 'one_step_call', 'outer_loop', 'family', 'substep_n',
                                    'scope', 'b_zero', 'k_zero', 'B', 'K', 'stage', 'field', 'source_hook', 'role'))
        need(row['event_ordinal'] == ordinals.get(key, 0), 'event ordinal')
        ordinals[key] = row['event_ordinal'] + 1
        raw = row['raw_hex']
        if role == 5:
            cause = row['causal_index']
            need(dtype == 5 and row['reason'] in (1, 2, 3) and raw is None
                 and 0 <= cause < index, 'absence')
            prior = rows[cause]
            need(prior['role'] == 1 and prior['raw_hex'] == '0000000000000000'
                 and all(prior[k] == row[k] for k in CONTEXT), 'causal predicate')
        else:
            need(row['reason'] == 0 and row['causal_index'] == NO_CAUSE and dtype != 5
                 and (role not in (1, 2) or dtype == 1)
                 and (role != 3 or dtype in (2, 3)), 'value metadata')
            width = 8 if dtype == 2 else 16
            need(type(raw) is str and re.fullmatch('[0-9a-f]{%d}' % width, raw) is not None, 'raw word')
            if dtype == 1:
                need(raw in ('0000000000000000', '0000000000000001'), 'boolean word')
            if dtype in (2, 3):
                need(math.isfinite(struct.unpack('>f' if dtype == 2 else '>d', bytes.fromhex(raw))[0]), 'nonfinite word')
    return epoch



def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def serialize_same_call(result, planned_call, planned_words, claimed_dso, path):
    """Serialize a value-mode executor result; all claimed identities stay unverified."""
    result = copy.deepcopy(result)
    need(type(result) is dict and type(planned_call) is dict, 'executor result/call')
    ident, sequence = planned_call['input_id'], planned_call['sequence']
    need(type(sequence) is int and sequence > 0 and planned_call['mode'] == 'capture_on_value', 'planned call')
    need(type(path) is str and path and not path.startswith('/') and '..' not in Path(path).parts and '\\' not in path, 'asset path')
    need(result.get('schema') == 'kdm6.future_call_raw.v1'
         and (result.get('input_id'), result.get('sequence'), result.get('mode')) == (ident, sequence, 'capture_on_value')
         and type(result.get('return_code')) is int and result['return_code'] == 0
         and result.get('handle_nonnull') is False and result.get('handle_null_after') is True
         and result.get('close_rc') is None and result.get('dso_identity_status') == 'CALLER_SUPPLIED_UNVERIFIED'
         and rs.hex_sha(claimed_dso) and result.get('claimed_dso_sha256') == claimed_dso, 'executor call')
    need(rs.words(result.get('input_words'), 624, 'executor input') == rs.words(planned_words, 624, 'planned input'), 'executor input binding')
    rs.words(result.get('state_output_words'), 468, 'executor output')
    rain = result.get('same_call_rain')
    need(type(rain) is dict and set(rain) == {'raw_hex', 'graph_flag'} and type(rain['graph_flag']) is int
         and rain['graph_flag'] == 0 and type(rain['raw_hex']) is str
         and re.fullmatch('[0-9a-f]{16}', rain['raw_hex']) is not None
         and math.isfinite(struct.unpack('>d', bytes.fromhex(rain['raw_hex']))[0])
         and result.get('rain_unit_status') == 'UNAPPROVED'
         and result.get('rain_provenance') == 'SAME_CALL_CONTEXT_UNVERIFIED', 'rain checkpoint')
    sidecar = result.get('sidecar_records')
    need(type(sidecar) is list, 'sidecar records')
    matches = [r for r in sidecar if type(r) is dict and r.get('stage') == 'fnresult' and r.get('field') == 'rain_increment']
    need(len(matches) == 1, 'unique FnResult rain')
    rr = matches[0]
    need((rr.get('input_id'), rr.get('mode'), rr.get('runtime_call')) == (ident, 'capture_on_value', sequence)
         and (rr.get('scope'), rr.get('record_kind'), rr.get('b_zero'), rr.get('k_zero'),
              rr.get('native_level_bottom_first'), rr.get('B'), rr.get('K')) == ('column', 'value', 0, -1, -1, 1, -1)
         and rr.get('dtype') == 'f64' and rr.get('raw_hex') == rain['raw_hex'], 'FnResult rain binding')
    same = result.get('condition_v2_asset')
    need(type(same) is dict and set(same) == {'schema', 'status', 'sequence', 'input_id', 'mode', 'input_words',
         'state_output_words', 'same_call_rain', 'claimed_dso_sha256', 'dso_identity_status', 'graph_handle_token', 'capture'}
         and same['schema'] == 'kdm6.condition_v2_same_call.unverified.v1' and same['status'] == 'SPEC_ONLY_BLOCKED'
         and same['graph_handle_token'] is None, 'same-call asset')
    for key in ('sequence', 'input_id', 'mode', 'input_words', 'state_output_words', 'same_call_rain',
                'claimed_dso_sha256', 'dso_identity_status'):
        need(same[key] == result[key], 'same-call field mismatch: ' + key)
    encoded = canonical_bytes(same)
    need(result.get('condition_v2_asset_sha256') == hashlib.sha256(encoded).hexdigest(), 'same-call asset SHA')
    reader = same['capture']
    need(type(reader) is dict and set(reader) == {'status', 'records', 'graph_metadata_only'}
         and reader['status'] == 'SPEC_ONLY_BLOCKED' and reader['graph_metadata_only'] is False, 'reader copy')
    checked_records(reader['records'], ident, sequence)
    payload = {'schema': ASSET_SCHEMA, 'input_id': ident, 'sequence': sequence, 'mode': 'capture_on_value',
               'input_words': list(planned_words), 'dso_sha256': claimed_dso, 'reader': reader,
               'state_output_words': list(result['state_output_words']), 'same_call_rain': rain,
               'same_call_asset': same, 'same_call_asset_sha256': hashlib.sha256(encoded).hexdigest(),
               'rain_record': rr}
    raw = canonical_bytes(payload)
    need(len(raw) <= MAX_ASSET_BYTES, 'asset byte bound')
    return {'entry': {'input_id': ident, 'sequence': sequence,
                      'asset': {'path': path, 'sha256': hashlib.sha256(raw).hexdigest()}}, 'bytes': raw,
            'status': 'SPEC_ONLY', 'eligibility': 'NOT_ELIGIBLE'}


def join(receipt, assets, envelope):
    """Join 45 caller-provided reader-copy assets, retaining order and provenance limits."""
    receipt = copy.deepcopy(receipt)
    assets = dict(assets)
    envelope = copy.deepcopy(envelope)
    rs.validate(receipt, assets)
    plan, _ = rs.load_plan()
    need(type(envelope) is dict and set(envelope) == {'schema', 'status', 'plan_gzip_sha256', 'calls'}
         and envelope['schema'] == SCHEMA and envelope['status'] == 'SPEC_ONLY'
         and envelope['plan_gzip_sha256'] == rs.PLAN_GZ_SHA, 'envelope')
    expected = [call for call in plan['calls'] if call['mode'] == 'capture_on_value']
    need(len(expected) == 45 and type(envelope['calls']) is list and len(envelope['calls']) == 45, '45-call inventory')
    inputs = {entry['id']: entry['words'] for entry in plan['inputs']}
    dso = receipt['build']['new_instrumented_dso_sha256']
    receipt_calls = {(call['input_id'], call['mode']): call for call in receipt['calls'] if call['status'] == 'completed'}
    output = []
    used = set()
    total = 0
    for planned, entry in zip(expected, envelope['calls']):
        need(type(entry) is dict and set(entry) == {'input_id', 'sequence', 'asset'}
             and (entry['input_id'], entry['sequence']) == (planned['input_id'], planned['sequence']), 'call order')
        ref = entry['asset']
        need(type(ref) is dict and ref.get('path') not in used, 'duplicate asset path')
        raw = rs.asset(ref, assets)
        need(len(raw) <= MAX_ASSET_BYTES, 'asset byte bound')
        used.add(ref['path'])
        item = json.loads(raw, object_pairs_hook=no_duplicates)
        need(type(item) is dict and set(item) == {'schema', 'input_id', 'sequence', 'mode', 'input_words', 'dso_sha256', 'reader', 'state_output_words', 'same_call_rain', 'same_call_asset', 'same_call_asset_sha256', 'rain_record'}
             and item['schema'] == ASSET_SCHEMA
             and (item['input_id'], item['sequence'], item['mode']) == (entry['input_id'], entry['sequence'], 'capture_on_value')
             and item['dso_sha256'] == dso, 'asset call identity')
        need(rs.words(item['input_words'], 624, 'reader input') == inputs[entry['input_id']], 'input words')
        source = item['same_call_asset']
        need(type(source) is dict, 'same-call source')
        replay_result = {'schema': 'kdm6.future_call_raw.v1', 'input_id': entry['input_id'],
                         'sequence': entry['sequence'], 'mode': 'capture_on_value', 'return_code': 0,
                         'handle_nonnull': False, 'handle_null_after': True, 'close_rc': None,
                         'dso_identity_status': 'CALLER_SUPPLIED_UNVERIFIED', 'claimed_dso_sha256': dso,
                         'input_words': item['input_words'], 'state_output_words': item['state_output_words'],
                         'same_call_rain': item['same_call_rain'], 'rain_unit_status': 'UNAPPROVED',
                         'rain_provenance': 'SAME_CALL_CONTEXT_UNVERIFIED', 'sidecar_records': [item['rain_record']],
                         'condition_v2_asset': source, 'condition_v2_asset_sha256': item['same_call_asset_sha256']}
        canonical = serialize_same_call(replay_result, planned, inputs[entry['input_id']], dso, ref['path'])
        need(raw == canonical['bytes'], 'noncanonical or mismatched same-call asset')
        call = receipt_calls.get((entry['input_id'], 'capture_on_value'))
        need(type(call) is dict and call['sequence'] == entry['sequence'], 'receipt call binding')
        output_payload = json.loads(rs.asset(call['output_asset'], assets), object_pairs_hook=no_duplicates)
        need(output_payload['input_words'] == item['input_words'] and
             output_payload['state_output_words'] == item['state_output_words'] and
             output_payload['dso_sha256'] == dso, 'receipt output binding')
        reader = item['reader']
        need(type(reader) is dict and set(reader) == {'status', 'records', 'graph_metadata_only'}
             and reader['status'] == 'SPEC_ONLY_BLOCKED' and reader['graph_metadata_only'] is False, 'reader copy')
        rows = reader['records']
        checked_records(rows, entry['input_id'], entry['sequence'])
        total += len(rows)
        need(total <= MAX_TOTAL_RECORDS, 'total record bound')
        output.append({'input_id': entry['input_id'], 'sequence': entry['sequence'],
                       'asset_sha256': hashlib.sha256(raw).hexdigest(), 'records': rows})
    return {'schema': SCHEMA, 'status': 'SPEC_ONLY', 'eligibility': 'NOT_ELIGIBLE',
            'plan_gzip_sha256': rs.PLAN_GZ_SHA, 'calls': output,
            'scope': 'Untrusted serialized reader copies and caller assets; no producer, execution, mapping, or scientific proof.'}


def project_gate_input(receipt, assets, envelope, gate_input, bindings, contract, schedules):
    """Validate a hypothetical projection but never emit an augmented FD input.

    Schedules, mappings and copied assets do not establish per-call provenance.
    Mixed phases require a reviewed census; all other projections are unresolved.
    """
    import importlib.util

    path = HERE / 'condition_consumer_v2.py'
    spec = importlib.util.spec_from_file_location('condition_consumer_for_receipt_v3', path)
    consumer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(consumer)
    joined = join(receipt, assets, envelope)
    entries = {x['input_id']: x for x in joined['calls']}
    need(type(schedules) is dict, 'hypothetical schedules')
    ids = {bindings['center']} | {cid for roles in bindings['samples'].values() for cid in roles.values()}
    need(ids <= set(entries) and set(schedules) == ids, 'selected call schedule inventory')
    sites = contract['sites']
    captures = {}
    scopes = {1: 'layer', 2: 'column', 3: 'scalar'}
    roles = {1: 'consumed_bool', 2: 'diagnostic_bool', 3: 'operand', 4: 'control', 5: 'not_evaluated'}
    dtypes = {1: 'bool', 2: 'f32', 3: 'f64', 4: 'i64', 5: 'none'}
    reasons = {0: 'none', 1: 'gate_false', 2: 'optional_input_absent', 3: 'family_not_reached'}
    for ident in ids:
        entry = entries[ident]
        rows = entry['records']
        need(rows, 'empty call context')
        need(len({x['context_epoch'] for x in rows}) == 1, 'mixed call epoch')
        need(len({x['one_step_call'] for x in rows}) == 1,
             'UNSUPPORTED: mixed one_step_call phases require a reviewed phase census')
        call = {'input_id': ident, 'sequence': entry['sequence'], 'mode': 'capture_on_value',
                'context_epoch': rows[0]['context_epoch'], 'one_step_call': rows[0]['one_step_call']}
        converted = []
        for r in rows:
            matching = [s for s in sites if all(s[k] == r[k] for k in ('stage', 'field', 'source_hook', 'family'))
                        and s['scope'] == scopes[r['scope']]
                        and (r['role'] == 5 or (s['role'] == roles[r['role']] and s['dtype'] == dtypes[r['dtype']]))]
            need(len(matching) == 1, 'missing or ambiguous hypothetical site')
            raw = r['raw_hex']
            if r['dtype'] == 1:
                raw = raw == '0000000000000001'
            elif r['dtype'] == 4:
                raw = int(raw, 16)
                if raw >= 1 << 63:
                    raw -= 1 << 64
            item = {k: r[k] for k in ('input_id', 'mode', 'context_epoch', 'runtime_call', 'one_step_call',
                                       'outer_loop', 'family', 'substep_n', 'B', 'K', 'b_zero', 'k_zero',
                                       'native_level_bottom_first', 'event_ordinal', 'stage', 'field', 'source_hook')}
            item.update(site_id=matching[0]['id'], scope=scopes[r['scope']], role=roles[r['role']],
                        dtype=dtypes[r['dtype']], raw=raw, reason=reasons[r['reason']],
                        causal_index=None if r['causal_index'] == NO_CAUSE else r['causal_index'])
            converted.append(item)
        captures[ident] = {'call': call, 'capture': {'schema': consumer.SCHEMA, 'status': 'SPEC_ONLY',
                            'call': call, 'schedule': copy.deepcopy(schedules[ident]), 'records': converted}}
    consumer.add_conditions(gate_input, bindings, captures, copy.deepcopy(contract),
                            receipt=receipt, assets=assets)
    raise ValueError('UNRESOLVED: independent per-call provenance not established')
