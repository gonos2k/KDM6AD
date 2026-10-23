# Executed native-domain ice-only 2×2 comparison — 2026-10-23

All four arms completed **129 chunks and 65,988 native columns each**: 516
actual KDM calls, plus four pilot calls. Each call uses dt=20 s, 39 levels,
fp64, ncmin land/sea 10/10. The input is the existing MP137 00:00:40 endpoint
packet. There are **zero new full-host steps, DA trials or RTTOV calls**.

The P3 preparation metadata has also been corrected: both representative
producer fields now identify the final packet generator (`2e144050…`). Prior
hashes are retained in `producer_history`, with origin/phase labels. The packet
itself has not changed. Earlier preparation reports keep their historical
zero-domain-call status; this report supplies the subsequent execution record.

## Pilot and full-grid execution

The B=512 pilot selected the packet with the largest column condensed-water
inventory (chunk 38). This is a stress proxy, not proof of worst runtime.
All four pilot outputs were finite, with no negative water; observed wall times
were 0.272–0.284 s and single-child RSS 211–216 MB (decimal).

The full-grid partition is 128 chunks of 512 and one of 452. Four arms run in
sequence, with ten workers per arm and one numerical thread per worker.

| Mode | First-ice handoff | Arrival | Completed calls | Observed wall s | Peak single-child RSS bytes |
| --- | --- | --- | ---: | ---: | ---: |
| raw_cap | raw vt | Legacy cap | 129 | 5.4966 | 235061248 |
| norm_cap | vt/DELZ | Legacy cap | 129 | 22.4629 | 225427456 |
| raw_actual | raw vt | actual departure | 129 | 23.4043 | 224395264 |
| norm_actual | vt/DELZ | actual departure | 129 | 24.0447 | 224935936 |

Wall time includes admission, file I/O and process startup. These single-run
observations are not a controlled performance benchmark and do not establish
that one physical rule causes the time difference. RSS is the maximum of a
single child, not total simultaneous worker memory. All outputs were finite;
none of the twelve raw output rows was negative. Minimum dry theta was
290.5816264612215 K in each arm.

An initial coordinate validation incorrectly assumed NX=282 and refused the
packet **before any KDM call**. It was corrected to NX=234, with independent
234-column boundary and transposed-map rejection tests. The first completed
arm's time logs initially parsed RSS as null because of multiple spaces. All
129 original logs were reparsed and receipts annotated; no physics call was
repeated. Final runner parsing rejects missing measurements. The final runner
source, used for the three later arms, is preserved under `execution_sources/`;
current source only reformats it and renames a local dimension variable. The
first raw_cap arm used the earlier resource-parser revision, whose full source
hash was not separately frozen at run start. This limits controller-source
attribution for that arm; its model binary and all numerical inputs/outputs
remain pinned and independently checked. Per-arm elapsed values were recorded
by the surrounding orchestration, not emitted by the archived runner.

## Column diagnostics

Means below are unweighted over columns. Water units are kg/m² **per column**,
using that request's DEN×DELZ; these are not physical regional mass totals.
The residual is raw six-species state change plus reported total precipitation.

| Mode | Mean raw residual | Minimum raw residual | Columns outside numerical diagnostic gate | Mean offline H_RATE, K/s |
| --- | ---: | ---: | ---: | ---: |
| raw_cap | −6.442165398203281e−4 | −0.4135621359742411 | 32694 | −2.361984202698115e−5 |
| norm_cap | −1.087424322205230e−4 | −0.1817715693076842 | 7234 | −2.765132088069557e−5 |
| raw_actual | −1.087379838929069e−4 | −0.1817715693076840 | 5360 | −2.154958654487831e−5 |
| norm_actual | −1.087424322205230e−4 | −0.1817715693076842 | 7234 | −2.765132088069557e−5 |

The changed arms reduce this mean diagnostic deficit. **Physical water closure
is not certified in any arm.** Remaining deficits cannot be assigned to an
internal process from these endpoint records alone. Raw-flux dimensions and
historical number payload units remain conditional. The main sedimentation
chain stays Legacy. The gate is a rounded-arithmetic diagnostic, not a new
physical acceptance tolerance.

The mean reported total precipitation is 0.0001534297287909016 mm in each arm.
It is not bit-identical per column: normalized arms differ from baseline in 72
columns, maximum 4.679402771259485e−16 mm; raw_actual differs in 10 columns,
maximum 2.407412430484045e−35 mm. Snow/ice and graupel are subsets of the total.

Offline uniform interior cleanup changes the mean water inventory by
−2.291604004041577e−7 (raw_cap), −6.941457539116812e−7 (norm_cap/norm_actual),
and −3.456214403087416e−7 kg/m² (raw_actual). These are kept separate from
kernel changes and precipitation, with no invented vapor/latent compensation.
H_RATE is dry-mass averaged within each column and then spatially unweighted.
The maximum pointwise H_RATE difference from baseline is 0.011275405554395842
K/s for normalized arms and 0.005827177370452721 K/s for raw_actual. These are
moist-theta memory differences, not BT changes or measured RK consumption.

Normalized-cap and normalized-actual have identical stored offline finish
profiles, but their water diagnostics are not bit-identical: maximum raw
residual difference is 1.734723475976807e−18 kg/m². Equal rounded summary
statistics do not establish an identical kernel map or derivatives.

## Provenance and replay

- Base public source: main `3323f01525b8e4834a82809f8d02e574da622916`.
- Final packet manifest: `24630a58b03e54d90cc4bb6c6167e0571b02d2d002095424b19789286914601d`.
- Admitted experimental executable: `b8051d8b8c983dd91e98c98204d900b27da39054eceeb282d4f9e0025cf894e7`.
- Its previously attributed isolated archive: `0bf2c94d30d66ba5a76767ae526ee5ea89d944a8cc242f95255b20a23bdb8b3a`.
- Saved endpoint: `7a353f1fa4f6636864ac169c9ee8d16869d1f38c8e998762c19659404cbb9c8e`.
- Final runner (three later arms): `298b1f8d8b742e44d47393fbd1f6475ec54d9b1727b465b73e28f86006e5277b`.

The existing isolated build receipt in the
[earlier campaign](../ice_factorial_batch_smoke_2026-10-23/build_receipt.json)
records compilation/linkage; this campaign reuses that exact executable and
checks its bytes before/after every subprocess. Operational f32 sources,
installed library and host executable are unchanged. The previously paused DA
processes remain stopped.

`chunk_receipts.json` binds every request/response, mode, source chunk, range
and resource result. Four `*.columns.npz` archives expose every column's scalar
metrics for public statistics/gate replay. `selected_columns.npz` contains five
post-hoc slices (grid endpoints, baseline residual extrema, largest normalized
H change) from actual batch responses, with raw input/output/forcing and finish
values. They are not new B=1 evaluations. The full binary streams and full
finish profiles remain private. The final analysis was rerun after validation
and formatting changes, reusing the same responses and adding **zero KDM calls**.

## Scope and next decision

The first-ice alternatives have value evidence across this fixed packet and
partition. They have no new JVP/VJP/FD certificate. No candidate is adopted;
the next scientific choice is which alternate map to certify locally before
any native deployment. Existing Legacy AD/RTTOV and two-step carry milestones
are not reopened. No full RK adjoint, number migration, map-area water budget,
observation timing alignment, whole-domain DA or forecast improvement is claimed.

Validation and Green/Red findings are recorded in `validation.json`. See the
[contract](../../../docs/NATIVE_DOMAIN_ICE_FACTORIAL.md) for measurement and
unit assumptions. Graph coverage remains public-source plus semantic links;
private host AST coverage is unavailable.
