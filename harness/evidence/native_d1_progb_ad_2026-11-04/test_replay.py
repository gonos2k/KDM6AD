"""Same-call post-D1 ProgB density and BRS derivative regression."""

from __future__ import annotations

import hashlib
import importlib.util
import math
from pathlib import Path
import subprocess
import sys
import unittest

import torch


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "native_d1_progb_replay", HERE / "replay.py"
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("native post-D1 ProgB replay import failed")
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


class NativeD1ProgBAD(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = replay.replay()

    def test_same_call_progb_operands_and_reclamp(self) -> None:
        result = self.result
        self.assertEqual(result["capture_rows"], 8892)
        self.assertEqual(result["prior_rows_raw_bit_equal"], 7917)
        base = result["baseline"]
        self.assertEqual(base["levels_raw_bit_replayed"], 39)
        self.assertEqual(
            base["branch_counts"],
            {"inactive": 31, "lower": 0, "interior": 8, "upper": 0},
        )
        cell = base["native16"]
        self.assertEqual(cell["idx_left"], 7)
        self.assertEqual(cell["idx_right"], 8)
        self.assertEqual(cell["rhox_op"], 899.9209324078314)
        self.assertEqual(cell["rhox_c"], cell["rhox_op"])
        self.assertEqual(cell["bg_new"], cell["bg"])
        self.assertEqual(base["native16_merged_brs"], cell["bg_new"])
        self.assertEqual(
            result["source_and_run"]["off_on_endpoint_sha256"],
            "225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070",
        )

    def test_branch_local_jvp_vjp_and_fd(self) -> None:
        data = self.result["conditional_derivatives"]
        self.assertEqual(
            data["baseline_branch_signature"][1], (True, True, True, True, 7, 8)
        )
        for name in (
            "relative_qv16",
            "absolute_t16",
            "relative_qg16",
            "relative_rhox16",
        ):
            with self.subTest(direction=name):
                direction = data["directions"][name]
                dot = direction["weighted_jvp_contraction"]
                self.assertAlmostEqual(
                    direction["weighted_vjp_contraction"],
                    dot,
                    delta=2e-8 * max(1e-12, abs(dot)),
                )
                for step in direction["finite_differences"].values():
                    self.assertLess(step["endpoint_rho_raw"][1], 900.0)
                    self.assertGreater(step["endpoint_rho_raw"][0], 800.0)
                    self.assertLess(step["max_normalized_fd_jvp_error"], 1e-6)
        order = data["output_order"]
        qg = dict(zip(order, data["directions"]["relative_qg16"]["jvp"]))
        self.assertGreater(qg["rhox"], 0)
        self.assertEqual(qg["brs_reclamped"], 0)
        rhox = dict(zip(order, data["directions"]["relative_rhox16"]["jvp"]))
        self.assertLess(rhox["rhox"], 0)
        self.assertGreater(rhox["brs_reclamped"], 0)

    def test_explicit_qg_upper_cap_crossing(self) -> None:
        cross = self.result["conditional_derivatives"]["qg_cross_cap"]
        self.assertGreater(cross["critical_positive_relative_step"], 1e-5)
        self.assertLess(cross["critical_positive_relative_step"], 1e-4)
        self.assertLess(cross["lower_rho_raw"], 900.0)
        self.assertGreater(cross["upper_rho_raw"], 900.0)
        self.assertEqual(cross["upper_rhox"], 900.0)
        self.assertNotEqual(cross["cross_branch_secant"][3], cross["local_jvp"][3])

    def test_synthetic_gates_caps_and_table_knots(self) -> None:
        bg = 2.0**-20
        for bound in (100.0, 800.0, 900.0):
            qg = bound * bg
            for candidate in (
                math.nextafter(qg, 0.0),
                qg,
                math.nextafter(qg, math.inf),
            ):
                with self.subTest(bound=bound, qg=candidate):
                    scalar = replay.scalar_progb(candidate, bg)
                    output, _ = replay.torch_progb(
                        torch.tensor(candidate, dtype=torch.float64),
                        torch.tensor(bg, dtype=torch.float64),
                    )
                    for i, field in enumerate(
                        ("qg", "bg", "rhox_op", "rhox", "bg_new", "avtg", "bvtg")
                    ):
                        self.assertEqual(
                            replay.word(output[i].item()), replay.word(scalar[field])
                        )
            exact = replay.scalar_progb(qg, bg)
            self.assertEqual(exact["rhox"], bound)
        inactive = replay.scalar_progb(1e-9, 1e-15)
        self.assertFalse(inactive["active"])
        self.assertEqual(inactive["rhox"], 400.0)
        self.assertEqual(inactive["bg_new"], 1e-15)
        self.assertEqual(inactive["avtg"], 0)
        active = replay.scalar_progb(math.nextafter(1e-9, math.inf), 1e-15)
        self.assertTrue(active["active"])
        self.assertEqual(active["rhox"], 900.0)
        brs_only = replay.scalar_progb(0.0, math.nextafter(1e-15, math.inf))
        self.assertTrue(brs_only["active"])
        self.assertEqual(brs_only["rhox"], 100.0)
        self.assertEqual(brs_only["bg_new"], 0.0)
        brs_output, brs_signature = replay.torch_progb(
            torch.tensor(0.0, dtype=torch.float64),
            torch.tensor(math.nextafter(1e-15, math.inf), dtype=torch.float64),
        )
        self.assertTrue(brs_signature[0])
        self.assertEqual(
            replay.word(brs_output[3].item()), replay.word(brs_only["rhox"])
        )
        self.assertEqual(
            replay.word(brs_output[4].item()), replay.word(brs_only["bg_new"])
        )

    def test_inactive_merged_rhox_rehash_is_outside_history_replay(self) -> None:
        # k=24 has a retained, nonzero merged rhox, but its producer history
        # is outside this packet. The default path still pins the full CSV.
        original = (HERE / replay.CAPTURE).read_bytes()
        altered = changed(replay.MERGE, "rhox", 24, "0")
        self.assertNotEqual(altered, original)
        result = replay.replay(
            capture_override=altered,
            capture_sha=hashlib.sha256(altered).hexdigest(),
        )
        self.assertEqual(result, self.result)

    def test_rehashed_new_and_parent_mutations_fail(self) -> None:
        for stage, field, raw in (
            (replay.STAGE, "rhox_op", "0"),
            (replay.STAGE, "rhox_c", "0"),
            (replay.STAGE, "bg_new", "0"),
            (replay.STAGE, "idx_left", "0"),
            (replay.MERGE, "bg", "0"),
        ):
            with self.subTest(stage=stage, field=field):
                bad = changed(stage, field, replay.TARGET, raw)
                with self.assertRaises(ValueError):
                    replay.replay(
                        capture_override=bad,
                        capture_sha=hashlib.sha256(bad).hexdigest(),
                    )
        bad = changed("d1_melt_consumer", "brs_after", replay.TARGET, "0")
        with self.assertRaisesRegex(ValueError, "parent 7917 rows"):
            replay.replay(
                capture_override=bad, capture_sha=hashlib.sha256(bad).hexdigest()
            )

    def test_rehashed_identity_and_order_mutations_fail(self) -> None:
        raw = (HERE / replay.CAPTURE).read_text()
        bad = raw.replace(
            ",27945,23,32248,39,d1_postmelt_progb,qg,",
            ",27945,23,32712,39,d1_postmelt_progb,qg,",
            1,
        ).encode()
        self.assertNotEqual(bad, raw.encode())
        with self.assertRaisesRegex(ValueError, "ProgB call identity"):
            replay.replay(
                capture_override=bad, capture_sha=hashlib.sha256(bad).hexdigest()
            )
        lines = raw.splitlines()
        first = next(
            i for i, line in enumerate(lines) if ",d1_postmelt_progb,qg," in line
        )
        lines[first], lines[first + 1] = lines[first + 1], lines[first]
        reordered = ("\n".join(lines) + "\n").encode()
        with self.assertRaisesRegex(ValueError, "ProgB row order"):
            replay.replay(
                capture_override=reordered,
                capture_sha=hashlib.sha256(reordered).hexdigest(),
            )

    def test_cli(self) -> None:
        done = subprocess.run(
            [sys.executable, str(HERE / "replay.py")],
            cwd=HERE.parents[2],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("NATIVE_D1_PROGB_AD_REPLAY_PASSED", done.stdout)


if __name__ == "__main__":
    unittest.main()
