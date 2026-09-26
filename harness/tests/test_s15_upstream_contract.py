from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import s15_upstream_contract as contract


ROOT = Path(__file__).resolve().parents[2]
PROJECTION = ROOT / "harness/evidence/s15_step2_public/s15_upstream_coordinate_projection_2026-09-27.json"
CONFIG = {"rk_order": 3, "adv_opt": "POSITIVEDEF"}


def _records() -> tuple[list[dict], list[dict]]:
    slots = contract.load_coordinate_projection(PROJECTION)
    producers, consumers = [], []
    for slot in slots:
        key = slot["schedule_key"]
        i, j, k = slot["coordinate"]
        ordinary = key[1] < 3
        order = ["y", "x", "z"] if ordinary else ["z", "x", "y"]
        terms = {"y": "3F800000", "x": "BF800000", "z": "40000000"}
        prefixes = ["3F800000", "00000000", "40000000"] if ordinary else [
            "40000000", "3F800000", "40000000"
        ]
        identity = dict(zip(contract.KEY_FIELDS, [*key, i, j, k]))
        producer = {
            **identity,
            "branch": "ordinary" if ordinary else "positive_definite",
            "dispatch": {
                **CONFIG,
                "selected_branch": "ordinary" if ordinary else "positive_definite",
            },
            "face_fluxes": {
                "y": {"minus": "BF800000", "plus": "3F800000"},
                "x": {"minus": "40000000", "plus": "40400000"},
                "z": {"minus": "40800000", "plus": "40A00000"},
            },
            "directional_tendencies": {f"{axis}_tendency": terms[axis] for axis in terms},
            "tendency_order": order,
            "initial_tendency": "00000000",
            "accumulated_tendency": prefixes,
        }
        if not ordinary:
            producer.update({
                "pd_limiter_active": True,
                "pd_scale": "3F000000",
                "pd_flux_out": "3F800000",
                "pd_available_state": "40000000",
                "pd_low_order_fluxes": producer["face_fluxes"],
                "pd_high_order_fluxes": producer["face_fluxes"],
            })
        consumer = {
            **identity,
            "advect_tend": "3F800000", "msfty": "3F800000",
            "sc_tend": "BF800000", "tendency": "00000000",
            "reference": "3F800000", "dt": "41A00000",
            "c1": "00000000", "c2": "3F800000",
            "muold": "3F800000", "munew": "3F800000",
            "rk_store": "3F800000",
        }
        producers.append(producer)
        consumers.append(consumer)
    return producers, consumers


def test_coordinate_projection_has_separate_exact_sha_and_ordered_six_slots() -> None:
    slots = contract.load_coordinate_projection(PROJECTION)
    assert len(slots) == 6
    assert [slot["schedule_key"] for slot in slots] == [list(k) for k in contract.EXPECTED_SCHEDULE]
    with pytest.raises(contract.ContractError, match="SHA-256"):
        contract.load_coordinate_projection(PROJECTION, "0" * 64)


def test_synthetic_records_join_by_full_identity_and_keep_signed_faces() -> None:
    producers, consumers = _records()
    pairs = contract.validate_witnesses(producers, consumers, PROJECTION, CONFIG)
    assert len(pairs) == 6
    assert pairs[0][0]["face_fluxes"]["y"]["minus"] == "BF800000"
    assert pairs[0][1]["sc_tend"] == "BF800000"


@pytest.mark.parametrize("mutation", ["arbitrary_coordinate", "stage_mix", "missing_sc_tend",
                                       "wrong_dispatch", "wrong_source_order"])
def test_synthetic_contract_rejects_coordinate_stage_or_consumer_drift(mutation: str) -> None:
    producers, consumers = _records()
    if mutation == "arbitrary_coordinate":
        producers[0]["i"] = 234
    elif mutation == "stage_mix":
        consumers[0]["rk"] = 2
    elif mutation == "missing_sc_tend":
        consumers[0].pop("sc_tend")
    elif mutation == "wrong_dispatch":
        producers[4]["dispatch"]["selected_branch"] = "ordinary"
    elif mutation == "wrong_source_order":
        producers[0]["accumulated_tendency"] = ["3F800000", "40000000", "40400000"]
    with pytest.raises(contract.ContractError):
        contract.validate_witnesses(producers, consumers, PROJECTION, CONFIG)


@pytest.mark.parametrize("order,expected", [
    (["y", "x", "z"], ["3F800000", "00000000", "40000000"]),
    (["z", "x", "y"], ["40000000", "3F800000", "40000000"]),
])
def test_source_order_accumulation_replays_signed_direction_terms(order: list[str],
                                                                  expected: list[str]) -> None:
    terms = {"y": "3F800000", "x": "BF800000", "z": "40000000"}
    assert contract.source_order_prefixes("00000000", terms, order) == expected
