#!/usr/bin/env python3
"""Matched mass/number closure on ONE chain, ONE call set (owner §5.2).

The earlier closure compared `qr` on the MAIN chain over 1-3 calls against `ni`
on the ICE chain over 95, using the UNCAPPED `fall`/`falln` accumulators, and
excluded any call where a cap bound -- detected by an endpoint recursion that
only works at `mstep == 1`. It supported the defect but was not a controlled
contrast.

The overlay now emits the ACTUAL capped bottom-cell transfers per sub-step,

    G33F XFER <loop> <n> <col> <main|ice> f32 <dq> <dn>

from the same statement pair the kernel uses, so for each chain:

    R_q = [W(post) - W(pre)] + sum_n den_bot*delz_bot*dq
    R_n = [N(post) - N(pre)] + sum_n den_bot*delz_bot*dn

are formed on the SAME call, the SAME chain, and the SAME cap state -- and
`mstep > 1` is admissible, because nothing is reconstructed.

`main` carries qr/nr, `ice` carries qi/ni (F:1179-1180).
"""
from __future__ import annotations

import re
import struct
import subprocess
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import g33_number_transport as nt  # noqa: E402

XFER = re.compile(r"^G33F XFER (\d+) (\d+) (\d+) (main|ice) f32 "
                  r"([0-9A-F]{8}) ([0-9A-F]{8})$")

#: chain -> (mass field, number field) as the kernel's two sub-cycles carry them.
CHAIN = {"main": ("qr", "nr"), "ice": ("qi", "ni")}


def _f32(h: str) -> float:
    return struct.unpack(">f", bytes.fromhex(h))[0]


def transfers(stream: str) -> dict:
    """{(call_index, loop, col, chain): (sum dq, sum dn)} over the sub-steps.

    Summed over `n` because the bottom cell exports once per sub-step and the
    segment budget spans all of them. Keyed by the call's ordinal so it can be
    joined to the parsed calls without re-deriving anything.
    """
    out, idx = {}, 0
    for line in stream.splitlines():
        if line.startswith("G33N CALL_BEGIN"):
            idx += 1
        elif (m := XFER.match(line)):
            loop, _n, col, chain, dq, dn = m.groups()
            k = (idx, int(loop), int(col), chain)
            a, b = out.get(k, (0.0, 0.0))
            out[k] = (a + _f32(dq), b + _f32(dn))
    return out


def closures(stream: str) -> dict:
    """{(chain, species, col): {'out':…, 'residual':…, 'calls':…}}."""
    xf = transfers(stream)
    acc = {}
    for i, call in enumerate(nt.calls(stream), start=1):
        for lp in sorted(call["loops"]):
            pre, post = call["outer_pre_sed"], call["outer_post_sed"]
            for col in sorted({c for l, c, _ in pre if l == lp}):
                ks = sorted(k for l, c, k in pre if c == col and l == lp)
                den = [pre[(lp, col, k)]["rho"] for k in ks]
                dz = [pre[(lp, col, k)]["delz"] for k in ks]
                w = den[-1] * dz[-1]            # bottom-cell rho*dz
                for chain, (mass, num) in CHAIN.items():
                    if (i, lp, col, chain) not in xf:
                        continue
                    dq, dn = xf[(i, lp, col, chain)]
                    for species, transfer in ((mass, dq), (num, dn)):
                        x0 = sum(den[t] * dz[t] * pre[(lp, col, ks[t])][species]
                                 for t in range(len(ks)))
                        x1 = sum(den[t] * dz[t] * post[(lp, col, ks[t])][species]
                                 for t in range(len(ks)))
                        d = acc.setdefault((chain, species, col),
                                           {"out": 0.0, "residual": 0.0,
                                            "start": 0.0, "calls": 0})
                        d["out"] += w * transfer
                        d["residual"] += (x1 - x0) + w * transfer
                        d["start"] += x0
                        d["calls"] += 1
    return acc


def report(stream: str) -> None:
    acc = closures(stream)
    print("  MATCHED closure — same chain, same calls, actual capped transfers")
    print("  mstep is NOT restricted: nothing is reconstructed from endpoints.\n")
    print(f"  {'chain':>5} {'sp':>3} {'col':>3} {'calls':>6} {'surface out':>14} "
          f"{'residual':>14} {'resid/out':>11}")
    for (chain, sp, col), d in sorted(acc.items()):
        if d["out"] == 0:
            continue
        print(f"  {chain:>5} {sp:>3} {col:>3} {d['calls']:>6} {d['out']:14.5e} "
              f"{d['residual']:14.5e} {d['residual']/d['out']:10.4%}")
    print("\n  A matched pair is the two rows sharing a chain and a column:")
    print("  the mass row is the CONTROL for the number row beside it. If the mass")
    print("  row does not close, the accounting for that chain is missing a term")
    print("  and NEITHER row of the pair is evidence.")
    for (chain, sp, col), d in sorted(acc.items()):
        if sp.startswith("q") and d["out"] and abs(d["residual"] / d["out"]) > 1e-3:
            print(f"    !! {chain}/{sp} col {col}: mass control fails at "
                  f"{d['residual']/d['out']:.2%} — the {chain} rows are not usable")


def main(argv) -> int:
    if len(argv) != 2:
        print(__doc__)
        print("usage: g33_matched_closure.py <driver-built-with---nflux> <nsplit>")
        return 2
    r = subprocess.run([argv[0], argv[1], "rezero"], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"driver exited {r.returncode}\n{r.stderr[-2000:]}")
    report(r.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
