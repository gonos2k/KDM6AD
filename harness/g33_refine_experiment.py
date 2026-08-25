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
#: Run-role analyzers digested BEFORE they execute, and re-checked after, so
#: the bytes attested are the bytes the interpreter compiled. Hashing at
#: dispatch read whatever the tree held then -- reproduced, d212a1b1 executed
#: and 59f7f5dd was attested. Hashing on the line AFTER the import still put
#: the read after the execution it claims to describe (Codex, twice).
_EAGER_AT_LOAD: dict = {}

#: What each analyzer's bytes were WHEN IT WAS IMPORTED, so the manifest can
#: pin what ran rather than what the tree holds afterwards. `None` means this
#: process cannot say -- `produce()` refuses to publish such a bundle.
_IMPORTED: dict = {}



#: Recorded in `_IMPORTED` when the seam could not hold a module to HEAD
#: because GIT could not answer -- as opposed to `None`, which means the
#: module was already in memory when the analysis dispatched.
#:
#: Two different facts. Being pre-imported is a NORMAL condition of a shared
#: interpreter, which is why the library path tolerates it and publishes a
#: declaration instead of refusing. Git being unable to answer is not normal
#: in any process: nothing held those bytes to anything, so the bundle would
#: rest on an import nobody checked. Folded into one value, the tolerance
#: written for the first covered the second (Codex).
UNVERIFIED = "git-could-not-answer"


class Unattestable(Exception):
    """The bytes that just executed cannot be pinned to HEAD.

    NOT a `SystemExit`. Refusing at IMPORT applies a production invariant --
    a fresh process where the producer is imported first -- to every process
    that merely READS a manifest: `g33_identity` imports this module at its
    own module level, so on a machine without git, importing it killed the
    validator that imports IT (Codex, reproduced in a fresh process; the
    earlier measurement had this module already loaded, which is exactly the
    condition that hides it).

    The seam below records the analyzer as unattested and `produce()` refuses
    to publish, which is where the claim is actually made. A reader gets a
    manifest checked as far as it can be, and a producer gets its refusal.
    """


def _run_git(*args, cwd=None):
    """A git invocation that RETURNS rather than raises.

    Every call here already handles "git could not answer" through a
    non-zero return; none of them handled git being unusable, which arrives
    as an exception from a helper the caller never knew ran. One contract,
    one place, so a call added later inherits it (Codex).
    """
    try:
        return subprocess.run(("git",) + args, cwd=cwd, capture_output=True)
    except (OSError, subprocess.SubprocessError):
        return subprocess.CompletedProcess(args, returncode=127, stdout=b"",
                                           stderr=b"")


def _require_head_digest(rel: Path, got: str, what: str) -> str:
    """A digest ALREADY TAKEN, held to HEAD. Separate from reading the file,
    because the eager path must attest the bytes that executed at load and
    must not re-read the tree afterwards."""
    # NO GIT IS A REFUSAL, not a traceback. Without it nothing can pin the
    # bytes that just executed, which is exactly what this gate is for -- so
    # the answer is the same refusal as a file missing from HEAD, and the
    # caller sees a stated reason rather than an exception from a helper it
    # never knew ran (Codex, found end-to-end through the evidence chain,
    # which imports this module).
    blob = _run_git("show", f"HEAD:{rel}", cwd=HERE.parent)
    if blob.returncode != 0:
        # NO GIT AND NO SUCH PATH ARE ONE ANSWER: either way nothing can pin
        # the bytes that just executed, which is what this gate is for.
        raise Unattestable(
            f"{rel} is not readable from HEAD, so nothing can pin the bytes "
            f"that {what} just executed")
    want = hashlib.sha256(blob.stdout).hexdigest()
    if got != want:
        raise SystemExit(
            f"REFUSED: {rel} executed as {got[:12]} but HEAD holds "
            f"{want[:12]} -- the bundle would pin bytes that did not run. "
            f"Commit the change.")
    return got


def _running_as_cli() -> bool:
    """Is this the producer running as a script, i.e. publishing evidence?

    Faking it makes the run STRICTER, never looser -- the refusal above is
    what it gates -- so it is safe to read the way a digest is not.
    """
    main = sys.modules.get("__main__")
    f = getattr(main, "__file__", None)
    return bool(f) and Path(f).resolve() == Path(__file__).resolve()


def _is_duplicate_execution() -> bool:
    """Is another instance of THIS FILE already in `sys.modules`?

    It runs as `__main__` and again when a module imports it by name. Faking
    this only makes the producer skip attestation, which makes publication
    refuse -- so it is safe to trust in a way a digest is not.
    """
    me = Path(__file__).resolve()
    mine = sys.modules.get(__name__)
    for mod in list(sys.modules.values()):
        f = getattr(mod, "__file__", None)
        if f and mod is not mine and Path(f).resolve() == me:
            return True
    return False


def _eager_import(name: str):
    """Import a run-role analyzer, attesting the bytes that will run.

    These modules cannot reach the lazy `_an` seam: they are imported here
    because they also play a RUN role -- `g33_number_transport` makes the
    arm streams -- and the seam runs much later. The same rule is applied at
    the only place it can be, around the import itself.
    """
    import importlib
    # NOTHING may have imported it yet, or the "before" hash is taken after
    # the execution it brackets. `g33_probe_read` pulls this module in, so
    # attesting it after that import measured a module that had already run
    # (Codex). This call sits ahead of every other g33 import for that
    # reason, and says so if the order is ever changed.
    prior = sys.modules.get(name)
    if prior is not None:
        # NO CROSS-EXECUTION RECORD. Two earlier attempts kept one -- on the
        # attested module, then in a private registry -- and BOTH were
        # forgeable: everything in a Python process can write module
        # attributes and `sys.modules`, so there is no place in-process that
        # the code being attested cannot reach. Reproduced twice, bytes
        # a6cdf165 and 79ebfc28 each attesting themselves as HEAD (Codex).
        #
        # The only case that needs it is this file being executed TWICE --
        # as `__main__`, and again when another module imports it by name.
        # That duplicate does not publish anything, so it simply does not
        # attest: its `_EAGER_AT_LOAD` stays empty, `_an` marks the module
        # unattestable, and `produce()` refuses to publish from it. Fail
        # closed, with nothing to forge.
        if _is_duplicate_execution():
            # THIS FILE RUNS TWICE ON EVERY REAL RUN: as `__main__`, and again
            # when `g33_identity` imports it by name. The second execution was
            # checked by nothing at all -- it recompiled the producer's own
            # bytes with no comparison to anything (Codex). It holds them to
            # HEAD here, which is the same guarantee `require_pinned_producer`
            # gives the first execution, and needs no cross-instance state --
            # there is no in-process place the attested code cannot reach.
            try:
                _require_head_digest(
                    Path("harness/g33_refine_experiment.py"),
                    hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    "the producer's second execution")
            except Unattestable:
                pass                    # recorded as unattested just below
            # NOT SILENTLY SKIPPED. `extension_protocol` reaches this module
            # through the module-level `nt`, never through `_an`, so leaving
            # no record meant nothing marked it -- and a duplicate instance
            # published an INSTRUMENTED bundle, 20 analyses, with this module
            # missing from `executed_analyzers` entirely. Measured.
            _IMPORTED[name] = None
            return prior
        # NOT A RAISE. Refusing at IMPORT applied a production invariant --
        # a fresh process where this module is imported first -- to a shared
        # interpreter, and pytest collection died with SystemExit before a
        # single test ran: many test modules import `g33_probe_read`, which
        # pulls this one in. The process records that it cannot attest, and
        # `produce()` refuses to publish, which is where the claim is made.
        _IMPORTED[name] = None
        return prior
    src = HERE / f"{name}.py"
    before = hashlib.sha256(src.read_bytes()).hexdigest()
    mod = importlib.import_module(name)
    after = hashlib.sha256(src.read_bytes()).hexdigest()
    if before != after:
        raise SystemExit(
            f"REFUSED: {name} changed while it was being imported "
            f"({before[:12]} -> {after[:12]})")
    # HELD TO HEAD HERE, not later. `_an` returns early for anything already
    # in `_IMPORTED`, so recording an unverified digest there skipped the
    # check entirely: an edited module was accepted with its own digest.
    try:
        checked = _require_head_digest(Path(f"harness/{name}.py"), before, name)
    except Unattestable:
        # NOT the same as a module already in memory: nothing held these
        # bytes to anything, so `produce()` refuses on every path.
        _IMPORTED[name] = UNVERIFIED
        return mod
    _EAGER_AT_LOAD[name] = checked
    # ...and into the record the manifest is built from. `extension_protocol`
    # reaches this module through the module-level `nt`, never through `_an`,
    # so leaving it only in `_EAGER_AT_LOAD` meant a bundle whose analyses it
    # produced never named it. Measured: 20 analyses published with it absent
    # from `executed_analyzers` (Codex).
    _IMPORTED[name] = checked
    return mod


nt = _eager_import("g33_number_transport")     # noqa: E402

import g33_refine_analyze as ra        # noqa: E402
import g33_refine_manifest as rm       # noqa: E402
import g33_probe_read as pr           # noqa: E402
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
    # BEFORE the import, and never against a module already in memory
    # (Codex). `import_module` returns the CACHED module when one exists, so
    # hashing the file afterwards described whatever the tree held THEN --
    # reproduced: bytes d86879e0 executed, 6bc1b9c8 was recorded and
    # accepted. A module imported outside this seam has already run code
    # nothing checked, which is the property the seam exists to give.
    # ONE attestation per module, taken when it executed (Codex). A second
    # dispatch returns the same cached object, so re-hashing the file then
    # described a LATER state of the tree -- and if HEAD moved mid-run, that
    # later read passes and overwrites the record with bytes that never ran.
    # Reproduced: the record went from the executed digest to one the
    # interpreter had never compiled.
    if name in _IMPORTED:
        return importlib.import_module(name)
    # Already in memory and never attested here: this process cannot say what
    # bytes ran, so it records that it cannot rather than hashing the file and
    # pretending. Refusing outright would be wrong -- the analyzer suites
    # import these modules directly, which is their subject, and they publish
    # nothing. `produce()` refuses to PUBLISH a bundle carrying one of these,
    # which is where the claim is actually made.
    if name in sys.modules:
        # ...unless the PRODUCER ITSELF imports it at module load. A run-role
        # module cannot reach a lazy seam that runs later, so it is attested
        # here by the same rule -- its bytes, held to HEAD. The residual
        # window is narrower than the one §8 closed but not zero: it executed
        # before `require_pinned_producer()`, so an edit reverted before that
        # preflight would still go unseen. Closing it needs the detached
        # snapshot, which is the open half of §8.
        if name in _EAGER_AT_LOAD:
            try:
                _IMPORTED[name] = _require_head_digest(
                    Path(f"harness/{name}.py"), _EAGER_AT_LOAD[name], name)
            except Unattestable:
                _IMPORTED[name] = UNVERIFIED
            return sys.modules[name]
        _IMPORTED[name] = None
        return sys.modules[name]
    src = HERE / f"{name}.py"
    before = _require_head_bytes(src, name) if src.is_file() else None
    mod = importlib.import_module(name)
    # ...and the bytes that just EXECUTED are held to HEAD, here, at the
    # moment they run (owner review §8). The preflight compares the working
    # tree at t0 and the pin re-reads it at t4, so an analyzer edited at t1,
    # imported at t2 and restored at t3 ran bytes neither check ever saw --
    # reproduced end to end: `d86879e0` executed, `6bc1b9c8` was pinned.
    # A hash taken at the point of use cannot be undone by a later revert.
    # ...and unchanged ACROSS the import, so the bytes checked are the bytes
    # the interpreter compiled.
    got = Path(getattr(mod, "__file__", "") or "")
    if got.is_file():
        after = _require_head_bytes(got, name)
        if before is not None and after != before:
            raise SystemExit(
                f"REFUSED: {name} changed while it was being imported "
                f"({before[:12]} -> {after[:12]})")
        _IMPORTED[name] = after
    return mod



#: Analyzer modules the producer imports at module load because they also
#: play a RUN role -- `g33_number_transport` makes arm streams and is also
#: the seed of `extension_protocol`. They cannot reach the lazy seam.
_EAGER = frozenset({"g33_number_transport"})


def _require_head_bytes(src: Path, what: str) -> str:
    """The file's digest, refused unless it is the digest HEAD holds."""
    got = hashlib.sha256(src.read_bytes()).hexdigest()
    try:
        rel = src.resolve().relative_to(HERE.parent)
    except ValueError:
        return got                      # outside the repo: nothing pins it
    return _require_head_digest(rel, got, what)


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


#: NOT CALLED anywhere today (audit, 2026-08-24). Kept rather than deleted:
#: it answers a question this campaign has asked before and will ask again,
#: and this session cost three separate reimplementations of things that
#: already existed. Deleting an unused answer plants that mistake in the
#: future. If it is still unused when the next reader passes, the reason to
#: keep it is weaker than it is now -- say so then.
def fixture_dt_bits(fixture: str) -> str:
    return fixture_dt_bits_from(
        (HERE / "g33_fortran" / f"{fixture}.f90").read_text(), f"{fixture}.f90")


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


#: The kernel's frozen sub-cycle limit, as a fact ABOUT A SOURCE FILE --
#: and WHICH file depends on the algorithm, exactly as the build script
#: chooses it (refine_build.sh:54-55). Pinning the legacy module for a
#: conservative bundle recorded a digest of a file that run never compiled
#: (Codex).
KERNEL_SOURCES = {
    "legacy": Path("host/KIM-meso_v1.0/phys/module_mp_kdm6.F"),
    # THE THREE GRAUPEL-MELT COUNTERFACTUALS (owner review 4.5). Diagnostic
    # arms: none is proposed as the release fix, and the freeze-lift request
    # names them as the comparison it does not settle. Generated by
    # make_graupel_melt_arms.py from the pinned base, never hand-edited.
    "melt_g1": Path("host/KIM-meso_v1.0/phys/module_mp_kdm6_melt_g1.F"),
    "melt_g2": Path("host/KIM-meso_v1.0/phys/module_mp_kdm6_melt_g2.F"),
    "melt_g3": Path("host/KIM-meso_v1.0/phys/module_mp_kdm6_melt_g3.F"),
    "conservative": Path("host/KIM-meso_v1.0/phys/module_mp_kdm6_cons.F"),
    # ARM N (owner freeze-lift, 2026-08-21). Legacy with the interface number
    # transfer carrying the layer AIR MASS ratio instead of the thickness ratio
    # alone -- two lines, `dnr` and `dni`, which were the only two of seven
    # transfer sites in that loop without a density factor. Diagnostic: it is
    # selected by `--algo`, it changes no default, and the identity in
    # `g33_number_transport` predicts its residual collapses to roundoff.
    "nmass": Path("host/KIM-meso_v1.0/phys/module_mp_kdm6_nmass.F"),
    # ARM L (same freeze-lift). `ncmin` becomes per-column, so a tile's last
    # column no longer thresholds all of it. The loop that sets it already
    # walked every column -- writing a SCALAR made every iteration overwrite
    # the previous, which is why only the last one survived.
    "lncmin": Path("host/KIM-meso_v1.0/phys/module_mp_kdm6_lncmin.F"),
    # ...and the four combined arms the N x C x L factorial needs. Generated by
    # `make_factorial_variants.py`, never hand-edited.
    "nmasslncmin": Path("host/KIM-meso_v1.0/phys/module_mp_kdm6_nmasslncmin.F"),
    # ARM N_d (owner freeze-lift, 2026-08-22). Arm N with the DRY layer-mass
    # ratio: `rho_d = rho/(1+q)`, so the weight carries `(1+q(k))/(1+q(k+1))`.
    # Arm N closes the OPERATOR's moist ledger; this closes the PHYSICAL one
    # (G33-BASIS-006). Diagnostic: selected by `--algo`, changes no default,
    # and `g33_number_basis` predicts its dry residual vanishes the same
    # algebraic way Arm N's moist one does.
    "nmass_dry": Path("host/KIM-meso_v1.0/phys/module_mp_kdm6_nmass_dry.F"),
    # ARM N_d-WINDOW (owner approval, 2026-08-23): Arm N_d told the WINDOW-
    # INITIAL dry layer mass by the driver, as an extra `mdry0` argument. A
    # harness instrument only -- it separates the arm's algebra from the
    # harness's fixed-forcing artefact (FINDING_fixed_dry_mass_arm_v1) and says
    # nothing about production, where the host supplies a dynamics-consistent
    # `den` every call.
    "nmass_dry_window": Path("host/KIM-meso_v1.0/phys/module_mp_kdm6_nmass_dry_window.F"),
    "cons_nmass": Path("host/KIM-meso_v1.0/phys/module_mp_kdm6_cons_nmass.F"),
    "cons_lncmin": Path("host/KIM-meso_v1.0/phys/module_mp_kdm6_cons_lncmin.F"),
    "cons_nmasslncmin": Path("host/KIM-meso_v1.0/phys/module_mp_kdm6_cons_nmasslncmin.F"),
}
#: v2 added `algorithm`: which kernel the limit was read from is part of
#: the fact, and a tag whose required keys change without changing is a tag
#: that means two things (Codex).
#: v3 records the limit read from the bytes the compiler actually read --
#: an --nflux build feeds it a generated overlay, so the pinned module's
#: constant was an assumption about that overlay until now (owner review §4).
KERNEL_GEOMETRY_SCHEMA = "kdm6_subcycle_v3"
KNOWN_KERNEL_GEOMETRY_SCHEMAS = ("kdm6_subcycle_v1", "kdm6_subcycle_v2",
                                 "kdm6_subcycle_v3")
#: The CLOSED expected-run contract (owner review §5). Versioned because it
#: is a document schema: an added field is a new contract, not a new
#: optional convenience, and "compare if present" is what made the previous
#: block deletable field by field.
EXPECTED_RUN_SCHEMA = "g33_expected_run_v1"


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
    rel = KERNEL_SOURCES.get(algo)
    if rel is None:
        raise SystemExit(
            f"REFUSED: no kernel source is known for algorithm {algo!r}; the "
            f"build script compiles {sorted(KERNEL_SOURCES)}")
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
                         "arm": arm, "sha256": rm.sha256(ap),
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
_PARSER_MODULES = ("g33_refine_analyze", "g33_number_transport", "g33_probe_read",
                   # The FIXTURE REGISTRY. The producer resolves the stream's
                   # declared fixture through it to compare against the one the
                   # caller asked for, so its bytes decide whether a member is
                   # accepted at all. Reaching it without pinning it is the
                   # exact hole `unpinned_reachable()` exists to find, and it
                   # found this one.
                   "g33_fixture_v1",
                   # THE FORWARD-ERROR SCREEN. `g33_matched_closure` computes
                   # every residual's screening bound through
                   # `g33_factorial._screen`, so those bytes decide whether a
                   # closure is reported as resolved. A bundle that pins the
                   # residual and not the threshold it is judged against pins
                   # half the claim. Same hole, same finder -- and this is the
                   # second time `unpinned_reachable()` has caught a widening
                   # the same week (owner review, defect-class audit).
                   "g33_factorial")


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
        _run_git("cat-file", "blob", blob, cwd=HERE.parent).stdout).hexdigest()
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
        # ONE rule, shared with the evidence chain (owner §6). This checked
        # `is_file()` and the digest, and both follow symlinks, so a link to a
        # file outside the bundle satisfied its digest and was republished --
        # while the chain refused the same bundle as NOT-SELF-CONTAINED.
        state = rm.payload_state(f, want, final)
        if state == "absent":
            raise SystemExit(f"REFUSED: {final} declares {entry['file']} but it "
                             f"is missing -- the directory is incomplete")
        if state == "NOT-SELF-CONTAINED":
            raise SystemExit(
                f"REFUSED: {final}/{entry['file']} is not bundle payload -- a "
                f"symlink, or a file outside the bundle root. A correct digest "
                f"does not make it an immutable archive")
        if state != "matches":
            raise SystemExit(f"REFUSED: {final}/{entry['file']} does not match "
                             f"the digest its manifest recorded")
    # The manifest and the bundle directory are payload too (owner §6).
    for what, q in (("manifest.json", mf), ("bundle directory", final)):
        if q.is_symlink():
            raise SystemExit(
                f"REFUSED: {what} is a symlink -- the bytes an address names "
                f"have to be inside the bundle")


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


@dataclass(frozen=True)
class SourceSnapshot:
    """What the compiler actually read, keyed by logical path.

    The build stages every compiled source by content and logs the digest it
    fed the compiler; this is that log, frozen, so every consumer derives
    from ONE set of bytes instead of re-reading the working tree afterwards
    (owner review §5). `entries` is {logical path: (staged path, digest)}.
    """
    entries: tuple

    def _get(self, logical: str) -> tuple:
        for path, staged, sha in self.entries:
            if path == logical:
                return staged, sha
        raise FixtureContractError(
            f"{logical} is not among the compiled sources "
            f"{sorted(p for p, _, _ in self.entries)}")

    def digest(self, logical: str) -> str:
        return self._get(logical)[1]

    def text(self, logical: str) -> str:
        """The bytes themselves, re-checked against the digest the build
        recorded for them: the staged store is shared, and this read happens
        after the compile that justified it."""
        staged, sha = self._get(logical)
        p = Path(staged)
        if not p.is_file():
            raise FixtureContractError(f"the staged {logical} is gone: {staged}")
        got = hashlib.sha256(p.read_bytes()).hexdigest()
        if got != sha:
            raise FixtureContractError(
                f"the staged {logical} now holds {got[:12]}, the build "
                f"compiled {sha[:12]}")
        return p.read_text()


def source_snapshot(build_dir: Path) -> SourceSnapshot:
    """The staged map and the source log, joined.

    Also holds every TRACKED compiled source to its HEAD blob: the point of
    a pin is that the recorded bytes are the executed bytes, and a file
    edited after staging and restored before the manifest was written passed
    both the preflight and the final check while the executable came from
    the edit (owner review §5, §7). `host/**` is gitignored, so those are
    pinned by digest alone and cannot be compared to a blob.
    """
    smap, slog = build_dir / "staged-map.txt", build_dir / "sources.txt"
    # A MISSING log is not an empty one (Codex): iterating over nothing made
    # the HEAD-blob check below pass vacuously, so deleting the log cleared
    # the gate that exists to say what was compiled. A build writes both.
    for f in (smap, slog):
        if not f.is_file():
            raise SystemExit(
                f"REFUSED: {f.name} is not in the build directory, so what "
                f"the compiler read cannot be established")
    staged = {}
    for ln in smap.read_text().splitlines():
        path, _, logical = ln.partition("\t")
        if logical:
            staged[logical.strip()] = path
    entries, bad = [], []
    for ln in slog.read_text().splitlines():
        logical, _, sha = ln.partition("\t")
        logical, sha = logical.strip(), sha.strip()
        if not logical or not sha:
            continue
        # ...and an entry with no staged file is unverifiable, not fine:
        # `digest()` would keep answering from the log while the bytes it
        # names are unavailable, so every consumer that asks only for the
        # digest would pass on a claim nothing can check (Codex).
        if logical not in staged:
            bad.append(f"  {logical}: compiled, but the staged bytes are not "
                       f"recorded in staged-map.txt")
            continue
        entries.append((logical, staged[logical], sha))
        blob = _head_blob(logical)
        if blob is not None and blob != sha:
            bad.append(f"  {logical}: compiled {sha[:12]}, HEAD holds "
                       f"{blob[:12]}")
    # `bad` first: "this source was not staged" says what is wrong, while
    # "nothing was logged" is what that looks like from a distance.
    if bad:
        raise SystemExit(
            "REFUSED: the bytes the compiler read cannot be established.\n"
            + "\n".join(bad) +
            "\nCommit the change, or the bundle records a build it did not "
            "describe.")
    if not entries:
        raise SystemExit(
            "REFUSED: no compiled source was logged, so the build cannot say "
            "what it read")
    return SourceSnapshot(entries=tuple(entries))


def _head_blob(logical: str) -> str | None:
    """The SHA-256 of this path's content at HEAD, or None when git does not
    track it (`host/**` is private and gitignored)."""
    r = _run_git("show", f"HEAD:{logical}", cwd=HERE.parent)
    if r.returncode != 0:
        return None
    return hashlib.sha256(r.stdout).hexdigest()


def resolved_violations(man: dict, root: Path, contract) -> list:
    """The manifest against the BYTES it points at, before publication.

    `rm.validate` can only hold a document to itself. The fixture's
    parameters are in the fixture's bytes, the sub-cycle limit is in the
    compiled overlay's, and each member's geometry is in its own stream --
    so the resolved comparison is a different check from the structural one,
    and it belongs on the publish path rather than only in the chain
    (owner review §9).
    """
    bad = []
    exp = man.get("expected_run") or {}
    src = (HERE / "g33_fortran" / f"{contract.fixture}.f90").read_text()
    for key, want in (("columns", fixture_dims(contract.fixture)[0]),
                      ("levels", fixture_dims(contract.fixture)[1]),
                      ("dt_bits", fixture_dt_bits_from(src, contract.fixture)),
                      ("window_seconds", fixture_horizon_from(src,
                                                              contract.fixture)),
                      ("fixture_id", contract.fixture)):
        if exp.get(key) != want:
            bad.append(f"expected_run.{key} {exp.get(key)!r} is not the "
                       f"fixture's {want!r}")
    kg = man.get("kernel_geometry") or {}
    if kg.get("dtcldcr") != contract.dtcldcr:
        bad.append(f"kernel_geometry.dtcldcr {kg.get('dtcldcr')!r} is not the "
                   f"{contract.dtcldcr!r} this build was held to")
    for m in man.get("members") or []:
        p = root / m.get("file", "")
        if not p.is_file():
            bad.append(f"members[{m.get('file')!r}] is not in the bundle")
            continue
        want_d, want_L, want_h = expected_geometry(
            contract.horizon, m["nsplit"], contract.precision,
            contract.dtcldcr)
        for key, want in (("delt", want_d), ("dtcld", want_h)):
            if f"{m.get(key, float('nan')):.6f}" != f"{want:.6f}":
                bad.append(f"members[{m['file']}] records {key}={m.get(key)!r},"
                           f" the fixture's horizon gives {want}")
        if m.get("loops") != want_L:
            bad.append(f"members[{m['file']}] records loops={m.get('loops')!r},"
                       f" the kernel's rule gives {want_L}")
    return bad + _witness_violations(man, root)


#: The four records that describe ONE build. `build_artifacts` digests each
#: file, so each is faithfully recorded -- but nothing asked whether they
#: describe the same build (owner review §6). Measured: a manifest embedding
#: build A beside a published `build_provenance.json` holding build B, with
#: the artifact digest honestly naming B, validated CLEAN.
def _witness_violations(man: dict, root: Path) -> list:
    bad = []
    embedded = man.get("build_provenance")
    published = root / "build_provenance.json"
    if not isinstance(embedded, dict) or not published.is_file():
        return ["build_provenance is not an object, or the published record "
                "is not in the bundle"]
    try:
        got = json.loads(published.read_text())
    except ValueError as e:
        return [f"build_provenance.json is not readable JSON: {e}"]
    # PARSING SAYS THE SYNTAX IS JSON, NOT THAT THE DOCUMENT IS A RECORD
    # (Codex). JSON allows an array, a string, a number, `true` and `null` at
    # the top, and the comparison below reads keys off it -- all five raised
    # out of the gate instead of failing it, measured. Same defect, same
    # line, in the collector's own `verify()`.
    if not isinstance(got, dict):
        return [f"the published build_provenance.json is a "
                f"{type(got).__name__}, not a record: there is nothing in it "
                f"to compare the embedded one against"]
    if got != embedded:
        keys = sorted({k for k in set(got) | set(embedded)
                       if got.get(k) != embedded.get(k)})
        bad.append(f"the manifest's build_provenance is not the published "
                   f"build_provenance.json; they differ at {keys}")
    # ...and the two logs the collector read them FROM, through the collector's
    # own parsers, so this comparison cannot drift from how the record is made.
    # ...and the two logs the record was DERIVED from. The collector owns
    # that derivation and is deliberately reached only as a subprocess -- it
    # is stdlib-only so it can run inside the build, and importing it here
    # would move it into the producer's import closure and reclassify it in
    # the identity graph. So the check crosses the same boundary the build
    # already uses, and there is still exactly one definition of the format.
    r = subprocess.run([sys.executable, str(HERE / "g33_build_provenance.py"),
                        "--verify", str(root)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        bad += [ln for ln in r.stdout.splitlines() if ln.strip()] or \
            [f"the published logs do not re-derive the record: {r.stderr.strip()[:200]}"]
    return bad


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
        if not rm.applicable(name, precision):
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
    nl = _an("g33_ncmin_locality")
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
            nflux: bool, module: Path | None = None, findings=(),
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
    unverified = sorted(k for k, v in _IMPORTED.items() if v is UNVERIFIED)
    if unverified:
        raise SystemExit(
            f"REFUSED: {unverified} could not be held to HEAD when they were "
            f"imported -- git could not answer, so nothing pins the bytes "
            f"that ran. Re-run in a process where git works; a later recovery "
            f"does not verify an import that already happened.")
    # The algorithm selects the module (owner §11). The build script picks
    # the kernel to compile from `--algo` while the module the manifest pins
    # arrived separately, defaulting to legacy -- so a conservative run had to
    # line the two up by hand. One authority; departures are recorded.
    canonical = KERNEL_SOURCES.get(algo)
    if canonical is None:
        raise SystemExit(
            f"REFUSED: no kernel source is known for algorithm {algo!r}; "
            f"the build compiles {sorted(KERNEL_SOURCES)}")
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
        snap = source_snapshot(tmp)
        fixture_logical = f"harness/g33_fortran/{fixture}.f90"
        fixture_bytes = snap.text(fixture_logical)
        # Belt and braces: the snapshot holds tracked sources to HEAD and the
        # preflight holds the working tree to HEAD, so these two agree by
        # construction -- but "by construction" is the claim a gate exists to
        # check, and this is the one that says the manifest pins what ran.
        tree_fx = rm.sha256(HERE / "g33_fortran" / f"{fixture}.f90")
        if snap.digest(fixture_logical) != tree_fx:
            raise SystemExit(
                f"REFUSED: the compiled fixture is "
                f"{snap.digest(fixture_logical)[:12]}, the manifest would pin "
                f"{tree_fx[:12]}")
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
                man["analyses"] += _driver_analyses(
                    tmp, exe, nsplits, mode, width, contract.levels,
                    algo=algo, fixture=fixture,
                    horizon=contract.horizon,
                    dtcldcr=kgeom["dtcldcr"])
            # Analyses of the bundle's OWN binary across decompositions. They
            # need the --nflux build, whose G33N records say which tiles the
            # kernel actually received.
            man["analyses"] += _multi_run_analyses(tmp, exe, fixture,
                                                   precision, algo, contract)
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
        # WHAT ACTUALLY RAN, digested at import (owner review §8). The pins
        # above are re-read from the working tree at the END of a run that
        # takes the better part of an hour; this block is the digest each
        # analyzer had when its first statement executed, so a transient edit
        # cannot be undone by restoring the file before the manifest is
        # written. Empty on a run that dispatched no analyzer.
        if _IMPORTED:
            unattested = sorted(k for k, v in _IMPORTED.items()
                                if v is None or v is UNVERIFIED)
            # PUBLISHED EVIDENCE COMES FROM THE CLI, and there this is always
            # empty: the producer is `__main__` in a fresh process and every
            # analyzer reaches it through the seam. A library import -- the
            # test suite -- shares an interpreter where other modules have
            # already imported analyzers, so refusing there stopped every
            # in-process `produce()` in the full run. The bundle claims only
            # what it can attest; the CLI refuses rather than claim less.
            if unattested and _running_as_cli():
                raise SystemExit(
                    f"REFUSED: {unattested} were already in memory when the "
                    f"analysis dispatched, so what executed cannot be "
                    f"established. A producer runs in a fresh process for "
                    f"exactly this reason.")
            attested = {k: v for k, v in _IMPORTED.items() if v is not None}
            if attested:
                man["executed_analyzers"] = [
                    {"module": k, "sha256": v} for k, v in sorted(attested.items())]
            # ...and SAY what could not be attested -- but only once the
            # dispatch scope is known, below, where `identity` exists.
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
                                        "commands.txt", "sources.txt",
                                        # the GENERATED overlay an --nflux
                                        # build feeds the compiler: the bytes
                                        # the executable was made from are
                                        # evidence, not a temporary
                                        "module_mp_ovl.F"))
            if q.is_file()]
        man["arm"] = arm
        # The SAME word the analyses were selected by, so the manifest cannot
        # declare one precision and have been analysed at another.
        man["precision"] = precision
        # The EXPERIMENT the bundle claims to be (owner review §6). The
        # algorithm lived only in the member rows, so the document could say
        # what each member ran and never what the bundle was FOR -- and the
        # checker had nothing to hold a re-validated member to. `expected_run`
        # states the fixture's own parameters beside the requested
        # decomposition, so every member's geometry is a derivable fact the
        # validator recomputes rather than a number it copies.
        man["algorithm"] = algo
        # A run that leaves the kernel its algorithm selects has to say so,
        # or a reader with only the manifest takes it for a standard one
        # (owner §11).
        if nonstandard:
            man["nonstandard_module"] = True
        man["kernel_geometry"] = kgeom
        man["expected_run"] = {
            "schema": EXPECTED_RUN_SCHEMA,
            # the fixture the MANIFEST pins, not a name the producer holds
            # separately: two records of one fact
            "fixture_id": Path(man["fixture_path"]).stem,
            "fixture_sha256": man["fixture_sha256"],
            # The RAW WORD is the canonical horizon (owner review §5): a
            # decimal alias like 300.000001 rounds to the same f32 geometry,
            # so a document comparing only the decimal can name a horizon the
            # fixture does not hold.
            # ...of the COMPILED fixture (owner review §5): this block is
            # what the recipe id hashes, so re-reading the tree here would
            # let the request describe a domain the executable never had.
            "dt_bits": fixture_dt_bits_from(fixture_bytes, fixture),
            "window_seconds": contract.horizon,
            "columns": width,
            "levels": contract.levels,
            "algorithm": algo,
            "precision": precision,
            "source_precision": "f32",
            "mode": mode,
            "nsplits": sorted(nsplits),
            "rho_profile": rho_profile,
            # Declared only where a protocol in this bundle RECORDS a
            # tiling -- G33N under --nflux, or G33P on the probe/f64 arms.
            # A plain reference bundle has neither, and a declaration
            # nothing can substantiate is a decoration (Codex).
            **({"tile_sizes": [width]}
               if (nflux or arm in ("probe", "f64")) else {}),
        }
        # The ROLE GRAPH the layered ids are derived under (owner priority 8).
        # Without it those ids are a function of the manifest AND of whichever
        # checkout computes them, so a refactor that moves a module between
        # roles moves a historical bundle's run_content_id with no bundle byte
        # having changed. Imported here rather than at module scope: g33_identity
        # imports this module, and the cycle only closes at call time.
        import g33_identity as gi
        man["identity"] = gi.identity_block(
            {a["analysis"] for a in man["analyses"] if a.get("analyzer")})
        # ...and NOW say what could not be attested. Dropping it silently
        # published a bundle whose record a reader cannot tell apart from a
        # complete one: measured, 20 analyses with 7 modules named and
        # `g33_number_transport` simply absent (Codex). A bundle that cannot
        # say what ran has to say that.
        #
        # SCOPED TO WHAT THIS BUNDLE DISPATCHES TO, by the validator's own
        # authority. The seam records an analyzer it could not attest whether
        # or not any analysis here reaches it, so a suite that imported
        # `g33_number_transport` before the producer made every in-process
        # `produce()` publish a name the validator refuses as unrelated --
        # 13 tests, and only when collection put that module first. A module
        # this bundle never dispatched to decided nothing in it, so it owes
        # the record nothing; the CLI refusal above still fires on the FULL
        # set, so nothing is relaxed on the path that publishes evidence.
        if _IMPORTED:
            reached = rm.dispatched_seeds(man)
            confess = sorted(k for k, v in _IMPORTED.items()
                             if v is None and k in reached)
            if confess:
                man["unattested_analyzers"] = confess
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
        # ...and the RESOLVED experiment (owner review §9). `rm.validate`
        # holds the document to itself; the fixture's own parameters live in
        # its bytes and the members' in theirs, and until now only the
        # evidence chain compared them -- so a producer regression writing
        # `levels: 999` entered the immutable store and was found afterwards.
        # This repository's rule is the other way round: refuse before
        # publishing.
        violations += resolved_violations(man, tmp, contract)
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
    ap.add_argument("--finding", type=Path, action="append", default=[])
    a = ap.parse_args(argv)
    # absolute(), NOT resolve(): once `dest` is a symlink into the bundle store,
    # resolve() follows it and the next publish writes its store INSIDE the
    # previous bundle (owner §10.3 fallout, found by rerunning for real).
    dest = produce(a.outdir.absolute(), fixture=a.fixture, algo=a.algo,
                   nsplits=[int(x) for x in a.nsplit.split(",")], mode=a.mode,
                   nflux=a.nflux, module=a.module_override,
                   findings=a.finding, arm=a.arm,
                   rho_profile=a.rho_profile)
    print(dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
