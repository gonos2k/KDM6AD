import gzip
import importlib.util
import json
import math
import struct
import unittest
from pathlib import Path

p = Path(__file__).with_name("analysis.py")
spec = importlib.util.spec_from_file_location("batch4", p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def compare(test, a, b, path="root"):
    test.assertEqual(type(a), type(b), path)
    if isinstance(a, dict):
        test.assertEqual(a.keys(), b.keys(), path)
        for k in a:
            compare(test, a[k], b[k], path + "." + k)
    elif isinstance(a, list):
        test.assertEqual(len(a), len(b), path)
        for i, (x, y) in enumerate(zip(a, b)):
            compare(test, x, y, path + f"[{i}]")
    elif isinstance(a, float):
        test.assertTrue(math.isfinite(a) and math.isfinite(b), path)
        test.assertEqual(struct.pack(">d", a), struct.pack(">d", b), path)
    else:
        test.assertEqual(a, b, path)


class AnalysisTests(unittest.TestCase):
    def test_second_forward_checks_plus2_endpoint_masks(self):
        receipt = {
            "schema": "kdm6.batch3.screen.v1",
            "endpoints": [
                {
                    "key": "lower_nc_+2",
                    "installed_capture_exact_468": True,
                    "capture_rows": 19656,
                    "bool_changed_keys": [],
                    "schedule_changed_keys": [],
                }
            ],
        }
        self.assertTrue(m.recorded_endpoint_stable(receipt, "lower_nc_+2"))
        receipt["endpoints"][0]["bool_changed_keys"] = ["changed_mask"]
        self.assertFalse(m.recorded_endpoint_stable(receipt, "lower_nc_+2"))
        receipt["endpoints"][0]["bool_changed_keys"] = []
        receipt["endpoints"].append(dict(receipt["endpoints"][0]))
        with self.assertRaisesRegex(ValueError, "receipt inventory"):
            m.recorded_endpoint_stable(receipt, "lower_nc_+2")
        with self.assertRaisesRegex(ValueError, "receipt inventory"):
            m.checked_second_forward_stable(False, receipt, "lower_nc_+2")

    def test_saved_and_inventory(self):
        result = m.analyze()
        saved = json.loads(gzip.decompress(p.with_name("results.json.gz").read_bytes()))
        compare(self, result, saved)
        self.assertEqual(len(result["output_rows"]), 61 * 468)
        self.assertEqual(len(result["nc_second_forward_rows"]), 9 * 468)
        self.assertEqual(len(result["f32_f64_stage_link"]["all_101_mismatches"]), 101)
        self.assertFalse(
            result["f32_f64_stage_link"]["nc16"]["baseline_rounded_f32_mismatch"]
        )

    def test_signed_zero_and_recorded_crossing(self):
        row = m.row_metrics(
            "lower",
            "th",
            1e-4,
            0,
            "0000000000000000",
            "8000000000000000",
            "0000000000000000",
            1.0,
            True,
            "central",
        )
        self.assertEqual(row["classification"], "unresolved_equal_words")
        self.assertFalse(row["endpoint_words_equal"])
        row = m.row_metrics(
            "upper", "pii", 1e-4, 0, m.w(1.0), m.w(2.0), m.w(1.0), 1.0, False, "central"
        )
        self.assertEqual(row["classification"], "captured_branch_crossing")

    def test_componentwise_direction_and_mutation(self):
        lo = [m.w(0.0)] * 624
        hi = lo.copy()
        hi[15] = m.w(0.0001)
        hi[39 + 15] = m.w(0.0000001)
        seed = [m.w(0.0)] * 624
        seed[15] = m.w((m.f(hi[15]) - m.f(lo[15])) / 0.0002)
        seed[39 + 15] = m.w((m.f(hi[39 + 15]) - m.f(lo[39 + 15])) / 0.0002)
        m.check_effective_direction(lo, hi, 0.0002, seed)
        seed[39 + 15] = m.w(1.0)
        with self.assertRaisesRegex(ValueError, "represented componentwise"):
            m.check_effective_direction(lo, hi, 0.0002, seed)

    def test_ulp_adjacent_does_not_claim_accuracy(self):
        x = m.w(1.0)
        y = m.w(math.nextafter(1.0, math.inf))
        row = m.row_metrics(
            "baseline", "nc", 1e-6, 0, x, y, m.w(0.0), 1e-6, True, "first_forward"
        )
        self.assertEqual(row["signal_ulp_distance"], 1)
        self.assertEqual(row["classification"], "exploratory_distinct_words")
        self.assertNotIn("pass", row["classification"])


if __name__ == "__main__":
    unittest.main()
