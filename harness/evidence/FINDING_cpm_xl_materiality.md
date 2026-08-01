# How much the `cpm`/`xl` divergence is worth: 1.4–1.6 % of the freezing heat

Materiality estimate for the one item still awaiting adjudication. Computed
entirely from the v14 evidence and the freeze replay — **no production code was
run or changed**.

## Method

For every cell, replay the D2–D4 freeze heat twice with the **same rates** (they
are bit-identical between the backends at f64) and each backend's own coefficient:

    c_F = f32(xlf_F / cpm_F)        c_C = f32(xlf_C / cpm_C)
    heating = c_F · Σ rates         dT_err = (c_C − c_F) · Σ rates

`heating` is the latent warming that freeze block delivers; `dT_err` is the part
of it attributable to the coefficient divergence.

## Result

| loop | col | k | heating (K) | dT_err (K) | err / heating |
|---|---|---|---|---|---|
| 1 | 3 | 0–3 | 4.5e-05 … 8.5e-04 | **0** | **0 %** |
| 2 | 3 | 0 | 5.184e-04 | 7.238e-06 | **1.40 %** |
| 2 | 3 | 1 | 7.756e-04 | 1.152e-05 | 1.49 % |
| 2 | 3 | 2 | 1.133e-03 | 1.775e-05 | 1.57 % |
| 2 | 3 | 3 | 1.642e-03 | 2.698e-05 | **1.64 %** |
| 3 | 3 | 0–3 | 4.8e-04 … 1.4e-03 | 6.7e-06 … 2.3e-05 | 1.39 – 1.64 % |

**Loop 1 is exactly zero** — the coefficients agree there, as the
"fixed at kernel entry vs re-fixed at sub-cycle entry" characterisation predicts.

## What is robust, and what is not

The **absolute** error here is negligible — 2.7e-05 K at worst — but that is a
property of this fixture, where the freeze block delivers at most 1.6e-03 K of
heating. It says nothing about a real case.

The **ratio** is the robust quantity, because both the heating and the error are
`c × Σrates` with the same rates: the error is a fixed fraction of whatever
latent heating the freeze block delivers, independent of how large that is.

    a cell whose freezing warms it by  1 K   carries ≈ 16 mK of error
                                      10 K   carries ≈ 0.16 K

The ratio also grows down the column (1.40 % at k 0 to 1.64 % at k 3) and is
essentially unchanged between loops 2 and 3, tracking how far each cell's state
has moved from the sub-cycle entry the port re-fixed at.

## Three things this does NOT bound

- **Only the freeze block is measured.** `cpm` and `xl` are read by the melt heat
  term, by `xlwork2` in the state update, and by the saturation-adjustment path.
  This is one consumer of several, so 1.4–1.6 % is a floor on the effect of the
  divergence, not a total.
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
