# Final ice ncmin consumer resolution — 2026-09-06

Baseline: PR213 merged main `15aaefe178eea419e089cacabc7badaec92769fe`.
This follows the inherited final-ice gate finding; it does not reopen the
previous window-adjoint or freeze numerical-domain closures.

## Contract and disposition

The final ice DSD snap is active only when both `qi >= qmin` and
`ni >= ncmin_cell`. Outside that gate, the map is identity: `ni_out = ni`,
with `d(ni_out)/d(ni) = 1` and `d(ni_out)/d(qi) = 0`. Inside the gate the
existing lambda bounds and number reconstruction apply. Equality is active.
Without a per-cell tensor the existing scalar `c.NCMIN` gate applies.

The Python producer already delivered `ncmin_tensor` to the final consumer.
The missing condition was in `apply_dsd_number_limiters_torch`, which still
used scalar `c.NCMIN` for ice. C++ `coordinator.cpp` and the local reference
Fortran final ice block already use the per-cell gate. Their source was read;
they were not rebuilt or executed for this change.

| ID | Finding | Resolution | Status |
| --- | --- | --- | --- |
| ICE214-01 | Final ice ignores per-cell ncmin, changing inactive values and gradients | Use the existing cloud/C++ pattern: compute the ice snap, then retain the input below its per-cell floor | Fixed; regressions pass |
| DOC214-01 | Coordinator/constants still describe scalar-only rate gates | Describe existing tensor budgets, rate gates and slope/DSD consumers | Fixed |
| DOC214-02 | Runtime and saturation-adjustment descriptions say CCN is deferred | Describe driver-carried CCN, the optional activation path and local conversion behavior | Fixed |
| DOC214-03 | Runtime advertises an implemented Jacobian API | Mark it unsupported; retain the existing explicit exception and supported VJP/JVP/parameter APIs | Fixed |

No new numerical guard, parameter option or physical arm was added. The
executable AST changes only in the final DSD helper; runtime/constants changes
are descriptions. Operational C++/Fortran and the packed AD ABI are unchanged.
The function name and arithmetic of the existing ice snap are retained.

## Regression evidence

`oracle/tests/test_dsd_ncmin_contract.py` contains five portable tests:

- Heterogeneous floors: identical `ni=50` is active under floor 10 and retained
  under floor 100; `ni=100` is active at equality. Non-ice fields are unchanged.
- Independent analytic VJP and forward-mode JVP, including inactive identity
  derivatives and the tangent/adjoint dot product.
- `None` and an explicit scalar-default tensor preserve the scalar contract.
- The mass gate retains the input just below `qmin`, with equality active.

Before the source fix, the new suite returned **2 failed / 3 passed**: the
value and derivative counterexamples failed. After the fix all five passed.
The focused coordinator/parameter/window run returned **59 passed**, including
those five; these are not additional independent counts.

The active branch expectations use the existing f32-derived initialization
constant `PIDNI` with an independently stated lambda-bound reconstruction.
Inactive expectations require only identity, so they do not duplicate the
production gate implementation. No tolerance was relaxed to pass the change.

## Additional review and scope

The full local oracle run returned **1,086 passed / 26 skipped** on
Python 3.10.11 / PyTorch 2.13.0 / macOS CPU. The focused 59 tests are included
in that total. Ruff and Python compilation pass.

A separate old/new-module comparison sampled 4,096 positive scalar-default
cells with independently varied mass, number and density. All state outputs
and both ice mass/number partial derivatives were bit-identical and finite.
This is sampled preservation evidence, not a guarantee for all finite inputs.

Independent RED review reproduced all six value branches and identity/snap
partials after the fix, with no additional finding in its bounded consumer
scan. GREEN's full-step review is recorded below when complete. The two
existing team agents use Luna xhigh; no new team was spawned.
Graphify was updated. Raw review artifacts stay outside the wiki under
`graphify-out/ice-ncmin-resolution-20260906/` in the development checkout.

The direct-helper defect changes the declared conditional map. Its frequency
in real meteorological states and effect on forecasts remain unmeasured.
M1 applied ten-minute transfers, M2 first-negative QIB operands, particle-number
units, D4 operation order and forecast performance remain separate open work.
This change does not certify a new WRF/MPI run or live RTTOV assimilation.
