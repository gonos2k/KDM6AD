# Applied-face QNC guard on the saved seven-cell witness

Base: `main 83f65c60033baebce2aa8c0668f1c34e5d2dc510`, after PR #471.
The [versioned packet](../harness/evidence/native_qnc_applied_face_guard_2026-10-28/README.md)
uses the archived PR #471 raw words. This is an offline acceptance test for a
selected seven-cell neighborhood, not a new host variant or an operational
limiter change.

## Predicate

For a trial donor scale, round each of its six outgoing correction faces to
binary32 and put that **same word** at both incidences of the shared face.
Keep the recorded low-order and outer faces, PD-prepared `SCALAR_OLD`, RK
coefficients, scalar source and metrics fixed. Evaluate the actual saved-face
numerator of each affected cell in exact rational arithmetic:

\[
R_c=A_{\mathrm{old},c}N_{\mathrm{old},c}
 +\Delta t_c\{MSFTY_c[D_{\mathrm{low},c}+D_{\mathrm{corr},c}]
 +S_c\}.
\]

The local predicate requires `A_new>0`, `R_c>0`, and every binary32 RK result
compatible with the recorded original axis/RK modes to be finite and positive
for all seven cells. This packet also requires one predicted binary32 word per
cell across those compatible modes; ambiguous predictions are rejected. The
evaluator searches representable scale words downward
from the original, choosing the first that passes. It checks exact weighted
internal-face cancellation and reports the separately weighted **rounded RK
state** change. This is intentionally stricter than the selected profiles'
hard moment validator, which only requires positive NC where QC is positive.
The recorded `S_c=SCALAR_TEND` is zero in all seven cells; the evaluator
rejects nonzero values, so the source term in the displayed equation is not
exercised by this packet.

The runtime rule would also need to handle other source terms, cells whose
low-order state is already invalid, interactions among multiple limited
donors, tile/halo ownership, and a verified numerical error bound or executed
operation sequence. The current packet cannot establish those conditions over
the whole native grid. No physical particle-number interpretation is attached
to the numerical weight.

## Frozen witness result

| Case at `(113,70,12)` | First passing decrement | Scale word | Exact target residual | Compatible f32 target NC |
| --- | ---: | --- | ---: | ---: |
| Control | 0 | `3C54898F` | +164.537023468 | +0.001692894381 |
| α=0.25, original | 0, fails | `3C54898F` | −409.781200447 | −0.006369509734 |
| α=0.25, one ULP | 1, fails | `3C54898E` | −111.694128672 | +0.001692894381 |
| α=0.25, two ULP | **2, passes locally** | `3C54898D` | **+218.030350812** | **+0.001692894381** |

At two ULP, all six receiver residuals and all seven compatible f32 values
remain positive. Six distinct correction-face words change. The exact weighted
change from the six internal faces is zero, while the weighted rounded RK-state
change is **+33.4951201411** in the recorded numerical coordinate. This
separation is expected: small receiver changes do not appear in their saved
binary32 NC words. These are frozen-input predictions; the two-ULP proposal
has not been applied to an executable or run through KDM/RTTOV.

## Next execution gate

Before using such a predicate in the host, derive its full RK/PD input and
rounding contract from the active source and test it on more than these two
recorded cases. A trace-enabled variant must record the applied face word on
both sides, the affected RK state and source, the chosen scale, tile/halo
ownership, and trace-off/on final checkpoint identity. The whole fixed `M0`
must then retain every profile; the existing α candidate still loses **54
profiles / 378 channel cells**. The QI donor subnormal case requires separate
work. Only a full-support checkpoint can receive a whole-domain direct RTTOV
cost and be considered for an accepted analysis and second assimilation.
