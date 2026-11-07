# NC rate producers and cloud-number limiter on a captured native column (2026-11-07)

This packet extends [the applied NC budget trace](../native_nc_budget_terms_2026-11-07/README.md) for the same `(203,149)` native-state column, 39 levels and 20-second f64 C ABI value call. The selected direction is the joint QG17+BRS17 relative `±10^-3` perturbation. Baseline and both endpoints were re-executed with capture off and on: **three paired value cases**, no new private host/RTTOV or AD execution.

## Captured producer and limiter path

The new source adds **44 value-only capture calls** to the #549 coordinator. Removing them restores the published #549 coordinator byte for byte; runtime and CMake sources are unchanged. New rows record:

- `nracw`: the B2 accretion function's consumed NC/NR/QR, drop-size and slope operands, runtime parameter values and returned rate;
- `naacw`: the C2c riming function's returned `nsacw`/`ngacw`, QS/QG weights, floor and returned weighted rate;
- cold and warm cloud-number limiter gates, NC/reservoir floor, ordered source sums, the relevant pre-limiter operands and the two rates before and after each limiter.

The public replay recomputes the B2 large/small-drop formulas, selected drop branch, rain gate and `NC/dt` cap; the C2c weighted formula and qsum gate; and both cloud-number limiter sums, factors and applied stores. It uses the executed f64 operation order. The **`nsacw` and `ngacw` returned rates are inputs to the C2c weighted-formula replay**: this packet does not independently reconstruct their own raw rate, Wilt-factor, individual cap or gate producers. All captured operands and stage outputs are pinned with SHA-256 in the default CLI.

For **3×39=117 level-calls**, each selected producer output, limiter sum, pre/post-limiter rate and #549 `state_update` consumer rate matches the scalar replay by raw f64 bits. In these calls the cold and warm cloud-number limiters do not reduce either rate. Each case has 23 cold-gated and 16 warm-gated levels, but **zero levels with a cloud-number scale factor below one**. At native level 16, the cold gate is off and the warm gate is on with factor exactly one. Captured source×20 is about 30.6 million against an NC reservoir of about 184.7 million, leaving a wide no-scale margin in this selected cell.

| Native 16 value | Joint negative endpoint | Joint positive endpoint |
| --- | ---: | ---: |
| Produced/applied `nracw` | `562055.7607829178` | `562066.0296393145` |
| Produced/applied `naacw` | `483381.1401947831` | `483316.88254621363` |
| `ngacw` input to weighted producer | `324.6523727175901` | `326.3849455793129` |
| QS weight | `0.0005376252287222719` | same |
| QG weight | `4.1773620988021945e-5` | `4.185085477148888e-5` |
| Warm NC-limiter source×20 | `30637116.027020358` | `30634751.09793784` |
| Warm NC-limiter factor | `1` | `1` |

Both selected endpoints use the **large-drop** B2 branch, pass the rain gate and remain below the individual `NC/dt` cap. The C2c qsum gate is active. `nsacw` is raw-equal across these two endpoints while QG and `ngacw` differ. These observations locate the `nracw` and weighted `naacw` differences in their producer calculations before the cloud-number limiter. They do **not** isolate the causal contribution of each B2 input, explain the upstream `ngacw` producer, or establish a physical particle-number budget.

## Preservation and validation boundary

Capture-off/on `state`, `forcing`, `xland` and `output` arrays are raw-equal in every case and raw-equal to the corresponding #549 arrays. Each new capture has **16,497 rows**; removing the 44 fields × 39 levels leaves the parent **14,781 rows** in order, datatype and raw words. The replay executes the #549 verifier before checking this packet, verifies all captured call IDs/vertical indices, source/build/run receipt hashes and `-ffp-contract=off`, then compares every producer→cold limiter→warm limiter→#549 consumer handoff. The private DSO/archive/object bytes remain outside the public packet; the public verifier checks their source and hash records, and does not rebuild or rerun the private DSO.

Test overrides with updated hashes reject changed formula operands, limiter source/gate, final rate and endpoint claims. A coordinated rewrite of *all* captures and operands could remain internally consistent, so the arithmetic replay is not a general authenticity proof; the default CLI pins the original asset hashes. Selected f64 value paths and inactive limiter factors do not certify limiter-boundary derivatives, upstream `nsacw`/`ngacw` production, process JVP/VJP, operational f32, QNICE/NCCN physical units or GK2A–RTTOV cost sensitivity. `scientific_status` and `physical_unit_status` remain `INCONCLUSIVE`.

Run `python -m unittest discover -s harness/evidence/native_nc_rate_producer_2026-11-07 -v` and repeat with `PYTHONOPTIMIZE=1 python -O`.
