"""The N x C x L factorial: one reader, one control and one span PER RESPONSE.

This module has been wrong three times, each time in a way its own table showed.

It called the three corrections ORTHOGONAL from absolute residuals whose `I_NC`
was 0.0235 -- marginal selectivity reported as a statement about cross terms.

It then fixed the mathematics and left `window` selecting the span for four
responses out of six, so a "first-call" table carried whole-window cap and
partition numbers.

And it fixed the span with ONE global reader and ONE global control policy, which
re-mixed what the span fix had just separated. N, C and L do not need the same
ones:

    R_qr, R_qi   the ACTUAL-transfer budget. No control of their own, ON
                 PURPOSE: a failing mass closure is the defect C exists to
                 remove, so rejecting the arm for it deletes the C response
                 from the C experiment.
    R_nr, R_ni   the same reader, each PAIRED with its chain's mass row --
                 a number residual is a number-specific measurement only where
                 the mass beside it closed.
    D_*_metric   the endpoint-recovered metric residual, under its own name.
                 `column()` inverts the update, so its MASS rows close by
                 construction and are not a budget; measured on the first call,
                 legacy ice reads -8.83e-17 recovered against -6.006e-01 from
                 the actual records.
    cap_*        a LEGACY-MECHANISM diagnostic, not C's native invariant. The
                 legacy ice interface term IS that arm's mass non-closure to
                 the digit; for the conservative arm the same term is -3.373e-01
                 while its column closes to 2.3e-08. One quantity cannot be the
                 conserved invariant of both operators.
    partition_*  four questions -- first segment, last segment, the WINDOW's
                 final state, and the path -- each carrying its own span,
                 because the last post-sedimentation segment is not what the
                 forecast carries.

Every response is `{value, unit, reader, span, paired_control, valid, reason,
screening_bound}`, and a contrast is computed only where the response is valid
in ALL EIGHT arms. Where it is not, `conditionals()` still reports the halves
that are: on `g33_fixture_multisubcycle_v1` at mstep <= 10 the C=0 half fails
its mass control and the C=1 half closes, which makes `N_at_C1` a controlled
measurement of Arm N at high sub-step count even though `beta_N` is not scorable.

SIGNED, NOT ABSOLUTE. `|R|` hides sign reversal and turns cancellation into
apparent effect.

RESPONSES ARE NOT COMPARABLE ACROSS ROWS. Each carries its unit, and nothing
here reports a "largest effect in the table".
"""
from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

#: f32 unit roundoff. The stream's values are f32 bit patterns, so no quantity
#: derived from them resolves below this times its own scale, whatever
#: precision the summation is done in.
U32 = 2.0 ** -24
#: ... and the f64 unit roundoff, for the summation this module performs.
U64 = 2.0 ** -53


class FactorialError(Exception):
    """A table that cannot be trusted to be a factorial of anything."""


#: arm -> (N, C, L). ONE table, so factor assignment is never inferred from a
#: name. Two readings in this campaign were lost to substring tests on the
#: algorithm string -- `"nmass" in algo` is right today and is not a contract.
ALGO_FACTORS = {
    "legacy": (0, 0, 0),
    "nmass": (1, 0, 0),
    "lncmin": (0, 0, 1),
    "nmasslncmin": (1, 0, 1),
    "conservative": (0, 1, 0),
    "cons_nmass": (1, 1, 0),
    "cons_lncmin": (0, 1, 1),
    "cons_nmasslncmin": (1, 1, 1),
}

#: response -> spec. ONE reader, ONE control and ONE span PER RESPONSE, because
#: N, C and L do not need the same ones and a single global policy re-mixes what
#: the span fix just separated.
#:
#: `reader`   matched   the actual XFER records, admissible at any mstep
#:            recovered `column()` inverting the update -- needs mstep == 1, and
#:                      its MASS rows close by construction, so they are named
#:                      as a diagnostic rather than offered as a budget
#:            capin     the interface protocol
#:            state     the post-sed / window-final states
#: `control`  the (chain, species) mass row whose closure this response's
#:            interpretation depends on, or None where it depends on none.
#: `span`     `selected` follows --window; anything else is fixed and says so.
#:
#: The MASS rows carry no control of their own ON PURPOSE. A failing mass
#: closure is the defect C exists to remove, so rejecting the arm for it would
#: delete the C response from the C experiment (owner review section 5.1).
RESPONSES = {
    "R_qr_num": ("kg m-2", None, "matched", None, "selected"),
    "R_qr_den": ("kg m-2", None, "matched", None, "selected"),
    "R_qr": ("dimensionless", "C", "matched", None, "selected"),
    "R_qi_num": ("kg m-2", "C", "matched", None, "selected"),
    "R_qi_den": ("kg m-2", None, "matched", None, "selected"),
    "R_qi": ("dimensionless", "C", "matched", None, "selected"),
    "R_nr_num": ("number m-2", "N", "matched", ("main", "qr"), "selected"),
    # The DENOMINATOR carries no control. It is the starting inventory, a state
    # quantity, and a failing mass closure does not make it unmeasurable --
    # gating it deleted exactly the inventory half that numerator/denominator
    # separation exists to expose (owner review §8).
    "R_nr_den": ("number m-2", None, "matched", None, "selected"),
    "R_nr": ("dimensionless", "N", "matched", ("main", "qr"), "selected"),
    "R_ni_num": ("number m-2", "N", "matched", ("ice", "qi"), "selected"),
    "R_ni_den": ("number m-2", None, "matched", None, "selected"),
    "R_ni": ("dimensionless", "N", "matched", ("ice", "qi"), "selected"),
    # The endpoint-recovered metric diagnostic, under its own name. It measures
    # the residual of the number METRIC as the endpoints imply it, which is a
    # different quantity from the actual-transfer budget above -- and the
    # published N x C masking result is this one.
    "D_nr_metric": ("dimensionless", "N", "recovered", None, "selected"),
    "D_ni_metric": ("dimensionless", "N", "recovered", None, "selected"),
    "cap_main_signed": ("kg m-2", None, "capin", None, "selected"),
    "cap_main_destroyed": ("kg m-2", None, "capin", None, "selected"),
    "cap_main_created": ("kg m-2", None, "capin", None, "selected"),
    "cap_ice_signed": ("kg m-2", None, "capin", None, "selected"),
    "cap_ice_destroyed": ("kg m-2", None, "capin", None, "selected"),
    "cap_ice_created": ("kg m-2", None, "capin", None, "selected"),
    # TWO COUNTS AT EVERY POINT, because they are two units. A CELL is a
    # (split, column, level) whose state differs in at least one field; a
    # COMPONENT is one (field, column, level). Reporting 4 at the last segment
    # beside 32 at the window final and calling it eight-fold growth compared a
    # cell count with a component count (owner review §7).
    "partition_first_cells": ("cells", "L", "state", None, "first-segment-post"),
    "partition_first_components": ("components", "L", "state", None,
                                   "first-segment-post"),
    "partition_last_segment_cells": ("cells", "L", "state", None,
                                     "last-segment-post"),
    "partition_last_segment_components": ("components", "L", "state", None,
                                          "last-segment-post"),
    "partition_window_final_cells": ("cells", "L", "state", None,
                                     "window-final"),
    "partition_window_final_components": ("components", "L", "state", None,
                                          "window-final"),
    "partition_path_cells": ("cells", "L", "state", None, "all-segments"),
    "partition_path_components": ("components", "L", "state", None,
                                  "all-segments"),
}

#: species -> the chain its cap belongs to, so the cap and the residual of one
#: chain are read in the same terms.
CHAIN_OF = {"qr": "main", "nr": "main", "qi": "ice", "ni": "ice"}


def _gamma(n: int, u: float) -> float:
    """The standard summation growth factor, `n*u / (1 - n*u)`."""
    d = 1.0 - n * u
    return (n * u / d) if d > 0 else float("inf")


def _screen(sum_abs: float, n_terms: int) -> float:
    """The scale below which a sum of f32-derived terms says nothing.

    Two contributions, and the first dominates: the inputs are f32, so each
    carries `U32` of its own magnitude however exactly it is then summed; and
    this module's own f64 accumulation adds `gamma(n)`. A coefficient is
    reported against this rather than against a bare epsilon, because
    "is it resolved" is a question about magnitude and operation count, not
    about whether a number is non-zero.
    """
    return sum_abs * (U32 + _gamma(max(n_terms, 1), U64))


def _ratio_screen(num, den, b_num, b_den) -> float:
    """First-order propagation for `R = A / D`.

    The bound used to be the numerator's alone divided by `|D|`, which ignores
    that the denominator is itself a sum of f32-derived terms. For a small `L`
    effect or a third-order term, the missing piece is the one that decides
    whether it is resolved.

        |dR| <= |dA|/|D| + |A||dD|/D^2
    """
    if not den:
        return 0.0
    return b_num / abs(den) + abs(num) * b_den / (den * den)


def _matched_rows(stream: str, span_calls: frozenset):
    """`closures()` once, with each chain's mass control taken ON THE SPAN.

    `mc.usable()` reads every per-call record, so a row that closes on call 1
    and fails on call 7 failed a FIRST-CALL table too. The control is a
    property of the span the response is taken over, so it is cut to the same
    calls before it is asked.

    Nothing is raised. Which rows closed is a RESULT -- for the C arm the
    legacy failure IS the response -- so the verdicts are returned and each
    response decides for itself whether it needs them (owner review §5).
    """
    import g33_matched_closure as mc
    rows = mc.closures(stream, "operator")
    control = {}
    for (chain, sp, col), d in rows.items():
        if not sp.startswith("q"):
            continue
        pcs = [pc for pc in d["per_call"] if pc["call"] in span_calls]
        if not pcs:
            control[(chain, col)] = (False, "no calls on this span")
            continue
        ok, why = mc.usable({"per_call": pcs, "residual": 0.0, "out": 0.0,
                             "calls": len(pcs)})
        control[(chain, col)] = (ok, why)
    return rows, control


def _matched_residual(rows: dict, span_calls: frozenset, species: str):
    """The residual from ACTUAL transfers, admissible at any `mstep`.

    `column()` inverts the update to recover the transfers, which needs one
    sub-step. `g33_matched_closure` reads the `XFER` records the kernel emits
    and reconstructs nothing -- "mstep > 1 is admissible".
    """
    num = den = b_num = b_den = 0.0
    seen = False
    cols = set()
    for (chain, sp, col), d in rows.items():
        if sp != species:
            continue
        for pc in d["per_call"]:
            if pc["call"] not in span_calls:
                continue
            seen = True
            cols.add((chain, col))
            num += pc["residual"]
            den += pc["start"]
            b_num += _screen(pc["scale"], pc["ops"])
            b_den += _screen(abs(pc["start"]), pc["ops"])
    if not seen:
        return None
    return {"num": num, "den": den, "b_num": b_num, "b_den": b_den,
            "cols": cols}


def _recovered_ratio(span, species):
    """The endpoint-recovered metric residual, and whether the span was whole.

    `column()` returns None above one sub-step. An all-`None` span used to
    become `0.0` -- indistinguishable from a residual that vanished -- so the
    eligible rows are counted against what the span should have produced and a
    short count invalidates the response instead of scoring it.
    """
    import g33_number_transport as nt
    num = den = sum_abs = 0.0
    eligible = expected = terms = 0
    for call in span:
        loop = nt.single_loop(call)
        for col in sorted({c for l, c, _k in call["outer_pre_sed"] if l == loop}):
            expected += 1
            row = nt.column(call, col, species)
            if row is None:
                continue
            eligible += 1
            num += row["residual"]
            den += row["start"]
            sum_abs += abs(row["residual"]) + abs(row["start"])
            terms += 2
    return {"num": num, "den": den, "sum_abs": sum_abs, "terms": terms,
            "eligible": eligible, "expected": expected}


def _cap(stream: str, span_calls: frozenset) -> dict:
    """Per chain: signed defect, destruction and creation, over ONE span.

    `cap_sink()` returns rows for the whole stream with no way to select a
    call, so the interfaces are walked directly -- `Interface` carries its own
    1-based `call` -- and the span is applied here where it belongs.

    This is a LEGACY-MECHANISM diagnostic, not C's native invariant. Measured:
    the legacy first-call ice interface term (+6.006e-01 of starting mass) IS
    that arm's actual mass non-closure to the digit, and for the conservative
    arm the same term reads -3.373e-01 while its column budget closes to
    2.3e-08. One quantity cannot be the conserved invariant of both operators.
    C's outcome response is the actual-transfer `R_qi` (owner review §10).
    """
    import g33_cap_interface as ci
    out = {}
    for chain in ("main", "ice"):
        signed = destroyed = created = sum_abs = 0.0
        n = 0
        for f in ci._walk(stream, "operator"):
            if f.chain != chain or f.call not in span_calls:
                continue
            s = -f.mass_term          # Sink.signed: the interface term negated
            signed += s
            destroyed += max(s, 0.0)
            created += max(-s, 0.0)
            sum_abs += abs(s)
            n += 1
        out[chain] = {"signed": signed, "destroyed": destroyed,
                      "created": created, "sum_abs": sum_abs, "terms": n}
    return out


def _segment_states(text: str) -> dict:
    """`(split, col, level) -> post-sedimentation state`, every segment."""
    import g33_number_transport as nt
    got = {}
    for call in nt.calls(text):
        loop = nt.single_loop(call)
        if not isinstance(loop, int):
            continue
        for (lvl, col, k), val in call["outer_post_sed"].items():
            if lvl == loop:
                got[(call["split"], col, k)] = tuple(sorted(val.items()))
    return got


def _window_final(text: str) -> dict:
    """The window's FINAL state, from the G33R block the driver writes.

    The last post-sedimentation segment is not the window final state: other
    microphysical processes run after sedimentation within the same call. The
    driver emits `outF` -- the state the run ends on -- and that is what a
    forecast would carry, so it is compared separately from the segment
    (owner review §8).
    """
    import g33_refine_analyze as ra
    d = ra.read_text(text)
    return {k[1:]: v for k, v in d.items()
            if isinstance(k, tuple) and k[0] == "state"}


def _partition(single: str, split: str) -> dict:
    """Four partition responses, over an EXACT common universe.

    The universe was intersected before, so a split stream missing a column or
    a sub-step compared fewer states and reported BETTER invariance. That is
    fail-open: the count a missing state removes is the count the response is.

    Four quantities, because they are four questions -- after ONE segment,
    after the LAST segment, at the WINDOW's final state, and how often they
    ever differed. The published 45 was the last of these.
    """
    a, b = _segment_states(single), _segment_states(split)
    if set(a) != set(b):
        raise FactorialError(
            f"the two decompositions do not describe the same segment states: "
            f"{len(set(a) - set(b))} missing, {len(set(b) - set(a))} extra. "
            f"Comparing the intersection would report better invariance for a "
            f"shorter run.")
    fa, fb = _window_final(single), _window_final(split)
    if set(fa) != set(fb):
        raise FactorialError(
            f"the two decompositions do not describe the same window-final "
            f"state: {len(set(fa) - set(fb))} missing, "
            f"{len(set(fb) - set(fa))} extra")
    splits = sorted({k[0] for k in a})
    if not splits:
        raise FactorialError("no segment states recovered from either stream")
    lo, hi = splits[0], splits[-1]

    def counts(keys):
        """(differing cells, differing field components) over `keys`."""
        cells = comps = 0
        for k in keys:
            da = dict(a[k])
            db = dict(b[k])
            n = sum(1 for f in da if da[f] != db.get(f, object()))
            cells += bool(n)
            comps += n
        return float(cells), float(comps)

    first_c, first_p = counts([k for k in a if k[0] == lo])
    last_c, last_p = counts([k for k in a if k[0] == hi])
    path_c, path_p = counts(list(a))
    # The window-final block is already keyed per (field, column, level), so a
    # differing entry IS a component; the cells it touches are its (col, level).
    wf_comp = [k for k in fa if fa[k] != fb[k]]
    return {
        "partition_first_cells": first_c,
        "partition_first_components": first_p,
        "partition_last_segment_cells": last_c,
        "partition_last_segment_components": last_p,
        "partition_window_final_cells": float(len({k[1:] for k in wf_comp})),
        "partition_window_final_components": float(len(wf_comp)),
        "partition_path_cells": path_c,
        "partition_path_components": path_p,
    }


def responses(stream_single: str, stream_split: str, *,
              window: bool = False) -> dict:
    """Every response, each with its own reader, control, span and verdict.

    A response is `{value, unit, reader, span, paired_control, valid, reason,
    screening_bound}`. There is no global `--matched` any more: the actual
    transfers are the budget rows, the endpoint recovery is a separately named
    metric diagnostic, and a failing mass control invalidates the number
    response it is paired with and nothing else.
    """
    import g33_number_transport as nt
    calls = nt.calls(stream_single)
    span = calls if window else calls[:1]
    span_calls = frozenset(range(1, len(span) + 1))
    selected = "window" if window else "first-call"

    rows, control = _matched_rows(stream_single, span_calls)
    out = {}

    def put(name, value, *, valid=True, reason=""):
        unit, owner, reader, ctrl, spanspec = RESPONSES[name]
        out[name] = {"value": value, "unit": unit, "owner": owner,
                     "reader": reader, "paired_control": list(ctrl) if ctrl
                     else None,
                     "span": selected if spanspec == "selected" else spanspec,
                     "valid": valid, "reason": reason, "screening_bound": 0.0}

    for species in ("qr", "qi", "nr", "ni"):
        r = _matched_residual(rows, span_calls, species)
        ctrl = RESPONSES[f"R_{species}"][3]
        bad = ""
        if ctrl and r:
            fails = [f"{c[0]}/{c[1]}: {control[c][1]}" for c in sorted(r["cols"])
                     if c in control and not control[c][0]]
            # The control is the chain's OWN mass row; a number response is
            # only a number-specific measurement where it closed.
            fails += [f"{ctrl[0]}/{col}: {why}"
                      for (ch, col), (ok, why) in sorted(control.items())
                      if ch == ctrl[0] and not ok]
            bad = "; ".join(dict.fromkeys(fails))
        for suffix, value, bound in (
                ("_num", r["num"] if r else 0.0, r["b_num"] if r else 0.0),
                ("_den", r["den"] if r else 0.0, r["b_den"] if r else 0.0),
                ("", (r["num"] / r["den"] if r and r["den"] else 0.0),
                 _ratio_screen(r["num"], r["den"], r["b_num"], r["b_den"])
                 if r else 0.0)):
            name = f"R_{species}{suffix}"
            # The control is per RESPONSE: the ratio and the numerator need the
            # chain's mass row, the denominator does not.
            gated = RESPONSES[name][3] is not None
            reason = "no matched rows on this span" if not r else (
                bad if gated else "")
            # A/0 is undefined, not zero. Reporting 0.0 for it makes an
            # unmeasurable ratio indistinguishable from a residual that
            # vanished -- the same shape as the coverage defect already closed.
            if not suffix and r and not r["den"]:
                reason = reason or "zero denominator: the ratio is undefined"
            put(name, value, valid=bool(r) and not reason, reason=reason)
            out[name]["screening_bound"] = bound

    for species, name in (("nr", "D_nr_metric"), ("ni", "D_ni_metric")):
        d = _recovered_ratio(span, species)
        short = d["eligible"] != d["expected"]
        put(name, d["num"] / d["den"] if d["den"] else 0.0,
            valid=not short,
            reason=(f"{d['eligible']} of {d['expected']} rows recoverable -- "
                    f"`column()` refuses mstep > 1, and a ratio over the rows "
                    f"that happened to survive is not the span's residual")
            if short else "")
        out[name]["screening_bound"] = _ratio_screen(
            d["num"], d["den"], _screen(d["sum_abs"], d["terms"]),
            _screen(abs(d["den"]), d["terms"]))

    cap = _cap(stream_single, span_calls)
    for chain in ("main", "ice"):
        c = cap[chain]
        for what in ("signed", "destroyed", "created"):
            put(f"cap_{chain}_{what}", c[what])
            out[f"cap_{chain}_{what}"]["screening_bound"] = _screen(
                c["sum_abs"], c["terms"])

    for name, value in _partition(stream_single, stream_split).items():
        put(name, value)                # integer counts: exact, unscreened
    return out


def check_identity(name: str, single: str, split: str) -> dict:
    """The arm's identity, from the STREAMS rather than from the file name.

    Both algorithm-tag mistakes in this campaign were of this shape: an
    artifact that could not name its own operator, believed because a path
    said so. The factor row is chosen by `name`, so `name` has to be the thing
    the kernel actually ran.
    """
    import g33_number_transport as nt
    a = nt.validated_run_identity(single)
    b = nt.validated_run_identity(split)
    if a["algorithm"] != name or b["algorithm"] != name:
        raise FactorialError(
            f"{name}: the streams declare algorithm "
            f"{a['algorithm']!r}/{b['algorithm']!r}. The factor row is chosen "
            f"by the name, so the name has to be what ran.")
    for key in ("nsplit", "carry", "rho", "width", "levels", "delt", "dtcld"):
        if a[key] != b[key]:
            raise FactorialError(
                f"{name}: the two decompositions differ in {key} "
                f"({a[key]!r} vs {b[key]!r}) -- they are not the same "
                f"experiment run two ways.")
    if a["ntile"] == b["ntile"]:
        raise FactorialError(
            f"{name}: both streams ran {a['ntile']} tile(s), so there is no "
            f"decomposition to compare and `partition` would be zero by "
            f"construction.")
    # delt/dtcld/loops were COMPARED between the two decompositions and then
    # dropped from the returned dict, so the cross-arm gate that reads this
    # could not see them: two arms on different timesteps passed (owner §9).
    return {"algorithm": a["algorithm"], "nsplit": a["nsplit"],
            "mode": a["carry"], "rho": a["rho"], "width": a["width"],
            "levels": a["levels"], "delt": a["delt"], "dtcld": a["dtcld"],
            "loops": a.get("loops"), "tiles_single": a["tile_sizes"],
            "tiles_split": b["tile_sizes"]}


def _raw_input(text: str) -> dict:
    """What a run was HANDED: the G33R `initial` state and every forcing.

    `xland` is in there now. `ncmin` branches on the land mask (F:876-882) and
    Arm L is the correction to that branch, so it is the one input L's causal
    story rests on -- and until the driver emitted it, no analysis comparing
    two decompositions could check they were given the same one.
    """
    import g33_refine_analyze as ra
    d = ra.read_text(text)
    return {k: v for k, v in d.items()
            if isinstance(k, tuple) and k[0] in ("initial", "forcing")}


def same_input(name: str, single: str, split: str) -> None:
    """The two DECOMPOSITIONS of one arm must have been handed the same run.

    `check_identity` compared their metadata -- nsplit, mode, rho, width,
    levels, delt, dtcld -- and never their state. Two streams can agree on all
    of that and start from different atmospheres, and then every `partition`
    count reads as a decomposition effect (owner review §6).
    """
    a, b = _raw_input(single), _raw_input(split)
    if set(a) != set(b):
        raise FactorialError(
            f"{name}: the two decompositions do not carry the same input "
            f"records: {len(set(a) ^ set(b))} differ in the key set")
    bad = sorted(k for k in a if a[k] != b[k])
    if bad:
        raise FactorialError(
            f"{name}: the two decompositions were handed different inputs -- "
            f"{len(bad)} of {len(a)} cells differ, e.g. {bad[:3]}. Every "
            f"`partition` count would read as a decomposition effect.")


def same_atmosphere(streams: dict) -> None:
    """Every arm must have been handed the SAME atmosphere, bit for bit.

    The previous gate compared four column-integrated scalars -- the `_den`
    responses -- and two different vertical profiles can share an integral:
    `sum m_k x_k` is equal for many `x_k`. A necessary condition read as a
    sufficient one is how a factorial ends up attributing a difference to the
    factor that names the arm when the arms did not start level.

    So the comparison is the raw G33R `initial` state and `forcing` records,
    every field, every cell, as the bytes the driver emitted.
    """
    ref = ref_arm = None
    for arm, text in streams.items():
        got = _raw_input(text)
        if ref is None:
            ref, ref_arm = got, arm
            continue
        if set(got) != set(ref):
            raise FactorialError(
                f"{arm} and {ref_arm} do not even carry the same initial "
                f"records: {len(set(ref) ^ set(got))} differ in the key set")
        bad = sorted(k for k in ref if got[k] != ref[k])
        if bad:
            raise FactorialError(
                f"{arm} and {ref_arm} were not handed the same atmosphere: "
                f"{len(bad)} of {len(ref)} initial/forcing cells differ, "
                f"e.g. {bad[:3]}. A factorial cannot attribute a difference to "
                f"the factor that names the arm when the arms did not start "
                f"level.")


def coefficients(table: dict, screens: dict | None = None) -> dict:
    """Standard 2^3 contrasts on +/-1 coding, per response.

    Returns `{response: {term: beta}}` with terms "", "N", "C", "L", "NC",
    "NL", "CL", "NCL", the empty key being the grand mean, plus `_bound` and
    `_valid`. A response is scored only where it is VALID IN ALL EIGHT ARMS: a
    contrast over the arms whose control happened to close is not a contrast.
    `_invalid` names the arms that stopped it and why.

    `beta` is the HALF-effect: a factor whose 0 -> 1 step moves the response
    by `d` has `beta = d/2`.
    """
    arms = [a for a in ALGO_FACTORS if a in table]
    if len(arms) != 8:
        raise FactorialError(
            f"a 2^3 factorial needs all eight arms, got {len(arms)}: "
            f"{sorted(set(ALGO_FACTORS) - set(arms))} missing")
    names = "NCL"
    out = {}
    for response in RESPONSES:
        invalid = {a: table[a][response]["reason"] for a in arms
                   if not table[a][response]["valid"]}
        if invalid:
            # NO NUMBERS. The contract says a contrast is computed only where
            # the response is valid in all eight arms, and the previous version
            # computed it anyway and attached `_valid: false` -- so the JSON
            # carried a beta that a reader, a binding or a notebook could pick
            # up without ever consulting the flag. A refusal that still hands
            # over the answer is not a refusal.
            out[response] = dict.fromkeys(
                ["", "N", "C", "L", "NC", "NL", "CL", "NCL", "_bound"])
            out[response].update({"_valid": False, "_invalid": invalid})
            continue
        betas = {"_valid": True}
        for size in range(4):
            for subset in _subsets(names, size):
                acc = 0.0
                for arm in arms:
                    x = [2 * f - 1 for f in ALGO_FACTORS[arm]]   # 0/1 -> -1/+1
                    sign = 1
                    for ch in subset:
                        sign *= x[names.index(ch)]
                    acc += sign * table[arm][response]["value"]
                betas[subset] = acc / 8.0
        betas["_bound"] = sum(table[a][response]["screening_bound"]
                              for a in arms) / 8.0
        out[response] = betas
    return out


def conditionals(table: dict) -> dict:
    """The effect of each factor at each level of each other factor.

    Easier to read than a contrast and harder to overstate. An interaction
    coefficient says the effect DEPENDS on another factor; these say what the
    effect actually is on each side, and the two shapes a 2-factor interaction
    can take -- "X only acts while Y is off" and "X only acts while Y is on" --
    are different sentences that one `beta_XY` does not distinguish.

    A conditional is reported only where the four arms entering it are all
    valid, and `null` otherwise. That is what makes it useful when the full
    contrast is not scorable: on `g33_fixture_multisubcycle_v1` at mstep <= 10
    the C=0 half fails its mass control while the C=1 half closes, so
    `N_at_C1` is a controlled measurement of Arm N at high sub-step count even
    though `beta_N` is not.
    """
    names = "NCL"
    out = {}
    for response in RESPONSES:
        row = {}
        for i, x in enumerate(names):
            for j, y in enumerate(names):
                if i == j:
                    continue
                for level in (0, 1):
                    hi = [a for a in table if ALGO_FACTORS[a][i] == 1
                          and ALGO_FACTORS[a][j] == level]
                    lo = [a for a in table if ALGO_FACTORS[a][i] == 0
                          and ALGO_FACTORS[a][j] == level]
                    if not all(table[a][response]["valid"] for a in hi + lo):
                        row[f"{x}_at_{y}{level}"] = None
                        continue
                    row[f"{x}_at_{y}{level}"] = (
                        sum(table[a][response]["value"] for a in hi) / len(hi)
                        - sum(table[a][response]["value"] for a in lo) / len(lo))
        # ... and the SIMPLE effects underneath them. `N_at_C1` averages over
        # L, so an N x L interaction inside that half is hidden in the mean.
        # These are the two halves it is a mean of, and they are what says
        # whether quoting the average is safe (owner review §11).
        k = 2                       # the remaining factor, for each ordered pair
        for i, x in enumerate(names):
            for j, y in enumerate(names):
                if i == j:
                    continue
                z = names[3 - i - j] if {i, j} != {0, 1} else names[
                    [t for t in range(3) if t not in (i, j)][0]]
                zi = names.index(z)
                for ly in (0, 1):
                    for lz in (0, 1):
                        hi = [a for a in table if ALGO_FACTORS[a][i] == 1
                              and ALGO_FACTORS[a][j] == ly
                              and ALGO_FACTORS[a][zi] == lz]
                        lo = [a for a in table if ALGO_FACTORS[a][i] == 0
                              and ALGO_FACTORS[a][j] == ly
                              and ALGO_FACTORS[a][zi] == lz]
                        key = f"{x}_at_{y}{ly}_{z}{lz}"
                        if not all(table[a][response]["valid"] for a in hi + lo):
                            row[key] = None
                            continue
                        row[key] = (table[hi[0]][response]["value"]
                                    - table[lo[0]][response]["value"])
        out[response] = row
    return out


def _subsets(chars, size):
    """Subsets of `chars` of the given size, IN `chars` ORDER.

    Sorting alphabetically gave `CN` and `LN`, which name the same terms and
    read as different ones. The factor order is the experiment's, not the
    alphabet's.
    """
    return ["".join(c) for c in combinations(chars, size)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("arm", nargs="+", metavar="ARM=SINGLE,SPLIT",
                    help="one per arm: the two decompositions of that arm's run")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--window", action="store_true",
                    help="accumulate over the whole run instead of the matched "
                         "first call")
    args = ap.parse_args()

    table, identity, streams = {}, {}, {}
    for spec in args.arm:
        name, _, paths = spec.partition("=")
        if name not in ALGO_FACTORS:
            raise SystemExit(f"{name}: not an arm of this factorial")
        single, _, split = paths.partition(",")
        if not single or not split:
            raise SystemExit(f"{spec}: need ARM=SINGLE,SPLIT")
        s, pth = Path(single).read_text(), Path(split).read_text()
        identity[name] = check_identity(name, s, pth)
        same_input(name, s, pth)        # this arm's two decompositions
        streams[name] = s
        table[name] = responses(s, pth, window=args.window)

    ref = identity.get("legacy")
    if ref:
        for name, ident in identity.items():
            bad = [k for k, v in ref.items()
                   if k != "algorithm" and ident[k] != v]
            if bad:
                raise SystemExit(
                    f"{name} and legacy differ in {bad}: the arms are not one "
                    f"experiment")
    same_atmosphere(streams)        # raw initial + forcing, every arm
    beta = coefficients(table)
    cond = conditionals(table)

    span = "window" if args.window else "first-call"
    print(f"\n  SELECTED SPAN: {span}   "
          f"(each response also carries its own, below)\n")
    print("  " + f"{'arm':18s} {'NCL':>4s} " +
          " ".join(f"{k:>13s}" for k in RESPONSES))
    for arm in ALGO_FACTORS:
        n, c, l = ALGO_FACTORS[arm]
        cells = []
        for k in RESPONSES:
            r = table[arm][k]
            cells.append(f"{r['value']:13.5e}" if r["valid"] else f"{'--':>13}")
        print("  " + f"{arm:18s} {n}{c}{l:<2d} " + " ".join(cells))
    print(f"\n  {'response':28s} {'reader':10s} {'span':18s} {'ctrl':9s} "
          + " ".join(f"{t:>12s}" for t in ("N", "C", "L", "NC", "bound")))
    for response, (unit, owner, reader, ctrl, spanspec) in RESPONSES.items():
        b = beta[response]
        sp = span if spanspec == "selected" else spanspec
        cs = f"{ctrl[0]}/{ctrl[1]}" if ctrl else "-"
        if not b["_valid"]:
            why = sorted(set(b["_invalid"].values()))[0][:46]
            print(f"  {response:28s} {reader:10s} {sp:18s} {cs:9s} "
                  f"NOT SCORED: {why}")
            continue
        print(f"  {response:28s} {reader:10s} {sp:18s} {cs:9s} "
              + " ".join(f"{b[t]:12.4e}" for t in ("N", "C", "L", "NC"))
              + f" {b['_bound']:12.4e}")
    print("\n  Units differ between rows: compare terms WITHIN a response, "
          "never magnitudes across them.")
    print("  `D_*_metric` is the ENDPOINT-RECOVERED metric residual, a different"
          "\n  quantity from the actual-transfer budget rows above it.\n")

    doc = {"selected_span": span, "arms": ALGO_FACTORS, "identity": identity,
           "responses": table, "coefficients": beta, "conditionals": cond}
    if args.json:
        args.json.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
