"""The captured ice slope/intercept response reaches C4 and the ice update."""

import importlib
import json
import unittest
from pathlib import Path

module = importlib.import_module(
    "harness.evidence.native_c5_limiter_call_2026-11-01.ice_auxiliary_ad")


class IceAuxiliaryAD(unittest.TestCase):
    def test_two_native_cells(self):
        for level in (20, 22):
            with self.subTest(level=level):
                result = module.diagnose(level)
                self.assertIn("INCONCLUSIVE", result["status"])
                for direction in result["directions"].values():
                    self.assertAlmostEqual(
                        direction["extra_qi_from_auxiliary"],
                        direction["independent_extra_qi"], delta=2e-15)
                    self.assertLess(abs(direction["vjp_dual_error"]), 2e-11)
                    self.assertLess(
                        abs(direction["fd_minus_actual_jvp"][0]), 2e-14)
                    self.assertLess(
                        abs(direction["fd_minus_actual_jvp"][1]), 2e-7)
        result = module.diagnose(22)
        self.assertAlmostEqual(
            result["directions"]["relative_qi"]["extra_qi_from_auxiliary"],
            7.237213036e-8, delta=2e-15)
        self.assertAlmostEqual(
            result["directions"]["relative_ni"]["extra_qi_from_auxiliary"],
            1.447442543e-7, delta=2e-15)

    def test_corrupt_intercept_cannot_become_baseline(self):
        source = Path(module.ROOT) / "selected_packet.json"
        packet = json.loads(source.read_bytes())
        row = next(r for r in packet["selected_rows"] if
                   r["k_zero"] == "22" and r["stage"] == "c4_in"
                   and r["field"] == "n0i")
        row["raw_hex"] = format(int(row["raw_hex"], 16) ^ 1, "x")
        original = module.rows_for
        try:
            module.rows_for = lambda level: {
                (r["stage"], r["field"]): r for r in packet["selected_rows"]
                if r["k_zero"] == str(level)}
            with self.assertRaisesRegex(ValueError, "captured ice intercept raw bits"):
                module.diagnose(22)
        finally:
            module.rows_for = original


if __name__ == "__main__":
    unittest.main()
