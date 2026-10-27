# Native QNC shared-face application — 2026-10-27

## Question and executed scope

PR457 established that `advect_scalar_pd` takes an outgoing limiter branch
at native `(i,j,k)=(221,63,6)` in both control and the rejected alpha0.25
candidate, yet the latter enters KDM with negative NC. This follow-up asks
whether the six post-limiter face values are actually shared by the target
and its adjacent cells, and whether each of those cells consumes the recorded
values in its RK3 tendency calculation.

The experiment repeated the same READY40 state twice for each input, with
shared-face logging off/on. All **four full-domain 20-second host steps**
completed at 00:01:00. Within each input, ACKs and all 652 checkpoint
variables / 322,426,586 numeric elements are bitwise equal, and the endpoint
matches the earlier PR457 result. The current source/build/DSO and input
hashes are separated in the [public packet](../harness/evidence/native_qnc_shared_face_2026-10-27/README.md).
There were no RTTOV/optimizer calls and no accepted analysis update.

## Local face and tendency evidence

The owner tile for the witness and six adjacent native cells is `(i=1…235,
j=1…142,k=1…39)` at the computation boundary; the second tile starts at
`j=143` and logged a non-owner call. The source routine's `time_step`
argument was 20 seconds, while the checkpoint/upstream record's actual model
`itimestep` was 3. The trace keeps these meanings separate.

For every target face, the target and the adjoining cell read the **same raw
binary32 word** for the limited high-order correction *and* the low-order
flux. This holds for west/east, south/north and lower/upper faces in both
control and alpha0.25. At each of the seven cells, the recorded post-limiter
faces and cell-local metrics reproduce the successive Z, X and Y tendency
words under a source-compatible binary32 operation candidate: **21/21 per
input**. The target's final word also equals that run's upstream
`ADVECT_TEND` word. This is evidence of the actual face-array consumption
path; it does not identify an executed FMA instruction.

The source's applied divergence uses the correction and low-order terms
separately. In simplified notation, the x update is

\[
\mathcal T_i^x\leftarrow \mathcal T_i^x
-m_{x,i}r_x\big[(F^c_{x,E}-F^c_{x,W})+(F^\ell_{x,E}-F^\ell_{x,W})\big],
\]

with the analogous y update and a vertically oriented `RDZW` update first.
The local map factor (m_{x,i}) differs between cells; a shared raw face word
does **not** require equal-and-opposite unweighted tendency words. The six
internal target–neighbor faces have 30 outer perimeter face incidences in
this seven-cell star. Closing a physical number budget requires the outer
neighbors, native mass/volume coordinate and boundary/halo treatment. Raw
NC physical units remain uncertified.

| Target QNC after RK3, legacy raw coordinate | Control | Alpha0.25 |
| --- | ---: | ---: |
| Actual KDM input | +3.442540646 | −3.814399242 |

The face values differ between control and candidate, but that finite
comparison is **not an additive process attribution**. The candidate remains
inadmissible where QC stays positive after negative NC is clamped to zero;
no candidate RTTOV cost was defined. The saved-operand exact-rational
target-cell residual remains negative as documented in
[the preceding budget review](NATIVE_TRACE_GUARDS_AND_QNC_BUDGET_20261027.md).

## Completion and next gate

This step closes the **selected shared-face identity and seven-cell tendency
replay** gate. It does not close shared-face conservation over the whole
domain, diagnose a physical particle-number unit, repair the limiter, or
establish a usable analysis. The next bounded measurement is the outer-face
donor/receiver and native mass-coordinate budget across a larger patch,
including tile/halo interfaces where relevant. Only then can a physically
justified change be tested against the entire fixed observation support and
RTTOV cost.
