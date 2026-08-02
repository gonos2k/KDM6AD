"""The build records what built it (owner review §9)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import g33_build_provenance as bp  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def build(tmp_path):
    """A minimal build directory: sources, a command log, and an outdir."""
    for name, text in (("m.F", "module\n"), ("f.f90", "fixture\n"),
                       ("b.sh", "#!/bin/sh\n")):
        (tmp_path / name).write_text(text)
    out = tmp_path / "out"
    out.mkdir()
    return out, tmp_path


def _collect(out, root, fc="/bin/sh"):
    return bp.collect(out, fc, root / "m.F", root / "f.f90", root / "b.sh")


def test_the_compiler_is_digested_not_quoted(build):
    """`"compiler": "gfortran 15.2.0"` is a string the caller typed. Two hosts
    reporting it produce different numbers. The digest is of the binary."""
    out, root = build
    named, absolute = _collect(out, root, "sh"), _collect(out, root, "/bin/sh")
    assert named["compiler_sha256"] == absolute["compiler_sha256"]
    assert named["compiler_path"] == "/bin/sh"          # resolved, not "sh"
    assert named["compiler_sha256"] == bp.sha256(Path("/bin/sh"))


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


def test_it_writes_the_json_the_manifest_reads(build):
    out, root = build
    assert bp.main([str(out), "/bin/sh", str(root / "m.F"),
                    str(root / "f.f90"), str(root / "b.sh")]) == 0
    assert json.loads((out / "build_provenance.json").read_text())["tree_dirty"] \
        in (True, False)


def test_the_refinement_build_calls_it(build):
    """A provenance writer nothing invokes records nothing."""
    script = REPO / "harness/g33_fortran/refine_build.sh"
    assert "g33_build_provenance.py" in script.read_text()


def test_wrong_argument_count_is_usage_not_a_traceback():
    assert bp.main(["only-one"]) == 2
