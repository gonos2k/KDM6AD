#!/usr/bin/env python3
"""Export completed captured values; never invokes the experiment."""

import argparse
import gzip
import json
import shutil
import sys
from pathlib import Path

from verify import (
    CORNERS,
    HS,
    LAUNCH_SHA,
    MODES,
    PINS_SHA,
    RUNNER_SHA,
    sha,
    verify,
    verify_sources,
)


def export(source, dest):
    verify_sources()
    # Source paths are checked before copying. A failed/incomplete run cannot be
    # exported, and an existing destination is never overwritten.
    pins_path = source / "prepared/pins.json"
    if (
        sha(source / "runner.py") != RUNNER_SHA
        or sha(source / "locked_launch.py") != LAUNCH_SHA
        or sha(pins_path) != PINS_SHA
    ):
        raise ValueError("locked source mismatch")
    pins = json.loads(pins_path.read_text())
    for name, digest in pins["sources"].items():
        if sha(Path(name)) != digest:
            raise ValueError(f"live source or asset mismatch: {name}")
    # The fixed runtime identities are recorded for interpretation. Rechecking
    # source bytes does not prove the currently loaded linked library identity.
    import numpy as np
    import torch
    import netCDF4

    runtime = {
        "python_version": sys.version,
        "python_executable_sha256": sha(Path(sys.executable)),
        "numpy_version": np.__version__,
        "torch_version": str(torch.__version__),
        "torch_extension_sha256": sha(Path(torch._C.__file__)),
        "netcdf4_version": netCDF4.__version__,
        "netcdf4_extension_sha256": sha(Path(netCDF4._netCDF4.__file__)),
    }
    if runtime != pins["runtime"]:
        raise ValueError("runtime mismatch")
    inputs = {
        "runner.py": source / "runner.py",
        "locked_launch.py": source / "locked_launch.py",
        "pins.json": pins_path,
        "preflight.json": source / "preflight.json",
        "summary.json": source / "results/summary.json",
        "attempt.json": source / "results/attempt.json",
    }
    for corner in CORNERS:
        candidates = [
            Path(p) for p in pins["sources"] if p.endswith(f"/{corner}/result.npz")
        ]
        if len(candidates) != 1:
            raise ValueError("ambiguous preserved baseline")
        inputs[f"{corner}_baseline.npz"] = candidates[0]
    keys = [f"{c}_K" for c in CORNERS] + [
        f"{c}_{m}_{i}_{s}"
        for c in CORNERS
        for m in MODES
        for i in range(len(HS))
        for s in ("plus", "minus")
    ]
    for key in keys:
        case = source / "results" / key
        paths = [p for p in (case / "in").rglob("*") if p.is_file()] + [
            case / "out" / n for n in ("run.sh", "env.sh", "rttov_test.txt")
        ]
        observed = {str(p.relative_to(case)): sha(p) for p in sorted(paths)}
        if observed != pins["cases"][key]:
            raise ValueError(f"captured case input mismatch: {key}")
        for name in ("receipt.json", "values.npz"):
            inputs[f"{key}/{name}"] = source / "results" / key / name
        inputs[f"{key}/direct_radiance.txt"] = case / "out/direct/radiance.txt"
        if key.endswith("_K"):
            inputs[f"{key}/k_radiance.txt"] = case / "out/k/radiance.txt"
            inputs[f"{key}/profiles_k.txt.gz"] = case / "out/k/profiles_k.txt"
    for path in inputs.values():
        if not path.is_file():
            raise ValueError(f"missing completed capture: {path}")
    dest.mkdir(parents=False, exist_ok=False)
    files = {}
    for name, path in inputs.items():
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if name.endswith(".gz"):
            before = sha(path)
            target.write_bytes(gzip.compress(path.read_bytes(), mtime=0))
            if (
                sha(path) != before
                or __import__("hashlib")
                .sha256(gzip.decompress(target.read_bytes()))
                .hexdigest()
                != before
            ):
                raise ValueError(f"capture changed while compressing: {path}")
        else:
            shutil.copyfile(path, target)
            if sha(target) != sha(path):
                raise ValueError(f"capture changed while copying: {path}")
        files[name] = sha(target)
    (dest / "packet.json").write_text(
        json.dumps(
            {"schema": "east-optical-derivative-packet-v1", "files": files},
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    result = verify(dest)
    print(
        json.dumps(
            {
                "packet": str(dest),
                "packet_sha256": sha(dest / "packet.json"),
                "status": result["status"],
                "reason": result["reason"],
            },
            indent=2,
        )
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    export(args.source, args.destination)


if __name__ == "__main__":
    main()
