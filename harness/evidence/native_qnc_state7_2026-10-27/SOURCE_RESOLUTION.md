# Native seven-cell QNC state-trace source resolution

Both trace-on runs used one private host executable, SHA-256
`c623581aef8f7e0e560687cc658cc58d78038a8312118df8bf10e2f557e39a73`.
The runtime KDM DSO is unchanged from PR459, SHA-256
`9e01047610e290db36505ad52919a9f99ad97b8fe2c2924eb8aca2cba88ad92e`.
The private successful build receipt SHA-256 is
`184ba4b4fb0483d60e920d55daa6ea4f0915fe7bc0b62104191e13b4eeccb8b4`.
Only the archive member `solve_em.o` changed; the private archive SHA-256 is
`995aa9e71e3fc477ef9d3137e3a82387a15b11f81952d89f22b891fa361e042b`.

The [public trace overlay](../../native_qnc_state7_overlay.py), SHA-256
`c90896238d63c74f5c7865174255d0b8b5f976d35e3004712d2a5e9871de17f3`,
requires the **saved executed V4 generated** `solve_em.f90` input SHA-256
`a10a2aae453f1d0fcaa96d288d235db0087df3c6a28a4d4035e39f53790c8f71`.
It produces the private compiled output SHA-256
`0842aafdd2ba4fb252fe8dc58f18043d691a818b9fc092ee533c693f4574f85d`;
the new `solve_em.o` SHA-256 is
`7977811f1c1ff84b6835d50dc556cc87fac373bea608ca6caf66b66c6cbd04c2`.
The PR459 `module_advect_em.o`, PR457 `module_em.o`, FP64 KDM bridge and
nonadiabatic host inputs remain as pinned in the base executable. Generic
dynamics compiler flags and numerical update expressions were retained.

The first isolated preflight compile lacked the existing
`kdm6ad_moment_trace_v2.mod` search directory and failed before creating an
object. The successful second preflight supplied both the PR457 and V4 module
directories, compiled this exact source, and preceded the new private link.
No model/RTTOV call was made during either compile preflight or linking.

The public packet carries raw records and hashes, **not** private generated
Fortran, objects, archive, executable, DSO or checkpoint payloads. The
current active private host source is not substituted for this saved executed
source; full source-to-binary inspection requires the canonical private
research tree and its receipts.
