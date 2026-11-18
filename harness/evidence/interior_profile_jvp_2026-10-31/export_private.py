#!/usr/bin/env python3
"""Extract one pinned native column for an offline profile-builder JVP audit."""

import argparse
import hashlib
import json
import os
from pathlib import Path

import netCDF4
import numpy as np

CHECKPOINT_SHA = "950bc5d67dc8cf4980091ecac19a9b7b1ba94756e83d9bd101180e55863c0bb6"
INPUTS_SHA = "c9df709fe00578b4468187cb782006da105cce28c3666d26de5e03c6c4bd461b"
CASE_MANIFEST_SHA = "58d23f72be7ae717b20d0d60b53f908c2ecf28bd1c973756a1d4c7e4f0ec7c8d"
I0, J0, K0 = 163, 241, 20
CENTER = (
    "THM_2", "QVAPOR", "QCLOUD", "QICE", "QSNOW", "QNCLOUD",
    "QNICE", "QRAIN", "QGRAUP", "QNCCN", "QNRAIN", "QIB",
    "P", "PB", "AL", "ALB",
)
INTERFACE = ("PH_2", "PHB")
VERTICAL = ("FNM", "FNP")
REFERENCE = {
    "p_lay_hpa": "rttov_reference__p_lay_hPa",
    "p_half_hpa": "rttov_reference__p_half_hPa",
    "t_k": "rttov_reference__t_K",
    "q_ppmv": "rttov_reference__q_ppmv",
}


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def digest_open_file(stream):
    stream.seek(0)
    h = hashlib.sha256()
    for chunk in iter(lambda: stream.read(8 << 20), b""):
        h.update(chunk)
    return h.hexdigest()


def is_owned(path, identity):
    if identity is None:
        return False
    try:
        current = path.lstat()
    except FileNotFoundError:
        return False
    return (current.st_dev, current.st_ino) == identity


def remove_if_owned(path, identity):
    if is_owned(path, identity):
        path.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--case-manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.suffix != ".npz":
        parser.error("--out must end in .npz")
    pinned_sources = (
        (args.checkpoint, CHECKPOINT_SHA),
        (args.inputs, INPUTS_SHA),
        (args.case_manifest, CASE_MANIFEST_SHA),
    )
    for path, expected in pinned_sources:
        if digest(path) != expected:
            raise ValueError(f"pinned private input differs: {path}")
    config = json.loads(args.case_manifest.read_bytes())["case_preparation"]
    arrays = {}
    with netCDF4.Dataset(args.checkpoint) as dataset:
        dataset.set_auto_mask(False)
        dataset.set_auto_scale(False)
        unit_labels = {
            name: str(getattr(dataset.variables[name], "units", ""))
            for name in ("QICE", "QNICE", "AL", "ALB")
        }
        for name in CENTER:
            value = dataset.variables[name]
            if value.shape != (1, 39, 282, 234) or value.dtype != np.float32:
                raise ValueError(f"unexpected native center field {name}")
            arrays[name] = np.asarray(value[0, :, J0, I0], dtype=np.float32)
        for name in INTERFACE:
            value = dataset.variables[name]
            if value.shape != (1, 40, 282, 234) or value.dtype != np.float32:
                raise ValueError(f"unexpected native interface field {name}")
            arrays[name] = np.asarray(value[0, :, J0, I0], dtype=np.float32)
        for name in VERTICAL:
            value = dataset.variables[name]
            if value.shape != (1, 39) or value.dtype != np.float32:
                raise ValueError(f"unexpected native vertical field {name}")
            arrays[name] = np.asarray(value[0, :], dtype=np.float32)
        xland = dataset.variables["XLAND"]
        if xland.shape != (1, 282, 234) or xland.dtype != np.float32:
            raise ValueError("unexpected XLAND")
        arrays["XLAND"] = np.asarray(xland[0, J0, I0], dtype=np.float32)
    with np.load(args.inputs, allow_pickle=False) as source:
        for name, key in REFERENCE.items():
            arrays["reference__" + name] = np.array(source[key], dtype=np.float64)
    if any(not np.isfinite(value).all() for value in arrays.values()):
        raise ValueError("nonfinite selected input")
    metadata_path = args.out.with_suffix(".json")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    npz_identity = metadata_identity = None
    try:
        # Reserve both names exclusively before writing either payload. Passing the
        # file object also prevents NumPy from silently appending another suffix.
        with args.out.open("x+b") as npz_stream:
            npz_stat = os.fstat(npz_stream.fileno())
            npz_identity = (npz_stat.st_dev, npz_stat.st_ino)
            with metadata_path.open("xb") as metadata_stream:
                metadata_stat = os.fstat(metadata_stream.fileno())
                metadata_identity = (metadata_stat.st_dev, metadata_stat.st_ino)
                np.savez_compressed(npz_stream, **arrays)
                npz_stream.flush()
                os.fsync(npz_stream.fileno())
                fixture_sha = digest_open_file(npz_stream)
                metadata = {
                    "schema": "kdm6.interior_profile_jvp_column.v1",
                    "native_ijk_1based": [164, 242, 21],
                    "flat_index_0based": 56557,
                    "rttov_row_0based": 45,
                    "fixed_upper_count": 27,
                    "source_sha256": {
                        "checkpoint": CHECKPOINT_SHA,
                        "observation_inputs": INPUTS_SHA,
                        "case_manifest": CASE_MANIFEST_SHA,
                    },
                    "exporter_sha256": digest(Path(__file__)),
                    "fixture_sha256": fixture_sha,
                    "prep_configuration": config["prep_configuration"],
                    "experiment": {
                        name: config["experiment"][name]
                        for name in ("ncmin_land", "ncmin_sea")
                    },
                    "coordinate_contract": "raw checkpoint QNICE; profile_jvp converts raw NI/rho_d before the dry-number optical bridge",
                    "checkpoint_unit_labels": unit_labels,
                    "raw_number_unit_certified": False,
                }
                metadata_stream.write((json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode())
                metadata_stream.flush()
                os.fsync(metadata_stream.fileno())
        for path, expected in pinned_sources:
            if digest(path) != expected:
                raise ValueError(f"pinned private input changed during export: {path}")
        if not is_owned(args.out, npz_identity) or not is_owned(metadata_path, metadata_identity):
            raise RuntimeError("output path replaced during export")
    except BaseException:
        remove_if_owned(metadata_path, metadata_identity)
        remove_if_owned(args.out, npz_identity)
        raise
    print(json.dumps({"fixture_sha256": metadata["fixture_sha256"], "selected_levels": 39}))


if __name__ == "__main__":
    main()
