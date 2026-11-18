#!/usr/bin/env python3
"""Blocked successor contract and synthetic structure checks; no KDM calls.

Group/label presence cannot prove atomic field coverage or actual execution.
This module never grants execution authority or authenticates provenance.
"""

import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys

HERE = Path(__file__).resolve().parent
PRE = HERE.parent / "native_host_preflight_2026-11-12"
sys.path.insert(0, str(PRE))
import fd_gate  # noqa: E402

PARENT_SHA = "4d6a935c9d83d987a8a2149d58699b2812af565785d20c599cf9f49f05846b8a"
CONTRACT_SHA = "f55dcc442868e83a6a7d1521e0ce9fd77dbc6f9ad9cacca27e8c18fd367ba2f7"
ATOMIC_CATALOG_DRAFT_SHA = (
    "05d2291d1060ddee582c443d719035b8e4a84a1c8293c4385ed5208e60aa331d"
)
POLICY_COMMIT = "7654dd565350d09b58fce09f36b4d162b16123ca"
ZERO = "0000000000000000"


def need(ok, why):
    if not ok:
        raise ValueError(why)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def raw64(word):
    need(
        isinstance(word, str) and re.fullmatch("[0-9a-f]{16}", word) is not None,
        "f64 word",
    )
    x = struct.unpack(">d", bytes.fromhex(word))[0]
    need(math.isfinite(x), "finite f64")
    return x


def vector(words, count):
    need(isinstance(words, list) and len(words) == count, "word count")
    for word in words:
        raw64(word)
    return words


def packed_sha(words):
    return sha(b"".join(bytes.fromhex(w) for w in words))


def draft():
    parent_bytes = (PRE / "plan.json.gz").read_bytes()
    contract_bytes = (PRE / "field_contract.json").read_bytes()
    atomic_bytes = (HERE / "atomic_catalog_draft.json").read_bytes()
    need(
        sha(parent_bytes) == PARENT_SHA
        and sha(contract_bytes) == CONTRACT_SHA
        and sha(atomic_bytes) == ATOMIC_CATALOG_DRAFT_SHA,
        "parent hash",
    )
    parent = json.loads(gzip.decompress(parent_bytes))
    contract = json.loads(contract_bytes)
    atomic = json.loads(atomic_bytes)
    need(
        parent["status"] == "SPEC_ONLY"
        and len(parent["inputs"]) == 45
        and len(parent["calls"]) == 100
        and parent["limits"]["wall_seconds_max"] == 900,
        "parent plan",
    )
    need(contract["status"] == "SPEC_ONLY", "contract status")
    need(
        atomic["status"] == "DRAFT_BLOCKED"
        and atomic["parent_contract_sha256"] == CONTRACT_SHA
        and len(atomic["atoms"]) == 191
        and len(atomic["proposed_masks"]) == 19,
        "atomic catalog draft status",
    )
    groups = [x["id"] for entries in contract["groups"].values() for x in entries]
    masks = [x["id"] for x in contract["proposed_new_masks"]]
    need(
        len(groups) == len(set(groups)) == 28 and len(masks) == len(set(masks)) == 19,
        "contract IDs",
    )
    return {
        "schema": "kdm6.native_host_execution_successor.v1",
        "status": "DRAFT_BLOCKED",
        "target_status": "EXECUTION_READY",
        "parent_plan_gzip_sha256": PARENT_SHA,
        "field_contract_sha256": CONTRACT_SHA,
        "atomic_catalog_draft_sha256": ATOMIC_CATALOG_DRAFT_SHA,
        "atomic_catalog_draft_sites": 191,
        "policy_source_commit": POLICY_COMMIT,
        "inputs": parent["inputs"],
        "calls": parent["calls"],
        "controls": parent["controls"],
        "limits": parent["limits"],
        "base_source_pins": parent["build_requirements"]["source_pins"],
        "required_build_flags": [
            "-ffp-contract=off",
            "assertions enabled in test targets",
        ],
        "independent_evidence_requirements": [
            "external watchdog normal exit and full wall <=900 seconds",
            "independent loader receipt matching exact isolated DSO and dependency hashes",
            "reviewed atomic source field and mask catalog",
            "same-call total rain sidecar for capture off/on and graph calls",
        ],
        "measurement_group_ids": groups,
        "measurement_groups": {
            name: [x["id"] for x in entries]
            for name, entries in contract["groups"].items()
        },
        "mask_ids": masks,
        "mask_groups": {m["id"]: m["group"] for m in contract["proposed_new_masks"]},
        "record_identity": contract["identity"],
        "required_build": {
            "isolated_source_diff_sha256": None,
            "atomic_field_catalog_sha256": None,
            "compiler_and_flags": None,
            "instrumented_dso_sha256": None,
            "dependency_sha256": None,
            "loader_receipt_sha256": None,
            "external_watchdog_sha256": None,
        },
        "blockers": [
            "reviewed atomic tensor/branch catalog absent",
            "isolated source/build/DSO/dependency pins absent",
            "independent loader receipt absent",
            "external watchdog and normal-exit/full-wall witness absent",
        ],
        "execution_receipt": None,
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
        "precipitation_unit_measure_status": "FnResult rain unit and measure are unapproved; sidecar preserves raw words only",
        "scope": "source-only DRAFT; 28 IDs are groups, not atomic tensors; no authorization or model execution",
    }


def effective_seeds():
    parent = (PRE / "plan.json.gz").read_bytes()
    result = {}
    for center, dirs in (
        ("baseline", ("nc", "th", "qv")),
        ("lower", ("nc", "pii", "th", "qv")),
        ("upper", ("nc", "pii", "th", "qv")),
    ):
        for direction in dirs:
            gp = fd_gate.canonical_plan(parent, PARENT_SHA, center, direction, 0)
            for step in gp["steps"]:
                h = fd_gate.val(step["h_word"])
                den = h if step["stencil"] == "forward" else 2 * h
                words = [
                    fd_gate.word((fd_gate.val(b) - fd_gate.val(a)) / den)
                    for a, b in zip(
                        step["lower_input_words"], step["upper_input_words"]
                    )
                ]
                result[f"{center}:{direction}:{step['id']}"] = words
    need(len(result) == 21, "effective seed count")
    return result


def validate_identity(r, planned, required):
    need(all(k in r for k in required), "record identity missing")
    need((r["input_id"], r["mode"]) in planned, "record call identity")
    need(
        type(r["runtime_call"]) is int
        and r["runtime_call"] >= 1
        and type(r["one_step_call"]) is int
        and r["one_step_call"] >= 0
        and type(r["outer_loop"]) is int
        and r["outer_loop"] >= 0
        and r["substep_family"] in ("main", "ice", "none")
        and type(r["substep_n"]) is int
        and r["substep_n"] >= 0
        and r["b_zero"] == 0
        and type(r["b_zero"]) is int
        and type(r["event_ordinal"]) is int
        and r["event_ordinal"] >= 0
        and isinstance(r["stage"], str)
        and r["stage"]
        and isinstance(r["field"], str)
        and r["field"],
        "record indices",
    )
    if r["scope"] == "column":
        need(
            r["k_zero"] is None and r["native_level_bottom_first"] is None,
            "column scope",
        )
    else:
        need(
            r["scope"] == "layer"
            and type(r["k_zero"]) is int
            and 0 <= r["k_zero"] < 39
            and type(r["native_level_bottom_first"]) is int
            and r["native_level_bottom_first"] == 39 - r["k_zero"],
            "layer scope",
        )


def require_execution_ready(_candidate):
    raise ValueError(
        "execution blocked: reviewed atomic catalog, isolated build pins, external watchdog and independent loader receipt required"
    )


def validate_synthetic(bundle):
    """Check hypothetical structure only; cannot establish field coverage/truth."""
    spec = draft()
    need(
        bundle.get("schema") == "kdm6.native_host_successor_synthetic.v1"
        and bundle.get("origin") == "SYNTHETIC_TEST_ONLY",
        "synthetic only",
    )
    need(
        bundle.get("parent_plan_sha256") == PARENT_SHA
        and bundle.get("policy_source_commit") == POLICY_COMMIT,
        "parent/source identity",
    )
    calls = bundle["calls"]
    planned = spec["calls"]
    inputs = {x["id"]: x for x in spec["inputs"]}
    need(
        isinstance(calls, list) and len(calls) == len(planned) == 100,
        "call ledger count",
    )
    need(
        type(bundle["wall_seconds"]) in (int, float)
        and math.isfinite(bundle["wall_seconds"])
        and 0 <= bundle["wall_seconds"] <= 900,
        "wall budget",
    )
    outputs = {}
    seq = {}
    for row, expected in zip(calls, planned):
        need(
            type(row["sequence"]) is int
            and (row["sequence"], row["input_id"], row["mode"])
            == (expected["sequence"], expected["input_id"], expected["mode"]),
            "call order",
        )
        if row["status"] == "SKIPPED":
            need(
                expected["status"] == "PLANNED_OPTIONAL"
                and isinstance(row.get("reason"), str)
                and row["reason"].strip(),
                "skipped required call",
            )
            continue
        need(
            row["status"] == "COMPLETED"
            and type(row["return_code"]) is int
            and row["return_code"] == 0,
            "call failure",
        )
        need(
            vector(row["input_words"], 624) == inputs[row["input_id"]]["words"],
            "call input mismatch",
        )
        need(row["input_sha256"] == packed_sha(row["input_words"]), "input word hash")
        vector(row["state_output_words"], 468)
        need(
            row["output_sha256"] == packed_sha(row["state_output_words"]),
            "output word hash",
        )
        sidecar = row["rain_sidecar"]
        need(
            sidecar["scope"] == "same_call_total_precipitation_raw"
            and sidecar["sha256"] == sha(bytes.fromhex(sidecar["word"])),
            "rain sidecar hash/scope",
        )
        rain = raw64(sidecar["word"])
        need(rain >= 0, "negative total precipitation")
        outputs[(row["input_id"], row["mode"])] = (
            row["state_output_words"],
            sidecar["word"],
        )
        seq[(row["input_id"], row["mode"])] = row["sequence"]
    for input_id in inputs:
        need(
            outputs[(input_id, "capture_off_value")]
            == outputs[(input_id, "capture_on_value")],
            "capture output/rain mismatch",
        )
    for (input_id, mode), out in outputs.items():
        if mode in ("center_joint_graph", "installed_value_optional"):
            need(
                out == outputs[(input_id, "capture_off_value")],
                "graph/installed output/rain mismatch",
            )
    # Direct word comparison, not merely a caller-supplied rehashed seed label.
    expected = effective_seeds()
    seeds = bundle["effective_jvp_seeds"]
    need(
        isinstance(seeds, dict) and set(seeds) == set(expected),
        "effective JVP inventory",
    )
    for key, item in seeds.items():
        seed = vector(item["words"], 624)
        need(
            seed == expected[key] and item["sha256"] == packed_sha(seed),
            "effective JVP seed",
        )
        center = key.split(":")[0]
        need(
            item["graph_sequence"] == seq[(center, "center_joint_graph")]
            and vector(item["graph_input_words"], 624) == inputs[center]["words"],
            "effective JVP graph binding",
        )
        need(
            vector(item["forward_words"], 468)
            == outputs[(center, "center_joint_graph")][0],
            "effective JVP forward",
        )
        need(
            item["return_code"] == 0
            and type(item["return_code"]) is int
            and item["jvp_sha256"] == packed_sha(vector(item["jvp_words"], 468)),
            "effective JVP output",
        )
    vjp = bundle["vjp_cotangent"]
    cot = vector(vjp["words"], 468)
    expected_cot = [ZERO] * 468
    expected_cot[8 * 39 + 15] = "3ff0000000000000"
    need(
        vjp["id"] == "state:nc:15"
        and cot == expected_cot
        and vjp["sha256"] == packed_sha(cot),
        "VJP cotangent",
    )
    need(
        vjp["graph_sequence"] == seq[("baseline", "center_joint_graph")]
        and vector(vjp["forward_words"], 468)
        == outputs[("baseline", "center_joint_graph")][0]
        and vjp["return_code"] == 0
        and vjp["vjp_sha256"] == packed_sha(vector(vjp["vjp_words"], 624)),
        "VJP graph/output",
    )
    records = bundle["records"]
    need(isinstance(records, list) and records, "records missing")
    identity_fields = spec["record_identity"]["required"]
    seen = set()
    ordinals = {}
    group_coverage = set()
    mask_coverage = set()
    graph_coverage = set()
    for r in records:
        validate_identity(r, seq, identity_fields)
        need(r["call_sequence"] == seq[(r["input_id"], r["mode"])], "record sequence")
        ident = tuple(r[k] for k in identity_fields)
        need(ident not in seen, "duplicate record")
        seen.add(ident)
        ordinals.setdefault(ident[:-1], []).append(r["event_ordinal"])
        need(
            r["measurement_group_id"] in spec["measurement_group_ids"],
            "unknown measurement group",
        )
        if r["record_kind"] in ("value", "mask"):
            need(
                r["derivative_mode"] == "none"
                and r["direction_id"] == "none"
                and r["seed_sha256"] == "none"
                and r["cotangent_id"] == "none",
                "value/mask derivative identity",
            )
        if r["record_kind"] == "value":
            need(r["mode"] == "capture_on_value", "value mode")
            raw64(r["raw_hex"])
            group_coverage.add((r["input_id"], r["measurement_group_id"]))
        elif r["record_kind"] == "mask":
            need(
                r["mode"] == "capture_on_value"
                and r["mask_id"] in spec["mask_ids"]
                and r["measurement_group_id"]
                in spec["measurement_groups"][spec["mask_groups"][r["mask_id"]]]
                and type(r["mask_value"]) is bool,
                "mask identity/payload",
            )
            mask_coverage.add((r["input_id"], r["mask_id"]))
        elif r["record_kind"] == "live_tangent":
            need(
                r["mode"] == "center_joint_graph"
                and r["input_id"] in ("baseline", "lower", "upper")
                and r["derivative_mode"] == "jvp"
                and r["cotangent_id"] == "none",
                "live mode",
            )
            raw64(r["raw_hex"])
            graph_coverage.add((r["input_id"], r["measurement_group_id"]))
            need(
                r["direction_id"] in expected
                and r["direction_id"].startswith(r["input_id"] + ":")
                and r["seed_sha256"] == packed_sha(expected[r["direction_id"]]),
                "live seed binding",
            )
        else:
            raise ValueError("record kind")
    need(
        all(sorted(v) == list(range(len(v))) for v in ordinals.values()),
        "record ordinals",
    )
    need(
        all(
            (i, g) in group_coverage
            for i in inputs
            for g in spec["measurement_group_ids"]
        ),
        "missing measurement group",
    )
    need(
        all((i, m) in mask_coverage for i in inputs for m in spec["mask_ids"]),
        "missing mask",
    )
    need(
        all(
            (i, g) in graph_coverage
            for i in ("baseline", "lower", "upper")
            for g in spec["measurement_group_ids"]
        ),
        "missing live group",
    )
    return {
        "status": "DRAFT_BLOCKED",
        "synthetic_only": True,
        "execution_ready": False,
        "scientific_status": "INCONCLUSIVE",
        "scope": "synthetic label coverage only; 28 group IDs are not atomic field coverage; build/loader/watchdog and provenance not validated",
    }
