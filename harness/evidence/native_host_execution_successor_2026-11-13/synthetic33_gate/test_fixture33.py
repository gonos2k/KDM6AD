import unittest
import fixture33 as f
from fixture_plan import raw_words,perturb
class Fixture33Test(unittest.TestCase):
    def test_schedule(self):
        a=f.plan();self.assertEqual(len(a),33);self.assertEqual([x['seq'] for x in a],list(range(1,34)))
        self.assertEqual(len({(x['fixture'],x['mode'],x['direction'],x['offset']) for x in a}),33)
    def test_directions_and_represented_perturbations(self):
        self.assertNotEqual(f.direction('nc'),f.direction('th'))
        for c in f.CASES:
            x=f.center(c)
            for d in f.DIRECTIONS:
                for h in f.H:
                    self.assertNotEqual(raw_words(perturb(x,f.direction(d),h)),raw_words(x))
                    self.assertNotEqual(raw_words(perturb(x,f.direction(d),-h)),raw_words(x))
    def test_bad_case_rejected(self):
        with self.assertRaises(ValueError):f.center('native')
if __name__=='__main__':unittest.main()
