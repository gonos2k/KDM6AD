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
import re
import shutil
import subprocess
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(("git",) + args, capture_output=True,
                          text=True).stdout.strip()


def normaliser(out: Path, tmp: Path | None = None, repo: Path | None = None):
    """Strip WHERE this ran, keep WHAT was built (owner §10.3, §7).

    `<OUT>` for the output directory. `<TMP>` for the temporary root: the
    staged sources and the generated overlay live under `$TMPDIR`, so the
    compile commands and `compiled_module_path` carried `/tmp` on one host
    and `/var/folders/...` on another -- measured, the content id moved
    between them for identical bytes. The digest-bearing BASENAME survives,
    which is what the source map is matched on. `<REPO>` for the checkout
    root, for the same reason one level up.

    Named and exported rather than inlined, because the publish gate compares
    the published logs to this record and has to normalise them the SAME way
    -- against the directories the build actually used, which only
    `diagnostic` remembers.
    """
    # BOTH spellings of each directory. macOS resolves `/var/folders/...` to
    # `/private/var/folders/...`, so replacing only the literal turned
    # `/private/var/.../T/x` into `/private<TMP>/x` -- neither the path nor a
    # clean tag (found by the provenance suite).
    subs = []
    for d, tag in ((out, "<OUT>"), (tmp, "<TMP>"), (repo, "<REPO>")):
        if not d:
            continue
        for form in {str(Path(d)).rstrip("/"), str(Path(d).resolve()).rstrip("/")}:
            subs.append((form, tag))
    # Longest first: `$TMPDIR` may contain the output directory, and replacing
    # the shorter one first would leave a half-normalised path.
    subs.sort(key=lambda kv: len(kv[0]), reverse=True)

    def norm(c: str) -> str:
        for lit, tag in subs:
            c = c.replace(lit, tag)
        return c
    return norm


#: The EXACT set of roles this build compiles. A source list was an ordered
#: bag of {path, digest}: dropping six of seven rows, repeating one logical
#: path under two digests, or adding a row nothing compiled all validated
#: CLEAN (owner §5). Naming the roles makes the set checkable, and an
#: unrecognised path gets `null` so a new source has to be declared here
#: deliberately rather than slipping in as one more row.
SOURCE_ROLES = (
    ("fixture", r"g33_fixture_[A-Za-z0-9_]+\.f90$"),
    ("driver", r"g33_refine_driver\.f90$"),
    ("stub", r"stub_wrf_error\.f90$"),
    ("libmassv", r"libmassv\.F$"),
    ("model_constants", r"module_model_constants\.F$"),
    ("radar", r"module_mp_radar\.F$"),
    ("module", r"(module_mp_ovl\.F|module_mp_kdm6[A-Za-z0-9_]*\.F)$"),
)
#: Every role a complete build leaves behind.
REQUIRED_ROLES = frozenset(r for r, _ in SOURCE_ROLES)
BUILD_PROVENANCE_SCHEMA = "g33_build_provenance_v1"


def role_of(path: str):
    """Which role a compiled source plays, or None when nothing claims it."""
    for role, pattern in SOURCE_ROLES:
        if re.search(pattern, path):
            return role
    return None


def _source_row(line: str, norm) -> dict:
    """One `sources.txt` line as a record: the logical path, and the digest
    of what the compiler read."""
    path, _, sha = line.partition("\t")
    p = norm(path)
    return {"path": p, "role": role_of(p),
            "sha256": sha.strip() or sha256(Path(path))}


def collect(out: Path, fc: str, module: Path, fixture: Path, script: Path,
            exe: Path | None = None, compiled: Path | None = None,
            staged: Path | None = None,
            staged_fixture: Path | None = None) -> dict:
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
    import os, tempfile
    norm = normaliser(out, Path(os.environ.get("TMPDIR", tempfile.gettempdir())),
                      Path(__file__).resolve().parents[1])
    ident = {
        "schema": BUILD_PROVENANCE_SCHEMA,
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
        # `path<TAB>digest`, where the digest is of the bytes the compiler
        # was fed, taken AT COMPILE TIME (owner review §10, Codex). Re-reading
        # the path here is what left a window: staging makes the compiled
        # bytes addressable, and recording their digest at the moment of
        # compilation is what closes it. A line without a digest is an older
        # log, and is hashed as before.
        "sources": ([_source_row(ln, norm) for ln in
                     dict.fromkeys(srcs.read_text().splitlines()) if ln.strip()]
                    if srcs.exists() else []),
        "executable_sha256": sha256(exe) if exe and Path(exe).exists() else None,
        "build_script_sha256": sha256(script),
        # The PATH is the pinned host location -- what the experiment is
        # about -- and the DIGEST is of the staged bytes the compiler read,
        # which are the same bytes by construction (owner review §10).
        "module_path": norm(str(module)),
        "module_sha256": sha256(staged if staged is not None else module),
        # None when the pinned module IS what was compiled.
        "compiled_module_path": (norm(str(compiled)) if compiled
                                 and Path(compiled) != Path(module) else None),
        "compiled_module_sha256": (sha256(compiled) if compiled
                                   and Path(compiled) != Path(module) else None),
        # ...and the FIXTURE digest is of the staged bytes too (owner §4).
        # `sources[]` already carried the compiled fixture's digest while this
        # field re-read the working tree, so one provenance document held two
        # fixture digests from two sources.
        "fixture_path": norm(str(fixture)),
        "fixture_sha256": sha256(staged_fixture if staged_fixture is not None
                                 else fixture),
        "repo_commit": _git("rev-parse", "HEAD"),
        "tree_dirty": bool(_git("status", "--porcelain")),
    }
    import os as _os, tempfile as _tf
    return ident | {"diagnostic": {
        "outdir": str(out),
        "tmpdir": str(Path(_os.environ.get("TMPDIR", _tf.gettempdir()))),
        "repo_root": str(Path(__file__).resolve().parents[1]),
        "compiler_path": binary,
        "compiler_f951_path": f951 if Path(f951).is_file() else None,
        "executable_path": str(exe) if exe else None,
        "compile_commands_literal": (cmds.read_text().splitlines()
                                     if cmds.exists() else []),
    }}


def verify(root: Path) -> list:
    """The published record against the two logs it was DERIVED from.

    `collect()` builds `sources` and `compile_commands` by reading these
    files, so at collection time the three agree by construction. What this
    checks is that they still agree at PUBLICATION -- an edit in between
    would leave a record describing a build the logs no longer show (owner
    review §6). It lives here, beside the parsers, so the comparison cannot
    drift from how the record is written; the producer reaches it through
    the same subprocess boundary the build uses.
    """
    record = root / "build_provenance.json"
    if not record.is_file():
        return ["build_provenance.json is not in the bundle"]
    try:
        got = json.loads(record.read_text())
    except ValueError as e:
        return [f"build_provenance.json is not readable JSON: {e}"]
    # The logs are copied VERBATIM from the build directory while the record
    # is normalised against it, so the comparison needs the directory the
    # build ran in -- which only the diagnostic block remembers.
    outdir = (got.get("diagnostic") or {}).get("outdir")
    if not outdir:
        return ["build_provenance.diagnostic.outdir is missing, so the "
                "published logs cannot be normalised the way the record was"]
    norm, bad = normaliser(Path(outdir)), []
    srcs, cmds = root / "sources.txt", root / "commands.txt"
    # ABSENT is not ABSENT-AND-FINE (Codex): skipping the comparison when a
    # log is missing let deleting it clear the check, so a record could claim
    # sources and commands with nothing left to contradict them. Every build
    # writes both, so a bundle without them is not a bundle this can verify.
    for f in (srcs, cmds):
        if not f.is_file():
            bad.append(f"{f.name} is not in the bundle, so "
                       f"build_provenance cannot be re-derived from it")
    if bad:
        return bad
    # A checker REPORTS; it does not crash on the artifact it is judging.
    # `_source_row` falls back to hashing the path when a line carries no
    # digest -- right for an older log, but on a tampered one it reached for
    # a file that does not exist and raised out of the verification instead
    # of failing it.
    lines = [ln for ln in srcs.read_text().splitlines() if ln.strip()]
    malformed = [ln for ln in lines if "\t" not in ln or not ln.split("\t")[1].strip()]
    if malformed:
        return bad + [f"sources.txt line {lines.index(malformed[0]) + 1} carries "
                      f"no digest: {malformed[0][:60]!r}"]
    rows = [_source_row(ln, norm) for ln in lines]
    if rows != got.get("sources"):
        bad.append("sources.txt is not build_provenance.sources")
    if [norm(c) for c in cmds.read_text().splitlines()] != \
            got.get("compile_commands"):
        bad.append("commands.txt is not build_provenance.compile_commands")
    return bad


def main(argv) -> int:
    if len(argv) == 2 and argv[0] == "--verify":
        bad = verify(Path(argv[1]))
        print("\n".join(bad))
        return 1 if bad else 0
    if not 5 <= len(argv) <= 9:
        print(__doc__)
        return 2
    out = Path(argv[0])
    (out / "build_provenance.json").write_text(
        json.dumps(collect(out, argv[1], Path(argv[2]), Path(argv[3]),
                           Path(argv[4]),
                           Path(argv[5]) if len(argv) > 5 else None,
                           Path(argv[6]) if len(argv) > 6 else None,
                           Path(argv[7]) if len(argv) > 7 else None,
                           Path(argv[8]) if len(argv) > 8 else None),
                   indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
