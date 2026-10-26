# Native QNC flux and limiter trace — 2026-10-27

This follows the PR456 upstream RK trace at native one-based `(i,j,k)=(221,63,6)`.
The same 00:00:40 READY state was used for a control and the previously proposed
alpha=0.25 T/Q input. Each input had an independent trace-off/on 20-second
**full-domain host** run to 00:01:00. The detailed flux record covers one native
cell and its six face neighbors; it is not a B512 microphysics rerun or a
four-column model integration.

## Executed path and noninterference

The selected comparison comprises four successful host steps and eight KDM
wrapper entries. Both trace-off/on pairs have identical ACK bytes and every
numeric word in the final 652-variable, 322,426,586-element checkpoint
comparison. Control and alpha=0.25 are distinct physical inputs; their
endpoints are not asserted equal. The corrected trace produces one 77-row
scalar-QNC group per trace-on run. Its final RK1 and RK3 tendency words match
the same run's `ADVECT_TEND` records bitwise.

Two earlier control host steps belong to a rejected engineering capture: its
first column represented 20-second `nl_get_time_step(1)` rather than model
`itimestep=3`, and it also selected a moist-QV call with the same species index.
That V1 trace was not used for QNC attribution. A later alpha preflight failed
before `advance()` with a plan-key error and made zero host steps. The four
corrected runs above are the scientific comparison. No RTTOV, optimizer,
accepted analysis update, or second assimilation call occurred in this trace
campaign.

The forward retained its original nonadiabatic configuration: MP137,
`NO_MP_HEATING=0`, `USE_THETA_M=1`, `USE_Q_DIABATIC=0`, RRTMG LW/SW 4/4,
PBL 11, CU 37, LSM 2, and the existing zero-out settings. The source and
execution receipt identify the private compiled T/Q control hook; this hook is
not installed in the canonical active host source. Both cases used one MPI
rank and one thread.

## Measured scalar transport

The table gives cumulative QNC `ADVECT_TEND` within each RK advection call in
the host's legacy raw number coordinate. RK1 uses ordinary scalar advection;
RK3 uses the configured positive-definite flux limiter. `Y→X→Z` and `Z→X→Y`
are the actual operation orders for these two calls.

| Stage | Control | Alpha 0.25 | Candidate minus control |
| --- | ---: | ---: | ---: |
| RK1 start | 0 | 0 | 0 |
| RK1 after Y | −16,462,380,032 | −16,462,355,456 | +24,576 |
| RK1 after X | +42,724,278,272 | +42,724,343,808 | +65,536 |
| RK1 after Z | −181,919,596,544 | −181,919,629,312 | −32,768 |
| RK3 start | 0 | 0 | 0 |
| RK3 after Z | −181,824,126,976 | −181,824,716,800 | −589,824 |
| RK3 after X | −92,462,514,176 | −92,462,604,288 | −90,112 |
| RK3 after Y | −104,208,449,536 | −104,208,482,304 | −32,768 |

The first measured numerical difference is at the RK1 Y flux application, not
at the final RK3 scalar store. Both cases already have negative intermediate
QNC after RK2. The final RK3 update then changes the control's QNC to
`+3.4425406456` and alpha=0.25's to `−3.8143992424`. The latter is the
negative REAL4 input later seen by KDM, which clamps NC to zero while QC
remains positive. The alpha proposal therefore remains inadmissible on the
fixed observation support.

## Observed positive-definite limiter

At the target cell, the recorded low-state threshold `PH_LOW` and outgoing
correction `FLUX_OUT` are:

For this executed positive-definite routine, the low-state expression is

\[
P_{\ell}=\big[(c_1\mu_b+c_2)+c_1\mu_{\mathrm{old}}\big]N_{\mathrm{old}}
-\Delta t\left\{m_xm_y\left[r_x(F_{x,E}^{\ell}-F_{x,W}^{\ell})
+r_y(F_{y,N}^{\ell}-F_{y,S}^{\ell})\right]
+m_yr_z(F_{z,T}^{\ell}-F_{z,B}^{\ell})\right\}.
\]

All terms here are in the host's mass-coordinate, legacy raw number path.
Here `m_x,m_y` are `MSFTX,MSFTY`, `r_x,r_y,r_z` are `RDX,RDY,RDZW`, and
superscript `\ell` denotes a low-order face flux.
The limiter compares its recorded outgoing correction flux with this quantity.

| Value, raw mass-coordinate arithmetic | Control | Alpha 0.25 |
| --- | ---: | ---: |
| `PH_LOW` | 5,499,637,989,376 | 5,499,649,523,712 |
| `FLUX_OUT` | 6,881,175,142,400 | 6,881,198,735,360 |
| `FLUX_OUT > PH_LOW` | true | true |
| recorded outgoing scale | 0.7992295027 | 0.7992284298 |

The target cell's limiter branch was taken in both cases. The six recorded
face neighbors did not take that outgoing branch. Recorded pre/post correction
face words match the donor scale associated with each face, and low-order face
words are unchanged. The observed post-limiter Z, X, Y divergence reconstructs
the saved tendency under a source-compatible binary32 arithmetic candidate.

This identifies the **applied flux path** and shows that a taken limiter branch
did not guarantee a nonnegative final stored NC in this run. The executed
`advect_scalar_pd` low-state expression uses the captured `field_old` base and
low-order faces; it has no `qmin` or `ieva_corr` term. Those belong to the
separate monotonic routine and must not be attributed to this run. The
control `PH_LOW` matches a separated binary32 replay; the alpha=0.25 value is
one binary32 ULP above that replay and matches a source-compatible FMA
contraction candidate. The executed machine instruction sequence was not
captured, so that candidate does not prove which contraction the compiler
used. A conservative number budget is still open because both sides of every
shared face and the complete domain/neighbor ledger were not recorded.
The physical units of legacy raw NC remain unverified. No flux limiter or
microphysics equation was changed.

## Next decision gate

| Review item | Status after this trace |
| --- | --- |
| R1–R4: FP/FD qualification and QC–NC boundary capture | Previously closed; unchanged |
| R5a: locate actual QNC advection and limiter response | Measured at the selected witness, with same-run bit joins |
| R5b: closed budget and physically justified admissible proposal | Open; missing shared-face/domain budget and full-support result |
| R6: full-domain checkpoint RTTOV cost | Open; candidate is still inadmissible |
| R7–R9: representable trial integration, cumulative optimization, next assimilation | Open |

An admissible repair must explain why the limited target-cell update still
stores negative NC, including source-order rounding and the relevant shared
faces. It must preserve applied donor/receiver flux and
cloud mass–number consistency. Adding an NC floor or dropping invalid
observations would alter the scientific problem without answering this
question. Once a justified candidate keeps the entire fixed observation
support, evaluate its completed checkpoint directly with RTTOV and compare
actual temperature, water vapour, condensate and BT at the same positions.
An accepted state can then be carried into the next assimilation.

The [public packet](../harness/evidence/native_qnc_flux_2026-10-27/README.md)
contains raw-bit records, source/build receipts, offline replay and the
trace-off/on comparisons. The replay makes no model calls.
