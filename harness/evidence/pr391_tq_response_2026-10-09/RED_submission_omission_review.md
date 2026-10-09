# Red submission and evidence omission review

Audit date: 2026-10-09, before staging; final cross-check at 12:26 JST. I reviewed the current Git candidate set, reports, JSON receipts, authored scripts and linked cached run files. I did not rerun KDM6, RTTOV, MPI or the forecast. This is a submission/readiness review, not another scientific result.

## Findings and disposition

| Priority | Candidate | Finding | Required edit |
| --- | --- | --- | --- |
| P1 — contradictory metadata (resolved) | `harness/evidence/pr391_clear_state_2026-10-09/GREEN_response_review.md:7` | The initial audit found reversed one-based native indices. | Corrected to `(j=87,i=49)`, consistent with zero-based `J=86,I=48` and all main/Red receipts. |
| P1 — publication status (resolved) | `harness/evidence/REPORT_pr391_review_resolution_2026-10-09.md` final paragraph | The initial audit found wording that said local work did not perform a publication despite the active PR request. | Reframed with the user’s 12:13 JST PR request and 12:14 JST omission audit; it now limits claims to no merge/science/operational approval. |

## Scope and identity findings

The checklist initially reused `D1` for “local research sequence applied,” while the linked decision memo’s D1 is the still-open choice about starting a new long target run. This is resolved: the checklist now uses `SEQ1` and has explicit open `R1` and `R2` rows; the formal D1–D4 decisions and new long-run decision remain open.

The cost JSON’s baseline `run_case_directory` no longer contains the q profile named by its execution-time hash. `RESULT.json` records baseline `q.txt` SHA-256 `8d5b00aa058fae51b5272ddc8f6f65e1bcaa34a65c8e499c099128b87e6cb135`, which matches the immutable paired `case_00` file; the current `run_baseline/q.txt` hashes to `3b2cbbbbdb66bc4f096830a2259ad92cc6b943e0f181005e9df844c4829bad67` because the local-H qv finite differences reused the directory. [ExecutionPathIdentity.json](../pr391_tq_cost_2026-10-09/ExecutionPathIdentity.json) now binds the saved result digest to execution-time profile hashes and explains that the present scratch file is the q-plus endpoint. A checksum-matched copy of the executed runner is preserved; the future-path runner uses isolated FD directories and did not produce the saved values. Treat this as resolved evidence-path metadata, not a baseline cost defect.

The after-run `M_source_identity.json` is current and cross-bound: its cost-result and Red-receipt digests match; the worktree is at the stated `a85b39eb` revision; tracked `oracle/kdm6` has no diff; and runtime/coordinator/thermo/satadj hashes match the Red receipt. Both source records clearly disclaim a pre-launch pin and a new RTTOV source-to-binary attestation. The main/weak runner hashes, future cost-runner hash, weak-point receipt hash, source hashes, guard-source hash, and preserved clear-result hash match their current files.

## Passed and bounded checks

- `python -m pytest -q oracle/tests/test_clear_candidate_diagnostic_guards.py`: 2 passed. These are receipt-preservation and archive/public mismatch guards; neither test opens the forecast or runs the model.
- The six-case RTTOV cost receipt’s per-channel quality flags match the retained `rttov_test.log` files. Actual cached `hydro.txt` native suffix slots 6/7 match the receipt’s cloud hashes. Huber arithmetic recomputes exactly from the recorded residuals and masks. The common seven-channel comparison remains marked invalid; channels 12–15 are explicitly diagnostic-only.
- The five T/Q response cases are correctly labeled as one selected layer, with physical-T-to-theta conversion and fixed forcing. The supplemental T−0.8 K H∘M derivative has its own full-map scope, seven-channel support, and no-optimization caveat. The earlier clear/wet selected-output derivatives are not described as a full state Jacobian.
- `M_source_identity.json` resolves the after-run model-source identity gap. No new source-to-binary RTTOV build claim is made.

`git ls-files --others --exclude-standard` currently shows text, source scripts, and JSON only; no native NetCDF, full checkpoint NPZ, full RTTOV profile, executable, coefficient payload or licensed source is in that candidate list. The private checkpoints and RTTOV work directories are ignored under `graphify-out/`. The clear-state receipt includes 66-slot water/ice `q/qs` vectors, each with 27 null upper-reference slots and 39 numeric native-layer values. These ratios are derived from the already-public enriched 39-level P/T/Q receipt and match the supplied external review; they are not raw NetCDF state or newly exposed private values, and the user authorized publication of these derived diagnostics. I therefore do not treat their length alone as a privacy blocker. The cost JSON also repeats the selected seven-channel `observation_bt_K` vector from the hash-pinned observation input alongside model BT and residual vectors. These are channel-space sample values, not full profiles; confirm that the PR’s data-publication scope permits publishing the selected observed-value vector. If raw observation samples are excluded, retain the source hash and report only scalar costs/support. Full private state/profile assets remain private.

The observation timing clarification is now in the main report: saved input 05:55:40, nominal local endpoint 05:56:00, unchanged AMI row 320/column 48, and no claim of VIIRS/AMI pixel-time correspondence.


## Coordinator publication disposition

The PR includes the selected seven-channel observation BT values already published in the paired observation packet and the derived saturation ratios from previously public P/T/Q. The report explicitly separates these small channel/derived diagnostics from private full State/Forcing checkpoints, native NetCDF and licensed assets. This payload-scope question is resolved; no additional private raw profile is being published.
