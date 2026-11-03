"""Same-call D1 numerical handoff and conditional derivative regression."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("native_d1_ad_replay", HERE / "replay.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("native D1 AD replay import failed")
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)


def changed(stage: str, field: str, k_zero: int, raw_hex: str) -> bytes:
    lines = (HERE / replay.CAPTURE_NAME).read_text().splitlines()
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


class NativeD1ConditionalAD(unittest.TestCase):
    def test_same_call_replay_and_no_splice_chain(self) -> None:
        r = replay.replay()
        self.assertEqual(r["parent_rows_raw_bit_equal"], 3471)
        self.assertEqual(r["new_rows"], 507)
        self.assertEqual(r["d1_stores"]["melted_native_levels"], [15])
        self.assertEqual(r["no_splice_chain"]["fixed_speed_c3_ni_raw_bit_matches"], 39)
        self.assertFalse(r["no_splice_chain"]["hardcoded_qi15_splice"])
        level15 = r["d1_stores"]["level15"]
        self.assertEqual(level15["pimlt_qi"], level15["qi_before"])
        self.assertEqual(
            level15["qc_before"] + level15["qi_before"], level15["qc_after_store2"]
        )
        self.assertEqual(level15["qi_after_store2"], 0)
        self.assertLess(level15["t_after_d1"], level15["t_before"])

    def test_conditional_jvp_vjp_and_represented_differences(self) -> None:
        r = replay.replay()
        d = r["conditional_derivatives"]
        q = r["d1_stores"]["level15"]["qi_before"]
        self.assertEqual(d["output_order"], ("QC", "QI", "NC", "NI", "T"))
        self.assertEqual(d["qi_relative_jvp"][0], q)
        self.assertEqual(d["qi_relative_jvp"][1:4], [0, 0, 0])
        self.assertLess(d["qi_relative_jvp"][4], 0)
        self.assertEqual(d["ni_positive_absolute_jvp"][2], 1)
        self.assertTrue(d["ni_zero_gate_boundary"])
        fd = d["qi_relative_finite_differences"]["0.001"]
        self.assertGreater(abs(fd["output_difference"][4]) / fd["output_ulp"][4], 100)
        self.assertLess(abs(fd["fd_minus_jvp"][4]), 6e-11)

    def test_rehashed_new_operand_and_output_mutations_are_rejected(self) -> None:
        for field, word, error in (
            ("qv_before", "3ff0000000000000", "D1 QV-to-cpm producer"),
            ("cpm_safe", "408f866077ac2b34", "D1 cpm clamp"),
            ("qc_after_store2", "3e958aa28ec12560", "D1 source-order qc_after_store2"),
            ("t_after_d1", "407139f99f0d0156", "D1 source-order t_after_d1"),
        ):
            with self.subTest(field=field):
                bad = changed("c3_pre_mf_d1", field, 24, word)
                with self.assertRaisesRegex(ValueError, error):
                    replay.replay(
                        capture_override=bad,
                        capture_sha=hashlib.sha256(bad).hexdigest(),
                    )

    def test_rehashed_parent_and_identity_mutations_are_rejected(self) -> None:
        bad = changed("c3_pre_mf_d1", "pimlt_qi", 24, "0")
        with self.assertRaisesRegex(ValueError, "D1 parent raw bits"):
            replay.replay(
                capture_override=bad, capture_sha=hashlib.sha256(bad).hexdigest()
            )
        raw = (HERE / replay.CAPTURE_NAME).read_text()
        bad = raw.replace(
            ",22617,24,32248,39,c3_pre_mf_d1,qc_before,",
            ",22617,24,32712,39,c3_pre_mf_d1,qc_before,",
            1,
        ).encode()
        self.assertNotEqual(raw.encode(), bad)
        with self.assertRaisesRegex(ValueError, "D1 AD same-call tile identity"):
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
        self.assertIn("NATIVE_QNICE_D1_CONDITIONAL_AD_REPLAY_PASSED", done.stdout)


if __name__ == "__main__":
    unittest.main()
