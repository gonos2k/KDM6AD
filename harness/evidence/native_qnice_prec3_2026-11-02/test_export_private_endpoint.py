"""Reject ambiguous time, axis and scaling in the private extractor."""

import importlib
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
