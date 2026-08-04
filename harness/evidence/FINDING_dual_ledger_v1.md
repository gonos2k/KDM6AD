# Two column measures, and the invariance that is a property of this fixture

<!-- claim-status: generated from CLAIMS.yaml, do not edit -->

| claim | status | grade | scope |
|---|---|---|---|
| `G33-BASIS-003` | **active** | confirmed | g33_fixture_multisubcycle_v1, legacy, h = 25 s for the fixture numbers; the humidity sweep is CONSTRUCTED and shows the cancellation is contingent, not what the divergence is in any particular forecast. Number and mass rows only -- water and enthalpy are not yet on both bases. Says nothing about which basis the reference INTENDS, which is G33-BASIS-002 and an owner decision. |

Statuses above are the authority; prose below may predate them.
<!-- /claim-status -->

Owner §9. `den` passed to the kernel is **moist**-air density

    rho_m = rho_d (1 + qv)        (module_big_step_utilities_em.F:4856)

while `nr` and the `q` fields are mixing ratios per **dry**-air kg. So there are
two different column integrals:

| measure | integral | what it is |
|---|---|---|
| `operator` | Σ ρ_m Δz x | the budget the operator itself closes |
| `physical` | Σ ρ_d Δz x | what is physically conserved |

Reporting one of them makes a statement about the **operator** read as a statement
about the **atmosphere**. Every row now carries both.

## Absolute values do shift

Surface outflow, legacy, h = 25 s:

| row | operator | physical | shift |
|---|---|---|---|
| `main/nr/1` | 5.624630e+05 | 5.619011e+05 | −0.0999% |
| `main/nr/3` | 1.158840e+05 | 1.157636e+05 | −0.1039% |
| `ice/qi/2` | 7.654400e−04 | 7.646601e−04 | −0.1019% |

which is just the column-mean `qv` of about 0.1%.

## The ratios do not — **on this fixture**

| row | operator ratio | physical ratio | divergence |
|---|---|---|---|
| `main/nr/1` | 0.150035513207 | 0.150035513207 | 6.4e−14 |
| `main/nr/2` | 0.133376996409 | 0.133376996409 | 3.1e−14 |
| `main/nr/3` | 0.118402461045 | 0.118402461045 | 1.0e−14 |

Machine zero. It would be easy to conclude that the basis question does not
affect the defect magnitude. **That conclusion does not survive one step of
checking**, and the owner flagged exactly this (§9.3).

## Why it cancels here, and when it stops

The conversion is `1 + qv`, so it factors out of a ratio only when it is
vertically **constant**. This fixture's is nearly so:

| column | 1+qv range | spread |
|---|---|---|
| 1 | 1.001000 – 1.001037 | 3.7e−05 |
| 2 | 1.001020 – 1.001046 | 2.6e−05 |
| 3 | 1.000323 – 1.001040 | **7.2e−04** |

Built explicitly, holding everything else fixed and varying only the humidity
profile:

| profile | divergence of the two ratios |
|---|---|
| uniform `qv = 0.001` | **2.2e−15** — the basis genuinely cancels |
| this fixture's column-3 spread | 3.7e−04 |
| ordinary troposphere, `qv` 2e−5 → 1.8e−2 | **1.4e−02** |

So on a real column the two ratios differ by **over a percent relative** — on a
15% defect that is 15.00% against 14.79%. The invariance is a property of a
**near-dry fixture**, not of the quantity, and must not be quoted as the latter.

The divergence tracks the **spread**, not the mean: adding a large constant
humidity barely moves it, which is what "1+qv factors out" predicts and is
tested directly.

## One assumption became a measurement

The closure uses the pre-sedimentation density at both endpoints. That is only
sound if sedimentation leaves `qv` alone. Both endpoints now carry `qv`, and
across every call and column `max |Δqv| = 0.000e+00` — exactly zero, not small.
Sedimentation moves hydrometeors, not vapour, and the ledger now checks it rather
than relying on it.

## Limits

- **This does not answer which basis the reference intends.** That is
  `G33-BASIS-002`, and the owner's §9.1 reframes it correctly: the question is
  not "which is physically right" — for a per-dry-kg field the physical density
  is the dry one — but which of legacy-compatible / dry-conservative / both the
  variant should offer. That is an owner decision and is untouched here.
- **Number and mass rows only.** §9.2 asks for water and enthalpy on both bases
  too. Those ledgers live outside this closure and are not converted yet; naming
  it rather than implying coverage.
- **The realistic profile is constructed.** It demonstrates that the cancellation
  is contingent, not what the divergence is in any particular forecast. Measuring
  that needs the real case, which is the §14-8 gate.
- The fixture's own divergence is 1e−14, so nothing previously published about
  this fixture's ratios changes.
