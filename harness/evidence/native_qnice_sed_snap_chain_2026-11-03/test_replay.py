"""Regression checks for the bounded fixed-operand NI chain."""

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


class ConditionalChain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = replay.replay()

    def test_baseline_handoffs_and_unresolved_qi_are_explicit(self):
        r = self.result
        self.assertTrue(r["baseline_39_ni_stage_words_equal"])
        self.assertTrue(r["reconstructed_qi_equals_snap_a_input_in_38_layers"])
        self.assertEqual(r["target_native_levels_1based"], [20, 21, 22, 23])
        self.assertEqual(r["unresolved_qi_native_level_1based"], 15)
        self.assertEqual(r["unresolved_qi_snap_a_input"], 0.0)
        self.assertTrue(
            math.isclose(
                r["unresolved_qi_sed_output"],
                6.109135817357022e-11,
                rel_tol=1.0e-12,
            )
        )
        self.assertFalse(r["native_full_process_derivative_certified"])
        self.assertEqual(r["physical_unit_status"], "INCONCLUSIVE")

    def test_three_sparse_paths_and_represented_differences(self):
        r = self.result
        expectations = {
            "relative_q21": (1.0429468145871474, 0.0, 0.0, 0.0),
            "relative_ni21": (0.0, 0.1358895005804943, 0.0, 0.0),
            "relative_ni23": (0.0, 0.0, 171.31746311439238, 116547.04977661459),
        }
        for name, expected in expectations.items():
            with self.subTest(name=name):
                direction = r["directions"][name]
                self.assertEqual(len(direction["finite_differences"]), 3)
                for got, predicted in zip(direction["jvp"], expected):
                    self.assertTrue(
                        math.isclose(got, predicted, rel_tol=1.0e-12, abs_tol=1.0e-11)
                    )
                for fd in direction["finite_differences"]:
                    self.assertGreater(abs(fd["actual_gap"]), 0.0)
                    self.assertLess(fd["max_scaled_fd_minus_jvp"], 1.0e-9)
                    self.assertEqual(
                        fd["branch_signature_plus"],
                        r["baseline_support_branch_signature"],
                    )
                    self.assertEqual(
                        fd["branch_signature_minus"],
                        r["baseline_support_branch_signature"],
                    )
                    self.assertGreater(fd["snap_b_min_lambda_margin"], 0.0)
                transpose = r["transpose_checks"][name]
                self.assertTrue(
                    math.isclose(
                        transpose["jvp_dot_weight"],
                        transpose["seed_dot_vjp"],
                        rel_tol=1.0e-12,
                        abs_tol=1.0e-10,
                    )
                )

    def test_rehashed_speed_or_snap_b_lambda_change_rejected(self):
        original = replay.CAPTURE.read_bytes()
        for stage, field, native_level, replacement, message in (
            (
                replay.S,
                "workn_qi",
                21,
                replay.bits(1.0),
                "conditional baseline raw-word handoff",
            ),
            (
                "c3_pre_snap_b",
                "lambda_raw",
                20,
                replay.bits(9000.0),
                "captured snap gate/lambda inferred winner",
            ),
            (
                "c3_pre_mf_d1",
                "ni_after_store2",
                39,
                replay.bits(1.0),
                "conditional baseline raw-word handoff",
            ),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as folder:
                lines = original.decode().splitlines()
                for index, line in enumerate(lines):
                    cells = line.split(",")
                    if (
                        len(cells) == 11
                        and cells[4] == str(39 - native_level)
                        and cells[7:9] == [stage, field]
                    ):
                        cells[10] = replacement
                        lines[index] = ",".join(cells)
                        break
                else:
                    self.fail("target row absent")
                raw = ("\n".join(lines) + "\n").encode()
                path = Path(folder) / "rehashed.csv"
                path.write_bytes(raw)
                new_hash = hashlib.sha256(raw).hexdigest()
                local = json.loads(replay.SNAP_A_RESULT.read_bytes())
                local["parent_capture_sha256"] = new_hash
                local_raw = (json.dumps(local, sort_keys=True) + "\n").encode()
                local_path = Path(folder) / "rehashed_snap_a_result.json"
                local_path.write_bytes(local_raw)
                with (
                    patch.object(replay, "CAPTURE", path),
                    patch.object(replay, "CAPTURE_SHA256", new_hash),
                    patch.object(replay, "CAPTURE_PARENT_LINK_SHA256", new_hash),
                    patch.object(replay, "SNAP_A_RESULT", local_path),
                    patch.object(
                        replay,
                        "SNAP_A_RESULT_SHA256",
                        hashlib.sha256(local_raw).hexdigest(),
                    ),
                ):
                    with self.assertRaisesRegex(ValueError, message):
                        replay.replay()

    def test_cli(self):
        result = subprocess.run(
            [sys.executable, str(HERE / "replay.py")],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("NATIVE_QNICE_SED_SNAP_CHAIN_REPLAY_PASSED", result.stdout)


if __name__ == "__main__":
    unittest.main()
