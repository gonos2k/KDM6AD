#!/usr/bin/env python3
"""Mutation tests replay the actual paired packet when it is supplied."""
import copy
import hashlib
import json
from pathlib import Path
import unittest

from verify_packet import STAGES, verify, verify_sources

PACKET = Path(__file__).with_name('selected_packet.json')
PIN = Path(__file__).with_name('selected_packet.sha256')


def encode(packet):
    raw = json.dumps(packet, sort_keys=True, separators=(',', ':')).encode()
    return raw, hashlib.sha256(raw).hexdigest()


def synthetic_packet():
    h = 'a' * 64
    run = {key: h for key in ('historical_plan_sha256', 'origin_sha256', 'startup_sha256',
          'endpoint_sha256', 'historical_endpoint_sha256', 'executable_sha256', 'dso_sha256',
          'isolated_build_receipt_sha256')}
    run.update(source_sha256={'runtime': h}, compiled_source_sha256={'runtime': h},
               historical_endpoint_match=True, capture_files={'capture.csv': h})
    members = {name + '.cpp.o': {'historical_sha256': h, 'diagnostic_sha256': h}
               for name in ('cloud_dsd', 'cold', 'coordinator', 'melt_freeze', 'ops', 'progb', 'runtime', 'satadj', 'sedimentation', 'sedimentation_conservative', 'slope', 'state', 'thermo', 'warm')}
    build = {'schema':'kdm6.isolated_factorial_qr_capture_build.v1', 'dso_sha256':h,
             'source_sha256':{'runtime':h}, 'archive_members':members,
             'rebuilt_object_sha256':{'runtime.cpp.o':h, 'coordinator.cpp.o':h},
             'compile_flags':'-ffp-contract=off', 'bridge_compile_flags':'-ffp-contract=off'}
    run['isolated_build_receipt_sha256'] = hashlib.sha256((json.dumps(build, indent=2, sort_keys=True) + '\n').encode()).hexdigest()
    trace = [{'stage': stage, 'step': 3, 'native_ijk_1based': [164, 242, k],
              'fields': ['QI','NI','P','DEN'], 'raw_hex': ['00000000'] * 4}
             for k in (21, 23) for stage in ('MP_INPUT', 'MP_OUTPUT')]
    rows = []
    for k in (20, 22):
        for stage, fields in STAGES.items():
            for field in fields:
                dtype = 'f32' if stage == 'abi_ingress' else ('bool' if field in
                    ('icenuc.ifsat', 'depsub.ifsat', 'depsub.ice_complete_sublim') else 'f64')
                rows.append(dict(one_step_call='1', runtime_call='1', substep='1', b_zero='22617',
                            k_zero=str(k), B='32248', K='39', stage=stage, field=field,
                            dtype=dtype, raw_hex='0'))
    # Sedimentation sits between these two stages: differing values are allowed.
    next(r for r in rows if r['stage'] == 'step_entry' and r['field'] == 'state.qi')['raw_hex'] = '3ff0000000000000'
    meta = dict(one_step_call='1', runtime_call='1', substep='1', b_zero='0', k_zero='0',
                B='32248', K='39', stage='meta', field='dtcld', dtype='f64', raw_hex='4034000000000000')
    return {'schema':'kdm6.native_c3_c4_dsd_selected.v1', 'scientific_status':'INCONCLUSIVE',
            'coordinate':{'native_ijk_1based':[[164,242,21],[164,242,23]],
                          'batch_b_zero':22617,'k_zero':[20,22],'tile2_B':32248,
                          'tile2_its_ite_jts_jte':[2,233,143,281]},
            'run_off':copy.deepcopy(run), 'run_on':copy.deepcopy(run), 'isolated_build_receipt':build,
            'host_trace_sha256':{'off_v6':h,'on_v6':h},
            'host_selected_trace':{'off_v6':copy.deepcopy(trace),'on_v6':copy.deepcopy(trace)},
            'selected_rows':rows,
            'capture_files':[{'name':'capture.csv','sha256':h,'total_rows':2,'scalar_rows':1,
                              'metadata_rows':1,'identity':['1','1','1','32248','39']}],
            'capture_metadata':[{'name':'capture.csv','rows':[meta]}],
            'unique_batch_checks':[{'batch_b_zero':22617,'six_host_fields_exact':True,'unique_candidate_count':1}],
            'limitations':['raw QNICE physical basis remains uncertified']}


class SyntheticStructure(unittest.TestCase):
    def test_replay_and_rehashed_mutations(self):
        packet = synthetic_packet()
        raw, pin = encode(packet)
        self.assertEqual(verify(raw, pin, check_local_sources=False)['selected_calls'], 1)
        def corrupt_member(p):
            p['isolated_build_receipt']['archive_members']['cold.cpp.o']['diagnostic_sha256'] = 'b' * 64
            digest = hashlib.sha256((json.dumps(p['isolated_build_receipt'], indent=2, sort_keys=True) + '\n').encode()).hexdigest()
            p['run_off']['isolated_build_receipt_sha256'] = digest
            p['run_on']['isolated_build_receipt_sha256'] = digest
        for mutate in (corrupt_member, lambda p: p['run_off']['source_sha256'].__setitem__('runtime', 'x'),
                       lambda p: p['capture_metadata'][0]['rows'][0].__setitem__('substep', '2'),
                       lambda p: p['selected_rows'].pop()):
            changed = copy.deepcopy(packet)
            mutate(changed)
            with self.assertRaises(ValueError):
                verify(*encode(changed), check_local_sources=False)


@unittest.skipUnless(PACKET.is_file() and PIN.is_file(), 'paired packet and independently pinned digest not yet supplied')
class PacketReplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = PACKET.read_bytes()
        cls.pin = PIN.read_text().split()[0]
        cls.packet = json.loads(cls.raw)

    def test_actual_packet(self):
        verify_sources()
        self.assertEqual(verify(self.raw, self.pin)['scientific_status'], 'INCONCLUSIVE')

    def reject(self, mutate):
        packet = copy.deepcopy(self.packet)
        mutate(packet)
        raw, digest = encode(packet)  # adversary recomputes the outer digest
        with self.assertRaises((ValueError, KeyError)):
            verify(raw, digest)

    def test_rehashed_semantic_mutations(self):
        def mutate_row(stage, field):
            def mutation(p):
                row = next(x for x in p['selected_rows'] if x['stage'] == stage and x['field'] == field)
                row['raw_hex'] = format(int(row['raw_hex'], 16) ^ 1, 'x')
            return mutation
        def coupled_candidate(p):
            row = next(x for x in p['selected_rows'] if x['stage'] == 'c4_out' and x['field'] == 'depsub.pidep')
            call = tuple(row[x] for x in ('one_step_call', 'runtime_call', 'substep', 'k_zero'))
            other = next(x for x in p['selected_rows'] if x['stage'] == 'pre_limit' and x['field'] == 'cold_out.pidep' and tuple(x[k] for k in ('one_step_call', 'runtime_call', 'substep', 'k_zero')) == call)
            row['raw_hex'] = format(int(row['raw_hex'], 16) ^ 1, 'x')
            other['raw_hex'] = row['raw_hex']
        cases = [
            mutate_row('abi_ingress', 'qi'),
            mutate_row('converted_ingress', 'scalar_ingress_forcing->p'),
            mutate_row('pre_limit', 'cold_out.pidep'),
            mutate_row('limited', 'scaled.cold.pidep'),
            mutate_row('state_in', 'working.ni'),
            mutate_row('state_out', 'new_state.qi'),
            mutate_row('dsd_out', 'new_state.qi'),
            coupled_candidate,
            lambda p: p['selected_rows'].pop(),
            lambda p: p['run_on'].__setitem__('endpoint_sha256', '0' * 64),
            lambda p: p['host_selected_trace']['on_v6'][0]['raw_hex'].__setitem__(0, '00000000'),
            lambda p: p['capture_metadata'][0]['rows'][0].__setitem__('raw_hex', '0'),
        ]
        for mutation in cases:
            with self.subTest(mutation=mutation):
                self.reject(mutation)

    def test_wrong_pin(self):
        with self.assertRaises(ValueError):
            verify(self.raw, '0' * 64)


if __name__ == '__main__':
    unittest.main()
