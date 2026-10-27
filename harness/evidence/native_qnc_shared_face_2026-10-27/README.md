# Native QNC seven-cell shared-face trace — 2026-10-27

This packet adds a bounded measurement to the [PR457 target-cell trace](../native_qnc_flux_2026-10-27/README.md).
The native one-based witness is `(i,j,k)=(221,63,6)`; array order in Fortran
and the trace is `(i,k,j)=(221,6,63)`. Control and the earlier rejected
alpha0.25 T/Q candidate each ran one independent trace-off and trace-on
**full-domain MP137 host step** from READY 00:00:40 to 00:01:00 on
`234×282` native columns and 39 mass levels.

## Execution and noninterference

The four steps completed on one MPI rank and one thread with two host tiles.
Each case's trace-off/on final checkpoints have the same SHA-256 and compare
raw-bit equal for **652 variables and 322,426,586 numeric values**, with
identical applied-control ACK bytes. Control and alpha0.25 are different
inputs and are not asserted equal to each other. Each new endpoint also equals
its corresponding historical PR457 endpoint. The alpha0.25 run applied the
same **117,172** T/Q grid-level pairs (170,749 components) as before; it is
not a new accepted analysis.

The trace-on case records one 147-value seven-cell group in its owned tile,
plus call headers for both tiles. Each trace-on host/KDM V2 file records two
wrapper entries. Runtime readback confirms `SCALAR_ADV_OPT=1` (the
`advect_scalar_pd` path), RK order 3, horizontal/vertical scalar orders 5/3,
`NUMTILES=2`, MP137, `NO_MP_HEATING=0`, RRTMG LW/SW 4/4, PBL11, CU37,
and `USE_Q_DIABATIC=0`. The full forward was not made adiabatic for this test.
Four host steps were executed; this packet's offline replay makes zero host,
KDM, RTTOV or optimizer calls. [Producer/build hashes](SOURCE_RESOLUTION.md)
and [execution receipts](receipts/execution_summary.json) distinguish those
two kinds of work. Storage-only APFS clones replaced this campaign's own
closed files after byte/hash comparison with identical historical files; the
original checkpoints and traces were not modified.

## Measured shared faces

At the **post-limiter, pre-divergence** boundary, the target and each of its
six face neighbors independently record the correction (`fqx/fqy/fqz`) and
low-order (`fqxl/fqyl/fqzl`) face words. For each case, **all six pairs match
bitwise in both components**. The seven cells also record their cumulative
RK3 Z→X→Y `ADVECT_TEND`; all **21 stage values** match either a source-grouped
binary32 separate-operation replay or a corresponding outer-FMA arithmetic
candidate. The actual emitted instruction sequence is not claimed. The
target's new face/tendency words match the same run's PR457 V2 trace and final
upstream `ADVECT_TEND` bits.

| Target-cell final RK3 QNC, legacy raw coordinate | Control | Alpha0.25 |
| --- | ---: | ---: |
| KDM input before its NC clamp | +3.442540646 | −3.814399242 |

The negative candidate input and positive QC still leave the earlier
alpha0.25 candidate inadmissible on the fixed observation support. No
candidate RTTOV cost or second assimilation was calculated here.

`fqx/fqy/fqz` are correction fluxes; **the low-order face term is separate**.
Equal face words do not imply equal-and-opposite raw cell tendencies: the
two cells use their own map factors and the other faces in their divergence.
The seven-cell star has six internal target–neighbor faces and **30 external
perimeter face incidences**. Those outer consumers and the domain boundary
budget were not measured, so neither physical particle-number units nor
whole-domain conservation is certified. The result measures the applied
shared-face and local tendency path, not an admissible repair.

## Offline reproduction

From the repository root:

```sh
python3 -m harness.evidence.native_qnc_shared_face_2026-10-27.replay
```

It checks every packet file's byte count/SHA-256 and the current reader and
overlay sources, then regenerates [analysis.json](analysis.json) byte for
byte. The printed `REPLAY_PASSED` result has zero model calls. The earlier
PR457 packet remains immutable. The raw files here are the *new same-run*
copies; their QNC flux/upstream/KDM boundary bytes happen to match the prior
packet exactly, and the new run receipts pin that equality.
