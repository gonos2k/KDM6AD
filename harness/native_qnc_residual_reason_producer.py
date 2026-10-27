"""Capture fixed-support QC/NC and QI/NI failures before and after one host step.

The value-only producer reads existing private checkpoints. It records raw f32
words only at failing final levels; it neither runs nor modifies the host.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


NX, NY, LEVELS, COLUMNS = 234, 282, 39, 65988
BASELINE_SHA = "c919f13c3ceb4defec42e43e0b60ad71d22d10f57a9454f6f880f98ec1bf9144"
SUPPORT_SHA = "c4154b4b735fcbfb5509b1f23ee53f4cfe17b46ccf0c6930f63aa244f2a0f9a9"
READY_SHA = "0c4836a2a44531c98d38d3ded15cab5048679b1139f3e4fd96fb62eff84bfad3"
FINAL_SHA = "e2b069e68c3a844d92ce17b1ef30a3ba21645882cb4ad2f7d57797458a3ae78f"
FIELDS = ("QCLOUD", "QNCLOUD", "QICE", "QNICE")


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _fields(path: Path) -> dict[str, np.ndarray]:
    import netCDF4

    out = {}
    with netCDF4.Dataset(path) as dataset:
        dataset.set_auto_maskandscale(False)
        for name in FIELDS:
            variable = dataset[name]
            if (variable.dtype != np.float32 or variable.shape != (1, LEVELS, NY, NX) or
                    tuple(variable.dimensions) != ("Time", "bottom_top", "south_north", "west_east")):
                raise ValueError(f"checkpoint {name} schema differs")
            value = np.asarray(variable[0])
            if not np.isfinite(value).all():
                raise ValueError(f"checkpoint {name} has nonfinite values")
            out[name] = value.reshape(LEVELS, COLUMNS)
    return out


def _flags(fields: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    qc, nc, qi, ni = (fields[name] for name in FIELDS)
    return {"liquid_QC_positive_NC_nonpositive": (qc > 0) & (nc <= 0),
            "ice_QI_positive_NI_nonpositive": (qi > 0) & (ni <= 0),
            "negative_NC": nc < 0, "negative_NI": ni < 0}


def produce(ready: Path, final: Path, baseline: Path, support: Path, output: Path) -> dict:
    if output.exists() or output.is_symlink():
        raise FileExistsError("residual reason output requires a fresh path")
    for path, expected in ((ready, READY_SHA), (final, FINAL_SHA),
                           (baseline, BASELINE_SHA), (support, SUPPORT_SHA)):
        if sha(path) != expected:
            raise ValueError(f"pinned input differs: {path.name}")
    with np.load(baseline, allow_pickle=False) as archive:
        m0 = np.asarray(archive["m0_mask"], dtype=np.bool_)
        flat = np.asarray(archive["flat_index"], dtype=np.int32)
    with np.load(support, allow_pickle=False) as archive:
        published_bad = np.asarray(archive["alpha025_hard_invalid"], dtype=np.bool_)
    if (m0.shape != (COLUMNS, 7) or not np.array_equal(flat, np.arange(COLUMNS, dtype=np.int32))
            or published_bad.shape != (COLUMNS,)):
        raise ValueError("published M0 or hard-mask shape differs")
    before = _fields(ready)
    after = _fields(final)
    ready_flags, final_flags = _flags(before), _flags(after)
    ready_bad = np.any(np.stack([np.any(value, axis=0) for value in ready_flags.values()]), axis=0)
    final_bad = np.any(np.stack([np.any(value, axis=0) for value in final_flags.values()]), axis=0)
    if not np.array_equal(final_bad, published_bad):
        raise ValueError("final reasons do not reproduce published hard-invalid mask")
    supported = m0.any(axis=1)
    missing = np.flatnonzero(final_bad & supported)
    if missing.size != 54 or int(m0[missing].sum()) != 378 or 14728 in missing:
        raise ValueError("final fixed-support failure set differs")
    rows = []
    for index in missing.tolist():
        kinds = {name: (np.flatnonzero(value[:, index]) + 1).astype(int).tolist()
                 for name, value in final_flags.items() if value[:, index].any()}
        ready_kinds = {name: (np.flatnonzero(value[:, index]) + 1).astype(int).tolist()
                       for name, value in ready_flags.items() if value[:, index].any()}
        levels = sorted({level for selected in (*kinds.values(), *ready_kinds.values())
                         for level in selected})
        word_rows = []
        for k1 in levels:
            k0 = k1 - 1
            word_rows.append({"native_k_one_based": k1,
                              "final_f32_hex": {name: f"{int(after[name][k0, index].view(np.uint32)):08X}"
                                                for name in FIELDS},
                              "ready_f32_hex": {name: f"{int(before[name][k0, index].view(np.uint32)):08X}"
                                                for name in FIELDS}})
        rows.append({"flat_index_zero_based": index, "i_one_based": index % NX + 1,
                     "j_one_based": index // NX + 1,
                     "M0_channel_count": int(m0[index].sum()),
                     "final_reason_levels_one_based": kinds,
                     "ready_reason_levels_one_based": ready_kinds,
                     "already_hard_invalid_at_ready": bool(ready_bad[index]),
                     "failing_level_words": word_rows})
    def count(name: str) -> int:
        return int(np.count_nonzero(np.any(final_flags[name], axis=0) & supported))
    result = {"schema": "kdm6.native_qnc_residual_reason_rows.v1",
              "producer_sha256": sha(Path(__file__)),
              "input_sha256": {"pre_command_READY40": READY_SHA, "candidate_final": FINAL_SHA,
                               "published_M0": BASELINE_SHA, "published_hard_masks": SUPPORT_SHA},
              "M0_profiles": int(supported.sum()),
              "remaining_invalid_M0_profiles": int(missing.size),
              "remaining_invalid_M0_channel_cells": int(m0[missing].sum()),
              "reason_profile_counts": {name: count(name) for name in final_flags},
              "remaining_already_invalid_at_pre_command_READY40": sum(
                  row["already_hard_invalid_at_ready"] for row in rows),
              "remaining_new_since_pre_command_READY40": sum(
                  not row["already_hard_invalid_at_ready"] for row in rows),
              "rows": rows,
              "model_calls": {"host": 0, "KDM6": 0, "RTTOV": 0, "optimizer": 0}}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("ready", "final", "baseline", "support", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    result = produce(args.ready, args.final, args.baseline, args.support, args.output)
    print(json.dumps({"status": "RESIDUAL_REASONS_CAPTURED",
                      "profiles": result["remaining_invalid_M0_profiles"],
                      "ready": result["remaining_already_invalid_at_pre_command_READY40"],
                      "new": result["remaining_new_since_pre_command_READY40"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
