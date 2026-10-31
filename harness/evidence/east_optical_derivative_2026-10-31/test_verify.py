import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

import verify as verifier
from verify import sha, verify

HERE = Path(__file__).resolve().parent


class PacketTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "packet"
        shutil.copytree(HERE / "packet", self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_changed_source_fails_at_entry(self):
        for name in ("verify.py", "export.py"):
            with self.subTest(name=name):
                source_copy = Path(self.temp.name) / name.replace(".py", "")
                source_copy.mkdir()
                for item in (
                    "verify.py",
                    "export.py",
                    "test_verify.py",
                    "README.md",
                    "source_manifest.json",
                ):
                    shutil.copyfile(HERE / item, source_copy / item)
                changed = source_copy / name
                changed.write_bytes(changed.read_bytes() + b"\n# modified\n")
                for command in (
                    [sys.executable, str(source_copy / "verify.py"), str(self.root)],
                    [
                        sys.executable,
                        str(source_copy / "export.py"),
                        "missing",
                        "unused",
                    ],
                ):
                    result = subprocess.run(
                        command, capture_output=True, text=True, check=False
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(f"source hash: {name}", result.stderr)

    def test_replay(self):
        result = verify(self.root)
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertEqual(
            result["comparisons"]["GG"]["hydro"]["steps"][1]["nonzero_bt_elements"], 70
        )
        for corner in ("GG", "PP"):
            for mode in ("deff", "mixed"):
                self.assertEqual(
                    [
                        s["observed_20_micron_knot_crossing_rows"]
                        for s in result["comparisons"][corner][mode]["steps"]
                    ],
                    [42, 0, 0, 0],
                )
            self.assertTrue(
                all(
                    s["observed_20_micron_knot_crossing_rows"] == 0
                    for s in result["comparisons"][corner]["hydro"]["steps"]
                )
            )

    def test_corrupted_capture_rejected(self):
        path = self.root / "GG_hydro_0_plus/values.npz"
        path.write_bytes(path.read_bytes() + b"x")
        with self.assertRaisesRegex(ValueError, "packet hash"):
            verify(self.root)

    def test_rehashed_raw_quality_still_rejected(self):
        name = "GG_hydro_0_plus/direct_radiance.txt"
        path = self.root / name
        contents = path.read_text().replace(
            "RADIANCE%QUALITY = (\n         0", "RADIANCE%QUALITY = (\n         1", 1
        )
        path.write_text(contents)
        mpath = self.root / "packet.json"
        manifest = json.loads(mpath.read_text())
        manifest["files"][name] = sha(path)
        mpath.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "raw direct quality"):
            verify(self.root)

    def test_rehashed_summary_still_recomputed(self):
        path = self.root / "summary.json"
        summary = json.loads(path.read_text())
        summary["comparisons"]["GG"]["steps"]["hydro_0.001"]["fd"][0][0] += 1
        path.write_text(json.dumps(summary))
        mpath = self.root / "packet.json"
        manifest = json.loads(mpath.read_text())
        manifest["files"]["summary.json"] = sha(path)
        mpath.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "FD or JVP shape/computation mismatch"):
            verify(self.root)

    def test_alternate_reduction_order_is_within_explicit_bound(self):
        def alternate(kh, kd, vh, vd):
            return np.sum(kh * vh[:, None, :], axis=-1) + np.sum(
                kd * vd[:, None, :], axis=-1
            )

        with mock.patch.object(verifier, "contract_jvp", alternate):
            result = verify(self.root)
        self.assertEqual(result["status"], "INCONCLUSIVE")
        for corner in ("GG", "PP"):
            for mode in ("hydro", "deff", "mixed"):
                for step in result["comparisons"][corner][mode]["steps"]:
                    arithmetic = step["arithmetic_replay"]
                    self.assertLessEqual(
                        arithmetic["saved_vs_recomputed_jvp_max_abs"],
                        2 * arithmetic["jvp_roundoff_bound_max_abs"],
                    )

    def test_roundoff_bound_rejects_rhs_intermediate_underflow(self):
        kh = np.zeros((10, 7, 1), dtype=np.float64)
        kd = np.zeros_like(kh)
        vh = np.zeros((10, 1), dtype=np.float64)
        vd = np.zeros_like(vh)
        cot = np.zeros((10, 7), dtype=np.float64)
        kh[0, 0, 0] = np.nextafter(0.0, 1.0)
        vh[0, 0] = 1e308
        cot[0, 0] = 1.0 / 70.0
        with self.assertRaisesRegex(ValueError, "rhs cotangent-K intermediate"):
            verifier.exact_contraction_reference(kh, kd, vh, vd, cot)

    def test_fd_bit_comparison_distinguishes_signed_zero(self):
        self.assertFalse(
            verifier.same(
                np.array([[0.0]], dtype=np.float64),
                np.array([[-0.0]], dtype=np.float64),
            )
        )

    def test_rehashed_derived_jvp_and_dot_beyond_bound_are_rejected(self):
        for field in ("jvp", "dot_lhs", "dot_rhs"):
            with self.subTest(field=field):
                root = Path(self.temp.name) / f"packet_{field}"
                shutil.copytree(HERE / "packet", root)
                path = root / "summary.json"
                summary = json.loads(path.read_text())
                step = summary["comparisons"]["GG"]["steps"]["hydro_0.001"]
                if field == "jvp":
                    step[field][0][0] += 1e-10
                    expected = "saved JVP exceeds binary64 reduction bound"
                else:
                    step[field] += 1e-10
                    expected = f"saved {'lhs' if field == 'dot_lhs' else 'rhs'} dot exceeds binary64 reduction bound"
                path.write_text(json.dumps(summary))
                mpath = root / "packet.json"
                manifest = json.loads(mpath.read_text())
                manifest["files"]["summary.json"] = sha(path)
                mpath.write_text(json.dumps(manifest))
                with self.assertRaisesRegex(ValueError, expected):
                    verify(root)

    def test_rehashed_baseline_rejected_by_source_pin(self):
        path = self.root / "GG_baseline.npz"
        path.write_bytes(path.read_bytes() + b"x")
        mpath = self.root / "packet.json"
        manifest = json.loads(mpath.read_text())
        manifest["files"]["GG_baseline.npz"] = sha(path)
        mpath.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "source pin"):
            verify(self.root)


if __name__ == "__main__":
    unittest.main()
