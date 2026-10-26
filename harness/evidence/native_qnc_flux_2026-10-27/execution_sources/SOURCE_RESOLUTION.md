# V3 executed overlay source resolution

The V5 control and V6 alpha0.25 plans both pin the same V3 host executable
(`9a83ad7007339a7a479c08c95c4e604c5999ca24b49338dbe452a4e139821e96`), runtime
DSO (`9e01047610e290db36505ad52919a9f99ad97b8fe2c2924eb8aca2cba88ad92e`), and
build receipt (`fe17d37f9beecce107ed56debd5ce67aafca058faa31b32a75aa9bdb6d716a01`).

The exact private `native_qnc_flux_advect_overlay.py` snapshot used for that
build is retained here as
[`native_qnc_flux_advect_overlay_pr457_v3.py.txt`](native_qnc_flux_advect_overlay_pr457_v3.py.txt),
SHA-256 `8f8fc66dba4d7cfbb72e8198e77dee5cafbd85814524b84c365883c11e01192b`.
A later formatting-only Ruff cleanup changed the current public overlay bytes
to SHA-256 `d3390212e9a37e208d6b25a9d4322ecaa7541a9c1fd47aa9fa4c3aa0cdf74027`;
its generated Fortran source remains byte-identical to the executed overlay
output, SHA-256 `72403b4bb9ac713ec20f06a1ff362c44302bcae32c69d5c5f8769d457975d1b5`.
This records source resolution; it does not substitute the later overlay bytes
for the executed snapshot.

The context instrumentation is resolved the same way. The exact V3
`native_qnc_flux_context_overlay.py` snapshot is retained as
[`native_qnc_flux_context_overlay_pr457_v3.py.txt`](native_qnc_flux_context_overlay_pr457_v3.py.txt),
SHA-256 `09506bea263af4e5dea58f178f16e9a62018c05549a7f38eb4b2bb581f84d4ad`.
The generated/compiled host Fortran outputs are private and are not copied into
this public packet. Their output identities are retained as metadata only:
`module_em.f90` is 120,524 bytes with SHA-256
`cc0352105f196ac17deb00e4e5b0ef1a0f18d08d9572bd77046441406ad06c3d`;
`module_advect_em.f90` is 377,540 bytes with SHA-256
`72403b4bb9ac713ec20f06a1ff362c44302bcae32c69d5c5f8769d457975d1b5`. The
public packet keeps the two source overlay scripts, the exact executed Python
overlay snapshots and these generated-output hashes/byte counts; it does not
publish generated host source contents.
