# FP environment and saved Q65 review follow-up

Base main: `1c077608e8728bad3a53a868483dbd5916eec214`.
This packet changes verification only. No new host, KDM, RTTOV or optimizer
calls were made. It neither accepts a full-host candidate nor changes any
historical derivative verdict or tolerance.

## FP environment predicate

The earlier predicate accepted missing FPCR information if no field explicitly
reported a bad value. It also read the redundant `fpcr_round_to_nearest` field,
which is absent from the direct-runtime reference loader. The revised predicate
requires positive evidence from that loader's actual fields:

- FE round-to-nearest is true;
- raw FPCR was available;
- `fpcr_rounding_mode_bits` is integer zero;
- float32 FZ bit24 is false.

An optional contradictory nearest flag or failed/malformed roundtrip probe also
refuses compatibility. Missing environment evidence does not erase saved numeric
comparisons; it prevents `half_ulp_bound_validated` from becoming true.
This checks rounding controls, not restoration of exception-status flags.

The 23 focused tests exercise missing/unknown controls, real reference headers,
alternate rounding/FZ settings and contradictory probe evidence. Six related
test modules pass 151 tests locally. Existing published block40 and nonsquare B8
environment snapshots still pass; block34's missing capture remains unconfirmed.
The original H1 manifest and runtime receipts are unchanged. Its old verifier
and tests are byte-preserved through the [source resolver](../native_full_physics_forward_2026-10-25/historical_source_resolution.json).

## Original requested-direction Q65 resolution

Run from the repository root; the replay writes JSON only to stdout:

```sh
python3 harness/evidence/fp_environment_review_2026-10-26/block22_q65_resolution.py
```

The [saved result](block22_q65_resolution.json) binds the original packet's
input/plan/lineage manifests, baseline/JVP and all epsilon endpoint arrays.
The target is block22 row368, native flat11632. The affected Q coordinate is
RTTOV one-based layer65, corresponding to native **one-based mass level2** in
this column. It is not the previously analyzed activation layer18.

At epsilon 1e-6, the local binary64 spacing is 3.637978807091713e-12 ppmv.
The measured endpoint difference is 74 ULP, whereas the saved tangent implies
72.33640535545564 ULP. The observed coordinate tolerance ratio is 215.5597;
even the nearest possible gap (72 ULP) yields 43.8733, above the frozen limit1.
This also affects epsilon1e-5, but Q65 passes at epsilon1e-3 and 1e-2.
It is a resolution diagnostic for this coordinate, not a new common33 pass.

Using saved post-finish native qv and its tangent, an independent 80-digit
Decimal calculation of

\[
Q=10^6\frac{a q}{1+a q},\qquad
\dot Q=10^6\frac{a}{(1+a q)^2}\dot q
\]

agrees with the saved Q tangent to relative 1.32e-16. It checks this conversion
and coordinate connection; the upstream KDM tangent itself remains a supplied
input. The later **effective binary32-native direction C4** is a different
campaign and its failures remain open.

Root reran this replay and obtained a byte-identical JSON result. Root also
reran the public full-domain baseline arithmetic: 65,988 columns, 377,342 fixed
support cells, `J=11.007963317242059`. These are offline calculations, not new
model calls or a candidate improvement.

See the [current checklist](../../../docs/NATIVE_ANALYSIS_REVIEW_CHECKLIST_20261026.md)
for the unresolved QC–NC boundary trace, general runner wiring, cumulative
optimization and second analysis. No arbitrary number/Q floor or support
reduction was introduced.
