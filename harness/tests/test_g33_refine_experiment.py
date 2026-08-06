"""A bundle is produced whole or not at all (owner priority-2).

The bundles used to be assembled by hand — one step built and wrote provenance,
another ran the driver, a third stitched a manifest — so nothing structurally
prevented provenance from one build being published beside members from another.
These tests hold the replacement to that: fail-closed at every stage, and visible
under the destination only after everything succeeded.
"""
import json
import re
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
    def build(workdir, fixture, algo, nflux, arm="reference"):
        if fail_at == "build":
            raise SystemExit("build failed")
        (workdir / "build_provenance.json").write_text(json.dumps({
            "module_sha256": xp.rm.sha256(MOD), "fixture_sha256": xp.rm.sha256(FIX),
            "sources": [], "executable_sha256": "ab" * 32}))
        return workdir / "driver"

    def members(exe, out, ns, mode, *, arm="reference", nflux=False,
                rho_profile="as-is", width=3):
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
    # about is the producer's atomicity and its manifest.
    monkeypatch.setattr(xp, "_analyses", lambda *a, **k: [])
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
            rho_profile="as-is", width=3):
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


def test_the_f64_arm_is_bound_into_the_manifest_and_is_never_decision_evidence(
        tmp_path, monkeypatch):
    """An f64 member is an INSTRUMENT. The artifact must say so, not only the
    prose around it (owner priority 2)."""
    def build(workdir, fixture, algo, nflux, arm="reference"):
        assert arm == "f64"
        (workdir / "build_provenance.json").write_text(json.dumps({
            "module_sha256": xp.rm.sha256(MOD), "fixture_sha256": xp.rm.sha256(FIX),
            "sources": [], "executable_sha256": "cd" * 32}))
        return workdir / "driver"

    def probe_members(exe, out, ns, mode, rho_profile="as-is", width=3):
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
    with pytest.raises(xp.pr.ProbeError, match="is missing"):
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
    src = (ROOT.parent / "harness/g33_refine_experiment.py").read_text()
    assert 'man["analyses"] = _analyses(tmp, exe, nsplits, mode) if nflux else []' \
        in src


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

    def fake(exe, n, chain="main", *, mode, width, baseline_stream=None,
             keep=None):
        seen.update(exe=exe, n=n, mode=mode, width=width,
                    baseline=baseline_stream)
        if keep is not None:
            keep["as-is"] = "x"
        return {"arms": {}}

    monkeypatch.setattr(xp.mtj, "analysis", fake)
    (tmp_path / "n7.carry.txt").write_text("member-bytes\n")
    xp._driver_analyses(tmp_path, Path("drv"), [7], "carry", 5)
    assert seen["mode"] == "carry", "the bundle's mode must be inherited"
    assert seen["width"] == 5, "the fixture width must be inherited"
    assert seen["baseline"] == "member-bytes\n", \
        "the baseline must be the bundle's stored member, not a re-run"


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
                        lambda out, exe, ns, mode, width: seen.update(
                            mode=mode, width=width) or [])
    monkeypatch.setattr(xp, "fixture_width", lambda fixture: 5)
    xp.produce(tmp_path / "bundle", fixture="g33_fixture_multisubcycle_v1",
               algo="legacy", nsplits=(3, 6), mode="carry", nflux=True,
               module=MOD)
    assert seen == {"mode": "carry", "width": 5}, (
        "produce() must hand the analysis the bundle's OWN mode and fixture "
        f"width, got {seen}")


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
    monkeypatch.setattr(xp, "require_pinned_producer", lambda: None)


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
        <= set(xp.PRODUCER_MODULES)
