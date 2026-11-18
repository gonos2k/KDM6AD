"""Export selected f32 endpoint words from the pinned private wrfrst file."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from netCDF4 import Dataset, default_fillvals


EXPECTED_ENDPOINT_SHA256 = (
    "950bc5d67dc8cf4980091ecac19a9b7b1ba94756e83d9bd101180e55863c0bb6"
)
FIELDS = ("AL", "ALB", "RHO", "QVAPOR", "QNICE")
EXPECTED_TIME = b"2025-07-19_00:01:00"
EXPECTED_DIMS = ("Time", "bottom_top", "south_north", "west_east")
EXPECTED_SHAPE = (1, 39, 282, 234)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def export(endpoint):
    endpoint = Path(endpoint)
    if digest(endpoint) != EXPECTED_ENDPOINT_SHA256:
        raise ValueError("private endpoint SHA-256 differs")
    cells = {}
    with Dataset(endpoint) as ds:
        ds.set_auto_maskandscale(False)
        times = ds.variables["Times"]
        if (times.dimensions != ("Time", "DateStrLen") or
                times.shape != (1, len(EXPECTED_TIME)) or
                times[0, :].tobytes() != EXPECTED_TIME):
            raise ValueError("endpoint saved time")
        for native_k in (21, 23):
            words = {}
            for name in FIELDS:
                variable = ds.variables[name]
                if (variable.dtype != np.dtype("float32") or
                        variable.dimensions != EXPECTED_DIMS or
                        variable.shape != EXPECTED_SHAPE or
                        any(hasattr(variable, attr) for attr in
                            ("scale_factor", "add_offset", "_FillValue",
                             "missing_value"))):
                    raise ValueError("endpoint field dtype/shape " + name)
                value = np.asarray(variable[0, native_k-1, 242-1, 164-1])
                if (not np.isfinite(value) or
                        value == np.float32(default_fillvals["f4"])):
                    raise ValueError("missing or nonfinite endpoint value " + name)
                words[name] = format(int.from_bytes(
                    value.astype("<f4", copy=False).tobytes(), "little"), "08x")
            cells[str(native_k)] = words
    if digest(endpoint) != EXPECTED_ENDPOINT_SHA256:
        raise ValueError("private endpoint changed during extraction")
    return {"schema": "kdm6.native_qnice_endpoint_words.v1",
            "endpoint_sha256": EXPECTED_ENDPOINT_SHA256,
            "native_ij_1based": [164, 242], "saved_time": EXPECTED_TIME.decode(),
            "cells": cells,
            "timing": "saved 00:01:00 endpoint, not the microphysics call"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = export(args.endpoint)
    payload = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode()
    with args.out.open("xb") as stream:
        stream.write(payload)


if __name__ == "__main__":
    main()
