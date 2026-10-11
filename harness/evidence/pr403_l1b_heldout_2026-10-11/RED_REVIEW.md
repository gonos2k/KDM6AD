# PR403 held-out GK2A AMI L1B Red review

## Result

I found no material source, selection, decode, or quality-accounting blocker. The two sampled scenes are the exact predeclared 05:56 nominal filename slots on 2025-07-20 and 2025-07-21. Each selected complete nine-channel LA020GE source set has matching S3 key/size/ETag in the saved listing; all 18 local files match the recorded SHA-256, size, and single-part ETag MD5. The download receipt binds to plan SHA-256 ce5a3d4a4109813ef61aa199c8b0bcef83d8828d9fdeebe6db5675d275ee54f3; it records 18 files / 8,555,216 bytes and no retry. The private source/payload records are mode 0600 in a 0700 directory. I did not download files or call any model, RTTOV, H/K/M, optimizer, or acquisition path.

The plan uses timestamps and channel completeness only. Both dates had all nine required channels at exactly 05:56, so no fallback was used. The fixed location-only nearest pixel is zero-based row 320, column 48 on each date, at 35.419250693° N, 122.137241647° E and 679.550515 m from the fixed point. I independently inverted the saved GEOS metadata across the 500×500 image and got the same nearest pixel and distance. The fixed 5×5 window contains 25 geolocated cells on each date; it is descriptive per-pixel data with no mean or QA-based selection.

## Independent raw decode and quality checks

I checked each original NetCDF channel file, all 18 of them. The image_pixel_values variables are uint16; their headers identify each expected channel and specify 16 total bits, 2 DQF bits, and channel-specific valid DN width (WV063 12 bits, the remaining channels 13 bits). The per-file DN-to-radiance and Planck/polynomial tuples exactly match the pinned channel table, including its BT wavenumber. The 17 shared scene-family metadata values, geometry, and raw time fields agree across all nine channels per date.

I independently unpacked DQF from the top two raw-word bits and DN from each channel's specified lower valid bits. Every scene has 250,000 finite-geolocation pixels per channel, all with DQF code 0; the selected point and all 25 patch cells per channel match the CSV raw words, DN, DQF, and BT values. I recalculated BT from DN with the file calibration attributes and pinned wavenumber; it matches the reported point and patch BT values to better than 1e-10 K. No NetCDF mask or _FillValue/missing_value attribute is present in these variables, and no nonzero DQF bit pattern occurs in these two scenes. The raw words and decoded DQF remain in the private payload. DQF 0 is source L1B data quality only; it does not mean cloud-free, liquid, ocean-surface, or valid-SST conditions.

The selected point values for the seven analysis channels (10–16) are:

| Channel | AMI channel | July 20 (K) | July 21 (K) |
|---|---:|---:|---:|
| WV073 | 10 | 260.29868 | 252.28933 |
| IR087 | 11 | 291.07781 | 280.18480 |
| IR096 | 12 | 266.19366 | 259.48832 |
| IR105 | 13 | 293.87456 | 282.63887 |
| IR112 | 14 | 293.17789 | 280.15782 |
| IR123 | 15 | 289.65966 | 276.56614 |
| IR133 | 16 | 273.99778 | 262.80886 |

Channels 8 and 9 remain in the source/payload as supporting AMI L1B data. No extra filtering was used to select a particular channel value, location, or date.

## Time, lineage, and limits

The selected filenames identify nominal OBT slots 202507200556 and 202507210556. The scene acquisition headers parse as OBT 20250720_055656 and 20250721_055655; mission_reference_time is the planned UTC 05:50:00, not an observed pixel time. Observation start/end and UTC/OBT synchronization numbers are preserved as raw seconds without inferring an epoch or offset. The payload leaves valid_time_utc unset. These values cannot establish an actual UTC matchup.

The same geographic target coordinate is reused for the two dates; no July 19 native state, forcing, or old RTTOV result was paired with either L1B scene. They are two observations on separate days, not a declaration of independent meteorological events. This result gives GK2A L1B brightness temperatures and source-quality metadata only. It provides no SST retrieval, clear-sky/cloud/phase label, cloud height, atmospheric profile, independent O3/T truth, observation-error R estimate, or new native/RTTOV/DA validation.

The listing XML contains 480 S3 entries per prefix; the selector's reported 360 count is specifically the LA020GE-matching object subset after filtering other resolutions. The exact 9-channel files for the predeclared slot match that subset. This is a count-scope distinction, not a disagreement in the selected source files.

The private payload SHA-256 is d24bb3a5d029ec13d1b25d0afdae95637a971d6d304f38bcc73dae461220bd90; public result SHA-256 is 3182efa96388e650e03e249c5aa0ca775d1d7935cc2a323542904b6b3b1c7268. The plan, helper, four listing files, source file hashes, raw private receipts and independently re-derived channel/point values are bound in the packet.

## Addendum: additive radiance replay

The later `REPLAYED_PATCH_RADIANCE.csv` contains 450 per-pixel rows (two dates × 25 cells × nine channels). I independently recalculated every value as `DN_to_Radiance_Offset + DN_to_Radiance_Gain × retained DN` using the pinned calibration table. Keys, DN values and reader DQF match `FIXED_PATCH_SAMPLES.csv` exactly; all radiance values match exactly at serialized double precision. The replay SHA-256 is `a072ad5f9e7324ea9d460a6f92c63582f4c592b0eba1886aeb37b12628df70f7`, bound in `RADIANCE_REPLAY.json`. This is an additive calculation from already retained words and calibration metadata after the original decode; it does not change or retroactively add a radiance array to the original `FIXED_POINT_PATCH.npz`. It forms no spatial mean. The JSON and revised CSV header, `radiance_mW_m2_inverse_sr_inverse_per_cm1`, make the inverse spectral-radiance unit explicit. This clarity suggestion is resolved.

The coordinator report now explicitly says the native model, IC/BC, KDM6AD and RTTOV assets were not used to produce these observation-only scene results. That resolves the earlier scope wording concern.
