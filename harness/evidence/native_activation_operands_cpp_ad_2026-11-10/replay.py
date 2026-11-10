#!/usr/bin/env python3
"""Child replay scaffold for native activation operand captures.

The #575 boundary replay owns the broad input/branch/AD evidence. This child
packet imports and verifies that parent before reading its own operand payload.
Operand schema validation is intentionally pending the frozen runner result.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from functools import lru_cache
from pathlib import Path
import struct


HERE = Path(__file__).resolve().parent
EVIDENCE = HERE.parent
PARENT = EVIDENCE / "native_activation_upper_boundary_cpp_ad_2026-11-10"
THERMAL_PARENT = EVIDENCE / "native_d1_thermal_input_cpp_ad_2026-11-10"
PARENT_REPLAY_SHA256 = "5f5bd5f80638601961ac040ad364753f2964a6a92fb13e8dc2dbd58036d3af51"
PARENT_MANIFEST_SHA256 = "65e8497cc7e1b79f6d50cdf5e56675b0008e354059cc2d2217f3fe673c15619e"
PARENT_BOUNDARY_SHA256 = "b80da7363594c00b700b4a4a2e12d1e41569ce1a51232100cdb0c36d4d6f90d3"
MANIFEST_SHA256 = "99b4aceb3c34d01faf348c63af4a5f27358666798e357809688ae9976cef9c4d"
ACTIVATION_EXECUTED_COORDINATOR = (
    EVIDENCE / "native_d1_coeres_upstream_cpp_ad_2026-11-10/executed_cpp/coordinator.cpp")
OPERAND_PAYLOAD = HERE / "raw/activation_boundary.json"
OPERAND_BOUNDARY_SCHEMA = "kdm6.native_d1_activation_boundary_operands.v1"
EVENT_IDENTITY_FIELDS = {"event_id", "forward_call_ordinal", "trace_index"}
OPERAND_NUMERIC_FIELDS = (
    "sw_ratio", "safe_pow_clamped_base_diagnostic", "activation_fraction_one",
    "activation_fraction_pow", "activation_fraction_min_output", "ncact_preclamp_fma",
    "ncact_clamped_numerator", "ncact_nccn_rate_cap", "ncact_min_output",
)
OPERAND_BOOLEAN_FIELDS = (
    "activation_fraction_pow_lt_one", "activation_fraction_pow_eq_one",
    "activation_fraction_pow_gt_one", "ncact_raw_lt_nccn_rate_cap",
    "ncact_raw_eq_nccn_rate_cap", "ncact_raw_gt_nccn_rate_cap",
)
OPERAND_AD_JVP_FIELDS = OPERAND_NUMERIC_FIELDS
OPERAND_AD_VJP_FIELDS = tuple(field for field in OPERAND_NUMERIC_FIELDS
                               if field != "activation_fraction_one")
OPERAND_WORD_FIELDS = {
    "sw_ratio": "sw_ratio_word",
    "safe_pow_clamped_base_diagnostic": "safe_pow_clamped_base_diagnostic_word",
    "activation_fraction_pow": "activation_fraction_pow_word",
    "ncact_nccn_rate_cap": "ncact_nccn_rate_cap_word",
}
OPERAND_BOOL_STAGE_FIELDS = {
    "activation_fraction_pow_lt_one", "activation_fraction_pow_eq_one",
    "activation_fraction_pow_gt_one", "ncact_raw_lt_nccn_rate_cap",
    "ncact_raw_eq_nccn_rate_cap", "ncact_raw_gt_nccn_rate_cap",
}
OPERAND_STAGE_NAMES = {
    "fd_satadj_inner." + name
    for name in (*OPERAND_NUMERIC_FIELDS, *OPERAND_BOOL_STAGE_FIELDS)
}
OPERAND_NUMERIC_STAGE_NAMES = OPERAND_STAGE_NAMES - {
    "fd_satadj_inner." + name for name in OPERAND_BOOL_STAGE_FIELDS
}
EPS = 1.0e-15
ACTK = 0.6
ACTIVATION_FD_STEPS = {
    "th16": {
        "fraction_eq_one": (1.0e-4, 1.0e-5, 1.0e-6),
        "fraction_below_one": (1.0e-4, 1.0e-5, 1.0e-6, 1.0e-7),
    },
    "qv16": {
        "fraction_eq_one": (1.0e-3, 1.0e-4, 1.0e-5, 1.0e-6, 1.0e-7),
        "fraction_below_one": (1.0e-5, 1.0e-6, 1.0e-7, 1.0e-8),
    },
}

OPERAND_VALUE_KEYS = {
    "sw_ratio", "sw_ratio_word", "safe_pow_clamped_base_diagnostic",
    "safe_pow_clamped_base_diagnostic_word", "activation_fraction_one",
    "activation_fraction_pow", "activation_fraction_pow_word",
    "activation_fraction_min_output", "activation_fraction_pow_lt_one",
    "activation_fraction_pow_eq_one", "activation_fraction_pow_gt_one",
    "ncact_preclamp_fma", "ncact_clamped_numerator", "ncact_nccn_rate_cap",
    "ncact_nccn_rate_cap_word", "ncact_min_output",
    "ncact_raw_lt_nccn_rate_cap", "ncact_raw_eq_nccn_rate_cap",
    "ncact_raw_gt_nccn_rate_cap",
}


def need(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def reject_json_constant(value: str) -> None:
    raise ValueError("nonstandard JSON numeric constant: " + value)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def f64_word(value: float) -> str:
    return format(struct.unpack(">Q", struct.pack(">d", float(value)))[0], "016x")


def exact(left: float, right: float, message: str) -> None:
    need(math.isfinite(float(left)) and math.isfinite(float(right)), message + " finite operands")
    need(f64_word(float(left)) == f64_word(float(right)), message)


def nonnegative_ulp_distance(left: float, right: float) -> int:
    need(math.isfinite(left) and math.isfinite(right) and left >= 0.0 and right >= 0.0,
         "ULP distance requires finite nonnegative values")
    return abs(int(f64_word(left), 16) - int(f64_word(right), 16))


def require_finite_tree(value: object, where: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            require_finite_tree(child, where + "/" + str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            require_finite_tree(child, where + "/" + str(index))
    elif isinstance(value, bool) or value is None or isinstance(value, str):
        return
    elif isinstance(value, (int, float)):
        need(math.isfinite(float(value)), where + " finite JSON number")


def compare_parent_projection(parent: object, child: object, parent_module: object,
                              path: str = "root") -> None:
    """Require every old value-tree field unchanged while allowing child fields.

    Only the top-level schema may differ by design. Numeric leaves are compared
    with the parent replay's f64-bit-aware comparator.
    """
    if path == "root/schema":
        need(child == OPERAND_BOUNDARY_SCHEMA, "child operand schema")
        return
    if isinstance(parent, dict):
        need(isinstance(child, dict), "child projection object type: " + path)
        allowed_extras: set[str] = set()
        if path == "root":
            allowed_extras.add("parent_schema")
            need(child.get("parent_schema") == "kdm6.native_d1_activation_boundary.v1",
                 "child declares the correct parent boundary schema")
        elif path.endswith("/output_gaps") or path.endswith("/outputs"):
            allowed_extras.update(OPERAND_NUMERIC_FIELDS)
        elif path.endswith("/jvp"):
            allowed_extras.update(OPERAND_AD_JVP_FIELDS)
        elif path.endswith("/vjp_rows"):
            allowed_extras.update(OPERAND_AD_VJP_FIELDS)
        elif "input_word" in parent and "d1_branch" in parent:
            allowed_extras.update({"operand_values", *EVENT_IDENTITY_FIELDS})
        elif {"input", "branch", "jvp", "vjp_rows"}.issubset(parent):
            allowed_extras.update({"event_id", "forward_call_ordinal"})
        elif {"endpoint", "outputs", "nominal_step"}.issubset(parent):
            allowed_extras.update({"event_id", "forward_call_ordinal", "same_operand_branch"})
        need(set(child) == set(parent) | allowed_extras,
             "child projection key inventory: " + path)
        for key, value in parent.items():
            compare_parent_projection(value, child[key], parent_module, path + "/" + str(key))
    elif isinstance(parent, list):
        need(isinstance(child, list) and len(parent) == len(child),
             "child projection list shape: " + path)
        for index, (parent_value, child_value) in enumerate(zip(parent, child)):
            compare_parent_projection(parent_value, child_value, parent_module,
                                      path + "/" + str(index))
    else:
        need(parent_module.same_recorded_tree(parent, child),
             "child projection changes parent value: " + path)


def _project_old_stage_map(old_map: dict, new_map: dict, parent_module: object,
                           why: str) -> None:
    projected = {key: value for key, value in new_map.items() if key not in OPERAND_STAGE_NAMES}
    need(set(projected) == set(old_map), why + " old stage key inventory")
    for key, value in old_map.items():
        need(parent_module.same_recorded_tree(value, projected[key]),
             why + " old stage value/raw type: " + key)


def verify_default_cpp_projection(old_data: dict, new_data: dict,
                                  parent_module: object) -> dict[str, int]:
    need(new_data["schema"] == old_data["schema"], "default C++ result schema unchanged")
    need(set(new_data) == set(old_data), "default C++ top-level keys unchanged")
    old_order, new_order = old_data["stage_numeric_order"], new_data["stage_numeric_order"]
    need(len(new_order) == len(set(new_order))
         and len(new_order) == len(old_order) + len(OPERAND_NUMERIC_STAGE_NAMES)
         and new_order == sorted(new_order),
         "default C++ stage order is unique, sorted and complete")
    need([name for name in new_order if name not in OPERAND_STAGE_NAMES] == old_order,
         "default C++ stage order projects to parent")
    need(set(new_order) == set(old_order) | OPERAND_NUMERIC_STAGE_NAMES,
         "default C++ numeric operand stage additions")
    need(set(new_data["baseline"]) == set(old_data["baseline"]),
         "default C++ baseline field inventory")
    for key, value in old_data["baseline"].items():
        if key in ("stage_scalars", "stage_types"):
            _project_old_stage_map(value, new_data["baseline"][key], parent_module,
                                   "default C++ baseline " + key)
        else:
            need(parent_module.same_recorded_tree(value, new_data["baseline"][key]),
                 "default C++ parent baseline raw field: " + key)
    for key in set(old_data) - {"schema", "stage_numeric_order", "baseline", "directions"}:
        if key == "thermal_directions":
            verify_thermal_directions_projection(old_data[key], new_data[key], old_order,
                                                 new_order, parent_module)
        else:
            need(parent_module.same_recorded_tree(old_data[key], new_data[key]),
                 "default C++ parent raw field: " + key)
    need(set(new_data["directions"]) == set(old_data["directions"]),
         "default C++ direction inventory")
    for direction_name, old_direction in old_data["directions"].items():
        new_direction = new_data["directions"][direction_name]
        need(set(new_direction) == set(old_direction),
             "default C++ direction fields: " + direction_name)
        for key, old_value in old_direction.items():
            if key == "stage_jvp":
                need(len(new_value := new_direction[key]) == len(new_order),
                     "default C++ stage JVP shape: " + direction_name)
                mapped = dict(zip(new_order, new_value))
                projected = [mapped[name] for name in old_order]
                need(parent_module.same_recorded_tree(old_value, projected),
                     "default C++ parent stage JVP: " + direction_name)
            elif key == "finite_differences":
                need(set(new_direction[key]) == set(old_value),
                     "default C++ FD step inventory: " + direction_name)
                for h, old_pair in old_value.items():
                    new_pair = new_direction[key][h]
                    need(set(new_pair) == set(old_pair),
                         "default C++ FD fields: " + direction_name + "/" + h)
                    for side in ("low", "high"):
                        _project_old_stage_map(
                            old_pair[side + "_stages"], new_pair[side + "_stages"],
                            parent_module, "default C++ FD stages " + direction_name + "/" + h + "/" + side)
                    for pair_key in set(old_pair) - {"low_stages", "high_stages"}:
                        need(parent_module.same_recorded_tree(old_pair[pair_key], new_pair[pair_key]),
                             "default C++ FD raw: " + direction_name + "/" + h + "/" + pair_key)
            else:
                need(parent_module.same_recorded_tree(old_value, new_direction[key]),
                     "default C++ direction raw: " + direction_name + "/" + key)
    return {"old_numeric_stage_fields_projected": len(old_order),
            "new_numeric_operand_stages": len(OPERAND_NUMERIC_STAGE_NAMES),
            "old_baseline_stage_fields_projected": len(old_data["baseline"]["stage_scalars"])}


def verify_thermal_directions_projection(old_thermal: dict, new_thermal: dict,
                                         old_order: list[str], new_order: list[str],
                                         parent_module: object) -> None:
    need(set(new_thermal) == set(old_thermal), "default thermal-direction key inventory")
    for key in (set(old_thermal) - {"directions"}):
        need(parent_module.same_recorded_tree(old_thermal[key], new_thermal[key]),
             "default thermal-direction parent data: " + key)
    need(set(new_thermal["directions"]) == set(old_thermal["directions"]),
         "default thermal direction names")
    for name, old_direction in old_thermal["directions"].items():
        new_direction = new_thermal["directions"][name]
        need(set(new_direction) == set(old_direction),
             "default thermal direction fields: " + name)
        for key, old_value in old_direction.items():
            if key == "jvp":
                need(set(new_direction[key]) == set(old_value),
                     "default thermal JVP fields: " + name)
                for jvp_key, old_jvp in old_value.items():
                    if jvp_key == "stage_jvp":
                        values = new_direction[key][jvp_key]
                        need(len(values) == len(new_order)
                             and all(isinstance(value, (int, float))
                                     and not isinstance(value, bool)
                                     and math.isfinite(float(value)) for value in values),
                             "default thermal stage JVP shape/finite: " + name)
                        mapped = dict(zip(new_order, values))
                        projected = [mapped[stage] for stage in old_order]
                        need(parent_module.same_recorded_tree(old_jvp, projected),
                             "default thermal parent stage JVP: " + name)
                    else:
                        need(parent_module.same_recorded_tree(old_jvp,
                                                               new_direction[key][jvp_key]),
                             "default thermal parent JVP: " + name + "/" + jvp_key)
            elif key == "finite_differences":
                need(set(new_direction[key]) == set(old_value),
                     "default thermal FD step inventory: " + name)
                for step, old_pair in old_value.items():
                    new_pair = new_direction[key][step]
                    need(set(new_pair) == set(old_pair),
                         "default thermal FD pair fields: " + name + "/" + step)
                    for side in ("high", "low"):
                        _project_old_stage_map(
                            old_pair[side + "_stages"], new_pair[side + "_stages"],
                            parent_module, "default thermal FD stages " + name + "/" + step + "/" + side)
                    for pair_key in set(old_pair) - {"high_stages", "low_stages"}:
                        need(parent_module.same_recorded_tree(old_pair[pair_key], new_pair[pair_key]),
                             "default thermal FD parent data: " + name + "/" + step + "/" + pair_key)
            else:
                need(parent_module.same_recorded_tree(old_value, new_direction[key]),
                     "default thermal parent direction data: " + name + "/" + key)


def verify_operand_observation(row: dict, why: str) -> dict[str, object]:
    require_finite_tree(row, why)
    operands = row["operand_values"]
    need(set(operands) == OPERAND_VALUE_KEYS, why + " operand field inventory")
    values = {name: float(operands[name]) for name in OPERAND_NUMERIC_FIELDS}
    need(all(math.isfinite(value) for value in values.values()), why + " finite operands")
    for name, word_name in OPERAND_WORD_FIELDS.items():
        need(str(operands[word_name]).zfill(16) == f64_word(values[name]),
             why + " operand raw word: " + name)
    for name in OPERAND_BOOLEAN_FIELDS:
        need(type(operands[name]) is bool, why + " bool operand flag: " + name)

    sw_percent = float(row["sw_percent"])
    sw_ratio = max(sw_percent / 0.48, 0.0)
    need(math.isfinite(sw_ratio), why + " finite sw_ratio calculation")
    exact(values["sw_ratio"], sw_ratio, why + " sw_ratio source order")
    pow_base = max(sw_ratio, EPS)
    exact(values["safe_pow_clamped_base_diagnostic"], pow_base,
          why + " safe_pow clamp diagnostic")
    exact(values["activation_fraction_one"], 1.0, why + " min-one operand")
    expected_pow = math.pow(pow_base, ACTK)
    pow_distance = nonnegative_ulp_distance(expected_pow, values["activation_fraction_pow"])
    need(pow_distance <= 16, why + " independent activation safe_pow within portable ULP")
    pow_value = values["activation_fraction_pow"]
    if pow_base == 1.0:
        exact(pow_value, 1.0, why + " exact safe_pow(1, ACTK) value")
    expected_flags = {
        "activation_fraction_pow_lt_one": pow_value < 1.0,
        "activation_fraction_pow_eq_one": pow_value == 1.0,
        "activation_fraction_pow_gt_one": pow_value > 1.0,
    }
    for name, expected in expected_flags.items():
        need(operands[name] is expected, why + " pow comparator: " + name)
    expected_fraction = min(values["activation_fraction_one"], pow_value)
    exact(values["activation_fraction_min_output"], expected_fraction,
          why + " activation min operand/result")
    exact(float(row["activated_fraction"]), expected_fraction,
          why + " old activation output handoff")

    nc = float(row["nc_input"])
    nccn = float(row["nccn_input"])
    dt = float(row["dtcld"])
    need(math.isfinite(nc) and math.isfinite(nccn) and math.isfinite(dt) and dt > 0.0,
         why + " finite NC/NCCN and positive dt")
    expected_preclamp = -nc + ((nccn + nc) * expected_fraction)
    expected_clamped = max(expected_preclamp, 0.0)
    expected_raw_rate = expected_clamped / dt
    expected_cap = max(nccn, 0.0) / dt
    expected_min = min(expected_raw_rate, expected_cap)
    sw_positive = bool(row["sw_positive"])
    expected_gated = expected_min if sw_positive else 0.0
    for name, expected in (
        ("ncact_preclamp_fma", expected_preclamp),
        ("ncact_clamped_numerator", expected_clamped),
        ("ncact_nccn_rate_cap", expected_cap),
        ("ncact_min_output", expected_min),
    ):
        need(math.isfinite(expected), why + " finite source result: " + name)
        exact(values[name], expected, why + " source order: " + name)
    exact(float(row["ncact_raw"]), expected_raw_rate, why + " legacy rate handoff")
    exact(float(row["ncact_rate_cap"]), expected_cap, why + " legacy cap handoff")
    exact(float(row["ncact_raw_minus_cap"]), expected_raw_rate - expected_cap,
          why + " legacy cap margin")
    exact(float(row["ncact"]), expected_gated, why + " legacy post-gate handoff")
    exact(float(row["ncact_cap_active"]), float(expected_raw_rate > expected_cap),
          why + " legacy strict-cap diagnostic")
    exact(float(row["ncact_cap_tie"]), float(expected_raw_rate == expected_cap),
          why + " legacy cap-tie diagnostic")
    expected_cap_flags = {
        "ncact_raw_lt_nccn_rate_cap": expected_raw_rate < expected_cap,
        "ncact_raw_eq_nccn_rate_cap": expected_raw_rate == expected_cap,
        "ncact_raw_gt_nccn_rate_cap": expected_raw_rate > expected_cap,
    }
    for name, expected in expected_cap_flags.items():
        need(operands[name] is expected, why + " cap comparator: " + name)
    need(sum(expected_flags.values()) == 1 and sum(expected_cap_flags.values()) == 1,
         why + " one-hot comparison diagnostics")
    return {
        "pow_operand_class": ("below_one" if pow_value < 1.0 else
                              "above_one" if pow_value > 1.0 else "equal_one"),
        "pow_math_ulp_distance": pow_distance,
        "ncact_rate_cap_class": ("raw_below_cap" if expected_raw_rate < expected_cap else
                                 "raw_above_cap" if expected_raw_rate > expected_cap else "tie"),
        "pre_gate_rate_equals_old_rate_when_sw_positive": sw_positive,
    }


def _near_jvp(actual: float, expected: float, why: str) -> None:
    need(math.isfinite(actual) and math.isfinite(expected), why + " finite JVP values")
    tolerance = 1.0e-8 * max(abs(actual), abs(expected), 1.0)
    need(abs(actual - expected) <= tolerance, why + " source JVP chain")


def _operand_event_rows(boundary: dict) -> list[tuple[str, dict]]:
    rows = [("baseline", boundary["baseline"])]
    for axis in ("th16", "qv16"):
        axis_data = boundary["axes"][axis]
        for bracket_name, bracket in axis_data["bisection"].items():
            rows.append((axis + "/" + bracket_name + "/lower", bracket["lower"]))
            rows.append((axis + "/" + bracket_name + "/upper", bracket["upper"]))
            rows.extend((axis + "/" + bracket_name + "/trace/" + str(index), item)
                        for index, item in enumerate(bracket["trace"]))
        for side, point in axis_data["interior_points"].items():
            rows.append((axis + "/" + side + "/branch", point["branch"]))
            for index, step in enumerate(point["one_sided_fd"]["step_scales"]):
                rows.append((axis + "/" + side + "/fd/" + str(index), step["endpoint"]))
    return rows


def _actual_operand_call_rows(boundary: dict) -> list[tuple[str, dict, str]]:
    """Return one row per captured C++ forward, excluding summary copies."""
    rows: list[tuple[str, dict, str]] = [("baseline", boundary["baseline"], "baseline")]
    for axis in ("th16", "qv16"):
        axis_data = boundary["axes"][axis]
        for bracket_name in module_order_brackets():
            trace = axis_data["bisection"][bracket_name]["trace"]
            rows.extend((axis + "/" + bracket_name + "/trace/" + str(index), item,
                         "bisection/" + axis + "/" + bracket_name + "/trace_" + str(index))
                        for index, item in enumerate(trace))
    for axis in ("th16", "qv16"):
        for side in ("fraction_eq_one", "fraction_below_one"):
            point = boundary["axes"][axis]["interior_points"][side]
            rows.append((axis + "/" + side + "/ad", point["branch"],
                         axis + "/" + side + "/interior_ad"))
    for axis in ("th16", "qv16"):
        for side in ("fraction_eq_one", "fraction_below_one"):
            point = boundary["axes"][axis]["interior_points"][side]
            for index, step in enumerate(point["one_sided_fd"]["step_scales"]):
                nominal_step = float(step["nominal_step"])
                rows.append((axis + "/" + side + "/fd/" + str(index), step["endpoint"],
                             axis + "/" + side + "/fd/" + format(nominal_step, ".8g")))
    return rows


def module_order_brackets() -> tuple[str, str]:
    return ("sw_percent_0p48", "activated_fraction_ge_1_observed_value")


def verify_call_event_identity(boundary: dict, parent_module: object) -> dict[str, object]:
    events = _actual_operand_call_rows(boundary)
    need(len(events) == 189, "operand-bearing event count matches 190 calls minus baseline-off")
    ordinals: list[int] = []
    event_ids: list[str] = []
    for path, row, expected_event_id in events:
        need(row.get("event_id") == expected_event_id,
             "call event ID identity: " + path)
        need("forward_call_ordinal" in row and type(row["forward_call_ordinal"]) is int,
             "forward call ordinal: " + path)
        ordinal = row["forward_call_ordinal"]
        need(ordinal >= 1, "captured event follows baseline-off call: " + path)
        ordinals.append(ordinal)
        event_ids.append(row["event_id"])
        if "/trace/" in path:
            expected_trace_index = int(path.rsplit("/", 1)[1])
            need(type(row.get("trace_index")) is int
                 and row["trace_index"] == expected_trace_index,
                 "local bisection trace index: " + path)
        else:
            need(row.get("trace_index") == -1, "non-bisection event trace-index sentinel: " + path)
    need(len(set(event_ids)) == len(event_ids), "unique event IDs for separate calls")
    need(ordinals == list(range(1, 190)),
         "captured call ordinals preserve baseline/bisection/AD/FD order")

    # Lower/upper bracket objects repeat already-recorded trace events. They
    # must reference the same event identity rather than imply extra forwards.
    for axis in ("th16", "qv16"):
        for side in ("fraction_eq_one", "fraction_below_one"):
            point = boundary["axes"][axis]["interior_points"][side]
            branch = point["branch"]
            need(point.get("event_id") == branch.get("event_id")
                 and point.get("forward_call_ordinal") == branch.get("forward_call_ordinal"),
                 "interior AD identity matches its branch row: " + axis + "/" + side)
            for index, step in enumerate(point["one_sided_fd"]["step_scales"]):
                endpoint = step["endpoint"]
                need(step.get("event_id") == endpoint.get("event_id")
                     and step.get("forward_call_ordinal") == endpoint.get("forward_call_ordinal"),
                     "FD identity matches its endpoint row: " + axis + "/" + side + "/" + str(index))
        for bracket_name in module_order_brackets():
            bracket = boundary["axes"][axis]["bisection"][bracket_name]
            trace = bracket["trace"]
            for side in ("lower", "upper"):
                summary_row = bracket[side]
                target_word = str(summary_row["input_word"]).zfill(16)
                trace_row = next(row for row in trace
                                 if str(row["input_word"]).zfill(16) == target_word)
                for key in ("event_id", "forward_call_ordinal", "trace_index"):
                    need(summary_row.get(key) == trace_row.get(key),
                         "bracket " + side + " references trace event: "
                         + axis + "/" + bracket_name + "/" + key)
                need(parent_module.same_recorded_tree(summary_row["operand_values"],
                                                       trace_row["operand_values"]),
                     "bracket summary operands equal trace event: " + axis + "/" + bracket_name)
    return {"operand_bearing_forward_events": len(events),
            "forward_call_ordinal_first": ordinals[0],
            "forward_call_ordinal_last": ordinals[-1],
            "unique_event_ids": len(set(event_ids))}


def verify_repeated_operand_values(boundary: dict, parent_module: object) -> dict[str, int]:
    """Bind live operand observations from separate calls at the same full input."""
    first_by_input: dict[tuple[str, str], tuple[str, dict]] = {}
    comparisons = 0
    for event_path, row, _ in _actual_operand_call_rows(boundary):
        # The remaining state, forcing and controls are fixed by the pinned
        # runner input; TH16 and QV16 are its only changed coordinates.
        input_key = (f64_word(float(row["th16"])), f64_word(float(row["qv16"])))
        if input_key in first_by_input:
            first_path, first_row = first_by_input[input_key]
            need(parent_module.same_recorded_tree(first_row["operand_values"],
                                                  row["operand_values"]),
                 "repeated-input operand values: " + first_path + " / " + event_path)
            comparisons += 1
        else:
            first_by_input[input_key] = (event_path, row)
    need(len(first_by_input) == 105 and comparisons == 84,
         "complete repeated-input operand observation pairs")
    return {"distinct_full_inputs": len(first_by_input),
            "repeated_operand_pairs_verified": comparisons}


def _signed_f64_ulp_distance(left: float, right: float) -> int:
    def ordered(value: float) -> int:
        raw = int(f64_word(value), 16)
        return (~raw & ((1 << 64) - 1)) if raw & (1 << 63) else raw | (1 << 63)
    need(math.isfinite(left) and math.isfinite(right), "finite operand gap values")
    return abs(ordered(left) - ordered(right))


def _verify_operand_output_gaps(parent: dict, child: dict, why: str) -> int:
    checked = 0
    for axis in ("th16", "qv16"):
        for bracket_name, bracket in child["axes"][axis]["bisection"].items():
            old_gaps = set(parent["axes"][axis]["bisection"][bracket_name]["output_gaps"])
            need(set(bracket["output_gaps"]) == old_gaps | set(OPERAND_NUMERIC_FIELDS),
                 why + " operand gap inventory: " + axis + "/" + bracket_name)
            lower, upper = bracket["lower"]["operand_values"], bracket["upper"]["operand_values"]
            for field in OPERAND_NUMERIC_FIELDS:
                low_value, high_value = float(lower[field]), float(upper[field])
                gap = bracket["output_gaps"][field]
                delta = high_value - low_value
                need(math.isfinite(delta), why + " finite operand gap: " + field)
                exact(float(gap["lower"]), low_value, why + " lower operand gap: " + field)
                exact(float(gap["upper"]), high_value, why + " upper operand gap: " + field)
                exact(float(gap["delta"]), delta, why + " operand gap delta: " + field)
                distance = _signed_f64_ulp_distance(low_value, high_value)
                need(int(gap["ulp_distance"]) == distance,
                     why + " operand gap ULP: " + field)
                status = ("unresolved_at_f64_output_resolution" if distance <= 1
                          else "resolved_above_one_output_ulp")
                need(gap["resolution_status"] == status,
                     why + " operand gap resolution: " + field)
                checked += 1
    return checked


def _verify_operand_interior(point: dict, axis: str, side: str,
                             parent_point: dict, why: str) -> dict[str, object]:
    parent_jvp = parent_point["jvp"]
    parent_vjp = parent_point["vjp_rows"]
    point_jvp = point["jvp"]
    point_vjp = point["vjp_rows"]
    need(set(point_jvp) == set(parent_jvp) | set(OPERAND_AD_JVP_FIELDS),
         why + " JVP operand inventory")
    need(set(point_vjp) == set(parent_vjp) | set(OPERAND_AD_VJP_FIELDS),
         why + " VJP operand inventory")
    event = point["branch"]["operand_values"]
    need(point["branch"]["sw_positive"] is True,
         why + " selected interior point is in the positive-supersaturation gate")
    for field in OPERAND_AD_JVP_FIELDS:
        tangent = float(point_jvp[field])
        need(math.isfinite(tangent), why + " finite operand JVP: " + field)
    exact(float(point_jvp["activation_fraction_one"]), 0.0,
          why + " constant one operand JVP")
    exact(float(point_jvp["activation_fraction_min_output"]),
          float(point_jvp["activated_fraction"]),
          why + " activation min JVP to legacy output")
    exact(float(point_jvp["ncact_min_output"]), float(point_jvp["ncact"]),
          why + " ncact min JVP to legacy output")
    _near_jvp(float(point_jvp["sw_ratio"]), float(point_jvp["sw_percent"]) / 0.48,
              why + " sw_ratio")
    _near_jvp(float(point_jvp["safe_pow_clamped_base_diagnostic"]),
              float(point_jvp["sw_ratio"]), why + " safe_pow base diagnostic")
    pow_base = float(event["safe_pow_clamped_base_diagnostic"])
    if pow_base > EPS:
        expected_pow_jvp = ACTK * math.pow(pow_base, ACTK - 1.0) * float(point_jvp["sw_ratio"])
        _near_jvp(float(point_jvp["activation_fraction_pow"]), expected_pow_jvp,
                  why + " safe_pow derivative")
    pow_value = float(event["activation_fraction_pow"])
    if pow_value < 1.0:
        exact(float(point_jvp["activation_fraction_min_output"]),
              float(point_jvp["activation_fraction_pow"]),
              why + " strict pow-below-one JVP path")
    elif pow_value > 1.0:
        exact(float(point_jvp["activation_fraction_min_output"]), 0.0,
              why + " strict pow-above-one JVP path")
    rate = float(point["branch"]["ncact_raw"])
    rate_cap = float(event["ncact_nccn_rate_cap"])
    if rate < rate_cap:
        exact(float(point_jvp["ncact_min_output"]), float(point_jvp["ncact_raw"]),
              why + " strict raw-below-cap JVP path")
    elif rate > rate_cap:
        exact(float(point_jvp["ncact_min_output"]), float(point_jvp["ncact_nccn_rate_cap"]),
              why + " strict raw-above-cap JVP path")
    preclamp = float(event["ncact_preclamp_fma"])
    if preclamp > 0.0:
        exact(float(point_jvp["ncact_clamped_numerator"]),
              float(point_jvp["ncact_preclamp_fma"]),
              why + " strict positive numerator-clamp JVP path")
    elif preclamp < 0.0:
        exact(float(point_jvp["ncact_clamped_numerator"]), 0.0,
              why + " strict negative numerator-clamp JVP path")
    _near_jvp(float(point_jvp["ncact_raw"]),
              float(point_jvp["ncact_clamped_numerator"]) / float(point["branch"]["dtcld"]),
              why + " rate division")
    # At pow==1, the observed AD tangent is retained; the minimum tie policy is
    # backend behavior and is not inferred from the equal-valued operands.

    axis_index = 15 if axis == "th16" else 54
    seed = 1.0 if axis == "th16" else float(point["input"]["qv16"])
    vjp_rows_checked = 0
    for field in OPERAND_AD_VJP_FIELDS:
        row = point_vjp[field]
        values = row["values"]
        words = row["raw_hex"]
        need(len(values) == len(words) == 468,
             why + " operand VJP vector shape: " + field)
        floats = [float(value) for value in values]
        need(all(math.isfinite(value) for value in floats),
             why + " finite operand VJP: " + field)
        for index, (value, raw_word) in enumerate(zip(floats, words)):
            need(f64_word(value) == str(raw_word).zfill(16),
                 why + " operand VJP raw word " + field + "/" + str(index))
        dot = floats[axis_index] * seed
        recorded_dot = float(row["direction_vjp_dot"])
        tangent = float(point_jvp[field])
        need(math.isfinite(dot) and math.isfinite(recorded_dot) and math.isfinite(tangent),
             why + " finite operand VJP/JVP dot: " + field)
        tolerance = 1.0e-8 * max(abs(dot), abs(recorded_dot), abs(tangent), 1.0)
        need(abs(recorded_dot - dot) <= tolerance,
             why + " operand VJP dot reconstruction: " + field)
        need(abs(recorded_dot - tangent) <= tolerance,
             why + " operand VJP/JVP transpose: " + field)
        exact(float(row["dot_minus_jvp"]), recorded_dot - tangent,
              why + " operand VJP/JVP residual: " + field)
        vjp_rows_checked += 1

    fd_checks = 0
    pow_fd_relative_errors: list[float] = []
    ncact_min_fd_relative_errors: list[float] = []
    pow_fd_accuracy_passes: list[str] = []
    ncact_min_fd_accuracy_passes: list[str] = []
    ncact_min_fd_unresolved_steps: list[str] = []
    for step in point["one_sided_fd"]["step_scales"]:
        outputs = step["outputs"]
        need(set(outputs) == set(parent_point["one_sided_fd"]["step_scales"][0]["outputs"])
             | set(OPERAND_NUMERIC_FIELDS), why + " FD operand output inventory")
        endpoint_values = step["endpoint"]["operand_values"]
        base_values = point["branch"]["operand_values"]
        comparison_fields = (
            "activation_fraction_pow_lt_one", "activation_fraction_pow_eq_one",
            "activation_fraction_pow_gt_one", "ncact_raw_lt_nccn_rate_cap",
            "ncact_raw_eq_nccn_rate_cap", "ncact_raw_gt_nccn_rate_cap",
        )
        same_operand_branch = all(base_values[name] == endpoint_values[name]
                                  for name in comparison_fields)
        need(step.get("same_operand_branch") is same_operand_branch,
             why + " same-operand-branch diagnostic")
        gap = float(step["parameter_gap"])
        need(math.isfinite(gap) and gap > 0.0, why + " positive finite FD parameter gap")
        for field in OPERAND_NUMERIC_FIELDS:
            output = outputs[field]
            base_value, endpoint_value = float(base_values[field]), float(endpoint_values[field])
            exact(float(output["base"]), base_value, why + " FD operand base: " + field)
            exact(float(output["endpoint"]), endpoint_value,
                  why + " FD operand endpoint: " + field)
            finite_difference = (endpoint_value - base_value) / gap
            tangent = float(point_jvp[field])
            need(math.isfinite(finite_difference) and math.isfinite(tangent),
                 why + " finite operand FD/JVP: " + field)
            exact(float(output["fd"]), finite_difference, why + " FD operand quotient: " + field)
            exact(float(output["ad_jvp"]), tangent, why + " FD operand JVP link: " + field)
            exact(float(output["fd_minus_jvp"]), finite_difference - tangent,
                  why + " FD operand residual: " + field)
            distance = _signed_f64_ulp_distance(endpoint_value, base_value)
            need(int(output["output_ulp_distance"]) == distance,
                 why + " FD operand ULP: " + field)
            status = ("unresolved_within_32_output_ulps" if distance <= 32
                      else "resolved_over_32_output_ulps")
            need(output["resolution_status"] == status,
                 why + " FD operand resolution: " + field)
            if field in ("activation_fraction_pow", "ncact_min_output"):
                if distance <= 32:
                    if field == "ncact_min_output":
                        ncact_min_fd_unresolved_steps.append(str(step["nominal_step"]))
                else:
                    relative_error = abs(finite_difference - tangent) / max(
                        abs(finite_difference), abs(tangent), math.ulp(base_value))
                    need(math.isfinite(relative_error),
                         why + " finite operand FD relative error: " + field)
                    error_collection = (pow_fd_relative_errors if field == "activation_fraction_pow"
                                        else ncact_min_fd_relative_errors)
                    error_collection.append(relative_error)
                    threshold = 1.0e-5 if field == "activation_fraction_pow" else 1.0e-6
                    if relative_error <= threshold:
                        (pow_fd_accuracy_passes if field == "activation_fraction_pow"
                         else ncact_min_fd_accuracy_passes).append(str(step["nominal_step"]))
            fd_checks += 1
    need(bool(pow_fd_accuracy_passes),
         why + " activation_fraction_pow has a resolved same-branch FD scale within 1e-5")
    if side == "fraction_below_one":
        need(event["ncact_raw_lt_nccn_rate_cap"] is True,
             why + " observed strict raw-below-cap branch")
        need(bool(ncact_min_fd_accuracy_passes),
             why + " raw-below-cap ncact_min_output has a resolved same-branch FD scale within 1e-6")
        cap_tie_summary = "not applicable: strict raw-below-cap operand ordering"
    else:
        need(event["ncact_raw_eq_nccn_rate_cap"] is True,
             why + " observed cap-side equality")
        exact(float(point_jvp["ncact_raw"]), 0.0, why + " cap-side raw-rate tangent zero")
        exact(float(point_jvp["ncact_nccn_rate_cap"]), 0.0,
              why + " cap-side NCCN-rate tangent zero")
        exact(float(point_jvp["ncact_min_output"]), 0.0,
              why + " cap-side min-output tangent zero")
        need(len(ncact_min_fd_unresolved_steps) == len(point["one_sided_fd"]["step_scales"]),
             why + " cap-side ncact minimum FD remains output-unresolved")
        cap_tie_summary = (
            "tie observed but derivative policy not inferred; both rate/cap operand tangents are zero")
    return {
        "operand_vjp_rows": vjp_rows_checked,
        "operand_fd_checks": fd_checks,
        "activation_fraction_pow_fd_relative_errors": pow_fd_relative_errors,
        "activation_fraction_pow_fd_accuracy_passes_at_1e-5": pow_fd_accuracy_passes,
        "ncact_min_output_fd_relative_errors": ncact_min_fd_relative_errors,
        "ncact_min_output_fd_accuracy_passes_at_1e-6": ncact_min_fd_accuracy_passes,
        "ncact_min_output_unresolved_cap_side_steps": ncact_min_fd_unresolved_steps,
        "ncact_cap_tie_subgradient": cap_tie_summary,
    }


def verify_operand_boundary(parent_boundary: dict, child_boundary: dict,
                            parent_module: object) -> dict[str, object]:
    require_finite_tree(child_boundary, "activation operand boundary payload")
    need(child_boundary["schema"] == OPERAND_BOUNDARY_SCHEMA,
         "activation operand boundary schema")
    compare_parent_projection(parent_boundary, child_boundary, parent_module)
    operand_rows = _operand_event_rows(child_boundary)
    for event_id, row in operand_rows:
        verify_operand_observation(row, "operand observation object " + event_id)
    event_identity = verify_call_event_identity(child_boundary, parent_module)
    repeated_operands = verify_repeated_operand_values(child_boundary, parent_module)
    classifications: dict[str, int] = {
        "pow_below_one": 0, "pow_equal_one": 0, "pow_above_one": 0,
        "ncact_raw_below_cap": 0, "ncact_tie": 0, "ncact_raw_above_cap": 0,
    }
    unique_events = _actual_operand_call_rows(child_boundary)
    for event_id, row, _ in unique_events:
        classification = verify_operand_observation(row, "operand observation " + event_id)
        classifications["pow_" + classification["pow_operand_class"]] += 1
        classifications["ncact_" + classification["ncact_rate_cap_class"]] += 1

    gap_count = _verify_operand_output_gaps(
        parent_boundary, child_boundary, "activation boundary operand gaps")
    interior_counts: dict[str, dict[str, object]] = {}
    for axis in ("th16", "qv16"):
        interior_counts[axis] = {}
        parent_axis = parent_boundary["axes"][axis]["interior_points"]
        child_axis = child_boundary["axes"][axis]["interior_points"]
        for side in ("fraction_eq_one", "fraction_below_one"):
            interior_counts[axis][side] = _verify_operand_interior(
                child_axis[side], axis, side, parent_axis[side],
                "activation operand AD/FD " + axis + "/" + side)
    return {
        "operand_observation_objects_verified": len(operand_rows),
        **event_identity,
        **repeated_operands,
        "operand_output_gaps_verified": gap_count,
        "operand_comparison_classifications": classifications,
        "operand_interior_ad_fd_checks": interior_counts,
        "parent_projection_raw_equal": True,
    }


@lru_cache(maxsize=1)
def verified_parent() -> tuple[object, dict]:
    """Pin, import and fully run the parent packet before loading child data."""
    manifest_raw = (PARENT / "manifest.json").read_bytes()
    need(sha(manifest_raw) == PARENT_MANIFEST_SHA256, "pinned #575 parent manifest SHA")
    manifest = json.loads(manifest_raw)
    need(manifest["schema"] == "kdm6.native_activation_upper_boundary_cpp_ad_packet.v1",
         "#575 parent manifest schema")
    boundary_raw = (PARENT / "raw/activation_boundary.json").read_bytes()
    need(sha(boundary_raw) == PARENT_BOUNDARY_SHA256, "pinned #575 boundary-result SHA")
    replay_source = PARENT / "replay.py"
    replay_raw = replay_source.read_bytes()
    need(sha(replay_raw) == PARENT_REPLAY_SHA256, "pinned #575 parent replay source SHA")

    spec = importlib.util.spec_from_file_location("activation_boundary_parent_replay", replay_source)
    need(spec is not None and spec.loader is not None, "#575 parent replay loader")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    summary = module.replay()
    need(summary["schema"] == "kdm6.native_activation_upper_boundary_cpp_ad_replay.v1",
         "verified #575 parent replay schema")
    need(summary["activation_bisection_trace_rows"] == 168
         and summary["activation_interior_ad_calls"] == 4
         and summary["activation_one_sided_fd_calls"] == 16
         and summary["activation_call_counts"]["total_full_call_forwards"] == 190,
         "verified #575 parent event/call contract")
    need(summary["scientific_status"] == "INCONCLUSIVE"
         and summary["physical_unit_status"] == "INCONCLUSIVE",
         "verified #575 parent status remains inconclusive")
    return module, summary


def replay(*, operand_override: tuple[bytes, str] | None = None,
           default_cpp_override: tuple[bytes, str] | None = None) -> dict:
    """Verify parent first, then verify the child operand delta and its projection."""
    parent_module, parent_summary = verified_parent()
    provenance_path = HERE / "provenance.py"
    provenance_spec = importlib.util.spec_from_file_location("activation_operands_provenance", provenance_path)
    need(provenance_spec is not None and provenance_spec.loader is not None,
         "activation operand provenance loader")
    provenance_module = importlib.util.module_from_spec(provenance_spec)
    provenance_spec.loader.exec_module(provenance_module)
    provenance_summary = provenance_module.verify_provenance()

    default_raw = (HERE / "raw/cpp_result.json").read_bytes()
    if default_cpp_override is not None:
        default_raw, expected_sha = default_cpp_override
        need(sha(default_raw) == expected_sha, "default C++ result override SHA")
    child_cpp_result = json.loads(default_raw)
    parent_cpp_result = json.loads((THERMAL_PARENT / "raw/cpp_result.json").read_text())
    default_projection = verify_default_cpp_projection(
        parent_cpp_result, child_cpp_result, parent_module)

    if operand_override is None:
        raw = OPERAND_PAYLOAD.read_bytes()
    else:
        raw, expected_sha = operand_override
        need(sha(raw) == expected_sha, "activation operand override SHA")
    child_boundary = json.loads(raw, parse_constant=reject_json_constant)
    require_finite_tree(child_boundary, "activation operand boundary JSON")
    parent_boundary = json.loads((PARENT / "raw/activation_boundary.json").read_text())
    operand_summary = verify_operand_boundary(parent_boundary, child_boundary, parent_module)
    return {
        "schema": "kdm6.native_activation_operands_cpp_ad_replay.v1",
        "parent_schema": parent_summary["schema"],
        "parent_replay_sha256": PARENT_REPLAY_SHA256,
        "scientific_status": parent_summary["scientific_status"],
        "physical_unit_status": parent_summary["physical_unit_status"],
        "provenance": provenance_summary,
        "default_cpp_projection": default_projection,
        **operand_summary,
    }


def main() -> None:
    result = replay()
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
