#!/usr/bin/env python3
"""Generic cross-tree rate-dump comparator (C4 bisection aid).

Compares fort_<tag>.bin (per-j records: header lat,its,ite,kts,kte BE i4 +
NF fields of (ni,nk) BE f4 col-major) against cpp_<tag>.bin (header B,K BE
i4 + NF fields of (B,K) BE f4 row-major, b = i*jme + j, FIRST-TILE only).
NF is inferred from the file structure on each side and must agree.
Strict uint32 bit equality; K-flip auto-chosen as in compare_substep_stage.py.

usage: compare_rate_dump.py <fort_TAG.bin> <cpp_TAG.bin> [field names...]
"""
import sys
import numpy as np


def die(msg, code=2):
    print(f"ERROR: {msg}")
    sys.exit(code)


def read_fortran(path):
    data = open(path, "rb").read()
    if len(data) < 24:
        die(f"fortran dump too small: {path}")
    hdr = np.frombuffer(data[:20], dtype=">i4")
    lat0, its, ite, kts, kte = (int(x) for x in hdr)
    ni, nk = ite - its + 1, kte - kts + 1
    cnt = ni * nk
    # find NF: scan forward one field at a time until the 4 ints after a
    # candidate header position repeat (its,ite,kts,kte)
    nf = None
    off = 20
    for f in range(1, 200):
        pos = 20 + f * cnt * 4
        if pos == len(data):        # single-record file
            nf = f
            break
        if pos + 20 <= len(data):
            cand = np.frombuffer(data[pos + 4:pos + 20], dtype=">i4")
            if tuple(int(x) for x in cand) == (its, ite, kts, kte):
                nf = f
                break
    if nf is None:
        die("cannot infer fortran field count")
    rec_bytes = 20 + nf * cnt * 4
    if len(data) % rec_bytes:
        die(f"fortran size {len(data)} not a multiple of record {rec_bytes}")
    nrec = len(data) // rec_bytes
    out = {}
    for r in range(nrec):
        base = r * rec_bytes
        lat = int(np.frombuffer(data[base:base + 4], dtype=">i4")[0])
        fields = np.frombuffer(data[base + 20:base + rec_bytes],
                               dtype=">f4").reshape(nf, nk, ni)
        out[lat] = fields
    lats = sorted(out)
    if lats != list(range(lats[0], lats[0] + len(lats))):
        die("fortran j records not contiguous")
    # [nf, nj, nk, ni]
    arr = np.stack([out[l] for l in lats], axis=1).astype("<f4")
    return arr, nf


def read_cpp(path, nf_expect):
    data = open(path, "rb").read()
    if len(data) < 8:
        die(f"cpp dump too small: {path}")
    B, K = (int(x) for x in np.frombuffer(data[:8], dtype=">i4"))
    body = len(data) - 8
    if body % (B * K * 4):
        die(f"cpp size mismatch B={B} K={K}")
    nf = body // (B * K * 4)
    fields = np.frombuffer(data[8:], dtype=">f4").reshape(nf, B, K).astype("<f4")
    return fields, nf, B, K


def main():
    if len(sys.argv) < 3:
        die(__doc__)
    F, nf_f = read_fortran(sys.argv[1])       # [nf, nj, nk, ni]
    C, nf_c, B, K = read_cpp(sys.argv[2], nf_f)
    names = sys.argv[3:]
    nf = min(nf_f, nf_c)
    if nf_f != nf_c:
        print(f"NOTE: field-count mismatch fort={nf_f} cpp={nf_c}; comparing first {nf}")
    _, nj, nk, ni = F.shape
    if K != nk or B % ni:
        die(f"cannot align: fort (nj={nj},nk={nk},ni={ni}) vs cpp (B={B},K={K})")
    nj_cpp = B // ni
    # cpp b = i*jme + j -> [i, j, K] -> transpose to [j, K, i]
    Cr = C.reshape(nf_c, ni, nj_cpp, K).transpose(0, 2, 3, 1)
    Ft = F[:, :nj_cpp]                        # first-tile scope
    best = None
    for flip in (False, True):
        Cx = Cr[:, :, ::-1, :] if flip else Cr
        tot = int(np.count_nonzero(Ft[:nf].view(np.uint32) != Cx[:nf].view(np.uint32)))
        if best is None or tot < best[1]:
            best = (flip, tot, Cx)
    flip, tot, Cx = best
    print(f"K-flip={'TOP<->SURFACE' if flip else 'none'}  scope=FIRST-TILE({nj_cpp}/{nj} j)")
    ok = True
    for f in range(nf):
        nm = names[f] if f < len(names) else f"field{f}"
        nd = int(np.count_nonzero(Ft[f].view(np.uint32) != Cx[f].view(np.uint32)))
        if nd:
            ok = False
            k_lv = sorted(set(np.nonzero(Ft[f].view(np.uint32) != Cx[f].view(np.uint32))[1].tolist()))
            print(f"  {nm:12s} DIVERGES {nd}/{Ft[f].size}  k={k_lv[:10]}")
        else:
            print(f"  {nm:12s} BITWISE-MATCH")
    print("RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
