#!/usr/bin/env python3
"""Which PROCESS carries a qr difference, decomposed against the actual update.

The first version of this file summed rate operands from a dict in Python f64
and called the result a process share. Five things were wrong with that, and
the owner review (P0-SCI-1) found all five:

  * the warm branch adds `paacw` TWICE (F:2922, `+paacw(i,k)+paacw(i,k)`) and a
    dict cannot hold a key twice, so the multiplicity was structurally lost;
  * records were keyed `(col, k)`, so a second internal loop would overwrite the
    first with no sign that it had;
  * a missing operand read as `0.0` through `.get(term, 0.0)`, making an
    uninstrumented term indistinguishable from a zero rate;
  * branch comparability COUNTED cold and warm cells rather than comparing the
    `(col, k)` branch map, so two different maps with the same totals passed;
  * the terms were summed in f64 while the reference accumulates f32 in source
    order under a positivity clamp, which is neither associative nor linear.

And `g33_update_replay` already had the correct ordered form. This module now
uses it rather than restating it.

The decomposition is a SOURCE-ORDER TELESCOPING. With F the actual update --
f32 association, `*dtcld`, `max(...,0)` -- and the operand vectors of the two
runs written O and W,

    C_j = F(W_1..W_j, O_{j+1}..O_n) - F(W_1..W_{j-1}, O_j..O_n)

so that `sum_j C_j == F(W) - F(O)` exactly, by construction rather than by
assumption. Terms are aggregated by NAME afterwards, which is why `paacw`
appearing twice contributes two steps to one name.

This remains a DIRECT decomposition. `pracw` consumes rain `praut` produces, so
a term can carry the arithmetic while another is upstream of it causally.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g33_refine_analyze as ra  # noqa: E402
import g33_update_replay as ur  # noqa: E402

STAGE = "micro_qr_operands"
PRE, POST = "micro_pre_state_update", "micro_post_state_update"

#: Every operand either arm consumes, plus the branch flag. A cell must carry
#: exactly this set: a missing one is refused rather than read as zero.
OPERANDS = frozenset(n for _s, n in ur.COLD_TERMS + ur.WARM_TERMS)
REQUIRED = OPERANDS | {"cold_gate"}


def _want_f32(kind: str, stage: str, field: str, key, label: str) -> None:
    if kind != "f32":
        raise ra.RefineError(
            f"{label}: `{stage}` {field} at {key} is {kind}, not f32 -- it is "
            f"read as float bits, so the wrong type is a wrong number")


def _rows(text: str, stage: str, *, label: str):
    """(key, term, hex) for one stage, refusing anything malformed.

    A short line used to be skipped by a `len(p) >= 11` test, so a truncated
    record read as an absent one. Absence and corruption are different, and
    only one of them is safe to continue from.
    """
    for ln in text.splitlines():
        p = ln.split()
        if p[:2] != ["G33F", "STAGE"] or len(p) < 5 or p[4] != stage:
            continue
        if len(p) != 11:
            raise ra.RefineError(
                f"{label}: malformed `{stage}` record -- {len(p)} fields, "
                f"expected 11: {ln[:90]!r}")
        # SHAPE here, TYPE at the point of use. A stage mixes types --
        # `substep_pre` carries f32 `dtcld`, i32 `mstep` and u8 `gate` -- so
        # enumerating allowed types per stage refused legitimate records twice
        # over. Each reader asserts the type of the fields it consumes.
        yield (int(p[2]), int(p[5]), int(p[7]), int(p[8])), p[6], p[9], p[10]


def read_cells(text: str, *, label: str) -> dict:
    """{(call, loop, col, k): {term: f32}}, strictly.

    Keyed by the WHOLE identity. Under `(col, k)` a second internal loop
    overwrote the first and the artifact recorded no trace of it.
    """
    ra.read_text(text, nsplit=1, label=label)
    out: dict = {}
    for key, term, kind, hexv in _rows(text, STAGE, label=label):
        _want_f32(kind, STAGE, term, key, label)
        cell = out.setdefault(key, {})
        if term in cell:
            raise ra.RefineError(
                f"{label}: duplicate `{term}` for cell {key} -- a repeated "
                f"record is corruption, not an update")
        cell[term] = float(ur.f32(int(hexv, 16)))
    if not out:
        raise ra.RefineError(
            f"{label}: no `{STAGE}` records -- this needs the instrumented build")
    for key, cell in sorted(out.items()):
        missing = REQUIRED - set(cell)
        if missing:
            raise ra.RefineError(
                f"{label}: cell {key} is missing {sorted(missing)} -- an "
                f"operand that was not emitted is not an operand that is zero")
        # The gate is a PREDICATE and its domain is {0, 1}. The first version
        # of this file checked that and the rewrite dropped it, so
        # `cold_gate == 1.0` silently mapped 0.5, 7.0 and NaN to "warm" -- and
        # on a cell the temperature also calls warm, the corruption agreed with
        # the derived branch and reported zero disagreements (Codex).
        gate = cell["cold_gate"]
        if gate not in (0.0, 1.0):
            raise ra.RefineError(
                f"{label}: cell {key} has cold_gate {gate!r}, which is not 0 "
                f"or 1 -- a branch predicate outside its domain says the "
                f"record is corrupt, not that the cell is warm")
    return out


def read_state(text: str, *, label: str) -> dict:
    """{(call, loop, col, k): {"qr_pre", "qr_post", "t"}} as raw f32 bits."""
    out: dict = {}
    for stage, field, into in ((PRE, "qr", "qr_pre"), (POST, "qr", "qr_post"),
                               (PRE, "t", "t")):
        for key, term, kind, hexv in _rows(text, stage, label=label):
            if term != field:
                continue
            _want_f32(kind, stage, field, key, label)
            cell = out.setdefault(key, {})
            if into in cell:
                # `read_cells` refused this and `read_state` did not, so a
                # repeated state record silently REPLACED the value the replay
                # closes against -- the one number that decides whether the
                # decomposition is of the actual update (Codex).
                raise ra.RefineError(
                    f"{label}: duplicate `{stage}` {field} for cell {key} -- "
                    f"the replay closes against this value, so a second one is "
                    f"corruption, not an update")
            cell[into] = int(hexv, 16)
    return out


def read_dtcld(text: str, *, label: str) -> float:
    got = set()
    for key, term, kind, h in _rows(text, "substep_pre", label=label):
        if term == "dtcld":
            _want_f32(kind, "substep_pre", term, key, label)
            got.add(float(ur.f32(int(h, 16))))
    if len(got) != 1:
        raise ra.RefineError(f"{label}: dtcld is {got or 'absent'}; the "
                             f"decomposition needs exactly one")
    return got.pop()


def _apply(values: list, terms: tuple, qr_pre_bits: int, dtcld: float,
           clamp: bool) -> np.float32:
    """F, in the source's own association. Mirrors `ur.rate_sum`/`ur.replay_qr`
    with the operands supplied POSITIONALLY, so a term occurring twice is two
    separate adds rather than one doubled one."""
    s = np.float32(0.0)
    for (sign, _name), v in zip(terms, values):
        v = np.float32(v)
        s = np.float32(s + v) if sign == "+" else np.float32(s - v)
    out = np.float32(np.float32(ur.f32(qr_pre_bits))
                     + np.float32(s * np.float32(dtcld)))
    return np.float32(max(out, np.float32(0.0))) if clamp else out


def _telescope(base: dict, got: dict, terms: tuple, qr_pre_bits: int,
               dtcld: float, clamp: bool) -> dict:
    """Per-term contributions summing EXACTLY to F(got) - F(base)."""
    o = [base[n] for _s, n in terms]
    w = [got[n] for _s, n in terms]
    mix, prev = list(o), _apply(o, terms, qr_pre_bits, dtcld, clamp)
    out: dict = {}
    for j, (_sign, name) in enumerate(terms):
        mix[j] = w[j]
        cur = _apply(mix, terms, qr_pre_bits, dtcld, clamp)
        out[name] = out.get(name, 0.0) + float(cur - prev)
        prev = cur
    return out


def verify_replay(cells: dict, state: dict, dtcld: float, *, label: str) -> dict:
    """Every cell's update must replay from its own operands, or nothing here
    is a decomposition of the update. This is a PRECONDITION, not a diagnostic.

    The branch is taken from the recorded temperature, not from `cold_gate`;
    the flag is then evidence ABOUT the producer rather than the definition of
    the answer, and disagreement is reported.
    """
    bad, flag_disagrees = [], []
    for key, cell in sorted(cells.items()):
        st = state.get(key)
        if not st or {"qr_pre", "qr_post", "t"} - set(st):
            raise ra.RefineError(f"{label}: cell {key} has operands but no "
                                 f"pre/post qr state to close against")
        cold = ur.is_cold(st["t"])
        if bool(cell["cold_gate"] == 1.0) != cold:
            flag_disagrees.append(key)
            continue
        pred = ur.replay_qr(st["qr_pre"], cell, dtcld, cold)
        if pred != st["qr_post"]:
            bad.append({"cell": list(key), "predicted": pred,
                        "actual": st["qr_post"]})
    if flag_disagrees:
        # The producer's flag and the branch derived from the recorded
        # temperature disagree, so one of them is wrong about which operand
        # set the cell applied. Counting that and carrying on would decompose
        # against terms the cell never used.
        raise ra.RefineError(
            f"{label}: `cold_gate` disagrees with the temperature-derived "
            f"branch in {len(flag_disagrees)} cell(s), first "
            f"{flag_disagrees[0]} -- the operand set for those cells is not "
            f"established")
    if bad:
        raise ra.RefineError(
            f"{label}: the qr update does not replay from its operands in "
            f"{len(bad)} cell(s), first {bad[0]} -- a process decomposition of "
            f"an update nobody can reproduce is not evidence")
    return {"cells": len(cells), "cold_gate_disagrees": len(flag_disagrees)}


#: How far a WEIGHTED closure may sit from zero and still be closed.
#:
#: The unweighted closure is exact and is tested as `== 0.0`: every term and the
#: actual difference are the same f32 words summed in float64 in the same order.
#: The weighted one cannot be, and not because anything is approximate --
#: `w*(a+b)` and `w*a + w*b` are different float64 expressions, so multiplying
#: through the sum reorders it. What is left is float64 rounding over the cells
#: of one column, which this bounds RELATIVELY: an absolute bound would mean
#: something different on a column whose total is 1e-5 and one whose total is
#: 1e+2, and both occur here.
#:
#: 64 * 2^-53 is ~7.1e-15 -- room for a few tens of roundings, far below any
#: difference a term could carry, so a real gap cannot hide under it.
F64_CLOSURE_TOL = 64 * 2.0 ** -53


def _closes(basis: str, gap: float, actual: float) -> bool:
    """Whether a per-basis closure is closed.

    Exactly for the unweighted basis, and to the float64 rounding of the
    reordered sum for the weighted ones -- see `F64_CLOSURE_TOL`. A zero actual
    difference is closed only by a zero gap: there is nothing to take a relative
    bound against, and calling any gap small compared to zero would make the
    check pass hardest exactly where it means least.
    """
    if basis == "unweighted" or actual == 0.0:
        return gap == 0.0
    return abs(gap) <= F64_CLOSURE_TOL * abs(actual)


def decompose(base_text: str, got_text: str, width: int, run) -> dict:
    """Per column, which terms move, weighted and unweighted."""
    a, b = (read_cells(base_text, label="base"), read_cells(got_text, label="got"))
    sa, sb = (read_state(base_text, label="base"), read_state(got_text, label="got"))
    dt_a, dt_b = read_dtcld(base_text, label="base"), read_dtcld(got_text, label="got")
    if dt_a != dt_b:
        raise ra.RefineError(f"dtcld differs between the runs ({dt_a} vs {dt_b})")
    replay = {"base": verify_replay(a, sa, dt_a, label="base"),
              "got": verify_replay(b, sb, dt_b, label="got")}

    # THE PRE-STATE. The telescoping substitutes operands one at a time into a
    # single starting qr, so it decomposes
    #
    #     F(qr_O-, r_W) - F(qr_O-, r_O)
    #
    # and the difference that actually exists between the runs is
    #
    #     F(qr_W-, r_W) - F(qr_O-, r_O)  =  C_pre + sum_j C_j,
    #     C_pre = F(qr_W-, r_W) - F(qr_O-, r_W).
    #
    # Each leg replaying its own update proves F(qr_O-,r_O)=qr_O+ and
    # F(qr_W-,r_W)=qr_W+. It does NOT prove qr_O- == qr_W-, and without that
    # the reported shares are of a quantity that is not the run difference
    # (owner §4.2).
    #
    # Measured here: identical in all 12 cells, so C_pre is zero -- which is
    # exactly why it has to be CHECKED rather than relied on.
    differing = sorted(k for k in a if sa[k]["qr_pre"] != sb[k]["qr_pre"])
    if differing:
        raise ra.RefineError(
            f"the two runs start from different qr in {len(differing)} cell(s), "
            f"first {differing[0]} -- the decomposition substitutes operands "
            f"into ONE starting state, so a pre-state difference is a term it "
            f"does not carry")
    replay["prestate_equal_cells"] = len(a)
    replay["prestate_different_cells"] = 0
    if set(a) != set(b):
        raise ra.RefineError("the two runs emitted different cells")

    # The branch MAP, cell by cell. Counting cold and warm cells let two
    # different maps with the same totals compare as term-comparable.
    flipped = sorted(k for k in a if ur.is_cold(sa[k]["t"]) != ur.is_cold(sb[k]["t"]))
    if flipped:
        raise ra.RefineError(
            f"{len(flipped)} cell(s) changed branch between the runs, first "
            f"{flipped[0]} -- the two apply different operand sets there, so "
            f"they are not term-comparable")

    out: dict = {}
    for col in range(1, width + 1):
        keys = sorted(k for k in a if k[2] == col)
        if not keys:
            raise ra.RefineError(f"column {col} emitted no {STAGE} records")
        acc = {basis: {} for basis in ("unweighted", "operator", "physical")}
        totals = dict.fromkeys(acc, 0.0)
        # CLOSURE against the update the runs actually performed, in raw f32
        # words: sum_j C_j must equal the real post-state difference. The
        # telescoping is exact by construction GIVEN a shared pre-state, and
        # this is the statement that says so rather than assuming it.
        #
        # PER BASIS (owner priority 4). It was computed unweighted only, while
        # the claim's headline -- 86.99/13.01 -- is the mass-weighted pair. The
        # weighted closure does follow from the per-cell identity under a fixed
        # weight, so this is not a doubt about the arithmetic; it is that a
        # reader had to do that step themselves to see the headline closed. The
        # actual difference is carried into each basis by the SAME weight the
        # terms take, in the same loop, so nothing is re-derived.
        actual = dict.fromkeys(acc, 0.0)
        preclamp: dict = {}
        for key in keys:
            _c, _l, _col, k = key
            cold = ur.is_cold(sa[key]["t"])
            terms = ur.COLD_TERMS if cold else ur.WARM_TERMS
            post = _telescope(a[key], b[key], terms, sa[key]["qr_pre"], dt_a, True)
            pre = _telescope(a[key], b[key], terms, sa[key]["qr_pre"], dt_a, False)
            rho = run[("forcing", "rho", col, k)]
            dz = run[("forcing", "delz", col, k)]
            qv0 = run[("initial", "qv", col, k)]
            w = {"unweighted": 1.0, "operator": rho * dz,
                 "physical": rho / (1.0 + qv0) * dz}
            d = float(np.float32(ur.f32(sb[key]["qr_post"]))
                      - np.float32(ur.f32(sa[key]["qr_post"])))
            for basis, wt in w.items():
                actual[basis] += d * wt
            for term, v in post.items():
                for basis, wt in w.items():
                    acc[basis][term] = acc[basis].get(term, 0.0) + v * wt
                    totals[basis] += v * wt
            for term, v in pre.items():
                preclamp[term] = preclamp.get(term, 0.0) + v

        gaps = {basis: actual[basis] - totals[basis] for basis in acc}

        out[str(col)] = {
            "cells": len(keys),
            "actual_post_delta": actual["unweighted"],
            "telescoped_minus_actual": gaps["unweighted"],
            "closes_against_actual_update": gaps["unweighted"] == 0.0,
            "cold_cells": sum(1 for k in keys if ur.is_cold(sa[k]["t"])),
            **{basis: {
                "delta": acc[basis],
                "total_delta": totals[basis],
                # The same closure, in the basis the share is reported in.
                "actual_post_delta": actual[basis],
                "telescoped_minus_actual": gaps[basis],
                "closes_against_actual_update": _closes(basis, gaps[basis],
                                                        actual[basis]),
                # Shares only where there IS a change: a share of a zero total
                # is not a number, and 0/0 printed as a percentage is how a
                # null result acquires a mechanism.
                "share": ({t: v / totals[basis] for t, v in acc[basis].items() if v}
                          if totals[basis] else {}),
            } for basis in acc},
            # Reported separately because the clamp is where the update stops
            # being linear: a term whose pre-clamp contribution is large and
            # post-clamp contribution is zero was clipped, not absent.
            "preclamp_delta": preclamp,
        }
    return {"columns": out, "replay": replay, "dtcld": dt_a}


def analysis(driver: str, fixture: str) -> dict:
    """Oracle decomposition against the whole domain, as a multi-run analysis."""
    import g33_ncmin_locality as nl
    width = nl.fixture_dims(fixture)[0]
    oracle, whole = (1,) * width, (width,)
    base_text, got_text = nl.run(driver, oracle), nl.run(driver, whole)
    got = decompose(base_text, got_text, width, ra.read_text(base_text))
    return {
        **got,
        "compared": {"oracle": list(oracle), "against": list(whole)},
        "ran": {"nsplit": 1, "carry": "rezero", "rho": "as-is", "width": width,
                "decompositions": [list(oracle), list(whole)]},
    }
