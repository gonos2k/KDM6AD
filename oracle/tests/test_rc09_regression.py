"""Release-candidate input integrity regressions."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import pytest

from scripts import rc09_regression as rc


def _provenance(reference: dict) -> dict:
    return {
        "source_clean": True,
        **{key: reference[key] for key in ("python", "torch", "platform", "arch")},
    }


def test_reference_hash_and_parse_use_the_same_bytes(tmp_path, monkeypatch):
    original = rc.REFERENCE.read_bytes()
    reference = json.loads(original)
    path = tmp_path / "reference.json"
    path.write_bytes(original)
    monkeypatch.setattr(rc, "REFERENCE", path)
    monkeypatch.setattr(rc, "provenance", lambda: _provenance(reference))
    monkeypatch.setattr(rc, "run", lambda parsed: {"fixture": parsed["fixture"]})
    original_read = Path.read_bytes

    def replaced_after_read(self):
        payload = original_read(self)
        if self == path:
            path.write_text('{"fixture":"replaced"}')
        return payload

    monkeypatch.setattr(Path, "read_bytes", replaced_after_read)
    output = tmp_path / "result.json"
    monkeypatch.setattr(sys, "argv", ["rc09_regression.py", "--output", str(output)])
    assert rc.main() == 0
    result = json.loads(output.read_text())
    assert result["reference_sha256"] == hashlib.sha256(original).hexdigest()
    assert result["fixture"] == "mixed_phase_two_cell_v1"


@pytest.mark.parametrize("change", ["loose_tolerance", "nan_value"])
def test_mutated_reference_fails_closed(tmp_path, monkeypatch, change):
    reference = json.loads(rc.REFERENCE.read_text())
    if change == "loose_tolerance":
        reference["rtol"] = 1.0
    else:
        reference["state_out"]["th"][0] = float("nan")
    path = tmp_path / "reference.json"
    path.write_text(json.dumps(reference, allow_nan=True))
    monkeypatch.setattr(rc, "REFERENCE", path)
    monkeypatch.setattr(rc, "provenance", lambda: _provenance(reference))
    output = tmp_path / "result.json"
    monkeypatch.setattr(sys, "argv", ["rc09_regression.py", "--output", str(output)])
    assert rc.main() == 1
    result = json.loads(output.read_text())
    assert result["status"] == "FAIL"
    assert result["message"] == "forward reference SHA mismatch"
