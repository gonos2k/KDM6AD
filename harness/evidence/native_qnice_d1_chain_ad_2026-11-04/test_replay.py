"""Selected conditional native ice-speed and D1 chain checks."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "native_d1_chain_replay", HERE / "replay.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("native D1 chain replay import failed")
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)


class NativeD1SpeedChain(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = replay.replay()

    def test_baseline_no_splice_and_branch_contract(self) -> None:
        result = self.result
        self.assertFalse(result["baseline_fixed_speed"]["hardcoded_qi15_splice"])
        self.assertEqual(
            result["baseline_fixed_speed"]["raw_bit_matches_per_field"], 39
        )
        self.assertEqual(len(result["baseline_fixed_speed"]["checked_fields"]), 13)
        self.assertEqual(result["native16_relative_speed_jvp"], 0)
        self.assertFalse(result["native_full_process_derivative_certified"])
        signature = result["branch_signature_selected_15_16_22_23"]
        self.assertEqual(signature[0][6], "tie")  # Native 15 zero departure.
        self.assertTrue(signature[0][8])  # Warm, positive post-sed QI melts.
        self.assertFalse(signature[0][9])  # Post-D1 snap A QI gate inactive.
        self.assertTrue(signature[1][3])  # Native 16 slope lower clamp.
        self.assertTrue(signature[1][10])  # Snap A lower rewrite.
        self.assertTrue(signature[1][12])  # Snap B remains active.
        self.assertFalse(signature[1][13])  # Snap B is interior.

    def test_d1_and_speed_producer_jvps_vjps_and_fd_resolution(self) -> None:
        result = self.result
        paths = result["input_directions"]
        q16 = paths["relative_qi16"]["jvp"]
        q23 = paths["relative_qi23"]["jvp"]
        mixed = paths["relative_qi16_qi23"]["jvp"]
        self.assertAlmostEqual(q16[0], 6.10913581735702e-11, delta=1e-21)
        self.assertEqual(q16[1:4], [0, 0, 0])
        self.assertAlmostEqual(q16[4], -2.119551621600676e-8, delta=1e-18)
        self.assertAlmostEqual(q16[6], 0.354010809709542, delta=1e-12)
        self.assertAlmostEqual(q23[7], 57.10582274001688, delta=1e-9)
        self.assertAlmostEqual(q23[8], -57.59018034479256, delta=1e-9)
        for got, left, right in zip(mixed, q16, q23, strict=True):
            self.assertAlmostEqual(got, left + right, delta=1e-11)
        for path in paths.values():
            self.assertAlmostEqual(
                path["weighted_vjp_contraction"],
                path["weighted_jvp_contraction"],
                delta=1e-9,
            )
            self.assertTrue(
                all(
                    step["max_normalized_fd_residual"] <= step["acceptance_bound"]
                    for step in path["finite_differences"].values()
                )
            )
        fd = paths["relative_qi16"]["finite_differences"]["0.001"]
        self.assertGreater(abs(fd["output_difference"][4]) / fd["output_ulp"][4], 700)
        self.assertAlmostEqual(fd["represented_input_gaps"]["16"], 0.002, delta=1e-14)

    def test_changed_consumed_speed_or_heat_capacity_breaks_baseline(self) -> None:
        d1, speed, fields, q0, n0, op, fixed, _ = replay.load()
        params = speed.default_slope_params()
        bad_op = dict(op)
        bad_op["work1_qi"] = op["work1_qi"].clone()
        bad_op["work1_qi"][replay.L16] *= 1.001
        output, parts = replay.chain(
            q0, n0, speed, bad_op, fixed, params, dynamic=False
        )
        with self.assertRaisesRegex(ValueError, "fixed-speed no-splice raw bits"):
            replay.raw_baseline(d1, fields, parts, output)
        bad_fixed = dict(fixed)
        bad_fixed["cpm_safe"] = fixed["cpm_safe"].clone()
        bad_fixed["cpm_safe"][replay.L15] *= 1.001
        output, parts = replay.chain(
            q0, n0, speed, op, bad_fixed, params, dynamic=False
        )
        with self.assertRaisesRegex(ValueError, "fixed-speed no-splice raw bits"):
            replay.raw_baseline(d1, fields, parts, output)

    def test_cli(self) -> None:
        done = subprocess.run(
            [sys.executable, str(HERE / "replay.py")],
            cwd=HERE.parents[2],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("NATIVE_QNICE_D1_SPEED_CHAIN_AD_REPLAY_PASSED", done.stdout)


if __name__ == "__main__":
    unittest.main()
