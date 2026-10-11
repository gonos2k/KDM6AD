"""Public synthetic NetCDF regression for the exact post-stop archive error."""
import importlib.util
from pathlib import Path


_path = (Path(__file__).resolve().parents[2] /
         "harness/evidence/pr407_native_saved_time_bound_2026-10-11/test_saved_time_counterexample.py")
_spec = importlib.util.spec_from_file_location("portable_exact_stop_counterexample", _path)
_module = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_module)
test_july20_saved_state_rejected_after_july19_one_minute_run = (
    _module.test_july20_saved_state_rejected_after_july19_one_minute_run
)
