#!/usr/bin/env python3
"""One command that produces a refinement bundle, or produces nothing.

Owner P0-2/priority-2. The bundles were assembled by hand: `refine_build.sh` wrote
build provenance, a separate step ran the driver, and a third stitched outputs and
findings into a manifest. Nothing structurally prevented provenance from one build
being published beside members from another -- which is the failure the provenance
exists to make impossible.

    build -> run every member -> strict-parse -> cross-member checks
          -> manifest -> ATOMIC publish

Every stage is fail-closed and the bundle is published by renaming a fully-built
temporary directory, so a run that dies half way leaves the previous bundle
exactly as it was rather than a half-replaced one.

    g33_refine_experiment.py <outdir> --fixture=NAME --algo=legacy \\
        --nsplit 3,6,12,24 [--nflux] [--finding path ...]

`--nflux` also turns on the number-flux/ice-substep overlay, and is recorded in
the manifest as `instrumented`, because an instrumented member is a different
artifact from a plain one even when the two agree bit for bit.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import g33_refine_analyze as ra        # noqa: E402
import g33_refine_manifest as rm       # noqa: E402
import g33_probe_read as pr           # noqa: E402

BUILD = HERE / "g33_fortran" / "refine_build.sh"


def _run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise SystemExit(f"FAILED: {' '.join(map(str, cmd))}\n{r.stderr[-2000:]}")
    return r.stdout


def build(workdir: Path, fixture: str, algo: str, nflux: bool,
          arm: str = "reference") -> Path:
    """Compile into `workdir`, returning the driver that will produce members.

    `arm` selects the instrument: `reference` is the f32 operator being certified,
    `probe` adds the full-precision G33P stream at that same precision, and `f64`
    promotes the kernel and emits ONLY G33P. The arm is carried into the manifest
    because an f64 member is not the reference and must never be read as one
    (owner priority 2).
    """
    cmd = [str(BUILD), str(workdir), f"--fixture={fixture}", f"--algo={algo}"]
    if nflux:
        cmd.append("--nflux")
    if arm in ("probe", "f64"):
        cmd.append(f"--{arm}")
    _run(cmd)
    exe = workdir / "g33_refine_driver"
    if not exe.exists():
        raise SystemExit(f"build produced no driver at {exe}")
    return exe


def members(exe: Path, out: Path, nsplits, mode: str) -> dict:
    """Run every member and STRICT-parse it before it is allowed to be one."""
    runs = {}
    for n in nsplits:
        p = out / f"n{n}.{mode}.txt"
        p.write_text(_run([str(exe), str(n), mode]))
        runs[n] = ra.read(p, nsplit=n)      # refuses anything malformed
    return runs


def _probe_member(path: Path) -> dict:
    """One f64 member, via the G33P strict parser."""
    r = pr.read(path.read_text())
    m = re.match(r"^n(\d+)\.(carry|rezero)\.txt$", path.name)
    if not m:
        raise pr.ProbeError(f"{path.name}: not n<N>.<carry|rezero>.txt")
    return {"file": path.name, "output_sha256": rm.sha256(path),
            "nsplit": int(m.group(1)), "mode": m.group(2),
            "precision": r[("meta", "precision")],
            "source_precision": r[("meta", "source_precision")]}


def probe_members(exe: Path, out: Path, nsplits, mode: str) -> dict:
    """Run every member and read it with the G33P strict parser."""
    runs = {}
    for n in nsplits:
        p = out / f"n{n}.{mode}.txt"
        p.write_text(_run([str(exe), str(n), mode]))
        runs[n] = pr.read(p.read_text())
    return runs


def produce(dest: Path, *, fixture: str, algo: str, nsplits, mode: str,
            nflux: bool, module: Path, findings=(), arm: str = "reference") -> Path:
    """Build, run, validate and publish. Returns the published bundle."""
    tmp = Path(tempfile.mkdtemp(prefix=".g33-bundle-", dir=dest.parent))
    try:
        exe = build(tmp, fixture, algo, nflux, arm)
        if arm == "f64":
            # An f64 build emits no G33R at all, so there are no refinement
            # members to strict-parse; the probe stream is the artifact, and it
            # is read by its own parser.
            runs = probe_members(exe, tmp, nsplits, mode)
        else:
            runs = members(exe, tmp, nsplits, mode)
            if len(runs) > 1:
                ra.require_same_universe(runs)      # one experiment, not several
        fx = HERE / "g33_fortran" / f"{fixture}.f90"
        man = rm.build(tmp, module=module, fixture=fx,
                       member_reader=_probe_member if arm == "f64" else None,
                       compiler=_run(["gfortran", "--version"]).splitlines()[0],
                       analyzer=HERE / "g33_refine_analyze.py",
                       build_provenance=tmp / "build_provenance.json",
                       findings=findings)
        man["instrumented"] = nflux
        man["arm"] = arm
        man["precision"] = "f64" if arm == "f64" else "f32"
        # An instrument arm can never be decision evidence, and says so in the
        # artifact rather than only in prose.
        man["decision_eligible"] = False
        (tmp / "manifest.json").write_text(
            rm.json.dumps(man, indent=2, sort_keys=True) + "\n")
        # Publish by moving ONE symlink (owner §7.4). The previous shape was
        # `dest -> dest.prev` then `tmp -> dest`: two renames with a window in
        # between where the canonical path does not exist, and if the second
        # failed the bundle was gone from where readers look. Here the bundle
        # lands in an immutable directory named by its own manifest digest and
        # `dest` is a symlink swapped atomically over it, so there is no moment
        # at which `dest` is absent or half-replaced.
        store = dest.parent / f"{dest.name}.bundles"
        store.mkdir(exist_ok=True)
        final = store / rm.sha256(tmp / "manifest.json")[:16]
        # Content-addressed: an identical manifest is the same bundle. Removing
        # and rebuilding it would delete the directory `dest` currently points at
        # -- the very window this design exists to close -- so an existing one is
        # reused and the temp discarded.
        if not final.exists():
            os.rename(tmp, final)
        link = dest.with_name(dest.name + ".new")
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(final, target_is_directory=True)
        os.replace(link, dest) if dest.is_symlink() or not dest.exists() \
            else _replace_dir_with_link(dest, link)
        return dest
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _replace_dir_with_link(dest: Path, link: Path) -> None:
    """One-time migration off a real directory. Unavoidable non-atomic step, and
    it happens once per destination rather than on every publish."""
    shutil.rmtree(dest)
    os.replace(link, dest)


def main(argv) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("outdir", type=Path)
    ap.add_argument("--fixture", default="g33_fixture_multisubcycle_v1")
    ap.add_argument("--algo", default="legacy")
    ap.add_argument("--mode", default="rezero", choices=("rezero", "carry"))
    ap.add_argument("--nsplit", required=True,
                    help="comma-separated, e.g. 3,6,12,24")
    ap.add_argument("--nflux", action="store_true")
    ap.add_argument("--arm", default="reference",
                    choices=("reference", "probe", "f64"),
                    help="f64 is an INSTRUMENT: it emits no G33R and is never "
                         "decision evidence")
    ap.add_argument("--module", type=Path,
                    default=Path("host/KIM-meso_v1.0/phys/module_mp_kdm6.F"))
    ap.add_argument("--finding", type=Path, action="append", default=[])
    a = ap.parse_args(argv)
    dest = produce(a.outdir.resolve(), fixture=a.fixture, algo=a.algo,
                   nsplits=[int(x) for x in a.nsplit.split(",")], mode=a.mode,
                   nflux=a.nflux, module=a.module, findings=a.finding, arm=a.arm)
    print(dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
