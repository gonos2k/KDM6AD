"""SPEC_ONLY value-condition contract; never establishes real coverage or eligibility.

Caller-supplied site mappings are not source verification. In particular no
producer currently emits a reviewed census for the 19 proposed mask families.
The event_ordinal=0 restriction and site-to-gate mappings are unverified draft
assumptions. This module does not integrate receipt validation or adapt_many.
It assumes a future C reader enforces successful-forward commit before export;
this consumer cannot establish that event from a caller assertion.
"""

import copy
import json
import math
import re
import struct
import sys
from pathlib import Path

MASKS = frozenset(
    (
        "entry_nc_floor",
        "entry_nccn_bounds",
        "snap1_per_cell_gate",
        "snap2_per_cell_gate",
        "lambda_active",
        "lambda_bounds",
        "dsd_ncmin",
        "dsd_ncmax",
        "cleanup_qc",
        "temperature_floor",
        "water_es_cap",
        "satadj_paths",
        "safe_pow_floor",
        "ncact_preclamp",
        "nccn_cap_clamp",
        "main_transport_gate",
        "ice_transport_gate",
        "warm_cold_gate",
        "progb_density_gate",
    )
)
SCHEMA = "kdm6.condition_consumer_draft.v2"
PREFIX = "__condition_consumer_draft_v2__:"


def need(ok, message):
    if not ok:
        raise ValueError(message)


def _word(dtype, value):
    if dtype == "bool":
        need(type(value) is bool, "boolean payload")
    elif dtype in ("f32", "f64"):
        size = 8 if dtype == "f32" else 16
        need(
            type(value) is str
            and re.fullmatch("[0-9a-f]{%d}" % size, value) is not None,
            "float payload",
        )
        number = struct.unpack(">f" if dtype == "f32" else ">d", bytes.fromhex(value))[
            0
        ]
        need(math.isfinite(number), "nonfinite condition evidence")
    elif dtype == "i64":
        need(type(value) is int and -(2**63) <= value < 2**63, "integer payload")
    else:
        raise ValueError("unknown dtype")


def validate(contract, capture, call):
    """Validate a caller-declared hypothetical census, never source completeness.

    Each mask is linked to one or more explicitly declared sites. A site has a
    reviewed-by-caller role, dtype, scope, dynamic family and allowed same-scope
    causal gates. Manifest and census must eventually be source-pinned/reviewed;
    here they are untrusted hypotheses and cannot establish coverage.
    """
    need(
        type(contract) is dict
        and set(contract) == {"schema", "status", "sites"}
        and contract["schema"] == SCHEMA
        and contract["status"] == "SPEC_ONLY",
        "contract",
    )
    sites = contract["sites"]
    need(type(sites) is list and sites, "sites")
    spec = {}
    for s in sites:
        need(
            type(s) is dict
            and set(s)
            == {
                "id",
                "mask",
                "stage",
                "field",
                "source_hook",
                "family",
                "scope",
                "role",
                "dtype",
                "allowed_false_gates",
            },
            "site fields",
        )
        need(
            all(
                type(s[k]) is str and s[k]
                for k in ("id", "mask", "stage", "field", "source_hook")
            ),
            "site identity",
        )
        need(
            s["id"] not in spec
            and s["mask"] in MASKS
            and s["family"] in ("main", "ice")
            and s["scope"] in ("layer", "column", "scalar"),
            "site identity",
        )
        need(
            (s["role"], s["dtype"])
            in (
                ("consumed_bool", "bool"),
                ("diagnostic_bool", "bool"),
                ("operand", "f32"),
                ("operand", "f64"),
                ("control", "f32"),
                ("control", "f64"),
                ("control", "i64"),
            ),
            "site role/dtype",
        )
        need(
            type(s["allowed_false_gates"]) is list
            and all(type(x) is str and x for x in s["allowed_false_gates"])
            and len(set(s["allowed_false_gates"])) == len(s["allowed_false_gates"]),
            "causal mapping",
        )
        spec[s["id"]] = s
    need({s["mask"] for s in sites} == MASKS, "19 mask census required")
    need(
        {s["mask"] for s in sites if s["role"] in ("consumed_bool", "diagnostic_bool")} == MASKS,
        "each mask needs a declared Boolean role",
    )
    for s in sites:
        for gate in s["allowed_false_gates"]:
            need(
                gate in spec
                and spec[gate]["role"] == "consumed_bool"
                and spec[gate]["scope"] == s["scope"]
                and spec[gate]["family"] == s["family"],
                "unsupported causal mapping",
            )
    need(
        type(call) is dict
        and set(call)
        == {"input_id", "sequence", "mode", "context_epoch", "one_step_call"}
        and type(call["input_id"]) is str
        and call["input_id"]
        and all(
            type(call[k]) is int and call[k] >= 0
            for k in ("sequence", "context_epoch", "one_step_call")
        )
        and call["mode"] == "capture_on_value",
        "call",
    )
    need(
        type(capture) is dict
        and set(capture) == {"schema", "status", "call", "schedule", "records"}
        and capture["schema"] == SCHEMA
        and capture["status"] == "SPEC_ONLY"
        and capture["call"] == call,
        "capture/call",
    )
    schedules = {}
    for x in capture["schedule"]:
        need(
            type(x) is dict
            and set(x) == {"outer_loop", "family", "substeps"}
            and type(x["outer_loop"]) is int
            and x["outer_loop"] > 0
            and x["family"] in ("main", "ice")
            and type(x["substeps"]) is int
            and x["substeps"] >= 0,
            "schedule",
        )
        key = (x["outer_loop"], x["family"])
        need(key not in schedules, "duplicate schedule")
        schedules[key] = x["substeps"]
    loops = {k[0] for k in schedules}
    need(
        loops
        and loops == set(range(1, max(loops) + 1))
        and all((loop, family) in schedules for loop in loops for family in ("main", "ice")),
        "schedule census",
    )
    expected = set()
    for site in sites:
        for (loop, family), count in schedules.items():
            if family != site["family"]:
                continue
            # Zero-substep families have no site invocation; schedule records
            # retain the missing family, never invent false mask values.
            for n in range(1, count + 1):
                for k in range(39) if site["scope"] == "layer" else (-1,):
                    expected.add((site["id"], loop, family, n, k))
    records = capture["records"]
    need(type(records) is list, "records")
    need(
        all(type(r) is dict and r.get("one_step_call") == call["one_step_call"] for r in records),
        "UNSUPPORTED: mixed one_step_call phases require a reviewed phase census",
    )
    seen = {}
    comparisons = {}
    observed_masks = set()
    keys = {
        "site_id",
        "input_id",
        "mode",
        "context_epoch",
        "runtime_call",
        "one_step_call",
        "outer_loop",
        "family",
        "substep_n",
        "scope",
        "B",
        "K",
        "b_zero",
        "k_zero",
        "native_level_bottom_first",
        "event_ordinal",
        "stage",
        "field",
        "source_hook",
        "role",
        "dtype",
        "raw",
        "reason",
        "causal_index",
    }
    for index, r in enumerate(records):
        need(
            type(r) is dict and set(r) == keys and r["site_id"] in spec,
            "record fields/site",
        )
        s = spec[r["site_id"]]
        need(
            all(
                type(r[k]) is int
                for k in (
                    "context_epoch",
                    "runtime_call",
                    "one_step_call",
                    "outer_loop",
                    "substep_n",
                    "B",
                    "K",
                    "b_zero",
                    "k_zero",
                    "native_level_bottom_first",
                    "event_ordinal",
                )
            ),
            "record integer types",
        )
        need(
            r["input_id"] == call["input_id"]
            and r["mode"] == call["mode"]
            and r["runtime_call"] == call["sequence"]
            and r["context_epoch"] == call["context_epoch"]
            and r["one_step_call"] == call["one_step_call"]
            and r["event_ordinal"] == 0,
            "record call binding",
        )
        need(
            all(
                r[k] == s[k]
                for k in ("stage", "field", "source_hook", "family", "scope")
            ),
            "record site binding",
        )
        k = r["k_zero"]
        scope = s["scope"]
        need(
            (
                scope == "layer"
                and (r["B"], r["K"]) == (1, 39)
                and 0 <= k < 39
                and r["b_zero"] == 0
                and r["native_level_bottom_first"] == 39 - k
            )
            or (
                scope == "column"
                and (r["B"], r["K"]) == (1, -1)
                and (r["b_zero"], k, r["native_level_bottom_first"]) == (0, -1, -1)
            )
            or (
                scope == "scalar"
                and (r["B"], r["K"]) == (-1, -1)
                and (r["b_zero"], k, r["native_level_bottom_first"]) == (-1, -1, -1)
            ),
            "record coordinates",
        )
        key = (r["site_id"], r["outer_loop"], r["family"], r["substep_n"], k)
        need(key in expected and key not in seen, "unknown or duplicate record")
        if r["role"] == "not_evaluated":
            ci = r["causal_index"]
            need(
                r["dtype"] == "none"
                and r["raw"] is None
                and r["reason"] == "gate_false"
                and type(ci) is int
                and 0 <= ci < index,
                "inactive evidence",
            )
            cause = records[ci]
            need(
                cause["site_id"] in s["allowed_false_gates"]
                and cause["role"] == "consumed_bool"
                and cause["dtype"] == "bool"
                and cause["raw"] is False,
                "false causal gate",
            )
            need(
                all(
                    cause[z] == r[z]
                    for z in (
                        "input_id",
                        "mode",
                        "context_epoch",
                        "runtime_call",
                        "one_step_call",
                        "outer_loop",
                        "family",
                        "substep_n",
                        "scope",
                        "B",
                        "K",
                        "b_zero",
                        "k_zero",
                        "native_level_bottom_first",
                        "event_ordinal",
                    )
                ),
                "causal context",
            )
            outcome = ("inactive", "gate_false", cause["site_id"])
        else:
            need(
                r["role"] == s["role"]
                and r["dtype"] == s["dtype"]
                and r["reason"] == "none"
                and r["causal_index"] is None,
                "record role",
            )
            _word(r["dtype"], r["raw"])
            outcome = ("present", r["role"], r["dtype"], r["raw"])
        seen[key] = index
        if r["role"] in ("consumed_bool", "diagnostic_bool"):
            observed_masks.add((s["mask"], r["role"]))
        if r["role"] in ("consumed_bool", "diagnostic_bool", "not_evaluated"):
            comparisons[key] = outcome
    need(set(seen) == expected, "incomplete dynamic census")
    return {
        "schedule": schedules,
        "conditions": comparisons,
        "observed_masks": observed_masks,
        "status": "SPEC_ONLY",
        "eligibility": "NOT_ELIGIBLE",
    }


def _add_conditions(gate_input, bindings, captures, contract, expected_bindings, expected_calls):
    """Synthetic-only internal crossing exercise, never evidence or a public adapter.

    It preserves all existing masks/schedules. Bindings associate each role with
    input_id and capture call; aliased IDs must have identical planned input.
    Arbitrary expected bindings are accepted; none of this establishes provenance.
    """
    data = copy.deepcopy(gate_input)
    need(type(bindings) is dict and bindings == expected_bindings, "canonical role binding")
    samples, steps = data["samples"], data["plan"]["steps"]
    ids = [s["id"] for s in samples]
    pids = [p["id"] for p in steps]
    need(
        len(ids) == len(set(ids))
        and len(pids) == len(set(pids))
        and set(ids) == set(pids)
        and set(bindings["samples"]) == set(ids),
        "step bindings",
    )
    plans = {p["id"]: p for p in steps}
    slots = [(data["center"], bindings["center"], data["plan"]["center_input_words"])]
    for sample in samples:
        roles = {"lower", "upper"} | ({"plus2"} if "plus2" in sample else set())
        role_bindings = bindings["samples"][sample["id"]]
        need(
            type(role_bindings) is dict
            and set(role_bindings) == roles
            and ("plus2_input_words" in plans[sample["id"]]) == ("plus2" in roles),
            "role bindings",
        )
        slots.extend(
            (sample[r], role_bindings[r], plans[sample["id"]][r + "_input_words"])
            for r in sorted(roles)
        )
    bound = {}
    for _, cid, words in slots:
        need(type(cid) is str and cid and type(words) is list, "call binding")
        need(cid not in bound or bound[cid] == words, "call alias")
        bound[cid] = words
    need(type(captures) is dict and set(captures) == set(bound), "capture inventory")
    parsed = {}
    for cid, item in captures.items():
        need(
            type(item) is dict
            and set(item) == {"call", "capture"}
            and item["call"]["input_id"] == cid,
            "capture binding",
        )
        need(item["call"]["sequence"] == expected_calls[cid], "canonical call sequence")
        parsed[cid] = validate(contract, item["capture"], item["call"])
        declared = {(s["mask"], s["role"]) for s in contract["sites"] if s["role"] in ("consumed_bool", "diagnostic_bool")}
        need(parsed[cid]["observed_masks"] == declared, "NOT_OBSERVED: incomplete Boolean condition coverage")
    call_sequences = [item["call"]["sequence"] for item in captures.values()]
    need(
        len(call_sequences) == len(set(call_sequences)),
        "duplicate capture call sequence",
    )
    union = set().union(*(set(v["conditions"]) for v in parsed.values()))
    signatures = {}
    for cid, value in parsed.items():
        signatures[cid] = json.dumps(
            {
                "schedule": sorted(
                    (a, b, n) for (a, b), n in value["schedule"].items()
                ),
                "conditions": [
                    (k, value["conditions"].get(k, ("absent_due_to_schedule",)))
                    for k in sorted(union)
                ],
            },
            separators=(",", ":"),
        )
    variants = sorted(set(signatures.values()))
    for obs, cid, _ in slots:
        need(not any(k.startswith(PREFIX) for k in obs["masks"]), "reserved namespace")
        obs["masks"].update(
            {PREFIX + str(i): signatures[cid] == v for i, v in enumerate(variants)}
        )
    return data


def add_conditions(gate_input, bindings, captures, contract, *, receipt, assets):
    """Revalidate the v1 receipt and bind every condition to its canonical role.

    The supplemental records and their source mappings remain unverified draft
    assertions; validation does not confer execution or scientific eligibility.
    """
    preflight = Path(__file__).resolve().parent.parent / "native_host_preflight_2026-11-12"
    if str(preflight) not in sys.path:
        sys.path.insert(0, str(preflight))
    import fd_input_adapter as adapter
    import receipt_schema as rs

    need(Path(adapter.__file__).resolve() == preflight / "fd_input_adapter.py" and
         Path(rs.__file__).resolve() == preflight / "receipt_schema.py", "preflight module identity")
    receipt = copy.deepcopy(receipt)
    assets = dict(assets)
    center = gate_input["center_name"]
    direction = gate_input["direction"]
    output_index = gate_input["plan"]["output_index"]
    checked = adapter.adapt(receipt, assets, center, direction, output_index)
    need(gate_input == checked["gate_input"], "gate input differs from validated receipt")
    canonical, _ = rs.load_plan()
    inputs = canonical["inputs"]
    calls = canonical["calls"]
    expected = {"center": center, "samples": {}}
    for step in gate_input["plan"]["steps"]:
        h = adapter.fd_gate.val(step["h_word"])
        def lookup(multiple):
            found = [x for x in inputs if x["center"] == center and x["direction"] == direction
                     and x["h"] == h and x["multiple"] == multiple]
            need(len(found) == 1, "canonical endpoint")
            return found[0]["id"]
        entry = {"lower": center if step["stencil"] == "forward" else lookup(-1),
                 "upper": lookup(1)}
        if "plus2_input_words" in step:
            entry["plus2"] = lookup(2)
        expected["samples"][step["id"]] = entry
    by_id = {x["id"]: x for x in inputs}
    for step in gate_input["plan"]["steps"]:
        for role, cid in expected["samples"][step["id"]].items():
            need(by_id[cid]["words"] == step[role + "_input_words"], "canonical endpoint words")
    need(by_id[center]["words"] == gate_input["plan"]["center_input_words"], "canonical center words")
    selected = {expected["center"]} | {cid for v in expected["samples"].values() for cid in v.values()}
    expected_calls = {}
    for cid in selected:
        matches = [x for x in calls if x["input_id"] == cid and x["mode"] == "capture_on_value"]
        need(len(matches) == 1, "canonical capture call")
        expected_calls[cid] = matches[0]["sequence"]
    # Payloads remain caller-supplied: even a rehashed receipt cannot prove
    # that a relabelled condition stream came from this call. Do not hand any
    # v2-augmented input to the FD gate until that linkage is independently
    # verifiable; a digest alone establishes consistency, not provenance.
    need(bindings == expected, "canonical role binding")
    need(type(captures) is dict and set(captures) == selected, "capture inventory")
    for cid, item in captures.items():
        need(item["call"]["input_id"] == cid and item["call"]["sequence"] == expected_calls[cid], "canonical call sequence")
    raise ValueError("UNRESOLVED: v2 call-to-payload provenance not independently verified")
