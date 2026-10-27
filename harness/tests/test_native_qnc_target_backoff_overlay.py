from __future__ import annotations

from pathlib import Path
import sys

import pytest

from harness.native_qnc_target_backoff_overlay import ANCHOR, CONTEXT, REPLACEMENT, inject, main


FIXTURE = "\n".join(CONTEXT) + "\n" + ANCHOR + "unchanged other limiter\n"


def test_target_backoff_injects_only_the_pinned_pd_site():
    changed = inject(FIXTURE)
    assert changed.count(REPLACEMENT) == 1
    assert changed.replace(REPLACEMENT, ANCHOR, 1) == FIXTURE
    assert "scale=NEAREST(scale,-1.)" in changed


def test_target_backoff_rejects_missing_context_or_duplicate_site():
    with pytest.raises(ValueError, match="context or positive-definite limiter site"):
        inject(ANCHOR)
    with pytest.raises(ValueError, match="context or positive-definite limiter site"):
        inject(FIXTURE + ANCHOR)


def test_target_backoff_cli_preserves_unpinned_input(tmp_path: Path, monkeypatch):
    source = tmp_path / "module_advect_em.f90"
    output = tmp_path / "variant.f90"
    source.write_text(FIXTURE)
    original = source.read_bytes()
    monkeypatch.setattr(sys, "argv", ["backoff", "--source", str(source), "--output", str(output)])
    with pytest.raises(ValueError, match="source SHA differs"):
        main()
    assert source.read_bytes() == original
    assert not output.exists()
