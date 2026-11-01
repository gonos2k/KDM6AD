import importlib
import math
import unittest

Replay = importlib.import_module(
    'harness.evidence.native_c3_c4_local_ad_2026-11-01.replay').Replay


class LocalReplayTest(unittest.TestCase):
    def test_native_baselines_and_ni_directions(self):
        for k in (21, 23):
            r = Replay(k)
            r.baseline()
            for h in (0.1, 1.0, 10.0):
                d = r.derivative('ni', h)
                expected = [0., 0., 0., 0., 1.] if k == 21 else [
                    -2.5085092781071627e-13, -0.05, 0., -5.0170185562143256e-12, 0.]
                for name in ('jvp', 'vjp', 'fd'):
                    for actual, target in zip(d[name], expected):
                        if target == 0.:
                            self.assertLessEqual(abs(actual), 2e-14,
                                                 (k, h, name, actual, target))
                        else:
                            self.assertTrue(math.isclose(actual, target, rel_tol=2e-8, abs_tol=0),
                                            (k, h, name, actual, target))

    def test_relative_n0i_direction(self):
        for k, expected in ((21, -8.782281178665383e-12), (23, 1.0855819230719068e-8)):
            r = Replay(k)
            r.baseline()
            d = r.derivative('n0', 1e-4)
            for name in ('jvp', 'vjp', 'fd'):
                self.assertTrue(math.isclose(d[name][2], expected, rel_tol=2e-8))
                self.assertTrue(math.isclose(d[name][3], expected * r.dt, rel_tol=2e-8))
                self.assertEqual(d[name][4], 0.)


if __name__ == '__main__':
    unittest.main()
