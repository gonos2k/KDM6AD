# Native QC/NC boundary trace plan

**Status: planning only.** This source audit did not change model physics, build an executable, or run the model. The three full-physics T/Q trials are complete and all three fail the fixed M0 moment/profile admission test. This note identifies what the retained evidence shows and the smallest extra trace that would locate where a witness QC/NC pair diverges.

## Pinned execution and retained evidence

All three candidate runs used the same isolated host executable and experimental library:

- WRF executable SHA-256: faf7ec5f66c89acdea20ea0cef1ca38030071020ff5ebec6f2d4b4da37291ca0
- Loaded DSO SHA-256: 8e57e5e29112ff735e4bf2e3f5fe974b9728171fcaf5f149fda4d7f137da4e63
- C API source SHA-256: 9f1780de844474de588cbe5bb174488676f69f5bf3a9db6ab864255809a1da2c
- Private ISO binding overlay SHA-256: be86f08bc9344f9a426014eea7e9202daede8a93fa2ec144c9568fd5b4a0c66b
- The separate experimental value-only symbol is kdm6_native_fp64_value_c. The operational kdm6_step_c body and default install were left unchanged.

The retained private WRF build receipt binds the running executable to a private relink with only kdm6_iso_c.o changed. It records the MP137 wrapper object SHA-256 e9898b60336a9dc22cff3798124ab7fa9fc4ac29701e673af95390a23bd68ce7 and source SHA-256 8b47bc625c6b402626e888fe02e5e380fd8557cc582c5c8db4d3be54b97550fa. Applying the existing native_trace_overlay.py MP137 insertions in memory to the current private module_mp_kdm6ad.F review copy reproduces that source hash; the active uninstrumented source file itself has a different hash. The retained archive also pins kdm6ad_native_trace.o and kdm6ad_step_control.o. The selected-column trace files prove those trace records were emitted in the executed process.

Each run launched from the original 00:00:40 restart and captured its own READY40 checkpoint. All three candidate READY40 checkpoints matched the no-analysis control READY40 bitwise across 652 serialized variables / 322,426,586 numeric values. Each one-step run finished at 00:01:00, itimestep 3, with two MP137 wrapper entries in RSL. Runtime settings were MP137, no_mp_heating=0, use_theta_m=1, use_q_diabatic=0, RRTMG LW/SW=4/4, PBL=11, LSM=2, cumulus=37, radt=20/60, one MPI rank, and one thread. Selectors were norm_actual / actual_departure.

Three relevant witness coordinates are flat 5770 (i=155,j=25,k=19), flat 14728 (i=221,j=63,k=6), and flat 21852 (i=91,j=94,k=4). The saved final checkpoints and three-trial admission audit contain their READY40, control, and candidate-output values. The full M0 support source is domain_support_maps_qmin_v5.npz, SHA-256 0ea175aa9aef7e2486f9d09d5e369dc07ed1a09bfd8adb9cf49df505e6fedbd4, bound by DOMAIN_SUMMARY_QMIN_v5.json. M0 is 377,342 supported channel cells, 53,906 for each channel 10–16.

The four native_trace.hex files are reusable only for context: each has 156 records (39 levels × four stages) at the unrelated trace column i=156,j=21, step 3. The records are MP_INPUT, MP_OUTPUT, FINISH_PRE and FINISH_POST. Hashes are:

| Run | native_trace.hex SHA-256 |
|---|---|
| No-analysis control | 1dd7d6a836ae1ef85da522e5dad1902d5c56cdfc1f37b7d546d71c97a1554127 |
| alpha=1.0 | 492da15d8d1f95044b9a191c3c828cfb8546257d69469a599270c35fb86e7e22 |
| alpha=0.50 | a869a151b544ee3731b04796fcfa390583bca457fa9b5b8868dd42414bc9c487 |
| alpha=0.25 | 01dfc4151a0f1e1537e3d9068f1358d2dda8a217f169a1a53d81dbf5c52a29bb |

Those files do not cover the three witnesses, do not record C++ FP64 output, and do not contain actual CABI dimensions or tile bounds. The final restart proves the output state but cannot localize the stage that produced it.

## Existing producer/consumer points

| Boundary | Source location and meaning |
|---|---|
| READY40 capture | harness/native_live_stepper.py:292-328 captures the host’s own restart-ready checkpoint before the solve. compare_frames compares all serialized fields. |
| Analysis preparation and ACK | harness/native_analysis_increment.py:85-145 binds the T/Q increment to the checkpoint. harness/native_live_stepper.py:378-442 reads THM_2/QVAPOR once and verifies the REAL4 state; :463-520 publishes the command and validates every ACK row. The generated hook in harness/native_step_control_overlay.py applies grid%t_2 and grid%moist(P_QV) in share/mediation_integrate.F:med_before_solve_io before solve. |
| Host pre-KDM | host/KIM-meso_v1.0/phys/module_microphysics_driver.F:2885-2925 calls kdm6ad. module_mp_kdm6ad.F:230-264 packs current host state and forcing into REAL4 TH_IN…DELZ_IN; :266-296 finite-checks and calls the C binding. |
| Experimental C++ FP64 bridge | libtorch/bridge/kdm6_c_api.cpp:362-453 receives REAL4 pointers, widens state and forcing at :423-432, then calls kdm6_step at :452. result.state_out is FP64 after that return. :455-467 checks finiteness and REAL4 representability; :469-471 converts state to REAL4 output arrays; :473-506 converts RHOG and surface increments. |
| REAL4 host writeback | module_mp_kdm6ad.F:307-323 validates TH_OUT…BG_OUT and increments; :324-345 copies REAL4 outputs back into WRF arrays. |
| Wrapper diagnostics and precipitation accumulation | module_mp_kdm6ad.F:347-418 computes re_*, reflectivity; :420-466 updates run accumulators and per-call precipitation diagnostics; :468-490 final wrapper checks. |
| Moist-physics finish | module_big_step_utilities_em.F:5682-5765 computes MP heating/QV/QC tendencies and the theta_m/diabatic fields. Existing FINISH_PRE/POST trace insertions are in harness/native_trace_overlay.py:105-144, :179-210. |
| Final checkpoint | harness/native_live_stepper.py:529-535 captures the ending checkpoint; :541-574 validates run completion, input identity, trace completeness and loaded DSO. |

The current trace overlay records MP_INPUT after REAL4 packing and before the C call, then MP_OUTPUT after C returns but before the host writeback loop. MP_INPUT has 12 state fields plus DEN/PII/P/DELZ, but omits XLAND and ncmin. MP_OUTPUT contains 12 state fields and RHOG. Both are REAL4 records, not C++ FP64 state. The V1 reader keys only on stage/step/i/k/j and rejects duplicates (harness/native_trace_records.py:75-129); it cannot distinguish repeated wrapper calls for a target.

Fortran wrapper extents are available at the producer: IM=ITE-ITS+1, KM=KTE-KTS+1, JM=JTE-JTS+1 in module_mp_kdm6ad.F:147-149, then passed with ITS:ITE/KTS:KTE/JTS:JTE at :290-296. They were not serialized by the three trial traces. Do not infer them from observation B512 blocks or the two RSL markers.

## Minimum diagnostic trace

For each of the three specified columns and all 39 levels, use a versioned opt-in trace with a distinct wrapper call index:

1. Reuse the exact READY40 checkpoint, T/Q command and strict ACK. These prove the applied input bits and the one-use full-domain binding.
2. Add a wrapper-call header before kdm6_step containing the WRF timestep, ITS/ITE, KTS/KTE, JTS/JTE, IM/KM/JM, dt, XLAND and ncmin values. Record selected MP_INPUT REAL4 state/forcing immediately before the C call.
3. In the separate value-only C API entry, record selected FP64 state/forcing after widening at lines 423-432 and selected result.state_out plus RHOG/surface increments immediately after line 452, before REAL4 conversion at :469. Use a private trace selector that maps the three global coordinates to tile-local indices; do not change the operational ABI or physics.
4. Record selected REAL4 output-buffer values and then host-array values after the module_mp_kdm6ad.F writeback loop at :324-345. Add one WRAPPER_POST record after the radius/reflectivity/surface-accumulator block at :347-466.
5. Extend FINISH_PRE/POST to the three target columns using the existing field contract. Keep the final 00:01:00 checkpoint as the downstream state.

Trace rows should include trial/alpha, model time, WRF timestep, wrapper call index, global and tile-local coordinates, tile bounds, CABI shape, stage, field, dtype, and raw bits (8 hex digits for REAL4, 16 for REAL8). Preserve the existing outputs when tracing is disabled. For an enabled run, compare pre-KDM and final/ACK data to the corresponding pinned trial inputs; log all wrapper invocations, including calls whose tile does not cover a witness.

## Current limits and execution boundary

No existing artifact provides per-witness pre-KDM or FP64 output values, so the precise stage where NC became zero is still unknown. The original three-candidate search is complete. Diagnostic replays are a separate execution stage: record their call budget, build an isolated private trace variant, and pin the overlay, C API/ISO binding, executable/DSO, original restart, runtime assets and READY/ACK. Use a paired trace-off/on replay to test noninterference; until that succeeds, do not attribute differences to the original physics. This packet contains no such new execution and does not extend the candidate search.

The existing value-only boundary gate allows diagnostic forwarding only; its block34 FP-environment capture is unavailable, so it does not certify operational REAL4 parity or deployment. Candidate RTTOV quality and cost were not computed, and no full-host adjoint or gradient claim follows from these traces.
