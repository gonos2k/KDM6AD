"""NC16 one-hot C ABI VJP and branch-window replay regressions."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest

import numpy as np

import replay


HERE = Path(__file__).resolve().parent


def changed_result(field: str, index: tuple[int, int], delta: float) -> bytes:
    with np.load(HERE / "raw/nc16_result.npz", allow_pickle=False) as source:
        arrays = {name: np.array(source[name], copy=True) for name in source.files}
    arrays[field][index] += delta
    buf = io.BytesIO()
    np.savez_compressed(buf, **arrays)
    return buf.getvalue()


class NC16VJPReplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = replay.replay()

    def test_one_hot_vjp_full_coordinate_transpose_and_selected_fd(self) -> None:
        result = self.result
        self.assertEqual(result["seed_packed_offset"], 327)
        self.assertEqual(result["seed_native_level"], 16)
        self.assertEqual(result["vjp_finite_cells"], 468)
        self.assertEqual(result["coordinate_jvp_cells"], 468)
        self.assertEqual(result["parent_raw_equal_arrays"], 11)
        self.assertLess(result["coordinate_max_normalized_transpose_gap"], 1e-13)
        cases = {(x["direction"], x["h"]): x for x in result["finite_differences"]}
        self.assertEqual(len(cases), 8)
        for name, hs in replay.LOCAL.items():
            for h in hs:
                self.assertFalse(cases[name, h]["branch_crossing"])
                if (name, h) != ("qv", 1e-5):
                    self.assertLess(cases[name, h]["normalized_fd_jvp"], 5e-6)
        for name, h in replay.CROSSING.items():
            self.assertTrue(cases[name, h]["branch_crossing"])
            self.assertGreater(cases[name, h]["normalized_fd_jvp"], 1e-2)

    def test_rehashed_seed_misplacement_is_rejected(self) -> None:
        with np.load(HERE / "raw/nc16_result.npz", allow_pickle=False) as source:
            arrays = {name: np.array(source[name], copy=True) for name in source.files}
        arrays["seed_nc16"][8, 15] = 0.0
        arrays["seed_nc16"][8, 16] = 1.0
        buf = io.BytesIO()
        np.savez_compressed(buf, **arrays)
        raw = buf.getvalue()
        with self.assertRaisesRegex(ValueError, "NC16 one-hot seed"):
            replay.replay(
                result_override=raw, result_sha=hashlib.sha256(raw).hexdigest()
            )

    def test_rehashed_untested_component_vjp_mutation_is_rejected(self) -> None:
        raw = changed_result("vjp_nc16", (0, 20), 1.0)
        with self.assertRaisesRegex(
            ValueError, "full coordinate JVP/VJP transpose map"
        ):
            replay.replay(
                result_override=raw, result_sha=hashlib.sha256(raw).hexdigest()
            )

    def test_rehashed_coordinate_jvp_mutation_is_rejected(self) -> None:
        raw = changed_result("coordinate_jvp_nc16", (0, 20), 1.0)
        with self.assertRaisesRegex(
            ValueError, "full coordinate JVP/VJP transpose map"
        ):
            replay.replay(
                result_override=raw, result_sha=hashlib.sha256(raw).hexdigest()
            )

    def test_cli_and_saved_result(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(HERE / "replay.py")],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(json.loads(proc.stdout), self.result)
        self.assertEqual(json.loads((HERE / "results.json").read_text()), self.result)


if __name__ == "__main__":
    unittest.main()
