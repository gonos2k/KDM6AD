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

#: One hex field, either width. The width is the STORAGE the build gave a
#: default real; `PROTOCOL` below says which, and `_real` refuses a record whose
#: width, label and header do not all agree (owner D6).
_H = r"([0-9A-F]{8}|[0-9A-F]{16})"

#: Declared by the driver from `storage_size`, `radix`, `digits` and
#: `maxexponent`, so it is what the compiler reports about its own model rather
#: than what the build script meant. Absent in every stream produced before the
#: f64 family existed, which is exactly the f32 default.
#:
#: EIGHT fields, not two. A width says how many bytes to take and says nothing
#: about how they are laid out -- and `_real` unpacks with `>f`/`>d`, which is
#: IEEE binary32/binary64, a thing no Fortran standard promises from a storage
#: size. Two fields would be a header that states half of what the reader
#: assumes, which is worse than the archived streams that state none of it and
#: are read under a documented default (owner priority 7).
PROTOCOL = re.compile(r"^G33N PROTOCOL (\d+) (\d+) (\d+) (\d+) (\d+) "
                      r"(\d+) (\d+) (\d+)$")
#: ...and any PROTOCOL line at all, so a header in the OLD two-field shape is
#: refused rather than falling through to "no header, assume f32" -- which would
#: read an f64 stream as f32 and is the whole defect the header exists for.
ANY_PROTOCOL = re.compile(r"^G33N PROTOCOL\b")
DEFAULT_REAL_BYTES = 4

#: bytes -> (radix, digits, maxexponent) for the IEEE binary formats this
#: parser can decode. A stream reporting anything else is refused: the bytes
#: would be a real number in a model `struct.unpack` does not implement.
IEEE_FORMAT = {4: (2, 24, 128), 8: (2, 53, 1024)}

#: Payload width per LABEL, in hex digits. The label says how wide the bytes
#: are; what the number MEANS is the schema's dtype, and after D6 those are two
#: tables because -fdefault-real-8 makes them disagree.
HEX_WIDTH = {"f32": 8, "f64": 16, "i32": 8, "u8": 2}

#: Records this parser CHECKS without consuming.
#:
#: The stream legitimately carries stages the number analyses never read
#: (kernel_init_constants, the micro bisection) and the whole G33FOP op ladder.
#: "Not read" had quietly become "not looked at": the family check accepted the
#: first token and nothing ever matched the rest of the line, so a record whose
#: Z edit descriptor OVERFLOWED -- which is what an eight-byte default real
#: written through `Z8.8` does -- was dropped without a word. That is the same
#: wrong-number path D6 closed for the widths it happened to reach, surviving in
#: the family it did not (owner priority 3).
#:
#: The key is what a width must be CONSTANT over: (stage, field) for a stage,
#: (op_id, field) for an op rung.
ANY_STAGE = re.compile(r"^G33F STAGE (\d+) (\S+) (\S+) (\d+) (\S+) (\d+) (-?\d+) "
                       r"(f32|f64|i32|u8) ([0-9A-F]+)$")
G33FOP = re.compile(r"^G33FOP (\d+) (\S+) (\d+) (\d+) (-?\d+) (\S+) (\S+) "
                    r"(f32|f64|u8) ([0-9A-F]+)$")
#: family -> (pattern, key group numbers, label group, hex group)
CHECKED_SHAPES = {"STAGE": (ANY_STAGE, (3, 5), 8, 9),
                  "G33FOP": (G33FOP, (6, 7), 8, 9)}

STREAM_BEGIN = re.compile(
    r"^G33N STREAM_BEGIN (\d+) (\d+) (\d+) (\d+) (\S+) (\S+) (\S+) (\S+)$")
XFER = re.compile(r"^G33F XFER (\d+) (\d+) (\d+) (main|ice) (f32|f64) "
                  + _H + " " + _H + "$")
CAPIN = re.compile(r"^G33F CAPIN (\d+) (\d+) (\d+) (-?\d+) (main|ice) (f32|f64) "
                   + " ".join([_H] * 4) + "$")
TOPOUT = re.compile(r"^G33F TOPOUT (\d+) (\d+) (\d+) (-?\d+) (main|ice) (f32|f64) "
                    + " ".join([_H] * 2) + "$")
#: Extension records this parser knows. A stream declaring a feature it does not
#: emit, or emitting one it did not declare, is refused.
FEATURES = {"mstep", "mstepi", "nflux", "xfer", "capin", "topout"}

#: The density-control arms. `as-is` is the unperturbed forcing; the rest are
#: interventions, and a stream must say which it is.
RHO_PROFILES = {"as-is", "uniform", "inverted", "x2", "offset+", "offset-"}

#: G33F record families this parser recognises. STAGE and the op ladder are
#: consumed selectively; the rest are the number extension.
KNOWN_G33F = {"STAGE", "MSTEP", "MSTEPI", "NFLUX", "XFER", "CAPIN", "TOPOUT",
              "G33FOP"}
STREAM_END = re.compile(r"^G33N STREAM_END$")
CALL_BEGIN = re.compile(r"^G33N CALL_BEGIN (\d+) (\d+) (\d+) (\d+) (\d+) (\d+) "
                        + _H + "$")
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
                   r"(\S+) (\d+) (-?\d+) (f32|f64) " + _H + "$")
NFLUX = re.compile(r"^G33F NFLUX \d+ (\d+) (\S+) (f32|f64) " + _H + "$")
MSTEP = re.compile(r"^G33F MSTEP \d+ \S+ (\d+) i32 ([0-9A-F]{8})$")
MSTEPI = re.compile(r"^G33F MSTEPI \d+ (\d+) i32 ([0-9A-F]{8})$")

#: A sub-step count is bounded by the kernel's own law: mstep = ceil(dtcld/dt_sed)
#: over a column of K cells. `FFFFFFFF` read as unsigned is 4.29e9, and the
#: universe check materialises `set(range(1, mstep+1))` -- so a malformed record
#: exhausts memory before any error is raised (owner P1-11.6). The bound is
#: generous: no fixture or kernel law reaches it.
MSTEP_MAX = 1 << 16

#: species -> (sub-step record governing it, uncapped surface accumulator or None,
#: whether its inflow carries the density ratio). `mstep` covers qr/nr/qs/qg,
#: `mstep_i` covers qi/ni (F:1179-1180). The mass rows are the CONTROL.
SPECIES = {"nr": ("main", "bottom_falln_nr", False),
           "ni": ("ice", "bottom_falln_ni", False),
           "qr": ("main", None, True),
           "qi": ("ice", None, True)}


def _f32(h: str) -> float:
    return struct.unpack(">f", bytes.fromhex(h))[0]


def _real(label: str, h: str, real_bytes: int, call=None) -> float:
    """One real, decoded at the width the record declares -- and refused unless
    the label, the hex width and the stream's own header ALL agree.

    Three ways to be wrong here and only the first was ever possible before:
    the bytes are half a number (an f64 build writing through an int32 mold),
    the label lies about the width, or the stream header disagrees with its own
    records. Any of them yields a valid-looking float, so none may be inferred
    from the others -- each is checked (owner D6).
    """
    want = {"f32": 4, "f64": 8}[label]
    if len(h) != 2 * want:
        _expect_stream(False, f"a {label} record carries {len(h)} hex digits, "
                              f"not {2 * want}")
    if label == "f32" and real_bytes != 4:
        _expect_stream(False, f"an f32 record in a stream whose header declares "
                              f"{real_bytes}-byte reals")
    if label == "f64" and real_bytes != 8:
        _expect_stream(False, f"an f64 record in a stream whose header declares "
                              f"{real_bytes}-byte reals")
    return struct.unpack(">d" if want == 8 else ">f", bytes.fromhex(h))[0]


#: Decoders for a checked-only payload, by storage label. `i32` decodes and
#: imposes nothing: a stage integer's domain is a property of the FIELD, not of
#: the width, and `mstep` -- the one this parser bounds -- is bounded where it is
#: consumed. Decoding it anyway is what makes "every label has a decoder" a
#: checkable statement rather than a list someone has to remember to extend.
_DECODE = {"f32": lambda h: struct.unpack(">f", bytes.fromhex(h))[0],
           "f64": lambda h: struct.unpack(">d", bytes.fromhex(h))[0],
           "i32": lambda h: struct.unpack(">i", bytes.fromhex(h))[0],
           "u8": lambda h: h}


def _domain(fam: str, label: str, hexv: str, line: str) -> None:
    """The payload is a VALUE, not just the right number of hex digits.

    Width and label agreement says the bytes are the size they claim. It does
    not say they are a number: `7FF8000000000000` is a perfectly well-formed
    sixteen-digit f64 and it is NaN, and `FF` is a perfectly well-formed u8 and
    the emitter can only write `00` or `01` (`merge(1, 0, <logical>)`).
    Measured: both parsed clean.

    The consumed records have had this since a NaN XFER reached a JSON writer
    that emits a bare `NaN` token -- malformed evidence that had passed every
    gate (owner P0-5). The checked-only families got the width half of that
    check and not the value half, so the same NaN in the op ladder was fine
    (owner priority 2).
    """
    v = _DECODE[label](hexv)
    if label == "u8":
        if v not in ("00", "01"):
            raise StreamError(
                f"{fam} u8 payload {v!r} is outside the boolean domain the "
                f"emitter can write (merge(1, 0, ...)): {line!r}")
    elif isinstance(v, float) and (v != v or abs(v) == float("inf")):
        raise StreamError(f"{fam} {label} payload is {v}: {line!r}")


def _shape(line: str, fam: str, widths: dict) -> None:
    """One emitted record this parser does not consume, checked anyway.

    Three things, and only the first is about this record alone:

      the line MATCHES its family's grammar -- an overflowed or truncated
      payload is refused instead of silently matching nothing;
      the hex width is the one the LABEL promises;
      the label is the one this key carried EARLIER IN THE SAME STREAM.

    The last is what a per-record check cannot give and a header cannot either:
    a single PROTOCOL header says what a default real is, but a field pinned at
    `real(...,4)` is legitimately narrower than that, so "matches the header" is
    not the contract. "Never changes width within one run" is, and it is the
    property a mixed-width stream breaks.

    What this does NOT certify is which of the two a given field should be.
    That is a property of the Fortran EXPRESSION behind the binding, it is
    decided by `g33_fortran_bindings.storage_class`, and the overlay generator
    checks the whole table against it before it writes a line.
    """
    pat, keys, li, hi = CHECKED_SHAPES[fam]
    m = pat.match(line)
    if not m:
        raise StreamError(f"malformed {fam} record: {line!r}")
    label, hexv = m.group(li), m.group(hi)
    if len(hexv) != HEX_WIDTH[label]:
        raise StreamError(
            f"{fam} record labelled {label} carries {len(hexv)} hex digits, "
            f"not {HEX_WIDTH[label]}: {line!r}")
    _domain(fam, label, hexv, line)
    key = (fam, tuple(m.group(g) for g in keys))
    if widths.setdefault(key, label) != label:
        raise StreamError(
            f"{fam} {'.'.join(key[1])} is {label} here and {widths[key]} "
            f"earlier in the same stream; a field does not change width "
            f"mid-run, so one of the two records is not the number it says")


def _mstep(hexv: str, call) -> int:
    """A sub-step count, decoded SIGNED and bounded before it is used.

    Read unsigned and unbounded, `FFFFFFFF` becomes 4.29e9 and the exact-universe
    check tries to materialise a set that large -- memory exhaustion before any
    clean error (owner P1-11.6).
    """
    v = struct.unpack(">i", bytes.fromhex(hexv))[0]
    if not 1 <= v <= MSTEP_MAX:
        raise StreamError(
            f"call {call['call_id']}: mstep {v} is outside 1..{MSTEP_MAX}")
    return v


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

    A call with NO loops is refused before the per-loop walk (owner review §5).
    Every completeness rule here iterates `call["loops"]`, so an empty set ran
    every check zero times and an empty call -- CALL_BEGIN, CALL_END, nothing
    between -- counted as complete. Measured: a two-tile split whose first
    tile carried zero records parsed clean, its declared columns covered by
    nothing, while the tile-span check happily summed the declaration. The
    recurring defect class: measuring nothing, certified as complete.
    """
    if not call["loops"]:
        raise StreamError(
            f"call {call['call_id']} declares columns "
            f"{call['cols']} and carries no records at all -- an empty call "
            f"is not a processed tile, it is a declaration with nothing "
            f"behind it")
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
    # PROTOCOL is a HEADER record, not a bracket one, so it is out of the
    # STREAM_BEGIN/END position checks. Leaving it in made those checks depend
    # on which of the two the driver happens to write first.
    g33n = [l for l in stream.splitlines()
            if l.startswith("G33N") and not ANY_PROTOCOL.match(l)]
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
    # What a default real is in THIS stream. Absent in every stream produced
    # before the f64 family existed, and those were all f32 builds -- so the
    # default is the answer for them, not a guess (owner D6).
    rb = DEFAULT_REAL_BYTES
    # The PROTOCOL header's POSITION and UNIQUENESS, which nothing checked: `rb`
    # was a variable the loop reassigned, so a second header mid-stream simply
    # took effect and a run whose first half was f32 and whose second half was
    # f64 read as one consistent stream. A width is a property of the BUILD, so
    # it cannot change inside one run -- and a header arriving after the records
    # it governs would be retroactive, which is not a contract either
    # (owner priority 2).
    proto, body = False, False
    # (family, key) -> the label it first carried, for the records below that
    # this parser checks without consuming.
    widths = {}
    for line in stream.splitlines():
        if (m := PROTOCOL.match(line)):
            if proto:
                raise StreamError(
                    "two G33N PROTOCOL headers in one stream: the default-real "
                    "width is what the compiler did to the whole run, so a "
                    "second declaration cannot be true of the same records")
            if body or ended:
                raise StreamError(
                    "a G33N PROTOCOL header after the stream body began: every "
                    "record before it was read at the default width, so the "
                    "header would be retroactive")
            proto = True
            rb, db = int(m.group(1)), int(m.group(2))
            _expect_stream(rb in (4, 8),
                           f"stream declares {rb}-byte default reals")
            _expect_stream(db == 8,
                           f"stream declares {db}-byte doubles; -fdefault-real-8 "
                           f"without -fdefault-double-8 promotes them to 16 and "
                           f"the schema-f64 fields stop being readable")
            for what, nbytes, at in (("default reals", rb, 3), ("doubles", db, 6)):
                got = tuple(int(m.group(g)) for g in (at, at + 1, at + 2))
                if got != IEEE_FORMAT[nbytes]:
                    raise StreamError(
                        f"stream declares {nbytes}-byte {what} with "
                        f"(radix, digits, maxexponent) {got}, not "
                        f"{IEEE_FORMAT[nbytes]} -- the reader decodes IEEE "
                        f"binary{nbytes * 8}, and a width alone does not make "
                        f"the bytes one")
            continue
        if ANY_PROTOCOL.match(line):
            raise StreamError(
                f"malformed G33N PROTOCOL header: {line!r} -- it must carry the "
                f"real and double widths AND both radix/digits/maxexponent "
                f"triples. A header stating half of what the reader assumes is "
                f"worse than none, because none is read under a documented "
                f"default and half is read as agreement")
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
            body = True
            cid, split, tile = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if cid != expect:
                raise StreamError(f"call ids jump: expected {expect}, got {cid}")
            # RANGES first, then the equation (owner review §6). The cid
            # equation alone is satisfiable outside the domain: under ntile=2,
            # split=0/tile=3 gives cid 1 and split=1/tile=2 gives cid 2, and
            # both parsed clean -- a decomposition the header does not
            # describe, admitted because arithmetic is not a range check.
            if header and not 1 <= split <= header["nsplit"]:
                raise StreamError(
                    f"call {cid}: split {split} is outside 1..{header['nsplit']}")
            if header and not 1 <= tile <= header["ntile"]:
                raise StreamError(
                    f"call {cid}: tile {tile} is outside 1..{header['ntile']}")
            if header and cid != (split - 1) * header["ntile"] + tile:
                raise StreamError(
                    f"call {cid} does not match split {split} tile {tile} under "
                    f"ntile={header['ntile']}")
            # The GEOMETRY the call declares, checked where it is declared
            # (owner review §5). Each was individually masked by later checks
            # on well-formed streams and unchecked on degenerate ones: K=0
            # makes the level universe empty, an inverted column range makes
            # `range(lo, hi+1)` empty, and `delt` reached `_blank` without a
            # finiteness check anywhere.
            lo_c, hi_c, kk = int(m.group(4)), int(m.group(5)), int(m.group(6))
            if kk < 1:
                raise StreamError(f"call {cid}: K={kk} is not a level count")
            if not 1 <= lo_c <= hi_c:
                raise StreamError(
                    f"call {cid}: column range {lo_c}..{hi_c} is not a "
                    f"non-empty 1-based range")
            # `delt` carries no label -- the record shape predates the f64
            # family and every archived stream has it -- so its width comes
            # from the PROTOCOL header, which is emitted before any call.
            delt = _real("f64" if rb == 8 else "f32", m.group(7), rb)
            if delt != delt or abs(delt) == float("inf") or delt <= 0:
                raise StreamError(
                    f"call {cid}: delt={delt} is not a positive finite "
                    f"timestep")
            cur = _blank(cid, split, tile, delt)
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
        # CHECKED before the consumption branches, and before the `cur is None`
        # drop below: a record this parser does not read is still a record the
        # run emitted, and the only thing worse than reading it wrong is not
        # looking at it (owner priority 3).
        if fam in CHECKED_SHAPES:
            _shape(line, fam, widths)
        # An extension record describes one bracketed call and is meaningless
        # outside it. Falling through to `continue` DROPPED it silently, so a
        # stream whose records had drifted out of their brackets looked complete
        # -- and CAPIN had no completeness check to notice the loss (owner P0-4).
        if fam in EXTENSION_FAMILIES and cur is None:
            raise StreamError(f"{fam} record outside any call: {line!r}")
        # CLOSED WORLD, and it has to be closed HERE.
        #
        # The unknown-family refusals below sit AFTER this point, so they only
        # ever saw records inside a bracket. An unknown `G33N` between two
        # calls, an unknown `G33F` before the first one, a well-formed G33FOP
        # after STREAM_END -- each was dropped without a word, and the parsed
        # call count did not move. Measured: four such mutations on a real f64
        # stream, four silent acceptances. That is the same defect class as the
        # `********` payload that vanished instead of failing: a record the
        # parser cannot place must not become a record that was never there
        # (owner priority 1).
        #
        # Every bracket and header record is handled above and `continue`d, so
        # anything reaching here in this parser's own namespace is a DATA
        # record, and a data record outside a call describes nothing. Real
        # streams carry none: measured 0 across every stream this parser reads.
        # Other protocols sharing the same stdout -- G33R, G33P -- are not ours
        # and are left alone, which is what keeps the world closed rather than
        # merely small.
        if cur is None:
            if line.startswith(("G33N", "G33F")):
                raise StreamError(
                    f"record {'after STREAM_END' if ended else 'outside any call'}"
                    f": {line!r} -- this parser's namespace is closed, so a "
                    f"record it cannot place is a protocol change, not noise")
            continue                      # another protocol's records: not ours
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
            stage, field, col, k, dt, hexv = m.groups()
            loop = int(line.split()[2])
            cur["loops"].add(loop)
            _put(cur[stage], (loop, int(col), int(k)), field,
                 _real(dt, hexv, rb), cur)
        elif (m := MSTEP.match(line)):
            loop = int(line.split()[2])
            cur["loops"].add(loop)
            _put(cur["mstep"], (loop, "main", int(m.group(1))), None,
                 _mstep(m.group(2), cur), cur)
        elif (m := MSTEPI.match(line)):
            loop = int(line.split()[2])
            cur["loops"].add(loop)
            _put(cur["mstep"], (loop, "ice", int(m.group(1))), None,
                 _mstep(m.group(2), cur), cur)
        elif (m := NFLUX.match(line)):
            loop = int(line.split()[2])
            cur["loops"].add(loop)
            col, field, dt, hexv = m.groups()
            _put(cur["flux"], (loop, int(col)), field, _real(dt, hexv, rb), cur)
        elif (m := XFER.match(line)):
            loop, n, col, chain, dt, dq, dn = m.groups()
            cur["loops"].add(int(loop))
            _put(cur["xfer"], (int(loop), int(n), int(col), chain), None,
                 (_real(dt, dq, rb), _real(dt, dn, rb)), cur)
        elif (m := CAPIN.match(line)):
            loop, n, col, k, chain, dt, oq, iq, on, ino = m.groups()
            cur["loops"].add(int(loop))
            _put(cur["capin"], (int(loop), int(n), int(col), chain, int(k)), None,
                 tuple(_real(dt, h, rb) for h in (oq, iq, on, ino)), cur)
        elif (m := TOPOUT.match(line)):
            loop, n, col, k, chain, dt, oq, on = m.groups()
            cur["loops"].add(int(loop))
            _put(cur["topout"], (int(loop), int(n), int(col), chain, int(k)), None,
                 (_real(dt, oq, rb), _real(dt, on, rb)), cur)
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
        # One stream, one problem: every call must declare the SAME level
        # count and the SAME timestep (owner review §6). The ranges above plus
        # the cid equation plus the sequential-id and count checks force the
        # (split, tile) set to be exactly {1..nsplit} x {1..ntile} -- a
        # bijection needs no separate universe walk -- but nothing tied K and
        # delt together across calls, so one call could describe a different
        # vertical grid or step than its neighbours and each would validate
        # alone.
        ks = {c["K"] for c in out}
        if len(ks) > 1:
            raise StreamError(
                f"calls declare different level counts {sorted(ks)} -- one "
                f"stream describes one problem")
        dts = {c["delt"] for c in out}
        if len(dts) > 1:
            raise StreamError(
                f"calls declare different timesteps {sorted(dts)} -- one "
                f"stream describes one problem")
        # Every split's tiles must cover THE DOMAIN exactly once: a gap or an
        # overlap between tiles is a decomposition that did not process the
        # state it claims to (owner P0-3).
        #
        # Anchored at COLUMN 1, and congruent ACROSS splits (owner review §7).
        # The check used to take the first tile's own start as the origin, so a
        # split covering 2..3 -- column 1 missing entirely -- was contiguous
        # from where it happened to begin, and passed. And nothing compared one
        # split's coverage against another's, so 1..2 beside 1..3 was two
        # decompositions of two different domains in one stream. The real
        # driver refuses both before emitting, but this parser judges
        # arbitrary artifacts and may not re-assume the producer's checks.
        spans = {}
        for sp in sorted({c["split"] for c in out}):
            seg = sorted(c["cols"] for c in out if c["split"] == sp)
            lo = 1
            for a, b in seg:
                if a != lo:
                    raise StreamError(
                        f"split {sp}: tile columns {seg} do not cover the "
                        f"domain from column 1 -- gap or overlap at column {lo}")
                lo = b + 1
            spans[sp] = lo - 1
        if len(set(spans.values())) > 1:
            raise StreamError(
                f"splits cover different domains: {spans} -- one stream, one "
                f"domain, so every decomposition must partition the same "
                f"columns")
    return out


def validated_run_identity(text: str, expected_width: int | None = None,
                           expected_levels: int | None = None) -> dict:
    """The run identity, FROM the strict parser -- never beside it.

    The evidence chain re-derived nsplit/carry/rho/width from the published
    bytes with two regular expressions, so a stream the strict parser REFUSES
    -- duplicate STREAM_BEGIN, an unterminated call, NaN payloads -- could
    still report `matches` for its run identity. Measured: it did (owner
    review §6). One function, built on `calls()`, used by the producer at
    publish time and by the chain on the published artifact, so there is no
    weaker reader to drift back to.

    `expected_width`/`expected_levels` pin the domain where the caller knows
    it: `calls()` itself proves the tiles partition 1..W for a single W and
    one K, and these prove W and K are the FIXTURE's. Without the width pin a
    stream whose G33N covers 1..2 beside a window protocol covering 1..3 is
    two internally-strict protocols describing different domains in one
    stdout, and every G33N analysis silently omits column 3 (owner review §4).
    """
    parsed = calls(text)
    hdr = stream_header(text)
    width = max(c["cols"][1] for c in parsed)
    levels = parsed[0]["K"]
    if expected_width is not None and width != expected_width:
        raise StreamError(
            f"the stream's splits cover columns 1..{width}, the caller "
            f"expected the fixture's 1..{expected_width}")
    if expected_levels is not None and levels != expected_levels:
        raise StreamError(
            f"the stream declares K={levels} levels, the caller expected the "
            f"fixture's {expected_levels}")
    return {"nsplit": hdr["nsplit"], "carry": hdr["mode"],
            "rho": hdr["rho_profile"], "width": width, "levels": levels}


def stream_header(stream: str) -> dict:
    """What the stream DECLARES about the run that produced it.

    `calls()` reads this to validate the body and then throws it away, so a
    caller wanting to ask "which run is this?" had to re-derive it from a
    filename or trust a manifest field. Those are the two things that cannot
    check each other (owner priority 5).
    """
    for line in stream.splitlines():
        if (m := STREAM_BEGIN.match(line)):
            (schema, nsplit, ntile, expected, algo, mode, feats,
             rho_profile) = m.groups()
            return {"schema": int(schema), "nsplit": int(nsplit),
                    "ntile": int(ntile), "expected_calls": int(expected),
                    "algorithm": algo, "mode": mode,
                    "features": set(feats.split(",")), "rho_profile": rho_profile}
    raise StreamError("stream carries no G33N STREAM_BEGIN header")


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
