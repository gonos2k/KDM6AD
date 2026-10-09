"""Protect retained scientific receipts before private forecast access."""
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "harness/diagnose_clear_candidate.py"
PUBLIC = ROOT / "harness/evidence/native358_artifact_diag_2026-10-08/results/native8frame_failed_run_artifact_diagnostic_enriched.json"


def test_existing_receipt_is_preserved_before_inputs_are_opened(tmp_path):
    output = tmp_path / "prior.json"
    original = b'{"historical_status":"invalid"}\n'
    output.write_bytes(original)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(output),
         "--zip", str(tmp_path / "missing.zip"),
         "--forecast", str(tmp_path / "missing.nc")],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert "output already exists" in result.stderr
    assert output.read_bytes() == original


def test_mixed_archive_and_public_profile_is_refused_before_forecast(tmp_path):
    public = json.loads(PUBLIC.read_text())
    public["per_frame"][0]["native_t_layer_K"][0] += 1.0
    changed = tmp_path / "different_profile.json"
    changed.write_text(json.dumps(public))
    output = tmp_path / "must_not_be_created.json"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--public", str(changed),
         "--forecast", str(tmp_path / "missing.nc"), "--output", str(output)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert "do not match the paired public receipt" in result.stderr
    assert not output.exists()
