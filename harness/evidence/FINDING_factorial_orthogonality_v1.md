# The N x C x L factorial: one reader, control and span per response

This finding has been wrong three times, in ways that were visible in its own
table each time.

The first version called the three corrections ORTHOGONAL from a table of
absolute residuals whose `I_NC` was 0.0235 -- 13.8 % of baseline against an f32
epsilon of 1.19e-07. What it had observed was MARGINAL SELECTIVITY, which is a
different claim and does not imply the second.

The second version fixed the mathematics and left a defect in the instrument.
`window` selected the span for the four residual responses and nothing else:
the cap walked the whole stream and `partition` counted every sub-step, in BOTH
tables. Measured, the two were bit-identical across the two spans -- which reads
as "the trajectory does not move them" and was really the same whole-window
number printed twice. So the "first-call" table was a hybrid of first-call
residuals and whole-window diagnostics, and no statement about C or L in it was
a first-call statement.

The third version gave every response the same span and then gave them all the
same READER and the same CONTROL POLICY, which re-mixed what the span fix had
just separated. Rejecting an arm because its mass control failed deletes the C
response from the C experiment, since a failing mass closure is the defect C
exists to remove. Measured: on this fixture the main-chain `qr` control passes
on every arm (3e-02 at worst) while ice fails, and a scorable actual-transfer
`R_nr` was being discarded by an ice-chain verdict it does not depend on.

Now each response carries its own reader, control, span and verdict, and a
contrast is computed only where the response is valid in all eight arms.

## What is withdrawn

**"C moves its own cap invariant on the first call."** The published figures
(+2.435 -> -3.400) were the whole 300 s window. On the first call the ice cap
term runs +3.540e-02 -> -1.988e-02, about seventy times smaller.

**"The same N x C shape appears in the cap."** It does not, on either span. On
the first call the cap has NO N x C interaction at all: the conditional effect
of C is -9.379e-01 at N=0 and -9.379e-01 at N=1, identical, and every cap
`beta_NC` is exactly zero. The +7.245e-02 that was read as a masking signature
was a whole-window number sitting in a first-call table.

Over the window there IS an N x C term, and it is the OTHER shape:

    R_ni           C at N=0  -9.085e-02     C at N=1   3.198e-17
    cap_ice_rel    N at C=0   1.691e-04     N at C=1  -1.564e-02

`R_ni` is C masked by N -- C acts only while N has not already removed the
residual. The cap is N gated by C -- N acts only while C is present. Both are
N x C interactions and they are not the same sentence; one `beta_NC` cannot
tell them apart, which is why conditional effects are now reported beside it.

**"`partition` is L-selective on the first call."** After ONE sub-step the two
decompositions agree completely: `partition_first` is 0 for all eight arms, so
there is nothing for L to be selective about there. The 45 that was published
is a PATH count over all twelve sub-steps. The three questions are now separate:

| response | legacy | `lncmin` | beta_L |
|---|---|---|---|
| `partition_first` | 0 | 0 | 0 |
| `partition_endpoint` | 4 | 0 | -2.000 |
| `partition_path` | 45 | 0 | -2.250e+01 |

L's effect is real and it is a TRAJECTORY effect, not a first-call one.

## What survives

**`R_nr` is N-selective on the first call**, and there the cross terms really
are at roundoff: every interaction coefficient is 1.99e-20 against a main effect
of 1.843e-03 and a screening scale of 5.97e-08.

**`D_ni_metric` carries an N x C MASKING interaction on both spans.**

The name matters and this finding had it wrong. `D_ni_metric` is the
ENDPOINT-RECOVERED number-metric residual; `R_ni` is the actual-transfer
budget, and they are different quantities. The published masking result is the
first of them:

    first call   beta_C = -5.865e-03   beta_NC = +5.865e-03
    window       beta_C = -2.271e-02   beta_NC = +2.271e-02

The actual-transfer `R_ni` contrast is NOT scorable across all eight arms on
this fixture, because the C=0 half fails its ice mass control. What it does
give, in the C=1 half where the control closes, is a conditional -- see below.

Equal and opposite on each span: C's effect exists only where N has not already
removed the residual, so main effect and interaction cancel exactly in the N=1
half. Both are resolved -- the screening scale is 6.4e-08 and 6.6e-08.

This is a statement about the two operators' measured interaction on this
fixture. It is not a demonstration that the two physical processes are
dynamically coupled.

**The matched control is now verified mechanically.** On the first call every
`_den` response -- the starting inventory each arm was handed -- is identical
across all eight arms, `beta = 0` exactly. `same_atmosphere()` refuses a table
where it is not.

## What the cap actually does, and what the mass rows could not say

`Sink.signed` says in its own docstring that it is a SIGNED DEFECT and not a
sink, and offers `destroyed`/`created` separately for exactly this reason.
Summing every chain and column into one signed scalar hides the direction, and
a reversal was read as C "doing its job". Split, ice chain, kg m-2:

| span | arm | destroyed | created | signed |
|---|---|---|---|---|
| first call | `legacy` | 3.540e-02 | 0.000 | +3.540e-02 |
| first call | `conservative` | 0.000 | 1.988e-02 | -1.988e-02 |
| window | `legacy` | 2.435 | 0.000 | +2.435 |
| window | `conservative` | 0.000 | 3.380 | -3.400 |

Read alone, that says C removes the destruction and replaces it with creation.
It is not enough to conclude either way, because the interface term is not the
column budget -- and the response that was supposed to be the column budget
could not answer.

**`R_qi` closes by construction under the recovered reader.** `column()`
recovers the transfers by INVERTING the update, so the budget it rebuilds
cannot fail to balance; the module's own header says the mass rows "return ~0
BY CONSTRUCTION of their weight". Reading the ACTUAL `XFER` records instead,
on the same first call of the same fixture:

| arm | recovered `R_qi` | matched, from actual transfers |
|---|---|---|
| `legacy` | -8.828e-17 | **-6.006e-01** |
| `conservative` | -6.822e-17 | **+2.306e-08** |

Legacy's ice mass column does not close on the first call: it is short by
60.06 % of its starting inventory, which is EXACTLY the cap interface term
(+6.006e-01 signed, same number, opposite sign by the `signed = -mass_term`
convention). And the conservative arm closes it to 2.3e-08.

So **C does restore the ice mass budget on the first call**, and the
"replaces destruction with creation of larger magnitude" reading came from the
interface term alone. For the conservative arm that term is -3.373e-01 while
its column closes, so for that arm the operator-basis interface term is no
longer the budget defect -- which is what the corrected interface changes.

The general lesson is the one this cycle keeps paying for: a response that
cannot fail is not a control. `R_qi` at 1e-17 was read as "the mass closes" in
the previous version of this finding, and the mass did not close.

## The window ratio moves through BOTH numerator and denominator

Over the window the arms hold different fields, so `R_ni`'s denominator -- the
number inventory each arm reached -- is no longer common:

    beta_L(R_ni_num) = +1.808e+04        beta_L(R_ni_den) = -9.891e+05
    beta_C(R_ni_den) = +8.337e+08        beta_N(R_ni_den) = -6.155e+08

The earlier text attributed the window's small `beta_L(R_ni)` to the
decomposition change "reaching the residual through the fields". Both terms
move, and a ratio cannot say which drove it, so numerator and denominator are
now separate responses. The accurate sentence is that the local-threshold
correction changes the trajectory state, and that changed state alters both the
defect generated and the inventory it is measured against.

## Units

Responses carry their units and are not comparable across rows. A coefficient on
a dimensionless ratio and one on a mass term are different kinds of quantity, so
nothing here reports a "largest effect in the table" -- a sentence the previous
version did use, about `beta_C(cap) = -2.845` beside `beta_N(R_ni) = -0.079`.

Each coefficient is reported against a screening scale computed from its own
terms, `sum|terms| * (U32 + gamma(n, U64))`, rather than against a bare epsilon:
the inputs are f32, so nothing derived from them resolves below that. Integer
counts are exact and are not screened.

## What the per-response policy measures that nothing could before

**`R_qi` is a response, not a rejection criterion.** First call:
`beta_C = +3.0030e-01`, legacy -6.006e-01 to conservative 2.306e-08. C's own
outcome, scored.

**Matched `R_nr` scores for the first time**: `beta_N = -1.8426e-03`, every
cross term at 1.4e-20, under the main-chain mass control which closes on all
eight arms.

**`mstep > 1` is no longer a blanket NO-GO.** On
`g33_fixture_multisubcycle_v1` at `nsplit = 3`, `mstep <= 10`:

| response | control | result |
|---|---|---|
| `R_qr` | none needed | `beta_C` = +2.3163e-02 |
| `R_qi` | none needed | `beta_C` = +3.7655e-01 |
| `R_nr` | `main/qr` | not scorable -- C=0 half fails |
| `R_ni` | `ice/qi` | not scorable -- C=0 half fails |
| `D_*_metric` | -- | not scorable -- 4 and 5 of 9 rows recoverable |

and within the C=1 half, where the mass control closes:

    N_at_C1(R_nr) = -1.06042e-02      (1.06042e-02 -> -5.83e-09)
    N_at_C1(R_ni) = -2.56255e-02
    N_at_C0       = not evidence

That is the campaign's FIRST controlled measurement of Arm N above one
sub-step, from actual transfers. `N_at_C0` reports "not evidence" rather than a
number: the validity discipline must not leak through the conditionals.

**`partition_window_final` is a different count from the last segment.** The
last post-sedimentation segment is not the window final state -- other
microphysics runs after sedimentation in the same call. Reading the driver's own
`outF` block instead:

| response | legacy | `lncmin` | beta_L | beta_N |
|---|---|---|---|---|
| point | legacy cells | legacy components | `lncmin` |
|---|---|---|---|
| first segment | 0 | 0 | 0 |
| last segment | 4 | 38 | 0 |
| **window final** | **4** | **33** | 0 |
| path | 45 | 416 | 0 |

**AND THE EARLIER READING OF THIS TABLE WAS A UNIT ERROR.** It reported
`4` at the last segment beside `32` at the window final and called the
difference growth. Those were a CELL count and a COMPONENT count: a cell is a
`(split, column, level)` differing in at least one field, a component is one
`(field, column, level)`. Measured in matched units there is no growth at all --
4 cells at both points, and the component count NARROWS, 38 to 33. The `32` was
also wrong for legacy specifically, which is 33; the L=0 arms average 32.75,
which is where `beta_L = -16.375` came from.

What survives, and is now measured in both units at all four points: every
`lncmin`-family arm is exactly 0 everywhere, and every L=0 arm is not. Arm L
collapses the decomposition dependence completely; it does not merely shrink
it.

## What the actual-transfer budget says at mstep > 1

On `g33_fixture_multisubcycle_v1`, `nsplit = 3`, `mstep <= 10`, the C=0 half
fails its mass control and the C=1 half closes, so the contrast is not scorable
and the conditional is:

    N_at_C1(R_nr) = -1.06042e-02        N_at_C1(R_ni) = -2.56255e-02
    N_at_C0       = not evidence

and the SIMPLE effects underneath say the average is safe to quote: both are
identical at L=0 and at L=1, so no N x L interaction is hidden inside that
half.

## The contract a figure from this table has to pass

Every response carries `{value, unit, reader, span, paired_control, valid,
reason, screening_bound}`, an invalid contrast carries `None` in every term,
and `bindable(beta, term)` is the single door a coefficient goes through to
reach `CLAIMS.yaml`. A contrast computed over arms whose control failed is not
a contrast, and the check is a function rather than something each caller is
trusted to remember.

The identity a cross-arm comparison needs is complete now: algorithm, nsplit,
mode, rho, width, levels, delt, dtcld, loops, **fixture** and window seconds.
The fixture was the gap -- the driver had imported `FIXTURE_ID` since it was
written and never emitted it, so eight arms could be compared without anything
checking they ran on one atmosphere.

And an averaged conditional says whether it may stand for its halves.
`N_at_C1` is the mean of `N_at_C1_L0` and `N_at_C1_L1`; where those differ,
quoting the mean hides an N x L interaction inside that half. At mstep <= 10
they are identical to the last digit on every response, so the average is
representative -- measured, with the flag computed from the response's own
screening scale.

## What is still not measured

- Longer than 300 s, and any real atmospheric column.
- `mstep > 1` for the NUMBER responses. The mass responses are now measured
  there (above); what remains unavailable is `R_nr`/`R_ni` in the C=0 half.
  Previously stated as a blanket NO-GO, and that was too broad. The recovered reader
  refuses it -- measured, 1 of 3 rows recoverable at `nsplit = 3` on
  `g33_fixture_multisubcycle_v1`, where the old code would have returned a
  ratio over the one that survived. The actual-transfer reader is admissible at
  any `mstep` and refuses too, on its own control: the chain mass rows fail
  their gamma_n screening threshold on every fixture available here -- 4 of 6
  at `nsplit = 3` (worst 6.9e+05x), 2 of 6 at `nsplit = 24` (9.2e+05x), and
  3 of 6 on `g33_fixture_boundary_mapping_v1` itself (1.4e+06x). The module's
  rule is that the mass row is the control for the number row beside it, so
  neither is evidence there. An `mstep > 1` factorial needs a fixture whose
  mass accounting closes, not a different reader.
- The physical dry-air basis, which is `FINDING_number_basis_gap_v1`.

## Reproducing

    python3 harness/g33_factorial.py \
        legacy=<single>,<split> ... one ARM=SINGLE,SPLIT per arm \
        [--window] --json factorial.json

Every arm's streams are checked against the arm NAME from their own headers,
the two decompositions must agree on fixture, nsplit, mode, rho, width and
levels and must differ in tile count, the partition universes must match
exactly, and the residual coverage must be complete. Any of those failing is a
refusal, not a footnote.
