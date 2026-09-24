"""Independent expected-event manifests versus measured/derived/synthetic data."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))
from evidence_spec import (  # noqa: E402
    EvidenceTier, ExpectedEvidence, EvidenceRecord, EvidencePlan, audit_evidence,
)


SOURCE = "a" * 64
PAYLOAD = "b" * 64


def _plan():
    return EvidencePlan("independent_case", (
        ExpectedEvidence((1, "D2_PRE"), EvidenceTier.MEASURED,
                         source_sha256=SOURCE, payload_sha256=PAYLOAD),
        ExpectedEvidence((1, "budget"), EvidenceTier.DERIVED,
                         parents=((1, "D2_PRE"),)),
        ExpectedEvidence(("toy", "counterexample"), EvidenceTier.SYNTHETIC,
                         generator_id="fixed_two_cell_v1"),
    ))


def _records():
    return (
        EvidenceRecord((1, "D2_PRE"), EvidenceTier.MEASURED,
                       source_sha256=SOURCE, payload_sha256=PAYLOAD),
        EvidenceRecord((1, "budget"), EvidenceTier.DERIVED,
                       parents=((1, "D2_PRE"),)),
        EvidenceRecord(("toy", "counterexample"), EvidenceTier.SYNTHETIC,
                       generator_id="fixed_two_cell_v1"),
    )


def test_independent_plan_keeps_three_provenance_tiers_distinct():
    result = audit_evidence(_plan(), _records())
    assert (result.measured, result.derived, result.synthetic) == (1, 1, 1)
    assert result.scope == "manifest_consistency_only"


def test_missing_extra_duplicate_and_wrong_tier_are_rejected():
    expected = _plan()
    rows = _records()
    with pytest.raises(ValueError, match="missing or unexpected"):
        audit_evidence(expected, rows[:-1])
    with pytest.raises(ValueError, match="duplicate observed"):
        audit_evidence(expected, rows + (rows[0],))
    with pytest.raises(ValueError, match="missing or unexpected"):
        audit_evidence(expected, rows + (
            EvidenceRecord(("extra",), EvidenceTier.SYNTHETIC, generator_id="other"),))
    wrong = list(rows)
    wrong[0] = EvidenceRecord((1, "D2_PRE"), EvidenceTier.SYNTHETIC,
                              generator_id="fabricated")
    with pytest.raises(ValueError, match="tier, ancestry"):
        audit_evidence(expected, tuple(wrong))


def test_source_payload_parent_and_generator_changes_are_rejected():
    rows = list(_records())
    for replacement in (
        EvidenceRecord(rows[0].key, EvidenceTier.MEASURED,
                       source_sha256="c" * 64, payload_sha256=PAYLOAD),
        EvidenceRecord(rows[0].key, EvidenceTier.MEASURED,
                       source_sha256=SOURCE, payload_sha256="c" * 64),
    ):
        with pytest.raises(ValueError, match="tier, ancestry"):
            audit_evidence(_plan(), (replacement, *rows[1:]))
    wrong_derived = EvidenceRecord(rows[1].key, EvidenceTier.DERIVED,
                                   parents=(("toy", "counterexample"),))
    with pytest.raises(ValueError, match="tier, ancestry"):
        audit_evidence(_plan(), (rows[0], wrong_derived, rows[2]))
    wrong_synthetic = EvidenceRecord(rows[2].key, EvidenceTier.SYNTHETIC,
                                     generator_id="result_selected_after_viewing")
    with pytest.raises(ValueError, match="tier, ancestry"):
        audit_evidence(_plan(), (rows[0], rows[1], wrong_synthetic))


def test_invalid_expected_parent_order_and_source_contract_reject():
    with pytest.raises(ValueError, match="parent must precede"):
        audit_evidence(EvidencePlan("wrong", (
            ExpectedEvidence(("derived",), EvidenceTier.DERIVED,
                             parents=(("measured",),)),
            ExpectedEvidence(("measured",), EvidenceTier.MEASURED,
                             source_sha256=SOURCE),
        )), ())
    with pytest.raises(ValueError, match="source digest"):
        audit_evidence(EvidencePlan("wrong", (
            ExpectedEvidence(("m",), EvidenceTier.MEASURED,
                             source_sha256="not-a-sha"),
        )), ())


def test_fixed_native_case_still_replays_through_common_manifest_validator():
    import json
    from replay_phase_native import replay

    data = json.loads((Path(__file__).resolve().parents[2]
                       / "harness/evidence/native_phase_event_2026-09-24.json").read_text())
    assert replay(data)["native_runs_reported"] == 2
