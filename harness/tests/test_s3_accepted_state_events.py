import json
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from s3_accepted_state_events import (
    FACE_ORDER,
    HOST_MODULE_EM_OBJECT_SHA256,
    SCHEMA,
    SOURCE_HASHES,
    _first_qn_candidate,
    _replay_advect_scalar_yxz,
    attribute_event,
    first_qn_candidate,
)
from replay_negative_number_trace import rk_value


EVIDENCE = Path(__file__).parents[1] / "evidence/number_face_flux_2026-09-24.json"


def _word(value):
    return "0x" + struct.pack("!f", value).hex()


def _f32(value):
    return struct.unpack("!f", struct.pack("!f", value))[0]


def _raw_event(*, x_right=2.0, y_south=0.0, y_north=0.0, z_top=0.0,
               value_before=1.0, rk=1, state_class="solver_internal"):
    checkpoint, producer = {
        "solver_internal": ("RK_AFTER", "rk_update_scalar"),
        "model_step_accepted": ("STEP_ACCEPTED", "step_acceptance_scan"),
    }[state_class]
    identity = {
        "field": "QNCLOUD", "species": 3, "step": 2, "rk": rk,
        "rank": 0, "tile": 1, "i": 46, "k": 1, "j": 2,
    }
    event = {
        "schema": SCHEMA,
        "source_hashes": SOURCE_HASHES,
        "layout": {"mpi_ranks": 1, "threads": 1, "tiles": 1},
        "state_class": state_class,
        "checkpoint": checkpoint,
        "producer": producer,
        "copy_only": False,
        "identity": identity,
        "rk": rk,
        "value_before_bits": _word(value_before),
        "value_after_bits": _word(-1.0),
        "native_build_sha256": "a" * 64,
        "module_em_object_sha256": HOST_MODULE_EM_OBJECT_SHA256,
        "control_history_sha256": "b" * 64,
        "capture_history_sha256": "b" * 64,
    }
    if state_class == "model_step_accepted":
        event.pop("value_before_bits")
        event.pop("limiter", None)
        event.pop("face_flux_bits", None)
        event.pop("metric_bits", None)
        event.pop("rk_bits", None)
        return event
    flux = dict.fromkeys(FACE_ORDER, _word(0.0))
    flux["xR"] = _word(x_right)
    flux["yS"] = _word(y_south)
    flux["yN"] = _word(y_north)
    flux["zT"] = _word(z_top)
    tendency = _f32(0.0)
    tendency = _f32(tendency - _f32(_f32(y_north - y_south)))
    tendency = _f32(tendency - _f32(_f32(x_right)))
    tendency = _f32(tendency - _f32(_f32(z_top)))
    event["value_after_bits"] = _word(_f32(value_before + tendency))
    event.update(
        limiter="none_at_this_stage",
        advection_orders={"horizontal": 5, "vertical": 3},
        face_flux_bits=flux,
        metric_bits={name: _word(1.0) for name in ("msftx", "msfty", "rdx", "rdy", "rdzw", "dt")},
        rk_bits={
            "c1": _word(0.0), "c2": _word(1.0), "mu_old": _word(0.0),
            "mu_new": _word(0.0), "mu_base": _word(0.0),
            "scalar_tend": _word(0.0), "observed_advect_tend": _word(tendency),
        },
    )
    return event


def _g2_data():
    return json.loads(EVIDENCE.read_text())


@pytest.mark.parametrize("variant, expected", [("original", -243.41905212402344),
                                                ("normalized", -243.55775451660156)])
def test_g2_scan_pins_first_rk1_qn_candidate_for_face_capture(variant, expected):
    candidate = first_qn_candidate(str(EVIDENCE), variant)

    assert (candidate.field, candidate.step, candidate.rk) == ("QNCLOUD", 2, 1)
    assert (candidate.i, candidate.k, candidate.j) == (46, 1, 2)
    assert candidate.before == 0.0
    assert candidate.after == expected
    assert candidate.state_class == "solver_internal"


def test_candidate_reader_rejects_impossible_tile_census_at_any_prior_checkpoint():
    data = _g2_data()
    row = next(r for r in data["variants"]["original"]["summaries"]
               if (r["step"], r["rk"], r["stage"], r["field"], r["tile"])
               == (1, 1, "RK_AFTER", "QNCLOUD", 1))
    row["owned"] -= 1

    with pytest.raises(ValueError, match="tile geometry/census mismatch"):
        _first_qn_candidate(data, "original")


def test_candidate_reader_rejects_out_of_tile_transition_coordinate():
    data = _g2_data()
    row = next(r for r in data["variants"]["normalized"]["summaries"]
               if (r["step"], r["rk"], r["stage"], r["field"], r["tile"])
               == (2, 1, "RK_AFTER", "QNCLOUD", 1))
    row["first_new_j"] = 143

    with pytest.raises(ValueError, match="outside its declared owner tile"):
        _first_qn_candidate(data, "normalized")


def test_candidate_reader_rejects_wrong_target_field_identity():
    data = _g2_data()
    row = next(r for r in data["variants"]["original"]["summaries"]
               if (r["step"], r["rk"], r["stage"], r["field"], r["tile"])
               == (2, 1, "RK_AFTER", "QNCLOUD", 1))
    row["selected"] = 6

    with pytest.raises(ValueError, match="candidate owner/field identity mismatch"):
        _first_qn_candidate(data, "original")


def test_file_reader_rejects_mutated_evidence_bytes(tmp_path):
    data = _g2_data()
    data["variants"]["original"]["summaries"][0]["owned"] = 1
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(data))

    with pytest.raises(ValueError, match="evidence bytes"):
        first_qn_candidate(str(changed), "original")


def test_raw_face_fluxes_reconstruct_the_rk1_face_pair_crossing():
    result = attribute_event(_raw_event())

    assert result.status == "UNVERIFIED_RECEIPT"
    assert result.cause == "native_receipt_not_externally_pinned"
    assert result.replay_group == "x_pair"
    assert result.rk_numerator == -1
    assert result.accepted_value == -1.0


def test_y_then_x_face_replay_preserves_a_half_ulp_x_remainder():
    large = float(2**24)
    y_prefix = large + 2.0
    flux = {"yS": y_prefix, "yN": 0.0, "xL": 0.0, "xR": 1.0, "zB": 0.0, "zT": large}
    metrics = dict.fromkeys(("msftx", "msfty", "rdx", "rdy", "rdzw", "dt"), 1.0)
    tendency, prefixes = _replay_advect_scalar_yxz(flux, metrics)

    assert prefixes["y_pair"] == y_prefix
    assert prefixes["x_pair"] == large  # f32((2**24 + 2) - 1) ties back to 2**24.
    assert prefixes["z_pair"] == 0.0
    assert tendency == 0.0
    assert rk_value({
        "old": 1.0, "rk": 1, "value": 1.0, "mu_old": 0.0,
        "mu_new": 0.0, "mu_base": 0.0, "c1": 0.0, "c2": 1.0,
        "advect_tend": tendency, "msfty": 1.0, "sc_tend": 0.0,
        "dt": 1.0, "i": 46, "j": 2,
    }) == 1.0

    # Reversing the first two directional updates creates a distinct prefix:
    # X stores -1 before Y's +(2**24 + 2) term swallows it at the half-ULP tie.
    reversed_first = _f32(0.0 - _f32(flux["xR"] - flux["xL"]))
    reversed_after_y = _f32(reversed_first - _f32(flux["yN"] - flux["yS"]))
    assert reversed_first == -1.0
    assert reversed_after_y == large


def test_y_x_z_prefix_identifies_the_crossing_after_mixed_axis_cancellation():
    result = attribute_event(_raw_event(x_right=1.2, y_south=0.5, z_top=0.4))

    assert result.status == "UNVERIFIED_RECEIPT"
    assert result.replay_group == "z_pair"


def test_missing_raw_face_operand_fails_closed():
    event = _raw_event()
    del event["face_flux_bits"]["zT"]

    with pytest.raises(ValueError, match="exactly six oriented face flux"):
        attribute_event(event)


def test_source_order_replay_must_match_observed_advective_tendency():
    event = _raw_event()
    event["rk_bits"]["observed_advect_tend"] = _word(-3.0)

    with pytest.raises(ValueError, match="does not match observed advective tendency"):
        attribute_event(event)


def test_fused_rk_store_must_match_observed_store_bits():
    event = _raw_event()
    event["value_after_bits"] = _word(-2.0)

    with pytest.raises(ValueError, match="does not match observed output"):
        attribute_event(event)


def test_caller_supplied_amount_deltas_are_not_part_of_the_event_schema():
    event = _raw_event()
    event["available"] = 1.0
    event["amount_delta"] = -20.0

    with pytest.raises(ValueError, match="raw-operand schema"):
        attribute_event(event)


def test_identity_and_receipt_must_match_before_arithmetic_replay():
    event = _raw_event()
    event["identity"]["i"] = 47
    with pytest.raises(ValueError, match="coordinate differs"):
        attribute_event(event)

    event = _raw_event()
    event["capture_history_sha256"] = "c" * 64
    with pytest.raises(ValueError, match="noninterference"):
        attribute_event(event)


def test_rk1_cannot_claim_a_pd_limiter_owner_or_scale():
    event = _raw_event()
    event["limiter"] = {"owner": "donor-17", "scale": _word(0.5)}

    with pytest.raises(ValueError, match="PD limiter attribution is invalid"):
        attribute_event(event)


def test_raw_replay_requires_the_captured_advection_order():
    event = _raw_event()
    event["advection_orders"]["horizontal"] = 6

    with pytest.raises(ValueError, match="5th/3rd order"):
        attribute_event(event)


@pytest.mark.parametrize("field", ["rk", "identity.rk"])
def test_rk_stage_rejects_boolean_aliases(field):
    event = _raw_event()
    if field == "rk":
        event["rk"] = True
    else:
        event["identity"]["rk"] = True

    with pytest.raises(ValueError, match="integer"):
        attribute_event(event)


def test_accepted_state_is_classification_only_without_intervening_ledger():
    result = attribute_event(_raw_event(rk=3, state_class="model_step_accepted"))

    assert result.status == "UNVERIFIED_ARITHMETIC"
    assert result.cause == "accepted_state_classification_only"
    assert result.rk_numerator is None
    assert result.replay_group is None


def test_accepted_state_rejects_attached_pre_microphysics_face_attribution():
    event = _raw_event(rk=3, state_class="model_step_accepted")
    event["face_flux_bits"] = {name: _word(0.0) for name in FACE_ORDER}

    with pytest.raises(ValueError, match="classification-only"):
        attribute_event(event)


def test_later_rk_event_cannot_reuse_the_rk1_face_formula():
    event = _raw_event(rk=3)

    with pytest.raises(ValueError, match="source arithmetic is pinned only"):
        attribute_event(event)
