# PR405 Green review — native valid-time linkage

## Finding

Use native `valid_time` coverage to decide whether a retained state can be linked to a held-out scene. A new initialization date is not inherently required: a forecast initialized July 19 could be eligible if it preserves a provenance-complete model state at the required observation time. The cached candidate receipts reviewed here do not show such a July 20 or July 21 valid state.

The cached 84-path inventory is initialization-suffix evidence only: 83 ordinary paths and one quarantined path carry suffix `202507190000`. That suffix count cannot rule out longer-lead valid states. The known candidate horizons recorded in `NATIVE_model_readiness_2026-10-07.json` and the later receipts are:

- Current canonical `lc05_da_run` forecast: July 19 00:00:00 through 00:01:00.
- Pinned C5 forecast: July 19 00:00:00 through 00:00:40.
- Separately retained SS-directory hourly forecast: July 19 00:00 through 12:00 UTC. This is the longest valid-time candidate in the named records, but its directory/configuration differs and it is not attributed to the pinned C5 run.
- The accepted recent native run has saved times only from July 19 05:55:40 through 05:58:00; science acceptance remains false.

Thus the documented candidates do not demonstrate valid-state coverage at the scenes' nominal July 20 05:56 or July 21 05:56 labels. Those labels are not certified pixel UTC: filename OBT and planned UTC remain distinct, and actual pixel time remains unresolved. The result is a bounded non-match in the cached candidate evidence, not global archive absence and not proof that a July 19 initialization could never produce a later valid state.

`NATIVE_TIME_LINKAGE.json` records both scenes as `PENDING_NATIVE_INPUT`, with no selected run or state and no analysis executed. Under its explicitly assumed nominal-filename-time-as-model-UTC research mode, the July 20 case requires background 05:55:40, slot 05:56:00, and the current eight-frame intake through 05:58:00, a 107,760-second lead from the July 19 00:00 IC. July 21 requires the corresponding 05:55:40/05:56:00/05:58:00 times at a 194,160-second lead. The JSON leaves observed pixel UTC null. If one date obtains a suitable provenance-bound state and inputs first, its baseline/analysis/final audit can proceed without waiting for the other date.

## Boundary-time correction

The old native-availability note described the July 19 boundary file as ending at 09:00 by treating its last `Times` record as the interval end. Read-only metadata inspection of the canonical `wrfbdy_d01` confirms `Times` rows at 00, 03, 06, and 09 UTC, but also reveals its per-record domain metadata: `THISBDYTIME` is 00/03/06/09 and `NEXTBDYTIME` is 03/06/09/12. The runnable host source explains these fields: `output_wrf.F` writes the current boundary time and next time as current plus `bdyfrq`; `input_wrf.F` reads them as the starting and ending valid dates and uses `this_bdy_time <= currentTime < next_bdy_time`. The final interval is `[09:00, 12:00)`. A run may reach a terminal saved state at 12:00, but this metadata does not authorize advancing at or beyond 12:00. This corrects the prior 09:00 endpoint. It still does not establish a full-domain forecast state at July 20/21, and it does not extend the boundary file into those dates.

Only `Times` and the boundary time-coordinate metadata variables were read for this correction. No boundary forcing or model state arrays were read. The hourly 12:00 forecast horizon comes from its existing Times-only receipt; no large forecast file was reopened.

## Scope and completion

The evidence supports a valid-time-centered availability status: no July 20/21 native state is demonstrated in the specifically named, cached candidates. Do not make the stronger claim that all 84 inventory paths have been checked for their valid-time horizon, because the inventory receipt records suffix counts rather than one horizon per path. A future matched analysis may use any initialization date that has a suitable, lineage-bound valid state and required forcing/model inputs at the declared scene time; it must preserve native center/interface pressures, T/Q/hydrometeors, and actual saved valid times through the observation interface.

The current observation edition remains GK2A AMI L1B only. External SST, MLS, VIIRS, and L2 are deferred extensions, not completion gates. Actual pixel UTC and footprint correspondence remain limits; nominal scene date must be presented as a declared assumption if used for a candidate link.

The user's PR404 review at main `cc0a2edb` updated the same 100-point rubric from **78 to 79/100**, changing only the first L1B area from 14 to 15. The user-supplied vector is `[15, 12, 8, 10, 13, 11, 5, 5]` (sum 79). This review transcribes that assessment; it is not a new PR405 score or a score computed by this audit. The historical 56/75 belongs to a different earlier rubric. The boundary-time correction and valid-time availability review add no points.

## Review limits

- Reused the cached 84-path inventory, dated readiness receipt, accepted-run completion receipt, and current PR404 availability packet. No broad inventory scan or archive request was repeated.
- Read only `Times`, `THISBDYTIME`, and `NEXTBDYTIME` metadata from the one known canonical boundary file to resolve the 09:00-versus-12:00 endpoint. No full-scene/model arrays, native rerun, acquisition, RTTOV/H/K, KDM M, or optimizer were used.
- The longest forecast candidate in the named records is the separate hourly run through July 19 12:00. This is not a census of all 84 forecast horizons and does not establish absence from uninspected files or archives.
- The source query was run before review: `graphify query "How do the cached 84 native forecast inventory paths, valid Times metadata, run recipes, and AMI held-out dates connect to actual July 20/21 valid-state availability?" --budget 1200`. The graph surfaced the native State and T/Q capture path; availability and temporal claims were verified against the cached receipts and runnable WRF source lines, especially `share/input_wrf.F:1182–1192`.

**Disposition:** Green on the valid-time distinction and the bounded candidate evidence. Correct the old boundary endpoint to the exclusive 12:00 limit for this file, allowing a terminal state there but no further advance on this metadata alone. Keep July 20/21 model-connected availability conditional on an actual lineage-bound valid state at the required time; do not make new initialization date a prerequisite by itself.
