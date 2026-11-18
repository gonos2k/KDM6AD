import copy
import gzip
import importlib.util
import json
import unittest
import zipfile
from pathlib import Path

p = Path(__file__).with_name("stage_compare.py")
s = importlib.util.spec_from_file_location("stage_compare", p)
m = importlib.util.module_from_spec(s)
s.loader.exec_module(m)


class StageCompareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = m.capture(m.F32.read_bytes())
        cls.b = m.capture(
            (m.HERE / "raw/stage_compare_f64_baseline.csv.gz").read_bytes()
        )

    def test_replay_and_saved_result(self):
        result = m.replay()
        self.assertEqual(
            m.encode(result), (m.HERE / "stage_compare.json.gz").read_bytes()
        )
        self.assertTrue(
            all(
                x["equal"] and x["f32_values"] == x["f64_values"] == [1.0]
                for x in result["comparison"]["runtime_full_schedule"].values()
            )
        )
        self.assertEqual(
            result["comparison"]["boolean_mask_mismatches_by_stage"][
                "d1_postmelt_progb"
            ]["counts_by_field"],
            {"zero_den": 39, "op_f32": 39},
        )

    def test_record_identity_mutation_rejected(self):
        a = copy.deepcopy(self.a)
        a[0]["field"] = "changed"
        with self.assertRaisesRegex(ValueError, "alignment"):
            m.compare(a, self.b)

    def test_boolean_difference_is_inventoried(self):
        b = copy.deepcopy(self.b)
        r = next(
            x for x in b if x["dtype"] == "bool" and x["stage"] != "d1_postmelt_progb"
        )
        r["raw_hex"] = "1" if r["raw_hex"] == "0" else "0"
        self.assertIn(
            r["stage"], m.summarize(self.a, b)["boolean_mask_mismatches_by_stage"]
        )

    def test_lower_full_stage_evidence(self):
        result = m.replay()
        for row in result["lower_full_stage_endpoints"]["details"]:
            self.assertEqual(
                (
                    row["captured_boolean_count"],
                    row["captured_schedule_count"],
                    row["number_field_records_count"],
                ),
                (1170, 195, 70),
            )
            self.assertFalse(row["captured_bool_mismatches"])
            self.assertFalse(row["captured_schedule_mismatches"])
            self.assertTrue(all(x["equal"] for x in row["number_field_records"]))
            self.assertEqual(
                (
                    row["first_recorded_native16_change_after_entry"]["stage"],
                    row["first_recorded_native16_change_after_entry"]["field"],
                ),
                ("d1_upstream_entry", "t"),
            )

    def test_endpoint_receipt_failure_rejected(self):
        bound = json.loads(gzip.decompress(m.BOUNDARY.read_bytes()))
        receipt = json.loads((m.HERE / "raw/stage_screening_receipt.json").read_bytes())
        next(
            r
            for r in receipt["records"]
            if r["key"] == "lower_th_-1" and r["mode"] == "capture"
        )["installed_capture_exact_468"] = False
        with zipfile.ZipFile(m.ZIP) as z:
            raw = z.read("parity_calls/4074002793cded6a_capture.csv.gz")
        with self.assertRaisesRegex(ValueError, "screen capture receipt status"):
            m.lower_endpoints(bound, raw, json.dumps(receipt).encode())

    def test_progb_mode_review(self):
        review = m.progb_review(self.a, self.b)
        self.assertEqual(review["observed"]["f32"]["zero_den"]["raw_hex"], "1")
        self.assertEqual(review["observed"]["f64"]["zero_den"]["raw_hex"], "0")
        self.assertEqual(review["observed"]["f32"]["active"]["raw_hex"], "0")

    def test_lower_plateau_mutation_rejected(self):
        bound = json.loads(gzip.decompress(m.BOUNDARY.read_bytes()))
        c = next(x for x in bound["centers"] if x["name"] == "lower")
        word = c["probes"][0]["word"]
        next(x for x in bound["events"] if x["th_word"] == word)["trace"]["nc_final"][
            "raw_hex"
        ] = "0"
        with zipfile.ZipFile(m.ZIP) as z:
            raw = z.read("parity_calls/4074002793cded6a_capture.csv.gz")
        with self.assertRaisesRegex(ValueError, "plateau invariant"):
            m.plateau(bound, raw)


if __name__ == "__main__":
    unittest.main()
