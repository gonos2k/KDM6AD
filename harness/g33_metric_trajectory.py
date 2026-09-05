#!/usr/bin/env python3
"""Weight and transport effects on the full applied interface residual.

For layer weights w=rho*dz and paired applied transfers F=(dn_out,dn_in),

    R(w,F) = sum_e (w_lo*dn_in - w_up*dn_out)
    R(w',F') - R(w,F) = [R(w',F)-R(w,F)] + [R(w',F')-R(w',F)]
                        weight effect       transport response

This is a weight-first decomposition: the interaction R(w'-w,F'-F) is
assigned to the transport response, not a unique order-independent cause.
The counterfactual fixes BOTH baseline departure and arrival. With unmatched
transfers, adding a constant c to density changes R by c*sum(B-A), where
A=dz_up*dn_out and B=dz_lo*dn_in; it need not cancel. The density contribution
and transfer mismatch are reported separately as an accounting identity, not
substituted for the full residual in the decomposition.

The analysis first validates the requested run and the cross-arm run identity.
Interface identities (call, loop, substep, upper, lower) and geometry must match.
On the historical multisubcycle fixture, inverted changes main column 3's
schedule, so that comparison is undefined. Equal interface counts are not
sufficient: calls with different schedules can overwrite or mispair records.

The measure here uses moist density. Its physical number interpretation remains
conditional on the unresolved host/kernel unit contract (SCIENCE_STATUS.md).
Older JSON predating quantity=full_interface_residual decomposed only the density
contribution; its metric/actual/trajectory values must not be mixed with these.

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

    This extracts operands for arithmetic. Use `analysis` for a density-arm
    experiment: that boundary also validates the request and paired run identities.
    """
    return _interface_terms(nt.calls(stream), chain)


def _interface_terms(calls: list, chain: str) -> dict:
    """Reuse an already validated parse without reading the stream again."""
    rows = {}
    if chain not in ("main", "ice"):
        raise ValueError(f"unknown sedimentation chain {chain!r}")
    for key, departure, arrival in nt.applied_interfaces(calls):
        ci, lp, n, col, ch, ku, kl = key
        if ch != chain:
            continue
        pre = calls[ci - 1]["outer_pre_sed"]
        up, lo = pre[(lp, col, ku)], pre[(lp, col, kl)]
        rows.setdefault(col, {})[(ci, lp, n, ku, kl)] = {
            "drho": lo["rho"] - up["rho"],
            "rho_up": up["rho"],
            "dz_up": up["delz"], "dn_out": departure[1],
            "rho_lo": lo["rho"], "dz_lo": lo["delz"], "dn_in": arrival[1]}
    return rows


def residual(weights: dict, transfers: dict) -> float:
    """R(w,F), using paired arrivals and departures on an identical key universe."""
    return sum(
        weights[k]["rho_lo"] * weights[k]["dz_lo"] * transfers[k]["dn_in"]
        - weights[k]["rho_up"] * weights[k]["dz_up"] * transfers[k]["dn_out"]
        for k in weights)


def decompose(base: dict, arm: dict) -> dict:
    """Full residual change = weight_effect + trajectory, by matched column.

    baseline=R(w,F), metric=R(w',F), actual=R(w',F'). Thus metric is the
    counterfactual residual level; weight_effect=metric-baseline is its change.
    The weight-first order assigns R(w'-w,F'-F) to trajectory. These arithmetic
    operands must come from comparable experiments, as checked by `analysis`.
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
        baseline = residual(b, b)
        metric = residual(rows, b)
        actual = residual(rows, rows)
        density = sum(r["drho"] * r["dz_up"] * r["dn_out"] for r in rows.values())
        # The historical number_cap_term name includes caps, metric conversion
        # and rounding. Its NET sum may hide cancellation across interfaces.
        mismatches = [r["rho_lo"] * (r["dz_lo"] * r["dn_in"]
                                     - r["dz_up"] * r["dn_out"])
                      for r in rows.values()]
        numcap = sum(mismatches)
        out[col] = {
            "comparable": True, "interfaces": len(rows),
            "baseline": baseline, "metric": metric, "actual": actual,
            "weight_effect": metric - baseline,
            "trajectory": actual - metric,
            "residual_change": actual - baseline,
            "metric_over_baseline": metric / baseline if baseline else None,
            "actual_over_baseline": actual / baseline if baseline else None,
            # Fraction of the full counterfactual residual, undefined at zero.
            "trajectory_over_metric": (abs((actual - metric) / metric)
                                       if metric else None),
            "density_contribution": density,
            "number_cap_term": numcap,
            "sum_abs_number_transfer_mismatch": sum(abs(v) for v in mismatches),
            "full_interface_residual": actual,
            # NET diagnostic agreement only; individual mismatches may cancel.
            "measure_only": abs(numcap) <= 1e-9 * max(abs(density), 1e-300),
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
    if mode not in ("rezero", "carry"):
        raise ValueError(f"unsupported mode {mode!r}; expected 'rezero' or 'carry'")
    supplied_raw = raw is not None
    if raw is None:
        raw = rmx.collect(driver, nsplit, mode=mode, width=width,
                          baseline_stream=baseline_stream)
    if set(raw) != set(ARMS):
        raise nt.StreamError("density matrix must contain exactly the requested arms")
    if baseline_stream is not None and raw["as-is"] != baseline_stream:
        raise nt.StreamError("raw as-is stream differs from the supplied bundle baseline")
    identities, terms = {}, {}
    for arm in ARMS:
        rid, calls = nt.validated_run_identity(
            raw[arm], expected_width=width, with_calls=True)
        want = {"nsplit": nsplit, "carry": mode, "rho": arm}
        for field, value in want.items():
            if rid[field] != value:
                raise nt.StreamError(
                    f"{arm}: requested {field}={value!r}, stream declares {rid[field]!r}")
        if arm != "as-is":
            # All run-identity fields are fixed except the requested density
            # intervention. Adaptive mstep is response data, not in this identity.
            for field, value in identities["as-is"].items():
                if field != "rho" and rid[field] != value:
                    raise nt.StreamError(
                        f"{arm}: {field} differs from as-is "
                        f"({rid[field]!r} vs {value!r}); not a density-only comparison")
        identities[arm] = rid
        terms[arm] = _interface_terms(calls, chain)
    base = terms["as-is"]
    # Hand the raw streams back so the caller can PRESERVE them beside the
    # analysis. Without this the six runs existed only inside this function and
    # the evidence chain stopped at a derived JSON (owner §4).
    if keep is not None:
        keep.update(raw)
    return {"quantity": "full_interface_residual",
            "chain": chain, "mode": mode, "nsplit": nsplit, "tile_width": width,
            "baseline": ("bundle member" if baseline_stream is not None
                         else "provided raw" if supplied_raw else "re-run"),
            # argv records the validated request, not evidence of a subprocess
            # execution when the caller provided raw streams.
            "arms_runtime": {a: {"argv": [str(nsplit), mode, str(width), a],
                                 "declared_rho_profile": identities[a]["rho"],
                                 "run_identity": identities[a]}
                             for a in ARMS},
            "arms": {a: decompose(base, terms[a])
                     for a in ARMS if a != "as-is"}}


def report(driver: str, nsplit: int, *, result: dict | None = None) -> None:
    a = analysis(driver, nsplit) if result is None else result
    print("  Full applied interface residual: R(w,F) = sum(w_lo*dn_in-w_up*dn_out).")
    print("  weight effect = R(arm weights, baseline transfers) - R(baseline)")
    print("  transport response = R(arm) - R(arm weights, baseline transfers)")
    print("  residual change = weight effect + transport response.\n")
    print("  Weight-first order: the weight/transfer interaction is in transport response.")
    print(f"  {'arm':10} {'col':>3} {'baseline':>13} {'actual':>13} "
          f"{'weight effect':>13} {'transport':>13} {'change':>13}")
    for arm, cols in a["arms"].items():
        for col, r in cols.items():
            if not r["comparable"]:
                print(f"  {arm:10} {col:>3}  {r['reason']}")
                continue
            print(f"  {arm:10} {col:>3} {r['baseline']:13.5e} {r['actual']:13.5e} "
                  f"{r['weight_effect']:13.5e} {r['trajectory']:13.5e} "
                  f"{r['residual_change']:13.5e}")
            ratio = (f"{r['actual_over_baseline']:.6g}"
                     if r["actual_over_baseline"] is not None else "undefined")
            print(f"    density={r['density_contribution']:+.6e} "
                  f"mismatch={r['number_cap_term']:+.6e} "
                  f"full={r['actual']:+.6e} actual/base={ratio}")
    print("\n  A uniform density offset changes R by c*sum(dz_lo*dn_in-dz_up*dn_out).")
    print("  measure_only describes NET mismatch, not cap inactivity at every interface.")


def main(argv) -> int:
    if not 2 <= len(argv) <= 3:
        print(__doc__)
        return 2
    result = analysis(argv[0], int(argv[1]))
    report(argv[0], int(argv[1]), result=result)
    if len(argv) == 3:
        Path(argv[2]).write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
