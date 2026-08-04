#!/usr/bin/env python3
"""Sedimentation does not conserve column NUMBER under the rho*dz measure.

The mass transfer carries the density ratio implicitly (`falk` is built with
`dend(k+1)`, the inflow divides by `dend(k)`, F:1214-1219). The number transfer
carries only the thickness ratio (F:1221-1224):

    dnr(i,k+1) = min(falkn(i,k+1,1)*delz(i,k+1)/delz(i,k)*dtcld, nrs(i,k+1,1))
    nrs(i,k,1) = max(nrs(i,k,1) - dnr(i,k) + dnr(i,k+1), 0.)

`nrs` IS the prognostic number MIXING ratio (`nrs(i,k,1) = nr(i,k,j)`, F:388), so
the physical column measure is `sum_k den_k*delz_k*nr_k`. Weighted, the number
arriving below is `den(lower)*delz(upper)*b` where the number that left above was
`den(upper)*delz(upper)*b`. Density increases downward, so every interface
CREATES number:

    created = sum over interfaces of [den(lower) - den(upper)] * delz(upper) * b

## Why the transfers are recovered rather than read

`falln` is the UNCAPPED accumulator: the kernel removes `min(falkn*dtcld, nrs)`
but `falln` sums `falkn`. Using it as the surface flux mixes this defect with the
P0-4b interface-cap gap, and the total then exceeds what the density ratios can
explain. With `mstep == 1` there is exactly one substep, so the per-interface
transfers follow from the state change alone, top down:

    b_0 = nr_0 - nr'_0                                (top cell: no inflow)
    b_t = nr_t - nr'_t + b_{t-1} * delz_{t-1}/delz_t

which is what the kernel actually did, caps included, and the bottom cell's `b`
is the true surface removal. Restricted to `mstep == 1` because with more
substeps the composition is not invertible from endpoints.

## What is and is not evidence here

Two things that LOOK like proof are not, and both were caught by working them out
rather than by the numbers looking wrong.

Summing `[den(lower)-den(upper)]*delz(upper)*a` and recovering the residual is an
ALGEBRAIC identity of the recursion -- it telescopes for ANY `a`. And the mass
channel returning zero is forced the same way: with
`w_t = den_{t-1}dz_{t-1}/(den_t dz_t)` every telescoped term is identically zero,
so mass MUST return ~0 whatever the data. Together they check the arithmetic and
say nothing about the physics.

The evidence is a HYPOTHESIS TEST against data the recursion does not consume.
Recover `a` under each candidate inflow weight

    x'_t = x_t - a_t + a_{t-1} * w_t     w_t = dz_{t-1}/dz_t                 (A)
                                         w_t = den_{t-1}dz_{t-1}/(den_t dz_t) (B)

and compare the recovered bottom-cell transfer against the independently emitted
`falln` accumulator. A wrong `w` does not reproduce it. Measured (h = 3.125 s):
(A) gives 1.00000-1.00001 for `nr` in every column, (B) gives 0.850-0.925. The
source says (A) at F:1222; the run agrees, and excludes (B) by 7-15%.

Reads a `refine_build.sh --nflux` stream: the sub-step counts come from
`G33F MSTEP`/`MSTEPI`, and the ice one needs the number macro.
"""
from __future__ import annotations

import json
import re
import struct
import subprocess
import sys
from pathlib import Path

STREAM_BEGIN = re.compile(
    r"^G33N STREAM_BEGIN (\d+) (\d+) (\d+) (\d+) (\S+) (\S+) (\S+) (\S+)$")
XFER = re.compile(r"^G33F XFER (\d+) (\d+) (\d+) (main|ice) f32 "
                  r"([0-9A-F]{8}) ([0-9A-F]{8})$")
CAPIN = re.compile(r"^G33F CAPIN (\d+) (\d+) (\d+) (-?\d+) (main|ice) f32 "
                   r"([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8}) ([0-9A-F]{8})$")
TOPOUT = re.compile(r"^G33F TOPOUT (\d+) (\d+) (\d+) (-?\d+) (main|ice) f32 "
                    r"([0-9A-F]{8}) ([0-9A-F]{8})$")
#: Extension records this parser knows. A stream declaring a feature it does not
#: emit, or emitting one it did not declare, is refused.
FEATURES = {"mstep", "mstepi", "nflux", "xfer", "capin", "topout"}

#: The density-control arms. `as-is` is the unperturbed forcing; the rest are
#: interventions, and a stream must say which it is.
RHO_PROFILES = {"as-is", "uniform", "inverted", "x2"}

#: G33F record families this parser recognises. STAGE and the op ladder are
#: consumed selectively; the rest are the number extension.
KNOWN_G33F = {"STAGE", "MSTEP", "MSTEPI", "NFLUX", "XFER", "CAPIN", "TOPOUT",
              "G33FOP"}
STREAM_END = re.compile(r"^G33N STREAM_END$")
CALL_BEGIN = re.compile(r"^G33N CALL_BEGIN (\d+) (\d+) (\d+) (\d+) (\d+) (\d+) "
                        r"([0-9A-F]{8})$")
CALL_END = re.compile(r"^G33N CALL_END (\d+) (\d+) (\d+)$")
#: The protocol this parser implements. A stream declaring another is refused
#: rather than read with the wrong field meanings.
SCHEMA = 4

#: G33F family -> the header feature that must declare it. A record whose feature
#: the header did not declare is REFUSED rather than parsed anyway: the contract
#: said "emitting an undeclared feature is rejected" while the parser read them
#: regardless and merely skipped the universe check (owner P0-3).
FAMILY_FEATURE = {"MSTEP": "mstep", "MSTEPI": "mstepi", "NFLUX": "nflux",
                  "XFER": "xfer", "CAPIN": "capin", "TOPOUT": "topout"}

#: These describe one bracketed call and are meaningless outside it. `cur is
#: None: continue` silently DROPPED them, so a stream whose CAPIN records had
#: drifted out of their brackets looked complete (owner P0-4).
EXTENSION_FAMILIES = frozenset(FAMILY_FEATURE)

#: What the closure reads out of each stage. Rectangularity below is checked
#: against the stream's own field set, so a field the driver adds needs no change
#: here; these are the ones whose ABSENCE would make the analysis wrong rather
#: than merely different.
#: `qv` is required at BOTH endpoints because the DRY basis needs
#: rho_d = rho_m/(1+qv), and because carrying it at both turns "sedimentation does
#: not touch qv" from an assumption into something the ledger checks.
STAGE_REQUIRED = {"outer_pre_sed": ("rho", "delz", "qv", "nr", "ni", "qr", "qi"),
                  "outer_post_sed": ("qv", "nr", "ni", "qr", "qi")}
STAGE = re.compile(r"^G33F STAGE \d+ \S+ (outer_pre_sed|outer_post_sed|surface) 0 "
                   r"(\S+) (\d+) (-?\d+) f32 ([0-9A-F]{8})$")
NFLUX = re.compile(r"^G33F NFLUX \d+ (\d+) (\S+) f32 ([0-9A-F]{8})$")
MSTEP = re.compile(r"^G33F MSTEP \d+ \S+ (\d+) i32 ([0-9A-F]{8})$")
MSTEPI = re.compile(r"^G33F MSTEPI \d+ (\d+) i32 ([0-9A-F]{8})$")

#: species -> (sub-step record governing it, uncapped surface accumulator or None,
#: whether its inflow carries the density ratio). `mstep` covers qr/nr/qs/qg,
#: `mstep_i` covers qi/ni (F:1179-1180). The mass rows are the CONTROL.
SPECIES = {"nr": ("main", "bottom_falln_nr", False),
           "ni": ("ice", "bottom_falln_ni", False),
           "qr": ("main", None, True),
           "qi": ("ice", None, True)}


def _f32(h: str) -> float:
    return struct.unpack(">f", bytes.fromhex(h))[0]


class StreamError(Exception):
    """The stream is not a complete record of the run it claims to be."""


#: Every NFLUX group is exactly these, once per column per call.
NFLUX_FIELDS = ("bottom_falln_nr", "bottom_falln_ni", "nflux_den", "nflux_delz",
                "nflux_dtcld")


def _blank(call_id=None, split=None, tile=None, delt=None):
    return {"call_id": call_id, "split": split, "tile": tile, "delt": delt,
            "cols": None, "K": None,
            "outer_pre_sed": {}, "outer_post_sed": {}, "surface": {},
            "flux": {}, "mstep": {}, "loops": set(),
            "xfer": {}, "capin": {}, "topout": {}}


def single_loop(call) -> int:
    """The one inner cloud-subcycle this call ran, or an error.

    The budget arithmetic below differences the state ACROSS the sedimentation
    segment of one loop. With loops > 1 the call contains several such segments
    and a single pre/post pair does not describe it -- so the analysis refuses
    the call instead of collapsing it (owner P0-3).
    """
    loops = call["loops"]
    if len(loops) != 1:
        raise StreamError(
            f"call {call['call_id']} ran {sorted(loops)} inner loops; the segment "
            f"budget is defined for one, so this call is not analysable")
    return next(iter(loops))


def _check(call):
    """A call is complete or it is not evidence (owner P0-4).

    Completeness is checked PER INNER LOOP. Whether a call can carry a segment
    budget is a separate question, asked by `single_loop` at analysis time: a
    multi-loop call is a well-formed stream that this particular arithmetic does
    not describe, and conflating the two would make the parser reject data it has
    no complaint about.
    """
    for lp in sorted(call["loops"]):
        _check_loop(call, lp, call.get("features", frozenset()))


#: Every NFLUX group is exactly these, once per column per loop.
def _check_loop(call, lp, feats=frozenset()):
    cols = {c for l, c, _ in call["outer_pre_sed"] if l == lp}
    # The declared column range is a CONTRACT, not decoration: it was recorded
    # and thrown away (owner P0-3).
    if call["cols"]:
        want = set(range(call["cols"][0], call["cols"][1] + 1))
        if cols != want:
            raise StreamError(
                f"call {call['call_id']} loop {lp}: state covers columns "
                f"{sorted(cols)}, CALL_BEGIN declared {sorted(want)}")
    if not cols:
        raise StreamError(f"call {call['call_id']} loop {lp}: no pre-sed state")
    if {c for l, c, _ in call["outer_post_sed"] if l == lp} != cols:
        raise StreamError(f"call {call['call_id']}: post-sed covers different columns")
    # EXACT rectangular universe: fields x columns x levels, PER COLUMN.
    #
    # The level check pooled every column into one set, so a column short a level
    # passed whenever another column supplied it. That is not cosmetic: the
    # matched closure builds each column's integral from exactly these per-column
    # level sets, so a short column silently integrates over fewer cells AND
    # takes the wrong cell as the bottom one (owner §14).
    #
    # The field set is taken from the stream rather than hardcoded -- a field the
    # driver adds needs no change here -- but every cell must carry the same one,
    # which is what stops one field's gap being filled by another's presence.
    for stage, required in STAGE_REQUIRED.items():
        cells = {(c, k) for l, c, k in call[stage] if l == lp}
        if not cells:
            raise StreamError(
                f"call {call['call_id']} loop {lp}: no {stage} records")
        fields = {f for (l, c, k), rec in call[stage].items() if l == lp
                  for f in rec}
        if missing := set(required) - fields:
            raise StreamError(
                f"call {call['call_id']} loop {lp}: {stage} carries no "
                f"{sorted(missing)}, which the closure reads")
        for c in sorted(cols):
            ks = {k for cc, k in cells if cc == c}
            want = set(range(call["K"])) if call["K"] is not None else ks
            if ks != want:
                raise StreamError(
                    f"call {call['call_id']} loop {lp} col {c}: {stage} levels "
                    f"{sorted(ks)} do not match the declared K={call['K']}")
            for k in sorted(ks):
                got = set(call[stage][(lp, c, k)])
                if got != fields:
                    raise StreamError(
                        f"call {call['call_id']} loop {lp} col {c} level {k}: "
                        f"{stage} carries fields {sorted(got)}, the rest of the "
                        f"stage carries {sorted(fields)}")
    # Filtered BY LOOP: unfiltered, a column missing its NFLUX in loop 1 passed
    # because loop 2 supplied one (owner P0-2).
    got = {c for l, c in call["flux"] if l == lp}
    if got != cols:
        raise StreamError(
            f"call {call['call_id']} loop {lp}: NFLUX covers {sorted(got)}, "
            f"state covers {sorted(cols)}")
    for (l, c), f in ((k, v) for k, v in call["flux"].items() if k[0] == lp):
        if set(f) != set(NFLUX_FIELDS):
            raise StreamError(f"call {call['call_id']} col {c}: NFLUX fields "
                              f"{sorted(f)} != {sorted(NFLUX_FIELDS)}")
        for name, v in f.items():
            if v != v or abs(v) == float("inf"):
                raise StreamError(f"call {call['call_id']} col {c}: {name} is {v}")
        for name in ("nflux_den", "nflux_delz", "nflux_dtcld"):
            if f[name] <= 0:
                raise StreamError(f"call {call['call_id']} col {c}: {name}={f[name]}")
    for chain in ("main", "ice"):
        got = {c for l, ch, c in call["mstep"] if ch == chain and l == lp}
        if got != cols:
            raise StreamError(
                f"call {call['call_id']} loop {lp}: {chain} sub-step counts "
                f"cover {sorted(got)}, state covers {sorted(cols)}")
        # The extension records have an EXACT universe, and it is a universe over
        # (sub-step, LEVEL) -- not sub-step alone. Each fires unconditionally at
        # its site, so `mstep` and `K` determine exactly how many there must be:
        #
        #   XFER    the bottom-cell transfer, once per sub-step
        #   TOPOUT  the top-cell removal, once per sub-step, always at k == 0
        #   CAPIN   one per interface, k = 1..K-1, per sub-step
        #
        # TOPOUT previously checked the sub-step set only, so a record at the
        # wrong level -- or two at the same sub-step and different levels -- was
        # accepted (owner P0-6). CAPIN had no completeness check at all, so a
        # feature declared with ZERO records passed and the cap analysis it backs
        # would have been computed over nothing (owner P0-1).
        for c in sorted(cols):
            ms = call["mstep"][(lp, chain, c)]
            if ms < 1:
                raise StreamError(
                    f"call {call['call_id']} loop {lp} col {c} {chain}: "
                    f"mstep={ms} is not a sub-step count")
            subs = set(range(1, ms + 1))
            exact = {"xfer": ({(n,) for n in subs},
                              {(n,) for l, n, cc, ch in call["xfer"]
                               if (l, cc, ch) == (lp, c, chain)}),
                     "topout": ({(n, 0) for n in subs},
                                {(n, k) for l, n, cc, ch, k in call["topout"]
                                 if (l, cc, ch) == (lp, c, chain)})}
            if call["K"] is not None:
                exact["capin"] = (
                    {(n, k) for n in subs for k in range(1, call["K"])},
                    {(n, k) for l, n, cc, ch, k in call["capin"]
                     if (l, cc, ch) == (lp, c, chain)})
            for fam, (want, got) in exact.items():
                if fam in feats and got != want:
                    raise StreamError(
                        f"call {call['call_id']} loop {lp} col {c} {chain}: "
                        f"{fam} covers {sorted(got)}, the exact universe under "
                        f"mstep={ms}, K={call['K']} is {sorted(want)}")


def calls(stream: str) -> list:
    """Every validated call, as a LIST (owner P0-1).

    A generator let a caller take the first call with `next()` and never reach
    the end-of-stream checks, so a truncated stream passed by not being read to
    the end. The whole stream is validated before anything is returned.

    Bracketed by the driver's `G33N CALL_BEGIN/END`, not inferred from record
    order: the kernel's own `loop` resets to 1 every call, so a reader keying on
    it collapses every call onto the last, and a truncated stream or a changed
    call count is silently re-attributed instead of refused.
    """
    g33n = [l for l in stream.splitlines() if l.startswith("G33N")]
    _expect_stream(g33n, "stream carries no G33N records")
    _expect_stream(STREAM_BEGIN.match(g33n[0]),
                   f"first G33N record is not STREAM_BEGIN: {g33n[0]!r}")
    _expect_stream(STREAM_END.match(g33n[-1]),
                   "last G33N record is not STREAM_END — the stream is truncated")
    _expect_stream(sum(1 for l in g33n if STREAM_BEGIN.match(l)) == 1,
                   "more than one STREAM_BEGIN")
    _expect_stream(sum(1 for l in g33n if STREAM_END.match(l)) == 1,
                   "more than one STREAM_END")
    out = []
    cur, expect, header, ended, seen = None, 1, None, False, 0
    emitted = set()
    for line in stream.splitlines():
        if (m := STREAM_BEGIN.match(line)):
            if header:
                raise StreamError("two STREAM_BEGIN headers in one stream")
            (schema, nsplit, ntile, expected, algo, mode, feats,
             rho_profile) = m.groups()
            if int(schema) != SCHEMA:
                raise StreamError(f"stream declares schema {schema}, parser is {SCHEMA}")
            features = set(feats.split(","))
            unknown = features - FEATURES
            if unknown:
                raise StreamError(f"stream declares unknown features {sorted(unknown)}")
            if rho_profile not in RHO_PROFILES:
                raise StreamError(
                    f"stream declares unknown rho_profile {rho_profile!r}; "
                    f"expected one of {sorted(RHO_PROFILES)}")
            header = {"nsplit": int(nsplit), "ntile": int(ntile),
                      "expected_calls": int(expected), "algorithm": algo,
                      "mode": mode, "features": features,
                      # The forcing intervention this run applied. An experiment
                      # arm that lives only in a document has to be INFERRED from
                      # the numbers; here it is part of the record (owner §5).
                      "rho_profile": rho_profile}
            if header["expected_calls"] != header["nsplit"] * header["ntile"]:
                raise StreamError(
                    f"header is inconsistent: {nsplit} splits x {ntile} tiles is not "
                    f"{expected} calls")
            continue
        if STREAM_END.match(line):
            if cur is not None:
                raise StreamError(f"STREAM_END inside call {cur['call_id']}")
            ended = True
            continue
        if (m := CALL_BEGIN.match(line)):
            if cur is not None:
                raise StreamError(f"call {cur['call_id']} never ended")
            if ended:
                raise StreamError("a call begins after STREAM_END")
            cid, split, tile = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if cid != expect:
                raise StreamError(f"call ids jump: expected {expect}, got {cid}")
            if header and cid != (split - 1) * header["ntile"] + tile:
                raise StreamError(
                    f"call {cid} does not match split {split} tile {tile} under "
                    f"ntile={header['ntile']}")
            cur = _blank(cid, split, tile, _f32(m.group(7)))
            cur["cols"] = (int(m.group(4)), int(m.group(5)))
            cur["K"] = int(m.group(6))
            continue
        if (m := CALL_END.match(line)):
            if cur is None or int(m.group(1)) != cur["call_id"]:
                raise StreamError(f"CALL_END {m.group(1)} without a matching begin")
            if (int(m.group(2)), int(m.group(3))) != (cur["split"], cur["tile"]):
                raise StreamError(
                    f"CALL_END {m.group(1)} reports split/tile "
                    f"{m.group(2)}/{m.group(3)}, begin said "
                    f"{cur['split']}/{cur['tile']}")
            cur["features"] = header["features"] if header else frozenset()
            _check(cur)
            out.append(cur)
            cur, expect, seen = None, expect + 1, seen + 1
            continue
        fam = _family(line) if line.startswith("G33F") else None
        # An extension record describes one bracketed call and is meaningless
        # outside it. Falling through to `continue` DROPPED it silently, so a
        # stream whose records had drifted out of their brackets looked complete
        # -- and CAPIN had no completeness check to notice the loss (owner P0-4).
        if fam in EXTENSION_FAMILIES and cur is None:
            raise StreamError(f"{fam} record outside any call: {line!r}")
        if cur is None:
            continue                      # records outside any call: not ours
        if fam in FAMILY_FEATURE:
            feat = FAMILY_FEATURE[fam]
            if header and feat not in header["features"]:
                raise StreamError(
                    f"call {cur['call_id']}: {fam} record but the header declares "
                    f"features {sorted(header['features'])}, not {feat!r}")
            emitted.add(feat)
        # The kernel's own `loop` is part of the identity (owner P0-3): a call
        # with loops > 1 emits the same (stage, col, k) once per loop, and a key
        # without it lets the last loop silently overwrite the first.
        if (m := STAGE.match(line)):
            stage, field, col, k, hexv = m.groups()
            loop = int(line.split()[2])
            cur["loops"].add(loop)
            _put(cur[stage], (loop, int(col), int(k)), field, _f32(hexv), cur)
        elif (m := MSTEP.match(line)):
            loop = int(line.split()[2])
            cur["loops"].add(loop)
            _put(cur["mstep"], (loop, "main", int(m.group(1))), None,
                 int(m.group(2), 16), cur)
        elif (m := MSTEPI.match(line)):
            loop = int(line.split()[2])
            cur["loops"].add(loop)
            _put(cur["mstep"], (loop, "ice", int(m.group(1))), None,
                 int(m.group(2), 16), cur)
        elif (m := NFLUX.match(line)):
            loop = int(line.split()[2])
            cur["loops"].add(loop)
            col, field, hexv = m.groups()
            _put(cur["flux"], (loop, int(col)), field, _f32(hexv), cur)
        elif (m := XFER.match(line)):
            loop, n, col, chain, dq, dn = m.groups()
            cur["loops"].add(int(loop))
            _put(cur["xfer"], (int(loop), int(n), int(col), chain), None,
                 (_f32(dq), _f32(dn)), cur)
        elif (m := CAPIN.match(line)):
            loop, n, col, k, chain, oq, iq, on, ino = m.groups()
            cur["loops"].add(int(loop))
            _put(cur["capin"], (int(loop), int(n), int(col), chain, int(k)), None,
                 (_f32(oq), _f32(iq), _f32(on), _f32(ino)), cur)
        elif (m := TOPOUT.match(line)):
            loop, n, col, k, chain, oq, on = m.groups()
            cur["loops"].add(int(loop))
            _put(cur["topout"], (int(loop), int(n), int(col), chain, int(k)), None,
                 (_f32(oq), _f32(on)), cur)
        elif line.startswith("G33N"):
            raise StreamError(f"unknown G33N record inside a call: {line!r}")
        elif line.startswith("G33F"):
            # Reject an unknown record FAMILY, not an unconsumed stage: the
            # stream legitimately carries STAGE records for stages this parser
            # does not read (kernel_init_constants, the op ladder). A family it
            # has never heard of is a protocol mismatch (owner P0-E1).
            # `G33FOP` is its own family with no space after G33F, so the family
            # is the first token when it is not exactly "G33F".
            if fam not in KNOWN_G33F:
                raise StreamError(f"unknown G33F record family {fam!r}: {line!r}")
    if cur is not None:
        raise StreamError(f"stream ends inside call {cur['call_id']}")
    # The header is mandatory (checked above), so these always run.
    if header:
        if not ended:
            raise StreamError(
                f"stream has no STREAM_END: it stopped after {seen} of "
                f"{header['expected_calls']} calls")
        if seen != header["expected_calls"]:
            raise StreamError(
                f"stream carries {seen} calls, header declared "
                f"{header['expected_calls']}")
        # A feature declared and never emitted is the failure mode that looks
        # like success: `capin` in the header with zero CAPIN records passed,
        # and the cap analysis it backs would have been computed over nothing
        # (owner P0-1).
        missing = header["features"] - emitted
        if missing:
            raise StreamError(
                f"header declares features {sorted(missing)} that no record "
                f"in the stream emits")
        # Every split's tiles must cover the domain exactly once: a gap or an
        # overlap between tiles is a decomposition that did not process the
        # state it claims to (owner P0-3).
        for sp in sorted({c["split"] for c in out}):
            seg = sorted(c["cols"] for c in out if c["split"] == sp)
            lo = seg[0][0]
            for a, b in seg:
                if a != lo:
                    raise StreamError(
                        f"split {sp}: tile columns {seg} leave a gap or overlap "
                        f"at column {lo}")
                lo = b + 1
    return out


def _expect_stream(cond, msg):
    if not cond:
        raise StreamError(msg)


def _finite(value, where, call):
    """No NaN or Inf may enter a store (owner P0-5).

    The finite check lived in `_check_loop` and covered NFLUX and CAPIN only, so
    a NaN XFER parsed cleanly, made the matched residual NaN, and reached a JSON
    writer that emits a bare `NaN` token -- malformed evidence that had passed
    every gate. Checking at the write makes it uniform over every float record
    instead of a list someone has to remember to extend.
    """
    for v in (value if isinstance(value, tuple) else (value,)):
        if isinstance(v, float) and (v != v or abs(v) == float("inf")):
            raise StreamError(f"call {call['call_id']}: non-finite value {v} "
                              f"at {where}")


def _family(line: str) -> str:
    """The G33F record family. `G33FOP` has no space after G33F, so the family is
    the first token whenever that token is not exactly `G33F`."""
    tok = line.split()
    return tok[0] if tok[0] != "G33F" else (tok[1] if len(tok) > 1 else "")


def _put(store, key, field, value, call):
    """One write per (key, field). A second is a defect, not an update.

    A repeat carrying the SAME value used to overwrite silently (owner P0-2).
    That contradicted this docstring, and a duplicated stream is not a valid
    record of a run whatever the values agree on -- the duplication itself is the
    defect, not the disagreement.
    """
    _finite(value, key if field is None else f"{key}.{field}", call)
    if field is None:
        if key in store:
            raise StreamError(f"call {call['call_id']}: duplicate record {key}")
        store[key] = value
    else:
        slot = store.setdefault(key, {})
        if field in slot:
            raise StreamError(
                f"call {call['call_id']}: duplicate record {key}.{field}")
        slot[field] = value


def transfers(x, x_post, w):
    """Per-cell outflow in mixing-ratio units, top-first, from the state change.

    `w[t]` is the inflow weight the kernel applies to what left the cell above.
    Valid for a single substep only; see the module docstring.
    """
    a = [x[0] - x_post[0]]
    for t in range(1, len(x)):
        a.append(x[t] - x_post[t] + a[t - 1] * w[t])
    return a


def column(call, col, species):
    """One (call, column, species): measured residual and predicted creation, or
    None where the sub-step count makes the transfers unrecoverable."""
    chain, fkey, carries_density = SPECIES[species]
    lp = single_loop(call)
    if call["mstep"].get((lp, chain, col)) != 1:
        return None
    pre, post = call["outer_pre_sed"], call["outer_post_sed"]
    ks = sorted(k for l, c, k in pre if c == col and l == lp)   # 0 = TOP
    den = [pre[(lp, col, k)]["rho"] for k in ks]
    dz = [pre[(lp, col, k)]["delz"] for k in ks]
    x = [pre[(lp, col, k)][species] for k in ks]
    x1 = [post[(lp, col, k)][species] for k in ks]
    w = [0.0] + [dz[t - 1] / dz[t] * (den[t - 1] / den[t] if carries_density else 1.0)
                 for t in range(1, len(ks))]
    a = transfers(x, x1, w)

    n0w = sum(den[t] * dz[t] * x[t] for t in range(len(ks)))
    n1w = sum(den[t] * dz[t] * x1[t] for t in range(len(ks)))
    surface = den[-1] * dz[-1] * a[-1]
    residual = (n1w - n0w) + surface
    out = {"start": n0w, "residual": residual, "surface": surface,
           "relative": residual / n0w if n0w else 0.0, "final": 0.0,
           "surface_uncapped": 0.0}
    if fkey:   # independent check of the recovery, where an accumulator exists
        f = call["flux"][(lp, col)]
        out["surface_uncapped"] = f[fkey] * den[-1] * dz[-1] * f["nflux_dtcld"]
    return out


#: species -> (its emitted surface accumulator, whether the accumulator is a
#: NUMBER flux [# kg-1 s-1, needs den] or a MASS flux [kg m-3 s-1, does not]).
EMITTED = {"qr": ("bottom_fall_qr", False), "nr": ("bottom_falln_nr", True),
           "ni": ("bottom_falln_ni", True)}


def closure(call, col, species):
    """Transport-only closure from EMITTED data alone -- no recursion.

    The segment `outer_pre_sed .. outer_post_sed` is F:1189-1340: both
    sedimentation sub-cycles and nothing else, so it isolates transport WITHOUT
    needing a fixture with the microphysical sources switched off. Conservation
    under the rho*dz measure means

        [X(post) - X(pre)] + F_surface = 0

    and every term here is read from the stream. That is what makes the MASS row a
    real control: unlike the recovered-transfer form, nothing in this arithmetic
    forces it to vanish.
    """
    acc, is_number = EMITTED[species]
    lp = single_loop(call)
    pre, post, srf = call["outer_pre_sed"], call["outer_post_sed"], call["surface"]
    f = call["flux"].get((lp, col), {})
    ks = sorted(k for l, c, k in pre if c == col and l == lp)
    den = [pre[(lp, col, k)]["rho"] for k in ks]
    dz = [pre[(lp, col, k)]["delz"] for k in ks]
    x0 = sum(den[t] * dz[t] * pre[(lp, col, ks[t])][species] for t in range(len(ks)))
    x1 = sum(den[t] * dz[t] * post[(lp, col, ks[t])][species] for t in range(len(ks)))
    raw = f.get(acc, srf.get((lp, col, -1), {}).get(acc))
    if raw is None:
        return None
    # falln is [# kg-1 s-1] so it needs den; fall is [kg m-3 s-1] so it does not.
    out = raw * dz[-1] * f["nflux_dtcld"] * (den[-1] if is_number else 1.0)
    return {"start": x0, "out": out, "residual": (x1 - x0) + out}


def closure_report(stream: str) -> dict:
    """{species: {col: ...}} plus the printed table."""
    acc = {}
    for call in calls(stream):
        for col in sorted({c for _, c, _ in call["outer_pre_sed"]}):
            for sp in EMITTED:
                # The caps are per SPECIES, so the check has to be too. Where the
                # emitted accumulator and the recovered transfer disagree the
                # `min`/`max` bound and the emitted flux overstates the removal;
                # such a call measures the cap, not the transport.
                if sp in SPECIES and SPECIES[sp][1] is not None:
                    c = column(call, col, sp)
                    if c is None or abs(c["surface"] - c["surface_uncapped"]) > \
                            1e-6 * abs(c["surface_uncapped"] or 1.0):
                        continue
                r = closure(call, col, sp)
                if r is None or r["start"] == 0 or r["out"] == 0:
                    continue
                d = acc.setdefault((sp, col), {"n": 0, "out": 0.0, "residual": 0.0})
                d["n"] += 1
                d["out"] += r["out"]
                d["residual"] += r["residual"]
    print("\n  TRANSPORT-ONLY closure from EMITTED data alone (no recursion)")
    print("  The segment is both sedimentation sub-cycles and nothing else, so a")
    print("  sources-off fixture is not needed. qr is a REAL control here.\n")
    print(f"  {'sp':>3} {'col':>4} {'calls':>6} {'surface out':>14} "
          f"{'residual':>14} {'residual/out':>14}")
    for (sp, col), d in sorted(acc.items(), key=lambda kv: (kv[0][0][0] != "q", kv[0])):
        rel = d["residual"] / d["out"] if d["out"] else float("nan")
        print(f"  {sp:>3} {col:>4} {d['n']:>6} {d['out']:14.5e} "
              f"{d['residual']:14.5e} {rel:13.4%}")
    return {f"{sp}/{col}": d for (sp, col), d in acc.items()}


def report(stream: str) -> None:
    acc = {}
    for call in calls(stream):
        for col in sorted({c for _, c, _ in call["outer_pre_sed"]}):
            for sp in SPECIES:
                r = column(call, col, sp)
                if r is None or r["start"] == 0:
                    continue
                d = acc.setdefault((sp, col), dict.fromkeys(r, 0.0) | {"n": 0})
                for k, v in r.items():
                    d[k] += v
                d["n"] += 1
                # overwritten each call, so it ends as the last call's end state
                d["final"] = r["start"] + r["residual"] - r["surface"]
    print("  rho*dz column number across the sedimentation segment,  mstep == 1 only")
    print("  qr/qi return ~0 BY CONSTRUCTION of their weight -- an arithmetic check,")
    print("  not a control. The evidence is recovered/falln; see the module docstring.\n")
    print(f"  {'sp':>3} {'col':>4} {'calls':>6} {'created':>13} {'per call':>10} "
          f"{'/ N final':>11} {'recovered/falln':>16}")
    for (sp, col), d in sorted(acc.items(),
                               key=lambda kv: (kv[0][0] not in ("qr", "qi"), kv[0])):
        chk = (d["surface"] / d["surface_uncapped"]
               if d["surface_uncapped"] else float("nan"))
        fin = d["final"]
        print(f"  {sp:>3} {col:>4} {d['n']:>6} {d['residual']:13.5e} "
              f"{d['relative'] / d['n']:9.4%} "
              f"{(d['residual'] / fin if fin else float('nan')):10.2%} {chk:16.4f}")
    print("\n  created  = [X(post_sed) - X(pre_sed)] + surface out;  0 iff conserved")
    print("  per call = mean of created/X at the start of that call")
    print("  recovered/falln = 1.0000 means the caps did not bind and the recovery")
    print("                    is exact; rows far from 1 are cap-dominated, not usable")
    closure_report(stream)


def main(argv) -> int:
    if not 2 <= len(argv) <= 3:
        print(__doc__)
        print("usage: g33_number_transport.py <driver-built-with---nflux> "
              "<nsplit> [analysis.json]")
        return 2
    r = subprocess.run([argv[0], argv[1], "rezero"], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(
            f"driver exited {r.returncode} — stdout is not evidence however "
            f"complete it looks (owner P0-1)\n{r.stderr[-2000:]}")
    stream = r.stdout
    report(stream)
    if len(argv) == 3:
        # The table a finding quotes and the JSON a manifest digests come from
        # ONE call, so they cannot drift apart (owner P0-4).
        Path(argv[2]).write_text(json.dumps(
            {"nsplit": int(argv[1]), "closure": closure_report(stream),
             "calls": sum(1 for _ in calls(stream))},
            indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
