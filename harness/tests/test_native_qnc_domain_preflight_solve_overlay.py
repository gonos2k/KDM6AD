"""Source-only checks for the pinned, trace-only RK target expansion."""
from pathlib import Path

import pytest

from harness import native_qnc_domain_preflight_solve_overlay as overlay


ROWS = (Path(__file__).resolve().parents[1] /
        "evidence/native_qnc_host_backoff_review_2026-10-28/residual_reason_rows.json")


def test_liquid_targets_are_unique_and_preserve_writer_target_indices(monkeypatch):
    source = ("BEGIN\n" + "\n".join(overlay.BASE_LINES) + "\nEND\n").encode()
    monkeypatch.setattr(overlay, "BASE_SOURCE_SHA256", overlay.sha(source))
    rendered, targets = overlay.render_solve(source, ROWS.read_bytes())
    assert targets[:10] == overlay.BASE_TARGETS_IKJ
    assert len(targets) == len(set(targets)) == 61
    assert all(coord in targets for coord in overlay.liquid_failure_coords(ROWS.read_bytes()))
    assert b"KDM6AD_UPNC_NTARGET = 61" in rendered
    assert rendered.startswith(b"BEGIN\n") and rendered.endswith(b"\nEND\n")


def test_source_and_residual_byte_changes_fail_closed(monkeypatch):
    source = "\n".join(overlay.BASE_LINES).encode()
    monkeypatch.setattr(overlay, "BASE_SOURCE_SHA256", overlay.sha(source))
    with pytest.raises(ValueError, match="private solve source changed"):
        overlay.render_solve(source + b"!", ROWS.read_bytes())
    with pytest.raises(ValueError, match="residual layer rows changed"):
        overlay.render_solve(source, ROWS.read_bytes() + b" ")
