# Native QNC flux trace packet — 2026-10-27

This packet preserves two valid trace-on executions: V5 control and V6
alpha0.25. Each selected run contains the raw 77-row QNC-flux V2 trace plus its
same-run upstream NC TSV and V2 host/kernel hex traces. The paired trace-off
runs are included only as noninterference comparators.

## Run accounting and noninterference

Both selected on-runs completed one 20-second host step from READY 00:00:40 to
00:01:00 / timestep 3. Each has two KDM wrapper entries, 77 raw `VAL` records,
zero RTTOV calls, and zero optimizer calls. Together with the two trace-off
comparison arms, the two noninterference pairs comprise four completed host
steps and eight KDM wrapper entries total. The V5 and V6 pair receipts report
bitwise-equal full endpoints over 652 variables / 322,426,586 numeric elements,
zero mismatches, and byte-identical ACKs. No candidate acceptance, new RTTOV
cost, or second assimilation is represented. The broader private V3+V5/V6
campaign history totals six completed host steps / twelve KDM wrapper entries:
two earlier V3 control steps plus the four V5/V6 comparison steps. Only the
four V5/V6 steps are the corrected paired comparison in this packet; the V3
on-arm reader failure is history, not a valid current V2 trace.

The source-bound result, plan, launch, and build receipts are copied with
absolute local roots redacted. Selected run results pin their V5/V6 plans; the
plans and shared build receipt pin the same V3 host executable (`9a83ad7007339a7a479c08c95c4e604c5999ca24b49338dbe452a4e139821e96`)
and runtime DSO
(`9e01047610e290db36505ad52919a9f99ad97b8fe2c2924eb8aca2cba88ad92e`). Their
original source hashes and redacted copy hashes are listed in `manifest.json`. `receipts/runtime_flags.json` records actual saved
`namelist.output` readback for both selected on-runs; the two source files have
the same SHA-256. Values include MP137, RRTMG LW/SW 4/4, surface layer 1,
surface physics 2, PBL 11, urban 1, CU 37, `NO_MP_HEATING=0`,
`USE_THETA_M=1`, `USE_Q_DIABATIC=0`, `MP_ZERO_OUT=2`, and
`MP_ZERO_OUT_ALL=0`.

## Interpretation limits

This packet is raw trace/provenance material. The source-compatible local
`PH_LOW` arithmetic replay now matches with an FMA-contraction candidate, but
the compiler instruction sequence was not observed. Captured local formula
inputs do not close a shared-face or domain conservation budget. Do not infer a
named physical cause, corrected physics, accepted candidate, RTTOV improvement,
or cycling result from these traces alone.

`history/README.md` points to the preserved V1 overlay and records pre-step and
reader failures separately. Those attempts are not counted as successful
current traces. Packet copying made no host, KDM, RTTOV, or optimizer calls.
The offline arithmetic replay reads the saved records only and is described in
`replay.py`. From the repository root run:

```sh
python3 -m harness.evidence.native_qnc_flux_2026-10-27.replay
```

It compares its deterministic output to the hash-pinned `analysis.json` and
prints `REPLAY_PASSED`; it makes zero model calls.

## Files

`manifest.json` inventories packet files and external reader/producer pins
with exact bytes and SHA-256. Raw trace files are byte copies from the named executed run; copied JSON receipts are
redacted only for absolute local paths. The V5 control pair receipt and V6
alpha0.25 pair/full-checkpoint receipts are included under `receipts/`.
`execution_sources/SOURCE_RESOLUTION.md` links both V3 overlay snapshots to
exact generated Fortran SHA/byte metadata; private host source contents are not
part of the packet.
