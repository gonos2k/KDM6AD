"""The candidate-input target set and pinned source contract."""
from pathlib import Path
import sys

import pytest

from harness.native_qnc_candidate_face_overlay import (
    SEAM_SENTINELS_IKJ, main, receiver_union, render_advect,
)
from harness.native_qnc_domain_preflight_advect_overlay import failure_layer_coordinates


ROWS = (Path(__file__).resolve().parents[1] /
        "evidence/native_qnc_host_backoff_review_2026-10-28/residual_reason_rows.json")


def test_receiver_union_contains_every_declared_donor_and_six_receivers():
    raw = ROWS.read_bytes()
    donors = failure_layer_coordinates(raw)
    union = set(receiver_union(raw))
    assert len(donors) == 54
    assert len(union) == 382
    assert set(SEAM_SENTINELS_IKJ).issubset(union)
    for i, k, j in donors:
        assert {(i, k, j), (i - 1, k, j), (i + 1, k, j),
                (i, k, j - 1), (i, k, j + 1), (i, k - 1, j),
                (i, k + 1, j)}.issubset(union)


def test_renderer_rejects_other_source_or_failure_rows():
    raw = ROWS.read_bytes()
    with pytest.raises(ValueError, match="private advection source changed"):
        render_advect(b"not PR474 source", raw)
    with pytest.raises(ValueError, match="residual_reason_rows.json SHA differs"):
        receiver_union(raw + b" ")


def test_cli_rejects_output_alias_without_changing_input(tmp_path: Path, monkeypatch):
    source = tmp_path / "source.f90"
    source.write_bytes(b"private input sentinel")
    alias = tmp_path / "alias.f90"
    alias.symlink_to(source)
    monkeypatch.setattr(sys, "argv", [
        "overlay", "--advect-source", str(source), "--failure-json", str(ROWS),
        "--advect-output", str(alias),
    ])
    with pytest.raises(FileExistsError, match="output must be new"):
        main()
    assert source.read_bytes() == b"private input sentinel"
