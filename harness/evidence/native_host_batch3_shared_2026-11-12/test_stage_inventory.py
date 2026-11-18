import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import stage_inventory as inv


class StageInventoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = inv.inventory()

    def test_all_stages_fields_dtypes_counts_and_saved_summary(self):
        self.assertEqual(inv.verify(), self.result)
        stages = self.result["stage_records"]
        self.assertEqual(
            (self.result["stages_count"], self.result["rows"]), (51, 19656)
        )
        self.assertEqual(sum(s["field_count"] for s in stages.values()), 505)
        self.assertEqual(sum(s["row_count"] for s in stages.values()), 19656)
        self.assertEqual(stages["runtime_full_entry"]["row_count"], 468)
        self.assertEqual(
            stages["fd_satadj_inner"]["fields_by_dtype_count"]["nc_final"], {"f64": 39}
        )
        self.assertEqual(
            stages["ice_sedimentation_n1"]["fields_by_dtype_count"]["applied_out_ni"],
            {"f64": 38},
        )
        self.assertEqual(stages["ice_sedimentation_n1"]["substeps"], [1])
        self.assertTrue(
            all(
                s["field_count"] == len(s["fields_by_dtype_count"])
                for s in stages.values()
            )
        )
        self.assertTrue(
            all(
                s["row_count"]
                == sum(sum(x.values()) for x in s["fields_by_dtype_count"].values())
                for s in stages.values()
            )
        )

    def test_saved_summary_rejects_missing_stage_field_dtype_or_count(self):
        for mutation in ("stage", "field", "dtype", "count"):
            altered = copy.deepcopy(self.result)
            stage = altered["stage_records"]["fd_satadj_inner"]
            if mutation == "stage":
                del altered["stage_records"]["fd_satadj_inner"]
            elif mutation == "field":
                del stage["fields_by_dtype_count"]["nc_final"]
            elif mutation == "dtype":
                stage["fields_by_dtype_count"]["nc_final"] = {"f32": 39}
            else:
                stage["row_count"] += 1
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as d:
                path = Path(d) / "saved.json"
                path.write_text(json.dumps(altered))
                with (
                    mock.patch.object(inv, "SAVED", path),
                    self.assertRaisesRegex(ValueError, "saved inventory mismatch"),
                ):
                    inv.verify()

    def test_capture_hash_rejects_changed_input(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "capture.gz"
            path.write_bytes(inv.CAPTURE.read_bytes() + b"x")
            with (
                mock.patch.object(inv, "CAPTURE", path),
                self.assertRaisesRegex(ValueError, "gzip SHA-256"),
            ):
                inv.inventory()

    def test_gaps_are_narrow_exact_labels(self):
        gaps = self.result["ledger_exact_label_gaps"]
        self.assertIn(
            {"stage": "fd_main", "field": "applied_out_qr"},
            gaps["sedimentation_mass_departure_arrival"],
        )
        self.assertIn(
            {"stage": "fd_satadj_inner", "field": "pcond"}, gaps["heat_budget"]
        )
        self.assertNotIn(
            {"stage": "ice_sedimentation_n1", "field": "applied_out_ni"},
            gaps["sedimentation_number_all_substeps"],
        )
        self.assertIn("not ruled out", self.result["gaps_scope"])


if __name__ == "__main__":
    unittest.main()
