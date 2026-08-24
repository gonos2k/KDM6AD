# The ice chain does not close per call either, and the rain chain does

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

## Measured on the conservative base, because it does not follow

The review objected that legacy admitting no call does not make the conservative
base unusable: the C correction changes what the interface cap does, and so
changes `qi` closure itself. That is right, and it needed no new arm -- the
existing `conservative` and `cons_nmass` arms run on this fixture.

| base | `qi` median \|R\|/start | `qi` max | admissible |
|---|---|---|---|
| `legacy` | 4.9184e-03 | **1.000** | **0** of 36 |
| `conservative` | 4.3900e-03 | **9.301e-03** | **0** of 36 |
| `cons_nmass` | 4.3849e-03 | 9.297e-03 | **0** of 36 |

`qr` is 22 of 36 on all three, so the instrument is working on all three.

**The C correction does change ice closure, and by a lot -- in the tail.** Legacy
has a call in which the ENTIRE starting ice inventory is unaccounted for, a
ratio of 1.000; under the conservative base the worst call is 9.3e-03. Two
orders. So the objection was well founded and the inference this finding first
drew was not available.

**The median barely moves** -- 4.92e-03 to 4.39e-03 -- and stays about 3 000
times the tool's own per-call tolerance of 1.43e-06 of `start`. So the
admissible set is empty on every base available here, and now by measurement on
each rather than by extension from one.

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

## The per-call test, run

The review objected that a whole-window `qi` ledger failing does not make a
PER-CALL ice sedimentation test impossible: bracket each call's
`outer_pre_sed -> outer_post_sed` with its emitted `XFER`, keep only the calls
whose MASS row closes, and compare arms on the number row over those. Conversion
between calls is then absorbed into each call's new initial state.

That is right as method, and the harness already carries the bracket
(`g33_matched_closure(..., "physical")`, `per_call`). Run on the gradient
fixture, legacy, 36 calls (12 x 3 columns), `|residual| / start`:

| tolerance | `qr` calls admissible | `qi` calls admissible |
|---|---|---|
| 1e-07 | **22** of 36 | **0** of 36 |
| 1e-06 | 22 | 0 |
| 1e-05 | 22 | 0 |
| 1e-04 | 29 | 0 |
| 1e-03 | 36 | **0** |
| 1e-02 | 36 | 22 |

Median `|residual| / start`: `qr` **3.54e-08**, `qi` **4.92e-03**, with an ice
maximum of **1.00** -- a call in which the entire starting ice inventory is
unaccounted for by sedimentation plus surface flux.

**`qr` is the positive control and it passes.** The bracket, the emitted
transfer and the screen all work: 22 of 36 rain calls close to 1e-07 on the same
instrument, in the same stream, over the same calls. So the empty ice column is
not an instrument that cannot detect closure. It is ice not closing.

Under any tolerance tight enough to mean "mass-closed", the admissible set on
this fixture is **empty**, so the arms have nothing to be compared over. The
review's redesign is runnable and returns nothing here -- which is a measurement,
where this finding previously had an argument.

### And the tool's own screen says the same thing -- I had misread it

This section first claimed `g33_matched_closure`'s per-call screen "is about
2.0 x the starting inventory, so it admits a 200 % error", and that all 36 ice
calls "close" against it. **That was a misreading of the tool, not a defect in
it.** `scale` is the SUM OF MAGNITUDES that cancelled -- `|start| + |final| +
|surface|`, so about `2 x start` by construction -- and the screen is
`control_tolerance(ops, scale) = gamma_n * scale`, which is smaller by the
operation count.

Measured against the tool's actual screen:

| species | median tolerance / start | calls within tolerance |
|---|---|---|
| `qr` | 1.4305e-06 | **22** of 36 |
| `qi` | 1.4270e-06 | **0** of 36 |

which is exactly the hand-rolled sweep above -- 22 and 0 -- from the tool's own
threshold rather than a tolerance chosen here. So the conclusion does not change
and its support is stronger: the instrument had a tight screen all along, and
reading `scale` as if it were that screen was mine.

## What would be needed

Either a ledger that carries the conversion terms -- a full ice-phase budget
across `qi`, `qs`, `qg` and their number species, which is a new instrument --
or a fixture where ice sediments WITHOUT converting: cold enough throughout that
melting is off, and thin enough in the other hydrometeors that riming and
aggregation do not fire.

That is a fixture problem and not a member-count problem: the question is not
under-sampled, it is not defined in the region the fixture occupies. More calls,
more columns and more arms all sample the same region, and the region does not
contain a sedimentation-only ice signal to find.

(This sentence originally cited a finding by name that **does not exist** --
`FINDING_g33_fixture_cannot_answer_thermo_policy_v1`. The fact is real and is
recorded in the campaign's working notes, but I promoted a remembered fact to a
filename, so a reader following the citation would have found nothing and the
claim would have been resting on an absence. The argument is made here instead
of borrowed.)

## What this does establish

That rain-chain results do NOT generalise to ice on the strength of the shared
edit. The N-family edits change two statements, one per chain, and the rain one
is measured while the ice one is not. Anything said about the ice chain from
this fixture would be said from a ratio whose denominator is 54 times too small.

One fixture, one operator, `mstep = 1`, f32.
