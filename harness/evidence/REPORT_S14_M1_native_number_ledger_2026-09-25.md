# S14 M1: matched 600 s mp37 applied rain-number ledger

S14 M1 is closed for this declared mp37 selected-column 600 s witness. The
matched control/capture pair records actual limited rain-number departures,
paired arrivals, bottom export, and a per-substep ledger on the selected 39-level
column. Green and Red review found no remaining scoped P1/P2 issue, including
the fixed capture schema, schedule, history receipt and late-group mutation
checks. The physical number basis remains unresolved; no density factor or
units interpretation was applied.

## Run identity and scope

Both lanes used the retained 5 km input set: wrfinput_d01
(5a9ae8da…c4d970), wrfbdy_d01 (d46e5d71…c5e6c) and wrfchainp_d01
(c8e300d2…c0c4e3). Each run used mp37, a 20 s step, 600 s total, one MPI
rank on the actual 1×1 grid, one model thread, and history every 10 minutes
with history_interval_s=0. Both active-input identities were complete and
stable, and both runs exited successfully.

The selected Fortran column (i=144,j=153) and level K13 were fixed from the
prior input-based S2 selection: initial QRAIN and QCLOUD are positive while
QNRAIN is zero. The trace is one column, not a domain census. The control
executable SHA-256 is
36bdabe26a1b5613bc25e9107f2118766dafb393dc49ba19027864da57492cd7;
the capture executable is
1fad13519d90729a3eccdad47051dcc7f05c55967abcb8df46b49e5d6169f5b5.
Both reuse the isolated, source-attributed S2 shadow build. The capture-only
Fortran source is guarded by KDM6_S2_NUMBER_CAPTURE, strips exactly to
host/KIM-meso_v1.0/phys/module_mp_kdm6.F, and has SHA-256
5ceca0627c5be831f47c958e85b1ff2612fd9a50fd9bf1c3c40bf0ac6eb951c0.
The canonical host source, installed executable and libraries were not edited.
Input, build, runner, executable and lane receipts are summarized in
native_s14_m1_number_transfer_2026-09-25.json.

The two full history files each contain exactly t=0 and t=600 s and have the
same SHA-256 (154ab800148c98fb16abb143665ad7d737b1537af87bab3fb5638803cbc705c9).
At each saved frame, strict comparison found 253/253 common numeric variables
raw-bit equal plus exact equality for Times (254 common variables total). The
comparator stdout receipt is retained and its digest is code-pinned by the replay.

## Applied-transfer witness

The bounded selected-column capture has 25,235 typed records (3.65 MB), below
the predeclared 50,000-record ceiling. It covers all 30 KDM6 calls, with
host/kernel entry and return at all 39 levels per call. At kernel entry, three
QNRAIN values, one QRAIN value and thirteen QCLOUD values were clamped from
negative host input to zero; these observed interface normalizations are
counted separately from the applied transport ledger.

The trace contains 95 complete sedimentation groups across the 30 calls. The
selected column naturally exercised mstep=1…6: six calls had mstep 1, two
had mstep 2, eleven had mstep 3, five had mstep 4, four had mstep 5 and two
had mstep 6. Each group includes all 38 internal faces and the top cell. The
replayer validates the actual source-ordered caps and state updates, and
records 1,480 active interface occurrences with separately measured nonzero
dn_out and dn_in. Bottom export was positive in 87 of the 95 groups.
No independent face cap bound a number departure or arrival in this selected
column; the logged departure and arrival offers were applied as recorded.

For each group, the replayer pairs the upper-cell departure with the lower-cell
arrival and reports the residual as an offered metric/density term plus any
cap-unmatched term. The table sums the 95 per-substep ledger occurrences over
the ten-minute run; these accumulated diagnostics are not a single physical
inventory or a unit decision.

| Conditional number measure | Offered metric/density term | Cap-unmatched term | Observed interface residual | Weighted departure denominator | Bottom export | Store-rounding closure |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| dz·n | −0.007950697 | 0 | −0.007950697 | 2,840,825.321605 | 3,092.813203 | −0.062333129 |
| rho_m·dz·n | 113,405.220596 | 0 | 113,405.220596 | 2,239,949.301193 | 3,371.141351 | −0.051986871 |
| rho_d·dz·n (conditional dry density) | 110,211.751415 | 0 | 110,211.751415 | 2,221,823.804623 | 3,322.933781 | −0.051576292 |

Per-group inventory closure equals the replayed source-order binary32 store
rounding to double-precision summation error. The raw number-bundle cap
replay found no warm or cold donor-floor cap in this selected column. This
does not imply the face residual vanishes: with applied caps absent here, the
moist/dry weighted interface terms retain the captured density contrast.

## Within-call processes and between-call dynamics

The replay keeps the microphysics-call stages separate. Across the 30 calls,
it records 48 positive snow-melt rain-number updates, four graupel-melt
updates and one rain-freeze sink; the autoconversion path had no positive
number-rate records. All 1,170 warm/cold process-bundle update pairs replay in
source order, including their stored-state changes and rounding/floor
remainders.

For each call, the ledger partitions raw stored QNR as kernel-entry
normalization, pre-sedimentation process change, applied sedimentation
substeps, and post-sedimentation process change through host return. The
source-tagged melt/freeze changes, warm/cold rate-bundle changes and remaining
microphysics/threshold remainder are reported separately. All 30 raw call
partitions close; the largest closure residual is 6.3e-13 in the reported
column-sum arithmetic.

Across the 30 calls, the raw (unweighted) stored-QNR bookkeeping reports a
pre-sedimentation process delta of 0, direct melt/freeze change of +13,142.394,
warm/cold stored-state change of −259.774, remaining post-sedimentation
microphysics/threshold remainder of −181.692, and sedimentation state change
of +511.117. These terms sum to the measured +13,212.046 host-entry-to-return
column-state change; they are raw stored values, not a physical inventory.
The 29 transitions from one call's host return to the next call's host entry
are retained as per-level raw QNR differences. Their RK/dynamics operands
were not instrumented, so they remain an unassigned between-call remainder
and are not folded into the within-call sedimentation ledger.

This is a legacy mp37 result. Its observed mstep 1–6 values do not replace or
generalize the separate normalized mp237 S4 evidence. The Registry's per-kg
declaration, the kernel's dimensional number-density equation and the stored
QNR physical basis remain unresolved; dz·n, rho_m·dz·n and conditional
rho_d·dz·n are reported only as separate diagnostics.

## Review, reproduction and limits

Green and Red rechecked the replay schema and run receipt guards; the final
focused suite passes 23 tests, including capture-schema remapping, altered
history hash/size, strict-comparator report mutation, forged run-contract, late
face deletion and warm/cold relocation regressions.

The paired runner commands, input/build hashes, saved-time checks, selected
capture, replay JSON and full local run receipts are identified in
native_s14_m1_number_transfer_2026-09-25.json. Focused checks pass:

- python3 -m pytest -q -W error harness/tests/test_replay_s2_number_trace.py harness/tests/test_replay_s14_m1_number_ledger.py — 23 passed.
- ruff check harness/replay_s2_number_trace.py harness/replay_s14_m1_number_ledger.py harness/tests/test_replay_s2_number_trace.py harness/tests/test_replay_s14_m1_number_ledger.py — passed.
- git diff --check — passed.

This closure applies only to the declared retained-input, selected-column
mp37 witness. S2 physical number basis, S4 normalized mp237, other columns and
schemes, the operational default, domain-wide budgets, mp137 validation and
forecast impact remain separate and open.
## Knowledge graph

Graphify refreshed the public structural graph and merged semantic extraction
for the changed Markdown evidence. HTML visualization was skipped because the
graph exceeds the 5,000-node limit. The public corpus omits the private host
tree, so it cannot represent the local Fortran producer path; canonical source
hashes and the instrumented capture are recorded separately as direct execution
evidence.
