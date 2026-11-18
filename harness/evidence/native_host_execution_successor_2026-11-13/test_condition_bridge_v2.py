import copy
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('bridge', HERE / 'condition_bridge_v2.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
spec = importlib.util.spec_from_file_location('fixture', HERE.parent / 'native_host_preflight_2026-11-12' / 'test_fd_gate.py')
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)


def sidecar(cid, count=1):
    schedules = [{'outer_loop': 1, 'family': 'main', 'active': True, 'substeps': count},
                 {'outer_loop': 1, 'family': 'ice', 'active': False, 'substeps': 0}]
    records = []
    for s in schedules:
        for n in (range(1, s['substeps'] + 1) if s['active'] else (0,)):
            for mask in b.MASKS:
                records.append(dict(call_id=cid, runtime_call=0, one_step_call=0,
                    outer_loop=1, family=s['family'], substep_n=n, scope='column',
                    b_zero=0, k_zero=-1, native_level_bottom_first=-1, stage='synthetic',
                    field=mask, event_ordinal=0, mask_id=mask,
                    availability='present' if s['active'] else 'inactive',
                    value=True if s['active'] else None,
                    reason=None if s['active'] else 'family_gate_false'))
    return dict(schema=b.SCHEMA, status='SYNTHETIC_ONLY', call_id=cid, schedule=schedules, records=records)


def case(stencil='central', third=False):
    data = f.example(stencil=stencil)
    if third:
        step = copy.deepcopy(data['plan']['steps'][1]); sample = copy.deepcopy(data['samples'][1])
        step['id'] = sample['id'] = 'third'; step['h_word'] = b.gate.word(.5)
        center = data['plan']['center_input_words']; lo = center.copy(); hi = center.copy()
        lo[0] = b.gate.word(.5); hi[0] = b.gate.word(1.5)
        step['lower_input_words'] = lo; step['upper_input_words'] = hi
        sample['jvp_output_words'][0] = b.gate.word((b.gate.val(sample['upper']['output_words'][0]) - b.gate.val(sample['lower']['output_words'][0])))
        data['plan']['steps'].append(step); data['samples'].append(sample)
        data['plan_sha256'] = b.gate.plan_sha(data['plan'])
    bindings = {'center': 'center', 'samples': {}}
    ids = {'center'}
    for s in data['samples']:
        roles = {'lower', 'upper'} | ({'plus2'} if stencil == 'forward' else set())
        bindings['samples'][s['id']] = {r: s['id'] + ':' + r for r in roles}
        ids.update(bindings['samples'][s['id']].values())
    return data, bindings, {cid: sidecar(cid) for cid in ids}


class BridgeTests(unittest.TestCase):
    def test_mask_and_schedule_crossings(self):
        d, x, c = case()
        self.assertEqual(b.evaluate(d, x, c)['tag'], 'LOCAL_NUMERIC_CONSISTENT')
        cid = x['samples']['0']['upper']; c[cid]['records'][0]['value'] = False
        self.assertEqual(b.evaluate(d, x, c)['tag'], 'BRANCH_CROSSING')
        c[cid] = sidecar(cid, 2)
        self.assertEqual(b.evaluate(d, x, c)['tag'], 'BRANCH_CROSSING')

    def test_plus2_and_diagnostic(self):
        d, x, c = case('forward'); cid = x['samples']['0']['plus2']
        c[cid]['records'][0]['value'] = False
        self.assertEqual(b.evaluate(d, x, c)['tag'], 'BRANCH_CROSSING')
        d, x, c = case(third=True); cid = x['samples']['third']['upper']
        c[cid]['records'][0]['value'] = False
        r = b.evaluate(d, x, c)
        self.assertEqual(r['tag'], 'LOCAL_NUMERIC_CONSISTENT')
        self.assertEqual(next(s for s in r['steps'] if s['id'] == 'third')['tag'], 'BRANCH_CROSSING')
        self.assertEqual(r['gate_eligibility'], 'NOT_ELIGIBLE')

    def test_fail_closed(self):
        for mutation in ('missing', 'duplicate', 'unknown', 'wrong_call', 'inactive', 'claim'):
            d, x, c = case(); cid = x['center']; s = c[cid]
            if mutation == 'missing': s['records'].pop()
            elif mutation == 'duplicate': s['records'].append(copy.deepcopy(s['records'][0]))
            elif mutation == 'unknown': s['records'][0]['mask_id'] = s['records'][0]['field'] = 'unknown'
            elif mutation == 'wrong_call': s['records'][0]['call_id'] = 'wrong'
            elif mutation == 'inactive': s['records'][-1]['reason'] = 'unexplained'
            else: s['status'] = 'COMPLETE'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): b.evaluate(d, x, c)

    def test_order_independent(self):
        d, x, c = case(); c[x['center']]['records'].reverse()
        self.assertEqual(b.evaluate(d, x, c)['tag'], 'LOCAL_NUMERIC_CONSISTENT')

    def test_endpoint_alias_rejected_and_forward_center_reuse(self):
        d, x, c = case()
        cid = x['samples']['0']['upper']
        c[cid]['records'][0]['value'] = False
        self.assertEqual(b.evaluate(d, x, c)['tag'], 'BRANCH_CROSSING')
        x['samples']['0']['upper'] = x['center']
        with self.assertRaisesRegex(ValueError, 'different planned inputs'):
            b.evaluate(d, x, c)

        d, x, c = case('forward')
        old = x['samples']['0']['lower']
        x['samples']['0']['lower'] = x['center']
        del c[old]
        self.assertEqual(b.evaluate(d, x, c)['tag'], 'LOCAL_NUMERIC_CONSISTENT')

if __name__ == '__main__': unittest.main()
