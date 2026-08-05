#!/usr/bin/env python3
"""Splitting a perturbed arm's residual into metric and trajectory (owner §7).

The density arms come out at −0.99 and +2.01 rather than exactly −1 and +2, and
that departure was once attributed to "density also changes the fall speed". It
was withdrawn: density also changes the next call's pre-sedimentation state, the
cap state, and every density-dependent rate, so naming fall speed picked one
candidate out of several without separating them.

What the departure IS, exactly, is

    R(rho') = sum_j drho'_j dz_j d_j(rho)              metric-only counterfactual
            + sum_j drho'_j dz_j [d_j(rho') - d_j(rho)]  trajectory response

The first term holds the TRANSFERS at their unperturbed values and moves only the
density gap -- so it is the pure metric scaling, and for `inverted` it is exactly
−R(rho) and for `x2` exactly 2R(rho), by construction of those profiles. The
second is everything the perturbation did to the run itself. Their sum is the
measured residual identically, so this is a decomposition and not a model.

Interfaces correspond one-to-one only when the arm leaves the SUB-STEP SCHEDULE
alone, which `uniform` and `x2` do and `inverted` does NOT: it drops column 3's
`mstep` from 3 to 2 in call 1, because density sets the fall speed and `mstep` is
derived from it. Where the schedule moves there is no interface correspondence
and the metric counterfactual is undefined, so that column is reported
`comparable: false` rather than zipped against unrelated interfaces.

(An earlier control claimed the schedule was identical in every arm. It merged
every call into one dict keyed by `(loop, chain, col)` -- identical across calls
-- so later calls overwrote earlier ones and it compared only the last call.)

    python g33_metric_trajectory.py <driver---nflux> <nsplit> [out.json]
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import g33_number_transport as nt  # noqa: E402

#: `offset+/-` shift every level by the same constant, so the GRADIENT is
#: untouched and only the absolute density moves. Since the residual depends on
#: (rho_below - rho_above), a constant cancels exactly -- which separates "the
#: gradient matters" from "the magnitude matters" far more directly than scaling
#: the contrast does (owner §7).
ARMS = ("as-is", "uniform", "inverted", "x2", "offset+", "offset-")


def interface_terms(stream: str, chain: str = "main") -> dict:
    """{col: [(drho, dz_above, dn_departure), ...]} in a deterministic order.

    `dn_departure` is the number that actually LEFT the cell above, taken from
    TOPOUT at the top interface and CAPIN's own-outflow below it -- the same
    pairing the cap-interface analysis uses.
    """
    rows = {}
    for call in nt.calls(stream):
        for lp in sorted(call["loops"]):
            pre = call["outer_pre_sed"]
            for col in sorted({c for l, c, _ in pre if l == lp}):
                ks = sorted(k for l, c, k in pre if c == col and l == lp)
                rho = {k: pre[(lp, col, k)]["rho"] for k in ks}
                dz = {k: pre[(lp, col, k)]["delz"] for k in ks}
                ms = call["mstep"].get((lp, chain, col))
                if ms is None:
                    continue
                for n in range(1, ms + 1):
                    top = call["topout"].get((lp, n, col, chain, 0))
                    if top is None:
                        continue
                    own = {0: top[1]}
                    for j in ks[1:]:
                        cap = call["capin"].get((lp, n, col, chain, j))
                        if cap:
                            own[j] = cap[2]
                    for j in ks[1:]:
                        if (j - 1) not in own:
                            continue
                        rows.setdefault(col, []).append(
                            (rho[j] - rho[j - 1], dz[j - 1], own[j - 1]))
    return rows


def decompose(base: dict, arm: dict) -> dict:
    """{col: {metric, trajectory, actual, ...}} for one arm against the baseline.

    `metric` uses the ARM's density gap with the BASELINE transfer; `actual` uses
    both from the arm. Their difference is what the perturbation did to the run
    rather than to the measure.
    """
    out = {}
    for col, rows in sorted(arm.items()):
        b = base.get(col)
        if b is None or len(b) != len(rows):
            # A different interface count means the arm changed the SUB-STEP
            # SCHEDULE, so there is no one-to-one interface correspondence and
            # the metric counterfactual is undefined -- `inverted` does this in
            # column 3. Reported rather than forced onto a zip that would pair
            # unrelated interfaces.
            out[col] = {"comparable": False,
                        "reason": f"interface count {len(rows)} vs "
                                  f"{len(b) if b else 0} — the arm changed the "
                                  f"sub-step schedule, so interfaces do not "
                                  f"correspond"}
            continue
        metric = sum(dr * dz * bd for (dr, dz, _), (_, _, bd) in zip(rows, b))
        actual = sum(dr * dz * dn for dr, dz, dn in rows)
        baseline = sum(dr * dz * dn for dr, dz, dn in b)
        out[col] = {
            "comparable": True, "interfaces": len(rows),
            "baseline": baseline, "metric": metric, "actual": actual,
            "trajectory": actual - metric,
            "metric_over_baseline": metric / baseline if baseline else None,
            "actual_over_baseline": actual / baseline if baseline else None,
            # The trajectory response as a fraction of the METRIC term. This is
            # the number that answers "how large is the departure from exactly
            # -1 and +2", and it is a measurement rather than an attribution.
            # Normalising by (actual - baseline) instead would divide by the
            # whole change from the unperturbed arm -- about 2x baseline for
            # `inverted` -- and make a 1% departure read as 0.5%.
            "trajectory_over_metric": (abs((actual - metric) / metric)
                                       if metric else None),
        }
    return out


def analysis(driver: str, nsplit: int, chain: str = "main") -> dict:
    def run(arm):
        r = subprocess.run([driver, str(nsplit), "rezero", "3", arm],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"{arm}: driver exited {r.returncode}\n{r.stderr[-2000:]}")
        return interface_terms(r.stdout, chain)

    base = run("as-is")
    return {"chain": chain,
            "arms": {a: decompose(base, run(a)) for a in ARMS if a != "as-is"}}


def report(driver: str, nsplit: int) -> None:
    a = analysis(driver, nsplit)
    print("  The departure from -1 and +2, decomposed rather than attributed.\n")
    print("  metric    = arm's density gap x BASELINE transfer  (pure measure)")
    print("  trajectory = what the perturbation did to the run itself")
    print("  Their sum is the measured residual identically.\n")
    print(f"  {'arm':10} {'col':>3} {'metric/base':>12} {'actual/base':>12} "
          f"{'trajectory':>13} {'traj/metric':>12}")
    for arm, cols in a["arms"].items():
        for col, r in cols.items():
            if not r["comparable"]:
                print(f"  {arm:10} {col:>3}  {r['reason']}")
                continue
            sh = (f"{100*r['trajectory_over_metric']:11.2f}%"
                  if r["trajectory_over_metric"] is not None else "  -")
            print(f"  {arm:10} {col:>3} {r['metric_over_baseline']:12.4f} "
                  f"{r['actual_over_baseline']:12.4f} {r['trajectory']:13.5e} {sh}")
    print("\n  metric/base is EXACT by construction: 0 (uniform), -1 (inverted),")
    print("  +2 (x2), and +1 for the OFFSET arms — a constant added to every level")
    print("  cancels out of (rho_below - rho_above) identically. So an offset")
    print("  changes the magnitude without touching the metric term, and whatever")
    print("  the residual does there is trajectory, not measure.")


def main(argv) -> int:
    if not 2 <= len(argv) <= 3:
        print(__doc__)
        return 2
    report(argv[0], int(argv[1]))
    if len(argv) == 3:
        Path(argv[2]).write_text(
            json.dumps(analysis(argv[0], int(argv[1])), indent=2,
                       sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
