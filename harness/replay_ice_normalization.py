#!/usr/bin/env python3
"""Check retained mp237 ice-normalization records, not physical number approval."""

import json
import math
from collections import Counter
from pathlib import Path

from replay_native_number import f32


EVIDENCE = (
    Path(__file__).resolve().parent / "evidence/normalized_handoff_2026-09-24.json"
)
FIELDS = "tag call lat loop substep i native_k raw_mass_velocity raw_number_velocity mass_coefficient number_coefficient dz dt qi ni mstep candidate departure_qi departure_ni upper_departure_qi upper_departure_ni post_qi post_ni".split()
INTS = {"call", "lat", "loop", "substep", "i", "native_k"}
COUNTS = {
    "RAW_INITIAL": 39,
    "INITIAL_NORMALIZED": 39,
    "INITIAL_MSTEP": 39,
    "RAW_MAIN": 39,
    "MAIN_NORMALIZED": 39,
    "LATER_RAW": 39,
    "LATER_NORMALIZED": 39,
    "HANDOFF_TOP_BEFORE": 1,
    "HANDOFF_TOP_AFTER": 1,
    "HANDOFF_INTERIOR_BEFORE": 38,
    "HANDOFF_INTERIOR_AFTER": 38,
}
CALLS, LEVELS, TARGET_I, LAT = (1, 2), set(range(1, 40)), 144, 153


def validate(data):
    if not __debug__:
        raise RuntimeError("assertions must remain enabled")
    assert data["schema"] == "normalized-handoff-v1"
    assert data["scope"] == "isolated_mp237_normalization_only_two_native_calls"
    for flag in (
        "operational_fix_applied",
        "physical_number_basis_resolved",
        "accepted_observation_cost",
    ):
        assert data[flag] is False, flag

    p = data["provenance"]
    for name in ("control_valid", "capture_valid"):
        run = p[name]
        assert run["experiment_valid"] and run["model_completed"]
        assert run["exit_code"] == 0 and run["active_input_identity_complete"]
        assert run["actual_proc_grid"] == "1x1"
    ni = data["noninterference"]
    assert ni["input_records_equal"] and ni["namelist_equal"]
    assert ni["sha256"]["control"] == ni["sha256"]["capture"]
    assert [f["frame"] for f in ni["frames"]] == [0, 1, 2]
    assert all(f["numeric_equal"] == 253 and f["times_equal"] for f in ni["frames"])
    transform = p["source_transform"]
    assert transform["capture_strips_to_normalized_byte_exact"]
    delta = transform["physical_delta"]
    assert delta["source_lines_added"] == 2
    assert not delta["initial_mstep_selection_changed"]
    assert not delta["later_ice_normalization_changed"]
    assert "no n>=2 consumer executed" in p["later_stage_scope"]
    assert "rho was not captured" in p["mass_budget_scope"]

    records = data["records"]
    assert data["fields"] == FIELDS and len(records) == 702
    tags = Counter()
    stage = {}
    for r in records:
        assert set(r) == set(FIELDS)
        tags[r["tag"]] += 1
        assert r["call"] in CALLS and r["lat"] == LAT and r["i"] == TARGET_I
        assert (
            r["loop"] == 1 and r["native_k"] in LEVELS and r["dz"] > 0 and r["dt"] > 0
        )
        assert all(math.isfinite(r[k]) for k in FIELDS if k not in INTS | {"tag"})
        key = (r["call"], r["loop"], r["substep"], r["i"], r["native_k"])
        assert (r["tag"], key) not in stage, (r["tag"], key)
        stage[(r["tag"], key)] = r
    assert dict(tags) == {tag: n * 2 for tag, n in COUNTS.items()}, (
        "stage counts differ"
    )
    for tag, n in COUNTS.items():
        for call in CALLS:
            rows = [r for r in records if r["tag"] == tag and r["call"] == call]
            expected = (
                {39}
                if tag.startswith("HANDOFF_TOP")
                else set(range(1, 39))
                if tag.startswith("HANDOFF_INTERIOR")
                else LEVELS
            )
            assert len(rows) == n and {r["native_k"] for r in rows} == expected, tag

    def rows(tag):
        return {key: row for (name, key), row in stage.items() if name == tag}

    stages = {tag: rows(tag) for tag in COUNTS}
    max_raw_m = max_raw_n = max_rate_m = max_rate_n = 0.0
    max_cfl = {
        "INITIAL_NORMALIZED": 0.0,
        "MAIN_NORMALIZED": 0.0,
        "LATER_NORMALIZED": 0.0,
    }
    cfl_by_call = {
        tag: {call: {"mass": 0.0, "number": 0.0} for call in CALLS} for tag in max_cfl
    }
    for raw_tag, norm_tag in (
        ("RAW_INITIAL", "INITIAL_NORMALIZED"),
        ("RAW_MAIN", "MAIN_NORMALIZED"),
        ("LATER_RAW", "LATER_NORMALIZED"),
    ):
        raw, norm = stages[raw_tag], stages[norm_tag]
        assert raw.keys() == norm.keys()
        for key, a in raw.items():
            b = norm[key]
            assert a["dz"] == b["dz"] and a["dt"] == b["dt"]
            assert a["raw_mass_velocity"] / a["dz"] == b["mass_coefficient"]
            assert a["raw_number_velocity"] / a["dz"] == b["number_coefficient"]
            max_raw_m = max(max_raw_m, abs(a["raw_mass_velocity"]))
            max_raw_n = max(max_raw_n, abs(a["raw_number_velocity"]))
            max_rate_m = max(max_rate_m, abs(b["mass_coefficient"]))
            max_rate_n = max(max_rate_n, abs(b["number_coefficient"]))
            mass_cfl = b["mass_coefficient"] * b["dt"]
            number_cfl = b["number_coefficient"] * b["dt"]
            max_cfl[norm_tag] = max(max_cfl[norm_tag], mass_cfl, number_cfl)
            cfl_by_call[norm_tag][key[0]]["mass"] = max(
                cfl_by_call[norm_tag][key[0]]["mass"], mass_cfl
            )
            cfl_by_call[norm_tag][key[0]]["number"] = max(
                cfl_by_call[norm_tag][key[0]]["number"], number_cfl
            )

    # NINT(max(work1,workn)*dtcld + .5), then max(...,1); operands are DP.
    initial, selected = stages["INITIAL_NORMALIZED"], stages["INITIAL_MSTEP"]
    assert initial.keys() == selected.keys()
    candidates = []
    for call in CALLS:
        current = 1
        for k in range(39, 0, -1):
            key = (call, 1, 0, TARGET_I, k)
            row, got = initial[key], selected[key]
            cfl = max(row["mass_coefficient"], row["number_coefficient"]) * row["dt"]
            candidate = mstep_candidate(cfl)
            assert got["candidate"] == candidate
            current = max(current, candidate)
            assert got["mstep"] == current
            candidates.append(candidate)

    main = stages["MAIN_NORMALIZED"]
    handoff_before = rows("HANDOFF_TOP_BEFORE") | rows("HANDOFF_INTERIOR_BEFORE")
    handoff_after = rows("HANDOFF_TOP_AFTER") | rows("HANDOFF_INTERIOR_AFTER")
    initial_equal = 0
    for key, r in handoff_before.items():
        m = main[key]
        assert (r["dt"], r["mstep"]) == (m["dt"], m["mstep"]), (
            "handoff time/substep mismatch"
        )
        assert r["mass_coefficient"] == m["mass_coefficient"], (
            "handoff mass uses main-normalized"
        )
        assert r["number_coefficient"] == m["number_coefficient"], (
            "handoff number uses main-normalized"
        )
        earlier = initial[(key[0], 1, 0, TARGET_I, key[4])]
        initial_equal += (r["mass_coefficient"], r["number_coefficient"]) == (
            earlier["mass_coefficient"],
            earlier["number_coefficient"],
        )

    # Replay only the captured ni expression in f32 source order. No rho was
    # captured, so this does not assert a mass or physical number budget.
    max_dep_rate = max_arrival_rate = max_number_error = 0.0
    for key, before in handoff_before.items():
        after = handoff_after[key]
        assert all(
            before[f] == after[f]
            for f in ("dt", "mstep", "dz", "mass_coefficient", "number_coefficient")
        )
        assert 0 <= after["departure_ni"] <= before["ni"]
        subtracted = f32(before["ni"] - after["departure_ni"])
        max_dep_rate = max(max_dep_rate, abs(after["departure_ni"]) / before["dt"])
        if key[4] == 39:
            assert after["upper_departure_ni"] == 0.0
            expected = subtracted
        else:
            upper_key = (key[0], key[1], key[2], key[3], key[4] + 1)
            upper = handoff_after[upper_key]
            assert after["upper_departure_ni"] == upper["departure_ni"]
            arrival = f32(f32(after["upper_departure_ni"] * upper["dz"]) / before["dz"])
            max_arrival_rate = max(max_arrival_rate, abs(arrival) / before["dt"])
            expected = f32(subtracted + arrival)
        assert after["post_ni"] == expected == after["ni"]
        max_number_error = max(max_number_error, abs(after["post_ni"] - expected))

    assert all(r["mstep"] == 1 for r in main.values())
    assert {key[2] for key in stages["LATER_NORMALIZED"]} == {1}
    first_negative = None
    for call in CALLS:
        for k in range(39, 0, -1):
            key = (call, 1, 1, TARGET_I, k)
            before = (
                rows("HANDOFF_TOP_BEFORE")
                if k == 39
                else rows("HANDOFF_INTERIOR_BEFORE")
            )[key]
            after = (
                rows("HANDOFF_TOP_AFTER") if k == 39 else rows("HANDOFF_INTERIOR_AFTER")
            )[key]
            for phase, row, fields in (
                ("before", before, ("qi", "ni")),
                ("after", after, ("post_qi", "post_ni")),
            ):
                for field in fields:
                    if row[field] < 0:
                        first_negative = dict(
                            call=call,
                            native_k=k,
                            phase=phase,
                            field=field,
                            value=row[field],
                        )
                        break
                if first_negative:
                    break
            if first_negative:
                break
        if first_negative:
            break

    return {
        "calls": list(CALLS),
        "records": len(records),
        "stage_counts": dict(tags),
        "control_capture_noninterference": True,
        "mstep_max": max(int(r["mstep"]) for r in selected.values()),
        "max_cfl_mstep_selection": max_cfl["INITIAL_NORMALIZED"],
        "max_cfl_main_consumed": max_cfl["MAIN_NORMALIZED"],
        "max_cfl_later_prep_unconsumed": max_cfl["LATER_NORMALIZED"],
        "main_consumed_cfl_by_call": cfl_by_call["MAIN_NORMALIZED"],
        "later_prep_cfl_by_call_unconsumed": cfl_by_call["LATER_NORMALIZED"],
        "max_raw_mass_velocity_m_s": max_raw_m,
        "max_raw_number_velocity_m_s": max_raw_n,
        "max_mass_coefficient_s-1": max_rate_m,
        "max_number_coefficient_s-1": max_rate_n,
        "max_number_departure_rate_kernel_units_s-1": max_dep_rate,
        "max_number_arrival_rate_kernel_units_s-1": max_arrival_rate,
        "number_update_rows": len(handoff_before),
        "max_abs_number_update_error": max_number_error,
        "handoff_rows_matching_main_normalized": len(handoff_before),
        "handoff_rows_also_equal_initial_values": initial_equal,
        "first_negative_state_at_handoff": first_negative,
        "later_stage_scope": "n=1 preparation only; no n>=2 consumer ran (mstep_i=1)",
        "operational_fix_applied": False,
        "physical_number_basis_resolved": False,
        "accepted_observation_cost": False,
        "budget_scope": "ni f32 update replay only; rho absent; no physical number or mass budget",
    }


def mstep_candidate(cfl):
    """For nonnegative cfl, mirror Fortran NINT(cfl + 0.5) with floor(cfl+1)."""
    assert math.isfinite(cfl) and cfl >= 0
    return max(math.floor((cfl + 0.5) + 0.5), 1)


if __name__ == "__main__":
    print(
        json.dumps(
            validate(json.loads(EVIDENCE.read_text())),
            separators=(",", ":"),
            sort_keys=True,
        )
    )
