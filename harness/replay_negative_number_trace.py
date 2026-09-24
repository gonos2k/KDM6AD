#!/usr/bin/env python3
"""Replay selected mp237 host updates and boundary copies, not a positivity fix."""

import json
import math
import struct
from fractions import Fraction
from pathlib import Path

from replay_native_number import f32

EVIDENCE = Path(__file__).parent / "evidence/negative_number_trace_2026-09-24.json"


def bits(x):
    return struct.unpack("I", struct.pack("f", x))[0]


def fma32(a, b, c):
    """Exact-rational product+sum, rounded once to finite binary32.

    Check adjacent floats against the exact rational to avoid double rounding
    through Python binary64. This bounded witness rejects overflow.
    """
    assert all(math.isfinite(x) and f32(x) == x for x in (a, b, c))
    exact = Fraction(a) * Fraction(b) + Fraction(c)
    guess = f32(float(exact))
    assert math.isfinite(guess)
    if guess == 0:
        candidates = [-(2.0**-149), 0.0, 2.0**-149]
    else:
        n = bits(guess)
        candidates = [
            struct.unpack("f", struct.pack("I", i))[0] for i in (n - 1, n, n + 1)
        ]
    nearest = min(
        (x for x in candidates if math.isfinite(x)),
        key=lambda x: (abs(Fraction(x) - exact), bits(x) & 1),
    )
    if nearest == 0 and exact:
        return math.copysign(0.0, float(exact))
    if (
        exact == 0
        and c == 0
        and math.copysign(1.0, a) * math.copysign(1.0, b) < 0
        and math.copysign(1.0, c) < 0
    ):
        return -0.0
    return nearest


def rk_value(x, *, pd=False):
    old = x["old"] if pd or x["rk"] != 1 else x["value"]
    mo = f32(x["mu_old"] + x["mu_base"])
    mn = f32(x["mu_new"] + x["mu_base"])
    weight_old = fma32(x["c1"], mo, x["c2"])
    weight_new = fma32(x["c1"], mn, x["c2"])
    assert weight_new > 0
    interior = 2 <= x["i"] <= 233 and 2 <= x["j"] <= 281
    adv = f32(x["advect_tend"] * x["msfty"]) if interior and not pd else 0.0
    tendency = f32(adv + x["sc_tend"])
    return f32(fma32(weight_old, old, f32(x["dt"] * tendency)) / weight_new)


def replay(data):
    if not __debug__:
        raise RuntimeError("assertions must remain enabled")
    assert data["schema"] == "negative-number-trace-v1"
    for flag in (
        "operational_fix_applied",
        "physical_number_basis_resolved",
        "accepted_observation_cost",
    ):
        assert data[flag] is False
    proof = data["noninterference"]
    assert proof["sha256"]["control"] == proof["sha256"]["capture"]
    assert proof["input_records_equal"] and proof["namelist_equal"]
    assert proof["frames"] == [
        dict(frame=i, numeric_equal=253, times_equal=True) for i in range(3)
    ]
    p = data["provenance"]
    assert p["source"]["stripped_exact"] is True
    assert p["run_valid"]["experiment_valid"] and p["run_valid"]["model_completed"]
    assert p["run_valid"]["exit_code"] == 0
    assert p["module_em_object_matches_archive"] is True
    assert p["configuration"] == dict(
        spec_zone=1,
        specified=True,
        nested=False,
        have_bcs_scalar=False,
        scalar_adv_opt=1,
        polar=False,
    )
    assert len(data["history_targets"]) == 11
    for h, target in zip(data["history_targets"], p["source"]["targets"][:11]):
        assert all(h[k] == target[k] for k in ("field", "i", "j", "k"))
    records = data["records"]
    expected_fields = set(data["fields"])
    assert expected_fields == {
        "stage",
        "step",
        "rk",
        "target",
        "species",
        "i",
        "k",
        "j",
        "tile",
        "value",
        "old",
        "sc_tend",
        "advect_tend",
        "c1",
        "c2",
        "mu_old",
        "mu_new",
        "mu_base",
        "dt",
        "msfty",
        "spec_zone",
    }
    assert len(records) == 1188
    index = {}
    stages = [("BEGIN", 0), ("MICRO_BEFORE", 0), ("MICRO_AFTER", 0), ("END", 0)]
    for rk in (1, 2, 3):
        stages += [
            (s, rk)
            for s in (
                "TEND_BEFORE",
                "RK_BEFORE",
                "RK_AFTER",
                "FLOW_DEP_BDY_BEFORE",
                "FLOW_DEP_BDY_AFTER",
            )
        ]
    for rk in (1, 2, 4):
        stages += [
            (s, rk) for s in ("SET_PHYSICAL_BC3D_BEFORE", "SET_PHYSICAL_BC3D_AFTER")
        ]
    stages += [("PD_BEFORE", 3), ("PD_AFTER", 3)]
    for r in records:
        assert set(r) == expected_fields
        assert all(math.isfinite(v) for k, v in r.items() if k != "stage")
        key = (r["stage"], r["step"], r["rk"], r["target"])
        assert key not in index
        index[key] = r
        target = p["source"]["targets"][r["target"] - 1]
        assert (r["i"], r["j"], r["k"]) == (target["i"], target["j"], target["k"])
        assert r["species"] == {"QNCLOUD": 3, "QNICE": 4, "QNRAIN": 6}[target["field"]]
    assert set(index) == {
        (stage, step, rk, t)
        for stage, rk in stages
        for step in (1, 2)
        for t in range(1, 23)
    }
    rk_count = pd_count = 0
    for r in records:
        if r["stage"] == "RK_BEFORE":
            post = index["RK_AFTER", r["step"], r["rk"], r["target"]]
            assert bits(rk_value(r)) == bits(post["value"])
            rk_count += 1
        elif r["stage"] == "PD_BEFORE":
            post = index["PD_AFTER", r["step"], r["rk"], r["target"]]
            assert bits(rk_value(r, pd=True)) == bits(post["old"])
            assert post["old"] >= 0 and post["sc_tend"] == 0
            pd_count += 1
    chronology = [("BEGIN", 0)]
    for rk in (1, 2, 3):
        if rk == 3:
            chronology += [("PD_BEFORE", 3), ("PD_AFTER", 3)]
        chronology += [
            (s, rk)
            for s in (
                "TEND_BEFORE",
                "RK_BEFORE",
                "RK_AFTER",
                "FLOW_DEP_BDY_BEFORE",
                "FLOW_DEP_BDY_AFTER",
            )
        ]
        if rk < 3:
            chronology += [
                (s, rk) for s in ("SET_PHYSICAL_BC3D_BEFORE", "SET_PHYSICAL_BC3D_AFTER")
            ]
    chronology += [
        ("MICRO_BEFORE", 0),
        ("MICRO_AFTER", 0),
        ("SET_PHYSICAL_BC3D_BEFORE", 4),
        ("SET_PHYSICAL_BC3D_AFTER", 4),
        ("END", 0),
    ]
    rank = {key: i for i, key in enumerate(chronology)}
    chains = []
    for t in range(1, 12):
        donor = t + 11
        negative = [r for r in records if r["target"] == donor and r["value"] < 0]
        first = min(negative, key=lambda r: (r["step"], rank[r["stage"], r["rk"]]))
        assert first["stage"] == "RK_AFTER" and first["step"] == 2
        before = index["RK_BEFORE", 2, first["rk"], donor]
        assert before["value"] >= 0
        for step in (1, 2):
            for rk in (1, 2, 3):
                flow = index["FLOW_DEP_BDY_BEFORE", step, rk, t]
                after = index["FLOW_DEP_BDY_AFTER", step, rk, t]
                inner = index["RK_AFTER", step, rk, donor]
                # FLOW slots old/sc_tend/c1/c2 hold donor value, velocity, donor j, zone.
                assert flow["old"] == inner["value"]
                assert (int(flow["advect_tend"]), int(flow["c1"])) == (
                    inner["i"],
                    inner["j"],
                )
                assert flow["c2"] == 1
                assert after["value"] == (flow["old"] if flow["sc_tend"] > 0 else 0.0)
        outer_before = index["MICRO_BEFORE", 2, 0, t]["value"]
        outer_after = index["MICRO_AFTER", 2, 0, t]["value"]
        inner_before = index["MICRO_BEFORE", 2, 0, donor]["value"]
        inner_after = index["MICRO_AFTER", 2, 0, donor]["value"]
        assert outer_before == outer_after == inner_before < 0 <= inner_after
        assert (
            index["END", 2, 0, t]["value"]
            == data["history_targets"][t - 1]["value"]
            == outer_after
        )
        chains.append(
            dict(
                target=t,
                first_negative_rk=first["rk"],
                first_negative_value=first["value"],
                final_boundary=outer_after,
                inner_after_microphysics=inner_after,
            )
        )
    return dict(
        scope="selected_22_cells_two_steps_native_trace",
        rk_updates_exact=rk_count,
        pd_updates_exact=pd_count,
        chains=chains,
        operational_fix_applied=False,
        physical_number_basis_resolved=False,
        accepted_observation_cost=False,
    )


if __name__ == "__main__":
    print(json.dumps(replay(json.loads(EVIDENCE.read_text())), indent=2))
