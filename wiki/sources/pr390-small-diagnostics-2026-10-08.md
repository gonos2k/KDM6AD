---
title: PR390 MPI and actual RTTOV extinction diagnostics
type: source
date_modified: 2026-10-08
---
# PR390 MPI and actual RTTOV extinction diagnostics

The [local follow-up report](../../harness/evidence/REPORT_pr390_small_diagnostics_2026-10-08.md)
starts from PR390 `ada6fc42`. Minimum Fortran controls demonstrated the existing
observer's MPI-finalize and C-exit forwarding with the historical KDM6AD/PyTorch
runtime loaded. A separate paired 20-second initial-time experimental mp337
(normalized variant 2, dry number 1, value-only) host smoke exited
normally with/without the observer; its two saved frames had 254 variables
bit-identical, including Times. This does not explain the historical 358-minute
launcher exit 1 or validate its target-time arrays.

One saved RTTOV profile was replayed with the original executable and a separate
private diagnostic build. All 11 retained direct/K output files were byte-identical.
Actual total extinction exceeded 20 km^-1 in top-down one-based layers 65–66 of
channel 8 and 64–66 of channel 9; maxima were 38.407033 and 22.595690 km^-1.
The measured additional hydrometeor contribution was zero; individual gas
species were not attributed. These arrays come from the new diagnostic build,
not the historical binary, and replace proxy estimates only for that input.

The candidate and exploratory 1 K/zero-bias objective stay fixed. Retrieval QA,
pixel UTC, parallax/common footprint, the clear-model/liquid-retrieval mismatch
and a valid target run remain OPEN. R2 remains OPEN. The earlier distance P3 is
closed; no new geometry/cost replay was required. See
[[review388389-local-resolution-2026-10-08]] and
[[native-target-artifact-diagnostic-2026-10-08]].
