# Shared-face producer source resolution

Both trace-on cases used one private executable, SHA-256
`effbecc59a3d6471f86c75259f27d54bb80826de7f327cdac16c930fadac031b`.
Its runtime KDM DSO is the unchanged PR457 V3 library, SHA-256
`9e01047610e290db36505ad52919a9f99ad97b8fe2c2924eb8aca2cba88ad92e`.
The private build receipt has SHA-256
`d59c9bee9509f36bed27f88a35d328c3fe2feef090dd398c5a382b8355aaa596`.

The [public overlay producer](../../native_qnc_shared_face_overlay.py) has
SHA-256 `74c591eecaa7e47a06491b6a5dc80caffc19155500a354054465e3a1bf6f0e72`.
It requires the executed PR457 V3 `module_advect_em.f90` input SHA-256
`72403b4bb9ac713ec20f06a1ff362c44302bcae32c69d5c5f8769d457975d1b5`.
The newly generated/compiled private Fortran source SHA-256 is
`234e39590fe2b864df8c1e038014e502cd0db662ebf2578dea41a60141dd09ec`.
The new `module_advect_em.o` SHA-256 is
`f0be3cf5cdb1d09a631f5fa262b8b181420277e06538b41cf2dc520172cb801d`.
Only that archive member changed from the PR457 V3 host. The private archive
SHA-256 is `240c5a78ef602162fbb7eb141c10094bd421aab8b4dd91d48a9475ae03f75115`.
The `module_em.o` context setter and the compiled FP64 KDM bridge are unchanged.
The original generic dynamics compiler command was preserved; the private
build made zero model/RTTOV calls.

The shared-trace header's `model_step_arg` is the source routine's Fortran
`time_step` argument, measured as **20 seconds**. It is **not** the model
`itimestep=3`; that value is checked from the same-run upstream trace and
00:01:00 checkpoint. Two tile call headers have an owner flag and actual
tile/domain bounds. The seven-cell star is fully inside the first tile;
the second tile logs a non-owner header only.

Private generated Fortran, archives, executable, DSO and checkpoints are not
published. The executable and producer relationship is documented by the
private source/build receipts and their hashes, and the public packet carries
the exact raw trace and redacted run summaries.
