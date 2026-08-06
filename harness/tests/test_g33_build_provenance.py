"""The build records what built it (owner review §9).

Uses stub compilers rather than a real one: `/bin/sh` is bash on macOS and dash
on Ubuntu, and only one of those answers `--version`, so a test written against
it asserts the platform rather than the code.
"""
import hashlib
import json
import os
import shutil
import subprocess
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
    # the literal path is DIAGNOSTIC now; the digest is the identity (§10.3)
    assert named["diagnostic"]["compiler_path"] == str(root / "fc")
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


def test_every_compiled_source_is_digested_not_just_the_module(tmp_path, build):
    """libmassv, the model constants, the radar module, the stub and the driver
    all change results, and host/** is gitignored so repo_commit cannot see them
    (owner P0-3)."""
    out, root = build
    (out / "sources.txt").write_text(f"{root / 'm.F'}\n{root / 'f.f90'}\n")
    got = _collect(out, root)["sources"]
    assert [g["path"] for g in got] == [str(root / "m.F"), str(root / "f.f90")]
    assert got[0]["sha256"] == bp.sha256(root / "m.F")


def test_the_executable_that_ran_is_digested(build):
    """The binary is the artifact that produced the numbers."""
    out, root = build
    exe = _stub(root / "exe", "exit 0")
    p = bp.collect(out, str(root / "fc"), root / "m.F", root / "f.f90",
                   root / "b.sh", exe)
    assert p["executable_sha256"] == bp.sha256(exe)
    assert p["diagnostic"]["executable_path"] == str(exe)
    assert _collect(out, root)["executable_sha256"] is None


def test_identity_is_stable_across_output_directories(build, tmp_path):
    """A content-addressed bundle got a new name every rerun because the compile
    commands and paths carried the temp directory (owner §10.3)."""
    out, root = build
    (out / "commands.txt").write_text(f"gfortran -c a.f90 -J{out} -o {out}/a.o\n")
    a = _collect(out, root)
    other = tmp_path / "elsewhere"
    other.mkdir()
    (other / "commands.txt").write_text(
        f"gfortran -c a.f90 -J{other} -o {other}/a.o\n")
    b = bp.collect(other, str(root / "fc"), root / "m.F", root / "f.f90",
                   root / "b.sh")
    strip = lambda d: {k: v for k, v in d.items() if k != "diagnostic"}
    assert strip(a) == strip(b), "identity must not carry the output directory"
    assert a["diagnostic"] != b["diagnostic"], "diagnostics record where it ran"
    assert a["compile_commands"] == ["gfortran -c a.f90 -J<OUT> -o <OUT>/a.o"]


def test_the_build_logs_its_sources_and_its_link():
    """A provenance field nothing populates records nothing."""
    script = (REPO / "harness/g33_fortran/refine_build.sh").read_text()
    assert "SRCLOG=" in script and 'printf \'%s\\n\' "${@: -1}" >>"$SRCLOG"' in script
    assert 'printf \'%q \' "${LINK[@]}" >>"$CMDLOG"' in script


def test_wrong_argument_count_is_usage_not_a_traceback():
    assert bp.main(["only-one"]) == 2


# ---- owner priority-4: the precision-scaling arms ---------------------------

def test_the_f64_arm_pins_double_precision_too():
    """-fdefault-real-8 alone promotes `double precision` to REAL(16) and the
    radar hostmatrix call stops typechecking. The pair is required."""
    script = (REPO / "harness/g33_fortran/refine_build.sh").read_text()
    assert "-fdefault-real-8 -fdefault-double-8" in script


def test_the_probe_is_a_separate_record_family():
    """The G33R stream is f32 hex by contract; a full-precision probe cannot ride
    on it without changing what the strict parser and the decision protocol see."""
    drv = (REPO / "harness/g33_fortran/g33_refine_driver.f90").read_text()
    assert "KDM6_G33_PRECISION_PROBE" in drv and "'G33P STATE'" in drv
    analyzer = (REPO / "harness/g33_refine_analyze.py").read_text()
    assert "G33P" not in analyzer, "the probe must not enter the G33R parser"


def test_the_f32_control_arm_exists_and_is_not_the_f64_one():
    script = (REPO / "harness/g33_fortran/refine_build.sh").read_text()
    assert "--probe)" in script and "--f64)" in script


def test_the_bit_pattern_helper_is_kind_explicit():
    """`transfer(bits, value)` reinterprets a 4-byte word as whatever the default
    real is — under the f64 probe that made every fixture constant garbage and the
    run produced NaN."""
    drv = (REPO / "harness/g33_fortran/g33_refine_driver.f90").read_text()
    assert "real(real32) :: word" in drv and "real(word, kind(value))" in drv


def test_the_overlay_is_compiled_from_a_CONTENT_ADDRESSED_path():
    """gfortran embeds each source's filename in the binary for backtraces, and
    -ffile-prefix-map does not reach that string, so an overlay written into the
    output directory gave the same instrumented build a different executable
    digest in every run (owner §9.1).

    The digest is taken in FULL and the path uses a truncation of it, so the
    build can verify a reused path against the whole thing (owner §13 P1) --
    see test_a_STALE_overlay_at_the_content_addressed_path_is_REFUSED, which
    exercises the reuse end to end rather than by reading the script.
    """
    script = (REPO / "harness/g33_fortran/refine_build.sh").read_text()
    assert 'MODULE_SRC="${TMPDIR:-/tmp}/g33-ovl-${OVLFULL}.F"' in script


def test_identity_paths_are_normalised(build):
    """sources[].path, module_path, fixture_path and compiled_module_path are
    identity-bearing; a literal temp path made them vary per run (§9.1)."""
    out, root = build
    (out / "sources.txt").write_text(f"{out}/generated.F\n")
    (out / "generated.F").write_text("x\n")
    got = _collect(out, root)
    assert got["sources"][0]["path"].startswith("<OUT>")


# ---- owner priority-2: f64 + nflux is guarded at all THREE layers ------------
#
# The Python producer refused the combination; the build script it calls did not,
# so anyone invoking the script directly still got a binary whose G33F number
# records carry four bytes of an eight-byte real labelled `f32` -- a
# valid-looking bit pattern that is not the number.

def test_the_build_script_refuses_f64_with_nflux():
    """The layer that was missing: `refine_build.sh OUT --f64 --nflux` set both
    and carried on."""
    script = REPO / "harness/g33_fortran/refine_build.sh"
    r = subprocess.run(["bash", str(script), "/tmp/should-not-exist",
                        "--f64", "--nflux"], capture_output=True, text=True,
                       cwd=REPO)
    assert r.returncode != 0, "the build script accepted --f64 --nflux"
    assert "refused" in r.stderr


def test_the_preprocessor_refuses_it_too():
    """Catches a hand-rolled compile that reaches neither the producer nor the
    script, and fails at COMPILE time rather than emitting a binary whose output
    is quietly wrong."""
    drv = (REPO / "harness/g33_fortran/g33_refine_driver.f90").read_text()
    assert "#if defined(KDM6_G33_F64) && defined(KDM6_G33_NUMBER_DUMP)" in drv
    assert "#error" in drv


@pytest.mark.skipif(shutil.which("gfortran") is None, reason="needs gfortran")
def test_the_preprocessor_guard_actually_fires():
    """A guard nothing triggers is worse than none: it reads as protection."""
    drv = REPO / "harness/g33_fortran/g33_refine_driver.f90"
    bad = subprocess.run(["gfortran", "-cpp", "-fsyntax-only", "-ffree-form",
                          "-DKDM6_G33_F64", "-DKDM6_G33_NUMBER_DUMP", str(drv)],
                         capture_output=True, text=True)
    assert "no f64 number record family" in bad.stderr
    # ...and stays silent for the combination that IS supported.
    ok = subprocess.run(["gfortran", "-cpp", "-fsyntax-only", "-ffree-form",
                         "-DKDM6_G33_NUMBER_DUMP", str(drv)],
                        capture_output=True, text=True)
    assert "no f64 number record family" not in ok.stderr


def test_the_overlay_path_carries_the_WHOLE_digest_so_it_cannot_collide(tmp_path):
    """A 16-hex truncation left a real race (owner §13 P1-4): two builds whose
    overlays share a 64-bit prefix but differ in content both see "no file",
    both write, and the loser's compile can read the winner's source. The full
    digest removes the class -- same digest means same content, different
    content means a different path -- so this asserts the NAME, and that a
    rebuild reuses it rather than multiplying files."""
    if shutil.which("gfortran") is None or not (
            REPO / "host/KIM-meso_v1.0/phys/module_mp_kdm6.F").is_file():
        pytest.skip("local-only (needs gfortran + the gitignored host tree)")
    env = dict(os.environ, TMPDIR=str(tmp_path))
    args = ["bash", str(REPO / "harness/g33_fortran/refine_build.sh"),
            str(tmp_path / "b1"), "--fixture=g33_fixture_multisubcycle_v1",
            "--algo=legacy", "--nflux"]
    assert subprocess.run(args, capture_output=True, text=True, cwd=REPO,
                          env=env).returncode == 0
    args[2] = str(tmp_path / "b2")
    assert subprocess.run(args, capture_output=True, text=True, cwd=REPO,
                          env=env).returncode == 0

    overlays = list(tmp_path.glob("g33-ovl-*.F"))
    assert len(overlays) == 1, f"two builds, {len(overlays)} overlay files"
    digest = overlays[0].name[len("g33-ovl-"):-len(".F")]
    assert len(digest) == 64, f"path carries {len(digest)} hex, not the full digest"
    assert hashlib.sha256(overlays[0].read_bytes()).hexdigest() == digest
    assert not list(tmp_path.glob("*.tmp")), "a temp file survived the rename"
