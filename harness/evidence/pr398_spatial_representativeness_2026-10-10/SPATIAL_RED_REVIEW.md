# PR398 fixed-candidate spatial Red review

This review covers the predeclared native 3×3 patch, AMI 5×5 patch, VIIRS
centers selected inside the native-center bounds, and the existing local 5 km
forecast inventory. All samples retain their original fixed candidate
identities. The work used retained files only; it called no new native model,
KDM M, H/RTTOV, optimizer, or external data acquisition.

## Inputs and execution path

The common plan fixes native cells `j=85..87, i=47..49` at saved frames
1, 4, and 6; AMI rows `318..322`, columns `46..50` around `(320,48)` for
channels 10–16; and VIIRS CloudPhase centers inside the axis-aligned bounds of
the nine native cell centers. The VIIRS selection is a descriptive center
bounds filter. It does not represent the exact cell union, cell-edge polygon,
sensor footprint, area weighting, or parallax-corrected match.

The accepted native intake has exit code 0, `experiment_valid=true`,
`model_completed=true`, and eight saved times matching its declared sequence.
PR395's intake reader enforced that saved-time contract. The V3 spatial
extractor additionally reads only the forecast `Times` field before its
one-shot marker, checks all eight rows and the selected `[1,4,6]` labels, then
checks forecast size and modification time around the selected hyperslab
read. The before, after, and time-preflight stats match (2,543,209,268 bytes;
mtime `1791595485694435349`). The multi-gigabyte forecast was not fully
hashed; these checks do not establish full-file cryptographic identity.

The native V1 attempt stopped on its manifest-versus-selected-time-list gate
before opening the forecast. That setup receipt and source remain preserved.
V2 was plan-only. V3 is the sole native 3×3 extraction; it returned 60 arrays
and 27 fixed cell/time diagnostic rows, with no retry, M/H, or optimizer calls.
The private NPZ hash is
`947c72c12ebe289b7ddc84fba1281635d77ffbcfe23f204345cc97abeebc1c21` and
matches the canonical private copy. I independently checked all 60 keys'
shapes, dtypes, hashes, and finite floating arrays. The saved center arrays
match the accepted intake. Center pressure has 39 native levels, reconstructed
P8W has 40 interfaces, and host eta dry mass is float32 with shape
`[3,3,3,39]`.

## Native patch result

Across the 27 cells, raw `QCLOUD` and `QNCLOUD` are zero; raw `QNCCN` is
nonzero, about `1.11×10^9` to `1.96×10^9` in the source field's recorded
number units. The Registry labels number fields `# kg-1` without establishing
the dry-versus-moist mass basis; `QIB` is labeled `m3 kg-1`. No number
calibration or conversion is asserted. All 27 cells have `HGT=0 m` and
`XLAND=2` in the saved frames. The phase-aware `qv/qs` diagnostic spans about
95.15–95.99%, with its maximum at bottom-up level index 3. This uses KDM6
thermodynamics; it is not observed vapor-pressure relative humidity.

The reported QC sums are unweighted sums over levels. They are not LWP, a
vertical path integral, or a water budget. The host eta dry-mass measure is
retained, but no mass-weighted water path is reported. The native patch shows
the fixed cells' saved state; it does not establish a column-average over
physical areas or identify the cause of any satellite/native difference.

## AMI patch result

The AMI table contains exactly 25 fixed pixels for each of seven channels
(175 rows total). Every sample has raw and reader DQF 0, no NetCDF fill mask,
and positive finite calibrated radiance; the direct packed-word decode
reproduces the authoritative reader BT exactly. The center `(320,48)` matches
the retained candidate's seven BTs exactly and its DQFs match.

| AMI channel | Valid BT range (K) | Spatial range (K) |
|---|---:|---:|
| WV073 | 263.193–263.428 | 0.235 |
| IR087 | 286.344–291.249 | 4.905 |
| IR096 | 262.193–265.184 | 2.991 |
| IR105 | 288.932–293.708 | 4.776 |
| IR112 | 289.147–292.964 | 3.818 |
| IR123 | 287.313–289.989 | 2.676 |
| IR133 | 273.431–274.562 | 1.130 |

Radiance is retained per pixel from the hash-bound `offset + gain × DN`
equation; the code does not average BTs and convert the mean to radiance.
These are descriptive patch radiances and BTs, not a footprint integral or a
calibrated spatial observation-error variance. The retained calibration
metadata says the 2025 FD SRF version is unverified, so this does not validate
the exact spectral response of the original samples.

## VIIRS patch result

The native-center bounding box contains 103 distinct VIIRS geolocation
centers, including the unchanged candidate `(205,27)`. Their same-granule
GMTCO coordinates match the CloudPhase geolocations. Raw categories are
CloudPhase `1` for 103/103 and CloudType `2` for 103/103. The raw
CloudPhaseFlag byte is `0` for 94 pixels and `5` for 9. Those bytes are not
bit-decoded here. CloudPhase and CloudType declare `valid_range=[0,5]` and
`[0,8]`; all selected raw values fall within those ranges, with no fill values.
CloudPhaseFlag declares `valid_range=[0,1]`, while 9 selected raw bytes equal
5. The pinned observation packet documents the product's packed-byte/
valid-range inconsistency. The spatial result preserves those raw bytes and
does not classify the nine values as usable or unusable QA. The sample
center's four angles match the retained geometry result; across selected
centers satellite zenith spans 68.829–69.053° and azimuth spans
−91.868–−90.848°.

These are counts of geolocated sample centers, not area-weighted cloud
fraction or 103 independent observations. No full CloudHeight source was
available and hash-verified for this patch, so center CTH was not extended.
No per-pixel UTC, footprint overlap, height datum, parallax displacement, or
physical AMI/VIIRS/native matchup is established. In particular, raw class
counts do not resolve the native zero-QCLOUD neighborhood into an observed
model error.

## Existing 5 km date inventory

The bounded local `host/` inventory contains 84 `klfs_lc05_fcst.*` paths.
The suffix counts independently reproduce as 83 with initialization suffix
`202507190000` and one quarantined clobbered copy with the same initial stamp.
The inspected retained initial condition is `2025-07-19_00:00:00`; the
boundary file covers 00:00, 03:00, 06:00, and 09:00. The other retained files
are repeated frames, run variants, or coarser outputs from that same
initialization. They do not supply two independent event dates for this
candidate. This conclusion is limited to the inspected local inventory; it
does not claim that unavailable archives contain no other dates.

## Red disposition

The artifacts support a fixed-candidate spatial description and help bound
representativeness. They do not support best-neighbor selection, candidate
replacement, physical overlap, per-pixel time alignment, a validated cloud
mask, retrieval identifiability, calibrated error covariance, physical water
closure, or forecast-skill claims. Raw phase flags, calibration/SRF status,
pixel time, CTH datum, footprints, and pixel areas remain distinct
uncertainties.

### Provenance

- Native plan/driver: `NATIVE_PATCH_v3.json`, `native_patch_v3.py`; driver SHA
  `6921bfb0a05d6d9619f242beca5a702e81a3546f54252c6b33501b5763abf2ff`, plan
  SHA `4867f925372325a477a5c3ee5141053f07e932235551ed0a1d5a9af8f4308364`.
- Native result/table: `NATIVE_PATCH_RESULT_v3.json`, `NATIVE_PATCH_TABLE_v3.md`,
  `NATIVE_PATCH_SUMMARY_v3.md`; result SHA
  `3417158f5e47fe836f24b49309bfe3df36b81d34ecb4d4a1266ba38706dd7efb`.
- Native availability inventory: `NATIVE_5KM_AVAILABILITY_v3.json`.
- Observation source/result: `observation_patch.py`, `OBSERVATION_PATCH.json`;
  source SHA `8994402e328d7f60fb573a19ff9e66fd91f42d01cdff930c252fc7285aae9903`,
  result SHA `4efd2fffece5de6303bdeda5623c8929d53c97f14760940748d2483bd6b783f0`,
  private NPZ SHA `0b55e3e5f78b21a19476d1f6557a8fed23ff74a50eaab8322a4603a147003234`.
- Observation tables: `AMI_PATCH_5x5.csv`, `AMI_PATCH_CHANNEL_SUMMARY.csv`,
  and `VIIRS_PATCH_CATEGORY_COUNTS.csv`; each file hash is recorded in
  `OBSERVATION_PATCH.json`. The corresponding compact arrays and row-level
  VIIRS geolocation/angles are in the hash-bound private NPZ listed there.
  `OBSERVATION_PATCH_QA_AUDIT.json` separately records the CloudPhaseFlag
  declared-range discrepancy while confirming that the extraction receipt,
  public tables, and private NPZ remain unchanged.
- Source contracts: `harness/evidence/pr395_native_tq_intake_2026-10-10/intake_native_tq.py`,
  `harness/evidence/native358_artifact_diag_2026-10-08/recipe/run_native_kma_bt_frames.py`,
  `oracle/kdm6/thermo.py`, `oracle/kdm6/obs/gk2a_l1b.py`, and
  `oracle/kdm6/obs/gk2a_l1b_la.py`.
