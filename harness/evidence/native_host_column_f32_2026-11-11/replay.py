#!/usr/bin/env python3
"""Check published column words and isolated activation trace; no host execution."""
import csv
import gzip
import io
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct

HERE = Path(__file__).resolve().parent
TILE_SHA = 'a13d3aafdc4d71ffe5ea7a59616a48f4ea7c6ab3da813b8883bb7277df71ecce'
DSO_SHA = '7adcb6921f6205af66c62720ce9447928a1608f5c261546183b928bebbd9dba7'
SELECTED_SHA = 'e3117d277a073042bbae648b87e7dd6661d14b600fc8245f6aeabc19fe715eae'
INPUTS = 'th qv qc qr qi qs qg nccn nc ni nr bg rho pii p delz'.split()
OUTPUTS = INPUTS[:12] + ['rain', 'snow', 'graupel', 'rhog']


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()


def value(word):
    return struct.unpack('<f', struct.pack('<I', int(word, 16)))[0]


def rounded(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]


def word(x):
    return f"{struct.unpack('<I', struct.pack('<f', x))[0]:08x}"


def vector(words, count, label):
    need(isinstance(words, list) and len(words) == count, label + ' length')
    need(all(isinstance(w, str) and re.fullmatch('[0-9a-f]{8}', w) and math.isfinite(value(w)) for w in words), label + ' words')
    return words


def validate_column(selected, replay, parent):
    need(selected['schema'] == 'kdm6.selected_native_f32.v1' and selected['source_tile_sha256'] == TILE_SHA, 'selected source')
    need(selected['source_case'] == 'ss_real_case_20260619_063620/SS' and selected['model_start'] == '2025-07-19_00:00:00' and selected['model_step_end'] == '2025-07-19_00:00:20', 'case and time receipt')
    need(selected['call_index'] == 2 and selected['tile_shape'] == [232, 39, 139] and selected['tile_bounds'] == {'i': [2,233], 'j': [143,281]}, 'tile receipt')
    need(selected['column_native'] == [203,149] and selected['column_zero_based'] == [201,6] and selected['runtime_b_zero'] == 201*139+6, 'column mapping')
    need((selected['dt'], selected['ncmin_land'], selected['ncmin_sea'], selected['flags'], selected['value_only']) == (20,10,10,0,1) and selected['xland_word_hex'] == '40000000' and selected['tile_return_code'] == 0, 'ABI controls')
    ins, outs = selected['input_words_hex'], selected['output_words_hex']
    need(list(ins) == INPUTS and list(outs) == OUTPUTS[:12], 'ABI field order')
    for name in INPUTS: vector(ins[name], 39, 'input '+name)
    for name in OUTPUTS[:12]: vector(outs[name], 39, 'output '+name)
    increments = selected['increments_words_hex']
    need(list(increments) == OUTPUTS[12:15], 'increment order')
    actual_expected = dict(outs)
    for name in OUTPUTS[12:15]:
        vector([increments[name]], 1, name)
        actual_expected[name] = [increments[name]]
    actual_expected['rhog'] = vector(selected['rhog_words_hex'],39,'rhog')
    need(replay['schema'] == 'kdm6.selected_native_f32_replay.v1' and replay['selected_json_sha256'] == SELECTED_SHA and replay['tile_sha256'] == TILE_SHA and replay['dso_sha256'] == DSO_SHA, 'B=1 provenance')
    need(replay['return_code'] == 0 and replay['handle_null'] is True and replay['input_words_verified'] == 624 and replay['output_words_verified'] == 510 and replay['independent_tile_index_verification'] is True and replay['schedule'] == 'not exposed by ABI', 'B=1 metadata')
    actual = replay['actual_output_words_hex']
    need(set(actual) == set(OUTPUTS), 'B=1 output fields')
    for name in OUTPUTS: vector(actual[name], 1 if name in OUTPUTS[12:15] else 39, 'B=1 '+name)
    counts = {name: sum(a != b for a,b in zip(actual_expected[name],actual[name])) for name in OUTPUTS}
    need(counts == replay['raw_mismatch_counts'] and not any(counts.values()), 'B=1 vs tile output mismatch')
    need(parent['native_ij'] == selected['column_native'] and parent['packed_ij_zero'] == selected['column_zero_based'] and parent['xland_word_hex'] == selected['xland_word_hex'], 'parent column metadata')
    for name in INPUTS: need(parent['input_words_hex'][name] == [ins[name][k] for k in (0,19,38)], 'parent input '+name)
    for name in OUTPUTS[:12]: need(parent['output_words_hex'][name] == [outs[name][k] for k in (0,19,38)], 'parent output '+name)
    need(parent['increment_words_hex'] == increments and parent['rhog_words_hex'] == [actual_expected['rhog'][k] for k in (0,19,38)], 'parent diagnostics')
    return actual


TRACE_BOOL = set("sw_positive activation_fraction_pow_lt_one activation_fraction_pow_eq_one activation_fraction_pow_gt_one ncact_raw_lt_nccn_rate_cap ncact_raw_eq_nccn_rate_cap ncact_raw_gt_nccn_rate_cap cloud_complete_evap nccn_floor_active nccn_cap_active".split())
TRACE_FLOAT = set("qv_input qs1 sw_percent sw_ratio activation_fraction_one activation_fraction_pow safe_pow_clamped_base_diagnostic activation_fraction_min_output activated_fraction ncact_raw ncact_preclamp_fma ncact_clamped_numerator ncact_nccn_rate_cap ncact_min_output ncact nc_input nccn_input nc_after_activation nccn_after_activation nc_evap_amount nc_final nccn_final_raw nccn_final".split())


def validate_activation(data, actual):
    need(data['schema'] == 'kdm6.selected_native_f32_activation.v1' and data['source_tile_sha256'] == TILE_SHA and data['selected_input_sha256'] == SELECTED_SHA and data['installed_dso_sha256'] == DSO_SHA, 'activation provenance')
    need(data['identity'] == {'runtime_call': 1, 'one_step_call': 1, 'substep': 0, 'b_zero': 0, 'k_zero': 23, 'native_level': 16, 'stage': 'fd_satadj_inner'}, 'activation identity')
    need(data['output_noninterference'] == {'installed_vs_capture_on_off_equal': True, 'compared_words': 510, 'return_codes': [0,0,0]}, 'activation noninterference receipt')
    if True:
        trace = data['trace']
        need(set(trace) == TRACE_BOOL | TRACE_FLOAT, 'trace fields')
        for name in TRACE_BOOL:
            need(trace[name].get('dtype') == 'bool' and trace[name].get('raw_hex') in ('0', '1'), 'trace bool: ' + name)
        for name in TRACE_FLOAT:
            item = trace[name]
            w = item.get('raw_hex')
            need(item.get('dtype') == 'f32' and isinstance(w, str) and re.fullmatch(r'[0-9a-f]{1,8}', w) is not None, 'trace f32: ' + name)
            vector([w.zfill(8)], 1, 'trace: ' + name)
        def val(name): return value(trace[name]['raw_hex'])
        def flag(name): return trace[name]['raw_hex'] == '1'
        def exact_f32(name, expected):
            need(int(trace[name]['raw_hex'], 16) == int(word(expected), 16),
                 'source-order f32: ' + name)

        qv, qs1 = val('qv_input'), val('qs1')
        rh = rounded(qv / max(qs1, rounded(1.0e-9)))
        sw = rounded(rounded(rh - 1.0) * 100.0)
        exact_f32('sw_percent', sw)
        ratio = max(rounded(sw / rounded(0.48)), 0.0)
        exact_f32('sw_ratio', ratio)
        exact_f32('safe_pow_clamped_base_diagnostic', max(ratio, rounded(1.0e-15)))
        exact_f32('activation_fraction_one', 1.0)
        pow_expected = rounded(math.pow(max(ratio, rounded(1.0e-15)), rounded(0.6)))
        need(abs(int(word(pow_expected), 16)
                 - int(trace['activation_fraction_pow']['raw_hex'], 16)) <= 4,
             'independent safe_pow f32 within 4 ULP')
        exact_f32('activation_fraction_min_output',
                  min(val('activation_fraction_one'), val('activation_fraction_pow')))
        exact_f32('activated_fraction', val('activation_fraction_min_output'))

        nc, nccn = val('nc_input'), val('nccn_input')
        preclamp = rounded(-nc + rounded(rounded(nccn + nc)
                                             * val('activated_fraction')))
        exact_f32('ncact_preclamp_fma', preclamp)
        numerator = max(preclamp, 0.0)
        exact_f32('ncact_clamped_numerator', numerator)
        raw_rate = rounded(numerator / rounded(20.0))
        rate_cap = rounded(max(nccn, 0.0) / rounded(20.0))
        exact_f32('ncact_raw', raw_rate)
        exact_f32('ncact_nccn_rate_cap', rate_cap)
        exact_f32('ncact_min_output', min(raw_rate, rate_cap))
        exact_f32('ncact', val('ncact_min_output') if sw > 0.0 else 0.0)
        transfer = rounded(val('ncact') * rounded(20.0))
        nc_after = max(rounded(nc + transfer), 0.0)
        nccn_after = max(rounded(nccn - transfer), 0.0)
        exact_f32('nc_after_activation', nc_after)
        exact_f32('nccn_after_activation', nccn_after)
        evap_amount = rounded(nc_after * float(flag('cloud_complete_evap')))
        exact_f32('nc_evap_amount', evap_amount)
        nc_final = max(rounded(nc_after - evap_amount), 0.0)
        nccn_final_raw = rounded(nccn_after + evap_amount)
        exact_f32('nc_final', nc_final)
        exact_f32('nccn_final_raw', nccn_final_raw)
        exact_f32('nccn_final', min(max(nccn_final_raw, rounded(1.0e8)),
                                      rounded(2.0e10)))
        need(flag('nccn_floor_active') == (nccn_final_raw < rounded(1.0e8))
             and flag('nccn_cap_active') == (nccn_final_raw > rounded(2.0e10)),
             'NCCN reservoir limit masks')
        need(flag('sw_positive') == (val('sw_percent') > 0), 'sw positive mask')
        for prefix, left, right in (('activation_fraction_pow', 'activation_fraction_pow', 'activation_fraction_one'), ('ncact_raw', 'ncact_raw', 'ncact_nccn_rate_cap')):
            for suffix, condition in (('lt', val(left) < val(right)), ('eq', val(left) == val(right)), ('gt', val(left) > val(right))):
                name = prefix + '_' + suffix + ('_one' if prefix == 'activation_fraction_pow' else '_nccn_rate_cap')
                need(flag(name) == condition, 'comparison mask: ' + name)
        need(val('activation_fraction_min_output') == min(val('activation_fraction_pow'), val('activation_fraction_one')), 'fraction min')
        need(val('ncact_min_output') == min(val('ncact_raw'), val('ncact_nccn_rate_cap')), 'ncact min')
    need(int(data['trace']['nc_final']['raw_hex'],16) == int(actual['nc'][15],16) and int(data['trace']['nccn_final']['raw_hex'],16) == int(actual['nccn'][15],16), 'activation final output link')



def validate_activation_calls(data, selected, actual, activation):
    need(data['schema'] == 'kdm6.selected_native_activation_calls.v1' and data['scope'] == 'B=1 replay of host-captured input; no host-attached activation observation', 'activation calls scope')
    need(data['selected_json_sha256'] == SELECTED_SHA and data['tile_sha256'] == TILE_SHA and data['field_order'] == INPUTS and data['xland_word_hex'] == selected['xland_word_hex'], 'activation calls provenance')
    need(data['controls'] == {'dt':20.0, 'flags':0, 'im':1, 'jm':1, 'km':39, 'ncmin_land':10.0, 'ncmin_sea':10.0, 'value_only':1}, 'activation calls controls')
    need(set(data['input_words_hex']) == set(INPUTS), 'activation input fields')
    for name in INPUTS:
        vector(data['input_words_hex'][name], 39, 'activation input '+name)
        need(data['input_words_hex'][name] == selected['input_words_hex'][name], 'activation input mismatch: '+name)
    calls = data['calls']
    need(set(calls) == {'installed', 'capture_off', 'capture_on'}, 'activation calls')
    for label, call in calls.items():
        dso = DSO_SHA if label == 'installed' else activation['capture_dso_sha256']
        path = 'private://installed_dso/libkdm6_c.2.0.0.dylib' if label == 'installed' else 'private://f32_capture_dso/libkdm6_c.dylib'
        need(call['dso_sha256'] == dso and call['dso_path'] == path and call['return_code'] == 0 and call['handle_null'] is True, 'activation call DSO/status: '+label)
        outputs = call['output_words_hex']
        need(set(outputs) == set(OUTPUTS), 'activation output fields: '+label)
        for name in OUTPUTS:
            vector(outputs[name], 1 if name in OUTPUTS[12:15] else 39, 'activation output '+name)
            need(outputs[name] == actual[name], 'activation call output mismatch: '+label+' '+name)
    return True


TH_STOP_FLOAT = set('qv_input qs1 sw_percent sw_ratio activation_fraction_pow activation_fraction_min_output activated_fraction nc_input nccn_input ncact_raw ncact_nccn_rate_cap'.split())
TH_STOP_BOOL = TRACE_BOOL
TH_GUARD_BOOL = TH_STOP_BOOL - set('activation_fraction_pow_lt_one activation_fraction_pow_eq_one activation_fraction_pow_gt_one'.split())
TH_OFFSETS = [0] + [1 << k for k in range(12)]
TH_SWEEP_SHA = 'fbabe09b78ddf763e90f738a844ca9cb7bb279e0de0d39588dab3f17c82627b8'
TH_RUNNER_SHA = 'b8894b76d93fec3b8cadd1be80e043bbf04b7cf37ca29ba6aaf3105b686e4050'


def validate_th_search_stop(data, selected, activation):
    """Check the published TH probe record, not the unavailable private calls."""
    need(data['schema'] == 'kdm6.selected_host_f32_th_search_stop.v1'
         and data['scope'] == 'B=1 value-only perturbation of host-captured column; not a perturbed host tile or f32 AD',
         'TH search scope')
    need(data['private_sweep_sha256'] == TH_SWEEP_SHA
         and data['selected_json_sha256'] == SELECTED_SHA
         and data['private_input_bin_sha256'] == '8aced88b4f4f967a7cde0692837617b5ed3d058ccb30de8d2acdd7c43690d8ea'
         and data['runner_sha256'] == TH_RUNNER_SHA
         and data['installed_dso_sha256'] == DSO_SHA
         and data['capture_dso_sha256'] == activation['capture_dso_sha256'],
         'TH search provenance')
    need(data['axis'] == 'th16' and data['base_input_words'] == {
        'th': selected['input_words_hex']['th'][15],
        'qv': selected['input_words_hex']['qv'][15],
    } and data['max_word_distance'] == 1 << 20, 'TH search base input')
    need(data['probe_offsets'] == TH_OFFSETS
         and data['trace_identity'] == activation['identity'], 'TH search schedule and identity')
    samples = data['samples']
    need(isinstance(samples, list) and len(samples) == len(TH_OFFSETS), 'TH search sample inventory')
    base = int(data['base_input_words']['th'], 16)
    recorded = []
    for index, sample in enumerate(samples):
        need(sample['th_input_word'] == f'{base + TH_OFFSETS[index]:08x}', 'TH search input word')
        trace = sample['trace']
        need(set(trace) == TH_STOP_FLOAT | TH_STOP_BOOL, 'TH search trace fields')
        for name in TH_STOP_FLOAT:
            item = trace[name]
            raw = item.get('raw_hex')
            need(item.get('dtype') == 'f32' and isinstance(raw, str)
                 and re.fullmatch('[0-9a-f]{1,8}', raw) is not None,
                 'TH search f32 field: ' + name)
            vector([raw.zfill(8)], 1, 'TH search f32: ' + name)
        for name in TH_STOP_BOOL:
            item = trace[name]
            need(item.get('dtype') == 'bool' and item.get('raw_hex') in ('0', '1'),
                 'TH search mask: ' + name)
        val = lambda name: value(trace[name]['raw_hex'])
        mask = lambda name: trace[name]['raw_hex'] == '1'
        exact = lambda name, expected: need(int(trace[name]['raw_hex'], 16) == int(word(expected), 16),
                                             'TH search source-order: ' + name)
        rh = rounded(val('qv_input') / max(val('qs1'), rounded(1.0e-9)))
        sw = rounded(rounded(rh - 1.0) * 100.0)
        exact('sw_percent', sw)
        ratio = max(rounded(sw / rounded(0.48)), 0.0)
        exact('sw_ratio', ratio)
        pow_expected = rounded(math.pow(max(ratio, rounded(1.0e-15)), rounded(0.6)))
        need(abs(int(word(pow_expected), 16) - int(trace['activation_fraction_pow']['raw_hex'], 16)) <= 4,
             'TH search pow within 4 f32 ULP')
        exact('activation_fraction_min_output', min(1.0, val('activation_fraction_pow')))
        exact('activated_fraction', val('activation_fraction_min_output'))
        preclamp = rounded(-val('nc_input') + rounded(
            rounded(val('nccn_input') + val('nc_input')) * val('activated_fraction')))
        exact('ncact_raw', rounded(max(preclamp, 0.0) / rounded(20.0)))
        exact('ncact_nccn_rate_cap', rounded(max(val('nccn_input'), 0.0) / rounded(20.0)))
        for stem, left, right in (
            ('activation_fraction_pow', val('activation_fraction_pow'), 1.0),
            ('ncact_raw', val('ncact_raw'), val('ncact_nccn_rate_cap')),
        ):
            suffix = '_one' if stem == 'activation_fraction_pow' else '_nccn_rate_cap'
            for comparison, expected in (('lt', left < right), ('eq', left == right), ('gt', left > right)):
                need(mask(stem + '_' + comparison + suffix) == expected,
                     'TH search comparison mask: ' + stem + '_' + comparison)
        recorded.append({name: trace[name]['raw_hex'] for name in TH_STOP_BOOL})
    need({name: samples[0]['trace'][name] for name in TH_STOP_FLOAT | TH_STOP_BOOL}
         == {name: activation['trace'][name] for name in TH_STOP_FLOAT | TH_STOP_BOOL},
         'TH search baseline activation link')
    need(all(all(row[name] == recorded[0][name] for name in TH_GUARD_BOOL)
             for row in recorded[:-1]), 'TH search pre-stop masks')
    changed = {name: (recorded[0][name], recorded[-1][name])
               for name in TH_GUARD_BOOL if recorded[-1][name] != recorded[0][name]}
    need(changed == {'ncact_raw_eq_nccn_rate_cap': ('1', '0'),
                     'ncact_raw_lt_nccn_rate_cap': ('0', '1')}, 'TH search stop masks')
    need(all(value(sample['trace']['sw_percent']['raw_hex']) > 0.48 for sample in samples[:-1])
         and value(samples[-1]['trace']['sw_percent']['raw_hex']) < 0.48,
         'TH search sampled supersaturation')
    need(all(sample['trace']['sw_positive']['raw_hex'] == '1' for sample in samples),
         'TH search positive supersaturation mask')
    need(data['stop'] == {
        'status': 'stopped',
        'reason': 'unrelated masks changed: {"ncact_raw_eq_nccn_rate_cap": ["1", "0"], "ncact_raw_lt_nccn_rate_cap": ["0", "1"]}',
        'last_unchanged_sample_index': 11,
        'changed_sample_index': 12,
        'boundaries_recorded': 0,
        'qv_search_attempted': False,
    }, 'TH search stop decision')
    need(data['baseline_parity'] == [
        {'axis':'th','word':data['base_input_words']['th'],'mode':'off','match':True},
        {'axis':'th','word':data['base_input_words']['th'],'mode':'installed','match':True},
    ], 'TH search baseline parity receipt')
    return len(samples)

def validate_private(tile_path, dso_path, selected):
    """Optionally bind every public column word to the pinned private tile and DSO."""
    import ctypes
    import importlib.util
    import numpy as np
    spec = importlib.util.spec_from_file_location('parent_tile_replay', HERE.parent / 'native_host_tile_abi_2026-11-11' / 'replay.py')
    parent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parent)
    inputs, xland, outputs = parent.read_tile(tile_path)
    ij = 6 * 232 + 201
    indices = [(6 * 39 + k) * 232 + 201 for k in range(39)]
    def words(a, idx):
        return [f'{int(a.view("u4")[i]):08x}' for i in idx]
    for name, array in zip(INPUTS, inputs): need(words(array, indices) == selected['input_words_hex'][name], 'private tile input '+name)
    need(words(xland, [ij])[0] == selected['xland_word_hex'], 'private tile xland')
    for name, array in zip(OUTPUTS[:12], outputs[:12]): need(words(array, indices) == selected['output_words_hex'][name], 'private tile output '+name)
    for name, array in zip(OUTPUTS[12:15], outputs[12:15]): need(words(array, [ij])[0] == selected['increments_words_hex'][name], 'private tile increment '+name)
    need(words(outputs[15], indices) == selected['rhog_words_hex'], 'private tile rhog')
    parent.replay_private(tile_path, dso_path)
    column_inputs = [np.asarray(array[indices], dtype='<f4').copy() for array in inputs]
    column_xland = np.asarray(xland[[ij]], dtype='<f4').copy()
    column_outputs = [np.empty(39, dtype='<f4') for _ in range(12)]
    column_outputs += [np.empty(1, dtype='<f4') for _ in range(3)]
    column_outputs += [np.empty(39, dtype='<f4')]
    lib = ctypes.CDLL(str(Path(dso_path).resolve()))
    fn = lib.kdm6_step_c
    ptr = ctypes.POINTER(ctypes.c_float)
    fn.argtypes = [ptr] * 16 + [ctypes.c_int] * 3 + [ctypes.c_double]
    fn.argtypes += [ctypes.c_int] * 2 + [ptr] * 12
    fn.argtypes += [ctypes.POINTER(ctypes.c_void_p), ptr, ctypes.c_double, ctypes.c_double]
    fn.argtypes += [ptr] * 4
    fn.restype = ctypes.c_int
    pointer = lambda array: array.ctypes.data_as(ptr)
    handle = ctypes.c_void_p()
    rc = fn(*map(pointer, column_inputs), 1, 39, 1, 20.0, 0, 1,
            *map(pointer, column_outputs[:12]), ctypes.byref(handle),
            pointer(column_xland), 10.0, 10.0,
            *map(pointer, column_outputs[12:]))
    need(rc == 0 and handle.value is None, 'private B=1 ABI call status')
    expected = {**selected['output_words_hex'],
                **{key: [value] for key, value in selected['increments_words_hex'].items()},
                'rhog': selected['rhog_words_hex']}
    for name, array in zip(OUTPUTS, column_outputs):
        actual = [f'{int(value):08x}' for value in array.view('<u4')]
        need(actual == expected[name], 'private B=1 output: '+name)


MANIFEST_SHA = 'c1f17fff7818778dbf287faa2248da50abba6718c9d7d1cea91248048b0d4af9'
PINS = {
    'raw/activation_calls.json': '4b181883e4723f34881dbda2cd1da97cdbdbbbe671029c8a95e0d7463f717f45',
    'raw/activation_capture.csv.gz': '257b136e97b976bce08db0d2f682855f201024d785c8048c5645fee5e622e642',
    'raw/activation_summary.json': '8354c4682dc632b92b9a1322079cb4a6b64e348916fdb61e03e5dbedbf2b471b',
    'raw/b1_replay.json': '542f2578f8abf38563921d354aa7dff6617056238d1d319185a2ec55c26bc0f8',
    'raw/column_receipt.json': '90b6926124e34523e2cbb1361f467732628ff16aba2d6808db927f3168891851',
    'raw/selected_full.json': SELECTED_SHA,
    'raw/th_search_stop.json': '896e33963ff44af5e815b6d81d064e0829858eee708128c0fc940a46f3d83413',
}
PARENT_SHA = 'e9ce79d45090218c43754a54ff078373e7e69335fdc8f3e9eea2d7f285e55232'
CSV_SHA = 'b211688e9d3c63885a976edde93f9283fb637c3ea2cf232980e34ebbf835bb38'


def load_packet(root=HERE):
    need(sha(root / 'manifest.json') == MANIFEST_SHA, 'manifest SHA-256')
    manifest = json.loads((root / 'manifest.json').read_text())
    need(manifest['schema'] == 'kdm6.native_host_column_f32_packet.v1' and manifest['files'] == PINS, 'manifest contents')
    for name, digest in PINS.items(): need(sha(root / name) == digest, 'independent asset SHA-256: ' + name)
    raw = root / 'raw'
    read = lambda n: json.loads((raw / n).read_text())
    receipt = read('column_receipt.json')
    # The original #580 receipt remains byte-for-byte fixed; the TH supplement is
    # independently pinned by this packet's updated manifest.
    need(receipt['schema'] == 'kdm6.native_host_column_f32_receipt.v1' and receipt['files'] == {k:v for k,v in PINS.items() if k not in ('raw/column_receipt.json', 'raw/th_search_stop.json')}, 'receipt files')
    need(receipt['parent_host_tile_capture_sha256'] == TILE_SHA and receipt['installed_dso_sha256'] == DSO_SHA and receipt['parent_public_selected_summary_sha256'] == PARENT_SHA and receipt['input_word_count'] == 624 and receipt['output_word_count'] == 510 and receipt['private_activation_capture_csv_sha256'] == CSV_SHA, 'receipt provenance')
    need(receipt['scope'] == 'selected 39-level host-call column and separate B=1 C ABI replay; no host-tile stage AD or schedule claim', 'receipt scope')
    parent_path = root.parent / 'native_host_tile_abi_2026-11-11/raw/selected_column.json'
    need(sha(parent_path) == PARENT_SHA, 'parent selected SHA-256')
    selected, replay, activation = read('selected_full.json'), read('b1_replay.json'), read('activation_summary.json')
    need(replay['dso_path'] == 'private://installed_dso/libkdm6_c.2.0.0.dylib', 'DSO path')
    historical_path = root.parent / 'native_host_tile_abi_2026-11-11/raw/column_vs_556.json'
    need(sha(historical_path) == '3e340fbaace52100478931bd8c29cfd1380f679f342a092c0479b737d468bde5', 'parent historical comparison SHA-256')
    historical = json.loads(historical_path.read_text())
    need(historical['th']['equal'] == 0 and historical['th']['different'] == 39 and historical['th']['first_different']['host_word'] == selected['input_words_hex']['th'][0] and historical['th']['first_different']['reference_word'] != selected['input_words_hex']['th'][0], 'historical input distinction')
    actual = validate_column(selected, replay, json.loads(parent_path.read_text()))
    validate_activation(activation, actual)
    validate_th_search_stop(read('th_search_stop.json'), selected, activation)
    validate_activation_calls(read('activation_calls.json'), selected, actual, activation)
    need(receipt['private_activation_calls_original_sha256'] == 'e6b686caac613735414b61d3ee245f6394cc09240b8daa2407778074d1414c6b', 'activation calls original SHA-256')
    csv_bytes = gzip.decompress((raw / 'activation_capture.csv.gz').read_bytes())
    need(hashlib.sha256(csv_bytes).hexdigest() == CSV_SHA == activation['capture_csv_sha256'], 'capture CSV SHA-256')
    rows = list(csv.DictReader(line for line in io.StringIO(csv_bytes.decode('ascii')) if not line.startswith('#')))
    need(len(rows) == activation['capture_csv_rows'] == 19656, 'capture CSV row count')
    identity = activation['identity']
    matches = [r for r in rows if all(r[k] == str(v) for k,v in identity.items() if k != 'native_level')]
    need(len(matches) == len(activation['trace']) == 33 and len({r['field'] for r in matches}) == 33, 'captured stage rows')
    need({r['field']: {'dtype':r['dtype'], 'raw_hex':r['raw_hex']} for r in matches} == activation['trace'] and all(r['B'] == '1' and r['K'] == '39' for r in matches), 'stage trace CSV mismatch')
    return selected


def public_summary(selected=None):
    if selected is None:
        selected = load_packet()
    return {
        'schema': 'kdm6.native_host_column_f32_public_replay.v1',
        'input_words': 624,
        'tile_output_words': 510,
        'archived_b1_output_words': 510,
        'installed_capture_calls': 3,
        'output_words_compared_per_call': 510,
        'tile_vs_archived_b1_raw_mismatches': 0,
        'activation_stage_trace_fields': 33,
        'capture_csv_rows': 19656,
        'th_search_recorded_samples': 13,
        'th_search_last_unchanged_word': '439fff36',
        'th_search_changed_word': '43a00336',
        'th_search_limit': 'B=1 sampled search stopped on rate/cap mask change before a certified activation bracket; no QV search, host perturbed replay, boundary or AD claim',
        'native_column': selected['column_native'],
        'levels': 39,
        'call_scope': 'host tile call and separate B=1 call; internal schedule unobserved',
        'public_limit': 'validates published words and captured trace arithmetic; host invocation, private tile and installed library are not independently re-executed in public mode',
        'private_check': 'optional with PRIVATE_TILE_PATH and PRIVATE_DSO_PATH; checks selected words against full tile and reruns full tile plus B=1 with the pinned installed DSO',
        'activation_limit': 'isolated B=1 capture hook; capture DSO is not rerun by the private check; cloud complete evaporation is an observed gate; independent power check allows four f32 ULP',
        'scientific_status': 'INCONCLUSIVE',
        'physical_unit_status': 'INCONCLUSIVE',
    }


def main():
    selected = load_packet()
    summary = public_summary(selected)
    tile, dso = os.environ.get('PRIVATE_TILE_PATH'), os.environ.get('PRIVATE_DSO_PATH')
    need(bool(tile) == bool(dso), 'set both PRIVATE_TILE_PATH and PRIVATE_DSO_PATH')
    if tile:
        validate_private(tile, dso, selected)
        print(json.dumps({**summary, 'private_reexecution': 'PASSED'}, indent=2, sort_keys=True))
    else:
        print(json.dumps({**summary, 'private_reexecution': 'SKIPPED'}, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
