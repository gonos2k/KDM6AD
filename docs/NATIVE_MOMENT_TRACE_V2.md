# Native QC–NC boundary measurements, V2

This opt-in diagnostic implements the follow-up to main `a1c63630` / PR454.
The earlier [dated plan](NATIVE_QC_NC_TRACE_PLAN_20261026.md) is preserved as a
historical source. Its proposed reuse of FINISH_PRE/POST is insufficient:
QC_RATE is not QCLOUD, and neither V1 finish record contains NC.

## Actual state and call identity

The new producer reads **actual host** `moist(...,P_QC)` and
`scalar(...,P_QNC)` in `solve_em`, before and after the call to
`moist_physics_finish_em`. It does not change the finish signature or physics.
The original V1 thermodynamic trace remains separate and unchanged.

The private host build uses the saved V1-compiled wrapper source
`module_mp_kdm6ad.f90` (SHA-256
`457c9b904711397f4cbc01fbcd588c48a7739200ce50d00e30098209d220207a`) and a
fresh `solve_em.f90` preprocessed from the pinned `solve_em.F` input (SHA-256
`2e82c883af596e50bb7daa879ff8597a8c572ce03d2b14d0859629201f61c0ea`). The
V2 solve overlay is applied to that fresh translation unit. The previously
saved generated `solve_em.f90` is stale for current S15 keyword interfaces and
is not used to compile the V2 executable.

Native one-based target columns are `(155,25)`, `(221,63)` and `(91,94)`;
all 39 mass levels are recorded. The known witnesses are levels 19, 6 and 4
respectively. Raw NC coordinates remain uncertified physical number units.

Set `KDM6AD_MOMENT_TRACE_V2_DIR` only for the new isolated trace build.
Its absence disables the V2 records. The selected directory must be new for
that run; neither producer may overwrite an existing output file.

Both `host.hex` and `kernel.hex` start with:

```text
# KDM6AD_MOMENT_TRACE_V2
```

Each wrapper call emits one header in each file, including calls whose tile
does not contain a target:

```text
CALL call_id step its ite kts kte jts jte im km jm dt_hex64 ncmin_land_hex64 ncmin_sea_hex64
VAL call_id stage i k j dtype field raw_hex
```

`call_id` is a process-local ordinal starting at 1. Bounds and recorded indices
are global and one-based; `im/km/jm` are local inclusive extents, not global
upper bounds. The C++ batch index is `(i-its)*jm+(j-jts)`.
Scalar header parameters are binary64 bits; QC/NC values use 8 hex digits for
f32 and 16 for f64. Run metadata carries trial identity, timestamps and source,
input, executable and library hashes once, rather than repeating them per value.

| Stage | Owner | Value |
| --- | --- | --- |
| MP_INPUT | host/f32 | Packed REAL4 QC/NC before the C call |
| FP64_INPUT | kernel/f64 | Decoded and widened input QC/NC |
| FP64_OUTPUT | kernel/f64 | `result.state_out` before REAL4 conversion |
| MP_OUTPUT | host/f32 | Returned REAL4 output buffers |
| HOST_WRITEBACK | host/f32 | Host arrays immediately after writeback |
| WRAPPER_POST | host/f32 | Host arrays after wrapper diagnostics/accumulators |
| ZERO_OUT_PRE | host/f32 | Caller states before optional zero-out processing |
| MOMENTS_PRE | host/f32 | Caller states after zero-out, immediately before finish |
| MOMENTS_POST | host/f32 | Caller states immediately after finish |

Finish loops select each target's registered wrapper-call owner; they do not
assume the last wrapper call owns every target or that finish tile bounds equal
KDM bounds. They intersect the caller's storage K range with the owning
wrapper's native KTS/KTE: the caller has an extra top storage slot that is not
one of the 39 mass levels. Observation B512/B452 chunks do not define host tiles.

The strict reader joins the files by matching call headers, rejects duplicate
value keys and mismatched owners/dtypes, and requires every selected target,
QC/NC field, level and stage. Header-only non-target calls remain visible.
The private C context setter exists only in the separate instrumentation build;
the operational 14-symbol ABI and packed AD fields are unchanged. Scalar
extraction is confined to that explicitly value-only entry and cannot feed back
into physics.

## Execution and interpretation gate

The first diagnostic budget is four independent full-physics 40→60 s steps:
control V2-off/on and historical alpha1 V2-off/on, each from the same original
40 s restart and its READY40 boundary. "V2-off" retains the old V1 diagnostics.
No 60 s result is renamed as a new 40 s initial state.

Before attributing a boundary, compare all serialized checkpoint variable bits,
input identity and applied T/Q ACK values within each off/on pair; also check
the off replay against its historical experiment. Preserve actual tile bounds,
`mp_zero_out`/`mp_zero_out_all`, nonadiabatic settings, loaded-library identity
and every request/failure in the receipts. The forward retains full configured
physics, one MPI rank and one thread.

If alpha1 does not explain the alpha0.25-specific witness, add only that paired
off/on diagnostic, recording the separate two-step extension. Do not launch
another alpha search, alter NC/Q floors, shrink M0 or claim a new derivative
certificate. A measured QC–NC boundary is distinct from a corrected physical
policy or an accepted full-host analysis.

## Initial telemetry correction and execution accounting

The initial control off/on pair completed and reproduced the historical
checkpoint exactly. Its on stream also recorded the extra top storage slot
in three caller stages. The strict reader correctly rejected those raw rows;
neither the rows nor the validation criterion were altered. Both model runs,
the raw stream and the executed producer source are preserved.

The corrected producer uses the per-target owner K bounds above. Only its
Fortran diagnostic module was recompiled; the two larger instrumented host
objects and the same C API/physics archive were reused. An actual Fortran/C++
regression with nonzero extra storage values tests this boundary.

The corrected four-run campaign is separate from the two initial controls.
Together with the conditional alpha0.25 pair, execution accounting therefore
includes **eight** independent 40→60 s host steps. All are diagnostic replays of
the same existing inputs/proposals, not new optimization trials or a time cycle.
Full state off/on and historical comparisons are required for each corrected
pair. Storage-only APFS clones of verified byte-identical outputs preserve file
contents and hashes while avoiding repeated disk allocation; historical files
are untouched.
