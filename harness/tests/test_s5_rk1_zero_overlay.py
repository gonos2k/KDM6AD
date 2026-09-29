"""Exact-source and opt-in guards for the S5 RK1 zero-store candidate."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import s5_rk1_zero_overlay as probe  # noqa: E402


def test_macro_off_restores_both_original_stores():
    source = "before\n" + "between\n".join(probe.STORES.values()) + "after\n"
    overlay = probe.render(source)
    assert overlay.count(f"#ifdef {probe.GUARD}") == 2
    assert "IF (rk_step == 1) THEN" in overlay
    assert "u_2(i,k,j) = 0." in overlay
    assert "v_2(i,k,j) = 0." in overlay
    assert probe.strip(overlay) == source


def test_refuses_unpinned_source(tmp_path):
    source = tmp_path / "module_small_step_em.F"
    output = tmp_path / "overlay.F"
    source.write_text("".join(probe.STORES.values()))
    with pytest.raises(ValueError, match="source differs"):
        probe.generate(source, output)
    assert not output.exists()
