#!/usr/bin/env python3
"""SPEC_ONLY: construct bounded predeclared inputs; never invoke KDM."""

import gzip
import hashlib
import json
import math
from pathlib import Path
import struct
import zipfile

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE.parent
ROOT = EVIDENCE.parent.parent
SELECTED = EVIDENCE / "native_host_column_f32_2026-11-11/raw/selected_full.json"
PRIOR = EVIDENCE / "native_host_batch3_shared_2026-11-12"
ARCHIVE = PRIOR / "raw/screening_raw.zip"
SOURCE_PINS = {
    "libtorch/CMakeLists.txt": "4584bef636bce249782077c13a78b9d39a110d7ba927bb6f930da509b1c8cb4f",
    "docs/NATIVE_HOST_BATCH4_COMMON_CAPTURE_20261112.md": "72d49c8100421498cbab37abf342e43f723e125238ca354d17bd54ebcf282863",
    "libtorch/bridge/kdm6_c_api.cpp": "8c3f4a96dc7078eea8b19806d70c0ec6477debbc2cead04eec32403c26efe049",
    "libtorch/bridge/kdm6_c_api.h": "de9ca99da4a77af741a875fd4c69de39c68525dbcd781e900144585bb1fd9481",
    "libtorch/src/ops.cpp": "0c0cb13fc97c66888424121453537af953165746d9e9bdc6e21fa69dccbe9014",
    "harness/evidence/native_host_batch3_shared_2026-11-12/raw/stage_compare_f64_receipt.json": "9be944f01b7be43929877517ec2067b60451ed34f033164cf54a965061a4d2cc",
    "harness/evidence/native_host_column_f32_2026-11-11/raw/selected_full.json": "e3117d277a073042bbae648b87e7dd6661d14b600fc8245f6aeabc19fe715eae",
    "harness/evidence/native_host_batch3_shared_2026-11-12/raw/screening_raw.zip": "f682b42606d133b72b77e6a31ef0eef47a971a3e975f52a8b230229a7bf48088",
    "harness/evidence/native_host_batch3_shared_2026-11-12/raw/screening_preflight_plan.json": "4a1870660005751aaa208155d92f79c4feac77cc5d83114e1358b96d3df19e0c",
    "harness/evidence/native_host_batch3_shared_2026-11-12/stage_inventory.json": "c82a86bdd0e41db4615a01b6da17e29030115cc521aeedab911b9d1e54e36e06",
    "libtorch/src/runtime.cpp": "ae40dac52a3768fb2381fda90213cca1736a04a864cb49fe7590b2f7afc109f8",
    "libtorch/src/coordinator.cpp": "2a9d9df17dd9bab8d8288bd2d2c6e57ebd7dc65b15d688c06c523cd825b0c932",
    "libtorch/src/sedimentation.cpp": "1fd41e6dff2f99cf80cf9f318245cb50cb2d107d2f9053f8c65802f6b4037c2a",
}
FIELDS = (
    "th",
    "qv",
    "qc",
    "qr",
    "qi",
    "qs",
    "qg",
    "nccn",
    "nc",
    "ni",
    "nr",
    "bg",
    "rho",
    "pii",
    "p",
    "delz",
)
CENTERS = {
    "baseline": "4073ff66c0000000",
    "lower": "4074002793cded6a",
    "upper": "407400797f530c23",
}
SCALES = {"nc": 1e8, "pii": 1.0, "th": 1.0, "qv": 0.001}
INSTALLED = "7adcb6921f6205af66c62720ce9447928a1608f5c261546183b928bebbd9dba7"


def need(ok, message):
    if not ok:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def to64(value):
    return struct.pack(">d", value).hex()


def from64(word):
    return struct.unpack(">d", bytes.fromhex(word))[0]


def from32(word):
    return struct.unpack(">f", bytes.fromhex(word))[0]


def verify_sources():
    for name, expected in SOURCE_PINS.items():
        need(digest((ROOT / name).read_bytes()) == expected, "source SHA-256: " + name)


def specs():
    result = []
    for center in CENTERS:
        result.append((center, "center", 0.0, 0))
        for h in (1e-4, 1e-5, 1e-6):
            for m in (1, 2):
                result.append((center, "nc", h, m))
        if center in ("lower", "upper"):
            for h in (1e-4, 1e-5, 1e-6):
                for m in (-1, 1):
                    result.append((center, "pii", h, m))
        for direction in ("th", "qv"):
            for m in (-1, 1):
                result.append((center, direction, 1e-5, m))
    return result


def calculate_input(base, center, direction, h, multiple):
    need(len(base) == 624 and center in CENTERS, "base/center")
    need((center, direction, h, multiple) in specs(), "undeclared input")
    out = list(base)
    out[15] = CENTERS[center]
    changed = {}
    if direction == "center":
        need(h == 0 and multiple == 0, "center controls")
    else:
        need(direction in SCALES and h in (1e-4, 1e-5, 1e-6), "direction/step")
        need(
            multiple in ((1, 2) if direction == "nc" else (-1, 1)),
            "inadmissible stencil",
        )
        idx = FIELDS.index(direction) * 39 + 15
        original = from64(out[idx])
        result = original + multiple * h * SCALES[direction]
        out[idx] = to64(result)
        need(out[idx] != to64(original), "zero represented perturbation")
        changed[direction + "16"] = {
            "base_word": to64(original),
            "input_word": out[idx],
            "represented_delta_word": to64(result - original),
        }
    for word in out:
        need(len(word) == 16 and math.isfinite(from64(word)), "nonfinite input")
    for name in ("th", "qv", "nccn", "rho", "pii", "p", "delz"):
        need(
            from64(out[FIELDS.index(name) * 39 + 15]) > 0, "nonpositive target " + name
        )
    need(from64(out[8 * 39 + 15]) >= 0, "negative NC")
    return out, changed


def construct():
    verify_sources()
    selected = json.loads(SELECTED.read_bytes())
    source = selected["input_words_hex"]
    need(
        selected["column_native"] == [203, 149]
        and selected["tile_shape"] == [232, 39, 139]
        and selected["model_start"] == "2025-07-19_00:00:00",
        "selected source metadata",
    )
    base = [to64(from32(word)) for field in FIELDS for word in source[field]]
    need(len(base) == 624, "widened input count")
    parent = json.loads((PRIOR / "raw/screening_preflight_plan.json").read_bytes())
    need({c["name"]: c["word"] for c in parent["centers"]} == CENTERS, "parent centers")
    need(
        {d["id"]: d["seed"] for d in parent["directions"] if d["id"] in SCALES}
        == {k: {k + "16": v} for k, v in SCALES.items()},
        "parent seeds",
    )
    with zipfile.ZipFile(ARCHIVE) as z:
        screen = json.loads(z.read("screen/inputs.json"))["inputs"]
        adaptive = json.loads(z.read("adaptive/inputs.json"))
        old = screen + adaptive["fixed_inputs"] + adaptive["optional_inputs"]
    records = []
    for center, direction, h, m in specs():
        words, delta = calculate_input(base, center, direction, h, m)
        matches = [
            x
            for x in old
            if x["center"] == center
            and x["direction"] == (None if direction == "center" else direction)
            and x["h_multiple"] == m
            and (direction == "center" or (x.get("nominal_h", 1e-4) == h))
        ]
        need(len(matches) == 1, "archived declared input ambiguity")
        need(
            words == matches[0]["state_words"] + matches[0]["forcing_words"],
            "archived declared input mismatch",
        )
        key = (
            center if direction == "center" else f"{center}:{direction}:{h:.0e}:{m:+d}"
        )
        records.append(
            {
                "id": key,
                "center": center,
                "direction": direction,
                "h": h,
                "multiple": m,
                "words": words,
                "represented_deltas": delta,
                "archived_input_key": matches[0]["key"],
                "archived_output_status": "not established by input match",
            }
        )
    need(
        len(records) == 45
        and len({r["id"] for r in records}) == 45
        and len({tuple(r["words"]) for r in records}) == 45,
        "input uniqueness",
    )
    installed = [
        r["id"]
        for r in records
        if r["direction"] == "center"
        or (
            r["center"] in ("lower", "upper")
            and r["direction"] == "pii"
            and r["h"] == 1e-6
        )
    ]
    calls = [
        {"input_id": r["id"], "mode": mode, "status": "PLANNED"}
        for r in records
        for mode in ("capture_off_value", "capture_on_value")
    ]
    calls += [
        {"input_id": r["id"], "mode": "center_joint_graph", "status": "PLANNED"}
        for r in records
        if r["direction"] == "center"
    ]
    calls += [
        {
            "input_id": key,
            "mode": "installed_value_optional",
            "status": "PLANNED_OPTIONAL",
        }
        for key in installed
    ]
    need(len(installed) == 7 and len(calls) == 100, "call budget")
    for index, call in enumerate(calls, 1):
        call["sequence"] = index
    return {
        "schema": "kdm6.native_host_capture_preflight.v1",
        "status": "SPEC_ONLY",
        "execution_receipt": None,
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
        "scope": "planned separate B=1 f64 calls; no physical model call made by this plan; no host tile or RTTOV claim",
        "controls": {
            "shape": [1, 39, 1],
            "dt": 20.0,
            "xland": 2.0,
            "ncmin_land": 10.0,
            "ncmin_sea": 10.0,
            "physics_variant": "Legacy",
            "dry_number": 0,
            "threads": 1,
        },
        "build_requirements": {
            "source_pins": SOURCE_PINS,
            "ffp_contract": "off",
            "assertions": "enabled in test builds",
            "instrumented_dso_sha256": None,
            "installed_dso_sha256": INSTALLED,
            "dependency_hashes": "required before execution",
            "compiler_identity_and_flags": "required before execution",
            "blocker": "new instrumented DSO is not built or identified",
        },
        "limits": {
            "calls_max": 100,
            "wall_seconds_max": 900,
            "base_value_calls": 90,
            "center_graph_calls": 3,
            "optional_installed_calls": 7,
            "stop_policy": "do not exceed limits; mark any unexecuted calls incomplete; no passing result from truncation",
        },
        "input_field_order": list(FIELDS),
        "direction_seeds": {
            k: {"field": k, "level_zero_bottom_first": 15, "scale_f64_word": to64(v)}
            for k, v in SCALES.items()
        },
        "inputs": records,
        "calls": calls,
        "admissibility_scope": "finite words, target positivity and NC>=0 only; no moment-pair or physical-unit approval",
        "recording_scope": "captured masks and live tangents must be separately identified; source-only plan provides neither results nor execution receipt",
    }


def field_inventory():
    verify_sources()
    existing = json.loads((PRIOR / "stage_inventory.json").read_text())
    need(
        existing["stages_count"] == 51
        and existing["rows"] == 19656
        and sum(x["field_count"] for x in existing["stage_records"].values()) == 505,
        "parent stage inventory",
    )
    groups = {
        "nc_zero": {
            "observed_stages": [
                "runtime_full_entry",
                "nc_budget",
                "fd_state_update",
                "fd_satadj_inner",
                "fd_cleanup",
                "fd_dsd",
            ],
            "new_requirements": [
                "entry floor operands and masks",
                "NC and NCCN at each applied boundary and next consumer",
                "live JVP for each requested state and limiter operand",
            ],
            "source": [
                "libtorch/src/runtime.cpp:428",
                "libtorch/src/coordinator.cpp:2110",
                "libtorch/src/coordinator.cpp:2563",
            ],
        },
        "pii_chain": {
            "observed_stages": [
                "runtime_full_forcing",
                "d1_entry_thermo",
                "fd_satadj_inner",
            ],
            "new_requirements": [
                "PII to T, cpm, saturation and each minimum operand value and live tangent",
                "capture masks and stagewise outputs",
            ],
            "source": [
                "libtorch/src/runtime.cpp:53",
                "libtorch/src/coordinator.cpp:2563",
            ],
        },
        "rate_cap_tie": {
            "observed_stages": ["fd_satadj_inner"],
            "new_requirements": [
                "live raw-rate and cap values and tangents",
                "minimum output and tangent",
                "less/equal/greater masks",
            ],
            "source": ["libtorch/src/coordinator.cpp:2596"],
        },
        "sedimentation": {
            "observed_stages": [
                "runtime_full_schedule",
                "fd_main",
                "ice_sedimentation_n1",
            ],
            "new_requirements": [
                "per species and substep applied departure, arrival and bottom export",
                "before/after values, limiter gates and projection residual",
                "live tangent of applied amounts",
            ],
            "source": [
                "libtorch/src/sedimentation.cpp:105",
                "libtorch/src/sedimentation.cpp:151",
                "libtorch/src/sedimentation.cpp:246",
                "libtorch/src/coordinator.cpp:3061",
            ],
        },
        "named_process": {
            "observed_stages": ["nc_budget", "fd_state_update", "fd_d5"],
            "new_requirements": [
                "post-limiter named rates and applied amounts",
                "donor/recipient post-state and next consumer",
                "live tangent and branch masks",
            ],
            "source": [
                "libtorch/src/coordinator.cpp:1320",
                "libtorch/src/coordinator.cpp:2110",
            ],
        },
        "same_call_water": {
            "observed_stages": [
                "runtime_full_entry",
                "runtime_full_forcing",
                "runtime_full_exit",
            ],
            "new_requirements": [
                "total rain increment and kernel/cleanup boundary values",
                "rho and delz measure and live tangents",
                "separate overlapping snow/graupel diagnostics",
            ],
            "source": [
                "libtorch/src/runtime.cpp:525",
                "libtorch/src/sedimentation.cpp:300",
            ],
        },
        "heat_bg": {
            "observed_stages": ["d1_melt_producer", "d1_postmelt_progb", "fd_main"],
            "new_requirements": [
                "temperature, cpm, latent heats and applied phase-change terms",
                "BG/rhox and pre/post ProgB volume terms",
                "live tangents and masks",
            ],
            "source": [
                "libtorch/src/coordinator.cpp:2353",
                "libtorch/src/coordinator.cpp:2466",
                "libtorch/src/coordinator.cpp:2656",
            ],
        },
    }
    for group in groups.values():
        need(
            all(
                stage in existing["stage_records"] for stage in group["observed_stages"]
            ),
            "observed inventory stage",
        )
        group["required_record_kinds"] = ["value", "live_tangent", "mask"]
    return {
        "schema": "kdm6.native_host_capture_field_plan.v1",
        "status": "SPEC_ONLY",
        "parent_stage_inventory_sha256": SOURCE_PINS[
            "harness/evidence/native_host_batch3_shared_2026-11-12/stage_inventory.json"
        ],
        "parent_counts": {"stages": 51, "stage_field_pairs": 505, "rows": 19656},
        "groups": groups,
        "parent_exact_label_gaps": existing["ledger_exact_label_gaps"],
        "record_identity": [
            "input_id",
            "mode",
            "runtime_call",
            "one_step_call",
            "substep",
            "b_zero",
            "k_zero",
            "native_level_bottom_first",
            "stage",
            "field",
            "record_kind",
            "derivative_mode",
            "direction_id",
            "seed_sha256",
            "cotangent_id",
            "event_ordinal",
        ],
        "vertical_mapping": "native_level_bottom_first = 39 - k_zero; k_zero=0 is native top level 39",
        "duplicate_policy": "reject duplicate complete identity; repeated stage/field within one substep requires contiguous event_ordinal starting at zero; never overwrite stage.field",
        "missing_policy": "each planned required value, live tangent and mask record must be present or carry an explicit inactive-branch absence reason; no silent omission",
        "live_tensor_lifecycle": "retain the existing graph-connected tensor under complete identity until requested JVP/VJP is evaluated; no detach, item or no_grad; value-only CSV is a separate path",
        "identity_scope": "validator checks planned input ID, mode/kind and derivative seed identity; future execution replay must authenticate seed payload, recorded values, required-field coverage and inactive-branch absence reasons",
        "scope": "requirements only; existing capture is value-only and these labels are not a complete causal graph; live AD tensors must not be detached",
    }


def validate_record_identity(records, inventory, plan):
    """Reject repeated-substep overwrites in a future capture ledger."""
    need(isinstance(records, list) and records, "capture records required")
    need(
        plan["schema"] == "kdm6.native_host_capture_preflight.v1"
        and plan["status"] == "SPEC_ONLY",
        "planned capture identity",
    )
    inputs = {item["id"]: item for item in plan["inputs"]}
    need(len(inputs) == 45, "planned input inventory")
    fields = inventory["record_identity"]
    seen = set()
    ordinal_groups = {}
    for record in records:
        need(
            isinstance(record, dict) and all(field in record for field in fields),
            "complete capture record identity",
        )
        need(record["input_id"] in inputs, "unplanned capture input")
        kind, mode = record["record_kind"], record["mode"]
        need(
            (mode == "capture_on_value" and kind in ("value", "mask"))
            or (
                mode == "center_joint_graph"
                and kind == "live_tangent"
                and inputs[record["input_id"]]["direction"] == "center"
            ),
            "capture record mode/kind",
        )
        derivative_mode = record["derivative_mode"]
        if kind == "live_tangent":
            need(
                derivative_mode in ("jvp", "vjp")
                and isinstance(record["seed_sha256"], str)
                and len(record["seed_sha256"]) == 64
                and all(c in "0123456789abcdef" for c in record["seed_sha256"]),
                "live derivative seed identity",
            )
            if derivative_mode == "jvp":
                need(
                    record["direction_id"] in plan["direction_seeds"]
                    and record["cotangent_id"] == "none",
                    "JVP direction identity",
                )
            else:
                need(
                    record["direction_id"] == "none"
                    and isinstance(record["cotangent_id"], str)
                    and record["cotangent_id"] not in ("", "none"),
                    "VJP cotangent identity",
                )
        else:
            need(
                derivative_mode == "none"
                and record["direction_id"] == "none"
                and record["seed_sha256"] == "none"
                and record["cotangent_id"] == "none",
                "value/mask derivative identity",
            )
        need(
            type(record["runtime_call"]) is int
            and record["runtime_call"] >= 1
            and type(record["one_step_call"]) is int
            and record["one_step_call"] >= 0
            and type(record["substep"]) is int
            and record["substep"] >= 0
            and type(record["b_zero"]) is int
            and record["b_zero"] == 0
            and type(record["k_zero"]) is int
            and 0 <= record["k_zero"] < 39
            and type(record["native_level_bottom_first"]) is int
            and record["native_level_bottom_first"] == 39 - record["k_zero"]
            and type(record["event_ordinal"]) is int
            and record["event_ordinal"] >= 0,
            "capture record index/vertical mapping",
        )
        need(
            all(
                isinstance(record[key], str) and record[key]
                for key in ("input_id", "stage", "field")
            ),
            "capture record labels",
        )
        identity = tuple(record[field] for field in fields)
        need(identity not in seen, "duplicate capture record identity")
        seen.add(identity)
        base = identity[:-1]
        ordinal_groups.setdefault(base, []).append(record["event_ordinal"])
    need(
        all(
            sorted(ordinals) == list(range(len(ordinals)))
            for ordinals in ordinal_groups.values()
        ),
        "capture event ordinals must be contiguous",
    )
    return len(seen)


def execution_preflight(plan):
    need(
        plan["build_requirements"]["instrumented_dso_sha256"] is not None,
        "execution blocked: missing new instrumented DSO SHA-256",
    )
    raise ValueError("execution is outside this source-only preflight")


def verify():
    expected = construct()
    saved = json.loads(gzip.decompress((HERE / "plan.json.gz").read_bytes()))
    need(saved == expected, "saved plan mismatch")
    need(
        json.loads((HERE / "field_inventory.json").read_text()) == field_inventory(),
        "field inventory mismatch",
    )
    return expected


if __name__ == "__main__":
    p = verify()
    print(
        f"SPEC_ONLY: {len(p['inputs'])} inputs, {len(p['calls'])} planned/optional calls; execution blocked"
    )
