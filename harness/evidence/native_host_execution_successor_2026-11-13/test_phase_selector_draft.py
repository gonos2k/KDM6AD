import json
from pathlib import Path
import unittest

import phase_selector_draft as draft

HERE = Path(__file__).resolve().parent


class PhaseSelectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((HERE / "phase_selector_draft.json").read_text())

    def test_pinned_source_census(self):
        self.assertEqual(draft.census(), self.manifest)
        self.assertEqual(len(self.manifest["selector_families"]), 98)
        self.assertEqual(len(self.manifest["a7_v1_fields"]), 18)
        self.assertEqual(self.manifest["status"], "DRAFT_BLOCKED")

    def test_mixed_phase_and_repeated_ordinal(self):
        base = {
            "input_id": "fixture",
            "mode": "capture_on_value",
            "epoch": 1,
            "runtime_call": 1,
            "one_step_call": 0,
            "outer": 1,
            "family": "sedimentation_main",
            "n": 1,
            "scope": "column",
            "B": 1,
            "K": -1,
            "b": 0,
            "k": -1,
            "native": -1,
            "stage": "sedimentation_gate",
            "field": "active_main",
            "source_hook": "src/coordinator.cpp:sedimentation_gate.active_main",
            "role": "consumed_bool",
            "dtype": "bool",
            "ordinal": 0,
        }
        repeated = {**base, "ordinal": 1}
        micro = {
            **base,
            "one_step_call": 1,
            "family": "microphysics",
            "n": 0,
            "scope": "layer",
            "K": 39,
            "k": 0,
            "native": 39,
            "stage": "dsd_inner",
            "field": "nc_gt_ncmax",
            "source_hook": "src/coordinator.cpp:dsd_inner.nc_gt_ncmax",
        }
        self.assertEqual(
            draft.validate_observed([base, repeated, micro], self.manifest)["status"],
            "STRUCTURE_ONLY_INCOMPLETE",
        )
        bads = [
            {**repeated, "ordinal": 0},
            {**micro, "native": 1},
            {**base, "n": 0},
            {**base, "family": "invented", "n": 0},
            {**base, "family": "microphysics", "one_step_call": 1, "n": 0},
            {**micro, "source_hook": "unknown"},
            {**micro, "dtype": "f64"},
            {**micro, "role": "not_evaluated"},
        ]
        for bad in bads:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                draft.validate_observed([base, bad], self.manifest)
        with self.assertRaises(ValueError):
            draft.validate_observed([], self.manifest)

    def test_unknown_stage_and_invalid_scalar_dtype(self):
        scalar = next(
            x
            for x in self.manifest["selector_families"]
            if x["role"] == "control_scalar" and x["allowed_dtype"] == ["i64"]
        )
        rec = {
            "input_id": "fixture",
            "mode": "capture_on_value",
            "epoch": 1,
            "runtime_call": 1,
            "one_step_call": 0,
            "outer": 1,
            "family": "sedimentation_preslope",
            "n": 0,
            "scope": "scalar",
            "B": -1,
            "K": -1,
            "b": -1,
            "k": -1,
            "native": -1,
            "stage": scalar["stage"],
            "field": scalar["field"],
            "source_hook": scalar["source_hook"],
            "role": "control_scalar",
            "dtype": "i64",
            "ordinal": 0,
        }
        draft.validate_observed([rec], self.manifest)
        with self.assertRaises(ValueError):
            draft.validate_observed([{**rec, "dtype": "bool"}], self.manifest)
        with self.assertRaises(ValueError):
            draft.validate_observed([{**rec, "stage": "unknown"}], self.manifest)


if __name__ == "__main__":
    unittest.main()
