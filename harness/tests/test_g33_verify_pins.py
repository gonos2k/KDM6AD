"""The registry's figures, and the tool that reads them back.

`CLAIMS.yaml` pins figures as `path#json.pointer: value` -- the campaign's
central scientific claim is that those numbers still come out of the bundles
they name. That was checked by a script rewritten each cycle and lost with the
session, so the claim rested on a tool nobody could re-run.

THE FAIL-CLOSED PROPERTIES ARE TESTED ON A SYNTHETIC ARCHIVE, so they run
where CI runs. Written against the real bundles they skipped on every public
checkout -- which is exactly where a rule is most likely to regress unnoticed,
a sentence this cycle had already written down about a different table before
repeating it here (Codex). Only "the real pins reproduce" needs the real
archive; that a MISSING pin is refused is a property of the tool.
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

#: One claim, in the registry's own grammar, pinning one digest, one value and
#: one predicate -- the three kinds the tool reads.
BUNDLE = "store-x/exp-001.bundles/deadbeef"
REGISTRY = """\
claims:
  - id: G33-SYNTHETIC-001
    text: |
      a claim that exists to be broken
    status: active
    evidence_kind: measurement
    run_support: [g33_fixture_x_v1]
    artifact_status: pinned
    artifacts:
      - {bundle}/manifest.json: {digest}
    expected_values:
      - {bundle}/a.json#delt: 25.0
    expected_predicates:
      - {bundle}/a.json#closes: true
"""


@pytest.fixture
def archive(tmp_path, monkeypatch):
    """A registry and the bundle it pins, both synthetic."""
    home = tmp_path / "home"
    (home / BUNDLE).mkdir(parents=True)
    (home / BUNDLE / "manifest.json").write_text('{"artifact_type": "x"}\n')
    (home / BUNDLE / "a.json").write_text(
        json.dumps({"delt": 25.0, "closes": True}) + "\n")
    import hashlib
    digest = hashlib.sha256((home / BUNDLE / "manifest.json").read_bytes()).hexdigest()
    monkeypatch.setattr(vp, "HOME", home)

    def write(text):
        registry = tmp_path / "CLAIMS.yaml"
        registry.write_text(text)
        monkeypatch.setattr(ec, "REGISTRY", registry)
        out = io.StringIO()
        with redirect_stdout(out):
            rc = vp.main()
        return rc, out.getvalue()

    write.text = REGISTRY.format(bundle=BUNDLE, digest=digest)
    return write


def test_the_synthetic_registry_is_CLEAN_before_it_is_broken(archive):
    """Every case below edits this one; if it did not start clean they would
    all pass for the wrong reason."""
    rc, out = archive(archive.text)
    assert rc == 0, out
    assert "2 figures reproduce, 1 digests match" in out  # value + predicate


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
    pins = sum(len(c["artifacts"]) + len(c["expected_values"])
               + len(c["expected_predicates"]) for c in ec.claims())
    assert pins > 200, pins


@pytest.mark.parametrize("old,new,expect", [
    ("#delt: 25.0", "#delt: -999.5", "want -999.5"),
    ("#delt: 25.0", "#no_such_key: 25.0", "no such value"),
    # A predicate is a yes/no, and swapping it must not read as a rounding
    # difference.
    ("#closes: true", "#closes: false", "PREDICATE"),
    # ...and the whole-file digest, which is a different kind of pin.
    (None, None, "DIGEST"),          # the whole-file digest, a different pin
])
def test_a_MOVED_figure_is_reported(archive, old, new, expect):
    """A verifier that cannot fail has not verified anything."""
    if old is None:                   # repoint the manifest digest itself
        import re
        text = re.sub(r"(manifest\.json: )[0-9a-f]{64}", r"\g<1>" + "f" * 64,
                      archive.text)
    else:
        text = archive.text.replace(old, new)
    rc, out = archive(text)
    assert rc == 1 and expect in out, out


@pytest.mark.parametrize("old,new", [
    ("exp-001.bundles/", "exp-001.bundles-GONE/"),   # the bundle directory
    ("store-x/", "store-ABSENT/"),                   # the archive root
    ("store-x/", "some-future-store/"),              # an unknown store
    ("exp-001.bundles/", "exp-001.b/"),              # a shortened suffix
])
def test_EVIDENCE_THAT_IS_NOT_THERE_is_a_finding(archive, old, new):
    """Missing evidence was counted and reported as success (Codex).

    Every renaming here used to leave the tool printing that everything
    reproduced -- the first two by being counted as skips, the rest by
    falling outside whichever allowlist that draft used. An allowlist is
    fail-open by construction: what it does not name is silently not
    evidence.
    """
    rc, out = archive(archive.text.replace(old, new))
    assert rc == 1 and "not on this host" in out and "GONE" in out, out


def test_a_pin_a_LINE_SCAN_would_not_see_is_REFUSED(archive):
    """`- key:` with no value matches no `key: value-with-no-spaces`
    pattern, so the scanning drafts dropped it from the count and reported
    success. The chain's parser REFUSES a line it cannot read, which is the
    property that makes a miss visible."""
    with pytest.raises(ValueError):
        archive(archive.text.replace("#delt: 25.0", "#delt:"))


def test_a_registry_with_no_pins_is_refused(archive):
    """Nothing to verify is not the same as everything verified: zero
    disagreements over zero pins is exactly what a clean run prints."""
    text = "\n".join(l for l in archive.text.splitlines()
                     if BUNDLE not in l and not l.strip().startswith(
                         ("artifacts:", "expected_values:",
                          "expected_predicates:")))
    rc, out = archive(text)
    assert rc == 1 and "pins no evidence at all" in out, out


@pytest.mark.skipif(not HAVE_ARCHIVE, reason="no bundles on this host")
def test_every_pinned_figure_reproduces():
    """The claim itself, run as a test rather than by hand. The ONLY case
    here that needs the real archive."""
    assert vp.main() == 0
