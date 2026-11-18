import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import replay


class NucleationRuntimeReplayTest(unittest.TestCase):
    def test_full_runtime_and_c3_regimes(self):
        with contextlib.redirect_stdout(io.StringIO()) as captured:
            replay.main()
        result = json.loads(captured.getvalue())
        self.assertEqual(result["status"], "ICE_NUCLEATION_RUNTIME_REPLAY_PASSED")
        self.assertEqual(result["scientific_status"], "INCONCLUSIVE")
        self.assertEqual(set(result["variants"]), {"legacy", "normalized"})
        for variant in result["variants"].values():
            topology = variant["subcycle_topology"]
            self.assertEqual(topology["main_by_column"], [1.0, 1.0])
            self.assertEqual(topology["ice_by_column"], [1.0, 1.0])
            self.assertEqual(variant["C3_branch"]["outer"], [True] * 3)
            self.assertEqual(variant["C3_branch"]["inner"], [True] * 3)
            self.assertTrue(all(x > 0 for x in variant["C3"]["pinud"]))
            self.assertTrue(all(x > 0 for x in variant["C3"]["ninud"]))
        legacy = result["variants"]["legacy"]
        normalized = result["variants"]["normalized"]
        self.assertEqual(legacy["post_sed_qi"], [0.0] * 3)
        self.assertTrue(all(x > 0 for x in legacy["post_sed_ni"]))
        self.assertTrue(all(x > 0 for x in legacy["post_micro_qi"]))
        self.assertTrue(all(x > 0 for x in normalized["post_micro_qi"]))
        self.assertGreater(normalized["post_micro_qi"][0] / legacy["post_micro_qi"][0], 300)
        cases = result["isolated_C3_branches"]
        self.assertEqual(cases["target_deficit"]["cap_winner"], "deficit_mass_rate")
        self.assertEqual(cases["half_supply_cap"]["cap_winner"], "half_satdt")
        self.assertEqual(cases["remaining_supply_cap"]["cap_winner"], "supice")
        self.assertFalse(cases["outer_inactive"]["active"])
        self.assertFalse(cases["target_exceeded"]["active"])
        self.assertFalse(cases["target_equal"]["active"])
        self.assertFalse(cases["outer_inactive_exhausted_prev"]["ifsat"])
        self.assertTrue(cases["inner_inactive_exhausted_prev"]["ifsat"])
        self.assertEqual(result["uncapped_C3_derivative"]["number_jvp"], 0.0)
        self.assertAlmostEqual(result["uncapped_C3_derivative"]["mass_rate_jvp"],
                               -2.6179937124420904e-12, delta=1e-20)
        for mode in ("legacy", "normalized"):
            self.assertEqual(result["precision_probe"][mode]["post_sed_qi_dtype"],
                             "torch.float32")
            self.assertEqual(result["precision_probe"][mode]["post_freeze_qi_dtype"],
                             "torch.float64")
            for direction in ("qi_only", "ni_only"):
                diagnostic = result["runtime_selected_derivatives"][mode][direction]
                self.assertTrue(diagnostic["captured_stage_masks_equal"])
                self.assertGreater(diagnostic["jvp_scaled_norm"], 0)
                self.assertLess(diagnostic["max_abs_fd_minus_jvp_scaled"], 1e-8)
                self.assertEqual(set(diagnostic["outputs_by_field"]),
                                 {"qi", "ni", "qv", "th"})
                self.assertEqual(diagnostic["input_direction"]["relative_direction"], 1.0)
                for field in ("qi", "ni", "qv", "th"):
                    values = diagnostic["outputs_by_field"][field]
                    self.assertEqual(len(values["jvp_wrf_bottom_first"]), 2)
                    self.assertEqual(len(values["jvp_wrf_bottom_first"][0]), 3)
                    self.assertEqual(len(values["fd_minus_jvp_wrf_bottom_first"]), 2)
        for field in ("qi", "ni"):
            legacy = result["runtime_selected_derivatives"]["legacy"]["ni_only"][
                "outputs_by_field"][field]["jvp_wrf_bottom_first"][0][1]
            normalized = result["runtime_selected_derivatives"]["normalized"]["ni_only"][
                "outputs_by_field"][field]["jvp_wrf_bottom_first"][0][1]
            self.assertLess(legacy, 0.0)
            self.assertGreater(normalized, 0.0)

    def test_source_mutation_rejected(self):
        manifest = json.loads((replay.ROOT / "source_manifest.json").read_bytes())
        relative = next(iter(manifest))
        with tempfile.TemporaryDirectory() as tmp:
            altered = Path(tmp) / relative
            altered.parent.mkdir(parents=True)
            altered.write_bytes((replay.REPO / relative).read_bytes() + b"\n# changed\n")
            with patch.object(replay, "REPO", Path(tmp)):
                with self.assertRaisesRegex(ValueError, "source digest"):
                    replay.main()


if __name__ == "__main__":
    unittest.main()
