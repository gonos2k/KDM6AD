#!/usr/bin/env python3
"""The ONE way to load four legs for a G3.3-M decision.

Two consumers need the four-case evidence: the gate CLI, which adjudicates it, and the
evidence-artifact generator, which summarizes it. They had two independent loaders, and
the generator's was the weaker one — it read the C++ bundle without external anchors,
parsed the Fortran C-lane stdout directly with no bundle verification or attestation,
copied the verdict out of a previous run's result.json, and recomputed the first
divergence from `stages` alone.

That last one is the dangerous part. The comparator's first divergence ranges over the
op ladder as well as the snapshots, so once the comparison boundary is aligned and the
earliest difference moves INTO the ladder, the two answers separate: the comparator
reports an op, the artifact reports a later stage. Both would be published, and the
artifact is the document a reader trusts.

So there is one loader. It returns verified ARTIFACTS — never normalized dicts on their
own — and the caller gets the verdict from `adjudicate_verified`, which is the only
thing that has seen the attestation.
"""
from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import g33_bundle_io as bio            # noqa: E402
import g33_fortran_bundle_io as fbio   # noqa: E402
import g33_fourcase_comparator as cmp  # noqa: E402
import g33_normalize as nz             # noqa: E402

ALGORITHMS = ("legacy", "conservative")

#: Every error class that means "the EVIDENCE is bad", as opposed to "this harness has
#: a defect". A blanket except would turn a TypeError here into INVALID_EVIDENCE, which
#: reads as a verdict about the bundle and sends the reader to look at the wrong thing.
EVIDENCE_ERRORS = (bio.BundleError, fbio.FortranBundleError, nz.NormalizeError,
                   cmp.StructuralError, bio.gfx.UnknownFixture,
                   OSError, ValueError, KeyError)


@dataclass(frozen=True)
class LoadedFourCase:
    """Four verified legs and everything derived from them.

    `evidence` is present only for an anchored load: VerifiedFourCase.of() is the
    decision type, and building it from unanchored legs would produce an object whose
    name claims more than was checked.
    """
    fixture_id: str
    authority: dict
    fixture_identity: dict
    cpp_legs: dict            # algo -> VerifiedCppLeg
    fortran_legs: dict        # algo -> VerifiedFortranLeg
    normalized: dict          # "{algo}_{backend}" -> normalized run
    gate_a: dict | None
    anchored: bool
    evidence: object | None   # cmp.VerifiedFourCase, anchored loads only

    @property
    def attestation(self) -> dict:
        """What the LEGS reported, per leg — not what the caller asked for."""
        per_leg = {f"{algo}_cpp": self.cpp_legs[algo] for algo in ALGORITHMS}
        per_leg.update({f"{algo}_fortran": leg
                        for algo, leg in self.fortran_legs.items()})
        return {name: {"verdict_ready": bool(leg.verdict_ready),
                       "external_manifest": bool(leg.external_manifest_attested),
                       "source_commit": bool(leg.source_commit_attested),
                       "fixture": bool(leg.fixture_attested)}
                for name, leg in sorted(per_leg.items())}

    @property
    def attested(self) -> bool:
        return all(e["verdict_ready"] for e in self.attestation.values())

    def verdict(self) -> dict:
        """The verdict, from the path that matches what was actually attested."""
        if self.evidence is not None:
            return cmp.adjudicate_verified(self.evidence)
        return cmp.adjudicate_unattested(
            self.normalized["legacy_fortran"], self.normalized["legacy_cpp"],
            self.normalized["conservative_fortran"],
            self.normalized["conservative_cpp"])


def _load_fortran(bundle_dir, algo, *, manifest_sha, commit, fixture_id, fixture_sha,
                  anchored):
    leg = fbio.verify_fortran_bundle(
        bundle_dir, algo, expected_manifest_sha256=manifest_sha,
        expected_repo_commit=commit, expected_fixture_id=fixture_id,
        expected_fixture_manifest_sha256=fixture_sha)
    # The C++ normalizer refuses an unattested leg itself (require_verdict_ready);
    # the Fortran one has no such argument, so the equivalent refusal is here. Without
    # it an anchored load would accept a Fortran leg that failed its own attestation
    # while holding the C++ legs to theirs.
    if anchored and not leg.verdict_ready:
        raise fbio.FortranBundleError(
            f"{algo} Fortran leg is not verdict_ready "
            f"(bundle_verified={leg.bundle_verified} "
            f"manifest={leg.external_manifest_attested} "
            f"commit={leg.source_commit_attested} "
            f"fixture={leg.fixture_attested} clean={leg.repo_clean} "
            f"protocol_v={getattr(leg.run, 'protocol_version', None)})")
    return leg, nz.from_fortran_run(leg.run)


def load_verified_fourcase(
        *, cpp_bundle: Path, fortran_legacy: Path, fortran_conservative: Path,
        expected_manifest_sha256=None, expected_repo_commit=None,
        expected_fixture_id=None, expected_fixture_manifest_sha256=None,
        expected_fortran_legacy_manifest_sha256=None,
        expected_fortran_conservative_manifest_sha256=None,
        gate_a_scope_report: Path | None = None,
        expected_gate_a_scope_report_sha256=None) -> LoadedFourCase:
    """Load, verify and pair the four legs. Raises on unusable evidence.

    "Anchored" means all six external anchors were supplied. It is a property of the
    LOAD, not a request: an anchored load additionally requires Gate A and builds the
    decision type; an unanchored one is for debugging and cannot promote.
    """
    anchored = all((expected_manifest_sha256, expected_repo_commit,
                    expected_fixture_id, expected_fixture_manifest_sha256,
                    expected_fortran_legacy_manifest_sha256,
                    expected_fortran_conservative_manifest_sha256))
    fixture_id = expected_fixture_id or bio.gfx.DEFAULT_FIXTURE_ID
    # (B, K) are a PROPERTY of the fixture. Taken as separate arguments they could
    # disagree with the fixture actually named.
    _, authority = bio.gfx.load_fixture(fixture_id)

    cpp = bio.verify_cpp_bundle(
        cpp_bundle, expected_manifest_sha256=expected_manifest_sha256,
        expected_repo_commit=expected_repo_commit,
        expected_fixture_id=fixture_id,
        expected_fixture_manifest_sha256=expected_fixture_manifest_sha256)
    cpp_legs = cpp["algorithms"]
    normalized = {
        f"{algo}_cpp": nz.from_cpp_evidence(cpp_legs[algo],
                                            require_verdict_ready=anchored)
        for algo in ALGORITHMS}

    fortran_legs = {}
    for algo, bundle_dir, sha in (
            ("legacy", fortran_legacy, expected_fortran_legacy_manifest_sha256),
            ("conservative", fortran_conservative,
             expected_fortran_conservative_manifest_sha256)):
        fortran_legs[algo], normalized[f"{algo}_fortran"] = _load_fortran(
            bundle_dir, algo, manifest_sha=sha, commit=expected_repo_commit,
            fixture_id=expected_fixture_id,
            fixture_sha=expected_fixture_manifest_sha256, anchored=anchored)

    # Gate A is a DECISION PREREQUISITE, not an option. Excluding the variant module
    # from the toolchain comparison is what lets the two legs differ there;
    # authorizing WHICH conservative source may differ is a separate fact, and a
    # decision that skips it has not established it.
    gate_a = None
    if gate_a_scope_report is not None:
        got = hashlib.sha256(Path(gate_a_scope_report).read_bytes()).hexdigest()
        if expected_gate_a_scope_report_sha256 not in (None, got):
            raise fbio.FortranBundleError(
                f"Gate A report sha256 {got} != external anchor "
                f"{expected_gate_a_scope_report_sha256}")
        if anchored and expected_gate_a_scope_report_sha256 is None:
            raise fbio.FortranBundleError(
                "a decision-grade run needs --expected-gate-a-scope-report-sha256: "
                "a report checked only against itself attests nothing")
        gate_a = bio._load_json(Path(gate_a_scope_report), "Gate A scope report")
        fbio.authorized_by_gate_a(gate_a, fortran_legs)
    elif anchored:
        raise fbio.FortranBundleError(
            "a decision-grade run needs --gate-a-scope-report: allowing the two legs "
            "to compile different modules is not authorizing one")

    # The two Fortran CONTROL legs must come from one TOOLCHAIN. Built by different
    # compilers or from different sources they are not a controlled pair, and nothing
    # in the four-way problem identity would show it. Compared at toolchain() and not
    # on the whole BuildIdentity: legacy compiles module_mp_kdm6.F and conservative
    # module_mp_kdm6_cons.F, so their module hashes MUST differ — that difference is
    # the comparison. The full identity is still enforced WITHIN each bundle's lanes.
    builds = {algo: leg.build for algo, leg in fortran_legs.items()}
    if len({b.toolchain() for b in builds.values()}) != 1:
        raise fbio.FortranBundleError(
            "the Fortran legs were not built from one toolchain: "
            + ", ".join(f"{algo}={b.compiler_version}/{b.compiler_binary_sha256[:12]}"
                        for algo, b in sorted(builds.items())))

    evidence = None
    if anchored:
        # The factory normalizes each VERIFIED ARTIFACT itself. Handing it the runs
        # loaded above would re-open the hole the factory exists to close: the
        # artifact carries the attestation, the dict carries the numbers, and nothing
        # ties the two together.
        evidence = cmp.VerifiedFourCase.of(
            legacy_fortran=fortran_legs["legacy"], legacy_cpp=cpp_legs["legacy"],
            conservative_fortran=fortran_legs["conservative"],
            conservative_cpp=cpp_legs["conservative"],
            gate_a_report=gate_a, require_source_authorization=True)

    return LoadedFourCase(
        fixture_id=fixture_id, authority=authority,
        fixture_identity={
            "fixture_id": authority["fixture_id"],
            "fixture_manifest_sha256": bio.gfx.manifest_sha256(authority),
            "fixture_sha256": bio.gfx.fixture_sha256(authority),
            "parameter_sha256": bio.gfx.parameter_sha256(authority),
            "fortran_parameter_sha256": bio.gfx.fortran_parameter_sha256(authority)},
        cpp_legs=cpp_legs, fortran_legs=fortran_legs, normalized=normalized,
        gate_a=gate_a, anchored=anchored, evidence=evidence)
