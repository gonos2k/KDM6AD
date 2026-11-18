"""Branch-aware independent final NC/NCCN differences for TH16/QV16."""

from __future__ import annotations

import math
import struct


K = 39
NC16 = 8 * K + 15
NCCN16 = 7 * K + 15
ACCEPTED = {
    "th16_abs": frozenset(("0.001", "0.0001")),
    "qv16_rel": frozenset(("0.0001",)),
    "th16_abs_qv16_rel_joint": frozenset(("0.0001",)),
}
EXPECTED_CROSSINGS = frozenset((
    "th16_abs/0.01/high",
    "qv16_rel/0.001/low",
    "th16_abs_qv16_rel_joint/0.001/low",
))


def require(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError("thermal final FD: " + why)


def from_word(raw: str) -> float:
    require(isinstance(raw, str) and 1 <= len(raw) <= 16
            and all(char in "0123456789abcdefABCDEF" for char in raw),
            "raw f64 word syntax")
    bits = int(raw, 16)
    require(0 <= bits < 1 << 64, "raw f64 word range")
    value = struct.unpack(">d", bits.to_bytes(8, "big"))[0]
    require(math.isfinite(value), "finite f64 word")
    return value


def finite_values(why: str, *values: float) -> None:
    require(all(math.isfinite(value) for value in values), "finite " + why)


def finite_state_words(raw_words: list[str], why: str) -> list[float]:
    require(isinstance(raw_words, list) and len(raw_words) == 12 * K,
            why + " full state word inventory")
    return [from_word(raw) for raw in raw_words]


def check_final_thermal_differences(result: dict) -> dict[str, object]:
    """Accept only activation-stable final differences using represented gaps."""
    thermal = result["thermal_directions"]
    directions = thermal["directions"]
    require(set(directions) == set(ACCEPTED), "direction inventory")
    qv0 = float(thermal["input"]["qv16"])
    finite_values("baseline QV16", qv0)
    require(qv0 > 0.0, "positive baseline QV16")
    th_jvp = directions["th16_abs"]["jvp"]["final_nc_nccn"]
    qv_jvp = directions["qv16_rel"]["jvp"]["final_nc_nccn"]
    require(len(th_jvp) == len(qv_jvp) == 2, "final JVP pair inventory")
    finite_values("final TH/QV JVPs", *(float(x) for x in (*th_jvp, *qv_jvp)))
    require(float(th_jvp[1]) == float(qv_jvp[1]) == 0.0,
            "NCCN16 structural floor tangent")
    baseline = finite_state_words(result["baseline"]["value_final_raw"], "baseline")
    baseline_nc = baseline[NC16]
    baseline_nccn = baseline[NCCN16]
    baseline_th = float(thermal["input"]["th16"])
    finite_values("baseline TH16", baseline_th)
    require(thermal["baseline_d1_branch"]["activation"]["nccn_floor_active"],
            "baseline NCCN floor selected")

    crossings: list[str] = []
    accepted: list[dict[str, object]] = []
    finite_changes: list[dict[str, object]] = []
    one_sided: list[dict[str, object]] = []
    nccn_zero_comparisons = 0
    max_error = max_one_sided_error = 0.0
    for name, direction in directions.items():
        for hkey, pair in direction["finite_differences"].items():
            h = float(hkey)
            low_input, high_input = pair["low_input"], pair["high_input"]
            dth = float(high_input["th16"]) - float(low_input["th16"])
            dqv_rel = (float(high_input["qv16"]) - float(low_input["qv16"])) / qv0
            finite_values(name + "/" + hkey + " represented input gaps", h, dth, dqv_rel)
            predicted = float(th_jvp[0]) * dth + float(qv_jvp[0]) * dqv_rel
            high_state = finite_state_words(pair["high_final_raw"], name + "/" + hkey + "/high")
            low_state = finite_state_words(pair["low_final_raw"], name + "/" + hkey + "/low")
            high = high_state[NC16]
            low = low_state[NC16]
            observed = high - low
            scale = max(abs(observed), abs(predicted), math.ulp(baseline_nc))
            residual = abs(observed - predicted)
            error = residual / scale
            signal_ulp = abs(observed) / math.ulp(baseline_nc)
            finite_values(name + "/" + hkey + " NC16 central diagnostic",
                          high, low, observed, predicted, residual, scale, error, signal_ulp)

            changed = []
            for side in ("low", "high"):
                branch = pair[side + "_branch"]["activation"]
                if branch["activation_upper_bound_changed_vs_baseline"]:
                    changed.append(side)
                    crossings.append(name + "/" + hkey + "/" + side)
                require(branch["nccn_floor_active"],
                        name + "/" + hkey + "/" + side + " NCCN floor selected")
                nccn = (low_state if side == "low" else high_state)[NCCN16]
                require(nccn == baseline_nccn,
                        name + "/" + hkey + "/" + side + " final NCCN raw floor")
                nccn_zero_comparisons += 1

            row = {"direction": name, "h": hkey, "observed_nc16": observed,
                   "predicted_nc16": predicted, "relative_error": error,
                   "observed_output_ulp": signal_ulp,
                   "activation_crossing_sides": changed}
            if hkey in ACCEPTED[name]:
                require(not changed, name + "/" + hkey + " accepted activation branch")
                require(abs(observed) > 32 * math.ulp(baseline_nc),
                        name + "/" + hkey + " resolvable NC16 signal")
                require(error <= 1e-6, name + "/" + hkey + " final NC16 central derivative")
                max_error = max(max_error, error)
                accepted.append(row)
                for side, endpoint, endpoint_input in (
                    ("low", low, low_input), ("high", high, high_input)
                ):
                    one_dth = float(endpoint_input["th16"]) - baseline_th
                    one_dqv_rel = (float(endpoint_input["qv16"]) - qv0) / qv0
                    one_pred = float(th_jvp[0]) * one_dth + float(qv_jvp[0]) * one_dqv_rel
                    one_obs = endpoint - baseline_nc
                    one_scale = max(abs(one_obs), abs(one_pred), math.ulp(baseline_nc))
                    one_residual = abs(one_obs - one_pred)
                    one_error = one_residual / one_scale
                    finite_values(name + "/" + hkey + "/" + side + " NC16 one-sided diagnostic",
                                  one_dth, one_dqv_rel, one_pred, one_obs,
                                  one_residual, one_scale, one_error)
                    require(abs(one_obs) > 32 * math.ulp(baseline_nc),
                            name + "/" + hkey + "/" + side + " resolvable one-sided NC16")
                    require(one_error <= max(4 * h, 4 * math.ulp(baseline_nc) / one_scale),
                            name + "/" + hkey + "/" + side + " final NC16 one-sided derivative")
                    max_one_sided_error = max(max_one_sided_error, one_error)
                    one_sided.append({"direction": name, "h": hkey, "side": side,
                                      "observed_nc16": one_obs, "predicted_nc16": one_pred,
                                      "relative_error": one_error})
            else:
                require(changed, name + "/" + hkey + " excluded activation crossing")
                finite_changes.append(row)

    require(frozenset(crossings) == EXPECTED_CROSSINGS and len(crossings) == 3,
            "exact activation crossing set")
    require(len(accepted) == 4 and len(finite_changes) == 3 and len(one_sided) == 8
            and nccn_zero_comparisons == 14,
            "accepted/crossing endpoint inventory")
    finite_values("final summary extrema", max_error, max_one_sided_error)
    return {
        "thermal_final_nc_accepted_pairs": len(accepted),
        "thermal_final_nc_crossing_pairs": len(finite_changes),
        "thermal_final_nc_central_checks": accepted,
        "thermal_final_nc_one_sided_checks": one_sided,
        "thermal_final_crossing_finite_changes": finite_changes,
        "thermal_final_activation_crossing_endpoints": sorted(crossings),
        "thermal_final_nccn_floor_endpoint_checks": nccn_zero_comparisons,
        "max_thermal_final_nc_central_relative_error": max_error,
        "max_thermal_final_nc_one_sided_relative_error": max_one_sided_error,
    }
