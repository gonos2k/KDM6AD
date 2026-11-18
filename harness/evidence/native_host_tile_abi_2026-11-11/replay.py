#!/usr/bin/env python3
"""Validate the public receipt and optionally replay the private full tile.

The private file is a native little-endian f32 C-ABI capture; it is not
redistributed. The library must be the precise installed DSO in the receipt.
"""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parent
INPUTS = 'th qv qc qr qi qs qg nccn nc ni nr bg rho pii p delz'.split()
OUTPUTS = INPUTS[:12] + ['rain', 'snow', 'graupel', 'rhog']
TILE_SHA = 'a13d3aafdc4d71ffe5ea7a59616a48f4ea7c6ab3da813b8883bb7277df71ecce'
DSO_SHA = '7adcb6921f6205af66c62720ce9447928a1608f5c261546183b928bebbd9dba7'


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_tile(path):
    import numpy as np
    require(sha256(path) == TILE_SHA, 'private capture SHA-256 mismatch')
    with open(path, 'rb') as f:
        def exact(size):
            data = f.read(size)
            require(len(data) == size, 'truncated capture')
            return data
        im, km, jm, flags, value, call = struct.unpack('<6i', exact(24))
        dt, land, sea = struct.unpack('<3d', exact(24))
        require((im, km, jm, flags, value, call) == (232, 39, 139, 0, 1, 2), 'capture header mismatch')
        require((dt, land, sea) == (20., 10., 10.), 'capture scalar mismatch')
        n, m = im * km * jm, im * jm
        def array(count):
            return np.frombuffer(exact(4 * count), dtype='<f4').copy()
        inputs = [array(n) for _ in INPUTS]
        xland = array(m)
        rc, = struct.unpack('<i', exact(4))
        outputs = [array(n) for _ in range(12)] + [array(m) for _ in range(3)] + [array(n)]
        require(not f.read(1), 'trailing capture data')
        require(rc == 0, 'captured call failed')
    return inputs, xland, outputs


def selected_words(inputs, xland, outputs):
    """Extract the selected column in the capture's (j,k,i) linear layout."""
    def words(a, indices):
        return [f"{int(a.view('u4')[idx]):08x}" for idx in indices]
    indices = [(6 * 39 + k) * 232 + 201 for k in (0, 19, 38)]
    ij = 6 * 232 + 201
    return {
        "native_ij": [203, 149], "packed_ij_zero": [201, 6],
        "levels_zero_based": [0, 19, 38],
        "input_words_hex": {name: words(a, indices) for name, a in zip(INPUTS, inputs)},
        "xland_word_hex": words(xland, [ij])[0],
        "output_words_hex": {name: words(a, indices) for name, a in zip(OUTPUTS[:12], outputs[:12])},
        "increment_words_hex": {name: words(a, [ij])[0] for name, a in zip(OUTPUTS[12:15], outputs[12:15])},
        "rhog_words_hex": words(outputs[15], indices), "return_code": 0,
    }


def replay_private(tile_path, dso_path, selected=None):
    import numpy as np
    require(sha256(dso_path) == DSO_SHA, 'private DSO SHA-256 mismatch')
    inputs, xland, expected = read_tile(tile_path)
    if selected is not None:
        require(selected_words(inputs, xland, expected) == selected, "selected-column summary mismatch")
    outputs = [np.empty_like(a) for a in expected]
    lib = ctypes.CDLL(str(Path(dso_path).resolve()))
    fn = lib.kdm6_step_c
    ptr = ctypes.POINTER(ctypes.c_float)
    fn.argtypes = [ptr] * 16 + [ctypes.c_int] * 3 + [ctypes.c_double] + [ctypes.c_int] * 2 + [ptr] * 12 + [ctypes.POINTER(ctypes.c_void_p), ptr, ctypes.c_double, ctypes.c_double] + [ptr] * 4
    fn.restype = ctypes.c_int
    pointer = lambda a: a.ctypes.data_as(ptr)
    handle = ctypes.c_void_p()
    rc = fn(*map(pointer, inputs), 232, 39, 139, 20., 0, 1,
            *map(pointer, outputs[:12]), ctypes.byref(handle), pointer(xland),
            10., 10., *map(pointer, outputs[12:]))
    require(rc == 0 and handle.value is None, 'private replay call failed')
    counts = {name: int(np.count_nonzero(a.view('u4') != b.view('u4'))) for name, a, b in zip(OUTPUTS, expected, outputs)}
    require(not any(counts.values()), f'private replay mismatch: {counts}')
    return counts


def validate_public_receipts(receipt, selected, full, single, paired):
    """Cross-check receipt arithmetic; these are reported results, not raw data."""
    require(receipt['schema'] == 'kdm6.private_host_tile_abi.v1', 'receipt schema')
    require(receipt['scope'] == 'private host capture; public distribution excludes full native tile and full NetCDF outputs', 'receipt scope')
    require(set(receipt['exclusions']) == {'aborted first-tile input-only pilot', 'failed recursive DYLD interposition trial', 'internal schedule unobserved', 'mp37 parity not tested'}, 'receipt exclusions')
    loaded = receipt['loaded_libraries']
    require(set(loaded) == {'first_accepted_proxy_run', 'paired_on', 'paired_off'}, 'loader labels')
    first, on, off = loaded['first_accepted_proxy_run'], loaded['paired_on'], loaded['paired_off']
    require(first['wrf_pid'] == 25040 and first['observation'] == 'lsof snapshot of first accepted proxy run, not paired-on run', 'first loader attribution')
    require(len(first['snapshot']) == 2 and first['snapshot'][0].endswith('private://native_host_tile_abi_20261111/proxy.dylib') and first['snapshot'][1].endswith('private://installed_dso/libkdm6_c.2.0.0.dylib') and all('wrf.exe 25040 ' in row for row in first['snapshot']), 'first loader paths')
    require(on['runner_pid'] == 25482 and on['wrf_pid'] == 25487 and on['separate_lsof_snapshot'] == 'not captured' and on['evidence'] == 'paired-on captured full tile SHA equals first accepted tile SHA; this is not an independent loader observation', 'paired-on loader attribution')
    require(off['wrf_pid'] == 25647 and len(off['snapshot']) == 1 and 'wrf.exe 25647 ' in off['snapshot'][0] and off['snapshot'][0].endswith('private://installed_dso/libkdm6_c.2.0.0.dylib'), 'paired-off loader path')
    require(receipt['files']['installed_dso']['path'] == 'private://installed_dso/libkdm6_c.2.0.0.dylib', 'installed DSO path')
    historical = receipt['historical_reference']
    require(historical['reference_checkpoint'] == '2025-07-19_00:00:40' and historical['this_case_start'] == '2025-07-19_00:00:00' and historical['reference_compute'] == 'historical isolated f64' and historical['this_compute'] == 'installed f32' and historical['signature_matches_in_tile'] == 0, 'historical lineage')
    comparator = receipt['comparator_provenance']
    require(comparator['sha256'] == 'e90464a63300c7f95665dcf9d75ea6d5765669cee31a48e65006f572140de24b' and comparator['hash_timing'] == 'retrospective: computed after comparisons; no execution-time script hash was recorded', 'comparator provenance')
    require(len(comparator['commands']) == 4, 'comparator command count')
    tile = receipt['tile']
    require(tile['shape_im_km_jm'] == [232, 39, 139], 'tile dimensions')
    im, km, jm = tile['shape_im_km_jm']
    ib, jb = tile['bounds_i'], tile['bounds_j']
    native, packed = tile['native_column'], tile['packed_i_j_zero']
    require([ib[1] - ib[0] + 1, jb[1] - jb[0] + 1] == [im, jm], 'bounds dimensions')
    require([native[0] - ib[0], native[1] - jb[0]] == packed == [201, 6], 'column mapping')
    require(tile['runtime_b_zero'] == packed[0] * jm + packed[1] == 27945, 'runtime index')
    require((tile['call_index'], tile['dt'], tile['value_only'], tile['param_grad_flags'], tile['ncmin_land'], tile['ncmin_sea']) == (2, 20, 1, 0, 10, 10), 'call metadata')
    require(selected['native_ij'] == native and selected['packed_ij_zero'] == packed and selected['levels_zero_based'] == [0, 19, 38], 'selected coordinates')
    require(set(selected['input_words_hex']) == set(INPUTS) and set(selected['output_words_hex']) == set(OUTPUTS[:12]) and set(selected['increment_words_hex']) == set(OUTPUTS[12:15]), 'selected fields')
    words = list(selected['input_words_hex'].values()) + list(selected['output_words_hex'].values()) + [selected['rhog_words_hex']]
    require(all(len(w) == 3 for w in words), 'selected level count')
    words = sum(words, []) + list(selected['increment_words_hex'].values()) + [selected['xland_word_hex']]
    require(all(isinstance(w, str) and len(w) == 8 and all(c in '0123456789abcdef' for c in w) for w in words), 'invalid raw word')
    require(all((int(w, 16) & 0x7f800000) != 0x7f800000 for w in words), 'non-finite selected word')
    require(selected['return_code'] == 0, 'selected return code')
    require(full['dims'] == [im, km, jm] and full['capture_sha256'] == TILE_SHA and (full['dt'], full['land'], full['sea'], full['flags'], full['value'], full['call'], full['original_rc'], full['replay_rc'], full['handle']) == (20, 10, 10, 0, 1, 2, 0, 0, None), 'full replay metadata')
    for result in (full, single):
        counts = result['bit_mismatch_counts']
        require(set(counts) == set(OUTPUTS) and all(type(v) is int and v == 0 for v in counts.values()), 'replay mismatch counts')
    require(single['native_column'] == native and single['packed_ij_zero'] == packed and single['single_call_rc'] == single['tile_call_rc'] == 0, 'single-column receipt')
    require(receipt['full_tile_replay'] == full and receipt['single_column_replay'] == single, 'replay receipt disagreement')
    control = receipt['capture_off_on']
    require(control['timestamps'] == ['2025-07-19_00:00:00', '2025-07-19_00:00:20'], 'saved timestamps')
    require((control['forecast_variables_each_frame'], control['energy_variables_each_frame'], control['numeric_or_char_differences'], control['skipped']) == (254, 5, 0, 0), 'paired aggregate')
    require(control['details'] == paired and set(paired) == {'fcst_0', 'fcst_1', 'energy_0', 'energy_1'}, 'paired receipt disagreement')
    for name, row in paired.items():
        count = 254 if name.startswith('fcst') else 5
        frame = name[-1]
        require(row['returncode'] == 0 and f'frame index {frame}' in row['output'] and f'VARIABLES: {count} common, {count} BITWISE-MATCH, 0 DIFFER, 0 non-numeric' in row['output'] and 'RESULT: STRICT BITWISE PASS' in row['output'], 'paired comparison output')
    require(receipt['files']['capture_uncompressed']['sha256'] == TILE_SHA and receipt['files']['installed_dso']['sha256'] == DSO_SHA, 'artifact receipt hashes')
    return True


MANIFEST_SHA = '9fb9463b16a9a9b87acc360a343176a89af93bb545fd4f63d81c4062e2c2d481'
ASSETS = {
    'producer/proxy.c', 'producer/strict_bitwise_nc_executed.py',
    'raw/column_vs_556.json', 'raw/full_tile_replay_summary.json',
    'raw/host_tile_amendment.json', 'raw/host_tile_receipt.json',
    'raw/nearest_signature.json', 'raw/paired_host_outputs.json',
    'raw/producer_source_hashes.json', 'raw/selected_column.json',
    'raw/single_column_summary.json',
}
INDEPENDENT_PINS = {
    'raw/host_tile_receipt.json': 'd2818450d7e166f0a435be824c39c4e04ba8d66a34fa007784a49a173f9a0d6d',
    'raw/host_tile_amendment.json': '814d24b13e2d0fd7671e45cef57ab182afa238303b019258457cc87a55a803bc',
    'raw/selected_column.json': 'e9ce79d45090218c43754a54ff078373e7e69335fdc8f3e9eea2d7f285e55232',
    'producer/strict_bitwise_nc_executed.py': 'e90464a63300c7f95665dcf9d75ea6d5765669cee31a48e65006f572140de24b',
}


def validate_manifest(root=ROOT):
    path = root / 'manifest.json'
    require(sha256(path) == MANIFEST_SHA, 'manifest SHA-256 mismatch')
    manifest = json.loads(path.read_text())
    require(manifest['schema'] == 'kdm6.native_host_tile_abi_public_packet.v1', 'manifest schema')
    require(set(manifest['files']) == ASSETS, 'manifest asset set')
    for name, digest in INDEPENDENT_PINS.items():
        require(sha256(root / name) == digest, f'independent asset SHA-256 mismatch: {name}')
    for name, digest in manifest['files'].items():
        require(sha256(root / name) == digest, f'asset SHA-256 mismatch: {name}')


def load_records(root=ROOT):
    validate_manifest(root)
    raw = root / 'raw'
    names = ('host_tile_amendment.json', 'selected_column.json', 'full_tile_replay_summary.json', 'single_column_summary.json', 'paired_host_outputs.json')
    records = tuple(json.loads((raw / name).read_text()) for name in names)
    require(sha256(raw / 'selected_column.json') == records[0]['files']['selected_summary']['sha256'], 'selected summary SHA-256 mismatch')
    require(records[0]['private_amended_receipt_original_sha256'] == 'b05be0d28e2fbfff21ec38b6bbf0e7887c0ae5e0c915a87c965eeb2e81790799' and records[0]['amendment']['original_sha256'] == '3b904842c49b4a59164cc3252b9b5460d634202164865686057889d670f0f32d', 'private receipt SHA-256 mismatch')
    sources = json.loads((raw / 'producer_source_hashes.json').read_text())
    require(sources['schema'] == 'kdm6.native_host_tile_producer_sources.v1' and sources['public_proxy_view_is_executed_byte_identity'] is False and sources['public_proxy_view_sha256'] == sha256(root / 'producer/proxy.c') and sources['executed_private_source_sha256']['proxy.c'] != sources['public_proxy_view_sha256'] and sources['executed_private_source_sha256']['strict_bitwise_nc.py'] == sha256(root / 'producer/strict_bitwise_nc_executed.py'), 'producer source provenance')
    comparison = json.loads((raw / 'column_vs_556.json').read_text())
    require(set(comparison) == set(INPUTS), 'historical comparison fields')
    for name, row in comparison.items():
        require(type(row['equal']) is int and type(row['different']) is int and row['equal'] >= 0 and row['different'] > 0 and row['equal'] + row['different'] == 39, 'historical comparison counts')
        first = row['first_different']
        require(0 <= first['level_zero_based'] < 39 and first['host_word'] != first['reference_word'], 'historical first difference')
        if first['level_zero_based'] in (0, 19, 38):
            require(first['host_word'] == records[1]['input_words_hex'][name][(0, 19, 38).index(first['level_zero_based'])], 'historical selected word')
    return records


def public_summary(records=None):
    if records is None:
        records = load_records()
    validate_public_receipts(*records)
    receipt, selected, full, single, paired = records
    return {
        'schema': 'kdm6.native_host_tile_abi_public_replay.v1',
        'scope': 'public metadata consistency only; host invocation not independently authenticated',
        'tile_shape_im_km_jm': receipt['tile']['shape_im_km_jm'],
        'tile_call_index': receipt['tile']['call_index'],
        'native_column': selected['native_ij'],
        'packed_ij_zero': selected['packed_ij_zero'],
        'runtime_b_zero': receipt['tile']['runtime_b_zero'],
        'recorded_full_tile_mismatch_counts': full['bit_mismatch_counts'],
        'recorded_single_column_mismatch_counts': single['bit_mismatch_counts'],
        'recorded_paired_host_times': receipt['capture_off_on']['timestamps'],
        'recorded_forecast_variables_each_frame': receipt['capture_off_on']['forecast_variables_each_frame'],
        'recorded_energy_variables_each_frame': receipt['capture_off_on']['energy_variables_each_frame'],
        'recorded_historical_reference_signature_matches': receipt['historical_reference']['signature_matches_in_tile'],
        'private_full_tile_reexecution': 'SKIPPED unless private tile and exact DSO are supplied',
        'public_selected_levels_zero_based': selected['levels_zero_based'],
        'public_assets_verified': len(ASSETS),
        'scientific_status': 'INCONCLUSIVE',
        'physical_unit_status': 'INCONCLUSIVE',
    }


def main():
    records = load_records()
    summary = public_summary(records)
    tile, dso = os.environ.get('PRIVATE_TILE_PATH'), os.environ.get('PRIVATE_DSO_PATH')
    require(bool(tile) == bool(dso), 'set both PRIVATE_TILE_PATH and PRIVATE_DSO_PATH')
    if tile:
        replay_private(tile, dso, records[1])
        print(json.dumps({**summary, 'private_full_tile_reexecution': 'PASSED'}, indent=2, sort_keys=True))
    else:
        print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
