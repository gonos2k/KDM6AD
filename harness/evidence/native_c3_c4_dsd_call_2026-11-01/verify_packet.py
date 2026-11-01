#!/usr/bin/env python3
"""Offline checks of selected native evidence; packet digest must be supplied independently."""
import argparse
import hashlib
import json
import math
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
SOURCE_MANIFEST = ROOT / 'source_manifest.json'
SOURCE_FILES = {
    'CMakeLists.txt': REPO / 'libtorch/CMakeLists.txt',
    'bridge/kdm6_c_api.cpp': REPO / 'libtorch/bridge/kdm6_c_api.cpp',
    'src/runtime.cpp': ROOT / 'executed_overlay/runtime.cpp.txt',
    'src/coordinator.cpp': ROOT / 'executed_overlay/coordinator.cpp.txt',
    'src/sedimentation.cpp': ROOT / 'executed_overlay/sedimentation.cpp.txt',
    'src/sedimentation_conservative.cpp': ROOT / 'executed_overlay/sedimentation_conservative.cpp.txt',
}

STAGES = {
    "abi_ingress": {"qi", "ni", "p", "den"},
    "converted_ingress": {"scalar_ingress_state->qi", "scalar_ingress_state->ni",
                          "scalar_ingress_state->t", "scalar_ingress_state->qv",
                          "scalar_ingress_forcing->p", "scalar_ingress_forcing->den"},
    "step_entry": {"state.qi", "state.ni", "state.t", "state.qv", "forcing.p", "forcing.den"},
    "c3_in": {"pre.supcol", "pre.supsat", "pre.rh_ice", "prevp", "state.ni", "forcing.dend"},
    "c3_out": {"icenuc.pinud", "icenuc.ninud", "icenuc.ifsat"},
    "c4_in": {"state.qi", "state.qs", "state.qg", "n0i", "n0so", "n0go", "s.n0sfac_field",
              "work1_ice", "pre.work2", "pre.precg2", "s.rslope_s", "s.rslope2_s",
              "s.rslopeb_s", "s.rslopemu_s", "s.rslope_g", "s.rslope2_g", "s.rslopeb_g",
              "s.rslopemu_g", "s.rslope2_i", "s.rslopemu_i"},
    "c4_out": {"depsub.pidep", "depsub.psdep", "depsub.pgdep", "depsub.ifsat",
               "depsub.ice_complete_sublim"},
    "pre_limit": {"cold_out.pidep", "cold_out.pinud", "cold_out.ninud"},
    "limited": {"scaled.cold.pinud", "scaled.cold.ninud", "scaled.cold.pidep",
                "scaled.cold.psdep", "scaled.cold.pgdep", "scaled.cold.psaut",
                "scaled.cold.praci", "scaled.cold.psaci", "scaled.cold.pgaci",
                "scaled.cold.piacw", "scaled.cold.pmulcs", "scaled.cold.pmulcg",
                "scaled.cold.pmulrs", "scaled.cold.pmulrg", "scaled.cold.nraci",
                "scaled.cold.nsaci", "scaled.cold.ngaci", "scaled.cold.niacr",
                "scaled.cold.nsaut", "scaled.cold.nmulcs", "scaled.cold.nmulcg",
                "scaled.cold.nmulrs", "scaled.cold.nmulrg"},
    "state_in": {"working.qi", "working.ni"},
    "state_out": {"new_state.qi", "new_state.ni"},
    "dsd_in": {"new_state.qi", "new_state.ni", "forcing.dend", "ncmin_gate"},
    "dsd_out": {"new_state.qi", "new_state.ni"},
}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def verify_sources():
    pins = json.loads(SOURCE_MANIFEST.read_bytes())
    need(isinstance(pins, dict) and bool(pins), 'source manifest inventory')
    for relative, expected in pins.items():
        path = REPO / relative
        need(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected,
             'source digest ' + relative)


def number(row):
    dtype, raw = row['dtype'], row['raw_hex']
    need(dtype in ('f32', 'f64', 'bool') and isinstance(raw, str) and
         re.fullmatch(r'[0-9a-f]+', raw) is not None, 'row encoding')
    bits = int(raw, 16)
    if dtype == 'bool':
        need(bits in (0, 1), 'boolean encoding')
        return bool(bits)
    size = 4 if dtype == 'f32' else 8
    need(bits < 1 << (8 * size), 'bit width')
    v = struct.unpack('<f' if size == 4 else '<d', bits.to_bytes(size, 'little'))[0]
    need(math.isfinite(v), 'nonfinite scalar')
    return v


def verify(raw, pinned, *, check_local_sources=True):
    need(re.fullmatch(r'[0-9a-f]{64}', pinned) is not None, 'invalid independent sha256 pin')
    digest = hashlib.sha256(raw).hexdigest()
    need(digest == pinned, 'packet SHA-256 mismatch')
    p = json.loads(raw)
    need(p['schema'] == 'kdm6.native_c3_c4_dsd_selected.v1' and
         p['scientific_status'] == 'INCONCLUSIVE', 'schema or scientific status')
    c = p['coordinate']
    need(c['native_ijk_1based'] == [[164, 242, 21], [164, 242, 23]] and
         c['batch_b_zero'] == 22617 and c['k_zero'] == [20, 22] and
         c['tile2_B'] == 32248 and c['tile2_its_ite_jts_jte'] == [2, 233, 143, 281], 'coordinate')
    off, on = p['run_off'], p['run_on']
    for k in ('historical_plan_sha256', 'origin_sha256', 'startup_sha256', 'endpoint_sha256',
              'historical_endpoint_sha256', 'executable_sha256', 'dso_sha256', 'isolated_build_receipt_sha256'):
        need(re.fullmatch(r'[0-9a-f]{64}', off[k]) is not None and off[k] == on[k], 'paired hash ' + k)
    for field in ('source_sha256', 'compiled_source_sha256'):
        hashes = off[field]
        need(isinstance(hashes, dict) and bool(hashes) and hashes == on[field] and all(isinstance(x, str) and re.fullmatch(r'[0-9a-f]{64}', x) for x in hashes.values()), 'paired ' + field)
    build = p['isolated_build_receipt']
    need(build['schema'] == 'kdm6.isolated_factorial_qr_capture_build.v1', 'build receipt schema')
    # The exported receipt is a JSON object. This campaign's original receipt uses
    # sorted, two-space JSON plus one final newline; verify that exact encoding.
    build_bytes = (json.dumps(build, indent=2, sort_keys=True) + '\n').encode('utf-8')
    need(hashlib.sha256(build_bytes).hexdigest() == off['isolated_build_receipt_sha256'], 'build receipt digest')
    need(build['dso_sha256'] == off['dso_sha256'] and build['source_sha256'] == off['compiled_source_sha256'], 'build receipt identity')
    if check_local_sources:
        need(set(build['source_sha256']) == set(SOURCE_FILES), 'compiled source inventory')
        for name, path in SOURCE_FILES.items():
            need(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() ==
                 build['source_sha256'][name], 'compiled source snapshot ' + name)
        runner = ROOT / 'run_private.py'
        exporter = ROOT / 'export_private.py'
        need(off['private_runner_sha256'] == on['private_runner_sha256'] and
             runner.is_file() and hashlib.sha256(runner.read_bytes()).hexdigest() ==
             off['private_runner_sha256'], 'private runner source snapshot')
        need(exporter.is_file() and hashlib.sha256(exporter.read_bytes()).hexdigest() ==
             p['exporter_sha256'], 'private exporter source snapshot')
        expected_runtime_sources = {
            'harness/native_live_stepper.py', 'harness/run_ss_case.py',
            'libtorch/CMakeLists.txt', 'libtorch/bridge/kdm6_c_api.cpp',
            'libtorch/src/coordinator.cpp', 'libtorch/src/runtime.cpp',
        }
        need(set(off['source_sha256']) == expected_runtime_sources,
             'executed public source inventory')
        for relative, expected in off['source_sha256'].items():
            path = REPO / relative
            need(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected,
                 'executed public source ' + relative)
    members = build['archive_members']
    expected_members = {name + '.cpp.o' for name in ('cloud_dsd', 'cold', 'coordinator', 'melt_freeze', 'ops', 'progb', 'runtime', 'satadj', 'sedimentation', 'sedimentation_conservative', 'slope', 'state', 'thermo', 'warm')}
    need(set(members) == expected_members, 'archive member inventory')
    replaced = {'coordinator.cpp.o', 'runtime.cpp.o'}
    for name, hashes in members.items():
        need(set(hashes) == {'historical_sha256', 'diagnostic_sha256'} and all(isinstance(x, str) and re.fullmatch(r'[0-9a-f]{64}', x) for x in hashes.values()), 'archive member hash')
        if name in replaced:
            need(hashes['diagnostic_sha256'] == build['rebuilt_object_sha256'][name], 'rebuilt archive member')
        else:
            need(hashes['historical_sha256'] == hashes['diagnostic_sha256'], 'preserved archive member')
    need('-ffp-contract=off' in build['compile_flags'] and '-ffp-contract=off' in build['bridge_compile_flags'], 'build contraction flags')
    need(off['endpoint_sha256'] == off['historical_endpoint_sha256'] and
         off['historical_endpoint_match'] is True and on['historical_endpoint_match'] is True,
         'historical endpoint')
    traces = p['host_selected_trace']
    need(traces['off_v6'] == traces['on_v6'], 'host selected trace differs')
    th = p['host_trace_sha256']
    need(all(re.fullmatch(r'[0-9a-f]{64}', th[x]) for x in ('off_v6', 'on_v6')), 'host trace hashes')
    native = {}
    for rec in traces['on_v6']:
        key = (rec['stage'], tuple(rec['native_ijk_1based']))
        need(rec['step'] == 3 and key not in native and len(rec['fields']) == len(rec['raw_hex']) and
             len(set(rec['fields'])) == len(rec['fields']), 'host trace record')
        need(all(isinstance(h, str) and re.fullmatch(r'[0-9a-f]{8}', h) for h in rec['raw_hex']), 'host raw bits')
        native[key] = dict(zip(rec['fields'], rec['raw_hex']))
    need(set(native) == {(s, (164, 242, k)) for s in ('MP_INPUT', 'MP_OUTPUT') for k in (21, 23)}, 'host trace inventory')
    groups = {}
    rowkeys = {'one_step_call', 'runtime_call', 'substep', 'b_zero', 'k_zero', 'B', 'K', 'stage', 'field', 'dtype', 'raw_hex'}
    for row in p['selected_rows']:
        need(set(row) == rowkeys, 'row schema')
        for name in ('one_step_call', 'runtime_call', 'substep', 'b_zero', 'k_zero', 'B', 'K'):
            need(isinstance(row[name], str) and row[name].isdigit(), 'row index ' + name)
        need(int(row['b_zero']) == 22617 and int(row['B']) == 32248 and int(row['K']) == 39 and int(row['k_zero']) in (20, 22), 'row coordinate')
        stage, field = row['stage'], row['field']
        need(stage in STAGES and field in STAGES[stage], 'stage inventory')
        need(row['dtype'] == 'bool' if field in ('icenuc.ifsat', 'depsub.ifsat', 'depsub.ice_complete_sublim') else row['dtype'] in ('f32', 'f64'), 'field dtype')
        number(row)
        identity = tuple(row[x] for x in ('one_step_call', 'runtime_call', 'substep', 'k_zero'))
        group = groups.setdefault(identity, {})
        need((stage, field) not in group, 'duplicate selected row')
        group[(stage, field)] = row
    need(groups, 'no selected calls')
    calls = {identity[:3] for identity in groups}
    need(len({x[1] for x in calls}) == 1 and set(groups) == {call + (str(k),) for call in calls for k in (20, 22)}, 'call/level inventory')
    expected = {(stage, field) for stage, fields in STAGES.items() for field in fields}
    metadata = p['capture_metadata']
    need(len(metadata) == len(p['capture_files']) and {m['name'] for m in metadata} == {f['name'] for f in p['capture_files']}, 'capture metadata inventory')
    times = {}
    descriptors = {f['name']: f for f in p['capture_files']}
    for m in metadata:
        need(len(m['rows']) == 1, 'one timestep per capture')
        row = m['rows'][0]
        need(set(row) == rowkeys and row['stage'] == 'meta' and row['field'] == 'dtcld' and row['dtype'] == 'f64' and number(row) > 0, 'timestep metadata')
        call = tuple(row[x] for x in ('one_step_call', 'runtime_call', 'substep'))
        need(list(call) + [row['B'], row['K']] == descriptors[m['name']]['identity'], 'metadata capture identity')
        need(call not in times, 'duplicate timestep call')
        times[call] = number(row)
    need(calls <= set(times), 'selected call timestep')
    diagnostics = []
    for identity, rows in sorted(groups.items()):
        need(set(rows) == expected, 'incomplete stage inventory')
        def get(stage, field):
            return rows[(stage, field)]

        def val(stage, field):
            return number(get(stage, field))

        def same(a, b):
            return (a['dtype'], int(a['raw_hex'], 16)) == (b['dtype'], int(b['raw_hex'], 16))
        k = int(identity[3]) + 1
        for host, abi, conv in [('QI', 'qi', 'scalar_ingress_state->qi'), ('NI', 'ni', 'scalar_ingress_state->ni'), ('P', 'p', 'scalar_ingress_forcing->p'), ('DEN', 'den', 'scalar_ingress_forcing->den')]:
            a, b = get('abi_ingress', abi), get('converted_ingress', conv)
            need(a['dtype'] == 'f32' and int(a['raw_hex'], 16) == int(native[('MP_INPUT', (164, 242, k))][host], 16), 'host to ABI ' + host)
            expected_bits = int(a['raw_hex'], 16) if b['dtype'] == 'f32' else int.from_bytes(struct.pack('<d', number(a)), 'little')
            need(int(b['raw_hex'], 16) == expected_bits, 'ABI converted ' + host)
        # Converted ingress precedes sedimentation; step entry is after it.
        # Both inventories are required, but their state values need not match.
        active = (val('c3_in','pre.supcol') > 8 and val('c3_in','pre.supsat') > 0) or val('c3_in','pre.rh_ice') > 1.08
        dt = times[identity[:3]]
        def rnd(v, dtype):
            return struct.unpack('<f', struct.pack('<f', v))[0] if dtype == 'f32' else v
        dtype = get('c3_in', 'pre.supsat')['dtype']
        satdt = rnd(val('c3_in','pre.supsat') / dt, dtype)
        ifsat = active and abs(rnd(val('c3_in','prevp') + val('c3_out','icenuc.pinud'), dtype)) >= abs(satdt)
        need(val('c3_out','icenuc.ifsat') == ifsat, 'C3 saturation branch')
        # C3 source-order f64 arithmetic with the process's f32 Minud constant.
        def f32(x):
            return struct.unpack('<f', struct.pack('<f', x))[0]
        pi32 = f32(4.0 * f32(math.atan(1.0)))
        radius = f32(10.0e-6)
        minud = f32(f32(f32(f32(4.0 / 3.0) * pi32) * 500.0) * f32(f32(radius * radius) * radius))
        supcol, ni, den = (val('c3_in', 'pre.supcol'), val('c3_in', 'state.ni'), val('c3_in', 'forcing.dend'))
        nid_raw = (0.005 * math.exp(0.304 * supcol)) * 1000.0
        nid = min(max(nid_raw, 0.0), 500000.0)
        deficit_rate = (nid - ni) / dt
        raw_pinud = deficit_rate / max(den, 1e-9) * minud
        half_sat = 0.5 * satdt
        remaining = satdt - val('c3_in', 'prevp')
        selected = min(min(raw_pinud, half_sat), remaining)
        expected_pinud = selected if active and nid > ni else 0.0
        expected_ninud = selected * max(den, 1e-9) / minud if active and nid > ni else 0.0
        need(val('c3_out','icenuc.pinud') == expected_pinud and val('c3_out','icenuc.ninud') == expected_ninud, 'C3 source-order candidates')
        if not active:
            need(val('c3_out','icenuc.pinud') == 0 and val('c3_out','icenuc.ninud') == 0 and not val('c3_out','icenuc.ifsat'), 'C3 inactive output')
        if val('c3_in','pre.supcol') <= 0 or val('c4_in','state.qi') <= 0 or val('c3_out','icenuc.ifsat'):
            need(val('c4_out','depsub.pidep') == 0 and not val('c4_out','depsub.ice_complete_sublim'), 'C4 inactive ice output')
        # Independently replay the ice candidate, limiter and exact-equality
        # sublimation branch when all contributing tensors are f64.
        ice_fields = [('c4_in', x) for x in ('state.qi', 'n0i', 's.rslopemu_i', 's.rslope2_i', 'work1_ice')]
        ice_fields += [('c3_in', x) for x in ('pre.rh_ice', 'pre.supsat', 'prevp')]
        ice_fields += [('c3_out', 'icenuc.pinud')]
        if all(get(*x)['dtype'] == 'f64' for x in ice_fields):
            qi = val('c4_in','state.qi')
            raw_ice = (4.0 * val('c4_in','n0i') * 1.0 * val('c4_in','s.rslopemu_i') *
                       val('c4_in','s.rslope2_i') * (val('c3_in','pre.rh_ice') - 1.0) /
                       max(val('c4_in','work1_ice'), 1e-9))
            supice = satdt - val('c3_in','prevp') - val('c3_out','icenuc.pinud')
            cap = max(max(max(raw_ice, -qi / dt), 0.5 * satdt), supice) if raw_ice < 0 else min(min(raw_ice, 0.5 * satdt), supice)
            entered = val('c3_in','pre.supcol') > 0 and qi > 0 and not val('c3_out','icenuc.ifsat')
            need(val('c4_out','depsub.pidep') == (cap if entered else 0), 'C4 ice candidate and cap')
            need(val('c4_out','depsub.ice_complete_sublim') == (entered and raw_ice == -qi / dt and raw_ice < 0), 'C4 complete sublimation branch')
        c4_active = val('c3_in','pre.supcol') > 0
        running = rnd(val('c3_in','prevp') + val('c3_out','icenuc.pinud'), dtype)
        saturated = val('c3_out','icenuc.ifsat')
        for species, field in (('qi','pidep'), ('qs','psdep'), ('qg','pgdep')):
            entered = c4_active and val('c4_in','state.' + species) > 0 and not saturated
            rate = val('c4_out','depsub.' + field)
            if not entered:
                need(rate == 0, 'C4 inactive ' + field)
            running = rnd(running + rate, dtype)
            saturated = saturated or (entered and abs(running) >= abs(satdt))
        need(val('c4_out','depsub.ifsat') == saturated, 'C4 saturation branch')
        for f in ('pinud','ninud','pidep'):
            src = 'icenuc.' if f in ('pinud','ninud') else 'depsub.'
            stage = 'c3_out' if f in ('pinud','ninud') else 'c4_out'
            need(same(get(stage, src+f), get('pre_limit','cold_out.'+f)), 'candidate handoff ' + f)
            need(same(get('pre_limit','cold_out.'+f),
                      get('limited','scaled.cold.'+f)),
                 'selected limited rate unchanged ' + f)
        need(same(get('c3_in','state.ni'),get('state_in','working.ni')) and
             same(get('c4_in','state.qi'),get('state_in','working.qi')),
             'selected working-state handoff')
        # Reclassification, satadj and cleanup lie between these stages. Equality
        # is an observed property of the two selected cells, not a general rule.
        for field in ('qi','ni'):
            need(same(get('state_out','new_state.'+field),
                      get('dsd_in','new_state.'+field)),
                 'selected post-update to DSD input ' + field)
        need(same(get('dsd_in','new_state.qi'),get('dsd_out','new_state.qi')), 'DSD mass unchanged')
        for field in ('qi', 'ni'):
            bits = int.from_bytes(struct.pack('<f', val('dsd_out', 'new_state.' + field)), 'little')
            need(bits == int(native[('MP_OUTPUT', (164, 242, k))][field.upper()], 16), 'DSD to host output ' + field)
        # F32-generated pidni, with source-order f64 ratio and f32 1/3.
        cmi = f32(f32(pi32 * 500.0) / 6.0)
        pidni = f32(cmi * 6.0)
        q, n, density = (val('dsd_in','new_state.qi'), val('dsd_in','new_state.ni'), val('dsd_in','forcing.dend'))
        gate = q >= 1e-15 and n >= val('dsd_in','ncmin_gate')
        lamda = math.exp(math.log(max(pidni * n / max(q * density, 1e-30), 1e-30)) * f32(1.0/3.0)) if gate else None
        interior = gate and 9.08e3 < lamda < 1.82e6
        if interior:
            need(same(get('dsd_in','new_state.ni'), get('dsd_out','new_state.ni')), 'DSD interior number')
        diagnostics.append({'native_k_1based': k, 'selected_rate_and_stage_handoffs_equal': True,
                            'c3_active': active, 'c3_nid': nid, 'c3_deficit_rate': deficit_rate,
                            'c3_raw_pinud': raw_pinud, 'c3_half_satdt': half_sat, 'c3_remaining': remaining,
                            'c3_selected_pinud': expected_pinud, 'c3_selected_ninud': expected_ninud,
                            'c4_raw_pidep': raw_ice if all(get(*x)['dtype'] == 'f64' for x in ice_fields) else None,
                            'c4_selected_pidep': val('c4_out','depsub.pidep'), 'dsd_lamda': lamda, 'dsd_interior': interior})
        if val('dsd_in','new_state.qi') < 1e-15 or val('dsd_in','new_state.ni') < val('dsd_in','ncmin_gate'):
            need(same(get('dsd_in','new_state.ni'),get('dsd_out','new_state.ni')), 'DSD inactive number')
    files = p['capture_files']
    need(len(files) >= len(calls) and len({f['name'] for f in files}) == len(files), 'capture inventory')
    for f in files:
        need(re.fullmatch(r'[0-9a-f]{64}', f['sha256']) is not None and f['total_rows'] == f['scalar_rows'] + f['metadata_rows'] and f['metadata_rows'] == 1, 'capture receipt')
        need(on['capture_files'].get(f['name']) == f['sha256'], 'capture hash receipt')
    need(set(on['capture_files']) == {f['name'] for f in files}, 'capture file names')
    need(len(p['unique_batch_checks']) == len(calls) and all(x['batch_b_zero'] == 22617 and x['six_host_fields_exact'] is True and x['unique_candidate_count'] == 1 for x in p['unique_batch_checks']), 'unique batch receipts')
    need(any('QNICE' in x for x in p['limitations']), 'unit limitation')
    return {'packet_sha256': digest, 'selected_calls': len(calls), 'selected_rows': len(p['selected_rows']), 'local_source_snapshots_verified': check_local_sources, 'diagnostics': diagnostics, 'scientific_status': 'INCONCLUSIVE', 'stage_timing': 'converted ingress precedes sedimentation; step entry follows sedimentation', 'limitations': ['Full trace, capture, build inputs, archive members and endpoint bytes are not redistributed; their hashes are attestations, not independently verified artifacts.', 'C4 snow/graupel candidates, the full applied budget and active DSD boundary snaps are not fully replayed.', 'Raw QNICE physical basis remains uncertified.']}


def main():
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument('packet', type=Path)
    a.add_argument('--sha256', required=True, help='independently pinned SHA-256 of exact packet bytes')
    args = a.parse_args()
    try:
        verify_sources()
        raw = args.packet.read_bytes()  # exactly one read of the verified packet
        print(json.dumps(verify(raw, args.sha256), indent=2))
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
        print('INVALID: ' + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
