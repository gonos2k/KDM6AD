"""Active native D1 producer source-order and derivative regression."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "native_d1_producer_replay", HERE / "replay.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("native D1 producer replay import failed")
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


class NativeD1ProducerAD(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = replay.replay()

    def test_baseline_source_order_and_sequential_temperature(self) -> None:
        result = self.result
        self.assertEqual(result["capture_rows"], 6630)
        self.assertEqual(result["parent_rows_raw_bit_equal"], 4485)
        self.assertEqual(result["baseline_producer"]["raw_bit_replayed_levels"], 39)
        self.assertEqual(
            len(result["baseline_producer"]["source_order_derived_fields"]), 22
        )
        self.assertTrue(result["parent_sedimentation_and_D1_state_raw_bit_replayed"])
        level = result["baseline_producer"]["native16"]
        self.assertLess(level["psmlt_capped_g"], 0)
        self.assertLess(level["pgmlt_capped_g"], 0)
        self.assertLess(level["t1"], level["t"])
        self.assertGreater(
            result["baseline_producer"]["native16_snow_available_margin"], 0
        )
        self.assertGreater(
            result["baseline_producer"]["native16_graupel_available_margin"], 0
        )
        self.assertGreater(
            abs(
                result["baseline_producer"][
                    "native16_sequential_minus_parallel_pgmlt_raw"
                ]
            ),
            1e-8,
        )
        self.assertEqual(
            result["source_and_run"]["endpoint_sha256"],
            "225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070",
        )

    def test_independent_jvp_vjp_and_branch_preserving_fd(self) -> None:
        data = self.result["conditional_derivatives"]
        self.assertTrue(all(data["baseline_branch_signature"]))
        qv = data["directions"]["relative_qv16"]
        temp = data["directions"]["absolute_t16"]
        self.assertEqual(qv["jvp"][:3], [0, 0, 0])
        self.assertAlmostEqual(qv["jvp"][3], 0.00027883757429813735, delta=1e-14)
        self.assertAlmostEqual(qv["jvp"][6], -2.306241751629388e-9, delta=1e-18)
        self.assertAlmostEqual(qv["jvp"][7], 0.0003038600461751968, delta=1e-13)
        self.assertAlmostEqual(temp["jvp"][2], -8.666008166953617e-5, delta=1e-14)
        self.assertAlmostEqual(temp["jvp"][6], -8.022696118851808e-6, delta=1e-15)
        self.assertAlmostEqual(temp["jvp"][7], 0.9672106810027554, delta=1e-11)
        for name, direction in data["directions"].items():
            with self.subTest(direction=name):
                self.assertAlmostEqual(
                    direction["weighted_vjp_contraction"],
                    direction["weighted_jvp_contraction"],
                    delta=1e-12,
                )
                for step in direction["finite_differences"].values():
                    self.assertLessEqual(
                        step["max_nonzero_relative_fd_jvp_error"], 1e-6
                    )
                    self.assertGreater(step["temperature_signal_ulps"], 1e6)

    def test_rehashed_producer_intermediate_and_cap_mutations_fail(self) -> None:
        cases = (
            ("t1", "40712a274f20063d"),
            ("psmlt_raw", "0"),
            ("pgmlt_capped_g", "0"),
            ("precs2", "0"),
        )
        for field, word in cases:
            with self.subTest(field=field):
                bad = changed(replay.STAGE, field, replay.TARGET, word)
                with self.assertRaisesRegex(ValueError, "D1 producer"):
                    replay.replay(
                        capture_override=bad,
                        capture_sha=hashlib.sha256(bad).hexdigest(),
                    )

    def test_rhox_rehash_is_outside_selected_mass_and_heat_map(self) -> None:
        # D1 consumes rhox on its separate delta_brs/BRS path. This packet
        # verifies the snow/graupel mass rates and temperature, not BRS.
        altered = changed(replay.STAGE, "rhox", replay.TARGET, "408c1f5e11cf6bb3")
        result = replay.replay(
            capture_override=altered,
            capture_sha=hashlib.sha256(altered).hexdigest(),
        )
        self.assertEqual(result, self.result)

    def test_rehashed_identity_and_parent_row_mutations_fail(self) -> None:
        raw = (HERE / replay.CAPTURE).read_text()
        bad = raw.replace(
            ",27945,23,32248,39,d1_melt_producer,qs,",
            ",27945,23,32712,39,d1_melt_producer,qs,",
            1,
        ).encode()
        self.assertNotEqual(bad, raw.encode())
        with self.assertRaisesRegex(ValueError, "producer call/tile identity"):
            replay.replay(
                capture_override=bad, capture_sha=hashlib.sha256(bad).hexdigest()
            )
        old = changed("c3_pre_mf_d1", "psmlt_capped", replay.TARGET, "0")
        with self.assertRaisesRegex(ValueError, "parent 4485 raw words"):
            replay.replay(
                capture_override=old, capture_sha=hashlib.sha256(old).hexdigest()
            )

    def test_cli(self) -> None:
        done = subprocess.run(
            [sys.executable, str(HERE / "replay.py")],
            cwd=HERE.parents[2],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("NATIVE_D1_MELT_PRODUCER_AD_REPLAY_PASSED", done.stdout)


if __name__ == "__main__":
    unittest.main()
