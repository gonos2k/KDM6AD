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
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import g33_refine_analyze as ra        # noqa: E402
import g33_refine_manifest as rm       # noqa: E402
import g33_probe_read as pr           # noqa: E402
import g33_number_transport as nt     # noqa: E402
import g33_matched_closure as mc      # noqa: E402
import g33_cap_interface as ci        # noqa: E402
import g33_dual_ledger as dl          # noqa: E402
import g33_defect_magnitude as dm     # noqa: E402
import g33_metric_trajectory as mtj   # noqa: E402

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


def fixture_dims(fixture: str) -> tuple:
    """(columns, levels) DECLARED by the fixture source.

    An INDEPENDENT source of truth: nothing the driver prints can influence it.
    That is the point wherever completeness is being judged -- a run that
    silently drops a column agrees with itself perfectly, so only a figure from
    outside the run can catch it.
    """
    src = (HERE / "g33_fortran" / f"{fixture}.f90").read_text()
    m = re.search(r"integer,\s*parameter\s*::\s*B\s*=\s*(\d+)\s*,\s*"
                  r"K\s*=\s*(\d+)", src)
    if not m:
        raise SystemExit(f"cannot read dimensions B, K from {fixture}.f90")
    return int(m.group(1)), int(m.group(2))


def fixture_width(fixture: str) -> int:
    """The fixture's column count.

    The tile argument is positional and precedes the profile, so a non-default
    profile must pass one -- and hardcoding `3` silently produced a tile-sum
    error on any fixture that is not three columns wide (owner §9).
    """
    return fixture_dims(fixture)[0]


def _argv(exe: Path, n: int, mode: str, rho_profile: str, width: int = 3) -> list:
    """The driver command line, recorded verbatim in the manifest (owner §5.2).

    The density arms were run by hand outside the producer, so a published bundle
    could not say which forcing intervention made it. `width` is the whole domain
    as ONE tile -- the producer's own default decomposition -- taken from the
    fixture rather than assumed.
    """
    argv = [str(exe), str(n), mode]
    if rho_profile != "as-is":
        argv += [str(width), rho_profile]
    return argv


def members(exe: Path, out: Path, nsplits, mode: str, *, arm="reference",
            nflux=False, rho_profile="as-is", width=3) -> dict:
    """Run every member and STRICT-parse EVERY protocol it emits (owner P0-4).

    A bundle used to be published after validating only G33R, so a probe arm
    could ship a G33P stream that was truncated, transposed or NaN, and an
    --nflux arm could ship a G33N stream nothing had parsed. The arm declares
    which protocols must be present; each is read by its own strict parser.
    """
    runs = {}
    for n in nsplits:
        p = out / f"n{n}.{mode}.txt"
        text = _run(_argv(exe, n, mode, rho_profile, width))
        p.write_text(text)
        runs[n] = ra.read(p, nsplit=n)          # G33R
        if arm == "probe":
            probe = pr.read(text)               # G33P
            _agree(runs[n], probe, p.name)
        if nflux:
            nt.calls(text)                      # G33N, whole-stream validated
    return runs


def _agree(g33r: dict, g33p: dict, name: str) -> None:
    """At the probe arm the same f32 values are written twice — raw hex on G33R
    and decimal on G33P. Requiring them to agree catches exactly the two defects
    that got through before: a transposed index and a format that dropped an
    exponent's `E`."""
    for key, hexv in g33r.items():
        if key[0] not in ("state", "initial", "forcing", "prec"):
            continue
        got = g33p.get(key)
        if got is None:
            raise pr.ProbeError(f"{name}: G33P is missing {key}, which G33R has")
        # EXACT (owner §7.3). Both sides are the same f32 value written twice --
        # raw hex and decimal -- so they must round-trip to the same f32 word. A
        # 1e-6 relative tolerance admits several f32 ULP near 1 and would pass a
        # genuinely different number.
        if struct.pack(">f", got) != struct.pack(">f", hexv):
            raise pr.ProbeError(
                f"{name}: G33R and G33P are different f32 words at {key}: "
                f"{hexv!r} vs {got!r}")


def _probe_member(path: Path) -> dict:
    """One f64 member, via the G33P strict parser."""
    r = pr.read(path.read_text())
    m = re.match(r"^n(\d+)\.(carry|rezero)\.txt$", path.name)
    if not m:
        raise pr.ProbeError(f"{path.name}: not n<N>.<carry|rezero>.txt")
    if r[("meta", "nsplit")] != int(m.group(1)):
        raise pr.ProbeError(
            f"{path.name}: header says nsplit={r[('meta', 'nsplit')]}")
    if r[("meta", "mode")] != m.group(2):
        raise pr.ProbeError(f"{path.name}: header says mode={r[('meta', 'mode')]}")
    # dtcld/delt/loops are READ from the header (schema 2), so an f64 bundle can
    # describe a refinement chain like any other -- before this the manifest had
    # only nsplit from the filename and `is_refinement_chain` was meaningless on
    # the f64 arm (owner §10.1).
    return {"file": path.name, "output_sha256": rm.sha256(path),
            "nsplit": int(m.group(1)), "mode": m.group(2),
            "precision": r[("meta", "precision")],
            "source_precision": r[("meta", "source_precision")],
            "algorithm": r[("meta", "algorithm")],
            "fixture": r[("meta", "fixture")],
            "delt": r[("meta", "delt")], "loops": r[("meta", "loops")],
            "dtcld": r[("meta", "dtcld")]}


def probe_members(exe: Path, out: Path, nsplits, mode: str,
                  rho_profile: str = "as-is", width: int = 3) -> dict:
    """Run every member and read it with the G33P strict parser."""
    runs = {}
    for n in nsplits:
        p = out / f"n{n}.{mode}.txt"
        p.write_text(_run(_argv(exe, n, mode, rho_profile, width)))
        runs[n] = pr.read(p.read_text())
    return runs


#: analysis name -> (module, callable taking the stream) (owner §14-4). Only for
#: `--nflux` bundles: these all read the extension records.
ANALYSES = {
    "matched_closure": ("g33_matched_closure", lambda s: mc.analysis(s)),
    "cap_interface": ("g33_cap_interface", lambda s: ci.analysis(s)),
    "extension_protocol": ("g33_number_transport", lambda s: _protocol(s)),
    # Both column measures, always (owner §9): reporting one makes a statement
    # about the OPERATOR read as a statement about the ATMOSPHERE.
    "dual_ledger": ("g33_dual_ledger", lambda s: dl.analysis(s)),
    # What the headline percentage is a percentage OF (owner §11).
    "defect_magnitude": ("g33_defect_magnitude", lambda s: dm.analysis(s)),
    # Water destroyed INSIDE the column is not precipitation (owner §16-4).
    # Both ledgers, so the correction is visible rather than a silent swap.
    "internal_cap_enthalpy": ("g33_cap_interface",
                              lambda s: ci.enthalpy_with_cap_sink(s)),
}


def _protocol(stream: str) -> dict:
    """What the stream actually carried, as the strict parser saw it.

    Not a restatement of the header: the header DECLARES features, this records
    how many records of each family survived validation, so a reader can tell a
    complete extension stream from a header that merely claimed one.
    """
    calls = nt.calls(stream)
    fams = {f: sum(len(c[f]) for c in calls)
            for f in ("xfer", "capin", "topout", "mstep", "flux")}
    return {"schema": nt.SCHEMA, "calls": len(calls),
            "features": sorted(calls[0].get("features", ())) if calls else [],
            "record_counts": fams,
            "K": calls[0]["K"] if calls else None,
            "columns": list(calls[0]["cols"]) if calls else None}


def _driver_analyses(out: Path, exe: Path, nsplits, mode: str,
                     width: int) -> list:
    """Analyses that re-run the driver under several arms, not one stream.

    `mode` and `width` come from the bundle being produced (owner P0-2).

    Two further contracts (owner §4):

      * the BASELINE is the bundle's own stored `as-is` member, not a fresh run
        of it. Re-running meant the decomposition compared against a stream
        nobody kept, so the published member and the analysis baseline were only
        *probably* identical -- an evidence contract has to check, not assume;
      * every perturbation arm's RAW STREAM is written into the bundle and
        digested. Previously the six runs existed only inside the analysis
        function and the chain stopped at a derived JSON, so nothing downstream
        could re-derive the table or check which forcing produced it.
    """
    made = []
    for n in nsplits:
        member = out / f"n{n}.{mode}.txt"
        keep: dict = {}
        path = out / f"n{n}.{mode}.metric_trajectory.json"
        path.write_text(rm.json.dumps(
            mtj.analysis(str(exe), n, mode=mode, width=width,
                         baseline_stream=member.read_text(), keep=keep),
            indent=2, sort_keys=True) + "\n")
        made.append({"file": path.name, "nsplit": n,
                     "analysis": "metric_trajectory", "sha256": rm.sha256(path),
                     **_analyzer_pin("g33_metric_trajectory")})
        for arm, text in sorted(keep.items()):
            if arm == "as-is":
                continue                      # already published as the member
            ap = out / f"n{n}.{mode}.{arm.replace('+', 'plus').replace('-', 'minus')}.txt"
            ap.write_text(text)
            made.append({"file": ap.name, "nsplit": n, "analysis": "arm_stream",
                         "arm": arm, "sha256": rm.sha256(ap),
                         "runtime_argv": [str(n), mode, str(width), arm]})
    return made


#: Every module whose BYTES decide what a bundle contains -- the analyzers that
#: compute the numbers AND the strict parsers that admit the raw members. A
#: parser is not a lesser link: an analysis is only as good as the stream it was
#: allowed to read, and a wrong parser lets a truncated, duplicated or
#: mis-schema'd member through before any analyzer sees it (owner P0-2).
PRODUCER_MODULES = (
    "g33_refine_experiment", "g33_refine_manifest", "g33_build_provenance",
    # strict parsers -- these decide which raw members are admissible
    "g33_refine_analyze", "g33_number_transport", "g33_probe_read",
    # analyzers -- these decide what the numbers are
    "g33_matched_closure", "g33_cap_interface", "g33_dual_ledger",
    "g33_defect_magnitude", "g33_metric_trajectory",
)


def _pin(module: str) -> dict:
    """Where this module's bytes can be recovered from later."""
    path = f"harness/{module}.py"
    return {"path": path,
            "content_sha256": rm.sha256(HERE / f"{module}.py"),
            "commit": rm._git("rev-parse", "HEAD"),
            "blob_sha": rm._git("rev-parse", f"HEAD:{path}")}


def require_pinned_producer() -> None:
    """Every module that will RUN must be byte-identical to its HEAD blob.

    The manifest pins `git rev-parse HEAD:path`, but the analysis executes the
    WORKING-TREE module. An uncommitted edit therefore RAN while the manifest
    recorded the committed bytes, and the checker -- which resolves the blob --
    passed. `G33-CHAIN-003` asserted a dirty-tree refusal to rule this out; no
    such refusal existed, the producer merely RECORDED `tree_dirty` (owner
    P0-1). This is that refusal, and it compares the executed bytes rather than
    the tree's overall cleanliness, so an unrelated dirty file does not block a
    run while an edited analyzer does.
    """
    bad = []
    for module in PRODUCER_MODULES:
        path = f"harness/{module}.py"
        head = rm._git("rev-parse", f"HEAD:{path}")
        work = rm._git("hash-object", str(HERE / f"{module}.py"))
        if not head:
            bad.append(f"{path}: not in HEAD")
        elif head != work:
            bad.append(f"{path}: ran {work[:12]}, HEAD holds {head[:12]}")
    if bad:
        raise SystemExit(
            "REFUSED: the code that would run is not the code the manifest "
            "would pin.\n  " + "\n  ".join(bad) +
            "\nCommit the change, or the bundle records bytes that did not run.")


def _analyzer_pin(module: str) -> dict:
    """How to find the analyzer's bytes LATER: its commit and its git blob.

    `analyzer_sha256` alone can only answer "is today's file still the same",
    never "what did this bundle run" -- so an analyzer that legitimately moves
    on takes the answer with it. A blob SHA at a pinned commit is RESOLVABLE:
    `git rev-parse <commit>:<path>` returns those exact bytes whatever the
    working tree now holds (owner §16-6).
    """
    path = f"harness/{module}.py"
    return {"analyzer": path,
            "analyzer_sha256": rm.sha256(HERE / f"{module}.py"),
            "analyzer_commit": rm._git("rev-parse", "HEAD"),
            "analyzer_blob_sha": rm._git("rev-parse", f"HEAD:{path}")}


def _analyses(out: Path, exe: Path, nsplits, mode: str) -> list:
    """Run every analysis on every member, write it beside the member, digest it.

    The digest of the ANALYZER is recorded next to the digest of its output: an
    analysis JSON identifies what was concluded, and the module identifies the
    code that concluded it. Neither alone lets a reader re-derive the table.
    """
    made = []
    for n in nsplits:
        stream = (out / f"n{n}.{mode}.txt").read_text()
        for name, (mod, fn) in ANALYSES.items():
            path = out / f"n{n}.{mode}.{name}.json"
            path.write_text(rm.json.dumps(fn(stream), indent=2,
                                          sort_keys=True) + "\n")
            made.append({"file": path.name, "nsplit": n, "analysis": name,
                         "sha256": rm.sha256(path), **_analyzer_pin(mod)})
    return made


def produce(dest: Path, *, fixture: str, algo: str, nsplits, mode: str,
            nflux: bool, module: Path, findings=(), arm: str = "reference",
            rho_profile: str = "as-is") -> Path:
    """Build, run, validate and publish. Returns the published bundle."""
    # MATERIALISE FIRST (owner §13 P1). `nsplits` is walked six times below --
    # the duplicate check, the member loop, the analyses, the arm streams. A
    # generator is exhausted by the first walk, and every later one sees an
    # empty sequence: the bundle publishes with zero members, no error, and a
    # manifest that looks complete. Nothing downstream can tell that apart from
    # a bundle that was asked for nothing.
    nsplits = tuple(nsplits)
    require_pinned_producer()
    # f64 + nflux is a WRONG-NUMBER path, not merely an unsupported one (owner
    # P0-E2). The overlay's number records write `'f32', transfer(<real>, 0)`;
    # under -fdefault-real-8 that takes four bytes of an eight-byte value into an
    # int32 mold and labels the result f32, so the parser reads a valid-looking
    # f32 bit pattern that is not the number. The f64 branch also runs only
    # probe_members(), so nothing would parse G33N even though the manifest would
    # record an nflux parser. Refused until an f64 number protocol exists.
    if arm == "f64" and nflux:
        raise SystemExit(
            "--arm f64 with --nflux is refused: the G33F number records are "
            "declared f32 and would carry four bytes of an eight-byte real. An "
            "f64 number stream needs its own record family (16-hex-digit), not "
            "the f32 one relabelled.")
    # A density arm is a NUMBER-transport experiment, and only G33N and G33P
    # carry the arm. Plain G33R does not, and changing that header would
    # invalidate every archived decision artifact (72 committed members) and the
    # pinned non-invasiveness baseline -- an owner decision, not this producer's.
    # So the gap is closed by construction instead: a non-default profile cannot
    # be published through a path that would not record it (owner §9).
    if rho_profile != "as-is" and not (nflux or arm in ("probe", "f64")):
        raise SystemExit(
            f"--rho-profile {rho_profile} needs --nflux (or a probe/f64 arm): "
            f"the plain G33R stream does not record the density arm, so the "
            f"bundle would be unidentifiable from its raw members.")
    # A repeated nsplit on the COMMAND LINE never reaches the manifest's
    # duplicate check: both members write the same filename, the second
    # overwrites the first, and the published directory holds one (owner
    # P1-11.5). Refused where it is still visible.
    if len(nsplits) != len(set(nsplits)):
        dup = sorted({n for n in nsplits if nsplits.count(n) > 1})
        raise SystemExit(
            f"--nsplit repeats {dup}: both members would write one filename and "
            f"the second would overwrite the first, so the bundle would silently "
            f"contain fewer members than requested.")
    width = fixture_width(fixture)
    tmp = Path(tempfile.mkdtemp(prefix=".g33-bundle-", dir=dest.parent))
    try:
        exe = build(tmp, fixture, algo, nflux, arm)
        if arm == "f64":
            # An f64 build emits no G33R at all, so there are no refinement
            # members to strict-parse; the probe stream is the artifact, and it
            # is read by its own parser.
            runs = probe_members(exe, tmp, nsplits, mode, rho_profile, width)
            # The cross-member contract the manifest builder cannot apply on this
            # path: it leaves `runs` empty for a supplied member_reader, so an
            # f64 bundle got every per-member check and none of the between-member
            # ones (owner §8.4).
            pr.require_probe_chain(runs)
        else:
            runs = members(exe, tmp, nsplits, mode, arm=arm, nflux=nflux,
                           rho_profile=rho_profile, width=width)
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
        # The FORCING INTERVENTION, and the exact command line that applied it
        # (owner §5.2). Without these a bundle records what was built and run but
        # not what experiment it is an arm of.
        man["rho_profile"] = rho_profile
        man["runtime_argv"] = [_argv(Path("g33_refine_driver"), n, mode,
                                     rho_profile, width)[1:] for n in nsplits]
        # The ANALYSES, produced by the bundle and digested into it (owner §14-4).
        # A claim could pin a raw stream and a manifest, but the numbers it quotes
        # come from an analysis that ran somewhere else and left nothing behind --
        # so "the run is pinned" stopped one step short of the table.
        man["analyses"] = _analyses(tmp, exe, nsplits, mode) if nflux else []
        # The metric/trajectory split needs FOUR runs of the same driver, so it
        # is a bundle-level analysis rather than a per-member one. Only for the
        # unperturbed arm: running it from a perturbed bundle would take that
        # arm as its own baseline.
        if nflux and rho_profile == "as-is":
            man["analyses"] += _driver_analyses(tmp, exe, nsplits, mode, width)
        # The parser that ACTUALLY approved these members (owner §10.2): the
        # manifest recorded g33_refine_analyze.py even for an f64 arm, whose
        # members are read by the probe parser.
        parsers = [HERE / ("g33_probe_read.py" if arm == "f64"
                           else "g33_refine_analyze.py")]
        if arm == "probe":
            parsers.append(HERE / "g33_probe_read.py")
        if nflux:
            parsers.append(HERE / "g33_number_transport.py")
        # COMMIT + BLOB, like the analyzers (owner P0-2). A parser is not a
        # lesser link: an analysis is only as good as the stream it was allowed
        # to read, and a wrong parser admits a truncated, duplicated or
        # mis-schema'd member before any analyzer sees it. Recording only a
        # content digest left these checkable against today's working tree and
        # nothing else -- the same defect §16-6 fixed for the analyzers.
        man["member_parsers"] = [_pin(q.stem) for q in parsers]
        # Every module whose bytes decided what this bundle contains, pinned the
        # same way, so the chain does not stop at the ones a reader thinks to ask
        # about.
        man["producer_modules"] = [_pin(m) for m in PRODUCER_MODULES]
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
        # Addressed by the IDENTITY digest, not the file digest: the manifest
        # carries diagnostic paths that differ every run, so hashing the whole
        # file gave a new address each time and the "identical rerun reuses the
        # bundle" property held only under fake provenance (owner §10.3).
        final = store / rm.identity_digest(man)[:16]
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
    ap.add_argument("--rho-profile", default="as-is",
                    choices=("as-is", "uniform", "inverted", "x2", "offset+", "offset-"),
                    help="density-control arm; recorded in the stream header and "
                         "the manifest, so an arm is identifiable from the "
                         "artifact rather than from a document")
    ap.add_argument("--arm", default="reference",
                    choices=("reference", "probe", "f64"),
                    help="f64 is an INSTRUMENT: it emits no G33R and is never "
                         "decision evidence")
    ap.add_argument("--module", type=Path,
                    default=Path("host/KIM-meso_v1.0/phys/module_mp_kdm6.F"))
    ap.add_argument("--finding", type=Path, action="append", default=[])
    a = ap.parse_args(argv)
    # absolute(), NOT resolve(): once `dest` is a symlink into the bundle store,
    # resolve() follows it and the next publish writes its store INSIDE the
    # previous bundle (owner §10.3 fallout, found by rerunning for real).
    dest = produce(a.outdir.absolute(), fixture=a.fixture, algo=a.algo,
                   nsplits=[int(x) for x in a.nsplit.split(",")], mode=a.mode,
                   nflux=a.nflux, module=a.module, findings=a.finding, arm=a.arm,
                   rho_profile=a.rho_profile)
    print(dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
