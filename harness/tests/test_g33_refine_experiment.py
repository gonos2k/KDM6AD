"""A bundle is produced whole or not at all (owner priority-2).

The bundles used to be assembled by hand — one step built and wrote provenance,
another ran the driver, a third stitched a manifest — so nothing structurally
prevented provenance from one build being published beside members from another.
These tests hold the replacement to that: fail-closed at every stage, and visible
under the destination only after everything succeeded.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
REF = REPO / 'host' / 'KIM-meso_v1.0' / 'phys' / 'module_mp_kdm6.F'
sys.path.insert(0, str(ROOT))
import g33_refine_experiment as xp  # noqa: E402
import g33_refine_manifest as rm  # noqa: E402

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
        (workdir / "commands.txt").write_text("fake\n")
        (workdir / "sources.txt").write_text("fake\n")
        (workdir / "build_provenance.json").write_text(json.dumps({
            "module_sha256": xp.rm.sha256(MOD), "fixture_sha256": xp.rm.sha256(FIX),
            "sources": [], "executable_sha256": xp.rm.sha256(exe)}))
        return workdir / "driver"

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
        out_entries = []
        for kind in xp.rm.REQUIRED_WHEN_INSTRUMENTED:
            p = out / f"n{ns[0]}.{mode}.{kind}.json"
            p.write_text("{}\n")
            out_entries.append({
                "file": p.name, "nsplit": ns[0], "analysis": kind,
                "sha256": xp.rm.sha256(p),
                **xp._analyzer_pin(xp.ANALYSES[kind][0])})
        return out_entries

    def members(exe, out, ns, mode, *, arm="reference", nflux=False,
                rho_profile="as-is", width=3, levels=None):
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

    def bad(exe, out, ns, mode, *, arm="reference", nflux=False,
            rho_profile="as-is", width=3, levels=None):
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


def test_the_f64_arm_is_bound_into_the_manifest_and_is_never_decision_evidence(
        tmp_path, monkeypatch):
    """An f64 member is an INSTRUMENT. The artifact must say so, not only the
    prose around it (owner priority 2)."""
    def build(workdir, fixture, algo, nflux, arm="reference"):
        assert arm == "f64"
        # The BINARY is published in the bundle and v2 pins it, so the fake
        # build must leave one where a real build would -- and declare the
        # digest OF THAT FILE. Stubbing a different one made the fixture
        # describe a binary it had not written, which the manifest's
        # build_artifacts/build_provenance cross-check now refuses (owner §8.4).
        exe = workdir / "g33_refine_driver"
        exe.write_text("#!fake\n")
        (workdir / "commands.txt").write_text("fake\n")
        (workdir / "sources.txt").write_text("fake\n")
        (workdir / "build_provenance.json").write_text(json.dumps({
            "module_sha256": xp.rm.sha256(MOD), "fixture_sha256": xp.rm.sha256(FIX),
            "sources": [], "executable_sha256": xp.rm.sha256(exe)}))
        return workdir / "driver"

    def probe_members(exe, out, ns, mode, rho_profile="as-is", width=3,
                      levels=None, nflux=False):
        runs = {}
        for n in ns:
            p = out / f"n{n}.{mode}.txt"
            p.write_text(_probe_stream(n))
            runs[n] = xp.pr.read(p.read_text())
        return runs

    monkeypatch.setattr(xp, "build", build)
    monkeypatch.setattr(xp, "probe_members", probe_members)
    monkeypatch.setattr(xp, "_run", lambda cmd, **kw: "gfortran (fake) 1.0\n")
    dest = xp.produce(tmp_path / "b", fixture="g33_fixture_multisubcycle_v1",
                      algo="legacy", nsplits=(3, 6), mode="rezero", nflux=False,
                      module=MOD, arm="f64")
    man = json.loads((dest / "manifest.json").read_text())
    assert man["arm"] == "f64" and man["precision"] == "f64"
    assert man["decision_eligible"] is False
    assert [m["precision"] for m in man["members"]] == ["f64", "f64"]


def _probe_stream(nsplit=3):
    """A COMPLETE probe stream: the reader now requires the exact
    field x cell universe plus INITIAL, all three forcings and PREC, because
    'absent' silently disabled every check (owner §7.2)."""
    out = [f"G33P BEGIN 4 precision f64 source_precision f32 fixture fx "
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


def test_the_manifest_records_the_parser_that_APPROVED_the_members(
        tmp_path, monkeypatch):
    """It recorded g33_refine_analyze.py even for an f64 arm, whose members are
    read by the probe parser (owner §10.2)."""
    _fake(monkeypatch)
    dest = _produce(tmp_path / "b")
    got = [q["path"] for q in
           json.loads((dest / "manifest.json").read_text())["member_parsers"]]
    assert got == ["harness/g33_refine_analyze.py"]


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


def test_the_analyses_are_only_produced_for_instrumented_bundles():
    """All three read extension records, which a non-nflux stream does not carry;
    running them anyway would put an empty analysis in the manifest and make an
    uninstrumented bundle look analysed."""
    # Whitespace-normalised: the guard is the contract, not where the line
    # happens to wrap.
    src = " ".join((ROOT.parent
                    / "harness/g33_refine_experiment.py").read_text().split())
    assert ('man["analyses"] = (_analyses(tmp, exe, nsplits, mode, precision) '
            'if nflux else [])') in src


def test_each_analysis_records_the_ANALYZER_digest_beside_its_own():
    """An analysis JSON identifies what was concluded; the module identifies the
    code that concluded it. With only the first, a reader can check the table has
    not changed but cannot re-derive it (owner §14-4)."""
    src = (ROOT.parent / "harness/g33_refine_experiment.py").read_text()
    assert '"analyzer_sha256"' in src and '"sha256": rm.sha256(path)' in src


def test_the_evidence_chain_follows_the_manifest_to_the_ANALYSES():
    """Pinning a manifest that reaches the raw streams but not the analyses stops
    one step short of the numbers a claim actually quotes."""
    src = (ROOT.parent / "harness/g33_evidence_chain.py").read_text()
    assert 'man.get("analyses", [])' in src


# ---- owner §5.2: the bundle must say which forcing arm it is ------------------

def test_the_manifest_records_the_density_arm_and_the_exact_command_line():
    """The density arms were run by hand, outside the producer, so a published
    bundle recorded what was BUILT and RUN but not what experiment it was an arm
    of. A reader could not tell an `as-is` bundle from a `uniform` one."""
    src = (ROOT / "g33_refine_experiment.py").read_text()
    assert 'man["rho_profile"] = rho_profile' in src
    assert 'man["runtime_argv"]' in src
    assert '"--rho-profile"' in src


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

def test_the_driver_analysis_takes_mode_and_width_from_the_BUNDLE(tmp_path,
                                                                  monkeypatch):
    """Hardcoded `rezero` and tile `3` meant a --mode carry bundle shipped a
    metric_trajectory.json silently generated under rezero, inside a manifest
    whose members were carry; and a fixture that is not three columns wide failed
    the driver's tile-sum check (owner P0-2).

    Asserted BEHAVIOURALLY: the first version grepped for a literal call string
    and broke the moment two keyword arguments were added — the same brittleness
    as matching prose by substring. What matters is what `_driver_analyses`
    PASSES, so that is what is captured."""
    seen = {}

    def fake_collect(driver, n, *, mode, width, baseline_stream=None):
        seen.update(n=n, mode=mode, width=width, baseline=baseline_stream)
        return {"as-is": baseline_stream}

    def fake(exe, n, chain="main", *, mode, width, baseline_stream=None,
             keep=None, raw=None):
        seen.update(raw=raw)
        return {"arms": {}}

    import g33_metric_trajectory as mtj
    monkeypatch.setattr(mtj, "analysis", fake)
    monkeypatch.setattr(xp.rmx, "collect", fake_collect)
    (tmp_path / "n7.carry.txt").write_text("member-bytes\n")
    xp._driver_analyses(tmp_path, Path("drv"), [7], "carry", 5, 4)
    assert seen["mode"] == "carry", "the bundle's mode must be inherited"
    assert seen["width"] == 5, "the fixture width must be inherited"
    assert seen["baseline"] == "member-bytes\n", \
        "the baseline must be the bundle's stored member, not a re-run"
    assert seen["raw"] == {"as-is": "member-bytes\n"}, \
        "the analysis must receive the run side's collected streams"


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
                        lambda out, exe, ns, mode, width, levels: seen.update(
                            mode=mode, width=width, levels=levels) or [])
    monkeypatch.setattr(xp, "fixture_width", lambda fixture: 5)
    xp.produce(tmp_path / "bundle", fixture="g33_fixture_multisubcycle_v1",
               algo="legacy", nsplits=(3, 6), mode="carry", nflux=True,
               module=MOD)
    assert seen == {"mode": "carry", "width": 5, "levels": 4}, (
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


# ---- owner §8.1 / §16-6: the finding's analysis list is CHECKED against code --

FINDING = ROOT / "evidence" / "FINDING_bundle_analyses_v1.md"


def test_the_finding_lists_every_analysis_the_code_registers():
    """The finding said "three analyses" and named three while the registry had
    grown to five plus a bundle-level one — a document describing a superseded
    implementation, which the digest pin and the status stamp both pass.

    This is the cheapest useful prose-to-code check: the names in the finding's
    generated block must be exactly the names the producer registers. It does not
    verify the prose is *right*, only that it is not describing code that no
    longer exists — which is the failure that actually keeps happening.
    """
    block = re.search(r"<!-- analyses:.*?-->(.*?)<!-- /analyses -->",
                      FINDING.read_text(), re.S)
    assert block, "the generated analyses block is missing"
    listed = set(re.findall(r"^\| `([a-z_]+)` \|", block.group(1), re.M))
    registered = set(xp.ANALYSES) | {"metric_trajectory"}
    assert listed == registered, (
        f"finding lists {sorted(listed)}, code registers {sorted(registered)}")


def test_the_bundle_level_analysis_is_named_as_such():
    """`metric_trajectory` re-runs the driver under six arms; it is not a
    per-member stream analysis and the finding must not imply it is."""
    block = re.search(r"<!-- analyses:.*?-->(.*?)<!-- /analyses -->",
                      FINDING.read_text(), re.S).group(1)
    row = next(l for l in block.splitlines() if "`metric_trajectory`" in l)
    assert "bundle" in row and "per member" not in row


def test_a_GENERATOR_of_nsplits_does_not_publish_an_empty_bundle(tmp_path,
                                                                 monkeypatch):
    """`nsplits` is walked six times -- the duplicate check, the member loop, the
    analyses, the arm streams. A generator is exhausted by the first walk and
    every later one sees nothing, so the bundle publishes with zero members, no
    error, and a manifest that looks complete. It is materialised on entry."""
    seen = {}

    def fake_build(workdir, *a, **k):
        workdir.mkdir(parents=True, exist_ok=True)
        exe = workdir / "g33_refine_driver"
        exe.touch()
        return exe

    def fake_members(exe, out, nsplits, mode, **k):
        seen["n"] = list(nsplits)
        raise SystemExit("stop after the member loop")

    monkeypatch.setattr(xp, "build", fake_build)
    monkeypatch.setattr(xp, "members", fake_members)
    with pytest.raises(SystemExit):
        xp.produce(tmp_path / "b", fixture="g33_fixture_multisubcycle_v1",
                   algo="legacy", nsplits=(n for n in (3, 6, 12)),
                   mode="rezero", nflux=False, module=tmp_path / "m.F")
    assert seen["n"] == [3, 6, 12], \
        "the member loop saw an exhausted generator"


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
_REAL_PIN_CHECK = xp.require_pinned_producer


@pytest.fixture(autouse=True)
def _allow_a_dirty_tree_in_tests(monkeypatch):
    monkeypatch.setattr(xp, "require_pinned_producer", lambda *a, **k: None)


def test_the_producer_refuses_when_a_running_module_is_UNCOMMITTED(monkeypatch):
    """The claim said "the producer refuses a dirty tree, so HEAD:path is the
    bytes that ran". No such refusal existed -- `tree_dirty` was RECORDED. An
    uncommitted analyzer edit therefore ran while the manifest pinned the
    committed blob, and the checker, which resolves that blob, passed."""
    real = xp.rm._git

    def edited(*a):
        if a[:1] == ("hash-object",) and "g33_cap_interface" in str(a[-1]):
            return "0" * 40
        return real(*a)

    monkeypatch.setattr(xp.rm, "_git", edited)
    with pytest.raises(SystemExit, match="did not run"):
        _REAL_PIN_CHECK()


def test_a_producer_whose_bytes_MATCH_is_accepted(monkeypatch):
    """A refusal that fired unconditionally would also pass the test above.
    Forced to match rather than read off the tree, so the result does not depend
    on whether this checkout happens to be clean."""
    monkeypatch.setattr(xp.rm, "_git", lambda *a: "b" * 40)
    _REAL_PIN_CHECK()


def test_a_module_missing_from_HEAD_is_refused(monkeypatch):
    """A new analyzer that was never committed pins nothing at all."""
    real = xp.rm._git
    monkeypatch.setattr(xp.rm, "_git", lambda *a: (
        "" if a[:1] == ("rev-parse",) and "g33_dual_ledger" in str(a[-1])
        else real(*a)))
    with pytest.raises(SystemExit, match="not in HEAD"):
        _REAL_PIN_CHECK()


def test_the_PARSERS_are_pinned_by_commit_and_blob_like_the_analyzers():
    """An analysis is only as good as the stream its parser admitted, so a
    parser recorded by content digest alone was checkable against today's
    working tree and nothing else (owner P0-2)."""
    pin = xp._pin("g33_number_transport")
    assert set(pin) == {"path", "content_sha256", "commit", "blob_sha"}
    assert len(pin["blob_sha"]) == 40 and len(pin["content_sha256"]) == 64
    # The strict parsers must be in the pinned set, not only the analyzers.
    assert {"g33_refine_analyze", "g33_number_transport", "g33_probe_read"} \
        <= set(xp.producer_modules())
    # DERIVED, not hand-listed: an analyzer added to ANALYSES and forgotten in a
    # tuple escaped the byte binding entirely (owner §9.2).
    assert all(mod in xp.producer_modules() for mod, _fn in xp.ANALYSES.values())


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


def test_the_producer_writes_the_STRICT_schema():
    """A bundle made today must declare the contract it satisfies, or the
    checker cannot tell it from one that predates the pin blocks."""
    assert xp.rm.SCHEMA == "refinement_experiment_v3"


# ---- owner §9.1: an existing bundle directory is verified, not adopted -------

def test_an_identical_rerun_REUSES_the_bundle(tmp_path, monkeypatch):
    """Content-addressed: the same manifest is the same bundle, and rebuilding
    it would delete the directory `dest` points at."""
    _fake(monkeypatch)
    a = _produce(tmp_path / "b").resolve()
    b = _produce(tmp_path / "b").resolve()
    assert a == b
    assert len(list((tmp_path / "b.bundles").iterdir())) == 1


@pytest.mark.parametrize("damage", ["manifest-gone", "manifest-corrupt",
                                    "member-gone", "member-edited",
                                    "identity-mismatch"])
def test_a_DAMAGED_existing_bundle_is_refused_not_republished(tmp_path,
                                                              monkeypatch,
                                                              damage):
    """The address alone was the whole check, so a directory left by an
    interrupted run -- or edited by hand -- was republished under a digest it no
    longer matched (owner §9.1)."""
    _fake(monkeypatch)
    final = _produce(tmp_path / "b").resolve()
    mf = final / "manifest.json"
    if damage == "manifest-gone":
        mf.unlink()
    elif damage == "manifest-corrupt":
        mf.write_text("{not json")
    elif damage == "identity-mismatch":
        man = json.loads(mf.read_text())
        man["arm"] = "probe"                      # changes the identity
        mf.write_text(json.dumps(man))
    else:
        member = next(p for p in final.glob("n*.rezero.txt"))
        member.unlink() if damage == "member-gone" else \
            member.write_text("tampered\n")

    with pytest.raises(SystemExit, match="REFUSED"):
        _produce(tmp_path / "b")


def test_the_TRACKED_BUILD_INPUTS_are_pinned_by_commit_and_blob():
    """They decide the raw streams as surely as the analyzers decide the
    numbers, and build_provenance recorded only content digests -- checkable
    against today's working tree and nothing else (owner §9.2)."""
    for q in xp.TRACKED_BUILD_INPUTS:
        pin = xp._pin_path(q)
        assert set(pin) == {"path", "content_sha256", "commit", "blob_sha"}
        assert len(pin["blob_sha"]) == 40 and len(pin["commit"]) == 40
    names = {str(q) for q in xp.TRACKED_BUILD_INPUTS}
    assert "harness/g33_fortran/refine_build.sh" in names
    assert "harness/g33_fortran/g33_refine_driver.f90" in names
    assert not any("host/" in n for n in names), \
        "host/** is gitignored, so no commit holds it -- it stays content-only"


# ---- owner P0-1 / P0-2: the fixture, and pins that cannot lie ---------------

def test_an_UNCOMMITTED_selected_fixture_is_refused(monkeypatch):
    """The selected fixture is compiled from the working tree but was absent
    from the fixed `TRACKED_BUILD_INPUTS` tuple, so an uncommitted fixture
    published a bundle whose `content_sha256` (what ran) and `blob_sha` (what is
    recoverable) named different files -- and nothing failed (owner P0-1)."""
    real = xp.rm._git
    fx = "harness/g33_fortran/g33_fixture_multisubcycle_v1.f90"

    def edited(*a):
        if a[:1] == ("hash-object",) and "multisubcycle" in str(a[-1]):
            return "0" * 40
        return real(*a)

    monkeypatch.setattr(xp.rm, "_git", edited)
    with pytest.raises(SystemExit, match="did not run"):
        _REAL_PIN_CHECK("g33_fixture_multisubcycle_v1")
    # ...and the same tree passes when the fixture is not named.
    _REAL_PIN_CHECK()


def test_a_pin_REFUSES_to_be_built_when_content_and_blob_disagree(monkeypatch):
    """`content_sha256` records what RAN and `blob_sha` names what is
    RECOVERABLE. A pin whose two halves describe different files is a lie the
    checker cannot see, because resolving the blob succeeds either way. It is
    refused at construction rather than listed somewhere to remember."""
    real = xp.rm.sha256
    monkeypatch.setattr(xp.rm, "sha256", lambda p: "0" * 64)
    with pytest.raises(SystemExit, match="did not run"):
        xp._pin_path(Path("harness/g33_matched_closure.py"))
    monkeypatch.setattr(xp.rm, "sha256", real)
    xp._pin_path(Path("harness/g33_matched_closure.py"))     # consistent again


def test_the_BINARY_that_produced_the_numbers_is_pinned():
    """The finding said the driver "is not published in the bundle". It is:
    `os.rename(tmp, final)` moves the whole build directory, and the 320 kB
    executable sits there. Nothing verified it, so deleting or editing it left
    the bundle reusable (owner §7)."""
    import json
    b = Path.home() / "kdm6ad-g33m-migrate" / "number-003"
    if not (b / "manifest.json").is_file():
        pytest.skip("the migration bundle is not on this host")
    man = json.loads((b / "manifest.json").read_text())
    files = {a["file"] for a in man["build_artifacts"]}
    assert "g33_refine_driver" in files
    assert {"build_provenance.json", "commands.txt", "sources.txt"} <= files
    assert (b / "g33_refine_driver").is_file()


# ---- the pinned module list must be COMPLETE, not remembered ---------------

def test_every_module_the_producer_can_REACH_is_PINNED():
    """`producer_modules()` was a union of three hand-written tuples. Nothing
    failed when it drifted, so a producer that started importing a new module
    shipped bundles whose provenance silently omitted it -- the one list the
    binding depends on being the one nobody checked, one layer up from where
    owner §9.2 found it the first time.

    Compared over PATHS: a file can be pinned as a module OR as a build input,
    and those namespaces overlap only by accident."""
    missing = xp.unpinned_reachable()
    assert not missing, (
        f"reachable from the producer but pinned by NOTHING: {sorted(missing)}")


def test_the_completeness_check_CATCHES_a_new_import(monkeypatch):
    """A check that cannot fail is not a check."""
    real = xp._local_imports

    def with_extra(module):
        got = real(module)
        return got | {"g33_evidence_chain"} if module == "g33_refine_experiment" \
            else got

    monkeypatch.setattr(xp, "_local_imports", with_extra)
    assert "g33_evidence_chain" in xp.reachable_modules()
    assert "g33_evidence_chain" in xp.unpinned_reachable()


def test_a_SUBPROCESS_module_is_reachable_though_NOTHING_imports_it():
    """`g33_build_provenance` is executed by the build script and imported by
    no one, so an import closure alone would miss it entirely -- and it writes
    the provenance the whole chain rests on."""
    assert "g33_build_provenance" in xp._build_script_modules()
    assert "g33_build_provenance" not in xp._local_imports("g33_refine_experiment")
    assert "g33_build_provenance" in xp.reachable_modules()


def test_the_closure_runs_THROUGH_a_subprocess_module():
    """Unioning the subprocess modules in at the END left everything THEY
    import outside the closure. `make_fortran_overlay` generates the
    instrumentation injected into the frozen Fortran, so what it imports
    decides what every record in the stream says -- and `g33_schema` and
    `g33_expectation` reached only through it were pinned by nothing (Codex)."""
    assert "make_fortran_overlay" in xp._build_script_modules()
    assert "g33_schema" in xp._local_imports("make_fortran_overlay")
    for m in ("g33_schema", "g33_expectation"):
        assert m in xp.reachable_modules(), f"{m} must be in the closure"
        assert m not in xp.unpinned_reachable(), f"{m} must be pinned"


def test_a_module_in_the_g33_fortran_SUBDIRECTORY_is_resolvable():
    """The resolver looked only in harness/, so `make_fortran_overlay` -- which
    lives in harness/g33_fortran/ -- failed the is_file() test and was dropped
    silently, taking the entire overlay generator out of the closure."""
    assert xp._module_file("make_fortran_overlay") is not None
    assert xp._module_file("g33_refine_analyze") is not None
    assert xp._module_file("no_such_module_anywhere") is None


def test_a_script_named_only_in_a_COMMENT_is_not_a_script_that_runs():
    """Why this is a CHECK and not a derivation. `fortran_build.sh` appears in
    refine_build.sh only inside comments; a text scan pulls it in, and a list
    derived that way would be less trustworthy than the curated one."""
    sh = (Path(xp.HERE) / "g33_fortran" / "refine_build.sh").read_text()
    assert "fortran_build.sh" in sh, "the comment case must still exist"
    code = [l for l in sh.splitlines() if not l.lstrip().startswith("#")]
    assert not [l for l in code if "fortran_build.sh" in l]
    assert "fortran_build" not in xp._build_script_modules()


# ---- content identity must survive a REAL rebuild (owner P0-1) -------------

@pytest.mark.skipif(shutil.which("gfortran") is None or not REF.is_file(),
                    reason="local-only (needs gfortran + the host tree)")
def test_TWO_REAL_BUILDS_of_the_same_experiment_share_one_identity(tmp_path):
    """The regression the owner asked for by name: two real Fortran builds, not
    fake provenance.

    `identity_digest` stripped `diagnostic` KEYS inside the manifest, but
    `build_artifacts[].sha256` is a plain string holding the RAW digest of files
    that embed the output directory -- a fresh temporary path every run. So two
    identical experiments produced different addresses, and "an identical rerun
    reuses the bundle" could only ever hold under fake provenance, which is the
    one property a content address exists to provide (owner P0-1).

    Measured before the fix: the stripped manifests differed in exactly two
    fields, `build_provenance.json` and `commands.txt`, and in nothing else --
    `g33_refine_driver` was byte-identical."""
    ids = []
    for name in ("A", "B"):
        out = tmp_path / name
        r = subprocess.run([sys.executable, str(ROOT / "g33_refine_experiment.py"),
                            str(out), "--nsplit", "12", "--nflux"],
                           capture_output=True, text=True, cwd=REPO)
        assert r.returncode == 0, f"{name} failed:\n{r.stdout}\n{r.stderr}"
        store = sorted((tmp_path / f"{name}.bundles").iterdir())
        assert len(store) == 1, [p.name for p in store]
        ids.append(store[0].name)

    assert ids[0] == ids[1], (
        f"the same experiment built in two directories got two addresses:\n"
        f"  {ids[0]}\n  {ids[1]}")
    assert len(ids[0]) == 64, "the address must stay a full digest"


def test_the_LOCATION_DEPENDENT_artifacts_are_named_not_guessed():
    """Which artifacts are payload-only is a RULE in the manifest module, not a
    flag the producer sets per entry -- otherwise a producer could opt anything
    out of identity. Their integrity is unaffected: the evidence chain verifies
    every build_artifacts digest either way."""
    assert rm.LOCATION_DEPENDENT_ARTIFACTS == {"build_provenance.json",
                                               "commands.txt"}
    assert "g33_refine_driver" not in rm.LOCATION_DEPENDENT_ARTIFACTS, \
        "the binary that ran is the anchor -- it must stay in identity"
    assert "sources.txt" not in rm.LOCATION_DEPENDENT_ARTIFACTS, \
        "sources.txt holds repo-relative paths and was measured stable"


def test_identity_ignores_a_payload_digest_but_NOT_the_binary():
    """Both directions, so the strip cannot quietly widen."""
    base = {"schema": "x", "build_artifacts": [
        {"file": "g33_refine_driver", "sha256": "a" * 64},
        {"file": "commands.txt", "sha256": "b" * 64}]}
    moved = {"schema": "x", "build_artifacts": [
        {"file": "g33_refine_driver", "sha256": "a" * 64},
        {"file": "commands.txt", "sha256": "c" * 64}]}
    rebuilt = {"schema": "x", "build_artifacts": [
        {"file": "g33_refine_driver", "sha256": "d" * 64},
        {"file": "commands.txt", "sha256": "b" * 64}]}
    assert rm.identity_digest(base) == rm.identity_digest(moved)
    assert rm.identity_digest(base) != rm.identity_digest(rebuilt)


def test_an_UNRELATED_dirty_file_does_not_change_the_experiment():
    """The producer REFUSES when any byte that will run differs from HEAD, so a
    dirty tree can only mean unrelated files changed. Letting an edited README
    move the address contradicts the producer's own rule for what makes a run
    the same run (owner P0-1)."""
    clean = {"schema": "x", "tree_dirty": False, "build_provenance": {}}
    dirty = {"schema": "x", "tree_dirty": True, "build_provenance": {}}
    assert rm.identity_digest(clean) == rm.identity_digest(dirty)


def test_MULTI_RUN_analyzers_are_in_the_PIN_closure():
    """A multi-run analyzer decides what a bundle contains exactly as a
    per-member one does, so it must be pinned the same way. The first version
    hardcoded `_analyzer_pin("g33_ncmin_locality")` inside the builder, which
    put the analyzer's bytes into a bundle while leaving the module out of
    `producer_modules()` -- `unpinned_reachable()` caught it, which is what
    that check exists for (Codex)."""
    mods = {m for m, _fn in xp.MULTI_RUN.values()}
    assert mods, "no multi-run analysis registered -- this check would be vacuous"
    assert mods <= set(xp.producer_modules())
    assert not xp.unpinned_reachable()


def test_the_two_MULTI_RUN_registries_agree():
    """The producer says which analyses exist; the schema says which are
    valid. Declared in both because the producer imports the manifest module,
    so drift has to be a failure rather than a silently widened union."""
    assert tuple(xp.MULTI_RUN) == rm.MULTI_RUN_ANALYSES


def test_a_multi_run_analyzer_is_DERIVED_not_hardcoded():
    """From the registry, so adding one cannot repeat the omission."""
    src = (ROOT / "g33_refine_experiment.py").read_text()
    body = src[src.index("def _multi_run_analyses("):]
    body = body[:body.index("\ndef ", 1)]
    assert "_analyzer_pin(mod)" in body
    assert '_analyzer_pin("' not in body, "a hardcoded analyzer name came back"


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


def test_the_producer_gates_publication_on_the_RESOLVED_graph():
    """`rm.validate` is shape; `graph_violations` reads the pinned blobs. Only
    the second can see a graph that disagrees with the code, and it ran only
    AFTER publication -- so a regression in `identity_block()` would publish a
    structurally-valid bundle and be discovered by whoever read it later
    (owner review §4). Source-level: the producer must call both, and must
    treat an unresolvable blob as refusal, not absence."""
    src = " ".join((ROOT.parent / "harness/g33_refine_experiment.py")
                   .read_text().split())
    assert "violations += rm.graph_violations(man)" in src
    assert "except rm.BlobUnavailable" in src
    assert src.index("graph_violations(man)") < src.index(
        '(tmp / "manifest.json").write_text'), \
        "the resolved check must run BEFORE the manifest is written"


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
    run[("forcing", "rho", 2, 1)] = 1.0 * (1 + 1e-12)
    with pytest.raises(xp.ra.RefineError, match="two different runs"):
        xp._require_fixture_domain(_domain_text(), "n1.rezero.txt", 1,
                                   "rezero", "as-is", 3, 4, run)
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
    text = _ns(_nc(1, cols=(1, 2, 3), ks=4).replace("42C80000", hex32, 1))
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
    text = _ns(_nc(1, cols=(1, 2, 3), ks=4).replace("42C80000", hex32, 1))
    run = _samerun_window()
    run[("meta", "delt")] = 42.85714250
    with pytest.raises(xp.ra.RefineError, match="more precision than the F0.6"):
        xp._require_fixture_domain(text, "n7.rezero.txt", 1, "rezero",
                                   "as-is", 3, 4, run)
    run[("meta", "delt")] = float("nan")
    with pytest.raises(xp.ra.RefineError, match="more precision than the F0.6"):
        xp._require_fixture_domain(text, "n7.rezero.txt", 1, "rezero",
                                   "as-is", 3, 4, run)
