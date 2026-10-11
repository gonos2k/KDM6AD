"""Portable production-clock regressions; private native intake stays local."""
import importlib.util
from pathlib import Path

import pytest


PATH = (Path(__file__).resolve().parents[2] /
        "harness/evidence/pr407_native_saved_time_bound_2026-10-11/test_saved_time_contract_v4.py")
_spec = importlib.util.spec_from_file_location("portable_saved_host_clock_tests", PATH)
_tests = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_tests)
assert _tests.intake.CASE_SCHEMA == "kdm6ad_native_case_v4"

for _name in _tests.PORTABLE_TIME_TEST_NAMES:
    globals()[_name] = getattr(_tests, _name)


@pytest.fixture(autouse=True)
def _forbid_private_native_access(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("portable clock tests must not load private native/reference assets")
    monkeypatch.setattr(_tests.intake, "_load_legacy", forbidden)
    monkeypatch.setattr(_tests.intake.netCDF4, "Dataset", forbidden)
