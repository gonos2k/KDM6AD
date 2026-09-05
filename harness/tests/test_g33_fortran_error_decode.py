"""Failure reporting must preserve a driver's undecodable stderr."""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "harness" / "g33_fortran" / "run_fortran_abc.py"
sys.path.insert(0, str(ROOT / "harness" / "g33_fortran"))
sys.path.insert(0, str(ROOT / "harness"))


def test_abc_driver_error_decodes_with_explicit_error_policy(monkeypatch):
    spec = importlib.util.spec_from_file_location("run_fortran_abc_repro", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    class Built:
        returncode = 0

    class Failed:
        returncode = 1
        stdout = b""
        stderr = b"driver byte: \xff"

    calls = iter((Built(), Failed()))
    monkeypatch.setattr(mod.subprocess, "run", lambda *args, **kwargs: next(calls))
    with pytest.raises(SystemExit, match="driver byte: �"):
        mod._build_run("unused", "legacy", ["--dump"])
