# Seven-cell QNC faces and QI boundary donor, 2026-10-28

Base: `main e13da888ea540b22146ab391c12a79d6e9aec023`, after PR #470.
The [raw packet](../harness/evidence/native_qnc_star_qi_2026-10-28/README.md)
records the executed full-host comparison and the separate offline
counterfactual. The PR #465 target-only physical scale change stays at
`(221,63,6)`; this work adds opt-in tracing at native `(113,70,12)` and
`(1,168,33)`.

## Executed boundaries

Four accepted full-domain READY40→60 s steps compare control and the
still-rejected α=0.25 T/Q candidate with tracing off/on. The forward retains
`mp_physics=137`, `no_mp_heating=0`, radiation, one rank and one thread.
Within each case, the trace off/on checkpoint and applied-control ACK match
by bytes; both endpoints also match PR #469. Two additional attempts were
rejected and kept separate in the receipt: one MPI launcher exit 1 after a
byte-identical control checkpoint, and one α restart write blocked by disk
space. The accepted α off retry used a temporary RAM volume and a
hash-verified retained clone; those run and relocation files remain private,
while the public replay checks their path-free receipt.

The new seven-cell star has one actual owner tile. Every one of its six
correction-face pairs and six low-order-face pairs has identical raw bits on
both sides. All seven Z→X→Y tendencies reach the matching RK3 QNC inputs,
and each cell has a source-compatible PD/RK state reproduction. These checks
extend the selected target's PR #470 saved-face budget to its six immediate
receivers. They do not establish physical particle-number units or
whole-domain conservation.

## Frozen one-ULP paired-face probe

The offline probe changes the stored target limiter scale
`3C54898F → 3C54898E`, recomputes six outgoing correction faces and gives
each adjacent cell the same changed face word. Five α face words change.
The six internal pairs cancel exactly under the recorded numerical operator
weight and all 30 perimeter incidences are unchanged. The six receivers
retain positive exact-real residuals and source-compatible binary32 QNC.
At the target, however:

| Frozen α target result | Value |
| --- | ---: |
| Exact-real saved-face residual | **−111.694128672** |
| Corresponding exact-real QNC | **−0.001172556278** |
| Source-compatible binary32 QNC | **+0.001692894381** |

The opposite signs remain a concrete counterexample to approving a limiter
rule on final binary32 NC alone. The paired-face probe has **not** been run
as a changed host executable; freezing other limiter inputs is an explicit
condition of this calculation.

## Ice boundary input is now identified

At `(1,168,33)`, the target QI immediately before `flow_dep_bdy` is
`00000007` in both cases. The source's X-start branch is eligible, the
actual `grid%ru_m` input word is the same negative `C7B997A8`, and the
copy predicate is true in both runs. With `spec_zone=1`, the recorded donor
is `(2,168,33)`: its QI word is **0** in control and **`00000002`** in α.
The target after the call matches its respective donor word. The failure
therefore follows a donor-state difference under the same boundary branch.
The source of that donor's subnormal QI remains a separate question; the
raw `ru_m` coordinate is not certified as a physical wind speed.

## Remaining acceptance checklist

| Item | Status | Next evidence |
| --- | --- | --- |
| QNC star source and receiver trace | Complete for this selected seven-cell neighborhood | Preserve shared-face, PD/RK and exact/f32 distinctions. |
| QI target boundary branch and donor | Complete at `(1,168,33)` | Trace where the α donor obtains `00000002` only if a physical correction requires that cause. |
| General positivity/number-budget rule | Open | Derive a coordinate-independent limiter using applied face words, donor/receiver states, admissible moments and a certified number/mass mapping. |
| Whole fixed M0 and optical response | Open | Execute that justified variant, keep every M0 profile, report active/inactive cloud-slope and radius clamps, then compare direct whole-domain RTTOV cost. |
| Accepted state and next assimilation | Open | Carry a valid, cost-improving checkpoint and compute a second analysis with the fixed-prior definition. |

The current α checkpoint still loses **54 fixed-M0 profiles and 378 channel
cells**; its full-support RTTOV cost is undefined. No new K calculation,
accepted analysis, second assimilation or forecast-skill result follows
from this trace.
