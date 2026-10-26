# Offline native cloud efficacy audit

This packet pairs the saved baseline with the accepted restricted alpha=1 candidate on the original 65,988 native columns and 39 bottom-first mass levels. The candidate is a single saved KDM state response at the fixed analysis time. This audit made no new KDM, RTTOV, host, or optimizer calls and uses no external model or reanalysis data.

## Reproduced support and BT response

IR105 is channel 13 (channel index 3). The frozen baseline support has 54,504 columns; the subset with a nonzero restricted control has 43,062. The QC-empty warm-residual cohort is defined as all 39 baseline QC values equal to zero and baseline model BT minus observed BT greater than 10 K. It contains 11,730 supported columns, 9,699 of them with nonzero restricted controls.

On the 54,504 supported IR105 columns, the absolute candidate-minus-baseline BT change has median 9.04×10⁻⁶ K, p95 0.0198 K, p99 0.282 K, and maximum 11.405 K. There are 1,013 columns with |ΔBT| ≥ 0.1 K and 127 with |ΔBT| ≥ 1 K; the RMS increment is 0.113 K.

The baseline B−O residual RMSE is 19.9357 K; candidate A−O RMSE is 19.9250 K, a 0.0107 K improvement on this cohort. Absolute residual improves by at least 0.1 K for 999 columns and by at least 1 K for 122, while 1,072 columns worsen. For the QC-empty warm-residual cohort, maximum |ΔBT| is 0.0492 K and RMSE changes from 29.4555 K to 29.4549 K. No column in that cohort changes by at least 0.1 K.

## Native phases and optical mapping

The audit uses physical native temperature from the saved native-profile temperature field, not `T_NEW`. It reports layerwise ΔT, ΔQV, ΔQC, ΔQI, and ΔQS at matched native bottom-first levels and per-column LWP/IWP diagnostics. LWP uses QC. The direct ice optical mapping uses QI+QS; QI-only IWP and QG column mass are separate diagnostics. There is no QR remapping or area-integrated domain mass claim.

QC-zero-to-positive transitions are zero; 14 baseline-positive QC layer cells become zero. Profile-valid and fixed-support counts do not decrease. QC-empty does not mean optically empty: among supported m0 columns, QC-empty columns with QI or QS present number 15,328 at baseline and 15,330 at candidate. True optically empty columns require QC=QI=QS=0 at all 39 levels.

For valid saved RTTOV profiles, native CFRAC is read from the original result NPZs and mapped back to the bottom-first 39-level segment. Unsupported profile rows remain unknown. The source formula `rho_d*(QC+QI+QS)` with its 1e-6 g/m³ gate reproduces every stored CFRAC bit in valid rows. CFRAC changes at 11 native layer cells, all from positive to zero; there are no zero-to-positive transitions. CFRAC is a detached binary gate, not continuous cloud-cover truth. A warm IR105 residual alone is not evidence of cloud truth.

## Files and replay

`EFFICACY_AUDIT.json` contains the full metrics, cohort definitions, per-level summaries, hash checks, and limitations. `data/native_fields/` holds lossless binary64 NPZ splits, each under 50 MiB; `data/inputs/` contains the fixed channel comparison, restricted controls, and top-gradient receipt used by the analysis. `data/figures/` contains native-grid response maps, BT cohort distributions, and native-level deltas. `lineage/` preserves the v7 export/input manifests, execution receipts, and exact source snapshots. The manifests preserve original source paths as provenance; the arithmetic can be replayed from the relative `data/` artifacts.

The one-shot cloud-analysis effectiveness goal is **not met** by this result. The intended use is a fixed-time tendency diagnostic; applying a state change requires a fresh gradient/optimizer relinearization to assess another analysis iteration. No host time advance, forecast skill, unattended cycle, or convergence claim is made.
