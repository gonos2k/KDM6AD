#!/usr/bin/env python3
"""Preflight, download, and decode two fixed GK2A AMI LA020GE L1B scenes."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import sys
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import netCDF4
import numpy as np


ROOT = Path(__file__).resolve().parents[3]
sys_path = str(ROOT / "oracle")
if sys_path not in sys.path:
    sys.path.insert(0, sys_path)

from kdm6.obs.gk2a_l1b import (  # noqa: E402
    AMI_CHANNELS,
    CLEAN_IR_CHANNELS,
    load_cal_table,
    unpack_ami_word,
)
from kdm6.obs.gk2a_l1b_la import read_la_slot  # noqa: E402


PACKET = Path(__file__).resolve().parent
PRIVATE_ROOT = Path(
    "/Users/yhlee/KDM6AD-k/host/research_evidence/pr403_l1b_heldout_20261011"
)
CALIBRATION = ROOT / "oracle/kdm6/obs/data/gk2a_ami_cal_202507190000.json"
BUCKET_ROOT = "https://noaa-gk2a-pds.s3.amazonaws.com/"
DATES = ("20250720", "20250721")
TARGET_LAT = 35.415660858
TARGET_LON = 122.143310547
TARGET_STAMP = "0556"
RADIUS_M = 2500.0
WINDOW_HALF_WIDTH = 2
MAX_FILES = 18
MAX_BYTES = 20 * 1024 * 1024
S3_NS = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}
SLOT_RE = re.compile(
    r"^AMI/L1B/LA/202507/(20|21)/(05|06)/gk2a_ami_le1b_"
    r"([a-z0-9]+)_la020ge_(202507\d{6})\.nc$"
)
SOURCE_FILES = (
    "oracle/kdm6/obs/gk2a_l1b_la.py",
    "oracle/kdm6/obs/gk2a_l1b.py",
    "oracle/kdm6/obs/gk2a_l1b_fd.py",
    "oracle/kdm6/obs/obs_ingest.py",
)
CHANNEL_ID = {name: AMI_CHANNELS.index(name) + 1 for name in CLEAN_IR_CHANNELS}
EARTH_RADIUS_M = 6371008.77


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _s3_listing(day: str, hour: str, save_path: Path) -> tuple[dict, str]:
    prefix = f"AMI/L1B/LA/202507/{day[-2:]}/{hour}/"
    query = urllib.parse.urlencode({"list-type": "2", "prefix": prefix})
    url = f"{BUCKET_ROOT}?{query}"
    if save_path.exists():
        # A prior preflight may have saved the immutable public listing before
        # failing in local parsing. Reuse those exact bytes; never overwrite.
        body = save_path.read_bytes()
        status = 200
        listing_origin = "REUSED_SAVED_PUBLIC_LISTING"
    else:
        with urllib.request.urlopen(url, timeout=60) as response:
            body = response.read()
            status = response.status
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with save_path.open("xb") as stream:
            stream.write(body)
        os.chmod(save_path, 0o600)
        listing_origin = "FETCHED_PUBLIC_LISTING"
    root = ET.fromstring(body)
    require(status == 200, f"S3 listing failed: HTTP {status} for {prefix}")
    require(root.findtext("s:Prefix", namespaces=S3_NS) == prefix,
            f"saved S3 listing prefix does not match {prefix}")
    require(root.findtext("s:IsTruncated", namespaces=S3_NS) == "false",
            f"S3 listing is truncated: {prefix}")
    rows = []
    for item in root.findall("s:Contents", S3_NS):
        key = item.findtext("s:Key", namespaces=S3_NS)
        match = SLOT_RE.fullmatch(key or "")
        if not match:
            continue
        _, _, channel, stamp = match.groups()
        rows.append({
            "key": key,
            "channel": channel,
            "stamp": stamp,
            "size_bytes": int(item.findtext("s:Size", namespaces=S3_NS)),
            "etag": item.findtext("s:ETag", namespaces=S3_NS).strip('"'),
            "last_modified_utc": item.findtext("s:LastModified", namespaces=S3_NS),
        })
    return {"url": url, "prefix": prefix, "objects": rows,
            "listing_origin": listing_origin}, sha256(save_path)


def choose_slot(rows_by_slot: dict[str, dict[str, dict]], date: str,
                target_stamp: str = TARGET_STAMP) -> dict:
    """Select solely by completeness and nominal filename timestamp."""
    expected = set(CLEAN_IR_CHANNELS)
    exact = rows_by_slot.get(date + target_stamp, {})
    missing_exact = sorted(expected - set(exact))
    if not missing_exact:
        return {"selected_slot": date + target_stamp, "rule": "EXACT_SLOT_COMPLETE",
                "exact_slot_missing_channels": [], "candidate_slots": sorted(rows_by_slot)}

    target = datetime.strptime(date + target_stamp, "%Y%m%d%H%M")
    complete = []
    for stamp, by_channel in rows_by_slot.items():
        if stamp[:8] != date or not expected.issubset(by_channel):
            continue
        slot = datetime.strptime(stamp, "%Y%m%d%H%M")
        offset_seconds = (slot - target).total_seconds()
        if abs(offset_seconds) <= 600:
            complete.append((abs(offset_seconds), slot, stamp))
    if not complete:
        return {"selected_slot": None, "rule": "MISSING_SCENE_NO_COMPLETE_SLOT_WITHIN_10_MIN",
                "exact_slot_missing_channels": missing_exact,
                "candidate_slots": sorted(rows_by_slot)}
    _, _, selected = min(complete, key=lambda row: (row[0], row[1]))
    return {"selected_slot": selected, "rule": "NEAREST_COMPLETE_NOMINAL_SLOT_TIMESTAMP_ONLY",
            "exact_slot_missing_channels": missing_exact,
            "candidate_slots": sorted(rows_by_slot)}


def preflight(plan_id: str | None = None) -> dict:
    table_hash = sha256(CALIBRATION)
    table = load_cal_table(CALIBRATION)
    require(set(table.get("channels", {})).issuperset(CLEAN_IR_CHANNELS),
            "paired AMI calibration table lacks a required thermal channel")
    sources = {name: sha256(ROOT / name) for name in SOURCE_FILES}
    scenes = []
    manifest_root = PACKET / "source_listings"
    for date in DATES:
        rows_by_slot: dict[str, dict[str, dict]] = {}
        metadata_by_slot: dict[str, dict[str, dict]] = {}
        listing_receipts = []
        for hour in ("05", "06"):
            listing_path = manifest_root / f"{date}_{hour}.xml"
            listing, listing_hash = _s3_listing(date, hour, listing_path)
            listing_receipts.append({"hour": hour, "path": str(listing_path.relative_to(ROOT)),
                                     "sha256": listing_hash, "url": listing["url"],
                                     "listing_origin": listing["listing_origin"],
                                     "object_count": len(listing["objects"])})
            for row in listing["objects"]:
                stamp = row["stamp"]
                rows_by_slot.setdefault(stamp, {})[row["channel"]] = row
                metadata_by_slot.setdefault(stamp, {})[row["channel"]] = row
        choice = choose_slot(rows_by_slot, date)
        selected = choice["selected_slot"]
        chosen_rows = (metadata_by_slot[selected] if selected else {})
        source_objects = [chosen_rows[ch] for ch in CLEAN_IR_CHANNELS] if selected else []
        scenes.append({
            "date": date,
            "nominal_slot_obt": date + TARGET_STAMP,
            "selection": choice,
            "listed_hour_prefixes": listing_receipts,
            "selected_objects": source_objects,
            "selected_file_count": len(source_objects),
            "selected_total_bytes": sum(row["size_bytes"] for row in source_objects),
        })
    total_files = sum(scene["selected_file_count"] for scene in scenes)
    total_bytes = sum(scene["selected_total_bytes"] for scene in scenes)
    require(total_files <= MAX_FILES, f"file budget exceeded: {total_files} > {MAX_FILES}")
    require(total_bytes <= MAX_BYTES, f"byte budget exceeded: {total_bytes} > {MAX_BYTES}")
    plan_id = plan_id or f"pr403_l1b_{uuid.uuid4().hex[:12]}"
    require(re.fullmatch(r"[A-Za-z0-9_-]{8,40}", plan_id) is not None,
            "plan_id must contain 8-40 safe characters")
    helper_path = Path(__file__).resolve()
    plan = {
        "schema": "pr403_gk2a_l1b_heldout_preflight_v1",
        "status": "PREDECLARED_BEFORE_DOWNLOAD",
        "plan_id": plan_id,
        "selection_contract": {
            "target_latitude_deg": TARGET_LAT,
            "target_longitude_deg": TARGET_LON,
            "fixed_native_point": True,
            "nominal_slot_obt_hhmm": TARGET_STAMP,
            "exact_slot_first": True,
            "fallback": "Only if exact slot does not have all nine channels: nearest complete 9-channel nominal filename slot within ±10 minutes; tie earlier; selection uses timestamps and completeness only.",
            "timestamp_basis": "Filename nominal OBT label only; no UTC mapping inferred.",
            "analysis_radius_km": RADIUS_M / 1000.0,
            "point_or_window_selection": "Geographic nearest pixel only; no DQF, BT, residual, or apparent quality criteria select row/column.",
            "window": "5×5 original raster cells centered on geometric nearest pixel only when nearest distance <=2.5 km; no target shifting.",
            "supported_channels": list(CLEAN_IR_CHANNELS),
            "supported_channel_ids_1based": [CHANNEL_ID[ch] for ch in CLEAN_IR_CHANNELS],
            "analysis_channels": CLEAN_IR_CHANNELS[2:],
            "dqf_contract": "Existing production LA reader; DQF 0 counts as source-usable L1B only, never cloud/clear-sky classification.",
            "scene_independence": "Dates are separate scenes, not independent meteorological events by declaration.",
        },
        "download_budget": {"max_files": MAX_FILES, "selected_files": total_files,
                            "max_bytes": MAX_BYTES, "selected_bytes": total_bytes},
        "source": {
            "bucket": "noaa-gk2a-pds",
            "anonymous_https": True,
            "object_root": "AMI/L1B/LA/202507/{20,21}/{05,06}/",
            "objects_bound_by": "S3 key, size, last modified, and ETag from public listing before download; local SHA-256 recorded after download.",
            "source_listings": [receipt for scene in scenes for receipt in scene["listed_hour_prefixes"]],
        },
        "calibration": {"path": str(CALIBRATION), "sha256": table_hash,
                        "channel_names": list(CLEAN_IR_CHANNELS)},
        "production_sources": sources,
        "preflight_helper": {"path": str(helper_path), "sha256": sha256(helper_path)},
        "scenes": scenes,
        "execution_scope": {
            "preflight_observation_downloads": 0,
            "max_downloads": MAX_FILES,
            "rttov_H_K_M_model_optimizer_calls": 0,
            "external_model_or_reanalysis": 0,
        },
    }
    plan_path = PACKET / "PREDECLARED_PLAN.json"
    if plan_path.exists():
        raise FileExistsError(f"refusing to overwrite preflight plan: {plan_path}")
    with plan_path.open("x") as stream:
        json.dump(plan, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": plan["status"], "plan_id": plan_id,
                      "plan_path": str(plan_path), "plan_sha256": sha256(plan_path),
                      "selected_files": total_files, "selected_bytes": total_bytes,
                      "scenes": [{"date": s["date"], "status": s["selection"]["rule"],
                                  "slot": s["selection"]["selected_slot"]} for s in scenes]},
                     sort_keys=True))
    return plan


def _verify_frozen_sources(plan: dict) -> None:
    require(plan["preflight_helper"]["sha256"] == sha256(Path(__file__).resolve()),
            "preflight helper changed after source pin")
    require(plan["calibration"]["sha256"] == sha256(CALIBRATION),
            "calibration table changed after source pin")
    for name, digest in plan["production_sources"].items():
        require(sha256(ROOT / name) == digest, f"production reader source changed: {name}")
    for receipt in plan["source"]["source_listings"]:
        path = ROOT / receipt["path"]
        require(sha256(path) == receipt["sha256"], f"source listing changed: {path}")


def download(plan_path: Path, plan_sha: str) -> Path:
    require(sha256(plan_path) == plan_sha, "frozen plan SHA-256 mismatch")
    plan = json.loads(plan_path.read_text())
    require(plan["status"] == "PREDECLARED_BEFORE_DOWNLOAD", "unexpected plan status")
    _verify_frozen_sources(plan)
    private_root = PRIVATE_ROOT / plan["plan_id"]
    private_root.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(private_root.parent, 0o700)
    private_root.mkdir(mode=0o700, exist_ok=False)
    os.chmod(private_root, 0o700)
    guard = private_root / "DOWNLOAD_GUARD.json"
    with guard.open("x") as stream:
        json.dump({"plan_sha256": plan_sha, "automatic_retry": False,
                   "max_downloads": plan["download_budget"]["max_files"]}, stream)
    os.chmod(guard, 0o600)
    progress_path = private_root / "DOWNLOAD_PROGRESS.jsonl"
    progress = progress_path.open("x")
    os.chmod(progress_path, 0o600)
    failures = []
    count = 0
    try:
        for scene in plan["scenes"]:
            slot = scene["selection"]["selected_slot"]
            if slot is None:
                continue
            date_dir = private_root / scene["date"]
            date_dir.mkdir(mode=0o700)
            for obj in scene["selected_objects"]:
                count += 1
                require(count <= MAX_FILES, "download file budget exceeded")
                dest = date_dir / Path(obj["key"]).name
                require(not dest.exists(), f"refusing to overwrite {dest}")
                partial = dest.with_suffix(dest.suffix + ".partial")
                url = BUCKET_ROOT + urllib.parse.quote(obj["key"], safe="/")
                digest = hashlib.sha256()
                md5 = hashlib.md5()
                byte_count = 0
                try:
                    request = urllib.request.Request(url, method="GET")
                    with urllib.request.urlopen(request, timeout=90) as response:
                        require(response.status == 200, f"HTTP {response.status} for {obj['key']}")
                        response_etag = response.headers.get("ETag", "").strip('"')
                        response_length = response.headers.get("Content-Length")
                        require(response_etag == obj["etag"], f"S3 ETag changed: {obj['key']}")
                        require(response_length is None or int(response_length) == obj["size_bytes"],
                                f"S3 content length changed: {obj['key']}")
                        with partial.open("xb") as out:
                            os.chmod(partial, 0o600)
                            for chunk in iter(lambda: response.read(1 << 20), b""):
                                out.write(chunk)
                                digest.update(chunk)
                                md5.update(chunk)
                                byte_count += len(chunk)
                    require(byte_count == obj["size_bytes"], f"download length mismatch: {obj['key']}")
                    etag = obj["etag"]
                    if re.fullmatch(r"[0-9a-fA-F]{32}", etag):
                        require(md5.hexdigest().lower() == etag.lower(),
                                f"single-part ETag MD5 mismatch: {obj['key']}")
                    require(not dest.exists(), f"refusing to overwrite {dest}")
                    partial.rename(dest)
                    os.chmod(dest, 0o600)
                    record = {"status": "DOWNLOADED", "key": obj["key"],
                              "path": str(dest), "size_bytes": byte_count,
                              "etag": etag, "sha256": digest.hexdigest(),
                              "local_md5": md5.hexdigest()}
                    progress.write(json.dumps(record, sort_keys=True) + "\n")
                    progress.flush()
                except BaseException as exc:
                    failures.append({"key": obj["key"], "partial_path": str(partial),
                                     "bytes_written": byte_count,
                                     "exception_type": type(exc).__name__, "message": str(exc)})
                    raise
        receipt = {"status": "ALL_PLANNED_FILES_DOWNLOADED", "plan_sha256": plan_sha,
                   "automatic_retry": False, "downloaded_files": count,
                   "downloaded_bytes": sum(o["size_bytes"] for s in plan["scenes"]
                                            for o in s["selected_objects"]),
                   "progress_path": str(progress_path)}
        path = private_root / "DOWNLOAD_RECEIPT.json"
        with path.open("x") as stream:
            json.dump(receipt, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.chmod(path, 0o600)
        return private_root
    except BaseException as exc:
        failure = {"status": "FAILED_NO_AUTOMATIC_RETRY", "plan_sha256": plan_sha,
                   "downloads_completed": count - len(failures),
                   "failures": failures,
                   "exception_type": type(exc).__name__, "message": str(exc)}
        failure_path = private_root / "DOWNLOAD_FAILURE.json"
        with failure_path.open("x") as stream:
            json.dump(failure, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.chmod(failure_path, 0o600)
        raise
    finally:
        progress.close()


def _plain(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _headers(files: list[Path]) -> dict:
    output = {}
    for path in files:
        with netCDF4.Dataset(str(path)) as ds:
            var = ds.variables["image_pixel_values"]
            var.set_auto_maskandscale(False)
            output[path.name] = {
                "global_attributes_raw": {name: _plain(ds.getncattr(name)) for name in ds.ncattrs()},
                "image_pixel_values_attributes_raw": {
                    name: _plain(var.getncattr(name)) for name in var.ncattrs()},
                "dimensions": {name: len(dim) for name, dim in ds.dimensions.items()},
                "dtype": str(var.dtype),
            }
    return output


def haversine_m(lat: np.ndarray, lon: np.ndarray,
                target_lat: float = TARGET_LAT, target_lon: float = TARGET_LON) -> np.ndarray:
    lat1 = np.deg2rad(np.asarray(lat, dtype=np.float64))
    lon1 = np.deg2rad(np.asarray(lon, dtype=np.float64))
    lat0, lon0 = np.deg2rad([target_lat, target_lon])
    dlat, dlon = lat1 - lat0, lon1 - lon0
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat0) * np.cos(lat1) * np.sin(dlon / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def nearest_geolocated(lat: np.ndarray, lon: np.ndarray) -> tuple[int | None, np.ndarray, float]:
    lat = np.asarray(lat, dtype=np.float64).reshape(-1)
    lon = np.asarray(lon, dtype=np.float64).reshape(-1)
    require(lat.shape == lon.shape, "latitude/longitude arrays must have matching shapes")
    finite = np.isfinite(lat) & np.isfinite(lon)
    if not finite.any():
        return None, finite, math.inf
    distance = haversine_m(lat[finite], lon[finite])
    finite_indices = np.flatnonzero(finite)
    j = int(np.argmin(distance))
    return int(finite_indices[j]), finite, float(distance[j])


def decode(plan_path: Path, plan_sha: str, private_case: Path) -> None:
    require(sha256(plan_path) == plan_sha, "frozen plan SHA-256 mismatch")
    plan = json.loads(plan_path.read_text())
    _verify_frozen_sources(plan)
    receipt_path = private_case / "DOWNLOAD_RECEIPT.json"
    require(receipt_path.is_file(), "download receipt absent")
    receipt = json.loads(receipt_path.read_text())
    require(receipt["plan_sha256"] == plan_sha, "download receipt belongs to another plan")
    table = load_cal_table(CALIBRATION)
    scenes_result = []
    all_point_rows = []
    all_patch_rows = []
    private_arrays = {}
    for scene in plan["scenes"]:
        slot = scene["selection"]["selected_slot"]
        if slot is None:
            scenes_result.append({"date": scene["date"], "status": "MISSING_SCENE",
                                  "selection": scene["selection"]})
            continue
        files = [private_case / scene["date"] / Path(row["key"]).name
                 for row in scene["selected_objects"]]
        source_before = {path.name: sha256(path) for path in files}
        read = read_la_slot(files, table, stride=1)
        payload = read.payload
        lat = payload.lat.detach().cpu().numpy()
        lon = payload.lon.detach().cpu().numpy()
        bt = payload.bt.detach().cpu().numpy()
        quality = payload.obs_quality.detach().cpu().numpy()
        rows, cols = read.pixel_rows, read.pixel_cols
        index_by_rc = {(int(r), int(c)): i for i, (r, c) in enumerate(zip(rows, cols))}
        nearest_idx, finite_geo, nearest_distance = nearest_geolocated(lat, lon)
        status = "POINT_OFFSCENE"
        center_rc = None
        patch_coords = []
        if nearest_idx is not None and nearest_distance <= RADIUS_M:
            status = "POINT_WITHIN_RADIUS"
            center_rc = [int(rows[nearest_idx]), int(cols[nearest_idx])]
            for r in range(max(0, center_rc[0] - WINDOW_HALF_WIDTH),
                           min(500, center_rc[0] + WINDOW_HALF_WIDTH + 1)):
                for c in range(max(0, center_rc[1] - WINDOW_HALF_WIDTH),
                               min(500, center_rc[1] + WINDOW_HALF_WIDTH + 1)):
                    idx = index_by_rc.get((r, c))
                    if idx is not None:
                        patch_coords.append((r, c, idx))
        channel_quality_counts = {}
        for j, channel in enumerate(CLEAN_IR_CHANNELS):
            q = quality[:, j]
            counts = {str(int(value)): int(np.count_nonzero(q == value))
                      for value in np.unique(q)}
            channel_quality_counts[channel] = {
                "ami_channel_id_1based": CHANNEL_ID[channel],
                "all_finite_geometry_pixels": int(q.size),
                "reader_dqf_counts": counts,
                "dqf0_support": int(np.count_nonzero(q == 0)),
            }
        source_headers = _headers(files)
        point_record = None
        if nearest_idx is not None:
            point_record = {
                "row": int(rows[nearest_idx]), "column": int(cols[nearest_idx]),
                "latitude_deg": float(lat[nearest_idx]),
                "longitude_deg": float(lon[nearest_idx]),
                "distance_to_fixed_point_m": nearest_distance,
                "bt_K_by_channel": {ch: float(bt[nearest_idx, j])
                                    for j, ch in enumerate(CLEAN_IR_CHANNELS)},
                "reader_dqf_by_channel": {ch: int(quality[nearest_idx, j])
                                          for j, ch in enumerate(CLEAN_IR_CHANNELS)},
            }
            for j, channel in enumerate(CLEAN_IR_CHANNELS):
                all_point_rows.append({"date": scene["date"], "nominal_slot_obt": slot,
                                       "row": point_record["row"], "column": point_record["column"],
                                       "latitude_deg": point_record["latitude_deg"],
                                       "longitude_deg": point_record["longitude_deg"],
                                       "distance_to_fixed_point_m": nearest_distance,
                                       "channel": channel, "ami_channel_id_1based": CHANNEL_ID[channel],
                                       "bt_K": float(bt[nearest_idx, j]),
                                       "reader_dqf": int(quality[nearest_idx, j]),
                                       "dqf0_source_usable": bool(quality[nearest_idx, j] == 0),
                                       "selection_basis": "nearest_geolocation_only"})
        point_raw_words = np.full((5, 5, len(CLEAN_IR_CHANNELS)), 0, dtype=np.uint16)
        point_fill_mask = np.ones_like(point_raw_words, dtype=bool)
        raw_dqf = np.full_like(point_raw_words, 255, dtype=np.uint8)
        dn_words = np.full(point_raw_words.shape, np.nan, dtype=np.float64)
        patch_lat = np.full((5, 5), np.nan, dtype=np.float64)
        patch_lon = np.full((5, 5), np.nan, dtype=np.float64)
        patch_bt = np.full(point_raw_words.shape, np.nan, dtype=np.float64)
        patch_dqf = np.full(point_raw_words.shape, -1, dtype=np.int16)
        patch_distance = np.full((5, 5), np.nan, dtype=np.float64)
        if center_rc is not None:
            r0, c0 = center_rc
            for j, (channel, path) in enumerate(zip(CLEAN_IR_CHANNELS, files)):
                with netCDF4.Dataset(str(path)) as ds:
                    var = ds.variables["image_pixel_values"]
                    var.set_auto_maskandscale(False)
                    values_ma = var[max(0, r0-2):min(500, r0+3),
                                    max(0, c0-2):min(500, c0+3)]
                    valid_bits = int(var.getncattr("number_of_valid_bits_per_pixel"))
                    mask = np.ma.getmaskarray(values_ma)
                    values = np.asarray(np.ma.filled(values_ma, 0), dtype=np.uint16)
                # Position the edge-clipped window into a fixed 5×5 storage canvas.
                row_start, col_start = max(0, r0-2), max(0, c0-2)
                canvas_r, canvas_c = row_start - (r0-2), col_start - (c0-2)
                h, w = values.shape
                point_raw_words[canvas_r:canvas_r+h, canvas_c:canvas_c+w, j] = values
                point_fill_mask[canvas_r:canvas_r+h, canvas_c:canvas_c+w, j] = mask
                clean_values = np.ma.filled(values_ma, 0).astype(np.uint16)
                dn, qraw = unpack_ami_word(clean_values, valid_bits)
                raw_dqf[canvas_r:canvas_r+h, canvas_c:canvas_c+w, j] = qraw.astype(np.uint8)
                dn_words[canvas_r:canvas_r+h, canvas_c:canvas_c+w, j] = dn
            for r, c, idx in patch_coords:
                rr, cc = r - (r0-2), c - (c0-2)
                patch_lat[rr, cc], patch_lon[rr, cc] = lat[idx], lon[idx]
                patch_bt[rr, cc, :] = bt[idx, :]
                patch_dqf[rr, cc, :] = quality[idx, :].astype(np.int16)
                patch_distance[rr, cc] = float(haversine_m(np.array([lat[idx]]),
                                                            np.array([lon[idx]]))[0])
                for j, channel in enumerate(CLEAN_IR_CHANNELS):
                    all_patch_rows.append({"date": scene["date"], "nominal_slot_obt": slot,
                                           "center_row": r0, "center_column": c0,
                                           "row": r, "column": c,
                                           "latitude_deg": float(lat[idx]),
                                           "longitude_deg": float(lon[idx]),
                                           "distance_to_fixed_point_m": patch_distance[rr, cc],
                                           "channel": channel,
                                           "ami_channel_id_1based": CHANNEL_ID[channel],
                                           "raw_word_uint16": int(point_raw_words[rr, cc, j]),
                                           "dn": float(dn_words[rr, cc, j]),
                                           "embedded_dqf": int(raw_dqf[rr, cc, j]),
                                           "bt_K": float(bt[idx, j]),
                                           "reader_dqf": int(quality[idx, j]),
                                           "dqf0_source_usable": bool(quality[idx, j] == 0),
                                           "selection_basis": "fixed_5x5_location_window_no_QA_filter"})
        private_arrays[scene["date"] + "_raw_words"] = point_raw_words
        private_arrays[scene["date"] + "_raw_fill_mask"] = point_fill_mask
        private_arrays[scene["date"] + "_raw_dn"] = dn_words
        private_arrays[scene["date"] + "_raw_embedded_dqf"] = raw_dqf
        private_arrays[scene["date"] + "_patch_latitude_deg"] = patch_lat
        private_arrays[scene["date"] + "_patch_longitude_deg"] = patch_lon
        private_arrays[scene["date"] + "_patch_bt_K"] = patch_bt
        private_arrays[scene["date"] + "_patch_reader_dqf"] = patch_dqf
        private_arrays[scene["date"] + "_patch_distance_m"] = patch_distance
        require(source_before == {path.name: sha256(path) for path in files},
                "downloaded source bytes changed during decode")
        scenes_result.append({
            "date": scene["date"], "status": status,
            "selected_nominal_slot_obt": slot,
            "reader_metadata": read.metadata,
            "target_point": {"latitude_deg": TARGET_LAT, "longitude_deg": TARGET_LON},
            "nearest_pixel": point_record,
            "nearest_pixel_within_2p5km": bool(nearest_idx is not None and nearest_distance <= RADIUS_M),
            "fixed_window_rows_cols": center_rc,
            "fixed_window_geolocated_cells": len(patch_coords),
            "whole_scene_quality_counts": channel_quality_counts,
            "source_hashes_sha256_after_decode": source_before,
            "raw_headers": source_headers,
            "time_interpretation": "Filename label and scene acquisition are OBT; mission_reference_time is planned UTC; payload valid_time_utc remains unset.",
            "scientific_limits": [
                "L1B DQF is source data-quality metadata, not cloud or clear-sky classification.",
                "BT is a GK2A L1B brightness temperature; it is not a retrieved SST or independent cloud-phase label.",
                "Window values and DQF counts are descriptive; no averaging, fit, residual selection, or observation-error R estimate is performed.",
            ],
        })
    npz_path = private_case / "FIXED_POINT_PATCH.npz"
    with npz_path.open("xb") as stream:
        os.chmod(npz_path, 0o600)
        np.savez_compressed(stream, **private_arrays)
    npz_hash = sha256(npz_path)
    private_receipt = {"plan_sha256": plan_sha, "scenes": scenes_result,
                       "private_npz_path": str(npz_path), "private_npz_sha256": npz_hash,
                       "private_npz_mode": "0600", "private_directory_mode": "0700"}
    private_result = private_case / "DECODE_RECEIPT.json"
    with private_result.open("x") as stream:
        json.dump(private_receipt, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    os.chmod(private_result, 0o600)
    public = {
        "schema": "pr403_gk2a_l1b_heldout_result_v1",
        "status": "DECODED_GK2A_L1B_SCENES_ONLY",
        "plan_path": str(plan_path.relative_to(ROOT)),
        "plan_sha256": plan_sha,
        "download_receipt_path_private": str(private_case / "DOWNLOAD_RECEIPT.json"),
        "private_decode_receipt_path": str(private_result),
        "private_payload_path": str(npz_path),
        "private_payload_sha256": npz_hash,
        "scenes": [{k: v for k, v in scene.items()
                    if k not in ("reader_metadata", "raw_headers", "source_hashes_sha256_after_decode")}
                   for scene in scenes_result],
        "point_csv": str(PACKET / "POINT_SAMPLES.csv"),
        "patch_csv": str(PACKET / "FIXED_PATCH_SAMPLES.csv"),
        "interpretation": "Two GK2A AMI L1B scenes at distinct dates; not independent meteorological events, not SST/cloud-phase truth, and not newly validated native-model/RTTOV observations.",
    }
    result_path = PACKET / "RESULT.json"
    if result_path.exists():
        raise FileExistsError(f"refusing to overwrite {result_path}")
    with result_path.open("x") as stream:
        json.dump(public, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    for path, rows_out in ((PACKET / "POINT_SAMPLES.csv", all_point_rows),
                           (PACKET / "FIXED_PATCH_SAMPLES.csv", all_patch_rows)):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite {path}")
        fields = list(rows_out[0]) if rows_out else ["date", "status"]
        with path.open("x", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows_out)
    return public


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preflight", action="store_true")
    group.add_argument("--download", action="store_true")
    group.add_argument("--decode", action="store_true")
    parser.add_argument("--plan-id")
    parser.add_argument("--plan-sha256")
    parser.add_argument("--plan", type=Path, default=PACKET / "PREDECLARED_PLAN.json")
    parser.add_argument("--private-case", type=Path)
    args = parser.parse_args()
    if args.preflight:
        preflight(args.plan_id)
    elif args.download:
        if not args.plan_sha256:
            parser.error("--download requires --plan-sha256 for the frozen plan")
        private_case = download(args.plan, args.plan_sha256)
        print(json.dumps({"status": "DOWNLOADED", "private_case": str(private_case)}, sort_keys=True))
    else:
        if not args.plan_sha256 or not args.private_case:
            parser.error("--decode requires --plan-sha256 and --private-case")
        result = decode(args.plan, args.plan_sha256, args.private_case)
        print(json.dumps({"status": result["status"], "result": str(PACKET / "RESULT.json")}, sort_keys=True))


if __name__ == "__main__":
    main()
