#!/usr/bin/env python3
"""What built this? Written by the build itself (owner review §9).

A manifest that names its compiler as `"gfortran 15.2.0"` records a string the
caller typed, not the binary that ran. Two hosts with that same string produce
different numbers. The digest of the executable, the exact compile commands and
the source digests are known only inside the build, so the build writes them.

    python g33_build_provenance.py <outdir> <fc> <module> <fixture> <build-script>

Emits `<outdir>/build_provenance.json`, reading the compile commands from the
`<outdir>/commands.txt` the build logged.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(("git",) + args, capture_output=True,
                          text=True).stdout.strip()


def collect(out: Path, fc: str, module: Path, fixture: Path,
            script: Path) -> dict:
    """Provenance for one build. `fc` may be a name or a path; it is resolved,
    because the digest of whatever `gfortran` resolved to is the point."""
    binary = shutil.which(fc) or fc
    cmds = out / "commands.txt"
    return {
        "compiler_path": binary,
        "compiler_sha256": sha256(binary),
        "compiler_version": subprocess.run([binary, "--version"], text=True,
                                           capture_output=True).stdout.splitlines()[0],
        # From the log the build wrote as it compiled -- not from a caller that
        # may pass nothing, which would be indistinguishable from a build that
        # ran no commands.
        "compile_commands": cmds.read_text().splitlines() if cmds.exists() else [],
        "build_script_sha256": sha256(script),
        "module_path": str(module), "module_sha256": sha256(module),
        "fixture_path": str(fixture), "fixture_sha256": sha256(fixture),
        "repo_commit": _git("rev-parse", "HEAD"),
        "tree_dirty": bool(_git("status", "--porcelain")),
    }


def main(argv) -> int:
    if len(argv) != 5:
        print(__doc__)
        return 2
    out = Path(argv[0])
    (out / "build_provenance.json").write_text(
        json.dumps(collect(out, argv[1], Path(argv[2]), Path(argv[3]),
                           Path(argv[4])), indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
