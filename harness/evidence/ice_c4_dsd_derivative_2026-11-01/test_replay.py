import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import replay


class C4DsdDerivativeReplayTest(unittest.TestCase):
    def test_branch_derivatives_and_native_candidate_scope(self):
        with contextlib.redirect_stdout(io.StringIO()) as captured:
            replay.main()
        result = json.loads(captured.getvalue())
        self.assertEqual(result["status"], "ICE_C4_DSD_DERIVATIVE_REPLAY_PASSED")
        self.assertEqual(result["scientific_status"], "INCONCLUSIVE")
        for side in ("below_saturation", "above_saturation"):
            case = result[side]
            self.assertTrue(case["observer_jvp_raw_bits_equal"])
            self.assertTrue(case["checked_branch_and_trace_topology_equal"])
            self.assertNotEqual(case["input"]["nominal_one_sided_delta"],
                                case["input"]["represented_plus_delta"])
            self.assertNotEqual(case["outputs"]["qi"]["actual_output_signal"], 0.0)
            self.assertLess(abs(case["outputs"]["qi"]["actual_minus_jvp"]),
                            1e-6 * abs(case["outputs"]["qi"]["jvp"]))
        below = result["below_saturation"]
        above = result["above_saturation"]
        self.assertEqual(below["branch"]["C4_winners"], ["remaining"])
        self.assertEqual(above["branch"]["C4_winners"], ["inactive_ifsat"])
        self.assertEqual(below["outputs"]["qv"]["actual_output_signal"], 0.0)
        self.assertNotEqual(above["outputs"]["ni"]["actual_output_signal"], 0.0)
        local = result["exact_saturation_dsd_local"]
        self.assertEqual(local["partial_ni_out_by_ni_in"], 0.0)
        self.assertEqual(local["relative_ni_fd"], 0.0)
        self.assertEqual(local["relative_qi_sensitivity"], 1.0)
        self.assertEqual(local["ni_after"], 8.15540970156244)
        native = result["native_candidate_preflight"]
        self.assertIn("not a same-call", native["evidence_class"])
        self.assertLess(native["candidates"]["21"]["qv_minus_qs_ice_reconstructed"], 0)
        self.assertGreater(native["candidates"]["23"]["qv_minus_qs_ice_reconstructed"], 0)

    def test_modified_source_rejected(self):
        manifest = json.loads((replay.ROOT / "source_manifest.json").read_bytes())
        relative = next(iter(manifest))
        with tempfile.TemporaryDirectory() as tmp:
            changed = Path(tmp) / relative
            changed.parent.mkdir(parents=True)
            changed.write_bytes((replay.REPO / relative).read_bytes() + b"\n# changed\n")
            with patch.object(replay, "REPO", Path(tmp)):
                with self.assertRaisesRegex(ValueError, "source digest"):
                    replay.main()


if __name__ == "__main__":
    unittest.main()
