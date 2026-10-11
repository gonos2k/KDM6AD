#!/usr/bin/env python3
"""Add source-mask sidecars from existing PR403 raw slices; never redo acquisition."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path

import netCDF4
import numpy as np

PACKET = Path(__file__).resolve().parent
ORIGINAL = Path("/Users/yhlee/KDM6AD-k/host/research_evidence/pr403_l1b_heldout_20261011/l1bheldout20261011c")
DESTINATION = Path("/Users/yhlee/KDM6AD-k/host/research_evidence/pr404_l1b_source_mask_20261011/source-mask-v1")
spec = importlib.util.spec_from_file_location("heldout_l1b_v2", PACKET / "heldout_l1b_v2.py")
writer = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(writer)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    if DESTINATION.exists() or (PACKET / "MASK_REPAIR_RESULT.json").exists():
        raise FileExistsError("refusing repeat execution or result overwrite")
    old_payload = ORIGINAL / "FIXED_POINT_PATCH.npz"
    old_hash = sha(old_payload)
    if old_hash != "d24bb3a5d029ec13d1b25d0afdae95637a971d6d304f38bcc73dae461220bd90":
        raise ValueError("original PR403 payload changed")
    receipt = json.loads((ORIGINAL / "DOWNLOAD_RECEIPT.json").read_text())
    inputs = [json.loads(line) for line in Path(receipt["progress_path"]).read_text().splitlines()]
    if len(inputs) != 18 or receipt["plan_sha256"] != "ce5a3d4a4109813ef61aa199c8b0bcef83d8828d9fdeebe6db5675d275ee54f3":
        raise ValueError("original acquisition receipt changed")
    arrays, source_records = {}, []
    with np.load(old_payload, allow_pickle=False) as old:
        for date in writer.DATES:
            words = np.zeros((5, 5, 9), dtype=np.uint16)
            missing = np.zeros_like(words, dtype=bool)
            padding = np.ones_like(words, dtype=bool)
            dqf = np.full_like(words, 255, dtype=np.uint8)
            for j, channel in enumerate(writer.CLEAN_IR_CHANNELS):
                name = f"gk2a_ami_le1b_{channel}_la020ge_{date}0556.nc"
                row = next(r for r in inputs if Path(r["path"]).name == name)
                source = Path(row["path"])
                if sha(source) != row["sha256"]:
                    raise ValueError("raw source changed")
                with netCDF4.Dataset(source) as ds:
                    var = ds.variables["image_pixel_values"]
                    words[:, :, j], missing[:, :, j], padding[:, :, j] = writer.source_patch_canvas(var, 320, 48)
                    valid_bits = int(var.getncattr("number_of_valid_bits_per_pixel"))
                    attrs = {k: np.asarray(var.getncattr(k)).tolist() for k in
                             ("_FillValue", "missing_value", "scale_factor", "add_offset", "valid_min", "valid_max", "valid_range")
                             if k in var.ncattrs()}
                _, q = writer.unpack_ami_word(words[:, :, j], valid_bits)
                dqf[:, :, j] = np.where(padding[:, :, j], 255, q).astype(np.uint8)
                if sha(source) != row["sha256"]:
                    raise ValueError("source bytes changed during slice capture")
                source_records.append({"file": name, "sha256": row["sha256"], "source_mask_attributes": attrs,
                                       "source_missing_cells": int(missing[:, :, j].sum()),
                                       "padding_cells": int(padding[:, :, j].sum())})
            np.testing.assert_array_equal(words, old[date + "_raw_words"])
            np.testing.assert_array_equal(dqf, old[date + "_raw_embedded_dqf"])
            arrays[date + "_raw_words"] = words
            arrays[date + "_source_missing_mask"] = missing
            arrays[date + "_padding_mask"] = padding
            arrays[date + "_raw_embedded_dqf"] = dqf
    if sha(old_payload) != old_hash:
        raise ValueError("original payload changed")
    DESTINATION.mkdir(parents=True, mode=0o700)
    output = DESTINATION / "SOURCE_MASK_PATCH.npz"
    with output.open("xb") as stream:
        os.chmod(output, 0o600)
        np.savez_compressed(stream, **arrays)
    result = {"status": "ADDITIVE_SOURCE_MASK_SIDECAR_ONLY", "original_payload_sha256": old_hash,
              "original_acquisition_plan_sha256": receipt["plan_sha256"], "repair_source_sha256": sha(__file__),
              "future_writer_source_sha256": sha(PACKET / "heldout_l1b_v2.py"), "source_files": source_records,
              "output_private": str(output), "output_sha256": sha(output), "source_slices_read": 18,
              "original_words_and_embedded_DQF_unchanged": True, "original_payload_unchanged": True,
              "scope": "Existing 5x5 raw slices only; no full scene BT decode, acquisition, model, RTTOV or optimizer.",
              "future_writer_execution": "Only read/source-canvas helpers executed; future preflight/download/full-decode not run."}
    (PACKET / "MASK_REPAIR_RESULT.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    private_receipt = DESTINATION / "MASK_REPAIR_RESULT.json"
    private_receipt.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    os.chmod(private_receipt, 0o600)
    print(json.dumps({"status": result["status"], "source_slices_read": 18, "source_missing_cells": sum(r["source_missing_cells"] for r in source_records)}, indent=2))


if __name__ == "__main__":
    main()
