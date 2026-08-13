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
            row[basis] = {
                "W_initial": ends["initial"], "W_final": ends["state"],
                "P_surface": p, "residual": resid,
                "relative": resid / ends["initial"] if ends["initial"] else None,
            }
        ro, rp = row["operator"]["relative"], row["physical"]["relative"]
        # How much the basis MATTERS here. Reported as a ratio because the
        # claim is comparative: 213.6x on the column that closes to roundoff,
        # 1.0x on the two that do not.
        row["basis_factor"] = abs(rp / ro) if ro not in (None, 0.0) else None
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
