#!/usr/bin/env python3
"""Write the decision-grade provenance manifest for a standalone-Fortran build.

The Fortran leg is LOCAL-ONLY (the reference tree is gitignored), so a local
result can only be trusted if every input it was produced from is pinned. This
records the SHA256 of all four host reference sources (not just the mp module),
the harness generator + bindings + driver + stub, the actually-compiled module
(the overlay when instrumented), the executable, plus the compiler and the exact
compile/link commands. The driver run adds fixture_sha256 + stdout_sha256.

    g33_provenance.py <out_dir> <algo> <dump0|1> <fc> <module_src> <module_canon>

Paths are fixed by the repo layout (invoked from the repo root by fortran_build.sh).
"""
import hashlib
import json
import os
import subprocess
import sys

HOST = "host/KIM-meso_v1.0"
HERE = "harness/g33_fortran"


def _sha(path):
    # decision-grade: a missing/unreadable input is a HARD failure, never a
    # silent None hole in the manifest.
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    out_dir, algo, dump, fc, module_src, module_canon = sys.argv[1:7]
    host_sources = {
        "libmassv.F": f"{HOST}/frame/libmassv.F",
        "module_model_constants.F": f"{HOST}/share/module_model_constants.F",
        "module_mp_radar.F": f"{HOST}/phys/module_mp_radar.F",
        "module_mp_kdm6[_cons].F": module_canon,
    }
    # every file that shapes the produced bits: the driver + overlay generator +
    # bindings + stub, the build script itself, this provenance writer, and the
    # schema modules the generator validates against.
    harness_sources = {
        **{n: f"{HERE}/{n}" for n in (
            "make_fortran_overlay.py", "g33_fortran_bindings.py",
            "g33_fortran_driver.f90", "stub_wrf_error.f90",
            "fortran_build.sh", "g33_provenance.py", "g33_fortran_dump.py")},
        "g33_schema.py": "harness/g33_schema.py",
        "g33_expectation.py": "harness/g33_expectation.py",
    }
    ver = subprocess.run([fc, "--version"], capture_output=True, text=True).stdout
    cmds_path = os.path.join(out_dir, "commands.txt")
    manifest = {
        "algorithm": algo,
        "dump_instrumented": dump == "1",
        "host_source_sha256": {k: _sha(v) for k, v in host_sources.items()},
        "harness_source_sha256": {k: _sha(v) for k, v in harness_sources.items()},
        "module_compiled_sha256": _sha(module_src),   # the overlay when --dump
        "module_canonical_sha256": _sha(module_canon),
        "executable_sha256": _sha(os.path.join(out_dir, "g33_fortran_driver")),
        "compiler_path": fc,
        "compiler_version": ver.splitlines()[0] if ver else None,
        "commands": _sha_open(cmds_path),
        "note": "fixture_sha256 + stdout_sha256 are added by the run wrapper (runtime)",
    }
    # atomic publish: write .tmp then rename, so a partial write never masquerades
    # as a complete manifest.
    dst = os.path.join(out_dir, "provenance.json")
    tmp = dst + ".tmp"
    with open(tmp, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    os.replace(tmp, dst)


def _sha_open(cmds_path):
    with open(cmds_path) as f:
        return f.read().splitlines()


if __name__ == "__main__":
    main()
