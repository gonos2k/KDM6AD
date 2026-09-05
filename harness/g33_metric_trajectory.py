#!/usr/bin/env python3
"""Splitting a perturbed arm's density term into metric and trajectory (owner §7).

The density arms come out at −0.99 and +2.01 rather than exactly −1 and +2, and
that departure was once attributed to "density also changes the fall speed". It
was withdrawn: density also changes the next call's pre-sedimentation state, the
cap state, and every density-dependent rate, so naming fall speed picked one
candidate out of several without separating them.

For the density-contrast contribution the decomposition is

    D(rho') = sum_j drho'_j dz_j d_j(rho)              metric-only counterfactual
            + sum_j drho'_j dz_j [d_j(rho') - d_j(rho)]  trajectory response

The first term holds departures at their unperturbed values and moves the
density gap on unchanged layer geometry. The second is the response of this
density term to changed departures. Their sum is the density contribution,
not generally the full residual: add sum_j rho_lo*(dz_lo*dn_in-dz_up*dn_out).
The ideal inverted/x2 profiles scale the metric by -1 and +2; f32 profile rounding
can perturb those equalities. These are moist-density-weighted diagnostics;
the physical number-unit contract remains unresolved (SCIENCE_STATUS.md).

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
import sys
from pathlib import Path

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import g33_number_transport as nt  # noqa: E402
import g33_run_matrix as rmx  # noqa: E402

#: ONE arm list, owned by the run side: which streams exist is a fact about
#: the RUN, and the analysis reads whatever the matrix collected. The rationale
#: for the arms themselves (why offset+/- exist) lives with the list.
ARMS = rmx.ARMS


def interface_terms(stream: str, chain: str = "main") -> dict:
    """Applied transfers and density/geometry keyed by INTERFACE IDENTITY.

    The key is (call, loop, sub-step, upper level, lower level) -- everything
    that names the interface. It used to be a LIST, and `decompose` paired the
    two arms by position whenever the lengths matched (owner P0-1). Length is not
    identity: a baseline with mstep 2 then 1 and an arm with 1 then 2 have the
    same total and pair element 2 of one call against element 1 of another.

    That is not hypothetical. The immediately preceding density control merged
    every call under a key identical across calls, compared only the last one,
    and missed a real mstep 3->2 change. The same class of mistake, one layer up.

    `dn_departure` is the number that actually LEFT the cell above, taken from
    TOPOUT at the top interface and CAPIN's own-outflow below it -- the same
    pairing the cap-interface analysis uses.
    """
    rows = {}
    if chain not in ("main", "ice"):
        raise ValueError(f"unknown sedimentation chain {chain!r}")
    for i, call in enumerate(nt.calls(stream), start=1):
        nt.require_applied_interface_records(call)
        for lp in sorted(call["loops"]):
            pre = call["outer_pre_sed"]
            for col in sorted({c for l, c, _ in pre if l == lp}):
                ks = sorted(k for l, c, k in pre if c == col and l == lp)
                rho = {k: pre[(lp, col, k)]["rho"] for k in ks}
                dz = {k: pre[(lp, col, k)]["delz"] for k in ks}
                ms = call["mstep"][(lp, chain, col)]
                for n in range(1, ms + 1):
                    top = call["topout"][(lp, n, col, chain, 0)]
                    own, inflow = {0: top[1]}, {}
                    for j in ks[1:]:
                        cap = call["capin"][(lp, n, col, chain, j)]
                        own[j], inflow[j] = cap[2], cap[3]
                    for j in ks[1:]:
                        rows.setdefault(col, {})[(i, lp, n, j - 1, j)] = {
                            "drho": rho[j] - rho[j - 1],
                            "dz_up": dz[j - 1], "dn_out": own[j - 1],
                            # the ARRIVAL side, so the number-cap term can be
                            # computed rather than assumed zero (owner §5)
                            "rho_lo": rho[j], "dz_lo": dz[j],
                            "dn_in": inflow[j]}
    return rows


def decompose(base: dict, arm: dict) -> dict:
    """{col: {metric, trajectory, actual, ...}} for one arm against the baseline.

    `metric` uses the ARM's density gap with the BASELINE transfer; `actual` uses
    both from the arm. These are density contributions; `full_interface_residual`
    also includes the applied arrival/departure mismatch.
    """
    out = {}
    for col in sorted(base.keys() | arm.keys()):
        rows = arm.get(col) or {}
        b = base.get(col) or {}
        # EXACT KEY UNIVERSE, not equal counts (owner P0-1). Two arms with the
        # same number of interfaces can still be describing different ones.
        if set(b) != set(rows):
            miss, extra = len(set(b) - set(rows)), len(set(rows) - set(b))
            out[col] = {"comparable": False,
                        "reason": f"interface universes differ: {miss} missing, "
                                  f"{extra} extra (counts {len(rows)} vs "
                                  f"{len(b)}) — capture or sub-step schedules "
                                  f"differ, so interfaces do not correspond"}
            continue
        if any(rows[k][field] != b[k][field]
               for k in rows for field in ("dz_up", "dz_lo")):
            out[col] = {"comparable": False,
                        "reason": "layer geometry differs; this counterfactual varies density only"}
            continue
        if any(r["dn_in"] is None for r in (*rows.values(), *b.values())):
            raise ValueError("metric/trajectory decomposition requires every applied arrival")
        metric = sum(rows[k]["drho"] * rows[k]["dz_up"] * b[k]["dn_out"]
                     for k in rows)
        actual = sum(r["drho"] * r["dz_up"] * r["dn_out"] for r in rows.values())
        baseline = sum(r["drho"] * r["dz_up"] * r["dn_out"] for r in b.values())
        # THE THIRD TERM (owner §5). The complete interface residual is
        #     R_full = rho_lo*dz_lo*dn_in - rho_up*dz_up*dn_out
        # which splits EXACTLY as
        #     R_measure = (rho_lo - rho_up)*dz_up*dn_out      measure mismatch
        #     R_ncap    = rho_lo*(dz_lo*dn_in - dz_up*dn_out) arrival mismatch
        #
        # NOTE which "metric" is which. `metric` above is the COUNTERFACTUAL --
        # this arm's density gap against the BASELINE's transfers -- and belongs
        # to the metric/trajectory split. R_measure uses this arm's OWN
        # transfers, and that is `actual`. So the interface identity is
        #     actual + numcap == full
        # and NOT metric + numcap; conflating the two mixes a counterfactual with
        # a measurement.
        #
        # The historical name number_cap_term includes any transfer mismatch,
        # including metric conversion and rounding. A zero NET term does not
        # prove every interface matched; also report its absolute sum.
        mismatches = [r["rho_lo"] * (r["dz_lo"] * r["dn_in"]
                                     - r["dz_up"] * r["dn_out"])
                      for r in rows.values()]
        numcap = sum(mismatches)
        full = sum(r["rho_lo"] * r["dz_lo"] * r["dn_in"]
                   - (r["rho_lo"] - r["drho"]) * r["dz_up"] * r["dn_out"]
                   for r in rows.values())
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
            "number_cap_term": numcap,
            "sum_abs_number_transfer_mismatch": sum(abs(v) for v in mismatches),
            "full_interface_residual": full,
            # NET diagnostic agreement only; individual mismatches may cancel.
            "measure_only": abs(numcap) <= 1e-9 * max(abs(actual), 1e-300),
        }
    return out


def analysis(driver: str, nsplit: int, chain: str = "main", *,
             mode: str = "rezero", width: int = 3,
             baseline_stream: str | None = None,
             keep: dict | None = None, raw: dict | None = None) -> dict:
    """Decompose every density arm against `as-is`.

    `mode` and `width` are arguments, not constants (owner P0-2). Hardcoded, a
    bundle produced with `--mode carry` carried a `metric_trajectory.json`
    silently generated under `rezero`, and a fixture that is not three columns
    wide failed the driver's tile-sum check. The values a bundle actually used
    are recorded beside the result so a reader can see which run this describes.

    The DRIVER RUNS are not made here (owner review §8): the arm streams are
    raw run content, published and digested into the bundle, and the code that
    produces run content belongs in the run recipe -- so it lives in
    `g33_run_matrix`, which the producer imports directly. The `raw` parameter
    is the producer handing those collected streams in; without it this
    function asks `g33_run_matrix` itself, which keeps the standalone report
    working and keeps exactly one implementation of the matrix.
    """
    if raw is None:
        raw = rmx.collect(driver, nsplit, mode=mode, width=width,
                          baseline_stream=baseline_stream)
    base = interface_terms(raw["as-is"], chain)
    # Hand the raw streams back so the caller can PRESERVE them beside the
    # analysis. Without this the six runs existed only inside this function and
    # the evidence chain stopped at a derived JSON (owner §4).
    if keep is not None:
        keep.update(raw)
    return {"chain": chain, "mode": mode, "nsplit": nsplit, "tile_width": width,
            "baseline": ("bundle member" if baseline_stream is not None
                         else "re-run"),
            # The exact command line for each arm, and the arm the STREAM
            # declares -- so a reader can check the analysis describes the run it
            # claims to, without the raw bytes.
            "arms_runtime": {a: {"argv": [str(nsplit), mode, str(width), a],
                                 "declared_rho_profile": _declared_arm(raw[a])}
                             for a in ARMS},
            "arms": {a: decompose(base, interface_terms(raw[a], chain))
                     for a in ARMS if a != "as-is"}}


#: One reader for "which arm does this stream declare", the run side's.
_declared_arm = rmx.declared_arm


def report(driver: str, nsplit: int) -> None:
    a = analysis(driver, nsplit)
    print("  The departure from -1 and +2, decomposed rather than attributed.\n")
    print("  metric    = arm's density gap x BASELINE transfer  (pure measure)")
    print("  trajectory = changed departures' contribution to the density term")
    print("  metric + trajectory = density contribution; full residual also includes transfer mismatch.\n")
    print(f"  {'arm':10} {'col':>3} {'metric/base':>12} {'density/base':>12} "
          f"{'trajectory':>13} {'traj/metric':>12}")
    def ratio(value):
        return f"{value:12.4f}" if value is not None else f"{'-':>12}"

    for arm, cols in a["arms"].items():
        for col, r in cols.items():
            if not r["comparable"]:
                print(f"  {arm:10} {col:>3}  {r['reason']}")
                continue
            sh = (f"{100*r['trajectory_over_metric']:11.2f}%"
                  if r["trajectory_over_metric"] is not None else "  -")
            print(f"  {arm:10} {col:>3} {ratio(r['metric_over_baseline'])} "
                  f"{ratio(r['actual_over_baseline'])} {r['trajectory']:13.5e} {sh}")
            print(f"    density={r['actual']:+.6e} mismatch={r['number_cap_term']:+.6e} "
                  f"full={r['full_interface_residual']:+.6e}")
    print("\n  With ideal profiles metric/base is 0 (uniform), -1 (inverted),")
    print("  +2 (x2), and +1 for the OFFSET arms — a constant added to every level")
    print("  cancels in exact arithmetic. Rounded f32 profiles can perturb this.")
    print("  measure_only describes the NET mismatch, not cap inactivity at every interface.")


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
