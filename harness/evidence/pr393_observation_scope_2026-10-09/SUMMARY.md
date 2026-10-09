# PR393 observation scope and bounded target-run packet

Review basis: PR393 head `c543b98c`, still open when reviewed, on merged main `ce77afa2`. This packet reuses the PR391 observation receipt and native target receipt. It does not read or hash the 2.54 GB forecast, rerun its reader, launch a host/KDM6/RTTOV job, acquire satellite/model data, or change the candidate. The current checkout has no private `host/` tree; exact prior source/build/input identities below come from the archived receipts, not a fresh build inspection. The isolated RUN1 case is now staged, with consumed-file preflight and no launch; see [case preparation](../pr393_target_preparation_2026-10-09/PREPARATION.md) and [receipt](../pr393_target_preparation_2026-10-09/PREPARATION.json).

## What is measured

The fixed candidate remains NOAA-20 VIIRS JRR-CloudPhase v3r2 `JRR-CloudPhase_v3r2_j01_s202507190555475_e202507190557102_c202507190621171.nc`, row 205/column 27 (zero based), at 35.4156379700 N, 122.1433868408 E. Its pinned original SHA-256 is `7fef6df795254f628c79e92c25816fed720e855bba46a9ba74adb92abac0cfe2`; the retained NOAA-20 object path is `VIIRS-JRR-CloudPhase/2025/07/19/JRR-CloudPhase_v3r2_j01_s202507190555475_e202507190557102_c202507190621171.nc`. The candidate screen remains phase 1, stored QA byte 0, native `XLAND=2`, within 3.5 km, at least 10 cells from the native edge, then minimum center distance. The selected native cell remains j=86/i=48 (zero based; Fortran j=87/i=49), initial grid 282×234. Its nominal center is 7.367 m from the VIIRS nominal center. This is center-coordinate distance only.

At the VIIRS target, the stored values are `CloudPhase=1`, `CloudType=2`, `CloudPhaseFlag=0`. NOAA Cloud Type ATBD v3.0 classifies phase 1 as liquid and type 2 as liquid; this supports a retrieved cloud-top category, not a warm, single-layer, nonprecipitating, full-column classification. The variable metadata declares `CloudPhaseFlag` valid range 0..1, but the granule contains 214,771 nonfill raw values outside that range. The prior default netCDF masked read misreported 19,338 nonfill values as `-128`; the corrected stored-byte read found zero actual `-128` fill bytes in the arrays. The selected raw byte remains zero. No version-matched bit decoder or scientific QA approval is established. The NOAA SDR geolocation fields report scan `QF1=128` (mirror side B with other documented status bits zero), scan `QF2=0`, and target pixel `QF2=0`; this is geolocation status, not cloud-retrieval QA.

The same-overpass product objects are `JRR-CloudHeight_v3r2_j01_s202507190555475_e202507190557102_c202507190621171.nc` (pinned GCS generation `1752906345359928`) and `JRR-CloudDCOMP_v3r2_j01_s202507190555475_e202507190557102_c202507190627286.nc` (generation `1752906525369387`). The CloudHeight range receipt reports target CTH 587.736938 m, CTT 296.570679 K, CTP 940.985229 hPa, height QA 0, and height parameter flags `[3,1,1,1,1]`. The HDF5 field says units “Meter” but gives no explicit vertical datum in its stored attributes. It also stores parallax coordinates 35.415225983 N, 122.126564026 E, 1,525.19 m from the nominal point. These target values replayed from 36 cached HDF5 values; the complete CloudHeight and CloudDCOMP granules were not downloaded or full-file hash verified. CloudDCOMP `EQualityFlag=17` lies outside that field's declared 0..6 range, so its optical-depth/effective-radius values are not accepted truth.

AMI remains the same LA020GE 05:56 slot and pixel row 320/column 48. The selected IR105 sample is 291.3025922 K; all nine channel DQFs are zero. AMI is a 500×500 local-area product with nominal 2 km channels and SINC resampling. Center distances are 686.644 m VIIRS-to-AMI and 679.550 m AMI-to-native. These distances do not establish overlap of the VIIRS detector footprint, AMI resampling footprint, or 5 km model grid cell.

## What official metadata narrows, and what it does not

The KMA GK-2A L1B guide says `scene_acquisition_time` is the OBT of the first swath/first packet, and `mission_reference_time` is the planned UTC observation start for the whole image. It documents `observation_start_time`/`observation_end_time` as seconds and a `time_synchro_utc`/`time_synchro_obt` synchronization pair. In this selected file, the OBT-labelled scene string is `20250719_055656`, the planned UTC label is `20250719_055000`, `observation_start_time_raw` equals `time_synchro_obt_raw` at 806176616.1714611, and `time_synchro_utc_raw - time_synchro_obt_raw` is 0.0059725 s. The guide does not specify the numeric epoch for these fields or per-pixel time. Applying the paired offset to observation start/end is therefore only an exploratory mapping unless the product's numeric time basis is independently documented. The prior Satpy noon-epoch interpretation (05:56:56.171461–05:57:56.016143Z) remains conditional; the offset-adjusted interval would also be conditional. Neither is a certified AMI pixel UTC.

The VIIRS scan timing is better anchored: NOAA-20 GMTCO original hash `2a194c417533a1087543cc7a91b1de2a5a6d8d71d1d71e2bfeb1571cc9f8dd0c` matches valid EDR geolocation arrays exactly. With the product UTC aggregate anchor plus same-granule IET differences, target row 205 maps to scan 12, detector 13 (16 detector rows per scan), and yields a scan-start bracket 05:56:08.986512–05:56:10.773095Z. This is not per-pixel acquisition time; an absolute IET epoch/leap conversion was not independently certified. It brackets the saved native frames at 05:56:00 and 05:56:20 without making either a time-aligned sample.

NOAA ACHA v3.4's parallax equations use `(Zc−Zs)`, cloud-top height relative to surface height, with the satellite viewing angles. This narrows the quantity required for an ACHA-style correction, but does not define the datum of this sample's `CldTopHght` attribute or independently validate the stored parallax coordinates. The local tangent estimate is 2,866.61 m per assumed 1 km of surface-relative cloud height; treating 587.74 m as surface-relative would yield 1,684.81 m. These are sensitivity calculations from the retained geometry, not an applied correction or actual cloud displacement. Do not shift or reassign the fixed candidate from a center-distance comparison.

## Separate verified facts from exploratory cases

| Case | Fixed inputs and rule | Interpretation |
| --- | --- | --- |
| A — nominal-coordinate diagnostic (recommended for a future valid native run) | Keep VIIRS 205/27, AMI 320/48, and native j86/i48. Compare only the requested saved native frames at their recorded times. Use nominal coordinates, no parallax correction; mark AMI pixel UTC unresolved. | A reproducible diagnostic sampling design. It does not claim satellite simultaneity, footprint overlap, or physical matchup. |
| B — VIIRS scan-bracket display | Keep the same candidate; display 05:56:08.986512–05:56:10.773095Z beside native 05:56:00 and 05:56:20. No temporal interpolation; AMI UTC stays unresolved. | A bracketed context view, not a chosen native frame or matched observation. |
| C — conditional AMI timing | Only if a version-matched source establishes numeric epoch and pixel/scan timing, report the converted interval and its uncertainty next to A/B. Until then show both documented raw metadata and a separately labelled exploratory conversion. | Sensitivity only; do not call the conditional Satpy or sync-offset arithmetic certified UTC. |
| D — conditional parallax | Keep the fixed candidate and native cell. Show nominal and product-stored corrected coordinates side by side; if independently justified, also show an explicitly surface-relative height calculation. | Separate geometry sensitivity; do not infer footprint overlap or let the BT residual choose a shift. |

The BT and cloud-category agreement are not case-admission criteria. Observation QA, AMI time, cloud structure, parallax datum, and footprint may remain open while a future native target simulation is run and validated as a model experiment. They remain open for R2 physical comparison.

## Bounded future target-run specification (prepared, not launched)

Recommendation: if the owner selects D1's resource window, run the unchanged fixed candidate under Case A as a **nominal diagnostic**. Unclosed satellite QA/timing is not a prerequisite to running the native model; it limits interpretation of any observation comparison. This review did not launch the run.

Preserve the exact prior host experiment configuration and only use it if the archived identity checks below match the staged files. The prior invocation was:

```text
python harness/run_ss_case.py --mp 337 --minutes 358 --seconds 0 --history 0 --history-s 20 --np 1 --fixed-dt --label viirs_norm2_dry1_055540_055800 --case <new isolated case directory>
```

The placeholder must be a fresh isolated case directory; do not reuse the historical directory because the runner removes old `rsl`/`wrfout` files. Keep its exact actual files and input names:

| Role | Exact filename | SHA-256 from prior receipt |
| --- | --- | --- |
| Initial field | `/Users/yhlee/KDM6AD+/KIM-meso_v1.0/test/ss_real_case_20260619_063620/SS/wrfinput_d01` | `5a9ae8da992028dbf3a2a7652eb61532c1efab2acea7ea0e393e4cac8fd4c970` |
| Lateral boundary | `/Users/yhlee/KDM6AD+/KIM-meso_v1.0/test/ss_real_case_20260619_063620/SS/wrfbdy_d01` | `d46e5d7117c076956d130b4ff905fc34a5d53dbd5a0d9571311582b0a60c5e6c` |
| Auxiliary input 24 | `/Users/yhlee/KDM6AD+/KIM-meso_v1.0/test/ss_real_case_20260619_063620/SS/wrfchainp_d01` | `c8e300d2aa52f98c9060803438ab6f796bddd1e1cdd6b75a14e39a398cb0c4e3` |
| Expected forecast basename | `klfs_lc05_fcst.202507190000` | New run's identity is unknown until it runs |

The exact previous staged `namelist.input` is in `NATIVE_target_artifact_receipts_2026-10-08.zip` at `build/target/namelist.input`. Its relevant values are `run_minutes=358`, `run_seconds=0`, start 2025-07-19 00:00:00, `time_step=20`, `use_adaptive_time_step=.false.`, `step_to_output_time=.false.`, `mp_physics=337`, `history_interval=0`, `history_interval_s=20`, `history_begin_d=0`, `history_begin_h=5`, `history_begin_m=55`, `history_begin_s=40`, and the three exact input-name templates above. Keep the `history_begin_*` key names distinct from `history_interval*`. This preserves the previously observed eight outputs from 05:55:40 through 05:58:00 every 20 s. The UCAR WRF guide documents `history_begin` as elapsed time from run start and `_d/_h/_m/_s` alternatives; before relying on this private fork, inspect its `namelist.output` and the actual `Times` field.

The prior isolated build identity, not a guess for a new build, was:

| Build input | Exact prior identity |
| --- | --- |
| Archived build receipt source head | `30931e52f99e38f9abcd6e7e3b8cd055227a5c23` |
| PR393 review head | `c543b98cc42f0e906b63568df209d974300d771d` |
| Isolated patch manifest | `source_patch/patch_manifest.json`, SHA-256 `8b0a650d6bd4fb16941f52e0754c45581dc73e1ad5d8db23661a9e4dcb4d5ea8` |
| Experimental wrapper source | `/private/tmp/KDM6AD-viirs-native-run-20261007/isolated_project/host/KIM-meso_v1.0/phys/module_mp_kdm6ad_cons.F`, SHA-256 `e4ab55a672f28c47d341ebf75ce589b32c2bbaa4da960c6b04157ec682a46965` |
| Host ISO source | `/private/tmp/KDM6AD-viirs-native-run-20261007/isolated_project/host/KIM-meso_v1.0/phys/kdm6_iso_c.F`, SHA-256 `4c7f9f22df54e91f30f97d1d8c0b8921537913f4236c6baf56c5579701a64f07` |
| WRF executable | `/private/tmp/KDM6AD-viirs-native-run-20261007/isolated_project/host/KIM-meso_v1.0/main/wrf.exe`, SHA-256 `f467755ee9952dc2b1806e9dec3220689e2f26a2939234b0959065b1c357cd41` |
| Linked ABI library | `/private/tmp/KDM6AD-viirs-native-run-20261007/isolated_project/libtorch/install/lib/libkdm6_c.2.0.0.dylib`, SHA-256 `64cddefe4fce336a7b9a3979278692324a97a17fe7d5264224bcc05a7f20be2d`; ABI 2, args size 344 bytes |
| Run harness | `/private/tmp/KDM6AD-viirs-observation-context-20261007/harness/run_ss_case.py`, SHA-256 `175ade71058672b957d565ef88ffd7925bc7d74dfe559c36aaec61fa8de0d96e` (identical to current worktree script) |
| Runtime mode | marker `KDM6AD_PRIVATE_EXPERIMENTAL_MP337 physics_variant=2 dry_number=1`; report records `value_only=1`; one MPI rank, one model thread |

These are archived build identity pins, not a fresh PR393 build or proof of actual runtime-loaded libraries. A commit-to-commit `git diff --name-status 30931e52f99e38f9abcd6e7e3b8cd055227a5c23 c543b98cc42f0e906b63568df209d974300d771d -- libtorch` returned no tracked paths, so the public C++/libtorch source snapshot is unchanged between those commits. That does not establish which snapshot produced the staged dylib. The preflight matches consumed executable/library/input/wrapper/ISO/runner/namelist identities to the archive; it does not claim a new build from c543 or a runtime load. The public packet lacks a complete private WRF host source tree hash; this remains an attribution limit, not a new run gate. The canonical private host path is not present in this public worktree, and no new host build was performed.

Use the original `wrfinput_d01`/`wrfbdy_d01`/`wrfchainp_d01` inputs at the 00:00 base time; do not restart from the prior failed target forecast or modify the initial background. This is a forward model run only; it does not include a T/Q analysis, warm start, optimizer, or observation-tuned increment. The future run is valid as a **model experiment** only if the runner exits 0 and marks `experiment_valid=true`, the wrapper/library/input identities match the consumed-artifact preparation receipt, the model records normal completion, and actual output `Times` are exactly the eight saved times above. Preserve failures as invalid diagnostics; the prior 358-minute run logged WRF success but returned exit 1 after `prterun` reported improper termination. The cause remains unknown. The prior elapsed wall time was 20,823 s (about 5 h 47 min); that is historical observation only, not a prediction of the next run's duration or a resource-cost estimate.

Keep all 39 native levels, native pressure centers/interfaces, and selected native column. No external model/reanalysis, grid remapping, column substitution, or physics parameter change. A successful run does not close QA or R2, and an unfavorable BT or cloud match does not invalidate the run or select another candidate.

## Program-level statuses kept separate

| ID | Status at this review | Reason |
| --- | --- | --- |
| D1 | OPEN; bounded nominal target-run spec prepared, not launched | Future run requires its own resource/run decision; observation QA is not a run prerequisite. |
| D2 | OPEN | No approved physical observation comparison; BT/cloud presence never admits a case. |
| D3 | OPEN | First physical support regime, number/mass conventions and density roles are not adopted. |
| D4 | OPEN overall | Local 20/10/5 s response exists as a bounded diagnostic; full host timestep, native multi-column and unused-data checks remain separate. |
| R1 | OPEN | Physical regime, thresholds, admissible moments, density policy and applied budgets remain unapproved. |
| R2 | OPEN | No independently accepted time/QA/geometry/footprint-matched case with a valid new native run. |
| S17 | OPEN | Full signed number inventory, external/boundary flux and other omitted terms are unresolved; satadj-only closures do not close S17. |

## Provenance and coverage

The baseline graph query returned generic native artifact/footprint nodes and did not expose the observation records. I therefore checked the pinned local results and source code against the source summary and receipt. The graph is incomplete for this observation path; the semantic fragment at `graphify-out/pr393-observation-green/semantic.json` is review-scoped and is not a full graph refresh.

Local evidence: [PR391 observation summary](../pr391_observation_scope_2026-10-09/summary.md), [observation receipt](../pr391_observation_scope_2026-10-09/receipt.json), [VIIRS context report](../REPORT_VIIRS_context_2026-10-07.md), [native target artifact report](../REPORT_native_target_artifact_2026-10-08.md), [native run receipt](../native358_artifact_diag_2026-10-08/build/target_native_run_receipt_2026-10-08.json), [PR391 T/Q response report](../pr391_tq_response_2026-10-09/REPORT.md), and [target artifact receipt archive](../NATIVE_target_artifact_receipts_2026-10-08.zip).

Official primary references: [KMA GK-2A L1B data-use QA guide](https://datasvc.nmsc.kma.go.kr/resources/common/pdf/%EC%B2%9C%EB%A6%AC%EC%95%88%EC%9C%84%EC%84%B1%202A%ED%98%B8%20%20%EC%9E%90%EB%A3%8C%ED%99%9C%EC%9A%A9%20QA.pdf) defines the OBT/planned-UTC roles and listed metadata fields; [NOAA Cloud Type ATBD v3.0](https://www.star.nesdis.noaa.gov/jpss/documents/ATBD/ATBD_EPS_Cloud_CldType_v3.0.pdf) supports retrieved phase/type categories but not a version-matched QA bit interpretation; [NOAA VIIRS SDR Dictionary Rev L](https://nesdis-prod.s3.amazonaws.com/2024-01/474-00448-02-06_JPSS-VIIRS-SDR-DD-Part-6_L.pdf) documents scan/geolocation flags and azimuth convention; [NOAA ACHA ATBD v3.4](https://www.star.nesdis.noaa.gov/jpss/documents/ATBD/ATBD_EPS_Cloud_ACHA_v3.4.pdf) gives the `(Zc−Zs)` parallax relation; [UCAR WRF namelist guide](https://www2.mmm.ucar.edu/wrf/users/wrf_users_guide/build/html/namelist_variables.html) documents history begin/interval fields. None of these sources alone certifies this sample's physical matchup.
