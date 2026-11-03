"""Focused regression checks for the pinned snap-A local map."""

import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import replay


HERE = Path(__file__).resolve().parent


class SnapALocalReplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = replay.replay()

    def test_six_source_order_baselines_and_saved_reference(self):
        result = self.result
        saved = json.loads((HERE / "results.json").read_bytes())
        self.assertEqual(
            result["changed_native_levels_1based"], [25, 20, 19, 18, 17, 16]
        )
        self.assertEqual(
            result["changed_native_levels_1based"],
            saved["changed_native_levels_1based"],
        )
        self.assertEqual(result["observed_weighted_ni_dz_delta"], 49027.35812796282)
        self.assertTrue(result["baseline_39_outputs_raw_bits_equal"])
        self.assertTrue(result["baseline_39_gates_and_branch_winners_equal"])
        self.assertEqual(result["source_constants"]["pidni_f32_bits"], "44c4597c")
        self.assertLessEqual(result["lambda_raw_max_relative_difference"], 1.0e-12)
        self.assertEqual(result["physical_unit_status"], "INCONCLUSIVE")
        self.assertFalse(result["full_host_or_rttov_derivative_certified"])

    def test_relative_derivative_and_vjp_contract(self):
        result = self.result
        outputs = [item["ni_after"] for item in result["selected_levels"]]
        for direction in ("relative_q", "relative_dend"):
            record = result["relative_directions"][direction]
            for actual, expected in zip(record["jvp"], outputs):
                self.assertTrue(
                    math.isclose(actual, expected, rel_tol=1.0e-13, abs_tol=0.0)
                )
            self.assertEqual(len(record["finite_differences"]), 3)
            for fd in record["finite_differences"]:
                self.assertLess(fd["max_abs_fd_minus_jvp"], 5.0e-9)
                self.assertGreater(fd["min_output_signal_ulps"], 1.0e6)
                self.assertEqual(
                    fd["branch_signature_plus"], result["branch_signature_baseline"]
                )
                self.assertEqual(
                    fd["branch_signature_minus"], result["branch_signature_baseline"]
                )
        self.assertEqual(
            result["relative_directions"]["relative_ni_level20"]["jvp"], [0.0] * 6
        )
        self.assertEqual(result["vjp_ni_level20"], 0.0)
        self.assertLess(
            abs(result["joint_jvp_dot_cotangent"] - result["joint_seed_dot_vjp"]),
            1.0e-12,
        )

    def test_zero_ni_is_a_gate_boundary_not_two_sided_interior(self):
        self.assertEqual(
            self.result["ni_gate_boundary_levels_1based"], [25, 19, 18, 17, 16]
        )
        self.assertFalse(self.result["zero_ni_levels_two_sided_ni_derivative_claimed"])
        q = self.result["selected_levels"][0]["q"]
        den = self.result["selected_levels"][0]["dend"]
        at_zero = replay.scalar_branch(q, 0.0, den)
        below_zero = replay.scalar_branch(q, math.nextafter(0.0, -math.inf), den)
        self.assertTrue(at_zero["active"] and at_zero["low"])
        self.assertFalse(below_zero["active"])
        just_below_q = replay.scalar_branch(
            math.nextafter(replay.Q_GATE, 0.0), 0.0, den
        )
        at_q = replay.scalar_branch(replay.Q_GATE, 0.0, den)
        self.assertFalse(just_below_q["active"])
        self.assertTrue(at_q["active"] and at_q["low"])
        self.assertFalse(
            replay.strict_low_branch(replay.Q_GATE, 0.0, den, ni_interior=False)
        )
        self.assertTrue(replay.strict_low_branch(q, 0.0, den, ni_interior=False))
        self.assertFalse(replay.strict_low_branch(q, 0.0, den, ni_interior=True))

    def test_rehashed_lambda_winner_and_source_snapshot_mutations_fail(self):
        lines = replay.CAPTURE.read_text().splitlines()
        for index, line in enumerate(lines):
            parts = line.split(",")
            if (
                len(parts) == 11
                and parts[4] == "19"
                and parts[7:9] == [replay.STAGE, "lambda_raw"]
            ):
                parts[10] = replay.raw_word(9081.0)
                lines[index] = ",".join(parts)
                break
        else:
            self.fail("native level 20 lambda absent")
        changed = ("\n".join(lines) + "\n").encode()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "mutated.csv"
            path.write_bytes(changed)
            with (
                patch.object(replay, "CAPTURE", path),
                patch.object(
                    replay, "CAPTURE_SHA256", hashlib.sha256(changed).hexdigest()
                ),
            ):
                with self.assertRaisesRegex(
                    ValueError, "captured-gate/lambda inferred branch"
                ):
                    replay.replay()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source_dir = root / "source_snapshots"
            source_dir.mkdir()
            for name in replay.SOURCE_SNAPSHOT_PINS:
                raw = (HERE / "source_snapshots" / name).read_bytes()
                if name == "oracle_fconst.py.txt":
                    raw += b"\n# changed after capture\n"
                (source_dir / name).write_bytes(raw)
            with patch.object(replay, "HERE", root):
                with self.assertRaisesRegex(ValueError, "parent source/result SHA-256"):
                    replay.source_snapshots()

    def test_rehashed_parent_output_mutation_is_rejected(self):
        source = replay.CAPTURE.read_bytes()
        lines = source.decode().splitlines()
        for index, line in enumerate(lines):
            parts = line.split(",")
            if (
                len(parts) == 11
                and parts[4] == "19"
                and parts[7:9] == [replay.STAGE, "ni_after"]
            ):
                parts[10] = format(int(parts[10], 16) ^ 1, "x")
                lines[index] = ",".join(parts)
                break
        else:
            self.fail("native level 20 snap-A output absent")
        changed = ("\n".join(lines) + "\n").encode()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "mutated.csv"
            path.write_bytes(changed)
            with (
                patch.object(replay, "CAPTURE", path),
                patch.object(
                    replay, "CAPTURE_SHA256", hashlib.sha256(changed).hexdigest()
                ),
            ):
                with self.assertRaisesRegex(
                    ValueError, "source-order scalar and oracle NI raw bits"
                ):
                    replay.replay()

    def test_cli(self):
        complete = subprocess.run(
            [sys.executable, str(HERE / "replay.py")],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("NATIVE_QNICE_SNAP_A_LOCAL_AD_REPLAY_PASSED", complete.stdout)


if __name__ == "__main__":
    unittest.main()
