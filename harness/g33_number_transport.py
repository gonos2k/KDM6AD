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

CALL_BEGIN = re.compile(r"^G33N CALL_BEGIN (\d+) (\d+) (\d+) ([0-9A-F]{8})$")
CALL_END = re.compile(r"^G33N CALL_END (\d+) (\d+)$")
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


def _blank(call_id=None, tile=None, delt=None):
    return {"call_id": call_id, "tile": tile, "delt": delt,
            "outer_pre_sed": {}, "outer_post_sed": {}, "surface": {},
            "flux": {}, "mstep": {}}


def _check(call):
    """A call is complete or it is not evidence (owner P0-4)."""
    cols = {c for c, _ in call["outer_pre_sed"]}
    if not cols:
        raise StreamError(f"call {call['call_id']}: no pre-sed state")
    if {c for c, _ in call["outer_post_sed"]} != cols:
        raise StreamError(f"call {call['call_id']}: post-sed covers different columns")
    if set(call["flux"]) != cols:
        raise StreamError(
            f"call {call['call_id']}: NFLUX covers {sorted(call['flux'])}, "
            f"state covers {sorted(cols)}")
    for c, f in call["flux"].items():
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
        got = {c for ch, c in call["mstep"] if ch == chain}
        if got != cols:
            raise StreamError(f"call {call['call_id']}: {chain} sub-step counts "
                              f"cover {sorted(got)}, state covers {sorted(cols)}")


def calls(stream: str):
    """One validated dict per EXTERNAL kernel call.

    Bracketed by the driver's `G33N CALL_BEGIN/END`, not inferred from record
    order: the kernel's own `loop` resets to 1 every call, so a reader keying on
    it collapses every call onto the last, and a truncated stream or a changed
    call count is silently re-attributed instead of refused.
    """
    cur, expect = None, 1
    for line in stream.splitlines():
        if (m := CALL_BEGIN.match(line)):
            if cur is not None:
                raise StreamError(f"call {cur['call_id']} never ended")
            cid = int(m.group(1))
            if cid != expect:
                raise StreamError(f"call ids jump: expected {expect}, got {cid}")
            cur = _blank(cid, int(m.group(2)), _f32(m.group(4)))
            continue
        if (m := CALL_END.match(line)):
            if cur is None or int(m.group(1)) != cur["call_id"]:
                raise StreamError(f"CALL_END {m.group(1)} without a matching begin")
            _check(cur)
            yield cur
            cur, expect = None, expect + 1
            continue
        if cur is None:
            continue                      # records outside any call: not ours
        if (m := STAGE.match(line)):
            stage, field, col, k, hexv = m.groups()
            cur[stage].setdefault((int(col), int(k)), {})[field] = _f32(hexv)
        elif (m := MSTEP.match(line)):
            cur["mstep"][("main", int(m.group(1)))] = int(m.group(2), 16)
        elif (m := MSTEPI.match(line)):
            cur["mstep"][("ice", int(m.group(1)))] = int(m.group(2), 16)
        elif (m := NFLUX.match(line)):
            col, field, hexv = m.groups()
            cur["flux"].setdefault(int(col), {})[field] = _f32(hexv)
    if cur is not None:
        raise StreamError(f"stream ends inside call {cur['call_id']}")


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
    if call["mstep"].get((chain, col)) != 1:
        return None
    pre, post = call["outer_pre_sed"], call["outer_post_sed"]
    ks = sorted(k for c, k in pre if c == col)              # 0 = TOP
    den = [pre[(col, k)]["rho"] for k in ks]
    dz = [pre[(col, k)]["delz"] for k in ks]
    x = [pre[(col, k)][species] for k in ks]
    x1 = [post[(col, k)][species] for k in ks]
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
        f = call["flux"][col]
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
    pre, post, srf = call["outer_pre_sed"], call["outer_post_sed"], call["surface"]
    f = call["flux"].get(col, {})
    ks = sorted(k for c, k in pre if c == col)
    den = [pre[(col, k)]["rho"] for k in ks]
    dz = [pre[(col, k)]["delz"] for k in ks]
    x0 = sum(den[t] * dz[t] * pre[(col, ks[t])][species] for t in range(len(ks)))
    x1 = sum(den[t] * dz[t] * post[(col, ks[t])][species] for t in range(len(ks)))
    raw = f.get(acc, srf.get((col, -1), {}).get(acc))
    if raw is None:
        return None
    # falln is [# kg-1 s-1] so it needs den; fall is [kg m-3 s-1] so it does not.
    out = raw * dz[-1] * f["nflux_dtcld"] * (den[-1] if is_number else 1.0)
    return {"start": x0, "out": out, "residual": (x1 - x0) + out}


def closure_report(stream: str) -> dict:
    """{species: {col: ...}} plus the printed table."""
    acc = {}
    for call in calls(stream):
        for col in sorted({c for c, _ in call["outer_pre_sed"]}):
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
        for col in sorted({c for c, _ in call["outer_pre_sed"]}):
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
    stream = subprocess.run([argv[0], argv[1], "rezero"], capture_output=True,
                            text=True).stdout
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
