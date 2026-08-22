#!/usr/bin/env python3
"""Convergence and energy budgets of one operator under timestep refinement.

Reads `G33R` streams from the refinement drivers and reports, per member:
successive-difference orders, rho*dz column budgets, branch topology, and the two
energy ledgers of owner review §8.

Two rules a reader must know, because breaking either silently produces a number
that looks like a result:

  * SWEEPS ARE DESIGNED ON dtcld, NOT delt. The kernel picks its own internal step
    (F:930-932), so N = 1,2,3,6,12 gives dtcld = 100,150,100,50,25 -- not a
    refinement sequence. N in {3,6,12,24,48,96} halves cleanly.
  * ORDERS COME ONLY FROM SUCCESSIVE DIFFERENCES. Against the finest member the
    exponent is biased upward: a first-order operator reads +1.222 then +1.585.

Both are derived, measured and argued in harness/evidence/
FINDING_refinement_design_v1.md; the ledger results are in
FINDING_moist_enthalpy_ledger_v1.md. This module does not restate them.
"""
from __future__ import annotations

import math
import re
import struct
import sys
from pathlib import Path

_STATE = re.compile(r"^G33R (STATE|INITIAL)\s+(\S+)\s+(\d+)\s+(-?\d+)\s+([0-9A-Fa-f]{8})$")
_PREC = re.compile(r"^G33R PREC\s+(\d+)\s+(\d+)\s+([0-9A-Fa-f]{8})$")
#: The forcing names this reader accepts. `xland` was added because `ncmin`
#: branches on the land mask (F:876-882) and Arm L is the correction to that
#: branch -- so an analysis comparing two decompositions could not check they
#: were handed the same mask, the one input L's causal story rests on.
#:
#: WIDENING, not tightening. Every stream published under the previous set
#: parses unchanged and no pinned figure moves; a name outside the set is still
#: refused, so a typo cannot enter as a silent new quantity.
_FORCING_NAMES = ("rho", "delz", "pii", "xland")
#: The fixture the run was built against. Additive: a stream without it parses
#: as before and reports `fixture: None`, so no published member is invalidated.
_FIXTURE = re.compile(r"^G33R FIXTURE\s+(\S+)$")
_FORCING = re.compile(r"^G33R FORCING\s+(" + "|".join(_FORCING_NAMES) +
                      r")\s+(\d+)\s+(-?\d+)\s+([0-9A-Fa-f]{8})$")

#: The water species, split by the phase the code's latent heats treat them as.
#: MASS is derived, not restated: two copies of one species list is how a species
#: gets added to only one of them.
LIQUID = ("qc", "qr")
ICE = ("qi", "qs", "qg")
MASS = ("qv",) + LIQUID + ICE

#: Reported separately from MASS. A mass field and a number moment can converge at
#: different rates, and averaging them hides exactly the number-moment behaviour
#: the conservative-nr blocker is about.
NUMBER = ("nc", "ni", "nr", "nccn")


def f32(bits: int) -> float:
    return struct.unpack("<f", struct.pack("<I", bits))[0]


#: A member is a COMPLETE state, not "at least one record".
STATE_FIELDS = ("th", "qv", "qc", "qr", "qi", "qs", "qg",
                "nccn", "nc", "ni", "nr", "bg")
# `\s+`: the Fortran `merge` pads the mode to a fixed width, so the emitted
# separator is not always one space. A single-space pattern rejected every
# real member -- which is the safe direction, but for the wrong reason.
_BEGIN = re.compile(r"^G33R BEGIN nsplit\s+(\d+)\s+(carry|rezero)\s+(\S+)"
                    r"(?:\s+delt\s+(\S+)\s+loops\s+(\d+)\s+dtcld\s+(\S+))?$")
_END = re.compile(r"^G33R END$")


class RefineError(Exception):
    """A member that cannot be analysed. Never downgraded to a warning."""


def _expect(cond, msg, path):
    if not cond:
        raise RefineError(f"{path}: {msg}")


def read(path: Path, *, nsplit=None) -> dict:
    """One member from a file."""
    return read_text(path.read_text(), nsplit=nsplit, label=str(path))


def read_text(text: str, *, nsplit=None, label: str = "<stream>") -> dict:
    """One member, or raise.

    Every check corresponds to a way a truncated, duplicated or mislabelled stream
    would otherwise read as a valid result -- always in the flattering direction,
    since a member missing records shows a SMALLER error (§2).

    Takes text rather than a path because the G33R and G33N records live in ONE
    driver stream, so an analysis holding that stream reads both without
    round-tripping a temporary file (owner §16-3).
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    begins = [ln for ln in lines if ln.startswith("G33R BEGIN")]
    ends = [ln for ln in lines if _END.match(ln)]
    _expect(len(begins) == 1, f"expected exactly 1 BEGIN, found {len(begins)}", label)
    _expect(len(ends) == 1, f"expected exactly 1 END, found {len(ends)} "
                            "(a truncated run has none)", label)
    m = _BEGIN.match(begins[0])
    _expect(m, f"unparseable BEGIN: {begins[0]!r}", label)
    got_n, mode, algo = int(m.group(1)), m.group(2), m.group(3)
    # delt/loops/dtcld are what the KERNEL actually used. Recording them makes the
    # dtcld design rule checkable from the output instead of recomputed from delt
    # by whoever reads the table (owner review §2.3).
    delt, loops, dtcld = m.group(4), m.group(5), m.group(6)
    # The TOKEN is the record, and it is validated here, where it still
    # exists (Codex): float() collapses "42.857142999999999999" and
    # "4.2857143E+01" onto the same double as "42.857143", so a guard on the
    # parsed value cannot tell the F0.6 channel's output from a forgery
    # claiming precision the channel never produced. The channel has TWO
    # producers with two canonical sub-one spellings: gfortran's F0.6 prints
    # .390625 (474/474 published Fortran header tokens measured), and the C++
    # driver's std::fixed/setprecision(6) prints 0.390625
    # (g33_refine_driver.cpp:217) -- a grammar fitted to one refused the
    # other's valid streams (Codex). What NEITHER can print stays refused: a
    # padded integer part like 00042.857143 or 042.857143.
    if delt is not None:
        for tok, nmm in ((delt, "delt"), (dtcld, "dtcld")):
            _expect(re.fullmatch(r"(?:0|[1-9]\d*)?\.\d{6}", tok),
                    f"{nmm} token {tok!r} is not a fixed-6 record", label)
    if nsplit is not None:
        _expect(got_n == nsplit,
                f"BEGIN says nsplit={got_n}, filename says {nsplit} "
                "(a member analysed under the wrong step)", label)

    bi, ei = lines.index(begins[0]), lines.index(ends[0])
    _expect(bi < ei, "END precedes BEGIN", label)
    _expect(not [ln for ln in lines[:bi] + lines[ei + 1:] if ln.startswith("G33R")],
            "G33R records outside BEGIN..END", label)

    out, seen = {}, set()
    for ln in lines[bi + 1:ei]:
        if not ln.startswith("G33R"):
            continue                     # non-record chatter inside the block
        if m := _STATE.match(ln):
            cls, fld, i, k, b = m.groups()
            key = (cls.lower(), fld, int(i), int(k))
        elif m := _PREC.match(ln):
            f, i, b = m.groups()
            key = ("prec", int(f), int(i))
        elif m := _FORCING.match(ln):
            nm, i, k, b = m.groups()
            key = ("forcing", nm, int(i), int(k))
        elif m := _FIXTURE.match(ln):
            out[("meta", "fixture")] = m.group(1)
            continue
        else:
            raise RefineError(f"{label}: unrecognised G33R record: {ln!r}")
        _expect(key not in seen,
                f"duplicate record {key} — a second value would silently "
                "overwrite the first", label)
        seen.add(key)
        v = f32(int(b, 16))
        _expect(v == v and abs(v) != float("inf"),
                f"non-finite value at {key}", label)
        out[key] = v

    fo = [k for k in out if k[0] == "forcing"]
    init = [k for k in out if k[0] == "initial"]
    st = [k for k in out if k[0] == "state"]
    pr = [k for k in out if k[0] == "prec"]
    fields = {k[1] for k in st}
    _expect(fields == set(STATE_FIELDS),
            f"state field set is {sorted(fields)}, expected {sorted(STATE_FIELDS)}",
            label)
    cells = {(k[2], k[3]) for k in st}
    _expect(len(st) == len(STATE_FIELDS) * len(cells),
            f"state records {len(st)} != {len(STATE_FIELDS)} fields x "
            f"{len(cells)} cells — the grid is ragged", label)
    cols = {k[2] for k in pr}
    _expect(len(pr) == 3 * len(cols),
            f"prec records {len(pr)} != 3 species x {len(cols)} columns", label)
    # rho/delz are optional so streams from before they were emitted still parse,
    # but if either is present BOTH must be complete -- a half-populated forcing
    # set would silently drop columns from a physical budget.
    if fo:
        names = {k[1] for k in fo}
        # Checking only the names PRESENT let a stream carrying rho but no delz
        # through, to fail later inside a column budget (owner §7.1). rho and delz
        # are the rho*dz measure and are all-or-nothing; `pii` is not, because the
        # enthalpy ledger already reports its own absence and some producers do
        # not emit it.
        _expect(("rho" in names) == ("delz" in names),
                f"forcing carries {sorted(names)}: rho and delz are the rho*dz "
                f"measure and must be present together", label)
        for nm in names:
            got = {(k[2], k[3]) for k in fo if k[1] == nm}
            _expect(got == cells,
                    f"forcing `{nm}` covers {len(got)} cells, state covers "
                    f"{len(cells)}", label)
    if init:
        # Counting records lets a member with the right NUMBER of wrong cells
        # through, and the initial state is what every budget is measured from.
        _expect({k[1:] for k in init} == {k[1:] for k in st},
                "initial state covers different (field, col, k) than the final "
                "state", label)
    # Every column must carry the same levels: a ragged column silently shortens
    # a column integral.
    per_col = {c: {k for cc, k in cells if cc == c} for c, _ in cells}
    _expect(len({tuple(sorted(v)) for v in per_col.values()}) == 1,
            f"columns carry different level sets: "
            f"{ {c: sorted(v) for c, v in per_col.items()} }", label)
    # Precipitation is three species over exactly the state's columns -- and
    # ABSENT is a state the stream must declare, not one it falls into. Guarding
    # this on `if pr` let a stream with no PREC at all through, because the older
    # count check then compared 0 against 3*0 (owner §7.2).
    want = {(sp, c) for sp in (1, 2, 3) for c, _ in cells}
    _expect({(k[1], k[2]) for k in pr} == want,
            f"prec covers {len(pr)} of the {len(want)} (species, column) pairs the "
            f"state requires; a stream without precipitation is not a refinement "
            f"member", label)
    out.setdefault(("meta", "fixture"), None)
    out[("meta", "nsplit")] = got_n
    out[("meta", "mode")] = mode
    out[("meta", "algorithm")] = algo
    if loops is not None:
        out[("meta", "delt")] = float(delt)
        out[("meta", "loops")] = int(loops)
        out[("meta", "dtcld")] = float(dtcld)
    return out


def steps(runs: dict) -> dict:
    """{member: the dtcld the kernel actually used}. Fail-closed (owner P0-1).

    Orders used to be computed from the FILENAME's N, on the assumption
    `dtcld = 300/N`. `loops = max(nint(delt/dtcldcr),1)` (F:930) breaks it:
    N = 1,2,3 gives dtcld = 100,150,100 s, so an N-ordered chain need not be a
    step-ordered one and "N doubled" need not mean "the step halved". The stream
    reports what the kernel ran; that is what an order is against.
    """
    out = {}
    for n, r in runs.items():
        h = r.get(("meta", "dtcld"))
        if h is None:
            raise RefineError(
                f"member N={n} reports no dtcld — this stream predates the field, "
                f"and an order cannot be taken against a step nobody recorded")
        if not (math.isfinite(h) and h > 0):
            raise RefineError(f"member N={n} reports dtcld={h}")
        out[n] = h
    return out


def require_orderable(runs: dict) -> None:
    """Additionally required before an ORDER may be taken (owner P0-1).

    Distinct steps are not a property of every useful bundle -- the N=1/N=3
    policy control deliberately runs the same dtcld twice -- but they are
    required here, because the error series are keyed BY step and two members at
    one step collide silently, one overwriting the other.
    """
    H, seen = steps(runs), {}
    for n, h in sorted(H.items()):
        dup = next((m for m, g in seen.items() if math.isclose(h, g, rel_tol=1e-12)),
                   None)
        if dup is not None:
            raise RefineError(
                f"members N={dup} and N={n} both ran dtcld={h:g} s — an error "
                f"series keyed by step cannot contain the same step twice")
        seen[n] = h


def require_comparable(runs: dict) -> None:
    """One experiment, not several (owner P0-1/P0-2).

    Everything here would otherwise surface as a plausible-looking table built
    from members that never described the same integration. Step DISTINCTNESS is
    not here: see `require_orderable`.
    """
    modes = {r[("meta", "mode")] for r in runs.values()}
    if len(modes) > 1:
        raise RefineError(f"members mix modes: {sorted(modes)}")
    horizons = {round(r[("meta", "delt")] * r[("meta", "nsplit")], 6)
                for r in runs.values() if ("meta", "delt") in r}
    if len(horizons) > 1:
        raise RefineError(
            f"members integrate different total times: {sorted(horizons)} s — "
            f"their difference is not a discretisation error")


def require_same_universe(runs: dict) -> None:
    """Same identities in every member, checked once up front.

    Comparing over an intersection lets an incomplete member report a smaller
    error -- convergence measured on absence.
    """
    keyed = {n: {k for k in r if k[0] != "meta"} for n, r in runs.items()}
    ref_n = min(keyed)
    for n, ks in keyed.items():
        if ks != keyed[ref_n]:
            miss, extra = keyed[ref_n] - ks, ks - keyed[ref_n]
            raise RefineError(
                f"member N={n} has a different record universe from N={ref_n}: "
                f"{len(miss)} missing, {len(extra)} extra")
    algos = {r[("meta", "algorithm")] for r in runs.values()}
    if len(algos) > 1:
        raise RefineError(f"members mix algorithms: {sorted(algos)}")
    require_comparable(runs)


def _norm(a: dict, b: dict, keys) -> float:
    """Max absolute difference over `keys` — not RMS, which on a mostly-quiet
    synthetic fixture would measure how many cells are quiet."""
    # No `if k in a and k in b` guard: `require_same_universe` has already
    # established both carry every key, and a silent skip here is exactly how a
    # missing record turns into a smaller error norm.
    return max((abs(a[k] - b[k]) for k in keys), default=0.0)


def _keys(run, group):
    if group == "prec":
        return [k for k in run if k[0] == "prec"]
    if group == "th":
        return [k for k in run if k[0] == "state" and k[1] == "th"]
    names = MASS if group == "mass" else NUMBER
    return [k for k in run if k[0] == "state" and k[1] in names]


GROUPS = ("th", "mass", "number", "prec")

#: Physical column budgets (§7): sum_k rho_k dz_k q, per column so one bad column
#: is not diluted by the rest. The grouped max norms above are over MIXING RATIOS
#: and are set by a single migrating cell; these are what conservation is about.


def column_budgets(run: dict) -> dict:
    """{(quantity, col): rho*dz-weighted column integral}, or {} without forcing."""
    if not any(k[0] == "forcing" for k in run):
        return {}
    cells = {(k[2], k[3]) for k in run if k[0] == "state"}
    cols = sorted({c for c, _ in cells})
    out = {}
    for c in cols:
        ks = sorted(k for cc, k in cells if cc == c)
        w = {k: run[("forcing", "rho", c, k)] * run[("forcing", "delz", c, k)]
             for k in ks}
        out[("water", c)] = sum(
            w[k] * sum(run[("state", f, c, k)] for f in MASS) for k in ks)
        for n in ("nr", "ni", "nc", "nccn"):
            out[(n, c)] = sum(w[k] * run[("state", n, c, k)] for k in ks)
    return out


def _halved(a: float, b: float) -> bool:
    return math.isclose(a, 2 * b, rel_tol=1e-9)


def _halving_pairs(runs: dict) -> list:
    """(coarse, fine) member pairs whose ACTUAL step halved — adjacent in
    decreasing step, and only where the step really is twice the next."""
    H = steps(runs)
    order = sorted(runs, key=lambda n: -H[n])
    return [(a, b) for a, b in zip(order, order[1:]) if _halved(H[a], H[b])]


def _order_table(runs: dict, title: str, head: str, rows) -> None:
    """Successive orders p = log2(E_h / E_{h/2}) for labelled series.

    `rows` yields (label, err) with `err(lo, hi)` the difference between two
    members — a max norm over cells for one caller, a column integral for the
    other, which is why the error function is the interface. A dash where either
    error is exactly zero: bit-identical members are the absence of a rate, not a
    rate of zero. All-dash rows carry no signal and are not printed.
    """
    pairs = _halving_pairs(runs)
    print(f"\n  {title}")
    H = steps(runs)
    print(f"    {head}" + "  ".join(f"{H[lo]:g}->{H[hi]:g}".rjust(13)
                                    for lo, hi in pairs[:-1]))
    for label, err in rows:
        cells = []
        for i, (lo, hi) in enumerate(pairs[:-1]):
            # The two pairs must SHARE their middle member. With actual steps
            # 100,50,40,20 the halving pairs are (100,50) and (40,20): adjacent in
            # the list, but E(100->50)/E(40->20) spans two different chains and is
            # not a rate. Only a dyadic run of three members gives one (owner P0-6).
            if hi != pairs[i + 1][0]:
                cells.append("      -      ")
                continue
            e, e2 = err(lo, hi), err(hi, pairs[i + 1][1])
            cells.append("      -      " if e == 0 or e2 == 0
                         else f"{math.log2(e / e2):+13.3f}")
        if any(c.strip() != "-" for c in cells):
            print(f"    {label} " + "  ".join(cells))


#: Above this relative spread across members, a column integral is varying enough
#: for its successive differences to plausibly be a discretisation signal. Below
#: it the members agree to within the chain's own scatter and an "order" on them
#: is describing that scatter. NOT a conservation criterion -- see the name.
_FLAT_SPREAD = 1e-4


def cross_member_endpoint_spread(b: dict, key) -> float:
    """(max-min)/|mean| of one column integral across the members.

    Renamed from `conservation_spread` (owner priority 4): it measures
    STEP-INSENSITIVITY, not conservation. Every member losing the same 1 kg/m2
    gives a spread of zero and a conservation residual of 1. Conservation is
    `water_residual` below, which needs the initial state and the outflow.
    """
    v = [b[n][key] for n in b]
    m = sum(v) / len(v)
    return (max(v) - min(v)) / abs(m) if m else 0.0


#: The two column measures (owner §9.2). The `q` fields are mixing ratios per
#: DRY-air kg while `rho` is MOIST density, so a physical kg m^-2 needs rho_d.
MEASURES = ("operator", "physical")


def _column_density(run: dict, c: int, k: int, basis: str) -> float:
    """rho_m as emitted, or rho_d = rho_m/(1+qv).

    The dry density is taken from the INITIAL qv and used at BOTH endpoints.
    That is the physical convention, not a shortcut: column microphysics
    transports no dry air, so rho_d*dz for a layer is invariant across the step.
    Recomputing it from the final qv would make the measure itself move with the
    process being measured, and a budget whose weights change is not a budget.
    """
    rho = run[("forcing", "rho", c, k)]
    if basis == "operator":
        return rho
    return rho / (1.0 + run[("initial", "qv", c, k)])


def water_residual(run: dict, c: int, basis: str = "operator") -> dict:
    """The actual column-water conservation residual for ONE member.

        R_W = (W_final - W_initial) + P_surface

    Zero if the column conserves water. This is what "conserved" means; the
    cross-member spread above cannot say it, because members that all lose the
    same amount agree with each other perfectly (owner §5).

    `P` is the WRF `rain` diagnostic, which is known to depart from the ρΔz
    budget (P0-4b), so a nonzero R_W here is the SUM of any genuine
    non-conservation and that diagnostic defect. Reported, not attributed.
    """
    if not any(k[0] == "initial" for k in run) or \
       not any(k[0] == "forcing" for k in run):
        return {}
    if basis not in MEASURES:
        raise ValueError(f"basis must be one of {MEASURES}, got {basis!r}")
    ks = sorted(k[3] for k in run if k[0] == "state" and k[1] == "qv" and k[2] == c)
    w = lambda cls: sum(_column_density(run, c, k, basis)
                        * run[("forcing", "delz", c, k)]
                        * run[(cls, f, c, k)] for f in MASS for k in ks)
    wi, wf, p = w("initial"), w("state"), total_precip(run, c)
    return {"W_initial": wi, "W_final": wf, "P": p,
            "residual": (wf - wi) + p,
            "relative": ((wf - wi) + p) / abs(wi) if wi else float("nan")}


def water_residual_report(runs: dict) -> None:
    H = steps(runs)
    rows = [(n, c, water_residual(runs[n], c))
            for n in sorted(runs)
            for c in sorted({k[2] for k in runs[n] if k[0] == "state"})]
    rows = [(n, c, d) for n, c, d in rows if d]
    if not rows:
        print("\n  water conservation: needs INITIAL and forcing")
        return
    print("\n  COLUMN WATER CONSERVATION   R_W = (W_final - W_initial) + P_surface")
    print("  P is the `rain` diagnostic, which departs from the rho*dz budget"
          " (P0-4b),")
    print("  so a nonzero R_W is that defect PLUS any true non-conservation.")
    print(f"    {'h (s)':>8} {'col':>3} {'W_initial':>13} {'R_W':>13} {'R_W/W_i':>11}")
    for n, c, d in rows:
        print(f"    {H[n]:8g} {c:3d} {d['W_initial']:13.6e} {d['residual']:13.5e} "
              f"{d['relative']:11.3e}")


def budget_report(runs: dict) -> None:
    b = {n: column_budgets(runs[n]) for n in sorted(runs)}
    if not b[min(b)]:
        print("\n  column budgets: forcing not present in this stream set")
        return
    keys = sorted(b[min(b)])                       # (quantity, column)
    # An order on a CONSERVED quantity is not a convergence rate. On this fixture
    # column water varies 0.6-1.0% across the chain at f32 but only 1e-6 at f64:
    # the f32 variation is precision drift, so the exponents describe that drift,
    # not the solution. Flag it rather than print a number that reads like a rate.
    flat = [k for k in keys if cross_member_endpoint_spread(b, k) < _FLAT_SPREAD]
    if flat:
        print(f"\n  STEP-INSENSITIVE across the chain (spread < {_FLAT_SPREAD:g}).")
        print("  This is NOT a conservation statement: every member losing the same")
        print("  amount gives zero spread and a nonzero residual. Successive")
        print("  differences here describe the chain's own scatter, not a rate:")
        for k in flat:
            print(f"    {k[0]:10} col {k[1]}   spread "
                  f"{cross_member_endpoint_spread(b, k):.3e}")
    water = [k for k in keys if k[0] == "water"]
    if water and any(cross_member_endpoint_spread(b, k) >= _FLAT_SPREAD for k in water):
        # A GENERIC statement about what this table can and cannot mean. The
        # earlier version asserted a specific fixture's f64 result here, so any
        # future stream -- another fixture, a real case -- would have been told
        # its water variation is precision drift on evidence that says nothing
        # about it (owner §7.1). The interpretation belongs to the evidence
        # bundle; the analyzer states the precondition for reading these numbers.
        print("\n  WATER ORDERS ARE A RATE ONLY IF THE VARIATION IS PHYSICAL. Column")
        print("  water is conserved apart from precipitation, so a member-to-member")
        print("  spread can be discretisation OR precision. Deciding needs the same")
        print("  chain at another precision (`refine_build.sh --f64`); on")
        print("  g33_fixture_multisubcycle_v1 that comparison attributed it to")
        print("  precision (FINDING_column_water_orders_v1). Do not carry that")
        print("  attribution to a stream it was not measured on.")
    _order_table(
        runs, "rho*dz column budgets — successive order per column",
        f"{'quantity':10} {'col':>3} ",
        ((f"{q:10} {c:3d}",
          lambda lo, hi, q=q, c=c: abs(b[lo][(q, c)] - b[hi][(q, c)]))
         for q, c in keys))


def successive(runs: dict) -> dict:
    """E_h = |X_h - X_{h/2}| for the doubling pairs this sweep contains."""
    H, pairs = steps(runs), _halving_pairs(runs)
    out = {}
    for g in GROUPS:
        out[g] = {H[lo]: _norm(runs[lo], runs[hi], _keys(runs[lo], g))
                  for lo, hi in pairs}
    return out


def to_finest(runs: dict) -> dict:
    """The finest member is the one with the SMALLEST STEP, which is not always
    the largest N (owner P0-1)."""
    H = steps(runs)
    finest = min(runs, key=lambda n: H[n])
    out = {}
    for g in GROUPS:
        out[g] = {H[n]: _norm(runs[n], runs[finest], _keys(runs[n], g))
                  for n in sorted(runs) if n != finest}
    return out


def orders(series: dict) -> list:
    """p = log2(E_h / E_{h/2}) for each adjacent halving present.

    Reported as None when either error is exactly zero: a zero difference means
    the two members agree to the last bit, which is not an order-0 convergence
    rate, it is an absence of the signal the rate describes.
    """
    hs = sorted(series, reverse=True)
    out = []
    for h, hh in zip(hs, hs[1:]):
        if not _halved(h, hh):
            continue
        e, ee = series[h], series[hh]
        out.append((h, e, ee, None if e == 0 or ee == 0 else math.log2(e / ee)))
    return out


def report(runs: dict, label: str) -> None:
    H = steps(runs)
    print(f"\n=== {label} ===")
    print(f"    members: N = {sorted(runs)}  "
          f"(dtcld = {[round(H[n], 4) for n in sorted(runs)]} s, as the kernel ran them)")
    # (label, series, may_report_order). The flag is the point of this table:
    # an order from the error-to-finest series is biased upward and was misread
    # once already, so which series may carry one is fixed here rather than left
    # to the caller.
    for name, series, ordered in (
            ("successive |X_h - X_h/2|   (order estimated HERE)",
             successive(runs), True),
            (f"error to finest (dtcld={min(H.values()):g}s)   magnitude + monotonicity only",
             to_finest(runs), False)):
        print(f"\n  {name}")
        for g in GROUPS:
            s = series[g]
            if not s:
                continue
            cells = "  ".join(f"h={h:g}:{v:.6e}" for h, v in sorted(s.items(), reverse=True))
            print(f"    {g:7} {cells}")
            if ordered:
                for h, e, ee, p in orders(s):
                    pt = "n/a (a member is bit-identical)" if p is None else f"{p:+.3f}"
                    print(f"            order {h:g}->{h/2:g}: p = {pt}")
            else:
                v = [s[h] for h in sorted(s, reverse=True)]
                mono = all(a >= b for a, b in zip(v, v[1:]))
                print(f"            monotone decreasing: {mono}"
                      f"   (no order: the finest member is not the exact solution)")


def per_field(runs: dict) -> None:
    """Order per FIELD, and which cell sets each group max.

    A grouped max norm reports one field at one cell, so if that cell migrates the
    group order is partly a record of the move (§7). Both are printed so the group
    numbers can be read against the fields they actually came from.
    """
    first = runs[min(runs)]
    fields = sorted({k[1] for k in first if k[0] == "state"})
    _order_table(
        runs, "per-field successive order", f"{'field':6} ",
        ((f"{f:6}",
          lambda lo, hi, f=f: _norm(runs[lo], runs[hi],
                                    [x for x in runs[lo]
                                     if x[0] == "state" and x[1] == f]))
         for f in fields))

    print("\n  cell setting each group max (a moving cell makes the group order "
          "partly a record of the move)")
    for g in GROUPS:
        if g == "prec":
            continue
        trail = []
        for lo, hi in _halving_pairs(runs):
            _, best = max((abs(runs[lo][x] - runs[hi][x]), x)
                          for x in _keys(runs[lo], g))
            trail.append(f"{best[1]}/c{best[2]}k{best[3]}")
        print(f"    {g:7} " + " -> ".join(trail))


#: Above this a species counts as PRESENT. The kernel's own qmin; a crossing of it
#: between two members is a branch the arithmetic took differently, not a smaller
#: number.
_PRESENCE_EPS = 1.0e-12
T0C = 273.15


def topology(run: dict) -> dict:
    """FINAL-STATE PRESENCE PROXY -- not the branch topology (owner §8).

    A single |x| > 1e-12 across every field. The kernel's real gates are per field
    and per process (`qcrmin`, `qmin`/EPS, the qi threshold, `nrmin`/`ncmin`,
    complete evaporation, mstep/cap), and this sees only the FINAL state, so calling
    it "branch topology" overstates its scope. It was already promoted to a causal
    proof once and withdrawn; it must not be again.

    A classical order is only meaningful within one smooth branch (§5). This is
    ONE-SIDED: a difference between members proves the topology moved; agreement
    does not prove it stayed, since an intermediate flip can heal. The per-subcycle
    masks live inside the kernel and are not recoverable here.
    """
    if not any(k[0] == "forcing" and k[1] == "pii" for k in run):
        return {}
    cells = sorted({(k[2], k[3]) for k in run if k[0] == "state"})
    out = {}
    for c, k in cells:
        t = run[("state", "th", c, k)] * run[("forcing", "pii", c, k)]
        out[("cold", c, k)] = t <= T0C
        for f in MASS + ("nr", "ni", "nc"):
            out[(f, c, k)] = abs(run[("state", f, c, k)]) > _PRESENCE_EPS
    return out


def topology_report(runs: dict) -> None:
    H = steps(runs)
    ns = sorted(runs)
    t = {n: topology(runs[n]) for n in ns}
    if not t[ns[0]]:
        print("\n  topology: `pii` not present in this stream set")
        return
    ref = t[ns[0]]
    # A flip's MATERIALITY, not just its existence. On the arithmetic fixture the
    # qg flip that this record reports involves 3.9e-06 of the column water -- real
    # as a presence change, far too small to explain an O(1) change in a
    # convergence order. Printing the share stops the record being read as a
    # sufficient explanation for erratic exponents, which is how it was misread.
    def _share(n, fld, c):
        """rho*dz-WEIGHTED share of column water, which is this repo's declared
        column-water measure (docs/STATUS.md retired the unweighted layer sum).
        An unweighted version reads 3.884e-06 where the weighted one reads
        3.990e-06 on this fixture -- the conclusion is unchanged, but the
        withdrawal it supports depends on this magnitude, so it must be the
        physical measure rather than one that happens to agree."""
        r = runs[n]
        ks = sorted({k[3] for k in r if k[0] == "state"})
        if not all(("forcing", "rho", c, k) in r for k in ks):
            return float("nan")          # cannot weight: say so, do not fall back
        w = {k: r[("forcing", "rho", c, k)] * r[("forcing", "delz", c, k)] for k in ks}
        tot = sum(w[k] * sum(r[("state", f, c, k)] for f in MASS) for k in ks)
        return (sum(w[k] * r[("state", fld, c, k)] for k in ks) / tot) if tot else 0.0

    print(f"\n  final-state presence proxy, against the coarsest member "
          f"(N={ns[0]}) — NOT the branch topology")
    any_diff = False
    for n in ns[1:]:
        diff = sorted(k for k in ref if ref[k] != t[n][k])
        if diff:
            any_diff = True
            # max over BOTH members: a flip means the species is absent in one of
            # them, so measuring only the finer one always reports zero.
            worst = max((max(_share(n, a, b), _share(ns[0], a, b))
                         for a, b, _ in diff if a != "cold"), default=0.0)
            print(f"    N={n:3d} (h={H[n]:g}s): {len(diff)} flips  " +
                  ", ".join(f"{a}@c{b}k{c}" for a, b, c in diff[:6]) +
                  f"   [largest flipping species is {worst:.2e} of its column water]")
        else:
            print(f"    N={n:3d} (h={H[n]:g}s): identical")
    if not any_diff:
        print("    -> the FINAL topology is stable across the whole chain. That is "
              "consistent\n       with the exponents being rates, and does not "
              "establish it: an\n       intermediate flip can heal before the end.")


# ── physical moist-enthalpy ledger (owner review §8.2) ───────────────────────
#
# All from module_model_constants.F, the authority both legs compile against:
CPD, CPV = 7 * 287.0 / 2, 4 * 461.6      # 1004.5, 1846.4  (F:20, F:24)
CLIQ, CICE = 4190.0, 2106.0              # F:27, F:28
XLV, XLF, XLS = 2.5e6, 3.5e5, 2.85e6     # F:55, F:56, F:54
# XLS - XLV == XLF exactly, so the set is self-consistent at T0 and the reference
# enthalpies below cannot disagree with the code's own latent heats at T0.

def _enthalpies(t: float) -> tuple:
    """h_d, h_v, h_l, h_i at T, referenced to T0, per-phase heat capacities.

    Reproduces the code's latent heats at T0 (h_v-h_l = XLV, h_l-h_i = XLF) but
    NOT its temperature dependence -- that gap is what §8.2 measures.
    """
    dt = t - T0C
    return CPD * dt, CPV * dt + XLV, CLIQ * dt, CICE * dt - XLF


def outflow_split(run: dict, c: int, ks) -> dict:
    """-dW_col decomposed into what the diagnostic reports leaving at the bottom
    and what is unaccounted (owner P0-4).

        -dW_col = P_bottom + D_internal

    On this fixture D_internal is ~0 for the conservative interface (roundoff) and
    NEGATIVE for legacy -- the diagnostic reports MORE outflow than the column lost,
    which is the opposite sign from the P0-4b real-case defect where column loss
    EXCEEDED the diagnostic. Because the ledger charges `-dW_col` and not the
    diagnostic, it never charges phantom mass; what remains open is the LEVEL the
    departing water is charged at, which `_ledger` reports as a band.
    """
    w = _water_out(run, c, ks)
    p = total_precip(run, c)
    return {"water_out": w, "P_bottom": p, "D_internal": w - p,
            "D_share": (w - p) / w if w else float("nan")}


def _ledger(run: dict, h_cell, h_precip_out, basis: str = "operator",
            sink=None) -> dict:
    """residual = (H_end - H_start) + H carried out by precipitation, per column.

    Zero with no external forcing. The two ledgers differ ONLY in `h_cell` and
    `h_precip_out`, so their physics sits side by side and can be compared by
    reading it.
    """
    if not any(k[0] == "initial" for k in run) or \
       not any(k[0] == "forcing" and k[1] == "pii" for k in run):
        return {}
    cells = {(k[2], k[3]) for k in run if k[0] == "state"}
    out = {}
    for c in sorted({x for x, _ in cells}):
        ks = sorted(k for cc, k in cells if cc == c)

        def H(cls):
            return sum(_column_density(run, c, k, basis)
                       * run[("forcing", "delz", c, k)]
                       * h_cell(run, cls, c, k) for k in ks)

        # `pii` increases downward, so the larger one is the bottom level.
        kbot = ks[-1] if run[("forcing", "pii", c, ks[0])] < \
            run[("forcing", "pii", c, ks[-1])] else ks[0]
        h_start = H("initial")
        col_sink = (sink or {}).get(c)
        d = {"dH": H("state") - h_start,
             "H_precip_out": h_precip_out(run, c, kbot, ks, basis, col_sink),
             # What the charge was applied TO, so a reader can see the mass
             # behind the energy without re-deriving the budget.
             "water_out": _water_out(run, c, ks, basis),
             "H_start": h_start}
        d["residual"] = d["dH"] + d["H_precip_out"]
        d["relative"] = d["residual"] / abs(h_start) if h_start else float("nan")
        # THROUGHPUT norm (owner §6.4). `h_start` carries the column's whole
        # background sensible energy and an enthalpy-reference offset, so
        # dividing by it makes a process-scale error look small however large it
        # is next to the process. The denominator here is what actually moved.
        d["eta"] = abs(d["residual"]) / (abs(d["dH"]) + abs(d["H_precip_out"])
                                         or float("inf"))
        # MODELLING BAND, not an error bar. The departing water is charged at the
        # bottom-level temperature; nothing in the endpoint data says it left from
        # there. Recomputing the residual with every level in turn bounds how much
        # that choice is worth. On this fixture it is 15% of the legacy column-2
        # residual and 131% of the conservative one -- large enough that a point
        # value would overstate the comparison (owner P0-4).
        band = []
        for k in ks:
            alt = h_precip_out(run, c, k, ks, basis, col_sink)
            band.append((d["dH"] + alt) / abs(h_start) if h_start else float("nan"))
        d["relative_band"] = (min(band), max(band))
        out[c] = d
    return out


def _t(run: dict, cls: str, c: int, k: int) -> float:
    return run[(cls, "th", c, k)] * run[("forcing", "pii", c, k)]


def _h_consistent(run, cls, c, k) -> float:
    """h = h_d + qv h_v + ql h_l + qi h_i, per-phase heat capacities (§8.2)."""
    hd, hv, hl, hi = _enthalpies(_t(run, cls, c, k))
    return (hd + run[(cls, "qv", c, k)] * hv
            + sum(run[(cls, f, c, k)] for f in LIQUID) * hl
            + sum(run[(cls, f, c, k)] for f in ICE) * hi)


def _water_out(run, c, ks, basis: str = "operator") -> float:
    """Water that actually LEFT the column, from the rho*dz budget.

    NOT the fallout diagnostic. docs/STATUS.md records that the diagnostic and the
    column water loss disagree by an O(1) amount (P0-4b, the inflow cap), and a
    ledger built on the diagnostic inherits that defect instead of measuring
    thermodynamics: for legacy the diagnostic flux term is 4-7x the enthalpy change,
    so the residual becomes a restatement of the diagnostic error. Measured on this
    fixture, switching to the budget moves legacy's column-2 residual from
    -1.27e-02 to +9.8e-04 and removes essentially all of the apparent gap to the
    conservative interface.
    """
    # The BASIS must match the endpoints it is differenced against (owner P0-3).
    # This was fixed at moist density while `_ledger` weighted its endpoints by
    # rho_d under `physical`, so the "physical enthalpy residual" differenced a
    # DRY column change against a MOIST outflow -- a mixed measure, not a dry
    # closure.
    return -sum(_column_density(run, c, k, basis) * run[("forcing", "delz", c, k)]
                * sum(run[("state", f, c, k)] - run[("initial", f, c, k)] for f in MASS)
                for k in ks)


#: WRF convention, and it is NOT three disjoint species. F:1462-1464:
#:
#:     fallsum     = fall(1)+fall(2)+fall(3)+fall(4)   -> rain    == the TOTAL
#:     fallsum_qsi = fall(2)+fall(4)                   -> snow    == a SUBSET
#:     fallsum_qg  = fall(3)                           -> graupel == a SUBSET
#:
#: So `rain` is the total surface fallout of all four species and `snow`/`graupel`
#: are components of it. Summing the three double-counts the frozen part -- which is
#: what an earlier version of this module did, producing a spurious ~2x offset
#: against the column water budget that was nearly explained away as a convention.
def total_precip(run, c) -> float:
    """Total surface fallout in column `c` — `rain` alone, never a sum."""
    return run[("prec", 1, c)]


def _ice_fraction(run, c) -> float:
    """Frozen share of the departing water: (snow + graupel) / total."""
    tot = total_precip(run, c)
    return (run[("prec", 2, c)] + run[("prec", 3, c)]) / tot if tot else 0.0


def _sink_enthalpy(sink, *, arrival: bool = False) -> float:
    """Enthalpy carried by the internal mass defect, charged AT the interface.

    `sink` is a sequence of `g33_cap_interface.Sink` -- read by attribute
    (`signed`, `phase`, `t_up`, `t_lo`) rather than imported, so the dependency
    stays one-way.

    SIGNED, not gross: an interface that created mass is charged negatively, or
    the ledger does not close. `arrival` charges at the lower cell instead of
    the upper; the two BOUND the attribution, because a numerical annihilation
    has no single true location (owner §16-4 P0-1).

    The temperature is THIS CALL's pre-sedimentation value, not the window's
    initial one -- on column 3 those are 1.77 K apart by call 12.
    """
    total = 0.0
    for s in sink or ():
        t = s.t_lo if arrival else s.t_up
        if t is None:
            raise RefineError(
                "the internal-cap enthalpy needs the interface temperature, "
                "and this stream's stage records carry no `t`. The MASS sink is "
                "still measurable; the enthalpy charge is not.")
        _, _, hl, hi = _enthalpies(t)
        total += s.signed * (hi if s.phase == "ice" else hl)
    return total


def _precip_consistent(run, c, kbot, ks, basis="operator", sink=None) -> float:
    """Water leaving the column carries liquid or ice enthalpy out with it.

    With `sink` the charge is SPLIT (owner §16-4): water destroyed at an
    internal interface never reached the surface, so charging it at the
    bottom-level temperature and the surface phase fraction is wrong on both
    counts. An EMPTY sink is exactly the previous behaviour -- the whole column
    loss charged at the bottom -- so the two are comparable rather than swapped.
    """
    w = _water_out(run, c, ks, basis)
    _, _, hl, hi = _enthalpies(_t(run, "state", c, kbot))
    f = _ice_fraction(run, c)
    internal_mass = sum(s.signed for s in sink or ())
    # What crossed the surface is the column loss MINUS what never got there.
    return (w - internal_mass) * ((1.0 - f) * hl + f * hi) + _sink_enthalpy(sink)


def enthalpy_ledger(run: dict, basis: str = "operator", sink=None) -> dict:
    """Residual against CONSISTENT thermodynamics (§8.2).

    Approximate — dry-air mixing ratios against moist rho, precipitation flux at
    the bottom level — but identically so for every leg, so residuals COMPARE even
    where an absolute value would not.
    """
    return _ledger(run, _h_consistent, _precip_consistent, basis, sink)


# The code's own thermodynamics (module_mp_kdm6.F): cpmcal F:818, xlcal F:819,
# xlv1 = cl - cpv F:3406, and ONE cpm for the whole parcel rather than per-phase
# heat capacities (F:886-888). Reproducing the approximation is the point.
XLV1 = 4190.0 - 4 * 461.6      # cl - cpv = 2343.6, the slope §3.1 is about


def _code_coeffs(t: float, qv: float, qmin: float = 1.0e-32) -> tuple:
    q = max(qv, qmin)
    cpm = CPD * (1.0 - q) + q * CPV
    xl = XLV - XLV1 * (t - T0C)
    return cpm, xl, XLS - xl


def _h_code(run, cls, c, k) -> float:
    """h_op = cpm(qv)(T-T0) + xl(T) qv - xlf(T) q_ice — the code's own potential.

    Its heat updates all have the form `cpm dT = L dq`, so a conversion leaves this
    flat: vapour->liquid gives `cpm dT + xl dqv = 0`, liquid->ice gives
    `cpm dT - xlf dq_ice = 0`. Liquid's coefficient is zero because the code applies
    no latent heat to it.
    """
    t = _t(run, cls, c, k)
    qv = run[(cls, "qv", c, k)]
    cpm, xl, xlf = _code_coeffs(t, qv)
    return cpm * (t - T0C) + xl * qv - xlf * sum(run[(cls, f, c, k)] for f in ICE)


def _precip_code(run, c, kbot, ks, basis="operator", sink=None) -> float:
    """Sedimentation removes mass with no temperature change, so departing ice
    carries -xlf out and departing rain carries nothing -- the same convention the
    code's own updates imply. Departing water from the budget, not the diagnostic
    (see `_water_out`)."""
    _, _, xlf = _code_coeffs(_t(run, "state", c, kbot),
                             run[("state", "qv", c, kbot)])
    # `sink` is accepted and ignored: this ledger charges departing ice -xlf
    # whatever level it left from, so the split has nothing to move.
    return _water_out(run, c, ks, basis) * _ice_fraction(run, c) * -xlf


def operator_ledger(run: dict, basis: str = "operator") -> dict:
    """Residual against the code's OWN equations (§8.1).

    xl/xlf at the LOCAL temperature for every leg: the reference holds them at
    kernel entry and the port refreshes per sub-cycle, so one convention here keeps
    the ledger from encoding the answer to the question it is measuring.
    """
    return _ledger(run, _h_code, _precip_code, basis)


def ledger_report(runs: dict) -> None:
    """Both ledgers, one table shape, different physics — the point of running two:
    §8.2 asks whether the code agrees with consistent thermodynamics, §8.1 whether
    it agrees with its own equations, and they can disagree."""
    H = steps(runs)
    ns = sorted(runs)
    for title, ledger in (
            ("moist-enthalpy column residual   (dH + H_precip_out; zero if closed)",
             enthalpy_ledger),
            ("OPERATOR-consistency residual   (code's own cpm/xl; §8.1)",
             operator_ledger)):
        L = {n: ledger(runs[n]) for n in ns}
        if not L[ns[0]]:
            print("\n  ledger: initial state or `pii` missing")
            return
        print(f"\n  {title}")
        print(f"    {'h (s)':>7} {'col':>3} {'residual [J/m2]':>18} "
              f"{'/H_start':>11} {'eta':>9}   modelling band")
        for n in ns:
            for c in sorted(L[n]):
                d = L[n][c]
                lo, hi = d["relative_band"]
                print(f"    {H[n]:7g} {c:3d} {d['residual']:18.6e} "
                      f"{d['relative']:11.3e} {d['eta']:8.2%}   [{lo:.2e},{hi:.2e}]")
        print("    eta = |R| / (|dH| + |H_out|), the THROUGHPUT norm: /H_start divides")
        print("    a process-scale error by the column's whole background energy.")


def diagnostic_budget_consistency_report(runs: dict) -> None:
    """Does the fallout diagnostic agree with the column-water budget in THIS run?

    Named for what it measures (owner §10). A ratio of 1 means the diagnostic IS the
    budget and may be used as a physical quantity -- it says nothing about whether
    the precipitation is meteorologically right.

    Three separate conclusions in this evidence set were wrong because the fallout
    diagnostic was read as if it were the water that left the column. P0-4b records
    that they disagree by an O(1) amount; measured here the disagreement is a strong
    function of the timestep AND changes sign with the frozen fraction — the
    pure-liquid column under-reports by 19% while 97%-frozen columns over-report by
    9x. Printing the ratio makes that visible before anyone builds on it, instead of
    after.

    1.0 means the diagnostic IS the budget for that column and may be used as one.
    """
    H = steps(runs)
    ns = sorted(runs)
    if not any(k[0] == "initial" for k in runs[ns[0]]):
        print("\n  diagnostic trust: no INITIAL records, cannot compare")
        return
    cols = sorted({k[2] for k in runs[ns[0]] if k[0] == "state"})
    print("\n  fallout diagnostic / column water loss   "
          "(1.0 = the diagnostic IS the budget)")
    print(f"    {'h (s)':>7} " + " ".join(f"{'col'+str(c):>9}" for c in cols))
    for n in ns:
        r = runs[n]
        ks = sorted({k[3] for k in r if k[0] == "state"})
        row = []
        for c in cols:
            w = _water_out(r, c, ks)
            row.append(f"{total_precip(r, c) / w:9.4f}" if w else "        -")
        print(f"    {H[n]:7g} " + " ".join(row))


def main(argv) -> int:
    if not argv:
        print(__doc__)
        return 2
    d = Path(argv[0])
    runs = {}
    for p in sorted(d.glob("n*.rezero.txt")):
        n = int(re.match(r"n(\d+)\.", p.name).group(1))
        runs[n] = read(p, nsplit=n)
    if len(runs) < 2:
        raise SystemExit(f"need at least two members, found {sorted(runs)}")
    require_same_universe(runs)
    # A bundle that cannot carry an order is still worth reading: the N=1/N=3
    # policy control deliberately runs one step twice. Refuse the ORDER tables,
    # which are keyed by step and would silently collide, and print the rest.
    try:
        require_orderable(runs)
    except RefineError as e:
        print(f"\n=== {d.name} ===\n  NO ORDERS: {e}\n"
              f"  Reporting only the sections that do not key on the step.")
    else:
        report(runs, d.name)
        per_field(runs)
        budget_report(runs)
    water_residual_report(runs)
    topology_report(runs)
    ledger_report(runs)
    diagnostic_budget_consistency_report(runs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
