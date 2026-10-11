"""Synthetic writer integration; no network or production LA scene decode."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import netCDF4
import numpy as np
import pytest
import torch

SCRIPT = Path(__file__).with_name("heldout_l1b_v3.py")
spec = importlib.util.spec_from_file_location("heldout_v3_publication", SCRIPT)
writer = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(writer)


def setup_case(tmp_path, monkeypatch, *, selected=False):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    packet = tmp_path / "public"
    packet.mkdir()
    monkeypatch.setattr(writer, "PACKET", packet)
    monkeypatch.setattr(writer, "ROOT", tmp_path / "repo")
    objects, progress = [], []
    if selected:
        date_dir = private / "20250720"
        date_dir.mkdir()
        for ch in writer.CLEAN_IR_CHANNELS:
            file = date_dir / f"gk2a_ami_le1b_{ch}_la020ge_202507200556.nc"
            with netCDF4.Dataset(file, "w") as ds:
                ds.createDimension("y", 5)
                ds.createDimension("x", 5)
                var = ds.createVariable("image_pixel_values", "u2", ("y", "x"))
                var.setncattr("number_of_valid_bits_per_pixel", 13)
                var[:] = np.zeros((5, 5), dtype=np.uint16)
            data = file.read_bytes()
            etag = hashlib.md5(data).hexdigest()
            key = "synthetic/" + file.name
            objects.append({"key": key, "etag": etag, "size_bytes": len(data)})
            progress.append({"status": "DOWNLOADED", "key": key, "path": str(file),
                             "size_bytes": len(data), "etag": etag,
                             "sha256": writer.sha256(file)})
    plan = {
        "status": "PREDECLARED_BEFORE_DOWNLOAD",
        "preflight_helper": {"sha256": writer.sha256(SCRIPT)},
        "calibration": {"sha256": writer.sha256(writer.CALIBRATION)},
        "production_sources": {}, "source": {"source_listings": []},
        "scenes": [{"date": "20250720", "selection": {"selected_slot": "202507200556" if selected else None},
                    "selected_objects": objects}],
    }
    plan_path = tmp_path / "external-plan.json"
    plan_path.write_text(json.dumps(plan))
    digest = writer.sha256(plan_path)
    progress_path = private / "DOWNLOAD_PROGRESS.jsonl"
    progress_path.write_text("".join(json.dumps(r) + "\n" for r in progress))
    receipt = {"plan_sha256": digest, "status": "ALL_PLANNED_FILES_DOWNLOADED",
               "downloaded_files": len(objects), "downloaded_bytes": sum(r["size_bytes"] for r in objects),
               "progress_path": str(progress_path)}
    (private / "DOWNLOAD_RECEIPT.json").write_text(json.dumps(receipt))
    return plan_path, digest, private, packet


@pytest.mark.parametrize("field,value,message", [
    ("status", "FAILED_NO_AUTOMATIC_RETRY", "did not complete"),
    ("downloaded_files", 99, "file count"),
    ("downloaded_bytes", 99, "byte count"),
])
def test_invalid_receipt_refused_before_outputs(tmp_path, monkeypatch, field, value, message):
    plan, digest, private, packet = setup_case(tmp_path, monkeypatch)
    path = private / "DOWNLOAD_RECEIPT.json"
    receipt = json.loads(path.read_text())
    receipt[field] = value
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match=message):
        writer.decode(plan, digest, private)
    assert not (private / "FIXED_POINT_PATCH.npz").exists()
    assert not (packet / "RESULT.json").exists()


def test_existing_csv_refused_before_private_or_public_outputs(tmp_path, monkeypatch):
    plan, digest, private, packet = setup_case(tmp_path, monkeypatch)
    csv_path = packet / "POINT_SAMPLES.csv"
    csv_path.write_text("preserved-old-value\n")
    monkeypatch.setattr(writer, "validate_download_receipt",
                        lambda *args: pytest.fail("source intake must not run for conflicting outputs"))
    with pytest.raises(FileExistsError, match="POINT_SAMPLES"):
        writer.decode(plan, digest, private)
    assert csv_path.read_text() == "preserved-old-value\n"
    assert not (private / "FIXED_POINT_PATCH.npz").exists()
    assert not (packet / "RESULT.json").exists()


def test_csv_write_failure_leaves_no_success_marker(tmp_path, monkeypatch):
    plan, digest, private, packet = setup_case(tmp_path, monkeypatch)

    def fail_rows(*args, **kwargs):
        raise OSError("injected CSV write failure")

    monkeypatch.setattr(writer.csv.DictWriter, "writerows", fail_rows)
    with pytest.raises(OSError, match="injected CSV"):
        writer.decode(plan, digest, private)
    assert (private / "FIXED_POINT_PATCH.npz").exists()
    assert (packet / "POINT_SAMPLES.csv").exists()  # Preserve partial artifacts; no retry.
    assert not (packet / "RESULT.json").exists()


def test_missing_scenes_keep_normal_csv_headers_and_explicit_status(tmp_path, monkeypatch):
    plan, digest, private, packet = setup_case(tmp_path, monkeypatch)
    result = writer.decode(plan, digest, private)
    assert result["status"] == "NO_SCENES_AVAILABLE"
    assert result["decoded_scene_count"] == 0
    assert result["interpretation"].startswith("0 decoded")
    assert result["plan_path"] == str(plan.resolve())
    for file, fields in [("POINT_SAMPLES.csv", writer.POINT_FIELDS),
                         ("FIXED_PATCH_SAMPLES.csv", writer.PATCH_FIELDS)]:
        with (packet / file).open() as stream:
            rows = list(csv.reader(stream))
        assert rows == [list(fields)]


def test_progress_hash_mismatch_stops_before_reader(tmp_path, monkeypatch):
    plan, digest, private, packet = setup_case(tmp_path, monkeypatch, selected=True)
    progress = private / "DOWNLOAD_PROGRESS.jsonl"
    rows = [json.loads(line) for line in progress.read_text().splitlines()]
    rows[0]["sha256"] = "0" * 64
    progress.write_text("".join(json.dumps(r) + "\n" for r in rows))
    monkeypatch.setattr(writer, "read_la_slot", lambda *args, **kwargs: pytest.fail("reader must not run"))
    with pytest.raises(ValueError, match="changed after download"):
        writer.decode(plan, digest, private)
    assert not (packet / "RESULT.json").exists()


@pytest.mark.parametrize("corruption,message", [
    ("duplicate", "key coverage"),
    ("path", "source path"),
    ("etag", "ETag"),
])
def test_wrong_progress_identity_stops_before_reader(tmp_path, monkeypatch, corruption, message):
    plan, digest, private, packet = setup_case(tmp_path, monkeypatch, selected=True)
    progress = private / "DOWNLOAD_PROGRESS.jsonl"
    rows = [json.loads(line) for line in progress.read_text().splitlines()]
    if corruption == "duplicate":
        rows[1] = rows[0].copy()
    elif corruption == "path":
        rows[0]["path"] = rows[1]["path"]
    else:
        rows[0]["etag"] = "wrong-source-etag"
    progress.write_text("".join(json.dumps(r) + "\n" for r in rows))
    monkeypatch.setattr(writer, "read_la_slot", lambda *args, **kwargs: pytest.fail("reader must not run"))
    with pytest.raises(ValueError, match=message):
        writer.decode(plan, digest, private)
    assert not (packet / "RESULT.json").exists()


def test_nonempty_synthetic_decode_publishes_complete_mask_schema(tmp_path, monkeypatch):
    plan, digest, private, packet = setup_case(tmp_path, monkeypatch, selected=True)
    # Test the writer dataflow with a clearly synthetic reader payload.
    payload = SimpleNamespace(lat=torch.tensor([writer.TARGET_LAT], dtype=torch.float64),
                              lon=torch.tensor([writer.TARGET_LON], dtype=torch.float64),
                              bt=torch.full((1, 9), 291.0), obs_quality=torch.zeros((1, 9)))
    read = SimpleNamespace(payload=payload, pixel_rows=np.array([0]), pixel_cols=np.array([0]),
                           metadata={"synthetic_test": True})
    monkeypatch.setattr(writer, "read_la_slot", lambda *args, **kwargs: read)
    result = writer.decode(plan, digest, private)
    assert result["status"] == "DECODED_GK2A_L1B_SCENES_ONLY"
    assert result["decoded_scene_count"] == 1
    assert result["interpretation"].startswith("1 decoded")
    with (packet / "FIXED_PATCH_SAMPLES.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 9
    assert all(r["source_missing"] == "False" and r["padding"] == "False" for r in rows)
    with np.load(private / "FIXED_POINT_PATCH.npz", allow_pickle=False) as arrays:
        assert arrays["20250720_padding_mask"].sum() == 16 * 9
        assert not arrays["20250720_source_missing_mask"].any()
    assert (packet / "POINT_SAMPLES.csv").exists()
    assert json.loads((packet / "RESULT.json").read_text())["private_payload_sha256"] == writer.sha256(private / "FIXED_POINT_PATCH.npz")
