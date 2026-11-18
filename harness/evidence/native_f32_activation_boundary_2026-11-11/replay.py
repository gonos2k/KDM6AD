#!/usr/bin/env python3
"""Validate archived f32 C-ABI baseline arrays; this does not execute a host run."""
from __future__ import annotations

import hashlib
import gzip
import csv
import io
import json
import math
from pathlib import Path
import re
import struct

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / "native_pre2_input_cpp_ad_2026-11-08/raw/input.bin"
PARENT_SHA = "fbfe149519126de4192b0cf788ff9b56da65aef55fd1c6e2ff73a52b9844e82d"
NSTATE, NFORCING, LEVELS = 12, 4, 39


def need(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def parent_words(path: Path = PARENT) -> tuple[list[str], list[str]]:
    raw = path.read_bytes()
    need(hashlib.sha256(raw).hexdigest() == PARENT_SHA, "parent input SHA")
    need(len(raw) == 15 + 624 * 8 + 4 + 8 and raw[:15] == b"KDM6_PRE2_INPUT", "parent input format")
    values = struct.unpack_from("<624d", raw, 15)
    xland, dt = struct.unpack_from("<fd", raw, 15 + 624 * 8)
    need(xland == 2.0 and dt == 20.0, "parent controls")
    words = []
    for value in values:
        need(math.isfinite(value), "nonfinite parent input")
        try:
            packed = struct.pack("<f", value)
        except OverflowError as exc:
            raise ValueError("parent input not f32 representable") from exc
        need(struct.unpack("<f", packed)[0] == value, "parent input not exactly f32")
        words.append(f"{struct.unpack('<I', packed)[0]:08x}")
    return words[:468], words[468:]


def vector(value: object, count: int, label: str) -> list[str]:
    need(isinstance(value, list) and len(value) == count, label + " count")
    need(all(isinstance(x, str) and re.fullmatch(r"[0-9a-f]{8}", x) for x in value), label + " words")
    need(all(int(x, 16) & 0x7f800000 != 0x7f800000 for x in value), label + " finite")
    return value


def validate_call(call: dict, state: list[str], forcing: list[str], axis: str = "baseline", word: str = "") -> dict[str, list[str]]:
    need(isinstance(call, dict), "call object")
    need(call.get("schema") == "kdm6.native_f32_activation_probe_call.v1", "call schema")
    need(call.get("axis") == axis and call.get("override_word") == word, "call axis/override")
    need(axis in ("baseline", "th16", "qv16"), "axis")
    expected = state.copy()
    if axis != "baseline":
        vector([word], 1, "override")
        need(math.isfinite(struct.unpack('<f', struct.pack('<I', int(word, 16)))[0]), "override finite")
        expected[(0 if axis == "th16" else LEVELS) + 15] = word
    else:
        need(word == "", "baseline override")
    need(call.get("rc") == 0 and call.get("value_only") == 1 and call.get("handle_null") is True, "call status")
    need(call.get("shape") == [1, 39, 1] and call.get("dt_s") == 20 and call.get("xland") == 2 and call.get("ncmin_land") == 10 and call.get("ncmin_sea") == 10, "call controls")
    need(vector(call.get("source_state_f32_words"), 468, "state input") == expected, "state input mismatch")
    need(vector(call.get("source_forcing_f32_words"), 156, "forcing input") == forcing, "forcing input mismatch")
    arrays = call.get("state_output_f32_words")
    need(isinstance(arrays, list) and len(arrays) == 12, "state output fields")
    return {"state_output_f32_words": [w for a in arrays for w in vector(a, 39, "state output")],
            "precip_increment_f32_words": vector(call.get("precip_increment_f32_words"), 3, "precip output"),
            "rhog_output_f32_words": vector(call.get("rhog_output_f32_words"), 39, "rhog output")}


def baseline(raw_dir: Path = HERE / "raw") -> dict:
    state, forcing = parent_words()
    names = ("installed_baseline.json", "private_baseline_capture_off.json", "private_baseline_capture_on.json")
    outputs = [validate_call(json.loads((raw_dir / name).read_bytes()), state, forcing) for name in names]
    counts = {}
    for key in outputs[0]:
        need(outputs[0][key] == outputs[1][key] == outputs[2][key], "baseline parity: " + key)
        counts[key] = len(outputs[0][key])
    return {"baseline_arrays_equal": counts, "calls": 3, "scope": "archived standard f32 C ABI; no host-run claim"}



SWEEP_SHA = "05a540159575660f5e030da199a489f7fd31d8c78fdb00dea5231438c9352fc3"
TRACE_BOOL = set("sw_positive activation_fraction_pow_lt_one activation_fraction_pow_eq_one activation_fraction_pow_gt_one ncact_raw_lt_nccn_rate_cap ncact_raw_eq_nccn_rate_cap ncact_raw_gt_nccn_rate_cap cloud_complete_evap nccn_floor_active nccn_cap_active".split())
TRACE_FLOAT = set("qv_input qs1 sw_percent sw_ratio activation_fraction_one activation_fraction_pow safe_pow_clamped_base_diagnostic activation_fraction_min_output activated_fraction ncact_raw ncact_preclamp_fma ncact_clamped_numerator ncact_nccn_rate_cap ncact_min_output ncact nc_input nccn_input nc_after_activation nccn_after_activation nc_evap_amount nc_final nccn_final_raw nccn_final".split())


def as_f32(word: str) -> float:
    return struct.unpack('<f', struct.pack('<I', int(word, 16)))[0]


def round_f32(value: float) -> float:
    return struct.unpack('<f', struct.pack('<f', float(value)))[0]


def f32_word(value: float) -> str:
    return f"{struct.unpack('<I', struct.pack('<f', float(value)))[0]:08x}"


def validate_sweep(data: dict) -> dict:
    need(data.get('schema') == 'kdm6.native_f32_activation_boundary.sweep.v1' and data.get('input_sha256') == PARENT_SHA, 'sweep schema/input')
    events = data.get('events')
    need(isinstance(events, list) and len(events) == 36 and data.get('unique_events') == 36, 'sweep count')
    by_key = {}
    for e in events:
        axis, word = e['axis'], e['word']
        need(axis in ('th16', 'qv16'), 'sweep axis')
        vector([word], 1, 'sweep word')
        need(e['value'] == as_f32(word), 'sweep represented value')
        key = (axis, word)
        need(key not in by_key, 'duplicate sweep word')
        by_key[key] = e
        trace = e['trace']
        need(set(trace) == TRACE_BOOL | TRACE_FLOAT, 'trace fields')
        for name in TRACE_BOOL:
            need(trace[name].get('dtype') == 'bool' and trace[name].get('raw_hex') in ('0', '1'), 'trace bool: ' + name)
        for name in TRACE_FLOAT:
            item = trace[name]
            w = item.get('raw_hex')
            need(item.get('dtype') == 'f32' and isinstance(w, str) and re.fullmatch(r'[0-9a-f]{1,8}', w) is not None, 'trace f32: ' + name)
            vector([w.zfill(8)], 1, 'trace: ' + name)
        def val(name): return as_f32(trace[name]['raw_hex'])
        def flag(name): return trace[name]['raw_hex'] == '1'
        def exact_f32(name, expected):
            need(int(trace[name]['raw_hex'], 16) == int(f32_word(expected), 16),
                 'source-order f32: ' + name)

        qv, qs1 = val('qv_input'), val('qs1')
        rh = round_f32(qv / max(qs1, round_f32(1.0e-9)))
        sw = round_f32(round_f32(rh - 1.0) * 100.0)
        exact_f32('sw_percent', sw)
        ratio = max(round_f32(sw / round_f32(0.48)), 0.0)
        exact_f32('sw_ratio', ratio)
        exact_f32('safe_pow_clamped_base_diagnostic', max(ratio, round_f32(1.0e-15)))
        exact_f32('activation_fraction_one', 1.0)
        pow_expected = round_f32(math.pow(max(ratio, round_f32(1.0e-15)), round_f32(0.6)))
        need(abs(int(f32_word(pow_expected), 16)
                 - int(trace['activation_fraction_pow']['raw_hex'], 16)) <= 4,
             'independent safe_pow f32 within 4 ULP')
        exact_f32('activation_fraction_min_output',
                  min(val('activation_fraction_one'), val('activation_fraction_pow')))
        exact_f32('activated_fraction', val('activation_fraction_min_output'))

        nc, nccn = val('nc_input'), val('nccn_input')
        preclamp = round_f32(-nc + round_f32(round_f32(nccn + nc)
                                             * val('activated_fraction')))
        exact_f32('ncact_preclamp_fma', preclamp)
        numerator = max(preclamp, 0.0)
        exact_f32('ncact_clamped_numerator', numerator)
        raw_rate = round_f32(numerator / round_f32(20.0))
        rate_cap = round_f32(max(nccn, 0.0) / round_f32(20.0))
        exact_f32('ncact_raw', raw_rate)
        exact_f32('ncact_nccn_rate_cap', rate_cap)
        exact_f32('ncact_min_output', min(raw_rate, rate_cap))
        exact_f32('ncact', val('ncact_min_output') if sw > 0.0 else 0.0)
        transfer = round_f32(val('ncact') * round_f32(20.0))
        nc_after = max(round_f32(nc + transfer), 0.0)
        nccn_after = max(round_f32(nccn - transfer), 0.0)
        exact_f32('nc_after_activation', nc_after)
        exact_f32('nccn_after_activation', nccn_after)
        evap_amount = round_f32(nc_after * float(flag('cloud_complete_evap')))
        exact_f32('nc_evap_amount', evap_amount)
        nc_final = max(round_f32(nc_after - evap_amount), 0.0)
        nccn_final_raw = round_f32(nccn_after + evap_amount)
        exact_f32('nc_final', nc_final)
        exact_f32('nccn_final_raw', nccn_final_raw)
        exact_f32('nccn_final', min(max(nccn_final_raw, round_f32(1.0e8)),
                                      round_f32(2.0e10)))
        need(flag('nccn_floor_active') == (nccn_final_raw < round_f32(1.0e8))
             and flag('nccn_cap_active') == (nccn_final_raw > round_f32(2.0e10)),
             'NCCN reservoir limit masks')
        need(flag('sw_positive') == (val('sw_percent') > 0), 'sw positive mask')
        for prefix, left, right in (('activation_fraction_pow', 'activation_fraction_pow', 'activation_fraction_one'), ('ncact_raw', 'ncact_raw', 'ncact_nccn_rate_cap')):
            for suffix, condition in (('lt', val(left) < val(right)), ('eq', val(left) == val(right)), ('gt', val(left) > val(right))):
                name = prefix + '_' + suffix + ('_one' if prefix == 'activation_fraction_pow' else '_nccn_rate_cap')
                need(flag(name) == condition, 'comparison mask: ' + name)
        need(val('activation_fraction_min_output') == min(val('activation_fraction_pow'), val('activation_fraction_one')), 'fraction min')
        need(val('ncact_min_output') == min(val('ncact_raw'), val('ncact_nccn_rate_cap')), 'ncact min')
        arrays = e['state_output_f32_words']
        need(isinstance(arrays, list) and len(arrays) == 12, 'sweep state fields')
        for a in arrays: vector(a, 39, 'sweep state')
        vector(e['precip_increment_f32_words'], 3, 'sweep precip')
        vector(e['rhog_output_f32_words'], 39, 'sweep rhog')
        need(int(trace['nc_final']['raw_hex'], 16) == int(arrays[8][15], 16),
             'final NC trace/output link')
        need(int(trace['nccn_final']['raw_hex'], 16) == int(arrays[7][15], 16),
             'final NCCN trace/output link')
    state, _ = parent_words()
    base_th, base_qv = state[15], state[LEVELS + 15]
    by_full_input = {}
    repeated = 0
    for e in events:
        full_input = (e['word'] if e['axis'] == 'th16' else base_th,
                      e['word'] if e['axis'] == 'qv16' else base_qv)
        if full_input in by_full_input:
            first = by_full_input[full_input]
            for key in ('trace', 'state_output_f32_words',
                        'precip_increment_f32_words', 'rhog_output_f32_words'):
                need(e[key] == first[key], 'repeated full input observation: ' + key)
            repeated += 1
        else:
            by_full_input[full_input] = e
    need(len(by_full_input) == 35 and repeated == 1,
         'complete full-input sample inventory')
    def predicate(e, name):
        field, threshold = ('sw_percent', 0.48) if name == 'sw' else ('activation_fraction_min_output', 1.0)
        return as_f32(e['trace'][field]['raw_hex']) >= threshold
    expected = {('th16', 'sw'), ('th16', 'fraction'), ('qv16', 'sw'), ('qv16', 'fraction')}
    boundaries = data.get('boundaries')
    need(isinstance(boundaries, list) and len(boundaries) == 4 and {(b['axis'], b['predicate']) for b in boundaries} == expected, 'boundary inventory')
    for b in boundaries:
        axis, pred, lo, hi = b['axis'], b['predicate'], b['lower_word'], b['upper_word']
        need((axis, lo) in by_key and (axis, hi) in by_key and int(hi, 16) - int(lo, 16) == 1, 'adjacent sampled endpoints')
        gap = as_f32(hi) - as_f32(lo)
        need(math.isfinite(gap) and gap > 0 and b['gap'] == gap, 'endpoint gap')
        lower, upper = predicate(by_key[(axis, lo)], pred), predicate(by_key[(axis, hi)], pred)
        need(lower != upper and b['lower_predicate'] is lower and b['upper_predicate'] is upper, 'endpoint predicate')
    for axis in ('th16', 'qv16'):
        samples = sorted((int(w, 16), e) for (a, w), e in by_key.items() if a == axis)
        need(len(samples) == (13 if axis == 'th16' else 23), 'axis sample count')
        for pred in ('sw', 'fraction'):
            values = [predicate(e, pred) for _, e in samples]
            need(values == sorted(values, reverse=axis == 'th16'), 'sampled predicate monotonicity')
    diagnostics = {}
    for axis in ('th16', 'qv16'):
        b = next(b for b in boundaries if b['axis'] == axis and b['predicate'] == 'sw')
        lo, hi = by_key[(axis, b['lower_word'])], by_key[(axis, b['upper_word'])]
        fields = {}
        for key in ('state_output_f32_words', 'precip_increment_f32_words', 'rhog_output_f32_words'):
            left, right = lo[key], hi[key]
            if key == 'state_output_f32_words':
                left = [w for row in left for w in row]
                right = [w for row in right for w in row]
            def ordered(w):
                n = int(w, 16)
                return (~n & 0xffffffff) if n & 0x80000000 else n | 0x80000000
            deltas = [abs(as_f32(y) - as_f32(x)) for x, y in zip(left, right)]
            need(all(math.isfinite(d) for d in deltas), 'finite output deltas')
            fields[key] = {'changed_words': sum(x != y for x, y in zip(left, right)),
                           'max_word_distance': max(abs(ordered(x) - ordered(y)) for x, y in zip(left, right)),
                           'max_abs_delta': max(deltas)}
        diagnostics[axis] = {'lower_word': b['lower_word'], 'upper_word': b['upper_word'], 'input_gap': b['gap'], 'outputs': fields}
    return {'events': len(by_key), 'distinct_full_inputs': len(by_full_input),
            'repeated_full_input_checks': repeated, 'boundaries': len(boundaries),
            'endpoint_diagnostics': diagnostics,
            'scope': 'sampled endpoints only; no global uniqueness claim'}


def sweep(path: Path = HERE / 'raw/sweep/sweep.json') -> dict:
    raw = path.read_bytes()
    need(hashlib.sha256(raw).hexdigest() == SWEEP_SHA, 'sweep SHA')
    return validate_sweep(json.loads(raw))



def terminal_calls(packet: Path = HERE) -> dict:
    receipt_path = packet / 'raw/sweep/terminal_calls/receipt.json'
    raw = receipt_path.read_bytes()
    need(hashlib.sha256(raw).hexdigest() == '870d1180214bec5e8ca78fa2912e128c0cf35aa536218af4210fa4f2fb9338df', 'terminal receipt SHA')
    receipt = json.loads(raw)
    need(receipt.get('schema') == 'kdm6.native_f32_activation_boundary.terminal_calls.v1' and receipt.get('input_sha256') == PARENT_SHA, 'terminal receipt schema/input')
    sweep_raw = (packet / 'raw/sweep/sweep.json').read_bytes()
    need(hashlib.sha256(sweep_raw).hexdigest() == SWEEP_SHA, 'sweep SHA')
    data = json.loads(sweep_raw)
    validate_sweep(data)
    events = {(e['axis'], e['word']): e for e in data['events']}
    endpoints = {(b['axis'], b[k]) for b in data['boundaries'] for k in ('lower_word', 'upper_word')}
    state, forcing = parent_words()
    entries = receipt['calls']
    expected = {(axis, word, mode) for axis, word in endpoints for mode in ('installed', 'capture_off', 'capture_on')}
    need(len(entries) == 12 and {(e['axis'], e['word'], e['mode']) for e in entries} == expected, 'terminal inventory')
    for e in entries:
        axis, word, mode = e['axis'], e['word'], e['mode']
        expected_path = f'raw/sweep/terminal_calls/{axis}_{word}_{mode}.json'
        need(e['path'] == expected_path, 'terminal path')
        call_raw = (packet / expected_path).read_bytes()
        need(hashlib.sha256(call_raw).hexdigest() == e['sha256'], 'terminal call SHA')
        outputs = validate_call(json.loads(call_raw), state, forcing, axis, word)
        event = events[(axis, word)]
        expected_outputs = {'state_output_f32_words': [w for row in event['state_output_f32_words'] for w in row],
                            'precip_increment_f32_words': event['precip_increment_f32_words'],
                            'rhog_output_f32_words': event['rhog_output_f32_words']}
        need(outputs == expected_outputs, 'terminal output parity')
    for axis, word in endpoints:
        paths = list((packet / 'raw/sweep').glob(f'{axis}_{word}_native_qnice_applied_*.csv.gz'))
        need(len(paths) == 1, 'endpoint capture inventory')
        capture = gzip.decompress(paths[0].read_bytes()).decode()
        need(capture.rstrip().endswith('status=complete'), 'endpoint capture complete')
        trace = {}
        for row in csv.DictReader(line for line in io.StringIO(capture) if not line.startswith('#')):
            if row['stage'] == 'fd_satadj_inner' and row['k_zero'] == '23':
                need(row['runtime_call'] == '1' and row['one_step_call'] == '1' and row['substep'] == '0' and row['b_zero'] == '0' and row['field'] not in trace, 'capture identity')
                trace[row['field']] = {'dtype': row['dtype'], 'raw_hex': row['raw_hex']}
        need(trace == events[(axis, word)]['trace'], 'endpoint capture trace mismatch')
    return {'calls': len(entries), 'endpoints': len(endpoints), 'words_per_call': 510, 'endpoint_traces': 4}


def fixed_baseline_assets(raw_dir: Path = HERE / 'raw') -> None:
    pins = {'installed_baseline.json': 'ad148d1304b83c9d24b3f28b330279afd528b8158a27c0cd4737e86922204306',
            'private_baseline_capture_off.json': '73fbde1e9d2396d711b5d7ea946386eb17c31b59dce5cccf70cedaa7523e2177',
            'private_baseline_capture_on.json': '73fbde1e9d2396d711b5d7ea946386eb17c31b59dce5cccf70cedaa7523e2177'}
    for name, digest in pins.items():
        need(hashlib.sha256((raw_dir / name).read_bytes()).hexdigest() == digest, 'baseline call SHA: ' + name)


def baseline_capture_link(packet: Path = HERE) -> dict:
    state, forcing = parent_words()
    baseline_call = json.loads((packet / 'raw/private_baseline_capture_on.json').read_bytes())
    outputs = validate_call(baseline_call, state, forcing)
    sweep_data = json.loads((packet / 'raw/sweep/sweep.json').read_bytes())
    need(hashlib.sha256((packet / 'raw/sweep/sweep.json').read_bytes()).hexdigest()
         == SWEEP_SHA, 'baseline sweep SHA')
    validate_sweep(sweep_data)
    rows = [e for e in sweep_data['events'] if e['axis'] == 'th16' and e['word'] == state[15]]
    need(len(rows) == 1, 'baseline sweep event inventory')
    event = rows[0]
    compact = {'state_output_f32_words': [w for row in event['state_output_f32_words'] for w in row],
               'precip_increment_f32_words': event['precip_increment_f32_words'],
               'rhog_output_f32_words': event['rhog_output_f32_words']}
    need(outputs == compact, 'baseline call/sweep output link')
    paths = list((packet / 'raw/baseline_capture').glob('native_qnice_applied_*.csv.gz'))
    need(len(paths) == 1, 'baseline capture inventory')
    capture = gzip.decompress(paths[0].read_bytes()).decode()
    need(capture.rstrip().endswith('status=complete'), 'baseline capture complete')
    trace = {}
    for row in csv.DictReader(line for line in io.StringIO(capture) if not line.startswith('#')):
        if row['stage'] == 'fd_satadj_inner' and row['k_zero'] == '23':
            need(row['runtime_call'] == '1' and row['one_step_call'] == '1'
                 and row['substep'] == '0' and row['b_zero'] == '0'
                 and row['field'] not in trace, 'baseline capture identity')
            trace[row['field']] = {'dtype': row['dtype'], 'raw_hex': row['raw_hex']}
    need(trace == event['trace'], 'baseline capture trace/sweep link')
    return {'state_words_linked': 468, 'precip_words_linked': 3,
            'rhog_words_linked': 39, 'activation_fields_linked': len(trace)}



def fixed_sources() -> None:
    evidence = HERE.parent
    pins = {
        HERE / 'cpp/main.cpp': '0ba1904d6dfd38cbc9256e560354a369f779869b19a6a702eed78c6118e59351',
        HERE / 'cpp/CMakeLists.txt': '985d38a61cffb2f382a3e61f89d9ea15750637c73871e0510f563ec16187e207',
        HERE / 'producer/sweep.py': 'b791ac0eea87ad6dc0760d721fac7295c6de60fa41604a7863b476a9aee7632f',
        evidence / 'native_activation_operands_cpp_ad_2026-11-10/executed_cpp/coordinator.cpp': '6d1ac33a73900e59d49134450c76d226ddbdb54376446f53ac96da3b21ee9c8b',
        evidence / 'native_nc_rate_producer_2026-11-07/executed_cpp/runtime.cpp': 'd0bf029414d0c04c1c06a8b754e486827449b2574febb0ed49e1d0e3c8baab10',
        HERE / 'executed_cpp/ops.cpp': '0c0cb13fc97c66888424121453537af953165746d9e9bdc6e21fa69dccbe9014',
        HERE / 'executed_cpp/kdm6_c_api.cpp': '8c3f4a96dc7078eea8b19806d70c0ec6477debbc2cead04eec32403c26efe049',
    }
    for path, digest in pins.items():
        need(hashlib.sha256(path.read_bytes()).hexdigest() == digest, 'source SHA: ' + str(path))



def fixed_manifest() -> None:
    raw = (HERE / 'manifest.json').read_bytes()
    need(hashlib.sha256(raw).hexdigest() == '6bb7e29a34e99296421a9c32b7cb40a8c9aabfd362f98a6267523cfb9b4478a3', 'manifest SHA')
    manifest = json.loads(raw)
    need(manifest.get('schema') == 'kdm6.native_f32_activation_boundary_packet.v1', 'manifest schema')
    files = manifest['files']
    actual = {str(p.relative_to(HERE)) for d in ('raw', 'cpp', 'producer', 'executed_cpp')
              for p in (HERE / d).rglob('*') if p.is_file()}
    need(set(files) == actual, 'manifest inventory')
    for name, digest in files.items():
        need(hashlib.sha256((HERE / name).read_bytes()).hexdigest() == digest, 'asset SHA: ' + name)
    build = json.loads((HERE / 'raw/build_receipt.json').read_bytes())
    run = json.loads((HERE / 'raw/run_receipt.json').read_bytes())
    need(build.get('schema') == 'kdm6.native_f32_activation_boundary_build.v1' and run.get('schema') == 'kdm6.native_f32_activation_boundary_run.v1', 'receipt schema')
    need(run['input_sha256'] == PARENT_SHA and run['sweep_sha256'] == SWEEP_SHA and run['sweep_events'] == 36 and run['terminal_distinct_endpoints'] == 4, 'run receipt')
    for key, path in (('baseline_parity_sha256', 'raw/baseline_parity.json'), ('sweep_receipt_sha256', 'raw/sweep_receipt.json'), ('terminal_receipt_sha256', 'raw/sweep/terminal_calls/receipt.json')):
        need(run[key] == files[path], 'run receipt asset: ' + key)
    for key in ('installed_dso_sha256', 'capture_dso_sha256'):
        need(build[key] == run[key], 'DSO receipt: ' + key)
    for name, digest in build['flags_sha256'].items():
        need(files[name] == digest, 'build flags SHA')
    for name in ('core_flags.make.gz', 'bridge_flags.make.gz', 'runner_flags.make.gz'):
        flags = gzip.decompress((HERE / 'raw' / name).read_bytes()).decode()
        need('-ffp-contract=off' in flags and '-DNDEBUG' not in flags, 'flags: ' + name)
    for name in ('core_flags.make.gz', 'bridge_flags.make.gz'):
        need('KDM6_NATIVE_SCALAR_CAPTURE' in gzip.decompress((HERE / 'raw' / name).read_bytes()).decode(), 'capture flags')


def replay() -> dict:
    fixed_manifest()
    fixed_sources()
    fixed_baseline_assets()
    return {"baseline": baseline(), "baseline_capture": baseline_capture_link(),
            "sweep": sweep(), "terminal": terminal_calls(),
            "scientific_status": "INCONCLUSIVE", "physical_unit_status": "INCONCLUSIVE"}


def main() -> None:
    print(json.dumps(replay(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
