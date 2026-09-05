#!/usr/bin/env python3
"""Generic cross-tree rate-dump comparator (C4 bisection aid).

Compares fort_<tag>.bin (per-j records: header lat,its,ite,kts,kte BE i4 +
NF fields of (ni,nk) BE f4 col-major) against cpp_<tag>.bin (header B,K BE
i4 + NF fields of (B,K) BE f4 row-major, b = i*jme + j, FIRST-TILE only).
NF is inferred from the file structure on each side. Strict uint32 bit equality.

WHAT THIS TOOL REQUIRES YOU TO DECLARE (owner PR E). Three properties used to be
guessed, and each guess made a clean result mean less than it appeared to:

  * --k-order {same,flip} is MANDATORY. The orientation used to be chosen by
    whichever flip produced FEWER differences, which fits the orientation to the
    data: on a genuinely diverging pair the tool picked the reading that minimised
    the divergence it then reported. The other orientation's count is still printed,
    as information, but never decides anything.
  * --column-map names the b <-> (i,j) packing rather than baking it in. Only
    i_major (b = i*jme + j) is implemented; naming it makes it a stated assumption
    instead of a hidden one.
  * --min-fields N requires N field NAMES. Comparing "the first N of each side"
    assumes field i on one side is field i on the other, and nothing in the files
    establishes that. The names do not verify the correspondence either — they make
    the claim explicit and reviewable, which is the most this format allows.

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
  * A partial comparison CANNOT report PASS or exit 0. FIRST-TILE scope or a
    SUBSET of fields yields PARTIAL-CLEAN and exit 3, because a caller reading
    only the return code would otherwise take a first-tile subset comparison for
    a full validation. The label alone did not stop that: it was printed for a
    human, while exit 0 was what automation read.

exit: 0 full-domain, all-fields, bit-clean     1 differences found
      2 hard error (malformed/degenerate)      3 clean but PARTIAL

usage: compare_rate_dump.py <fort_TAG.bin> <cpp_TAG.bin>
           --k-order {same,flip} [--column-map i_major]
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
                         "sides must have >= N, and N names must be given); "
                         "the result is PARTIAL, never PASS")
    ap.add_argument("--k-order", required=True, choices=("same", "flip"),
                    help="DECLARED K orientation of the cpp dump relative to the "
                         "fortran one. Required: choosing it by whichever flip "
                         "differs less fits the orientation to the data")
    ap.add_argument("--column-map", default="i_major", choices=("i_major",),
                    help="b <-> (i,j) packing of the cpp dump; i_major is "
                         "b = i*jme + j. Named so it is a stated assumption")
    args = ap.parse_intermixed_args()

    F, nf_f = read_fortran(args.fort)         # [nf, nj, nk, ni]
    C, nf_c, B, K = read_cpp(args.cpp)

    if args.min_fields is not None:
        nf = args.min_fields
        if nf <= 0 or nf_f < nf or nf_c < nf:
            die(f"--min-fields {nf} exceeds a side's field count "
                f"(fort={nf_f} cpp={nf_c})")
        subset = (nf_f != nf) or (nf_c != nf)
        # A field-count mismatch means the two sides' field LISTS differ, so
        # "the first N of each" is a correspondence claim about data that does
        # not carry one. Names do not prove it; they put it on the record.
        if len(args.names) < nf:
            die(f"--min-fields {nf} needs {nf} field names: comparing the first "
                f"{nf} of each side asserts field i means the same thing in both "
                f"dumps, and nothing in the files establishes that (got "
                f"{len(args.names)} names)")
    else:
        if nf_f != nf_c:
            die(f"field-count mismatch fort={nf_f} cpp={nf_c} — a truncated "
                "dump parses as fewer fields; refusing the silent-subset "
                "compare. If the mismatch is a KNOWN cross-tree difference, "
                "opt in with --min-fields N.")
        nf = nf_f
        subset = False

    _, nj, nk, ni = F.shape
    # Raw equality of identical NaN/Inf words is not a physically interpretable
    # rate comparison.  Keep the documented ``brs`` exception (empty-cell
    # sentinel) and refuse the other fields before any orientation verdict.
    for label, data in (("fortran", F), ("cpp", C)):
        for field in range(nf):
            if not np.all(np.isfinite(data[field])):
                die(f"INSUFFICIENT {label} rate dump: field {field} has "
                    "non-finite values; no physical rate verdict")
    if K != nk or ni <= 0 or B % ni:
        die(f"cannot align: fort (nj={nj},nk={nk},ni={ni}) vs cpp (B={B},K={K})")
    nj_cpp = B // ni
    if nj_cpp > nj:
        die(f"cpp covers more j ({nj_cpp}) than fortran ({nj})")
    # the DECLARED packing (only i_major exists today); b = i*jme + j
    #   -> [i, j, K] -> transpose to [j, K, i]
    assert args.column_map == "i_major"       # argparse restricts the choices
    Cr = C.reshape(nf_c, ni, nj_cpp, K).transpose(0, 2, 3, 1)
    Ft = F[:, :nj_cpp]                        # first-tile scope
    # The DECLARED orientation, not the flattering one. Picking the flip with
    # fewer differences meant that on a genuinely diverging pair the tool chose
    # the reading that minimised the divergence it then reported.
    flip = args.k_order == "flip"
    Cx = Cr[:, :, ::-1, :] if flip else Cr
    tot = int(np.count_nonzero(u32(Ft[:nf]) != u32(Cx[:nf])))
    # the other orientation, as INFORMATION — it decides nothing
    other = Cr if flip else Cr[:, :, ::-1, :]
    other_tot = int(np.count_nonzero(u32(Ft[:nf]) != u32(other[:nf])))

    # FALSE-PASS GUARD (degenerate data): a 0-diff result under BOTH flips is
    # only meaningful if some compared field actually varies along K —
    # otherwise the dump is empty/uniform/never-fired and PASS is spurious.
    if tot == 0 and other_tot == 0:
        kvar = any(
            int(np.count_nonzero(u32(Ft[f][:, :-1, :]) !=
                                 u32(Ft[f][:, 1:, :]))) > 0
            for f in range(nf))
        if not kvar:
            die("DEGENERATE: 0 diffs under BOTH K-flips and no compared field "
                "varies along K (empty/uniform/never-fired dump) — refusing "
                "to report PASS.")

    first_tile = nj_cpp != nj
    scope = (f"FIRST-TILE({nj_cpp}/{nj} j)" if first_tile else "FULL-DOMAIN")
    label = scope + (f" SUBSET(first {nf}: fort={nf_f} cpp={nf_c})" if subset else "")
    print(f"K-order={args.k_order} (declared; the other reading gives "
          f"{other_tot} diffs)  column-map={args.column_map}  scope={label}")
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
    # A PARTIAL comparison cannot report PASS or exit 0. The label was printed for
    # a human while exit 0 was what automation read, so a first-tile subset compare
    # could be consumed as a full validation.
    partial = first_tile or subset
    if not ok:
        verdict, code = "FAIL", 1
    elif partial:
        verdict, code = "PARTIAL-CLEAN", 3
    else:
        verdict, code = "PASS", 0
    print(f"RESULT: {verdict} ({label})")
    if partial and ok:
        print("  NOT a full validation: bit-clean only over the compared scope.")
    sys.exit(code)


if __name__ == "__main__":
    main()
