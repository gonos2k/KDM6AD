# First-call response selectivity of the N x C x L arms, and an N x C masking interaction

**This finding replaces an earlier version that claimed the three corrections
"do not interact" and that "cross terms are at roundoff". That claim was wrong,
and its own table refutes it.** The owner's re-review computed the standard
interaction on the ice-number residual:

    I_NC = Y11 - Y10 - Y01 + Y00
         = 6.546e-20 - 7.540e-17 - 1.468e-01 + 1.703e-01
         = 0.0235                       -- 13.8 % of baseline

f32 machine epsilon is 1.19e-07. That is not roundoff.

What the first version actually observed was MARGINAL SELECTIVITY -- each
response moving with one factor -- and reported it as ORTHOGONALITY, which is a
statement about cross terms. The two are different claims and the first does
not imply the second. The earlier text even wrote "C moves `R_ni` only while
N=0", which IS the definition of an interaction, next to a heading saying there
was none.

## The response vector, signed

`g33_fixture_boundary_mapping_v1`, `nsplit = 12`, `rezero`, first call, the
same initial state on every arm. Residuals are relative to starting inventory
and **signed**: `|R|` is non-linear, hides sign reversal, and distorts any
coefficient computed from it.

`cap_sink` is the net interface cap term -- C's OWN invariant, absent from the
first version, which scored C only through its indirect effect on `R_ni`.
`partition` counts per-(split, column, level) final states differing between
the single tile and `(2,1)`.

| arm | NCL | R_nr | R_ni | R_qr | R_qi | cap_sink | partition |
|---|---|---|---|---|---|---|---|
| `legacy` | 000 | 3.685e-03 | 1.703e-01 | -1.011e-17 | -8.828e-17 | 2.435e+00 | 4.500e+01 |
| `nmass` | 100 | 1.936e-17 | 7.540e-17 | -1.011e-17 | -8.828e-17 | 2.435e+00 | 4.500e+01 |
| `lncmin` | 001 | 3.685e-03 | 1.703e-01 | -1.011e-17 | -8.828e-17 | 2.435e+00 | 0.000e+00 |
| `nmasslncmin` | 101 | 1.936e-17 | 7.540e-17 | -1.011e-17 | -8.828e-17 | 2.435e+00 | 0.000e+00 |
| `conservative` | 010 | 3.685e-03 | 1.468e-01 | -1.011e-17 | -6.822e-17 | -3.400e+00 | 4.500e+01 |
| `cons_nmass` | 110 | 1.936e-17 | -6.546e-20 | -1.011e-17 | -6.822e-17 | -3.110e+00 | 4.500e+01 |
| `cons_lncmin` | 011 | 3.685e-03 | 1.468e-01 | -1.011e-17 | -6.822e-17 | -3.400e+00 | 0.000e+00 |
| `cons_nmasslncmin` | 111 | 1.936e-17 | -6.546e-20 | -1.011e-17 | -6.822e-17 | -3.110e+00 | 0.000e+00 |

## Coefficients

Standard 2^3 contrasts on +/-1 coding, `beta_S = (1/8) sum (prod x_j) Y`.

Two conversions, so this table and the review's arithmetic are read as the same
numbers. `beta` is the HALF-effect: a factor whose 0 -> 1 step moves a response
by `d` has `beta = d/2`. And the review's `I_NC` is the two-level interaction at
fixed L, so `beta_NC = I_NC / 4` when L does not touch that response --
`0.0235 / 4 = 5.865e-03`, which is the entry below.

| response | native to | N | C | L | NC | NL | CL | NCL |
|---|---|---|---|---|---|---|---|---|
| `R_nr` | N | -1.843e-03 | -1.987e-20 | -1.987e-20 | -1.987e-20 | -1.987e-20 | -1.987e-20 | -1.987e-20 |
| `R_ni` | N | -7.927e-02 | -5.865e-03 | -8.182e-21 | 5.865e-03 | -8.182e-21 | -8.182e-21 | -8.182e-21 |
| `R_qr` | — | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `R_qi` | C | 0.000e+00 | 1.003e-17 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 |
| `cap_sink` | C | 7.247e-02 | -2.845e+00 | 1.931e-06 | 7.245e-02 | 6.955e-08 | -3.795e-06 | -1.368e-07 |
| `partition` | L | 0.000e+00 | 0.000e+00 | -2.250e+01 | 0.000e+00 | 0.000e+00 | 0.000e+00 | 0.000e+00 |

## What this says

**`R_nr` is N-selective, and there the cross terms really are at roundoff**:
every interaction coefficient is 1.99e-20 against a main effect of 1.84e-03.

**`partition` is L-selective**, every interaction identically zero.

**`R_qi` and `cap_sink` are C's**, and C does its own job: `beta_C(cap_sink)`
is -2.845, the largest main effect in the table, moving the net cap term from
+2.435 to -3.400.

**`R_ni` carries a real N x C interaction**, and its structure names it:

    beta_C(R_ni)  = -5.865e-03
    beta_NC(R_ni) = +5.865e-03

Equal magnitude, opposite sign. That is the signature of MASKING, not coupling:
C's effect exists only where N has not already removed the residual, so the
main effect and the interaction cancel exactly in the N=1 half. The same shape
appears in `cap_sink` (`beta_NC` = +7.245e-02 against `beta_N` = +7.247e-02).

So the defensible statement is selectivity plus a named saturation interaction
-- not orthogonality.

## Reproducing

    python harness/g33_factorial.py \\
        legacy=<bundle>/n3.rezero.txt,<bundle>/n21.rezero.txt \\
        ... one ARM=SINGLE,SPLIT per arm ... --json factorial_response.json

`coefficients()` refuses anything but all eight arms: a contrast computed off
seven is not a contrast.

## Over the whole window

The table above is the FIRST CALL, where every arm meets the same initial state
so a difference is the arm and nothing else. Accumulated over all twelve calls
of the 300 s window the arms hold different fields, so this is the operator over
its own trajectory -- the other question, not a more thorough version of the
first.

| response | N | C | L | NC | NL |
|---|---|---|---|---|---|
| `R_nr` | -2.154e-04 | -1.425e-05 | -9.77e-09 | +1.425e-05 | +9.77e-09 |
| `R_ni` | -1.092e-01 | -2.271e-02 | +1.827e-05 | +2.271e-02 | -1.798e-05 |
| `cap_sink` | 7.247e-02 | -2.845e+00 | 1.931e-06 | 7.245e-02 | 6.96e-08 |
| `partition` | 0 | 0 | -2.250e+01 | 0 | 0 |

Three things.

The legacy ice-number residual GROWS along the trajectory: 0.1703 on the first
call, 0.2637 over the window.

**The masking signature is preserved exactly.** `beta_C = -2.2713e-02` and
`beta_NC = +2.2713e-02`, still equal and opposite at four times the first-call
magnitude. Whatever the trajectory does to the size, the structure is the same:
C acts only where N has not already removed the residual.

And a term appears that the first call could not show. `beta_L` on `R_ni` is
1.83e-05 where it was exactly zero, with `NL` and `CL` at the same scale. That
is not L acquiring a number effect: it is the arms having DIFFERENT STATES after
call one, so the decomposition change reaches the residual through the fields
rather than through the operator. It is the reason the first call is the matched
comparison and this one is not.

## What is still not measured

- Whether the interaction stays a masking one over a TRAJECTORY. These are all
  first-call numbers on one identical initial state; the arms diverge
  afterwards precisely because their fields differ.
- One fixture, `nsplit = 12`, f32, `mstep > 1` not re-run.
- Nothing here is a forecast impact, a precipitation change, or a physical
  dry-air number statement -- Arm N closes the MOIST operator ledger
  (`dend = den`), and the dry-air arm is a separate experiment.
