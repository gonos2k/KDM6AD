"""Associate changed native levels with retained optical rows and Huber terms."""

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent


def analyze(w):
    result = []
    for p in w["profiles"]:
        levels = sorted({x["k_1based"] for x in p["changed_moment_words"]})
        layers = []
        for k in levels:
            # Native 39 levels are reversed, following the fixed 27-layer clear prefix.
            row = 27 + 39 - k
            values = []
            for opt in p["optics"]:
                ice = opt["hydro.txt"]["values"][row]
                liquid = opt["hydro_liquid"]["values"][row]
                size = opt["hydro_deff.txt"]["values"][row]
                frac = opt["hydro_frac.txt"]["values"][row]
                values.append(
                    {
                        "ice_g_m3": ice,
                        "liquid_g_m3": liquid,
                        "diameter_um": size,
                        "diameter_bound_observed": "minimum_10"
                        if size == 10
                        else ("maximum_120" if size == 120 else "interior"),
                        "cloud_fraction": frac,
                        "total_content_above_1e-6_g_m3": ice + liquid > 1e-6,
                    }
                )
            layers.append(
                {
                    "native_k_1based": k,
                    "rttov_layer_1based": row + 1,
                    "optics": values,
                    "guard_to_pilot": {
                        "ice_content_changed": values[1]["ice_g_m3"]
                        != values[2]["ice_g_m3"],
                        "observed_diameter_bound_category_changed": values[1][
                            "diameter_bound_observed"
                        ]
                        != values[2]["diameter_bound_observed"],
                        "serialized_content_threshold_side_changed": values[1][
                            "total_content_above_1e-6_g_m3"
                        ]
                        != values[2]["total_content_above_1e-6_g_m3"],
                        "cloud_fraction_changed": values[1]["cloud_fraction"]
                        != values[2]["cloud_fraction"],
                    },
                }
            )
        result.append(
            {
                "i": p["i"],
                "j": p["j"],
                "changed_native_layers": layers,
                "channel_bt_delta_pilot_minus_qnc": [
                    a - b for a, b in zip(p["bt"][2], p["bt"][1])
                ],
                "channel_huber_delta_pilot_minus_qnc": [
                    a - b for a, b in zip(p["huber"][2], p["huber"][1])
                ],
                "seven_channel_huber_delta": math.fsum(
                    a - b for a, b in zip(p["huber"][2], p["huber"][1])
                ),
            }
        )
    return {
        "channels": w["channels"],
        "cases": w["cases"],
        "profiles": result,
        "east10_channel_huber_deltas": [
            math.fsum(p["channel_huber_delta_pilot_minus_qnc"][i] for p in result)
            for i in range(7)
        ],
        "east10_fixed_m0_cost_delta": math.fsum(
            p["seven_channel_huber_delta"] for p in result
        )
        / 377342,
    }


if __name__ == "__main__":
    (HERE / "analysis.json").write_text(
        json.dumps(
            analyze(json.loads((HERE / "witness.json").read_bytes())),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
