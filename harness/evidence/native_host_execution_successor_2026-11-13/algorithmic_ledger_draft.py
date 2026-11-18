"""Validate a source-order transport diagnostic, without a physical budget claim."""

import math
import re
import struct

SCHEMA = "kdm6.batch6.algorithmic_transport_event.draft.v1"
ZERO = "0000000000000000"
WORD = re.compile(r"[0-9a-f]{16}\Z")
KINDS = {
    "qr": "mass_like", "qs": "mass_like", "qg": "mass_like", "qi": "mass_like",
    "nr": "number", "ni": "number", "brs": "graupel_volume",
}
MAIN = {"qr", "nr", "qs", "qg", "brs"}
FIELDS = {
    "schema", "input_id", "runtime_call", "one_step_call", "outer_loop",
    "substep_family", "substep_n", "b_zero", "k_zero",
    "native_level_bottom_first", "event_ordinal", "species", "source_kind",
    "dtype", "active", "x_before_word", "d_out_candidate_word",
    "d_in_candidate_word", "preclamp_word", "candidate_word", "selected_word",
}


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def value(word, label):
    need(isinstance(word, str) and WORD.fullmatch(word) is not None, label + " word")
    number = struct.unpack(">d", bytes.fromhex(word))[0]
    need(math.isfinite(number), label + " finite")
    return number


def raw(number):
    need(math.isfinite(number), "finite derived value")
    return struct.pack(">d", number).hex()


def validate_event(event):
    """Return gate-adjusted terms and a signed residual for one complete event.

    The returned terms are a declared diagnostic decomposition of the selected
    state coordinate. They are not conserved interface fluxes or physical units.
    """
    need(type(event) is dict and set(event) == FIELDS, "event field inventory")
    need(event["schema"] == SCHEMA and event["dtype"] == "f64", "draft schema/dtype")
    need(type(event["input_id"]) is str and bool(event["input_id"]), "input identity")
    for key in ("runtime_call", "one_step_call", "outer_loop", "substep_n", "event_ordinal"):
        need(type(event[key]) is int and event[key] >= 0, key + " identity")
    # Sedimentation runs inside the outer loop before micro_step() increments
    # the sidecar's one_step_call counter; its actual recorded value is zero.
    need(event["runtime_call"] > 0 and event["one_step_call"] == 0
         and event["substep_n"] >= 1, "sedimentation call identity")
    species = event["species"]
    need(species in KINDS, "species")
    expected_family = "sedimentation_main" if species in MAIN else "sedimentation_ice"
    need(event["substep_family"] == expected_family, "species/family")
    k = event["k_zero"]
    need(type(k) is int and 0 <= k < 39 and type(event["b_zero"]) is int
         and event["b_zero"] == 0
         and type(event["native_level_bottom_first"]) is int
         and event["native_level_bottom_first"] == 39 - k, "layer identity")
    top = k == 0
    need(event["source_kind"] == ("top_uncapped" if top else "interior_capped"),
         "top/interior source kind")
    need(type(event["active"]) is bool, "active gate")
    before = value(event["x_before_word"], "x_before")
    outgoing = value(event["d_out_candidate_word"], "d_out_candidate")
    incoming_word = event["d_in_candidate_word"]
    if top:
        need(incoming_word is None, "top has no source arrival")
        incoming = 0.0  # diagnostic neutral element, not an emitted graph node
    else:
        incoming = value(incoming_word, "d_in_candidate")
    preclamp = value(event["preclamp_word"], "preclamp")
    candidate = value(event["candidate_word"], "candidate")
    expected_preclamp = before - outgoing
    if not top:
        expected_preclamp = expected_preclamp + incoming
    # Exact finite f64 operations are staged in source order. Signed zero is
    # preserved in the record, but its selection policy needs a runtime check.
    need((raw(expected_preclamp) == event["preclamp_word"])
         or (expected_preclamp == preclamp == 0.0), "source-order preclamp")
    if preclamp > 0:
        need(event["candidate_word"] == event["preclamp_word"], "source clamp")
    else:
        need(candidate == 0.0, "source clamp")
    selected = value(event["selected_word"], "selected")
    need(event["selected_word"] == (event["candidate_word"] if event["active"]
                                    else event["x_before_word"]), "outer gate raw selection")
    applied_out = outgoing if event["active"] else 0.0
    applied_in = incoming if event["active"] else 0.0
    reconstructed = (before - applied_out) + applied_in
    residual = selected - reconstructed
    return {
        "schema": "kdm6.batch6.algorithmic_transport_diagnostic.v1",
        "input_id": event["input_id"],
        "species": species,
        "coordinate_kind": KINDS[species],
        "source_kind": event["source_kind"],
        "is_bottom_layer": k == 38,
        "gate_active": event["active"],
        "algorithmic_out_word": raw(applied_out),
        "algorithmic_in_word": raw(applied_in),
        "reconstructed_word": raw(reconstructed),
        "signed_residual_word": raw(residual),
        "scope": "PROPOSED_ALGORITHMIC_DIAGNOSTIC_ONLY",
        "arithmetic_status": "SOURCE_ORDER_RELATION_CHECKED_OPERAND_PROVENANCE_UNVERIFIED",
        "signed_zero_status": "RECORDED_RAW_WORD_RUNTIME_POLICY_UNVERIFIED"
        if preclamp == 0.0 else "NOT_AT_ZERO",
        "physical_flux_status": "UNRESOLVED",
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
    }


def analyze_events(events):
    need(type(events) is list and bool(events), "event list")
    seen = set()
    results = []
    for event in events:
        result = validate_event(event)
        identity = tuple(event[key] for key in (
            "input_id", "runtime_call", "one_step_call", "outer_loop",
            "substep_family", "substep_n", "b_zero", "k_zero", "event_ordinal", "species"
        ))
        need(identity not in seen, "duplicate transport event")
        seen.add(identity)
        results.append(result)
    return {"status": "DRAFT_BLOCKED", "events": len(results), "results": results,
            "scientific_status": "INCONCLUSIVE", "physical_unit_status": "INCONCLUSIVE"}
