import importlib.util
import math
import unittest
from pathlib import Path
import numpy as np

spec = importlib.util.spec_from_file_location(
    "replay", Path(__file__).with_name("replay.py")
)
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


class ReplayTest(unittest.TestCase):
    def test_signed_results_and_ratio(self):
        data = r.replay()
        for corner in ("GG", "PP"):
            for kind in r.KINDS:
                steps = data["results"][corner][kind]
                for j, s in enumerate(steps):
                    fd = np.array(s["fd"])
                    k = np.array(s["k_v"])
                    e = np.array(s["signed_fd_minus_k"])
                    np.testing.assert_array_equal(e, fd - k)
                    if j:
                        prev = np.array(steps[j - 1]["signed_fd_minus_k"])
                        for a, b, c in zip(
                            prev.flat,
                            e.flat,
                            np.array(s["ratio_to_previous"], dtype=object).flat,
                        ):
                            self.assertEqual(c, None if a == 0 else b / a)
            for p in data["synthesis"][corner]:
                self.assertTrue(all(x < 0 for x in p["Sq"]))
                self.assertTrue(all(x > 0 for x in p["Sd"]))
                self.assertLess(p["cosine"], 0)

    def test_sign_rank_and_edge(self):
        q = np.arange(1, 8, dtype=float)
        self.assertEqual(r.synth(q, -q)["cosine"], -1.0)
        self.assertEqual(r.synth(q, -q)["cancellation"], 1.0)
        for a, b in [(np.zeros(7), q), (q, np.full(7, np.nan)), (q[:6], q)]:
            with self.assertRaises(ValueError):
                r.synth(a, b)
        for n, d in [(1, 0), (math.inf, 1), (1, math.nan)]:
            with self.assertRaises(ValueError):
                r.ratio(n, d)
        with self.assertRaises(ValueError):
            r.product(1.0, 1.0, -1.0)

    def test_reduction_order_and_blas_independence(self):
        from unittest.mock import patch

        q = np.array([1e16, 1, -1e16, 3, 5, -2, 4], dtype=float)
        d = np.array([1, -2, 1, 8, -1, 3, 4], dtype=float)
        expected = r.synth(q, d)
        with (
            patch.object(np.linalg, "norm", side_effect=AssertionError("BLAS")),
            patch.object(np, "dot", side_effect=AssertionError("BLAS")),
        ):
            self.assertEqual(expected, r.synth(q[::-1], d[::-1]))

    def test_rehashed_changed_result_rejected(self):
        import hashlib
        import json
        import shutil
        import tempfile

        original = r.HERE
        with tempfile.TemporaryDirectory() as temp:
            r.HERE = Path(temp)
            for f in original.iterdir():
                if f.is_file():
                    shutil.copy(f, r.HERE / f.name)
            path = r.HERE / "results.json"
            data = json.loads(path.read_text())
            data["synthesis"]["GG"][0]["cosine"] += 0.01
            path.write_text(
                json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n"
            )
            manifest_path = r.HERE / "source_manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["files"]["results.json"] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            manifest_path.write_text(json.dumps(manifest))
            try:
                with self.assertRaisesRegex(ValueError, "result differs"):
                    r.main()
            finally:
                r.HERE = original

    def test_mutated_saved_results_rejected(self):
        import tempfile
        import shutil

        original = r.HERE
        with tempfile.TemporaryDirectory() as temp:
            r.HERE = Path(temp)
            for f in original.iterdir():
                if f.is_file():
                    shutil.copy(f, r.HERE / f.name)
            try:
                for name in (
                    "results.json",
                    "replay.py",
                    "test_replay.py",
                    "README.md",
                ):
                    path = r.HERE / name
                    original_bytes = path.read_bytes()
                    path.write_bytes(original_bytes + b"\nmutation")
                    with self.assertRaisesRegex(ValueError, "source hash " + name):
                        r.main()
                    path.write_bytes(original_bytes)
            finally:
                r.HERE = original


if __name__ == "__main__":
    unittest.main()
