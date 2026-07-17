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
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cmd_out(args: list[str]) -> str:
    try:
        return subprocess.run(args, capture_output=True, text=True,
                              timeout=60).stdout.strip().splitlines()[0]
    except Exception as e:  # toolchain probe only — record the failure, don't die
        return f"UNAVAILABLE ({e})"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", type=Path, default=REPO / "host" / "KIM-meso_v1.0")
    ap.add_argument("--gateb-log", type=Path, default=None,
                    help="Gate B driver output to embed")
    ap.add_argument("--gated-log", type=Path, action="append", default=[],
                    help="Gate D strict_bitwise_nc output(s) to embed (repeatable)")
    ap.add_argument("--out", type=Path, default=REPO / "artifacts" / "c4" /
                    "evidence_manifest.json")
    args = ap.parse_args()

    phys = args.host / "phys"
    dylib = (REPO / "libtorch" / "install" / "lib" / "libkdm6_c.dylib").resolve()

    head = cmd_out(["git", "-C", str(REPO), "rev-parse", "HEAD"])
    dirty = subprocess.run(["git", "-C", str(REPO), "diff", "--quiet", "HEAD",
                            "--", "libtorch", "oracle", "harness", "docs"],
                           capture_output=True).returncode != 0

    manifest = {
        "artifact": "conservative-interface-v1 C4 evidence",
        "public_repo": {
            "base_commit": "48d8c32",
            "head_commit": head,
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
    manifest["gate_a_scope_check"] = {
        "returncode": scope.returncode,
        "report": json.loads(scope.stdout),
    }

    if args.gateb_log and args.gateb_log.exists():
        text = args.gateb_log.read_text()
        manifest["gate_b"] = {
            "log": str(args.gateb_log),
            "pass": "GATE B: PASS" in text,
            "output": text,
        }
    if args.gated_log:
        manifest["gate_d"] = [
            {"log": str(p), "output": p.read_text()}
            for p in args.gated_log if p.exists()
        ]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2) + "\n")
    ok = scope.returncode == 0
    print(f"wrote {args.out}  (gate A scope: {'PASS' if ok else 'FAIL'})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
