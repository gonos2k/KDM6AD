"""Adapt caller-supplied receipt data to the captured-branch FD gate.

No model is invoked and receipt consistency is not independent provenance.
"""

import json

import fd_gate
import receipt_schema as rs


def adapt(receipt, assets, center, direction, output_index):
    validation = rs.validate(receipt, assets)
    canonical, _ = rs.load_plan()
    target = fd_gate.canonical_plan(
        fd_gate.PACKET.read_bytes(),
        fd_gate.PACKET_GZ_SHA,
        center,
        direction,
        output_index,
    )
    inputs = {x["id"]: x for x in canonical["inputs"]}
    calls = {
        (x["input_id"], x["mode"]): x
        for x in receipt["calls"]
        if x["status"] == "completed"
    }
    sequences = {key: value["sequence"] for key, value in calls.items()}
    conditions = rs.validate_conditions(receipt, assets, inputs, sequences)

    def observation(input_id):
        off = calls[(input_id, "capture_off_value")]
        on = calls[(input_id, "capture_on_value")]
        raw_off = json.loads(rs.asset(off["output_asset"], assets))
        raw_on = json.loads(rs.asset(on["output_asset"], assets))
        rs.need(
            raw_off["input_words"]
            == raw_on["input_words"]
            == inputs[input_id]["words"],
            "observation input binding",
        )
        return {
            "output_words": raw_on["state_output_words"],
            "reference_output_words": raw_off["state_output_words"],
            "masks": conditions[input_id]["masks"],
            "schedule": conditions[input_id]["schedule"],
        }

    def lookup(direction_id, h, multiple):
        found = [
            x
            for x in inputs.values()
            if x["center"] == center
            and x["direction"] == direction_id
            and x["h"] == h
            and x["multiple"] == multiple
        ]
        rs.need(len(found) == 1, "selected input identity")
        return found[0]["id"]

    center_obs = observation(center)
    samples = []
    for step in target["steps"]:
        h = fd_gate.val(step["h_word"])
        effective_id = f"{center}:{direction}:{step['id']}"
        effective = json.loads(
            rs.asset(receipt["effective_jvp_assets"][effective_id], assets)
        )
        upper = lookup(direction, h, 1)
        lower = center if direction == "nc" else lookup(direction, h, -1)
        sample = {
            "id": step["id"],
            "jvp_evaluation_input_words": effective["evaluation_input_words"],
            "jvp_direction_words": effective["effective_direction_words"],
            "jvp_output_words": effective["jvp_output_words"],
            "jvp_forward_output_words": effective["graph_forward_output_words"],
            "jvp_rc": effective["jvp_return_code"],
            "lower": observation(lower),
            "upper": observation(upper),
        }
        if direction == "nc":
            sample["plus2"] = observation(lookup(direction, h, 2))
        samples.append(sample)
    gate_input = {
        "schema": fd_gate.SCHEMA,
        "intent": "prospective_pre_capture_plan",
        "data_origin": "new_prospective_acquisition",
        "center_name": center,
        "direction": direction,
        "packet_plan_sha256": fd_gate.PACKET_GZ_SHA,
        "plan": target,
        "plan_sha256": fd_gate.plan_sha(target),
        "center": center_obs,
        "samples": samples,
    }
    result = fd_gate.evaluate(gate_input)
    return {
        "schema": "kdm6.receipt_fd_adapter.v1",
        "status": "NOT_ELIGIBLE_UNVERIFIED_PROVENANCE",
        "fd_gate_ready": False,
        "live_intermediate_effective_tangents": "NOT_LINKED",
        "scope": "caller-supplied capture conditions and outputs only; captured branches do not cover all physical branches; chronology and model execution unverified",
        "receipt_validation": validation,
        "gate_input": gate_input,
        "gate_result": result,
    }


def adapt_many(receipt, assets, center, direction, output_indices):
    """Validate a fresh snapshot once, then independently classify each output.

    Only compact gate results are returned; the shared input observations do
    not escape this invocation. No validated context is cached between calls.
    """
    import copy

    rs.need(
        isinstance(output_indices, list)
        and output_indices
        and all(type(x) is int and 0 <= x < 468 for x in output_indices)
        and len(set(output_indices)) == len(output_indices),
        "output indices",
    )
    receipt = copy.deepcopy(receipt)
    assets = dict(assets)  # asset() requires immutable bytes
    validation = rs.validate(receipt, assets)
    canonical, _ = rs.load_plan()
    inputs = {x["id"]: x for x in canonical["inputs"]}
    calls = {
        (x["input_id"], x["mode"]): x
        for x in receipt["calls"]
        if x["status"] == "completed"
    }
    sequences = {key: value["sequence"] for key, value in calls.items()}
    conditions = rs.validate_conditions(receipt, assets, inputs, sequences)
    target = fd_gate.canonical_plan(
        fd_gate.PACKET.read_bytes(),
        fd_gate.PACKET_GZ_SHA,
        center,
        direction,
        output_indices[0],
    )
    observations = {}

    def observation(input_id):
        if input_id not in observations:
            off = json.loads(
                rs.asset(calls[(input_id, "capture_off_value")]["output_asset"], assets)
            )
            on = json.loads(
                rs.asset(calls[(input_id, "capture_on_value")]["output_asset"], assets)
            )
            rs.need(
                off["input_words"] == on["input_words"] == inputs[input_id]["words"],
                "observation input binding",
            )
            observations[input_id] = {
                "output_words": on["state_output_words"],
                "reference_output_words": off["state_output_words"],
                "masks": conditions[input_id]["masks"],
                "schedule": conditions[input_id]["schedule"],
            }
        return observations[input_id]

    def lookup(h, multiple):
        found = [
            x["id"]
            for x in inputs.values()
            if x["center"] == center
            and x["direction"] == direction
            and x["h"] == h
            and x["multiple"] == multiple
        ]
        rs.need(len(found) == 1, "selected input identity")
        return found[0]

    center_obs = observation(center)
    samples = []
    for step in target["steps"]:
        h = fd_gate.val(step["h_word"])
        effective_id = f"{center}:{direction}:{step['id']}"
        effective = json.loads(
            rs.asset(receipt["effective_jvp_assets"][effective_id], assets)
        )
        lower = center if direction == "nc" else lookup(h, -1)
        sample = {
            "id": step["id"],
            "jvp_evaluation_input_words": effective["evaluation_input_words"],
            "jvp_direction_words": effective["effective_direction_words"],
            "jvp_output_words": effective["jvp_output_words"],
            "jvp_forward_output_words": effective["graph_forward_output_words"],
            "jvp_rc": effective["jvp_return_code"],
            "lower": observation(lower),
            "upper": observation(lookup(h, 1)),
        }
        if direction == "nc":
            sample["plus2"] = observation(lookup(h, 2))
        samples.append(sample)
    results = []
    for output_index in output_indices:
        target = fd_gate.canonical_plan(
            fd_gate.PACKET.read_bytes(),
            fd_gate.PACKET_GZ_SHA,
            center,
            direction,
            output_index,
        )
        gate_input = {
            "schema": fd_gate.SCHEMA,
            "intent": "prospective_pre_capture_plan",
            "data_origin": "new_prospective_acquisition",
            "center_name": center,
            "direction": direction,
            "packet_plan_sha256": fd_gate.PACKET_GZ_SHA,
            "plan": target,
            "plan_sha256": fd_gate.plan_sha(target),
            "center": center_obs,
            "samples": samples,
        }
        results.append(copy.deepcopy(fd_gate.evaluate(gate_input)))
    return {
        "schema": "kdm6.receipt_fd_adapter_many.v1",
        "status": "NOT_ELIGIBLE_UNVERIFIED_PROVENANCE",
        "fd_gate_ready": False,
        "live_intermediate_effective_tangents": "NOT_LINKED",
        "scope": "caller-supplied capture conditions and outputs only; captured branches do not cover all physical branches; chronology and model execution unverified",
        "receipt_validation": validation,
        "gate_results": results,
    }
