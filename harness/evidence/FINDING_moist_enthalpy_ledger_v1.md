# Both ledgers, corrected twice: a ~10x conservative advantage in one column, and no clean policy signal

<!-- claim-status: generated from CLAIMS.yaml, do not edit -->

| claim | status | grade | scope |
|---|---|---|---|
| `G33-PRECIP-002` | **withdrawn → G33-PRECIP-001** | — | g33_fixture_multisubcycle_v1, f32, column 2 |

Statuses above are the authority; prose below may predate them.
<!-- /claim-status -->

> **SCOPE CORRECTION (owner §6.4 follow-up).** The column-2 conservative advantage
> reported below is **precision-scoped and is 1.00× at f64**. Rebuilding this
> fixture with the kernel promoted to f64 shows it essentially does not
> precipitate (rain 2.0e-07 / ~0 / 0.0 mm against 4.8e-04 / 2.2e-02 / 3.5e-02 at
> f32), legacy and conservative go **bit-identical — 0 of 333 records differ**,
> and the ledger residuals coincide exactly. The advantage below measures how the
> two variants respond to a sedimentation cap event that f32 noise creates on a
> threshold-marginal fixture, **not the interface's thermodynamics**. It remains a
> valid statement about the f32 reference, which is the operator being certified.
> See [`FINDING_fixture_precipitates_only_at_f32_v1.md`](FINDING_fixture_precipitates_only_at_f32_v1.md).

**Revised twice after adversarial review, which found two independent defects in
the construction.** The first version's ~74×/~2200× conservative advantage and its
"refreshing loses 1.5× on both" were artifacts of (a) taking the enthalpy flux from
the known-defective fallout diagnostic and (b) double-counting the frozen species.
Both are fixed below. The corrected result: the conservative interface closes ~10×
better in the topologically stable column and is neutral elsewhere, and the
coefficient-policy contrast is a weak single-column signal that does not separate
the policies.

## The defect in the first version

Both ledgers took the enthalpy carried out by precipitation from the **fallout
diagnostic**. `docs/STATUS.md` already records (P0-4b) that the diagnostic and the
column water loss disagree by an O(1) amount, attributed to the inflow cap. Building
a physical budget on the defective quantity made the residual a restatement of that
defect:

| | flux / dH, col 2 | col 3 |
|---|---|---|
| legacy | **6.62** | 4.38 |
| conservative | 1.07 | 1.19 |

For legacy the flux term was **4–7× the enthalpy change**, so the residual was
essentially the flux, and the flux was the defective number. Conservative's
diagnostic happens to sit close to its column water loss, so its flux and its `dH`
nearly cancelled. **The apparent ~74× and ~2200× advantages were that difference,
not thermodynamics.**

## The correction

The enthalpy leaving must be proportional to the water that actually left, taken
from the ρΔz column budget. The diagnostic is used only for the liquid/ice **ratio**,
which is far less sensitive than its magnitude.

A test now pins the contract: changing the fallout diagnostic alone must not move
the ledger.

## A second defect, found by the same review

The species accounting was also wrong. WRF's convention, verbatim at F:1462-1464:

```
fallsum     = fall(1)+fall(2)+fall(3)+fall(4)   -> rain    == the TOTAL
fallsum_qsi = fall(2)+fall(4)                   -> snow    == a SUBSET
fallsum_qg  = fall(3)                           -> graupel == a SUBSET
```

`rain` is the total surface fallout of all four species; `snow` and `graupel` are
**components of it**. Summing the three double-counts the frozen part. That was the
source of the "~2× offset against the column water budget" that an earlier document
nearly explained away as a convention difference — it was a double-count, and the
factor tracked the frozen fraction rather than being a constant.

With the total taken correctly:

| leg | dtcld | total / (−ΔW) |
|---|---|---|
| **conservative** | 100 / 25 / 3.125 | **1.0000 / 1.0000 / 1.0000** |
| legacy | 100 / 25 / 3.125 | 4.97 / 4.26 / 0.992 |

**The conservative interface closes the column water budget exactly at every
timestep.** Legacy over-reports its fallout relative to the water that actually left
by ~5× at coarse steps, converging only near 3 s. That is the P0-4b defect measured
as a function of resolution.

## Corrected result (dtcld = 25 s, relative residual)

Both fixes applied — flux from the water budget, species counted correctly:

| leg | col | §8.1 operator | §8.2 physical |
|---|---|---|---|
| Fortran (call-fixed) | 1 | 3.342e-05 | −5.425e-06 |
| | 2 | −8.063e-05 | −9.031e-05 |
| | 3 | 5.084e-04 | 1.494e-04 |
| C++ legacy (sub-cycle-refreshed) | 1 | 3.399e-05 | −3.957e-06 |
| | 2 | −1.316e-04 | −1.369e-04 |
| | 3 | 5.082e-04 | 1.491e-04 |
| C++ conservative | 1 | 3.399e-05 | −3.957e-06 |
| | 2 | **3.228e-06** | **−1.237e-05** |
| | 3 | 5.117e-04 | 1.469e-04 |

### 1. The conservative interface closes better in column 2, and is neutral in column 3

Column 2: **3.23e-06 against 1.32e-04**. Column 3: all three legs agree to three
figures.

**The factor is a range, not a point (owner P0-4).** The departing water is charged
at the bottom-level temperature and nothing in the endpoint data says it left from
there. Recomputing with each level in turn moves the conservative column-2 residual
from 1.24e-05 to 2.86e-05 — a **131% band** — while legacy's moves only 15%. So the
advantage is **5–11×**, not "about 10×", and the spread comes from a modelling
choice rather than from measurement error. The analyzer now prints the band beside
every residual.

The outflow decomposition is also measured, and it does **not** match the shape P0-4
anticipated:

| leg | col | −ΔW_col | P_bottom | D_internal |
|---|---|---|---|---|
| legacy | 2 | 5.226e-03 | 3.076e-02 | **−2.553e-02** |
| conservative | 2 | 3.877e-03 | 3.877e-03 | **−7.6e-09** |

`D_internal = −ΔW_col − P_bottom` is ~0 for the conservative interface and
**negative** for legacy — the diagnostic reports *more* outflow than the column
lost, the **opposite sign** from the P0-4b real-case defect where column loss
exceeded the diagnostic. So on this fixture there is no internally deleted mass to
mis-locate, and because the ledger charges `−ΔW_col` rather than the diagnostic it
never charges phantom mass. What remains open is the level, which the band bounds.

### 2. The policy contrast is weak and not uniform

Fortran (call-fixed) against C++ legacy (refreshed): **1.6× in column 2** (−8.06e-05
against −1.32e-04, refreshed worse) and **identical to three figures in column 3**.

Far from the "~1.5× worse on both ledgers" first claimed, which was the diagnostic
defect, and not the "no measurable difference" of the first correction, which was
the species double-count. The honest reading is a weak, single-column signal that
**does not separate the policies with any confidence**, and which in any case
compares two implementations rather than two policies.

## Construction

Constants from `module_model_constants.F`: `cpd = 7·r_d/2 = 1004.5`,
`cpv = 4·r_v = 1846.4`, `cliq = 4190`, `cice = 2106`, `XLV = 2.5e6`, `XLF = 3.5e5`,
`XLS = 2.85e6`, and `XLS − XLV = XLF` exactly, so the reference enthalpies cannot
disagree with the code's latent heats at T0.

* **§8.2 physical** — per-phase heat capacities, Kirchhoff-consistent. Deliberately
  not the code's own `xlcal`/`cpmcal`: §3.1 puts the code's `dxlf/dT` at
  `c_l − c_pv = 2343.6` against a consistent `c_l − c_i = 2084`, and a ledger built
  from the code's formulas would be satisfied by construction.
* **§8.1 operator** — the code's own forms, one `cpm` for the parcel, so a
  conversion leaves the potential flat by construction.

Approximations, common to every leg so comparisons hold: mixing ratios treated as
per unit dry air against moist ρ; flux enthalpy at the bottom-level temperature;
liquid/ice split from the diagnostic's ratio.

## What this does NOT establish

- **No confident policy discrimination.** The 1.6× in column 2 is one column, one
  contrast, and confounded by every other difference between the two ports.
- **The ~1.5e-04 / 5e-04 column-3 residual is unattributed** and is common to all
  three legs — it may be the stated approximations, the threshold-cleanup sink
  `docs/STATUS.md` records, or a real gap.
- **The conservative advantage is confined to column 2.** It is absent in column 3,
  and column 1 has no ice so nothing acts there.
- Comparing C++ against Fortran is implementation against implementation; the
  reference-faithful C++ counterfactual, which would isolate the policy, is inside
  frozen code.
- Synthetic fixture, 300 s, microphysics only.
