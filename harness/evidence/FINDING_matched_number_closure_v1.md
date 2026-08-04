# Matched mass/number closure: same chain, same calls, and it holds at mstep = 10

<!-- claim-status: generated from CLAIMS.yaml, do not edit -->

| claim | status |
|---|---|
| `G33-NUMBER-005` | **active** |
| `G33-NUMBER-006` | **withdrawn → G33-ICE-CAP-001** |

Statuses above are the authority; prose below may predate them.
<!-- /claim-status -->

Owner §5.2 and §5.3. The earlier closure compared `qr` on the MAIN chain over 1–3
calls against `ni` on the ICE chain over 95, using the UNCAPPED `fall`/`falln`
accumulators, and excluded any call where a cap bound — detected by an endpoint
recursion valid only at `mstep == 1`. It supported the defect; it was not a
controlled contrast, and it could not reach operational sub-step counts.

## What changed

A new anchored overlay site emits the **actual capped** bottom-cell transfers,
once per sub-step, from the same statement pair the kernel uses:

```
G33F XFER <loop> <n> <col> <main|ice> f32 <dq> <dn>
```

`dqr/dnr` at F:1224 and `dqi/dni` at F:1309. Nothing is reconstructed, so
`mstep > 1` is admissible, and the mass and number of one chain come from one
call, one cap state, one statement pair.

## Matched result, h = 25 s (mstep 1 / 2 / 3)

| chain | species | col 1 | col 2 | col 3 |
|---|---|---|---|---|
| main | **qr** (control) | −0.0000% | +0.0001% | −0.0000% |
| main | **nr** | **+15.00%** | **+13.34%** | **+11.84%** |

All 12 calls, all three columns, no exclusions.

## Operational sub-step counts, h = 100 s (mstep 1 / 5 / 10)

| chain | species | col 2 (mstep 5) | col 3 (**mstep 10**) |
|---|---|---|---|
| main | **qr** (control) | −0.0576% | **−0.0000%** |
| main | **nr** | **+11.57%** | **+9.40%** |

**The defect persists at `mstep = 10` with the mass control closing to f32
roundoff.** §5.3 recorded operational magnitude as unmeasured; this measures it on
this fixture.

## The control earned its keep

Two rows are **not** evidence, and the mass control is what says so:

| row | mass control | verdict |
|---|---|---|
| ice, cols 2–3, h = 25 s | qi −384% / −269% | **unusable** |
| main, col 1, h = 100 s | qr −47.7% | **unusable** |

A mass control that fails means the accounting for that chain and call set is
missing a term, so **neither** row of the pair is evidence — not that ice number
is defective. The ice budget's missing term is not identified here; only
`qci(i,k,2)` writes at F:1289 and F:1309 lie inside the segment, so the gap is in
the analysis, not obviously in the kernel. The tool now prints an explicit
`!!` line whenever a mass control fails, so such a row cannot be read off the
table as a result.

## Limits

- One fixture, legacy only. The conservative variant is not run through this.
- The ice chain is unmeasured pending the missing term.
- The absolute `# m⁻²` figures carry the moist-vs-dry basis offset
  (`FINDING_number_mass_basis_v1`): 0.10% here, ~2% on a moist real case. The
  percentages above are ratios and are unaffected.
- Synthetic fixture, 300 s. No C4 verdict.
