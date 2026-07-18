#!/usr/bin/env python3
"""C4 Gate A evidence manifest builder (conservative-interface-v1).

Collects, into artifacts/c4/evidence_manifest.json:
  - public repo commit (+dirty flag) and the pinned base 48d8c32
  - sha256 of the four host Fortran sources (2 legacy never-modify + 2 new),
    kdm6_iso_c.F, and the installed libkdm6_c binary (symlink resolved)
  - scheme IDs and the ID→backend map
  - toolchain versions (gfortran/mpif90/clang/torch/OS)
  - the Gate A scope-check report (run in-process)
  - fixture provenance (Gate B driver + C3 fixture source hashes)
  - optional Gate B / Gate D result logs (paths passed in, content embedded)

The private host tree is NOT a git repo (gitignored inside the public repo),
so "host commit" is recorded as the file-sha pin set itself.

Owner-run tool: requires the private host tree. The public PR carries the
manifest OUTPUT, never the host sources.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cmd_out(args: list[str]) -> str:
    try:
        lines = subprocess.run(args, capture_output=True, text=True,
                               timeout=60).stdout.strip().splitlines()
        return lines[0] if lines else "UNAVAILABLE (no output)"
    except Exception as e:  # toolchain probe only — record the failure, don't die
        return f"UNAVAILABLE ({e})"


FATAL_RE = re.compile(
    r"MPI_ABORT|SIGSEGV|forrtl: severe|Fatal error in|NaN (BEFORE|after)")


def verify_recert_run(rundir: Path, np: int = 4) -> dict:
    """Fail-closed per-run verification of one 12h recert run (mirrors the
    host verify_run.sh contract): exit_code==0, SUCCESS COMPLETE WRF in every
    rank log (==np), no fatal/NaN marker. The SUCCESS COMPLETE WRF marker is
    the FULL-DURATION completeness proof — WRF prints it only after the entire
    integration finishes — so it is stronger than any frame count. (This case's
    --history 60 + base history_interval_s=20 emit 12 hourly frames drifting
    +20s/frame: 00:00:00 … 11:03:40; the 13th frame at ~12:04:00 falls past the
    12:00:00 run end, so 12 frames is the COMPLETE output, not truncation —
    verified against the `_12:00:00 wrf: SUCCESS COMPLETE WRF` marker.)
    Returns a dict with every checked fact and a single `verified` bool."""
    r: dict = {"rundir": str(rundir), "exists": rundir.is_dir()}
    if not r["exists"]:
        r["verified"] = False
        return r
    ec = (rundir / "exit_code").read_text().strip() if (rundir / "exit_code").exists() else None
    r["exit_code"] = ec
    # Validate rank IDENTITIES, not just the count: the run dir must contain
    # EXACTLY the rsl.error.0000 … {np-1} logs — no missing rank (a rank that
    # crashed without writing) and no stray extra (a stale log from a different
    # np decomposition would let a bare count slip through). The precise
    # 4-digit glob excludes backup/temp files (rsl.error.0000.bak/.tmp) that a
    # bare `rsl.error.*` would sweep in. Each rank log is read exactly once.
    rank_texts = {p.name: p.read_text(errors="replace")
                  for p in rundir.glob("rsl.error.[0-9][0-9][0-9][0-9]")}
    found_ranks = set(rank_texts)
    required_ranks = {f"rsl.error.{i:04d}" for i in range(np)}
    r["rank_logs"] = sorted(found_ranks)
    r["rank_ids_ok"] = (found_ranks == required_ranks)
    r["missing_ranks"] = sorted(required_ranks - found_ranks)
    r["extra_rank_logs"] = sorted(found_ranks - required_ranks)
    n_success = sum(1 for name in required_ranks
                    if "SUCCESS COMPLETE WRF" in rank_texts.get(name, ""))
    r["success_ranks"] = n_success
    # full-duration proof: the master rank (0000) reached SUCCESS at run end.
    r["reached_full_duration"] = bool(re.search(
        r"_12:00:00 wrf: SUCCESS COMPLETE WRF", rank_texts.get("rsl.error.0000", "")))
    fatal = sum(1 for t in rank_texts.values() if FATAL_RE.search(t))
    for p in sorted(rundir.glob("*.stdout")):
        if FATAL_RE.search(p.read_text(errors="replace")):
            fatal += 1
    r["fatal_markers"] = fatal
    fcst = sorted(rundir.glob("klfs_lc05_fcst.*")) or sorted(rundir.glob("wrfout_d01_*"))
    if fcst:
        import netCDF4 as nc
        with nc.Dataset(str(fcst[0])) as d:
            r["frames"] = d.dimensions["Time"].size if "Time" in d.dimensions else 1
        r["fcst"] = str(fcst[0])
    else:
        r["frames"] = 0
    r["verified"] = (ec == "0" and r["rank_ids_ok"] and n_success == np
                     and fatal == 0 and r["reached_full_duration"]
                     and r["frames"] >= 1)
    return r


def strict_bitwise_all_frames(f37: str, f137: str,
                              min_common_numeric: int = 250) -> dict:
    """254-var raw-bit (uint-view) comparison across EVERY common frame.
    FAIL-CLOSED — strict_bitwise is True ONLY if:
      * the variable SETS are identical (no only_a / only_b),
      * the frame counts are identical (na == nb, same cadence),
      * the number of common NUMERIC variables meets min_common_numeric — a
        malformed/degenerate file pair with a tiny common set must never pass,
      * and for EVERY frame, every one of those numeric variables was actually
        compared and matched (n_match == numeric_common AND n_diff == 0). A
        frame where variables were only skipped (nothing compared) fails."""
    import numpy as np
    import netCDF4 as nc
    a = nc.Dataset(f37); b = nc.Dataset(f137)
    a.set_auto_maskandscale(False); b.set_auto_maskandscale(False)
    na = a.dimensions["Time"].size if "Time" in a.dimensions else 1
    nb = b.dimensions["Time"].size if "Time" in b.dimensions else 1
    nframes = min(na, nb)
    common = sorted(set(a.variables) & set(b.variables))
    only_a = sorted(set(a.variables) - set(b.variables))
    only_b = sorted(set(b.variables) - set(a.variables))
    numeric_common = [v for v in common
                      if a.variables[v].dtype.kind in ("f", "i", "u")]
    ncnum = len(numeric_common)
    per_frame = []
    all_ok = ((not only_a) and (not only_b) and (na == nb) and nframes >= 1
              and ncnum >= min_common_numeric)
    itype = {1: np.uint8, 2: np.uint16, 4: np.uint32, 8: np.uint64}
    for fr in range(nframes):
        n_match = n_diff = n_skip = 0
        for v in common:
            va, vb = a.variables[v], b.variables[v]
            if va.dtype.kind not in ("f", "i", "u"):
                n_skip += 1; continue
            xa = np.asarray(va[fr]) if "Time" in va.dimensions else np.asarray(va[:])
            xb = np.asarray(vb[fr]) if "Time" in vb.dimensions else np.asarray(vb[:])
            if xa.shape != xb.shape or xa.dtype != xb.dtype:
                n_diff += 1; continue
            # .view() needs a contiguous buffer; NetCDF slices may not be.
            ua = np.ascontiguousarray(xa).view(itype[xa.dtype.itemsize])
            ub = np.ascontiguousarray(xb).view(itype[xb.dtype.itemsize])
            if int(np.count_nonzero(ua != ub)) == 0:
                n_match += 1
            else:
                n_diff += 1
        per_frame.append({"frame": fr, "match": n_match, "diff": n_diff,
                          "skip": n_skip, "numeric": ncnum})
        # a frame is clean ONLY if every numeric common var was compared and
        # matched — never on an empty/all-skipped comparison.
        if not (n_diff == 0 and n_match == ncnum and n_match > 0):
            all_ok = False
    a.close(); b.close()
    return {"frames_compared": nframes, "common_variables": len(common),
            "common_numeric_variables": ncnum,
            "min_common_numeric_required": min_common_numeric,
            "only_in_mp37": only_a, "only_in_mp137": only_b,
            "per_frame": per_frame, "strict_bitwise": all_ok}


def legacy_12h_block(runs_dir: Path) -> dict:
    """Assemble the fail-closed legacy 12h x np4 recertification block from the
    latest mp37/mp137 recert run dirs. strict_bitwise is recorded True ONLY
    when both runs verify AND EVERY common frame is 254-var raw-bit. The frame
    count is cadence-derived, not hardcoded: this case's --history 60 + base
    history_interval_s=20 emits 12 hourly frames drifting +20s/frame
    (00:00:00 … 11:03:40); the 13th at ~12:04:00 falls past the 12:00:00 end,
    so 12 IS the complete count. Completeness is proven by the per-run
    `_12:00:00 wrf: SUCCESS COMPLETE WRF` marker, never by a frame threshold."""
    def latest(glob):
        cands = sorted(runs_dir.glob(glob))
        return cands[-1] if cands else None
    d37 = latest("mp37_recert12h_*")
    d137 = latest("mp137_recert12h_*")
    block: dict = {
        "mp37_run": str(d37) if d37 else None,
        "mp137_run": str(d137) if d137 else None,
        "mp37": verify_recert_run(d37) if d37 else {"verified": False, "note": "no mp37 recert run"},
        "mp137": verify_recert_run(d137) if d137 else {"verified": False, "note": "no mp137 recert run"},
    }
    both_verified = bool(block["mp37"].get("verified")
                         and block["mp137"].get("verified"))
    if both_verified:
        cmp = strict_bitwise_all_frames(block["mp37"]["fcst"], block["mp137"]["fcst"])
        block["comparison"] = cmp
        block["strict_bitwise"] = bool(cmp["strict_bitwise"])
    else:
        block["comparison"] = None
        block["strict_bitwise"] = False
        block["note"] = ("recertification INCOMPLETE — both runs must verify "
                         "(exit_code=0, exactly np rank logs all with SUCCESS "
                         "COMPLETE WRF, reached 12:00:00, 0 fatal/NaN) before a "
                         "bitwise verdict is recorded")
    return block


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", type=Path, default=REPO / "host" / "KIM-meso_v1.0")
    ap.add_argument("--gateb-log", type=Path, default=None,
                    help="Gate B driver output to embed")
    ap.add_argument("--g3-report", type=Path, default=None,
                    help="gateb_g3_check.py JSON report to embed")
    ap.add_argument("--gated-log", type=Path, action="append", default=[],
                    help="Gate D strict_bitwise_nc output(s) to embed (repeatable)")
    ap.add_argument("--recert-runs", type=Path, default=None,
                    help="SS runs/ dir holding mp37/mp137_recert12h_* — assembles "
                         "the fail-closed legacy 12h x np4 recertification block")
    ap.add_argument("--recert-log", type=Path, default=None,
                    help="legacy12h_recert.log to embed verbatim")
    ap.add_argument("--out", type=Path, default=REPO / "artifacts" / "c4" /
                    "evidence_manifest.json")
    args = ap.parse_args()

    phys = args.host / "phys"
    dylib = (REPO / "libtorch" / "install" / "lib" / "libkdm6_c.dylib").resolve()

    head = cmd_out(["git", "-C", str(REPO), "rev-parse", "HEAD"])
    main_commit = cmd_out(["git", "-C", str(REPO), "rev-parse", "origin/main"])
    dirty = subprocess.run(["git", "-C", str(REPO), "diff", "--quiet", "HEAD",
                            "--", "libtorch", "oracle", "harness", "docs"],
                           capture_output=True).returncode != 0

    manifest = {
        "artifact": "conservative-interface-v1 C4 evidence",
        "public_repo": {
            "base_commit": "48d8c32",
            "producer_commit": head,
            "head_commit": head,
            "main_commit": main_commit,
            "tracked_tree_dirty_vs_head": dirty,
        },
        "private_host": {
            "path": str(args.host),
            "git": "not a git repo (gitignored in the public repo); "
                   "pinned by the sha256 set below",
        },
        "scheme_ids": {
            "37": "legacy KDM6 Fortran (never modified)",
            "137": "legacy KDM6AD C++ (never modified)",
            "237": "conservative-interface-v1 corrected Fortran reference",
            "337": "conservative-interface-v1 C++ (kdm6_step_v2_c physics_variant=1)",
        },
        "sha256": {
            "module_mp_kdm6.F": sha256(phys / "module_mp_kdm6.F"),
            "module_mp_kdm6ad.F": sha256(phys / "module_mp_kdm6ad.F"),
            "module_mp_kdm6_cons.F": sha256(phys / "module_mp_kdm6_cons.F"),
            "module_mp_kdm6ad_cons.F": sha256(phys / "module_mp_kdm6ad_cons.F"),
            "kdm6_iso_c.F": sha256(phys / "kdm6_iso_c.F"),
            "libkdm6_c(resolved)": sha256(dylib),
        },
        "libkdm6_c_resolved_path": str(dylib),
        "toolchain": {
            "os": f"{platform.system()} {platform.release()} {platform.machine()}",
            "gfortran": cmd_out(["gfortran", "--version"]),
            "mpif90": cmd_out(["mpif90", "--version"]),
            "clang": cmd_out(["clang", "--version"]),
            "torch": cmd_out([sys.executable, "-c",
                              "import torch; print(torch.__version__)"]),
        },
        "fixtures": {
            "gateb_driver.f90": sha256(args.host / "test" / "kdm6_cons_gateb" /
                                       "gateb_driver.f90"),
            "test_conservative_interface.cpp":
                sha256(REPO / "libtorch" / "tests" /
                       "test_conservative_interface.cpp"),
            "cons_fortran_scope_manifest.json":
                sha256(REPO / "harness" / "cons_fortran_scope_manifest.json"),
        },
    }

    # Gate A scope check, run in-process for the embedded report.
    scope = subprocess.run(
        [sys.executable, str(REPO / "harness" / "check_cons_fortran_scope.py"),
         "--legacy", str(phys / "module_mp_kdm6.F"),
         "--cons", str(phys / "module_mp_kdm6_cons.F"),
         "--legacy-wrapper", str(phys / "module_mp_kdm6ad.F")],
        capture_output=True, text=True)
    try:
        scope_report = json.loads(scope.stdout)
        scope_json_ok = True
    except json.JSONDecodeError:
        # the checker crashed before emitting its JSON report — surface the
        # raw output instead of masking it with a JSONDecodeError traceback.
        # Invalid JSON is itself a Gate A FAILURE (see the `ok` gate below):
        # a rc=0 with garbage output must NEVER read as PASS.
        scope_report = {"error": "scope checker produced no valid JSON",
                        "stdout": scope.stdout, "stderr": scope.stderr}
        scope_json_ok = False
    manifest["gate_a_scope_check"] = {
        "returncode": scope.returncode,
        "json_valid": scope_json_ok,
        "report": scope_report,
    }

    # Owner adjudication (2026-07-17) + the established cross-tree rate-dump
    # comparison scopes (compare_rate_dump.py refuses anything beyond these
    # without an explicit --min-fields opt-in).
    manifest["adjudication_2026_07_17"] = {
        "gate_b_g1_g2_g3_substitution": "APPROVED — standalone Gate B only; "
                                        "Gate D and C5 remain strict bitwise",
        "frozen_libtorch_instrumentation": "APPROVED — diagnostic-only, "
                                           "compile-time OFF default, separate "
                                           "diag branch, non-invasiveness gate",
        "production_numeric_changes_before_dump_evidence": "HELD",
        "fifth_fortran_physics_edit": "NOT pre-approved (reference stays "
                                      "reference; Case B requires re-opened "
                                      "Gate A adjudication)",
        "gate_d_conservative": "RESOLVED via C4-S1 (Case C shared C++ parity "
                               "fix, owner-approved 2026-07-18) — post-fix Gate D "
                               "short campaign 237<->337 measured FULL STRICT "
                               "BITWISE (see gate_d block)",
    }
    # C4-S1 shared parity exception (Case C, owner adjudication 2026-07-18).
    merge26 = cmd_out(["git", "-C", str(REPO), "rev-parse", "0b767e2"])
    # Full file list changed by the fix (merge-parents diff) — cmd_out only
    # returns the first line, so capture the whole list here.
    fix_files = subprocess.run(
        ["git", "-C", str(REPO), "diff", "--name-only", "0b767e2^1", "0b767e2"],
        capture_output=True, text=True).stdout.splitlines()
    manifest["c4s1_shared_piacw_fix"] = {
        "classification": "Case C — shared C++ reference-parity defect",
        "change": "libtorch/src/cold.cpp cloud_water_riming_torch piacw: "
                  "raw f64 PI -> path-conditional pi_t (operational f32 = "
                  "Fortran REAL(4) pi; fp64 DA keeps double pi)",
        "merge_commit": merge26,
        "files_changed": [f.strip() for f in fix_files],
        "binary_sha256": sha256(dylib),
        "fortran_modified": any(f.strip().endswith((".F", ".f90", ".F90"))
                                for f in fix_files),
        "tests": "test_cwr_piacw_pi_staging_f32_witness (RED->GREEN) + "
                 "_fp64_invariance; ctest 17/17; oracle parity 4/4",
    }
    manifest["gate_b_g3_3_status"] = {
        "verdict": "OPEN",
        "note": "piacw fixed the Gate D residual but NOT the standalone "
                "multi-subcycle G3.3 ULP-envelope exceedance (closure3 cons "
                "77852 > legacy 77312; species-iso 2188 > 1164 — unchanged "
                "pre/post fix). Attribution pending on "
                "analysis/c4-g3.3-first-divergence; Gate B is NOT closed as "
                "G1/G2/G3 until G3.3 is attributed or its metric re-adjudicated.",
    }
    if args.recert_runs is not None:
        manifest["legacy_12h_np4_recertification"] = legacy_12h_block(args.recert_runs)
        if args.recert_log and args.recert_log.exists():
            manifest["legacy_12h_np4_recertification"]["log"] = args.recert_log.read_text()
    manifest["gate_d_bisection_verdict_2026_07_17"] = {
        "seed_rate": "piacw (cloud-water accretion by ice, qc->qi)",
        "first_diverging_op": "the ×π multiply in cloud_water_riming_torch's "
                              "piacw chain: C++ raw f64 PI vs Fortran REAL(4) pi",
        "proof": "all inputs bitwise to the last double bit (paired f32 + "
                 "raw-64-bit dumps); offline ladder replication over ALL "
                 "28729 diverging cells: fort==f32-π chain 28729/28729, "
                 "cpp==f64-π chain 28729/28729, cross-assignments 0; all "
                 "100 state-flip cells ⊂ piacw-diff set",
        "classification": "legacy-SHARED latent class (not Case A / not "
                          "Case B): same idiom already fixed for psacw/"
                          "pgacw/paacw via path-conditional pi_t; piacw "
                          "left on raw PI; invisible in legacy "
                          "certifications (zero straddle flips), exposed "
                          "by the variant's supercooled cloud-ice "
                          "population",
        "rhox_suspect": "REFUTED (rhox bitwise in paired dumps)",
        "fix_pending_owner_adjudication": "piacw raw PI -> pi_t touches "
                                          "SHARED legacy C++ (outside the "
                                          "Case-A conservative-only "
                                          "pre-approval); provably moves "
                                          "legacy C++ piacw ONTO legacy "
                                          "Fortran; legacy re-cert scope "
                                          "required",
        "instrumentation": "diag/c4-poststateupdate-bisection only; "
                           "working tree reverted; Gate A re-verified "
                           "PASS; clean dylib sha reproduced; restored "
                           "237/337 runs STRICT BITWISE == pre-diag "
                           "baselines",
    }
    manifest["rate_dump_scope"] = {
        "graupel": {"fields": 8, "scope": "full list established", "verdict": "BITWISE"},
        "warmrates": {"fields": "first 8 of fort's 10 (--min-fields 8)",
                      "verdict": "BITWISE"},
        "ncrates": {"fields": "first 13 of fort 34 / cpp 23 (--min-fields 13; "
                              "trailing dbg_*/aux captures are capture-point "
                              "artifacts, not rates)",
                    "verdict": "BITWISE"},
    }

    if args.gateb_log and args.gateb_log.exists():
        text = args.gateb_log.read_text()
        manifest["gate_b"] = {
            "log": str(args.gateb_log),
            "pass": "GATE B: PASS" in text,
            "output": text,
        }
    if args.g3_report and args.g3_report.exists():
        manifest["gate_b_g3"] = json.loads(args.g3_report.read_text())
    if args.gated_log:
        manifest["gate_d"] = [
            {"log": str(p), "output": p.read_text()}
            for p in args.gated_log if p.exists()
        ]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2) + "\n")
    # Gate A passes ONLY if the checker exited 0 AND emitted a VALID JSON
    # report AND that report self-reports pass:true. A rc=0 with invalid or
    # non-passing JSON must fail loud — never a silent PASS.
    ok = (scope.returncode == 0
          and scope_json_ok
          and isinstance(scope_report, dict)
          and scope_report.get("pass") is True)
    print(f"wrote {args.out}  (gate A scope: {'PASS' if ok else 'FAIL'})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
