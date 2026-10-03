# C5 supported liquid state: actual BT, derivatives and output precision

The frozen input-only winner is global `(i,j)=(73,157)`, native frame 20 s. Its
[selection](REPORT_C5_coefficient_support_2026-10-03.md) and
[preparation receipt](C5_supported_preparation_receipt_2026-10-03.json) precede
radiative output. The 39 native layers remain intact, with 24 separately declared
reference layers above the model top. The single active liquid layer has Deff
7.80669453314748 µm; neither its size nor the selected coordinate was chosen from
BT residuals or finite-difference results. All new state/forcing/rho, native and
extended pressure/T/Q, cloud, surface and view inputs were independently reviewed.
The matched KO pixel is `(411,338)`, 0.711 km away, at the nominal 00:00 slot
(model time+20s). Nominal-orbit geometry and reconstructed REAL(4) P8W are explicit
assumptions, not measured ephemeris or captured host interfaces.

## A real numerical defect at the ASCII output boundary

With the existing 12-significant-digit test-driver output, the actual NC-to-BT
JVP/FD comparison failed: max-norm relative error **0.002966995584** at `h=1e-4`.
The original result and endpoints are retained as
[C5_nc_bt_12digits_result](C5_nc_bt_12digits_result_2026-10-03.json) and its
`base/plus/minus` NPZ siblings. Quality was stable and the VJP duality check matched.

Only `defn%realprec` was changed to **17** in the existing writer. This changes
emitted decimal precision, not RTTOV binary arithmetic, cloud physics, the
coefficient/hydrotable, model inputs, direction, h, tolerance or any quality gate.
Independent checks show all serialized physical input files are byte-identical
between the two runs. Every old BT endpoint and all four old cloud K fields are
exactly reproduced by rounding the new outputs to 12 significant digits. The
[execution receipt](C5_optical_execution_receipt_2026-10-03.json) pins both source
versions, engine/coefficient/hydrotable hashes, input files and output configurations.
This identifies output quantization as the cause of the observed discrepancy.

The unchanged frozen direction is `delta NC=0.01*NC`, other state and forcing
held fixed. Its native optical JVP flows through the existing dry-number builder
and is contracted with actual BT-seeded HYDRO6/7 and Deff6/7 K. The transpose
contraction supplies an independent Torch profile VJP; actual plus/minus engine
calls supply FD. [The executed source](C5_nc_bt_probe_source_2026-10-03.py)
requires exact prepared base fields, preserves output flags and uses the existing
validated packer/runner. It is an optical-state probe, **not a KDM time-step or
named-process sensitivity experiment**.

| Check | Actual 17-digit result | Frozen criterion |
| --- | ---: | ---: |
| BT-vector JVP/FD max-norm relative error | 2.07542515047e-7 | <=1e-5 |
| JVP/VJP relative duality residual | 4.46117619357e-16 | <=1e-12 |
| Nonzero tangent on radiance-supported channels | yes | required |
| BASE/plus/minus raw quality identical | yes | required |

These are vector-scale checks. WV073 has a tiny NC tangent (~1.52e-9 K) and
FD (~1.71e-9 K); a uniform per-channel relative accuracy claim would be wrong.
All channel values remain published in the [17-digit result](C5_nc_bt_17digits_result_2026-10-03.json)
and endpoint/derivative NPZ files; no weak channel was deleted to obtain PASS.

## Actual observation support and cost diagnostic

The first two channels retain quality 32768 (Delta-Eddington extinction cap);
channels10–16 have quality 0. All nine matched observed pixel quality flags are 0,
so the existing combined mask admits **7/9** channels. This is a new conditional
experiment; it does not relabel the legacy 0/9 approval campaign. The original
(71,101) gas-regression-limited result remains separately recorded.

[The matched-observation record](C5_matched_observation_diagnostic_2026-10-03.json)
uses fixed sigma 1 K and Huber delta 1 as a dimensioned diagnostic, with no fitted
bias, covariance or residual-based exclusion. Its nonempty score is 22.226371799;
NC score tangent is -0.00457751262958 and independent score FD is -0.00457751230698
(relative discrepancy 7.0475e-8) on the same frozen support. Residuals reach 7.46 K;
nonempty support and matching derivatives do not certify forecast or radiative
accuracy. `accepted_observation_cost=False` and all scientific/operational
approval flags remain false.

## Solver comparison within the installed table's actual capacity

The same immutable physical inputs were also evaluated with the separate thermal
DOM solver. Every supported DOM run has quality 0 for all nine channels and passes
the same vector JVP/FD and duality gates.

| Streams | BT-vector JVP/FD relative error | Actual status |
| --- | ---: | --- |
| 8 | 2.67190015921e-7 | PASS |
| 16 | 2.15607406311e-7 | PASS |
| 32 | 2.36078611491e-7 | PASS |
| 64 | not evaluated | rejected before radiance |

The installed hydrotable header has maxnmom 32. `rttov_check_options` rejects
nstreams>maxnmom; [the actual 64-stream error](C5_dom64_rejection_2026-10-03.txt)
is retained. No table expansion, limit override or false 64-stream success is used.
The capacity-constrained 8/16/32 sequence supplements, rather than erases, the
originally planned 16/32/64 experiment.

[The comparison](C5_dom_comparison_2026-10-03.json) reports max BT differences
8→16: 0.001993736803 K; 16→32: 0.000026388926 K. Corresponding max NC-tangent differences
are 7.18994e-6 K and 5.07762e-8 K. This is bounded angular refinement using shared
optical tables, not an independent physical truth or a certified32-stream error.

Delta-Eddington differs from DOM32 by up to 0.312639889 K in BT and 15.6243% in the
NC-tangent vector max-norm. Thus self-consistent AD/FD does not establish the
physical adequacy of the approximate solver. A scientific solver/accuracy decision
remains explicit; no production fixture or physical default was silently changed.

## Checklist scope

The discovered serialization failure and the requested input→size→actual BT/K→
independent FD→nonempty observed-support path are resolved in this bounded case.
The broader C5/S2/S11 scientific approval is **not closed**: original number-gate
calibration, general coupled qv/air-measure derivatives, independent optical
accuracy and accepted observation error/solver policy remain unresolved. The
compiled engine, table, native data and exact paths are separately attributed.
No fresh native host, MPI/restart validation, deployment or release is claimed.

Local validation: directly affected writer round-trip/count tests: 2 passed; actual
12/17-digit and DOM 8/16/32 runs as above; source/preparation and case input/output
hash checks. Required CI will be reported separately from these local executions.
