# The basis only bites where the closure is otherwise clean

<!-- claim-status: generated from CLAIMS.yaml, do not edit -->

| claim | status | grade | scope |
|---|---|---|---|
| `G33-BASIS-004` | **active** | confirmed | n12.rezero of the legacy refinement chain on g33_fixture_multisubcycle_v1. Says nothing about which basis the reference INTENDS to close, which is G33-BASIS-002 and an owner decision. P_surface is the WRF rain diagnostic and is not reweighted -- it is already a physical mass per area -- so the physical budget mixes a dry-weighted column change with a diagnostic whose own departure from the rho*dz budget is a separate known defect, and that defect dominates columns 2-3. |
| `G33-BASIS-005` | **active** | confirmed | g33_fixture_multisubcycle_v1, legacy, h = 25 s. The window-initial qv is read from `G33R INITIAL`, and rho and delz come from the union of all calls after being verified identical in each -- they are forcing. The measure is one immutable rho*dz per (col, k). . This scope previously described the FIRST implementation, which took qv from the first call's pre-sed record and refused a cell absent from that call. The text above corrects exactly that, so the two halves of this claim contradicted each other and a reader had to decide which was current (owner §6.2). The code matches the text: `window_cell_mass` reads ("initial", "qv", col, k) and keys the measure (col, k). . This does not settle whether the physical measure should be the canonical dry-air layer mass the host dynamics carries -- that is a separate binding, and G33-BASIS-002 remains the open compatibility question. |

Statuses above are the authority; prose below may predate them.
<!-- /claim-status -->

Owner §9.2. `qv, qc, qr, qi, qs, qg` are mixing ratios per **dry**-air kg while
`rho` is **moist** density, so a physical kg m⁻² needs ρ_d. The water closure, the
`qr/qi` mass control, the moist-enthalpy ledger and the operator-energy ledger are
all real statements about the operator's own metric — and none of them is
automatically a statement about physical dry-air conservation.

Both ledgers now take a `basis`, exactly as the number closure does.

## Water

`R_W = (W_final − W_initial) + P_surface`, relative:

| column | operator (ρ_m·Δz) | physical (ρ_d·Δz) | ratio |
|---|---|---|---|
| **1** | **4.5703e−09** | **9.7626e−07** | **213.6×** |
| 2 | 6.8273e−02 | 6.8364e−02 | 1.0× |
| 3 | 1.7131e−01 | 1.7158e−01 | 1.0× |

**The basis matters precisely where the residual is otherwise at roundoff.**
Column 1's closure looks exact — 4.6e−9 — and that is a statement about the
operator's own metric. Under the dry metric the same column closes 214× worse, at
1e−6. Columns 2 and 3 are dominated by the precipitation-diagnostic departure
(`FINDING_fallout_diagnostic_is_not_the_water_budget`), so a 0.1% change of
measure is invisible against a 7–17% residual.

That is the shape of the whole §9.2 question: converting a budget that is already
badly closed changes nothing worth reporting, and converting one that closes to
machine precision changes it by two orders of magnitude — and "conserved to
machine precision" is exactly the sentence people quote.

## Enthalpy

| ledger | column | operator | physical | ratio |
|---|---|---|---|---|
| consistent thermodynamics | 1 / 2 / 3 | −5.42e−06 / −9.03e−05 / 1.49e−04 | −5.42e−06 / −9.27e−05 / 1.48e−04 | 0.999 / 1.026 / 0.991 |
| the code's own equations | 1 / 2 / 3 | 3.34e−05 / −8.06e−05 / 5.08e−04 | 3.34e−05 / −8.29e−05 / 5.07e−04 | 1.000 / 1.028 / 0.998 |

**Corrected (owner P0-3): that table measured a MIXED basis, not a physical one.**
`_ledger` weighted its endpoints by ρ_d under `physical` while `_water_out` was
fixed at ρ_m, so the "physical enthalpy residual" differenced a **dry** column
change against a **moist** outflow. The 2.6–2.8% on column 2 was that mismatch,
not a basis sensitivity.

With the basis threaded through the outflow as well, the relative residual is
**basis-invariant to 3.3e−11 or better** in all six rows:

| ledger | col 1 | col 2 | col 3 |
|---|---|---|---|
| consistent thermodynamics | 3.3e−11 | 1.5e−12 | 1.3e−12 |
| the code's own equations | 3.4e−12 | 7.8e−13 | 3.2e−13 |

The absolute terms still move by the column-mean `q_v` (`H_start` −0.0999 /
+0.1019 / +0.1039%), so the conversion is being applied — it is the *relative*
residual that is invariant. The enthalpy ledgers are limited by the thermodynamic
approximations they declare, and the basis is not among them.

## Why ρ_d is taken from the initial humidity

`ρ_d·Δz` for a layer is invariant across a column-microphysics step: no dry air is
transported. So the dry density is computed once, from the initial `qv`, and used
at **both** endpoints. Recomputing it from the final `qv` would make the measure
move with the process being measured, and a budget whose weights change between
its endpoints is not a budget. This is asserted in a test rather than left to the
comment.

## Limits

- **This does not say which basis is right.** Under the operator metric the
  column-1 water residual is 4.6e−9; under the dry metric 9.8e−7. Which one the
  reference *intends* to close is `G33-BASIS-002` — an owner decision, and §9.1
  frames it correctly as a compatibility-policy choice rather than a physics one.
- **`P_surface` is not reweighted.** It is the WRF `rain` diagnostic, already a
  physical mass per area, so it enters both budgets unchanged. That is consistent,
  but it does mean the physical budget mixes a dry-weighted column change with a
  diagnostic whose own departure from the ρΔz budget is a separate known defect.
  On columns 2–3 that defect dominates everything here.
- **One fixture, one member.** `n12.rezero` of the legacy refinement chain.
- The `qr/qi` mass controls in the matched closure already carry both bases
  (`G33-BASIS-003`); this extends the same treatment to the two column ledgers,
  which completes §9.2's list.


## The physical measure was itself moving (owner §11)

`rho_d = rho_m/(1+qv)` was recomputed from **each external call's own pre-sed
`qv`** on the G33N side, so the same layer's dry-air mass moved between calls —
up to **0.0717%** across the twelve calls on this fixture, worst in column 3
where the microphysics is most active. Column microphysics transports no dry
air, so `rho_d·Δz` for a layer is invariant across the window: a budget whose
weights change with the process being measured is not a budget.

The G33R ledger (`_column_density`) had **already** held it at the initial `qv`
and said why in its docstring. The two halves of the codebase disagreed, and the
half with the argument written down was the one that was right.

`cell_measure()` now takes the measure once from the window's first call and
every analyzer shares it — window inventory, per-call closure, interface
residual, throughput, defect magnitude, dual ledger.

| row | per-call qv | window-fixed | change |
|---|---|---|---|
| `ice/ni/3` | −5.239382e+08 | −5.233938e+08 | 0.065% |
| `ice/qi/3` | −5.685992e-03 | −5.680085e-03 | 0.020% |
| `main/qr/1` | −1.506815e-10 | −1.505309e-10 | 1.9% (roundoff-scale value) |

The **operator** basis is byte-unchanged, because `rho_m` carries no `qv`:
`main/nr` stays 15.0036 / 13.3377 / 11.8402% and the ice cap share stays
100.00 / 100.00%. So no operator-basis headline moves.

A cell absent from the first call is **refused**, not recomputed — falling back
to that call's own density would silently restore the moving weight for exactly
the cells the window measure does not cover.

This does not settle what the physical measure *should be bound to*. Binding it
to the canonical dry-air layer mass the host dynamics carries is a separate
step; `G33-BASIS-002` remains the open compatibility question.
