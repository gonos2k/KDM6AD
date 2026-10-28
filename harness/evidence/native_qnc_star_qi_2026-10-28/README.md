# Seven-cell QNC and QI boundary-donor trace, 2026-10-28

This packet extends the executed PR #469 diagnostic variant. It records the
RK3 seven-cell star centered at native `(i,k,j)=(113,12,70)` and the actual
QI donor/`ru_m` inputs for `flow_dep_bdy` at `(1,33,168)`. The original PR
#465 donor-scale operation at `(221,6,63)` remains unchanged. Only private
`module_advect_em.o` and `solve_em.o` were rebuilt for opt-in recording; the
advection Fortran module interface and KDM DSO are byte-identical to the
inherited variant. Canonical active host source and operational defaults were
not edited.

Four **accepted** full-domain READY40→60 s runs use control/α=0.25 with
recording off/on, one MPI rank and one thread. `mp_physics=137`,
`no_mp_heating=0` and radiation remain active in the forward. Each case's
checkpoint SHA-256 and applied-control ACK agree between off/on and with the
same PR #469 input. The path-free `execution_summary.json` separates two
additional rejected attempts: a control run whose MPI launcher returned 1
after WRF wrote a byte-identical checkpoint, and an α trace-off run whose
restart write failed for lack of disk space. The accepted α trace-off retry
ran in an isolated RAM volume; its checkpoint hash and ACK were checked, an
identical retained checkpoint clone plus small logs/receipt were saved, and
the RAM volume was detached. Neither rejected attempt is counted as a
successful model step.

## Actual shared faces and RK3 states

Each on-run has 147 typed shared-face records and 1,550 typed state/donor
records. The reader verifies two RK3 tile calls and exactly one owner whose
tile contains the complete X/Y/K star and every required `k+1` face. Six
internal correction faces and their six low-order counterparts have the
**same raw word on both adjacent cells** in each run. Target faces and
directional tendencies join PR #469's QNC producer records. At all seven
cells, recorded Z→X→Y tendency matches the corresponding RK3 QNC update
input, and source-compatible PD old-buffer and ordinary RK3 arithmetic
reproduce the recorded state words. The original 678 PR #469 writer words
are unchanged in each new trace.

The selected target's original α RK3 QNC remains `−0.006369509734`; its
saved-face exact-real residual is `−409.781200447`. Its six immediate RK3
neighbors have positive QNC. The full checkpoint is unchanged, so the
original fixed M0 still loses **54 profiles / 378 channel cells**.

## Frozen paired-face one-ULP calculation

The offline analyzer also takes the PR #469 target's saved pre-limit faces
and lowers its **limiter scale** one binary32 ULP, `3C54898F → 3C54898E`.
It multiplies all six outgoing target correction faces in binary32 and
places each resulting word on the same face of the receiving neighbor. Five
distinct face words change for α. No low-order or perimeter face changes.

| α local frozen-input result | Value |
| --- | ---: |
| Target exact-real saved-face residual | **−111.694128672** |
| Target exact-real saved-face QNC | **−0.001172556278** |
| Target QNC from original-compatible f32 modes | **+0.001692894381** |
| Six neighboring exact-real residual signs | All positive |
| Seven source-compatible f32 QNC signs | All positive |
| Weighted internal-face change over seven cells | **Exactly 0** |

The 12 incidences of the six changed internal correction faces cancel in
the exact numerical ledger; the 30 perimeter incidences remain unchanged.
This is a **constructed frozen-input counterfactual**. No host run applied
that second one-ULP change at `(113,12,70)`. The target exact-real residual
is still negative despite positive candidate f32 NC, so a sign-only test
does not establish a general limiter rule. The numerical weight is not a
certified physical particle-number measure, and whole-domain conservation
is not claimed.

## QI boundary branch

At `(i,k,j)=(1,33,168)`, both runs enter the X-start boundary and have the
same negative `grid%ru_m` input word `C7B997A8` (raw value `−95023.3125`).
The stage record directly identifies donor `(2,33,168)` with `spec_zone=1`,
`periodic_x=false`, and the copy branch true in both runs:

| Actual QI word | Control | α=0.25 |
| --- | --- | --- |
| Target immediately before `flow_dep_bdy` | `00000007` | `00000007` |
| Donor read immediately before the call | `00000000` | `00000002` |
| Target after the call | `00000000` | `00000002` |

Thus the different target QI word follows a **different donor value under
the same recorded copy branch**. `ru_m` here is the exact raw array supplied
as the routine's `u` argument; its physical velocity units are not certified
by this packet. The QI word `00000002` remains a binary32 subnormal; no
physical ice creation or correction is inferred.

## Replay and limits

```bash
python3 -m harness.evidence.native_qnc_star_qi_2026-10-28.replay
```

The replay checks source/asset pins, the path-free execution summary's
accepted/rejected run fields and hashes, every typed record, historical
PR #469/#470 input hashes, paired faces, seven-cell source-compatible
states, frozen counterfactual and QI donor/branch join. The private build
receipt, RAM relocation receipt, retained clone and run logs were checked
locally; a public replay cannot reopen them. The replay makes **zero host,
KDM, RTTOV or optimizer calls**. The compiled instruction sequence, physical NC units,
all-domain conservation, admissible full-M0 candidate, full-domain RTTOV
cost, accepted update and second assimilation remain unverified.
