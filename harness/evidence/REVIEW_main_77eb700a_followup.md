# Review response: `main` at `77eb700a`

The owner's comprehensive re-review put four experiments first and graded the
three mechanisms. This records what each became. It is a checklist, not a
finding: the numbers belong to the claims and bundles it points at.

Its central instruction was scope, not technique:

> 이제 핵심은 corrected counterfactual을 적용했을 때 예측한 불변량이
> 회복되는가, 그리고 실제 기상 상태에서도 효과가 재현되는가

## Before the freeze-lift

Three results, none of which needed the frozen kernel. They share one move:
**separate the defect's COEFFICIENT from its EFFECT**, and the coefficient can
be measured on real data while the effect waits on an arm.

| what | result |
|---|---|
| §3.6 first link | the residual is an IDENTITY -- twelve rows, ratio 1.000000000000 |
| real atmosphere | `eps = den(lower)/den(upper) - 1`, LC05 2.5M interfaces, median 8.59 %, 11.2 % aloft |
| `ncmin` exposure | 39.1 % of columns mis-thresholded at one patch; 35.7 % disagree between one and eight |
| `ncmin` sensitivity | **negative** -- neither state on this host can bridge exposure to effect |

The negative result is kept because a bound quoted without its sensitivity
term reads as an effect.

## After the freeze-lift

**Arm N** (`--algo nmass`) weights the interface number transfer by air mass.
Two lines -- the only two of seven transfer sites in that loop without a
density factor. Across the density matrix, first call, same initial state:

    rho          legacy R/F_surface      Arm N
    as-is        11.84 .. 15.00 %        <= 0.0002 %
    inverted    -12.82 .. -16.20 %       <= 0.00007 %
    x2           23.38 .. 29.00 %        <= 0.00009 %
    uniform       0.000022 %          ==  0.000022 %

`uniform` is the control and the arm changes nothing there to the last digit.
Mass is unmoved bit for bit. §3.6's chain is closed on this fixture.

**Arm L** (`--algo lncmin`) makes `ncmin` per-column. The loop that sets it
ALREADY walked every column; writing a scalar made each iteration overwrite
the previous. Comparing per-(split, global column, level) final state against
the single-tile run:

    partition       legacy        Arm L
    (1,2)           0 / 144       0 / 144
    (2,1)          45 / 144       0 / 144
    (1,1,1)        22 / 144       0 / 144

`(1,2)` agreeing under legacy is not luck -- its last column is land, the same
type the single tile ends on. That row is why one agreeing partition proves
nothing.

**The factorial's eight arms are GENERATED** (`make_factorial_variants.py`),
not hand-edited: each edit stated once, asserted to match exactly twice, the
no-edit arm byte-identical to its base, and no generated line longer than the
canonical maximum -- a lengthened continuation is the edit whose truncation
compiles and computes something else.

## What this cost

Changing `g33_expectation.py` moved `verifier_semantics_sha256`, and the index
gate refused to keep the four-case artifact `current`. Regeneration was
attempted and refused twice -- correctly -- because the Gate A scope report is
not on this host, only its digest. The artifact is WITHDRAWN with its reason
in the file, and `current_decision_result` is null.

The four-case decision is OPEN until that report is available. That is worse
than yesterday and honest: the alternative was a verdict marked current that
this tree cannot reproduce.

## Open

- N x C x L factorial: arms generated, not yet run.
- `ncmin` sensitivity on a spun-up double-moment state over mixed coast.
- Real MPI one-step (`np = 1, 2, 4`).
- f32/f64 four-arm precision decomposition.
- Forcing VJP -- after the forward corrected physics settles.
