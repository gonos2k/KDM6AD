"""Derive path-free hard moment masks from three pinned native checkpoints.

This is a value-only evidence producer. It reads existing host checkpoints and
the published fixed M0 mask; it does not run or modify the model or RTTOV.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


BASELINE_SHA256 = "c919f13c3ceb4defec42e43e0b60ad71d22d10f57a9454f6f880f98ec1bf9144"
SHAPE = (39, 282, 234)
COLUMNS = 65988
FIELDS = ("QCLOUD", "QNCLOUD", "QICE", "QNICE")


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def hard_invalid(path: Path) -> np.ndarray:
    import netCDF4

    with netCDF4.Dataset(path) as ds:
        ds.set_auto_maskandscale(False)
        fields = {}
        for name in FIELDS:
            variable = ds[name]
            if (tuple(variable.dimensions) != ("Time", "bottom_top", "south_north", "west_east")
                    or variable.dtype != np.float32 or variable.shape != (1, *SHAPE)):
                raise ValueError(f"checkpoint {name} schema differs")
            values = np.asarray(variable[0])
            if not np.isfinite(values).all():
                raise ValueError(f"checkpoint {name} has nonfinite values")
            fields[name] = values.reshape(39, COLUMNS)
    qc, nc, qi, ni = (fields[name] for name in FIELDS)
    return np.any(((qc > 0) & (nc <= 0)) | ((qi > 0) & (ni <= 0)) |
                  (nc < 0) | (ni < 0), axis=0)


def produce(baseline: Path, checkpoints: dict[str, Path], output: Path, receipt: Path,
            expected_sha: dict[str, str]) -> dict:
    if output.exists() or output.is_symlink() or receipt.exists() or receipt.is_symlink():
        raise FileExistsError("support-mask output and receipt require fresh paths")
    if sha(baseline) != BASELINE_SHA256:
        raise ValueError("published full-domain M0 asset changed")
    with np.load(baseline, allow_pickle=False) as archive:
        m0 = np.asarray(archive["m0_mask"])
        flat = np.asarray(archive["flat_index"])
    if (m0.dtype != np.bool_ or m0.shape != (COLUMNS, 7) or flat.dtype != np.int32
            or not np.array_equal(flat, np.arange(COLUMNS, dtype=np.int32))):
        raise ValueError("published fixed support shape/index differs")
    expected_names = ("historical_alpha", "control", "alpha025")
    if tuple(checkpoints) != expected_names or set(expected_sha) != set(expected_names):
        raise ValueError("three ordered checkpoint identities are required")
    masks = {}
    for name in expected_names:
        path = checkpoints[name]
        if sha(path) != expected_sha[name]:
            raise ValueError(f"{name} checkpoint SHA differs")
        masks[name] = hard_invalid(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        np.savez_compressed(stream, m0_mask=m0, flat_indices=np.arange(COLUMNS, dtype=np.int32),
                            **{f"{name}_hard_invalid": value for name, value in masks.items()})
    result = {"schema": "kdm6.native_qnc_hard_mask_producer_receipt.v1",
              "producer_sha256": sha(Path(__file__)),
              "published_M0_sha256": BASELINE_SHA256,
              "input_checkpoint_sha256": expected_sha,
              "output_npz_sha256": sha(output),
              "output_npz_bytes": output.stat().st_size,
              "M0_profiles": int(m0.any(axis=1).sum()),
              "M0_channel_cells": int(m0.sum()),
              "hard_invalid_M0_profiles": {name: int(np.count_nonzero(mask & m0.any(axis=1)))
                                           for name, mask in masks.items()},
              "recovered_flat_indices": np.flatnonzero(
                  masks["historical_alpha"] & ~masks["alpha025"] & m0.any(axis=1)).astype(int).tolist(),
              "host_calls": 0, "KDM6_calls": 0, "RTTOV_calls": 0}
    with receipt.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    for name in ("historical-alpha", "control", "alpha025"):
        parser.add_argument(f"--{name}", type=Path, required=True)
        parser.add_argument(f"--{name}-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    checkpoints = {"historical_alpha": args.historical_alpha, "control": args.control,
                   "alpha025": args.alpha025}
    expected = {"historical_alpha": args.historical_alpha_sha256,
                "control": args.control_sha256, "alpha025": args.alpha025_sha256}
    result = produce(args.baseline, checkpoints, args.output, args.receipt, expected)
    print(json.dumps({"status": "HARD_MASKS_PRODUCED", "output_npz_sha256": result["output_npz_sha256"],
                      "hard_invalid_M0_profiles": result["hard_invalid_M0_profiles"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
