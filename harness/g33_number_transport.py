#!/usr/bin/env python3
"""Sedimentation does not conserve column NUMBER under the rho*dz measure.

The mass transfer carries the density ratio implicitly (`falk` is built with
`dend(k+1)`, the inflow divides by `dend(k)`, F:1214-1219). The number transfer
carries only the thickness ratio (F:1221-1224):

    dnr(i,k+1) = min(falkn(i,k+1,1)*delz(i,k+1)/delz(i,k)*dtcld, nrs(i,k+1,1))
    nrs(i,k,1) = max(nrs(i,k,1) - dnr(i,k) + dnr(i,k+1), 0.)

`nrs` receives the host's stored `nr` without conversion (F:388). Registry's
per-dry-kg interpretation and the slope equation's per-volume requirement remain
inconsistent; see SCIENCE_STATUS.md. `den` here is MOIST density. The dry-weight
ledger is physical number only under the per-dry-kg interpretation; a per-volume
interpretation instead uses sum dz*N. These diagnostic weights do not choose a
production unit contract.

IF thickness-weighted departure equals arrival, the density-weighted residual is

    created = sum over interfaces of [den(lower) - den(upper)] * delz(upper) * b

## Why the transfers are recovered rather than read

`falln` is the UNCAPPED accumulator: the kernel removes `min(falkn*dtcld, nrs)`
but `falln` sums `falkn`. Using it as the surface flux mixes this defect with the
P0-4b interface-cap gap, and the total then exceeds what the density ratios can
explain. With `mstep == 1` there is exactly one substep, so the per-interface
transfers follow from the state change alone, top down:

    b_0 = nr_0 - nr'_0                                (top cell: no inflow)
    b_t = nr_t - nr'_t + b_{t-1} * delz_{t-1}/delz_t

This recovery ASSUMES matched thickness-weighted interface transfers. Separate
departure/arrival caps can violate it even at mstep=1. The recovered bottom
value is not then a measured removal. For actual paired accounting use the
TOPOUT/CAPIN path in g33_cap_interface, which includes the additional term
rho_lo*(dz_lo*dn_in-dz_up*dn_out). More than one substep also makes recovery
non-invertible from endpoints.

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
import g33_arms

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

#: The arm's own declaration of which measure its number transfer weights by.
#: OPTIONAL and accepted before it is emitted: a record the parser refuses is a
#: record that cannot be added, and adding one to the driver first is what broke
#: 47 local tests once. Parser tolerant, driver second.
STREAM_METRIC = re.compile(r"^G33N METRIC (\S+)$")

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

#: The SURFACE stage's exact field vocabulary (owner review §7).
#:
#: Requiring merely that every column carry the SAME set let a stream whose
#: only surface field was something no analysis reads pass the universe check,
#: while a surface-based closure looking for `bottom_fall_qr` got `None` and
#: dropped its row in silence -- "a surface row exists" is not "the quantity
#: the analysis needs exists". Measured across the archive before enforcing:
#: all 26751 published surface cells carry exactly these seven.
#:
#: Stated HERE, with the protocol, rather than imported from the overlay
#: generator that emits them -- and a test compares the two, because two
#: records of one fact are only worth having if something checks them.
SURFACE_REQUIRED = frozenset({
    "bottom_fall_qr", "bottom_fall_qs", "bottom_fall_qg", "bottom_fall_qi",
    "bottom_fall_total", "delz_bottom", "surface_denr"})
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
#: species -> (chain, surface accumulator, whether the transfer WEIGHT carries
#: density under the LEGACY kernel).
#:
#: The third entry is a property of the ALGORITHM, not of the species, and
#: writing it here made that invisible while legacy was the only arm. Arm N
#: gives the number transfer the air-mass ratio, so recovering its transfers
#: with the thickness-only weight reconstructs the wrong `b` and reports a
#: residual that did not happen -- measured, the arm looked unchanged.
SPECIES = {"nr": ("main", "bottom_falln_nr", False),
           "ni": ("ice", "bottom_falln_ni", False),
           "qr": ("main", None, True),
           "qi": ("ice", None, True)}

#: WHICH LAYER MEASURE each arm's NUMBER transfer weights by. Read from the
#: stream's own header, so an artifact answers for the operator that made it
#: rather than for whichever the reader assumed.
#:
#: Every entry is transcribed from that arm's transfer statement, where the
#: Fortran's `k+1` is this analyzer's `t-1` (the source layer, since `ks` is
#: sorted with 0 = TOP):
#:
#:     legacy, lncmin, cons, cons_lncmin
#:         falkn*delz(k+1)/delz(k)                          -> thickness
#:     nmass, nmasslncmin, cons_nmass, cons_nmasslncmin
#:         falkn*dend(k+1)*delz(k+1)/(dend(k)*delz(k))      -> moist layer mass
#:     nmass_dry
#:         ...*(1.+q(k)) / (...*(1.+q(k+1)))                -> CURRENT dry mass
#:     nmass_dry_window
#:         falkn*mdry0(k+1)/mdry0(k)                        -> WINDOW dry mass
#:
#: The KEYS are the driver's own `ALGOTAG` strings, which are what a stream
#: carries -- not the variant file names, which differ (`conservative` against
#: `module_mp_kdm6_cons.F`). A test pins the two sets equal.
NUMBER_TRANSFER_METRIC = g33_arms.metrics()   # the keys are the driver's ALGOTAG strings


def number_transfer_metric(algorithm, declared=None) -> str:
    """Which layer measure does this arm's number transfer weight by?

    A TOTAL function over the registry above, which refuses a name it does not
    know. It replaces a boolean that answered `"nmass" in algorithm`, and the
    history of that boolean is the argument for this shape:

    * First it was a SET containing exactly `nmass`, so every combined arm --
      `nmasslncmin`, `cons_nmass`, `cons_nmasslncmin` -- was read back with the
      thickness weight. `nmass` closed to 1e-17 while `nmasslncmin`, the same
      edit plus an unrelated one, appeared WORSE than legacy.
    * Then it was the substring test, which fixed those four and silently
      swallowed two more: `nmass_dry` and `nmass_dry_window` contain `nmass`
      and weight by a DRY mass, so both were inverted with the moist measure.

    Both bugs are the same bug -- a name being asked a question it cannot
    answer -- and both were silent, because a wrong weight still produces
    numbers. A substring test cannot fail; a lookup can, and an unknown arm now
    stops the read instead of guessing at it (owner review §9).
    """
    if not isinstance(algorithm, str):
        raise ValueError(
            f"number transfer metric: algorithm is {algorithm!r}, not a name; "
            f"the stream header is what carries it")
    try:
        known = NUMBER_TRANSFER_METRIC[algorithm]
    except KeyError:
        known = None
    if known is None:
        # FAIL CLOSED. The docstring said an unknown arm stops the read, and the
        # code then returned `declared` when the stream supplied one -- so any
        # name at all could walk past the registry by declaring a measure. The
        # registry is the closed world; a declaration is a CROSS-CHECK on it,
        # never a substitute for it (owner review 4.4).
        raise ValueError(
            f"number transfer metric: {algorithm!r} is not a registered arm"
            + (f" (the stream declares {declared!r}, which is not enough -- add "
               f"the arm to NUMBER_TRANSFER_METRIC)" if declared else "")
            + f". Known: {', '.join(sorted(NUMBER_TRANSFER_METRIC))}")
    if known is not None:
        # TWO SOURCES THAT MUST AGREE. `declared` is what the BUILD said about
        # itself (`G33N METRIC`); `known` is what this table says the name
        # means. Either alone can be stale -- the table was wrong about
        # `nmass_dry` for a week, and a driver cascade can be edited without
        # its table. Disagreement is a defect in one of them and must not be
        # resolved silently in favour of either.
        if declared is not None and declared != known:
            raise ValueError(
                f"number transfer metric: the stream declares {declared!r} for "
                f"{algorithm!r} and the table says {known!r}. One of the two "
                f"is stale; do not guess which.")
        return known


def number_layer_measure(metric, den, dz, qv=None, mdry0=None):
    """The per-level measure whose RATIO is the arm's transfer weight.

    `den`, `dz`, `qv` are per-level lists in the analyzer's order (0 = TOP);
    `mdry0` is the window-initial dry layer MASS, which already contains its
    own thickness and so is returned as given.
    """
    n = len(dz)
    if metric == "thickness":
        return list(dz)
    if metric == "moist_layer_mass":
        return [den[t] * dz[t] for t in range(n)]
    if metric == "current_dry_layer_mass":
        if qv is None:
            raise ValueError(f"{metric} needs this call's qv")
        return [den[t] / (1.0 + qv[t]) * dz[t] for t in range(n)]
    if metric == "window_dry_layer_mass":
        if mdry0 is None:
            raise ValueError(
                f"{metric} needs the WINDOW-INITIAL dry mass, which a single "
                f"call's record does not carry")
        return list(mdry0)
    raise ValueError(f"unknown number transfer metric {metric!r}")


def number_layer_density(metric, den, qv=None, dry=None):
    """The DENSITY half of the arm's measure, for the closed form

        R = sum_j a_j dz_j ( B_{j+1} A_j / A_{j+1} - B_j )

    which keeps the thickness separate and so needs `A` alone rather than the
    layer mass. Exact while the thickness the arm weighted by is the thickness
    the ledger measures with -- true under the harness's fixed forcing, where
    `delz` does not move across the window.
    """
    if metric == "thickness":
        return [1.0] * len(den)
    if metric == "moist_layer_mass":
        return list(den)
    if metric == "current_dry_layer_mass":
        if qv is None:
            raise ValueError(f"{metric} needs this call's qv")
        return [den[t] / (1.0 + qv[t]) for t in range(len(den))]
    if metric == "window_dry_layer_mass":
        if dry is None:
            raise ValueError(f"{metric} needs the window-initial dry density")
        return list(dry)
    raise ValueError(f"unknown number transfer metric {metric!r}")


def number_transfer_weights(metric, den, dz, qv=None, mdry0=None):
    """`w[0] = 0`; `w[t] = measure[t-1] / measure[t]`, the ratio the arm applied
    when it moved number from `t-1` into `t`."""
    m = number_layer_measure(metric, den, dz, qv, mdry0)
    return [0.0] + [m[t - 1] / m[t] for t in range(1, len(m))]


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
    # The SURFACE stage gets the same exact-universe contract as pre/post
    # (owner review §9.2): its rows feed surface-dependent closures, and a
    # missing cell used to come back as None -- a row silently skipped
    # rather than a stream refused. Measured across all 8945 published
    # loops: every one carries exactly cols x {k=-1}, one field set.
    srf = {(c, k) for l, c, k in call["surface"] if l == lp}
    if srf != {(c, -1) for c in cols}:
        raise StreamError(
            f"call {call['call_id']} loop {lp}: surface covers "
            f"{sorted(srf)}, the state covers columns {sorted(cols)} at "
            f"k=-1 -- a surface row that is not there cannot be skipped, "
            f"only refused")
    for c in sorted(cols):
        got_sf = set(call["surface"][(lp, c, -1)])
        if got_sf != set(SURFACE_REQUIRED):
            raise StreamError(
                f"call {call['call_id']} loop {lp} col {c}: surface carries "
                f"fields {sorted(got_sf)}, the protocol's surface stage is "
                f"exactly {sorted(SURFACE_REQUIRED)} -- a row that is present "
                f"but missing the quantity an analysis reads is a silent skip")
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
        # DUPLICATE facts, compared (owner review §9.1): the NFLUX group
        # restates the bottom cell's rho/delz, recorded independently in
        # outer_pre_sed at k = K-1. Measured across 4827 published flux
        # groups: exactly equal, every one -- so a group that disagrees is
        # two runs' records, not a rounding.
        if call["K"] is not None:
            pre = call["outer_pre_sed"].get((lp, c, call["K"] - 1))
            if pre is not None:
                for nm, key in (("nflux_den", "rho"), ("nflux_delz", "delz")):
                    if f[nm] != pre[key]:
                        raise StreamError(
                            f"call {call['call_id']} loop {lp} col {c}: "
                            f"{nm}={f[nm]!r} but the bottom cell's {key} is "
                            f"{pre[key]!r} -- one run records one atmosphere")
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
    declared_metric = None
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
        if (m := STREAM_METRIC.match(line)):
            # The SAME position rule the header reader applies. Without it a
            # stream whose only declaration came after the body was accepted
            # here and refused there -- the two readers disagreeing about one
            # stream, which is the shape of every protocol defect in this file.
            if cur is not None or seen:
                raise StreamError(
                    f"G33N METRIC {m.group(1)!r} appears after the first call; "
                    f"the measure a stream is read with is fixed before its "
                    f"body, not chosen after it")
            declared_metric = _one_metric(declared_metric, m.group(1), header)
            continue
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
                      "declared_metric": declared_metric,
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
        # ...and one SUB-CYCLE step: dtcld is a scalar of the run, recorded
        # once per column in every NFLUX group, so any two disagreeing is two
        # runs' records in one stream (owner review §6).
        dtclds = {f["nflux_dtcld"] for c in out for f in c["flux"].values()}
        if len(dtclds) > 1:
            raise StreamError(
                f"NFLUX records declare different sub-cycle steps "
                f"{sorted(dtclds)} -- one stream describes one problem")
        # ...and one LOOP UNIVERSE (owner review §4, sixth round): the
        # per-loop checks walk the loops a call HAPPENS to carry, so a call
        # whose records all sit on loop 2 -- loop 1 entirely absent -- was
        # complete for every loop anyone looked at, and two calls could run
        # disjoint loop sets. The kernel counts inner loops 1..L from one on
        # every external call, so the set is exactly {1..L}, the same L for
        # every call.
        loop_sets = {tuple(sorted(c["loops"])) for c in out}
        if len(loop_sets) > 1:
            raise StreamError(
                f"calls carry different inner-loop sets "
                f"{sorted(loop_sets)} -- one stream describes one problem")
        lset = loop_sets.pop()
        if lset != tuple(range(1, len(lset) + 1)):
            raise StreamError(
                f"inner loops {list(lset)} are not exactly 1..{len(lset)} -- "
                f"a loop the kernel counted is missing from the record")
        # ...and the sub-cycle step is the external step divided by the loop
        # count -- the kernel's own rule, restated in every NFLUX group and
        # never compared to the CALL_BEGIN delt it derives from (owner
        # review §9.1). Checked as the kernel COMPUTES it (Codex, round
        # two): the kernel rounds the quotient delt/L to the build's real
        # width, and re-multiplying that back does NOT recover delt for
        # ~9%% of (delt, L) pairs at f64 -- a product rule refused VALID
        # sub-cycle streams. So the recorded dtcld must equal the
        # correctly-rounded quotient at the stream's own word width, which
        # is exact by construction of the operation being checked -- and a
        # forged dtcld still differs from that quotient at the same width.
        if dtclds:
            d = next(iter(dtclds))
            dt = next(iter(dts))
            wfmt = ">d" if rb == 8 else ">f"
            q = struct.unpack(wfmt, struct.pack(wfmt, dt / len(lset)))[0]
            if struct.pack(wfmt, d) != struct.pack(wfmt, q):
                raise StreamError(
                    f"NFLUX dtcld {d} != delt {dt} / {len(lset)} loops "
                    f"(= {q} at this stream's width) -- the sub-cycle step "
                    f"is not this stream's")
        # Every split's tiles must cover THE DOMAIN exactly once: a gap or an
        # overlap between tiles is a decomposition that did not process the
        # state it claims to (owner P0-3).
        #
        # Anchored at COLUMN 1, in TILE-ID ORDER, and IDENTICAL across splits
        # (owner review §5). Sorting each split's segments by column range let
        # tile 1 cover 2..3 while tile 2 covered 1..1 -- spatially contiguous,
        # but the tile that OWNS a column differs from the one the ID says --
        # and comparing only each split's last column let split 1 tile as
        # (1..1)(2..3) beside split 2's (1..2)(3..3): every substep of one
        # member running a different decomposition. `ncmin` is set by a tile's
        # LAST column, so which tile ends where is the scientific content of
        # the decomposition, not a labelling. The real driver refuses these
        # before emitting, but this parser judges arbitrary artifacts and may
        # not re-assume the producer's checks.
        by_split = {}
        for sp in sorted({c["split"] for c in out}):
            row = sorted((c["tile"], c["cols"]) for c in out
                         if c["split"] == sp)
            lo = 1
            for t, (a, b) in row:
                if a != lo:
                    raise StreamError(
                        f"split {sp}: tile {t} covers columns {a}..{b} where "
                        f"the domain stands at column {lo} -- tiles must "
                        f"partition 1..W in tile-ID order")
                lo = b + 1
            by_split[sp] = tuple(cols for _t, cols in row)
        if len(set(by_split.values())) > 1:
            raise StreamError(
                f"splits decompose the domain differently: {by_split} -- one "
                f"stream, one decomposition, so every split must run the same "
                f"tile vector")
    # THE OPERATOR TRAVELS WITH THE CALL. The transfer weight depends on which
    # kernel ran, and a reader that assumes legacy reconstructs the wrong `b`
    # for any other arm -- measured on Arm N, which looked unchanged until the
    # header reached here.
    # `G33N METRIC` follows STREAM_BEGIN, so the header dict built at the
    # header record cannot already hold it. Read the loop's own value, and set
    # it on EVERY call -- the first version of this line sat outside the loop
    # and reached only the last one.
    for c in out:
        c["algorithm"] = header["algorithm"]
        c["declared_metric"] = declared_metric
    return out


def validated_run_identity(text: str, expected_width: int | None = None,
                           expected_levels: int | None = None,
                           with_calls: bool = False):
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
    # The decomposition is part of the identity (owner review §5): `calls()`
    # has proven every split runs the same tile vector, so split 1's row IS
    # the stream's. `ncmin` is set by a tile's last column, which makes the
    # ranges scientific content, not bookkeeping. algorithm/delt/dtcld are
    # identity facts too (owner review §6): each is proven single for the
    # stream, so a caller holding a second protocol's copy can compare.
    row = sorted((c["tile"], c["cols"]) for c in parsed if c["split"] == 1)
    tiles = tuple(cols for _t, cols in row)
    dtclds = {f["nflux_dtcld"] for c in parsed for f in c["flux"].values()}
    rid = {"nsplit": hdr["nsplit"], "carry": hdr["mode"],
           "rho": hdr["rho_profile"], "width": width, "levels": levels,
           "ntile": hdr["ntile"], "tile_ranges": tiles,
           "tile_sizes": tuple(b - a + 1 for a, b in tiles),
           "algorithm": hdr["algorithm"],
           # THE MEASURE IS IDENTITY. Two streams with the same arm, splits and
           # timestep but different transfer measures were the same run to this
           # function -- and the measure decides which ledger a residual closes,
           # so they are not the same run at all (owner review 4.3). Resolved
           # through the registry, so an unregistered arm cannot reach here.
           "number_transfer_metric": number_transfer_metric(
               hdr["algorithm"], hdr.get("number_transfer_metric")),
           "delt": parsed[0]["delt"],
           "dtcld": dtclds.pop() if dtclds else None,
           # Proven exactly {1..L}, one L per stream, by `calls()` above --
           # so a caller holding the window header's `loops` can compare.
           "loops": len(parsed[0]["loops"])}
    # `with_calls` hands back the strict parse the identity was derived FROM,
    # so a caller that also needs the records (the same-run forcing check)
    # does not parse a many-megabyte stream twice. Same reader, same parse.
    return (rid, parsed) if with_calls else rid


def _one_metric(seen, value, head):
    """`G33N METRIC` exactly once, and only between the header and the first call.

    Three ways this was loose (owner review 4.1, 4.2):

    * a second declaration silently replaced the first, so a stream could
      change the measure its own body is read with;
    * a declaration BEFORE `STREAM_BEGIN` was accepted, though the parser
      requires the header to be the first G33N record;
    * a declaration after the body was accepted and applied retroactively to
      calls already parsed.

    It names the run's transfer measure, so any of those changes which ledger a
    residual is judged against. Fail closed.
    """
    if seen is not None:
        raise StreamError(
            f"stream declares G33N METRIC twice, {seen!r} then {value!r}; "
            f"the measure a stream is read with cannot change inside it")
    if head is None:
        raise StreamError(
            f"G33N METRIC {value!r} appears before STREAM_BEGIN; the header "
            f"must be the first G33N record and the metric follows it")
    if value not in set(NUMBER_TRANSFER_METRIC.values()):
        raise StreamError(
            f"G33N METRIC {value!r} is not a measure this analyzer can build "
            f"weights from; known: {sorted(set(NUMBER_TRANSFER_METRIC.values()))}")
    return value


def stream_header(stream: str) -> dict:
    """What the stream DECLARES about the run that produced it.

    `calls()` reads this to validate the body and then throws it away, so a
    caller wanting to ask "which run is this?" had to re-derive it from a
    filename or trust a manifest field. Those are the two things that cannot
    check each other (owner priority 5).
    """
    # THE METRIC FOLLOWS THE HEADER, so returning at STREAM_BEGIN cannot see it.
    # An earlier version did exactly that, and the field it left out is the one
    # that decides WHICH LEDGER a residual is read against -- two runs differing
    # only in it had the same identity (owner review 4.3).
    head = None
    declared_metric = None
    in_body = False
    for line in stream.splitlines():
        if (m := STREAM_METRIC.match(line)):
            # BREAKING AT THE FIRST CALL made this reader IGNORE a metric
            # declared after the body while `calls()` refused it -- so the two
            # readers disagreed about the same stream, and the one that decides
            # run identity was the permissive one. Scan to the end and refuse.
            #
            # The early return is therefore gone, and the cost was measured
            # rather than assumed: 3.3 ms over 10 968 lines, 5.9 ms over 43 869,
            # and `validated_run_identity` is the only caller -- once per
            # stream. Not worth a two-pass offset trick to get back.
            if in_body:
                raise StreamError(
                    f"G33N METRIC {m.group(1)!r} appears after the first call; "
                    f"the measure a stream is read with is fixed before its "
                    f"body, not chosen after it")
            declared_metric = _one_metric(declared_metric, m.group(1), head)
            continue
        if (m := STREAM_BEGIN.match(line)):
            (schema, nsplit, ntile, expected, algo, mode, feats,
             rho_profile) = m.groups()
            head = {"schema": int(schema), "nsplit": int(nsplit),
                    "ntile": int(ntile), "expected_calls": int(expected),
                    "algorithm": algo, "mode": mode,
                    "features": set(feats.split(",")), "rho_profile": rho_profile}
            continue
        if head is not None and CALL_BEGIN.match(line):
            in_body = True
    if head is None:
        raise StreamError("stream carries no G33N STREAM_BEGIN header")
    head["number_transfer_metric"] = declared_metric
    return head


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
    Valid only for a single substep with matched interface transfers; separate
    arrival caps break this recovery assumption. See the module docstring.
    """
    a = [x[0] - x_post[0]]
    for t in range(1, len(x)):
        a.append(x[t] - x_post[t] + a[t - 1] * w[t])
    return a


def column(call, col, species, mdry0=None):
    """One (call, column, species): measured residual and predicted creation, or
    None where the sub-step count makes the transfers unrecoverable.

    `mdry0` is the window-initial dry layer mass, per level in this column's
    order, required only by the arm that weights by it -- see
    `number_transfer_metric`. Without it that arm returns None rather than a
    reading taken with the wrong measure.
    """
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
    if species in ("nr", "ni"):
        # THE ARM'S OWN MEASURE. The mass species keep their per-species
        # default; only the number transfer is what the N-family edits change.
        metric = number_transfer_metric(call.get("algorithm"),
                                        call.get("declared_metric"))
        if metric == "window_dry_layer_mass" and mdry0 is None:
            # Honest refusal, on the same footing as mstep > 1: this arm's
            # weight is the WINDOW-INITIAL dry mass and one call's record does
            # not carry it. Inverting with any other measure would return
            # transfers that did not happen.
            return None
        qv = [pre[(lp, col, k)]["qv"] for k in ks] if "qv" in pre[(lp, col, ks[0])] else None
        w = number_transfer_weights(metric, den, dz, qv, mdry0)
    else:
        w = [0.0] + [dz[t - 1] / dz[t] * (den[t - 1] / den[t] if carries_density else 1.0)
                     for t in range(1, len(ks))]
    a = transfers(x, x1, w)

    n0w = sum(den[t] * dz[t] * x[t] for t in range(len(ks)))
    n1w = sum(den[t] * dz[t] * x1[t] for t in range(len(ks)))
    surface = den[-1] * dz[-1] * a[-1]
    residual = (n1w - n0w) + surface
    # Conditional density-contrast identity for the recovered transfers:
    #
    #     sum over interfaces of [den(lower) - den(upper)] * delz(upper) * b
    #
    # This telescopes by construction and cannot validate the matched-transfer
    # assumption. With independently capped arrivals, use CAPIN/TOPOUT instead.
    #
    # Only the INTERFACES. `a[-1]` leaves the column at the surface and is
    # the flux the residual is measured against, not a term in it.
    predicted = sum((den[t] - den[t - 1]) * dz[t - 1] * a[t - 1]
                    for t in range(1, len(ks)))
    out = {"start": n0w, "residual": residual, "surface": surface,
           "relative": residual / n0w if n0w else 0.0, "final": 0.0,
           "surface_uncapped": 0.0,
           "predicted_residual": predicted,
           # `None` where there is nothing to divide by. A uniform profile
           # drives both sides to ROUNDOFF, not to a clean zero -- measured,
           # -0.0 against 0.0 with a relative residual of 5e-17 -- so the
           # guard is a magnitude, not `if residual`. A ratio taken there
           # says nothing except which way the last bit fell.
           "predicted_over_measured": (
               predicted / residual
               if abs(residual) > 1e-12 * (abs(n0w) or 1.0) else None)}
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


def surface_cap_binds(call, col, species):
    """Did the SURFACE cap bind -- asked without recovering a transfer.

    The transport-only closure needs its `out` term to be the removal that
    actually happened. Where the `min` bound at the bottom cell, the emitted
    accumulator overstates it and the call measures the cap rather than the
    transport. That is the ONE question the guard asks; it is not the same as
    "did a cap bind anywhere", and conflating the two throws away every row
    with an interior cap for a reason the arithmetic never had.

    `G33F CAPIN` at the bottom cell carries that cell's own outflow per
    sub-step, so summing it gives what left, independent of `mstep`. Against
    the recovered-transfer test this agrees on 218 of 220 rows where both can
    see (`g33_fixture_multisubcycle_v1`, nsplit 3 and 24); the two exceptions
    are at 2.7e-11 relative and at an absolute scale of 1e-10, which is a
    tolerance comparing near-nothing, not a disagreement about capping.

    Returns None where the stream carries no CAPIN records for the chain: a
    guard that cannot see must not answer "no".
    """
    chain = SPECIES[species][0]
    ks = [k for (_l, _n, c, ch, k) in call["capin"] if c == col and ch == chain]
    if not ks:
        return None
    bottom = max(ks)
    number = species.startswith("n")
    left = sum((v[2] if number else v[0])
               for (_l, _n, c, ch, k), v in call["capin"].items()
               if c == col and ch == chain and k == bottom)
    f = call["flux"].get((single_loop(call), col), {})
    acc = EMITTED[species][0]
    raw = f.get(acc, call["surface"].get((single_loop(call), col, -1), {}).get(acc))
    if raw is None or "nflux_dtcld" not in f:
        return None
    uncapped = raw * f["nflux_dtcld"]
    return abs(left - uncapped) > 1e-6 * abs(uncapped or 1.0)


def interior_cap_binds(call, col, species):
    """Did the cap bind at an INTERIOR interface? Reported, never excluded.

    Where it does, the residual is still the operator's own behaviour -- the
    capped transfer is what ran -- but it is no longer transport alone, so the
    row is labelled rather than dropped. Measured on the multisubcycle fixture
    the interior cap binds hard: 214 mass and 202 number interfaces, smallest
    departure 2.6e-03 relative, median 76%.
    """
    chain = SPECIES[species][0]
    rows = [(k, v) for (_l, _n, c, ch, k), v in call["capin"].items()
            if c == col and ch == chain]
    if not rows:
        return None
    bottom = max(k for k, _v in rows)
    number = species.startswith("n")
    return any((v[2] != v[3]) if number else (v[0] != v[1])
               for k, v in rows if k != bottom)


def closure_report(stream: str, *, multistep: bool = True) -> dict:
    """{species: {col: ...}} plus the printed table.

    `multistep=False` restores the mstep == 1 restriction the guard used to
    impose by accident, so a figure published under it reproduces as stated.
    """
    acc = {}
    for call in calls(stream):
        lp = single_loop(call)
        for col in sorted({c for _, c, _ in call["outer_pre_sed"]}):
            for sp in EMITTED:
                mstep = call["mstep"].get((lp, SPECIES[sp][0], col))
                # The caps are per SPECIES, so the check has to be too. At
                # mstep == 1 this is the recovered-transfer test, UNCHANGED, so
                # every figure published under it is reproduced bit for bit.
                # Above it there is no transfer to recover, and the same
                # question is put to CAPIN instead -- which is what makes the
                # path that advertises "no recursion" finally live up to it.
                if sp in SPECIES and SPECIES[sp][1] is not None:
                    c = column(call, col, sp)
                    if c is not None:
                        if abs(c["surface"] - c["surface_uncapped"]) > \
                                1e-6 * abs(c["surface_uncapped"] or 1.0):
                            continue
                    else:
                        if not multistep or surface_cap_binds(call, col, sp) \
                                is not False:
                            continue
                r = closure(call, col, sp)
                if r is None or r["start"] == 0 or r["out"] == 0:
                    continue
                d = acc.setdefault((sp, col), {"n": 0, "out": 0.0, "residual": 0.0,
                                               "mstep_max": 0, "interior_cap": 0})
                d["n"] += 1
                d["out"] += r["out"]
                d["residual"] += r["residual"]
                d["mstep_max"] = max(d["mstep_max"], mstep or 0)
                d["interior_cap"] += bool(interior_cap_binds(call, col, sp))
    print("\n  TRANSPORT-ONLY closure from EMITTED data alone (no recursion)")
    print("  The segment is both sedimentation sub-cycles and nothing else, so a")
    print("  sources-off fixture is not needed. qr is a REAL control here.\n")
    print(f"  {'sp':>3} {'col':>4} {'calls':>6} {'mstep<=':>7} {'incap':>5} "
          f"{'surface out':>14} {'residual':>14} {'residual/out':>14}")
    for (sp, col), d in sorted(acc.items(), key=lambda kv: (kv[0][0][0] != "q", kv[0])):
        rel = d["residual"] / d["out"] if d["out"] else float("nan")
        print(f"  {sp:>3} {col:>4} {d['n']:>6} {d['mstep_max']:>7} "
              f"{d['interior_cap']:>5} {d['out']:14.5e} "
              f"{d['residual']:14.5e} {rel:13.4%}")
    print("\n  `incap` counts calls where the cap bound at an INTERIOR interface:"
          "\n  the row is the operator's own behaviour there, but it is no longer"
          "\n  transport alone. Labelled, not dropped.")
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
