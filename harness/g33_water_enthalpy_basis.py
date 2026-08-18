#!/usr/bin/env python3
"""The WATER and ENTHALPY column ledgers under both bases (owner §9.2).

`dual_ledger` reports both measures per SPECIES row. This reports them for the
column TOTALS, which is a different question and the one G33-BASIS-004 asks:
where the residual is otherwise at roundoff, the basis is the whole answer, and
where the column is dominated by a real departure it changes nothing.

Two things this had to get right, both measured rather than assumed.

`P_surface` is `prec[1]` ALONE. The three prec slots are the total and two of
its subsets -- column 1 carries 4.791301e-04 with both subsets exactly 0, and
column 2 carries 2.164629e-02 against snow 2.091130e-02 and graupel
4.745457e-04 -- so summing them double-counts. Summed, column 2 reads 1.56e-01
instead of 6.83e-02, and the residual stops being the water budget.

The physical weight uses the WINDOW-INITIAL qv at both endpoints. Sedimentation
moves hydrometeors, not vapour (`dual_ledger` measures `max_qv_change` as
exactly 0), so a weight that moved with the process would not be a budget.
"""
from __future__ import annotations

import math

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g33_cap_interface as ci  # noqa: E402
import g33_refine_analyze as ra  # noqa: E402
import g33_probe_read as pr  # noqa: E402

#: The water-bearing species. `qv` included: this is total water, not condensate.
WATER = ("qv", "qc", "qr", "qi", "qs", "qg")

BASES = ("operator", "physical")


def _weight(run: dict, col: int, k: int, basis: str) -> float:
    rho = run[("forcing", "rho", col, k)]
    dz = run[("forcing", "delz", col, k)]
    if basis == "operator":
        return rho * dz
    return rho / (1.0 + run[("initial", "qv", col, k)]) * dz


#: The standard forward-error growth factor for n floating-point operations,
#: g(n) = n*u/(1 - n*u) with u the unit roundoff (owner review §10).
def _gamma(n: int, u: float = 2.0 ** -53) -> float:
    d = 1.0 - n * u
    return (n * u / d) if d > 0 else float("inf")


def water(run: dict) -> dict:
    """Per column and basis: R_W = (W_final - W_initial) + P_surface."""
    cols = sorted({k[2] for k in run if len(k) == 4 and k[0] == "initial"})
    ks = sorted({k[3] for k in run if len(k) == 4 and k[0] == "initial"})
    out: dict = {}
    for col in cols:
        row: dict = {}
        for basis in BASES:
            ends = {}
            for tag in ("initial", "state"):
                ends[tag] = sum(
                    sum(run[(tag, s, col, k)] for s in WATER)
                    * _weight(run, col, k, basis) for k in ks)
            p = run[("prec", 1, col)]          # the TOTAL; 2 and 3 are subsets
            resid = (ends["state"] - ends["initial"]) + p
            # The residual IN UNITS OF the initial inventory's ULP (owner
            # review §8). "Closes below one ULP" was a claim about a ratio the
            # artifact never published, so its binding had to be an absolute
            # tolerance -- and the one chosen admitted 2.16 ULP against a
            # "< 1 ULP" sentence. The ratio and the verdict are fields now, so
            # the claim binds the predicate it actually makes, and a future
            # artifact at 1.5 ULP FAILS instead of passing a loose gate.
            ulp = math.ulp(ends["initial"]) if ends["initial"] else None
            # A FORWARD-ERROR SCREENING BOUND, not a single residual (owner
            # review §10). `|R| < ulp(W_0)` compares the residual to the
            # inventory's own resolution, which is a size indicator and says
            # nothing about how many operations produced it. The budget is
            # two column sums plus a surface term, so the bound carries the
            # operation counts and the magnitudes actually summed:
            #
            #   B_R = g(n_f)*S_f + g(n_0)*S_0 + g(2)*(|W_f|+|W_0|+|P|),
            #   g(n) = n*u / (1 - n*u),   u = 2^-53
            #
            # with S the sum of |w_k q_{s,k}| -- cancellation is exactly what
            # a residual near zero hides, and S is what makes it visible.
            scale = {}
            for tag in ("initial", "state"):
                scale[tag] = sum(
                    abs(run[(tag, s, col, k)] * _weight(run, col, k, basis))
                    for k in ks for s in WATER)
            n_terms = len(ks) * len(WATER)
            bound = (_gamma(n_terms) * scale["state"]
                     + _gamma(n_terms) * scale["initial"]
                     + _gamma(2) * (abs(ends["state"]) + abs(ends["initial"])
                                    + abs(p)))
            row[basis] = {
                "W_initial": ends["initial"], "W_final": ends["state"],
                "P_surface": p, "residual": resid,
                "relative": resid / ends["initial"] if ends["initial"] else None,
                "residual_in_initial_ulps": abs(resid) / ulp if ulp else None,
                # RENAMED from `closes_within_one_initial_ulp`: it states a
                # size relation and was read as closure. The screening verdict
                # is the field below, and it is the one a closure claim binds.
                "is_sub_ulp_of_initial_inventory":
                    (abs(resid) / ulp < 1.0) if ulp else None,
                "roundoff_scale": {"initial": scale["initial"],
                                   "final": scale["state"]},
                "roundoff_ops": n_terms,
                "roundoff_bound": bound,
                "residual_over_roundoff_bound":
                    (abs(resid) / bound) if bound else None,
                "passes_roundoff_screening":
                    (abs(resid) <= bound) if bound else None,
            }
        ro, rp = row["operator"]["relative"], row["physical"]["relative"]
        # How much the basis MATTERS here. Reported as a ratio because the
        # claim is comparative: 213.6x on the column that closes to roundoff,
        # 1.0x on the two that do not.
        #
        # A ratio of two residuals is only a physical comparison when BOTH
        # are resolved above their own roundoff bound (owner review §10).
        # Below it the denominator is noise and the ratio is arbitrarily
        # large -- correct as arithmetic, meaningless as a statement about
        # the bases. Unresolved gets `null` and a reason, not a number.
        resolved = all(
            row[b]["roundoff_bound"] and
            abs(row[b]["residual"]) > row[b]["roundoff_bound"]
            for b in ("operator", "physical"))
        if ro in (None, 0.0) or not resolved:
            row["basis_factor"] = None
            row["basis_factor_unresolved"] = (
                "denominator_not_resolved_above_roundoff" if ro not in (None, 0.0)
                else "operator_relative_is_zero_or_absent")
        else:
            row["basis_factor"] = abs(rp / ro)
        out[str(col)] = row
    return out


def enthalpy(stream: str) -> dict:
    """Both enthalpy ledgers under both bases, and how far apart they are.

    `enthalpy_with_cap_sink` has taken a basis since it was written; nothing
    passed one, so every bundle carried the operator measure alone and the
    claim that the relative residual is basis-invariant had no artifact.
    """
    got = {b: ci.enthalpy_with_cap_sink(stream, b) for b in BASES}
    out: dict = {}
    worst = 0.0
    for ledger in ("all_charged_at_surface", "with_internal_cap_sink"):
        for col in sorted(got["operator"][ledger]):
            a = got["operator"][ledger][col]["relative"]
            b = got["physical"][ledger][col]["relative"]
            d = abs(a - b)
            worst = max(worst, d)
            out[f"{ledger}/{col}"] = {"operator": a, "physical": b,
                                      "basis_difference": d}
    return {"rows": out, "worst_basis_difference": worst}


def analysis(stream: str) -> dict:
    # G33R or G33P -- the column ledgers need the window ENDPOINTS, and an
    # f64 build carries them in the probe family (owner D6 follow-on).
    try:
        run = pr.window_state(stream)
    except pr.ProbeError as e:
        # Refused with RefineError before, and the type is part of what a
        # caller sees. Only the boundary translates; the selection rule does
        # not get a second copy (Codex).
        raise ra.RefineError(str(e)) from e
    if not run:
        raise ra.RefineError("no window block: the column ledgers need the "
                             "window endpoints, not the per-call stream")
    return {"water": water(run), "enthalpy": enthalpy(stream),
            "note": "P_surface is prec[1], the TOTAL. prec[2] and prec[3] are "
                    "subsets of it, so summing the three double-counts."}
