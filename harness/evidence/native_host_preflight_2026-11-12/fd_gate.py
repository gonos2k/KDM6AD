#!/usr/bin/env python3
"""Prospective output-wise f64 finite-difference gate; no model execution.

The caller attests the plan was registered before data collection. This
program checks plan integrity, not the time or truth of that attestation.
"""

import gzip
import hashlib
import json
import math
import re
import struct
from pathlib import Path

FIELDS = ("th", "qv", "qc", "qr", "qi", "qs", "qg", "nccn", "nc", "ni", "nr", "bg")
SCALES = (1.0, 1e-3, 1e-3, 1e-3, 1e-3, 1e-3, 1e-3, 1e8, 1e8, 1e6, 1e6, 1e-6)
SCHEMA = "kdm6.output_fd_gate_input.v1"
PACKET_GZ_SHA = "4d6a935c9d83d987a8a2149d58699b2812af565785d20c599cf9f49f05846b8a"
PACKET = Path(__file__).resolve().with_name("plan.json.gz")
INPUT_FIELDS = FIELDS + ("rho", "pii", "p", "delz")


def need(ok, why):
    if not ok:
        raise ValueError(why)


def val(word):
    need(
        isinstance(word, str) and re.fullmatch(r"[0-9a-f]{16}", word) is not None,
        "invalid raw f64 word",
    )
    x = struct.unpack(">d", bytes.fromhex(word))[0]
    need(math.isfinite(x), "nonfinite f64 word")
    return x


def word(x):
    need(math.isfinite(x), "nonfinite derived value")
    return struct.pack(">d", x).hex()


def words(a, count, label):
    need(isinstance(a, list) and len(a) == count, label + " length")
    return [val(x) for x in a]


def plan_sha(plan):
    raw = json.dumps(
        plan, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def canonical_plan(packet_raw, expected_digest, center_name, direction, output_index):
    need(
        expected_digest == PACKET_GZ_SHA
        and hashlib.sha256(packet_raw).hexdigest() == PACKET_GZ_SHA,
        "canonical packet plan SHA",
    )
    packet = json.loads(gzip.decompress(packet_raw))
    need(
        packet["schema"] == "kdm6.native_host_capture_preflight.v1"
        and packet["status"] == "SPEC_ONLY"
        and packet["execution_receipt"] is None
        and packet["input_field_order"] == list(INPUT_FIELDS),
        "canonical packet schema",
    )
    need(
        center_name in ("baseline", "lower", "upper")
        and direction in packet["direction_seeds"],
        "canonical selection",
    )
    matches = [
        x
        for x in packet["inputs"]
        if x["center"] == center_name and x["direction"] == "center"
    ]
    need(len(matches) == 1, "canonical center")
    center = matches[0]["words"]
    words(center, 624, "canonical center")
    seed_data = packet["direction_seeds"][direction]
    need(
        seed_data["field"] == direction and seed_data["level_zero_bottom_first"] == 15,
        "canonical seed",
    )
    nominal = [word(0.0)] * 624
    nominal[INPUT_FIELDS.index(direction) * 39 + 15] = seed_data["scale_f64_word"]
    words(nominal, 624, "canonical direction")
    entries = [
        x
        for x in packet["inputs"]
        if x["center"] == center_name and x["direction"] == direction
    ]
    hs = sorted({x["h"] for x in entries})
    need(hs, "canonical direction has no steps")
    steps = []
    for h in hs:
        group = [x for x in entries if x["h"] == h]
        multiples = {x["multiple"]: x for x in group}
        wanted = {1, 2} if direction == "nc" else {-1, 1}
        need(
            len(group) == 2 and set(multiples) == wanted, "canonical endpoint inventory"
        )
        step = {
            "id": format(h, ".0e"),
            "h_word": word(h),
            "stencil": "forward" if direction == "nc" else "central",
            "lower_input_words": center
            if direction == "nc"
            else multiples[-1]["words"],
            "upper_input_words": multiples[1]["words"],
        }
        if direction == "nc":
            step["plus2_input_words"] = multiples[2]["words"]
        steps.append(step)
    return {
        "schema": "kdm6.output_fd_gate_plan.v1",
        "attestation": "caller_attests_registered_before_capture",
        "protocol_id": f"native-host-preflight:{center_name}:{direction}",
        "output_index": output_index,
        "center_input_words": center,
        "nominal_direction_words": nominal,
        "steps": steps,
    }


def observation(o, idx):
    need(isinstance(o, dict), "observation object")
    values = words(o["output_words"], 468, "observation output")
    words(o["reference_output_words"], 468, "observation reference")
    need(o["output_words"] == o["reference_output_words"], "output parity mismatch")
    value = values[idx]
    masks = o["masks"]
    schedule = o["schedule"]
    need(
        isinstance(masks, dict)
        and len(masks) > 0
        and all(isinstance(k, str) and k and type(v) is bool for k, v in masks.items()),
        "captured masks",
    )
    need(
        isinstance(schedule, dict)
        and len(schedule) > 0
        and all(
            isinstance(k, str)
            and k
            and isinstance(v, str)
            and re.fullmatch(r"[0-9a-f]{16}", v)
            and math.isfinite(val(v))
            for k, v in schedule.items()
        ),
        "captured schedule",
    )
    return value


def evaluate(data, *, allow_synthetic=False):
    need(
        data["schema"] == SCHEMA
        and data["intent"] == "prospective_pre_capture_plan"
        and data["data_origin"] == "new_prospective_acquisition",
        "prospective input required",
    )
    plan = data["plan"]
    need(data["plan_sha256"] == plan_sha(plan), "plan SHA")
    if not allow_synthetic:
        expected = canonical_plan(
            PACKET.read_bytes(),
            data["packet_plan_sha256"],
            data["center_name"],
            data["direction"],
            plan["output_index"],
        )
        need(plan == expected, "plan does not match pinned canonical packet")
    need(
        plan["schema"] == "kdm6.output_fd_gate_plan.v1"
        and plan["attestation"] == "caller_attests_registered_before_capture",
        "pre-capture plan attestation",
    )
    need(
        isinstance(plan["protocol_id"], str)
        and plan["protocol_id"]
        and not any(
            x in plan["protocol_id"].lower() for x in ("#586", "#587", "retrospective")
        ),
        "prospective protocol id",
    )
    idx = plan["output_index"]
    need(type(idx) is int and 0 <= idx < 468, "output index")
    center_input = plan["center_input_words"]
    center = words(center_input, 624, "center input")
    nominal = words(plan["nominal_direction_words"], 624, "nominal direction")
    need(any(x != 0 for x in nominal), "zero nominal direction")
    ps = plan["steps"]
    samples = data["samples"]
    need(
        isinstance(ps, list)
        and len(ps) >= 1
        and isinstance(samples, list)
        and len(samples) == len(ps),
        "at least one step required",
    )
    need(
        len({p["id"] for p in ps}) == len(ps)
        and len({s["id"] for s in samples}) == len(samples)
        and {p["id"] for p in ps} == {s["id"] for s in samples},
        "step identity",
    )
    need(len({val(p["h_word"]) for p in ps}) == len(ps), "distinct h required")
    need(len({p["stencil"] for p in ps}) == 1, "same stencil required")
    center_obs = observation(data["center"], idx)
    results = []
    for p in ps:
        sample = next(x for x in samples if x["id"] == p["id"])
        h = val(p["h_word"])
        need(h > 0, "positive h")
        stencil = p["stencil"]
        need(stencil in ("central", "forward"), "stencil")
        lower = words(p["lower_input_words"], 624, "lower input")
        upper = words(p["upper_input_words"], 624, "upper input")
        if stencil == "forward":
            need(p["lower_input_words"] == center_input, "forward base must be center")
        for i, n in enumerate(nominal):
            if n == 0:
                need(
                    p["lower_input_words"][i] == center_input[i]
                    and p["upper_input_words"][i] == center_input[i],
                    "undeclared input changed",
                )
                continue
            expected_lower = center[i] - h * n if stencil == "central" else center[i]
            expected_upper = center[i] + h * n
            need(
                p["lower_input_words"][i] == word(expected_lower)
                and p["upper_input_words"][i] == word(expected_upper),
                "planned perturbation does not match nominal direction",
            )
        # No undeclared coordinate may vary; a declared component that vanishes
        # or changes sign is a diagnostic, not a silent zero-seed comparison.
        den = 2 * h if stencil == "central" else h
        need(math.isfinite(den) and den > 0, "denominator")
        actual = [(b - a) / den for a, b in zip(lower, upper)]
        need(all(math.isfinite(x) for x in actual), "nonfinite effective direction")
        need(
            all(n != 0 or a == 0 for n, a in zip(nominal, actual)),
            "undeclared direction component",
        )
        degenerate = any(
            n != 0 and (a == 0 or (n > 0) != (a > 0)) for n, a in zip(nominal, actual)
        )
        if nominal[8 * 39 + 15] != 0 and center[8 * 39 + 15] == 0:
            need(
                lower[8 * 39 + 15] >= 0 and upper[8 * 39 + 15] >= 0,
                "negative NC from zero",
            )
        if stencil == "central":
            need(
                sample["jvp_evaluation_input_words"] == center_input,
                "central JVP evaluation point",
            )
        else:
            need(
                sample["jvp_evaluation_input_words"] == p["lower_input_words"],
                "forward JVP evaluation point",
            )
        words(sample["jvp_direction_words"], 624, "JVP direction")
        need(
            all(word(a) == s for a, s in zip(actual, sample["jvp_direction_words"])),
            "JVP direction not represented endpoint direction",
        )
        words(sample["jvp_forward_output_words"], 468, "graph forward")
        need(
            sample["jvp_forward_output_words"] == data["center"]["output_words"]
            and sample["jvp_rc"] == 0,
            "graph/value forward parity",
        )
        jvp = words(sample["jvp_output_words"], 468, "JVP output")[idx]
        lo = observation(sample["lower"], idx)
        hi = observation(sample["upper"], idx)
        if stencil == "forward":
            need(
                sample["lower"]["output_words"] == data["center"]["output_words"],
                "forward center output",
            )
        for obs in (sample["lower"], sample["upper"]):
            need(
                set(obs["masks"]) == set(data["center"]["masks"])
                and set(obs["schedule"]) == set(data["center"]["schedule"]),
                "capture key inventory",
            )
        crossing = any(
            o["masks"] != data["center"]["masks"]
            or o["schedule"] != data["center"]["schedule"]
            for o in (sample["lower"], sample["upper"])
        )
        dy = hi - lo
        fd = dy / den
        err = fd - jvp
        local_ulp = max(math.ulp(center_obs), math.ulp(lo), math.ulp(hi))
        signal_ulps = abs(dy) / local_ulp
        residual_ulps = abs(dy - jvp * den) / local_ulp
        need(
            all(math.isfinite(x) for x in (dy, fd, err, signal_ulps, residual_ulps)),
            "nonfinite derived metric",
        )
        relative = abs(err) / max(abs(fd), abs(jvp)) if max(abs(fd), abs(jvp)) else None
        if crossing:
            tag = "BRANCH_CROSSING"
        elif degenerate:
            tag = "DIRECTION_DEGENERATE"
        elif jvp == 0 or signal_ulps < 16:
            tag = "UNRESOLVED"
        elif relative <= 1e-6:
            tag = "STEP_NUMERIC_CONSISTENT"
        elif residual_ulps <= 4:
            tag = "ROUNDING_LIMITED"
        else:
            tag = "NUMERIC_MISMATCH"
        record = {
            "id": p["id"],
            "h_word": p["h_word"],
            "stencil": stencil,
            "output_lower_word": sample["lower"]["output_words"][idx],
            "output_upper_word": sample["upper"]["output_words"][idx],
            "jvp_output_word": sample["jvp_output_words"][idx],
            "effective_direction_words": sample["jvp_direction_words"],
            "delta_y": dy,
            "denominator": den,
            "fd": fd,
            "jvp": jvp,
            "fd_minus_jvp": err,
            "absolute_error": abs(err),
            "field_scale": SCALES[idx // 39],
            "field_scaled_absolute_error": abs(err) / SCALES[idx // 39],
            "relative_residual": relative,
            "output_residual_ulps": residual_ulps,
            "signal_ulps": signal_ulps,
            "zero_jvp_resolved_signal": jvp == 0.0 and signal_ulps >= 16,
            "tag": tag,
        }
        if "plus2_input_words" in p:
            need(stencil == "forward" and "plus2" in sample, "plus2 only for forward")
            plus2 = words(p["plus2_input_words"], 624, "plus2 input")
            v2 = observation(sample["plus2"], idx)
            need(
                all(
                    p["plus2_input_words"][i]
                    == (center_input[i] if n == 0 else word(center[i] + 2 * h * n))
                    for i, n in enumerate(nominal)
                ),
                "planned plus2 direction",
            )
            if nominal[8 * 39 + 15] != 0 and center[8 * 39 + 15] == 0:
                need(plus2[8 * 39 + 15] >= 0, "negative NC plus2")
            need(
                set(sample["plus2"]["masks"]) == set(data["center"]["masks"])
                and set(sample["plus2"]["schedule"]) == set(data["center"]["schedule"]),
                "plus2 capture key inventory",
            )
            changed = (
                sample["plus2"]["masks"] != data["center"]["masks"]
                or sample["plus2"]["schedule"] != data["center"]["schedule"]
            )
            record["forward_segments"] = {
                "center_to_plus_delta": hi - center_obs,
                "plus_to_plus2_delta": v2 - hi,
                "plus_equals_plus2": sample["upper"]["output_words"][idx]
                == sample["plus2"]["output_words"][idx],
                "plus2_crossing": changed,
            }
            if changed:
                record["tag"] = "BRANCH_CROSSING"
        results.append(record)
    tags = [x["tag"] for x in results]
    if "BRANCH_CROSSING" in tags:
        overall = "BRANCH_CROSSING"
    elif "DIRECTION_DEGENERATE" in tags:
        overall = "DIRECTION_DEGENERATE"
    elif "NUMERIC_MISMATCH" in tags:
        overall = "NUMERIC_MISMATCH"
    elif "UNRESOLVED" in tags:
        overall = "UNRESOLVED"
    elif "ROUNDING_LIMITED" in tags:
        overall = "ROUNDING_LIMITED"
    elif len(results) < 2:
        overall = "UNRESOLVED"
    else:
        overall = "LOCAL_NUMERIC_CONSISTENT"
    return {
        "schema": "kdm6.output_fd_gate_result.v1",
        "plan_sha256": data["plan_sha256"],
        "output_index": idx,
        "field": FIELDS[idx // 39],
        "native_level": idx % 39 + 1,
        "tag": overall,
        "steps": results,
        "scope": "CAPTURED_BRANCH_ONLY: local numerical consistency only; no full Jacobian, host forcing, physical budget or RTTOV certification",
        "registration": "caller attests pre-capture registration; evaluator cannot independently establish chronology",
        "provenance_status": "SYNTHETIC_ONLY"
        if allow_synthetic
        else "UNVERIFIED_EXECUTION_RECEIPTS",
        "gate_eligibility": "NOT_ELIGIBLE: numeric classification is schema-only until independent execution receipts are verified",
        "scientific_status": "INCONCLUSIVE",
        "physical_unit_status": "INCONCLUSIVE",
    }


def main():
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path)
    args = p.parse_args()
    print(
        json.dumps(
            evaluate(json.loads(args.input.read_bytes())),
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
