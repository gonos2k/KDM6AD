"""The claim registry is the authority on status (owner §7.5).

Findings accumulate corrections in place, so a reader cannot tell which sentence
is current — `FINDING_refinement_noise_floor_v1` still says "only the rain-chain
mstep is instrumented" while MSTEPI has been emitted since. A registry only helps
if it cannot itself drift, which is what these check.

Parsed without PyYAML: the file is a fixed, flat shape and the harness has no
third-party dependencies.
"""
import re
from pathlib import Path

import pytest

EVIDENCE = Path(__file__).resolve().parents[1] / "evidence"
REGISTRY = EVIDENCE / "CLAIMS.yaml"
STATUSES = {"active", "superseded", "withdrawn", "hold"}


def _claims():
    """[{id, status, scope, evidence[], superseded_by?}] from the registry.

    Handles `>` block scalars: a key whose value is folded continues on the
    following more-indented lines. Dropping them silently is how `scope` came
    out empty for exactly the claims whose scope needed the most words.
    """
    out, cur, pending = [], None, None
    for line in REGISTRY.read_text().splitlines():
        if re.match(r"^  - id: ", line):
            cur = {"id": line.split("id:", 1)[1].strip(), "evidence": []}
            out.append(cur)
            pending = None
        elif cur is not None and (m := re.match(r"^    (\w+): (.*)$", line)):
            key, val = m.group(1), m.group(2).strip()
            pending = None
            if key == "evidence_sha256":
                cur["evidence_sha256"] = dict(
                    t.split(":") for t in
                    re.findall(r"[\w.]+\.md:[0-9a-f]+", val))
            elif key == "evidence":
                cur["evidence"] = re.findall(r"[\w.]+\.md", val)
            elif val in (">", "|"):
                cur[key], pending = "", key      # folded: body follows
            else:
                cur[key] = val
        elif cur is not None and re.match(r"^      \S", line):
            if pending:
                cur[pending] = (cur[pending] + " " + line.strip()).strip()
            cur["evidence"] += re.findall(r"[\w.]+\.md", line)
    return out


CLAIMS = _claims()


def test_the_registry_parses_and_is_not_empty():
    assert len(CLAIMS) >= 10
    assert all(c["id"] for c in CLAIMS)


def test_claim_ids_are_unique():
    ids = [c["id"] for c in CLAIMS]
    assert len(ids) == len(set(ids))


def test_every_status_is_one_of_the_declared_states():
    for c in CLAIMS:
        assert c.get("status") in STATUSES, f"{c['id']}: {c.get('status')}"


def test_every_claim_names_evidence_that_exists():
    """A registry pointing at a document nobody wrote is worse than none."""
    for c in CLAIMS:
        assert c["evidence"], f"{c['id']} cites no evidence"
        for doc in c["evidence"]:
            assert (EVIDENCE / doc).exists(), f"{c['id']} cites missing {doc}"


def test_every_superseded_by_resolves_to_an_active_claim():
    by_id = {c["id"]: c for c in CLAIMS}
    for c in CLAIMS:
        nxt = c.get("superseded_by")
        if nxt is None:
            continue
        assert nxt in by_id, f"{c['id']} -> unknown {nxt}"
        assert by_id[nxt]["status"] == "active", \
            f"{c['id']} is superseded by {nxt}, which is not active"


def test_a_withdrawn_claim_must_say_what_replaced_it_or_stand_alone():
    """Withdrawing without a successor is allowed, but it must be deliberate:
    the pairs here all have one, and a new withdrawal without one should be a
    conscious edit to this test rather than an omission."""
    for c in CLAIMS:
        if c.get("status") == "withdrawn":
            assert "superseded_by" in c, f"{c['id']} withdrawn with no successor"


def test_every_claim_pins_the_DIGEST_of_its_evidence():
    """A registry that names a file binds nothing: the file can change under it.
    The digest is what makes a claim's evidence identifiable (owner §10.4)."""
    import hashlib
    for c in CLAIMS:
        pinned = c.get("evidence_sha256")
        assert pinned, f"{c['id']} pins no evidence digest"
        for doc in c["evidence"]:
            assert doc in pinned, f"{c['id']} cites {doc} without a digest"
            got = hashlib.sha256((EVIDENCE / doc).read_bytes()).hexdigest()[:16]
            assert pinned[doc] == got, (
                f"{c['id']}: {doc} has changed since the claim was pinned "
                f"({pinned[doc]} -> {got}). Re-read the claim, then re-pin.")


def test_every_claim_declares_a_scope():
    """The recurring defect this registry exists for is a fixture-scoped result
    quoted as a general one."""
    for c in CLAIMS:
        assert c.get("scope"), f"{c['id']} declares no scope"


@pytest.mark.parametrize("cid,expect", [
    ("G33-TURNOVER-001", "withdrawn"),      # roundoff attribution, owner P0-5
    ("G33-TURNOVER-002", "active"),
    ("G33-WATER-ORDER-001", "withdrawn"),   # mstep explains column-3 water
    ("G33-PRECIP-002", "withdrawn"),        # conservative enthalpy advantage
    ("G33-NUMBER-002", "active"),           # 6-14%, conditional
    # was hold/predicted; now measured on both arms, identical to the last digit
    ("G33-NUMBER-003", "active"),
])
def test_the_corrections_this_review_required_are_recorded(cid, expect):
    got = next((c for c in CLAIMS if c["id"] == cid), None)
    assert got is not None, f"{cid} missing from the registry"
    assert got["status"] == expect


# ---- owner §10: the narrative may not drift from the registry ---------------

def test_every_finding_carries_the_registry_verdict_and_it_is_current():
    """Declaring the registry authoritative did not stop a grade table in
    FINDING_column_water_orders_v1 saying "turnover is roundoff — confirmed" for
    two commits after the registry had withdrawn exactly that. The verdict is now
    stamped into each finding, and this fails when it goes stale."""
    import sys
    sys.path.insert(0, str(EVIDENCE.parent))
    import g33_claim_header as ch
    assert ch.stamp(check=True) == 0, "run harness/g33_claim_header.py"


def test_the_conservative_arm_is_measured_not_predicted():
    """It stood as predicted/unmeasured until the overlay gained per-algorithm
    anchors; the conservative update statements differ, so the legacy anchors did
    not exist in it (owner §11)."""
    c = next(c for c in CLAIMS if c["id"] == "G33-NUMBER-003")
    assert c["status"] == "active" and c["grade"] == "confirmed"
    assert "measurement" in c["basis"]


def test_a_withdrawn_claim_is_superseded_by_the_answer_to_ITS_question():
    """G33-NUMBER-006 (ice closure measures the ice defect) pointed at the
    MAIN-chain result. The claim that actually answers it is the ice cap
    explanation (owner §9.3)."""
    by_id = {c["id"]: c for c in CLAIMS}
    assert by_id["G33-NUMBER-006"]["superseded_by"] == "G33-ICE-CAP-001"
