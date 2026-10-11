# PR403 held-out GK2A AMI L1B scenes

Two new GK2A AMI Level-1B LA020GE scenes were selected at the fixed point (35.415660858° N, 122.143310547° E), using exact nominal filename slot 05:56 on July 20 and July 21, 2025. Each date had all nine requested channels at the exact slot, so no fallback was used. The pre-download plan is [`PREDECLARED_PLAN.json`](PREDECLARED_PLAN.json), SHA-256 `ce5a3d4a4109813ef61aa199c8b0bcef83d8828d9fdeebe6db5675d275ee54f3`. Selection depended only on the predeclared timestamp, channel completeness and geographic location.

The public S3 manifest pinned 18 source objects totaling 8,555,216 bytes, below the 20 MiB limit. All files downloaded once from `noaa-gk2a-pds`; local sizes and MD5 values match their single-part S3 ETags, and SHA-256 values are preserved in the private download/decode receipts. The canonical originals and selected pixel payload are under `/Users/yhlee/KDM6AD-k/host/research_evidence/pr403_l1b_heldout_20261011/l1bheldout20261011c/`, with private directory mode `0700` and data files mode `0600`. No retry was performed.

The existing `read_la_slot` reader and paired AMI calibration decoded both complete nine-channel scenes. In each, the location-only nearest pixel is at row 320, column 48, coordinates 35.419250693° N, 122.137241647° E, 679.55 m from the fixed point. It lies inside the predeclared 2.5 km radius. The fixed 5×5 raster window contains 25 geolocated cells for each date. The point BT values in K are:

| Channel | AMI channel | 2025-07-20 | 2025-07-21 |
|---|---:|---:|---:|
| WV063 | 8 | 238.89196 | 235.83764 |
| WV069 | 9 | 250.09905 | 243.83029 |
| WV073 | 10 | 260.29868 | 252.28933 |
| IR087 | 11 | 291.07781 | 280.18480 |
| IR096 | 12 | 266.19366 | 259.48832 |
| IR105 | 13 | 293.87456 | 282.63887 |
| IR112 | 14 | 293.17789 | 280.15782 |
| IR123 | 15 | 289.65966 | 276.56614 |
| IR133 | 16 | 273.99778 | 262.80886 |

At the selected point, the production reader reports DQF 0 in all nine channels on both dates. The full 500×500 scene also has DQF 0 for all 250,000 geolocated pixels in each channel. This is Level-1B source-data quality only: it is not a cloud, clear-sky, ocean-surface or phase classification. The 7-channel analysis subset remains channels 10–16; channels 8–9 are retained as supporting observations.

Time remains explicitly unverified as UTC. The filename slots are nominal OBT labels `202507200556` and `202507210556`; the reader preserves scene acquisition OBT `20250720_055656` and `20250721_055655`. Each file's `mission_reference_time` is planned UTC 05:50, not observed pixel time. Raw observation start/end and UTC/OBT synchronization numbers retain their original values and units, with no epoch or offset inferred. The production payload leaves `valid_time_utc` unset.

[`POINT_SAMPLES.csv`](POINT_SAMPLES.csv) contains the nearest-pixel BT/DQF values. [`FIXED_PATCH_SAMPLES.csv`](FIXED_PATCH_SAMPLES.csv) contains per-pixel values and packed words for the fixed 5×5 window; it does not average BT or estimate observation-error `R`. Full raw source files, header/navigation/calibration attributes, source hashes, packed patch arrays and decoded receipts remain in the restricted host archive. See [`RESULT.json`](RESULT.json) for the public result binding and [`PREFLIGHT_ATTEMPT1_FAILURE.md`](PREFLIGHT_ATTEMPT1_FAILURE.md) / [`PREFLIGHT_ATTEMPT2_FAILURE.md`](PREFLIGHT_ATTEMPT2_FAILURE.md) for preserved metadata-only preflight history; those attempts downloaded no granules.

These are two separate GK2A L1B scenes, not independent meteorological events. This evidence does not establish a cloud-free SST retrieval, an observed cloud phase, an SST profile, a matchup to July 19 model state, or a new native/RTTOV/KDM validation result. No SST/other sensor observation, RTTOV H/K, KDM M, native forecast or optimizer was used.

After the original decode, the coordinator reconstructed all 450 patch radiances from the retained DN and exact paired gain/offset. [`REPLAYED_PATCH_RADIANCE.csv`](REPLAYED_PATCH_RADIANCE.csv) and [`RADIANCE_REPLAY.json`](RADIANCE_REPLAY.json) record this additive arithmetic replay and its input/output hashes. Radiance arrays were not originally stored in the executed NPZ or patch CSV; these additional values are neither a new reader execution nor a spatial average.
