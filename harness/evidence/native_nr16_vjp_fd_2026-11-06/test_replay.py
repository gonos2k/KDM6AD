"""NR16 output-seed VJP and post-hoc saved endpoint FD regressions."""

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


def changed_result(name: str, index: tuple[int, int], delta: float) -> bytes:
    with np.load(HERE / "raw/nr16_result.npz", allow_pickle=False) as source:
        arrays = {key: np.array(source[key], copy=True) for key in source.files}
    arrays[name][index] += delta
    out = io.BytesIO()
    np.savez_compressed(out, **arrays)
    return out.getvalue()


class NR16VJPReplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = replay.replay()

    def test_seed_transpose_and_posthoc_fd_scope(self) -> None:
        result = self.result
        self.assertEqual(result["seed_packed_offset"], 405)
        self.assertEqual(result["seed_native_level"], 16)
        self.assertEqual(result["vjp_finite_cells"], 468)
        self.assertEqual(result["coordinate_jvp_cells"], 468)
        self.assertLess(result["coordinate_max_normalized_transpose_gap"], 1e-13)
        self.assertEqual(result["parent_raw_equal_arrays"], 11)
        self.assertEqual(len(result["comparisons"]), 26)
        self.assertEqual(result["numerical_agreement_pairs"], 21)
        self.assertEqual(result["recorded_cap_unchanged_pairs"], 19)
        self.assertEqual(result["masks_only_pairs"], 2)
        self.assertEqual(result["captured_cap_crossings"], 5)
        self.assertLess(
            result["max_numerical_agreement_true_relative_error"], replay.RELATIVE_GUARD
        )
        cases = {(x["direction"], x["h"]): x for x in result["comparisons"]}
        self.assertTrue(cases["th16_abs", 1e-2]["captured_cap_crossing"])
        self.assertLess(cases["th16_abs", 1e-2]["signal_relative_error"], 1e-5)
        self.assertTrue(cases["qg16_rel", 1e-5]["captured_cap_crossing"])
        self.assertGreater(cases["qg16_rel", 1e-5]["signal_relative_error"], 0.6)
        self.assertFalse(cases["qg_bg17_rel", 1e-3]["captured_cap_crossing"])
        self.assertLess(cases["qg_bg17_rel", 1e-3]["signal_relative_error"], 1e-5)
        for h in replay.OLD_STEPS["qs16_rel"]:
            self.assertIsNone(cases["qs16_rel", h]["captured_cap_crossing"])
            self.assertEqual(
                cases["qs16_rel", h]["cap_status"], "masks_only_unverified"
            )

    def test_rehashed_nc_instead_of_nr_seed_is_rejected(self) -> None:
        with np.load(HERE / "raw/nr16_result.npz", allow_pickle=False) as source:
            arrays = {key: np.array(source[key], copy=True) for key in source.files}
        arrays["seed_nr16"][10, 15] = 0.0
        arrays["seed_nr16"][8, 15] = 1.0
        out = io.BytesIO()
        np.savez_compressed(out, **arrays)
        raw = out.getvalue()
        with self.assertRaisesRegex(ValueError, "NR16 one-hot output seed"):
            replay.replay(
                result_override=raw, result_sha=hashlib.sha256(raw).hexdigest()
            )

    def test_rehashed_untested_vjp_component_is_rejected(self) -> None:
        raw = changed_result("vjp_nr16", (0, 20), 1.0)
        with self.assertRaisesRegex(ValueError, "full coordinate same-graph transpose"):
            replay.replay(
                result_override=raw, result_sha=hashlib.sha256(raw).hexdigest()
            )

    def test_rehashed_coordinate_jvp_is_rejected(self) -> None:
        raw = changed_result("coordinate_jvp_nr16", (0, 20), 1.0)
        with self.assertRaisesRegex(ValueError, "full coordinate same-graph transpose"):
            replay.replay(
                result_override=raw, result_sha=hashlib.sha256(raw).hexdigest()
            )

    def test_coordinated_rehashed_arrays_define_a_validation_limit(self) -> None:
        with np.load(HERE / "raw/nr16_result.npz", allow_pickle=False) as source:
            arrays = {key: np.array(source[key], copy=True) for key in source.files}
        arrays["vjp_nr16"][0, 20] = 1.0
        arrays["coordinate_jvp_nr16"][0, 20] = 1.0
        out = io.BytesIO()
        np.savez_compressed(out, **arrays)
        raw = out.getvalue()
        result = replay.replay(
            result_override=raw, result_sha=hashlib.sha256(raw).hexdigest()
        )
        self.assertEqual(result, self.result)

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
