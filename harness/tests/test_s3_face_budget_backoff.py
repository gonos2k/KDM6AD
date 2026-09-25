import json
import sys
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from s3_face_budget_backoff import (
    Cell,
    SharedFace,
    _face_numerator_contribution,
    backoff_donor,
)


EVIDENCE = Path(__file__).parents[1] / "evidence/number_face_flux_2026-09-24.json"


def _captured_cell(variant, target=5, step=2):
    data = json.loads(EVIDENCE.read_text())["variants"][variant]
    row = next(
        r
        for r in data["flux"]
        if r[0] == "POST" and r[1] == step and r[5] == target
    )
    values = row[9:]
    field, i, k, j = {
        5: ("QNCLOUD", 233, 12, 124),
    }[target]
    event = next(
        e
        for e in data["events"]
        if e.get("record_kind") == "RK_OPERAND"
        and (e["step"], e["rk"], e["stage"], e["field"], e["i"], e["k"], e["j"])
        == (step, 3, "RK_BEFORE", field, i, k, j)
    )
    rk = dict(
        old=event["scalar_old"],
        rk=3,
        value=event["value"],
        mu_old=event["mu1"],
        mu_new=event["mu2"],
        mu_base=event["mub"],
        c1=event["c1h"],
        c2=event["c2h"],
        advect_tend=event["advect_tend"],
        msfty=event["msfty"],
        sc_tend=event["scalar_tend"],
        dt=event["dt_rk"],
        i=event["i"],
        j=event["j"],
    )
    return Cell(
        high=tuple(values[17:23]),
        low=tuple(values[23:29]),
        initial_tendency=values[2],
        rdzw=values[12],
        msftx=values[8],
        rdx=values[10],
        rdy=values[11],
        rk=rk,
    )


def _receiver(donor, shared_slots, *, source=0.0):
    high = [0.0] * 6
    low = [0.0] * 6
    for donor_slot, receiver_slot in shared_slots:
        high[receiver_slot] = donor.high[donor_slot]
        low[receiver_slot] = donor.low[donor_slot]
    rk = dict(donor.rk)
    rk.update(old=1.0, value=1.0, sc_tend=source, i=232)
    return Cell(
        high=tuple(high),
        low=tuple(low),
        initial_tendency=0.0,
        rdzw=donor.rdzw,
        msftx=donor.msftx,
        rdx=donor.rdx,
        rdy=donor.rdy,
        rk=rk,
    )


def _complete_neighborhood(donor, *, starved_slot=None):
    opposite = {0: 1, 1: 0, 2: 3, 3: 2, 4: 5, 5: 4}
    outgoing = (0, 1, 2, 3)
    cells = [donor]
    shared = []
    for slot in outgoing:
        receiver_slot = opposite[slot]
        source = -1.0e12 if slot == starved_slot else 0.0
        cells.append(_receiver(donor, ((slot, receiver_slot),), source=source))
        shared.append(SharedFace(0, slot, len(cells) - 1, receiver_slot))
    return tuple(cells), tuple(shared)


@pytest.mark.parametrize("variant", ["original", "normalized"])
def test_recorded_final_rk_store_backoffs_without_clipping_or_changing_shared_faces(variant):
    donor = _captured_cell(variant)
    cells, shared = _complete_neighborhood(donor)
    result = backoff_donor(cells, shared, donor=0)

    assert result.accepted and result.reason == "backed_off"
    assert 0.0 < result.factor < 1.0
    assert result.before[0] < 0.0 <= result.after[0]
    assert all(value >= 0.0 for value in result.after)
    assert result.high_faces is not None
    total_face_numerator_change = Fraction(0)
    for face in shared:
        assert result.high_faces[face.donor][face.donor_slot] == (
            result.high_faces[face.receiver][face.receiver_slot]
        )
        assert cells[face.donor].low[face.donor_slot] == (
            cells[face.receiver].low[face.receiver_slot]
        )
        face_change = (result.high_faces[face.donor][face.donor_slot]
                       - donor.high[face.donor_slot])
        total_face_numerator_change += _face_numerator_contribution(
            donor, face.donor_slot, face_change
        ) + _face_numerator_contribution(
            cells[face.receiver], face.receiver_slot, face_change
        )
    assert total_face_numerator_change == Fraction(0)


def test_candidate_rejects_incomplete_receiver_topology():
    donor = _captured_cell("normalized")
    receiver_x = _receiver(donor, ((0, 1),))
    receiver_y = _receiver(donor, ((2, 3),))
    shared = (SharedFace(0, 0, 1, 1), SharedFace(0, 2, 2, 3))
    result = backoff_donor((donor, receiver_x, receiver_y), shared, donor=0)

    assert not result.accepted
    assert result.reason == "unpaired_outgoing_face"
    assert result.high_faces is None


def test_candidate_rejects_when_connected_receiver_cannot_accept_any_reduced_face():
    donor = _captured_cell("normalized")
    cells, shared = _complete_neighborhood(donor, starved_slot=0)
    result = backoff_donor(cells, shared, donor=0)

    assert not result.accepted
    assert result.factor is not None and result.factor > 0.0
    assert result.reason == "connected_receiver_budget_negative"
    assert result.before[1] < 0.0 and result.after[1] < 0.0
    assert result.high_faces is None


def test_candidate_rejects_unequal_metric_weight_on_a_shared_face():
    donor = _captured_cell("normalized")
    cells, shared = _complete_neighborhood(donor)
    altered = list(cells)
    altered[1] = replace(altered[1], msftx=altered[1].msftx * 2.0)

    with pytest.raises(ValueError, match="incompatible metric-weighted RK exchange"):
        backoff_donor(tuple(altered), shared, donor=0)
