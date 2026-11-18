"""Read-only replay of stored synthetic call assets; no model or DSO execution."""

import hashlib
import json
import math
import re
import struct
from pathlib import Path

import fixture33 as fixtures
import witness33
from fixture_plan import CENTER, FIELDS, K, raw_words
from selector_manifest_spec_v1 import SELECTORS


def need(ok, message):
    if not ok:
        raise ValueError(message)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def near(a, b, rtol=1e-5, atol=1e-8):
    return abs(a - b) <= atol + rtol * max(abs(a), abs(b))


def relative_residual(a, b):
    if a is None or b is None:
        return None
    scale = max(abs(a), abs(b))
    return abs(a / scale - b / scale) if scale else 0.0


def signed_residual(a, b):
    if a is None or b is None:
        return None, "UNAVAILABLE"
    difference = a - b
    return (difference, "FINITE") if math.isfinite(difference) else (None, "OVERFLOW")


def exact_fields(actual, expected):
    if type(actual) is not dict or actual.keys() != expected.keys():
        return False
    for key, value in expected.items():
        observed = actual[key]
        if type(observed) is not type(value):
            return False
        if type(value) is float:
            if struct.pack("=d", observed) != struct.pack("=d", value):
                return False
        elif observed != value:
            return False
    return True


def read_assets(directory):
    directory = Path(directory)
    schedule = fixtures.plan()
    journal = [
        json.loads(line)
        for line in (directory / "calls.jsonl").read_text().splitlines()
    ]
    need(len(journal) == 66, "journal length")
    assets = []
    for index, slot in enumerate(schedule):
        expected = {
            key: slot[key]
            for key in ("seq", "fixture", "mode", "direction", "offset", "input_sha256")
        }
        started, done = journal[index * 2 : index * 2 + 2]
        need(exact_fields(started, {**expected, "state": "STARTED"}), "started slot")
        raw = (directory / f"call_{index + 1:02}.json").read_bytes()
        need(
            exact_fields(
                done,
                {
                    **expected,
                    "state": "COMPLETED",
                    "asset_sha256": hashlib.sha256(raw).hexdigest(),
                    "bytes": len(raw),
                },
            ),
            "completed asset hash",
        )
        data = json.loads(raw)
        need(
            type(data) is dict
            and set(data) == {"schema", "slot", "input_words", "result"}
            and type(data["schema"]) is str
            and data["schema"] == "kdm6.synthetic33.call_asset.v3"
            and exact_fields(data["slot"], expected),
            "asset identity",
        )
        need(
            type(data["input_words"]) is str
            and re.fullmatch(r"[0-9a-f]{9984}", data["input_words"]) is not None,
            "input word encoding",
        )
        words = bytes.fromhex(data["input_words"])
        need(
            len(words) == 624 * 8
            and hashlib.sha256(words).hexdigest() == slot["input_sha256"],
            "input words",
        )
        values = struct.unpack("<624d", words)
        need(all(math.isfinite(x) for x in values), "input finite")
        data["values"] = values
        assets.append(data)
    need(
        {p.name for p in directory.glob("call_*.json")}
        == {f"call_{i:02}.json" for i in range(1, 34)},
        "asset inventory",
    )
    return assets


def replay(directory):
    assets = read_assets(directory)
    witness33.checked_results(assets)
    results = []
    for case_index, case in enumerate(fixtures.CASES):
        group = assets[11 * case_index : 11 * (case_index + 1)]
        off, on, graph = (x["result"] for x in group[:3])
        need(
            (off["out"], off["rain"])
            == (on["out"], on["rain"])
            == (graph["out"], graph["rain"]),
            "forward parity",
        )
        for result in (off, on, graph):
            need(
                len(bytes.fromhex(result["out"])) == 468 * 8, "forward output inventory"
            )
            need(
                type(result["rain"]) is int and 0 <= result["rain"] < (1 << 64),
                "rain word",
            )
        need(
            group[0]["input_words"]
            == group[1]["input_words"]
            == group[2]["input_words"],
            "center input parity",
        )
        for selector in SELECTORS:
            center, gd = on["selectors"][selector], graph["selectors"][selector]
            center_available = center["status"] == "SPEC_ONLY"
            graph_available = gd["status"] == "SPEC_ONLY"
            if center_available and graph_available:
                need(center["primal"] == gd["primal"], "selector primal parity")
            gradient = None
            if graph_available:
                words = gd["grad_words"]
                need(
                    len(words) == 624
                    and all(isinstance(x, str) and len(x) == 16 for x in words),
                    "gradient inventory",
                )
                gradient = [struct.unpack("=d", bytes.fromhex(x))[0] for x in words]
                need(all(math.isfinite(x) for x in gradient), "gradient finite")
            for direction_index, direction in enumerate(fixtures.DIRECTIONS):
                seed = fixtures.direction(direction)
                jvp = dot = None
                connectivity = "UNAVAILABLE"
                duality = "UNAVAILABLE"
                if graph_available:
                    dot = sum(g * v for g, v in zip(gradient, seed))
                    jvp, stored_dot = (
                        gd["jvps"][direction_index],
                        gd["dots"][direction_index],
                    )
                    need(
                        finite(dot) and finite(jvp) and finite(stored_dot),
                        "gradient result finite",
                    )
                    need(
                        near(dot, stored_dot, 1e-12, 1e-14),
                        "stored dot differs from gradient",
                    )
                    abi_status = gd["abi_jvp_statuses"][direction_index]
                    need(abi_status in (0, 1, 2), "ABI status")
                    mask = gd["mask"]
                    need(type(mask) is int and 0 <= mask < (1 << 16), "gradient mask")
                    bit = 1 << FIELDS.index(direction)
                    connectivity = (
                        "NO_GRAPH_PATH"
                        if abi_status == 1
                        else (
                            "CONNECTED"
                            if abi_status == 0 and (mask & bit)
                            else "UNCONNECTED"
                        )
                    )
                    need(
                        gd["direction_connectivity"][direction_index] == connectivity,
                        "connectivity",
                    )
                    duality = (
                        "UNCONNECTED"
                        if connectivity != "CONNECTED"
                        or gd["graph_flag"] != 1
                        or gd["vjp_status"] != 0
                        else ("CONSISTENT" if near(jvp, dot) else "MISMATCH")
                    )
                rows = []
                for step_index, h in enumerate(fixtures.H):
                    base_index = 3 + direction_index * 4 + step_index * 2
                    lower, upper = group[base_index : base_index + 2]
                    idx = FIELDS.index(direction) * K + CENTER
                    center_values = group[1]["values"]
                    lo, hi = lower["values"], upper["values"]
                    need(
                        all(
                            raw_words([lo[i]])
                            == raw_words([center_values[i]])
                            == raw_words([hi[i]])
                            for i in range(624)
                            if i != idx
                        ),
                        "unexpected perturbation",
                    )
                    gap = hi[idx] - lo[idx]
                    need(math.isfinite(gap) and gap > 0, "represented gap")
                    low_entry, high_entry = (
                        lower["result"]["selectors"][selector],
                        upper["result"]["selectors"][selector],
                    )
                    endpoint_available = (
                        low_entry["status"] == high_entry["status"] == "SPEC_ONLY"
                    )
                    fd = ulp_signal = None
                    resolution = "UNAVAILABLE"
                    if endpoint_available:
                        low = struct.unpack(
                            "=d", struct.pack("=Q", low_entry["primal"])
                        )[0]
                        high = struct.unpack(
                            "=d", struct.pack("=Q", high_entry["primal"])
                        )[0]
                        fd = (high - low) / gap * seed[idx]
                        need(math.isfinite(fd), "FD finite")
                        ulp_signal = abs(high - low) / max(
                            math.ulp(low), math.ulp(high)
                        )
                        resolution = (
                            "RESOLVED"
                            if ulp_signal >= 16 and abs(fd) >= 1e-8
                            else "UNRESOLVED"
                        )
                    conditions = [
                        r.get("conditions")
                        for r in (on, lower["result"], upper["result"])
                    ]
                    branch = (
                        "CROSS"
                        if all(conditions)
                        and not (conditions[0] == conditions[1] == conditions[2])
                        else (
                            "INCOMPLETE"
                            if any(not c for c in conditions)
                            or any(
                                r.get("unverified_absence", False)
                                for r in (on, lower["result"], upper["result"])
                            )
                            else "STABLE"
                        )
                    )
                    fd_ad_agreement = (
                        "UNAVAILABLE"
                        if not center_available
                        or resolution != "RESOLVED"
                        or jvp is None
                        or connectivity != "CONNECTED"
                        or gd["graph_flag"] != 1
                        else ("CONSISTENT" if near(fd, jvp) else "MISMATCH")
                    )
                    if duality == "MISMATCH":
                        fd_ad_exclusion_reason = "AD_DUALITY_MISMATCH"
                    elif branch == "CROSS":
                        fd_ad_exclusion_reason = "BRANCH_CROSSING"
                    elif branch == "INCOMPLETE":
                        fd_ad_exclusion_reason = "INCOMPLETE_CONDITIONS"
                    elif not center_available or not endpoint_available or jvp is None:
                        fd_ad_exclusion_reason = "UNAVAILABLE_VALUE"
                    elif connectivity != "CONNECTED" or gd["graph_flag"] != 1:
                        fd_ad_exclusion_reason = "UNCONNECTED_AD"
                    elif resolution != "RESOLVED":
                        fd_ad_exclusion_reason = "UNRESOLVED_FD"
                    else:
                        fd_ad_exclusion_reason = None
                    fd_difference, fd_difference_status = signed_residual(fd, jvp)
                    ad_difference, ad_difference_status = signed_residual(jvp, dot)
                    if duality == "MISMATCH":
                        status = "NUMERIC_MISMATCH"
                    elif branch == "CROSS":
                        status = "BRANCH_CROSSING"
                    elif branch == "INCOMPLETE":
                        status = "UNRESOLVED"
                    elif fd_ad_agreement == "MISMATCH":
                        # A resolved stable FD can disagree with a zero AD signal.
                        status = "NUMERIC_MISMATCH"
                    elif (
                        duality in ("UNCONNECTED", "UNAVAILABLE")
                        or not center_available
                        or resolution in ("UNRESOLVED", "UNAVAILABLE")
                        or jvp is None
                        or abs(jvp) < 1e-8
                    ):
                        status = "UNRESOLVED"
                    else:
                        status = (
                            "LOCAL_NUMERIC_CONSISTENT"
                            if near(fd, jvp)
                            else "NUMERIC_MISMATCH"
                        )
                    rows.append(
                        {
                            "h": h,
                            "represented_gap": gap,
                            "fd": fd,
                            "fd_minus_jvp": fd_difference,
                            "fd_minus_jvp_status": fd_difference_status,
                            "fd_ad_relative_residual": relative_residual(fd, jvp),
                            "output_ulp_signal": ulp_signal,
                            "resolution": resolution,
                            "ad_duality": duality,
                            "ad_duality_signed_residual": ad_difference,
                            "ad_duality_signed_residual_status": ad_difference_status,
                            "ad_duality_relative_residual": relative_residual(jvp, dot),
                            "fd_ad_agreement": fd_ad_agreement,
                            "fd_ad_eligible": fd_ad_exclusion_reason is None,
                            "fd_ad_exclusion_reason": fd_ad_exclusion_reason,
                            "recorded_branch_schedule": branch,
                            "status": status,
                        }
                    )
                stability = (
                    "STABLE"
                    if all(
                        row["recorded_branch_schedule"] == "STABLE"
                        and row["resolution"] == "RESOLVED"
                        for row in rows
                    )
                    and near(rows[0]["fd"], rows[1]["fd"])
                    else "UNSTABLE_OR_UNRESOLVED"
                )
                if any(row["ad_duality"] == "MISMATCH" for row in rows):
                    pair_status = "NUMERIC_MISMATCH"
                elif any(row["recorded_branch_schedule"] == "CROSS" for row in rows):
                    pair_status = "BRANCH_CROSSING"
                elif any(
                    row["recorded_branch_schedule"] == "INCOMPLETE" for row in rows
                ):
                    pair_status = "UNRESOLVED"
                elif any(row["status"] == "NUMERIC_MISMATCH" for row in rows):
                    pair_status = "NUMERIC_MISMATCH"
                elif all(row["status"] == "LOCAL_NUMERIC_CONSISTENT" for row in rows):
                    pair_status = (
                        "LOCAL_NUMERIC_CONSISTENT"
                        if stability == "STABLE"
                        else "NUMERIC_MISMATCH"
                    )
                else:
                    pair_status = "UNRESOLVED"
                pair_fd_agreement = (
                    "MISMATCH"
                    if any(row["fd_ad_agreement"] == "MISMATCH" for row in rows)
                    else "CONSISTENT"
                    if all(row["fd_ad_agreement"] == "CONSISTENT" for row in rows)
                    else "UNAVAILABLE"
                )
                pair_resolution = (
                    "RESOLVED"
                    if all(row["resolution"] == "RESOLVED" for row in rows)
                    else "UNAVAILABLE"
                    if any(row["resolution"] == "UNAVAILABLE" for row in rows)
                    else "UNRESOLVED"
                )
                pair_branch = (
                    "CROSS"
                    if any(row["recorded_branch_schedule"] == "CROSS" for row in rows)
                    else "INCOMPLETE"
                    if any(
                        row["recorded_branch_schedule"] == "INCOMPLETE" for row in rows
                    )
                    else "STABLE"
                )
                pair_fd_exclusions = sorted(
                    {
                        row["fd_ad_exclusion_reason"]
                        for row in rows
                        if row["fd_ad_exclusion_reason"] is not None
                    }
                )
                if not pair_fd_exclusions and stability != "STABLE":
                    pair_fd_exclusions = ["TWO_STEP_UNSTABLE"]
                ad_difference, ad_difference_status = signed_residual(jvp, dot)
                results.append(
                    {
                        "fixture": case,
                        "selector": selector,
                        "direction": direction,
                        "jvp": jvp,
                        "vjp_dot": dot,
                        "duality": duality,
                        "ad_duality_signed_residual": ad_difference,
                        "ad_duality_signed_residual_status": ad_difference_status,
                        "ad_duality_relative_residual": relative_residual(jvp, dot),
                        "fd_resolution": pair_resolution,
                        "fd_ad_agreement": pair_fd_agreement,
                        "fd_ad_eligible": not pair_fd_exclusions,
                        "fd_ad_exclusion_reasons": pair_fd_exclusions,
                        "recorded_branch_schedule": pair_branch,
                        "selector_status": "SPEC_ONLY"
                        if center_available
                        and graph_available
                        and all(row["resolution"] != "UNAVAILABLE" for row in rows)
                        else "INCONCLUSIVE",
                        "connectivity": connectivity,
                        "steps": rows,
                        "two_step_stability": stability,
                        "pair_status": pair_status,
                    }
                )
    return {
        "schema": "kdm6.synthetic33.offline_replay.v1",
        "status": "INCONCLUSIVE",
        "calls": len(assets),
        "thresholds": {
            "relative_tolerance": 1e-5,
            "absolute_tolerance": 1e-8,
            "minimum_output_ulps": 16,
            "minimum_fd_magnitude": 1e-8,
        },
        "rows": results,
        "scope": "offline synthetic evidence only; no model, DSO, native or physical claim",
    }
