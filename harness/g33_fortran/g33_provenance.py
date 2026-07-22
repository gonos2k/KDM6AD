#!/usr/bin/env python3
"""Write the build provenance for one local standalone-Fortran G3.3 case."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys

HOST = "host/KIM-meso_v1.0"
HERE = "harness/g33_fortran"


def _sha(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main() -> None:
    out_dir, algo, dump, fc, module_src, module_canon = sys.argv[1:7]
    host_sources = {
        "libmassv.F": f"{HOST}/frame/libmassv.F",
        "module_model_constants.F": f"{HOST}/share/module_model_constants.F",
        "module_mp_radar.F": f"{HOST}/phys/module_mp_radar.F",
        "module_mp_kdm6[_cons].F": module_canon,
    }
    harness_sources = {
        **{n: f"{HERE}/{n}" for n in (
            "make_fortran_overlay.py", "g33_fortran_bindings.py",
            "g33_fortran_driver.f90", "g33_fixture_v1.f90",
            "stub_wrf_error.f90", "fortran_build.sh", "g33_provenance.py",
            "g33_fortran_dump.py", "run_fortran_case.py")},
        "g33_fixture_v1.json": "harness/g33_fixture_v1.json",
        "g33_fixture_v1.py": "harness/g33_fixture_v1.py",
        "g33_fixture_v1.h": "harness/g33_overlay/g33_fixture_v1.h",
        "g33_fourcase_fixture_check.py": "harness/g33_fourcase_fixture_check.py",
        "g33_schema.py": "harness/g33_schema.py",
        "g33_expectation.py": "harness/g33_expectation.py",
    }
    fc_real = os.path.realpath(fc)
    version = subprocess.run([fc_real, "--version"], capture_output=True, text=True,
                             check=False).stdout
    commands_path = os.path.join(out_dir, "commands.txt")
    with open(commands_path, encoding="utf-8") as f:
        commands = f.read().splitlines()
    manifest = {
        "schema_version": 2,
        "algorithm": algo,
        "dump_instrumented": dump == "1",
        "host_source_sha256": {k: _sha(v) for k, v in host_sources.items()},
        "harness_source_sha256": {k: _sha(v) for k, v in harness_sources.items()},
        "module_compiled_sha256": _sha(module_src),
        "module_canonical_sha256": _sha(module_canon),
        "executable_sha256": _sha(os.path.join(out_dir, "g33_fortran_driver")),
        "compiler_path": fc_real,
        "compiler_binary_sha256": _sha(fc_real),
        "compiler_version": version.splitlines()[0] if version else None,
        "commands": commands,
        "note": "fixture, parameter and stdout identities are bound by run_manifest.json",
    }
    dst = os.path.join(out_dir, "provenance.json")
    tmp = dst + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    os.replace(tmp, dst)


if __name__ == "__main__":
    main()
