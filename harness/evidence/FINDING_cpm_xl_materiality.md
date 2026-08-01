# How much the `cpm`/`xl` divergence is worth: 1.4–1.6 % of the freezing heat

Materiality estimate for the one item still awaiting adjudication. Computed
entirely from the v14 evidence and the freeze replay — **no production code was
run or changed**.

## Method

For every cell, replay the D2–D4 freeze heat twice with the **same rates** (they
are bit-identical between the backends at f64) and each backend's own coefficient:

    c_F = f32(xlf_F / cpm_F)        c_C = f32(xlf_C / cpm_C)
    analytic_freeze_heat_contribution = c_F · Σ rates
    analytic_difference               = (c_C − c_F) · Σ rates

Both are CONTINUOUS quantities. The model stores `t` through three sequential f32
rounds, so neither equals the stored-state difference; the discrete counterpart is
below. Naming them "heating" and "error" invited exactly that conflation (owner
review §5).

## Result

| loop | col | k | analytic freeze-heat contribution (K) | analytic difference (K) | ratio |
|---|---|---|---|---|---|
| 1 | 3 | 0–3 | 4.5e-05 … 8.5e-04 | **0** | **0 %** |
| 2 | 3 | 0 | 5.184e-04 | 7.238e-06 | **1.40 %** |
| 2 | 3 | 1 | 7.756e-04 | 1.152e-05 | 1.49 % |
| 2 | 3 | 2 | 1.133e-03 | 1.775e-05 | 1.57 % |
| 2 | 3 | 3 | 1.642e-03 | 2.698e-05 | **1.64 %** |
| 3 | 3 | 0–3 | 4.8e-04 … 1.4e-03 | 6.7e-06 … 2.3e-05 | 1.39 – 1.64 % |

**Loop 1 is exactly zero** — the coefficients agree there, as the
"fixed at kernel entry vs re-fixed at sub-cycle entry" characterisation predicts.

## What the ratio is, and what it is not (owner review §5)

The **absolute** difference here is negligible — 2.7e-05 K at worst — but that is
a property of this fixture, where the freeze block delivers at most 1.6e-03 K of
heating. It says nothing about a real case.

The **ratio** is exact *for this counterfactual*: both quantities are `c · Σrates`
over the **same** rates, so

    (ΔT_C − ΔT_F) / ΔT_F  =  (c_C − c_F) / c_F

holds identically at that cell in that state. What it is **not** is a constant of
the scheme. `c_C − c_F` is itself `c(T_l, q_{v,l}) − c(T_0, q_{v,0})`, so it
depends on how far the state has moved, on the number of outer loops, and on the
rate–state feedback that moved it. So:

    a cell whose freezing warms it by  1 K   →  ≈ 16 mK
                                      10 K   →  ≈ 0.16 K

is a **linear extrapolation under the assumption that this fixture's loop-2/3
coefficient ratio carries over**. It is a scale for reasoning, not a prediction
for a case.

Within this fixture the ratio does move: 1.40 % at k 0 to 1.64 % at k 3, tracking
how far each cell has drifted from the sub-cycle entry the port re-fixed at.

## The discrete counterpart, measured (owner review §6)

The artifact now carries the 2×2 exact counterfactual at the seed cell — the three
sequential f32 stores replayed with each combination of the two coefficients —
and the Shapley split, which averages both attribution orders so neither operand
absorbs the interaction:

```
T(xlf_F,cpm_F) = 0x437396ba        T(xlf_C,cpm_C) = 0x437396bb
total stored ΔT = 1.5259e-05 K  =  exactly 1 ULP
Shapley:  xlf  1.5259e-05 K        cpm  0.0 K
```

So the two layers say different things and both are true:

| | `xlf` | `cpm` |
|---|---|---|
| analytic (relative) | +1.344 % | −0.052 % |
| discrete (stored ΔT) | **1 ULP** | **0** |

`cpm`'s share is real in the coefficient and vanishes in the f32 store at this
cell. That is not "xlf is the cause" — both operands differ, and both are
consequences of one policy difference — it is the statement that at this cell, at
storage granularity, only `xlf`'s share survives the rounding.

## Three things this does NOT bound

- **Only the freeze block is measured, and 1.4–1.6 % is NOT a floor.** (Owner
  review §4 — the earlier wording here said "floor" and that is wrong.) `cpm` and
  `xl` are also read by the melt heat term, by `xlwork2` in the state update, and
  by the saturation-adjustment path. Writing the total as

      E_total = E_freeze + E_melt + E_state + E_satadj + …

  gives `|E_total| ≤ Σ|E_i|` by the triangle inequality — an **upper** bound. It
  does **not** give `|E_total| ≥ |E_freeze|`: the other terms can carry the
  opposite sign and cancel. What this number is: **one measured process
  contribution**, neither a lower nor an upper bound on the total.
- **Sub-cycle count matters and is not varied here.** The port re-fixes at every
  sub-cycle entry; this fixture runs three. A step with more sub-cycles gives the
  coefficient more opportunities to move.
- **Which behaviour is correct is not settled by any of this.** The reference
  fixes the coefficients once per kernel call under an explicit comment
  ("neglect the changes during microphysical process calculation, emanuel(1994)").
  The port's refresh is arguably the better physics. This measures the size of the
  gap, not which side of it to stand on.

## Status

Variant-independent — both Fortran legs agree and both C++ legs agree — so this
is legacy-shared port fidelity and not the conservative interface. Both trees are
frozen. Adjudication is the owner's.
