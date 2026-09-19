# Offline layer contributions and K-text bounds (2026-09-19)

This report packages the retained PR221 center and PR223 PSFC-bottom K files
for the seven usable channel slots 9–15.  It contracts each raw K profile with
the fixed PR221 profile tangent, `a = K v`, over the native 39 model layers.
The complete exact decimal K tokens are in
[`layer_contributions_2026-09-19.json`](layer_contributions_2026-09-19.json);
the standalone standard-library replay is
[`replay_layer_contributions.py`](../replay_layer_contributions.py).

The layer index is zero-based, ordered from model top to bottom.  Layer-center
pressure increases downward; the active fixed-tangent support is deposition
at indices 18–21 (357.248–489.702 hPa) and riming at indices 20–21
(442.177–489.702 hPa).  Each tangent stores all 39 values, sparse nonzero
entries, and an explicit `zero_layer_indices` list.  `HYDRO6` and
`HYDRO_DEFF6` are zero across all 39 layers for both processes.  The layer
centers are common to the two cases; their `p_half` interface arrays are
retained separately because the PSFC-bottom case changes the final interface.

The table gives the total across the six packed fields of the fixed-tangent
PSFC-minus-center contraction for each channel.  `bound` is the sum of the six
per-field bounds `Σ |v| q/2`, where `q` is the decimal spacing of each exact
printed K token. Both columns have units K per dimensionless process control.
For a PSFC-minus-center difference, the bounds from **both** K files are added.

| process | channel | total delta | K-text bound |
|---|---:|---:|---:|
| deposition | 9 | -3.957022644783119e-10 | 4.438172006272813e-14 |
| deposition | 10 | 1.271496466754388e-08 | 1.609158858329912e-13 |
| deposition | 11 | 7.021399918764742e-09 | 1.609158858329912e-13 |
| deposition | 12 | 1.018530888151819e-08 | 1.609158858329912e-13 |
| deposition | 13 | 4.668422033177164e-09 | 1.609158858329912e-13 |
| deposition | 14 | 2.199216442643187e-09 | 1.612564582562270e-13 |
| deposition | 15 | -2.642289290282394e-10 | 1.612564582562270e-13 |
| riming | 9 | -5.018965737644815e-14 | 1.413380536225933e-18 |
| riming | 10 | -1.047163704626597e-11 | 1.251619486551342e-17 |
| riming | 11 | -6.323102617357647e-12 | 1.251619486551342e-17 |
| riming | 12 | -9.723890824049323e-12 | 1.251619486551342e-17 |
| riming | 13 | -5.137312635743044e-12 | 1.251619486551342e-17 |
| riming | 14 | -3.319637134708804e-12 | 1.256916854225217e-17 |
| riming | 15 | -7.258169724637933e-13 | 1.256916854225217e-17 |

The largest six-field bound is `1.612564582562270e-13` for deposition and
`1.256916854225217e-17` for riming.  The replay uses Decimal token spacing and
Decimal `|v| q / 2` accumulation before publishing the decimal bound.  This is
a conditional nearest-rounding bound for the fixed-v K text representation
only.  It does not bound upstream tangent error, RTTOV arithmetic, `dK/dx`,
the full observation-cost error, or the resolution of any upper extrapolation.
The replay also uses `math.fsum` for float contractions and six-field totals so
the published JSON is stable across Python 3.10 and 3.12; this is an artifact
reduction detail and does not modify the original K source or executable.

No live RTTOV call, new finite difference, or external model/reanalysis data
was used for this artifact.  Source hashes are recorded in the JSON for the
retained `native_view_aux.json`, `psfc_bottom.json`, both K files, and the
pressure inputs.

## Replay

From the repository root:

```bash
python3 harness/replay_layer_contributions.py
```

The check validates raw token coverage, tangent zero/nonzero partitioning,
`a = K v`, each per-field bound, and the six-field per-channel totals.
