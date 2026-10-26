"""Extract the three selected native QC/NC profiles from closed checkpoints.

Value-only data publication; this tool does not execute KDM, a host or RTTOV.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

TARGETS = ((155, 25), (221, 63), (91, 94))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def extract_context(ready: Path, final: Path, output: Path, receipt: Path,
                    *, ready_sha256: str, final_sha256: str) -> dict:
    for path in (output, receipt):
        if path.exists() or path.is_symlink():
            raise FileExistsError(f"context publication requires a fresh path: {path}")
    a, b = output.resolve(), receipt.resolve()
    if a == b or a in b.parents or b in a.parents:
        raise ValueError("context NPZ and receipt paths must be separate")
    for path, expected in ((ready, ready_sha256), (final, final_sha256)):
        if path.is_symlink() or sha256_file(path) != expected:
            raise ValueError(f"checkpoint must be a regular, hash-pinned file: {path}")
    from netCDF4 import Dataset

    arrays = {}
    for label, path in (("ready", ready), ("final", final)):
        with Dataset(path) as data:
            data.set_auto_maskandscale(False)
            for field, native in (("qc", "QCLOUD"), ("nc", "QNCLOUD")):
                variable = data.variables[native]
                if variable.shape != (1, 39, 282, 234) or variable.dtype != np.dtype("float32"):
                    raise ValueError(f"{native} is not the expected native REAL4 mass grid")
                values = np.stack([variable[0, :, j - 1, i - 1] for i, j in TARGETS])
                if values.dtype != np.float32 or not np.isfinite(values).all():
                    raise ValueError(f"{label} {native} is not finite raw binary32")
                arrays[f"{label}_{field}"] = values
    for path, expected in ((ready, ready_sha256), (final, final_sha256)):
        if sha256_file(path) != expected:
            raise ValueError("checkpoint changed while extracting selected values")
    with output.open("xb") as stream:
        np.savez_compressed(stream, **arrays)
    result = {
        "schema": "kdm6.native_moment_context_publication.v1",
        "scope": "Selected raw native QC/NC profiles only; no new model calls or number-unit certification.",
        "producer_sha256": sha256_file(Path(__file__)),
        "ready": {"name": ready.name, "sha256": ready_sha256, "bytes": ready.stat().st_size},
        "final": {"name": final.name, "sha256": final_sha256, "bytes": final.stat().st_size},
        "targets_one_based_i_j": [list(pair) for pair in TARGETS],
        "native_shape_i_k_j": [234, 39, 282],
        "context": {"name": output.name, "sha256": sha256_file(output), "bytes": output.stat().st_size},
        "array_keys": list(arrays), "array_shape": [3, 39], "array_dtype": "float32",
    }
    with receipt.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("ready", "final", "output", "receipt"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--ready-sha256", required=True)
    parser.add_argument("--final-sha256", required=True)
    args = parser.parse_args()
    result = extract_context(args.ready, args.final, args.output, args.receipt,
                             ready_sha256=args.ready_sha256, final_sha256=args.final_sha256)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
