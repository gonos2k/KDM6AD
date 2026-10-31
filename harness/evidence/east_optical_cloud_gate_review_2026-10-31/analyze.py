"""Classify saved east-edge ice optics by serialized cloud fraction."""

from __future__ import annotations

import json
import math
from pathlib import Path
import struct


PACKET = Path(__file__).resolve().parent
PARENT = PACKET.parent / "east_optical_witness_2026-10-31"
CHANNELS = tuple(range(10, 17))
EAST_J = (*range(3, 12), 52)
FIXED_M0_CELLS = 377342


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def huber(residual: float) -> float:
    return 0.5 * residual * residual if abs(residual) <= 1 else abs(residual) - 0.5


def bound_category(diameter: float) -> str:
    return (
        "minimum_10"
        if diameter == 10
        else ("maximum_120" if diameter == 120 else "interior")
    )


def _values(profile: dict, case: int, field: str) -> list[float]:
    values = profile["optics"][case][field]["values"]
    require(
        len(values) == 66 and all(math.isfinite(v) for v in values),
        f"invalid optical rows for {field}",
    )
    return values


def analyze(witness: dict) -> dict:
    require(witness["schema"] == "east-optical-witness-v1", "witness schema differs")
    require(
        witness["cases"] == ["original_control", "qnc_guard_control", "pilot_control"],
        "case ordering differs",
    )
    require(tuple(witness["channels"]) == CHANNELS, "channel ordering differs")
    profiles = witness["profiles"]
    require(len(profiles) == len(EAST_J), "east profile count differs")
    strata = {
        name: {
            "native_rows": 0,
            "ice_changed": 0,
            "ice_increase": 0,
            "ice_decrease": 0,
            "diameter_changed": 0,
            "diameter_bound_category_changed": 0,
        }
        for name in ("cloud_fraction_positive", "cloud_fraction_zero")
    }
    ratios: list[float] = []
    cloudy_diameter: list[dict] = []
    bt_deltas: list[float] = []
    profile_loss_deltas: list[float] = []
    threshold_crossings = 0
    cloud_fraction_changes = 0
    changed_moment_layers = 0

    for profile, j in zip(profiles, EAST_J):
        require(
            profile["i"] == 234 and profile["j"] == j, "east profile coordinate differs"
        )
        require(profile["flat"] == (j - 1) * 234 + 233, "east flat index differs")
        levels = {item["k_1based"] for item in profile["changed_moment_words"]}
        require(
            levels and all(1 <= k <= 39 for k in levels),
            "changed native level inventory differs",
        )
        changed_moment_layers += len(levels)
        ice = [_values(profile, case, "hydro.txt") for case in (1, 2)]
        liquid = [_values(profile, case, "hydro_liquid") for case in (1, 2)]
        diameter = [_values(profile, case, "hydro_deff.txt") for case in (1, 2)]
        fraction = [_values(profile, case, "hydro_frac.txt") for case in (1, 2)]
        for k in range(1, 40):
            row = 66 - k
            guard_frac, pilot_frac = fraction[0][row], fraction[1][row]
            require(
                guard_frac in (0.0, 0.999999) and pilot_frac in (0.0, 0.999999),
                "serialized cloud fraction differs from case contract",
            )
            cloud_fraction_changes += guard_frac != pilot_frac
            require(guard_frac == pilot_frac, "guard/pilot cloud fraction changed")
            name = (
                "cloud_fraction_positive" if guard_frac > 0 else "cloud_fraction_zero"
            )
            group = strata[name]
            group["native_rows"] += 1
            guard_ice, pilot_ice = ice[0][row], ice[1][row]
            guard_diameter, pilot_diameter = diameter[0][row], diameter[1][row]
            require(
                guard_ice >= 0
                and pilot_ice >= 0
                and liquid[0][row] >= 0
                and liquid[1][row] >= 0,
                "negative serialized hydrometeor content",
            )
            threshold_crossings += (guard_ice + liquid[0][row] > 1e-6) != (
                pilot_ice + liquid[1][row] > 1e-6
            )
            if guard_ice != pilot_ice:
                require(k in levels, "ice change outside changed-moment layers")
                group["ice_changed"] += 1
                group["ice_increase"] += pilot_ice > guard_ice
                group["ice_decrease"] += pilot_ice < guard_ice
                if guard_frac > 0:
                    require(
                        guard_ice > 0, "cloudy ice ratio has zero guard denominator"
                    )
                    ratios.append(pilot_ice / guard_ice)
            if guard_diameter != pilot_diameter:
                require(k in levels, "diameter change outside changed-moment layers")
                group["diameter_changed"] += 1
                if guard_frac > 0:
                    cloudy_diameter.append(
                        {
                            "native_ijk": [234, j, k],
                            "rttov_layer_1based": row + 1,
                            "guard_um": guard_diameter,
                            "pilot_um": pilot_diameter,
                            "delta_um": pilot_diameter - guard_diameter,
                            "guard_float64_ulp_um": math.ulp(guard_diameter),
                            "same_float32": struct.pack("=f", guard_diameter)
                            == struct.pack("=f", pilot_diameter),
                        }
                    )
            group["diameter_bound_category_changed"] += bound_category(
                guard_diameter
            ) != bound_category(pilot_diameter)

        obs, guard_bt, pilot_bt = (
            profile["observation"],
            profile["bt"][1],
            profile["bt"][2],
        )
        require(
            len(obs) == len(guard_bt) == len(pilot_bt) == len(CHANNELS),
            "BT/observation channel count differs",
        )
        require(
            all(
                math.isfinite(v) for values in (obs, guard_bt, pilot_bt) for v in values
            ),
            "nonfinite BT or observation",
        )
        deltas = [pilot - guard for guard, pilot in zip(guard_bt, pilot_bt)]
        bt_deltas.extend(deltas)
        losses = [
            huber(pilot - observed) - huber(guard - observed)
            for guard, pilot, observed in zip(guard_bt, pilot_bt, obs)
        ]
        stored = [
            pilot - guard
            for guard, pilot in zip(profile["huber"][1], profile["huber"][2])
        ]
        require(losses == stored, "stored Huber losses differ from BT/observation")
        profile_loss_deltas.append(math.fsum(losses))

    total_ice = sum(group["ice_changed"] for group in strata.values())
    require(
        total_ice == changed_moment_layers,
        "changed ice and changed-moment layer counts differ",
    )
    require(ratios, "no cloudy ice ratios")
    numerator = math.fsum(profile_loss_deltas)
    require(len(bt_deltas) == 70, "BT cell count differs")
    return {
        "schema": "east-optical-cloud-gate-review-v1",
        "cases": ["qnc_guard_control", "pilot_control"],
        "native_levels_examined": 390,
        "changed_moment_layers": changed_moment_layers,
        "strata": strata,
        "cloud_fraction_changed": cloud_fraction_changes,
        "serialized_total_content_threshold_crossings": threshold_crossings,
        "cloudy_ice_pilot_over_guard_ratio": {"min": min(ratios), "max": max(ratios)},
        "cloudy_diameter_changes": cloudy_diameter,
        "bt_delta_K": {
            "cells": len(bt_deltas),
            "negative": sum(delta < 0 for delta in bt_deltas),
            "positive": sum(delta > 0 for delta in bt_deltas),
            "zero": sum(delta == 0 for delta in bt_deltas),
            "min": min(bt_deltas),
            "max": max(bt_deltas),
        },
        "huber": {
            "numerator_delta": numerator,
            "local_70_cell_mean_delta": numerator / len(bt_deltas),
            "fixed_m0_denominator": FIXED_M0_CELLS,
            "fixed_m0_cost_delta": numerator / FIXED_M0_CELLS,
        },
        "scope": "saved serialized optical rows and direct BTs; no new model calls or causal attribution",
    }


def main() -> None:
    witness = json.loads((PARENT / "witness.json").read_bytes())
    print(json.dumps(analyze(witness), indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
