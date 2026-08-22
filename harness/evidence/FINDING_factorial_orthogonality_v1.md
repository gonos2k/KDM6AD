# The N x C x L factorial on one span, and three statements withdrawn from it

This finding has been wrong twice, in ways that were visible in its own table
both times.

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

Every response now takes the same span, and the span is part of the result.

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

**`R_ni` carries an N x C MASKING interaction on both spans.**

    first call   beta_C = -5.865e-03   beta_NC = +5.865e-03
    window       beta_C = -2.271e-02   beta_NC = +2.271e-02

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

## What the cap actually does, once destruction and creation are separated

`Sink.signed` says in its own docstring that it is a SIGNED DEFECT and not a
sink, and offers `destroyed`/`created` separately for exactly this reason.
Summing every chain and column into one signed scalar hides the direction, and
a reversal was read as C "doing its job".

Ice chain, whole window, kg m-2:

| arm | destroyed | created | signed |
|---|---|---|---|
| `legacy` | 2.435 | 0.000 | +2.435 |
| `conservative` | 0.000 | 3.380 | -3.400 |

C removes the destruction completely -- and replaces it with creation of larger
magnitude. `|signed|` goes from 2.435 to 3.400. So on this fixture the
conservative arm meets half of what restoring its own invariant would require
(`destroyed -> 0`) and moves the other half further from it (`created -> 0`
fails, and by 40 % more than what it removed).

That is a measurement of the interface term as `g33_cap_interface` defines it,
on one fixture. It is NOT a claim that the conservative arm creates water in the
column budget: the ice mass residual `R_qi` is at roundoff in every arm on both
spans, so whatever these interface terms are, they are not showing up as column
non-closure here.

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

## What is still not measured

- Longer than 300 s, and any real atmospheric column.
- `mstep > 1`. `column()` refuses it, and the analyzer now REFUSES the table
  rather than returning a ratio over whichever rows happened to survive. A
  factorial at `mstep ~ 10` needs the actual-transfer reader, not this one.
- Whether C's creation term is a defect in a budget that matters. `R_qi` says it
  is not visible in the column ice mass on this fixture.
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
