import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import replay


class SupplyReplayTest(unittest.TestCase):
    def test_full_runtime_half_cap_and_derivative(self):
        with contextlib.redirect_stdout(io.StringIO()) as captured:
            replay.main()
        result = json.loads(captured.getvalue())
        self.assertEqual(result["status"], "ICE_NUCLEATION_SUPPLY_REPLAY_PASSED")
        self.assertEqual(result["scientific_status"], "INCONCLUSIVE")
        weak = result["weak_half_supply"]
        strong = result["strong_target_deficit"]
        self.assertEqual(weak["selected_cap_first_column"], "half_satdt")
        self.assertEqual(strong["selected_cap_first_column"], "deficit_mass_rate")
        self.assertTrue(all(value > 0 for value in weak["C3_margin_deficit_minus_half"]))
        self.assertTrue(all(value > 0 for value in weak["C3_margin_remaining_minus_half"]))
        self.assertEqual(weak["automatic_subcycles"][0]["ice_by_column"], [1.0, 1.0])
        self.assertTrue(all(value > 0 for value in weak["C3_pinud"]))
        self.assertTrue(all(value > 0 for value in weak["C3_ninud"]))
        self.assertTrue(all(value > 0 for value in weak["final_qi"]))
        self.assertLess(weak["final_ni"][0], strong["final_ni"][0])
        direction = result["weak_qv_direction"]
        self.assertTrue(direction["captured_masks_equal"])
        self.assertEqual(direction["input_field"], "qv")
        self.assertEqual(set(direction["outputs_by_field"]), {"qi", "ni", "qv", "th"})
        self.assertGreater(direction["outputs_by_field"]["ni"]["jvp_wrf_bottom_first"][0][1], 0)
        self.assertLess(direction["max_abs_fd_minus_jvp_scaled"], 1e-6)
        boundary = result["ice_saturation_one_sided"]
        self.assertFalse(boundary["-1e-12"]["C3_outer_top"])
        self.assertFalse(boundary["0.0"]["C3_outer_top"])
        self.assertTrue(boundary["1e-12"]["C3_outer_top"])
        self.assertGreater(result["binary32_spacing_near_qs_ice"], 1e-10)

    def test_altered_source_rejected(self):
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
