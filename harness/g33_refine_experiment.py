#!/usr/bin/env python3
"""One command that produces a refinement bundle, or produces nothing.

Owner P0-2/priority-2. The bundles were assembled by hand: `refine_build.sh` wrote
build provenance, a separate step ran the driver, and a third stitched outputs and
findings into one record. Nothing structurally prevented provenance from one build
being published beside members from another -- which is the failure the provenance
exists to make impossible.

    build -> run every member -> strict-parse -> cross-member checks
          -> result.json (five fields) -> ATOMIC publish

Every stage is fail-closed and the bundle is published by renaming a fully-built
temporary directory, so a run that dies half way leaves the previous bundle
exactly as it was rather than a half-replaced one.

    g33_refine_experiment.py <outdir> --fixture=NAME --algo=legacy \\
        --nsplit 3,6,12,24 [--nflux]

`--nflux` also turns on the number-flux/ice-substep overlay, and is recorded in
the manifest as `instrumented`, because an instrumented member is a different
artifact from a plain one even when the two agree bit for bit.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
from dataclasses import dataclass, replace
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
import g33_number_transport as nt     # noqa: E402

import g33_refine_analyze as ra        # noqa: E402
import g33_result as res
import g33_arms       # noqa: E402
import g33_probe_read as pr           # noqa: E402
import g33_run_matrix as rmx          # noqa: E402  (run role: makes arm streams)



def _an(name: str):
    """An ANALYZER module, imported when an analysis runs -- never before, so
    every raw member is on disk and strict-parsed before any analyzer's first
    statement executes."""
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
    return fixture_dims_from(
        (HERE / "g33_fortran" / f"{fixture}.f90").read_text(), fixture)


def fixture_dims_from(src: str, where: str = "<fixture>") -> tuple:
    """(columns, levels) from BYTES, so a caller holding the fixture the
    compiler actually read can ask them of those bytes rather than of
    whatever is in the tree now (owner review §5)."""
    m = re.search(r"integer,\s*parameter\s*::\s*B\s*=\s*(\d+)\s*,\s*"
                  r"K\s*=\s*(\d+)", src)
    if not m:
        raise FixtureContractError(f"cannot read dimensions B, K from {where}")
    return int(m.group(1)), int(m.group(2))


def fixture_width(fixture: str) -> int:
    """The fixture's column count.

    The tile argument is positional and precedes the profile, so a non-default
    profile must pass one -- and hardcoding `3` silently produced a tile-sum
    error on any fixture that is not three columns wide (owner §9).
    """
    return fixture_dims(fixture)[0]


class FixtureContractError(ValueError):
    """A fixture that cannot answer for its own parameters.

    A ValueError, not a SystemExit (owner review §8): the evidence chain
    judges arbitrary artifacts and must report `FIXTURE-UNRESOLVED` for a
    malformed pin rather than terminating the process that found it. The
    producer translates it at its own boundary, where exiting is right.
    """


def fixture_horizon_from(src: str, where: str = "<fixture>") -> float:
    """The fixture's TOTAL integration time, from its `DT_BITS` word.

    The third dimension of a fixture, and the one nothing checked (owner
    review §4). B and K say what the domain IS; `DT_BITS` says how long the
    experiment RUNS, and the driver derives every member's step from it as
    `f32(DT_BITS)/nsplit`. Without it the contract proved a run internally
    consistent -- both protocols agreeing on delt=20 at nsplit=12 -- while
    the horizon it integrated (240 s) was not the fixture's (300 s).

    Takes TEXT, so the evidence chain can pass the PINNED blob's bytes and
    the producer the working tree's, through one reader.
    """
    return struct.unpack(
        ">f", bytes.fromhex(fixture_dt_bits_from(src, where)))[0]


def fixture_dt_bits_from(src: str, where: str = "<fixture>") -> str:
    """The fixture's `DT_BITS` WORD, uppercase hex -- the canonical horizon.

    The decimal is a decode of it, and two different decimals can decode to
    one f32 (owner review §5), so the word is what a document is held to.
    """
    m = re.search(r"DT_BITS\s*=\s*int\(z'([0-9A-Fa-f]{8})'", src)
    if not m:
        raise FixtureContractError(f"cannot read DT_BITS from {where}")
    return m.group(1).upper()


def fixture_horizon(fixture: str) -> float:
    return fixture_horizon_from(
        (HERE / "g33_fortran" / f"{fixture}.f90").read_text(), f"{fixture}.f90")


def expected_geometry(total_seconds: float, nsplit: int,
                      precision: str, dtcldcr: float) -> tuple:
    """(delt, loops, dtcld) exactly as the DRIVER computes them, at the
    build's default-real width.

    PURE (owner review §4). `dtcldcr` was a module global read from the
    working tree's private kernel source, with a silent 120.0 fallback when
    the tree lacked it -- so the same historical bundle could get different
    verdicts on two hosts, and a checker whose answer depends on its
    checkout is not checking a content-addressed archive. It is a parameter
    now: the producer takes it from the frozen source it is about to
    compile against, and the evidence chain from the value the bundle
    RECORDED.

        delt  = f32(DT_BITS)/nsplit                  (driver F:362)
        loops = max(nint(delt/dtcldcr), 1)           (kernel F:930)
        dtcld = delt/loops, or delt when delt <= dtcldcr  (F:931-932)
    """
    w = ">d" if precision == "f64" else ">f"

    def r(v):
        return struct.unpack(w, struct.pack(w, v))[0]

    delt = r(r(total_seconds) / nsplit)
    limit = r(dtcldcr)
    # The QUOTIENT is formed at the build's width before `nint` sees it
    # (owner review §9): dividing in Python's binary64 and rounding that is
    # a different function near a half-integer boundary, and the kernel's
    # arithmetic is the one being certified.
    q = r(delt / limit)
    # Fortran `nint` rounds half AWAY FROM ZERO; Python's round() is
    # half-to-even, which differs at exactly q = n + 0.5.
    loops = max(int(math.floor(q + 0.5)), 1)
    dtcld = delt if delt <= limit else r(delt / loops)
    return delt, loops, dtcld


#: v2 added `algorithm`: which kernel the limit was read from is part of
#: the fact, and a tag whose required keys change without changing is a tag
#: that means two things (Codex).
#: v3 records the limit read from the bytes the compiler actually read --
#: an --nflux build feeds it a generated overlay, so the pinned module's
#: constant was an assumption about that overlay until now (owner review §4).
KERNEL_GEOMETRY_SCHEMA = "kdm6_subcycle_v3"
KNOWN_KERNEL_GEOMETRY_SCHEMAS = ("kdm6_subcycle_v1", "kdm6_subcycle_v2",
                                 "kdm6_subcycle_v3")
@dataclass(frozen=True)
class RunContract:
    """Everything a raw execution is held to, read ONCE per bundle.

    The producer read the kernel source for its members and the multi-run
    legs read it again per leg, so one bundle had two geometry authorities
    and a source edit between them would bind different legs to different
    limits (owner review §6). Frozen, passed down, never re-derived: the
    contract a stream answers to is the contract the bundle was built
    under, whatever the tree does afterwards.
    """
    fixture: str
    columns: int
    levels: int
    horizon: float
    dtcldcr: float
    algorithm: str
    precision: str
    mode: str
    rho_profile: str
    tiles: tuple

    def for_tiles(self, tiles) -> "RunContract":
        """The same contract with a different requested decomposition -- the
        one axis a multi-run leg legitimately varies."""
        return replace(self, tiles=tuple(tiles))


def kernel_source(algo: str):
    """The kernel module an arm compiles: the one registry names the arm, the
    file follows the name."""
    if algo not in g33_arms.ARMS:
        return None
    stem = {"legacy": "module_mp_kdm6", "conservative": "module_mp_kdm6_cons"}.get(
        algo, f"module_mp_kdm6_{algo}")
    return Path("host/KIM-meso_v1.0/phys") / f"{stem}.F"


def _dtcldcr_from(text: str, where: str) -> float:
    """The one declaration of `dtcldcr` in a kernel source's bytes."""
    hits = re.findall(r"::\s*dtcldcr\s*=\s*([0-9.]+)", text)
    if len(hits) != 1:
        raise SystemExit(
            f"REFUSED: {where} declares dtcldcr {len(hits)} times; the "
            f"geometry contract needs exactly one")
    return float(hits[0])


def kernel_geometry(precision: str = "f32", algo: str = "legacy",
                    compiled: Path | None = None) -> dict:
    """What the kernel this bundle compiles against uses for `dtcldcr`.

    Recorded IN the bundle so a reader never has to have the private source
    to know what the run was held to (owner review §4). REFUSES rather than
    defaulting: a silent 120.0 is a number nobody measured, and the whole
    contract above is built on it.
    """
    rel = kernel_source(algo)
    if rel is None:
        raise SystemExit(
            f"REFUSED: no kernel source is known for algorithm {algo!r}; the "
            f"build script compiles {sorted(g33_arms.ARMS)}")
    src = HERE.parent / rel
    if not src.is_file():
        raise SystemExit(
            f"REFUSED: {rel} is not here, so the sub-cycle limit the "
            f"{algo} kernel enforces cannot be read -- and a default would "
            f"be a number nobody measured")
    value = _dtcldcr_from(src.read_text(), str(rel))
    w = ">d" if precision == "f64" else ">f"
    # ...and the bytes the COMPILER read, where this build generated them.
    # The overlay is derived from the module, so the two agreeing is the
    # expected case -- but "expected" is what a contract exists to check,
    # and the executable was made from the overlay (owner review §4).
    compiled_word = None
    if compiled is not None:
        got = _dtcldcr_from(Path(compiled).read_text(errors="replace"),
                            str(compiled))
        if struct.pack(w, got) != struct.pack(w, value):
            raise SystemExit(
                f"REFUSED: {rel} declares dtcldcr {value} but the compiled "
                f"{Path(compiled).name} declares {got} -- the executable was "
                f"made from the second")
        compiled_word = struct.pack(w, got).hex().upper()
    return {"schema": KERNEL_GEOMETRY_SCHEMA,
            **({"compiled_dtcldcr_word": compiled_word,
                "compiled_source_sha256": hashlib.sha256(
                    Path(compiled).read_bytes()).hexdigest()}
               if compiled is not None else {}),
            "dtcldcr": struct.unpack(w, struct.pack(w, value))[0],
            "dtcldcr_storage": precision,
            "dtcldcr_word": struct.pack(w, value).hex().upper(),
            "algorithm": algo,
            "source_path": str(rel),
            "source_sha256": hashlib.sha256(src.read_bytes()).hexdigest()}


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
            nflux=False, rho_profile="as-is", width=3, levels=None,
            algo=None, fixture=None, horizon=None, dtcldcr=None) -> dict:
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
        runs[n] = ra.read(p, nsplit=n)          # what the analyses read
        # ONE validator, every arm (owner review §9): the profile every
        # current member answers to, plus -- when the build emits G33N --
        # the fixture-domain and same-run contract, against the window dict
        # this arm defines.
        validate_member_stream(text, name=p.name, nsplit=n, mode=mode,
                               rho=rho_profile, width=width, levels=levels,
                               arm=arm, algo=algo, fixture=fixture,
                               horizon=horizon, tiles=(width,),
                               transport=nflux, dtcldcr=dtcldcr)
    return runs


def _require_current_profile(run, name, width, levels, algo=None, *,
                             nsplit=None, horizon=None, precision="f32",
                             tiles=None, dtcldcr=None):
    """What TODAY'S producer requires of every member it publishes -- with or
    without instrumentation (owner review §8).

    The strict parsers keep INITIAL, the rho/delz forcing and the
    delt/loops/dtcld header OPTIONAL so archived streams from before those
    records existed still parse -- right for a reader of history, wrong for
    a producer of evidence: a non-instrumented bundle could publish members
    with no initial state, no forcing and no time geometry, and nothing
    compared the window's domain to the fixture at all. Reading the archive
    and producing into it are different contracts; this is the second one.
    """
    wcols = {k[2] for k in run if len(k) == 4 and k[0] == "state"}
    wks = {k[3] for k in run if len(k) == 4 and k[0] == "state"}
    if wcols != set(range(1, width + 1)) or wks != set(range(levels)):
        raise ra.RefineError(
            f"{name}: the window covers columns {sorted(wcols)} x levels "
            f"{sorted(wks)}, the fixture declares 1..{width} x 0..{levels - 1}")
    if not any(k[0] == "initial" for k in run):
        raise ra.RefineError(
            f"{name}: no INITIAL state -- every budget is measured from it, "
            f"and a current member without one is not evidence")
    names = {k[1] for k in run if k[0] == "forcing"}
    if not {"rho", "delz"} <= names:
        raise ra.RefineError(
            f"{name}: forcing carries {sorted(names)} -- a current member "
            f"publishes its rho*dz measure, not a promise of one")
    for fld in ("delt", "loops", "dtcld"):
        if ("meta", fld) not in run:
            raise ra.RefineError(
                f"{name}: the header declares no {fld} -- a current member "
                f"records its own time geometry")
    delt = run[("meta", "delt")]
    loops = run[("meta", "loops")]
    dtcld = run[("meta", "dtcld")]
    if not (delt > 0 and dtcld > 0 and loops >= 1
            and run[("meta", "nsplit")] >= 1):
        raise ra.RefineError(
            f"{name}: delt={delt}, loops={loops}, dtcld={dtcld}, "
            f"nsplit={run[('meta', 'nsplit')]} -- run geometry must be "
            f"positive")
    # The member's time geometry against the FIXTURE'S, computed the way the
    # driver computes it (owner review §4, §8). This replaced a fixed-six
    # PRODUCT inverse -- `loops*dtcld == delt` -- which the transport parser
    # had already abandoned for refusing VALID streams (f32 delt=400, L=3
    # gives 3 x 133.333328 = 399.999984). And a self-consistent triple was
    # never the question: 12 members stepping 20 s are internally perfect
    # and integrate 240 s of a 300 s fixture.
    if horizon is not None and dtcldcr is not None:
        want_d, want_L, want_h = expected_geometry(horizon, nsplit, precision,
                                                   dtcldcr)
        if f"{delt:.6f}" != f"{want_d:.6f}":
            raise ra.RefineError(
                f"{name}: stepped delt={delt} at nsplit={nsplit}, but the "
                f"fixture's {horizon} s horizon gives {want_d} -- the member "
                f"integrates {delt * nsplit} s of a {horizon} s experiment")
        if loops != want_L:
            raise ra.RefineError(
                f"{name}: ran {loops} inner loops, the kernel's rule gives "
                f"{want_L} for delt={want_d}")
        if f"{dtcld:.6f}" != f"{want_h:.6f}":
            raise ra.RefineError(
                f"{name}: sub-cycled at dtcld={dtcld}, the kernel's rule "
                f"gives {want_h}")
    # The window's OWN tile record, where it has one (Codex): G33P carries
    # the vector in its header, so a probe or f64 member substantiates the
    # requested decomposition with or without the transport leg -- which is
    # what a non-instrumented bundle needs, having no G33N to be held to.
    wt = run.get(("meta", "tiles"))
    if tiles is not None and wt is not None and tuple(wt) != tuple(tiles):
        raise ra.RefineError(
            f"{name}: the window protocol decomposed as {tuple(wt)}, the "
            f"caller asked for {tuple(tiles)} -- `ncmin` is set by a tile's "
            f"last column, so these are two operators")
    walg = run.get(("meta", "algorithm"))
    if algo is not None and walg is not None and walg != algo:
        raise ra.RefineError(
            f"{name}: the member ran {walg}, the caller asked to build "
            f"{algo!r}")


def validate_member_stream(text, *, name, nsplit, contract=None, mode=None,
                           rho=None, width=None, levels=None,
                           arm="reference", algo=None, fixture=None,
                           horizon=None, tiles=None, transport=True,
                           dtcldcr=None):
    """ONE validator for every raw driver stream (owner review §6).

    The primary members carried the full fixture-domain / same-run contract;
    the density arms were checked only through their G33N identity, and the
    ncmin decompositions through their own gate set -- load-bearing raw
    streams published under a WEAKER contract than the members beside them.
    Every raw execution routes through here now: the window protocol is
    parsed by the arm's own strict parser, then held to the same contract
    the primary members answer to.
    """
    # A CONTRACT, where the caller has one (owner review §6): every field
    # below then comes from the object the producer built once, rather than
    # from arguments each call site assembles -- and from a source nobody
    # re-reads.
    if contract is not None:
        mode = contract.mode if mode is None else mode
        rho = contract.rho_profile if rho is None else rho
        width = contract.columns if width is None else width
        levels = contract.levels if levels is None else levels
        algo = contract.algorithm if algo is None else algo
        fixture = contract.fixture if fixture is None else fixture
        horizon = contract.horizon if horizon is None else horizon
        dtcldcr = contract.dtcldcr if dtcldcr is None else dtcldcr
        tiles = contract.tiles if tiles is None else tiles
    # EVERY arm read here, including the probe (owner review §9). The
    # function claimed to be the one validator while picking `pr.read` for
    # f64 alone, so a probe stream was read as G33R and then held to a
    # contract that demands G33P metadata it had never parsed -- a direct
    # call would refuse a valid member, and the primary probe path worked
    # only because `members()` did the G33R/G33P/_agree dance itself. The
    # dance lives here now, and there is no second path.
    if arm == "f64":
        window = pr.read(text)                       # no G33R on this arm
    else:
        g33r = ra.read_text(text, nsplit=nsplit, label=name)
        window = g33r
        if arm == "probe":
            probe = pr.read(text)
            _agree(g33r, probe, name)
            # G33P is the side that carries precision/source/fixture, and
            # `_agree` has just tied G33R to it record for record.
            window = probe
    _require_current_profile(window, name, width, levels, algo=algo,
                             nsplit=nsplit, horizon=horizon,
                             precision="f64" if arm == "f64" else "f32",
                             tiles=tiles, dtcldcr=dtcldcr)
    if transport:
        _require_fixture_domain(text, name, nsplit, mode, rho, width, levels,
                                window, arm=arm, algo=algo, fixture=fixture,
                                horizon=horizon, tiles=tiles,
                                dtcldcr=dtcldcr)
    return window


def _require_fixture_domain(text, name, n, mode, rho, width, levels, run,
                            arm="reference", algo=None, fixture=None,
                            horizon=None, tiles=None, dtcldcr=None):
    """The G33N leg against the fixture AND the window protocol beside it.

    Three parties describe one run in a single stdout: the G33N header, the
    window records (G33R/G33P), and the member metadata the manifest will
    carry. Any two agreeing proves nothing about the third, so all three are
    tied here, at production, where the text is in hand.

    `arm`/`algo`/`fixture` are the EXPECTED experiment (owner review §5):
    what the caller asked to run, held against what the stream claims to be.
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
    _require_same_run(name, rid, run, parsed, arm, algo, fixture,
                      horizon=horizon, nsplit=n, tiles=tiles,
                      dtcldcr=dtcldcr)


def _require_same_run(name, rid, run, parsed, arm="reference", algo=None,
                      fixture=None, *, horizon=None, nsplit=None,
                      tiles=None, dtcldcr=None):
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
    # The comparison width comes from the EXPECTED arm, never from the
    # header's own claim (owner review §5): letting a stream declare
    # precision=f32 chose the f32 width for it, which re-opened the 29-bit
    # conflation this contract closed -- a forged label was choosing how
    # strictly the forgery was checked. The header must then AGREE with the
    # arm, so an honest label is redundant and a dishonest one is refused.
    fmt = ">d" if arm == "f64" else ">f"

    def word(v):
        return struct.pack(fmt, v)

    if arm in ("probe", "f64"):
        want_prec = "f64" if arm == "f64" else "f32"
        wprec = run.get(("meta", "precision"))
        if wprec != want_prec:
            raise ra.RefineError(
                f"{name}: the {arm} arm writes G33P at {want_prec}, this "
                f"header claims {wprec!r} -- a label may not choose the "
                f"width it is checked at")
        if run.get(("meta", "source_precision")) != "f32":
            raise ra.RefineError(
                f"{name}: source_precision "
                f"{run.get(('meta', 'source_precision'))!r} -- the reference "
                f"this archive instruments is f32, always")
    wfix = run.get(("meta", "fixture"))
    if fixture is not None and wfix is not None:
        # BOTH SPELLINGS THROUGH THE REGISTRY. The stream carries the id and the
        # caller passes the module name, and comparing them raw refused every
        # stream the moment the driver began emitting the record this check was
        # written for.
        import g33_fixture_v1 as _fx
        try:
            same = _fx.canonical_id(wfix) == _fx.canonical_id(fixture)
        except _fx.UnknownFixture:
            same = wfix == fixture
        if not same:
            raise ra.RefineError(
                f"{name}: the window protocol ran fixture {wfix!r}, the caller "
                f"asked for {fixture!r}")
    walg = run.get(("meta", "algorithm"))
    if walg is not None and walg != rid["algorithm"]:
        raise ra.RefineError(
            f"{name}: the window protocol ran {walg}, the G33N leg ran "
            f"{rid['algorithm']} -- two algorithms, one stdout")
    if algo is not None and walg is not None and walg != algo:
        raise ra.RefineError(
            f"{name}: the window protocol ran {walg}, the caller asked to "
            f"build {algo!r}")
    wrho = run.get(("meta", "rho_profile"))
    if wrho is not None and wrho != rid["rho"]:
        raise ra.RefineError(
            f"{name}: the window protocol declares rho_profile {wrho!r}, "
            f"the G33N leg ran {rid['rho']!r}")
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
    # The LOOP COUNT is a duplicate fact too (owner review §4, sixth round):
    # the window header records what the kernel ran, `calls()` has proven the
    # G33N records cover exactly 1..L -- two records of one fact, compared.
    wloops = run.get(("meta", "loops"))
    if wloops is not None and wloops != rid["loops"]:
        raise ra.RefineError(
            f"{name}: the window protocol ran {wloops} inner loops, the G33N "
            f"records cover 1..{rid['loops']}")
    # ...and the G33N leg answers to the FIXTURE directly, at its own word
    # width. The window carries delt/dtcld through a six-decimal channel, so
    # binding G33N to the window binds it only to six decimals: a G33N delt
    # differing from the fixture's below that resolution satisfies both
    # comparisons. Here the raw word meets the raw expectation.
    if horizon is not None and nsplit is not None and dtcldcr is not None:
        want_d, want_L, want_h = expected_geometry(
            horizon, nsplit, "f64" if arm == "f64" else "f32", dtcldcr)
        if word(rid["delt"]) != word(want_d):
            raise ra.RefineError(
                f"{name}: the G33N leg stepped delt={rid['delt']!r}, the "
                f"fixture's {horizon} s over {nsplit} splits is {want_d!r}")
        if rid["loops"] != want_L:
            raise ra.RefineError(
                f"{name}: the G33N records cover 1..{rid['loops']}, the "
                f"kernel's rule gives {want_L} loops")
        if rid["dtcld"] is not None and word(rid["dtcld"]) != word(want_h):
            raise ra.RefineError(
                f"{name}: the G33N leg sub-cycled at {rid['dtcld']!r}, the "
                f"kernel's rule gives {want_h!r}")
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
    # ...and the decomposition the CALLER ASKED FOR (owner review §5). Both
    # protocols agreeing proves one decomposition, not the requested one --
    # and `ncmin` is a scalar set by a tile's last column, so an unrequested
    # tiling changes the operator. In the density experiment that is a
    # confounder: the arm moves the density profile, an unchecked tile change
    # would move the threshold vector with it, and the residual could not be
    # attributed to the intervention.
    if tiles is not None and tuple(tiles) != rid["tile_sizes"]:
        raise ra.RefineError(
            f"{name}: ran the decomposition {rid['tile_sizes']}, the caller "
            f"asked for {tuple(tiles)} -- `ncmin` is set by a tile's last "
            f"column, so these are two operators")
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
    return {"file": path.name, "output_sha256": res.sha256(path),
            "nsplit": int(m.group(1)), "mode": m.group(2),
            "precision": r[("meta", "precision")],
            "source_precision": r[("meta", "source_precision")],
            "algorithm": r[("meta", "algorithm")],
            "fixture": r[("meta", "fixture")],
            "delt": r[("meta", "delt")], "loops": r[("meta", "loops")],
            "dtcld": r[("meta", "dtcld")]}


def probe_members(exe: Path, out: Path, nsplits, mode: str,
                  rho_profile: str = "as-is", width: int = 3,
                  levels=None, nflux=False, algo=None, fixture=None,
                  horizon=None, dtcldcr=None) -> dict:
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
        validate_member_stream(text, name=p.name, nsplit=n, mode=mode,
                               rho=rho_profile, width=width, levels=levels,
                               arm="f64", algo=algo, fixture=fixture,
                               horizon=horizon, tiles=(width,),
                               transport=nflux, dtcldcr=dtcldcr)
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
         levels: int, where: str, tiles=None) -> dict:
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
    if tiles is not None:
        want["tile_sizes"] = tuple(tiles)
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
    # The DECOMPOSITION is part of the run identity, not decoration: two
    # arm streams differing only in their tiling are two operators (owner
    # review §5), and a `ran` block that cannot say which one it ran cannot
    # be re-checked against the request by anything downstream.
    return {"nsplit": nsplit, "carry": mode, "width": width, "rho": rho,
            "levels": levels, "ntile": got["ntile"],
            "tile_sizes": list(got["tile_sizes"]),
            "tile_ranges": [list(r) for r in got["tile_ranges"]]}


def _driver_analyses(out: Path, exe: Path, nsplits, mode: str,
                     width: int, levels: int, algo=None, fixture=None,
                     horizon=None, dtcldcr=None) -> list:
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
            path.write_text(json.dumps(
                _an("g33_metric_trajectory").analysis(
                    str(exe), n, chain, mode=mode, width=width,
                    baseline_stream=member.read_text(), raw=keep),
                indent=2, sort_keys=True) + "\n")
            made.append({"file": path.name, "nsplit": n, "chain": chain,
                         "analysis": "metric_trajectory",
                         "sha256": res.sha256(path)})
        for arm, text in sorted(keep.items()):
            if arm == "as-is":
                continue                      # already published as the member
            ap = out / f"n{n}.{mode}.{arm.replace('+', 'plus').replace('-', 'minus')}.txt"
            ap.write_text(text)
            # The FULL member contract, not just the G33N identity (owner
            # review §6): these are load-bearing raw streams -- the density
            # decomposition is computed from them -- and they were published
            # under a weaker contract than the members beside them. The arm
            # name is the stream's expected rho profile.
            validate_member_stream(text, name=ap.name, nsplit=n, mode=mode,
                                   rho=arm, width=width, levels=levels,
                                   algo=algo, fixture=fixture,
                                   horizon=horizon, tiles=(width,))
            made.append({"file": ap.name, "nsplit": n, "analysis": "arm_stream",
                         "arm": arm, "sha256": res.sha256(ap),
                         # STRUCTURED, and checked against the stream's own
                         # header rather than restated from the arguments this
                         # function was called with (owner priority 5).
                         "ran": _ran(text, nsplit=n, mode=mode, width=width,
                                     rho=arm, levels=levels, where=ap.name,
                                     tiles=(width,)),
                         "runtime_argv": [str(n), mode, str(width), arm]})
            # The arm's OWN defect magnitude. `metric_trajectory` reports each
            # arm as a ratio over the as-is baseline; a claim that also states
            # the arm's residual as a percentage of ITS surface flux was
            # therefore half-bindable, and binding half is what certified two
            # false numbers on G33-TRAJECTORY-001. The stream is published
            # precisely so this is re-derivable, so it is derived here.
            dp = out / f"{ap.stem}.defect_magnitude.json"
            dp.write_text(json.dumps(
                _an("g33_defect_magnitude").analysis(text), indent=2,
                                        sort_keys=True) + "\n")
            made.append({"file": dp.name, "nsplit": n, "arm": arm,
                         "analysis": "defect_magnitude", "sha256": res.sha256(dp)})
    return made


def _expect_reusable(final: Path, fresh: dict) -> None:
    """An existing bundle directory may be adopted only if it IS this run: its
    record parses, identifies as this run's identity, holds the SAME files with
    the SAME digests this run just produced, and every file it names is present
    inside it.

    The third condition is the reproducibility contract. The identity is the
    experiment (commit, command, binary, input); the result is what the
    experiment produced. Same identity with a different result is not a bundle
    to re-publish and not one to reuse -- it is non-determinism, a hidden
    environment dependency, an unrecorded input or a changed analyzer, and it
    must be seen rather than resolved by keeping whichever bundle came first.
    """
    have = res.load(final)
    if res.identity(have) != res.identity(fresh):
        raise SystemExit(
            f"REFUSED: {final} is addressed {res.identity(fresh)[:16]} but its "
            f"record identifies as {res.identity(have)[:16]}")
    old, new = res.payloads(have), res.payloads(fresh)
    if old != new:
        differ = sorted(set(old) ^ set(new)) + \
            sorted(f for f in set(old) & set(new) if old[f] != new[f])
        raise SystemExit(
            f"REFUSED: {final} has this run's identity but a different result -- "
            f"the same experiment did not reproduce:\n  "
            + "\n  ".join(f"{f}: {old.get(f, 'absent')[:16]} -> "
                           f"{new.get(f, 'absent')[:16]}" for f in differ))
    bad = res.verify(final)
    if bad:
        raise SystemExit(f"REFUSED: {final} does not hold what its record says:\n  "
                         + "\n  ".join(bad))


#: Analyses that run the DRIVER over several decompositions, name -> (module,
#: fn). A registry mirroring ANALYSES, so the producer runs and records them
#: the same way it does the per-member ones.
MULTI_RUN = {
    "ncmin_locality": ("g33_ncmin_locality",
                       lambda exe, fixture, algo=None, contract=None:
                       _ncmin().analysis(exe, fixture, algo, contract)),
    # WHICH PROCESS carries the difference the one above measures (owner §7).
    "qr_process_ledger": ("g33_qr_process_ledger",
                          lambda exe, fixture, algo=None, contract=None:
                          _ledger().analysis(exe, fixture, algo, contract)),
}


def _ledger():
    # THROUGH THE SEAM: a multi-run analyzer imported directly was
    # attested by nothing, so its seed appeared in neither list and
    # `unattested_analyzers` could not be held to cover the seeds
    # (Codex).
    pl = _an("g33_qr_process_ledger")
    return pl


def _ncmin():
    nl = _an("g33_ncmin_locality")
    return nl


def _multi_run_analyses(out: Path, exe: Path, fixture: str,
                        precision: str = "f32", algo: str | None = None,
                        contract=None) -> list:
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
        if not res.applicable(name, precision):
            continue
        _ncmin().begin_capture()
        # The bundle's ALGORITHM, bound BEFORE publication (owner
        # review §7): without it a multi-run stream whose two
        # protocols agreed on `conservative` could enter the
        # immutable store and be refused only later, by the chain.
        result = fn(str(exe), fixture, algo, contract)
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
            inputs.append({"file": stem, "sha256": res.sha256(rp),
                           "runtime_argv": [str(nsp), carry,
                                            ",".join(map(str, tiles)), rho]})
        # FROM THE RESULT, not from the fixture. Deriving the decompositions
        # from the fixture recorded what the analysis was ASSUMED to have run,
        # and omitting nsplit/mode/rho let the entry read as though it shared
        # the bundle's configuration -- which it does not (Codex).
        ran = result["ran"]
        path = out / f"{fixture}.{name}.json"
        path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        made.append({
            "file": path.name, "analysis": name, "sha256": res.sha256(path),
            "fixture": fixture, "ran": ran,
            "decompositions": ran["decompositions"],
            "inputs": sorted(inputs, key=lambda i: i["file"])})
    return made


def compositions_of(fixture: str) -> list:
    """The decompositions a multi-run analysis covered, from the fixture."""
    nl = _an("g33_ncmin_locality")
    return nl.compositions(fixture_dims(fixture)[0])


def _analyses(out: Path, exe: Path, nsplits, mode: str,
              precision: str = "f32") -> list:
    """Run every APPLICABLE analysis on every member, write it beside the
    member, digest it.

    The digest of the ANALYZER is recorded next to the digest of its output: an
    analysis JSON identifies what was concluded, and the module identifies the
    code that concluded it. Neither alone lets a reader re-derive the table.

    Applicability is asked of `res.ANALYSIS_PRECISIONS` rather than discovered by
    running the analyzer and seeing whether it raises: the two outcomes read the
    same from the bundle, and only one of them is a fact about the experiment
    (owner priority 6).
    """
    made = []
    for n in nsplits:
        stream = (out / f"n{n}.{mode}.txt").read_text()
        for name, (mod, fn) in ANALYSES.items():
            if not res.applicable(name, precision):
                continue
            path = out / f"n{n}.{mode}.{name}.json"
            path.write_text(json.dumps(fn(stream), indent=2,
                                          sort_keys=True) + "\n")
            made.append({"file": path.name, "nsplit": n, "analysis": name,
                         "sha256": res.sha256(path)})
    return made


def produce(dest: Path, *, fixture: str, algo: str, nsplits, mode: str,
            nflux: bool, module: Path | None = None,
            arm: str = "reference",
            rho_profile: str = "as-is") -> Path:
    """Build, run, validate and publish. Returns the published bundle."""
    # FIRST, BEFORE ANY OTHER GATE. An analyzer nothing could hold to HEAD
    # disqualifies the run whatever else is true, so it is not a verdict to
    # reach at publish time behind other refusals -- on a public checkout the
    # missing private kernel is refused long before, and the message a caller
    # sees would name that instead (Codex, reproduced on CI).
    #
    # Refused on EVERY path, not only the CLI. The tolerance further down is
    # for a module ALREADY IN MEMORY, which is a normal condition of a shared
    # interpreter; nothing holding a module's bytes to HEAD is not normal
    # anywhere. It fires whether or not git has since recovered, because
    # recovery does not retroactively verify an import that already happened.
    # The algorithm selects the module (owner §11). The build script picks
    # the kernel to compile from `--algo` while the module the manifest pins
    # arrived separately, defaulting to legacy -- so a conservative run had to
    # line the two up by hand. One authority; departures are recorded.
    # A bundle is immutable and addressed by (commit, command, binary, input).
    # A dirty tree's code is not any commit, so a bundle published from one
    # occupies the address of an experiment whose source cannot be recovered.
    # Refused HERE, before the build, so an hour of compute is not spent on a
    # run that cannot be published (owner review, dirty-publish policy).
    if res.git("status", "--porcelain"):
        raise SystemExit(
            "REFUSED: the working tree is dirty, so this run has no commit to "
            "publish under. Commit (or stash) first; `git status --porcelain` "
            "names what is uncommitted.")
    canonical = kernel_source(algo)
    if canonical is None:
        raise SystemExit(
            f"REFUSED: no kernel source is known for algorithm {algo!r}; "
            f"the build compiles {sorted(g33_arms.ARMS)}")
    nonstandard = module is not None and Path(module) != canonical
    module = canonical if module is None else Path(module)
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
    # The sub-cycle limit the kernel enforces, read ONCE from the frozen
    # source this build compiles against and recorded in the bundle: the
    # geometry contract is built on it, and a checker that re-reads it from
    # whatever tree it happens to sit in is not checking a content-addressed
    # archive (owner review §4).
    tmp = Path(tempfile.mkdtemp(prefix=".g33-bundle-", dir=dest.parent))
    try:
        exe = build(tmp, fixture, algo, nflux, arm)
        # AFTER the build, so the generated overlay the compiler read exists
        # and the record can answer for those bytes rather than assuming the
        # module's constant survived generation (owner review §4). Read ONCE
        # per bundle: every member, arm and multi-run leg is held to this
        # value, so a source edit mid-run cannot bind two legs to two limits.
        ovl = tmp / "module_mp_ovl.F"
        kgeom = kernel_geometry("f64" if arm == "f64" else "f32", algo,
                                ovl if ovl.is_file() else None)
        # The fixture's parameters come from the bytes the COMPILER read, not
        # from the working tree it was staged out of (owner review §5). They
        # were re-read here, so a fixture edited after staging and restored
        # before the manifest was written gave an executable built from one
        # domain and a record describing another.
        fixture_bytes = (HERE / "g33_fortran" / f"{fixture}.f90").read_text()
        contract = RunContract(
            fixture=fixture, columns=width,
            levels=fixture_dims_from(fixture_bytes, fixture)[1],
            horizon=fixture_horizon_from(fixture_bytes, fixture),
            dtcldcr=kgeom["dtcldcr"],
            algorithm=algo, precision="f64" if arm == "f64" else "f32",
            mode=mode, rho_profile=rho_profile, tiles=(width,))
        if arm == "f64":
            # An f64 build emits no G33R at all, so there are no refinement
            # members to strict-parse; the probe stream is the artifact, and it
            # is read by its own parser.
            runs = probe_members(exe, tmp, nsplits, mode, rho_profile, width,
                                 levels=contract.levels, nflux=nflux,
                                 algo=algo, fixture=fixture,
                                 horizon=contract.horizon,
                                 dtcldcr=kgeom["dtcldcr"])
            # The cross-member contract the manifest builder cannot apply on this
            # path: it leaves `runs` empty for a supplied member_reader, so an
            # f64 bundle got every per-member check and none of the between-member
            # ones (owner §8.4).
            pr.require_probe_chain(runs)
        else:
            runs = members(exe, tmp, nsplits, mode, arm=arm, nflux=nflux,
                           rho_profile=rho_profile, width=width,
                           levels=contract.levels,
                           algo=algo, fixture=fixture,
                           horizon=contract.horizon,
                           dtcldcr=kgeom["dtcldcr"])
            if len(runs) > 1:
                ra.require_same_universe(runs)      # one experiment, not several
        fx = HERE / "g33_fortran" / f"{fixture}.f90"
        precision = "f64" if arm == "f64" else "f32"
        # THE RESULT: the raw members through the strict parser, then every
        # applicable analysis over them, each file digested where it lies.
        reader = _probe_member if arm == "f64" else None
        member_rows = [res.member_entry(p, reader) for p in sorted(tmp.glob("n*.txt"))]
        analyses = _analyses(tmp, exe, nsplits, mode, precision) if nflux else []
        if nflux and rho_profile == "as-is":
            if res.applicable("metric_trajectory", precision):
                analyses += _driver_analyses(
                    tmp, exe, nsplits, mode, width, contract.levels,
                    algo=algo, fixture=fixture, horizon=contract.horizon,
                    dtcldcr=kgeom["dtcldcr"])
            analyses += _multi_run_analyses(tmp, exe, fixture, precision, algo,
                                            contract)
        command = ["--fixture", fixture, "--algo", algo, "--mode", mode,
                   "--nsplit", ",".join(str(n) for n in sorted(nsplits))]
        if nflux:
            command.append("--nflux")
        command += ["--rho-profile", rho_profile, "--arm", arm]
        if nonstandard:
            command += ["--module-override", res.repo_relative(module)]
        rec = res.record(commit=res.git("rev-parse", "HEAD"),
                         dirty=bool(res.git("status", "--porcelain")),
                         command=command,
                         binary_sha256=res.sha256(exe),
                         input_sha256=res.input_digest(fx, module, rho_profile),
                         members=member_rows, analyses=analyses)
        res.write(tmp, rec)
        store = dest.parent / f"{dest.name}.bundles"
        store.mkdir(exist_ok=True)
        identity = res.identity(rec)
        final = store / identity
        if final.exists():
            _expect_reusable(final, rec)
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
    # `--algo` chose the module the BUILD compiles while `--module` chose the
    # one the MANIFEST pins, and its default was legacy -- so a conservative
    # run had to line the two up by hand, and a mismatch was refused later by
    # the validator. Not a silent defect, but two authorities for one fact
    # (owner §11). The module follows the algorithm now; leaving that has to
    # be said out loud.
    ap.add_argument("--module-override", type=Path, default=None,
                    help="for a NONSTANDARD experiment: pin this file instead "
                         "of the kernel the algorithm selects, and record in "
                         "the manifest that it was done")
    a = ap.parse_args(argv)
    # absolute(), NOT resolve(): once `dest` is a symlink into the bundle store,
    # resolve() follows it and the next publish writes its store INSIDE the
    # previous bundle (owner §10.3 fallout, found by rerunning for real).
    dest = produce(a.outdir.absolute(), fixture=a.fixture, algo=a.algo,
                   nsplits=[int(x) for x in a.nsplit.split(",")], mode=a.mode,
                   nflux=a.nflux, module=a.module_override,
                   arm=a.arm,
                   rho_profile=a.rho_profile)
    print(dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
