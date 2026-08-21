"""The N x C x L factorial's response vector and its signed coefficients.

The first reading of this factorial declared the cross terms "at roundoff" from
looking at a table of ABSOLUTE residuals. The owner's re-review computed the
standard interaction and it is not:

    I_NC = Y11 - Y10 - Y01 + Y00 = 0.0235,  13.8 % of baseline

That is the difference between MARGINAL SELECTIVITY -- each response moving with
one factor -- and ORTHOGONALITY, which is a statement about cross terms. They are
not the same claim and the first does not imply the second.

Two things follow, and both are implemented here.

SIGNED, NOT ABSOLUTE. `|R|` is non-linear: it hides sign reversal, turns
cancellation into apparent effect, and distorts any coefficient computed from it.
Effects are computed on the signed response.

EACH CORRECTION MEASURED ON ITS OWN INVARIANT. N was scored on number closure and
L on decomposition invariance -- their own -- while C was scored only through its
indirect effect on the ice-number residual. C's own invariant is the interface cap
term, and without it the table cannot say whether C does its job independently.

The coefficients are the standard 2^3 contrasts on +/-1 coding,

    beta_S = (1/8) sum over arms of (prod_{j in S} x_j) * Y

and each is reported beside a roundoff screening scale, because "is this
interaction real" is a question about magnitude against resolution, not about
whether a number is non-zero.
"""
import argparse
import json
import sys
from itertools import combinations
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

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

#: The responses, and which factor each is the NATIVE invariant of. A response
#: with no owner is a diagnostic; one with an owner is the check that factor
#: has to pass on its own terms.
RESPONSES = (("R_nr", "N"), ("R_ni", "N"), ("R_qr", None), ("R_qi", "C"),
             ("cap_sink", "C"), ("partition", "L"))


def responses(stream_single: str, stream_split: str) -> dict:
    """The full signed response vector for one arm."""
    import g33_number_transport as nt
    import g33_cap_interface as ci
    out = {}
    calls = nt.calls(stream_single)
    first = calls[0]
    loop = nt.single_loop(first)
    cols = sorted({c for l, c, _k in first["outer_pre_sed"] if l == loop})
    for species, key in (("nr", "R_nr"), ("ni", "R_ni"),
                         ("qr", "R_qr"), ("qi", "R_qi")):
        total = start = 0.0
        for col in cols:
            row = nt.column(first, col, species)
            if row:
                total += row["residual"]      # SIGNED
                start += row["start"]
        out[key] = total / start if start else 0.0
    # C's own invariant: the net interface cap term, signed, over the first
    # call's columns. `cap_sink` returns per-column interface rows.
    sink = ci.cap_sink(stream_single)
    out["cap_sink"] = sum(row[3] for rows in sink.values() for row in rows)
    out["partition"] = float(_partition_diff(stream_single, stream_split))
    return out


def _partition_diff(single: str, split: str) -> int:
    """States differing between the two decompositions of the same run."""
    import g33_number_transport as nt

    def final(text):
        got = {}
        for call in nt.calls(text):
            loop = nt.single_loop(call)
            if not isinstance(loop, int):
                continue
            for (lvl, col, k), val in call["outer_post_sed"].items():
                if lvl == loop:
                    got[(call["split"], col, k)] = tuple(sorted(val.items()))
        return got
    a, b = final(single), final(split)
    shared = set(a) & set(b)
    return sum(1 for k in shared if a[k] != b[k])


def coefficients(table: dict) -> dict:
    """Standard 2^3 contrasts on +/-1 coding, per response.

    `table` is {arm: {response: value}}. Returns {response: {term: beta}} with
    terms "", "N", "C", "L", "NC", "NL", "CL", "NCL" -- the empty key being the
    grand mean.
    """
    arms = [a for a in ALGO_FACTORS if a in table]
    if len(arms) != 8:
        raise SystemExit(f"a 2^3 factorial needs all eight arms, got {len(arms)}")
    names = "NCL"
    out = {}
    for response, _owner in RESPONSES:
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
        out[response] = betas
    return out


def _subsets(chars, size):
    """Subsets of `chars` of the given size, IN `chars` ORDER.

    Sorting alphabetically gave `CN` and `LN`, which name the same terms and
    read as different ones. The factor order is the experiment's, not the
    alphabet's.
    """
    return ["".join(c) for c in combinations(chars, size)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("arm", nargs="+", metavar="ARM=SINGLE,SPLIT",
                    help="one per arm: the two raw streams of that arm's run")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()

    table = {}
    for spec in args.arm:
        name, _, paths = spec.partition("=")
        if name not in ALGO_FACTORS:
            raise SystemExit(f"{name}: not an arm of this factorial")
        single, _, split = paths.partition(",")
        if not single or not split:
            raise SystemExit(f"{spec}: need ARM=SINGLE,SPLIT")
        table[name] = responses(Path(single).read_text(),
                                Path(split).read_text())
    beta = coefficients(table)          # refuses anything but all eight

    terms = ["N", "C", "L", "NC", "NL", "CL", "NCL"]
    keys = [r for r, _ in RESPONSES]
    print("  " + f"{'arm':18s} {'NCL':>4s} " + " ".join(f"{k:>11s}" for k in keys))
    for arm in ALGO_FACTORS:
        n, c, l = ALGO_FACTORS[arm]
        print("  " + f"{arm:18s} {n}{c}{l:<2d} "
              + " ".join(f"{table[arm][k]:11.4e}" for k in keys))
    print()
    print("  " + f"{'response':10s} {'native':>6s} {'mean':>11s} "
          + " ".join(f"{t:>11s}" for t in terms))
    for response, owner in RESPONSES:
        b = beta[response]
        print("  " + f"{response:10s} {owner or '-':>6s} {b['']:11.4e} "
              + " ".join(f"{b[t]:11.4e}" for t in terms))

    doc = {"arms": ALGO_FACTORS, "responses": table, "coefficients": beta}
    if args.json:
        args.json.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
