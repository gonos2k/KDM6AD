# Native-input f32 activation boundary through the C ABI (2026-11-11)

This packet tests the standard **float32 `kdm6_step_c`** path on the saved native `(203,149)` column, 39 levels and 20-second call. The 12 state and four forcing arrays in the [parent input](../native_pre2_input_cpp_ad_2026-11-08/raw/input.bin) contain 624 f64 storage values, all of which are exact widenings of f32 words. The experiment uses those words directly with `im=jme=1`, `kme=39`, `xland=2` and `ncmin_land=ncmin_sea=10`. Experimental ice-factorial, QR-transport and QNC-guard environment overrides are unset.

This is a **single-column, value-only C ABI experiment**. It is not an observed call from the WRF host tile, a test of `mp_physics=37` versus 137, or an f32 AD result. The host may choose a different batch-wide substep schedule. The earlier [f64 activation packet](../native_activation_operands_cpp_ad_2026-11-10/README.md) supplies the search location, but its adjacent f64 input words and derivatives are not transferred to f32.

## Executed reference and capture

The selected baseline is called through the installed operational DSO and a separately built test-only DSO with `KDM6_NATIVE_SCALAR_CAPTURE=ON`. For the same input, the installed call, private capture-off call and capture-on call agree in raw f32 bits for **468 state outputs, three precipitation increments and 39 RHOG values**. Their input words and ABI controls also agree. The test-only build uses the previously published instrumented coordinator, which retains the actual live activation operands, and its captured target-layer row is f32 at `runtime_call=1, substep=0, k_zero=23` (native level 16). A first standalone runner attempt failed at `dlopen` before any ABI call because its Torch RPATH was missing; the repaired runner and both attempts are recorded separately.

The boundary sweep records **36 axis/word samples**: 13 along initial TH16 and 23 along initial QV16. They represent **35 distinct full-state inputs** because the baseline appears on both axes; the replay requires those two records to agree in every operand, mask and output word. Every sample keeps its represented f32 input word, the target activation operands and masks, and all 468+3+39 output words. The four *distinct* terminal endpoints were each rerun through the installed DSO and the capture DSO with capture off/on; all three outputs agree in raw bits at each endpoint. Complete scalar-capture CSVs are retained, compressed, for the baseline and four endpoints, and the replay links their selected-layer records to the compact events. These endpoint comparisons do not make the other sampled events independent host captures.

## Observed adjacent-f32 transitions

For both axes, bisections of `sw_percent >= 0.48` and the observed `activated_fraction >= 1` end at the same adjacent f32 input-word pair. TH16 is **potential temperature**. Physical temperature is the separately rounded f32 product `TH16*PII16`; at the baseline it is `274.6803283691406 K`, while the f64 product is `274.6803185248609 K`.

| Axis | Adjacent input words, lower / upper | Represented input gap | Fraction-side relation | Final NC16 upper − lower |
| --- | --- | ---: | --- | ---: |
| TH16 | `439ff9f0` / `439ff9f1` | `3.0517578125e−5 K` | `1` / `<1` | `−8,528` (**533 output f32 ULP**) |
| QV16 | `3befdf4f` / `3befdf50` | `4.656612873077393e−10` | `<1` / `1` | `+1,200` (**75 output f32 ULP**) |

The TH lower/upper `sw_percent` values are `0.4802107811 / 0.4799723625`, and the actual pre-minimum pow operands are `1.0002634525 / 0.9999654293`. The QV lower/upper values are `0.4799962044 / 0.4800081253`, with pow operands `0.9999952912 / 1.0000101328`. Thus these observed fraction-one endpoints have **strict `pow>1` value comparisons**. At those endpoints the separate activation-rate operands are tied at `5,000,000`; on the fraction-below-one sides, the raw rates (`4,999,561` for TH and `4,999,940` for QV) are below the same cap. A value tie is not a test of the minimum's tie derivative rule.

The sweep checks strict input-word ordering, sampled monotonicity and f32 source-order arithmetic for supersaturation, ratio, activation numerator, rate cap, both minimum outputs, the positive-supersaturation gate and the selected NC/NCCN updates. Every saved `nc_final` and `nccn_final` stage word must match its final state output word, including nonterminal samples. The independently evaluated `math.pow` is a **4-f32-ULP diagnostic**; the actual C++ pow operand and its handoff into the minimum are captured as raw f32 words. All 36 saved samples match the independent pow calculation in this environment, but the diagnostic allowance is retained for other math libraries. Adjacent f32 words at the recorded transitions do not prove global uniqueness, mathematical continuity, or a derivative at the discrete boundary. The final NC differences are finite changes of this f32 map and are reported with output-word resolution. No f32 JVP/VJP is inferred from them.

The recorded `cloud_complete_evap` mask is an input to the checked downstream NC/NCCN arithmetic. Its production from upstream cloud state is not independently reconstructed by this packet.

## Provenance and limits

The [manifest](manifest.json) pins the baseline calls, 36-event sweep, 12 terminal call JSONs, compressed scalar captures, runner/producer sources, executed `ops.cpp` and C ABI snapshots, flags, caches and receipts. Public replay recomputes input exactness, raw output equality, terminal-to-sweep links, branch predicates, represented gaps, finite values and recorded source-order relationships. It does **not** rebuild the private capture DSO or execute the WRF host. The two DSO hashes are cross-checked **between saved receipts**; the unavailable binary bytes cannot be hashed by public replay. Observed installed/capture output equality is limited to baseline and four terminal endpoints. Operational full-tile parity, physical mass/number/volume budgets, host AD and GK2A–RTTOV cost sensitivity remain open. `scientific_status` and `physical_unit_status` remain `INCONCLUSIVE`.

Run `python -m unittest discover -s harness/evidence/native_f32_activation_boundary_2026-11-11 -v` and repeat with `PYTHONOPTIMIZE=1 python -O`.
