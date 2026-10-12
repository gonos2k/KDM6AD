"""Local positive capture integration; explicitly skipped without private references."""
import importlib.util
from pathlib import Path
import sys


_path = (Path(__file__).resolve().parents[2] /
         "harness/evidence/pr408_synthetic_capture_success_2026-10-11/test_synthetic_capture_success.py")
_spec = importlib.util.spec_from_file_location("local_synthetic_capture_success_test", _path)
_module = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
# The archived PR407 driver imports this historical top-level name. Other
# collected tests load PR406 under the same name, so bind the intended version
# while importing the fixture, then restore the caller's module cache.
_adapter_path = _path.parent.parent / "pr407_native_saved_time_bound_2026-10-11/case_capture_adapter.py"
_adapter_spec = importlib.util.spec_from_file_location("case_capture_adapter", _adapter_path)
_adapter = importlib.util.module_from_spec(_adapter_spec)
assert _adapter_spec.loader is not None
_adapter_spec.loader.exec_module(_adapter)
_previous_adapter = sys.modules.get("case_capture_adapter")
sys.modules["case_capture_adapter"] = _adapter
try:
    _spec.loader.exec_module(_module)
finally:
    if _previous_adapter is None:
        sys.modules.pop("case_capture_adapter", None)
    else:
        sys.modules["case_capture_adapter"] = _previous_adapter
test_synthetic_capture_success_runs_real_kdm_and_publishes_auditable_checkpoint = (
    _module.test_synthetic_capture_success_runs_real_kdm_and_publishes_auditable_checkpoint
)
