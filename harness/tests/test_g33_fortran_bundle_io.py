"""Fortran leg attestation (public CI — no build).

The gate used to take the Fortran legs as raw `.g33f` paths. Parsing, semantics and
replay are all INTERNAL properties of the text: none of them ties a stream to the
compiler that produced it, the source it was built from, or the fixture it claims. So
`attested: true` described the C++ side only. These tests pin the bundle contract that
closes that, and are built on a synthetic bundle so they need no gfortran.
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "harness" / "g33_fortran"))
import g33_fixture_v1 as gfx                # noqa: E402
import g33_fortran_bundle_io as fbio        # noqa: E402
import g33_fortran_dump as fd               # noqa: E402

SAMPLE = Path(__file__).parent / "data" / "g33_legacy_sample.g33f"
COMMIT = "c" * 40


def _noninstrumented(raw: bytes) -> bytes:
    """What lanes A and B emit: the same inputs/state/precip, no MSTEP/OP/STAGE.

    A and B are non-instrumented runs, so their bytes differ from C by construction —
    that difference IS the instrumentation. Non-invasiveness is final state + precip
    equality, never byte equality.
    """
    drop = (b"G33FOP", b"G33F MSTEP", b"G33F STAGE")
    return b"\n".join(line for line in raw.split(b"\n")
                      if not any(line.startswith(d) for d in drop))


def _provenance(exe_bytes: bytes, *, canonical=True, compiler="f" * 64,
                version="GNU Fortran 13.2.0", host_sha=None) -> dict:
    """A real build record for one lane."""
    module = "m" * 64 if canonical else "n" * 64
    return {
        "schema_version": 2,
        "algorithm": "legacy",
        "dump_instrumented": not canonical,
        "host_source_sha256": host_sha or {"module_mp_kdm6.F": "h" * 64},
        "harness_source_sha256": {"g33_fortran_driver.f90": "j" * 64},
        "module_compiled_sha256": module,
        "module_canonical_sha256": "m" * 64,
        "executable_sha256": hashlib.sha256(exe_bytes).hexdigest(),
        "compiler_path": "/usr/bin/gfortran",
        "compiler_binary_sha256": compiler,
        "compiler_version": version,
        "commands": ["gfortran -c ..."],
    }


def _bundle(root: Path, *, dirty=False, algo="legacy", lane_edit=None,
            manifest_edit=None, prov_edit=None) -> Path:
    """A full bundle around the CHECKED-IN sample: real streams, real provenance,
    real executables. Everything the verifier claims to check must EXIST here, or the
    tests certify that unverified provenance is acceptable."""
    _, authority = gfx.load_fixture(gfx.DEFAULT_FIXTURE_ID)
    raw = SAMPLE.read_bytes()
    plain = _noninstrumented(raw)
    root.mkdir(parents=True, exist_ok=True)
    stdout_sha, stderr_sha, exe_sha, prov_sha = {}, {}, {}, {}
    for lane in ("A", "B", "C"):
        d = root / lane
        d.mkdir()
        base = raw if lane == "C" else plain
        data = lane_edit(lane, base) if lane_edit else base
        (d / "stdout.g33f").write_bytes(data)
        (d / "stderr.txt").write_bytes(b"")
        exe_bytes = f"#!/bin/sh\n# lane {lane} driver\n".encode()
        (d / "g33_fortran_driver").write_bytes(exe_bytes)
        prov = _provenance(exe_bytes, canonical=(lane == "A"))
        if prov_edit:
            prov_edit(lane, prov)
        (d / "provenance.json").write_text(json.dumps(prov, sort_keys=True))
        stdout_sha[lane] = hashlib.sha256(data).hexdigest()
        stderr_sha[lane] = hashlib.sha256(b"").hexdigest()
        exe_sha[lane] = hashlib.sha256(exe_bytes).hexdigest()
        prov_sha[lane] = hashlib.sha256(
            (d / "provenance.json").read_bytes()).hexdigest()

    run = fd.parse_fortran_run(raw.decode(), algo, authority["K"], authority["B"])
    manifest = {
        "schema_version": 2, "algorithm": algo,
        "repo_commit": COMMIT, "repo_dirty": dirty,
        "fixture_id": authority["fixture_id"],
        "fixture_manifest_sha256": gfx.manifest_sha256(authority),
        "fixture_sha256": gfx.fixture_sha256(authority),
        "parameter_sha256": gfx.parameter_sha256(authority),
        "fortran_parameter_sha256": gfx.fortran_parameter_sha256(authority),
        "abc_equal": True,
        "stdout_sha256": stdout_sha, "stderr_sha256": stderr_sha,
        "executable_sha256": exe_sha, "build_provenance_sha256": prov_sha,
        "op_record_count": len(run.ops),
        "mstep_per_column": {f"L{lp}/{ch}/col{c}": v
                             for (lp, ch, c), v in run.mstep.items()},
        "module_canonical_sha256": "m" * 64,
        "compiler_binary_sha256": "f" * 64,
        "compiler_version": "GNU Fortran 13.2.0",
        "host_source_sha256": {"module_mp_kdm6.F": "h" * 64},
        "harness_source_sha256": {"g33_fortran_driver.f90": "j" * 64},
    }
    if manifest_edit:
        manifest_edit(manifest)
    (root / "abc_manifest.json").write_text(json.dumps(manifest, sort_keys=True))
    return root


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _anchors(root: Path) -> dict:
    _, authority = gfx.load_fixture(gfx.DEFAULT_FIXTURE_ID)
    return {"expected_manifest_sha256": _sha(root / "abc_manifest.json"),
            "expected_repo_commit": COMMIT,
            "expected_fixture_id": gfx.DEFAULT_FIXTURE_ID,
            # the fixture BYTES: the id alone anchors a string, and the verifier
            # reads that JSON from its own tree
            "expected_fixture_manifest_sha256": gfx.manifest_sha256(authority)}


# ---- the happy path ----------------------------------------------------------

def test_a_complete_bundle_verifies_and_is_verdict_ready(tmp_path):
    root = _bundle(tmp_path / "b")
    leg = fbio.verify_fortran_bundle(root, "legacy", **_anchors(root))
    assert leg.verdict_ready and leg.bundle_verified and leg.repo_clean
    assert leg.run.ops                                   # the C lane really parsed
    assert set(leg.problem) == {"fixture_sha256", "parameter_sha256",
                                "fortran_parameter_sha256"}


def test_internal_verification_alone_is_not_verdict_ready(tmp_path):
    # exactly the old behaviour: valid text, nothing anchoring it
    leg = fbio.verify_fortran_bundle(_bundle(tmp_path / "b"), "legacy")
    assert leg.bundle_verified and not leg.verdict_ready


@pytest.mark.parametrize("drop", ["expected_manifest_sha256", "expected_repo_commit",
                                  "expected_fixture_id",
                                  "expected_fixture_manifest_sha256"])
def test_no_single_anchor_can_be_omitted(tmp_path, drop):
    root = _bundle(tmp_path / "b")
    kw = {k: v for k, v in _anchors(root).items() if k != drop}
    assert not fbio.verify_fortran_bundle(root, "legacy", **kw).verdict_ready


# ---- what the bundle must refuse ---------------------------------------------

def test_a_dirty_producer_tree_is_not_verdict_ready(tmp_path):
    # the recorded commit does not describe the source the evidence came from,
    # so the anchor would point at the wrong thing
    root = _bundle(tmp_path / "b", dirty=True)
    leg = fbio.verify_fortran_bundle(root, "legacy", **_anchors(root))
    assert leg.bundle_verified and not leg.repo_clean and not leg.verdict_ready


def test_a_tampered_lane_is_rejected(tmp_path):
    root = _bundle(tmp_path / "b")
    path = root / "C" / "stdout.g33f"
    path.write_bytes(path.read_bytes() + b"\n")          # sha no longer matches
    with pytest.raises(fbio.FortranBundleError, match="sha256"):
        fbio.verify_fortran_bundle(root, "legacy", **_anchors(root))


def test_a_lane_running_a_different_fixture_is_rejected(tmp_path):
    # an A/B run on other inputs whose final state happened to match C would
    # otherwise pass abc_equal on a false premise
    root = _bundle(tmp_path / "b")
    m = json.loads((root / "abc_manifest.json").read_text())
    m["fixture_sha256"] = "0" * 64
    (root / "abc_manifest.json").write_text(json.dumps(m, sort_keys=True))
    with pytest.raises(fbio.FortranBundleError, match="fixture_sha256"):
        fbio.verify_fortran_bundle(root, "legacy",
                                   expected_fixture_id=gfx.DEFAULT_FIXTURE_ID)


def test_the_algorithm_must_match_what_the_caller_asked_for(tmp_path):
    root = _bundle(tmp_path / "b", algo="legacy")
    with pytest.raises(fbio.FortranBundleError, match="asked for"):
        fbio.verify_fortran_bundle(root, "conservative", **_anchors(root))


def test_abc_equal_false_is_refused_even_if_everything_else_holds(tmp_path):
    root = _bundle(tmp_path / "b", manifest_edit=lambda m: m.update(abc_equal=False))
    with pytest.raises(fbio.FortranBundleError, match="abc_equal"):
        fbio.verify_fortran_bundle(root, "legacy")


def test_a_wrong_fixture_id_is_refused(tmp_path):
    root = _bundle(tmp_path / "b")
    with pytest.raises(fbio.FortranBundleError):
        fbio.verify_fortran_bundle(
            root, "legacy", expected_fixture_id="arithmetic_multisubcycle_v1")


def test_an_unknown_fixture_id_is_refused(tmp_path):
    with pytest.raises(fbio.FortranBundleError, match="unusable fixture"):
        fbio.verify_fortran_bundle(_bundle(tmp_path / "b"), "legacy",
                                   expected_fixture_id="no_such_fixture")


def test_a_missing_lane_is_refused(tmp_path):
    root = _bundle(tmp_path / "b")
    shutil.rmtree(root / "B")
    with pytest.raises(fbio.FortranBundleError, match="missing bundle file"):
        fbio.verify_fortran_bundle(root, "legacy", **_anchors(root))


def test_a_symlinked_lane_is_refused(tmp_path):
    root = _bundle(tmp_path / "b")
    target = root / "C" / "stdout.g33f"
    data = target.read_bytes()
    outside = tmp_path / "elsewhere.g33f"
    outside.write_bytes(data)
    target.unlink()
    target.symlink_to(outside)
    with pytest.raises(fbio.FortranBundleError, match="symlink"):
        fbio.verify_fortran_bundle(root, "legacy", **_anchors(root))


def test_the_leg_mirrors_the_cpp_verdict_ready_contract():
    # The two legs must reach the decision boundary demanding the SAME external
    # properties, or the gate keeps one rule for C++ and an honour system for
    # Fortran. (root_attested vs bundle_verified name the same idea per backend:
    # "this artifact's own structure was re-verified".)
    import g33_bundle_io as bio
    shared = {"external_manifest_attested", "source_commit_attested",
              "fixture_attested"}
    assert shared <= set(bio.VerifiedCppLeg.__dataclass_fields__)
    assert shared <= set(fbio.VerifiedFortranLeg.__dataclass_fields__)
    assert hasattr(bio.VerifiedCppLeg, "verdict_ready")
    assert hasattr(fbio.VerifiedFortranLeg, "verdict_ready")


def test_a_fixture_file_that_is_not_the_anchored_one_is_refused(tmp_path):
    # the id would still match; only the bytes reveal that the verifier read a
    # different file than the one anchored
    root = _bundle(tmp_path / "b")
    kw = dict(_anchors(root), expected_fixture_manifest_sha256="9" * 64)
    with pytest.raises(fbio.FortranBundleError, match="different fixture file"):
        fbio.verify_fortran_bundle(root, "legacy", **kw)


# ── provenance is CONSUMED, not merely recorded ───────────────────────────────
# Each of these used to pass: the verifier hashed stdout and stopped.

def test_a_missing_provenance_file_is_refused(tmp_path):
    root = _bundle(tmp_path / "b")
    (root / "A" / "provenance.json").unlink()
    with pytest.raises(fbio.FortranBundleError, match="missing bundle file"):
        fbio.verify_fortran_bundle(root, "legacy", **_anchors(root))


def test_a_modified_executable_is_refused(tmp_path):
    # the old check asked whether the recorded string was 64 characters long
    root = _bundle(tmp_path / "b")
    exe = root / "B" / "g33_fortran_driver"
    exe.write_bytes(exe.read_bytes() + b"x")
    with pytest.raises(fbio.FortranBundleError, match="executable"):
        fbio.verify_fortran_bundle(root, "legacy", **_anchors(root))


def test_a_modified_stderr_is_refused(tmp_path):
    root = _bundle(tmp_path / "b")
    (root / "C" / "stderr.txt").write_bytes(b"warning: something\n")
    with pytest.raises(fbio.FortranBundleError, match="stderr"):
        fbio.verify_fortran_bundle(root, "legacy", **_anchors(root))


def test_lane_A_must_be_the_canonical_module(tmp_path):
    # A is the control: an overlay there invalidates the non-invasiveness claim
    root = _bundle(tmp_path / "b",
                   prov_edit=lambda lane, p: p.update(module_compiled_sha256="z" * 64)
                   if lane == "A" else None)
    with pytest.raises(fbio.FortranBundleError, match="canonical module"):
        fbio.verify_fortran_bundle(root, "legacy", **_anchors(root))


def test_lanes_B_and_C_must_compile_the_same_module(tmp_path):
    root = _bundle(tmp_path / "b",
                   prov_edit=lambda lane, p: p.update(module_compiled_sha256="q" * 64)
                   if lane == "C" else None)
    with pytest.raises(fbio.FortranBundleError, match="different modules"):
        fbio.verify_fortran_bundle(root, "legacy", **_anchors(root))


def test_a_lane_built_by_a_different_compiler_is_refused(tmp_path):
    root = _bundle(tmp_path / "b",
                   prov_edit=lambda lane, p: p.update(compiler_binary_sha256="0" * 64)
                   if lane == "B" else None)
    with pytest.raises(fbio.FortranBundleError, match="different toolchain"):
        fbio.verify_fortran_bundle(root, "legacy", **_anchors(root))


def test_a_manifest_summary_that_disagrees_with_the_stream_is_refused(tmp_path):
    # a bundle whose op count describes a different run than the one it ships
    root = _bundle(tmp_path / "b",
                   manifest_edit=lambda m: m.update(op_record_count=1))
    with pytest.raises(fbio.FortranBundleError, match="op_record_count"):
        fbio.verify_fortran_bundle(root, "legacy", **_anchors(root))


def test_a_manifest_mstep_table_that_disagrees_is_refused(tmp_path):
    root = _bundle(tmp_path / "b",
                   manifest_edit=lambda m: m.update(
                       mstep_per_column={"L1/main/col1": 99}))
    with pytest.raises(fbio.FortranBundleError, match="mstep_per_column"):
        fbio.verify_fortran_bundle(root, "legacy", **_anchors(root))


def test_the_two_control_legs_must_share_a_build_identity(tmp_path):
    # legacy and conservative could have been built by different compilers and the
    # four-way problem identity would never have shown it
    a = fbio.verify_fortran_bundle(_bundle(tmp_path / "a"), "legacy",
                                   **_anchors(tmp_path / "a"))
    # a COHERENT bundle built by a different compiler: root and lanes agree with
    # each other, they just disagree with the first leg
    other = _bundle(tmp_path / "c",
                    prov_edit=lambda lane, p: p.update(
                        compiler_version="GNU Fortran 9.4.0"),
                    manifest_edit=lambda m: m.update(
                        compiler_version="GNU Fortran 9.4.0"))
    b = fbio.verify_fortran_bundle(other, "legacy", **_anchors(other))
    assert a.build != b.build, "a differing toolchain must be visible in BuildIdentity"


def test_a_verified_leg_cannot_be_forged_afterwards(tmp_path):
    root = _bundle(tmp_path / "b")
    leg = fbio.verify_fortran_bundle(root, "legacy", **_anchors(root))
    with pytest.raises(TypeError):
        leg.manifest["abc_equal"] = False


# ── the two control legs differ by MODULE and only by module ──────────────────

def test_the_two_legs_may_compile_DIFFERENT_modules(tmp_path):
    """legacy builds module_mp_kdm6.F, conservative module_mp_kdm6_cons.F. Those
    hashes MUST differ — that difference is the comparison. Requiring the whole
    BuildIdentity to match across legs made every real four-case run
    INVALID_EVIDENCE, which is how the mistake was found: on the dt=300 bundle, not
    in this file, because the fixture gave both legs the same module hash."""
    a = _bundle(tmp_path / "a")
    def _module(lane, p):                       # a whole variant, consistently
        p["module_canonical_sha256"] = "k" * 64
        if lane == "A":
            p["module_compiled_sha256"] = "k" * 64
    b = _bundle(tmp_path / "b", prov_edit=_module,
                manifest_edit=lambda m: m.update(module_canonical_sha256="k" * 64))
    lg = fbio.verify_fortran_bundle(a, "legacy", **_anchors(a))
    cn = fbio.verify_fortran_bundle(b, "legacy", **_anchors(b))
    assert lg.build != cn.build, "the module hash must be visible in BuildIdentity"
    assert lg.build.toolchain() == cn.build.toolchain(), (
        "...but the TOOLCHAIN is what the two control legs share")


def test_a_differing_toolchain_is_still_caught_across_legs(tmp_path):
    a = _bundle(tmp_path / "a")
    b = _bundle(tmp_path / "b",
                prov_edit=lambda lane, p: p.update(compiler_binary_sha256="0" * 64),
                manifest_edit=lambda m: m.update(compiler_binary_sha256="0" * 64))
    lg = fbio.verify_fortran_bundle(a, "legacy", **_anchors(a))
    cn = fbio.verify_fortran_bundle(b, "legacy", **_anchors(b))
    assert lg.build.toolchain() != cn.build.toolchain()


def test_a_differing_harness_source_is_caught_across_legs(tmp_path):
    # the module is dropped from toolchain() BY NAME, so everything else still counts
    a = _bundle(tmp_path / "a")
    harness = {"g33_fortran_driver.f90": "z" * 64}
    b = _bundle(tmp_path / "b",
                prov_edit=lambda lane, p: p.update(harness_source_sha256=harness),
                manifest_edit=lambda m: m.update(harness_source_sha256=harness))
    lg = fbio.verify_fortran_bundle(a, "legacy", **_anchors(a))
    cn = fbio.verify_fortran_bundle(b, "legacy", **_anchors(b))
    assert lg.build.toolchain() != cn.build.toolchain()
