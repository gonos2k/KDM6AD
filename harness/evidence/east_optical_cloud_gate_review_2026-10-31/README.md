# Serialized cloud-fraction stratification of the east optical witness

This packet reclassifies the ten PR #486 east-edge profiles using their saved
RTTOV optical rows and direct BTs. It makes **zero** host, KDM, RTTOV, K, or
optimizer calls. The parent witness and the QNC-only direct packet are replayed
before this summary is accepted.

| Guard → late-pilot change in native rows | All | Saved cloud fraction > 0 | Saved cloud fraction = 0 |
| --- | ---: | ---: | ---: |
| Ice content differs | 82 | 42 | 40 |
| Effective diameter differs | 30 | 1 | 29 |
| Observed diameter-bound category differs | 29 | 0 | 29 |
| Saved cloud fraction differs | 0 | 0 | 0 |

All 42 changed cloudy ice contents increase; pilot/guard ratios are
1.0230559951493698–5.238117019777437. The single cloudy diameter change
is native `(234,52,25)`, RTTOV layer 42: 20.020000000000003 →
20.020000000000007 µm, exactly one binary64 ULP; both values have the same
binary32 word. The 29 observed bound-category changes all occur where the
saved cloud fraction is zero. The label describes **saved output equality** to
10 or 120 µm, not whether the upstream clamp actually executed.

All 70 pilot-minus-guard BT values decrease, between −5.370063623403723 and
−0.798306485991759 K. Their seven-channel Huber numerator changes total
+123.92018052340481, or +1.7702882931914974 per affected channel cell.
On the unchanged full-M0 denominator of 377,342 cells, the contribution is
+0.0003284028295906759. BT direction and loss direction differ by channel;
these are distinct measures.

## Replay

```bash
python3 -m harness.evidence.east_optical_cloud_gate_review_2026-10-31.replay
```

The replay SHA-checks its calculation files and the immutable parent witness,
then runs the parent optical and QNC-only packet replays. It regenerates the
published `analysis.json` byte for byte and checks the cloud strata, one-ULP
event, BT signs and cost against the parent analysis. The model-call count in
this replay is zero; the archived direct-call evidence belongs to the earlier
packets.

This is a classification of **serialized** RTTOV inputs. The ice content is
the QI-plus-QS optical input in g/m³, not a vertical integral or domain ice
mass. The archived case files were not independently hash-pinned at their
execution time. The recorded cloud fraction, diameter-bound category and
binary64 values do not reveal pre-serialization operands or the upstream
radius clamp branch. No diameter-only RTTOV intervention has been performed
in this packet, so its radiative effect is not proven zero. QNICE raw units,
the boundary's applied physical budget, the new host JVP/VJP, analysis
acceptance, and pixel UTC remain unresolved.
