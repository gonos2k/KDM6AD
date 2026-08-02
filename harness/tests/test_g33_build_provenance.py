"""The build records what built it (owner review §9).

Uses stub compilers rather than a real one: `/bin/sh` is bash on macOS and dash
on Ubuntu, and only one of those answers `--version`, so a test written against
it asserts the platform rather than the code.
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import g33_build_provenance as bp  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def _stub(path: Path, prints: str) -> Path:
    path.write_text(f"#!/bin/sh\n{prints}\n")
    path.chmod(0o755)
    return path


@pytest.fixture
def build(tmp_path):
    """A minimal build: sources, an outdir, and a compiler that answers
    --version the way a real one does."""
    for name, text in (("m.F", "module\n"), ("f.f90", "fixture\n"),
                       ("b.sh", "#!/bin/sh\n")):
        (tmp_path / name).write_text(text)
    _stub(tmp_path / "fc", "echo 'GNU Fortran (stub) 15.2.0'")
    out = tmp_path / "out"
    out.mkdir()
    return out, tmp_path


def _collect(out, root, fc=None):
    return bp.collect(out, fc or str(root / "fc"), root / "m.F",
                      root / "f.f90", root / "b.sh")


def test_the_compiler_is_digested_not_quoted(build, monkeypatch):
    """`"compiler": "gfortran 15.2.0"` is a string the caller typed. Two hosts
    print it and produce different numbers. The digest is of the binary."""
    out, root = build
    # Prepend, not replace: collect() also shells out to git.
    monkeypatch.setenv("PATH", f"{root}{os.pathsep}{os.environ['PATH']}")
    named, absolute = _collect(out, root, "fc"), _collect(out, root)
    assert named["compiler_sha256"] == absolute["compiler_sha256"]
    assert named["compiler_path"] == str(root / "fc")      # resolved, not "fc"
    assert named["compiler_sha256"] == bp.sha256(root / "fc")
    assert named["compiler_version"] == "GNU Fortran (stub) 15.2.0"


def test_a_compiler_that_prints_no_version_is_null_not_a_crash(build):
    """Raising here would abort an otherwise successful build at its last step.
    `null` says the compiler printed nothing; the digest still identifies it."""
    out, root = build
    p = _collect(out, root, str(_stub(root / "quiet", "exit 0")))
    assert p["compiler_version"] is None
    assert p["compiler_sha256"] == bp.sha256(root / "quiet")


def test_commands_come_from_the_build_log_not_from_the_caller(build):
    """The caller can pass nothing; the build cannot forget what it ran."""
    out, root = build
    assert _collect(out, root)["compile_commands"] == []
    (out / "commands.txt").write_text("gfortran -c a.f90\ngfortran -c b.f90\n")
    assert _collect(out, root)["compile_commands"] == [
        "gfortran -c a.f90", "gfortran -c b.f90"]


def test_source_digests_track_the_sources(build):
    out, root = build
    before = _collect(out, root)
    (root / "m.F").write_text("module\n! edited\n")
    after = _collect(out, root)
    assert before["module_sha256"] != after["module_sha256"]
    assert before["fixture_sha256"] == after["fixture_sha256"]


def test_repo_state_is_recorded_as_a_commit_and_a_dirty_flag(build):
    out, root = build
    p = _collect(out, root)
    assert len(p["repo_commit"]) == 40 and isinstance(p["tree_dirty"], bool)


def test_a_compiler_that_is_not_there_is_loud(build):
    """Recording a digest of nothing would make the manifest claim a build it
    cannot describe."""
    out, root = build
    with pytest.raises(FileNotFoundError):
        _collect(out, root, str(root / "absent-compiler"))


def test_it_writes_the_json_the_manifest_reads(build):
    out, root = build
    assert bp.main([str(out), str(root / "fc"), str(root / "m.F"),
                    str(root / "f.f90"), str(root / "b.sh")]) == 0
    assert json.loads((out / "build_provenance.json").read_text())["tree_dirty"] \
        in (True, False)


def test_the_refinement_build_calls_it(build):
    """A provenance writer nothing invokes records nothing."""
    script = REPO / "harness/g33_fortran/refine_build.sh"
    assert "g33_build_provenance.py" in script.read_text()


def test_wrong_argument_count_is_usage_not_a_traceback():
    assert bp.main(["only-one"]) == 2
