#!/usr/bin/env python3
"""Re-verify a Fortran A/B/C bundle and return an opaque, attested leg.

The decision gate used to take the Fortran legs as raw `.g33f` paths: parse, check
semantics, replay, normalize. Every one of those is an INTERNAL property of the
stream. Nothing tied the stream to the compiler that produced it, the source it was
built from, the fixture it claims, or a revision anyone reviewed — so a result stamped
`attested: true` meant "the C++ bundle is externally anchored and the Fortran text is
self-consistent", which is not four-leg attestation.

The producer already records all of it (`abc_manifest.json`: compiler binary + version,
executable/stdout/stderr SHAs, canonical and compiled module SHAs, host and harness
source SHAs, fixture/parameter/local-parameter identity, repo commit and dirty state).
It simply had no consumer. This is that consumer, shaped like `verify_cpp_bundle` so
the two legs reach the decision boundary as the same kind of object.

External anchors are the same idea as the C++ side: a bundle that rewrites its own
manifest stays self-consistent, so a decision needs a value held outside it.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "g33_fortran"))
import g33_fixture_v1 as gfx           # noqa: E402
import g33_fortran_dump as fd          # noqa: E402
import g33_fortran_semantics as sem    # noqa: E402

LANES = ("A", "B", "C")


class FortranBundleError(Exception):
    """The Fortran bundle cannot be re-verified."""


@dataclass(frozen=True)
class BuildIdentity:
    """What produced this leg's binaries.

    The two Fortran control legs must share it. Nothing compared them before, so
    legacy and conservative could have come from different compilers, sources or
    flags and the four-way problem identity would not have shown it.
    """
    compiler_binary_sha256: str
    compiler_version: str
    module_canonical_sha256: str
    host_source_sha256: tuple          # sorted (name, sha) pairs
    harness_source_sha256: tuple

    @classmethod
    def of(cls, prov: dict) -> "BuildIdentity":
        return cls(
            compiler_binary_sha256=prov["compiler_binary_sha256"],
            compiler_version=prov["compiler_version"],
            module_canonical_sha256=prov["module_canonical_sha256"],
            host_source_sha256=tuple(sorted(prov["host_source_sha256"].items())),
            harness_source_sha256=tuple(sorted(prov["harness_source_sha256"].items())),
        )


@dataclass(frozen=True)
class VerifiedFortranLeg:
    """One Fortran leg that has passed re-verification.

    Deliberately mirrors VerifiedCppLeg: `verdict_ready` is the same conjunction, so
    `adjudicate_verified` can require the SAME property of all four legs instead of
    one rule for C++ and an honour system for Fortran.
    """
    algorithm: str
    manifest: dict
    run: object                                # the parsed C-lane run
    problem: dict | None = None
    build: BuildIdentity | None = None      # what produced the binaries
    bundle_verified: bool = False              # structure, hashes, A==B==C, semantics
    external_manifest_attested: bool = False   # manifest pinned to an OUTSIDE SHA
    source_commit_attested: bool = False       # repo_commit pinned to a reviewed rev
    fixture_attested: bool = False             # the fixture was NAMED from outside
    repo_clean: bool = False                   # producer tree described its commit

    @property
    def verdict_ready(self) -> bool:
        return (self.bundle_verified and self.external_manifest_attested
                and self.source_commit_attested and self.fixture_attested
                and self.repo_clean)


def _freeze(obj):
    """Recursively read-only. MappingProxyType guards only the TOP dict — a nested
    one stays writable, so a caller could forge run.stages after verification while
    verdict_ready stayed True. The C++ leg already froze deeply; this did not."""
    if isinstance(obj, dict):
        return MappingProxyType({k: _freeze(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return tuple(_freeze(v) for v in obj)
    return obj


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _under(root: Path, path: Path) -> Path:
    """Refuse anything outside the bundle, including via a symlink."""
    root_r, path_r = root.resolve(), path.resolve()
    if not str(path_r).startswith(str(root_r) + os.sep):
        raise FortranBundleError(f"{path} escapes the bundle root")
    if path.is_symlink():
        raise FortranBundleError(f"{path} is a symlink")
    if not path_r.is_file():
        raise FortranBundleError(f"missing bundle file: {path}")
    return path_r


def verify_fortran_bundle(bundle_dir, algorithm: str, *,
                          expected_manifest_sha256: str | None = None,
                          expected_repo_commit: str | None = None,
                          expected_fixture_id: str | None = None,
                          expected_fixture_manifest_sha256: str | None = None
                          ) -> VerifiedFortranLeg:
    """Re-verify one Fortran A/B/C bundle.

    Re-hashes every lane rather than trusting the manifest's own numbers, requires
    A==B==C on the RE-READ bytes, re-parses the C lane through the strict parser, and
    re-runs the semantic + offline-replay checks. The manifest's claims are treated as
    assertions to be checked, never as findings.
    """
    root = Path(bundle_dir)
    if not root.is_dir():
        raise FortranBundleError(f"bundle dir not found: {root}")

    manifest_path = _under(root, root / "abc_manifest.json")
    manifest_bytes = manifest_path.read_bytes()
    manifest_sha = _sha256_bytes(manifest_bytes)
    if expected_manifest_sha256 and manifest_sha != expected_manifest_sha256:
        raise FortranBundleError(
            f"manifest sha256 {manifest_sha} != expected {expected_manifest_sha256}")
    try:
        manifest = json.loads(manifest_bytes)
    except json.JSONDecodeError as e:
        raise FortranBundleError(f"abc_manifest.json is not JSON: {e}") from None

    if manifest.get("algorithm") != algorithm:
        raise FortranBundleError(
            f"bundle is {manifest.get('algorithm')!r}, asked for {algorithm!r}")
    if manifest.get("schema_version") != 2:
        raise FortranBundleError(
            f"unsupported manifest schema_version {manifest.get('schema_version')!r}")

    # A dirty producer tree means the recorded commit does not describe the source
    # the evidence came from — the anchor would point at the wrong thing.
    repo_clean = manifest.get("repo_dirty") is False
    commit = manifest.get("repo_commit")
    if expected_repo_commit and commit != expected_repo_commit:
        raise FortranBundleError(
            f"repo_commit {commit} != expected {expected_repo_commit}")

    # FIXTURE: named by the caller, checked against the checked-in authority. A
    # bundle checked against the fixture it declares attests nothing.
    fixture_id = expected_fixture_id or manifest.get("fixture_id")
    try:
        _, authority = gfx.load_fixture(fixture_id)
    except (gfx.UnknownFixture, ValueError, KeyError) as e:
        raise FortranBundleError(f"unusable fixture id {fixture_id!r}: {e}") from None
    # CONTENT anchor. The id names a registry entry, but the verifier reads that
    # JSON from its OWN working tree — on a divergent or dirty tree that is not the
    # file anyone reviewed. expected_repo_commit does not close this either: it pins
    # the evidence PRODUCER's commit, not the fixture the verifier read.
    resolved = gfx.manifest_sha256(authority)
    if expected_fixture_manifest_sha256 and resolved != expected_fixture_manifest_sha256:
        raise FortranBundleError(
            f"fixture manifest sha256 {resolved} != expected "
            f"{expected_fixture_manifest_sha256} — the verifier read a different "
            f"fixture file than the anchored one")
    if manifest.get("fixture_id") != authority["fixture_id"]:
        raise FortranBundleError(
            f"manifest fixture_id {manifest.get('fixture_id')!r} != "
            f"{authority['fixture_id']!r}")
    for key, want in (("fixture_manifest_sha256", gfx.manifest_sha256(authority)),
                      ("fixture_sha256", gfx.fixture_sha256(authority)),
                      ("parameter_sha256", gfx.parameter_sha256(authority)),
                      ("fortran_parameter_sha256",
                       gfx.fortran_parameter_sha256(authority))):
        if manifest.get(key) != want:
            raise FortranBundleError(f"manifest {key} != the {fixture_id} authority")

    # LANES: re-hash every artifact on disk. A manifest's own sha is an assertion
    # about a file, not a fact about it — and an executable "verified" by checking
    # that its recorded string is 64 characters long is not verified at all.
    streams, provenance = {}, {}
    for lane in LANES:
        lane_dir = root / lane
        data = _under(root, lane_dir / "stdout.g33f").read_bytes()
        if _sha256_bytes(data) != (manifest.get("stdout_sha256") or {}).get(lane):
            raise FortranBundleError(f"lane {lane} stdout sha256 != manifest")
        streams[lane] = data

        err = _under(root, lane_dir / "stderr.txt").read_bytes()
        if _sha256_bytes(err) != (manifest.get("stderr_sha256") or {}).get(lane):
            raise FortranBundleError(f"lane {lane} stderr sha256 != manifest")

        prov_path = _under(root, lane_dir / "provenance.json")
        prov_bytes = prov_path.read_bytes()
        if _sha256_bytes(prov_bytes) != (
                manifest.get("build_provenance_sha256") or {}).get(lane):
            raise FortranBundleError(f"lane {lane} provenance sha256 != manifest")
        try:
            prov = json.loads(prov_bytes)
        except json.JSONDecodeError as e:
            raise FortranBundleError(f"lane {lane} provenance is not JSON: {e}") from None
        need = ("compiler_binary_sha256", "compiler_version", "module_canonical_sha256",
                "module_compiled_sha256", "executable_sha256", "host_source_sha256",
                "harness_source_sha256")
        missing = [k for k in need if k not in prov]
        if missing:
            raise FortranBundleError(f"lane {lane} provenance lacks {missing}")
        provenance[lane] = prov

        # the ACTUAL binary, hashed, against BOTH records of it
        exe = _under(root, lane_dir / "g33_fortran_driver")
        exe_sha = _sha256_file(exe)
        if exe_sha != prov["executable_sha256"]:
            raise FortranBundleError(
                f"lane {lane} executable {exe_sha} != its own provenance")
        if exe_sha != (manifest.get("executable_sha256") or {}).get(lane):
            raise FortranBundleError(f"lane {lane} executable != root manifest")

    # BUILD COHERENCE across the lanes. A is the canonical build; B and C carry the
    # overlay, so their compiled module differs from A's by exactly the
    # instrumentation and must agree with each other.
    if provenance["A"]["module_compiled_sha256"] != \
            provenance["A"]["module_canonical_sha256"]:
        raise FortranBundleError("lane A is not the canonical module — it is the "
                                 "control, so an overlay there invalidates the run")
    if provenance["B"]["module_compiled_sha256"] != \
            provenance["C"]["module_compiled_sha256"]:
        raise FortranBundleError("lanes B and C compiled different modules")
    build = BuildIdentity.of(provenance["A"])
    for lane in ("B", "C"):
        if BuildIdentity.of(provenance[lane]) != build:
            raise FortranBundleError(
                f"lane {lane} was built from a different toolchain or source than A")
    # the root manifest's copies of the build facts must equal the lanes' own
    for key in ("module_canonical_sha256", "compiler_binary_sha256",
                "compiler_version", "host_source_sha256", "harness_source_sha256"):
        declared = manifest.get(key)
        if declared is not None and declared != provenance["A"][key]:
            raise FortranBundleError(f"root manifest {key} != lane provenance")

    # NON-INVASIVENESS, re-derived. A and B are non-instrumented and C is not, so
    # their BYTES differ by construction — that difference is the instrumentation.
    # What must match is the physics: final state and precipitation. Re-parse all
    # three rather than trusting the manifest's abc_equal flag.
    if manifest.get("abc_equal") is not True:
        raise FortranBundleError("manifest abc_equal is not True")
    B, K = authority["B"], authority["K"]
    parsed = {}
    for lane, data in streams.items():
        try:
            parsed[lane] = fd.parse_fortran_run(
                data.decode("ascii", "strict"), algorithm, K, B,
                evidence_mode="instrumented" if lane == "C" else "noninstrumented")
        except UnicodeDecodeError as e:
            raise FortranBundleError(f"lane {lane} is not ASCII: {e}") from None
        except Exception as e:                  # every reader here is fail-closed
            raise FortranBundleError(
                f"lane {lane} invalid: {type(e).__name__}: {e}") from None

    if not (parsed["A"].state == parsed["B"].state == parsed["C"].state):
        raise FortranBundleError("A/B/C final state differs — NOT non-invasive")
    if not (parsed["A"].precip == parsed["B"].precip == parsed["C"].precip):
        raise FortranBundleError("A/B/C precipitation differs — NOT non-invasive")
    # Every lane must have consumed the SAME fixture: otherwise an A/B run on other
    # inputs whose final state happened to match C would pass on a false premise.
    for lane, r in parsed.items():
        if (r.fixture_sha256, r.parameter_sha256, r.local_parameter_sha256) != (
                manifest["fixture_sha256"], manifest["parameter_sha256"],
                manifest["fortran_parameter_sha256"]):
            raise FortranBundleError(f"lane {lane} consumed a different fixture")

    run = parsed["C"]                           # the instrumented lane
    # The manifest's SUMMARIES are claims about the stream. Recompute them: a bundle
    # whose mstep table or op count disagrees with its own evidence is describing a
    # different run than the one it ships.
    declared_ops = manifest.get("op_record_count")
    if declared_ops is not None and declared_ops != len(run.ops):
        raise FortranBundleError(
            f"manifest op_record_count {declared_ops} != {len(run.ops)} in the C lane")
    declared_mstep = manifest.get("mstep_per_column") or {}
    actual_mstep = {f"L{lp}/{ch}/col{c}": v for (lp, ch, c), v in run.mstep.items()}
    if declared_mstep and declared_mstep != actual_mstep:
        raise FortranBundleError(
            f"manifest mstep_per_column != the C lane's own records")
    try:
        sem.verify_semantics(run)
        fd.verify_offline_replay(run)
    except Exception as e:
        raise FortranBundleError(f"C lane invalid: {type(e).__name__}: {e}") from None

    problem = {"fixture_sha256": manifest["fixture_sha256"],
               "parameter_sha256": manifest["parameter_sha256"],
               # the Fortran-only constants (ccn0/scale_h) the C++ leg bakes in:
               # part of "same problem", and absent from the C++ identity until a
               # direct probe of the baked values exists.
               "fortran_parameter_sha256": manifest["fortran_parameter_sha256"]}

    return VerifiedFortranLeg(
        algorithm=algorithm,
        manifest=_freeze(manifest),
        run=run,
        build=build,
        problem=problem,
        bundle_verified=True,
        external_manifest_attested=expected_manifest_sha256 is not None,
        source_commit_attested=expected_repo_commit is not None,
        fixture_attested=bool(expected_fixture_id
                              and expected_fixture_manifest_sha256),
        repo_clean=repo_clean,
    )
