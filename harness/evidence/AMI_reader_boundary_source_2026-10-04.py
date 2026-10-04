#!/usr/bin/env python3
"""Replay a frozen KO/archived-FD reader boundary; no KDM/RTTOV engines."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path
import netCDF4
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL_RECORD_SHA256 = "9b25cc3043a1f0c35aadd649c187696331f2f550c94ad808ab16f31f4fb8d6e4"
ARCHIVED_FD_STAMP = "202302160000"
sys.path.insert(0, str(ROOT / "oracle"))
from kdm6.obs.gk2a_l1b import AMI_CHANNELS, _read_ami_bt, load_cal_table  # noqa: E402
from kdm6.obs.gk2a_l1b_fd import read_fd_slot  # noqa: E402

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()
def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--record", type=Path, required=True,
                   help="immutable original AMI_reader_boundary_result JSON")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    record_path = args.record.resolve()
    record_sha = sha(record_path)
    if record_sha != ORIGINAL_RECORD_SHA256:
        raise ValueError("--record is not the immutable original boundary baseline")
    old = json.loads(record_path.read_text())
    ko, fd = Path(old["ko_file"]).resolve(), Path(old["fd_file"]).resolve()
    cal = ROOT / "oracle/kdm6/obs/data/gk2a_ami_cal_202507190000.json"
    legacy = ROOT / "harness/evidence/AMI_legacy_nominal_calibration_202507190000.json"
    sources = {
        "oracle/kdm6/obs/gk2a_l1b.py": ROOT / "oracle/kdm6/obs/gk2a_l1b.py",
        "oracle/kdm6/obs/gk2a_l1b_fd.py": ROOT / "oracle/kdm6/obs/gk2a_l1b_fd.py",
        "oracle/kdm6/obs/data/gk2a_ami_cal_202507190000.json": cal,
        "harness/evidence/AMI_legacy_nominal_calibration_202507190000.json": legacy,
    }
    source_hashes = {k: sha(v) for k, v in sources.items()}
    if source_hashes != old["source_sha256"]:
        raise ValueError("reader/calibration hashes differ from original record")
    if old["fd_stamp"] != ARCHIVED_FD_STAMP:
        raise ValueError("this replay is pinned to the separate archived 2023 FD sample")
    if sha(ko) != old["ko_file_sha256"] or sha(fd) != old["fd_sha256"]:
        raise ValueError("one of the recorded observation file hashes changed")
    shipped, archived = load_cal_table(cal)["channels"], load_cal_table(legacy)["channels"]
    with netCDF4.Dataset(str(ko), "r") as ds:
        var = ds.variables["image_pixel_values"]
        new_bt, new_q = _read_ami_bt(var, shipped["ir105"])
        old_bt, old_q = _read_ami_bt(var, archived["ir105"])
    pix = tuple(map(int, old["ko_pixel"]))
    if pix != (411, 338) or new_bt.shape != (900, 900) or old_bt.shape != (900, 900):
        raise ValueError("the frozen KO pixel/grid no longer matches the receipt")
    fd_obs = read_fd_slot([fd], stride=int(old["fd_stride"]))
    if fd_obs.valid_time_utc != old["fd_stamp"]:
        raise ValueError("archived FD reader timestamp differs from receipt")
    j = AMI_CHANNELS.index("ir087")
    values = {
        "ko_file": str(ko), "ko_file_sha256": sha(ko), "ko_pixel": list(pix),
        "new_source_paired_bt_K": float(new_bt[pix]), "legacy_bt_K": float(old_bt[pix]),
        "whole_ko_quality_array_identical": bool(np.array_equal(new_q, old_q)),
        "fd_file": str(fd), "fd_sha256": sha(fd), "fd_stamp": fd_obs.valid_time_utc,
        "fd_stride": int(old["fd_stride"]),
        "fd_usable": int(torch.count_nonzero(fd_obs.obs_quality[:, j] == 0.0).item()),
        "ko_stride": int(old["ko_stride"]),
    }
    for key, value in values.items():
        if value != old[key]:
            raise ValueError(f"replayed {key} differs from original record: {value!r}")
    if not values["whole_ko_quality_array_identical"]:
        raise ValueError("legacy and source-paired KO quality arrays differ")
    result = {
        "status": "BYTE_SOURCE_AND_VALUE_REPLAY_MATCH",
        "scope": "2025 KO IR105 and separate 2023 FD IR087 reader samples; no model or RTTOV run.",
        "original_record_path": str(record_path), "original_record_sha256": record_sha,
        "replayed_values": values, "ko_quality_shape": list(new_q.shape),
        "scientific_approval": False,
        "fd_is_2025_ko_lineage_or_replacement_data": False,
        "provenance": {"source_path": str(Path(__file__).resolve()),
                       "source_sha256": sha(Path(__file__).resolve()),
                       "cli_argv": sys.argv, "reader_calibration_source_sha256": source_hashes,
                       "python": platform.python_version(), "torch": str(torch.__version__),
                       "numpy": str(np.__version__)},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), "sha256": sha(args.output),
                      "status": result["status"]}, sort_keys=True))

if __name__ == "__main__":
    main()
