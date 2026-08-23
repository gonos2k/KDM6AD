# The ice chain's ledger measures conversion, so no arm can be read on it here

The review asks for the physical number correction to be generalised from rain
to ice, by building `cons_nmass_dry` on a mass-closed conservative base and
checking that `R_ni` goes to roundoff under a control where `R_qi` does. The
arm was not built, because the reading it would be judged by does not work on
this fixture -- and that is measurable before spending a build.

## What the ledger says about ice

`g33_fixture_moisture_gradient_v1`, legacy, 12 calls, window-initial physical
ledger:

| species | sum of surface flux | residual | residual / starting inventory |
|---|---|---|---|
| `qr` rain mass | 2.382e-01 | 5.043e-05 | **6.9e-06** |
| `nr` rain number | 9.655e+05 | 1.007e+04 | 1.6e-04 |
| `qi` ice mass | 1.123e-02 | **6.023e-01** | **97.7 %** |
| `ni` ice number | 1.192e+07 | 7.131e+08 | 16-24 % |

`qi` is a MASS species, and mass conserves to roundoff under this operator --
`FINDING_p0_4_water_budget` measures exactly that on the rain chain, and `qr`
above shows it again at 6.9e-06. Ice mass leaving a residual of 97.7 % of the
column's inventory is therefore not a conservation failure. It is the LEDGER
being out of scope.

The surface flux is 1.123e-02 against a residual of 6.023e-01 -- **a factor of
54.** The ice did not fall out of the bottom. It left the ice chain by melting,
riming, aggregation to snow and graupel, and sublimation -- conversion terms a
sedimentation-transport ledger does not carry, and was never built to.

## Why the conservative base does not fix it

The conservative arms change what the interface CAP does to a transfer, which is
why they close the mass budget where legacy's cap sinks it. That is a different
problem from this one. Here the transfer is not being capped away; it is being
correctly transported and then converted into a species the ledger stops
following. Any base, any arm, the same denominator.

The arm's effect on ice IS present and IS swamped: across `nmass`, `nmass_dry`
and `nmass_dry_window` the `ni` ratio moves from -45.68 to -45.57 to -45.53 in
column 1, about 0.2 %, under a residual two orders larger than the flux
normalising it. A 0.2 % move inside that is not a measurement.

## What would be needed

Either a ledger that carries the conversion terms -- a full ice-phase budget
across `qi`, `qs`, `qg` and their number species, which is a new instrument --
or a fixture where ice sediments WITHOUT converting: cold enough throughout that
melting is off, and thin enough in the other hydrometeors that riming and
aggregation do not fire.

That is a fixture problem and not a member-count problem, the same shape as
`FINDING_g33_fixture_cannot_answer_thermo_policy_v1`: the question is not
under-sampled, it is not defined in the region the fixture occupies.

## What this does establish

That rain-chain results do NOT generalise to ice on the strength of the shared
edit. The N-family edits change two statements, one per chain, and the rain one
is measured while the ice one is not. Anything said about the ice chain from
this fixture would be said from a ratio whose denominator is 54 times too small.

One fixture, one operator, `mstep = 1`, f32.
