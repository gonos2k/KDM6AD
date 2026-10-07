# Retained internal research inputs and missing physical correspondence

This is a read-only retained-data inventory, not a new collocation/forecast
experiment. No external model/reanalysis input was acquired or substituted.
The first attempt has no additional owner-supplied calibration/error statistics.

## Available bounded diagnostic

The sole retained native 5 km forecast used by C5 has SHA-256
`be0edb894d1ddc5996f925cf01d56d1d882b53d6ed0295566edac2cb60f31308`,
234×282 columns and 39 native levels. Direct NetCDF header reads confirm saved
UTCs 2025-07-19 00:00:00, :20 and :40. Copies are not new initializations.
C5 uses native `(i,j)=(73,157)` and KO pixel `(411,338)` at nominal 00:00.
The recorded grid-center separation is 0.7106 km. The closest retained active
liquid-number state is the :20 frame; the exact label-time frame does not have
that selected active cloud-number support.

This remains a nominal-time, fixed-forcing diagnostic. A longer Python window
against the same target is not a time-collocated observing sequence.

## Correspondence still unmeasured

| Quantity | Existing evidence | Remaining limitation |
| --- | --- | --- |
| KO object identity / DN / decoder | Hashed KO objects and source-paired KMA coefficient table | Decoder pairing does not establish the KO production SRF/calibration baseline |
| KO→ELA product lineage | Header names the ELA parent | Named parent/remapping record unavailable in searched retained roots |
| Pixel time | Nominal filename slot | Exact pixel scan/acquisition time absent; FD time cannot be transferred to KO |
| Geometry/footprint | Projection center and nominal orbit/view construction | Actual ephemeris/attitude, footprint and remapping weights unverified |
| R / bias / B | Existing diagnostic scale and prior implementations | No independent error/bias calibration data supplied; fixed assumptions only |
| Independent weather | One eligible initialization in retained inventory | Nearby columns and duplicate files are not independent initializations |

Sources: [epoch and product audit](CHECKLIST_pr366_epoch_srf_error_2026-10-04.md),
[header receipt](AMI_epoch_metadata_result_2026-10-04.json),
[C5 observation record](C5_matched_observation_diagnostic_2026-10-03.json),
[native window scope](REPORT_native_KMA_window_2026-10-05.md), and
[retained input inventory](REPORT_retained_input_inventory_2026-09-25.md).

R2 cannot be closed as a physically matched observation case from these inputs.
Keep C5 as conditional numerical evidence; do not substitute FD/LA, assign FD
acquisition time, tune sigma to the residual, or claim an independent case.

## Conditional coordinates for the first supported study

Declare stored QN as # per kg dry air and internal N as rho_entry*n; water
mixing ratios and optical content use their declared dry-mass/volume mapping.
Number floors/caps remain the existing internal volume-coordinate convention,
not calibrated physical thresholds. Runtime entry density, fixed background
optical density and the snapshot hybrid-column mass measure are different roles.
Do not replace one with another because its residual is smaller.

The current engineering evidence uses the warm-liquid C5 subset with no
precipitating/mixed-phase inference. It neither approves the historical 100/10
coefficients nor resolves trace mass/number/volume admissibility or full energy
closure. See the existing S2/S17 gates. Those decisions remain OPEN.
