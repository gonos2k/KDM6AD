#!/usr/bin/env python3
"""The committed dt=300 result must stay internally consistent (public CI, no build).

The scientific conclusion of the four-case run lived only in a PR comment and a local
path. This pins the decision-relevant summary in the repository, and checks the
properties a reader would otherwise have to take on trust — in particular that the
absolute and relative deltas are not the same numbers wearing different labels, which
is exactly how the first write-up of this result went wrong.
"""
import json
from pathlib import Path

ART = Path(__file__).resolve().parents[1] / "evidence" / "g33m_dt300_result.json"
DOC = json.loads(ART.read_text())


def test_the_verdict_is_recorded_with_its_attestation():
    assert DOC["verdict"] == "INCONCLUSIVE"
    assert DOC["attested"] is True
    assert "born AFTER sedimentation" in DOC["reason"]


def test_both_pairs_diverge_at_the_same_record():
    lf = DOC["first_divergence"]["legacy"]
    cf = DOC["first_divergence"]["conservative"]
    assert lf["phase"] == cf["phase"] == "outer_post_micro"
    assert lf["identity"] == cf["identity"]
    assert lf["signature"] == cf["signature"], (
        "the legacy pair carries no conservative arithmetic, so identical bits in "
        "both pairs is what makes this a legacy-shared difference")


def test_loop_one_sedimentation_is_bit_identical():
    for algo in ("legacy", "conservative"):
        by = DOC["per_algorithm"][algo]["differing_by_loop_and_stage"]
        for stage in ("outer_pre_sed", "substep_pre", "surface", "outer_post_sed"):
            assert by.get(f"L1/{stage}", 0) == 0, f"{algo} L1/{stage}"
        assert by["L1/outer_post_micro"] > 0


def test_the_carry_propagates_exactly():
    # L(n) outer_post_micro -> L(n+1) outer_pre_sed, which is what the bridge asserts
    by = DOC["per_algorithm"]["legacy"]["differing_by_loop_and_stage"]
    for loop in (1, 2):
        assert by[f"L{loop}/outer_post_micro"] == by[f"L{loop + 1}/outer_pre_sed"]


def test_absolute_and_relative_deltas_are_distinct_quantities():
    """The first write-up presented relative differences beside an absolute mass and
    latent closure, which cannot both be true of one set of numbers."""
    for lvl in DOC["condensation_closure"]["levels"]:
        assert abs(lvl["delta_qv_abs_kg_kg"]) < 1e-5, "absolute is a mixing ratio"
        assert abs(lvl["delta_qv_rel"]) > 1e-4, "relative is dimensionless and larger"
        assert lvl["delta_qv_abs_kg_kg"] != lvl["delta_qv_rel"]


def test_mass_closes_and_the_latent_residual_is_reported_not_hidden():
    for lvl in DOC["condensation_closure"]["levels"]:
        # vapour lost equals cloud water gained, to f32 epsilon on a ~6e-7 quantity
        assert abs(lvl["closure_residual_q_kg_kg"]) < 1e-9
        # the temperature residual is NOT zero; it is recorded, with the constants used
        assert lvl["Lv_J_kg"] == 2.5e6 and lvl["cp_J_kg_K"] == 1004.0
        assert 0 < lvl["closure_residual_T_K"] < 1e-4


def test_the_artifact_states_what_it_does_NOT_establish():
    missing = " ".join(DOC["scope"]["not_established"])
    for field in ("nc", "ni", "nccn", "brs"):
        assert field in missing, f"{field} is absent from the bridge and must be said"
    assert "INCONCLUSIVE" in missing
    assert "CONSISTENT" in DOC["condensation_closure"]["note"]
