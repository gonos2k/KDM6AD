"""Native selected-column QI applied transport and active D1 replay."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "native_qi_d1_active_replay", HERE / "replay.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("native QI applied replay import failed")
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)


def changed(stage: str, field: str, k_zero: int, raw_hex: str) -> bytes:
    lines = (HERE / replay.CAPTURE).read_text().splitlines()
    matches = 0
    for i, line in enumerate(lines):
        cells = line.split(",")
        if len(cells) == 11 and (cells[4], cells[7], cells[8]) == (
            str(k_zero),
            stage,
            field,
        ):
            cells[-1] = raw_hex
            lines[i] = ",".join(cells)
            matches += 1
    if matches != 1:
        raise AssertionError("mutation target is not unique")
    return ("\n".join(lines) + "\n").encode()


class NativeQIAppliedD1(unittest.TestCase):
    def test_same_call_applied_amounts_and_active_melt(self) -> None:
        result = replay.replay()
        self.assertEqual(result["capture_rows"], 4485)
        self.assertEqual(result["call"]["native_ij_1based"], [203, 149])
        self.assertEqual(result["call"]["b_zero"], 27945)
        self.assertEqual(result["sedimentation"]["raw_bit_replayed_levels"], 39)
        self.assertEqual(result["d1"]["raw_bit_replayed_levels"], 39)
        self.assertIn(16, result["d1"]["nonzero_snow_melt_native_levels"])
        self.assertIn(16, result["d1"]["nonzero_graupel_melt_native_levels"])
        self.assertIn(16, result["d1"]["nonzero_ice_melt_native_levels"])
        self.assertAlmostEqual(result["native17_actual_out_qi"], 1.524431280686188e-10)
        self.assertAlmostEqual(result["native16_actual_in_qi"], 1.5404679459033794e-10)
        self.assertEqual(
            result["native16_D1_applied_ice_melt"], result["native16_post_sed_qi"]
        )
        self.assertEqual(
            result["source_and_run"]["endpoint_sha256"],
            "225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070",
        )

    def test_state_replay_and_budget_are_distinct(self) -> None:
        result = replay.replay()
        budget = result["sedimentation"]
        self.assertEqual(budget["capped_departure_native_levels"], [])
        self.assertEqual(budget["bottom_actual_departure_mass"], 0)
        self.assertGreater(budget["mass_coordinate_change"], 0)
        self.assertGreater(budget["arithmetic_closure_residual"], 0)
        self.assertGreater(budget["max_abs_interface_mass_difference"], 0)
        self.assertLess(budget["max_abs_interface_mass_difference"], 1e-20)

    def test_rehashed_applied_amount_and_D1_melt_mutations_fail(self) -> None:
        cases = (
            (
                replay.SED,
                "applied_out_qi",
                39 - 17,
                "0",
                "source-order QI sedimentation",
            ),
            (
                replay.SED,
                "applied_in_qi",
                39 - 16,
                "0",
                "source-order QI sedimentation",
            ),
            ("c3_pre_mf_d1", "psmlt_capped", 39 - 16, "0", "D1 source-order state"),
        )
        for stage, field, k, word, expected in cases:
            with self.subTest(field=field):
                bad = changed(stage, field, k, word)
                with self.assertRaisesRegex(ValueError, expected):
                    replay.replay(
                        capture_override=bad,
                        capture_sha=hashlib.sha256(bad).hexdigest(),
                    )

    def test_rehashed_call_identity_and_row_order_fail(self) -> None:
        raw = (HERE / replay.CAPTURE).read_text()
        altered = raw.replace(
            ",27945,23,32248,39,c3_pre_mf_d1,qi_before,",
            ",27945,23,32712,39,c3_pre_mf_d1,qi_before,",
            1,
        ).encode()
        self.assertNotEqual(altered, raw.encode())
        with self.assertRaisesRegex(ValueError, "native call/tile identity"):
            replay.replay(
                capture_override=altered,
                capture_sha=hashlib.sha256(altered).hexdigest(),
            )
        lines = raw.splitlines()
        lines[100], lines[101] = lines[101], lines[100]
        swapped = ("\n".join(lines) + "\n").encode()
        with self.assertRaisesRegex(ValueError, "native row order signature"):
            replay.replay(
                capture_override=swapped,
                capture_sha=hashlib.sha256(swapped).hexdigest(),
            )

    def test_rehashed_one_ulp_runtime_qv_handoff_fails(self) -> None:
        rows = (HERE / replay.CAPTURE).read_text().splitlines()
        target = next(
            row
            for row in rows
            if ",27945,23,32248,39,runtime_entry_pre_clamp,qv," in row
        )
        adjacent = format(int(target.split(",")[-1], 16) + 1, "x")
        bad = changed("runtime_entry_pre_clamp", "qv", 39 - 16, adjacent)
        with self.assertRaisesRegex(ValueError, "raw-bit handoff"):
            replay.replay(
                capture_override=bad, capture_sha=hashlib.sha256(bad).hexdigest()
            )

    def test_cli(self) -> None:
        done = subprocess.run(
            [sys.executable, str(HERE / "replay.py")],
            cwd=HERE.parents[2],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("NATIVE_QI_APPLIED_D1_ACTIVE_REPLAY_PASSED", done.stdout)


if __name__ == "__main__":
    unittest.main()
