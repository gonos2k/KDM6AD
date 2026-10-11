# Green review: problem scope and evidence coverage

Reviewed the current PR409 evidence mapping against source and already executed
records. The central document now separates the user scope, upper science goal,
current numerical subproblem, and engineering execution. This resolves the
scope conflation noted in the prior matrix. This review adds no tests or
calculations and does not reopen native, M/H, optimizer, or input acquisition
work.

## Finding

The broader research objective concerns upper hydrometeor/process
attribution through applied transfer, later model state, optical inputs/BT, and
the observation cost. The demonstrated DA subproblem is narrower: one native
column, normalized-dry f64 KDM over a fixed 20 s forcing window, all-sky seven
channel Huber cost, and initial theta/Qv controls. It preserves the other
states/parameters as fixed auxiliary inputs. The local T/Q result is relevant
engineering linkage toward the broader objective; it does not close upper-level
process attribution or whole-system science validation.

The pre-alignment matrix's broad diagnostic phrases needed the model, variant,
regime, and changed fields beside them. The current draft limits the selected
process, NC-to-BT, H∘M, native two-direction, PR395 and PR408 evidence and keeps
their distinct coverage classes visible. No remaining blocking scope or
evidence mismatch was found in the reviewed draft.

## Source and executed-evidence map

| Claim area | Verified source / record | Coverage that can be stated |
|---|---|---|
| DA adapter and active controls | `oracle/kdm6/da_single_column.py:25-27,82-125,189-240,246-299`; actual PR395 `RESULT_3d2e97f159.json` `adapter_metadata.state_prior` | One native `[1,39]` column; 20 s forcing; initial `th` and `qv` only; seven AMI channels; fixed all-sky H, remaining model state, parameters and auxiliaries. Native 39 levels and pressure geometry are retained. |
| CVT definition | `oracle/kdm6/da_cvt.py:1-23,40-45,103-132,206-276`; PR395 receipt | `th` is additive; positive `qv` uses the exact pure-log map `qv*exp(0.08*v)` with epsilon 0. `qv_levels=12` means bottom-up levels. The receipt counts 39 theta and 12 Qv controls, other state controls 0, and parameter controls inactive. Declared entry bounds apply only to `ni` and `nccn`; those fields are fixed in this subproblem. |
| Cost and fixed inputs | `oracle/kdm6/da_dual.py:587-669`; `oracle/kdm6/da_fulldomain.py:672-697,749-790`; `da_single_column.py:225-240,246-299`; PR395 receipt | Objective includes state prior, parameter prior and observation term; the selected setup has inactive parameter prior, fixed zero bias, unit observation sigma, Huber delta 1, and background-frozen support requiring all seven channels valid. This is a declared research configuration, not an error-model validation. |
| Selected process response and applied transfer | `harness/evidence/pr391_tq_response_2026-10-09/REPORT.md:7-31`; `CHECKLIST_pr392_interpretation_2026-10-09.md:3-18`; selected S3/S10/satadj records | The records close selected local checks only: stated process/regime and changed fields, applied-transfer/JVP/FD where listed. The report explicitly limits the whole-call output check to `[qv,qc,T,nc,nccn]`, states no general number conservation, and calls out wet-case derivative error. These are not a complete upper-level process budget or host-wide attribution. |
| NC/NCCN to optics/BT | `harness/evidence/C5_nc_bt_17digits_result_2026-10-03.json`; `C5_optical_execution_receipt_2026-10-03.json`; `oracle/kdm6/rttov_bridge.py:106-123,156-200,252-272`; `oracle/kdm6/obs/model_profile_builder.py:298-350`; `rttov_obs_operator.py:36-53,89-103,125-179` | C5 is a fixed-profile NC→BT numerical probe, not a named-process derivative or accepted cost. The bridge/profile/RTTOV source shows the implementation path and its frozen optical assumptions; it does not upgrade the C5 probe to full process-to-observation proof. NCCN has no direct RTTOV BT path in the current operator. |
| Coupled H∘M cost sensitivity | `harness/evidence/pr391_tq_response_2026-10-09/RED_cost_review.md:5-18` | One weak-cloud point has an independent T/Q finite-difference comparison through the f64 KDM step, profile map, RTTOV K, and Huber cost, with seven-channel support held fixed. It is point/branch specific; baseline H-only sensitivity is separate. It does not establish higher derivatives, identifiability, all-regime validity, or resolve an invalid six-case common-support comparison. |
| Native two-direction checks | `harness/evidence/REPORT_supported_native_nccn_2026-10-03.md:14-59,61-88`; `native_two_direction_result_2026-10-03.json` | Historical PR353/N5.3 selected-column numerical checks cover two directions and 12 returned state fields, with stated JVP/VJP/FD limits. This is not a current-main clean production build, RTTOV cost, complete physical DSD/unit review, or general process attribution. The report itself leaves operational approval open. |
| Native analysis vs synthetic success | PR395 intake/capture receipt; PR408 `CHECKLIST_pr408_synthetic_capture_success_2026-10-11.md` | PR395 is one July 19 native-input analysis, returned diagnostic only; gradient and termination do not meet strict convergence. PR408 exercises a synthetic-H diagnostic/checkpoint path and is not actual RTTOV or a held-out July 20/21 result. Treat these as distinct coverage. |

## Bounded disposition

The current central wording distinguishes (a) upper hydrometeor/process science
goal, (b) the fixed-forcing f64 T/Q initial-state DA subproblem, and (c)
engineering links demonstrated by selected local/native/optical records. It
uses “closed” for selected subcases and preserves process, applied-transfer,
regime, fields and variant qualifications. Source code establishes pathways;
it does not certify physical conservation or scientific acceptance.

No additional `Δy_M` comparison is needed as a completion gate. It is an
optional diagnostic only if a claim specifically attributes an additional
observation-space contribution to microphysics. External SST, MLS, VIIRS, L2,
or other truth products are not required by the current AMI-only scope.

The 79/100 item is a reviewer-proposed conversation-management assessment, not
a user-owned scientific completion criterion. It must not be treated as a
physics acceptance threshold or as evidence added by this review.

No tests, calculations, model runs, optimizer calls, or data requests were
performed for this review. The source/evidence checks are bounded to the cited
KDM6AD repository records and do not claim exhaustive coverage of all host
processes or regimes.
