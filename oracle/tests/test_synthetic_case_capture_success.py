"""Local positive capture integration; explicitly skipped without private references."""
import importlib.util
from pathlib import Path


_path = (Path(__file__).resolve().parents[2] /
         "harness/evidence/pr408_synthetic_capture_success_2026-10-11/test_synthetic_capture_success.py")
_spec = importlib.util.spec_from_file_location("local_synthetic_capture_success_test", _path)
_module = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_module)
test_synthetic_capture_success_runs_real_kdm_and_publishes_auditable_checkpoint = (
    _module.test_synthetic_capture_success_runs_real_kdm_and_publishes_auditable_checkpoint
)
