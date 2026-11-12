"""Source-only future receipt validation; never authenticate or execute a model.

Passing this validator establishes internal consistency of caller-supplied bytes,
not when they were produced, which binary ran, or independent provenance.
"""

import csv
import functools
import gzip
import io
import hashlib
import json
import math
import re
import struct
from collections import defaultdict
from pathlib import Path

import plan
import fd_gate

HERE = Path(__file__).resolve().parent
PLAN_GZ_SHA = "4d6a935c9d83d987a8a2149d58699b2812af565785d20c599cf9f49f05846b8a"
FIELDS = plan.FIELDS
HEX = re.compile(r"^[0-9a-f]{64}$")
WORD = re.compile(r"^[0-9a-f]{16}$")
ZERO = "0000000000000000"
ONE = "3ff0000000000000"


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def hex_sha(s):
    return isinstance(s, str) and HEX.fullmatch(s) is not None and s != "0" * 64


def words(value, n, label):
    need(isinstance(value, list) and len(value) == n, label + " length")
    need(
        all(
            isinstance(w, str)
            and WORD.fullmatch(w)
            and math.isfinite(struct.unpack(">d", bytes.fromhex(w))[0])
            for w in value
        ),
        label + " words",
    )
    return value


def word_sha(seq):
    return sha(b"".join(bytes.fromhex(w) for w in seq))


def load_plan():
    raw = (HERE / "plan.json.gz").read_bytes()
    need(sha(raw) == PLAN_GZ_SHA, "canonical plan hash")
    p = json.loads(gzip.decompress(raw))
    inventory = json.loads((HERE / "field_inventory.json").read_text())
    need(
        p == plan.verify() and inventory == plan.field_inventory(),
        "canonical inputs/inventory",
    )
    return p, inventory


def asset(ref, assets):
    need(isinstance(ref, dict) and set(ref) == {"path", "sha256"}, "asset reference")
    path = ref["path"]
    need(
        isinstance(path, str)
        and path
        and not path.startswith("/")
        and ".." not in Path(path).parts
        and "\\" not in path,
        "asset path",
    )
    need(
        hex_sha(ref["sha256"])
        and path in assets
        and isinstance(assets[path], bytes)
        and sha(assets[path]) == ref["sha256"],
        "asset digest: " + path,
    )
    return assets[path]


def seed_payloads(registry, assets, canonical):
    need(isinstance(registry, dict) and len(registry) >= 5, "seed registry")
    result = {}
    jvp_seen = set()
    vjp_seen = set()
    for key, ref in registry.items():
        data = json.loads(asset(ref, assets))
        need(
            data["id"] == key and data["schema"] == "kdm6.derivative_seed.v1",
            "seed identity",
        )
        mode = data["derivative_mode"]
        if mode == "jvp":
            direction = data["direction_id"]
            need(
                key == "jvp:" + direction
                and direction in canonical["direction_seeds"]
                and data["cotangent_id"] == "none",
                "JVP seed identity",
            )
            actual = words(data["words"], 624, "JVP seed")
            seed = canonical["direction_seeds"][direction]
            expected = [ZERO] * 624
            expected[
                FIELDS.index(seed["field"]) * 39 + seed["level_zero_bottom_first"]
            ] = seed["scale_f64_word"]
            need(actual == expected, "JVP seed words differ from plan")
            jvp_seen.add(direction)
        elif mode == "vjp":
            ident = data["cotangent_id"]
            match = re.fullmatch(r"state:([a-z]+):([0-9]+)", ident)
            need(
                match is not None
                and match.group(1) in FIELDS[:12]
                and int(match.group(2)) < 39
                and str(int(match.group(2))) == match.group(2),
                "VJP cotangent ID",
            )
            need(
                key == "vjp:" + ident and data["direction_id"] == "none",
                "VJP seed identity",
            )
            actual = words(data["words"], 468, "VJP cotangent")
            expected = [ZERO] * 468
            expected[FIELDS.index(match.group(1)) * 39 + int(match.group(2))] = ONE
            need(actual == expected, "VJP cotangent words differ from ID")
            vjp_seen.add(ident)
        else:
            raise ValueError("unknown seed mode")
        expected_sha = word_sha(actual)
        need(data["seed_sha256"] == expected_sha, "seed word SHA-256")
        result[(mode, data["direction_id"], data["cotangent_id"])] = expected_sha
    need(
        jvp_seen == set(canonical["direction_seeds"]) and vjp_seen,
        "missing seed direction or cotangent",
    )
    return result


def effective_seed_specs():
    """Use the gate's pinned endpoints and its exact binary64 arithmetic."""
    raw = (HERE / "plan.json.gz").read_bytes()
    specs = {}
    for center, directions in (
        ("baseline", ("nc", "th", "qv")),
        ("lower", ("nc", "pii", "th", "qv")),
        ("upper", ("nc", "pii", "th", "qv")),
    ):
        for direction in directions:
            gate_plan = fd_gate.canonical_plan(raw, PLAN_GZ_SHA, center, direction, 0)
            for step in gate_plan["steps"]:
                h = fd_gate.val(step["h_word"])
                denominator = h if step["stencil"] == "forward" else 2 * h
                seed = [
                    fd_gate.word((fd_gate.val(b) - fd_gate.val(a)) / denominator)
                    for a, b in zip(
                        step["lower_input_words"], step["upper_input_words"]
                    )
                ]
                ident = f"{center}:{direction}:{step['id']}"
                need(ident not in specs, "duplicate effective seed ID")
                specs[ident] = {
                    "center": center,
                    "direction": direction,
                    "step_id": step["id"],
                    "evaluation_input_words": gate_plan["center_input_words"],
                    "effective_direction_words": seed,
                }
    need(len(specs) == 21, "effective seed inventory")
    return specs


def validate_effective_jvps(
    refs, assets, outputs, call_sequences, graph_handles, graph_jvp_hashes
):
    specs = effective_seed_specs()
    need(isinstance(refs, dict) and set(refs) == set(specs), "effective JVP inventory")
    for center in ("baseline", "lower", "upper"):
        need(
            set(graph_jvp_hashes[center])
            == {key for key, spec in specs.items() if spec["center"] == center},
            "graph JVP inventory",
        )
    for ident, spec in specs.items():
        payload = json.loads(asset(refs[ident], assets))
        need(
            payload["schema"] == "kdm6.effective_jvp_payload.v1"
            and payload["id"] == ident
            and payload["center"] == spec["center"]
            and payload["direction"] == spec["direction"]
            and payload["step_id"] == spec["step_id"],
            "effective JVP identity",
        )
        center = spec["center"]
        need(
            type(payload["jvp_return_code"]) is int and payload["jvp_return_code"] == 0,
            "effective JVP return code",
        )
        need(
            payload["graph_handle_id"] == graph_handles[center],
            "effective JVP graph handle",
        )
        need(
            type(payload["graph_sequence"]) is int
            and payload["graph_sequence"]
            == call_sequences[(center, "center_joint_graph")],
            "effective JVP graph call",
        )
        need(
            words(payload["evaluation_input_words"], 624, "JVP evaluation input")
            == spec["evaluation_input_words"],
            "effective JVP evaluation input",
        )
        direction = words(
            payload["effective_direction_words"], 624, "effective JVP direction"
        )
        need(
            direction == spec["effective_direction_words"]
            and payload["seed_sha256"] == word_sha(direction),
            "effective JVP seed mismatch",
        )
        forward = words(
            payload["graph_forward_output_words"], 468, "JVP forward output"
        )
        need(
            forward == outputs[(center, "center_joint_graph")],
            "effective JVP graph forward output",
        )
        jvp = words(payload["jvp_output_words"], 468, "JVP output")
        need(
            payload["jvp_output_sha256"]
            == word_sha(jvp)
            == graph_jvp_hashes[center][ident],
            "effective JVP output hash/graph binding",
        )
    return len(specs)


CONDITION_KEY_FIELDS = (
    "runtime_call",
    "one_step_call",
    "substep",
    "b_zero",
    "k_zero",
    "native_level_bottom_first",
    "stage",
    "field",
    "event_ordinal",
)
BASELINE_CAPTURE = (
    HERE.parent
    / "native_host_batch3_shared_2026-11-12/raw/stage_compare_f64_baseline.csv.gz"
)
BASELINE_CAPTURE_SHA = (
    "e84e020e8c4c219d9e93c3165c5e42cae8f53db1ec8b4fbc7826f6b6609c5649"
)
BASELINE_CSV_SHA = "49d60ae156212acdf987577ec271f4b5a56a318b5a9ff4829c36419397e29aba"


def condition_key(row):
    return "|".join(str(row[k]) for k in CONDITION_KEY_FIELDS)


def condition_contract():
    raw = BASELINE_CAPTURE.read_bytes()
    need(sha(raw) == BASELINE_CAPTURE_SHA, "baseline condition gzip SHA")
    return _condition_contract(raw)


@functools.lru_cache(maxsize=1)
def _condition_contract(raw):
    text = gzip.decompress(raw)
    need(sha(text) == BASELINE_CSV_SHA, "baseline condition CSV SHA")
    rows = list(
        csv.DictReader(
            line
            for line in io.StringIO(text.decode("ascii"))
            if not line.startswith("#")
        )
    )
    need(len(rows) == 19656, "baseline condition row count")
    masks = {}
    schedule = {}
    for r in rows:
        key = "|".join(
            (
                r["runtime_call"],
                r["one_step_call"],
                r["substep"],
                r["b_zero"],
                r["k_zero"],
                str(39 - int(r["k_zero"])),
                r["stage"],
                r["field"],
                "0",
            )
        )
        if r["dtype"] == "bool":
            need(
                key not in masks and r["raw_hex"] in ("0", "1"),
                "baseline mask identity",
            )
            masks[key] = r["raw_hex"] == "1"
        if (
            r["stage"] == "runtime_full_schedule"
            and r["field"]
            in ("mstep_ice_col", "mstep_main_col", "mstepmax_ice", "mstepmax_main")
        ) or (r["stage"] == "runtime_full_meta" and r["field"] == "loops"):
            need(
                key not in schedule and r["dtype"] == "f64",
                "baseline schedule identity",
            )
            schedule[key] = r["raw_hex"].zfill(16)
    need(len(masks) == 1170 and len(schedule) == 195, "baseline condition counts")
    mask_keys = tuple(sorted(masks))
    schedule_keys = tuple(sorted(schedule))
    contract = {"mask_keys": list(mask_keys), "schedule_keys": list(schedule_keys)}
    contract_sha = sha(
        json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
    )
    return mask_keys, schedule_keys, contract_sha, masks, schedule


def validate_conditions(receipt, assets, inputs, call_sequences):
    mask_keys, schedule_keys, contract_sha, _, _ = condition_contract()
    refs = receipt.get("condition_assets")
    need(
        isinstance(refs, dict) and set(refs) == set(inputs), "condition call inventory"
    )
    result = {}
    for input_id, ref in refs.items():
        obj = json.loads(asset(ref, assets))
        need(
            obj["schema"] == "kdm6.captured_conditions.v1"
            and obj["input_id"] == input_id
            and obj["mode"] == "capture_on_value"
            and type(obj["call_sequence"]) is int
            and obj["call_sequence"] == call_sequences[(input_id, "capture_on_value")]
            and obj["condition_contract_sha256"] == contract_sha,
            "condition call identity/contract",
        )
        mv, sv = obj["mask_values"], obj["schedule_words"]
        need(
            isinstance(mv, list)
            and len(mv) == len(mask_keys)
            and all(type(v) is bool for v in mv),
            "complete condition masks",
        )
        words(sv, len(schedule_keys), "complete condition schedules")
        result[input_id] = {
            "masks": dict(zip(mask_keys, mv)),
            "schedule": dict(zip(schedule_keys, sv)),
        }
    return result


def validate(receipt, assets):
    """Validate complete declared call/asset/coverage relationships, not truth."""
    canonical, inventory = load_plan()
    need(
        isinstance(receipt, dict)
        and receipt.get("schema") == "kdm6.native_host_capture_receipt.v1",
        "receipt schema",
    )
    need(
        receipt.get("plan_gzip_sha256") == PLAN_GZ_SHA
        and receipt.get("base_source_hashes")
        == canonical["build_requirements"]["source_pins"],
        "plan/source hashes",
    )
    build = receipt["build"]
    need(
        hex_sha(build["new_instrumented_dso_sha256"])
        and build["new_instrumented_dso_sha256"]
        != canonical["build_requirements"]["installed_dso_sha256"],
        "new instrumented DSO hash",
    )
    need(
        build["installed_dso_sha256"]
        == canonical["build_requirements"]["installed_dso_sha256"]
        and build["controls"] == canonical["controls"],
        "DSO/controls",
    )
    need(
        isinstance(build["compiler_identity"], str)
        and build["compiler_identity"].strip()
        and isinstance(build["compiler_flags"], list)
        and "-ffp-contract=off" in build["compiler_flags"],
        "compiler flags/identity",
    )
    need(
        build["test_assertions_enabled"] is True
        and isinstance(build["modified_source_sha256"], dict)
        and set(build["modified_source_sha256"])
        >= {
            "libtorch/src/runtime.cpp",
            "libtorch/src/coordinator.cpp",
            "libtorch/src/sedimentation.cpp",
        }
        and all(hex_sha(x) for x in build["modified_source_sha256"].values()),
        "instrumented source hashes",
    )
    source_assets = build["modified_source_assets"]
    need(
        isinstance(source_assets, dict)
        and set(source_assets) == set(build["modified_source_sha256"]),
        "modified source assets",
    )
    for name, ref in source_assets.items():
        need(
            sha(asset(ref, assets)) == build["modified_source_sha256"][name],
            "modified source asset hash",
        )
    deps = build["dependency_sha256"]
    need(
        isinstance(deps, dict)
        and set(deps)
        >= {"libtorch.dylib", "libtorch_cpu.dylib", "libc10.dylib", "libomp.dylib"}
        and all(hex_sha(x) for x in deps.values()),
        "dependency hashes",
    )
    need(
        type(receipt["elapsed_seconds"]) in (int, float)
        and math.isfinite(receipt["elapsed_seconds"])
        and 0 <= receipt["elapsed_seconds"] <= 900,
        "wall time budget",
    )
    seeds = seed_payloads(receipt["seed_assets"], assets, canonical)
    planned = canonical["calls"]
    calls = receipt["calls"]
    need(
        isinstance(calls, list) and len(calls) == len(planned) == 100,
        "complete call ledger",
    )
    inputs = {x["id"]: x for x in canonical["inputs"]}
    outputs = {}
    used_assets = set()
    call_sequences = {}
    graph_handles = {}
    graph_jvp_hashes = {}
    for spec, call in zip(planned, calls):
        need(
            type(call["sequence"]) is int
            and (call["sequence"], call["input_id"], call["mode"])
            == (spec["sequence"], spec["input_id"], spec["mode"]),
            "call identity/order",
        )
        optional = spec["status"] == "PLANNED_OPTIONAL"
        if call["status"] == "skipped":
            need(
                optional
                and isinstance(call.get("reason"), str)
                and call["reason"].strip()
                and call.get("output_asset") is None,
                "invalid skipped call",
            )
            continue
        need(
            call["status"] == "completed"
            and type(call.get("return_code")) is int
            and call["return_code"] == 0,
            "required call incomplete/failed",
        )
        ref = call["output_asset"]
        payload = json.loads(asset(ref, assets))
        need(ref["path"] not in used_assets, "reused call asset")
        used_assets.add(ref["path"])
        need(
            payload["schema"] == "kdm6.future_call_raw.v1"
            and (payload["sequence"], payload["input_id"], payload["mode"])
            == (call["sequence"], call["input_id"], call["mode"]),
            "call payload identity",
        )
        if call["mode"] == "center_joint_graph":
            handle = payload.get("graph_handle_id")
            need(
                isinstance(handle, str)
                and handle
                and handle not in graph_handles.values(),
                "graph handle identity",
            )
            graph_handles[call["input_id"]] = handle
            need(
                isinstance(payload.get("effective_jvp_output_sha256"), dict),
                "graph JVP output hashes",
            )
            graph_jvp_hashes[call["input_id"]] = payload["effective_jvp_output_sha256"]
        expected_dso = (
            build["installed_dso_sha256"]
            if call["mode"] == "installed_value_optional"
            else build["new_instrumented_dso_sha256"]
        )
        need(payload["dso_sha256"] == expected_dso, "call DSO mismatch")
        call_sequences[(call["input_id"], call["mode"])] = call["sequence"]
        need(
            words(payload["input_words"], 624, "call input")
            == inputs[call["input_id"]]["words"],
            "call input differs from plan",
        )
        out = words(payload["state_output_words"], 468, "call output")
        outputs[(call["input_id"], call["mode"])] = out
    for key in inputs:
        need(
            outputs[(key, "capture_off_value")] == outputs[(key, "capture_on_value")],
            "capture off/on output mismatch",
        )
    for (key, mode), out in outputs.items():
        if mode in ("center_joint_graph", "installed_value_optional"):
            need(
                out == outputs[(key, "capture_off_value")],
                "graph/installed output mismatch",
            )
    effective_count = validate_effective_jvps(
        receipt["effective_jvp_assets"],
        assets,
        outputs,
        call_sequences,
        graph_handles,
        graph_jvp_hashes,
    )
    conditions = validate_conditions(receipt, assets, inputs, call_sequences)
    records = json.loads(asset(receipt["capture_records_asset"], assets))
    need(
        isinstance(records, dict)
        and records.get("schema") == "kdm6.future_capture_records.v1",
        "capture records schema",
    )
    records = records["records"]
    plan.validate_record_identity(records, inventory, canonical)
    ids = {}
    coverage = defaultdict(set)
    for row in records:
        rid = row["record_id"]
        need(isinstance(rid, str) and rid and rid not in ids, "duplicate record ID")
        ids[rid] = row
        need(
            type(row["call_sequence"]) is int
            and call_sequences.get((row["input_id"], row["mode"]))
            == row["call_sequence"],
            "capture call binding",
        )
        group = row["group"]
        idx = row["requirement_index"]
        kind = row["record_kind"]
        need(
            group in inventory["groups"]
            and type(idx) is int
            and 0 <= idx < len(inventory["groups"][group]["new_requirements"]),
            "coverage requirement identity",
        )
        need(
            row["requirement"] == inventory["groups"][group]["new_requirements"][idx],
            "coverage requirement text",
        )
        if kind == "live_tangent":
            identity = (
                row["derivative_mode"],
                row["direction_id"],
                row["cotangent_id"],
            )
            need(
                identity in seeds and row["seed_sha256"] == seeds[identity],
                "live record seed payload mismatch",
            )
            seedkey = (row["derivative_mode"], row["direction_id"], row["cotangent_id"])
        else:
            seedkey = ("none", "none", "none")
        if row["availability"] == "present":
            need(
                row.get("inactive_reason") is None
                and row.get("inactive_mask_id") is None,
                "present field absence metadata",
            )
            if kind == "mask":
                key = condition_key(row)
                need(
                    key in conditions[row["input_id"]]["masks"]
                    and conditions[row["input_id"]]["masks"][key]
                    == (row["raw_hex"] == "1"),
                    "mask condition binding",
                )
                need(
                    row["dtype"] == "bool" and row["raw_hex"] in ("0", "1"),
                    "mask raw word",
                )
            else:
                need(
                    row["dtype"] == "f64"
                    and len(words([row["raw_hex"]], 1, "capture raw")) == 1,
                    "capture raw word",
                )
        elif row["availability"] == "inactive":
            need(kind == "value", "inactive mask or live tangent unsupported")
            need(
                isinstance(row.get("inactive_reason"), str)
                and row["inactive_reason"].strip()
                and row.get("raw_hex") is None
                and isinstance(row.get("inactive_mask_id"), str),
                "inactive absence reason",
            )
        else:
            raise ValueError("field availability")
        coverage[(row["input_id"], group, idx, kind)].add(seedkey)
    for row in records:
        if row["availability"] == "inactive":
            mask = ids.get(row["inactive_mask_id"])
            context = (
                "input_id",
                "call_sequence",
                "mode",
                "runtime_call",
                "one_step_call",
                "substep",
                "b_zero",
                "k_zero",
                "native_level_bottom_first",
                "stage",
                "group",
                "requirement_index",
            )
            need(
                mask is not None
                and mask["record_kind"] == "mask"
                and mask["availability"] == "present"
                and mask["raw_hex"] == "0"
                and all(mask[key] == row[key] for key in context),
                "inactive mask evidence",
            )
    required_seeds = set(seeds)
    for group, spec in inventory["groups"].items():
        for idx in range(len(spec["new_requirements"])):
            for key in inputs:
                for kind in ("value", "mask"):
                    need(
                        coverage[(key, group, idx, kind)],
                        f"missing {kind} coverage: {key}/{group}/{idx}",
                    )
            for center in ("baseline", "lower", "upper"):
                need(
                    required_seeds <= coverage[(center, group, idx, "live_tangent")],
                    f"missing live coverage: {center}/{group}/{idx}",
                )
    return {
        "status": "NOT_ELIGIBLE_UNVERIFIED_PROVENANCE",
        "effective_jvp_linkage": "REPRESENTED_SEEDS_AND_GRAPH_FORWARD_LINKED_UNVERIFIED",
        "effective_jvp_payloads": effective_count,
        "live_intermediate_effective_tangents": "NOT_LINKED",
        "fd_gate_ready": False,
        "scope": "schema and caller-supplied byte relationships only; no model executed or independent provenance verified",
        "calls": len(calls),
        "inputs": len(inputs),
        "capture_records": len(records),
        "seed_payloads": len(seeds),
    }


def validate_scheduler_bridge(
    receipt, scheduler, assets, *, scheduler_bytes, completion_bytes
):
    """Bind the synthetic scheduler envelope to the semantic bundle.

    The existing scheduler is synthetic-only. Matching it cannot establish a
    physical execution or independent provenance, even if all bytes agree.
    """
    need(
        isinstance(scheduler_bytes, bytes) and isinstance(completion_bytes, bytes),
        "scheduler receipt/marker bytes required",
    )
    need(json.loads(scheduler_bytes) == scheduler, "scheduler receipt bytes mismatch")
    marker = json.loads(completion_bytes)
    need(
        isinstance(marker, dict)
        and set(marker)
        == {"schema", "execution_scope", "plan_sha256", "receipt_sha256"}
        and marker["schema"] == "kdm6.native_host_preflight.budget_completion.v1"
        and marker["execution_scope"] == "SYNTHETIC_TEST_ONLY"
        and marker["receipt_sha256"] == sha(scheduler_bytes)
        and marker["plan_sha256"] == scheduler.get("plan_sha256"),
        "scheduler completion marker",
    )
    result = validate(receipt, assets)
    canonical, _ = load_plan()
    need(
        scheduler.get("schema") == "kdm6.native_host_preflight.execution_budget.v1"
        and scheduler.get("execution_scope") == "SYNTHETIC_TEST_ONLY"
        and scheduler.get("status") == "SYNTHETIC_COMPLETED_UNVERIFIED",
        "scheduler scope/status",
    )
    bound = json.loads(json.dumps(canonical))
    bound["build_requirements"]["instrumented_dso_sha256"] = receipt["build"][
        "new_instrumented_dso_sha256"
    ]
    digest = sha(
        json.dumps(
            bound, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    )
    need(
        scheduler.get("plan_gzip_sha256") == PLAN_GZ_SHA
        and scheduler.get("plan_sha256") == digest
        and scheduler.get("dso_sha256")
        == receipt["build"]["new_instrumented_dso_sha256"],
        "scheduler plan/DSO binding",
    )
    need(
        scheduler.get("controls") == canonical["controls"]
        and scheduler.get("limits") == canonical["limits"],
        "scheduler controls/limits",
    )
    need(
        type(scheduler.get("elapsed_seconds")) in (int, float)
        and math.isfinite(scheduler["elapsed_seconds"])
        and 0 <= scheduler["elapsed_seconds"] <= 900,
        "scheduler elapsed budget",
    )
    calls = scheduler.get("calls")
    need(
        isinstance(calls, list) and len(calls) == len(receipt["calls"]) == 100,
        "scheduler call count",
    )
    for expected, actual, planned in zip(receipt["calls"], calls, canonical["calls"]):
        need(
            all(
                actual.get(k) == expected[k]
                for k in ("sequence", "input_id", "mode", "status")
            )
            and type(actual.get("sequence")) is int,
            "scheduler call identity/status",
        )
        need(
            actual.get("required") is (planned["status"] == "PLANNED"),
            "scheduler required flag",
        )
        if expected["status"] == "completed":
            ref = expected["output_asset"]
            need(
                actual.get("returncode") == 0
                and type(actual.get("returncode")) is int
                and actual.get("output_path") == ref["path"]
                and actual.get("output_sha256") == ref["sha256"],
                "scheduler output asset binding",
            )
        else:
            need(
                actual.get("reason") == expected.get("reason"),
                "scheduler skipped reason",
            )
    return {**result, "scheduler_binding": "SYNTHETIC_ONLY_UNVERIFIED"}
