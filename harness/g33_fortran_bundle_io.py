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


#: Every FortranRun field that carries evidence in a mutable mapping. Named rather
#: than discovered, so a field added later is a deliberate decision about whether it
#: is evidence — a dir()-based sweep would freeze new fields silently either way.
_RUN_MAPPINGS = ("stages", "state", "precip", "fixin", "params", "localparams",
                 "init_params", "mstep")


class FortranBundleError(Exception):
    """The Fortran bundle cannot be re-verified."""


#: The EXACT host sources every lane must attest. Provenance checked only that the
#: map existed, so dropping one from all three lanes and the root manifest left
#: BuildIdentity comparing a smaller set and agreeing — and with the variant module
#: excluded from toolchain(), the fail-open surface was the whole shared tree.
#:
#: A closed world: adding a source makes CI fail until someone widens the attestation
#: scope deliberately (owner P1).
EXPECTED_HOST_SOURCES = frozenset((
    "libmassv.F", "module_model_constants.F", "module_mp_radar.F",
    "module_mp_kdm6[_cons].F",
))

#: Same, for the harness. `fixture.f90`/`fixture.h` are keyed by ROLE because the
#: build selects which generated fixture to compile.
EXPECTED_HARNESS_SOURCES = frozenset((
    "make_fortran_overlay.py", "g33_fortran_bindings.py", "g33_fortran_driver.f90",
    "stub_wrf_error.f90", "fortran_build.sh", "g33_provenance.py",
    "g33_fortran_dump.py", "run_fortran_case.py",
    "fixture.f90", "fixture.h",
    "g33_fixture_v1.json", "g33_fixture_v1.py",
    "g33_fourcase_fixture_check.py", "g33_schema.py", "g33_expectation.py",
))


#: The single normalized key under which provenance records whichever microphysics
#: variant this leg compiled. It is the ONE host source that legitimately differs
#: between the two control legs.
VARIANT_MODULE_KEY = "module_mp_kdm6[_cons].F"

#: The ONLY G33F protocol version a G3.3-M verdict may rest on.
#:
#: The parser deliberately accepts every past version — migration, and re-verifying
#: evidence produced before a tier existed, both need it — but the decision path must
#: not. Each bump closed a specific blind spot, and a stream from before it cannot
#: answer the question the gate asks:
#:
#:   v4  the bridge omits nc/ni/nccn/brs, so "the sedimentation result matched" is a
#:       claim about eight of twelve carried members. dt=300 is the worked example:
#:       at v4 the first difference read as post-microphysics; at v5 it moved to
#:       nccn, before sedimentation ran at all.
#:   v5  no kernel-call arguments and no `p`. outer_pre_sed is recorded AFTER the
#:       entry clamp, so it cannot separate "both legs were handed the same problem"
#:       from "the clamp erased the difference" (owner P0-3/P0-4).
#:   v8  the 12 prognostics are not the whole input to the microphysics: the ProgB
#:       auxiliary bundle it also consumes was unrecorded, so `x_F == x_C` with
#:       `a_F != a_C` was consistent with everything observed and "the difference is in
#:       the microphysics" was stronger than the records (owner P0-1.3).
#:   v7  records what kdm6init was CALLED with but not what it BUILT, so the module
#:       constants kdm62D actually reads were never compared across trees — and the C++
#:       port reproduces that block f32-stepwise on purpose, because a double-then-demote
#:       differs by 1 ULP (owner P0-1.1).
#:   v6  no snapshot BETWEEN the call arguments and the sedimentation entry, so the
#:       whole prologue is one unmeasured interval — and the C++ outer_pre_sed sat
#:       BEFORE its ProgB brs update while the Fortran one sits after ProgB_param, so
#:       one of the twelve carried fields was compared at two different instants.
#:
#: A pre-v6 bundle with valid external anchors would otherwise reach verdict_ready.
DECISION_PROTOCOL_VERSION = 12

#: Compile flags that change the NUMBERS. A leg built without -ffp-contract=off
#: fuses multiply-adds, so the same compiler and the same sources still give a
#: different answer — and comparing whole command strings instead would break on
#: paths and on the variant/instrumentation defines that are supposed to differ.
_NUMERIC_FLAGS = ("-ffp-contract=", "-O", "-ffast-math", "-funroll-loops",
                  "-ftree-vectorize", "-fno-", "-march=", "-mtune=", "-mfpmath=")


def _numeric_flags(commands) -> tuple:
    """The numerics-affecting flags each compile command carries, deduplicated and
    ordered. Paths, output names and the -D defines that SHOULD differ between the
    variants and between instrumented and control lanes are excluded."""
    out = set()
    for cmd in commands or ():
        for tok in str(cmd).split():
            if any(tok.startswith(f) for f in _NUMERIC_FLAGS):
                out.add(tok)
    return tuple(sorted(out))


#: Differences the design REQUIRES between the two control legs and between the
#: instrumented and control lanes. Everything else must match exactly.
_SANCTIONED_DEFINES = frozenset(("KDM6_CONS", "KDM6_G33_FORTRAN_DUMP"))


@dataclass(frozen=True)
class CompileProfile:
    """One compile command, identified by WHAT it produced.

    Flags used to be pooled from every command into one set, which loses the only
    thing that matters: a flag missing from the command that compiles the
    microphysics is invisible if any other command carries it. The build compiles the
    module and the driver separately and both pass -ffp-contract=off, so the union
    still contained it while the module was built with contraction on.

    A set also discarded order (-O2 -O0 vs -O0 -O2), duplicates and overrides.
    Ordered here, and compared exactly.
    """
    role: str                # from the -o target: module_mp, driver, radar, link ...
    ordered_flags: tuple     # every flag, in order, paths normalized away
    defines: tuple           # -D..., minus the sanctioned ones


def _compile_profiles(commands) -> tuple:
    """Every command as a role-keyed profile.

    Paths are dropped rather than normalized: build directories and source locations
    legitimately differ between runs, and keeping them would make the comparison fail
    for reasons that say nothing about the numbers.
    """
    import shlex
    out = {}
    for cmd in commands or ():
        toks = shlex.split(str(cmd))
        role, flags, defines, skip = None, [], [], False
        for i, tok in enumerate(toks):
            if skip:
                skip = False
                continue
            if tok == "-o":
                nxt = toks[i + 1] if i + 1 < len(toks) else ""
                role = os.path.basename(nxt).removesuffix(".o") or None
                skip = True
            elif tok.startswith("-D"):
                name = tok[2:].split("=")[0]
                if name not in _SANCTIONED_DEFINES:
                    defines.append(tok)
            elif tok.startswith(("-I", "-J", "-L", "-l")) or "/" in tok:
                continue                       # paths and library search dirs
            elif tok.startswith("-"):
                flags.append(tok)
        if role is None:
            continue
        if "-c" not in toks:
            role = "link"
        out[role] = CompileProfile(role, tuple(flags), tuple(sorted(defines)))
    return tuple(sorted(out.values(), key=lambda p: p.role))


@dataclass(frozen=True)
class ToolchainIdentity:
    """What produced both control legs. Compared ACROSS them; excludes the variant
    module, which is authorized separately (owner P0-2/P0-3)."""
    compiler_binary_sha256: str
    compiler_version: str
    compile_profiles: tuple            # per-command, per-role — not a pooled set
    shared_host_sources: tuple
    shared_harness_sources: tuple


@dataclass(frozen=True)
class VariantSourceIdentity:
    """WHICH microphysics source this leg compiled.

    toolchain() excludes the variant module because the two control legs must be
    allowed to differ there. Excluding it is not the same as authorizing it: on its
    own, an entirely different conservative module passes the toolchain gate as long
    as the bundle is internally self-consistent. This is the other half — the module
    is named, and `authorized_by_gate_a` binds it to the scope report that pins which
    edits the freeze-lift permitted (owner P0-2).
    """
    algorithm: str
    canonical_module_sha256: str
    compiled_module_sha256: str


def authorized_by_gate_a(report: dict, legs: dict) -> None:
    """The legs' modules must be the ones Gate A checked and passed.

    `report` is check_cons_fortran_scope.py's JSON output, which verifies that the
    conservative module is the legacy one modulo the renames and the EXACT pinned
    sedimentation-interface edits. Binding to it turns "the modules may differ" into
    "they differ in the authorized way" — without it the decision boundary accepts
    any conservative source whatsoever.
    """
    if report.get("pass") is not True:
        raise FortranBundleError(
            "the Gate A scope report does not pass: %r" % (report.get("failures"),))
    # WHAT produced this verdict. Without these the report says a checker somewhere
    # approved something, which any hand-written JSON also says.
    for field in ("schema_version", "checker_commit", "checker_source_sha256",
                  "scope_manifest_sha256"):
        if not report.get(field):
            raise FortranBundleError(
                "the Gate A report lacks %s — it records a verdict but not what "
                "produced it, which a self-consistent forgery also does" % field)
    # A DIRTY checker is not a checker anyone reviewed. `checker_commit` names a
    # revision, and on a dirty tree the file at that revision is not the file that
    # ran — so the commit identifies a checker whose behaviour is unknown, and the
    # authorization it grants cannot be reproduced (owner P0-8).
    if str(report["checker_commit"]).endswith("-dirty"):
        raise FortranBundleError(
            "the Gate A report was produced by a DIRTY checker tree (%s): regenerate "
            "it from a clean commit, or the authorization names a revision that is "
            "not what ran" % report["checker_commit"])
    pinned = report.get("sha256") or dict()
    for algo, filename in (("legacy", "module_mp_kdm6.F"),
                           ("conservative", "module_mp_kdm6_cons.F")):
        want = pinned.get(filename)
        if not want:
            raise FortranBundleError(
                "the Gate A report pins no sha256 for %s" % filename)
        got = legs[algo].variant_source.canonical_module_sha256
        if got != want:
            raise FortranBundleError(
                "the %s leg compiled module %s but Gate A authorized %s — this "
                "bundle's source is not the one whose edits were reviewed"
                % (algo, got, want))


@dataclass(frozen=True)
class BuildIdentity:
    """What produced this leg's binaries, at two levels.

    The WHOLE identity — microphysics module included — must hold across a bundle's
    own A/B/C lanes: they are three builds of one variant, so a differing module
    there means the control and the instrumented run are not the same program.

    ACROSS the two control legs only `toolchain()` may be compared. Legacy compiles
    module_mp_kdm6.F and conservative module_mp_kdm6_cons.F: those hashes MUST differ,
    because that difference IS the comparison. Requiring the full identity to match
    made every real four-case run INVALID_EVIDENCE — the same shape of mistake as the
    flat problem identity in the comparator (owner P0-C2).
    """
    compiler_binary_sha256: str
    compiler_version: str
    module_canonical_sha256: str
    host_source_sha256: tuple          # sorted (name, sha) pairs
    harness_source_sha256: tuple
    compile_profiles: tuple = ()       # per-role CompileProfile, from `commands`

    @classmethod
    def of(cls, prov: dict) -> "BuildIdentity":
        return cls(
            compiler_binary_sha256=prov["compiler_binary_sha256"],
            compiler_version=prov["compiler_version"],
            module_canonical_sha256=prov["module_canonical_sha256"],
            host_source_sha256=tuple(sorted(prov["host_source_sha256"].items())),
            harness_source_sha256=tuple(sorted(prov["harness_source_sha256"].items())),
            compile_profiles=_compile_profiles(prov.get("commands")),
        )

    def toolchain(self) -> "ToolchainIdentity":
        """Everything the two control legs must share.

        The variant module is excluded by its EXACT normalized key, not by a
        substring: `"kdm6" not in name` also dropped any future shared file whose
        name contains kdm6 — kdm6_constants.inc, kdm6_shared_helpers.F — silently
        moving it outside the comparison. Excluding one known key means a new shared
        source is compared by default and a new variant key fails loudly.
        """
        shared = tuple((n, h) for n, h in self.host_source_sha256
                       if n != VARIANT_MODULE_KEY)
        if len(shared) == len(self.host_source_sha256):
            raise FortranBundleError(
                f"provenance has no {VARIANT_MODULE_KEY!r} entry — the variant "
                f"module is not where the attestation scope expects it, so nothing "
                f"can be said about which sources the two legs share")
        return ToolchainIdentity(
            compiler_binary_sha256=self.compiler_binary_sha256,
            compiler_version=self.compiler_version,
            compile_profiles=self.compile_profiles,
            shared_host_sources=shared,
            shared_harness_sources=self.harness_source_sha256)


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
    variant_source: VariantSourceIdentity | None = None   # WHICH module it compiled
    bundle_verified: bool = False              # structure, hashes, A==B==C, semantics
    external_manifest_attested: bool = False   # manifest pinned to an OUTSIDE SHA
    source_commit_attested: bool = False       # repo_commit pinned to a reviewed rev
    fixture_attested: bool = False             # the fixture was NAMED from outside
    repo_clean: bool = False                   # producer tree described its commit

    @property
    def verdict_ready(self) -> bool:
        return (self.bundle_verified and self.external_manifest_attested
                and self.source_commit_attested and self.fixture_attested
                and self.repo_clean
                and getattr(self.run, "protocol_version", 0)
                == DECISION_PROTOCOL_VERSION)


def _no_dup_keys(pairs):
    """A repeated JSON key silently keeps the LAST value, so a manifest could carry
    two executable_sha256 entries and be verified against whichever survived. The C++
    reader already refused this; the Fortran one parsed with plain json.loads."""
    seen = {}
    for k, v in pairs:
        if k in seen:
            raise FortranBundleError(f"duplicate JSON key {k!r}")
        seen[k] = v
    return seen


def _freeze(obj):
    """Recursively read-only. MappingProxyType guards only the TOP dict — a nested
    one stays writable, so a caller could forge run.stages after verification while
    verdict_ready stayed True. The C++ leg already froze deeply; this did not."""
    if isinstance(obj, dict):
        return MappingProxyType({k: _freeze(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return tuple(_freeze(v) for v in obj)
    return obj


def _freeze_run(run):
    """A FortranRun whose payload mappings are read-only."""
    return replace(run, **{f: _freeze(getattr(run, f)) for f in _RUN_MAPPINGS})


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
        manifest = json.loads(manifest_bytes, object_pairs_hook=_no_dup_keys)
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
            prov = json.loads(prov_bytes, object_pairs_hook=_no_dup_keys)
        except json.JSONDecodeError as e:
            raise FortranBundleError(f"lane {lane} provenance is not JSON: {e}") from None
        need = ("compiler_binary_sha256", "compiler_version", "module_canonical_sha256",
                "module_compiled_sha256", "executable_sha256", "host_source_sha256",
                "harness_source_sha256")
        missing = [k for k in need if k not in prov]
        if missing:
            raise FortranBundleError(f"lane {lane} provenance lacks {missing}")
        # EXACT source universe, not merely "the map is present"
        for field, expected in (("host_source_sha256", EXPECTED_HOST_SOURCES),
                                ("harness_source_sha256", EXPECTED_HARNESS_SOURCES)):
            got = frozenset(prov[field])
            if got != expected:
                raise FortranBundleError(
                    f"lane {lane} {field} is not the attested set: "
                    f"missing {sorted(expected - got)}, "
                    f"unexpected {sorted(got - expected)}")
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
                evidence_mode="instrumented" if lane == "C" else "noninstrumented",
                # the FIXTURE's declaration, read from the authority this verifier
                # loads itself — never from the bundle, which would let a stream
                # authorize its own out-of-domain input
                allow_negative_input=authority.get("allows_negative_input", False))
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
    # Same rule for the two claims that decide ADMISSIBILITY rather than content.
    # A reader picks a bundle by its manifest — "this is v5 kernel evidence" — and a
    # manifest that says so over a v4 wrapper stream would route the wrong evidence
    # into the decision path. The stream's own banner is the authority; the manifest
    # is a claim about it, and the two must agree.
    for key, actual in (("g33f_protocol_version", run.protocol_version),
                        ("entry_boundary", run.entry_boundary)):
        declared = manifest.get(key)
        if declared is not None and declared != actual:
            raise FortranBundleError(
                f"manifest {key} {declared!r} != {actual!r} in the C lane's stream")
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
        # DEEP-frozen (owner P1 §8). FortranRun is a frozen dataclass, but its
        # stages/state/precip/fixin/params/localparams were plain mutable dicts, so
        #     leg = verify_fortran_bundle(...)
        #     leg.run.stages[key] = forged
        # left verdict_ready True while the evidence had changed under it. Frozen
        # HERE and not in parse_fortran_run: the parser is also used for ad-hoc
        # analysis and for building mutants, and only this path produces
        # decision-grade evidence.
        variant_source=VariantSourceIdentity(
            algorithm=algorithm,
            canonical_module_sha256=provenance["A"]["module_canonical_sha256"],
            compiled_module_sha256=provenance["A"]["module_compiled_sha256"]),
        run=_freeze_run(run),
        build=build,
        problem=problem,
        bundle_verified=True,
        external_manifest_attested=expected_manifest_sha256 is not None,
        source_commit_attested=expected_repo_commit is not None,
        fixture_attested=bool(expected_fixture_id
                              and expected_fixture_manifest_sha256),
        repo_clean=repo_clean,
    )
