import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import replay


class ProfileJvpReplayTest(unittest.TestCase):
    def test_real_column_replay(self):
        with contextlib.redirect_stdout(io.StringIO()) as captured:
            replay.main()
        result = json.loads(captured.getvalue())
        self.assertEqual(result["status"], "PROFILE_JVP_REPLAY_PASSED")
        self.assertEqual(result["scientific_status"], "INCONCLUSIVE")
        self.assertEqual(result["native_ijk"], [164, 242, 21])
        self.assertEqual(result["rttov_row"], 45)
        self.assertGreater(result["directions"]["coupled"]["jvp"][1], 0)
        self.assertLess(result["directions"]["raw_ni_only"]["jvp"][1], 0)
        self.assertEqual(result["directions"]["qi_rho_null"]["jvp"], [0.0, 0.0])
        expected = (9.220804259024717e-10, 1.5108492026905118e-9,
                    6.355934847879219e-9, 2.503401740072686e-8)
        for row, maximum in zip(result["real4_secants"], expected):
            self.assertEqual(row["channel_ids"], list(range(10, 17)))
            for name in ("bt_fd_minus_optical_k", "content_curvature_k",
                         "diameter_curvature_k", "bt_fd_minus_profile_jvp_k",
                         "decomposition_roundoff"):
                self.assertEqual(len(row[name]), 7)
            self.assertAlmostEqual(row["max_abs_bt_fd_minus_profile_jvp_k"],
                                   maximum, delta=1e-13)

    def test_mutated_column_is_rejected_before_jvp(self):
        raw = bytearray(replay.FIXTURE.read_bytes())
        raw[-1] ^= 1
        with tempfile.TemporaryDirectory() as tmp:
            changed = Path(tmp) / "native_column.npz"
            changed.write_bytes(raw)
            with patch.object(replay, "FIXTURE", changed), self.assertRaisesRegex(ValueError, "native fixture digest"):
                replay.main()

    def test_zero_jvp_cannot_pass_analytic_check(self):
        def wrong_jvp(*_args):
            return {
                name: np.zeros((1, 67 if name == "P_HALF" else 66), dtype=np.float64)
                for name in replay.PROFILE_FIELDS
            }

        with patch.object(replay, "profile_jvp", wrong_jvp):
            with self.assertRaisesRegex(ValueError, "qi_only content JVP"):
                replay.main()


if __name__ == "__main__":
    unittest.main()
