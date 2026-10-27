# Saved QNC seven-cell state budget — 2026-10-27

PR461's four full-domain host runs and bitwise trace-off/on comparisons remain the execution evidence. This update performs an **offline** analysis on the immutable saved state7 and shared-face records. Its versioned [public packet](../harness/evidence/native_qnc_state_budget_2026-10-27/README.md) pins historical assets and current analyzer sources separately. The earlier PR459 source-grouped face/tendency checks remain historical evidence; this replay checks their manifest binding and the saved PR460 weighted face identity, without repeating all 21 directional checks.

## Closed validation omission

The ordinary RK3 helper already compared both live QNC and the `SCALAR_OLD` output buffer. The aggregate pass decision checked only QNC. It now requires one source-compatible arithmetic candidate to match **both** fields. A one-ULP mutation of target `RKSCALAR_AFTER.SCALAR_OLD` makes the aggregate analysis fail in control and alpha0.25; unchanged historical results remain identical.

## State decomposition

For each saved cell, let `Aold` and `Anew` be the exact mass-coordinate factors formed from saved f32 operands; let `F` be the exact algebraic face-derived tendency, `T` the recorded `ADVECT_TEND`, `S` the PD scalar source, and `dt=20 s`. The PD prepared old buffer has an exact expression `(Apd·old+dt·S)/Apd` and a separately recorded stored value. Substituting each in turn into the RK3 numerator decomposes its actual saved QNC into four telescoping terms. At target `(221,63,6)`:

| Raw QNC term | Control | Alpha0.25 |
| --- | ---: | ---: |
| Exact saved-face/PD baseline | +2.060925420 | −0.062541972 |
| PD stored-old difference | −1.775498619 | −1.775498533 |
| Recorded advection versus exact face expression | +1.804024046 | −3.214212457 |
| Final RK arithmetic/store difference | +1.353089799 | +1.237853719 |
| Saved immediate RK3 QNC | **+3.442540646** | **−3.814399242** |

The fractions close exactly on the saved binary32 words; displayed decimals are rounded. In alpha0.25 the exact saved-face/PD baseline is already slightly negative. Raising precision only for the final scalar store cannot make that fixed-input baseline positive. A full-host precision change would alter upstream operands and is outside this calculation.

With `beta=-1/(MSFTX·MSFTY·RDZW)`, the seven-cell state-coordinate identity is:

```text
beta·(Anew·QNC_RK_after − Aold·SCALAR_OLD_PD_before)
  = 20·outer_face_contribution + beta·20·PD_SCALAR_TEND
    + PD_storage_arithmetic + advection_tendency_arithmetic
    + RK_state_arithmetic.
```

The 12 internal correction/low-order face pairs cancel exactly, leaving 30 outer incidences. In control/alpha0.25, `20·outer_face_contribution` is approximately `−555,352,592,727.6664 / −555,350,891,728.9988`; the advection arithmetic contribution is `−24,234.4843 / +24,776.3865`. Both agree with 20 times PR460's saved face and residual terms. All seven per-cell identities and their sum close exactly after recording nonzero arithmetic terms. This is **not** a physical mass or number conservation certificate: `SCALAR_OLD_PD_before` is a work buffer, beta is an operator-derived weight, and raw NC units are unresolved.

The saved target `kernel.hex` independently joins immediate RK3 QNC to FP64 KDM input. In alpha0.25 it records NC `−3.8143992424 → 0` between FP64 input and output while QC remains positive at output. `host.hex` records `MOMENTS_POST` NC 0 and positive QC. The individual internal process responsible for this transition is not isolated.

No new admissible full-host candidate, RTTOV candidate cost, or second assimilation is produced. A physically justified correction still needs to preserve shared-face application, mass–number admissibility and the entire fixed observation support before a cost comparison.
