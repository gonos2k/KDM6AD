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
    try:
        return hashlib.sha256(open(path, "rb").read()).hexdigest()
    except OSError:
        return None


def main():
    out_dir, algo, dump, fc, module_src, module_canon = sys.argv[1:7]
    host_sources = {
        "libmassv.F": f"{HOST}/frame/libmassv.F",
        "module_model_constants.F": f"{HOST}/share/module_model_constants.F",
        "module_mp_radar.F": f"{HOST}/phys/module_mp_radar.F",
        "module_mp_kdm6[_cons].F": module_canon,
    }
    harness_sources = {
        n: f"{HERE}/{n}" for n in (
            "make_fortran_overlay.py", "g33_fortran_bindings.py",
            "g33_fortran_driver.f90", "stub_wrf_error.f90")
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
        "commands": (open(cmds_path).read().splitlines()
                     if os.path.exists(cmds_path) else []),
        "note": "fixture_sha256 + stdout_sha256 are added by the driver run (runtime)",
    }
    json.dump(manifest, open(os.path.join(out_dir, "provenance.json"), "w"),
              indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
