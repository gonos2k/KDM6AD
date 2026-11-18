"""Regression checks for the pinned same-call native D1 QI trace."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("native_d1_qi_replay", HERE / "replay.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("native D1 replay import failed")
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)


def changed(stage: str, field: str, k_zero: int, raw_hex: str) -> bytes:
    lines = (HERE / replay.RAW_NAME).read_text().splitlines()
    found = 0
    for i, line in enumerate(lines):
        cells = line.split(",")
        if len(cells) == 11 and (cells[4], cells[7], cells[8]) == (
            str(k_zero),
            stage,
            field,
        ):
            cells[-1] = raw_hex
            lines[i] = ",".join(cells)
            found += 1
    if found != 1:
        raise AssertionError("mutation target is not unique")
    return ("\n".join(lines) + "\n").encode()


class NativeD1QIReplay(unittest.TestCase):
    def test_full_39_level_replay_and_level15_attribution(self) -> None:
        result = replay.replay()
        self.assertEqual(result["parent_rows_raw_bit_equal"], 2769)
        self.assertEqual(result["new_rows"], 702)
        self.assertEqual(result["d1_melt_native_levels"], [15])
        self.assertEqual(result["homogeneous_freeze_native_levels"], [])
        level = result["level15"]
        self.assertEqual(level["post_sed_qi"], 6.109135817357022e-11)
        self.assertEqual(level["d1_applied_pimlt_qi"], level["post_sed_qi"])
        self.assertGreater(level["d1_temperature_K"], 273.15)
        self.assertEqual(level["d1_first_store_qi"], 0.0)
        self.assertEqual(level["snap_a_input_qi"], 0.0)
        self.assertEqual(result["scientific_status"], "INCONCLUSIVE")

    def test_actual_cli(self) -> None:
        done = subprocess.run(
            [sys.executable, str(HERE / "replay.py")],
            cwd=HERE.parents[2],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("NATIVE_QNICE_D1_QI_REPLAY_PASSED", done.stdout)

    def test_rehashed_melt_amount_is_rejected(self) -> None:
        bad = changed("c3_pre_mf_d1", "pimlt_qi", 24, "0")
        with self.assertRaisesRegex(ValueError, "D1 melt producer raw bits"):
            replay.replay(
                capture_override=bad, capture_sha=hashlib.sha256(bad).hexdigest()
            )

    def test_rehashed_store_and_homogeneous_output_are_rejected(self) -> None:
        for stage, field, expected in (
            ("c3_pre_mf_d1", "qi_after_store1", "D1 QI store1 raw bits"),
            ("c3_pre_homogeneous_freeze", "qi_after", "homogeneous QI raw bits"),
        ):
            with self.subTest(stage=stage, field=field):
                bad = changed(stage, field, 24, "3cb0000000000000")
                with self.assertRaisesRegex(ValueError, expected):
                    replay.replay(
                        capture_override=bad,
                        capture_sha=hashlib.sha256(bad).hexdigest(),
                    )

    def test_rehashed_old_record_and_call_identity_are_rejected(self) -> None:
        old = changed("c3_pre_snap_a", "qi", 24, "3cb0000000000000")
        with self.assertRaisesRegex(ValueError, "parent record raw bits"):
            replay.replay(
                capture_override=old, capture_sha=hashlib.sha256(old).hexdigest()
            )
        raw = (HERE / replay.RAW_NAME).read_text()
        bad = raw.replace(
            ",22617,24,32248,39,c3_pre_mf_d1,qi_before,",
            ",22617,24,32712,39,c3_pre_mf_d1,qi_before,",
            1,
        ).encode()
        self.assertNotEqual(bad, raw.encode())
        with self.assertRaisesRegex(ValueError, "same-call tile identity"):
            replay.replay(
                capture_override=bad, capture_sha=hashlib.sha256(bad).hexdigest()
            )


if __name__ == "__main__":
    unittest.main()
