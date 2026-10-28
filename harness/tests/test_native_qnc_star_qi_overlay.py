from __future__ import annotations

from pathlib import Path
import sys

import pytest

from harness.native_qnc_star_qi_overlay import _replace, main, render_advect, render_solve


def test_private_source_pins_reject_other_bytes():
    with pytest.raises(ValueError, match="advection source SHA differs"):
        render_advect(b"different advection source")
    with pytest.raises(ValueError, match="solve source SHA differs"):
        render_solve(b"different solve source")


def test_anchor_requires_one_exact_site():
    with pytest.raises(ValueError, match="source anchor differs"):
        _replace("x", "missing", "new")
    with pytest.raises(ValueError, match="source anchor differs"):
        _replace("xx", "x", "new")


def test_cli_keeps_unpinned_inputs_and_outputs_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    advect = tmp_path / "module_advect_em.f90"
    solve = tmp_path / "solve_em.f90"
    advect.write_text("untrusted advection")
    solve.write_text("untrusted solve")
    outputs = (tmp_path / "new_advect.f90", tmp_path / "new_solve.f90")
    monkeypatch.setattr(sys, "argv", [
        "overlay", "--advect-source", str(advect), "--solve-source", str(solve),
        "--advect-output", str(outputs[0]), "--solve-output", str(outputs[1]),
    ])
    with pytest.raises(ValueError, match="advection source SHA differs"):
        main()
    assert advect.read_text() == "untrusted advection"
    assert solve.read_text() == "untrusted solve"
    assert not any(path.exists() for path in outputs)
