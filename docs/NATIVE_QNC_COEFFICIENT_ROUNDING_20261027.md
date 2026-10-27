# Native QNC PD/RK coefficient and rounding review — 2026-10-27

The [versioned offline packet](../harness/evidence/native_qnc_coeff_rounding_2026-10-27/README.md) fixes the remaining PR463 review finding and extends the saved seven-cell numerical ledger. The four executed PR461 full-domain 20-second host steps and their exact trace-off/on checkpoint comparisons remain the execution evidence; this update does not run the host or RTTOV.

## Coefficient contract

The prior exact state-budget calculation read PD `C1H/C2H` and reused them for ordinary RK3 mass factors without checking the RK records. The analyzer now checks the raw words at PD before/after and RK3 before/after, and calculates RK old/new factors from the RK record itself. Two mutations that change only target RK `C2H` in both ordinary before/after rows (`C6B384BB→C6B384BC` control and `C6B384BB→C6B384BA` alpha0.25) are rejected. In the unmodified 14 cells all words match, and the published exact budget and one-ULP probe values remain unchanged.

## Rounded-state diagnostic

The PR463 face probe recomputed each target outgoing correction face and installed identical words at the target and neighbor. Its exact seven-cell face total is unchanged. Using the same operator-derived weight `beta=-1/(MSFTX·MSFTY·RDZW)` and each cell's RK new mass factor **evaluated exactly from saved f32 operands**, the exact saved-input state-expression change sums to **0** in both cases. The change from the final original-compatible binary32 QNC words is **+12,836.142997905** (control) and **+10,268.913337873** (alpha0.25). The coefficient in this latter diagnostic is still that exact reconstructed factor, not an observed rounded mass-factor word. In both cases all six neighbor QNC words are unchanged; the difference comes from the target's newly positive stored word.

This distinguishes three statements: the shared correction faces are paired bitwise, the exact weighted face/state algebra cancels over the selected seven cells, and the **rounded final state sum does not**. The last quantity is a numerical-coordinate diagnostic with unresolved raw NC physical units and an operator-derived weight. It does not prove a physical particle-number source, conservation failure over the full model domain, or the emitted compiler instruction sequence.

The next physical gate is an applied donor/receiver rounding bound for a general limiter rule. An isolated full-host variant must then keep face sharing, all relevant cell states and the fixed observation support valid with nonadiabatic processes enabled. Only then can post-KDM cloud moments, RTTOV candidate cost and another assimilation be evaluated.
