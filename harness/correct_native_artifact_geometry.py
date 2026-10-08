"""Correct endpoint-labelled distances without rewriting historical H results."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

EARTH_RADIUS_M = 6371008.8


def spherical_distance_m(first, second):
    """Haversine distance between explicit (latitude, longitude) endpoints."""
    for point in (first, second):
        if len(point) != 2 or not all(math.isfinite(float(v)) for v in point):
            raise ValueError("distance needs two finite latitude/longitude pairs")
        if not (-90 <= point[0] <= 90 and -180 <= point[1] <= 180):
            raise ValueError("latitude/longitude outside geographical bounds")
    p1, l1 = map(math.radians, first)
    p2, l2 = map(math.radians, second)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin((l2 - l1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, max(0.0, a))))


def distance_fields(ami, native, viirs):
    """Use this explicit three-endpoint map in subsequent comparison producers."""
    return {
        "ami_center_vs_native_center_distance_m": spherical_distance_m(ami, native),
        "ami_center_vs_viirs_center_distance_m": spherical_distance_m(ami, viirs),
        "native_center_vs_viirs_center_distance_m": spherical_distance_m(native, viirs),
    }


def correction_record(result_path, observation_path):
    result_bytes, observation_bytes = result_path.read_bytes(), observation_path.read_bytes()
    result, obs = json.loads(result_bytes), json.loads(observation_bytes)
    candidate = obs["selected_viirs_sample"]
    if (result["selected_ami_lat_lon"] != obs["ami_lat_lon"]
            or result["selected_native_lat_lon"] != candidate["native_lat_lon"]
            or result["selected_native_j_i_0based"] != candidate["native_j_i_0based"]
            or result["selected_ami_row_col_0based"] != obs["ami_row_col_0based"]):
        raise ValueError("result and observation are not the same selected endpoints")
    if result["observation_result_sha256"] != hashlib.sha256(observation_bytes).hexdigest():
        raise ValueError("observation bytes differ from the result's pinned source")
    endpoints = {"ami": result["selected_ami_lat_lon"], "native": result["selected_native_lat_lon"],
                 "viirs": candidate["obs_lat_lon"]}
    record = {
        "schema": "native_artifact_geometry_correction_v1",
        "scope": "metadata-only sidecar; no model, RTTOV, BT, cost or acceptance change",
        "result_sha256": hashlib.sha256(result_bytes).hexdigest(),
        "observation_sha256": hashlib.sha256(observation_bytes).hexdigest(),
        "native_run_id": result["native_run_id"], "endpoints_lat_lon": endpoints,
        "earth_radius_m": EARTH_RADIUS_M,
        "historical_mislabelled_ami_native_distance_m": result["ami_center_vs_native_center_distance_m"],
        "corrected_distances": distance_fields(endpoints["ami"], endpoints["native"], endpoints["viirs"]),
        "native_run_valid": result["native_run_valid"], "experiment_valid": result["experiment_valid"],
        "diagnostic_only": result["diagnostic_only"], "eligible_for_artifact_gates": result["eligible_for_artifact_gates"],
    }
    if result_bytes != result_path.read_bytes() or observation_bytes != observation_path.read_bytes():
        raise RuntimeError("source changed during metadata correction")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("observation", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    record = correction_record(args.result, args.observation)
    with args.output.open("x") as stream:
        json.dump(record, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
