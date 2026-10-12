# Bounded identity audit: July 19 hourly MP137 candidate

## Finding

The named run was a completed 12-hour MP137 host integration, not merely a filename-based candidate. Its run-specific archive is `SS/runs/mp137_termparity_720min_hist60_np4_20260718_185625`; the archived `exit_code` is 0, and all four `rsl.error.0000` through `.0003` logs report `2025-07-19_12:00:00 wrf: SUCCESS COMPLETE WRF`. The run-specific WRF history file has 13 hourly `Times` from `2025-07-19_00:00:00` through `2025-07-19_12:00:00`. Metadata reports WRF V4.6.0, a 234×282 horizontal grid at 5 km, and 39 mass levels. Its copied run namelist and the source case namelist have matching SHA-256 `064b6f5ea5683ee3dc68d408c08bf4cbf588be06dbc7d99bb3529be8ba61554a`; that configuration declares `mp_physics=137`, a 20 s fixed step, a 720-minute run from 00:00 to 12:00, and hourly history output.

The directly associated `terminal_parity.log` names this exact MP137 run alongside its MP37 comparison, says both returned `exit_code=0`, and reports all 13 frames including 12:00 passed strict raw-bit comparison. This corroborates the run identity and completion, but that comparison is a parity result, not an independent certification of build provenance or scientific correctness.

## Provenance limits relevant to reuse

The candidate’s runtime log identifies WRF V4.6.0 and prints source-commit text `48d8c323edd91019529837a226bffbe51bf727ea`. That is useful runtime evidence, but no executable SHA or immutable build receipt is retained with the run. The current `SS/wrf.exe` symlink resolves to `host/KIM-meso_v1.0/main/wrf.exe`, whose current modification time is 2026-08-23—after the July 18 run—so its current bytes cannot identify the executable used then. The run wrapper archives the namelist and rank logs but not a binary digest.

The run namelist points to `wrfinput_d01`, `wrfbdy_d01` and `wrfchainp_d01` in the case directory. The corresponding current files have July 19 `Times`, 5 km grid and 39-level metadata; `wrfchainp_d01` reports a `START_DATE` attribute of 2024-07-23 06:00 even though its 13 `Times` records are 2025-07-19 00:00–12:00, and this metadata difference is unresolved here. The boundary file’s encoded `THISBDYTIME` / `NEXTBDYTIME` pairs cover `[00,03)`, `[03,06)`, `[06,09)` and `[09,12)`. The 12:00 boundary endpoint is end-exclusive for further advancement. No input-file hashes are captured in this run directory, so exact input-byte identity is not established by these receipts.

The root-level `SS/klfs_lc05_fcst.202507190000` file is not inode-identical to the run-specific child forecast, although both have the same size and modification time. The run-specific file is the one named by the terminal-parity receipt and is the safer artifact to reference. I did not hash either 4.13 GB forecast file, inspect forecast weather arrays, or assume byte identity from matching size/time.

The matching July 19 initialization, 5 km/39-level geometry, MP137 setting and successful 00–12 run make this a completed host artifact relevant for bounded candidate use. It is not byte-exactly admitted on build or input lineage. No direct `run_identity` JSON is present; identity is reconstructed from the terminal-parity record, run directory, namelist, exit marker and rank logs. Keep executable-byte and input-byte limitations explicit. This check does not certify forecast skill or the validity of analysis results.

## Bounded checks performed

Read only the named SS candidate parent and the exact terminal-parity child. Inspected the child’s small namelist, exit marker, terminal-parity record, WRF rank logs and runtime header; read NetCDF dimensions/attributes/`Times` from the run-specific output and NetCDF `Times`/`THISBDYTIME`/`NEXTBDYTIME` from the stated initial/boundary inputs; read `Times` from the hourly history output. The only other evidence consulted was the already-known PR404 native availability report/receipt, PR405 time-linkage correction, and LC05/WRF host wiki pages. No model run, model/H/optimizer call, broad inventory search, weather-array read or large forecast hash was performed.
