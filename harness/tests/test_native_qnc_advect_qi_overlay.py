from __future__ import annotations

from pathlib import Path
import sys

import pytest

from harness.native_qnc_advect_qi_overlay import main, render_advect, render_solve


def test_both_private_source_pins_reject_other_bytes():
    with pytest.raises(ValueError, match="advect source SHA"):
        render_advect(b"different advect source")
    with pytest.raises(ValueError, match="solve source SHA"):
        render_solve(b"different solve source")


def test_overlay_does_not_write_when_either_source_is_unpinned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    advect = tmp_path / "advect.f90"
    solve = tmp_path / "solve.f90"
    advect.write_text("untrusted advect")
    solve.write_text("untrusted solve")
    outputs = (tmp_path / "generated_advect.f90", tmp_path / "generated_solve.f90")
    monkeypatch.setattr(sys, "argv", [
        "overlay", "--advect-source", str(advect), "--solve-source", str(solve),
        "--advect-output", str(outputs[0]), "--solve-output", str(outputs[1]),
    ])
    with pytest.raises(ValueError, match="advect source SHA"):
        main()
    assert advect.read_text() == "untrusted advect"
    assert solve.read_text() == "untrusted solve"
    assert not any(path.exists() for path in outputs)
