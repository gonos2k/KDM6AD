#!/usr/bin/env python3
"""The committed dt=300 result must stay internally consistent (public CI, no build).

The scientific conclusion of the four-case run lived only in a PR comment and a local
path. This pins the decision-relevant summary in the repository and checks the
properties a reader would otherwise take on trust — in particular the two that earlier
versions of this artifact got wrong: the carry was proven by COUNTING differing
records, and the absolute and relative deltas were presented as if interchangeable.
"""
import json
from pathlib import Path

ART = Path(__file__).resolve().parents[1] / "evidence" / "g33m_dt300_result.json"
DOC = json.loads(ART.read_text())


def test_the_artifact_is_generated_not_hand_written():
    # a summary nobody can regenerate from the bundles is a claim, not evidence
    assert DOC["generated_by"] == "harness/make_g33m_evidence_artifact.py"
    assert DOC["schema_version"] >= 2
    assert DOC["verifier_tree_dirty"] is False, (
        "a committed artifact must be produced from a tree its commit describes")


def test_the_verdict_is_recorded_with_its_attestation():
    assert DOC["verdict"] == "INCONCLUSIVE"
    assert DOC["attested"] is True


def test_both_pairs_diverge_at_the_same_record():
    lf = DOC["first_divergence"]["legacy"]
    cf = DOC["first_divergence"]["conservative"]
    assert lf["identity"] == cf["identity"]
    assert (lf["f_bits"], lf["c_bits"]) == (cf["f_bits"], cf["c_bits"]), (
        "the legacy pair carries no conservative arithmetic, so identical bits in "
        "both pairs is what makes this a legacy-shared difference")


def test_the_first_divergence_is_upstream_of_sedimentation():
    """v5 records all twelve carried state members. With nc/ni/nccn/brs observed, the
    difference is already present at loop 1's sedimentation ENTRY — which the
    eight-field v4 bridge could not see, and which is why the earlier attribution to
    the microphysics had to be withdrawn."""
    ident = DOC["first_divergence"]["legacy"]["identity"]
    assert ident[0] == "outer_pre_sed" and ident[1] == 1
    assert ident[-1] == "nccn"


def test_the_carry_is_proven_by_identity_and_bits_not_by_counting():
    """Equal COUNTS of entirely different cells passed the previous check."""
    for algo, spans in DOC["carry_proof"].items():
        assert spans, algo
        for span, v in spans.items():
            assert v["identical"] is True, f"{algo} {span}"
            assert v["post_micro_digest"] == v["pre_sed_digest"], f"{algo} {span}"
            assert len(v["post_micro_digest"]) == 64


def test_absolute_and_relative_deltas_are_distinct_quantities():
    for lvl in DOC["condensation_closure"]["levels"]:
        assert abs(lvl["delta_qv_abs_kg_kg"]) < 1e-5, "absolute is a mixing ratio"
        assert abs(lvl["delta_qv_rel"]) > 1e-4, "relative is dimensionless and larger"
        assert lvl["delta_qv_abs_kg_kg"] != lvl["delta_qv_rel"]


def test_the_latent_residual_is_reported_as_a_diagnostic_not_a_bound():
    note = DOC["condensation_closure"]["note"]
    assert "CONSTANTS" in note and "not a bound" in note
    assert "CONSISTENT" in note
    for lvl in DOC["condensation_closure"]["levels"]:
        assert lvl["Lv_J_kg"] == 2.5e6 and lvl["cp_J_kg_K"] == 1004.0


def test_every_bundle_and_the_gate_a_report_are_pinned():
    assert len(DOC["cpp_manifest_sha256"]) == 64
    assert len(DOC["gate_a_report_sha256"] or "") == 64
    for algo in ("legacy", "conservative"):
        per = DOC["per_algorithm"][algo]
        assert len(per["fortran_manifest_sha256"]) == 64
        assert len(per["differing_digest"]) == 64
        assert per["probe_lineage"]["diagnostic_driver_sha256"]
