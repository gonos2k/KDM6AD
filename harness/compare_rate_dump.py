#!/usr/bin/env python3
"""Generic cross-tree rate-dump comparator (C4 bisection aid).

Compares fort_<tag>.bin (per-j records: header lat,its,ite,kts,kte BE i4 +
NF fields of (ni,nk) BE f4 col-major) against cpp_<tag>.bin (header B,K BE
i4 + NF fields of (B,K) BE f4 row-major, b = i*jme + j, FIRST-TILE only).
NF is inferred from the file structure on each side. Strict uint32 bit
equality; K-flip auto-chosen as in compare_substep_stage.py.

False-pass guards (Codex stop-review: an incomplete dump must never PASS):
  * HARD ERROR (exit 2) on: missing/too-small file, bad header (its>ite,
    kts>kte, B<=0, K<=0), size not a whole number of records/fields,
    duplicate or non-contiguous j records.
  * HARD ERROR (exit 2) if the two sides' field counts DIFFER — a
    truncated dump parses as "fewer fields" and would otherwise be
    compared as a silent subset. A KNOWN cross-tree field-count mismatch
    must be opted into with --min-fields N (both sides must still have
    >= N fields), and the RESULT line then carries a SUBSET label.
  * HARD ERROR (exit 2) if the comparison is bit-clean under BOTH K-flips
    AND no compared field varies along K — all-zero / never-fired /
    degenerate dumps must not report PASS (mirrors FALSE-PASS GUARD 1 of
    compare_substep_stage.py).
  * The RESULT line always carries the scope (FIRST-TILE vs FULL-DOMAIN)
    and, when --min-fields was used, the SUBSET label — a first-tile or
    subset pass must never read as a full validation.

usage: compare_rate_dump.py <fort_TAG.bin> <cpp_TAG.bin>
           [--min-fields N] [field names...]
"""
import argparse
import sys
import numpy as np


def die(msg, code=2):
    print(f"ERROR: {msg}")
    sys.exit(code)


def u32(a):
    # Raw-bit uint32 view. .view() needs a C-contiguous last axis; slices and
    # transposes here are non-contiguous, so make a contiguous copy first
    # (small arrays; correctness over the micro-cost).
    return np.ascontiguousarray(a).view(np.uint32)


def read_fortran(path):
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) < 24:
        die(f"fortran dump missing/too small: {path}")
    hdr = np.frombuffer(data[:20], dtype=">i4")
    lat0, its, ite, kts, kte = (int(x) for x in hdr)
    if its > ite or kts > kte:
        die(f"fortran bad header its={its} ite={ite} kts={kts} kte={kte}")
    ni, nk = ite - its + 1, kte - kts + 1
    cnt = ni * nk
    if cnt <= 0:
        die("fortran zero cells")
    # find NF: scan forward one field at a time until the 4 ints after a
    # candidate header position repeat (its,ite,kts,kte)
    nf = None
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
        die("cannot infer fortran field count (corrupt or truncated dump)")
    rec_bytes = 20 + nf * cnt * 4
    if len(data) % rec_bytes:
        die(f"fortran size {len(data)} not a multiple of record {rec_bytes} "
            "(truncated dump)")
    nrec = len(data) // rec_bytes
    out = {}
    for r in range(nrec):
        base = r * rec_bytes
        rhdr = np.frombuffer(data[base:base + 20], dtype=">i4")
        lat = int(rhdr[0])
        if tuple(int(x) for x in rhdr[1:]) != (its, ite, kts, kte):
            die(f"fortran tile bounds vary at record {r}")
        if lat in out:
            die(f"fortran duplicate j record lat={lat} (stale append-mode dump "
                "— clean fort_*.bin and re-run)")
        out[lat] = np.frombuffer(data[base + 20:base + rec_bytes],
                                 dtype=">f4").reshape(nf, nk, ni)
    lats = sorted(out)
    if lats != list(range(lats[0], lats[0] + len(lats))):
        die("fortran j records not contiguous")
    # [nf, nj, nk, ni]
    arr = np.stack([out[l] for l in lats], axis=1).astype("<f4")
    return arr, nf


def read_cpp(path):
    with open(path, "rb") as fh:
        data = fh.read()
    if len(data) < 12:
        die(f"cpp dump missing/too small: {path}")
    B, K = (int(x) for x in np.frombuffer(data[:8], dtype=">i4"))
    if B <= 0 or K <= 0:
        die(f"cpp bad header B={B} K={K}")
    body = len(data) - 8
    if body % (B * K * 4):
        die(f"cpp size mismatch B={B} K={K} (truncated dump)")
    nf = body // (B * K * 4)
    if nf == 0:
        die("cpp dump has zero fields")
    fields = np.frombuffer(data[8:], dtype=">f4").reshape(nf, B, K).astype("<f4")
    return fields, nf, B, K


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("fort")
    ap.add_argument("cpp")
    ap.add_argument("names", nargs="*")
    ap.add_argument("--min-fields", type=int, default=None,
                    help="explicit opt-in for a KNOWN cross-tree field-count "
                         "mismatch: compare exactly the first N fields (both "
                         "sides must have >= N); RESULT carries a SUBSET label")
    args = ap.parse_intermixed_args()

    F, nf_f = read_fortran(args.fort)         # [nf, nj, nk, ni]
    C, nf_c, B, K = read_cpp(args.cpp)

    if args.min_fields is not None:
        nf = args.min_fields
        if nf <= 0 or nf_f < nf or nf_c < nf:
            die(f"--min-fields {nf} exceeds a side's field count "
                f"(fort={nf_f} cpp={nf_c})")
        subset = (nf_f != nf) or (nf_c != nf)
    else:
        if nf_f != nf_c:
            die(f"field-count mismatch fort={nf_f} cpp={nf_c} — a truncated "
                "dump parses as fewer fields; refusing the silent-subset "
                "compare. If the mismatch is a KNOWN cross-tree difference, "
                "opt in with --min-fields N.")
        nf = nf_f
        subset = False

    _, nj, nk, ni = F.shape
    if K != nk or ni <= 0 or B % ni:
        die(f"cannot align: fort (nj={nj},nk={nk},ni={ni}) vs cpp (B={B},K={K})")
    nj_cpp = B // ni
    if nj_cpp > nj:
        die(f"cpp covers more j ({nj_cpp}) than fortran ({nj})")
    # cpp b = i*jme + j -> [i, j, K] -> transpose to [j, K, i]
    Cr = C.reshape(nf_c, ni, nj_cpp, K).transpose(0, 2, 3, 1)
    Ft = F[:, :nj_cpp]                        # first-tile scope
    best = None
    for flip in (False, True):
        Cx = Cr[:, :, ::-1, :] if flip else Cr
        tot = int(np.count_nonzero(u32(Ft[:nf]) != u32(Cx[:nf])))
        if best is None or tot < best[1]:
            best = (flip, tot, Cx)
    flip, tot, Cx = best

    # FALSE-PASS GUARD (degenerate data): a 0-diff result under BOTH flips is
    # only meaningful if some compared field actually varies along K —
    # otherwise the dump is empty/uniform/never-fired and PASS is spurious.
    other_tot = int(np.count_nonzero(
        u32(Ft[:nf]) !=
        u32((Cr[:, :, ::-1, :] if not flip else Cr)[:nf])))
    if tot == 0 and other_tot == 0:
        kvar = any(
            int(np.count_nonzero(u32(Ft[f][:, :-1, :]) !=
                                 u32(Ft[f][:, 1:, :]))) > 0
            for f in range(nf))
        if not kvar:
            die("DEGENERATE: 0 diffs under BOTH K-flips and no compared field "
                "varies along K (empty/uniform/never-fired dump) — refusing "
                "to report PASS.")

    scope = (f"FIRST-TILE({nj_cpp}/{nj} j)" if nj_cpp != nj else "FULL-DOMAIN")
    label = scope + (f" SUBSET(first {nf}: fort={nf_f} cpp={nf_c})" if subset else "")
    print(f"K-flip={'TOP<->SURFACE' if flip else 'none'}  scope={label}")
    ok = True
    for f in range(nf):
        nm = args.names[f] if f < len(args.names) else f"field{f}"
        nd = int(np.count_nonzero(u32(Ft[f]) != u32(Cx[f])))
        if nd:
            ok = False
            k_lv = sorted(set(np.nonzero(
                u32(Ft[f]) != u32(Cx[f]))[1].tolist()))
            print(f"  {nm:12s} DIVERGES {nd}/{Ft[f].size}  k={k_lv[:10]}")
        else:
            print(f"  {nm:12s} BITWISE-MATCH")
    print(f"RESULT: {'PASS' if ok else 'FAIL'} ({label})")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
