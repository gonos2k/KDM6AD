"""The N x C x L factorial: one span per table, and each response in its own terms.

Two corrections have already been made here and are kept. The response is
SIGNED, because `|R|` hides sign reversal and turns cancellation into apparent
effect. And the coefficients are the standard 2^3 contrasts,

    beta_S = (1/8) sum over arms of (prod_{j in S} x_j) * Y

computed rather than eyeballed, after "cross terms are at roundoff" was
published about a table whose own `I_NC` was 0.0235.

This version fixes what those corrections did not reach.

ONE SPAN PER TABLE. `window` selected the span for the four residual responses
and nothing else: `cap_sink` walked the whole stream and `partition` counted
every split, in BOTH tables. Measured, the two were bit-identical across the two
spans -- which read as "the trajectory does not move them" and was really "the
same whole-window number printed twice". So the first-call table was a hybrid,
and no statement about C or L in it was a first-call statement. Every response
now takes the same span, and the span is part of the result.

THE CAP RESPONSE IS NOT ONE SCALAR. `Sink.signed` says in its own docstring
that it is a SIGNED DEFECT and not a sink -- destruction and creation are
opposite signs of one number, and the type offers `destroyed`/`created`
separately for exactly that reason. Summing every chain and column into one
signed scalar hides both the cancellation and the direction, and a reversal
from +2.435 to -3.400 was read as C "doing its job". The cap is reported per
CHAIN, as signed, destroyed and created, and normalised by that chain's own
starting inventory so it is a number in the same terms as the residuals.

COVERAGE IS A RESULT, NOT A DEFAULT. `column()` refuses mstep > 1, and the old
code turned an empty row set into `0.0` -- indistinguishable from a residual
that really vanished. Eligibility is counted against what the span should have
produced, and an incomplete table is refused.

NUMERATOR AND DENOMINATOR ARE SEPARATE RESPONSES. A ratio can move because the
defect moved or because the inventory did, and one number cannot say which.

RESPONSES ARE NOT COMPARABLE ACROSS ROWS. Each carries its unit. A coefficient
on a dimensionless ratio and one on a mass term are not the same kind of
quantity, so nothing here reports a "largest effect in the table".
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

#: response -> (unit, which factor it is the NATIVE invariant of, or None).
#: The unit is carried so that nothing compares magnitudes across rows.
RESPONSES = {
    "R_nr_num": ("number m-2", "N"),
    "R_nr_den": ("number m-2", None),
    "R_nr": ("dimensionless", "N"),
    "R_ni_num": ("number m-2", "N"),
    "R_ni_den": ("number m-2", None),
    "R_ni": ("dimensionless", "N"),
    "R_qr_num": ("kg m-2", None),
    "R_qr_den": ("kg m-2", None),
    "R_qr": ("dimensionless", None),
    "R_qi_num": ("kg m-2", "C"),
    "R_qi_den": ("kg m-2", None),
    "R_qi": ("dimensionless", "C"),
    "cap_main_signed": ("kg m-2", "C"),
    "cap_main_destroyed": ("kg m-2", "C"),
    "cap_main_created": ("kg m-2", "C"),
    "cap_main_signed_rel": ("dimensionless", "C"),
    "cap_ice_signed": ("kg m-2", "C"),
    "cap_ice_destroyed": ("kg m-2", "C"),
    "cap_ice_created": ("kg m-2", "C"),
    "cap_ice_signed_rel": ("dimensionless", "C"),
    "partition_first": ("count", "L"),
    "partition_endpoint": ("count", "L"),
    "partition_path": ("count", "L"),
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


def _residual(span, species):
    """Signed residual, starting inventory, and the coverage behind them."""
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
            num += row["residual"]              # SIGNED
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


def _states(text: str) -> dict:
    """`(split, col, level) -> final state`, for every split in the run."""
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


def _partition(single: str, split: str) -> dict:
    """Three partition responses, over an EXACT common universe.

    The universe was intersected before, so a split stream missing a column or
    a sub-step compared fewer states and reported BETTER invariance. That is
    fail-open: the count a missing state reduces is the count the response is.
    A universe mismatch is refused.

    Three quantities, because they are three questions. `first` is the state
    after one sub-step, where the two decompositions still meet the same
    atmosphere. `endpoint` is the final state, which is what a forecast would
    carry. `path` is how often they differed anywhere along the way, and is
    the count the earlier table reported without saying which of the three it
    was.
    """
    a, b = _states(single), _states(split)
    if set(a) != set(b):
        missing = sorted(set(a) - set(b))[:2]
        extra = sorted(set(b) - set(a))[:2]
        raise FactorialError(
            f"the two decompositions do not describe the same states: "
            f"{len(set(a) - set(b))} missing (e.g. {missing}), "
            f"{len(set(b) - set(a))} extra (e.g. {extra}). Comparing the "
            f"intersection would report better invariance for a shorter run.")
    splits = sorted({k[0] for k in a})
    if not splits:
        raise FactorialError("no sub-step states recovered from either stream")
    lo, hi = splits[0], splits[-1]
    return {
        "partition_first": float(sum(1 for k in a if k[0] == lo and a[k] != b[k])),
        "partition_endpoint": float(sum(1 for k in a if k[0] == hi and a[k] != b[k])),
        "partition_path": float(sum(1 for k in a if a[k] != b[k])),
    }


def responses(stream_single: str, stream_split: str, *,
              window: bool = False) -> dict:
    """The full signed response vector for one arm, on ONE span.

    `window=True` accumulates across the whole run; the default is the first
    call, where every arm meets the same initial state so a difference is the
    arm and nothing else. After it the arms hold different fields, so the
    window is a different question rather than a longer version of the first.
    """
    import g33_number_transport as nt
    calls = nt.calls(stream_single)
    span = calls if window else calls[:1]
    span_calls = frozenset(range(1, len(span) + 1))

    out, meta = {}, {"span": "window" if window else "first-call",
                     "calls_in_span": len(span), "calls_in_stream": len(calls),
                     "screen": {}, "coverage": {}}
    starts = {}
    for species in ("nr", "ni", "qr", "qi"):
        r = _residual(span, species)
        if r["eligible"] != r["expected"]:
            raise FactorialError(
                f"{species}: {r['eligible']} of {r['expected']} (call, column) "
                f"rows are recoverable on this span -- `column()` refuses "
                f"mstep > 1, and a ratio taken over the rows that happened to "
                f"survive is not the span's residual. Use an analyzer that "
                f"reads the actual transfers.")
        out[f"R_{species}_num"] = r["num"]
        out[f"R_{species}_den"] = r["den"]
        out[f"R_{species}"] = r["num"] / r["den"] if r["den"] else 0.0
        starts[CHAIN_OF[species]] = r["den"] if species.startswith("q") else \
            starts.get(CHAIN_OF[species])
        meta["coverage"][species] = {"eligible": r["eligible"],
                                     "expected": r["expected"]}
        meta["screen"][f"R_{species}_num"] = _screen(r["sum_abs"], r["terms"])
        meta["screen"][f"R_{species}_den"] = _screen(r["sum_abs"], r["terms"])
        meta["screen"][f"R_{species}"] = (
            _screen(r["sum_abs"], r["terms"]) / abs(r["den"]) if r["den"] else 0.0)

    cap = _cap(stream_single, span_calls)
    for chain in ("main", "ice"):
        c = cap[chain]
        for what in ("signed", "destroyed", "created"):
            out[f"cap_{chain}_{what}"] = c[what]
            meta["screen"][f"cap_{chain}_{what}"] = _screen(c["sum_abs"],
                                                            c["terms"])
        # Normalised by the chain's OWN starting mass, so the cap is readable
        # beside that chain's residual instead of in units of its own.
        base = starts.get(chain)
        out[f"cap_{chain}_signed_rel"] = c["signed"] / base if base else 0.0
        meta["screen"][f"cap_{chain}_signed_rel"] = (
            _screen(c["sum_abs"], c["terms"]) / abs(base) if base else 0.0)

    part = _partition(stream_single, stream_split)
    out.update(part)
    for k in part:
        meta["screen"][k] = 0.0        # integer counts; exact, not screened
    meta["cap_interfaces"] = {c: cap[c]["terms"] for c in cap}
    out["_meta"] = meta
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
    return {"algorithm": a["algorithm"], "nsplit": a["nsplit"],
            "mode": a["carry"], "rho": a["rho"], "width": a["width"],
            "levels": a["levels"], "tiles_single": a["tile_sizes"],
            "tiles_split": b["tile_sizes"]}


def same_atmosphere(table: dict) -> None:
    """Every arm must have met the same initial state, or the design is not one.

    The first call's starting inventory is the atmosphere each arm was handed.
    Two arms that started differently cannot have their difference attributed
    to the factor that names them.
    """
    keys = [k for k in RESPONSES if k.endswith("_den")]
    ref = None
    for arm, row in table.items():
        got = tuple(row[k] for k in keys)
        if ref is None:
            ref, ref_arm = got, arm
        elif got != ref:
            bad = [k for k, x, y in zip(keys, got, ref) if x != y]
            raise FactorialError(
                f"{arm} and {ref_arm} did not start from the same atmosphere: "
                f"{bad} differ. On the first call that is a broken control; "
                f"over the window it is expected, and the window table must "
                f"not be checked with this.")


def coefficients(table: dict, screens: dict | None = None) -> dict:
    """Standard 2^3 contrasts on +/-1 coding, per response.

    Returns `{response: {term: beta}}` with terms "", "N", "C", "L", "NC",
    "NL", "CL", "NCL", the empty key being the grand mean. With `screens`
    (response -> per-arm screening scale) each response also carries
    `_bound`, the scale below which its coefficients say nothing.

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
        betas = {}
        for size in range(4):
            for subset in _subsets(names, size):
                acc = 0.0
                for arm in arms:
                    x = [2 * f - 1 for f in ALGO_FACTORS[arm]]   # 0/1 -> -1/+1
                    sign = 1
                    for ch in subset:
                        sign *= x[names.index(ch)]
                    acc += sign * table[arm][response]
                betas[subset] = acc / 8.0
        if screens:
            betas["_bound"] = sum(screens[arm].get(response, 0.0)
                                  for arm in arms) / 8.0
        out[response] = betas
    return out


def conditionals(table: dict) -> dict:
    """The effect of each factor at each level of each other factor.

    Easier to read than a contrast and harder to overstate. An interaction
    coefficient says the effect DEPENDS on another factor; these say what the
    effect actually is on each side, and the two shapes a 2-factor interaction
    can take -- "X only acts while Y is off" and "X only acts while Y is on" --
    are different sentences that one `beta_XY` does not distinguish.
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
                    row[f"{x}_at_{y}{level}"] = (
                        sum(table[a][response] for a in hi) / len(hi)
                        - sum(table[a][response] for a in lo) / len(lo))
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

    table, screens, identity = {}, {}, {}
    for spec in args.arm:
        name, _, paths = spec.partition("=")
        if name not in ALGO_FACTORS:
            raise SystemExit(f"{name}: not an arm of this factorial")
        single, _, split = paths.partition(",")
        if not single or not split:
            raise SystemExit(f"{spec}: need ARM=SINGLE,SPLIT")
        s, p = Path(single).read_text(), Path(split).read_text()
        identity[name] = check_identity(name, s, p)
        row = responses(s, p, window=args.window)
        screens[name] = row.pop("_meta")["screen"]
        table[name] = row

    shared = {k: v for k, v in identity["legacy"].items()
              if k not in ("algorithm",)} if "legacy" in identity else {}
    for name, ident in identity.items():
        for key, want in shared.items():
            if ident[key] != want:
                raise SystemExit(
                    f"{name} ran with {key}={ident[key]!r} while legacy ran "
                    f"{want!r}: the arms are not one experiment")
    if not args.window:
        same_atmosphere(table)          # the matched control, first call only
    beta = coefficients(table, screens)
    cond = conditionals(table)

    span = "window" if args.window else "first-call"
    print(f"\n  SPAN: {span}   (every response, not four of them)\n")
    print("  " + f"{'arm':18s} {'NCL':>4s} " +
          " ".join(f"{k:>13s}" for k in RESPONSES))
    for arm in ALGO_FACTORS:
        n, c, l = ALGO_FACTORS[arm]
        print("  " + f"{arm:18s} {n}{c}{l:<2d} " +
              " ".join(f"{table[arm][k]:13.5e}" for k in RESPONSES))
    print(f"\n  {'response':22s} {'unit':16s} {'native':>6s} "
          + " ".join(f"{t:>12s}" for t in ("N", "C", "L", "NC", "bound")))
    for response, (unit, owner) in RESPONSES.items():
        b = beta[response]
        print(f"  {response:22s} {unit:16s} {owner or '-':>6s} "
              + " ".join(f"{b[t]:12.4e}" for t in ("N", "C", "L", "NC"))
              + f" {b.get('_bound', 0.0):12.4e}")
    print("\n  Units differ between rows: compare terms WITHIN a response, "
          "never magnitudes across them.\n")

    doc = {"span": span, "arms": ALGO_FACTORS, "identity": identity,
           "units": {k: v[0] for k, v in RESPONSES.items()},
           "responses": table, "coefficients": beta, "conditionals": cond,
           "screens": screens}
    if args.json:
        args.json.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
