# PR398 bounded research follow-up checklist

Base: merged PR397 `26ff5a1f`. User authorized continuation of the latest
review and Green/Red audit. The existing successful native integration,
PR397 analysis, once-locks and receipts remain immutable. No new host run.

| Item | State | Evidence / completion criterion |
| --- | --- | --- |
| Initial all-sky routing, fixed process parameters, strict seven-channel quality | Previously closed | PR394–397; not reopened or rescored |
| Stored control/gradient block and layer interpretation | Done | `pr398_followup/CONTROL_BALANCE_PR397.json`; full control-chain observation gradient `g-v`, inactive-control checks; zero M/H calls |
| Separate same-objective iteration-budget experiment | Executed | `pr398_followup/ACTUAL_RUN_REPORT.md`; max_iter8/default max_eval10, original xb and zero controls; one run only |
| Cross-run fixture-path signature mismatch | Done, separate interpretation | `pr398_followup/POSTRUN_INTERPRETATION.json`; original failed driver assertion unchanged, effective H/assets equal, within-run signature strict; no retry |
| Predeclared direct-H host-time and centroid viewing-angle batch | Done | V2 frames1/4/6 × AMI/native centroid: all6 returned, all7 quality0; `pr398_followup_2026-10-10/REPORT_v2.md`; actual HGT retained, distinct from H∘M analysis |
| CTH as RTTOV surface elevation proposal | Withdrawn, never executed | Cloud-top height is not the model's surface elevation; V2 replaces this draft |
| Private result preservation outside temporary worktree | Done | `pr398_followup/LOCAL_PRESERVATION.json` (40 files) and `pr398_followup_2026-10-10/LOCAL_PRESERVATION_v2.json` (5 files), hash-checked canonical `host/research_evidence/` copies; originals preserved |
| Final Green consistency audit | Done | `pr398_followup/GREEN_REVIEW.md`; arithmetic, actual analysis and direct H evidence separated |
| Final Red counterexample audit | Done, no blocker in bounded scope | `pr398_followup/RED_REVIEW.md`; original raw-signature failure preserved, no convergence/cloud/skill or matchup claim |
| Pixel UTC, cloud-height datum, parallax and common footprint | Open | Conditional scene timing and centroid comparison do not establish these |
| Held-out warm-liquid event and further native columns | Open | Use unused native-model cases; do not substitute external model/reanalysis |
| Full flux water/heat closure | Open | State-change identities do not replace boundary/external fluxes |

Management score adopts the user-reviewed PR397 basis: 14+14+14+10+4=56/75
(74.7%, approximately75%). The PR398 bounded follow-up earns no automatic
extra points for PR/test counts or iteration budget. This is neither a
correctness probability nor forecast skill or remaining-time estimate.
