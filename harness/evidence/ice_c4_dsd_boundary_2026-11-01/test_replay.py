import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import replay


class C4DsdBoundaryReplayTest(unittest.TestCase):
    def test_saturation_boundary_and_low_temperature(self):
        with contextlib.redirect_stdout(io.StringIO()) as captured:
            replay.main()
        result = json.loads(captured.getvalue())
        self.assertEqual(result["status"], "ICE_C4_DSD_BOUNDARY_REPLAY_PASSED")
        self.assertEqual(result["scientific_status"], "INCONCLUSIVE")
        below = result["saturation_boundary"]["-1e-12"]
        exact = result["saturation_boundary"]["0.0"]
        above = result["saturation_boundary"]["1e-12"]
        self.assertFalse(below["C3"]["outer"])
        self.assertTrue(below["C4"]["active"])
        self.assertLess(below["C4"]["raw_pidep"], 0)
        self.assertGreater(below["C4"]["limited_pidep"], 0)
        self.assertEqual(below["C4"]["winning_candidates"], ["remaining"])
        self.assertEqual(below["DSD"]["ni_before"], below["DSD"]["ni_after"])
        self.assertEqual(set(exact["C4"]["winning_candidates"]),
                         {"raw", "half_satdt"})
        self.assertEqual(exact["C4"]["producer_pidep"], 0.0)
        self.assertTrue(exact["DSD"]["masks"]["ice_too_large"])
        self.assertEqual(exact["DSD"]["ni_after"], exact["DSD"]["ice_n_at_max"])
        self.assertFalse(above["C4"]["active"])
        self.assertTrue(above["C3"]["ifsat"])
        self.assertEqual(above["DSD"]["ni_before"], above["DSD"]["ni_after"])
        for case in result["low_temperature_supply"].values():
            self.assertTrue(case["C3"]["outer"])
            self.assertLess(case["C3"]["half_satdt"], case["C3"]["deficit_mass_rate"])
            self.assertLess(case["C3"]["half_satdt"], case["C3"]["supice"])
            self.assertEqual(case["subcycles"][0]["ice_by_column"], [1.0, 1.0])
        self.assertGreater(result["low_temperature_offset_over_spacing"], 10.0)

    def test_mutated_source_rejected(self):
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
