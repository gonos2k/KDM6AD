"""A bundle is produced whole or not at all (owner priority-2).

The bundles used to be assembled by hand — one step built and wrote provenance,
another ran the driver, a third stitched a manifest — so nothing structurally
prevented provenance from one build being published beside members from another.
These tests hold the replacement to that: fail-closed at every stage, and visible
under the destination only after everything succeeded.
"""
import hashlib
import os
import inspect
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.local

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
REF = REPO / 'host' / 'KIM-meso_v1.0' / 'phys' / 'module_mp_kdm6.F'
sys.path.insert(0, str(ROOT))
import g33_refine_experiment as xp  # noqa: E402
import g33_build_provenance as bp  # noqa: E402

sys.path.insert(0, str(ROOT / "tests"))
from test_g33_refine_analyze import _stream  # noqa: E402


def _fake(monkeypatch, *, nsplits=(3, 6), fail_at=None):
    """Stand in for the Fortran build: same call sequence, no compiler."""
    def build(workdir, fixture, algo, nflux, arm="reference"):
        if fail_at == "build":
            raise SystemExit("build failed")
        # The BINARY is published in the bundle and v2 pins it, so the fake
        # build must leave one where a real build would -- and declare the
        # digest OF THAT FILE. Stubbing a different one made the fixture
        # describe a binary it had not written, which the manifest's
        # build_artifacts/build_provenance cross-check now refuses (owner §8.4).
        exe = workdir / "g33_refine_driver"
        exe.write_text("#!fake\n")
        # the GENERATED overlay an instrumented build feeds the compiler --
        # v6 publishes it and reads the sub-cycle limit from those bytes
        ovl = workdir / "module_mp_ovl.F"
        ovl.write_text("   real, parameter, private :: dtcldcr = 120.\n")
        # ...and the logs the record is DERIVED from, agreeing with it: the
        # publish gate re-derives `sources`/`compile_commands` from these, and
        # a fake whose logs contradict its own record is exactly the build the
        # gate exists to refuse (owner review §6).
        (workdir / "commands.txt").write_text("gfortran -c fake\n")
        # The FIXTURE is a compiled source too, and the contract's B, K and
        # DT_BITS are read from the bytes the compiler got (owner review §5) --
        # a fake that logs only the module describes a build with no fixture.
        # the log the record is DERIVED from: one line per role, matching
        # `_FAKE_SOURCES` exactly, or the witness comparison refuses
        rows = _FAKE_SOURCES(FIX, ovl)
        (workdir / "sources.txt").write_text(
            "".join(f"{r['path']}\t{r['sha256']}\n" for r in rows))
        (workdir / "staged-map.txt").write_text(
            "".join(f"{ {'fixture': FIX, 'module': ovl}.get(r['role'], MOD) }"
                    f"\t{r['path']}\n" for r in rows))
        # a v6-shaped record: what a real build writes, faked
        (workdir / "build_provenance.json").write_text(json.dumps({
            "module_path": str(MOD),
            "module_sha256": xp.res.sha256(MOD),
            "fixture_sha256": xp.res.sha256(FIX),
            "compiler_version": "gfortran (fake) 1.0",
            "compiler_sha256": "1" * 64,
            "build_script_sha256": "7" * 64,
            "compile_commands": ["gfortran -c fake"],
            "sources": _FAKE_SOURCES(FIX, ovl),
            "compiled_module_sha256": xp.res.sha256(ovl),
            # WHERE THE BUILD RAN, in full. `verify()` normalises the
            # published logs by all three roots, so a one-key stand-in
            # described a build whose record could not be re-derived -- and
            # v7 holds this to an exact key set for that reason.
            "diagnostic": {
                "outdir": str(workdir),
                "tmpdir": str(workdir / "tmp"),
                "repo_root": str(REPO),
                "compiler_path": "/usr/bin/gfortran",
                "compiler_f951_path": "/usr/libexec/f951",
                "executable_path": str(exe),
                "compile_commands_literal": ["gfortran -c fake"],
            },
            # v7 holds this block to an EXACT key set and a role table, so a
            # fake that carries a subset describes a build that could not have
            # happened (owner review §5).
            "schema": "g33_build_provenance_v1",
            "compiler_f951_sha256": "5" * 64,
            "compiled_module_path": "module_mp_ovl.F",
            "fixture_path": FIXLOG,
            "repo_commit": "0" * 40,
            "tree_dirty": False,
            "executable_sha256": xp.res.sha256(exe)}, indent=2, sort_keys=True))
        return exe

    def analyses(out, exe, ns, mode, precision="f32"):
        """One well-formed entry per analysis a real bundle carries.

        The real `_analyses` runs the analyzers on a driver stream, which this
        fake has none of. Returning nothing made the producer publish an
        `instrumented` bundle with no analyses; returning ONE made it publish
        one with five of the six missing, which the schema now refuses -- an
        instrumented bundle must carry the analyses that make it instrumented
        (owner §8.3). The stub produces what a real bundle would rather than
        the test asserting a shape the contract forbids.
        """
        # ...and each analysis reaches its module THROUGH THE SEAM, as the
        # real `_analyses` does, so the bundle can say what executed (owner
        # review §8). A fake that fabricates analyses without dispatching
        # leaves the attestation empty -- a bundle claiming analyses that
        # nothing ran.
        for _kind in xp.res.REQUIRED_WHEN_INSTRUMENTED:
            _seed = xp.ANALYSES.get(_kind)
            if _seed:
                xp._an(_seed[0] if isinstance(_seed, tuple) else _seed)
        out_entries = []
        for kind in xp.res.REQUIRED_WHEN_INSTRUMENTED:
            p = out / f"n{ns[0]}.{mode}.{kind}.json"
            p.write_text("{}\n")
            out_entries.append({
                "file": p.name, "nsplit": ns[0], "analysis": kind,
                "sha256": xp.res.sha256(p)})
        return out_entries

    def members(exe, out, ns, mode, *, arm="reference", nflux=False,
                rho_profile="as-is", width=3, levels=None, algo=None,
                fixture=None, horizon=None, dtcldcr=None):
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
    # The fake's members are G33R-only, so the extension analyses have no G33N to
    # read. Their correctness is covered where they can actually run:
    # test_g33_cap_interface.py against a real stream and
    # test_g33_matched_closure.py against synthetic G33N. What these tests are
    # about is the producer's atomicity and its manifest -- but an instrumented
    # bundle with NO analyses is one the v2 validator refuses, so the stub
    # returns a well-formed entry rather than nothing.
    monkeypatch.setattr(xp, "_analyses", analyses)
    # _driver_analyses RUNS the driver four times; the fake build returns a
    # path with no binary behind it, so it must be stubbed alongside.
    monkeypatch.setattr(xp, "_driver_analyses", lambda *a, **k: [])
    monkeypatch.setattr(xp, "_run", lambda cmd, **kw: "gfortran (fake) 1.0\n")


# REAL files, because v6 ties the kernel record to the module the manifest
# pins and the resolved gate reads the fixture's own bytes: a stand-in would
# be testing a document that could not describe a run.
FIX = ROOT / "g33_fortran" / "g33_fixture_multisubcycle_v1.f90"
#: as the build logs it -- repo-relative, which is what the snapshot keys on
FIXLOG = str(FIX.relative_to(REPO))
# ...and RELATIVE, as the real invocation records it: the kernel record and
# the manifest name one file, so they must spell it the same way. The public
# checkout's STAND-IN is relative for the same reason -- an absolute
# `module_path` cannot equal the relative `source_path` the record carries,
# and v6 requires those two to be one file.
MOD = (xp.kernel_source("legacy")
       if (REPO / xp.kernel_source("legacy")).is_file()
       else FIX.relative_to(REPO))


def _FAKE_SOURCES(fix, ovl):
    """One row per role the v7 contract requires (owner review §5).

    The role is DERIVED, never asserted. `verify()` re-derives every role
    from the path, so a fake that labels its own rows can contradict the
    record it exists to match -- and on a PUBLIC checkout it did: `MOD`
    falls back to the fixture there, one path carried both `module` and
    `fixture`, and re-derivation called them both `fixture`. Fifteen tests
    failed on CI and none on a host that has `host/**` (measured, in a
    throwaway worktree -- which is what a public checkout is).

    THE MODULE ROW IS THE OVERLAY THIS FAKE ACTUALLY WROTE, which is also
    what a real build compiles: gfortran never opens `module_mp_kdm6.F`, it
    opens the overlay generated from it. Naming the private kernel here
    instead dressed a file that is ABSENT on a public checkout as compiled
    input, under a digest of its own path (Codex). The overlay exists on
    every checkout, so nothing has to be invented -- and `sources[module]`
    now agrees with `compiled_module_sha256`, which v7 requires.
    """
    rows = [{"path": FIXLOG, "sha256": xp.res.sha256(fix)},
            {"path": "module_mp_ovl.F", "sha256": xp.res.sha256(ovl)}]
    for path in ("harness/g33_fortran/g33_refine_driver.f90",
                 "harness/g33_fortran/stub_wrf_error.f90",
                 "host/KIM-meso_v1.0/frame/libmassv.F",
                 "host/KIM-meso_v1.0/share/module_model_constants.F",
                 "host/KIM-meso_v1.0/phys/module_mp_radar.F"):
        # A TRACKED path must carry its real digest: the snapshot holds every
        # compiled source in the repo to its HEAD blob, so a placeholder here
        # would describe a build from bytes that never existed. `host/**` is
        # gitignored, so those keep a stand-in -- they are inputs a real build
        # reads and this fake does not, which is a different thing from
        # inventing the module the record pins.
        real = REPO / path
        rows.append({"path": path,
                     "sha256": xp.res.sha256(real) if real.is_file()
                     else hashlib.sha256(path.encode()).hexdigest()})
    return [{"path": r["path"], "role": bp.role_of(r["path"]),
             "sha256": r["sha256"]} for r in rows]


def _produce(dest, **kw):
    return xp.produce(dest, fixture="g33_fixture_multisubcycle_v1", algo="legacy",
                      nsplits=kw.pop("nsplits", (3, 6)), mode="rezero",
                      nflux=kw.pop("nflux", False), module=MOD, **kw)


@pytest.fixture(autouse=True)
def _kernel_geometry_on_a_public_checkout(monkeypatch, request):
    """The kernel source is PRIVATE and gitignored, and the producer now
    REFUSES rather than defaulting the sub-cycle limit -- which is the point
    of that refusal, and which stops every bundle-ASSEMBLY test on a public
    checkout at a read those tests are not about. Where the source is
    present the real one is used; where it is absent the record is faked
    like the compiler and the driver beside it. The refusal has its own
    test."""
    # A test ABOUT the read opts out, or the seam would answer for it: on a
    # public checkout the stub replaced the function whose refusal the test
    # asserts, returning a fake for `legacy` and a KeyError for the unknown
    # algorithm rather than the SystemExit under test (Codex).
    if REF.is_file() or request.node.get_closest_marker("real_kernel_geometry"):
        return
    # The stand-in module is what the result record digests as the kernel
    # source, so it has to be what `kernel_source` names for `legacy`.
    monkeypatch.setattr(xp, "kernel_source",
                        lambda algo, _m=MOD: _m if algo == "legacy" else None)
    monkeypatch.setattr(xp, "kernel_geometry", _fake_kernel_geometry)


def _fake_kernel_geometry(precision="f32", algo="legacy", compiled=None):
    """The seam's record, shaped like the real one INCLUDING the compiled
    witness -- a v6 manifest assembled without it does not validate."""
    word = "42F00000" if precision == "f32" else "405E000000000000"
    return {"schema": xp.KERNEL_GEOMETRY_SCHEMA,
            **({"compiled_dtcldcr_word": word,
                "compiled_source_sha256": hashlib.sha256(
                    Path(compiled).read_bytes()).hexdigest()}
               if compiled is not None else {}),
            "dtcldcr": 120.0, "dtcldcr_storage": precision,
            "dtcldcr_word": word, "algorithm": algo,
            "source_path": str(xp.kernel_source(algo)),
            "source_sha256": xp.res.sha256(xp.kernel_source(algo))}


@pytest.mark.real_kernel_geometry
def test_the_public_checkout_seam_has_the_signature_it_stands_in_for():
    """The seam only runs where `host/**` is absent, so a signature that
    drifted from `kernel_geometry` broke NOTHING here and every bundle
    assembly test on CI -- which is where the compiled-overlay argument was
    added and this stub was not (Codex, twice now). Asserting the signature
    makes the drift fail on the machine that caused it."""
    shape = lambda f: [(p.name, p.default, p.kind)
                       for p in inspect.signature(f).parameters.values()]
    assert shape(_fake_kernel_geometry) == shape(xp.kernel_geometry)


@pytest.fixture(autouse=True)
def _fixture_path(monkeypatch):
    """produce() derives the fixture .f90 from its name; point it at a real file."""
    real = xp.res.input_digest
    monkeypatch.setattr(xp.res, "input_digest",
                        lambda fx, module, rho: real(FIX, module if Path(module).is_file() else FIX, rho))


@pytest.mark.parametrize("stage", ["build", "run"])
def test_a_failure_publishes_NOTHING(tmp_path, monkeypatch, stage):
    _fake(monkeypatch, fail_at=stage)
    with pytest.raises(SystemExit):
        _produce(tmp_path / "bundle")
    assert not (tmp_path / "bundle").exists()
    assert not list(tmp_path.glob(".g33-bundle-*")), "temp bundle left behind"


def test_a_member_that_fails_the_strict_parser_stops_the_run(tmp_path, monkeypatch):
    _fake(monkeypatch)

    def bad(exe, out, ns, mode, *, arm="reference", nflux=False,
            rho_profile="as-is", width=3, levels=None, algo=None,
            fixture=None, horizon=None, dtcldcr=None):
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
    assert len(target.name) == 64, (
        "bundle directory is named by the FULL manifest identity digest. A "
        "16-hex prefix is 64 bits, and the directory it names was REUSED "
        "without re-checking (owner §9.1).")


def test_an_identical_rerun_reuses_the_same_immutable_bundle(tmp_path, monkeypatch):
    """Content-addressed: the same manifest is the same bundle. Rebuilding it
    would delete the directory `dest` currently points at."""
    _fake(monkeypatch)
    first = _produce(tmp_path / "bundle").resolve()
    second = _produce(tmp_path / "bundle").resolve()
    assert first == second and first.exists()


def _probe_stream(nsplit=3, fixture="fx"):
    """A COMPLETE probe stream: the reader now requires the exact
    field x cell universe plus INITIAL, all three forcings and PREC, because
    'absent' silently disabled every check (owner §7.2)."""
    out = [f"G33P BEGIN 4 precision f64 source_precision f32 fixture {fixture} "
           f"algorithm legacy mode rezero tiles 1 rho_profile as-is "
           f"{nsplit} 1 1 {300.0/nsplit:.6f} {300.0/nsplit:.6f} 1 1"]
    for f in xp.pr.FIELDS:
        out.append(f"G33P STATE {f} 1 0   1.0000000000000000E+000")
        out.append(f"G33P INITIAL {f} 1 0   1.0000000000000000E+000")
    for nm in ("rho", "delz", "pii"):
        out.append(f"G33P FORCING {nm} 1 0   1.0000000000000000E+000")
    for sp in (1, 2, 3):
        out.append(f"G33P PREC {sp} 1   0.0000000000000000E+000")
    out.append("G33P END")
    return "\n".join(out) + "\n"


def test_the_probe_arm_cross_checks_G33R_against_G33P(tmp_path, monkeypatch):
    """The two defects that got through before were a transposed index and a
    format that dropped an exponent's `E`. Both show up as a value mismatch."""
    g33r = {("state", "qv", 1, 0): 1.0, ("prec", 1, 1): 2.0, ("prec", 2, 1): 3.0}
    xp._agree(g33r, dict(g33r), "n.txt")                    # identical: fine
    swapped = dict(g33r)
    swapped[("prec", 1, 1)], swapped[("prec", 2, 1)] = 3.0, 2.0
    with pytest.raises(xp.pr.ProbeError, match="different f32 words at"):
        xp._agree(g33r, swapped, "n.txt")
    missing = {k: v for k, v in g33r.items() if k != ("prec", 2, 1)}
    with pytest.raises(xp.pr.ProbeError, match="1 only on G33R"):
        xp._agree(g33r, missing, "n.txt")


# ---- owner §14-4: the analyses are produced BY the bundle and digested INTO it

def test_the_analysis_registry_names_a_real_module_and_callable():
    """A registry entry pointing at a module that does not exist would fail only
    when a bundle is produced -- which needs gfortran, so never in CI."""
    import importlib
    for name, (mod, fn) in xp.ANALYSES.items():
        m = importlib.import_module(mod)
        assert m is not None, f"{name} names a missing module {mod}"
        assert callable(fn)


# ---- owner §5.2: the bundle must say which forcing arm it is ------------------

def test_the_argv_helper_omits_the_arm_for_the_default():
    """`as-is` must produce the same command line the producer always used, or
    every existing bundle's runtime_argv would stop describing how it was made."""
    assert xp._argv(Path("drv"), 12, "rezero", "as-is") == ["drv", "12", "rezero"]
    assert xp._argv(Path("drv"), 12, "rezero", "uniform") == \
        ["drv", "12", "rezero", "3", "uniform"]


def test_a_density_arm_cannot_be_published_through_a_path_that_hides_it():
    """Only G33N and G33P carry the arm. Plain G33R does not, and changing that
    header would invalidate every archived decision artifact and the pinned
    non-invasiveness baseline — an owner decision, not this producer's. So the
    gap is closed by construction: the unidentifiable combination is refused
    (owner §9)."""
    with pytest.raises(SystemExit, match="needs --nflux"):
        xp.produce(Path("/tmp/should-not-exist"),
                   fixture="g33_fixture_multisubcycle_v1", algo="legacy",
                   nsplits=(3,), mode="rezero", nflux=False, module=MOD,
                   rho_profile="uniform")


def test_the_tile_width_comes_from_the_FIXTURE_not_a_constant():
    """`3` was hardcoded, so a non-default profile on any fixture that is not
    three columns wide would fail the driver's tile-sum check."""
    assert xp.fixture_width("g33_fixture_multisubcycle_v1") == 3
    assert xp._argv(Path("d"), 3, "rezero", "uniform", 7)[-2:] == ["7", "uniform"]


# ---- owner P0-2 / P1-11.5: the bundle analysis inherits the bundle's run ------

def test_PRODUCE_passes_the_bundles_own_mode_and_width_to_the_analysis(
        tmp_path, monkeypatch):
    """The other half, and the half where the defect actually lived.

    The test above calls `_driver_analyses` directly, so it proves that function
    forwards what it is given — and would still pass if `produce()` went back to
    calling it with a hardcoded `"rezero", 3`. That producer boundary is exactly
    where P0-2 was: a --mode carry bundle shipped a rezero analysis. Replacing
    the original source-grep with the isolated test alone DROPPED this coverage.
    """
    _fake(monkeypatch)
    seen = {}
    monkeypatch.setattr(xp, "_driver_analyses",
                        lambda out, exe, ns, mode, width, levels, algo=None,
                        fixture=None, horizon=None, dtcldcr=None: seen.update(
                            mode=mode, width=width, levels=levels) or [])

    xp.produce(tmp_path / "bundle", fixture="g33_fixture_multisubcycle_v1",
               algo="legacy", nsplits=(3, 6), mode="carry", nflux=True,
               module=MOD)
    want_w, want_k = xp.fixture_dims("g33_fixture_multisubcycle_v1")
    assert seen == {"mode": "carry", "width": want_w, "levels": want_k}, (
        "produce() must hand the analysis the bundle's OWN mode and fixture "
        f"width and level count, got {seen}")


def test_the_metric_analysis_records_the_run_it_describes():
    """argv per arm, and the arm each STREAM declares back — so a reader can
    check the analysis describes the run it claims to."""
    src = (ROOT.parent / "harness/g33_metric_trajectory.py").read_text()
    for f in ('"mode": mode', '"tile_width": width', '"arms_runtime"',
              '"declared_rho_profile"'):
        assert f in src


def test_a_repeated_nsplit_is_refused_at_the_COMMAND_LINE():
    """Both members write one filename, the second overwrites the first, and the
    published directory holds one — so the manifest's duplicate check never sees
    it (owner P1-11.5)."""
    with pytest.raises(SystemExit, match="repeats"):
        xp.produce(Path("/tmp/should-not-exist"),
                   fixture="g33_fixture_multisubcycle_v1", algo="legacy",
                   nsplits=(3, 3, 6), mode="rezero", nflux=False, module=MOD)


def test_a_duplicate_nsplit_is_still_refused_from_a_generator(tmp_path):
    """Materialising must not cost the duplicate check its input."""
    with pytest.raises(SystemExit, match="repeats"):
        xp.produce(tmp_path / "b", fixture="g33_fixture_multisubcycle_v1",
                   algo="legacy", nsplits=(n for n in (3, 6, 6)),
                   mode="rezero", nflux=False, module=tmp_path / "m.F")


# ---- owner P0-1 / P0-2: the bytes that RAN, bound to the pin -----------------

#: `produce()` refuses unless every producing module's working bytes hash to its
#: HEAD blob -- correct for a bundle, wrong for a test suite, which has to run
#: while those very modules are being edited. The tests that exercise the check
#: hold the real function and call it directly.


def test_an_EMPTY_nsplit_list_is_refused(tmp_path):
    """The generator fix stopped `nsplits` being exhausted; it did not stop a
    caller passing an empty one, and every loop then runs zero times and
    publishes a manifest that looks complete (owner P0-E3)."""
    with pytest.raises(SystemExit, match="at least one member"):
        xp.produce(tmp_path / "b", fixture="g33_fixture_multisubcycle_v1",
                   algo="legacy", nsplits=(), mode="rezero", nflux=False,
                   module=tmp_path / "m.F")


def test_a_NON_POSITIVE_nsplit_is_refused(tmp_path):
    for bad in ((0, 3), (-1,)):
        with pytest.raises(SystemExit, match="must be positive"):
            xp.produce(tmp_path / "b", fixture="g33_fixture_multisubcycle_v1",
                       algo="legacy", nsplits=bad, mode="rezero", nflux=False,
                       module=tmp_path / "m.F")


# ---- owner §9.1: an existing bundle directory is verified, not adopted -------

def test_an_identical_rerun_REUSES_the_bundle(tmp_path, monkeypatch):
    """Content-addressed: the same manifest is the same bundle, and rebuilding
    it would delete the directory `dest` points at."""
    _fake(monkeypatch)
    a = _produce(tmp_path / "b").resolve()
    b = _produce(tmp_path / "b").resolve()
    assert a == b
    assert len(list((tmp_path / "b.bundles").iterdir())) == 1


# ---- owner P0-1 / P0-2: the fixture, and pins that cannot lie ---------------

# ---- the pinned module list must be COMPLETE, not remembered ---------------

# ---- content identity must survive a REAL rebuild (owner P0-1) -------------

def test_the_MULTI_RUN_config_is_read_from_the_RESULT():
    """Not recomputed from the fixture. Deriving `decompositions` from the
    fixture recorded what the analysis was ASSUMED to have run; the analysis
    now reports what it drove, and the producer copies that (Codex)."""
    src = (ROOT / "g33_refine_experiment.py").read_text()
    body = src[src.index("def _multi_run_analyses("):]
    body = body[:body.index("\ndef ", 1)]
    assert 'ran = result["ran"]' in body
    assert '"decompositions": ran["decompositions"]' in body
    assert "compositions_of(fixture)" not in body, \
        "the recorded decompositions must come from the run, not the fixture"


# --- the window universe is EXACT, not summarized (owner review §4) ----------

def _domain_run(cols=(1, 2, 3), ks=range(4)):
    """A window `run` dict with only the keys the domain pin reads."""
    return {("state", "qr", c, k): 1.0 for c in cols for k in ks}


def _domain_text():
    from test_g33_number_transport import _call as _ncall, _stream as _nstream
    return _nstream(_ncall(1, cols=(1, 2, 3), ks=4))


def test_the_exact_window_universe_is_the_control_case():
    xp._require_fixture_domain(_domain_text(), "n1.rezero.txt", 1, "rezero",
                               "as-is", 3, 4, _samerun_window())


@pytest.mark.parametrize("cols,ks,match", [
    ((1, 3), range(4), "two protocols, two domains"),      # column 2 missing
    ((0, 1, 2, 3), range(4), "two protocols, two domains"),  # illegal column 0
    ((1, 2, 3), (-1, 0, 1, 2), "declares exactly 0..3"),   # shifted levels
    ((1, 2, 3), (0, 1, 2, 4), "declares exactly 0..3"),    # gapped levels
])
def test_a_summarized_domain_is_not_an_exact_one(cols, ks, match):
    """max(cols)==B and len(ks)==K are summaries: {1,3} has max 3 and
    {-1,0,1,2} has len 4, and each is a different domain wearing the right
    summary. The pin compares the SETS."""
    with pytest.raises(xp.ra.RefineError, match=match):
        xp._require_fixture_domain(_domain_text(), "n1.rezero.txt", 1,
                                   "rezero", "as-is", 3, 4,
                                   _domain_run(cols, ks))


# --- probe agreement is a UNIVERSE equality, then a value equality (§4.3) ----

def test_probe_agreement_requires_the_same_record_universe_BOTH_ways():
    """One direction let G33P carry records G33R never wrote: every G33R key
    found its counterpart, the extras were never visited, and two protocols
    with different domains were called agreed."""
    g33r = {("state", "qr", 1, 0): 1.0, ("meta", "nsplit"): 1}
    extra = dict(g33r)
    extra[("state", "qr", 2, 0)] = 5.0
    with pytest.raises(xp.pr.ProbeError, match="1 only on G33P"):
        xp._agree(g33r, extra, "x")
    with pytest.raises(xp.pr.ProbeError, match="1 only on G33R"):
        xp._agree(g33r, {("meta", "nsplit"): 1}, "x")
    xp._agree(g33r, dict(g33r), "x")    # the control still passes


# --- the SAME-RUN contract across protocols in one stdout (owner review §6) --

def _samerun_window(cols=(1, 2, 3), ks=range(4)):
    run = _domain_run(cols, ks)
    run[("meta", "algorithm")] = "legacy"
    run[("meta", "delt")] = 100.0
    run.update({("forcing", nm, c, k): 1.0
                for nm in ("rho", "delz") for c in cols for k in ks})
    return run


def test_the_same_run_contract_control_passes():
    xp._require_fixture_domain(_domain_text(), "n1.rezero.txt", 1, "rezero",
                               "as-is", 3, 4, _samerun_window())


@pytest.mark.parametrize("mutate,match", [
    (lambda r: r.update({("meta", "algorithm"): "conservative"}),
     "two algorithms, one stdout"),
    (lambda r: r.update({("meta", "delt"): 300.0}),
     "two timesteps, one stdout"),
    (lambda r: r.pop(("meta", "delt")),
     "declares no delt"),
    (lambda r: r.update({("forcing", "rho", 2, 1): 2.0}),
     "two different runs"),
    (lambda r: [r.pop(k) for k in list(r) if k[0] == "forcing"],
     "no rho/delz forcing"),
    (lambda r: r.update({("meta", "ntile"): 3}),
     "declares 3 tiles"),
    (lambda r: r.update({("meta", "tiles"): (1, 2)}),
     "two decompositions, one run"),
])
def test_two_strict_protocols_describing_two_runs_are_refused(mutate, match):
    """Each protocol validated only inside itself, so a G33N leg declaring
    legacy/delt=100/rho=1.0 beside a window declaring
    conservative/delt=300/rho=2.0 passed every check -- measured before this
    contract existed. Every fact BOTH sides record is now compared."""
    run = _samerun_window()
    mutate(run)
    with pytest.raises(xp.ra.RefineError, match=match):
        xp._require_fixture_domain(_domain_text(), "n1.rezero.txt", 1,
                                   "rezero", "as-is", 3, 4, run)


def test_the_same_run_contract_compares_at_the_MEMBERS_precision():
    """f32 words dropped 29 bits on the f64 arm, so two DISTINCT f64 streams
    whose forcing differed below f32 resolution compared equal (Codex). The
    width now comes from the window's declared precision: a sub-f32
    perturbation on an f64 member must refuse."""
    run = _samerun_window()
    run[("meta", "precision")] = "f64"
    run[("meta", "source_precision")] = "f32"
    run[("forcing", "rho", 2, 1)] = 1.0 * (1 + 1e-12)
    with pytest.raises(xp.ra.RefineError, match="two different runs"):
        xp._require_fixture_domain(_domain_text(), "n1.rezero.txt", 1,
                                   "rezero", "as-is", 3, 4, run, arm="f64")
    # ...and the SAME perturbation on an f32 member is below the value
    # model's resolution: both notations name one f32 word, so it passes.
    ok = _samerun_window()
    ok[("forcing", "rho", 2, 1)] = 1.0 * (1 + 1e-12)
    xp._require_fixture_domain(_domain_text(), "n1.rezero.txt", 1,
                               "rezero", "as-is", 3, 4, ok)


def test_a_valid_NON_INTEGRAL_split_is_not_two_timesteps():
    """delt/dtcld reach the window through the header's F0.6 print -- a
    six-decimal channel whatever the member's precision. Word equality at f64
    width refused delt = 300/7: exact in the G33N word, "42.857143" in the
    window, two spellings of ONE recorded fact (Codex). The channel's
    resolution is the binding's resolution; a genuinely different delt still
    refuses."""
    import struct
    delt32 = struct.unpack(">f", struct.pack(">f", 300.0 / 7.0))[0]
    hex32 = struct.pack(">f", delt32).hex().upper()
    from test_g33_number_transport import _call as _nc, _stream as _ns
    text = _ns(_nc(1, cols=(1, 2, 3), ks=4).replace("42C80000", hex32))
    run = _samerun_window()
    run[("meta", "precision")] = "f64"
    run[("meta", "delt")] = float(f"{delt32:.6f}")
    xp._require_fixture_domain(text, "n7.rezero.txt", 1, "rezero", "as-is",
                               3, 4, run)
    run[("meta", "delt")] = 300.0
    with pytest.raises(xp.ra.RefineError, match="two timesteps"):
        xp._require_fixture_domain(text, "n7.rezero.txt", 1, "rezero",
                                   "as-is", 3, 4, run)


def test_a_header_claiming_MORE_precision_than_its_channel_is_refused():
    """Rounding BOTH sides re-admitted forgery (Codex): delt=42.8571425 --
    more precision than F0.6 can produce, a genuinely different number than
    the G33N word -- rounded to the same six decimals and bound. A value
    that does not round-trip through the channel is refused, not rounded."""
    import struct
    delt32 = struct.unpack(">f", struct.pack(">f", 300.0 / 7.0))[0]
    hex32 = struct.pack(">f", delt32).hex().upper()
    from test_g33_number_transport import _call as _nc, _stream as _ns
    text = _ns(_nc(1, cols=(1, 2, 3), ks=4).replace("42C80000", hex32))
    run = _samerun_window()
    run[("meta", "delt")] = 42.85714250
    with pytest.raises(xp.ra.RefineError, match="more precision than the F0.6"):
        xp._require_fixture_domain(text, "n7.rezero.txt", 1, "rezero",
                                   "as-is", 3, 4, run)
    run[("meta", "delt")] = float("nan")
    with pytest.raises(xp.ra.RefineError, match="more precision than the F0.6"):
        xp._require_fixture_domain(text, "n7.rezero.txt", 1, "rezero",
                                   "as-is", 3, 4, run)


def test_the_window_loop_count_binds_the_G33N_loop_universe():
    """Two records of one fact (owner review §4, sixth round): the window
    header records what the kernel ran; calls() proves the G33N records
    cover exactly 1..L. A window declaring 3 beside records covering 1..1
    is two runs' paperwork in one stdout."""
    run = _samerun_window()
    run[("meta", "loops")] = 3
    with pytest.raises(xp.ra.RefineError, match="ran 3 inner loops"):
        xp._require_fixture_domain(_domain_text(), "n1.rezero.txt", 1,
                                   "rezero", "as-is", 3, 4, run)
    run[("meta", "loops")] = 1
    xp._require_fixture_domain(_domain_text(), "n1.rezero.txt", 1,
                               "rezero", "as-is", 3, 4, run)


# --- the EXPECTED experiment binds the header's claims (owner review §5) -----

def test_a_header_may_not_choose_the_width_it_is_checked_at():
    """The comparison width came from the header's own precision claim, so a
    G33P forging precision=f32 on an f64 stream re-opened the 29-bit
    conflation the width fix closed -- measured on a live member. The width
    now comes from the EXPECTED arm, and the header must agree with it."""
    run = _samerun_window()
    run[("meta", "precision")] = "f32"
    run[("meta", "source_precision")] = "f32"
    with pytest.raises(xp.ra.RefineError, match="may not choose the width"):
        xp._require_fixture_domain(_domain_text(), "n1.rezero.txt", 1,
                                   "rezero", "as-is", 3, 4, run, arm="f64")
    run[("meta", "precision")] = "f64"
    run[("meta", "source_precision")] = "f64"
    with pytest.raises(xp.ra.RefineError, match="f32, always"):
        xp._require_fixture_domain(_domain_text(), "n1.rezero.txt", 1,
                                   "rezero", "as-is", 3, 4, run, arm="f64")


@pytest.mark.parametrize("key,val,match", [
    (("meta", "fixture"), "g33_fixture_other_v1", "the caller asked for"),
    (("meta", "algorithm"), "conservative", "two algorithms, one stdout"),
    (("meta", "rho_profile"), "inverted", "rho_profile"),
])
def test_the_window_metadata_must_be_the_requested_experiment(key, val, match):
    run = _samerun_window()
    run[key] = val
    with pytest.raises(xp.ra.RefineError, match=match):
        xp._require_fixture_domain(_domain_text(), "n1.rezero.txt", 1,
                                   "rezero", "as-is", 3, 4, run,
                                   algo="legacy", fixture="g33_fixture_x")


# --- today's capability profile, instrumented or not (owner review §8) -------

def _profile_run():
    run = {("state", "qr", c, k): 1.0 for c in (1, 2) for k in range(2)}
    run[("initial", "qr", 1, 0)] = 1.0
    run.update({("forcing", nm, c, k): 1.0
                for nm in ("rho", "delz") for c in (1, 2) for k in range(2)})
    run.update({("meta", "delt"): 100.0, ("meta", "loops"): 1,
                ("meta", "dtcld"): 100.0, ("meta", "nsplit"): 1,
                ("meta", "algorithm"): "legacy"})
    return run


def test_the_current_profile_control_passes():
    xp._require_current_profile(_profile_run(), "n1", 2, 2, algo="legacy")


@pytest.mark.parametrize("mutate,match", [
    (lambda r: [r.pop(k) for k in list(r) if k[0] == "forcing"],
     "publishes its rho"),
    (lambda r: [r.pop(k) for k in list(r) if k[0] == "initial"],
     "no INITIAL state"),
    (lambda r: r.pop(("meta", "loops")), "declares no loops"),
    (lambda r: r.update({("meta", "dtcld"): 50.0}),
     "kernel's rule gives"),
    (lambda r: r.update({("meta", "delt"): -1.0, ("meta", "dtcld"): -1.0}),
     "must be positive"),
    (lambda r: [r.pop(k) for k in list(r)
                if k[0] == "state" and k[2] == 2],
     "the fixture declares"),
])
def test_a_member_below_todays_profile_is_refused(mutate, match):
    """The reader keeps INITIAL/forcing/time-geometry OPTIONAL so archived
    streams still parse; the producer of new evidence may not inherit that
    leniency (owner review §8). The loops x dtcld == delt rule is the
    kernel's own, measured to hold on all 192 published headers."""
    run = _profile_run()
    mutate(run)
    with pytest.raises(xp.ra.RefineError, match=match):
        xp._require_current_profile(run, "n1", 2, 2, nsplit=1, horizon=100.0, dtcldcr=120.0)


# --- the fixture's HORIZON is the third dimension (owner review §4) ---------

def test_the_fixture_horizon_and_the_kernels_geometry_rule():
    """DT_BITS is a fixture parameter like B and K, and every member's step
    is derived from it. The rule is the driver's own (F:362, F:930-932)."""
    assert xp.fixture_horizon("g33_fixture_boundary_mapping_v1") == 60.0
    assert xp.fixture_horizon("g33_fixture_multisubcycle_v1") == 300.0
    assert xp.expected_geometry(60.0, 12, "f32", 120.0) == (5.0, 1, 5.0)
    assert xp.expected_geometry(300.0, 3, "f64", 120.0) == (100.0, 1, 100.0)
    # delt > dtcldcr is where the loop count stops being 1
    assert xp.expected_geometry(300.0, 1, "f32", 120.0) == (300.0, 3, 100.0)


def test_a_member_that_integrates_the_WRONG_HORIZON_is_refused():
    """Both protocols agreeing on delt proves one internally consistent run,
    not the REQUESTED one: 12 members stepping 20 s are perfect with each
    other and integrate 240 s of a 300 s fixture. Measured before fixed."""
    run = _samerun_window()
    run[("initial", "qr", 1, 0)] = 1.0
    run.update({("meta", "loops"): 1, ("meta", "dtcld"): 100.0,
                ("meta", "nsplit"): 1})
    xp._require_current_profile(run, "n1", 3, 4, nsplit=1, horizon=100.0, dtcldcr=120.0)
    with pytest.raises(xp.ra.RefineError, match="integrates 100.0 s of a 300"):
        xp._require_current_profile(run, "n1", 3, 4, nsplit=1, horizon=300.0, dtcldcr=120.0)


def test_the_G33N_leg_answers_to_the_FIXTURE_at_its_own_width():
    """The window carries delt through a six-decimal channel, so binding the
    G33N leg to the window binds it only to six decimals. The raw word must
    meet the raw expectation."""
    run = _samerun_window()
    run[("meta", "loops")] = 1
    run[("meta", "dtcld")] = 100.0
    xp._require_fixture_domain(_domain_text(), "n1", 1, "rezero", "as-is",
                               3, 4, run, horizon=100.0, dtcldcr=120.0)
    with pytest.raises(xp.ra.RefineError, match="the fixture's 300.0 s"):
        xp._require_fixture_domain(_domain_text(), "n1", 1, "rezero", "as-is",
                                   3, 4, run, horizon=300.0, dtcldcr=120.0)


def test_the_REQUESTED_decomposition_binds_not_merely_a_coherent_one():
    """Both protocols agreeing proves ONE decomposition, not the requested
    one -- and `ncmin` is a scalar set by a tile's last column, so an
    unrequested tiling is a different operator. In the density experiment
    that is a confounder: the arm moves the density profile and an unchecked
    tile change would move the threshold vector with it. Measured before
    fixed."""
    from test_g33_number_transport import _call as _nc, _stream as _ns
    text = _ns(_nc(1, cols=(1,), split=1, tile=1),
               _nc(2, cols=(2, 3), split=1, tile=2), nsplit=1, ntile=2)
    run = _samerun_window(cols=(1, 2, 3), ks=range(2))
    run.update({("meta", "loops"): 1, ("meta", "dtcld"): 100.0,
                ("meta", "nsplit"): 1})
    xp._require_fixture_domain(text, "arm", 1, "rezero", "as-is", 3, 2, run,
                               horizon=100.0, tiles=(1, 2), dtcldcr=120.0)
    with pytest.raises(xp.ra.RefineError, match="asked for \\(3,\\)"):
        xp._require_fixture_domain(text, "arm", 1, "rezero", "as-is", 3, 2,
                                   run, horizon=100.0, tiles=(3,), dtcldcr=120.0)


def test_the_ONE_validator_reads_the_probe_arm_too(tmp_path):
    """It claimed to be the single validator while picking the G33P reader
    for f64 alone: a probe stream was read as G33R and then held to a
    contract demanding G33P metadata it had never parsed, so a direct call
    refused a VALID member and the primary path only worked because
    members() did the G33R/G33P/_agree dance itself (owner review §9)."""
    src = inspect.getsource(xp.validate_member_stream)
    assert "_agree(g33r, probe, name)" in src, \
        "the probe arm must be read and cross-checked inside the validator"
    assert "pr.read(text)" in src and "ra.read_text(" in src
    # ...and members() no longer keeps a second copy of that sequence
    body = inspect.getsource(xp.members)
    assert "_agree(" not in body and "_require_fixture_domain(" not in body


# --- the geometry rule is PURE, and its limit travels with the bundle (§4) ---

def test_expected_geometry_takes_its_limit_rather_than_reading_one():
    """It read `dtcldcr` from a module global sourced from the working
    tree's private kernel, with a silent 120.0 fallback -- so the same
    historical bundle could get different verdicts on two hosts, and a
    checker whose answer depends on its checkout is not checking a
    content-addressed archive. Measured: at 120 a 300 s / 1 split member is
    (300, 3, 100); at 60 it is (300, 5, 60), and a manifest CLEAN under one
    is refused under the other."""
    assert not hasattr(xp, "DTCLDCR"), "the ambient limit must be gone"
    assert xp.expected_geometry(300.0, 1, "f32", 120.0) == (300.0, 3, 100.0)
    assert xp.expected_geometry(300.0, 1, "f32", 60.0) == (300.0, 5, 60.0)
    with pytest.raises(TypeError):
        xp.expected_geometry(300.0, 1, "f32")       # no default to fall back to


@pytest.mark.skipif(not REF.is_file(),
                    reason="the private kernel source is not on this host")
def test_the_kernel_geometry_record_is_measured_not_assumed():
    """REFUSES rather than defaulting: a silent 120.0 is a number nobody
    measured, and the whole geometry contract is built on it."""
    kg = xp.kernel_geometry("f32")
    assert kg["schema"] == xp.KERNEL_GEOMETRY_SCHEMA
    assert kg["dtcldcr"] == 120.0 and kg["dtcldcr_word"] == "42F00000"
    assert len(kg["source_sha256"]) == 64
    assert xp.kernel_geometry("f64")["dtcldcr_word"] == "405E000000000000"


def test_the_loop_count_rounds_the_quotient_at_the_MEMBERS_width():
    """The kernel forms round_w(delt/dtcldcr) and applies nint to THAT;
    dividing in Python's binary64 and rounding that is a different function
    near a half-integer boundary (owner review §9)."""
    src = inspect.getsource(xp.expected_geometry)
    assert "q = r(delt / limit)" in src
    assert "math.floor(q + 0.5)" in src


@pytest.mark.skipif(not REF.is_file(),
                    reason="the private kernel source is not on this host")
def test_the_kernel_geometry_names_the_source_THIS_algorithm_compiles():
    """The build compiles a different module per algorithm
    (refine_build.sh:54-55), so pinning the legacy one for a conservative
    bundle recorded the digest of a file that run never compiled (Codex)."""
    legacy = xp.kernel_geometry("f32", "legacy")
    cons = xp.kernel_geometry("f32", "conservative")
    assert legacy["source_path"].endswith("module_mp_kdm6.F")
    assert cons["source_path"].endswith("module_mp_kdm6_cons.F")
    assert legacy["source_sha256"] != cons["source_sha256"]
    assert legacy["algorithm"] == "legacy" and cons["algorithm"] == "conservative"
    with pytest.raises(SystemExit, match="no kernel source is known"):
        xp.kernel_geometry("f32", "made-up")


def test_the_run_contract_is_frozen_and_varies_only_the_decomposition():
    """One object, read once, passed down -- and the single axis a
    multi-run leg legitimately varies is the requested tiling."""
    c = xp.RunContract(fixture="fx", columns=3, levels=4, horizon=60.0,
                       dtcldcr=120.0, algorithm="legacy", precision="f32",
                       mode="rezero", rho_profile="as-is", tiles=(3,))
    with pytest.raises(Exception):
        c.dtcldcr = 60.0                      # frozen
    other = c.for_tiles((1, 2))
    assert other.tiles == (1, 2)
    assert other.dtcldcr == c.dtcldcr and other.horizon == c.horizon


# ---- owner review §6: the four witnesses describe ONE build -----------------

# ---- owner review §6: reuse and the evidence chain share one rule ----------

# ---- owner review §11: one authority for which kernel is pinned ------------

def test_an_unknown_algorithm_is_refused_before_anything_is_built(tmp_path):
    """Deriving the module from the algorithm makes an unknown algorithm a
    refusal rather than a KeyError."""
    with pytest.raises(SystemExit, match="no kernel source is known"):
        xp.produce(tmp_path / "x", fixture="g33_fixture_multisubcycle_v1",
                   algo="nonesuch", nsplits=(3,), mode="rezero", nflux=False)


# ---- owner review §8: the bytes that RAN, checked when they run ------------


@pytest.fixture
def _allow_a_dirty_tree_in_tests(monkeypatch):
    """The record carries `+dirty`; nothing refuses a dirty tree any more."""
    return None


# ---- reuse: a directory at the address is adopted only if it IS this run ----

def _sound(tmp_path):
    root = tmp_path / "b"
    root.mkdir()
    exe = b"#!fake\n"
    (root / "g33_refine_driver").write_bytes(exe)
    (root / "n3.rezero.txt").write_text("payload\n")
    rec = xp.res.record(commit="a" * 40, dirty=False,
                        command=["--fixture", "fx"], binary_sha256=hashlib.sha256(exe).hexdigest(),
                        input_sha256="c" * 64,
                        members=[{"file": "n3.rezero.txt",
                                  "sha256": xp.res.sha256(root / "n3.rezero.txt"), "nsplit": 3}],
                        analyses=[])
    xp.res.write(root, rec)
    return root, rec


def test_a_sound_bundle_is_still_reusable(tmp_path):
    """The refusals must not cost the reuse path its reason to exist."""
    root, rec = _sound(tmp_path)
    xp._expect_reusable(root, xp.res.identity(rec))


@pytest.mark.parametrize("damage,reason", [
    (lambda r: (r / "result.json").unlink(), "no result.json"),
    (lambda r: (r / "result.json").write_text("{not json"), "will not parse"),
    (lambda r: (r / "n3.rezero.txt").write_text("edited\n"), "MISMATCH"),
    (lambda r: (r / "n3.rezero.txt").unlink(), "absent"),
    (lambda r: (r / "g33_refine_driver").write_bytes(b"other"), "g33_refine_driver"),
])
def test_a_DAMAGED_existing_bundle_is_refused_not_republished(tmp_path, damage, reason):
    root, rec = _sound(tmp_path)
    damage(root)
    with pytest.raises(SystemExit) as e:
        xp._expect_reusable(root, xp.res.identity(rec))
    assert reason in str(e.value)


# ---- what the record says about the run ----

def test_the_record_carries_the_density_arm_and_the_instrumentation(tmp_path, monkeypatch):
    _fake(monkeypatch)
    dest = _produce(tmp_path / "chain", nflux=True, rho_profile="uniform")
    rec = xp.res.load(dest)
    assert "--nflux" in rec["command"]
    i = rec["command"].index("--rho-profile")
    assert rec["command"][i + 1] == "uniform"


def test_the_analyses_are_only_produced_for_instrumented_bundles(tmp_path, monkeypatch):
    _fake(monkeypatch)
    plain = xp.res.load(_produce(tmp_path / "plain", nflux=False))
    assert plain["result"]["analyses"] == []
    inst = xp.res.load(_produce(tmp_path / "inst", nflux=True))
    assert {a["analysis"] for a in inst["result"]["analyses"]} >= set(xp.res.REQUIRED_WHEN_INSTRUMENTED)


def test_a_nonstandard_module_is_named_in_the_command(tmp_path, monkeypatch):
    _fake(monkeypatch)
    other = tmp_path / "other.F"
    other.write_text("x\n")
    dest = xp.produce(tmp_path / "chain", fixture="g33_fixture_multisubcycle_v1",
                      algo="legacy", nsplits=(3, 6), mode="rezero", nflux=False, module=other)
    assert "--module-override" in xp.res.load(dest)["command"]


def test_a_bundle_at_the_address_that_identifies_as_another_run_is_refused(tmp_path):
    root, rec = _sound(tmp_path)
    with pytest.raises(SystemExit) as e:
        xp._expect_reusable(root, "0" * 64)
    assert "identifies as" in str(e.value)
