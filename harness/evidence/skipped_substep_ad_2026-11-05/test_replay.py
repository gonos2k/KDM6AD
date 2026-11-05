"""Regression checks for the saved full-column skipped-substep AD packet."""

from __future__ import annotations

import gzip
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


class SkippedSubstepADReplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = replay.replay()

    def test_same_call_forward_and_repeated_ad(self) -> None:
        result = self.result
        self.assertEqual(result["parent_rows_raw_equal"], 9750)
        self.assertEqual(result["native_vs_B2_stage_raw_equal"], 11271)
        self.assertEqual(result["native_vs_B1_stage_mismatches"], 39)
        self.assertEqual(result["B1_graph_and_native_exit_raw_equal"], 468)
        self.assertEqual(result["B2_B1_jvp_raw_equal"], 1404)
        self.assertEqual(result["B2_B1_vjp_raw_equal"], 468)
        self.assertEqual(
            result["host"]["endpoint_sha256"],
            "225d2cabe8a466304c06ba1a04638b84c8456b8477326b6852c9217360440070",
        )

    def test_selected_fd_steps_and_outliers_are_separate(self) -> None:
        cases = {(x["direction"], x["h"]): x for x in self.result["finite_differences"]}
        self.assertEqual(len(cases), 8)
        for key in replay.ACCEPTED:
            self.assertTrue(cases[key]["local_fd_accepted"])
            self.assertLess(cases[key]["max_normalized_fd_jvp"], 5e-6)
        for key in set(cases) - replay.ACCEPTED:
            self.assertFalse(cases[key]["local_fd_accepted"])
            self.assertGreater(cases[key]["max_normalized_fd_jvp"], 1e-5)

    def test_rehashed_native_exit_mutation_is_rejected(self) -> None:
        path = HERE / "raw/native_full_column_capture.csv.gz"
        lines = gzip.decompress(path.read_bytes()).decode("ascii").splitlines()
        changed = 0
        for i, line in enumerate(lines):
            parts = line.split(",")
            if (
                len(parts) == 11
                and parts[4] == "23"
                and parts[7:9] == ["runtime_full_exit", "nr"]
            ):
                parts[10] = format(int(parts[10], 16) + 1, "x")
                lines[i] = ",".join(parts)
                changed += 1
        self.assertEqual(changed, 1)
        raw = gzip.compress(("\n".join(lines) + "\n").encode(), mtime=0)
        with self.assertRaisesRegex(ValueError, "stage relation"):
            replay.replay(
                native_override=raw, native_sha=hashlib.sha256(raw).hexdigest()
            )

    def test_rehashed_B2_vjp_mutation_is_rejected(self) -> None:
        with np.load(HERE / "raw/b2_ad_result.npz", allow_pickle=False) as source:
            arrays = {name: np.array(source[name], copy=True) for name in source.files}
        arrays["target_grad"][3, 18] += 1.0
        buffer = io.BytesIO()
        np.savez_compressed(buffer, **arrays)
        raw = buffer.getvalue()
        with self.assertRaisesRegex(ValueError, "target VJP"):
            replay.replay(b2_override=raw, b2_sha=hashlib.sha256(raw).hexdigest())

    def test_rehashed_fd_xland_mutation_is_rejected(self) -> None:
        label = "qv_1e-04_plus"
        with np.load(HERE / "raw/fd" / (label + ".npz"), allow_pickle=False) as source:
            arrays = {name: np.array(source[name], copy=True) for name in source.files}
        arrays["xland"][0] = np.float32(1.0)
        buffer = io.BytesIO()
        np.savez_compressed(buffer, **arrays)
        raw = buffer.getvalue()
        with self.assertRaisesRegex(ValueError, "FD fixed xland"):
            replay.replay(
                fd_npz_override=(label, raw, hashlib.sha256(raw).hexdigest())
            )

    def test_rehashed_fd_capture_forcing_mutation_is_rejected(self) -> None:
        label = "qv_1e-04_plus"
        lines = gzip.decompress((HERE / "raw/fd" / (label + ".csv.gz")).read_bytes())
        rows = lines.decode("ascii").splitlines()
        changed = 0
        for i, line in enumerate(rows):
            parts = line.split(",")
            if (
                len(parts) == 11
                and parts[4] == "23"
                and parts[7:9] == ["runtime_full_forcing", "rho"]
            ):
                parts[10] = format(int(parts[10], 16) + 1, "x")
                rows[i] = ",".join(parts)
                changed += 1
        self.assertEqual(changed, 1)
        raw = gzip.compress(("\n".join(rows) + "\n").encode("ascii"), mtime=0)
        with self.assertRaisesRegex(ValueError, "FD forcing capture"):
            replay.replay(
                fd_capture_override=(label, raw, hashlib.sha256(raw).hexdigest())
            )

    def test_rehashed_fd_capture_dtype_mutation_is_rejected(self) -> None:
        label = "qv_1e-04_plus"
        lines = gzip.decompress((HERE / "raw/fd" / (label + ".csv.gz")).read_bytes())
        rows = lines.decode("ascii").splitlines()
        changed = 0
        for i, line in enumerate(rows):
            parts = line.split(",")
            if (
                len(parts) == 11
                and parts[4] == "23"
                and parts[7:9] == ["runtime_full_entry", "qv"]
            ):
                parts[9] = "f32"
                rows[i] = ",".join(parts)
                changed += 1
        self.assertEqual(changed, 1)
        raw = gzip.compress(("\n".join(rows) + "\n").encode("ascii"), mtime=0)
        with self.assertRaisesRegex(ValueError, "capture numeric dtype"):
            replay.replay(
                fd_capture_override=(label, raw, hashlib.sha256(raw).hexdigest())
            )

    def test_cli(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(HERE / "replay.py")],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(json.loads(proc.stdout)["B2_B1_vjp_raw_equal"], 468)


if __name__ == "__main__":
    unittest.main()
