#!/usr/bin/env python3
"""Read only native time metadata and bind existing L1B targets conditionally.

Fixed current-case audit, not a model runner, input generator or scene selector.
Boundary metadata intervals and cached forecast horizons are different evidence.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

import netCDF4

ROOT = Path(__file__).resolve().parents[3]
PACKET = Path(__file__).resolve().parent
CASE = Path("/Users/yhlee/KDM6AD-k/host/lc05_da_run")
THIS_KEY = "md___thisbdytimee_x_t_d_o_m_a_i_n_m_e_t_a_data_"
NEXT_KEY = "md___nextbdytimee_x_t_d_o_m_a_i_n_m_e_t_a_data_"


def parse_time(value):
    return datetime.strptime(value, "%Y-%m-%d_%H:%M:%S")


def boundary_intervals(times, starts, ends):
    if not times or len(times) != len(starts) or len(starts) != len(ends):
        raise ValueError("boundary time metadata length mismatch")
    if list(times) != list(starts):
        raise ValueError("Times differ from THISBDYTIME record starts")
    result = []
    previous_end = None
    for start, end in zip(starts, ends):
        a, b = parse_time(start), parse_time(end)
        if b <= a or (previous_end is not None and a != previous_end):
            raise ValueError("invalid or discontinuous boundary interval")
        result.append({"start_inclusive": start, "end_exclusive": end})
        previous_end = b
    return result


def assess_window(initial_time, target_nominal_time, intervals):
    """Time coverage only: an earlier init can support a later valid date.

    A final state can be reached at the last interval endpoint; advancing from
    that endpoint requires another interval. This is not scientific admission.
    """
    initial, target = parse_time(initial_time), parse_time(target_nominal_time)
    start, end = parse_time(intervals[0]["start_inclusive"]), parse_time(intervals[-1]["end_exclusive"])
    if target < initial:
        raise ValueError("target precedes initialization")
    return {
        "initial_time": initial_time,
        "target_nominal_time_assumed_model_UTC": target_nominal_time,
        "forecast_lead_seconds": int((target - initial).total_seconds()),
        "local_background_valid_time_required": (target - timedelta(seconds=20)).strftime("%Y-%m-%d_%H:%M:%S"),
        "local_slot_valid_time_required": target_nominal_time,
        "existing_8frame_intake_last_time_required": (target + timedelta(seconds=120)).strftime("%Y-%m-%d_%H:%M:%S"),
        "boundary_supports_run_to_target": start <= initial <= target <= end,
        "boundary_supports_existing_8frame_intake": start <= initial <= target + timedelta(seconds=120) <= end,
        "advance_from_target_supported_by_current_BC": start <= target < end,
        "seconds_after_last_boundary_interval_end": max(0, int((target - end).total_seconds())),
        "same_initialization_date_required": False,
    }


def time_metadata(path, keys):
    before = path.stat()
    with netCDF4.Dataset(path) as ds:
        values = {key: [str(t) for t in netCDF4.chartostring(ds.variables[key][:]).reshape(-1)] for key in keys}
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("native metadata file changed during read")
    return {"path": str(path), "resolved": str(path.resolve()), "size_bytes": after.st_size,
            "mtime_ns": after.st_mtime_ns, "variables_read": values,
            "whole_file_hash": "NOT_COMPUTED; time metadata only"}


def main():
    output = PACKET / "NATIVE_TIME_LINKAGE.json"
    if output.exists():
        raise FileExistsError("refusing to overwrite time-linkage evidence")
    ic = time_metadata(CASE / "wrfinput_d01", ["Times"])
    bc = time_metadata(CASE / "wrfbdy_d01", ["Times", THIS_KEY, NEXT_KEY])
    v = bc["variables_read"]
    intervals = boundary_intervals(v["Times"], v[THIS_KEY], v[NEXT_KEY])
    initial = ic["variables_read"]["Times"][0]
    obs_path = ROOT / "harness/evidence/pr403_l1b_heldout_2026-10-11/RESULT.json"
    obs = json.loads(obs_path.read_text())
    links = []
    for scene in obs["scenes"]:
        stamp = datetime.strptime(scene["selected_nominal_slot_obt"], "%Y%m%d%H%M").strftime("%Y-%m-%d_%H:%M:%S")
        links.append({"observation_date": scene["date"], "nominal_slot_OBT": scene["selected_nominal_slot_obt"],
                      "time_assumption": "NOMINAL_FILENAME_TIME_AS_MODEL_UTC_RESEARCH_MODE; not measured pixel UTC",
                      "observed_pixel_UTC": None, "analysis_channel_ids": list(range(10, 17)),
                      "nearest_pixel": {k: scene["nearest_pixel"][k] for k in ["row", "column", "latitude_deg", "longitude_deg"]},
                      "existing_IC_candidate_time_assessment": assess_window(initial, stamp, intervals),
                      "selected_native_run_id": None, "selected_native_state_forcing_pressure_surface": None,
                      "status": "PENDING_NATIVE_INPUT", "analysis_executed": False})
    result = {"basis_main": "cc0a2edb", "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "IC_time_metadata": ic, "BC_time_metadata": bc, "boundary_intervals": intervals,
              "correction": "09UTC is the last boundary record START; its NEXTBDYTIME interval endpoint is12UTC. No boundary advance at/past12 is certified.",
              "L1B_result_sha256": hashlib.sha256(obs_path.read_bytes()).hexdigest(),
              "case_links": links, "calls": {"native": 0, "M": 0, "H_K": 0, "optimizer": 0, "acquisition": 0},
              "limits": "No state/boundary arrays or forecast files read. Cached initialization suffix counts are not valid-time horizon evidence. No global archive-absence claim."}
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"boundary_interval_end": intervals[-1]["end_exclusive"],
                      "case_statuses": [r["status"] for r in links]}, indent=2))


if __name__ == "__main__":
    main()
