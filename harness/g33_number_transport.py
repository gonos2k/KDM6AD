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

import re
import struct
import subprocess
import sys

STAGE = re.compile(r"^G33F STAGE \d+ \S+ (outer_pre_sed|outer_post_sed) 0 "
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


def _blank():
    return {"outer_pre_sed": {}, "outer_post_sed": {}, "flux": {}, "mstep": {}}


def calls(stream: str):
    """One dict per kernel call.

    Sequential, NOT keyed by the emitted `loop`: that is the inner cloud-subcycle
    index and resets to 1 on every call, so keying by it would collapse every
    call onto the last one.
    """
    cur = _blank()
    for line in stream.splitlines():
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
            if (field == "nflux_dtcld" and cur["outer_post_sed"]
                    and len(cur["flux"]) == len({c for c, _ in cur["outer_pre_sed"]})):
                yield cur
                cur = _blank()
    if cur["outer_post_sed"]:
        yield cur


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


def main(argv) -> int:
    if len(argv) != 2:
        print(__doc__)
        print("usage: g33_number_transport.py <driver-built-with---nflux> <nsplit>")
        return 2
    report(subprocess.run([argv[0], argv[1], "rezero"], capture_output=True,
                          text=True).stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
