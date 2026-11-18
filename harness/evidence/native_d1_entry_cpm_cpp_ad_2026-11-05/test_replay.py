"""Regression checks for same-call outer entry-cpm handoff and C++ AD."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

import replay

HERE = Path(__file__).resolve().parent


def mutate_capture(stage: str, field: str) -> bytes:
    lines = (HERE / replay.CAPTURE).read_text().splitlines()
    found = 0
    for i, line in enumerate(lines):
        cells = line.split(",")
        if len(cells) == 11 and cells[4] == "23" and cells[7:9] == [stage, field]:
            cells[10] = format(int(cells[10], 16) + 1, "x")
            lines[i] = ",".join(cells)
            found += 1
    if found != 1:
        raise AssertionError("selected capture row not unique")
    return ("\n".join(lines) + "\n").encode()


class NativeD1EntryCpmCppAD(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = replay.replay()
        cls.saved = (
            replay.parent_module()
            .parent_module()
            .parse_json((HERE / "raw/cpp_result.json").read_bytes())
        )

    def test_39_level_handoff_and_cpp_baseline(self) -> None:
        self.assertEqual(self.result["native_rows"], 9750)
        self.assertEqual(self.result["parent_rows_raw_bit_equal"], 9516)
        self.assertEqual(self.result["handoff"]["levels_raw_bit_joined"], 39)
        self.assertEqual(self.result["handoff"]["fresh_equals_applied_levels"], 39)
        self.assertEqual(
            self.result["verified_cpp"]["baseline_raw_bit_equal_outputs"], 27
        )
        self.assertTrue(self.result["verified_cpp"]["joint_first25_jvp_equals_parent"])

    def test_outer_d1_and_joint_tangents_are_distinct(self) -> None:
        dirs = self.saved["directions"]
        outer = dirs["relative_qv_outer16"]["jvp"]
        inner = dirs["relative_qv_d1_16"]["jvp"]
        joint = dirs["relative_qv_joint16"]["jvp"]
        self.assertGreater(outer[25], 6.0)
        self.assertEqual(outer[26], 0.0)
        self.assertEqual(inner[25], 0.0)
        self.assertEqual(inner[26], outer[25])
        self.assertEqual(inner[:25], [0.0] * 25)
        self.assertEqual(joint[:25], outer[:25])
        self.assertEqual(joint[25:], [outer[25], outer[25]])
        self.assertGreater(outer[15], 0.0)

    def test_rehashed_outer_and_received_cpm_mutations_fail(self) -> None:
        for stage, field in (
            ("runtime_entry_thermo", "entry_cpm"),
            ("d1_entry_thermo", "entry_cpm_arg"),
            ("d1_entry_thermo", "fresh_cpm"),
            ("d1_entry_thermo", "applied_cpm"),
            ("runtime_entry_thermo", "qv_for_cpm"),
        ):
            with self.subTest(stage=stage, field=field):
                raw = mutate_capture(stage, field)
                with self.assertRaises(ValueError):
                    replay.replay(
                        capture_override=raw,
                        capture_sha=hashlib.sha256(raw).hexdigest(),
                    )

    def test_rehashed_new_capture_row_reordering_fails(self) -> None:
        lines = (HERE / replay.CAPTURE).read_text().splitlines()
        indices = [
            i
            for i, line in enumerate(lines)
            if ",runtime_entry_thermo,qv_for_cpm,f64," in line
            and line.split(",")[4] in {"23", "24"}
        ]
        self.assertEqual(len(indices), 2)
        lines[indices[0]], lines[indices[1]] = lines[indices[1]], lines[indices[0]]
        raw = ("\n".join(lines) + "\n").encode()
        with self.assertRaisesRegex(ValueError, "old 9516 rows preserved"):
            replay.replay(
                capture_override=raw, capture_sha=hashlib.sha256(raw).hexdigest()
            )

    def _reject_cpp(self, transform) -> None:
        altered = copy.deepcopy(self.saved)
        transform(altered)
        raw = (
            json.dumps(altered, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        with self.assertRaises(ValueError):
            replay.replay(
                output_override=raw, output_sha=hashlib.sha256(raw).hexdigest()
            )

    def test_rehashed_cpp_baseline_and_joint_dots_fail(self) -> None:
        self._reject_cpp(lambda d: d["baseline"]["raw_hex"].__setitem__(25, "0"))

        def forge_dots(d):
            d["directions"]["relative_qv_joint16"]["jvp_dot"] = 0.0
            d["directions"]["relative_qv_joint16"]["vjp_dot"] = 0.0

        self._reject_cpp(forge_dots)

    def test_rehashed_cpp_jvp_and_fd_endpoint_fail(self) -> None:
        self._reject_cpp(
            lambda d: d["directions"]["relative_qv_outer16"]["jvp"].__setitem__(25, 0.0)
        )

        def forge_endpoint(d):
            d["directions"]["relative_qv_outer16"]["finite_differences"]["0.1"]["high"][
                25
            ] = 0.0

        self._reject_cpp(forge_endpoint)

    def test_cli(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(HERE / "replay.py")],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(
            json.loads(proc.stdout)["verified_cpp"]["baseline_raw_bit_equal_outputs"],
            27,
        )


if __name__ == "__main__":
    unittest.main()
