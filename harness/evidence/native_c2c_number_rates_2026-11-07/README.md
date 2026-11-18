# C2c snow/graupel number-riming producer replay (2026-11-07)

This packet continues the [NC rate-producer and limiter trace](../native_nc_rate_producer_2026-11-07/README.md) on the same saved `(203,149)` native-state column, 39 levels and 20-second f64 C ABI value call. It uses the baseline and joint QG17+BRS17 relative `±10^-3` endpoints. Each of the **three** inputs was run with capture off and on through a new isolated DSO. There is no new private host, RTTOV or AD execution.

## Producer arithmetic and capture provenance

Thirty value-only calls record the operands and actual parameter values passed to `cold::cloud_water_riming_torch` for its C2c snow and graupel number rates. Removing those calls restores the #550 coordinator byte for byte. The executed `cold.cpp` and `cold.h` snapshots match the public production source byte for byte; runtime and CMake sources match #550. Source, object/archive/DSO, flags, input, logs and output are linked by SHA-256 receipts. Private object/archive/DSO bytes are not distributed, so public CI checks the archived values and receipts rather than rebuilding that private binary.

The scalar replay reconstructs the **f64 path** in the executed source order:

- `qc_safe=max(QC,qcrmin)`, the snow/graupel Wilt ratios `QS/qc_safe` and `QG/qc_safe`, and the NaN-ignoring clamp to `[0,1]` followed by a square. The recorded ratios are finite, so this replay does not exercise the NaN branch.
- The snow prefactor's **stepwise f32 multiplication** of the captured f32 π, `avts`, `0.25` and `eacsc`, promoted to f64 before the mass/number and slope chain. The graupel chain starts with the executed f64 π constant.
- Each raw number-riming rate, its separate `min(raw,NC/dtcld)` cap, then the strict species gate `QS(or QG)>qcrmin AND NC>ncmin`.

The reconstructed returned `nsacw` and `ngacw` match the independent C2c return capture preserved in #550 by **raw f64 bits in all 3×39=117 level-calls**. Newly captured QS/QG, NC and per-cell `ncmin` also match the separate #550 weighting, B2 and limiter inputs. The #550 replay then checks the `nsacw`/`ngacw` weighted `naacw` producer, both NC limiter passes and the #549 consumer. This is a source-order arithmetic replay of observed values, not a second physical model.

The executed call's fixed C2c parameters and time step are also checked as f64 words against the source/default-record values, including `qcrmin=10^-9`, `qsum_floor=10^-15` and the promoted f32 `g3pbs` and π values. This catches a rehashed threshold change even when the observed gate and output do not change. The per-cell `ncmin` is checked against #550's separate limiter capture.

## Selected native layer and branch coverage

At native level 16 (`k_zero=23`), both endpoints pass the snow and graupel strict gates. Neither individual `NC/dt` cap is active; the cap is `9235842.971817337` in both endpoints.

| Value | Joint negative endpoint | Joint positive endpoint |
| --- | ---: | ---: |
| Raw and returned `nsacw` | `520914.7557322119` | same |
| Raw and returned `ngacw` | `324.6523727175901` | `326.3849455793129` |
| Snow Wilt factor | `0.9714102310981363` | same |
| Graupel Wilt factor | `0.005864724785212811` | `0.005886431000744751` |
| C2c input QG | `4.1773620988021945e-5` | `4.185085477148888e-5` |

At native level 16, the recorded C2c inputs that change between endpoints are `QG`, `avtg`, `g3pbg`, `rslope3_g` and `rslopeb_g`. The third graupel slope input, `rslopemu_g`, is raw-equal to `1.0` at all 39 levels in all three recorded calls. The snow operands used by this number-rate chain remain equal at native level 16. This identifies the changed inputs consumed by the graupel formula, **without assigning a counterfactual causal share to each input**. A constant returned `nsacw` is not evidence of a zero derivative in an arbitrary direction.

Across each 39-level call, the snow and graupel gates are each active at six levels. Neither species has a cap-active gated level in these records. Gate ties, an active cap, negative/NaN operands and operational f32's raw Wilt-division path therefore remain untested by this packet. Separate caps do not establish a combined NC number budget.

## Noninterference and validation boundary

Capture-off/on `state`, `forcing`, `xland` and `output` arrays are raw-equal in every case and raw-equal to #550. Each new CSV has **17,667 rows**; removing the 30 new fields ×39 levels restores the ordered **16,497 parent rows**, including datatype and raw words. The default CLI hashes every new asset and recursively runs the parent verifier. Rehashed test overrides reject changed snow-prefix, graupel-slope, gate threshold, Wilt denominator, datatype and signed endpoint claim. Coordinated edits of all mutually dependent captured operands can still be arithmetically self-consistent; original asset hashes and execution provenance are distinct checks.

The physical QNICE/NCCN number-unit contract, upstream production of the changed graupel slopes/`avtg`/`g3pbg`, process JVP/VJP, operational f32 and GK2A–RTTOV cost sensitivity remain outside this value-only packet. `scientific_status` and `physical_unit_status` remain `INCONCLUSIVE`.

Run `python -m unittest discover -s harness/evidence/native_c2c_number_rates_2026-11-07 -v` and repeat with `PYTHONOPTIMIZE=1 python -O`.
