#!/usr/bin/env python3
"""Departure against arrival, interface by interface (owner §14 priority-4).

The numbers this produces -- the cap explaining 100.00% of the ice mass residual,
binding at 39 of 255 interfaces, and the main chain's created/predicted ratio of
1.0000 -- were computed ad hoc and published from a document. There was no tool,
so nothing could recompute them and nothing could be digested into a bundle.

## The pairing

`G33F CAPIN` gives, for a cell at stream level `k`, its OWN outflow beside the
inflow it received from above. `G33F TOPOUT` gives the top cell's removal, which
CAPIN cannot: the top cell is updated outside the interior loop, so without it the
topmost interface is invisible.

For the interface between level `j-1` (above) and `j` (below):

    departure = own(j-1)      TOPOUT when j-1 == 0, else CAPIN's own
    arrival   = inflow(j)     CAPIN's inflow at j

Both are mixing ratios in their own cell's units -- the kernel adds `dq(i,k+1)`
straight into `qrs(i,k)` -- so under the column measure they weigh differently:

    delta = rho(j)*delz(j)*arrival - rho(j-1)*delz(j-1)*departure

which is signed the way the closure residual is: negative where the interface
destroys. The cap BINDS at an interface when departure != arrival, and that
difference is the P0-4b post-update-reservoir gap: `dq(i,k+1)` is written twice,
capped against the cell above PRE-update as its outflow and POST-update as the
inflow below.

For NUMBER the same pairing gives what the interface CREATES, which is compared
against the rho*dz-vs-dz prediction

    sum over interfaces of (rho(j) - rho(j-1)) * delz(j-1) * departure_n

on the same interfaces. Where the cap does not bind, the two must agree.

    python g33_cap_interface.py <driver---nflux> <nsplit> [out.json]
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import g33_matched_closure as mc  # noqa: E402
import g33_number_transport as nt  # noqa: E402


def interfaces(stream: str, basis: str = "operator") -> dict:
    """{(chain, col): {...}} -- the interface terms, and how often the cap bound.

    Requires `capin` and `topout`; the strict parser has already checked their
    exact universes, so a level or sub-step missing here is not possible.
    """
    acc = {}
    for call in nt.calls(stream):
        for lp in sorted(call["loops"]):
            pre = call["outer_pre_sed"]
            for col in sorted({c for l, c, _ in pre if l == lp}):
                ks = sorted(k for l, c, k in pre if c == col and l == lp)
                rho = {k: mc._density(pre[(lp, col, k)], basis) for k in ks}
                dz = {k: pre[(lp, col, k)]["delz"] for k in ks}
                for chain in ("main", "ice"):
                    ms = call["mstep"].get((lp, chain, col))
                    if ms is None:
                        continue
                    d = acc.setdefault((chain, col), {
                        "mass_interface_term": 0.0,
                        # NET is what the closure residual compares to; GROSS and
                        # MAX say how much interface activity produced it. A
                        # column whose positive and negative terms cancel has a
                        # small net and is not quiet (owner P1-11.2).
                        "sum_abs_interface_term": 0.0,
                        "max_abs_interface_term": 0.0,
                        "number_created": 0.0,
                        "number_predicted": 0.0, "interfaces": 0,
                        # NAMED for what is compared (owner §10). `cap_bound`
                        # counted only the MASS departure/arrival mismatch, so a
                        # figure quoted as "cap-bound interfaces" silently meant
                        # the mass cap and not the number one. And exact
                        # inequality counts a roundoff-scale difference as a
                        # binding cap, which is why every count is reported
                        # beside its magnitude.
                        "mass_departure_arrival_differ": 0,
                        "number_departure_arrival_differ": 0,
                        "either_differ": 0,
                        "number_transported": 0.0})
                    for n in range(1, ms + 1):
                        # own(j) and inflow(j), assembled from the two families
                        top = call["topout"].get((lp, n, col, chain, 0))
                        if top is None:
                            continue
                        own = {0: top}
                        inflow = {}
                        for j in ks[1:]:
                            cap = call["capin"].get((lp, n, col, chain, j))
                            if cap is None:
                                continue
                            oq, iq, on, ino = cap
                            own[j], inflow[j] = (oq, on), (iq, ino)
                        for j in ks[1:]:
                            if j not in inflow or (j - 1) not in own:
                                continue
                            dq_out, dn_out = own[j - 1]
                            dq_in, dn_in = inflow[j]
                            wa, wb = rho[j] * dz[j], rho[j - 1] * dz[j - 1]
                            term = wa * dq_in - wb * dq_out
                            d["mass_interface_term"] += term
                            d["sum_abs_interface_term"] += abs(term)
                            d["max_abs_interface_term"] = max(
                                d["max_abs_interface_term"], abs(term))
                            d["number_created"] += wa * dn_in - wb * dn_out
                            # what the measure mismatch alone predicts, on this
                            # same interface and the same emitted transfer
                            d["number_predicted"] += ((rho[j] - rho[j - 1])
                                                      * dz[j - 1] * dn_out)
                            # Total number crossing ANY interface, in column
                            # measure -- the throughput the residual should be
                            # compared against (owner §11). The surface transfer
                            # alone is what R/F already uses.
                            d["number_transported"] += abs(wb * dn_out)
                            d["interfaces"] += 1
                            md, nd = dq_out != dq_in, dn_out != dn_in
                            d["mass_departure_arrival_differ"] += int(md)
                            d["number_departure_arrival_differ"] += int(nd)
                            d["either_differ"] += int(md or nd)
    return acc


def analysis(stream: str) -> dict:
    """The interface table beside the matched closure it is meant to explain."""
    closure, iface = mc.analysis(stream), interfaces(stream)
    rows = {}
    for (chain, col), d in sorted(iface.items()):
        mass = closure.get(f"{chain}/{mc.CHAIN[chain][0]}/{col}")
        resid = mass["residual"] if mass else None
        rows[f"{chain}/{col}"] = {
            **d,
            "mass_residual": resid,
            # How much of the closure's mass residual the interface term is.
            # `null` rather than a division when there is no residual to explain.
            "explained": (d["mass_interface_term"] / resid
                          if resid not in (None, 0.0) else None),
            "created_over_predicted": (d["number_created"] / d["number_predicted"]
                                       if d["number_predicted"] else None),
        }
    # Split BY CHAIN, and beside the magnitude. A bare count said "39 of 255,
    # all in the ice chain"; the main chain in fact differs at 23 interfaces too,
    # but for a total interface term of 2.7e-11 against ice's 8.6e-03. Counting
    # without the magnitude made a roundoff-scale difference and a
    # residual-dominating one the same event.
    by_chain = {}
    for (chain, col), d in iface.items():
        c = by_chain.setdefault(chain, {
            "mass_departure_arrival_differ": 0,
            "number_departure_arrival_differ": 0, "either_differ": 0,
            "interfaces": 0, "net_interface_term": 0.0,
            "sum_abs_interface_term": 0.0, "max_abs_interface_term": 0.0})
        for k in ("mass_departure_arrival_differ",
                  "number_departure_arrival_differ", "either_differ",
                  "interfaces"):
            c[k] += d[k]
        # abs(net-per-column) UNDERSTATES activity when terms cancel inside a
        # column; the gross sum is accumulated per interface instead.
        c["net_interface_term"] += d["mass_interface_term"]
        c["sum_abs_interface_term"] += d["sum_abs_interface_term"]
        c["max_abs_interface_term"] = max(c["max_abs_interface_term"],
                                          d["max_abs_interface_term"])
    return {"rows": rows, "by_chain": by_chain,
            "mass_departure_arrival_differ":
                sum(d["mass_departure_arrival_differ"] for d in iface.values()),
            "number_departure_arrival_differ":
                sum(d["number_departure_arrival_differ"] for d in iface.values()),
            "either_differ": sum(d["either_differ"] for d in iface.values()),
            "total_interfaces": sum(d["interfaces"] for d in iface.values())}


def report(stream: str) -> None:
    a = analysis(stream)
    print("  Departure vs arrival, per interface. The cap binds where they differ.\n")
    print(f"  {'row':10} {'mass residual':>14} {'interface term':>15} "
          f"{'explained':>10} {'created/predicted':>18} {'cap':>8}")
    for k, r in a["rows"].items():
        ex = f"{100*r['explained']:.2f}%" if r["explained"] is not None else "-"
        cp = f"{r['created_over_predicted']:.4f}" \
            if r["created_over_predicted"] is not None else "-"
        print(f"  {k:10} {r['mass_residual']:14.6e} {r['mass_interface_term']:15.6e} "
              f"{ex:>10} {cp:>18} "
              f"{r['mass_departure_arrival_differ']:3}m/"
              f"{r['number_departure_arrival_differ']:<3}n")
    print(f"\n  Departure differs from arrival, of {a['total_interfaces']} "
          f"interfaces: mass at {a['mass_departure_arrival_differ']}, number at "
          f"{a['number_departure_arrival_differ']},")
    print(f"  either at {a['either_differ']}. A single 'cap-bound' count "
          f"conflated the mass cap")
    print("  with the number one, and a count alone conflates a roundoff-scale")
    print("  difference with a residual-dominating one:")
    for ch, c in sorted(a["by_chain"].items()):
        print(f"    {ch:5} mass {c['mass_departure_arrival_differ']:3} / number "
              f"{c['number_departure_arrival_differ']:3} of "
              f"{c['interfaces']:<4} net {c['net_interface_term']:+.3e} "
              f"gross {c['sum_abs_interface_term']:.3e} "
              f"max {c['max_abs_interface_term']:.3e}")


def main(argv) -> int:
    if not 2 <= len(argv) <= 3:
        print(__doc__)
        return 2
    r = subprocess.run([argv[0], argv[1], "rezero"], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"driver exited {r.returncode}\n{r.stderr[-2000:]}")
    report(r.stdout)
    if len(argv) == 3:
        Path(argv[2]).write_text(
            json.dumps(analysis(r.stdout), indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
