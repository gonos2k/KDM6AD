"""Check inferred native C5 baselines and represented local derivatives."""
import importlib
import math
import unittest

C5Replay = importlib.import_module(
    'harness.evidence.native_c3_c4_local_ad_2026-11-01.c5_replay').C5Replay


class C5ReplayTest(unittest.TestCase):
    def test_baseline_and_conditional_relative_derivatives(self):
        for k, ps_arm in ((21, 'zero'), (23, 'raw')):
            r = C5Replay(k)
            r.baseline()
            for h in (1e-3, 1e-4, 1e-5):
                d = r.derivative(h)
                for b in d['branches_minus_baseline_plus']:
                    self.assertTrue(b['active'])
                    self.assertFalse(b['warm_arm'])
                    self.assertEqual(b['ps_arm'], ps_arm)
                    self.assertEqual(b['ns_arm'], 'raw')
                    self.assertTrue(all(x != 0 for x in b['margins'].values()))
                state = d['state']
                for endpoint in state['clamp_margins_minus_baseline_plus']:
                    self.assertTrue(all(value > 0 for value in endpoint))
                for name in ('jvp', 'vjp', 'fd'):
                    for actual, expected in zip(state[name], state['analytic']):
                        self.assertTrue(math.isclose(actual, expected, rel_tol=2e-6, abs_tol=1e-14),
                                        (k, h, 'state', name, actual, expected))
                for name in ('jvp', 'vjp', 'fd'):
                    for actual, expected in zip(d[name], d['analytic']):
                        self.assertTrue(math.isclose(actual, expected, rel_tol=1e-7, abs_tol=1e-16),
                                        (k, h, name, actual, expected))

    def test_rate_baseline_mismatch_fails(self):
        r = C5Replay(23)
        r.saved[0] = 0.0
        with self.assertRaises(ValueError):
            r.baseline()


if __name__ == '__main__':
    unittest.main()
