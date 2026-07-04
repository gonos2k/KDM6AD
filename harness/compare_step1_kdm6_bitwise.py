#!/usr/bin/env python3
"""Bitwise compare KDM6 step dumps by raw float32 hex.

This is intentionally stricter than compare_step1_kdm6_vs_kdm6ad.py: no
float64 conversion, no tolerance, no RMSE as a pass criterion. A field passes
only when every raw IEEE-754 float32 bit is identical.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

FIELDS = ["Q", "QC", "QR", "QI", "QS", "QG", "NC", "NR", "NI", "NN", "BG", "TH"]


def load_dump(path: Path) -> tuple[dict[str, int], dict[str, np.ndarray]]:
    with path.open("rb") as f:
        hdr = np.fromfile(f, dtype=">i4", count=6)
        if hdr.size != 6:
            raise ValueError(f"{path}: short header")
        ims, ime, kms, kme, jms, jme = [int(x) for x in hdr]
        nx = ime - ims + 1
        nk = kme - kms + 1
        ny = jme - jms + 1
        n = nx * nk * ny
        arrays: dict[str, np.ndarray] = {}
        for field in FIELDS:
            arr = np.fromfile(f, dtype=">f4", count=n)
            if arr.size != n:
                raise ValueError(f"{path}: {field} short read ({arr.size} vs {n})")
            arrays[field] = arr.reshape((nx, nk, ny), order="F")
        expected_size = f.tell()
    actual_size = path.stat().st_size
    if actual_size != expected_size:
        extra = actual_size - expected_size
        if extra > 0:
            raise ValueError(f"{path}: trailing bytes after expected payload ({extra} extra bytes)")
        raise ValueError(f"{path}: size mismatch ({actual_size} bytes vs expected {expected_size})")
    dims = {"ims": ims, "ime": ime, "kms": kms, "kme": kme, "jms": jms, "jme": jme}
    return dims, arrays


def first_mismatch(a: np.ndarray, b: np.ndarray) -> tuple[tuple[int, int, int], int, int, float, float] | None:
    au = a.view(">u4")
    bu = b.view(">u4")
    diff = np.flatnonzero(au.ravel() != bu.ravel())
    if diff.size == 0:
        return None
    flat = int(diff[0])
    idx = np.unravel_index(flat, a.shape)
    a_hex = int(au[idx])
    b_hex = int(bu[idx])
    return idx, a_hex, b_hex, float(a[idx]), float(b[idx])


def compare_pair(label: str, ref_path: Path, got_path: Path) -> int:
    ref_dims, ref = load_dump(ref_path)
    got_dims, got = load_dump(got_path)
    print(f"\n## {label}")
    print(f"ref={ref_path}")
    print(f"got={got_path}")
    print(f"dims_ref={ref_dims}")
    print(f"dims_got={got_dims}")
    if ref_dims != got_dims:
        print("FAIL dims differ")
        return 1

    failures = 0
    for field in FIELDS:
        a = ref[field]
        b = got[field]
        if a.shape != b.shape or a.dtype != b.dtype:
            print(f"FAIL {field:6s} shape/dtype {a.shape}/{a.dtype} != {b.shape}/{b.dtype}")
            failures += 1
            continue
        mismatch = first_mismatch(a, b)
        if mismatch is None:
            print(f"PASS {field:6s} bitwise")
            continue
        idx, a_hex, b_hex, a_val, b_val = mismatch
        nneq = int(np.count_nonzero(a.view(">u4") != b.view(">u4")))
        print(
            f"FAIL {field:6s} nneq={nneq} first_idx={idx} "
            f"ref_hex=0x{a_hex:08x} got_hex=0x{b_hex:08x} "
            f"ref={a_val:.9e} got={b_val:.9e}"
        )
        failures += 1
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "paths",
        type=Path,
        nargs="+",
        help=(
            "Default: one directory containing kdm6_step1_*.bin files. "
            "With --pair-only: ref dump and got dump. "
            "With --tile-aware: mp37 run dir and mp137 run dir."
        ),
    )
    parser.add_argument(
        "--driver",
        action="store_true",
        help="also compare driver pre-call dumps kdm6_driver_step1_kdm6*_in.bin",
    )
    parser.add_argument(
        "--pair-only",
        action="store_true",
        help="compare exactly two dump files and do not require wrapper input/output files",
    )
    parser.add_argument(
        "--label",
        default="PAIR mp37 vs mp137",
        help="label for --pair-only output",
    )
    parser.add_argument(
        "--tile-aware",
        action="store_true",
        help="compare tile-aware upstream preselect and driver ij1/ij2 dumps from mp37/mp137 run dirs",
    )
    args = parser.parse_args()

    if args.pair_only:
        if len(args.paths) != 2:
            parser.error("--pair-only requires exactly two dump file paths")
        failures = compare_pair(args.label, args.paths[0], args.paths[1])
        if failures:
            print(f"\nBITWISE RESULT: FAIL ({failures} field-pair failures)")
            return 1
        print("\nBITWISE RESULT: PASS")
        return 0

    if args.tile_aware:
        if len(args.paths) != 2:
            parser.error("--tile-aware requires exactly two run directories: mp37_dir mp137_dir")
        mp37_dir, mp137_dir = args.paths
        tile_pairs = [
            (
                "UPSTREAM ENTRY mp37 vs mp137",
                mp37_dir / "kdm6_upstream_entry_kdm6_in.bin",
                mp137_dir / "kdm6_upstream_entry_kdm6ad_in.bin",
            ),
            (
                "UPSTREAM PRESELECT IJ1 mp37 vs mp137",
                mp37_dir / "kdm6_upstream_preselect_ij1_kdm6_in.bin",
                mp137_dir / "kdm6_upstream_preselect_ij1_kdm6ad_in.bin",
            ),
            (
                "UPSTREAM PRESELECT IJ2 mp37 vs mp137",
                mp37_dir / "kdm6_upstream_preselect_ij2_kdm6_in.bin",
                mp137_dir / "kdm6_upstream_preselect_ij2_kdm6ad_in.bin",
            ),
            (
                "DRIVER INPUT IJ1 mp37 vs mp137",
                mp37_dir / "kdm6_driver_step1_ij1_kdm6_in.bin",
                mp137_dir / "kdm6_driver_step1_ij1_kdm6ad_in.bin",
            ),
            (
                "DRIVER INPUT IJ2 mp37 vs mp137",
                mp37_dir / "kdm6_driver_step1_ij2_kdm6_in.bin",
                mp137_dir / "kdm6_driver_step1_ij2_kdm6ad_in.bin",
            ),
            (
                "DRIVER OUTPUT IJ1 mp37 vs mp137",
                mp37_dir / "kdm6_driver_step1_ij1_kdm6_out.bin",
                mp137_dir / "kdm6_driver_step1_ij1_kdm6ad_out.bin",
            ),
        ]
        failures = 0
        for label, ref_path, got_path in tile_pairs:
            failures += compare_pair(label, ref_path, got_path)
        if failures:
            print(f"\nBITWISE RESULT: FAIL ({failures} field-pair failures)")
            return 1
        print("\nBITWISE RESULT: PASS")
        return 0

    if len(args.paths) != 1:
        parser.error("default compare mode requires exactly one directory")
    d = args.paths[0]
    failures = 0
    if args.driver:
        failures += compare_pair(
            "DRIVER INPUT mp37 vs mp137",
            d / "kdm6_driver_step1_kdm6_in.bin",
            d / "kdm6_driver_step1_kdm6ad_in.bin",
        )
    failures += compare_pair("INPUT mp37 vs mp137", d / "kdm6_step1_kdm6_in.bin", d / "kdm6_step1_kdm6ad_in.bin")
    failures += compare_pair("OUTPUT mp37 vs mp137", d / "kdm6_step1_kdm6_out.bin", d / "kdm6_step1_kdm6ad_out.bin")
    if failures:
        print(f"\nBITWISE RESULT: FAIL ({failures} field-pair failures)")
        return 1
    print("\nBITWISE RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
