# Direct RTTOV original-M0 replay

This packet records completed direct runs and an offline arithmetic replay on
the original fixed M0. See the verification and limitations below.

`replay.py` is an offline, read-only NumPy/standard-library reader. It verifies
the original full-physics baseline NPZ SHA-256 (`c919f13c3ceb4defec42e43e0b60ad71d22d10f57a9454f6f880f98ec1bf9144`), including its original observation and M0, and reproduces its Huber delta=1 numerator and cost. It checks both packed files against independently supplied SHA-256 values, exact native flat and B512 order (129 blocks, tail included), identical observation bytes and fixed M0, and valid profile, true direct-result validity, zero direct quality and finite BT at every one of the 377,342 original M0 cells. It refuses to calculate a variant cost if either case fails. The loss uses row-ordered terms, `math.fsum` by channel then chunk, and the original fixed normalizer. The outputs compare each cost with the original baseline and alpha025 with control. The reader makes zero model calls.

Packed NPZ schema for **each** case: `flat_index` (65988,), `chunk_index` (65988,), `chunk_local_row` (65988,), `channel_id` (7,), `obs_bt_k` (65988,7), `m0_mask` boolean (65988,7), `bt_k` float64 (65988,7), `model_quality` int32 (65988,7), boolean `actual_valid_mask` (65988,7), and boolean `profile_valid` (65988,). The actual-valid mask must come from each chunk’s direct result `valid` array. Indices must be in canonical flat order, channels 10–16. Observation array dtype and bytes and the M0 must match the pinned baseline exactly. Out-of-support BT/quality may be placeholders; no cost is inferred there. The packing procedure must independently verify the 129 original completed block receipts, provenance, and original run identities; the array layout alone cannot establish that the declared direct calls were executed or that values came from them. The official packet replay checks the hash-pinned archive and producer receipts, including all 129 chunk receipts and capture hashes per case, case and checkpoint identities, and consistency of the recorded source pins. It verifies exact snapshots of the direct runner and packer; it cannot reopen every private source or RTTOV asset named in the binding.

The arithmetic reader can also be invoked separately with the pinned original baseline and recorded hashes:

```sh
python harness/evidence/native_qi_postmicro_direct_m0_2026-10-30/replay.py \
  --baseline PATH --control PATH --control-sha256 SHA256 \
  --alpha025 PATH --alpha025-sha256 SHA256
```

The host pilot measures a full boundary intervention's effect on the host state; a direct RTTOV cost difference on fixed M0 measures a separate observation-space outcome. Neither alone attributes change to a named KDM process, proves physical conservation, establishes a derivative, nor demonstrates forecast skill. The model checkpoint is at **2025-07-19 00:01:00** while the KO observation bundle has a nominal **00:00** slot; individual pixel UTC is unverified and no temporal correction is applied. Native model centers and derived interfaces are retained with the declared fixed clear upper prefix and RTTOV background/model-top assumptions of the [original observation baseline](../native_full_physics_observation_2026-10-25/README.md). See [source resolution](SOURCE_RESOLUTION.md) for the executed path and limits.

## Completed saved direct runs and offline verification

The completed packet contains the original-M0 direct results for control and
alpha025, each with 129 saved chunk captures. Run:

```sh
python harness/evidence/native_qi_postmicro_direct_m0_2026-10-30/packet_replay.py
```

This verifies the pinned manifest and artifact hashes, the exact 778-file
archive inventory, chunk receipt bindings, call counts, capture hashes and
ranges, and bytewise agreement of captured arrays with the two packed files.
It then runs the separate arithmetic replay and checks the published analysis.
It makes no model calls. `data/chunk_artifacts.tar.gz` contains the exact saved
binding, summary, attempt, result, and capture files; those JSON receipts retain
local private path strings for provenance. It does not contain the raw RTTOV
case directories, private checkpoints, or executable. The source-tree digest is
a snapshot recorded during execution, not a complete public source archive;
hashes and receipts are evidence of recorded provenance, not independent proof
of execution. The private packer checked SHA-256 of 61 compact call archives; the other 197 completed raw call directories were checked for presence but their entire contents were not individually hashed in this packet. Private workspaces remain necessary for a deeper audit. Exact direct runner, packer, and chunk exporter source snapshots are in `executed_sources/`.

On the unchanged original 377,342-cell support, the declared Huber costs are:

| Same observation and M0 | Cost | Difference from original control |
| --- | ---: | ---: |
| Original control baseline | 11.007963317242059 | 0 |
| QNC-guard + boundary-pilot control | 11.008295588872157 | +0.000332271630098191 |
| QNC-guard + boundary-pilot α=0.25 | 11.007331464977474 | −0.000631852264584509 |

The pilot α-minus-pilot control difference is **−0.0009641238946827002**.
This is a fixed-support observation diagnostic for the full host boundary
intervention, not an analysis acceptance decision, named-process attribution,
or forecast-skill result.

The separately replayed [BT diagnostics](observation_diagnostics.json) show
that, relative to the original control, pilot control changes 11 M0 profiles
(77 channel cells), while pilot α changes 48,257 profiles (337,714 channel
cells). These are **exact float64 bitwise differences with no magnitude
threshold**. At the repaired ice-boundary profile `(i,j)=(1,168)`, IR105 BT is
**295.086844603 K** in all three valid states. The pre-pilot α profile was
hard-invalid and had no direct BT, so these values do not measure a controlled
before/after BT effect of its `2u→0` QI correction.
At the prior QNC target `(221,63)`, the
three IR105 BT values are **285.822573426 / 286.148468954 / 285.822483468 K**
for original control / pilot control / pilot α. The pilot α change from the
original control there is about −0.000090 K; the 0.326 K pilot-control to
pilot-α gap has a different comparison baseline. The domain-wide cost change
cannot be attributed to one boundary ice cell or one named KDM process.

The checkpoint-to-RTTOV builder recomputes its ice optical inputs from the
candidate QI/NI and does not consume the saved host `RE_ICE` or `REFL_10CM`.
The late boundary overwrite can leave an earlier host ice-radius diagnostic
inconsistent with the new moments; this direct cost does not certify those
host diagnostics, physical moment units, or an applied mass/number budget.
