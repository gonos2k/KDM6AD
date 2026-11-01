# Native one-call C3/C4 and final DSD evidence

This packet retains the selected raw words from an **executed mp137 host step** at the native column `(164,242)`, one-based levels 21 and 23. The 20 s, one-MPI-rank, one-thread run starts at `2025-07-19 00:00:40` and ends at `00:01:00`. The initial restart, namelist and 79 external input assets passed their historical SHA-256 pins. The historical executable alone reproduced the retained endpoint. A separate diagnostic DSO was built from the pinned historical factorial/actual-QR physics archive with only runtime, coordinator and bridge objects replaced for capture. Its capture-off **and capture-on** full-domain endpoints both have the same SHA-256 as the historical endpoint: `950bc5d67dc8cf4980091ecac19a9b7b1ba94756e83d9bd101180e55863c0bb6`.

The WRF run has two physical tiles. The selected second tile has local `I=2..233`, `J=143..281`, and 39 levels, yielding tensor shape `B=32248`, `K=39`; native `(164,242)` maps to zero-based batch `22617` and native levels 21/23 to zero-based K `20/22`. This mapping was checked independently: the host's selected-column `MP_INPUT` f32 words for QI, NI, P and DEN match the C ABI ingress words at both levels, and six host QI/P/DEN values across two levels identify batch 22617 uniquely among all captured converted-ingress columns. Host `MP_OUTPUT` QI and NI words match the f32 writeback of the C++ final DSD output.

The [selected packet](selected_packet.json) preserves 172 selected scalar rows with dtype and raw IEEE bits, `dtcld`, the two selected host input/output trace records, the build receipt, and hashes for both complete C++ captures, both host traces, the inputs, executable, DSO and endpoints. [The verifier](verify_packet.py) hashes the exact packet bytes before parsing, checks the local executed-overlay source snapshots, enforces call-and-level stage inventory, compares raw input/output words, and independently replays the C3 ice-nucleation and C4 ice deposition candidates from the consumed operands. The full private captures, checkpoint, executable, input assets and archive are pinned but not redistributed, so their hashes are execution attestations rather than independently downloadable artifacts.

| Native level | C3 outer/inner result | Selected C3 mass rate `pinud` | Selected C4 ice rate `pidep` | Final DSD NI change |
| ---: | --- | ---: | ---: | --- |
| 21 | Outer cold/ice-saturation gate false | `0` | `−8.782281178665383e−12` | None; slope interior |
| 23 | Cold/ice-saturation and target-deficit gates true | `+8.164876727089497e−10` | `+1.0855819230719068e−8` | None; slope interior |

At level 21 the consumed C3 ice supersaturation is `−1.6577494779991542e−5`, so C3 does not produce ice despite its target number exceeding the consumed NI. C4 is active, and its negative raw rate wins the signed maximum among the raw rate, QI floor, half-saturation and remaining-supply candidates. At level 23 C3 consumes supersaturation `+3.9893618392460766e−5`, NI `116548.15443662195` and target number `119803.02648287981`. The target-number deficit produces the smallest C3 mass-rate candidate. The positive C4 raw rate is below both supply caps, so it is selected unchanged. The selected C3/C4 rates equal the captured pre-conservation and limited values in these two cells.

The state update changes level-23 QI from `6.436784183017238e−7` to `8.57046273367234e−7` and NI from `116548.15443662195` to `119786.63415268344` in the C++ f64 working coordinate. Reclassification, saturation adjustment and cleanup occur before final DSD; QI and NI are bit-identical at the two captured endpoints of that interval in these selected cells. The final DSD leaves both QI and NI unchanged at levels 21 and 23; its ice slopes are approximately `11612.32` and `80718.02`, strictly inside the `9080..1.82e6` limits. The host `MP_OUTPUT` stores the corresponding f32 values. The full QI/NI changes include other process rates; this packet does not certify a complete named-process or physical number budget.

**Coordinate and precision limit:** host QNICE is a REAL4 input. In this call its NI word is widened without a numerical density conversion before sedimentation; later C3 consumes the post-sedimentation working NI. That establishes the executed numerical handoff, not the physical mass/volume basis of QNICE. The C++ working state is f64 and writes REAL4 host outputs. This is value-only forward evidence, not a host JVP/VJP or operational f32-internal parity test. `scientific_status: INCONCLUSIVE` remains appropriate.

```bash
python3 -m harness.evidence.native_c3_c4_dsd_call_2026-11-01.verify_packet \
  harness/evidence/native_c3_c4_dsd_call_2026-11-01/selected_packet.json \
  --sha256 ef185f41ef0aca0226c980ee0449c7e8ec4809770c98e46a09acfc113c38a224
python3 -m unittest discover -s harness/evidence/native_c3_c4_dsd_call_2026-11-01 -v
```

The [private runner snapshot](run_private.py) and [private exporter snapshot](export_private.py) are included for source review. Their required host assets are unavailable in a public clone. The selected-packet SHA file is co-versioned with the packet; the reviewed Git commit supplies the external content identity.
