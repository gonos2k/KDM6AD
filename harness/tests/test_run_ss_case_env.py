#!/usr/bin/env python3
"""PR1-B1 contract: the SS parity runner must leave KMP_DUPLICATE_LIB_OK
caller-owned — never inject it. Parent UNSET stays unset; an explicit
parent TRUE/FALSE is preserved verbatim. The single-thread fence
(OMP/MKL/VECLIB) is unchanged.

Runs under pytest OR directly (`python3 test_run_ss_case_env.py`).
"""
import importlib.util
import os
import pathlib

RUNNER = pathlib.Path(__file__).resolve().parents[1] / "run_ss_case.py"


def _load():
    spec = importlib.util.spec_from_file_location("run_ss_case_under_test", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _child_env_for(parent_value):
    """build_child_env() with the parent's KMP_DUPLICATE_LIB_OK set to
    `parent_value` (None = unset), restoring the caller's environment after."""
    saved = os.environ.get("KMP_DUPLICATE_LIB_OK")
    try:
        if parent_value is None:
            os.environ.pop("KMP_DUPLICATE_LIB_OK", None)
        else:
            os.environ["KMP_DUPLICATE_LIB_OK"] = parent_value
        return _load().build_child_env()
    finally:
        if saved is None:
            os.environ.pop("KMP_DUPLICATE_LIB_OK", None)
        else:
            os.environ["KMP_DUPLICATE_LIB_OK"] = saved


def test_parent_unset_child_unset():
    assert "KMP_DUPLICATE_LIB_OK" not in _child_env_for(None)


def test_parent_true_child_true():
    assert _child_env_for("TRUE")["KMP_DUPLICATE_LIB_OK"] == "TRUE"


def test_parent_false_child_false():
    assert _child_env_for("FALSE")["KMP_DUPLICATE_LIB_OK"] == "FALSE"


def test_single_thread_fence_preserved():
    env = _child_env_for(None)
    for k in ("OMP_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS", "OMP_THREAD_LIMIT"):
        assert env[k] == "1", k


if __name__ == "__main__":
    tests = sorted((n, f) for n, f in globals().items() if n.startswith("test_") and callable(f))
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print(f"all {len(tests)} env-contract tests passed")
