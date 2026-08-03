"""A bundle is produced whole or not at all (owner priority-2).

The bundles used to be assembled by hand — one step built and wrote provenance,
another ran the driver, a third stitched a manifest — so nothing structurally
prevented provenance from one build being published beside members from another.
These tests hold the replacement to that: fail-closed at every stage, and visible
under the destination only after everything succeeded.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_refine_experiment as xp  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
from test_g33_refine_analyze import _stream  # noqa: E402


def _fake(monkeypatch, *, nsplits=(3, 6), fail_at=None):
    """Stand in for the Fortran build: same call sequence, no compiler."""
    def build(workdir, fixture, algo, nflux):
        if fail_at == "build":
            raise SystemExit("build failed")
        (workdir / "build_provenance.json").write_text(json.dumps({
            "module_sha256": xp.rm.sha256(MOD), "fixture_sha256": xp.rm.sha256(FIX),
            "sources": [], "executable_sha256": "ab" * 32}))
        return workdir / "driver"

    def members(exe, out, ns, mode):
        if fail_at == "run":
            raise SystemExit("driver failed")
        runs = {}
        for n in ns:
            body = _stream(nsplit=n).splitlines()
            body[0] = (f"G33R BEGIN nsplit {n} {mode} legacy "
                       f"delt {300.0/n:.6f} loops 1 dtcld {300.0/n:.6f}")
            p = out / f"n{n}.{mode}.txt"
            p.write_text("\n".join(body) + "\n")
            runs[n] = xp.ra.read(p, nsplit=n)
        return runs

    monkeypatch.setattr(xp, "build", build)
    monkeypatch.setattr(xp, "members", members)
    monkeypatch.setattr(xp, "_run", lambda cmd, **kw: "gfortran (fake) 1.0\n")


MOD = ROOT / "g33_refine_analyze.py"       # any two real files, for digests
FIX = ROOT / "g33_refine_manifest.py"


def _produce(dest, **kw):
    return xp.produce(dest, fixture="g33_fixture_multisubcycle_v1", algo="legacy",
                      nsplits=kw.pop("nsplits", (3, 6)), mode="rezero",
                      nflux=kw.pop("nflux", False), module=MOD, **kw)


@pytest.fixture(autouse=True)
def _fixture_path(monkeypatch):
    """produce() derives the fixture .f90 from its name; point it at a real file."""
    monkeypatch.setattr(xp.rm, "sha256", xp.rm.sha256)
    orig = xp.rm.build

    def build(outputs, *, module, fixture, **kw):
        return orig(outputs, module=module, fixture=FIX, **kw)
    monkeypatch.setattr(xp.rm, "build", build)


def test_a_complete_run_publishes_one_bundle(tmp_path, monkeypatch):
    _fake(monkeypatch)
    dest = _produce(tmp_path / "bundle")
    man = json.loads((dest / "manifest.json").read_text())
    assert [m["file"] for m in man["members"]] == ["n3.rezero.txt", "n6.rezero.txt"]
    assert man["is_refinement_chain"] and man["instrumented"] is False
    assert man["decision_eligible"] is False


def test_the_instrumented_flag_is_recorded(tmp_path, monkeypatch):
    """An instrumented member is a different artifact from a plain one even when
    the two agree bit for bit."""
    _fake(monkeypatch)
    dest = _produce(tmp_path / "b", nflux=True)
    assert json.loads((dest / "manifest.json").read_text())["instrumented"] is True


@pytest.mark.parametrize("stage", ["build", "run"])
def test_a_failure_publishes_NOTHING(tmp_path, monkeypatch, stage):
    _fake(monkeypatch, fail_at=stage)
    with pytest.raises(SystemExit):
        _produce(tmp_path / "bundle")
    assert not (tmp_path / "bundle").exists()
    assert not list(tmp_path.glob(".g33-bundle-*")), "temp bundle left behind"


def test_a_failure_leaves_the_PREVIOUS_bundle_intact(tmp_path, monkeypatch):
    """The failure mode this exists to stop: a half-replaced bundle that still
    looks like evidence."""
    _fake(monkeypatch)
    dest = _produce(tmp_path / "bundle")
    before = (dest / "manifest.json").read_text()
    _fake(monkeypatch, fail_at="run")
    with pytest.raises(SystemExit):
        _produce(tmp_path / "bundle")
    assert (dest / "manifest.json").read_text() == before


def test_a_member_that_fails_the_strict_parser_stops_the_run(tmp_path, monkeypatch):
    _fake(monkeypatch)

    def bad(exe, out, ns, mode):
        (out / "n3.rezero.txt").write_text("G33R BEGIN nsplit 3 rezero legacy\n")
        return {3: xp.ra.read(out / "n3.rezero.txt", nsplit=3)}
    monkeypatch.setattr(xp, "members", bad)
    with pytest.raises(xp.ra.RefineError):
        _produce(tmp_path / "bundle")
    assert not (tmp_path / "bundle").exists()


def test_publish_swaps_ONE_symlink_over_an_immutable_bundle(tmp_path, monkeypatch):
    """The previous shape renamed dest->dest.prev then tmp->dest: two steps with
    a window where the canonical path did not exist (owner §7.4)."""
    _fake(monkeypatch)
    dest = _produce(tmp_path / "bundle")
    assert dest.is_symlink(), "dest must be a symlink, not a real directory"
    target = dest.resolve()
    assert target.parent.name == "bundle.bundles"
    assert len(target.name) == 16, "bundle directory is named by its manifest digest"


def test_republishing_never_leaves_the_destination_absent(tmp_path, monkeypatch):
    """Publish twice; the second must land on a NEW immutable directory and the
    old one must survive, so no reader ever sees a missing or partial dest."""
    _fake(monkeypatch)
    dest = _produce(tmp_path / "bundle")
    first = dest.resolve()
    _fake(monkeypatch, nsplits=(3, 6, 12))
    dest = _produce(tmp_path / "bundle", nsplits=(3, 6, 12))
    second = dest.resolve()
    assert first != second and first.exists(), "the previous bundle is immutable"
    assert dest.is_symlink() and (dest / "manifest.json").exists()
    assert len(json.loads((dest / "manifest.json").read_text())["members"]) == 3


def test_an_identical_rerun_reuses_the_same_immutable_bundle(tmp_path, monkeypatch):
    """Content-addressed: the same manifest is the same bundle. Rebuilding it
    would delete the directory `dest` currently points at."""
    _fake(monkeypatch)
    first = _produce(tmp_path / "bundle").resolve()
    second = _produce(tmp_path / "bundle").resolve()
    assert first == second and first.exists()
