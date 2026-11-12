"""Synthetic receipt-to-gate adaptation; no model or DSO is invoked."""

import copy
import json
import unittest

import fd_input_adapter as adapter
import receipt_schema as rs
from test_receipt_schema import add, synthetic_bundle


class AdapterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt, cls.assets = synthetic_bundle()

    def bundle(self):
        return copy.deepcopy(self.receipt), dict(self.assets)

    def set_mask(self, receipt, assets, input_id):
        ref = receipt["condition_assets"][input_id]
        obj = json.loads(assets[ref["path"]])
        obj["mask_values"][-1] = not obj["mask_values"][-1]
        receipt["condition_assets"][input_id] = add(assets, ref["path"], obj)

    def test_upper_pii_diagnostic_crossing_does_not_become_eligible(self):
        receipt, assets = self.bundle()
        self.set_mask(receipt, assets, "upper:pii:1e-04:-1")
        result = adapter.adapt(receipt, assets, "upper", "pii", 0)
        self.assertEqual(result["status"], "NOT_ELIGIBLE_UNVERIFIED_PROVENANCE")
        self.assertFalse(result["fd_gate_ready"])
        self.assertEqual(result["live_intermediate_effective_tangents"], "NOT_LINKED")
        gate = result["gate_result"]
        self.assertEqual(gate["acceptance_step_ids"], ["1e-06", "1e-05"])
        diagnostic = next(x for x in gate["steps"] if x["id"] == "1e-04")
        self.assertEqual(
            (diagnostic["role"], diagnostic["tag"]), ("diagnostic", "BRANCH_CROSSING")
        )
        self.assertNotEqual(gate["tag"], "BRANCH_CROSSING")
        self.assertEqual(len(result["gate_input"]["center"]["masks"]), 1170)
        self.assertEqual(len(result["gate_input"]["center"]["schedule"]), 195)

    def test_selected_step_crossing_is_rejected_for_smooth_interpretation(self):
        receipt, assets = self.bundle()
        self.set_mask(receipt, assets, "upper:pii:1e-06:+1")
        result = adapter.adapt(receipt, assets, "upper", "pii", 0)
        self.assertEqual(result["gate_result"]["tag"], "BRANCH_CROSSING")
        self.assertTrue(
            result["gate_result"]["gate_eligibility"].startswith("NOT_ELIGIBLE")
        )

    def test_forward_nc_uses_center_plus_and_plus2(self):
        receipt, assets = self.bundle()
        result = adapter.adapt(receipt, assets, "lower", "nc", 0)
        self.assertEqual(len(result["gate_input"]["samples"]), 3)
        self.assertTrue(all("plus2" in x for x in result["gate_input"]["samples"]))
        self.assertTrue(
            all(
                x["lower"] == result["gate_input"]["center"]
                for x in result["gate_input"]["samples"]
            )
        )

    def test_missing_or_cross_call_condition_rejected_after_rehash(self):
        for mutation in (
            "missing",
            "wrong_sequence",
            "short_mask",
            "short_schedule",
            "bad_contract",
        ):
            receipt, assets = self.bundle()
            ident = "upper:pii:1e-06:+1"
            if mutation == "missing":
                del receipt["condition_assets"][ident]
            else:
                ref = receipt["condition_assets"][ident]
                obj = json.loads(assets[ref["path"]])
                if mutation == "wrong_sequence":
                    obj["call_sequence"] += 2
                elif mutation == "short_mask":
                    obj["mask_values"].pop()
                elif mutation == "short_schedule":
                    obj["schedule_words"].pop()
                else:
                    obj["condition_contract_sha256"] = "a" * 64
                receipt["condition_assets"][ident] = add(assets, ref["path"], obj)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                adapter.adapt(receipt, assets, "upper", "pii", 0)

    def test_rehashed_selected_output_mismatch_rejected(self):
        receipt, assets = self.bundle()
        call = next(
            x
            for x in receipt["calls"]
            if x["input_id"] == "upper:pii:1e-06:+1" and x["mode"] == "capture_on_value"
        )
        ref = call["output_asset"]
        obj = json.loads(assets[ref["path"]])
        obj["state_output_words"][0] = rs.ONE
        call["output_asset"] = add(assets, ref["path"], obj)
        with self.assertRaisesRegex(ValueError, "capture off/on output mismatch"):
            adapter.adapt(receipt, assets, "upper", "pii", 0)


if __name__ == "__main__":
    unittest.main()
