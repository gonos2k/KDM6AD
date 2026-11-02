# Native QNICE applied-change capture contract

**Purpose.** Explain the NI change from host ingress through sedimentation and the C3 input in one native 39-level column. The existing two-cell packet shows only net intervals: level 21 rises by `40.58969401890777` from ingress to post-sedimentation step entry, while level 23 falls by `171.66587587805407`. Equal step-entry and C3-input values in those cells do not identify every intervening operation. This contract specifies the records required for an applied numerical ledger; it is **not a completed capture or a physical number budget**.

## Identity and input boundary

Use the current 5 km native column `(164,242)` and all 39 model levels. Select the actual call by `(model time, time step, MPI rank, tile bounds, one_step_call, runtime_call, substep, B, K, native i,j,k)`, not by matching values alone. Record the executable, its resolved loaded DSO, linked object/archive, preprocessed host source, public and diagnostic C++ source, compile/link flags, input checkpoint, namelist and required asset hashes. The same instrumented binary and DSO must be used for capture-off and capture-on runs. Require raw-bit equality of their complete endpoints, and keep both endpoints with their receipts. The earlier C5 executable has a different hash from the present canonical `wrf.exe`; a new relink must be treated as a **new build**, even if it reproduces the old endpoint.

Filter the selected column and call **before** allocating or serializing per-stage data. Define and enforce a maximum row count and byte count from 39 levels, the observed substep schedule and the declared stage inventory; reject overflow, short writes and extra rows. Keep this capture in a separate opt-in file/schema so the historical 312-row C5 packet and exporter stay byte-identical. Verify that the existing paired-run exporter still accepts its expected capture-off/on receipts and unchanged C5 capture inventory, and emits the unchanged legacy packet schema.

Immediately after `moist_physics_prep_em` and before `microphysics_driver`, capture f32 AL, ALB, RHO, QV and QNICE for the selected column with the full call identity. At the actual mp137 wrapper, capture QV_CURR, QNI_CURR and DEN before packing, then their ABI words. Recompute f32 `1/(AL+ALB)` using source order and compare with same-call RHO/DEN. The saved `00:01:00` AL/ALB from the prior packet are a **later endpoint** and cannot be substituted here; `calc_p_rho_phi` executes after microphysics.

## Ordered NI inventory

Store the actual f32/f64 word and branch or limiter decision at each named boundary. The required inventory is:

| Interval | Capture from the executed path |
| --- | --- |
| Ingress | Host/ABI NI, C++ widened NI, pre/post `[0,1e6]` entry clamp, QI, QV, DEN and operation dtype. The two published NI inputs are inside that clamp, but the full column and neighboring contributions still require measurement. |
| Sedimentation | Full 39-level NI before/after **each executed ice substep**; top and interior candidate flux, actual departure and arrival after their independent caps, floor correction, prior and updated fall accumulator, `dz`, consumed density, velocity, `dtcld`, mstep, activation gate and top/bottom boundary flux. Retain the top-first sedimentation ↔ native bottom-first index map. Record reslope/number rewrites and dtype conversions occurring inside the chain. |
| Step entry → C3 | NI before/after D1 melt, homogeneous freezing, ice number snap A, each D2/D3 (and relevant D4) applied number store, snap B, and final dtype conversion. Include QI, DEN, lambda/threshold and selected masks so equal endpoint values cannot hide compensating changes. |
| C3 onward | Link the existing same-call C3/C4/C5, conservation limiter, state update and final DSD records by the same identity. Keep selected rate and actual applied amount distinct. |

The legacy ice sedimentation operator can cap departure and arrival differently. `fall_ni` is a cumulative diagnostic and may round without changing even when a candidate is nonzero. Therefore neither a candidate fall amount nor the accumulator increment may replace the **applied** departure/arrival records. The record count must equal the observed substep schedule for every selected level; reject missing, duplicate, reordered or differently identified rows.

## Replays and budgets

First replay each state update in its executed dtype and operation order. For each layer and substep, compare the retained before/after NI bits with the independently reconstructed applied departure, arrival, floor correction and rewrite; report a signed arithmetic residual. Sum the *actual applied* interface mismatches and top/bottom terms over the full column, with explicit layer thickness and the chosen numerical coordinate. Report nonzero interface differences rather than declaring conservation from a small closure residual. A physical inventory such as `Σ N_v Δz` or `Σ ρ_d n_d Δz` requires the original QNICE basis to be independently admitted. Keep host transport/restart production and kernel process changes as separate ledgers.

Use synthetic nonunit-density and unequal-depth two/three-layer tests with active arrival and departure caps, top/bottom flux, mstep gates and a number rewrite before native execution. Mutation tests must reject altered raw bits, wrong level orientation, swapped tile/time/call, omitted rows and mismatched source/build pins. Capture-on and capture-off forward outputs must be compared within the **same variant** in raw bits. This capture does not certify a JVP/VJP; later derivative tests need represented endpoint directions and fixed branch signatures.

## Execution preflight

As reviewed on 2026-11-02, free space on the shared `/private/tmp` and canonical-host volume was about **13 GiB after removing only our clean, previously pushed temporary worktrees**. The prior C5 off/on retained runs occupy `3.9 GiB` each. The runner copies output artifacts during a case, so the peak for a new isolated build and two retained runs has not been measured and may exceed free space. Do not launch the pair until a fresh-case dry run or disk budget proves enough headroom for both full outputs, captures and system operation. Keep the private host source/build in an isolated copy without the 80 GiB historical `test/` and 6.4 GiB `run/` trees; audit symlinks and ensure build and runtime resolve the intended isolated DSO. The host `./configure` path requires `./apply_kdm6ad_config.sh` before compiling. Existing operational binaries and libraries must not be overwritten.

The [current numerical and later-endpoint evidence](../harness/evidence/native_qnice_prec3_2026-11-02/README.md) remains `physical_unit_status: INCONCLUSIVE` until these execution and producer/restart records are available.
