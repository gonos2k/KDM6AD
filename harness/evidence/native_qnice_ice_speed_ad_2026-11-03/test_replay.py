"""Focused tests for native ice-speed producer sensitivity."""

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


class IceSpeedProducerAD(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = replay.replay()

    def test_recorded_speed_baseline_and_scope(self):
        result = self.result
        self.assertEqual(
            set(result["baseline_speed_raw_bit_matches"]), {"work1_qi", "workn_qi"}
        )
        self.assertTrue(
            all(0 <= n <= 39 for n in result["baseline_speed_raw_bit_matches"].values())
        )
        self.assertLessEqual(result["baseline_dynamic_minus_fixed_c3_max_abs"], 1.0e-8)
        self.assertEqual(result["target_native_levels_1based"], [20, 21, 22, 23])
        self.assertEqual(result["unresolved_qi_native_level_1based"], 15)
        self.assertFalse(result["native_full_process_derivative_certified"])
        self.assertEqual(result["physical_unit_status"], "INCONCLUSIVE")
        self.assertEqual(result["source_constants"]["pidni"], 1570.79638671875)
        for value in result["selected_active_speed_max_relative_difference"].values():
            self.assertLessEqual(value, 1.0e-12)

    def test_dynamic_speed_path_and_analytic_difference(self):
        directions = self.result["directions"]
        for name in ("relative_q21", "relative_ni21"):
            self.assertEqual(directions[name]["producer_path_delta"], [0.0] * 4)
        q23 = directions["relative_q23"]
        n23 = directions["relative_ni23"]
        self.assertEqual(q23["fixed_speed_jvp"], [0.0] * 4)
        for actual, expected in zip(
            q23["dynamic_speed_jvp"], (0.0, 0.0, 57.10582274001688, -57.59018034479256)
        ):
            self.assertTrue(
                math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-10)
            )
        self.assertLess(n23["dynamic_speed_jvp"][2], n23["fixed_speed_jvp"][2])
        self.assertTrue(
            math.isclose(n23["dynamic_speed_jvp"][2], 114.21164037437548, rel_tol=1e-12)
        )
        for direction in directions.values():
            for actual, predicted in zip(
                direction["dynamic_speed_jvp"], direction["analytic_dynamic"]
            ):
                self.assertTrue(
                    math.isclose(actual, predicted, rel_tol=1e-12, abs_tol=1e-10)
                )

    def test_endpoint_branches_and_represented_spacing(self):
        baseline = self.result["baseline_branch_signature"]
        for name, direction in self.result["directions"].items():
            with self.subTest(name=name):
                self.assertEqual(len(direction["finite_differences"]), 3)
                for fd in direction["finite_differences"]:
                    self.assertNotEqual(fd["actual_gap"], 0.0)
                    self.assertEqual(fd["branch_signature_plus"], baseline)
                    self.assertEqual(fd["branch_signature_minus"], baseline)
                    self.assertGreater(fd["snap_b_min_margin"], 0.0)
                    self.assertLess(
                        fd["max_scaled_fd_minus_jvp"], fd["acceptance_scaled_bound"]
                    )
                    self.assertLess(
                        fd["speed_max_relative_fd_minus_jvp"],
                        fd["speed_acceptance_scaled_bound"],
                    )
        self.assertGreater(
            self.result["baseline_support_margins"]["20"]["snap_b_low_gap"], 0.0
        )

    def test_weighted_vjp_and_transpose(self):
        for name, record in self.result["transpose_checks"].items():
            self.assertTrue(
                math.isclose(
                    record["jvp_dot_weight"],
                    record["seed_dot_vjp"],
                    rel_tol=1e-12,
                    abs_tol=1e-10,
                ),
                name,
            )
        for name, value in self.result["analytic_selected_vjp"].items():
            key = name.replace("relative_", "")
            self.assertTrue(
                math.isclose(
                    value, self.result["selected_vjp"][key], rel_tol=1e-12, abs_tol=1e-9
                )
            )

    def test_rehashed_consumed_speed_and_source_mutation_fail(self):
        lines = replay.CAPTURE.read_text().splitlines()
        for index, line in enumerate(lines):
            cells = line.split(",")
            if (
                len(cells) == 11
                and cells[4] == "16"
                and cells[7:9] == [replay.S, "workn_qi"]
            ):
                cells[10] = replay.word(1.0)
                lines[index] = ",".join(cells)
                break
        else:
            self.fail("native 23 speed row absent")
        raw = ("\n".join(lines) + "\n").encode()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            capture = root / "rehashed.csv"
            capture.write_bytes(raw)
            new_hash = hashlib.sha256(raw).hexdigest()
            parent = json.loads(replay.CHAIN_RESULT.read_bytes())
            parent["parent_capture_sha256"] = new_hash
            parent_raw = (json.dumps(parent, sort_keys=True) + "\n").encode()
            parent_path = root / "parent_result.json"
            parent_path.write_bytes(parent_raw)
            with (
                patch.object(replay, "CAPTURE", capture),
                patch.object(replay, "CAPTURE_SHA256", new_hash),
                patch.object(replay, "CHAIN_RESULT", parent_path),
                patch.object(
                    replay,
                    "CHAIN_RESULT_SHA256",
                    hashlib.sha256(parent_raw).hexdigest(),
                ),
            ):
                with self.assertRaisesRegex(
                    ValueError, "39-level and selected active speed producer baseline"
                ):
                    replay.replay()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            snap = root / "source_snapshots"
            snap.mkdir()
            for name in replay.SOURCE_PINS:
                value = (HERE / "source_snapshots" / name).read_bytes()
                if name == "oracle_slope.py.txt":
                    value += b"\n# changed after capture\n"
                (snap / name).write_bytes(value)
            with patch.object(replay, "HERE", root):
                with self.assertRaisesRegex(ValueError, "pinned input"):
                    replay.source_attribution()

    def test_cli(self):
        complete = subprocess.run(
            [sys.executable, str(HERE / "replay.py")],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("NATIVE_QNICE_ICE_SPEED_AD_REPLAY_PASSED", complete.stdout)


if __name__ == "__main__":
    unittest.main()
