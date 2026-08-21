# What Arm N leaves against the physical number measure, over a real atmosphere

Arm N closes the OPERATOR's number ledger: its residual collapses to roundoff
across the density matrix (`G33-NUMBER-010`). That ledger is MOIST --
`dend(i,k) = den(i,k)` at F:870 -- while the physical column number is taken in
DRY mass, because `nr` is per kg of dry air (`G33-BASIS-006`). So a gap remains
by construction, and `G33-BASIS-002` has been holding a decision open about it
without a size. This is the size.

No kernel change and no freeze-lift. The per-interface coefficient falls out of
the same identity, with the transfer cancelling, so it is a function of the
PROFILE alone.

## The closed form

With `A` the density the kernel weights the interface transfer by and `B` the
measure the ledger is taken in, one interface delivers

    eps = [B(lower)/B(upper)] * [A(upper)/A(lower)] - 1

| reading | A | B | eps |
|---|---|---|---|
| legacy, operator measure | 1 | `den` | `den(lo)/den(up) - 1` |
| legacy, physical measure | 1 | `den_d` | both terms |
| **Arm N, physical measure** | `den` | `den_d` | **`(1+qv_up)/(1+qv_lo) - 1`** |

`den_d = den/(1+qv)`. The third line is the result: what Arm N still leaves is
PURELY THE MOISTURE JUMP and does not depend on the density profile at all.

And the two compose exactly:

    1 + eps_legacy_dry = (1 + eps_legacy_moist) * (1 + eps_armn_dry)

verified on the data, not asserted -- max absolute error 4.44e-16 over 2 507 544
interfaces. So the legacy defect against the physical measure FACTORISES into a
density term and a moisture term, and Arm N removes exactly the first.

## Why no published fixture could answer this

Every stream in the archive that carries `qv` carries it UNIFORM in the column.
Measured across `kdm6ad-g33m-armn` (12 members), `-f64` (135) and `-migrate`
(144): maximum in-column spread exactly 0.0. Under a uniform profile the
moisture term is identically 1, the two ledgers differ by a constant per column,
and that constant cancels out of every ratio and every residual-over-start
figure.

That is not a hole in Arm N's evidence. It is the reason the basis question
stayed open on fixture evidence: the fixtures cannot distinguish the two
measures, so nothing measured on them was ever going to. It takes a moisture
GRADIENT, which is what a real state has.

## The measurement

`host/lc05_da_run/wrfinput_d01`, the real 5 km SS case. 2 507 544 interfaces.

| coefficient | median | mean | abs p90 | abs max |
|---|---|---|---|---|
| legacy, operator measure | 8.588e-02 | 7.027e-02 | 1.088e-01 | 1.151e-01 |
| legacy, physical measure | 8.557e-02 | 6.980e-02 | 1.088e-01 | 1.151e-01 |
| **Arm N, physical measure** | **-1.246e-04** | -4.529e-04 | 1.450e-03 | 7.079e-03 |

What Arm N leaves, as a fraction of what legacy had against the same measure:
median 0.33 %, p90 4.62 %.

The fraction exceeds 10 % at 2.15 % of interfaces, and its maximum is 3588 --
which is a denominator artefact, not a defect. Those are near-isopycnal
interfaces where legacy had almost no defect to remove: at that tail the median
absolute values are 8.20e-03 for legacy and 1.72e-03 for Arm N. A large share of
nearly nothing. The tool reports both, so the ratio is never read without its
scale.

By level, the moisture term peaks in the lower troposphere where the gradient
is, and vanishes above it:

| p (hPa) | qv median | legacy (dry) | Arm N (dry) |
|---|---|---|---|
| 999 | 1.72e-02 | 4.63e-03 | -9.49e-05 |
| 857 | 1.28e-02 | 3.17e-02 | -1.19e-03 |
| 513 | 2.98e-03 | 7.81e-02 | -6.65e-04 |
| 222 | 2.19e-04 | 9.00e-02 | -1.02e-04 |
| 95 | 4.63e-06 | 1.07e-01 | -6.02e-08 |
| 56 | 4.23e-06 | 1.13e-01 | -2.91e-07 |

## What this says, and what it does not

Arm N removes about 99.7 % of the legacy per-interface defect against the
PHYSICAL measure at the median, and the ~0.3 % it leaves is the moisture jump.
The largest absolute remainder anywhere in this state is 7.08e-03, against a
legacy defect reaching 1.15e-01.

So a further dry-air arm -- weighting by `den/(1+qv)` instead of `den` -- would
buy at most that much, and the freeze-lift request such an arm would need can
be written against a number rather than a suspicion. This finding does not ask
for one.

It is also NOT a forecast impact, a column-number change, or a precipitation
difference. `eps` is the per-interface coefficient of the transport metric; how
much number actually crosses an interface is `b`, which this does not measure.
One state, one time, one domain: the coefficient is a property of that
atmosphere's profile, and a drier or better-mixed one gives a different number.

## Reproducing

    python3 harness/g33_number_basis.py host/lc05_da_run/wrfinput_d01

`host/**` is private and gitignored, so the tool's properties are tested on
synthetic states in `harness/tests/test_g33_number_basis.py` -- including the
uniform-moisture case, which is the archive's own situation.
