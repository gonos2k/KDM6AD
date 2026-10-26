# Native trace input guards and saved QNC budget — 2026-10-27

Base: main `639d227c` after PR #457. This change hardens two public trace
tools and rechecks the saved QNC limiter operands. It does not change KDM or
host physics, the DA control, observation support, or an existing evidence
packet.

## Input and output guards

`native_moment_trace_overlay.py` now checks `--report` before planning or
applying an overlay. A report path that resolves to either pinned Fortran
source, is a symlink, is a hardlink to either source, or already exists is
rejected. A fresh report is created exclusively. The same expanded `~` path
is used for checking and writing. The source plan rejects symlinked path
components and paths escaping the isolated host root, and replacement keeps
the original file mode instead of installing `mkstemp`'s `0600` mode.

`replay_qnc_flux_limiter_trace.py` requires `LIMIT_HIT` to be a canonical
boolean bit and every other record to be a finite binary32 word. It checks
that in-memory record keys agree with their rows. The analyzer requires exact
Python integer configuration values, rejecting fractional floats, strings and
booleans that `int()` had previously accepted.

The overlay's `--apply` contract remains an isolated private source tree with
no concurrent adversarial writer. Preflight and source-hash checks do not make
path operations atomic against a hostile process that swaps parent directories
between checks and replacement. That stronger concurrency guarantee would
require descriptor-relative source operations and is outside this trace tool's
current execution contract.

## The PR #457 packet remains historical

The original 28-file packet and its manifest are unchanged. Its replay entry
point pins the *old* reader SHA-256 `b9dfde89…`, so that entry point must be
run from the PR #457/main `639d227c` tree. For example, use an isolated
checkout of that commit rather than changing the historical manifest. The
earlier PR #455 moment-trace evidence likewise retains its original overlay
source hash; this tool fix does not rewrite that source attribution. The
new reader can still read both original raw traces: the control and alpha0.25
analysis dictionaries match the packet's saved `analysis.json` exactly. A
focused regression test and a versioned companion command check those real
saved cases after the strict input validation change:

```sh
python3 -m harness.replay_pr457_qnc_with_hardened_reader
```

The companion verifies every original packet file and the historical reader
pin, then compares both current-reader results with the saved analysis. It
does not rewrite the original manifest or claim that its original source-pin
entry point ran under the new reader. This equality is an offline numerical
comparison, not a new host or RTTOV call.

## Exact arithmetic on saved target-cell operands

At native `(i,j,k)=(221,63,6)`, the saved `advect_scalar_pd` operands define
the target-cell low-order available amount (A), the signed net correction
from the **post-limiter** faces (O), and residual (R=A-O):

\[
A=\big[(c_1\mu_b+c_2)+c_1\mu_{\rm old}\big]N_{\rm old}
-\Delta t\left\{m_xm_y\left[r_x\Delta F^\ell_x+r_y\Delta F^\ell_y\right]
+m_yr_z\Delta F^\ell_z\right\},
\]

\[
O=\Delta t\left\{m_xm_y\left[r_x\Delta F^c_x+r_y\Delta F^c_y\right]
+m_yr_z\Delta F^c_z\right\},\qquad R=A-O.
\]

Here each face difference is upper/east/north minus lower/west/south in the
recorded source coordinate; superscripts \(\ell\) and \(c\) denote low-order
and applied correction faces. The old state and mass coefficients come from
the same run's `RKSCALAR_PD_AFTER`; the face words and metrics come from
`RK3_PD_POST_LIMIT_FACES`. The new mass factor uses the same run's later
`RKSCALAR_BEFORE` fields,
\(D=(c_1\mu_b+c_2)+c_1\mu_{\rm new}\). The recorded low-order faces are unchanged across
the limiter, and `SCALAR_TEND` is zero in this selected final RK update.
Each stored binary32 operand is converted to its exact rational value before
the displayed subtraction, multiplication and division.

| Saved-operand calculation | Control | Alpha 0.25 |
| --- | ---: | ---: |
| Recorded `PH_LOW − A` | −305,419.616 | +469,540.359 |
| Recorded `PH_LOW − O` | −279,643.282 | +303,550.519 |
| Exact local residual `R=A−O` | **+25,776.334** | **−165,989.840** |
| `R` / new mass factor | +0.285426801 | **−1.838040504** |
| Actual stored final RK3 QNC | +3.442540646 | **−3.814399242** |

The alpha0.25 recorded threshold exceeds the saved-operand exact available
amount by about 469,540, while its applied correction leaves about 303,551
below that threshold. Thus the exact residual of these *already rounded saved
operands* is negative. Keeping these face words and changing only the last
scalar subtract/divide/store to higher precision cannot make that local
residual positive. This does not test a full higher-precision host integration:
such an integration could change the upstream operands themselves. It also
does not identify an executed FMA instruction, certify physical units for raw
NC, or close shared-face/column/domain number conservation.

## Gates

The targeted overlay and replay tests pass, as do Ruff and the direct saved
PR #457 case comparison. The next physical gate remains the neighboring
shared-face and domain budget, followed by a justified candidate that keeps
the full fixed observation support. No new accepted candidate, RTTOV cost or
second assimilation was produced by this tool fix and offline calculation.

Source data: [PR #457 raw packet](../harness/evidence/native_qnc_flux_2026-10-27/README.md),
[upstream RK replay](../harness/analyze_upstream_nc_trace.py), and
[QNC flux replay](../harness/replay_qnc_flux_limiter_trace.py).
