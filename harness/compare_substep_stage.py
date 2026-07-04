#!/usr/bin/env python3
"""§34 sed-bisection harness — ANALYSIS tool (paired with the double-gated
KDM6_SUBSTEP_DUMP dump source in module_mp_kdm6.F + coordinator.cpp). The dumps are
DORMANT in the production build (compile-macro OFF in configure.wrf/CMakeLists);
to regenerate the fort_substep_*/cpp_substep_* inputs this reads, rebuild BOTH trees
with -DKDM6_SUBSTEP_DUMP and run with the KDM6_SUBSTEP_DUMP env dir set. This script
does NOT run in normal builds and produces no side effects.

Cross-tree per-substep STAGE localization.

Strict raw-float32 CELL-ALIGNED bitwise comparison of Fortran fort_substep_<tag>.bin
(mp37) vs C++ cpp_substep_<tag>.bin (mp137). NO tolerance — uint32 bit equality only.

Safety (Codex stop-review: comparator must not falsely pass invalid/non-aligned dumps):
  * HARD ERROR (exit 2) on: missing/empty file, bad header (its>ite, kts>kte, B<=0,
    K<=0), truncation (bytes consumed != file length), zero cells, non-contiguous j.
  * HARD FAIL (exit 2) if the two dumps cannot be cell-aligned (B != ni*nj or K != nk
    => halo/dim mismatch). We do NOT fall back to any order-insensitive heuristic.
  * Alignment is explicit: Fortran record = one j-tile, q(its:ite,kts:kte) col-major
    (i fastest) => per-field canonical [j,k,i]. C++ (B,K) row-major, b=i*jme+j
    (state.cpp) => reshape(im=ni, jme=nj, K)[i,j,K] -> transpose [j,K,i]. K-flip
    (runtime flip_k: sed K=0=top vs Fortran K=0=surface) tried both ways; the physical
    orientation is the one giving far fewer diffs (vertical reversal is unambiguous).
  * PASS (exit 0) ONLY if every field is cell-for-cell bit-identical under one flip.

Field order (both): qv qc qr qi qs qg nc nr ni nccn brs t
"""
import sys, os, struct, numpy as np

FIELDS = ["qv","qc","qr","qi","qs","qg","nc","nr","ni","nccn","brs","t"]

def local_libtorch_dylib():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    return os.path.join(root, "libtorch", "install", "lib", "libkdm6_c.dylib")

def die(msg, code=2):
    print(f"ERROR: {msg}"); sys.exit(code)

def read_fortran(path):
    if not os.path.exists(path): die(f"fortran dump missing: {path}")
    data = open(path,"rb").read()
    if len(data) == 0: die(f"fortran dump empty: {path}")
    off=0; n=len(data); recs={}  # lat -> {field: (nk,ni) array}
    its0=ite0=kts0=kte0=None
    while off < n:
        if off+20 > n: die(f"fortran header truncated at byte {off}")
        lat,its,ite,kts,kte = struct.unpack(">5i", data[off:off+20]); off+=20
        if its>ite or kts>kte: die(f"fortran bad header lat={lat} its={its} ite={ite} kts={kts} kte={kte}")
        if its0 is None: its0,ite0,kts0,kte0 = its,ite,kts,kte
        elif (its,ite,kts,kte)!=(its0,ite0,kts0,kte0): die("fortran tile bounds vary across records")
        ni=ite-its+1; nk=kte-kts+1; cnt=ni*nk
        rec={}
        for f in FIELDS:
            nb=cnt*4
            if off+nb>n: die(f"fortran field {f} truncated (lat={lat})")
            rec[f]=np.frombuffer(data[off:off+nb],dtype=">f4").astype("<f4").reshape(nk,ni); off+=nb
        if lat in recs: die(f"fortran duplicate lat={lat}")
        recs[lat]=rec
    if off!=n: die(f"fortran trailing bytes: consumed {off} of {n}")
    if not recs: die("fortran no records")
    lats=sorted(recs)
    if lats!=list(range(lats[0],lats[0]+len(lats))): die(f"fortran non-contiguous j: {lats[:3]}..{lats[-3:]}")
    ni=ite0-its0+1; nk=kte0-kts0+1; nj=len(lats)
    out={}
    for f in FIELDS:
        out[f]=np.stack([recs[j][f] for j in lats],axis=0)  # [j,k,i]
    return out, (nj,nk,ni)

def read_cpp(path):
    if not os.path.exists(path): die(f"cpp dump missing: {path}")
    data=open(path,"rb").read()
    if len(data)<8: die(f"cpp dump too short: {path}")
    B,K = struct.unpack(">2i", data[:8]); off=8
    if B<=0 or K<=0: die(f"cpp bad header B={B} K={K}")
    cnt=B*K; need=8+12*cnt*4
    if len(data)!=need: die(f"cpp size mismatch: have {len(data)} need {need} (B={B} K={K})")
    out={}
    for f in FIELDS:
        nb=cnt*4
        out[f]=np.frombuffer(data[off:off+nb],dtype=">f4").astype("<f4"); off+=nb
    return out, (B,K)

def main():
    if len(sys.argv)!=3:
        die("usage: compare_substep_stage.py <fort_substep_TAG.bin> <cpp_substep_TAG.bin>")
    # STALENESS GUARD (Codex: a stale peer dump can false-pass). A dump is stale iff its PRODUCING
    # BINARY changed after it: fort_* must be newer than wrf.exe (re-run mp37 after any Fortran rebuild);
    # cpp_* must be newer than the installed libkdm6_c.dylib (re-run mp137 after any C++ lib rebuild).
    _ssd = os.path.dirname(os.path.abspath(sys.argv[1]))
    _wrf = os.path.join(_ssd, 'wrf.exe')
    _lib = local_libtorch_dylib()
    if os.path.exists(_wrf) and os.path.getmtime(sys.argv[1]) < os.path.getmtime(_wrf):
        die("STALE fortran dump: %s predates wrf.exe — re-run mp37 (dump is from an older Fortran build)" % sys.argv[1])
    if os.path.exists(_lib) and os.path.getmtime(sys.argv[2]) < os.path.getmtime(_lib):
        die("STALE cpp dump: %s predates libkdm6_c.dylib — re-run mp137 (dump is from an older C++ lib)" % sys.argv[2])
    F,(nj,nk,ni) = read_fortran(sys.argv[1])
    C,(B,K)      = read_cpp(sys.argv[2])
    print(f"fortran: nj={nj} nk={nk} ni={ni} (cells={nj*nk*ni})   cpp: B={B} K={K} (cells={B*K})")
    # MALFORMED-DUMP GUARD (Codex): reject non-finite / degenerate dumps before any verdict — identical
    # garbage (NaN/inf from uninitialized memory, or all-constant) on both trees would else compare bit-equal
    # and FALSE-PASS. Finiteness on all fields EXCEPT brs: Fortran writes -inf into brs empty cells
    # (uninitialized memory) — the documented AD-limit out-of-scope field (see brs-ad-vs-bitwise memory);
    # its non-finite values are EXPECTED, not malformed. The other 11 fields are finite everywhere.
    for nm, D in (("fortran", F), ("cpp", C)):
        for f in FIELDS:
            if f == "brs":
                continue
            if not np.all(np.isfinite(D[f].astype(np.float64))):
                die(f"MALFORMED {nm} dump: field '{f}' has non-finite (NaN/inf) values — refusing verdict")
    # non-trivial: t (temperature) must vary across cells; all-constant ⇒ degenerate/empty dump.
    for nm, D in (("fortran", F), ("cpp", C)):
        if float(np.ptp(D["t"]))==0.0:
            die(f"DEGENERATE {nm} dump: t is constant across all cells — empty/uniform dump; verdict meaningless")
    # C++ dumps the FIRST WRF tile only (kdm6_substep_call==1); Fortran appends ALL
    # tiles (no per-call guard) -> nj_fort >= nj_cpp. Align the C++ tile against the
    # MATCHING leading Fortran j-records (first tile, lowest lat). Require exact
    # cell-count divisibility (no halo/partial) else hard-fail — NOT order-insensitive.
    if K!=nk:
        die(f"CANNOT ALIGN: cpp K={K} != fortran nk={nk}")
    if B % ni != 0:
        die(f"CANNOT ALIGN: cpp B={B} not divisible by fortran ni={ni}")
    nj_cpp = B // ni
    if nj_cpp > nj:
        die(f"CANNOT ALIGN: cpp tile nj={nj_cpp} > fortran nj={nj}")
    if nj_cpp != nj:
        print(f"NOTE: cpp covers first tile only (nj_cpp={nj_cpp} of fortran nj={nj}); "
              f"comparing leading {nj_cpp} j-records (first WRF tile).")
    # subset Fortran to the first tile (leading nj_cpp j-records)
    F = {f: F[f][:nj_cpp] for f in FIELDS}   # [j(0..nj_cpp-1), k, i]
    # cpp canonical: reshape [i,j,K] -> [j,K,i]
    cpp={f: C[f].reshape(ni,nj_cpp,K).transpose(1,2,0) for f in FIELDS}  # [j,K,i]
    res={}
    for flip in (False,True):
        tot=0; per={}
        for f in FIELDS:
            cc = cpp[f][:, ::-1, :] if flip else cpp[f]      # flip K axis
            d = int(np.count_nonzero(F[f].view(np.uint32)!=cc.copy().view(np.uint32)))
            per[f]=d; tot+=d
        res[flip]=(tot,per)
    (tot,per),flip = (res[False],False) if res[False][0]<=res[True][0] else (res[True],True)
    ncell = nj_cpp*nk*ni
    # FALSE-PASS GUARD 1 (alignment ambiguity): if BOTH K-flips give 0 total diffs, the data is K-symmetric
    # / degenerate / empty and the "match" does NOT validate alignment — a min-diffs auto-pick would report
    # a spurious PASS. Require a non-trivial K-varying reference field to disambiguate; else HARD-FAIL.
    if res[False][0]==0 and res[True][0]==0:
        # confirm with a field that should vary in K (t = temperature, monotonic-ish in K)
        tvar = int(np.count_nonzero(F["t"][:, :-1, :].view(np.uint32) != F["t"][:, 1:, :].view(np.uint32)))
        if tvar > 0:
            print("AMBIGUOUS ALIGNMENT: both K-flips give 0 diffs on K-varying data — comparator cannot "
                  "validate the flip; refusing to report PASS."); sys.exit(2)
        print("DEGENERATE: both K-flips 0 diffs AND t is K-constant (empty/uniform tile) — not a meaningful "
              "bitwise validation."); sys.exit(2)
    print(f"K-flip={'TOP<->SURFACE' if flip else 'none'}  (chosen: fewer diffs; other flip tot={res[not flip][0]})")
    allmatch=True
    for f in FIELDS:
        if per[f]==0: print(f"  {f:5s} BITWISE-MATCH ({ncell} cells)")
        else: allmatch=False; print(f"  {f:5s} DIVERGES  {per[f]}/{ncell} cells")
    # FALSE-PASS GUARD 2 (scope): the C++ dump is FIRST-TILE only when nj_cpp<nj. A PASS validates ONLY the
    # leading tile, NOT the full domain — label it so a first-tile pass is never mistaken for full bitwise.
    scope = "FIRST-TILE(%d/%d j) " % (nj_cpp, nj) if nj_cpp != nj else "FULL-DOMAIN "
    print("STAGE RESULT:", (scope+"BITWISE PASS") if allmatch else "FAIL (diverges)")
    sys.exit(0 if allmatch else 1)

if __name__=="__main__":
    main()
