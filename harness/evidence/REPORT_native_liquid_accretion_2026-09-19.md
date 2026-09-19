# Native liquid accretion liveRTTOV evidence — 2026-09-19

This report records the fixed native candidate 35711 (`j=152`, `i=143`), forecast `time_idx=1`, and the `accretion` process. It contains five completed RTTOV endpoints after two preserved failed attempts. No new calls were made while publishing this report.

The result is diagnostic-only. The nine collocated clean IR inputs (0-based channels 7–15) all receive RTTOV `rad_quality=32768`, bit 15 `qflag_delta_edd_ext_limits`; the retained mask is empty. Therefore `J=0` is an empty QC-mask result and does not validate the cost or its FD.

## Execution and provenance

| item | value |
|---|---|
| Candidate | flat 35711; `j=152`, `i=143`; accretion; forecast `time_idx=1`; reader `as_stored` |
| Native profile | 39 layers / 40 half-levels; exact `P/P_HALF`; source SHA-256 `30ee8656cedf57cc827ad041e4ed8084d8bbf5afdbe0a21b28b33564544bca9f` |
| Calls | 2 failed baseline attempts preserved; 5 completed endpoints under `graphify-out/pr224-liquid/live/actual-live-control-cases-9dc0rsrq` |
| Runtime | Python 3.10.11; NumPy 2.2.6; Torch 2.13.0 |
| Source selection | `selection_result_fallback_t001.json` SHA-256 `041d0676bafdb3d88a25bdde61b3a649ddf4a85739a8f51dd3b67c0e67cc82ed`; candidate metadata `f4bfa7ea4e3e3549875ed96232461c0aa2a0fc506244282b2836b0122879301c`; offline gate `78d253a6dfdc6fc19d87799558a39d82ad2967b44d80fd9d961b8849a6551487` |

Applied native geometry is latitude 38.51930618286133, longitude 127.565673828125, elevation 0.5965975341796875 km; view zenith/azimuth 44.592985352568284°/178.92321194526843° and solar zenith/azimuth 49.30700974446031°/94.87327996043538°. The scene anchor and solar auxiliary hashes are recorded in the JSON.

The time contract is model input `00:00:20`, KDM `dt=20 s`, post-KDM state label `00:00:40`, GK2A nominal slot `00:00:00`, and RTTOV auxiliary datetime `00:00:20`. Scene-anchor timing is separate; this is not claimed as exact KO pixel-time collocation.

Land uses `surftype=0`, `watertype=0`, actual skin/near-surface fields, Q2 dry-to-moist conversion, and fixed land IR emissivity 0.98. Fixture salinity/foam/snow/fastem/wind-fetch values remain assumptions, not measured land emissivity.

## Five endpoint BT/QC records

| endpoint | raw BT tokens (16 channels) | RTTOV quality (16) | retained mask (16) |
|---|---|---|---|
| `baseline` | `0.000000000000E+00 0.000000000000E+00 0.000000000000E+00 0.000000000000E+00 0.000000000000E+00 0.000000000000E+00 0.278858690708E+03 0.233091143304E+03 0.240781984698E+03 0.249521428891E+03 0.265148476050E+03 0.241532667861E+03 0.266122612058E+03 0.265354209476E+03 0.264003861704E+03 0.256233594021E+03` | `[0, 0, 0, 0, 0, 0, 32768, 32768, 32768, 32768, 32768, 32768, 32768, 32768, 32768, 32768]` | `[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]` |
| `alpha_minus_0.03` | `0.000000000000E+00 0.000000000000E+00 0.000000000000E+00 0.000000000000E+00 0.000000000000E+00 0.000000000000E+00 0.278858694567E+03 0.233091143304E+03 0.240781984701E+03 0.249521428905E+03 0.265148475818E+03 0.241532667773E+03 0.266122599895E+03 0.265354201300E+03 0.264003861671E+03 0.256233593993E+03` | `[0, 0, 0, 0, 0, 0, 32768, 32768, 32768, 32768, 32768, 32768, 32768, 32768, 32768, 32768]` | `[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]` |
| `alpha_plus_0.03` | `0.000000000000E+00 0.000000000000E+00 0.000000000000E+00 0.000000000000E+00 0.000000000000E+00 0.000000000000E+00 0.278858686731E+03 0.233091143304E+03 0.240781984696E+03 0.249521428877E+03 0.265148476288E+03 0.241532667951E+03 0.266122624595E+03 0.265354217903E+03 0.264003861738E+03 0.256233594050E+03` | `[0, 0, 0, 0, 0, 0, 32768, 32768, 32768, 32768, 32768, 32768, 32768, 32768, 32768, 32768]` | `[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]` |
| `alpha_minus_0.1` | `0.000000000000E+00 0.000000000000E+00 0.000000000000E+00 0.000000000000E+00 0.000000000000E+00 0.000000000000E+00 0.278858703128E+03 0.233091143304E+03 0.240781984707E+03 0.249521428937E+03 0.265148475306E+03 0.241532667579E+03 0.266122572907E+03 0.265354183161E+03 0.264003861598E+03 0.256233593930E+03` | `[0, 0, 0, 0, 0, 0, 32768, 32768, 32768, 32768, 32768, 32768, 32768, 32768, 32768, 32768]` | `[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]` |
| `alpha_plus_0.1` | `0.000000000000E+00 0.000000000000E+00 0.000000000000E+00 0.000000000000E+00 0.000000000000E+00 0.000000000000E+00 0.278858676967E+03 0.233091143304E+03 0.240781984689E+03 0.249521428841E+03 0.265148476872E+03 0.241532668173E+03 0.266122655372E+03 0.265354238589E+03 0.264003861821E+03 0.256233594122E+03` | `[0, 0, 0, 0, 0, 0, 32768, 32768, 32768, 32768, 32768, 32768, 32768, 32768, 32768, 32768]` | `[0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]` |

## Channels 7–15: diagnostic channel derivatives

Values are K per unit alpha. JVP/VJP are raw channel diagnostics; central FD uses the two live ±epsilon endpoints. Observed inputs are marked clean by the collocator but excluded by RTTOV quality. The E21.12 `1e-9 K` text bound is diagnostic-only.

| ch (0-based) | observed BT K | JVP | VJP | FD ε=.03 | FD ε=.1 | rad_quality | mask |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 7 | 231.050445339 | -2.894433519487036e-10 | -2.894433519487038e-10 | 0 | 0 | 32768 | 0 |
| 8 | 241.131730868 | -9.094608847783987e-08 | -9.094608847783985e-08 | -8.33333994402589e-08 | -8.999990086522303e-08 | 32768 | 0 |
| 9 | 245.394408553 | -4.767509236020603e-07 | -4.767509236020644e-07 | -4.666664684312612e-07 | -4.800000397153781e-07 | 32768 | 0 |
| 10 | 250.040921363 | 7.818157251901029e-06 | 7.818157251900993e-06 | 7.833332915652136e-06 | 7.829999901787232e-06 | 32768 | 0 |
| 11 | 240.762559432 | 2.967215971862512e-06 | 2.967215971862492e-06 | 2.966667030553557e-06 | 2.969999997048944e-06 | 32768 | 0 |
| 12 | 250.885185865 | 0.0004116182184302976 | 0.0004116182184302977 | 0.0004116666663852205 | 0.0004123249999565815 | 32768 | 0 |
| 13 | 252.600513981 | 0.0002766647795928008 | 0.0002766647795928008 | 0.0002767166667657269 | 0.0002771399999801361 | 32768 | 0 |
| 14 | 251.850793067 | 1.109768794076312e-06 | 1.109768794076302e-06 | 1.116667173543344e-06 | 1.114999861329125e-06 | 32768 | 0 |
| 15 | 247.048411123 | 9.573214671518027e-07 | 9.573214671517987e-07 | 9.500003746628257e-07 | 9.600000794307562e-07 | 32768 | 0 |

The maximum absolute JVP/VJP difference over these nine channels is `5.421010862427522e-20`; this does not promote the result because every observed channel is QC-excluded and the scalar cost mask is empty.

## Failure history

The first baseline failed because the copied fixture simple-cloud deck supplied `ctp=949 hPa`, exceeding the native bottom half-level pressure (~942.45 hPa). The second fresh attempt preserved the same rejection because RTTOV’s test driver independently reads the hard-coded `simple_cloud.txt` when present, even with `f_simple_cloud=`. The final local wrapper blanks the field and removes only the copied template file; all five completed cases assert the file is absent. No pressure clamp, solver change, clear-sky reclassification, QC relaxation, candidate switch, or extra call was used.

Compact JSON: [native_liquid_accretion_2026-09-19.json](native_liquid_accretion_2026-09-19.json)
Full local report and raw case paths remain under `/Users/yhlee/KDM6AD-audit-pr205/graphify-out/pr224-liquid/live`.

The local RTTOV `rttov_eddington_setup.F90` sets bit 15 when a
channel/layer extinction exceeds `max_ext_delta_edd=20`, then clips it.
This is a solver-quality limitation; it does not establish a pressure-top,
gas, or number-unit cause. The raw derivative agreement does not remove
this quality exclusion.

Independent Decimal recomputation directly from the displayed BT tokens gives
15/18 observed 5% comparisons and 13/18 satisfying
`abs(AD-FD) + 1e-9/(2*epsilon) <= 0.05*abs(AD)`. Both WV063
(index 7) differences are zero and fail; WV069 (index 8) at .03 also fails
observed agreement. The text-aware condition additionally fails WV069 at .1
and WV073 (index 9) at .03. These counts describe raw QC-excluded diagnostics,
not accepted observation validation. The table above retains the original
binary-float FD values; Decimal replay avoids that extra conversion rounding.
