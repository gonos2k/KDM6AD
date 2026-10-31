"""Output-path regressions using a small synthetic NetCDF and public column."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

try:
    import netCDF4
    import export_private as exporter
except ImportError:
    netCDF4 = None
    exporter = None


@unittest.skipUnless(netCDF4 is not None, "synthetic NetCDF export requires netCDF4")
class ExportPathTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        metadata = json.loads((Path(__file__).parent / "native_column.json").read_bytes())
        with np.load(Path(__file__).parent / "native_column.npz", allow_pickle=False) as stored:
            cls.values = {name: stored[name].copy() for name in stored.files}
        cls.checkpoint = cls.root / "synthetic.nc"
        cls.inputs = cls.root / "synthetic_inputs.npz"
        cls.manifest = cls.root / "synthetic_manifest.json"
        with netCDF4.Dataset(cls.checkpoint, "w", format="NETCDF4") as dataset:
            for name, size in (("Time", 1), ("bottom_top", 39), ("bottom_top_stag", 40),
                               ("south_north", 282), ("west_east", 234)):
                dataset.createDimension(name, size)
            for name in exporter.CENTER + exporter.INTERFACE:
                staggered = name in exporter.INTERFACE
                dims = ("Time", "bottom_top_stag" if staggered else "bottom_top",
                        "south_north", "west_east")
                variable = dataset.createVariable(name, "f4", dims,
                                                  chunksizes=(1, 40 if staggered else 39, 1, 1),
                                                  zlib=True, fill_value=False)
                variable[0, :, exporter.J0, exporter.I0] = cls.values[name]
            for name in exporter.VERTICAL:
                variable = dataset.createVariable(name, "f4", ("Time", "bottom_top"))
                variable[0, :] = cls.values[name]
            xland = dataset.createVariable("XLAND", "f4", ("Time", "south_north", "west_east"),
                                           chunksizes=(1, 1, 1), zlib=True, fill_value=False)
            xland[0, exporter.J0, exporter.I0] = cls.values["XLAND"]
            for name, units in metadata["checkpoint_unit_labels"].items():
                dataset.variables[name].setncattr("units", units)
        np.savez(cls.inputs, **{
            key: cls.values["reference__" + name]
            for name, key in exporter.REFERENCE.items()
        })
        cls.manifest.write_text(json.dumps({"case_preparation": {
            "prep_configuration": metadata["prep_configuration"],
            "experiment": metadata["experiment"],
        }}))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def export(self, out, *, fail_write=False):
        real_digest = exporter.digest
        fixed = {
            self.checkpoint: exporter.CHECKPOINT_SHA,
            self.inputs: exporter.INPUTS_SHA,
            self.manifest: exporter.CASE_MANIFEST_SHA,
        }

        def synthetic_digest(path):
            path = Path(path)
            return fixed[path] if path in fixed else real_digest(path)

        argv = ["export_private.py", "--checkpoint", str(self.checkpoint),
                "--inputs", str(self.inputs), "--case-manifest", str(self.manifest),
                "--out", str(out)]
        with patch.object(exporter, "digest", synthetic_digest), patch.object(sys, "argv", argv):
            with contextlib.redirect_stdout(io.StringIO()):
                if fail_write:
                    with patch.object(exporter.np, "savez_compressed", side_effect=RuntimeError("write failed")):
                        exporter.main()
                else:
                    exporter.main()

    def test_explicit_npz_output_and_digest(self):
        out = self.root / "fresh.npz"
        self.export(out)
        self.assertTrue(out.is_file())
        self.assertTrue(out.with_suffix(".json").is_file())
        self.assertFalse((self.root / "fresh.npz.npz").exists())
        with np.load(out, allow_pickle=False) as stored:
            self.assertTrue(np.array_equal(stored["QICE"], self.values["QICE"]))
        metadata = json.loads(out.with_suffix(".json").read_bytes())
        self.assertEqual(metadata["fixture_sha256"], exporter.digest(out))

    def test_missing_extension_rejected_without_output(self):
        out = self.root / "no_extension"
        implicit_npz = self.root / "no_extension.npz"
        implicit_npz.write_bytes(b"existing implicit target")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.export(out)
        self.assertFalse(out.exists())
        self.assertEqual(implicit_npz.read_bytes(), b"existing implicit target")
        self.assertFalse((self.root / "no_extension.json").exists())

    def test_existing_npz_is_preserved(self):
        out = self.root / "existing_npz.npz"
        out.write_bytes(b"original data")
        with self.assertRaises(FileExistsError):
            self.export(out)
        self.assertEqual(out.read_bytes(), b"original data")
        self.assertFalse(out.with_suffix(".json").exists())

    def test_existing_metadata_is_preserved(self):
        out = self.root / "existing_metadata.npz"
        metadata = out.with_suffix(".json")
        metadata.write_bytes(b"original metadata")
        with self.assertRaises(FileExistsError):
            self.export(out)
        self.assertEqual(metadata.read_bytes(), b"original metadata")
        self.assertFalse(out.exists())

    def test_failed_write_removes_both_reserved_outputs(self):
        out = self.root / "failed.npz"
        with self.assertRaisesRegex(RuntimeError, "write failed"):
            self.export(out, fail_write=True)
        self.assertFalse(out.exists())
        self.assertFalse(out.with_suffix(".json").exists())

    def test_replaced_output_is_rejected_without_removing_replacement(self):
        out = self.root / "replaced.npz"
        old_digest = exporter.digest_open_file

        def replace_after_write(stream):
            result = old_digest(stream)
            out.rename(self.root / "replaced_owned.npz")
            out.write_bytes(b"another writer")
            return result

        with patch.object(exporter, "digest_open_file", replace_after_write):
            with self.assertRaisesRegex(RuntimeError, "output path replaced"):
                self.export(out)
        self.assertEqual(out.read_bytes(), b"another writer")
        self.assertFalse(out.with_suffix(".json").exists())


if __name__ == "__main__":
    unittest.main()
