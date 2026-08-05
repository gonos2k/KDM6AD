# Half of what the ledger called "precipitation out" never precipitated

<!-- claim-status: generated from CLAIMS.yaml, do not edit -->

| claim | status | grade | scope |
|---|---|---|---|
| `G33-ENTHALPY-003` | **active** | confirmed-with-scope | g33_fixture_multisubcycle_v1, legacy, h = 25 s, operator basis. The sink is a LOWER BOUND: the kernel caps dqr/dqs/dqg/dqi and only dqr and dqi carry a CAPIN anchor, while snow and graupel ARE present on this fixture at column losses of the same order as the measured sink -- so the shortfall is real and no upper bound is established. Instrumenting dqs/dqg is an overlay extension that widens the emitted main\|ice chain vocabulary and is deferred as a protocol change. enthalpy_ledger() without a sink is unchanged, so the previous figures remain reproducible. |

Statuses above are the authority; prose below may predate them.
<!-- /claim-status -->

Owner §16-4. The moist-enthalpy ledger charges the column's whole ρΔz water loss
as precipitation: `H_precip_out = (−ΔW_col) · h(T_bottom, f_surface)`, where
`f_surface` is the frozen share of the *fallout diagnostic*. That is right only
if every kilogram the column lost went out through the bottom.

It did not. The post-update-reservoir cap (P0-4b) destroys water at **internal**
interfaces: `dq(i,k+1)` is written twice, capped against the cell above
pre-update as its outflow and post-update as the inflow below, and the
difference is annihilated mid-column. That water never reached the surface, so
it was charged at the wrong temperature and in a phase chosen by a surface
diagnostic that never saw it.

## The size of it

Legacy, `g33_fixture_multisubcycle_v1`, h = 25 s, operator basis:

| col | column loss `−ΔW_col` | cap sink | sink share | interfaces |
|---|---|---|---|---|
| 1 | 4.7913e-04 | −1.7428e-11 | −0.00% | 6 |
| 2 | 5.0895e-03 | **2.9422e-03** | **57.81%** | 11 |
| 3 | 1.1842e-02 | **5.6860e-03** | **48.02%** | 45 |

In columns 2 and 3, **roughly half** of what the ledger called precipitation was
destroyed inside the column. Column 1 is at roundoff, which is the control: the
cap does not bite there and the term correctly vanishes rather than being a
constant offset applied everywhere.

## Why it had to be measured, not inferred

`outflow_split()` already decomposed `−ΔW_col = P_bottom + D_internal` — but
`P_bottom` is the fallout **diagnostic**, and
`FINDING_moist_enthalpy_ledger_v1.md` records that the diagnostic and the column
water loss disagree by an O(1) amount — which is why `_water_out` was moved onto
the budget in the first place. The inferred split is not a measurement of the
sink:

| col | `D_internal` inferred (`w − P`) | cap sink measured (CAPIN/TOPOUT) |
|---|---|---|
| 1 | −2.2535e-09 | −1.7428e-11 |
| 2 | **−1.6557e-02** | **+2.9422e-03** |
| 3 | **−2.3168e-02** | **+5.6860e-03** |

The inferred value is **negative in all three columns**. A cap can only destroy,
so a negative internal sink is not a physical quantity at all — it is the
diagnostic's own departure from the budget wearing the name of one. It also
disagrees with the measurement in **sign** and by a factor of 4–6 in magnitude,
so no scaling reconciles them.

`g33_cap_interface.cap_sink()` measures it directly from the interface pairing
that already existed: `rho(j−1)·Δz(j−1)·departure − rho(j)·Δz(j)·arrival`, per
interface, per sub-step.

## The phase is the anchor, not a guess

Each CAPIN site is anchored on a specific kernel array, so the phase of a
destroyed parcel is known from where the record was emitted:

| chain | anchor | array | phase |
|---|---|---|---|
| `main` | F:1225 `qrs(i,k,1) = max(qrs(i,k,1)-dqr(i,k)+dqr(i,k+1),0.)` | rain | liquid |
| `ice` | F:1289 `qci(i,k,2) = max(qci(i,k,2)-...,0.)` | cloud ice | ice |

## What the correction is worth

Recharging the sink at its own level and phase, against the previous
charge-everything-at-the-bottom:

| col | residual, all at surface | residual, split | correction | of residual |
|---|---|---|---|---|
| 1 | −4.833601e+01 | −4.833601e+01 | −3.38e-08 | 0.00% |
| 2 | −7.026636e+01 | −8.484304e+01 | −1.4577e+01 | **20.74%** |
| 3 | +5.397817e+02 | +5.117740e+02 | −2.8008e+01 | **−5.19%** |

**The correction does not close the residual, and in column 2 it makes it
worse.** That is reported rather than buried: charging water where it was
actually destroyed is correct independently of which direction it moves the
number, and a correction that only ever improved things would be the suspicious
one. Something else remains in the enthalpy residual; this is not it.

The **level** is what does the work, not the phase relabelling. Charging at the
departure level versus the arrival level differs by 3.2 J/m² (col 2) and
6.0 J/m² (col 3) — a fifth of the correction — so the surface-vs-interface
choice dominates the up-vs-down one.

## Limits

- **The sink is a LOWER BOUND.** The kernel caps four species — `dqr` (F:1225),
  `dqs` (F:1237), `dqg` (F:1243), `dqi` (F:1289) — and only the first and last
  carry a CAPIN anchor. Snow and graupel **are present on this fixture** (column
  losses 1.85e-03 + 9.27e-04 in column 2, 1.67e-03 + 4.98e-04 in column 3, the
  same order as the measured sink), so the shortfall is real rather than
  academic. No upper bound is established: a species' cap sink is bounded by the
  mass crossing its interfaces, not by its net column loss.
- **Closing it is an overlay extension, not a physics change.** Two more
  `CAP_SITES` anchors would instrument `dqs`/`dqg`. It is deferred rather than
  done because it widens the emitted `main|ice` chain vocabulary, which reaches
  the exact-universe checks, the parser and every archived bundle's
  compatibility — a protocol change to schedule, not to slip in.
- **`enthalpy_ledger(run)` without a sink is unchanged.** The split is opt-in, so
  the previous figures are still reproducible side by side rather than silently
  replaced.
- The ledger's other approximations are untouched: dry-air mixing ratios against
  moist ρ, and the surface part still charged at the bottom level.
