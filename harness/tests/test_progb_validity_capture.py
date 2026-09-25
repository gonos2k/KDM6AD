from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from make_progb_validity_capture import MACRO, _guard, strip_capture  # noqa: E402


def test_strip_exact_restores_base_arm_and_removes_insertion():
    base = "a = 1\n"
    changed = _guard("replace", "a = 2\n", base) + _guard("insert", "write(*,*) 3\n")
    source = base + "z = 4\n"
    overlay = source.replace(base, changed, 1)
    assert f"#ifdef {MACRO}" in overlay
    assert strip_capture(overlay) == source


def test_strip_exact_rejects_unclosed_or_unknown_capture_block():
    with pytest.raises(ValueError, match="missing capture end marker"):
        strip_capture("! S10_CAPTURE_BEGIN:broken\n#ifdef KDM6_PROGB_VALIDITY_CAPTURE\n")
