#!/usr/bin/env python3
"""KDM6AD (mp=137) vs KDM6 (mp=37) wrfout parity harness.

A precision-changing port of a chaotic system CANNOT be validated by per-cell
bit-match at long lead times (single-prec mp37 ↔ double-prec mp137 → ULP
amplification through convective instability; see the project memory
"project-kdm6-warm-rain-autoconv-timing-gap"). The defensible criteria are:

  (1) EARLY-FRAME FORWARD CONSISTENCY — on identical ideal IC, the per-cell
      domain-MEAN relative difference at the first output frame(s) must sit at
      the float32-epsilon level (~1e-7..1e-5). That is the signature of "same
      physics, different arithmetic precision", not a scheme bug. A macroscopic
      mean seed (>~1e-3) at frame 1 would indicate a real inconsistency.
  (2) STABILITY — mp137 must integrate without NaN/Inf wherever mp37 does.
  (3) BULK AGREEMENT — domain-total water path / precip / per-species maxima
      should stay in-band (chaos redistributes; it should not systematically
      blow up or vanish a species).

Usage:
  kdm6_parity.py <wrfout_mp37> <wrfout_mp137> [--case NAME] [--early N]
"""
import sys, argparse
import numpy as np
import netCDF4 as nc

HYDRO = ["QVAPOR", "QCLOUD", "QRAIN", "QICE", "QSNOW", "QGRAUP"]
# KDM6 is a 6-class scheme: every one of these (+ θ) must be present in BOTH
# wrfouts. A missing field means the comparison cannot cover all species, so the
# gate must FAIL rather than silently checking only the intersection.
REQUIRED = ["T"] + HYDRO
TEMP_BASE = 300.0  # WRF 'T' is θ perturbation about 300 K


def f(d, v, fr):
    # Fill masked (_FillValue) cells with NaN so the FillValue-only-wrfout I/O
    # failure (libomp flush bug) surfaces as non-finite data instead of being
    # silently dropped — otherwise the gate would "pass" on a run with no real data.
    return np.ma.filled(d.variables[v][fr].astype(np.float64), np.nan)


def common_vars(a, b):
    return [v for v in (["T"] + HYDRO) if v in a.variables and v in b.variables]


def reldiff_field(va, vb, is_temp):
    """Domain max & mean relative difference. Temperature uses absolute θ
    (θ-pert+300) as the denominator so near-zero perturbations don't blow up."""
    if is_temp:
        a = va + TEMP_BASE
        b = vb + TEMP_BASE
        denom = np.abs(a)
    else:
        a, b = va, vb
        denom = np.maximum(np.abs(a), 1.0e-12)  # floor: below this is numerical zero
    # restrict to cells finite on BOTH sides (NaN/FillValue cells are excluded)
    finite = np.isfinite(a) & np.isfinite(b) & np.isfinite(denom)
    if not is_temp:
        finite &= np.maximum(np.abs(a), np.abs(b)) > 1.0e-9  # physically non-trivial
    if not finite.any():
        return float("nan"), float("nan")  # no comparable data -> signal upward
    rel = np.abs(a[finite] - b[finite]) / denom[finite]
    return float(rel.max()), float(rel.mean())


def scan_validity(d, nframes):
    """First frame with non-finite data. Returns (frame, var, kind):
      'no-data' = whole frame is NaN/FillValue (libomp I/O flush failure),
      'nan'     = partial NaN (real physics instability). None if all clean."""
    # Include the accumulated-precip fields: RAINNC/RAINC NaN/FillValue must be
    # caught here, otherwise the bulk np.nansum silently drops it and a run with
    # bad precip data slides through as "zero precip, in band".
    for fr in range(nframes):
        for v in HYDRO + ["T", "RAINNC", "RAINC"]:
            if v in d.variables:
                nbad = int(np.isnan(f(d, v, fr)).sum())
                if nbad == 0:
                    continue
                size = d.variables[v][fr].size
                return fr, v, ("no-data" if nbad == size else "nan")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mp37")
    ap.add_argument("mp137")
    ap.add_argument("--case", default="?")
    ap.add_argument("--early", type=int, default=1, help="frame index for the consistency probe")
    ap.add_argument("--expect-frames", type=int, default=None,
                    help="minimum frames BOTH runs must contain; fewer = aborted run = FAIL")
    args = ap.parse_args()

    a = nc.Dataset(args.mp37)
    b = nc.Dataset(args.mp137)
    na = a.dimensions["Time"].size
    nb = b.dimensions["Time"].size
    ncommon = min(na, nb)
    cv = common_vars(a, b)
    missing = [v for v in REQUIRED if v not in a.variables or v not in b.variables]
    # RAINNC (grid-scale accumulated precip, the KDM6 output) must exist to verify
    # precipitation parity; a run lacking it cannot pass on precip silently.
    if not ("RAINNC" in a.variables and "RAINNC" in b.variables):
        missing = missing + ["RAINNC"]

    print(f"\n================ PARITY: {args.case} ================")
    print(f"  mp37={args.mp37.split('/')[-1]} ({na} frames)")
    print(f"  mp137={args.mp137.split('/')[-1]} ({nb} frames)   common={ncommon}")
    print(f"  shared fields: {', '.join(cv)}")
    print(f"  required species: {', '.join(REQUIRED)}"
          + (f"   MISSING: {', '.join(missing)}" if missing else "   (all present)"))

    # ── (0) IC IDENTITY GATE ─────────────────────────────────────────────────
    # A scheme-consistency comparison is only valid if both runs start from the
    # SAME initial field. Some ideal cases (convrad) seed convection with a
    # non-deterministic `call random_seed` -> different IC per ideal.exe run ->
    # comparison is meaningless. Frame 0 must be bit-identical (or float-eps).
    ic_max = 0.0
    print("\n[0] IC identity (frame 0 — must match for a valid comparison)")
    for v in [x for x in ["T", "QVAPOR"] if x in a.variables and x in b.variables]:
        mx, mn = reldiff_field(f(a, v, 0), f(b, v, 0), v == "T")
        ic_max = max(ic_max, mx)
        print(f"    {v:>8}: max reldiff {mx:.2e}  mean {mn:.2e}")
    ic_valid = ic_max < 1.0e-5
    print(f"    -> {'IDENTICAL IC (valid)' if ic_valid else f'DIFFERENT IC (max {ic_max:.2e}) — COMPARISON INVALID'}")

    # ── (2) STABILITY ────────────────────────────────────────────────────────
    val37 = scan_validity(a, na)
    val137 = scan_validity(b, nb)
    def vstr(x):
        return "clean" if x is None else f"{x[2]} at frame {x[0]} ({x[1]})"
    print("\n[2] stability (NaN/FillValue scan)")
    print(f"    mp37 : {vstr(val37)}")
    print(f"    mp137: {vstr(val137)}")

    # ── (1) EARLY-FRAME FORWARD CONSISTENCY ──────────────────────────────────
    print("\n[1] early-frame forward consistency (domain mean reldiff = seed level)")
    print(f"    {'frame':>5} " + " ".join(f"{v:>22}" for v in cv))
    print(f"    {'':>5} " + " ".join(f"{'max / mean':>22}" for _ in cv))
    seed_mean = {}
    probe_frames = sorted(set([1, 2, 3, args.early, min(5, ncommon - 1)]))
    probe_frames = [fr for fr in probe_frames if 0 <= fr < ncommon]
    for fr in probe_frames:
        cells = []
        for v in cv:
            mx, mn = reldiff_field(f(a, v, fr), f(b, v, fr), v == "T")
            cells.append(f"{mx:8.1e}/{mn:8.1e}")
            if fr == args.early:
                seed_mean[v] = mn
        print(f"    {fr:>5} " + " ".join(f"{c:>22}" for c in cells))

    # ── (3) BULK AGREEMENT at last common frame ──────────────────────────────
    lf = ncommon - 1
    print(f"\n[3] bulk agreement @ last common frame {lf}  (domain sum; ratio=137/37)")
    bulk_ok = True
    for v in cv:
        sa = float(np.nansum(f(a, v, lf)))
        sb = float(np.nansum(f(b, v, lf)))
        ratio = sb / sa if abs(sa) > 1e-30 else (np.inf if abs(sb) > 1e-30 else 1.0)
        flag = "" if (0.33 <= ratio <= 3.0 or (abs(sa) < 1e-20 and abs(sb) < 1e-20)) else "  <-- out of band"
        if flag:
            bulk_ok = False
        print(f"    {v:>8}: 37={sa:12.4e}  137={sb:12.4e}  ratio={ratio:7.3f}{flag}")
    # Accumulated precip is an INTEGRATED output (robust to chaos in a converged
    # sense) and must be gated, not just printed — a divergent total precip is a
    # real failure even if instantaneous fields look in-band.
    for rv in ["RAINNC", "RAINC"]:
        if rv in a.variables and rv in b.variables:
            pa = f(a, rv, lf); pb = f(b, rv, lf)
            # Defense in depth: NaN/FillValue precip is bad data, not zero precip.
            # (scan_validity already flags it -> DATA-FAIL before this prints, but
            # guard here too so a plain `.sum()` can't be fooled by masked cells.)
            if np.isnan(pa).any() or np.isnan(pb).any():
                bulk_ok = False
                print(f"    {rv:>8}: contains NaN/FillValue cells -> BAD precip data (gated)")
                continue
            ra = float(pa.sum()); rb = float(pb.sum())
            ratio = rb / ra if abs(ra) > 1e-30 else (np.inf if abs(rb) > 1e-30 else 1.0)
            flag = "" if (0.33 <= ratio <= 3.0 or (abs(ra) < 1e-20 and abs(rb) < 1e-20)) else "  <-- out of band"
            if flag:
                bulk_ok = False
            print(f"    {rv:>8}: 37={ra:12.4e}  137={rb:12.4e}  ratio={ratio:7.3f}{flag}  (domain-sum mm)")

    # ── VERDICT ──────────────────────────────────────────────────────────────
    # seed: use the moisture+thermo mean reldiff at the probe frame. NaN means
    # the probe frame had no comparable finite cells (FillValue / no data).
    key_fields = [v for v in ["QVAPOR", "T"] if v in seed_mean]
    seed_vals = [seed_mean[v] for v in key_fields if np.isfinite(seed_mean[v])]
    seed = max(seed_vals) if seed_vals else float("nan")
    nodata = ((val37 is not None and val37[2] == "no-data")
              or (val137 is not None and val137[2] == "no-data"))
    real_nan_137 = val137 is not None and val137[2] == "nan"
    real_nan_37 = val37 is not None and val37[2] == "nan"
    # A run that wrote FEWER frames than its peer aborted early (crash / CFL
    # blowup / MPI abort). Its partial frames may look "consistent", but the run
    # itself FAILED — comparing only the surviving frames would report success
    # for a crashed run. Likewise --expect-frames asserts absolute completion
    # (catches the case where BOTH runs aborted identically at the same frame).
    frames_mismatch = na != nb
    short_run = "mp137" if nb < na else "mp37"
    truncated = (args.expect_frames is not None
                 and (na < args.expect_frames or nb < args.expect_frames))

    # Exit code is the GATE: 0 = pass, non-zero = fail (so callers can detect it).
    #  0 CONSISTENT | 1 FAIL/REVIEW | 2 INVALID-IC | 3 DATA-FAIL(FillValue)
    #  4 INCOMPLETE | 5 MISSING-SPECIES
    print("\n[VERDICT]")
    if missing:
        # Checked FIRST: a missing required field (esp. T/QVAPOR used by the IC
        # gate) would otherwise let the other checks silently pass on a subset.
        verdict = (f"FAIL(missing-species) — required field(s) absent from a run: "
                   f"{', '.join(missing)}; cannot verify parity across all species")
        rc = 5
    elif not ic_valid:
        verdict = (f"INVALID — runs start from DIFFERENT ICs (frame-0 reldiff {ic_max:.2e}); "
                   f"fix the IC generator's random seed before comparing")
        rc = 2
    elif frames_mismatch:
        verdict = (f"INCOMPLETE — {short_run} wrote {min(na, nb)} frames vs the peer's "
                   f"{max(na, nb)}; it aborted early (crash / CFL blowup / MPI abort). "
                   f"A partial run cannot pass parity even if its surviving frames match.")
        rc = 4
    elif truncated:
        verdict = (f"INCOMPLETE — fewer than --expect-frames={args.expect_frames} frames "
                   f"(mp37={na}, mp137={nb}); both runs aborted before completion.")
        rc = 4
    elif nodata:
        who = "mp37" if (val37 and val37[2] == "no-data") else "mp137"
        verdict = (f"DATA-FAIL — {who} wrfout is FillValue-only after the IC frame "
                   f"(libomp I/O flush, T11); no usable data to compare")
        rc = 3
    elif real_nan_137 and not real_nan_37:
        verdict = f"FAIL(NaN) — mp137 instability NaN at frame {val137[0]} ({val137[1]}) where mp37 is clean"
        rc = 1
    elif real_nan_37:
        verdict = f"FAIL(reference-NaN) — mp37 itself NaNs at frame {val37[0]} ({val37[1]}); reference invalid"
        rc = 1
    elif not np.isfinite(seed):
        verdict = f"FAIL(no-data) — frame-{args.early} probe has no comparable finite cells"
        rc = 1
    elif seed > 1.0e-3:
        verdict = f"FAIL(macroscopic-step1) — frame-{args.early} seed mean reldiff {seed:.2e} >> float-eps"
        rc = 1
    elif seed > 3.0e-5:
        verdict = f"REVIEW — frame-{args.early} seed mean reldiff {seed:.2e} above pure float-eps band (inspect)"
        rc = 1
    elif not bulk_ok:
        # Seed is float-eps (scheme-consistent per step), but the INTEGRATED
        # fields diverged out of band (e.g. squall RAINNC 24×). Not a clean pass:
        # this session showed the bulk divergence reflects a real marginal-vigor
        # difference (precision-amplified / CFL-marginal), not benign chaos.
        verdict = (f"REVIEW(bulk) — frame-{args.early} seed {seed:.2e} is float-eps "
                   f"(per-step consistent) BUT bulk OUT-OF-BAND: integrated fields diverged; "
                   f"inspect (precision-amplified / marginal-vigor, not a clean pass)")
        rc = 1
    elif args.expect_frames is None:
        # Everything checked is consistent, but completion is NOT proven: na==nb
        # only shows the two runs stopped at the SAME frame, which both-crashed-
        # identically also satisfies. A clean PASS requires the caller to assert
        # the expected history-frame count so a both-short (incomplete) run fails.
        verdict = (f"REVIEW(completion-unverified) — frames match ({na}) and all fields "
                   f"are consistent, but completion is UNPROVEN: both runs could have "
                   f"aborted at the same frame. Re-run with --expect-frames=N (the namelist "
                   f"history count) to certify a clean pass.")
        rc = 1
    else:
        verdict = (f"CONSISTENT — {na} frames (>= expect {args.expect_frames}), "
                   f"frame-{args.early} seed {seed:.2e} at float-eps AND bulk in-band; "
                   f"faithful per-step port, both runs complete, integrated fields agree.")
        rc = 0
    print(f"    {args.case}: {verdict}  [exit {rc}]")
    return rc


if __name__ == "__main__":
    sys.exit(main())
