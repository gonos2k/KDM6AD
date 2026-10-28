from __future__ import annotations

import re
from pathlib import Path
import sys

import pytest

import harness.native_qnc_candidate_solve_overlay as overlay


ROWS = (Path(__file__).resolve().parents[1] / "evidence/native_qnc_host_backoff_review_2026-10-28"
        / "residual_reason_rows.json").read_bytes()


def _base_targets() -> tuple[tuple[int, int, int], ...]:
    failed = overlay.failure_layer_coordinates(ROWS)
    union = set(overlay.candidate_union(ROWS))
    neighbors = sorted(union - set(failed))
    outside = next((i, k, j) for i in range(1, 500) for k in range(1, 40)
                   for j in range(1, 283) if (i, k, j) not in union)
    result = tuple(failed) + tuple(neighbors[:6]) + (outside,)
    assert len(result) == overlay.BASE_TARGET_COUNT and len(set(result)) == len(result)
    return result


def _fixture(targets: tuple[tuple[int, int, int], ...]) -> bytes:
    values = {axis: tuple(coord[index] for coord in targets)
              for axis, index in overlay.ARRAYS}
    lines = [
        "SUBROUTINE solve_em_fixture",
        "   INTEGER, PARAMETER :: KDM6AD_UPNC_NTARGET = 61",
    ]
    for axis, _ in overlay.ARRAYS:
        joined = ", ".join(str(value) for value in values[axis])
        lines.append(
            f"   INTEGER, PARAMETER :: KDM6AD_UPNC_{axis}(KDM6AD_UPNC_NTARGET) = (/ {joined} /)")
    lines.extend(("   INTEGER :: untouched", "   untouched = 0", "END SUBROUTINE solve_em_fixture", ""))
    return "\n".join(lines).encode("ascii")


def _target_declaration_line_indices(source: bytes) -> set[int]:
    return {n for n, line in enumerate(source.decode().splitlines())
            if re.search(r"KDM6AD_UPNC_NTARGET|KDM6AD_UPNC_[IKJ]\(", line)}


def test_render_preserves_61_prefix_and_appends_sorted_neighbor_union(monkeypatch):
    base = _base_targets()
    source = _fixture(base)
    monkeypatch.setattr(overlay, "SOLVE_SOURCE_SHA256", overlay.sha(source))

    rendered, targets = overlay.render_solve(source, ROWS)
    final_count, parsed = overlay._parse_targets(rendered)
    expected_suffix = tuple(sorted(set(overlay.candidate_union(ROWS)) - set(base)))
    expected_suffix += overlay.SEAM_SENTINELS_IKJ

    assert final_count == 383
    assert len(overlay.candidate_union(ROWS)) == 374
    assert targets == parsed
    assert targets[:61] == base
    assert targets[61:] == expected_suffix
    assert len(targets[61:]) == 322
    assert targets[-8:] == overlay.SEAM_SENTINELS_IKJ


def test_render_changes_only_four_target_declarations(monkeypatch):
    source = _fixture(_base_targets())
    monkeypatch.setattr(overlay, "SOLVE_SOURCE_SHA256", overlay.sha(source))
    rendered, _ = overlay.render_solve(source, ROWS)
    original_lines = source.decode().splitlines()
    rendered_lines = rendered.decode().splitlines()
    changed = {n for n, (old, new) in enumerate(zip(original_lines, rendered_lines)) if old != new}
    assert len(rendered_lines) == len(original_lines)
    assert changed == _target_declaration_line_indices(source)


def test_source_and_failure_json_pins_are_enforced(monkeypatch):
    source = _fixture(_base_targets())
    monkeypatch.setattr(overlay, "SOLVE_SOURCE_SHA256", overlay.sha(source))
    with pytest.raises(ValueError, match="residual_reason_rows.json SHA differs"):
        overlay.render_solve(source, ROWS + b" ")
    with pytest.raises(ValueError, match="solve source SHA differs"):
        overlay.render_solve(b"not PR474 source", ROWS)


def test_cli_writes_new_output_without_mutating_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    base = _base_targets()
    source = _fixture(base)
    source_path = tmp_path / "solve_em.f90"
    output_path = tmp_path / "solve_em_candidate.f90"
    source_path.write_bytes(source)
    original_rows = ROWS
    monkeypatch.setattr(overlay, "SOLVE_SOURCE_SHA256", overlay.sha(source))
    monkeypatch.setattr(sys, "argv", [
        "overlay", "--solve-source", str(source_path), "--failure-json", str(tmp_path / "rows.json"),
        "--solve-output", str(output_path),
    ])
    (tmp_path / "rows.json").write_bytes(original_rows)

    assert overlay.main() == 0
    assert source_path.read_bytes() == source
    assert (tmp_path / "rows.json").read_bytes() == original_rows
    assert output_path.is_file()
    with pytest.raises(FileExistsError):
        overlay.main()
