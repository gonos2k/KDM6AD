# Post-freeze pre2 graupel producers consumed by C2c (2026-11-07)

This packet connects [the C2c number-rate input capture](../native_c2c_number_rates_2026-11-07/README.md) to the **post-D2–D4 `rebuild_aux` preamble (`pre2`)**, rather than to the earlier post-D1 `pre1`. It re-executes the saved `(203,149)` native-state column (39 levels, 20 seconds) at baseline and joint QG17+BRS17 relative `±10^-3` endpoints. Each of the three f64 C ABI value calls runs capture off/on. This is not a new private host/RTTOV or C++ AD execution.

## Executed stage and preservation

Twenty-four value-only captures record QG/BRS before and after D2–D4; the state and forcing supplied to `pre2`; its merged ProgB density/BRS, `pidn0g`, `avtg`, `bvtg`, `g3pbg` and slope parameters; and QG/BRS received by the later C2c call. Removing the 24 capture calls recovers the #551 coordinator byte for byte. The executed ProgB source retains #535's earlier **capture-only** block and matches that published source snapshot byte for byte; slope source and headers match tracked production source. The additional C++ captures do not replace the private DSO/archive/object provenance recorded by SHA-256.

Each of the three on captures has **18,603 rows**. Removing the 24 new fields ×39 levels leaves all **17,667** #551 parent rows in their original order, datatype and raw words. Capture-off/on `state`, `forcing`, `xland` and `output` arrays are raw-equal, and each is raw-equal to the parent endpoint. Public replay first verifies the #551 packet, then source/build/run receipts and every new producer-to-consumer row.

## Value and branch replay

For all **3×39=117** level-calls, the prior postmelt QG and BRS reslope stores are raw-equal to the D2–D4 input; D2–D4's QG/BRS output equals the actual `pre2` input by raw f64 bits. `pre2` QG, returned BRS, `avtg`, `g3pbg`, `rslope3_g`, `rslopeb_g` and `rslopemu_g` are raw-equal to the later C2c-consumed values. `pre2`'s density input is also raw-equal to C2c's recorded density. The separate `progb_active` and `qg<=qcrmin` slope-mask bits are checked from the captured inputs. Across the three calls, ProgB is active in **eight levels per call** and the graupel slope is unmasked in **seven**; the inactive persistent ProgB histories are forwarded by raw words but are not reconstructed from their earlier producers here.

On the active ProgB branch, an independent scalar replay computes `QG/max(BRS,10^-15)`, density clamp `[100,900]`, returned BRS, and the executed 9-node, right-search interpolation for `avtg` and `bvtg`. These match the C++ capture by raw f64 bits in **24 active level-calls**. The active, unmasked graupel slope's reciprocal `exp(log(ratio)·0.25)`, square, cube and `rslopeb_g=pow(rslope_g,bvtg)` match by raw bits in the observed local environment for **21 level-calls**. The public verifier allows up to eight ULP for the independent Python slope transcendental calculations across environments while keeping all C++ producer-to-C2c handoffs raw-exact. `pidn0g` has a four-ULP portable scalar bound (local maximum one ULP), and `g3pbg=exp(lgamma(3+bvtg))` has a **16-ULP** portable bound (local maximum seven ULP); those are independent arithmetic checks, not replacements for the raw C++ handoff. A rehashed one-ULP `pidn0g` override can pass this portable arithmetic check if the selected slope outputs round identically; the default CLI still pins the original capture bytes. `rslopemu_g` is raw f64 `1.0` in all 117 recorded cells.

At native level 16, D2–D4 leaves QG and BRS raw-unchanged in all three calls. The pre2 ProgB density remains on the **interior 800–900 table segment**: `899.9209558196019` at the negative endpoint and `899.9209090320801` at the positive endpoint, leaving about `0.079` to the 900 upper cap. The post-freeze pre2 values consumed by C2c are:

| Pre2/C2c value | Joint negative endpoint | Joint positive endpoint |
| --- | ---: | ---: |
| QG | `4.1773620988021945e-5` | `4.185085477148888e-5` |
| BRS after pre2 ProgB | `4.641921128503633e-8` | `4.650503655538133e-8` |
| `avtg` | `146.03613667901004` | `146.03613309003282` |
| `g3pbg` | `3.419674557361348` | `3.419674558784236` |
| `rslope3_g` | `1.1894592732106105e-11` | `1.1911083009331149e-11` |
| `rslopeb_g` | `0.012169441099154838` | `0.0121723963551336` |

This identifies the **post-freeze producer and exact C2c handoff** for the five changed native-16 inputs. It does not isolate which earlier transport, D1 or other state update caused the joint QG/BRS change. Nor does an endpoint difference certify a local JVP/VJP. Both sides of this selected finite change remain on the recorded interior ProgB and unmasked slope branches; other runtime branches may exist.

## Validation boundary

The default CLI pins source, producer, build/run receipt and raw assets with SHA-256. Rehashed test overrides reject wrong postmelt→D2–D4→pre2 forwarding, ProgB/slope branch bits, a changed slope producer word and a false endpoint step. Coordinated rewrites of mutually dependent test inputs can remain arithmetically self-consistent, while the original manifest still fixes the archived bytes. The selected f64 replay does not certify a full host Jacobian, process JVP/VJP, active density caps, retained inactive diagnostics, operational f32, physical QNICE/BRS number units or GK2A–RTTOV cost sensitivity. `scientific_status` and `physical_unit_status` remain `INCONCLUSIVE`.

Run `python -m unittest discover -s harness/evidence/native_c2c_pre2_upstream_2026-11-07 -v` and repeat with `PYTHONOPTIMIZE=1 python -O`.
