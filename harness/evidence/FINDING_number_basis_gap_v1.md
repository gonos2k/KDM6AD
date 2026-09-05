# Arm N's matched-transfer coefficient on a dry-density measure

Review scope correction (2026-09-05): “physical” below denotes the dry-density
weight conditional on interpreting stored number as per dry-air kg. The kernel
slope's conflicting per-volume requirement remains unresolved (SCIENCE_STATUS.md).
The coefficients below describe matched/unclipped transfers; actual independently
capped departures and arrivals require the additional transfer-mismatch term.
These coefficient statistics alone do not measure a full transport residual.

Arm N closes the OPERATOR's number ledger: its residual collapses to roundoff
across the density matrix (`G33-NUMBER-010`). That ledger is MOIST --
`dend(i,k) = den(i,k)` at F:870. If `nr` is interpreted per dry-air kg,
the column-number measure instead uses dry density. The kernel slope requires
per-volume number, so that interpretation is conditional, not a settled unit
contract. This finding measures the profile coefficient under matched transfers.

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
interfaces. The matched-transfer coefficient factorises into density and
moisture factors. Independent outflow/inflow caps add a separate mismatch term;
this factorisation does not describe the full capped residual.

## Why no published fixture could answer this

Every stream in the archive that carries `qv` carries it UNIFORM in the column.
Measured across `kdm6ad-g33m-armn` (12 members), `-f64` (135) and `-migrate`
(144): maximum in-column spread exactly 0.0. Under a uniform profile the
moisture factor `1 + eps_armn_dry` is identically 1, the two ledgers differ by a constant per column,
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

## Rain-bearing and flux-weighted coefficient statistics

Everything above runs over all 2 507 544 interfaces of the state, and most of
them carry no rain number at all. A coefficient there is a property of the air,
not of anything being transported: the defect only reaches a forecast where
there is something to transport.

Restricted to interfaces whose BOTH cells carry the field, on the 20 s `mp37`
forecast frame of the same case:

| population | interfaces | median | p90 | flux-weighted |
|---|---|---|---|---|
| `QNRAIN`, both cells loaded | 13 611 | 1.92 % | 3.45 % | 1.97 % |
| `QNRAIN`, **upper cell loaded** | 23 492 | 2.02 % | 3.55 % | 1.98 % |
| all interfaces | 2 507 544 | 0.33 % | 4.62 % | -- |

Three refinements, none of which moves the answer.

The first published population required BOTH cells to carry number.
Sedimentation moves number DOWNWARD, so an interface whose upper cell is loaded
and whose lower cell is empty is transport-active and was excluded: the
published population was 42 % of the right one.

A ratio of medians is not the column residual. Under matched transfers its
density contribution is `sum_j F_j eps_j`. The historical flux-weighted
coefficient ratios above are 1.97% and 1.98%; actual capped departures and arrivals
were not measured by this profile analysis.

And the dry density is now the model's own `mu_d`/`d(eta)` rather than a
thermodynamic estimate, which moves the median from 1.94 % to 1.92 %.

The recorded coefficient comparison is **about 2% on rain-bearing interfaces**,
against 0.33% over all interfaces. About six times larger for rain, because rain
number sits in the moist lower troposphere where the moisture gradient is
steepest -- which is exactly where the two ledgers differ.

The complementary 99.7% and 98.1% summaries describe these coefficient ratios;
they are not measured fractions of physical number creation removed by Arm N.

This also corrects a blocker recorded in `CHECKLIST_review_main_2935fcd2.md`.
That checklist said no state on this host carried a populated rain-number field,
having checked `wrfinput_d01` (a cold start) and the 100 km IDEAL run. It did
not check the real case's own forecast output, which carries `QNRAIN` after
twenty seconds. The blocker was wrong.

## What this says, and what it does not

The median all-interface coefficient ratio leaves about 0.3% on the conditional
dry-density measure, due to the moisture gradient.
The largest absolute remainder anywhere in this state is 7.08e-03, against a
legacy defect reaching 1.15e-01.

These profile coefficients do not bound the improvement from changing a kernel
metric. Such a change also affects applied transfers and the evolving state;
the unit contract and full residual need to be established first.

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
