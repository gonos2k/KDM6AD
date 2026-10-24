# Actual main-QR transfer and surface-diagnostic accounting

This follows the two stage-level witnesses in
[LOCALIZED_ICE_BUDGET_AD.md](LOCALIZED_ICE_BUDGET_AD.md). The original B512
blocks34/40,39 levels,dt20 and ice-factorial maps remain fixed. An isolated
observer adds logs to Legacy main rain transport and the common surface
return. No physics expression, default, installed library or host case changes.

## Executed quantities

The generator verifies all four pinned public source files and requires its
factorial base rendering to equal the supplied frozen v6 overlay bytes. It
changes only private `sedimentation.cpp` and `coordinator.cpp`; runtime and
conservative-ice bytes are unchanged. Original QR arithmetic text remains in
place. Tensor handles preserve the entry and cap operands; all extraction and
attempt reconstruction happen inside helper-local `NoGradGuard` scopes.

An interior cell uses the already executed values

\[
d_k=\min(a_k,q_k^-),\quad
v_k=\min(b_k,q_{k-1}^{\mathrm{post}}),\quad
q_k^+=\max(q_k^- -d_k+v_k,0).
\]

Here `dqr_k` and `dqr_above` are logged directly. The arrival cap is the
**upper donor's post-update reservoir**, distinct from its entry value. The
unnamed attempts are trace reconstructions with the source's original
multiply/divide association. For the top cell, which has no inflow or named
min-cap operand, applied departure is observed as before−after; the expected
`min(attempt,before)` is kept as a separate diagnostic.

Records are top-first and retain call_index, main substep n, local mstep/gate,
raw/safe DEND and DELZ, work1/workn, stored falk and previous stored falk,
entry/after/cap operands, attempted/applied transfers, and fallout accumulator
before/after. The main's global loop bound is shared by all512 columns even
when a particular column is inactive. The original partition remains part of
the executed map; a B1 re-run is not this experiment.

## Fixed-measure identities

Let `mu=DEND*DELZ` from the actual request. For each main substep define

\[
D_k=\mu_kd_k,\quad A_k=\mu_kv_k,\quad G_k=D_k-A_{k+1}.
\]

State changes use rounded binary64 `mu*(q_after-q_before)` products followed
by `fsum`, never subtraction of large inventory sums. Subject to the recorded
floating update remainder,

\[
\Delta W+D_b+\sum_kG_k=\varepsilon.
\]

Bottom actual departure `D_b`, arrival `A_b`, and net bottom depletion
`mu_b*(q_before_b-q_after_b)` are separate. With positive arrival, net
depletion is departure minus arrival; it cannot stand for total departure.
Signed `G_k` can be negative as well as positive.

The surface routine reports the accumulated **falk**, which can exceed the
applied state departure. The trace captures all four bottom fall rates and
the actual returned total/snow-ice/graupel outputs. The QR-only component is a
reconstruction, not an additional ABI output. Its operation order is exactly
`max(fall_qr,0)*DELZ/DENR*dtcld*1000`; it is not simplified to another grouping.
For `P_QR` so reconstructed,

\[
\Delta W+P_{QR}
=(P_{QR}-D_b)-\sum_kG_k+\varepsilon.
\]

This splits diagnostic bottom excess from internal transfer mismatch. Step
aggregates and endpoint state deltas may differ by recorded roundoff due to
floating telescoping; both use explicit delta-product contracts.

## Evidence and limits

Eight full-B512 forward comparisons (control-map instrumented off/on in four
mode/chunk cases) retain the original frozen response bytes. Separate fresh
processes compare selected first-order products between the frozen v6 C API,
the new observer build with trace off and trace on, within each variant.
These are selected products, not a full-Jacobian proof.

The [evidence report](../harness/evidence/qr_boundary_attribution_2026-10-24/REPORT.md)
records the measured witnesses. This is fixed-request code accounting, not an
RK/map-area water budget, number/energy conservation certificate, new RTTOV
cost derivative, or an operational adoption of a different physical map.
