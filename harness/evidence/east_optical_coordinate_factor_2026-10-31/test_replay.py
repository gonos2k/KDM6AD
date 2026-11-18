import importlib.util
import os
import io
from unittest import mock

import numpy as np
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "replay", Path(__file__).with_name("replay.py")
)
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


class ReplayTest(unittest.TestCase):
    def test_derivative_independent_central_difference(self):
        filt = (950.0, 0.2, 1.01)
        cal = {
            "bt_wavenumber_cm1": 951.0,
            "Plank_constant_h": 6.626e-34,
            "light_speed": 2.998e8,
            "Boltzmann_constant_k": 1.381e-23,
            "Teff_to_Tbb_c0": 0.1,
            "Teff_to_Tbb_c1": 0.999,
            "Teff_to_Tbb_c2": 1e-7,
        }
        radiance = 80.0
        step = 1e-3
        psi, phi, ratio = r.derive(radiance, filt, cal)
        pm, fm, _ = r.derive(radiance - step, filt, cal)
        pp, fp, _ = r.derive(radiance + step, filt, cal)
        self.assertAlmostEqual(ratio, (fp - fm) / (pp - pm), places=8)
        self.assertGreater(psi, 0)
        self.assertGreater(phi, 0)

    def test_rejects_modified_coefficient(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "coefficient"
            p.write_text("FILTER_FUNCTIONS\n")
            with self.assertRaisesRegex(ValueError, "SHA mismatch"):
                r.filters(p)

    def test_verified_bytes_survive_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data"
            path.write_bytes(b"verified")
            digest = r.hashlib.sha256(b"verified").hexdigest()
            original = Path.read_bytes

            def replace_after_read(target):
                data = original(target)
                target.write_bytes(b"replacement")
                return data

            with mock.patch.object(Path, "read_bytes", replace_after_read):
                captured = r.verified_bytes(path, digest)
            self.assertEqual(captured, b"verified")
            self.assertEqual(path.read_bytes(), b"replacement")

    def test_ascii_nan_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalid ASCII values"):
            r.parse_blocks(b"RADIANCE%BT = (nan)", r"RADIANCE%(BT)")

    @unittest.skipUnless(
        os.environ.get("KDM6AD_RTTOV_COEFFICIENT"), "coefficient unavailable"
    )
    def test_saved_nan_rejected(self):
        original = r.verified_bytes

        def mutated(path, digest):
            data = original(path, digest)
            if str(path).endswith("GG_K/values.npz"):
                with np.load(io.BytesIO(data), allow_pickle=False) as archive:
                    values = {key: archive[key].copy() for key in archive.files}
                values["ratio"][0, 0] = np.nan
                out = io.BytesIO()
                np.savez(out, **values)
                return out.getvalue()
            return data

        with mock.patch.object(r, "verified_bytes", side_effect=mutated):
            with self.assertRaisesRegex(ValueError, "non-finite saved ratio"):
                r.run(Path(os.environ["KDM6AD_RTTOV_COEFFICIENT"]))

    @unittest.skipUnless(
        os.environ.get("KDM6AD_RTTOV_COEFFICIENT"),
        "separately supplied coefficient unavailable",
    )
    def test_real_packet(self):
        out = r.run(Path(os.environ["KDM6AD_RTTOV_COEFFICIENT"]))
        self.assertEqual(out["cells"], 140)
        self.assertEqual(out["status"], "INCONCLUSIVE")


if __name__ == "__main__":
    unittest.main()
