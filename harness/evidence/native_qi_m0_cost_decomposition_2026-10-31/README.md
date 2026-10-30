# Where the fixed-M0 direct cost changes

This packet decomposes the [PR #483 saved direct results](../native_qi_postmicro_direct_m0_2026-10-30/README.md)
without new host, KDM, RTTOV, K, or optimizer calls. It keeps the original
53,906-profile, 377,342-channel-cell M0, observation BTs, 129 B512/tail
blocks, and declared Huber function. The three comparisons remain separate:
pilot Control minus original Control, pilot α=0.25 minus original Control, and
pilot α minus pilot Control.

## Control increase is concentrated at the east boundary

| Pilot Control − original Control, common M0 denominator | Cost contribution |
| --- | ---: |
| East edge, 10 profiles `(i,j)=(234,3..11),(234,52)` | **+0.000328402829590676** |
| Interior QNC target `(221,63)` | **+0.000003868800508032** |
| West, south, north, and four corners | 0 |
| Regrouped profile/cell total | **+0.000332271630098708** |
| Difference between separately rounded published costs | **+0.000332271630098191** |

The east ten account for **98.83565126914912%** of the regrouped increase.
All 11 changed profiles have a **positive seven-channel Huber loss change**.
Within those profiles, a few channel cells can improve while other channels
worsen; profilewise and cellwise signed gross amounts are reported separately
in `analysis.json`. The maximum Control BT change is about **5.370064 K** at
east profile `(234,52)`. BT change counts use exact float64 bits, not a
magnitude tolerance.

The private checkpoint-bound [state receipt](data/original_vs_qnc_guard_checkpoint.json)
finds only 15 `QNCLOUD` and one `RE_CLOUD` word difference between the
original and QNC-guard Control checkpoints across 652 variables and
322,426,586 numeric elements. None is at the east ten. The selected
[moment witness](data/east_cost_moment_witness.json) records QICE and QNICE
changes over 5–14 layers at each east profile under the late boundary pilot,
while the original and QNC-guard words there agree. At the interior QNC
target, the pilot does not change those moments; the earlier guard changed
`QNCLOUD` at k=6. The east cost connection follows from this state identity
and the per-profile observation operator; the full PR #483 three-state cost
alone does not isolate every QNC-guard and boundary effect. Public replay
checks the bounded receipts and source snapshots, but does not reopen the
private full checkpoints.
The field-reader pin identifies the current source; the private witness execution
did not record that reader's SHA, so this is not independent proof of its
executed version.

## α changes many profiles; comparison baseline matters

Against original Control, pilot α has **33,453** M0 profiles with lower
seven-channel loss and **14,804** with higher loss. Channel 10's domain cost
contribution increases; channels 11–16 decrease. Against *pilot* Control,
all seven channel contributions decrease. Pilot α differs in BT bits from
original Control at 48,257 M0 profiles and 337,714 channel cells. Of those
M0 cells, **5,075** exceed 0.01 K, **966** exceed 0.1 K, and **127** exceed
1 K in absolute BT change. These nested threshold exceedance counts describe scale while
retaining the separate bitwise count.

Geography uses six **disjoint** buckets: corners, four edges excluding
corners, and interior. Every contribution uses the same global 377,342-cell
denominator; no local edge mean is substituted. Per-channel/profile/region
losses are regrouped with `math.fsum`. Their displayed total differs from
subtracting the separately rounded published aggregate costs by at most
about `1.1e-15`; `analysis.json` records that roundoff gap explicitly.

## Reproduce and interpret

```bash
python3 -m harness.evidence.native_qi_m0_cost_decomposition_2026-10-31.replay
```

The replay verifies source and packet hashes, including the `native_qnc_residual_reason_producer.py`
field reader imported by the private witness exporter, then runs the parent #483 packet
replay, regenerates both decomposition files, checks each of 258 direct
receipts' selected profile indices, `nprofiles`, channel/BT coordinate,
direct/K flags, and recomputed block Huber numerator, and joins the bounded
checkpoint and moment receipts. It makes **zero model calls**. The existing
private direct execution remains the source of the saved BTs; hashes and
selected checkpoint extracts do not independently rerun it.

This is an **observation-space decomposition**, not a named-process causal
attribution or analysis acceptance. The late boundary operation still needs
its physical boundary/number-unit contract, host ice diagnostic consistency,
and JVP/VJP validation. The model checkpoint is 00:01:00 against a nominal
00:00 observation slot with unverified pixel UTC and no temporal correction.
The original RTTOV model-top/background assumptions remain in force.
