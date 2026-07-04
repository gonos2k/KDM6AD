#!/usr/bin/env python3
"""STRICT raw-bit (uint-view) comparison of two NetCDF/HDF5 history files (mp37 vs mp137).
NO tolerance — uint32/uint64 bit equality per element, at the LAST common time frame.
HDF5 byte layout/metadata differ even for identical data, so we compare DATA VARIABLES, not raw bytes.

usage: strict_bitwise_nc.py <file37> <file137> [frame_index]
  frame_index: 0-based Time index to compare (default = last common frame).
exit 0 iff every common numeric variable is bit-identical AND variable sets match.
"""
import sys, numpy as np, netCDF4 as nc

def main():
    a = nc.Dataset(sys.argv[1], "r"); b = nc.Dataset(sys.argv[2], "r")
    a.set_auto_maskandscale(False); b.set_auto_maskandscale(False)
    na = a.dimensions["Time"].size if "Time" in a.dimensions else 1
    nb = b.dimensions["Time"].size if "Time" in b.dimensions else 1
    explicit = len(sys.argv) > 3
    frame = int(sys.argv[3]) if explicit else min(na, nb) - 1
    label = "selected" if explicit else "last common"
    print(f"# {sys.argv[1].split('/')[-1]} (frames={na}) vs {sys.argv[2].split('/')[-1]} (frames={nb})")
    print(f"# strict uint-bitwise compare at {label} frame index {frame}")
    common = sorted(set(a.variables) & set(b.variables))
    only_a = sorted(set(a.variables) - set(b.variables))
    only_b = sorted(set(b.variables) - set(a.variables))
    n_match = n_diff = n_skip = 0
    diffs = []
    for v in common:
        va, vb = a.variables[v], b.variables[v]
        if va.dtype.kind not in ("f", "i", "u"):
            n_skip += 1; continue
        if va.dimensions != vb.dimensions:
            diffs.append((v, f"DIM MISMATCH {va.dimensions} vs {vb.dimensions}")); n_diff += 1; continue
        if "Time" in va.dimensions:
            try: xa = np.asarray(va[frame]); xb = np.asarray(vb[frame])
            except IndexError: diffs.append((v, "frame oob")); n_diff += 1; continue
        else:
            xa = np.asarray(va[:]); xb = np.asarray(vb[:])
        if xa.shape != xb.shape:
            diffs.append((v, f"SHAPE {xa.shape} vs {xb.shape}")); n_diff += 1; continue
        if xa.dtype != xb.dtype:
            diffs.append((v, f"DTYPE {xa.dtype} vs {xb.dtype}")); n_diff += 1; continue
        # raw-bit view
        itype = {1:np.uint8,2:np.uint16,4:np.uint32,8:np.uint64}.get(xa.dtype.itemsize)
        ua = xa.view(itype); ub = xb.view(itype)
        ndiff = int(np.count_nonzero(ua != ub))
        if ndiff == 0:
            n_match += 1
        else:
            n_diff += 1
            mx = float(np.abs(xa.astype(np.float64) - xb.astype(np.float64)).max())
            diffs.append((v, f"DIVERGES {ndiff}/{xa.size} cells (max|Δ|={mx:.3e})"))
    print(f"\nVARIABLES: {len(common)} common, {n_match} BITWISE-MATCH, {n_diff} DIFFER, {n_skip} non-numeric")
    if only_a: print(f"ONLY in file37 ({len(only_a)}): {only_a}")
    if only_b: print(f"ONLY in file137 ({len(only_b)}): {only_b}")
    if diffs:
        print("\nDIFFERING variables:")
        for v, msg in diffs: print(f"  {v:22s} {msg}")
    ok = (n_diff == 0) and (not only_a) and (not only_b)
    print(f"\nRESULT: {'STRICT BITWISE PASS' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
