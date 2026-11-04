"""Same-call D1 snow/graupel melt-to-state replay regression."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "native_d1_melt_state_replay", HERE / "replay.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("D1 state replay import failed")
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)


def changed(stage: str, field: str, k: int, raw_hex: str) -> bytes:
    lines = (HERE / replay.CAPTURE).read_text().splitlines()
    matched = 0
    for i, line in enumerate(lines):
        cells = line.split(",")
        if len(cells) == 11 and (cells[4], cells[7], cells[8]) == (
            str(k),
            stage,
            field,
        ):
            cells[-1] = raw_hex
            lines[i] = ",".join(cells)
            matched += 1
    if matched != 1:
        raise AssertionError("mutation target is not unique")
    return ("\n".join(lines) + "\n").encode()


class NativeD1MeltStateAD(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = replay.replay()

    def test_native_baseline_and_sequential_stores(self) -> None:
        result = self.result
        self.assertEqual(result["capture_rows"], 7917)
        self.assertEqual(result["prior_rows_raw_bit_equal"], 6630)
        self.assertEqual(result["baseline"]["levels_raw_bit_replayed"], 39)
        self.assertEqual(result["baseline"]["brs_reslope_changed_native_levels"], [])
        self.assertLess(
            result["baseline"]["max_abs_local_qs_qg_qr_mass_roundoff"], 1e-18
        )
        cell = result["baseline"]["native16"]
        self.assertLess(cell["qs_after"], cell["qs_before"])
        self.assertLess(cell["qg_after"], cell["qg_before"])
        self.assertGreater(cell["qr1"], cell["qr_before"])
        self.assertGreater(cell["qr2"], cell["qr1"])
        self.assertGreater(cell["nr1"], cell["nr_before"])
        self.assertGreater(cell["nr2"], cell["nr1"])
        self.assertLess(cell["brs_after"], cell["brs_before"])
        # This actual f64 cell distinguishes sequential NR stores from summing
        # the two number-transfer terms before subtracting.
        prod = result["baseline"]["native16_producer"]
        ps = -0.00013202611149878743
        pg = -1.2225833390863422e-05
        combined = cell["nr_before"] - (prod["sfac"] * ps + prod["gfac"] * pg)
        self.assertNotEqual(replay.word(combined), replay.word(cell["nr2"]))
        self.assertEqual(
            result["source_and_run"]["off_on_endpoint_sha256"],
            "225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070",
        )

    def test_local_mass_number_brs_jvp_vjp_and_fd(self) -> None:
        data = self.result["conditional_derivatives"]
        names = data["output_order"]
        self.assertTrue(all(data["baseline_branch_signature"]))
        for direction_name in (
            "relative_qv16",
            "absolute_t16",
            "relative_qs16",
            "relative_qg16",
            "relative_rhox16",
        ):
            with self.subTest(direction=direction_name):
                direction = data["directions"][direction_name]
                self.assertAlmostEqual(
                    direction["weighted_vjp_contraction"],
                    direction["weighted_jvp_contraction"],
                    delta=1e-8,
                )
                for step in direction["finite_differences"].values():
                    self.assertLess(step["max_nonzero_relative_fd_jvp_error"], 0.011)
        qv = dict(zip(names, data["directions"]["relative_qv16"]["jvp"]))
        self.assertEqual(qv["qs_after"], 0)
        self.assertLess(qv["qg_after"], 0)
        self.assertGreater(qv["nr_after"], 0)
        self.assertLess(qv["brs_after"], 0)
        temp = dict(zip(names, data["directions"]["absolute_t16"]["jvp"]))
        self.assertGreater(temp["qr_after"], 0)
        self.assertGreater(temp["nr_after"], 0)
        rhox = dict(zip(names, data["directions"]["relative_rhox16"]["jvp"]))
        self.assertGreater(rhox["brs_after"], 0)
        self.assertEqual(rhox["qr_after"], 0)

    def test_rehashed_new_producer_and_consumer_mutations_fail(self) -> None:
        cases = (
            (replay.PRODUCER, "sfac", "0"),
            (replay.PRODUCER, "delta_brs_capped", "0"),
            (replay.CONSUMER, "qr1", "0"),
            (replay.CONSUMER, "nr2", "0"),
            (replay.CONSUMER, "brs_after", "0"),
        )
        for stage, field, word in cases:
            with self.subTest(field=field):
                bad = changed(stage, field, replay.TARGET, word)
                with self.assertRaises(ValueError):
                    replay.replay(
                        capture_override=bad,
                        capture_sha=hashlib.sha256(bad).hexdigest(),
                    )

    def test_rehashed_parent_row_and_order_mutations_fail(self) -> None:
        bad = changed(replay.PRODUCER, "psmlt_raw", replay.TARGET, "0")
        with self.assertRaisesRegex(ValueError, "parent 6630 rows"):
            replay.replay(
                capture_override=bad, capture_sha=hashlib.sha256(bad).hexdigest()
            )
        lines = (HERE / replay.CAPTURE).read_text().splitlines()
        first = next(
            i for i, s in enumerate(lines) if ",d1_melt_consumer,qs_before," in s
        )
        lines[first], lines[first + 1] = lines[first + 1], lines[first]
        reordered = ("\n".join(lines) + "\n").encode()
        with self.assertRaisesRegex(ValueError, "row order"):
            replay.replay(
                capture_override=reordered,
                capture_sha=hashlib.sha256(reordered).hexdigest(),
            )

    def test_rehashed_entry_and_d1_freeze_forgeries_fail(self) -> None:
        for name in ("qr", "nr", "brs"):
            with self.subTest(entry=name):
                bad = changed(replay.ENTRY, name, replay.TARGET, "0")
                with self.assertRaisesRegex(ValueError, "entry-to-consumer handoff"):
                    replay.replay(
                        capture_override=bad,
                        capture_sha=hashlib.sha256(bad).hexdigest(),
                    )
        for name in ("pfrzdtr", "nfrzdtr", "delta_brs_freeze"):
            with self.subTest(freeze=name):
                bad = changed(replay.CONSUMER, name, replay.TARGET, "3ff0000000000000")
                with self.assertRaisesRegex(ValueError, "D1-only freeze amount"):
                    replay.replay(
                        capture_override=bad,
                        capture_sha=hashlib.sha256(bad).hexdigest(),
                    )

        # Preserve the consumer's arithmetic and the two reslope words while
        # forging its BRS input. The independently captured D1-entry word must
        # reject the otherwise self-consistent chain.
        cell = self.result["baseline"]["native16"]
        new_before = cell["brs_before"] + 1e-6
        new_after = (
            new_before
            + self.result["baseline"]["native16_producer"]["delta_brs_capped"]
        )
        replacements = {
            (replay.CONSUMER, "brs_before"): replay.word(new_before),
            (replay.CONSUMER, "brs_after"): replay.word(new_after),
            (replay.RESLOPE, "brs_before"): replay.word(new_after),
            (replay.RESLOPE, "brs_after"): replay.word(new_after),
        }
        lines = (HERE / replay.CAPTURE).read_text().splitlines()
        seen = set()
        for i, line in enumerate(lines):
            cells = line.split(",")
            if len(cells) == 11 and cells[4] == str(replay.TARGET):
                key = (cells[7], cells[8])
                if key in replacements:
                    cells[-1] = replacements[key]
                    lines[i] = ",".join(cells)
                    seen.add(key)
        self.assertEqual(seen, set(replacements))
        forged = ("\n".join(lines) + "\n").encode()
        with self.assertRaisesRegex(ValueError, "entry-to-consumer handoff"):
            replay.replay(
                capture_override=forged,
                capture_sha=hashlib.sha256(forged).hexdigest(),
            )

    def test_cli(self) -> None:
        done = subprocess.run(
            [sys.executable, str(HERE / "replay.py")],
            cwd=HERE.parents[2],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("NATIVE_D1_MELT_STATE_AD_REPLAY_PASSED", done.stdout)


if __name__ == "__main__":
    unittest.main()
