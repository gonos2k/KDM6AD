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


def _rows(text: str, stage: str):
    for p in (ln.split() for ln in text.splitlines()):
        if len(p) >= 11 and p[:2] == ["G33F", "STAGE"] and p[4] == stage:
            # (call, loop, col, k), term, value
            yield (int(p[2]), int(p[5]), int(p[7]), int(p[8])), p[6], p[10]


def read_cells(text: str, *, label: str) -> dict:
    """{(call, loop, col, k): {term: f32}}, strictly.

    Keyed by the WHOLE identity. Under `(col, k)` a second internal loop
    overwrote the first and the artifact recorded no trace of it.
    """
    ra.read_text(text, nsplit=1, label=label)
    out: dict = {}
    for key, term, hexv in _rows(text, STAGE):
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
    return out


def read_state(text: str, *, label: str) -> dict:
    """{(call, loop, col, k): {"qr_pre", "qr_post", "t"}} as raw f32 bits."""
    out: dict = {}
    for stage, field, into in ((PRE, "qr", "qr_pre"), (POST, "qr", "qr_post"),
                               (PRE, "t", "t")):
        for key, term, hexv in _rows(text, stage):
            if term == field:
                out.setdefault(key, {})[into] = int(hexv, 16)
    return out


def read_dtcld(text: str, *, label: str) -> float:
    got = {float(ur.f32(int(h, 16)))
           for _k, term, h in _rows(text, "substep_pre") if term == "dtcld"}
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
        pred = ur.replay_qr(st["qr_pre"], cell, dtcld, cold)
        if pred != st["qr_post"]:
            bad.append({"cell": list(key), "predicted": pred,
                        "actual": st["qr_post"]})
    if bad:
        raise ra.RefineError(
            f"{label}: the qr update does not replay from its operands in "
            f"{len(bad)} cell(s), first {bad[0]} -- a process decomposition of "
            f"an update nobody can reproduce is not evidence")
    return {"cells": len(cells), "cold_gate_disagrees": len(flag_disagrees)}


def decompose(base_text: str, got_text: str, width: int, run) -> dict:
    """Per column, which terms move, weighted and unweighted."""
    a, b = (read_cells(base_text, label="base"), read_cells(got_text, label="got"))
    sa, sb = (read_state(base_text, label="base"), read_state(got_text, label="got"))
    dt_a, dt_b = read_dtcld(base_text, label="base"), read_dtcld(got_text, label="got")
    if dt_a != dt_b:
        raise ra.RefineError(f"dtcld differs between the runs ({dt_a} vs {dt_b})")
    replay = {"base": verify_replay(a, sa, dt_a, label="base"),
              "got": verify_replay(b, sb, dt_b, label="got")}
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
            for term, v in post.items():
                for basis, wt in w.items():
                    acc[basis][term] = acc[basis].get(term, 0.0) + v * wt
                    totals[basis] += v * wt
            for term, v in pre.items():
                preclamp[term] = preclamp.get(term, 0.0) + v

        out[str(col)] = {
            "cells": len(keys),
            "cold_cells": sum(1 for k in keys if ur.is_cold(sa[k]["t"])),
            **{basis: {
                "delta": acc[basis],
                "total_delta": totals[basis],
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
