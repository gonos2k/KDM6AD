#!/usr/bin/env python3
"""Mean particle mass and column number (owner review §7).

Water-mass closure alone does not make a conservative variant complete. The
interface moves MASS with a rho*dz measure and NUMBER with the legacy dz-only one
(sedimentation_conservative.cpp:91-92 against :109), so §7's arithmetic predicts a
transferred population's mean particle mass shifts by the density ratio:

    dq_l / dn_l = (rho_u / rho_l) (dq_u / dn_u)

Measured against the LEGACY run at the same cell, not against the same run's start:
over 300 s of full microphysics q and n change independently through condensation,
nucleation and aggregation, so a changed q/n within one run is ordinary physics.
The interface is the only difference between the two runs, and the TOP level has no
inflow from above, so its ratio of exactly 1 is the control.

Column number is reported as a CHANGE, not a residual: the surface number flux is
not emitted -- only mass precipitation is -- and calling it a residual would claim
a balance whose outflow term does not exist here.

Reads the same G33R streams as g33_refine_analyze.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g33_refine_analyze as ra   # noqa: E402

#: (mass, number) pairs the kernel carries as a two-moment species.
PAIRS = (("qr", "nr"), ("qi", "ni"), ("qc", "nc"))

#: Below this a species is absent and q/n is meaningless, not extreme.
_EPS = 1.0e-12


def mean_particle_mass(run: dict, cls: str = "state") -> dict:
    """{(species, col, k): q/n} where both moments are present."""
    out = {}
    for q, n in PAIRS:
        for key in (k for k in run if k[0] == cls and k[1] == q):
            _, _, c, k = key
            qv, nv = run[key], run[(cls, n, c, k)]
            if qv > _EPS and nv > _EPS:
                out[(q, c, k)] = qv / nv
    return out


def column_number(run: dict, cls: str = "state") -> dict:
    """{(species, col): sum_k rho_k dz_k n_k}, or {} without forcing."""
    if not any(k[0] == "forcing" for k in run):
        return {}
    cells = {(k[2], k[3]) for k in run if k[0] == "state"}
    out = {}
    for c in sorted({x for x, _ in cells}):
        ks = [k for cc, k in cells if cc == c]
        for _, n in PAIRS:
            out[(n, c)] = sum(
                run[("forcing", "rho", c, k)] * run[("forcing", "delz", c, k)]
                * run[(cls, n, c, k)] for k in ks)
    return out


def compare(legacy: Path, conservative: Path) -> None:
    """Mean particle mass and column number, conservative against legacy."""
    L, C = ra.read(legacy), ra.read(conservative)
    # NOT ra.require_same_universe: that also demands one algorithm, which is right
    # for members of a refinement chain and wrong here, where comparing the two
    # variants is the point. The record universe must still match.
    kl = {k for k in L if k[0] != "meta"}
    kc = {k for k in C if k[0] != "meta"}
    if kl != kc:
        raise ra.RefineError(f"{legacy.name} and {conservative.name} carry "
                             f"different records ({len(kl ^ kc)} differ)")
    ml, mc = mean_particle_mass(L), mean_particle_mass(C)

    print(f"\n=== {conservative.name} vs legacy ===")
    print("\n  mean particle mass q/n, conservative / legacy   "
          "(§7 predicts rho_u/rho_l per transfer)")
    for key in sorted(set(ml) & set(mc)):
        sp, c, k = key
        top = " <== top level, no inflow" if k == max(
            x[2] for x in ml if x[0] == sp and x[1] == c) else ""
        print(f"    {sp:3} col{c} k{k}   {mc[key] / ml[key]:9.4f}{top}")

    nl, nc = column_number(L), column_number(C)
    if nl:
        print("\n  rho*dz column number, conservative / legacy   "
              "(CHANGE: the surface number flux is not emitted)")
        for key in sorted(nl):
            if nl[key]:
                print(f"    {key[0]:4} col{key[1]}   {nc[key] / nl[key]:9.4f}")


def main(argv) -> int:
    if len(argv) != 2:
        print(__doc__)
        print("usage: g33_number_budget.py <legacy-dir> <conservative-dir>")
        return 2
    a, b = Path(argv[0]), Path(argv[1])
    for p in sorted(a.glob("n*.txt")):
        q = b / p.name
        if q.exists():
            compare(p, q)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
