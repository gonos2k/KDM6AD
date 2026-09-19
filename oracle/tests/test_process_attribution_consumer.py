"""Bounded CLI propagation checks for process-attribution resolution metadata."""
from __future__ import annotations

from dataclasses import replace
import json
import sys

from kdm6.process_attribution import attribute_process, warm_fixture
from scripts import diagnose_process_attribution as diagnose


def test_cli_preserves_rate_resolution_fields_in_json_and_markdown(
    monkeypatch, tmp_path,
):
    baseline = attribute_process(*warm_fixture(), "autoconv", regime="warm")
    injected = replace(
        baseline,
        status="unresolved_output_resolution",
        reason="FD signal is at or below the per-field output-ULP bound",
        rate_fd_ulp_bound={"praut": 1.0e-7},
        rate_output_resolution_fields=("praut",),
        rate_field_status={"praut": "output_resolution_unresolved"},
    )

    monkeypatch.setattr(
        diagnose, "coverage_matrix", lambda **_: {"warm": {"autoconv": injected}}
    )
    output_dir = tmp_path / "attribution"
    monkeypatch.setattr(
        sys, "argv", ["diagnose_process_attribution", "--out", str(output_dir)]
    )

    assert diagnose.main() == 0

    payload = json.loads((output_dir / "attribution.json").read_text())
    record = payload["matrix"]["warm"]["autoconv"]
    assert record["rate_output_resolution_fields"] == ["praut"]
    assert record["rate_field_status"]["praut"] == "output_resolution_unresolved"
    assert record["reason"] == injected.reason

    markdown = (output_dir / "attribution.md").read_text()
    assert "rate ULP fields" in markdown
    assert "| warm | autoconv | unresolved_output_resolution |" in markdown
    assert "| praut |" in markdown
    assert "attribution.json is authoritative" in markdown
