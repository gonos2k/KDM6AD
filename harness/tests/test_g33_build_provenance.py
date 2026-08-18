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
    assert "SRCLOG=" in script
    # the log carries the LOGICAL path with the digest of the bytes the
    # compiler was actually fed, taken at compile time -- re-reading the
    # path when collecting is what staging exists to remove (owner §10)
    assert 'sha=$(shasum -a 256 "$last" | cut -d\' \' -f1)' in script
    assert '>>"$SRCLOG"' in script
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


# ---- owner D6: f64 + nflux is a RECORD FAMILY, no longer a refusal ---------
#
# It was guarded at three layers -- producer, build script, preprocessor --
# because the G33F number records wrote `'f32', transfer(<real>, 0)`, and under
# -fdefault-real-8 that took four bytes of an eight-byte value into an int32
# mold. Measured before the fix: pi emitted `54442D18`, the LOW word of
# 400921FB54442D18, which reads as a perfectly ordinary 3.3702806e+12.
#
# Three guards, and each of them was the reason the fix kept being deferred.
# What replaces them is the agreement between a record's label, its hex width
# and the stream's own PROTOCOL header, which is checked on every read.

def test_the_build_script_ACCEPTS_f64_with_nflux_now():
    """The refusal is gone from the layer that had it last. Not a build: this
    only has to get past the guard, and it fails later for want of an output
    directory it was told not to create."""
    script = REPO / "harness/g33_fortran/refine_build.sh"
    r = subprocess.run(["bash", str(script), "/tmp/g33-should-not-exist",
                        "--f64", "--nflux"], capture_output=True, text=True,
                       cwd=REPO)
    assert "refused" not in r.stderr, r.stderr[:300]


def test_the_build_script_passes_the_REAL_KIND_to_the_overlay():
    """The overlay's width and the compiler's flag must come from ONE variable.
    An overlay generated for f32 and compiled with -fdefault-real-8 is exactly
    the wrong-number path, and nothing downstream could tell."""
    sh = (REPO / "harness/g33_fortran/refine_build.sh").read_text()
    assert "--real-kind=\"$REAL_KIND\"" in sh
    # Both derived from $F64, so they cannot disagree about which arm this is.
    kind = next(l for l in sh.splitlines() if l.strip().endswith("REAL_KIND=f64"))
    flag = next(l for l in sh.splitlines() if "-fdefault-real-8" in l
                and not l.lstrip().startswith("#"))
    assert '"$F64" = 1' in kind, kind
    assert sh.index(kind) < sh.index(flag)


def test_the_preprocessor_guard_is_GONE_and_the_driver_still_compiles():
    """A guard that outlives its reason reads as protection and refuses work
    that is now correct.

    Names the retired guard rather than asserting the driver has no `#error`
    at all: the sub-cycle limit arrives as a `-D` from the build, and a
    driver that compiles without it would carry no limit at all (§11)."""
    lines = (REPO / "harness/g33_fortran/g33_refine_driver.f90").read_text() \
        .splitlines()
    assert not any("no f64 number record family" in ln for ln in lines)
    errors = [i for i, ln in enumerate(lines) if ln.startswith("#error")]
    assert [lines[i - 1] for i in errors] == ["#ifndef KDM6_DTCLDCR"], \
        "the only refusal left is a driver with no sub-cycle limit at all"


@pytest.mark.skipif(shutil.which("gfortran") is None, reason="needs gfortran")
def test_the_driver_compiles_under_BOTH_real_kinds(tmp_path):
    """The combination that was refused at compile time now has to parse.

    `-DKDM6_DTCLDCR` is what the build passes from the compiled kernel (§11),
    so a direct compile has to pass it too -- and the last case asserts that
    LEAVING IT OUT is the refusal, not a driver carrying no limit."""
    drv = REPO / "harness/g33_fortran/g33_refine_driver.f90"
    base = ["gfortran", "-cpp", "-fsyntax-only", "-ffree-form",
            "-ffree-line-length-none", "-DKDM6_G33_NUMBER_DUMP"]
    for extra in ([], ["-DKDM6_G33_F64"]):
        r = subprocess.run([*base, "-DKDM6_DTCLDCR=120.", *extra, str(drv)],
                           capture_output=True, text=True, cwd=tmp_path)
        # It cannot LINK here (no fixture module), but it must get past the
        # preprocessor and the declaration section.
        assert "no f64 number record family" not in r.stderr
        assert "#error" not in r.stderr
    r = subprocess.run([*base, str(drv)], capture_output=True, text=True,
                       cwd=tmp_path)
    # (both runs fail on the missing .mod files, so the MESSAGE is the signal)
    assert "must pass the compiled kernel" in r.stderr


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


def test_the_driver_takes_the_subcycle_limit_from_what_was_compiled():
    """`loops_used = max(nint(delt_used/120.0), 1)` made the window header a
    THIRD owner of the sub-cycle limit, agreeing with the pinned kernel by
    coincidence (owner review §11). Forcing the driver's constant to 60 while
    the kernel kept 120 moved the header to `loops 5 dtcld 60.000000` with
    EVERY kernel record byte-identical -- a geometry claim nothing else in the
    stream could contradict. The build now reads the limit out of the bytes it
    is about to compile (the overlay under --nflux, not the original), and a
    driver built without it does not compile at all."""
    build = (REPO / "harness/g33_fortran/refine_build.sh").read_text()
    driver = (REPO / "harness/g33_fortran/g33_refine_driver.f90").read_text()
    extract = build.split("DTCLDCR=$(sed")[1].split("\n")[0]
    assert '"$MODULE_SRC"' in extract, "the limit must come from what is compiled"
    assert '"-DKDM6_DTCLDCR=$DTCLDCR"' in build
    assert "#ifndef KDM6_DTCLDCR" in driver and "#error" in driver
    assert "real, parameter :: dtcldcr = KDM6_DTCLDCR" in driver
    assert "120.0" not in driver.split("loops_used = ")[1].split("\n")[0]


def test_a_kernel_declaring_the_limit_twice_is_refused_not_guessed():
    """One declaration or none: picking one of two would let the build and the
    kernel disagree silently, which is the whole point of reading it here."""
    build = (REPO / "harness/g33_fortran/refine_build.sh").read_text()
    guard = build.split("DTCLDCR=$(sed")[1]
    assert "grep -c ." in guard and "declares dtcldcr" in guard
    assert "exit 2" in guard.split("declares dtcldcr")[1][:200]


def _stage_fn(script: str) -> str:
    """The shipped `stage()`, lifted so the test exercises it rather than a
    paraphrase of it."""
    return "stage() {" + script.split("stage() {", 1)[1].split("\n}\n", 1)[0] + "\n}"


@pytest.mark.skipif(shutil.which("shasum") is None, reason="needs shasum")
def test_the_staging_address_is_the_digest_of_what_it_STORES(tmp_path):
    """Staging hashed the SOURCE and copied it afterwards, which is the window
    staging exists to close, one level down (Codex): an edit in between stored
    bytes under an address that is not their digest. The store is shared and
    persistent, so the poisoning outlived the build -- a later run asking for
    the ORIGINAL digest was handed those bytes by the existence check and
    compiled them.

    The adversary edits ONLY the source, and only when something hashes it, so
    it fires exactly when the source is read before it is copied."""
    stage_dir, out = tmp_path / "stage", tmp_path / "out"
    binn = tmp_path / "bin"
    for d in (stage_dir, out, binn):
        d.mkdir()
    (binn / "shasum").write_text(
        '#!/bin/bash\n'
        f'out=$({shutil.which("shasum")} "$@")\n'
        'f="${@: -1}"\n'
        '[ "$f" = "$G33_RACE_FILE" ] && printf "EDITED\\n" >>"$f"\n'
        'printf "%s\\n" "$out"\n')
    (binn / "shasum").chmod(0o755)
    src = tmp_path / "src.F"
    src.write_text("original bytes\n")
    want = hashlib.sha256(src.read_bytes()).hexdigest()

    script = (REPO / "harness/g33_fortran/refine_build.sh").read_text()
    prog = (f'set -euo pipefail\nSTAGE={stage_dir}\n'
            f'STAGE_MAP={out}/staged-map.txt\n:>"$STAGE_MAP"\n'
            + _lift(script, "addr_claim", "addr_verify", "addr_install", "stage")
            + f'\nstage {src}\nprintf "%s" "$STAGED"\n')
    env = {**os.environ, "PATH": f"{binn}{os.pathsep}{os.environ['PATH']}",
           "G33_RACE_FILE": str(src)}
    dst = Path(subprocess.run(["bash", "-c", prog], capture_output=True,
                              text=True, env=env, check=True).stdout.strip())

    assert dst.name.split("-")[0] == bp.sha256(dst), \
        "the staged entry's address is not the digest of its own bytes"
    # ...and the store cannot answer for an address it does not hold: a later
    # build staging the UNCHANGED source gets the original bytes back
    src.write_text("original bytes\n")
    again = Path(subprocess.run(
        ["bash", "-c", prog], capture_output=True, text=True,
        env={**os.environ, "PATH": env["PATH"], "G33_RACE_FILE": ""},
        check=True).stdout.strip())
    assert again.name.split("-")[0] == want
    assert again.read_text() == "original bytes\n"
    assert not list(stage_dir.glob(".staging.*")), "a staging temp survived"


def test_every_compiled_source_including_the_driver_is_staged():
    """The driver was the one compiled input read straight from the tree, so
    the collector's re-read window stayed open on the file that writes the
    window header (Codex)."""
    script = (REPO / "harness/g33_fortran/refine_build.sh") \
        .read_text().replace("\\\n", " ")        # one command, one line
    compiles = [ln for ln in script.splitlines() if ln.startswith("fc ")]
    assert compiles, "the build stopped using fc(); this guard is now blind"
    # `stage` is a STATEMENT now (its refusals cannot abort from inside a
    # command substitution), so the compile input is the variable it publishes
    staged = ('"$STAGED"', '"$DRIVER_STAGED"', '"$MODULE_SRC"')
    unstaged = [ln for ln in compiles if not ln.rstrip().endswith(staged)]
    assert not unstaged, f"compiled without staging: {unstaged}"
    # ...and every one of those variables is set by an actual stage call
    assert script.count("\nstage ") >= len(compiles) - 1, \
        "an fc line reuses a staged variable nothing set for it"


def _lift(script: str, *fns: str) -> str:
    """The shipped shell functions, so the test exercises them rather than a
    paraphrase that can drift from them."""
    out = []
    for fn in fns:
        out.append(fn + "() {" + script.split(fn + "() {", 1)[1]
                   .split("\n}\n", 1)[0] + "\n}")
    return "\n".join(out)


@pytest.mark.skipif(shutil.which("shasum") is None, reason="needs shasum")
@pytest.mark.parametrize("plant,why", [
    ("cp $OTHER $ADDR", "content that is not its address"),
    ("ln -s $OTHER $ADDR", "a symlink"),
    ("mkdir -p $ADDR", "a directory"),
    ("mkfifo $ADDR", "a fifo"),
])
def test_an_existing_cache_entry_is_verified_not_trusted(tmp_path, plant, why):
    """Naming an entry by its digest makes WRITES honest; it does not make a
    shared store immutable (owner review §4). `$TMPDIR` is long-lived, so an
    entry already at an address -- from the pre-#140 implementation that could
    write one, an interrupted run, or anything else with write access -- went
    straight to the compiler, because the existence check asked only whether a
    path was there. Reproduced: the store returned B under A's address.

    The non-regular cases are here because `ln` reports SUCCESS when its
    target is a directory (it means "put it inside"), so an install-then-trust
    guard accepted one."""
    stage_dir, out = tmp_path / "stage", tmp_path / "out"
    stage_dir.mkdir(), out.mkdir()
    src, other = tmp_path / "src.F", tmp_path / "other.F"
    src.write_text("A: the real source\n")
    other.write_text("B: something else\n")
    addr = stage_dir / f"{bp.sha256(src)}-src.F"
    script = (REPO / "harness/g33_fortran/refine_build.sh").read_text()
    prog = (f'set -euo pipefail\nSTAGE={stage_dir}\nSTAGE_MAP={out}/map.txt\n'
            f':>"$STAGE_MAP"\nOTHER={other}\nADDR={addr}\n{plant}\n'
            + _lift(script, "addr_claim", "addr_verify", "addr_install", "stage")
            + f'\nstage {src}\ncat "$STAGED"\n')
    r = subprocess.run(["bash", "-c", prog], capture_output=True, text=True)
    assert r.returncode == 2, f"{why} was accepted: {r.stdout!r}"
    assert "REFUSED" in r.stderr
    assert "B: something else" not in r.stdout


@pytest.mark.skipif(shutil.which("shasum") is None, reason="needs shasum")
def test_a_sound_cache_entry_is_reused_and_an_empty_store_is_filled(tmp_path):
    """The refusals must not cost the cache its reason to exist."""
    stage_dir, out = tmp_path / "stage", tmp_path / "out"
    stage_dir.mkdir(), out.mkdir()
    src = tmp_path / "src.F"
    src.write_text("A: the real source\n")
    script = (REPO / "harness/g33_fortran/refine_build.sh").read_text()
    prog = (f'set -euo pipefail\nSTAGE={stage_dir}\nSTAGE_MAP={out}/map.txt\n'
            f':>"$STAGE_MAP"\n'
            + _lift(script, "addr_claim", "addr_verify", "addr_install", "stage")
            + f'\nstage {src}\nstage {src}\ncat "$STAGED"\n')
    r = subprocess.run(["bash", "-c", prog], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == "A: the real source\n", r.stderr
    assert len(list(stage_dir.glob("*-src.F"))) == 1
    assert not list(stage_dir.glob(".staging.*"))


def test_staging_is_never_called_from_a_command_substitution():
    """`fc ... "$(stage "$SRC")"` runs `stage` in a SUBSHELL, so its `exit 2`
    ended only the substitution: the script continued and the compiler was
    handed an EMPTY last argument. Every refusal in `stage` was unreachable
    from the one place that calls it. Fail-closed logic cannot live behind
    `$( )` -- `stage` publishes into `$STAGED` and is called as a statement."""
    script = (REPO / "harness/g33_fortran/refine_build.sh").read_text()
    # CODE only: the comment above `stage` quotes the pattern it removed, and
    # a guard that reads its own prose would fail on the explanation for it
    code = "\n".join(ln for ln in script.splitlines()
                     if not ln.lstrip().startswith("#"))
    assert "$(stage " not in code, "a refusal behind a subshell cannot abort"
    assert 'STAGED="$dst"' in code


@pytest.mark.parametrize("drop", ["sources.txt", "commands.txt"])
def test_a_MISSING_log_cannot_clear_the_witness_comparison(tmp_path, drop):
    """Skipping the comparison when a log is absent let DELETING it clear the
    check, so a record could claim sources and compile commands with nothing
    left to contradict them -- fail-open under transient deletion (Codex)."""
    root = tmp_path / "b"
    root.mkdir()
    (root / "sources.txt").write_text("harness/x.f90\t" + "a" * 64 + "\n")
    (root / "commands.txt").write_text("gfortran -c x.f90\n")
    (root / "build_provenance.json").write_text(json.dumps({
        "sources": [{"path": "harness/x.f90", "sha256": "a" * 64}],
        "compile_commands": ["gfortran -c x.f90"],
        "diagnostic": {"outdir": "/build"}}))
    assert bp.verify(root) == []
    (root / drop).unlink()
    got = bp.verify(root)
    assert got and drop in got[0] and "not in the bundle" in got[0]


def test_a_malformed_source_line_is_REPORTED_not_raised(tmp_path):
    """`_source_row` falls back to hashing the path when a line carries no
    digest -- right for an older log, but on a tampered one it reached for a
    file that does not exist and raised out of the verification instead of
    failing it. A checker reports on the artifact it judges."""
    root = tmp_path / "b"
    root.mkdir()
    (root / "sources.txt").write_text("harness/x.f90\t" + "a" * 64 + "\nsmuggled\n")
    (root / "commands.txt").write_text("gfortran -c x.f90\n")
    (root / "build_provenance.json").write_text(json.dumps({
        "sources": [{"path": "harness/x.f90", "sha256": "a" * 64}],
        "compile_commands": ["gfortran -c x.f90"],
        "diagnostic": {"outdir": "/build"}}))
    got = bp.verify(root)                      # must not raise
    assert got and "carries no digest" in got[0] and "line 2" in got[0]
