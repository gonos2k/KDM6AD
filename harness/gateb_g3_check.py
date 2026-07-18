#!/usr/bin/env python3
"""Gate B G3 verifier — owner-adjudicated no-new-divergence conditions
(2026-07-17 adjudication). Consumes the Gate B driver's machine-readable
diff listing (gateb_diffs.txt: "case|field| j k fort_bits cpp_bits" and
"case|field|NONFINITE j k" records) and enforces, per multi-subcycle
fixture case (conservative pair vs its "LEG " legacy-control twin):

  G3.1  conservative cross-tree differing FIELD set
            SUBSET-OF  legacy cross-tree differing field set
  G3.2  conservative differing-CELL mask (per case, union over fields)
            SUBSET-OF or equal to the legacy baseline mask
  G3.3  conservative max ULP  <=  legacy baseline ULP envelope (per case)
  G3.4  NO non-finite value on either pair (any NONFINITE record fails)

Single-subcycle cases are gated raw-bit by the driver itself (G1) and are
required to be ABSENT from the conservative diff listing here.

"same first-divergence stage where comparable" and mstep/branch-signature
checks are host-dump-level properties (compare_substep_stage.py /
compare_rate_dump.py) — out of this standalone checker's scope, recorded
as such in the report.

usage: gateb_g3_check.py <gateb_diffs.txt> [--json-out report.json]
exit 0 iff every G3 condition holds.
"""
import argparse
import json
import sys
from collections import defaultdict

# multi-subcycle fixtures: conservative case name -> legacy control twin
MULTI_PAIRS = {
    "closure3-C3.3": "LEG closure3",
    "species-iso": "LEG species-iso",
}
# single-subcycle fixtures: raw-bit gated (G1) — must not appear at all
SINGLE_CASES = {"single-layer", "mstep-mix", "LEG single-layer", "LEG mstep-mix"}


def ulp(a_bits: int, b_bits: int) -> int:
    # f32 ULP distance: map the sign-magnitude bit pattern onto a monotone
    # integer line (u < 0x80000000 -> u; else 0x80000000 - u) and subtract.
    def key(u):
        return u if u < 0x80000000 else 0x80000000 - u
    return abs(key(a_bits & 0xFFFFFFFF) - key(b_bits & 0xFFFFFFFF))


def load(path):
    diffs = defaultdict(lambda: defaultdict(dict))   # case -> field -> (j,k) -> ulp
    nonfinite = []
    with open(path) as fh:
        lines = fh.readlines()
    for raw in lines:
        raw = raw.rstrip("\n")
        if not raw.strip():
            continue
        parts = raw.split("|")
        if len(parts) != 3:
            print(f"ERROR: malformed record: {raw!r}")
            sys.exit(2)
        case, field, rest = parts[0].strip(), parts[1].strip(), parts[2]
        if rest.startswith("NONFINITE"):
            toks = rest.split()
            nonfinite.append((case, field, int(toks[1]), int(toks[2])))
            continue
        toks = rest.split()
        if len(toks) != 4:
            print(f"ERROR: malformed diff record: {raw!r}")
            sys.exit(2)
        # j k ia ib — all DECIMAL (the driver writes Fortran `I0`, not hex);
        # ia/ib are int32 transfers of the f32 bits (may be negative).
        try:
            j, k, ia, ib = (int(t) for t in toks)
        except ValueError:
            print(f"ERROR: non-integer diff record: {raw!r}")
            sys.exit(2)
        diffs[case][field][(j, k)] = ulp(ia, ib)
    return diffs, nonfinite


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("difffile")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    diffs, nonfinite = load(args.difffile)
    report = {"checker": "gateb_g3_check", "pass": False, "failures": [],
              "cases": {}, "nonfinite_records": len(nonfinite),
              "scope_note": ("first-divergence-stage and mstep/branch-signature "
                             "comparability are host-dump-level checks "
                             "(compare_substep_stage/compare_rate_dump), not "
                             "assessable from final-state diffs; recorded as "
                             "out-of-scope here.")}
    fails = report["failures"]

    # G3.4 — non-finite anywhere fails
    if nonfinite:
        fails.append(f"G3.4: {len(nonfinite)} NONFINITE records (first: "
                     f"{nonfinite[0]})")

    # G1 backstop — single-subcycle cases must be diff-free
    for case in sorted(diffs):
        if case in SINGLE_CASES and diffs[case]:
            fails.append(f"G1: single-subcycle case {case!r} has diffs "
                         "(raw-bit gate violated)")
        if case not in SINGLE_CASES and case not in MULTI_PAIRS and \
           case not in MULTI_PAIRS.values():
            fails.append(f"unknown case in diff listing: {case!r}")

    for cons_case, leg_case in MULTI_PAIRS.items():
        cd, ld = diffs.get(cons_case, {}), diffs.get(leg_case, {})
        c_fields, l_fields = set(cd), set(ld)
        c_cells = {cell for f in cd for cell in cd[f]}
        l_cells = {cell for f in ld for cell in ld[f]}
        c_ulp = max((u for f in cd for u in cd[f].values()), default=0)
        l_ulp = max((u for f in ld for u in ld[f].values()), default=0)
        entry = {
            "cons_fields": sorted(c_fields), "legacy_fields": sorted(l_fields),
            "cons_cells": len(c_cells), "legacy_cells": len(l_cells),
            "cons_max_ulp": c_ulp, "legacy_max_ulp_envelope": l_ulp,
            "per_field_max_ulp": {
                f: {"cons": max(cd.get(f, {}).values(), default=0),
                    "legacy": max(ld.get(f, {}).values(), default=0)}
                for f in sorted(c_fields | l_fields)},
            "field_subset": c_fields <= l_fields,
            "cell_mask_subset": c_cells <= l_cells,
            "ulp_within_envelope": c_ulp <= l_ulp,
        }
        report["cases"][cons_case] = entry
        if not entry["field_subset"]:
            fails.append(f"G3.1 {cons_case}: cons fields "
                         f"{sorted(c_fields - l_fields)} not in legacy set")
        if not entry["cell_mask_subset"]:
            extra = sorted(c_cells - l_cells)[:5]
            fails.append(f"G3.2 {cons_case}: {len(c_cells - l_cells)} cons "
                         f"cells outside the legacy mask (first: {extra})")
        if not entry["ulp_within_envelope"]:
            fails.append(f"G3.3 {cons_case}: cons max ULP {c_ulp} exceeds "
                         f"legacy envelope {l_ulp}")

    report["pass"] = not fails
    out = json.dumps(report, indent=2)
    if args.json_out:
        open(args.json_out, "w").write(out + "\n")
    print(out)
    print(f"\ngateb_g3_check: {'PASS' if report['pass'] else 'FAIL'}",
          file=sys.stderr)
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
