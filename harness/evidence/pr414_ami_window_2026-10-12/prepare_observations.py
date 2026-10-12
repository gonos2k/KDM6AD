#!/usr/bin/env python3
"""Acquire and decode only the declared Jul19 AMI 0556/0606/0616 observations.

This producer creates observation inputs only. It does not read native forecast
arrays, call RTTOV, invoke M, or start an optimizer. Downloads are single-attempt
and exclusive; an error is preserved and is never retried automatically.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import urllib.parse
import urllib.request

import numpy as np

PACKET = Path(__file__).resolve().parent
ROOT = PACKET.parents[2]
sys.path.insert(0, str(ROOT / "oracle"))

from kdm6.obs.gk2a_l1b import AMI_CHANNELS, CLEAN_IR_CHANNELS, load_cal_table  # noqa: E402
from kdm6.obs.gk2a_l1b_la import read_la_slot  # noqa: E402

PRIVATE_ROOT = Path("/Users/yhlee/KDM6AD-k/host/research_evidence/pr414_ami_window_20261012")
ORIGINAL_RESTORE = ROOT / "harness/evidence/pr411_v4_actual_integration_2026-10-12/RESTORE_RESULT.json"
ORIGINAL_WIRE = ROOT / "harness/evidence/pr412_native_process_case_2026-10-12/L1B_WIRE_RESULT.json"
ORIGINAL_CASE = ROOT / "harness/evidence/pr412_native_process_case_2026-10-12/CASE.json"
SOURCE_LIST = ROOT / "graphify-out/other-native-search-20261012/AMI_0606_0616_SOURCE_LIST.json"
CALIBRATION = ROOT / "oracle/kdm6/obs/data/gk2a_ami_cal_202507190000.json"
MASK_HELPER = ROOT / "harness/evidence/pr403_l1b_heldout_2026-10-11/heldout_l1b.py"
BUCKET_ROOT = "https://noaa-gk2a-pds.s3.amazonaws.com/"
DATE = "20250719"
SLOTS = ("202507190556", "202507190606", "202507190616")
MODEL_TIMES = ("2025-07-19_05:56:00", "2025-07-19_06:06:00", "2025-07-19_06:16:00")
STEP_INDICES = (1, 31, 61)
BACKGROUND_TIME = "2025-07-19_05:55:40"
DT_S = 20
N_STEPS = 61
TIME_ASSUMPTION = "NOMINAL_FILENAME_TIME_AS_MODEL_UTC_RESEARCH_MODE"
TARGET_MODE = "PR412_JUL19_NATURAL_LIQUID_COLUMN"
TARGET_RADIUS_M = 2500.0
MAX_NEW_FILES = 18
PLAN_PATH = PACKET / "PREDECLARED.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def write_exclusive(path: Path, value, *, private: bool = False) -> None:
    path = Path(path)
    with path.open("x") as stream:
        if private:
            path.chmod(0o600)
        stream.write(json.dumps(value, indent=2, sort_keys=True,
                                ensure_ascii=False, allow_nan=False) + "\n")


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load helper module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_snapshot() -> dict[str, str]:
    paths = (
        Path(__file__).resolve(),
        ROOT / "oracle/kdm6/obs/gk2a_l1b_la.py",
        ROOT / "oracle/kdm6/obs/gk2a_l1b.py",
        ROOT / "oracle/kdm6/obs/gk2a_l1b_fd.py",
        ROOT / "oracle/kdm6/obs/obs_ingest.py",
        MASK_HELPER,
    )
    return {str(path.resolve()): sha256(path) for path in paths}


def _select_new_objects(source_listing: dict) -> list[dict]:
    required = set(CLEAN_IR_CHANNELS)
    selected = []
    seen = set()
    for row in source_listing.get("slots", []):
        key = row.get("key", "")
        match = re.fullmatch(
            r"AMI/L1B/LA/202507/19/06/gk2a_ami_le1b_([a-z0-9]+)_la020ge_(202507190606|202507190616)\.nc",
            key)
        if match is None:
            continue
        channel, slot = match.groups()
        if channel not in required:
            continue
        pair = (slot, channel)
        if pair in seen:
            raise ValueError(f"duplicate source-list entry for {slot}/{channel}")
        seen.add(pair)
        etag_raw = str(row["etag"])
        selected.append({
            "key": key,
            "channel": channel,
            "slot_obt": slot,
            "size_bytes": int(row["size"]),
            "etag": etag_raw.strip('"'),
            "etag_raw": etag_raw,
        })
    expected = {(slot, channel) for slot in SLOTS[1:] for channel in CLEAN_IR_CHANNELS}
    if seen != expected:
        missing = sorted(expected - seen)
        extra = sorted(seen - expected)
        raise ValueError(f"prelisted 0606/0616 thermal object set mismatch; missing={missing}, extra={extra}")
    return sorted(selected, key=lambda x: (x["slot_obt"], CLEAN_IR_CHANNELS.index(x["channel"])))


def _original_0556_records() -> tuple[list[dict], dict]:
    if not ORIGINAL_RESTORE.is_file():
        raise FileNotFoundError(f"original PR411 restore receipt missing: {ORIGINAL_RESTORE}")
    restore = json.loads(ORIGINAL_RESTORE.read_text())
    require(restore.get("status") == "ALL_NINE_ORIGINAL_HASHES_RESTORED",
            "original PR411 0556 source restoration is not complete")
    original_rows = restore.get("files", [])
    if len(original_rows) != len(CLEAN_IR_CHANNELS):
        raise ValueError("expected the original nine PR411 0556 files")
    records = []
    for row in original_rows:
        path = Path(row["path"])
        if not path.is_file():
            raise FileNotFoundError(f"immutable original 0556 object is absent: {path}")
        if sha256(path) != row["expected_sha256"]:
            raise ValueError(f"immutable original 0556 object hash mismatch: {path}")
        match = re.fullmatch(r"gk2a_ami_le1b_([a-z0-9]+)_la020ge_(202507190556)\.nc", path.name)
        if match is None:
            raise ValueError(f"unexpected original observation file name: {path.name}")
        channel, slot = match.groups()
        if row.get("bytes") is not None and path.stat().st_size != int(row["bytes"]):
            raise ValueError(f"original 0556 size mismatch: {path}")
        records.append({
            "channel": channel,
            "slot_obt": slot,
            "key": f"AMI/L1B/LA/202507/19/05/{path.name}",
            "path": str(path.resolve()),
            "size_bytes": path.stat().st_size,
            "sha256": row["expected_sha256"],
            "etag": str(row.get("etag", "")).strip('"') or None,
            "immutable_reused_source": True,
        })
    by_channel = {row["channel"] for row in records}
    if by_channel != set(CLEAN_IR_CHANNELS):
        raise ValueError(f"original PR411 0556 channel set mismatch: {sorted(by_channel)}")
    # Confirm PR412's source binding refers to the same exact nine bytes.
    wire = json.loads(ORIGINAL_WIRE.read_text())
    receipt = json.loads(Path(wire["private_decode_receipt_path"]).read_text())
    receipt_hashes = {row.get("name"): row.get("expected_sha256")
                      for row in receipt.get("source_files", [])}
    restored_hashes = {Path(row["path"]).name: row["sha256"]
                       for row in records}
    if receipt_hashes != restored_hashes:
        raise ValueError("original PR411 0556 bytes differ from PR412's actual observation files")
    return sorted(records, key=lambda x: CLEAN_IR_CHANNELS.index(x["channel"])), {
        "restore_receipt_path": str(ORIGINAL_RESTORE.resolve()),
        "restore_receipt_sha256": sha256(ORIGINAL_RESTORE),
        "wire_result_path": str(ORIGINAL_WIRE.resolve()),
        "wire_result_sha256": sha256(ORIGINAL_WIRE),
        "decode_receipt_path": str(Path(wire["private_decode_receipt_path"]).resolve()),
        "decode_receipt_sha256": sha256(Path(wire["private_decode_receipt_path"])),
    }


def build_plan() -> dict:
    if not SOURCE_LIST.is_file():
        raise FileNotFoundError(f"root-provided public S3 listing is missing: {SOURCE_LIST}")
    listing_bytes_hash = sha256(SOURCE_LIST)
    listing = json.loads(SOURCE_LIST.read_text())
    require(listing.get("truncated") == "false", "source listing must be complete")
    require(listing.get("url") == "https://noaa-gk2a-pds.s3.amazonaws.com/?list-type=2&prefix=AMI/L1B/LA/202507/19/06/",
            "unexpected source-list URL or prefix")
    new_objects = _select_new_objects(listing)
    require(len(new_objects) == MAX_NEW_FILES,
            f"declared download count must be exactly {MAX_NEW_FILES}")
    total_new_bytes = sum(row["size_bytes"] for row in new_objects)
    original, original_binding = _original_0556_records()
    case = json.loads(ORIGINAL_CASE.read_text())
    require(case["case_id"] == "PR412_JUL19_NATURAL_LIQUID_COLUMN",
            "unexpected original native case id")
    native = case["native"]
    require(native["background_valid_time"] == BACKGROUND_TIME,
            "PR412 background time differs from declared window origin")
    target = native["column"]
    slot_times = []
    for obt, model_time, step in zip(SLOTS, MODEL_TIMES, STEP_INDICES):
        slot_times.append({
            "nominal_slot_obt": obt,
            "nominal_model_time": model_time,
            "step_index": step,
            "seconds_after_saved_background": step * DT_S,
        })
    sources = source_snapshot()
    return {
        "schema": "pr414_ami_window_observation_preflight_v1",
        "status": "PREDECLARED_BEFORE_DOWNLOAD",
        "window_id": "PR414_JUL19_AMI_0556_0606_0616",
        "current_main": "f16645f11cf09c5ec47852cf4533552ea9c04fae",
        "producer_path": str(Path(__file__).resolve()),
        "producer_sha256": sources[str(Path(__file__).resolve())],
        "source_list_path": str(SOURCE_LIST.resolve()),
        "source_list_sha256": listing_bytes_hash,
        "s3_listing_url": listing["url"],
        "source_bucket": "noaa-gk2a-pds",
        "channels_source_nine": list(CLEAN_IR_CHANNELS),
        "analysis_channel_names": list(CLEAN_IR_CHANNELS[2:]),
        "analysis_channel_ids_1based": [AMI_CHANNELS.index(name) + 1
                                        for name in CLEAN_IR_CHANNELS[2:]],
        "calibration_path": str(CALIBRATION.resolve()),
        "calibration_sha256": sha256(CALIBRATION),
        "reader_source_sha256": sources,
        "time_assumption": "NOMINAL_FILENAME_TIME_AS_MODEL_UTC_RESEARCH_MODE",
        "time_assumption_note": (
            "Scene filename OBT labels are represented as nominal model UTC for the declared local window only; "
            "per-pixel UTC remains unverified and is never synthesized."),
        "native_reference": {
            "case_id": case["case_id"],
            "case_path": str(ORIGINAL_CASE.resolve()),
            "case_sha256": sha256(ORIGINAL_CASE),
            "run_id": native["run_id"],
            "run_dir": native["run_dir"],
            "initial_time": native["initial_time"],
            "background_valid_time": native["background_valid_time"],
            "column_j_i": [int(target["j"]), int(target["i"])],
            "latitude_deg": float(target["expected_latitude_deg"]),
            "longitude_deg": float(target["expected_longitude_deg"]),
            "coordinate_tolerance_deg": float(target["coordinate_tolerance_deg"]),
        },
        "original_0556_sources": original,
        "original_0556_bindings": original_binding,
        "new_s3_objects": new_objects,
        "download_budget": {
            "max_files": MAX_NEW_FILES,
            "planned_files": len(new_objects),
            "max_bytes": total_new_bytes,
            "planned_bytes": total_new_bytes,
            "automatic_retry": False,
            "request_attempts_per_object": 1,
            "extra_channels_downloaded": 0,
            "extra_slots_downloaded": 0,
        },
        "window_time_map": {
            "background_valid_time": BACKGROUND_TIME,
            "dt_s": DT_S,
            "n_steps": N_STEPS,
            "slot_times": slot_times,
            "forcing_window_bound_by_this_producer": False,
            "host_states_after_background_bound_by_this_producer": False,
            "pixel_utc_verified": False,
        },
        "decode_contract": {
            "reader": "unchanged oracle/kdm6/obs/gk2a_l1b_la.py::read_la_slot",
            "stride": 1,
            "geoselection_target": "PR412 selected native column j103/i48",
            "selection_precedes_quality_and_bt_checks": True,
            "radius_m": TARGET_RADIUS_M,
            "required_supported_channel_ids_1based": [10, 11, 12, 13, 14, 15, 16],
            "required_dqf_for_supported_channels": 0,
            "alternate_pixel_fallback": False,
            "alternate_slot_fallback": False,
        },
        "private_output_root": str(PRIVATE_ROOT),
        "automatic_retry": False,
        "rttov_H_K_M_optimizer_native_calls": 0,
        "source_file_binding": sources,
    }


def verify_plan(plan_path: Path, plan_sha: str) -> dict:
    require(sha256(plan_path) == plan_sha, "frozen observation plan SHA-256 mismatch")
    plan = json.loads(plan_path.read_text())
    require(plan["status"] == "PREDECLARED_BEFORE_DOWNLOAD",
            "observation plan status is not PREDECLARED_BEFORE_DOWNLOAD")
    require(sha256(Path(plan["producer_path"])) == plan["producer_sha256"],
            "observation preparation producer changed after preflight")
    require(sha256(Path(plan["source_list_path"])) == plan["source_list_sha256"],
            "public S3 listing changed after preflight")
    require(sha256(Path(plan["calibration_path"])) == plan["calibration_sha256"],
            "paired calibration changed after preflight")
    for path, digest in plan["source_file_binding"].items():
        require(sha256(Path(path)) == digest, f"reader/helper source changed: {path}")
    for row in plan["original_0556_sources"]:
        path = Path(row["path"])
        require(path.is_file() and path.stat().st_size == row["size_bytes"]
                and sha256(path) == row["sha256"],
                f"immutable original 0556 input changed: {path}")
    return plan


def preflight() -> dict:
    plan = build_plan()
    write_exclusive(PLAN_PATH, plan)
    return plan


def _write_private_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    write_exclusive(path, value, private=True)


def download_objects(plan: dict, plan_sha: str) -> tuple[Path, list[dict]]:
    if PRIVATE_ROOT.exists():
        raise FileExistsError(f"refusing to overwrite private observation root: {PRIVATE_ROOT}")
    PRIVATE_ROOT.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_ROOT.mkdir(mode=0o700, exist_ok=False)
    os.chmod(PRIVATE_ROOT, 0o700)
    guard_path = PRIVATE_ROOT / "DOWNLOAD_GUARD.json"
    _write_private_json(guard_path, {
        "schema": "pr414_no_retry_download_guard_v1",
        "plan_sha256": plan_sha,
        "max_new_files": MAX_NEW_FILES,
        "planned_new_bytes": plan["download_budget"]["planned_bytes"],
        "automatic_retry": False,
        "request_attempts_per_object": 1,
    })
    run_marker = PACKET / "DOWNLOAD_STARTED_ONCE.json"
    write_exclusive(run_marker, {"plan_sha256": plan_sha,
                                 "new_file_count": MAX_NEW_FILES,
                                 "automatic_retry": False})
    downloaded = []
    progress_path = PRIVATE_ROOT / "DOWNLOAD_PROGRESS.jsonl"
    with progress_path.open("x") as progress:
        os.chmod(progress_path, 0o600)
        try:
            for index, obj in enumerate(plan["new_s3_objects"], start=1):
                if index > MAX_NEW_FILES:
                    raise ValueError("download file budget exceeded")
                slot_dir = PRIVATE_ROOT / "raw" / obj["slot_obt"]
                slot_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                destination = slot_dir / Path(obj["key"]).name
                if destination.exists():
                    raise FileExistsError(f"refusing to overwrite download: {destination}")
                partial = destination.with_name(destination.name + ".partial")
                if partial.exists():
                    raise FileExistsError(f"refusing to overwrite partial download: {partial}")
                url = BUCKET_ROOT + urllib.parse.quote(obj["key"], safe="/")
                digest = hashlib.sha256()
                md5 = hashlib.md5()
                byte_count = 0
                request = urllib.request.Request(url, method="GET")
                # Exactly one urlopen invocation per planned object; no retry loop.
                with urllib.request.urlopen(request, timeout=90) as response:
                    status = int(response.status)
                    response_etag = str(response.headers.get("ETag", "")).strip('"')
                    content_length = response.headers.get("Content-Length")
                    if status != 200:
                        raise ValueError(f"HTTP {status} for {obj['key']}")
                    if response_etag != obj["etag"]:
                        raise ValueError(f"ETag changed for {obj['key']}")
                    if content_length is not None and int(content_length) != obj["size_bytes"]:
                        raise ValueError(f"Content-Length changed for {obj['key']}")
                    with partial.open("xb") as out:
                        os.chmod(partial, 0o600)
                        for chunk in iter(lambda: response.read(1 << 20), b""):
                            byte_count += len(chunk)
                            if byte_count > obj["size_bytes"]:
                                raise ValueError(f"download exceeded listed size: {obj['key']}")
                            out.write(chunk)
                            digest.update(chunk)
                            md5.update(chunk)
                if byte_count != obj["size_bytes"]:
                    raise ValueError(f"download size mismatch for {obj['key']}")
                if re.fullmatch(r"[0-9a-fA-F]{32}", obj["etag"]):
                    if md5.hexdigest().lower() != obj["etag"].lower():
                        raise ValueError(f"single-part ETag/MD5 mismatch for {obj['key']}")
                partial.rename(destination)
                os.chmod(destination, 0o600)
                item = {
                    "index": index,
                    "key": obj["key"],
                    "slot_obt": obj["slot_obt"],
                    "channel": obj["channel"],
                    "path": str(destination.resolve()),
                    "size_bytes": byte_count,
                    "etag": obj["etag"],
                    "sha256": digest.hexdigest(),
                    "local_md5": md5.hexdigest(),
                    "request_attempts": 1,
                    "http_status": status,
                }
                downloaded.append(item)
                progress.write(json.dumps(item, sort_keys=True) + "\n")
                progress.flush()
        except BaseException as exc:
            failure = {
                "schema": "pr414_observation_download_failure_v1",
                "status": "FAILED_NO_AUTOMATIC_RETRY",
                "plan_sha256": plan_sha,
                "completed_files": len(downloaded),
                "failed_object": (plan["new_s3_objects"][len(downloaded)]
                                  if len(downloaded) < len(plan["new_s3_objects"])
                                  else None),
                "exception_type": type(exc).__name__,
                "message": str(exc),
                "automatic_retry": False,
            }
            _write_private_json(PRIVATE_ROOT / "DOWNLOAD_FAILURE.json", failure)
            write_exclusive(PACKET / "DOWNLOAD_FAILURE.json", failure)
            raise
    total_bytes = sum(item["size_bytes"] for item in downloaded)
    if len(downloaded) != MAX_NEW_FILES or total_bytes != plan["download_budget"]["planned_bytes"]:
        raise ValueError("completed download set differs from exact predeclared 18-file budget")
    receipt = {
        "schema": "pr414_observation_download_receipt_v1",
        "status": "ALL_18_PLANNED_OBJECTS_DOWNLOADED",
        "plan_sha256": plan_sha,
        "source_list_sha256": plan["source_list_sha256"],
        "downloaded_files": len(downloaded),
        "downloaded_bytes": total_bytes,
        "automatic_retry": False,
        "request_attempts_total": len(downloaded),
        "files": downloaded,
    }
    receipt_path = PRIVATE_ROOT / "DOWNLOAD_RECEIPT.json"
    _write_private_json(receipt_path, receipt)
    write_exclusive(PACKET / "DOWNLOAD_RECEIPT.json", receipt)
    return receipt_path, downloaded


def _nearest_point(reader, target_lat: float, target_lon: float, helpers):
    lat = reader.payload.lat.detach().cpu().numpy().reshape(-1)
    lon = reader.payload.lon.detach().cpu().numpy().reshape(-1)
    bt = reader.payload.bt.detach().cpu().numpy()
    quality = reader.payload.obs_quality.detach().cpu().numpy()
    rows = np.asarray(reader.pixel_rows)
    cols = np.asarray(reader.pixel_cols)
    if len(rows) != len(lat) or len(cols) != len(lat):
        raise ValueError("reader pixel row/column arrays do not align to decoded geolocation")
    finite = np.isfinite(lat) & np.isfinite(lon)
    indices = np.flatnonzero(finite)
    if not indices.size:
        return None, bt, quality, float("inf")
    distances = helpers.haversine_m(lat[finite], lon[finite],
                                    target_lat=target_lat, target_lon=target_lon)
    best = int(indices[int(np.argmin(distances))])
    distance = float(np.min(distances))
    point = {
        "row": int(rows[best]),
        "column": int(cols[best]),
        "latitude_deg": float(lat[best]),
        "longitude_deg": float(lon[best]),
    }
    return (best, point), bt, quality, distance


def decode_observations(plan: dict, plan_sha: str, downloaded: list[dict],
                        download_receipt_path: Path) -> dict:
    # Confirm the reused original observation source still has exactly its PR411/PR412 bytes.
    original_files = [Path(row["path"]) for row in plan["original_0556_sources"]]
    source_by_slot = {SLOTS[0]: original_files}
    new_rows_by_slot = {slot: [] for slot in SLOTS[1:]}
    for row in downloaded:
        new_rows_by_slot[row["slot_obt"]].append(row)
    for slot in SLOTS[1:]:
        rows = new_rows_by_slot[slot]
        if len(rows) != len(CLEAN_IR_CHANNELS):
            raise ValueError(f"download receipt lacks nine files for {slot}")
        source_by_slot[slot] = [Path(row["path"]) for row in sorted(
            rows, key=lambda item: CLEAN_IR_CHANNELS.index(item["channel"]))]

    source_rows_by_slot = {}
    for slot in SLOTS:
        if slot == SLOTS[0]:
            source_rows_by_slot[slot] = plan["original_0556_sources"]
        else:
            source_rows_by_slot[slot] = sorted(
                new_rows_by_slot[slot],
                key=lambda item: CLEAN_IR_CHANNELS.index(item["channel"]))
        if [Path(row["path"]).name for row in source_rows_by_slot[slot]] != [
                f"gk2a_ami_le1b_{channel}_la020ge_{slot}.nc"
                for channel in CLEAN_IR_CHANNELS]:
            raise ValueError(f"slot {slot} input order does not match CLEAN_IR_CHANNELS")

    helpers = load_module(MASK_HELPER, "pr414_existing_geos_helper")
    table = load_cal_table(CALIBRATION)
    native_ref = plan["native_reference"]
    original_wire = json.loads(ORIGINAL_WIRE.read_text())
    original_scene = original_wire["scenes"][0]
    original_point = original_scene["nearest_pixel"]
    original_receipt = json.loads(Path(original_wire["private_decode_receipt_path"]).read_text())
    expected_reader_geos = original_receipt["scenes"][0]["reader_metadata"]["geos"]
    original_point_expected = {key: original_point[key]
                              for key in ("row", "column", "latitude_deg", "longitude_deg")}
    analysis_pos = [CLEAN_IR_CHANNELS.index(name) for name in CLEAN_IR_CHANNELS[2:]]
    analysis_names = list(CLEAN_IR_CHANNELS[2:])
    analysis_ids = [AMI_CHANNELS.index(name) + 1 for name in analysis_names]
    slot_results = []
    y_bt = []
    y_dqf = []
    private_arrays = {}
    all_source_records = []
    reader_source_hashes = plan["reader_source_sha256"]
    for slot, model_time, step in zip(SLOTS, MODEL_TIMES, STEP_INDICES):
        files = source_by_slot[slot]
        before = {str(path.resolve()): sha256(path) for path in files}
        reader = read_la_slot(files, table, stride=1)
        found, bt, quality, distance = _nearest_point(
            reader, native_ref["latitude_deg"], native_ref["longitude_deg"], helpers)
        if found is None:
            point = None
            channel_bt = None
            channel_dqf = None
            support_dqf0 = False
        else:
            idx, point = found
            # The chosen location is fixed by distance alone. Only after selection
            # do we inspect DQF and BT; an invalid point is retained as a failure.
            channel_bt = [float(bt[idx, j]) for j in range(len(CLEAN_IR_CHANNELS))]
            channel_dqf = [int(quality[idx, j]) for j in range(len(CLEAN_IR_CHANNELS))]
            support_dqf0 = all(channel_dqf[j] == 0 and np.isfinite(channel_bt[j])
                               for j in analysis_pos)
        reader_geos = dict(reader.metadata["geos"])
        if point is None:
            point_matches_original = False
        else:
            point_matches_original = (
                point["row"] == original_point_expected["row"]
                and point["column"] == original_point_expected["column"]
                and point["latitude_deg"] == original_point_expected["latitude_deg"]
                and point["longitude_deg"] == original_point_expected["longitude_deg"])
        geos_matches_original = reader_geos == expected_reader_geos
        within_radius = bool(distance <= TARGET_RADIUS_M)
        if slot == SLOTS[0]:
            if point != original_point_expected:
                raise ValueError("immutable 0556 reader point differs from PR412 actual observation")
            if not geos_matches_original:
                raise ValueError("immutable 0556 reader GEOS differs from PR412 actual observation")
            if channel_bt[2:] != [float(original_point["bt_K_by_channel"][ch])
                                  for ch in CLEAN_IR_CHANNELS[2:]]:
                raise ValueError("immutable 0556 BTs differ from PR412 actual L1B result")
            if channel_dqf[2:] != [int(original_point["reader_dqf_by_channel"][ch])
                                   for ch in CLEAN_IR_CHANNELS[2:]]:
                raise ValueError("immutable 0556 DQFs differ from PR412 actual L1B result")

        source_rows = source_rows_by_slot[slot]
        source_files = []
        for row in source_rows:
            path = Path(row["path"]).resolve()
            digest = sha256(path)
            if digest != before[str(path)]:
                raise ValueError(f"raw source changed during decode: {path}")
            source_record = {
                "key": row["key"],
                "channel": row["channel"],
                "path": str(path),
                "size_bytes": int(row["size_bytes"]),
                "sha256": digest,
                "etag": row.get("etag"),
                "immutable_reused_source": bool(row.get("immutable_reused_source", False)),
            }
            source_files.append(source_record)
            all_source_records.append(source_record)

        if found is not None:
            slot_y = [float(bt[idx, j]) for j in analysis_pos]
            slot_dqf = [int(quality[idx, j]) for j in analysis_pos]
            y_bt.append(slot_y)
            y_dqf.append(slot_dqf)
            private_arrays[f"step_{step}_y_bt_K"] = np.asarray(slot_y, dtype=np.float64)
            private_arrays[f"step_{step}_reader_dqf"] = np.asarray(slot_dqf, dtype=np.int16)
            private_arrays[f"step_{step}_all9_bt_K"] = np.asarray(channel_bt, dtype=np.float64)
            private_arrays[f"step_{step}_all9_reader_dqf"] = np.asarray(channel_dqf, dtype=np.int16)
        slot_result = {
            "step_index": int(step),
            "nominal_slot_obt": slot,
            "nominal_model_time": model_time,
            "scene_date": "2025-07-19",
            "pixel_utc": None,
            "pixel_utc_time_verified": False,
            "time_assumption": TIME_ASSUMPTION,
            "nearest_pixel": point,
            "reader_geos": reader_geos,
            "distance_to_native_column_m": distance,
            "within_2p5km": within_radius,
            "point_matches_original_pr412_observation": point_matches_original,
            "reader_geos_matches_original_pr412_observation": geos_matches_original,
            "analysis_channel_names": analysis_names,
            "analysis_channel_ids": analysis_ids,
            "y_bt_K": slot_y if found is not None else None,
            "reader_dqf": slot_dqf if found is not None else None,
            "all_nine_channel_names": list(CLEAN_IR_CHANNELS),
            "all_nine_bt_K_by_channel": ({ch: channel_bt[j] for j, ch in enumerate(CLEAN_IR_CHANNELS)}
                                          if channel_bt is not None else None),
            "all_nine_reader_dqf_by_channel": ({ch: channel_dqf[j] for j, ch in enumerate(CLEAN_IR_CHANNELS)}
                                                if channel_dqf is not None else None),
            "all_seven_analysis_channels_finite_and_dqf0": bool(support_dqf0),
            "reader_metadata": reader.metadata,
            "source_files": source_files,
            "selection_basis": "nearest finite GEOS pixel to fixed PR412 native j103/i48; distance only before DQF/BT inspection",
        }
        slot_results.append(slot_result)

    # Source snapshot after decoding includes reused originals and new downloads.
    source_after = {row["path"]: row["sha256"] for row in all_source_records}
    if len(source_after) != 27:
        raise ValueError(f"expected 27 bound raw files (nine reused + eighteen downloaded), got {len(source_after)}")
    for source_path, digest in source_after.items():
        if sha256(Path(source_path)) != digest:
            raise ValueError(f"raw observation input changed after decode: {source_path}")

    private_payload = PRIVATE_ROOT / "OBS_WINDOW_VALUES.npz"
    with private_payload.open("xb") as stream:
        os.chmod(private_payload, 0o600)
        np.savez_compressed(stream, **private_arrays)
    payload_hash = sha256(private_payload)
    private_decode_receipt = {
        "schema": "pr414_ami_window_decode_receipt_v1",
        "status": "DECODED_GK2A_L1B_POINTS_ONLY",
        "plan_sha256": plan_sha,
        "download_receipt_path": str(download_receipt_path.resolve()),
        "download_receipt_sha256": sha256(download_receipt_path),
        "private_payload_path": str(private_payload.resolve()),
        "private_payload_sha256": payload_hash,
        "private_payload_mode": "0600",
        "raw_source_count": len(source_after),
        "raw_source_sha256": source_after,
        "slots": [{key: slot[key] for key in (
            "step_index", "nominal_slot_obt", "nominal_model_time", "scene_date",
            "pixel_utc", "pixel_utc_time_verified", "time_assumption",
            "nearest_pixel", "reader_geos", "distance_to_native_column_m",
            "within_2p5km", "point_matches_original_pr412_observation",
            "reader_geos_matches_original_pr412_observation",
            "all_seven_analysis_channels_finite_and_dqf0", "source_files")}
            for slot in slot_results],
        "no_native_forecast_states_for_later_slots_bound": True,
        "native_forcing_sequence_bound": False,
        "native_model_RTTOV_H_K_M_optimizer_calls": 0,
        "no_pixel_time_UTC_inference": True,
    }
    decode_receipt_path = PRIVATE_ROOT / "DECODE_RECEIPT.json"
    _write_private_json(decode_receipt_path, private_decode_receipt)

    all_gate = all(slot["all_seven_analysis_channels_finite_and_dqf0"]
                   and slot["within_2p5km"]
                   and slot["point_matches_original_pr412_observation"]
                   and slot["reader_geos_matches_original_pr412_observation"]
                   for slot in slot_results)
    bound_files = dict(source_after)
    bound_files[str(private_payload.resolve())] = payload_hash
    bound_files[str(download_receipt_path.resolve())] = sha256(download_receipt_path)
    bound_files[str(decode_receipt_path.resolve())] = sha256(decode_receipt_path)
    bound_files[str(ORIGINAL_RESTORE.resolve())] = sha256(ORIGINAL_RESTORE)
    bound_files[str(ORIGINAL_WIRE.resolve())] = sha256(ORIGINAL_WIRE)
    bound_files[str(Path(plan["original_0556_bindings"]["decode_receipt_path"]).resolve())] = \
        plan["original_0556_bindings"]["decode_receipt_sha256"]
    bound_files[str(SOURCE_LIST.resolve())] = plan["source_list_sha256"]
    for path, digest in reader_source_hashes.items():
        bound_files[str(Path(path).resolve())] = digest
    bound_files[str(CALIBRATION.resolve())] = plan["calibration_sha256"]
    bound_files[str(Path(plan["native_reference"]["case_path"]).resolve())] = \
        plan["native_reference"]["case_sha256"]
    download_public_path = PACKET / "DOWNLOAD_RECEIPT.json"
    public_download_receipt = json.loads(download_public_path.read_text())
    observation_output = {
        "schema": "pr414_ami_window_observations_v1",
        "status": "DECODED_L1B_POINTS_ONLY",
        "window_id": plan["window_id"],
        "date": "2025-07-19",
        "time_assumption": TIME_ASSUMPTION,
        "time_assumption_note": plan["time_assumption_note"],
        "background_valid_time": BACKGROUND_TIME,
        "dt_s": DT_S,
        "n_steps": N_STEPS,
        "slot_indices": list(STEP_INDICES),
        "forcing_window_bound": False,
        "native_later_states_bound": False,
        "native_integration_or_cycling_claim": False,
        "target_native_case": plan["native_reference"],
        "analysis_channel_ids": analysis_ids,
        "analysis_channel_names": analysis_names,
        "source_channel_names": list(CLEAN_IR_CHANNELS),
        "source_slot_downloads": {
            "reused_original_0556_files": len(plan["original_0556_sources"]),
            "new_0606_0616_files": len(public_download_receipt["files"]),
            "new_0606_0616_bytes": public_download_receipt["downloaded_bytes"],
            "automatic_retry": False,
        },
        "slots": slot_results,
        "all_slots_pass_support_gate": all_gate,
        "status_detail": ("READY_FOR_DECLARED_WINDOW_ADAPTER_ONLY" if all_gate
                          else "FAIL_CLOSED_SUPPORT_OR_NAVIGATION_GATE"),
        "private_payload": {
            "path": str(private_payload.resolve()),
            "sha256": payload_hash,
            "mode": "0600",
            "array_names": sorted(private_arrays),
        },
        "private_decode_receipt": {
            "path": str(decode_receipt_path.resolve()),
            "sha256": sha256(decode_receipt_path),
            "mode": "0600",
        },
        "private_download_receipt": {
            "path": str(download_receipt_path.resolve()),
            "sha256": sha256(download_receipt_path),
            "mode": "0600",
        },
        "bound_files": dict(sorted(bound_files.items())),
        "limitations": [
            "This preparation decodes observations only; it does not bind the 61-step native forcing sequence or later host states.",
            "Filename OBT labels are used only under the explicit nominal-UTC research assumption; pixel UTC remains null/unverified.",
            "Source DQF0 is L1B source usability, not cloud truth or analysis acceptance.",
            "No alternate time slot or alternate pixel is selected if the fixed spatial/time/support gates fail.",
        ],
    }
    write_exclusive(PACKET / "OBSERVATIONS.json", observation_output)
    return observation_output


def execute(plan_sha: str) -> dict:
    plan = verify_plan(PLAN_PATH, plan_sha)
    download_receipt_path, downloaded = download_objects(plan, plan_sha)
    return decode_observations(plan, plan_sha, downloaded, download_receipt_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preflight", action="store_true")
    group.add_argument("--execute", action="store_true")
    parser.add_argument("--plan-sha256")
    args = parser.parse_args()
    if args.preflight:
        if PLAN_PATH.exists():
            raise FileExistsError(f"refusing to overwrite observation plan: {PLAN_PATH}")
        plan = preflight()
        plan_sha = sha256(PLAN_PATH)
        print(json.dumps({"status": plan["status"], "plan_sha256": plan_sha,
                          "new_downloads": plan["download_budget"]["planned_files"],
                          "new_download_bytes": plan["download_budget"]["planned_bytes"],
                          "source_list_sha256": plan["source_list_sha256"]}, sort_keys=True))
        return 0
    if args.plan_sha256 is None:
        raise ValueError("--execute requires the exact --plan-sha256 printed by --preflight")
    observations = execute(args.plan_sha256)
    print(json.dumps({"status": observations["status"],
                      "status_detail": observations["status_detail"],
                      "slots": [{"step_index": s["step_index"],
                                 "nominal_slot_obt": s["nominal_slot_obt"],
                                 "nearest_pixel": s["nearest_pixel"],
                                 "all_seven_analysis_channels_finite_and_dqf0":
                                     s["all_seven_analysis_channels_finite_and_dqf0"]}
                                for s in observations["slots"]],
                      "native_forcing_bound": observations["forcing_window_bound"]},
                     sort_keys=True))
    return 0 if observations["all_slots_pass_support_gate"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
