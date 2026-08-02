# Both ledgers, corrected: they do NOT discriminate the thermodynamic policy

**Revised after adversarial review, which refuted both of the first version's
conclusions.** They were artifacts of building the ledgers on the fallout
diagnostic. The corrected result is a negative one: on this fixture neither ledger
separates the coefficient policies, and the conservative interface's advantage is
marginal and not consistent across columns.

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

## Corrected result (dtcld = 25 s, relative residual)

| leg | col | §8.1 operator | §8.2 physical |
|---|---|---|---|
| Fortran (call-fixed) | 1 | 3.342e-05 | −5.425e-06 |
| | 2 | 1.011e-03 | 9.990e-04 |
| | 3 | 9.692e-04 | 6.209e-04 |
| C++ legacy (sub-cycle-refreshed) | 1 | 3.399e-05 | −3.957e-06 |
| | 2 | 9.893e-04 | 9.815e-04 |
| | 3 | 9.698e-04 | 6.215e-04 |
| C++ conservative | 1 | 3.399e-05 | −3.957e-06 |
| | 2 | 7.316e-04 | 7.144e-04 |
| | 3 | 1.080e-03 | 7.288e-04 |

### 1. The ledgers do not separate the coefficient policies

Fortran (call-fixed) against C++ legacy (sub-cycle-refreshed):

| | col 2 | col 3 |
|---|---|---|
| §8.1 | 1.011e-03 vs 9.893e-04 | 9.692e-04 vs 9.698e-04 |
| §8.2 | 9.990e-04 vs 9.815e-04 | 6.209e-04 vs 6.215e-04 |

**Within 2%, and identical to four figures in column 3.** The first version's
"refreshing closes both ledgers ~1.5× worse" was the diagnostic defect, which is
larger under legacy at coarse steps. **On the corrected ledgers there is no
measurable policy difference at all.**

That is a negative result and it matters: with §9's convergence route
structurally blocked on this fixture, the energy ledgers were the remaining
discriminator, and they do not discriminate either.

### 2. The conservative interface's advantage is marginal and inconsistent

Better in column 2 (7.32e-04 against 9.89e-04, **1.35×**) and **worse in column 3**
(1.080e-03 against 9.698e-04). Not the ~74×/~2200× first reported, and not a
uniform improvement.

### 3. All three legs close to ~1e-3, and column 1 to ~1e-5

Column 1 is 288–290 K with no ice, so almost nothing happens and the residual is a
floor of the construction. The ~1e-3 in columns 2 and 3 is common to every leg and
is not attributed here — it may be the approximations below, the threshold-cleanup
sink `docs/STATUS.md` records, or a real gap.

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

- **No policy discrimination.** Both ledgers are silent on the `cpm`/`xl` question.
- **The ~1e-3 common residual is unattributed.**
- Comparing C++ against Fortran is implementation against implementation; the
  reference-faithful C++ counterfactual, which would isolate the policy, is inside
  frozen code.
- Synthetic fixture, 300 s, microphysics only.
