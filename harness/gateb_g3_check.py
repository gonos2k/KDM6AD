#!/usr/bin/env python3
"""Gate B G3 comparison checker — owner-adjudicated no-new-divergence predicates
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

The diff-listing format records only differences.  It has no zero-difference
sentinel, declared population, or sealed producer census, so this standalone
tool reports observed predicate results for comparison/debugging only.  It
cannot issue a decision-grade full-G3 PASS; the additive G3.3-M protocol has
the separate completeness/evidence contract for that decision.

usage: gateb_g3_check.py <gateb_diffs.txt> [--json-out report.json]
exit 1 when observed predicates fail, and 2 when the structurally valid
comparison is incomplete for a decision (or the input is malformed).
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


class G3EvidenceError(ValueError):
    """The diff listing is not a structurally usable G3 evidence stream."""


def ulp(a_bits: int, b_bits: int) -> int:
    # f32 ULP distance: map the sign-magnitude bit pattern onto a monotone
    # integer line (u < 0x80000000 -> u; else 0x80000000 - u) and subtract.
    def key(u):
        return u if u < 0x80000000 else 0x80000000 - u
    return abs(key(a_bits & 0xFFFFFFFF) - key(b_bits & 0xFFFFFFFF))


def load(path):
    diffs = defaultdict(lambda: defaultdict(dict))   # case -> field -> (j,k) -> ulp
    nonfinite = []
    seen = set()
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except UnicodeDecodeError as exc:
        raise G3EvidenceError(f"evidence listing is not valid UTF-8: {exc}") from None
    for raw in lines:
        raw = raw.rstrip("\n")
        if not raw.strip():
            continue
        parts = raw.split("|")
        if len(parts) != 3:
            raise G3EvidenceError(f"malformed record: {raw!r}")
        case, field, rest = parts[0].strip(), parts[1].strip(), parts[2]
        if not case or not field:
            raise G3EvidenceError(f"malformed record with empty case/field: {raw!r}")
        if rest.startswith("NONFINITE"):
            toks = rest.split()
            if len(toks) != 3:
                raise G3EvidenceError(f"malformed NONFINITE record: {raw!r}")
            try:
                j, k = (int(t) for t in toks[1:])
            except ValueError:
                raise G3EvidenceError(f"non-integer NONFINITE record: {raw!r}") from None
            if j < 0 or k < 0:
                raise G3EvidenceError(f"negative NONFINITE coordinate: {raw!r}")
            key = (case, field, j, k)
            if key in seen:
                raise G3EvidenceError(f"duplicate evidence record: {raw!r}")
            seen.add(key)
            nonfinite.append((case, field, j, k))
            continue
        toks = rest.split()
        if len(toks) != 4:
            raise G3EvidenceError(f"malformed diff record: {raw!r}")
        # j k ia ib — all DECIMAL (the driver writes Fortran `I0`, not hex);
        # ia/ib are int32 transfers of the f32 bits (may be negative).
        try:
            j, k, ia, ib = (int(t) for t in toks)
        except ValueError:
            raise G3EvidenceError(f"non-integer diff record: {raw!r}") from None
        if j < 0 or k < 0:
            raise G3EvidenceError(f"negative diff coordinate: {raw!r}")
        i32 = -(1 << 31), (1 << 31) - 1
        if not (i32[0] <= ia <= i32[1] and i32[0] <= ib <= i32[1]):
            raise G3EvidenceError(
                f"diff bit transfer outside signed int32 range: {raw!r}")
        key = (case, field, j, k)
        if key in seen:
            raise G3EvidenceError(f"duplicate evidence record: {raw!r}")
        seen.add(key)
        diffs[case][field][(j, k)] = ulp(ia, ib)
    if not seen:
        # A diff listing has no independent zero-diff sentinel.  An empty file
        # therefore proves that no evidence was consumed, not that every required
        # pair was compared cleanly.
        raise G3EvidenceError("empty evidence listing: no G3 records were supplied")
    return diffs, nonfinite


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("difffile")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    try:
        diffs, nonfinite = load(args.difffile)
    except (OSError, G3EvidenceError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    report = {"checker": "gateb_g3_check", "pass": False,
              "decision": False, "comparison_only": True,
              "evidence_strength": "PARTIAL", "failures": [],
              "cases": {}, "nonfinite_records": len(nonfinite),
              "observed_predicates_pass": False,
              "census": {"available": False,
                          "reason": ("gateb_diffs.txt contains differing records only; "
                                     "the required population/zero-difference census "
                                     "is not part of this input contract")},
              "scope_note": ("first-divergence-stage and mstep/branch-signature "
                             "comparability are host-dump-level checks "
                             "(compare_substep_stage/compare_rate_dump), not "
                             "assessable from final-state diffs; recorded as "
                             "out-of-scope here. This report is also "
                             "comparison-only: without a sealed census, absence "
                             "of a record cannot establish equality over the "
                             "required population, and no full-G3 decision is "
                             "claimed.")}
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

    # ``not fails`` means only that the records observed in this partial stream
    # satisfy the subset/envelope predicates.  A diff-only stream cannot prove
    # that omitted records were compared, so retain the observed result under a
    # diagnostic name and keep the decision verdict fail-closed.
    report["observed_predicates_pass"] = not fails
    report["pass"] = False
    out = json.dumps(report, indent=2)
    if args.json_out:
        open(args.json_out, "w").write(out + "\n")
    print(out)
    observed = "OK" if report["observed_predicates_pass"] else "FAIL"
    print(f"\ngateb_g3_check: COMPARISON-ONLY (observed predicates {observed}; "
          "no decision-grade census)", file=sys.stderr)
    return 1 if fails else 2


if __name__ == "__main__":
    sys.exit(main())
