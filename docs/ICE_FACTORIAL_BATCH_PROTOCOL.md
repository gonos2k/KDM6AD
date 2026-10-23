# Ice factorial fp64 batch tool

`harness/ice_factorial_batch.cpp` is a value-only research executable
linked against one explicitly identified experimental `libkdm6.a`. It accepts
one request, calls `kdm6_fn` once for the whole `(B,L)` tensor, verifies the
input tensors were not modified, and publishes one response without replacing
an existing path. Select `raw_cap`, `norm_cap`, `raw_actual`, or `norm_actual`
with `KDM6_ICE_FACTORIAL_MODE`; the experimental archive implements that
ice-only mode. Keep the same `B` chunk size and column order for every arm.
The runtime's batched stepping may use column-wide reductions, so B=1 versus
B>1 and different chunk boundaries are separate experiment identities.

All integers and IEEE binary64 values are little-endian. Version 1 has no
padding:

| Request field | Type | Meaning |
|---|---:|---|
| magic | 8 bytes | `K6BATI1\0` |
| version, B, L | u32 each | version is 1; `1<=B<=4096`, `1<=L<=256` |
| dt, ncmin_land, ncmin_sea | f64 each | dt positive, thresholds nonnegative |
| state | f64 `[12,B,L]` | State::fields order: th,qv,qc,qr,qi,qs,qg,nccn,nc,ni,nr,bg |
| forcing | f64 `[4,B,L]` | Forcing::fields order: rho,pii,p,delz; every value positive |
| xland | f64 `[B]` | each value is 1 (land) or 2 (sea) |

The request header is 44 bytes. The response starts with `K6BATO1\0`, then
version, B, L as u32 (20-byte header), then echoes state and forcing, followed
by state_out `[12,B,L]` and precipitation `[3,B]` in total-rain, snow/ice,
graupel order. The echoed arrays and outputs are finite binary64 values.

`harness/ice_factorial_batch.py` validates and packs requests, decodes exact
response sizes, and runs a deterministic fixed-size chunk plan. Its NPZ input
keys are `state` `(12,N,L)`, `forcing` `(4,N,L)`, and `xland` `(N,)`. It writes
one request and response per chunk and emits a plan with SHA-256 hashes. It
does not create or remap model columns; the native-domain preparer owns that
input and must preserve the host's original ordering and pressure/state data.
For prepared manifests, `--dry-run --workers 10` validates the whole bundle
and records a four-arm plan without calling KDM6. An explicit `--execute`
selects one arm; `--workers` accepts 1–10 independent chunk subprocesses, with
one CPU thread per child. Chunk result records are sorted back to manifest
order. Run arms sequentially when capping total work at ten CPUs.

This executable is deliberately outside CMake production targets, the C ABI,
installation, and host dispatch. Build it as an isolated tool object against
the chosen archive, preserving that archive's source receipt and compiler
flags including `-ffp-contract=off`. Record archive/tool hashes, exact inputs,
mode, chunk size, and executed commands with each run. This transport and a
small smoke capture do not certify a full-domain run, changed-map AD, physical
conservation, RTTOV derivatives, or forecast behavior.
