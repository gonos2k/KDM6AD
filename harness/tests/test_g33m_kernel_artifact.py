#!/usr/bin/env python3
"""The kernel-boundary artifact must say what it is — public CI, no build.

The wrapper-boundary artifact was admissible as a comparison-boundary diagnostic and
nothing more, and the only way to tell was to read the reason string. This one carries
the admissibility facts as fields, so a reader (or a later gate) can check them without
parsing prose.
"""
import json
from pathlib import Path

import pytest

ART = Path(__file__).resolve().parents[1] / "evidence" / "g33m_dt300_kernel_result.json"
KERNEL = "kdm62d_kernel_entry_v1"


@pytest.fixture(scope="module")
def art():
    return json.loads(ART.read_text())


def test_all_four_legs_entered_at_the_kernel(art):
    """The whole point. A wrapper leg compared against the C++ port is evidence about
    the BOUNDARY, not about conservative-interface arithmetic."""
    boundary = art["comparison_boundary"]
    assert set(boundary) == {"legacy_fortran", "legacy_cpp",
                             "conservative_fortran", "conservative_cpp"}
    assert set(boundary.values()) == {KERNEL}, boundary
    # SUPERSEDED: this artifact was produced under a contract that has since been shown
    # defective, so the test asserts its STATUS rather than re-certifying its numbers.
    assert "superseded" in art, (
        "an artifact carrying the pre-PR#88 shape must say so; regenerating it needs four "
        "fresh legs at one revision")


def test_it_is_decision_tier_and_fully_attested(art):
    assert art["evidence_tier"] == "decision"
    assert art["attested"] is True
    assert all(leg["verdict_ready"] for leg in art["attestation"].values())
    assert art["verifier_tree_dirty"] is False, (
        "an artifact stamped from a dirty tree does not describe a reviewable revision")


def test_the_verdict_is_not_overstated(art):
    """The tool's ceiling is PASS_MECHANISM and only from the op ladder. Anything that
    reads as a C4 verdict here would be this harness promoting its own evidence."""
    assert art["verdict"] in ("INCONCLUSIVE", "FAIL", "PASS_MECHANISM",
                              "INVALID_EVIDENCE")
    assert art["verdict"] != "PASS"


def test_both_pairs_first_diverge_at_the_same_place_with_the_same_bits(art):
    """The shared-seed observation, recorded rather than described.

    legacy contains no conservative interface at all, so a divergence it shows too
    cannot have been introduced by that interface. Equal BITS make it the same
    difference and not merely the same location.
    """
    fd = art["first_divergence"]
    leg, con = fd["legacy"], fd["conservative"]
    assert leg is not None and con is not None
    assert leg["identity"] == con["identity"], (leg["identity"], con["identity"])
    assert leg["signature"] == con["signature"], (leg["signature"], con["signature"])


def test_the_sedimentation_result_matched_through_the_diverging_loop(art):
    """The reason must attribute, not just locate. `outer_pre_sed` and `outer_post_sed`
    matching up to the loop where post_micro differs is what makes "born after
    sedimentation" a statement about origin rather than about first sight."""
    assert "born AFTER sedimentation" in art["reason"]
    assert art["first_divergence"]["legacy"]["phase"] == "outer_post_micro"


def test_a_vacuous_carry_row_is_not_accepted_as_proof(art):
    """This test used to require `identical is True` on every bridge — which the L1->L2 row
    satisfies with `records: 0` and the SHA256 of the empty string.

    So the test was pinning the very defect PR #88 identified: a comparison of the two
    backends' DIFFERENCE SETS, vacuous when both are empty. It now refuses an empty row
    outright, which is why this artifact had to be marked superseded rather than
    re-certified — the numbers are what they are and cannot be fixed in place.
    """
    empty = [(algo, name) for algo, bridges in art.get("carry_proof", {}).items()
             for name, b in bridges.items() if b.get("records", 0) == 0]
    if empty:
        assert "superseded" in art, (
            f"vacuous carry rows {empty} in an artifact that does not declare itself "
            f"superseded")
        return
    # a regenerated artifact must carry the intra-backend proof, over the whole state
    proofs = art.get("intra_backend_carry_proof")
    assert proofs, "no intra-backend carry proof"
    for leg, spans in proofs.items():
        for name, row in spans.items():
            assert row["records"] > 0 and row["identical"] is True, f"{leg} {name}"
