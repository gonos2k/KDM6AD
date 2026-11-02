"""Reject ambiguous time, axis and scaling in the private extractor."""

import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from netCDF4 import Dataset


module = importlib.import_module(
    "harness.evidence.native_qnice_prec3_2026-11-02.export_private_endpoint"
)


class PrivateEndpointSelection(unittest.TestCase):
    def make_file(self, path, *, saved_time, dims=None, scale=False,
                  missing=False):
        with Dataset(path, "w") as ds:
            for name, length in (("Time", 1), ("DateStrLen", 19),
                                 ("bottom_top", 39), ("south_north", 282),
                                 ("west_east", 234)):
                ds.createDimension(name, length)
            times = ds.createVariable("Times", "S1", ("Time", "DateStrLen"))
            times[0, :] = np.frombuffer(saved_time, dtype="S1")
            if dims is not None:
                al = ds.createVariable("AL", "f4", dims)
                if scale:
                    al.scale_factor = 2.0
                if missing:
                    al.missing_value = np.float32(-9999.0)

    def reject(self, *, saved_time, dims=None, scale=False,
               missing=False, message):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "endpoint.nc"
            self.make_file(path, saved_time=saved_time, dims=dims,
                           scale=scale, missing=missing)
            with patch.object(module, "EXPECTED_ENDPOINT_SHA256", module.digest(path)):
                with self.assertRaisesRegex(ValueError, message):
                    module.export(path)

    def test_wrong_saved_time(self):
        self.reject(saved_time=b"2025-07-19_00:00:40", message="saved time")

    def test_wrong_axis_order(self):
        self.reject(saved_time=module.EXPECTED_TIME,
                    dims=("Time", "bottom_top", "west_east", "south_north"),
                    message="dtype/shape AL")

    def test_scaled_field(self):
        self.reject(saved_time=module.EXPECTED_TIME,
                    dims=module.EXPECTED_DIMS, scale=True,
                    message="dtype/shape AL")

    def test_missing_value_attribute(self):
        self.reject(saved_time=module.EXPECTED_TIME,
                    dims=module.EXPECTED_DIMS, missing=True,
                    message="dtype/shape AL")

    def test_default_fill_without_attribute(self):
        self.reject(saved_time=module.EXPECTED_TIME,
                    dims=module.EXPECTED_DIMS,
                    message="missing or nonfinite endpoint value AL")

    def test_valid_two_level_selection_and_cli_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "endpoint.nc"
            output = Path(tmp) / "selected.json"
            # Independently specified IEEE-754 words for k + field_index/4.
            expected = {
                "21": dict(zip(module.FIELDS, (
                    "41a80000", "41aa0000", "41ac0000", "41ae0000", "41b00000"))),
                "23": dict(zip(module.FIELDS, (
                    "41b80000", "41ba0000", "41bc0000", "41be0000", "41c00000"))),
            }
            with Dataset(source, "w") as ds:
                for name, length in (("Time", 1), ("DateStrLen", 19),
                                     ("bottom_top", 39), ("south_north", 282),
                                     ("west_east", 234)):
                    ds.createDimension(name, length)
                times = ds.createVariable("Times", "S1", ("Time", "DateStrLen"))
                times[0, :] = np.frombuffer(module.EXPECTED_TIME, dtype="S1")
                for field_index, name in enumerate(module.FIELDS):
                    var = ds.createVariable(name, "f4", module.EXPECTED_DIMS)
                    for native_k in (21, 23):
                        value = np.float32(native_k + field_index / 4)
                        var[0, native_k-1, 241, 163] = value
                        var[0, native_k-1, 241, 164] = np.float32(900 + field_index)
                        var[0, native_k-1, 242, 163] = np.float32(800 + field_index)
            with patch.object(module, "EXPECTED_ENDPOINT_SHA256", module.digest(source)):
                result = module.export(source)
                self.assertEqual(result["cells"], expected)
                with patch.object(sys, "argv", ["export_private_endpoint",
                                               "--endpoint", str(source),
                                               "--out", str(output)]):
                    module.main()
                self.assertEqual(output.read_bytes(),
                                 (json.dumps(result, indent=2, sort_keys=True)
                                  + "\n").encode())
                with patch.object(sys, "argv", ["export_private_endpoint",
                                               "--endpoint", str(source),
                                               "--out", str(output)]):
                    with self.assertRaises(FileExistsError):
                        module.main()


if __name__ == "__main__":
    unittest.main()
