import contextlib
import io
import json
import unittest
from unittest.mock import patch

import torch

import replay

from harness.tests.test_ice_chain_applied_budget import _inputs, _run
from oracle.kdm6.coordinator import apply_threshold_cleanup_torch


class PostSedimentFateReplayTest(unittest.TestCase):
    def test_same_synthetic_column_fate(self):
        with contextlib.redirect_stdout(io.StringIO()) as captured:
            replay.main()
        result = json.loads(captured.getvalue())
        self.assertEqual(result["status"], "ICE_POST_SED_FATE_REPLAY_PASSED")
        self.assertEqual(result["scientific_status"], "INCONCLUSIVE")
        self.assertEqual(result["post_first_ice"], result["post_full_sedimentation"])
        self.assertEqual(result["runtime_setup_contrast"]["runtime_selected_ice_mstep_by_column"],
                         [1.0, 1.0])
        self.assertFalse(result["runtime_setup_contrast"]["reclamp_changes_this_chain_output"])
        self.assertEqual(result["post_full_sedimentation"]["qi"], [0.0] * 3)
        self.assertTrue(all(value > 0 for value in result["post_full_sedimentation"]["ni"]))
        self.assertEqual(result["early_cleanup_control"]["ni"], [0.0] * 3)
        self.assertTrue(all(value > 1e-15 for value in result["snapshots"]["d2_d4_freeze"]["qi_after_top_first"]))
        self.assertTrue(all(value > 0 for value in result["applied_cold_rates"]["pinud_qi_rate"]))
        self.assertTrue(all(value > 0 for value in result["applied_cold_rates"]["ninud_ni_rate"]))
        self.assertTrue(all(value > 0 for value in result["final_microphysics"]["qi"]))
        self.assertTrue(all(value > 0 for value in result["final_microphysics"]["ni"]))
        self.assertEqual(result["branches"]["picons"]["reclassify"], [False] * 3)
        self.assertEqual(result["branches"]["cleanup_keep_qi"], [True] * 3)
        self.assertEqual(result["branches"]["dsd_limiter"]["ice_too_small"], [False] * 3)
        self.assertEqual(result["branches"]["dsd_limiter"]["ice_too_large"], [False] * 3)

    def test_early_paired_cleanup_would_remove_orphan_number(self):
        state, forcing, mask, params, work = _inputs(torch.float64)
        post_fall = _run(state, forcing, mask, params, work, normalized=False).state
        self.assertTrue(torch.all(post_fall.qi[0] == 0))
        self.assertTrue(torch.all(post_fall.ni[0] > 0))
        early = apply_threshold_cleanup_torch(post_fall)
        self.assertTrue(torch.all(early.qi[0] == 0))
        self.assertTrue(torch.all(early.ni[0] == 0))

    def test_mutated_source_rejected(self):
        with patch.object(replay, "REPO", replay.ROOT):
            with self.assertRaisesRegex(ValueError, "source digest"):
                replay.main()


if __name__ == "__main__":
    unittest.main()
