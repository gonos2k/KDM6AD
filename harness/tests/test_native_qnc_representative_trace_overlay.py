from __future__ import annotations

from pathlib import Path
import sys

import pytest

from harness.native_qnc_representative_trace_overlay import REPLACEMENTS, inject, main


STAGES = ("RKSCALAR_PD_BEFORE", "RKSCALAR_PD_AFTER", "RKSCALAR_BEFORE",
          "RKSCALAR_AFTER", "PRE_MICROPHYSICS")
FIXTURE = "\n".join([old for old, _ in REPLACEMENTS] +
                    [f"CALL kdm6ad_upnc_trace('{stage}'" for stage in STAGES])


def test_representative_overlay_changes_only_declared_trace_sites():
    changed = inject(FIXTURE)
    for old, new in REPLACEMENTS:
        assert changed.count(new) == 1
        changed = changed.replace(new, old, 1)
    assert changed == FIXTURE


def test_representative_overlay_rejects_missing_or_duplicate_anchor():
    with pytest.raises(ValueError, match="source anchor differs"):
        inject(FIXTURE.replace(REPLACEMENTS[0][0], "", 1))
    with pytest.raises(ValueError, match="source anchor differs"):
        inject(FIXTURE + "\n" + REPLACEMENTS[0][0])


def test_representative_overlay_cli_preserves_unpinned_input(tmp_path: Path, monkeypatch):
    source = tmp_path / "solve_em.f90"
    output = tmp_path / "variant.f90"
    source.write_text(FIXTURE)
    original = source.read_bytes()
    monkeypatch.setattr(sys, "argv", ["trace", "--source", str(source), "--output", str(output)])
    with pytest.raises(ValueError, match="source SHA differs"):
        main()
    assert source.read_bytes() == original
    assert not output.exists()
