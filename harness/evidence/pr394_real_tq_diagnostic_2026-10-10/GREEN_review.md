# Final Green coverage review

Read-only review of saved artifacts; no experiment or calculation was replayed.
The analysis driver SHA, preflight and baseline receipt hashes, reconstructed
raw hash and Jb+Jtheta+Jo decomposition agree with RESULT. All 19 recorded
production-source entries and the immutable paired-case maps match before and
after. The checkpoint, frame, cost, executable and coefficient hashes were
recorded once rather than all rehashed afterward; only the explicit before/
after maps establish invariance.

The actual baseline H retains seven AMI channels 10–16 with zero model quality
flags and exact stored BT/Jo and profile arrays. The one-forcing, 20-second,
normalized-dry analysis uses all-sky routing, frozen seven-channel quality,
39 potential-temperature and 12 lower-level water-vapor controls; other state
and all parameter controls are inactive. The final component sum equals the
final closure trace. Successful logical results exclude failed attempts and
the separately evaluated baseline H; executable launches are uninstrumented.

Coverage is a max_iter=1 integration diagnostic on an invalid historical-run
checkpoint. Returned full State and final-slot QC/NC were not persisted;
physical-temperature, relative-qv and RH metrics are unavailable. Original
raw write bytes were not captured before metadata correction; the raw file
is explicitly reconstructed. Baseline driver source is not archived, so its
transition to the analysis driver cannot be independently source-diffed.
These limitations remain open. No new valid native or independent observation
case, physical acceptance or score increase follows.
