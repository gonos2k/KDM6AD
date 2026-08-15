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
import ast
import hashlib
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
import g33_run_matrix as rmx          # noqa: E402  (run role: makes arm streams)


def _an(name: str):
    """An ANALYZER module, imported when an analysis runs -- never before.

    The analyzers were imported at module load, so their top-level code
    executed before the raw driver was built or run. The identity layering
    claims analysis-only bytes cannot influence the run; a Python import is
    code EXECUTION, not a dependency declaration, so an import-time side
    effect -- an environment variable, a numeric-context change, a monkey
    patch -- would have run first and the claim would rest on inspection of
    today's analyzers rather than on structure (owner review §8). Importing
    at dispatch time puts every raw member on disk, strict-parsed, before any
    analyzer's first statement executes.
    """
    import importlib
    return importlib.import_module(name)

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
            nflux=False, rho_profile="as-is", width=3, levels=None) -> dict:
    """Run every member and STRICT-parse EVERY protocol it emits (owner P0-4).

    A bundle used to be published after validating only G33R, so a probe arm
    could ship a G33P stream that was truncated, transposed or NaN, and an
    --nflux arm could ship a G33N stream nothing had parsed. The arm declares
    which protocols must be present; each is read by its own strict parser.

    The G33N leg is pinned to the FIXTURE's domain, not merely to itself
    (owner review §4). `calls()` proves the tiles partition 1..W for one W and
    one K; nothing proved W and K were the fixture's B and K, so a stdout
    whose window protocol covered 1..3 beside a G33N covering 1..2 was two
    internally-strict protocols describing different domains, and every G33N
    analysis silently omitted column 3. The arm streams have carried this pin
    since the typed `ran` block; the PRIMARY members -- the ones every claim
    binds into -- did not.
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
            _require_fixture_domain(text, p.name, n, mode, rho_profile,
                                    width, levels, runs[n])
    return runs


def _require_fixture_domain(text, name, n, mode, rho, width, levels, run):
    """The G33N leg against the fixture AND the window protocol beside it.

    Three parties describe one run in a single stdout: the G33N header, the
    window records (G33R/G33P), and the member metadata the manifest will
    carry. Any two agreeing proves nothing about the third, so all three are
    tied here, at production, where the text is in hand.
    """
    rid, parsed = nt.validated_run_identity(text, expected_width=width,
                                            expected_levels=levels,
                                            with_calls=True)
    want = {"nsplit": n, "carry": mode, "rho": rho, "width": width}
    got = {k: rid[k] for k in want}
    if got != want:
        raise ra.RefineError(
            f"{name}: the G33N leg declares {got}, the member is being "
            f"published as {want}")
    # ...and the WINDOW protocol in the same stdout. `run` is keyed
    # (class, field, col, k); its columns and levels are the window's domain.
    # EXACT sets, not max/len (owner review §4): {1,3} has max 3, {-1,0,1,2}
    # has len 4, and either is a different domain wearing the right summary.
    wcols = {k[2] for k in run if len(k) == 4 and k[0] == "state"}
    wks = {k[3] for k in run if len(k) == 4 and k[0] == "state"}
    if wcols != set(range(1, rid["width"] + 1)):
        raise ra.RefineError(
            f"{name}: the window protocol covers columns {sorted(wcols)} "
            f"and the G33N leg covers exactly 1..{rid['width']} -- two "
            f"protocols, two domains, one stdout")
    if wks != set(range(rid["levels"])):
        raise ra.RefineError(
            f"{name}: the window protocol carries levels {sorted(wks)} and "
            f"the G33N leg declares exactly 0..{rid['levels'] - 1}")
    _require_same_run(name, rid, run, parsed)


def _require_same_run(name, rid, run, parsed):
    """The SAME-RUN contract (owner review §6): the protocols in one stdout
    record the same facts twice, and until here nothing compared them.

    Two internally-strict protocols can describe two different runs: a G33N
    leg declaring legacy/delt=100 beside a window declaring
    conservative/delt=300 passed every check, because each fact was validated
    only inside its own protocol. Every fact both sides record is compared;
    a fact only one side records cannot be, and stays with that side's own
    checks. Floats compare as WORDS AT THE MEMBER'S PRECISION -- the two
    protocols print the same value in different notations, so word equality
    is the honest test and a tolerance would re-admit genuinely different
    numbers. The width comes from the window's declared precision (Codex):
    comparing an f64 member's records as f32 words dropped 29 bits, so two
    DISTINCT f64 streams whose rho/delz differed below f32 resolution
    compared equal -- the conflation this contract exists to refuse. On an
    f64 member both sides carry exact f64 (16-hex payloads, 17-digit
    decimals); on an f32 member the f32 word is the value model itself.
    """
    fmt = ">d" if run.get(("meta", "precision")) == "f64" else ">f"

    def word(v):
        return struct.pack(fmt, v)

    walg = run.get(("meta", "algorithm"))
    if walg is not None and walg != rid["algorithm"]:
        raise ra.RefineError(
            f"{name}: the window protocol ran {walg}, the G33N leg ran "
            f"{rid['algorithm']} -- two algorithms, one stdout")
    # delt/dtcld reach the window through the header's F0.6 print -- a
    # SIX-DECIMAL channel on both G33R and G33P, whatever the member's
    # precision. Word equality at f64 width therefore refused VALID
    # non-integral splits (Codex): delt = 300/7 is exact in the G33N word and
    # "42.857143" in the window, two spellings of one recorded fact. A record
    # can only bind as tightly as its channel, so these two compare at the
    # channel's resolution: the G33N word must PRINT to the window's record.
    #
    # ...and the window's value must itself BE that channel's output (Codex,
    # round two): rounding BOTH sides re-admitted forgery, because a header
    # carrying delt=42.8571425 -- more precision than F0.6 can produce, and a
    # genuinely different number than the G33N word -- rounded to the same
    # six decimals and bound. This parser judges arbitrary artifacts and may
    # not re-assume the producer's printing, so a value that does not
    # round-trip through the channel is refused, not rounded. The
    # full-precision channels (the per-cell forcing below) keep word equality
    # at the member's width.
    def rec6(v):
        return f"{v:.6f}"

    wdelt = run.get(("meta", "delt"))
    if wdelt is None:
        raise ra.RefineError(
            f"{name}: the window protocol declares no delt to hold the G33N "
            f"leg's {rid['delt']} to -- the same-run contract cannot bind")
    for label, wv in (("delt", wdelt), ("dtcld", run.get(("meta", "dtcld")))):
        if wv is not None and float(rec6(wv)) != wv:
            raise ra.RefineError(
                f"{name}: the window protocol's {label}={wv!r} carries more "
                f"precision than the F0.6 channel can produce -- not that "
                f"channel's record, so nothing to bind at its resolution")
    if rec6(wdelt) != rec6(rid["delt"]):
        raise ra.RefineError(
            f"{name}: the window protocol stepped delt={wdelt}, the G33N leg "
            f"stepped delt={rid['delt']} -- two timesteps, one stdout")
    wdt = run.get(("meta", "dtcld"))
    if (wdt is not None and rid["dtcld"] is not None
            and rec6(wdt) != rec6(rid["dtcld"])):
        raise ra.RefineError(
            f"{name}: the window protocol sub-cycled at dtcld={wdt}, the "
            f"G33N leg at {rid['dtcld']}")
    wn = run.get(("meta", "ntile"))
    if wn is not None and wn != rid["ntile"]:
        raise ra.RefineError(
            f"{name}: the window protocol declares {wn} tiles, the G33N leg "
            f"ran {rid['ntile']}")
    wt = run.get(("meta", "tiles"))
    if wt is not None and tuple(wt) != rid["tile_sizes"]:
        raise ra.RefineError(
            f"{name}: the window protocol decomposed as {tuple(wt)}, the "
            f"G33N leg as {rid['tile_sizes']} -- two decompositions, one run")
    # The forcing VALUES, per cell (owner review §6): matched closure builds
    # the physical layer mass from G33N's rho/delz beside the window's initial
    # qv, which silently assumes the two protocols' rho/delz are the same
    # numbers. Assume nothing: compare every cell of every call.
    frc = {(k[1], k[2], k[3]): v for k, v in run.items()
           if k[0] == "forcing" and k[1] in ("rho", "delz")}
    if not frc:
        raise ra.RefineError(
            f"{name}: the window protocol carries no rho/delz forcing to hold "
            f"the G33N leg's to -- the same-run contract cannot bind")
    for call in parsed:
            for (lp, c, kk), rec in call["outer_pre_sed"].items():
                for nm in ("rho", "delz"):
                    wv = frc.get((nm, c, kk))
                    if wv is None or word(rec[nm]) != word(wv):
                        raise ra.RefineError(
                            f"{name}: call {call['call_id']} loop {lp} "
                            f"col {c} level {kk}: G33N {nm}={rec[nm]!r} vs "
                            f"window forcing {wv!r} -- the physical measure "
                            f"would be built from two different runs")


def _agree(g33r: dict, g33p: dict, name: str) -> None:
    """At the probe arm the same f32 values are written twice — raw hex on G33R
    and decimal on G33P. Requiring them to agree catches exactly the two defects
    that got through before: a transposed index and a format that dropped an
    exponent's `E`.

    BOTH directions (owner review §4.3): checking only that every G33R key has
    a G33P counterpart let G33P carry records G33R never wrote -- {1,3} against
    {1,2,3} compared two columns and called three agreed. The two protocols
    must describe the same record universe before any value is compared."""
    fams = ("state", "initial", "forcing", "prec")
    kr = {k for k in g33r if k[0] in fams}
    kp = {k for k in g33p if k[0] in fams}
    if kr != kp:
        raise pr.ProbeError(
            f"{name}: G33R and G33P describe different record universes: "
            f"{len(kp - kr)} only on G33P, {len(kr - kp)} only on G33R")
    for key, hexv in g33r.items():
        if key[0] not in fams:
            continue
        got = g33p[key]
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
                  rho_profile: str = "as-is", width: int = 3,
                  levels=None, nflux=False) -> dict:
    """Run every member: G33P strict parse AND the fixture-domain pin.

    The f64 path validated only G33P; the G33N leg in the same stdout was read
    later by each analysis without a fixture width to hold it to, so a G33N
    covering fewer columns than the window protocol would pass every strict
    parse and the analyses would silently omit the rest (owner review §4).
    The pin reads the G33N header, so it applies exactly when the build emits
    one -- an --nflux build; without the overlay there is no transport stream
    for any parser to hold to anything.
    """
    runs = {}
    for n in nsplits:
        p = out / f"n{n}.{mode}.txt"
        text = _run(_argv(exe, n, mode, rho_profile, width))
        p.write_text(text)
        runs[n] = pr.read(text)
        if nflux:
            _require_fixture_domain(text, p.name, n, mode, rho_profile,
                                    width, levels, runs[n])
    return runs


#: analysis name -> (module, callable taking the stream) (owner §14-4). Only for
#: `--nflux` bundles: these all read the extension records.
ANALYSES = {
    "matched_closure": ("g33_matched_closure", lambda s: _an("g33_matched_closure").analysis(s)),
    "cap_interface": ("g33_cap_interface", lambda s: _an("g33_cap_interface").analysis(s)),
    "extension_protocol": ("g33_number_transport", lambda s: _protocol(s)),
    # Both column measures, always (owner §9): reporting one makes a statement
    # about the OPERATOR read as a statement about the ATMOSPHERE.
    "dual_ledger": ("g33_dual_ledger", lambda s: _an("g33_dual_ledger").analysis(s)),
    # What the headline percentage is a percentage OF (owner §11).
    "defect_magnitude": ("g33_defect_magnitude", lambda s: _an("g33_defect_magnitude").analysis(s)),
    # WHICH sub-step schedule each chain ran, not how many records it emitted.
    # The parser has always filed mstep and mstepi together; nothing reduced
    # them, so `extension_protocol` could say 72 mstep records and not say that
    # column 3 ran three of them while the ice chain ran one.
    "substep_schedule": ("g33_substep_schedule", lambda s: _an("g33_substep_schedule").analysis(s)),
    # The COLUMN totals under both bases. `dual_ledger` answers this per
    # species; §9.2 asks it of the column, where the basis is the whole answer
    # on a column that closes to roundoff and changes nothing on one that does
    # not.
    "water_enthalpy_basis": ("g33_water_enthalpy_basis",
                             lambda s: _an("g33_water_enthalpy_basis").analysis(s)),
    # Water destroyed INSIDE the column is not precipitation (owner §16-4).
    # Both ledgers, so the correction is visible rather than a silent swap.
    "internal_cap_enthalpy": ("g33_cap_interface",
                              lambda s: _an("g33_cap_interface").enthalpy_with_cap_sink(s)),
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


def _ran(text: str, *, nsplit: int, mode: str, width: int, rho: str,
         levels: int, where: str) -> dict:
    """The arm's run identity, TYPED and checked against the raw stream.

    `runtime_argv` is four strings and the schema compared two of them --
    argv[0] against `nsplit`, argv[3] against `arm`. The mode and the domain
    width were recorded and never read, so half the identity of an arbitrary v2
    manifest went unverified. And nothing compared any position against the
    RECORD the run produced, which is the only party that knows what actually
    ran rather than what a caller meant to ask for (owner priority 5).

    So the four fields are checked here, where the text is in hand: the stream's
    own STREAM_BEGIN carries nsplit, mode and the density arm, and its
    CALL_BEGIN brackets carry the columns, which is where the width is. A run
    that does not answer for itself cannot be published as an arm.
    """
    # ONE reader for run identity, the strict one (owner review §6): the
    # evidence chain and this function previously derived it separately, and
    # the chain's copy was two regular expressions that reported `matches` on
    # streams `calls()` refuses.
    try:
        got = nt.validated_run_identity(text, expected_width=width,
                                        expected_levels=levels)
    except nt.StreamError as e:
        raise ra.RefineError(f"{where}: {e}")
    # `levels` is the FIXTURE's K, passed in -- not read back from the stream
    # (owner review §9): `want["levels"] = got["levels"]` satisfied the schema
    # while checking the stream against itself, which is no check at all.
    want = {"nsplit": nsplit, "carry": mode, "rho": rho, "width": width,
            "levels": levels}
    if {k: got[k] for k in want} != want:
        raise ra.RefineError(
            f"{where}: the stream declares {got} and the manifest entry would "
            f"say {want} -- an arm that describes a different run than the one "
            f"it is filed as is worse than an unrecorded one")
    # `carry` is the multi-run block's spelling of the driver's mode argument.
    # One name for one argument, or the archive carries both.
    #
    # `levels` joins the block for the same reason `width` is in it: the run
    # identity is the domain the stream actually processed, and the chain
    # compares this block against `validated_run_identity`, which now proves
    # K as well as W (owner review §4).
    return {"nsplit": nsplit, "carry": mode, "width": width, "rho": rho,
            "levels": levels}


def _driver_analyses(out: Path, exe: Path, nsplits, mode: str,
                     width: int, levels: int) -> list:
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
        # The driver matrix runs ONCE, through the run-role module (owner
        # review §8): the arm streams are raw run content published into the
        # bundle, so the code that produces them must sit in the run recipe --
        # `g33_run_matrix` is imported directly, never through the analysis
        # dispatch. Both chains then read the SAME collected streams, which
        # makes chain-independence structural where it used to be a
        # compare-after-the-fact between two separate driver passes.
        keep = rmx.collect(str(exe), n, mode=mode, width=width,
                           baseline_stream=member.read_text())
        # BOTH chains. `mtj.analysis` has taken a `chain` since it was written
        # and nothing ever passed it, so every bundle carried the main chain
        # and the ice one existed only as a default nobody exercised --
        # G33-NUMBER-009 is entirely about ice and had no artifact to bind.
        for chain in ("main", "ice"):
            stem = f"n{n}.{mode}" + ("" if chain == "main" else f".{chain}")
            path = out / f"{stem}.metric_trajectory.json"
            path.write_text(rm.json.dumps(
                _an("g33_metric_trajectory").analysis(
                    str(exe), n, chain, mode=mode, width=width,
                    baseline_stream=member.read_text(), raw=keep),
                indent=2, sort_keys=True) + "\n")
            made.append({"file": path.name, "nsplit": n, "chain": chain,
                         "analysis": "metric_trajectory",
                         "sha256": rm.sha256(path),
                         **_analyzer_pin("g33_metric_trajectory")})
        for arm, text in sorted(keep.items()):
            if arm == "as-is":
                continue                      # already published as the member
            ap = out / f"n{n}.{mode}.{arm.replace('+', 'plus').replace('-', 'minus')}.txt"
            ap.write_text(text)
            made.append({"file": ap.name, "nsplit": n, "analysis": "arm_stream",
                         "arm": arm, "sha256": rm.sha256(ap),
                         # STRUCTURED, and checked against the stream's own
                         # header rather than restated from the arguments this
                         # function was called with (owner priority 5).
                         "ran": _ran(text, nsplit=n, mode=mode, width=width,
                                     rho=arm, levels=levels, where=ap.name),
                         "runtime_argv": [str(n), mode, str(width), arm]})
            # The arm's OWN defect magnitude. `metric_trajectory` reports each
            # arm as a ratio over the as-is baseline; a claim that also states
            # the arm's residual as a percentage of ITS surface flux was
            # therefore half-bindable, and binding half is what certified two
            # false numbers on G33-TRAJECTORY-001. The stream is published
            # precisely so this is re-derivable, so it is derived here.
            dp = out / f"{ap.stem}.defect_magnitude.json"
            dp.write_text(rm.json.dumps(
                _an("g33_defect_magnitude").analysis(text), indent=2,
                                        sort_keys=True) + "\n")
            made.append({"file": dp.name, "nsplit": n, "arm": arm,
                         "analysis": "defect_magnitude", "sha256": rm.sha256(dp),
                         **_analyzer_pin("g33_defect_magnitude")})
    return made


#: The modules a bundle's contents do NOT depend on the caller remembering.
#:
#: `PRODUCER_MODULES` was a hand-written tuple, so an analyzer added to
#: `ANALYSES` and not to the tuple escaped the working-byte binding entirely --
#: the one list whose completeness the binding depends on was the one nobody
#: checked (owner §9.2). It is DERIVED now: the core producer, plus every module
#: `ANALYSES` names, plus the strict parsers that admit raw members.
#:
#: A parser is not a lesser link: an analysis is only as good as the stream it
#: was allowed to read, and a wrong parser lets a truncated, duplicated or
#: mis-schema'd member through before any analyzer sees it (owner P0-2).
_CORE_MODULES = ("g33_refine_experiment", "g33_refine_manifest",
                 "g33_build_provenance",
                 # The LAYERED IDENTITY derivation. It decides the role graph a
                 # bundle records, and that block is what makes the ids
                 # reproducible from the archive rather than from a checkout --
                 # so its bytes decide what the recorded identity MEANS
                 # (owner priority 8).
                 "g33_identity",
                 # The OVERLAY generator's dependencies. `make_fortran_overlay`
                 # is pinned as a tracked build input, but what it imports was
                 # pinned by nothing -- and that code decides which
                 # instrumentation is injected into the frozen Fortran, so it
                 # decides what every record in the stream says (Codex).
                 "g33_schema", "g33_expectation",
                 # The reference UPDATE semantics: COLD_TERMS/WARM_TERMS, the
                 # source-order f32 accumulation and the positivity clamp. The
                 # qr process ledger decomposes against it, so these bytes
                 # decide what the decomposition MEANS. It became reachable the
                 # moment the ledger stopped restating the terms and started
                 # importing them, and the closure caught that on the next run
                 # (Codex) -- which is what the closure is for.
                 "g33_update_replay",
                 # The density-arm matrix runner (owner review §8): it decides
                 # what every published arm stream IS -- which arms run, and
                 # that requested equals declared -- so its bytes are run
                 # content's provenance. Split out of the metric-trajectory
                 # analyzer precisely so the run recipe pins it; the
                 # completeness check below caught its absence from this
                 # tuple, which is what the check is for.
                 "g33_run_matrix")
_PARSER_MODULES = ("g33_refine_analyze", "g33_number_transport", "g33_probe_read")


#: Tracked files the BUILD reads. `host/**` is gitignored and cannot be pinned
#: to a commit, so build_provenance keeps its content digests; these can be.
TRACKED_BUILD_INPUTS = (
    Path("harness/g33_fortran/refine_build.sh"),
    Path("harness/g33_fortran/make_fortran_overlay.py"),
    Path("harness/g33_fortran/g33_fortran_bindings.py"),
    Path("harness/g33_fortran/g33_refine_driver.f90"),
    Path("harness/g33_fortran/stub_wrf_error.f90"),
)


def _pin_path(rel: Path) -> dict:
    """Where a tracked file's bytes can be recovered from later.

    REFUSES an inconsistent triple. `content_sha256` records what RAN and
    `blob_sha` names what is RECOVERABLE; when they disagree the pin describes
    two different files, and the checker -- which only resolves the blob --
    passes it (owner P0-1/P0-2). Verified here rather than in a list of paths
    someone has to remember to extend: a pin that cannot be honest refuses to
    exist.
    """
    commit = rm._git("rev-parse", "HEAD")
    blob = rm._git("rev-parse", f"HEAD:{rel}")
    content = rm.sha256(HERE.parent / rel)
    if not blob:
        raise SystemExit(f"REFUSED: {rel} is not in HEAD, so nothing can pin it")
    recovered = hashlib.sha256(
        subprocess.run(["git", "cat-file", "blob", blob], cwd=HERE.parent,
                       capture_output=True).stdout).hexdigest()
    if recovered != content:
        raise SystemExit(
            f"REFUSED: {rel} ran as {content[:12]} but HEAD holds {recovered[:12]}"
            f" -- the pin would name a file that did not run. Commit the change.")
    return {"path": str(rel), "content_sha256": content,
            "commit": commit, "blob_sha": blob}


def producer_modules() -> tuple:
    """Every module whose bytes decide what a bundle contains."""
    return tuple(sorted(set(_CORE_MODULES) | set(_PARSER_MODULES)
                        | {mod for mod, _fn in ANALYSES.values()}
                        | {mod for mod, _fn in MULTI_RUN.values()}
                        | {"g33_metric_trajectory"}))


#: Where a harness module can live. `make_fortran_overlay` and
#: `g33_fortran_bindings` are in the g33_fortran/ subdirectory, and a resolver
#: that only looked in harness/ dropped them silently -- taking the whole
#: overlay generator, and everything IT imports, out of the closure (Codex).
_MODULE_DIRS = (HERE, HERE / "g33_fortran")


def _module_file(module: str):
    """The file backing `module`, or None."""
    return next((d / f"{module}.py" for d in _MODULE_DIRS
                 if (d / f"{module}.py").is_file()), None)


def pinned_paths() -> set:
    """Every file the bundle records a pin for, in either form: a producer
    module pinned by name, or a build input pinned by path. The comparison is
    over PATHS because those two namespaces overlap only by accident --
    `make_fortran_overlay` is pinned, but not as a module."""
    return {Path("harness") / f"{m}.py" for m in producer_modules()} \
        | set(TRACKED_BUILD_INPUTS)


def unpinned_reachable() -> set:
    """Reachable code that NOTHING pins. Empty, or the bundle's provenance is
    incomplete."""
    return {m for m in reachable_modules()
            if _module_file(m).relative_to(HERE.parent) not in pinned_paths()}


def _local_imports(module: str) -> set:
    """The harness modules `module` DEPENDS ON. By AST, not by text: a name in
    a comment or a docstring is not an import.

    A lazy `_an("...")` dispatch is a dependency edge like an `import`
    statement -- it names a module whose bytes decide the result -- and it is
    collected here so making an import lazy changes WHEN the code executes
    without changing what the derivation says it depends on. Without this, the
    lazy-import change would have silently dropped every analyzer from the
    reachable set and the role graph (owner review §8: execution isolation
    must not weaken the dependency record).
    """
    f = _module_file(module)
    if f is None:
        return set()
    names = set()
    for n in ast.walk(ast.parse(f.read_text())):
        if isinstance(n, ast.Import):
            names |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            names.add(n.module.split(".")[0])
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                and n.func.id == "_an":
            names |= {a.value for a in n.args
                      if isinstance(a, ast.Constant) and isinstance(a.value, str)}
    return {m for m in names if _module_file(m) is not None}


def reachable_modules() -> set:
    """Every harness module the producer can actually reach, COMPUTED.

    Two ways a module gets to decide what a bundle contains, and only one is an
    import:

      - imported, transitively, from the producer or any analysis module
      - EXECUTED by the build script -- `g33_build_provenance` is run as a
        subprocess and imported by nothing, so an import closure alone would
        miss it entirely

    This does not REPLACE `producer_modules()`. Deriving that list textually
    from a shell script would be worse than curating it: `fortran_build.sh`
    appears in refine_build.sh only inside comments, and a text scan pulls it
    in. What was missing is that nothing FAILED when the curated list drifted,
    so this is the check, not the source.
    """
    seeds = ({"g33_refine_experiment"} | {m for m, _fn in ANALYSES.values()}
             | {m for m, _fn in MULTI_RUN.values()} | _build_script_modules())
    seen = set()
    todo = list(seeds)
    while todo:
        m = todo.pop()
        if m in seen:
            continue
        seen.add(m)
        # THROUGH the subprocess modules too. Unioning them in at the end left
        # everything the overlay generator imports outside the closure, and
        # that code decides what instrumentation is injected into the frozen
        # Fortran -- so it decides what every record in the stream says (Codex).
        todo += list(_local_imports(m) - seen)
    return seen


def _build_script_modules() -> set:
    """Harness modules the build EXECUTES. Comment lines are stripped first --
    a script named in a comment is not a script that runs."""
    out = set()
    for sh in TRACKED_BUILD_INPUTS:
        p = HERE.parent / sh
        if p.suffix != ".sh" or not p.is_file():
            continue
        for line in p.read_text().splitlines():
            if line.lstrip().startswith("#") or not re.search(r"\bpython3?\b", line):
                continue
            out |= {m for m in re.findall(r"([a-z0-9_]+)\.py", line)
                    if _module_file(m) is not None}
    return out


def _pin(module: str) -> dict:
    """Where this module's bytes can be recovered from later."""
    return _pin_path(Path("harness") / f"{module}.py")


def _expect_reusable(final: Path, identity: str, man: dict) -> None:
    """An existing bundle directory may be adopted only if it IS this bundle.

    The address alone was the whole check, so a directory left by an interrupted
    run -- or edited by hand -- was republished under a digest it no longer
    matched. Verified: the manifest parses, satisfies its own schema, carries
    the same identity, and every file it declares is present with the digest it
    recorded (owner §9.1).
    """
    mf = final / "manifest.json"
    if not mf.is_file():
        raise SystemExit(f"REFUSED: {final} exists but has no manifest.json")
    try:
        have = rm.json.loads(mf.read_text())
    except ValueError as e:
        raise SystemExit(f"REFUSED: {final}/manifest.json will not parse: {e}")
    bad = rm.validate(have)
    if bad:
        raise SystemExit(f"REFUSED: {final} holds an invalid manifest:\n  "
                         + "\n  ".join(bad))
    if rm.identity_digest(have) != identity:
        raise SystemExit(
            f"REFUSED: {final} is addressed {identity[:16]} but its manifest "
            f"identifies as {rm.identity_digest(have)[:16]}")
    # NESTED inputs too. A multi-run analysis records the raw stdout it read,
    # with a digest each, and this loop walked only the three TOP-LEVEL blocks
    # -- so an interrupted or hand-edited directory whose `mr.*.txt` had been
    # changed or removed was adopted as this bundle, because the derived JSON
    # beside it still matched (owner §5.2).
    nested = [src for a in (have.get("analyses") or [])
              if isinstance(a, dict)
              for src in (a.get("inputs") or []) if isinstance(src, dict)]
    for entry in ((have.get("members") or []) + (have.get("analyses") or [])
                  + (have.get("build_artifacts") or []) + nested):
        f = final / entry["file"]
        want = entry.get("output_sha256") or entry.get("sha256")
        if not f.is_file():
            raise SystemExit(f"REFUSED: {final} declares {entry['file']} but it "
                             f"is missing -- the directory is incomplete")
        if rm.sha256(f) != want:
            raise SystemExit(f"REFUSED: {final}/{entry['file']} does not match "
                             f"the digest its manifest recorded")


def require_pinned_producer(fixture: str | None = None) -> None:
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
    paths = [f"harness/{m}.py" for m in producer_modules()]
    paths += [str(q) for q in TRACKED_BUILD_INPUTS]
    # The SELECTED fixture is compiled from the working tree but was absent from
    # the fixed tuple, so an uncommitted fixture published a bundle whose
    # `content_sha256` and `blob_sha` named different files (owner P0-1).
    if fixture:
        paths.append(f"harness/g33_fortran/{fixture}.f90")
    for path in paths:
        head = rm._git("rev-parse", f"HEAD:{path}")
        work = rm._git("hash-object", str(HERE.parent / path))
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


#: Analyses that run the DRIVER over several decompositions, name -> (module,
#: fn). A REGISTRY, mirroring ANALYSES, so `producer_modules()` derives their
#: modules the same way it derives the per-member ones. The first version
#: hardcoded `_analyzer_pin("g33_ncmin_locality")` inside the builder, which
#: put the analyzer's bytes into a bundle while leaving the module out of the
#: pin list -- the completeness check caught it as `unpinned_reachable`
#: (Codex). A registry cannot drift the way a hand-written call can.
MULTI_RUN = {
    "ncmin_locality": ("g33_ncmin_locality",
                       lambda exe, fixture: _ncmin().analysis(exe, fixture)),
    # WHICH PROCESS carries the difference the one above measures (owner §7).
    "qr_process_ledger": ("g33_qr_process_ledger",
                          lambda exe, fixture: _ledger().analysis(exe, fixture)),
}


def _ledger():
    import g33_qr_process_ledger as pl
    return pl


def _ncmin():
    import g33_ncmin_locality as nl
    return nl


def _multi_run_analyses(out: Path, exe: Path, fixture: str,
                        precision: str = "f32") -> list:
    """Analyses that run the DRIVER over several decompositions.

    Emitted only where the fixture can support the question. `ncmin_locality`
    compares decompositions that impose DIFFERENT thresholds, so on a
    single-surface fixture there is no across-class pair and the analysis
    refuses rather than reporting a one-directional result. Producing it there
    anyway would put a vacuous table in the bundle.

    ...and only where the PRECISION can. Both of these read the bundle's G33R
    member and `qr_process_ledger` replays f32 words besides, so at an f64 arm
    they were being handed a stream neither is defined on -- which surfaced as
    a parser error from inside the producer, indistinguishable in the bundle
    from an analysis nobody ran (owner priority 6).
    """
    made = []
    if len(_ncmin().equivalence_classes(fixture)) < 2:
        return made
    for name, (mod, fn) in MULTI_RUN.items():
        if not rm.applicable(name, precision):
            continue
        _ncmin().begin_capture()
        result = fn(str(exe), fixture)
        # The RAW streams this analysis consumed, preserved as bundle members.
        # Without them the chain reached the derived JSON, the analyzer and the
        # binary, but never the stdout those numbers were computed from: the
        # run was reproducible and the evidence was not retained, which are
        # different contracts (owner P0-EVIDENCE-1). The density arms have
        # always been kept this way.
        inputs = []
        for (_drv, nsp, carry, tiles, rho), text in _ncmin().recorded_runs().items():
            stem = f"mr.n{nsp}.{carry}.{rho}.tiles-{'-'.join(map(str, tiles))}.txt"
            rp = out / stem
            if not rp.exists():          # shared between analyses, written once
                rp.write_text(text)
            inputs.append({"file": stem, "sha256": rm.sha256(rp),
                           "runtime_argv": [str(nsp), carry,
                                            ",".join(map(str, tiles)), rho]})
        # FROM THE RESULT, not from the fixture. Deriving the decompositions
        # from the fixture recorded what the analysis was ASSUMED to have run,
        # and omitting nsplit/mode/rho let the entry read as though it shared
        # the bundle's configuration -- which it does not (Codex).
        ran = result["ran"]
        path = out / f"{fixture}.{name}.json"
        path.write_text(rm.json.dumps(result, indent=2, sort_keys=True) + "\n")
        made.append({
            "file": path.name, "analysis": name, "sha256": rm.sha256(path),
            "fixture": fixture, "ran": ran,
            "decompositions": ran["decompositions"],
            "inputs": sorted(inputs, key=lambda i: i["file"]),
            **_analyzer_pin(mod)})
    return made


def compositions_of(fixture: str) -> list:
    """The decompositions a multi-run analysis covered, from the fixture."""
    import g33_ncmin_locality as nl
    return nl.compositions(fixture_dims(fixture)[0])


def _analyses(out: Path, exe: Path, nsplits, mode: str,
              precision: str = "f32") -> list:
    """Run every APPLICABLE analysis on every member, write it beside the
    member, digest it.

    The digest of the ANALYZER is recorded next to the digest of its output: an
    analysis JSON identifies what was concluded, and the module identifies the
    code that concluded it. Neither alone lets a reader re-derive the table.

    Applicability is asked of `rm.ANALYSIS_PRECISIONS` rather than discovered by
    running the analyzer and seeing whether it raises: the two outcomes read the
    same from the bundle, and only one of them is a fact about the experiment
    (owner priority 6).
    """
    made = []
    for n in nsplits:
        stream = (out / f"n{n}.{mode}.txt").read_text()
        for name, (mod, fn) in ANALYSES.items():
            if not rm.applicable(name, precision):
                continue
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
    # A refinement experiment with no members is not a small experiment (owner
    # P0-E3). The generator fix stopped `nsplits` being exhausted; it did not
    # stop a caller passing an empty one, and every loop below then runs zero
    # times and publishes a manifest that looks complete.
    if not nsplits:
        raise SystemExit("--nsplit must name at least one member: a bundle with "
                         "no members is not a refinement experiment")
    if any(n < 1 for n in nsplits):
        raise SystemExit(f"--nsplit must be positive, got {sorted(nsplits)}")
    require_pinned_producer(fixture)
    # f64 + nflux WAS a wrong-number path: the overlay's number records wrote
    # `'f32', transfer(<real>, 0)`, and under -fdefault-real-8 that took four
    # bytes of an eight-byte value into an int32 mold and labelled the result
    # f32. The record family now exists and the width is carried by the stream's
    # own PROTOCOL header (owner D6), so the combination is allowed.
    #
    # The f64 branch still reads PROBE members: an f64 build emits no G33R, so
    # there is nothing for the refinement parser to read. What --nflux adds is
    # the G33N/G33F stream in the same stdout, which the number analyses take.
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
            runs = probe_members(exe, tmp, nsplits, mode, rho_profile, width,
                                 levels=fixture_dims(fixture)[1], nflux=nflux)
            # The cross-member contract the manifest builder cannot apply on this
            # path: it leaves `runs` empty for a supplied member_reader, so an
            # f64 bundle got every per-member check and none of the between-member
            # ones (owner §8.4).
            pr.require_probe_chain(runs)
        else:
            runs = members(exe, tmp, nsplits, mode, arm=arm, nflux=nflux,
                           rho_profile=rho_profile, width=width,
                           levels=fixture_dims(fixture)[1])
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
        precision = "f64" if arm == "f64" else "f32"
        man["analyses"] = (_analyses(tmp, exe, nsplits, mode, precision)
                           if nflux else [])
        # The metric/trajectory split needs FOUR runs of the same driver, so it
        # is a bundle-level analysis rather than a per-member one. Only for the
        # unperturbed arm: running it from a perturbed bundle would take that
        # arm as its own baseline.
        if nflux and rho_profile == "as-is":
            if rm.applicable("metric_trajectory", precision):
                man["analyses"] += _driver_analyses(tmp, exe, nsplits, mode,
                                                    width,
                                                    fixture_dims(fixture)[1])
            # Analyses of the bundle's OWN binary across decompositions. They
            # need the --nflux build, whose G33N records say which tiles the
            # kernel actually received.
            man["analyses"] += _multi_run_analyses(tmp, exe, fixture, precision)
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
        man["producer_modules"] = [_pin(m) for m in producer_modules()]
        # The TRACKED build inputs decide the raw streams as surely as the
        # analyzers decide the numbers, and build_provenance recorded only their
        # content digests -- checkable against today's working tree and nothing
        # else (owner §9.2). The private `host/**` sources stay content-only:
        # they are gitignored, so no commit holds them.
        man["tracked_build_inputs"] = [
            _pin_path(q) for q in TRACKED_BUILD_INPUTS
            + (Path("harness/g33_fortran") / f"{fixture}.f90",)]
        # The BINARY and its provenance are in the bundle -- the finding said
        # they were not, which was simply false: `os.rename(tmp, final)` moves
        # the whole build directory. Nothing verified them, so deleting or
        # editing the driver in an existing bundle left it reusable (owner §7).
        man["build_artifacts"] = [
            {"file": q.name, "sha256": rm.sha256(q)}
            for q in (tmp / n for n in ("g33_refine_driver",
                                        "build_provenance.json",
                                        "commands.txt", "sources.txt"))
            if q.is_file()]
        man["arm"] = arm
        # The SAME word the analyses were selected by, so the manifest cannot
        # declare one precision and have been analysed at another.
        man["precision"] = precision
        # The ROLE GRAPH the layered ids are derived under (owner priority 8).
        # Without it those ids are a function of the manifest AND of whichever
        # checkout computes them, so a refactor that moves a module between
        # roles moves a historical bundle's run_content_id with no bundle byte
        # having changed. Imported here rather than at module scope: g33_identity
        # imports this module, and the cycle only closes at call time.
        import g33_identity as gi
        man["identity"] = gi.identity_block(
            {a["analysis"] for a in man["analyses"] if a.get("analyzer")})
        # An instrument arm can never be decision evidence, and says so in the
        # artifact rather than only in prose.
        man["decision_eligible"] = False
        # ONE validator, called here and by the evidence checker, so a bundle
        # cannot be valid to the producer and invalid to the reader (owner
        # P0-2). Before publish, so a malformed bundle is never renamed into
        # place rather than being caught by whoever reads it later.
        violations = rm.validate(man)
        # ...and the RESOLVED graph check, which the schema deliberately does
        # not run -- reading blobs is not shape validation, and a public clone
        # may legitimately lack them. The PRODUCER may not: it pinned those
        # blobs seconds ago from its own HEAD, so `BlobUnavailable` here is a
        # broken pin, not an excusable absence. Without this the check ran only
        # AFTER publication, in the evidence chain -- so a regression in
        # `identity_block()` would publish a structurally-valid bundle and be
        # discovered by whoever read it later (owner review §4).
        try:
            violations += rm.graph_violations(man)
        except rm.BlobUnavailable as e:
            raise SystemExit(
                f"REFUSED: the identity graph cannot be resolved against the "
                f"pinned blobs at publish time -- {e}")
        if violations:
            raise SystemExit("REFUSED: the manifest does not satisfy "
                             f"{man['schema']}:\n  " + "\n  ".join(violations))
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
        # FULL digest (owner §9.1). A 16-hex prefix is 64 bits, and the
        # directory it names is REUSED without re-checking: a stale directory
        # from an interrupted run, a hand-edited one, or a different full digest
        # sharing the prefix would all be adopted as this bundle. The overlay
        # cache was widened to the whole digest for the same reason; the bundle
        # store had not been.
        identity = rm.identity_digest(man)
        final = store / identity
        # Content-addressed: an identical manifest is the same bundle. Removing
        # and rebuilding it would delete the directory `dest` currently points at
        # -- the very window this design exists to close -- so an existing one is
        # reused and the temp discarded. But only after it is VERIFIED: reuse
        # without checking is how a corrupt directory becomes a published one.
        if final.exists():
            _expect_reusable(final, identity, man)
        else:
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
