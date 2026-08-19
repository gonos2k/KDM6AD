"""The registry's figures, and the tool that reads them back.

`CLAIMS.yaml` pins figures as `path#json.pointer: value` -- the campaign's
central scientific claim is that those numbers still come out of the bundles
they name. That was checked by a script rewritten each cycle and lost with the
session, so the claim rested on a tool nobody could re-run.
"""
import io
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_verify_pins as vp  # noqa: E402

HAVE_ARCHIVE = (Path.home() / "kdm6ad-g33m-migrate").is_dir()
needs_archive = pytest.mark.skipif(not HAVE_ARCHIVE, reason="no bundles here")


def _run(monkeypatch, tmp_path, text):
    registry = tmp_path / "CLAIMS.yaml"
    registry.write_text(text)
    monkeypatch.setattr(vp, "REGISTRY", registry)
    out = io.StringIO()
    with redirect_stdout(out):
        rc = vp.main()
    return rc, out.getvalue()


def test_the_registry_pins_evidence_this_tool_recognises():
    """A classifier that matches nothing reports zero disagreements, which
    reads exactly like a clean run."""
    rows = re.findall(r"^\s+- (\S+?): (\S+)\s*$", vp.REGISTRY.read_text(), re.M)
    pins = [ref for ref, _ in rows if vp.is_evidence(ref)]
    assert len(pins) > 200, len(pins)
    assert any("#" in ref for ref in pins), "no figure pointers recognised"


@needs_archive
def test_every_pinned_figure_reproduces():
    """The claim itself, run as a test rather than by hand."""
    assert vp.main() == 0


@needs_archive
def test_a_MOVED_figure_is_reported(monkeypatch, tmp_path):
    """A verifier that cannot fail has not verified anything."""
    text = vp.REGISTRY.read_text()
    hit = next(m for m in re.finditer(r"^(\s+- \S+?#\S+?: )(\S+)\s*$", text, re.M)
               if m.group(2) not in ("true", "false"))
    rc, out = _run(monkeypatch, tmp_path,
                   text[:hit.start()] + hit.group(1) + "-999.5\n" + text[hit.end():])
    assert rc == 1 and "FIGURE" in out


@needs_archive
def test_a_pointer_the_bundle_does_not_carry_is_reported(monkeypatch, tmp_path):
    """Walking to a value that is not there is a claim the bundle does not
    support, not a reason to stop reading."""
    text = re.sub(r"(#)[A-Za-z_.0-9,+-]+(: )", r"\1no_such_key\2",
                  vp.REGISTRY.read_text(), count=1)
    rc, out = _run(monkeypatch, tmp_path, text)
    assert rc == 1 and "no such value" in out


@needs_archive
@pytest.mark.parametrize("edit,expect", [
    (lambda t: t.replace("ncmin-001.bundles/", "ncmin-001.bundles-GONE/"),
     "not on this host"),
    (lambda t: t.replace("kdm6ad-g33m-migrate/", "kdm6ad-g33m-ABSENT/"),
     "not on this host"),
    # ...and the renamings an ALLOWLIST would silently drop instead. Both
    # spellings this tool used to key on -- `.bundles/` and the archive-root
    # prefix -- stopped being evidence when renamed, and the count fell while
    # the tool reported success (Codex, twice).
    (lambda t: t.replace("kdm6ad-g33m-migrate/", "kdm6ad-archive-2026/"),
     "not on this host"),
    (lambda t: t.replace("kdm6ad-g33m-f64/", "some-future-store/"),
     "not on this host"),
    (lambda t: t.replace("ncmin-001.bundles/", "ncmin-001.b/"),
     "not on this host"),
])
def test_EVIDENCE_THAT_IS_NOT_THERE_is_a_finding(monkeypatch, tmp_path,
                                                 edit, expect):
    """Missing evidence was counted and reported as success (Codex).

    Worse, the row filter keyed on the directory name `.bundles/`, so
    renaming one archive took 35 figures out of the count entirely and the
    tool still said everything reproduced. A pin either reproduces,
    disagrees, or is GONE -- and only the first is a pass.
    """
    rc, out = _run(monkeypatch, tmp_path, edit(vp.REGISTRY.read_text()))
    assert rc == 1 and expect in out and "GONE" in out


def test_a_row_that_looks_like_a_path_is_never_silently_dropped():
    """The classification is inverted for a reason: an allowlist is
    fail-open by construction.

    Whatever it does not name is silently not evidence, which is how two
    rounds of renamings took pins out of the count while the tool printed
    success. So `FIELD_KEYS` names the registry's own scalar fields, every
    path-like key is evidence, and anything path-like that still escapes is
    REPORTED. This holds the field list to that shape: a field key that
    contains a path separator would re-open the hole.
    """
    assert not any("/" in k or "#" in k for k in vp.FIELD_KEYS), vp.FIELD_KEYS
    assert vp.is_evidence("some-future-store/x.bundles/abc/manifest.json#a.b")
    assert vp.is_evidence("/absolute/path/manifest.json")
    assert not vp.is_evidence("id")


def test_the_field_list_is_exactly_what_the_registry_uses():
    """Naming a field the registry does not use is pre-emptive exemption:
    the day one of them starts holding a path, it is exempt before anyone
    looks. The list drifting the other way is the same hole in reverse -- a
    new scalar field would be read as an unresolvable artefact."""
    rows = re.findall(r"^\s+- (\S+?): (\S+)\s*$", vp.REGISTRY.read_text(), re.M)
    scalar = {ref for ref, _ in rows if "/" not in ref and "#" not in ref}
    assert scalar == vp.FIELD_KEYS, (scalar ^ vp.FIELD_KEYS)


def test_a_registry_with_no_pins_is_refused(monkeypatch, tmp_path):
    """Nothing to verify is not the same as everything verified: zero
    disagreements over zero pins is exactly what a clean run prints."""
    text = "\n".join(l for l in vp.REGISTRY.read_text().splitlines()
                     if "kdm6ad-g33m-" not in l)
    rc, out = _run(monkeypatch, tmp_path, text)
    assert rc == 1 and "pins no evidence at all" in out
