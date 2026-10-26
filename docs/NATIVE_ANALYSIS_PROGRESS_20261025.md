# Native satellite analysis progress — 2026-10-25

As of `2026-10-25T15:15:15Z`, after immutable interim snapshot H1
(`7d4d2d85b9c444b7cae9e842bec9ff332a013814`). This dated page supplements H1;
it does not revise the earlier packet or checklist hashes.

Follow-up: [2026-10-26 review checklist](NATIVE_ANALYSIS_REVIEW_CHECKLIST_20261026.md)
records the FP-environment predicate correction, saved Q65 resolution diagnosis
and outstanding QC–NC tracing. The execution outcomes below remain unchanged.

## Full-physics value steps and trial admission

- The no-new-analysis control and α=1, 0.5 and 0.25 T/Q candidates each
  completed one independent 40→60 s full-physics host step from the same pinned
  40 s origin. Each pre-update READY40 matched the control bitwise. The configured
  nonadiabatic physics remained enabled with `NO_MP_HEATING=0`,
  `USE_THETA_M=1`, `USE_Q_DIABATIC=0`.
- Outcome: `NO_ADMISSIBLE_TESTED_FULL_HOST_UPDATE (3 trials)`. Each trial lost
  rows from the frozen full-domain baseline M0 support through the native
  profile guard before candidate RTTOV: α=1 lost 53 rows / 371 channel cells;
  α=0.5 lost 63 / 441; α=0.25 lost 55 / 385. These are confirmed pre-RTTOV
  support losses, not candidate RTTOV-quality failures. No mask was shrunk,
  no number floor was applied, candidate RTTOV calls were zero, and no update
  was accepted. Trial candidate costs are undefined.
- Strict ACKs were α=1: 561,407 applied rows / 855,443 components; α=0.5:
  311,455 / 411,023; α=0.25: 117,172 / 170,749. The ACK records application;
  it does not establish an admissible observation cost or cloud improvement.

## Full-domain control checkpoint-to-RTTOV baseline

- C7 baseline direct RTTOV is complete for all 65,988 mapped native columns in
  129 unique successful chunks. The original failed chunk-55 request remains
  preserved. Its filtered RTTOV process succeeded; a durable 502-profile result
  was recovered from saved output with zero additional RTTOV calls. The total
  ledger is 130 requests, including the preserved failure and reused pilot
  chunks. No new KDM, K, host-step or optimizer calls occurred during C7.
- Fixed baseline M0 support is 377,342 channel cells across 53,906 columns
  (53,906 per AMI channel 10–16). The seven-channel KO source has valid QC/DQF
  at every column; no mapped source column is missing. Separate excluded rows
  are 41 initial negative-number moments, 1,033 native profile-invalid rows,
  one Q-min input profile and 11,007 rows with nonzero direct-RTTOV quality.
- The baseline-only direct observation objective is `J=11.007963317242059`,
  numerator `4,153,766.894054753`, `Z=377,342`. This is not a candidate
  improvement, gradient, closed physical budget or forecast-skill result. The
  outer ring contributes 160 supported columns / 1,120 channel cells; the
  64,960-column interior contributes 53,746 / 376,222. The chunk-55 zero-Q
  profile at flat 28195, native 1-based `(i=116, j=121, k=30)`, is excluded
  only from the RTTOV profile call; its native row and Q are unchanged.
- Evidence: [baseline packet](../harness/evidence/native_full_physics_observation_2026-10-25/README.md)
  and [trial packet](../harness/evidence/native_full_physics_trials_2026-10-25/README.md).
  Pixel-specific KO UTC remains unverified; the model endpoint is 00:01:00 and
  the unchanged KO bundle is nominally 00:00.

## Remaining gates

- C7 control baseline and C8 full-physics host steps are complete. All three
  tested T/Q updates are inadmissible on frozen M0 support, so the cloud-analysis
  objective is not met. Candidate RTTOV cost is unavailable.
- C4 conditional component results: 45 KDM forwards (including baselines),
  4 JVP, 4 VJP, 4 K and 38 direct RTTOV calls, with no host calls. No rank
  passes the common 33-part profile/BT/cost gate. Native-17 rank 1 passes only
  epsilon `1e-6` (ratio `0.17599`); other required gates fail. V14 coordinate
  triage used the wrong norm and is withdrawn; v15 corrects accounting without
  changing tolerances. The directional gate failure is not proof of an AD bug.
- C5/C6 fixed-prior full-domain optimizer iterations and C9 a second analysis
  are not implemented or run. No accepted update, full-host AD, derivative
  certificate, forecast or unattended cycling result is claimed.
