"""Conditional QV heat-capacity tangent on the captured native D1 call."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "native_d1_cpm_ad_replay", HERE / "replay.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("native D1 cpm replay import failed")
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)


class NativeD1CpmAD(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = replay.replay()

    def test_baseline_raw_words_and_conditional_scope(self) -> None:
        result = self.result
        self.assertEqual(result["baseline_runtime_to_D1_qv_raw_bit_matches"], 39)
        self.assertEqual(result["baseline_cpm_raw_bit_matches"], 39)
        self.assertEqual(result["baseline_cpm_safe_raw_bit_matches"], 39)
        self.assertEqual(result["baseline_no_splice_raw_bit_matches_per_field"], 39)
        self.assertFalse(result["native_full_process_derivative_certified"])
        self.assertEqual(result["physical_unit_status"], "INCONCLUSIVE")

    def test_analytic_jvp_vjp_and_temperature_resolution(self) -> None:
        result = self.result
        self.assertAlmostEqual(
            result["cpm_relative_jvp"], 4.297103257244453, delta=1e-12
        )
        self.assertEqual(result["jvp"][:4], [0, 0, 0, 0])
        self.assertEqual(result["jvp"][5:], [0, 0, 0, 0])
        self.assertAlmostEqual(result["jvp"][4], 9.028507464652678e-11, delta=1e-21)
        self.assertAlmostEqual(
            result["weighted_vjp_contraction"],
            result["weighted_jvp_contraction"],
            delta=1e-19,
        )
        fd = result["finite_differences"]
        self.assertGreater(fd["0.25"]["temperature_signal_ulps"], 700)
        self.assertGreater(fd["0.1"]["temperature_signal_ulps"], 300)
        self.assertLess(fd["0.01"]["temperature_signal_ulps"], 40)
        for step in fd.values():
            self.assertLessEqual(
                abs(step["fd_minus_jvp"][4]), step["temperature_acceptance_bound"]
            )
        self.assertTrue(result["adjacent_qv_has_same_rounded_cpm"])

    def test_one_ulp_qv_collision_is_detected_by_raw_handoff(self) -> None:
        _, _, _, fields, *_ = replay.baseline()
        altered = dict(fields)
        key = ("c3_pre_mf_d1", "qv_before", replay.L15)
        altered[key] = dict(fields[key], raw_hex="3f74e7fd20000001")
        with self.assertRaisesRegex(ValueError, "runtime-to-D1 QV raw handoff"):
            replay.verify_qv_handoff(altered)

    def test_cli(self) -> None:
        done = subprocess.run(
            [sys.executable, str(HERE / "replay.py")],
            cwd=HERE.parents[2],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("NATIVE_QNICE_D1_CPM_AD_REPLAY_PASSED", done.stdout)


if __name__ == "__main__":
    unittest.main()
