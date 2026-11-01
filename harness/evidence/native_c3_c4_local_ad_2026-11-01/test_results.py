"""Recompute the published local diagnostics from the pinned source packet."""

import copy
import importlib
import json
import math
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
PACKAGE = 'harness.evidence.native_c3_c4_local_ad_2026-11-01'


def compare(fresh, saved, path='result'):
    """Bound scalar replay variation while rejecting substantive report changes."""
    if isinstance(fresh, dict):
        if not isinstance(saved, dict) or set(fresh) != set(saved):
            raise ValueError(path + ': mapping inventory')
        for key in fresh:
            compare(fresh[key], saved[key], path + '/' + str(key))
    elif isinstance(fresh, list):
        if not isinstance(saved, list) or len(fresh) != len(saved):
            raise ValueError(path + ': sequence inventory')
        for index, (left, right) in enumerate(zip(fresh, saved)):
            compare(left, right, path + '/' + str(index))
    elif isinstance(fresh, bool) or fresh is None or isinstance(fresh, str):
        if type(fresh) is not type(saved) or fresh != saved:
            raise ValueError(path + ': discrete value')
    elif isinstance(fresh, (int, float)):
        if type(saved) not in (int, float) or not math.isfinite(float(saved)):
            raise ValueError(path + ': numeric type or finite value')
        left, right = float(fresh), float(saved)
        scale = max(abs(left), abs(right))
        # Cancellation-scale values can vary by a few binary64 roundings. Other
        # derived scalar diagnostics retain a 2e-8 relative replay bound.
        tolerance = 2e-15 if scale < 1e-14 else 2e-8 * scale
        if abs(left - right) > tolerance:
            raise ValueError(path + ': numerical replay mismatch')
    else:
        raise TypeError(path + ': unsupported result type')


class SavedResultsTest(unittest.TestCase):
    def test_saved_results_match_fresh_and_reject_mutations(self):
        for module_name, file_name, mutation in (
            ('replay', 'results.json', lambda value:
                value['23']['ni']['0.1']['jvp'].__setitem__(3,
                    value['23']['ni']['0.1']['jvp'][3] * 1.01)),
            ('c5_replay', 'c5_results.json', lambda value:
                value['23']['0.0001']['state']['jvp'].__setitem__(1,
                    value['23']['0.0001']['state']['jvp'][1] + 1.0)),
        ):
            with self.subTest(module=module_name):
                module = importlib.import_module(PACKAGE + '.' + module_name)
                fresh = json.loads(json.dumps(module.report()))
                saved = json.loads((ROOT / file_name).read_bytes())
                compare(fresh, saved)
                altered = copy.deepcopy(saved)
                mutation(altered)
                with self.assertRaisesRegex(ValueError, 'numerical replay mismatch'):
                    compare(fresh, altered)


if __name__ == '__main__':
    unittest.main()
