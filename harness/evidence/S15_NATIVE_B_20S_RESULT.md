# S15 owner-scoped B result: first 20 seconds

Status: **OPEN**. This package records a bounded owner-5 capture and its same-executable control/capture check. It does not establish a QIB transition cause, select a graupel policy, or certify host AD.

## Result

The isolated B executable was linked from the pinned r6 owner-scoped objects against the untouched S8 archive. Its SHA-256 is `d20e716a5e27c88782f9e60d628e4b53f33939664e255d2a9d85c9336d8ec953`. The first link attempt failed because `SDKROOT` was unset; the retry set it to the path returned by `xcrun --show-sdk-path`. The retry changed no source, object, or archive hashes.

The B discovery run completed the 20-second LC05 case on one MPI rank and one thread. The saved forecast times are `2025-07-19_00:00:00` and `2025-07-19_00:00:20`. All six predeclared owner-5 summary rows are present, with zero QIB sign transitions and no first-event rows. The discovery stream contains 51 trace-melt witnesses with unique `(step, latitude row, substep)` keys. All 51 pass applicable gate, mass, and temperature checks. Every row has `rhox_valid=0`; the measured `brs1` values remain untrusted, and **zero actual valid-rhox volume updates were validated**. A constructed valid-rhox row and mutation test exercise the verifier only.

The later logging-off control and logging-on capture used the same B executable and the same retained LC05 inputs. At both saved frame indices 0 and 1, the forecast output's 253 populated numeric variables and exact `Times` pass strict raw-bit comparison. The energy output's four populated numeric variables and `Times` also pass at both frames. The prcp and ocean outputs have zero saved frames and no populated numeric variables, so they provide no parity result. The confirmation event stream is byte-identical to the frozen discovery stream and passes its external-plan replay.

The QIB owner-5 first-transition gate remains open. The zero count is a null witness for this first-timestep window; it does not resolve the negative-QIB attribution question.

## A capture correction

The earlier A discovery emitted six `P_QIB` rows from generic scalar call sites without an owner field. `P_QIB` is an array index reused by other scalar arrays. Those rows are invalid as owner-5 QIB evidence and are excluded from the B reference plan, count, and event keys.

## Reviewable artifacts

The public packet is **PUBLIC_REDACTED**. Its path-normalized projections and
manifest are under `s15_b20_public/`:

- `s15_native_B_20S_public_manifest.json` — SHA-256 `02e7cfc7b0c0362f496eedad6705abeaa2b76c42808dd92092de5b0ac8580276`.
- `s15_native_compile_receipt_2026-09-26_r6_public.json` — projection SHA-256 `f8c05d592215721253e899a51dc69fd09b872b10eea803496be7ca686550aa8c`; original local receipt SHA-256 `67183b38e001a5137159778823c4b5032d475b72d9cbf05d572fca16cbfecf3b`.
- `s15_native_owner_schedule_2026-09-26_public.json` — projection SHA-256 `aee5d350572c3753f0d6caf2f6671a4be45005edb3c7f8d15d04411b5bd53da8`; original local schedule SHA-256 `34d671cefcbad485a3d3ccf276e91c60933cce86394485574080dbcd1e58cf8c`.
- `s15_native_discovery_b_event_reference_2026-09-26_public.json` — projection SHA-256 `4e04d743f89ea33057f5adcb65701abee33899c8d8c6283addba0e4fc765c034`; original local reference SHA-256 `b28204f00124d5f4e7358e9f0e554c75b541acdf1113526f6ccc0907d869078b`.

The manifest lists the original SHA-256 values for those three required
dependencies and the path-bearing r10 plan/link/run receipts. The original
records remain **LOCAL_VERIFIED** in ignored local evidence; public projections
are redacted summaries, not executable plans or receipts, and their SHA values
must not replace the original run-chain pins. The packet includes run/build/input
identity metadata, hashes, bounded event keys, and aggregate counts. It contains
no raw field arrays, full-domain NetCDF, private host source, objects, or
executables.

## Next bounded window

The current overlay captures timestep 1 only. A step-2 investigation needs its
own source-pinned plan, overlay, compile, disassembly audit, link, and review.
That work is tracked separately; this package contains no step-2 plan, build,
link, or run.

## Review checklist

- Confirm the six step-1 summary keys are source-declared owner 5 × three RK stages × two retained tiles.
- Confirm the A alias rows are excluded and the B QIB count is reported as zero.
- Confirm the 51 melt rows are keyed per latitude row and substep and pass applicable gate/mass/temperature replay; all `brs1` volume updates remain untrusted because `rhox_valid=0`.
- Confirm the strict comparison claim is limited to populated forecast and energy outputs; prcp/ocean are explicitly insufficient.
- Keep the QIB attribution gate open and review the step-2 plan separately before any new build or launch.
