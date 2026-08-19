"""The registry's figures, and the tool that reads them back.

`CLAIMS.yaml` pins figures as `path#json.pointer: value` -- the campaign's
central scientific claim is that those numbers still come out of the bundles
they name. That was checked by a script rewritten each cycle and lost with the
session, so the claim rested on a tool nobody could re-run.
"""
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_evidence_chain as ec  # noqa: E402
import g33_verify_pins as vp  # noqa: E402

HAVE_ARCHIVE = (Path.home() / "kdm6ad-g33m-migrate").is_dir()
needs_archive = pytest.mark.skipif(not HAVE_ARCHIVE, reason="no bundles here")


def _run(monkeypatch, tmp_path, text):
    """The tool against an edited registry, through the chain's own parser."""
    registry = tmp_path / "CLAIMS.yaml"
    registry.write_text(text)
    monkeypatch.setattr(ec, "REGISTRY", registry)
    out = io.StringIO()
    with redirect_stdout(out):
        rc = vp.main()
    return rc, out.getvalue()


def test_the_tool_and_the_chain_read_ONE_registry():
    """Three drafts of this tool parsed the registry with a pattern of their
    own and each silently dropped what its pattern did not match -- rows
    outside `.bundles/`, then rows outside the archive-root prefix, then
    rows whose value was empty or carried a space (Codex, three rounds).

    Two readers of one document is also two answers to "what is evidence
    here", which is the defect this cycle already closed once elsewhere.
    """
    src = (ROOT / "g33_verify_pins.py").read_text()
    assert "import g33_evidence_chain" in src
    assert "re.findall" not in src and "yaml.safe_load" not in src


def test_the_registry_pins_evidence_the_parser_recognises():
    """A parser that matches nothing reports zero disagreements, which reads
    exactly like a clean run."""
    claims = ec.claims()
    pins = sum(len(c["artifacts"]) + len(c["expected_values"])
               + len(c["expected_predicates"]) for c in claims)
    assert pins > 200, pins


@needs_archive
def test_every_pinned_figure_reproduces():
    """The claim itself, run as a test rather than by hand."""
    assert vp.main() == 0


@needs_archive
@pytest.mark.parametrize("edit,expect", [
    (lambda t: t.replace("#delt: 25.0", "#delt: -999.5"), "want -999.5"),
    (lambda t: t.replace("#delt: 25.0", "#no_such_key: 25.0"),
     "no such value"),
    # A predicate is a yes/no, and swapping it must not read as a rounding
    # difference.
    (lambda t: t.replace("#by_chain.main.3.constant_across_calls: false",
                         "#by_chain.main.3.constant_across_calls: true"),
     "PREDICATE"),
])
def test_a_MOVED_figure_is_reported(monkeypatch, tmp_path, edit, expect):
    """A verifier that cannot fail has not verified anything."""
    rc, out = _run(monkeypatch, tmp_path, edit(ec.REGISTRY.read_text()))
    assert rc == 1 and expect in out


@needs_archive
@pytest.mark.parametrize("old,new", [
    ("ncmin-001.bundles/", "ncmin-001.bundles-GONE/"),   # the bundle dir
    ("kdm6ad-g33m-migrate/", "kdm6ad-g33m-ABSENT/"),     # the archive root
    ("kdm6ad-g33m-migrate/", "kdm6ad-archive-2026/"),    # a RENAMED root
    ("kdm6ad-g33m-f64/", "some-future-store/"),          # an unknown store
    ("ncmin-001.bundles/", "ncmin-001.b/"),              # a shortened suffix
])
def test_EVIDENCE_THAT_IS_NOT_THERE_is_a_finding(monkeypatch, tmp_path,
                                                 old, new):
    """Missing evidence was counted and reported as success (Codex).

    Every renaming here used to leave the tool printing that everything
    reproduced -- the first two by being counted as skips, the last three by
    falling outside whichever allowlist that draft used. An allowlist is
    fail-open by construction: what it does not name is silently not
    evidence.
    """
    rc, out = _run(monkeypatch, tmp_path, ec.REGISTRY.read_text().replace(old, new))
    assert rc == 1 and "not on this host" in out and "GONE" in out


@needs_archive
def test_a_pin_a_LINE_SCAN_would_not_see_is_still_checked(monkeypatch,
                                                          tmp_path):
    """`- key: <empty>` matches no `key: value-with-no-spaces` pattern, so
    the scanning drafts dropped it from the count and reported success. The
    chain's parser REFUSES a line it cannot read, which is the property that
    makes a miss visible."""
    text = ec.REGISTRY.read_text().replace("#delt: 25.0", "#delt:")
    with pytest.raises(ValueError):
        _run(monkeypatch, tmp_path, text)


def test_a_registry_with_no_pins_is_refused(monkeypatch, tmp_path):
    """Nothing to verify is not the same as everything verified: zero
    disagreements over zero pins is exactly what a clean run prints."""
    text = "\n".join(l for l in ec.REGISTRY.read_text().splitlines()
                     if "kdm6ad-g33m-" not in l)
    rc, out = _run(monkeypatch, tmp_path, text)
    assert rc == 1 and "pins no evidence at all" in out
