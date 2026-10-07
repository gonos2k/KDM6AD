"""A range-masked packed flag must not be misreported as a true fill."""
import importlib.util
from pathlib import Path

import netCDF4
import numpy as np

PATH = Path(__file__).resolve().parents[1] / 'evidence/VIIRS_context_source_2026-10-07.py'
spec = importlib.util.spec_from_file_location('viirs_context_evidence', PATH)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def test_stored_quality_preserves_nonfill_byte_outside_declared_range(tmp_path):
    path = tmp_path / 'packed.nc'
    with netCDF4.Dataset(path, 'w') as d:
        d.createDimension('pixels', 4)
        variable = d.createVariable('quality', 'i1', ('pixels',), fill_value=-128)
        variable.valid_range = np.array([0, 1], dtype=np.int8)
        variable[:] = np.array([0, 1, 5, -128], dtype=np.int8)
    with netCDF4.Dataset(path) as d:
        variable = d['quality']
        assert np.ma.getmaskarray(variable[:]).tolist() == [False, False, True, True]
        raw = probe.stored(variable)
        assert raw.tolist() == [0, 1, 5, -128]
        assert probe.qa_statistics(raw, -128, [0, 1]) == {
            'stored_counts': {'-128': 1, '0': 1, '1': 1, '5': 1},
            'fill_pixels': 1, 'nonfill_outside_declared_range': 1,
        }
