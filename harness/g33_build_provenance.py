#!/usr/bin/env python3
"""What built this? Written by the build itself (owner review §9).

A manifest that names its compiler as `"gfortran 15.2.0"` records a string the
caller typed, not the binary that ran. Two hosts with that same string produce
different numbers. The digest of the executable, the exact compile commands and
the source digests are known only inside the build, so the build writes them.

    python g33_build_provenance.py <outdir> <fc> <module> <fixture> <build-script> \
        [exe] [compiled-module]

`module` is the PINNED reference the experiment is about; `compiled-module` is
what the compiler actually saw, which differs under `--dump`/`--nflux` where it is
the macro-gated overlay. Recording only the compiled one would leave an
instrumented bundle unlinkable to the reference it instruments.

Emits `<outdir>/build_provenance.json`, reading the compile commands from
`<outdir>/commands.txt` and the compiled sources from `<outdir>/sources.txt`,
both of which the build logged as it ran.

Digesting only the module and fixture left the rest of the link invisible
(owner P0-3): `libmassv.F`, `module_model_constants.F`, `module_mp_radar.F`, the
error stub and the driver all change results, and `host/**` is gitignored so
`repo_commit`/`tree_dirty` cannot see them. The final executable is digested too,
because that is the artifact that actually produced the numbers.
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


def collect(out: Path, fc: str, module: Path, fixture: Path, script: Path,
            exe: Path | None = None, compiled: Path | None = None) -> dict:
    """Provenance for one build. `fc` may be a name or a path; it is resolved,
    because the digest of whatever `gfortran` resolved to is the point."""
    binary = shutil.which(fc) or fc
    cmds, srcs = out / "commands.txt", out / "sources.txt"
    # The compiler DRIVER is a thin wrapper; the program that does the compiling
    # is `f951`, and it is the one whose digest identifies the code generator.
    f951 = subprocess.run([binary, "-print-prog-name=f951"], text=True,
                          capture_output=True).stdout.strip()
    # A compiler that prints no version gets `null`, not "" -- and never an
    # exception, which would abort an otherwise successful build at its last
    # step. The digest above is the field that identifies the binary anyway.
    version = subprocess.run([binary, "--version"], text=True,
                             capture_output=True).stdout.splitlines()
    # IDENTITY vs DIAGNOSTIC (owner §10.3). Everything that determines the result
    # is stable across runs -- the executable digest is bit-identical between two
    # builds of the same sources -- but the compile commands and paths carry the
    # temporary output directory, so a content-addressed bundle got a different
    # name every rerun. `<OUT>` stands in for that directory in the identity view;
    # the literal paths stay under `diagnostic`, where they answer "where did this
    # happen" rather than "what was built".
    norm = lambda c: c.replace(str(out), "<OUT>")
    ident = {
        "compiler_sha256": sha256(binary),
        "compiler_version": version[0] if version else None,
        # From the log the build wrote as it compiled -- not from a caller that
        # may pass nothing, which would be indistinguishable from a build that
        # ran no commands.
        "compile_commands": [norm(c) for c in cmds.read_text().splitlines()]
                            if cmds.exists() else [],
        "compiler_f951_sha256": (sha256(f951) if Path(f951).is_file() else None),
        # Every source the build compiled, in build order, each by digest.
        # Paths normalised here too (owner §9.1): under --nflux the compiled
        # module is a generated overlay INSIDE the temp output directory, so a
        # literal path gave the same instrumented build a different identity in
        # every run. The digest is what identifies a source; the literal path is
        # diagnostic.
        "sources": ([{"path": norm(ln), "sha256": sha256(ln)}
                     for ln in dict.fromkeys(srcs.read_text().split())]
                    if srcs.exists() else []),
        "executable_sha256": sha256(exe) if exe and Path(exe).exists() else None,
        "build_script_sha256": sha256(script),
        "module_path": norm(str(module)), "module_sha256": sha256(module),
        # None when the pinned module IS what was compiled.
        "compiled_module_path": (norm(str(compiled)) if compiled
                                 and Path(compiled) != Path(module) else None),
        "compiled_module_sha256": (sha256(compiled) if compiled
                                   and Path(compiled) != Path(module) else None),
        "fixture_path": norm(str(fixture)), "fixture_sha256": sha256(fixture),
        "repo_commit": _git("rev-parse", "HEAD"),
        "tree_dirty": bool(_git("status", "--porcelain")),
    }
    return ident | {"diagnostic": {
        "outdir": str(out),
        "compiler_path": binary,
        "compiler_f951_path": f951 if Path(f951).is_file() else None,
        "executable_path": str(exe) if exe else None,
        "compile_commands_literal": (cmds.read_text().splitlines()
                                     if cmds.exists() else []),
    }}


def main(argv) -> int:
    if not 5 <= len(argv) <= 7:
        print(__doc__)
        return 2
    out = Path(argv[0])
    (out / "build_provenance.json").write_text(
        json.dumps(collect(out, argv[1], Path(argv[2]), Path(argv[3]),
                           Path(argv[4]),
                           Path(argv[5]) if len(argv) > 5 else None,
                           Path(argv[6]) if len(argv) > 6 else None),
                   indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
