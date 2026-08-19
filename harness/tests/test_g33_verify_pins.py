"""The registry's figures, and the tool that reads them back.

`CLAIMS.yaml` pins figures as `path#json.pointer: value` -- the campaign's
central scientific claim is that those numbers still come out of the bundles
they name. That was checked by a script rewritten each cycle and lost with the
session, so the claim rested on a tool nobody could re-run.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_verify_pins as vp  # noqa: E402


def test_the_registry_pins_figures_this_tool_can_parse():
    """A parser that matches nothing reports zero disagreements, which reads
    exactly like a clean run."""
    import re
    rows = re.findall(r"^\s+- (\S+?): (\S+)\s*$", vp.REGISTRY.read_text(), re.M)
    pinned = [r for r in rows if ".bundles/" in r[0]]
    assert len(pinned) > 100, len(pinned)
    assert any("#" in ref for ref, _ in pinned), "no figure pointers parsed"


@pytest.mark.skipif(not (Path.home() / "kdm6ad-g33m-migrate").is_dir(),
                    reason="no bundles on this host")
def test_every_pinned_figure_reproduces():
    """The claim itself, run as a test rather than by hand."""
    assert vp.main() == 0


@pytest.mark.skipif(not (Path.home() / "kdm6ad-g33m-migrate").is_dir(),
                    reason="no bundles on this host")
def test_a_MOVED_figure_is_reported(tmp_path, monkeypatch, capsys):
    """A verifier that cannot fail has not verified anything: the check is
    pointed at a registry whose value was changed, and must say so."""
    text = vp.REGISTRY.read_text()
    import re
    hit = next(m for m in re.finditer(r"^(\s+- \S+?#\S+?: )(\S+)\s*$", text, re.M)
               if m.group(2) not in ("true", "false"))
    moved = tmp_path / "CLAIMS.yaml"
    moved.write_text(text[:hit.start()] + hit.group(1) + "-999.5\n"
                     + text[hit.end():])
    monkeypatch.setattr(vp, "REGISTRY", moved)
    assert vp.main() == 1
    assert "FIGURE" in capsys.readouterr().out
