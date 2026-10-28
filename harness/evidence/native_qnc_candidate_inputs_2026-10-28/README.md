# Native QNC candidate-input packet

Reproduce from the repository root:

```bash
python3 -m harness.evidence.native_qnc_candidate_inputs_2026-10-28.replay
```

The replay verifies its manifest, current calculation sources, raw records,
and the PR #474 parent replay before regenerating `analysis.json` byte for
byte. The offline replay makes **zero host, KDM6, RTTOV or optimizer calls**.
The execution receipt reports four accepted full-domain, 20 s host steps
(control and α=0.25, trace off/on) plus two preliminary α steps excluded from
the final v2 analysis. Eight KDM wrapper entries are expected from the
two-tile path, not independently counted in this packet.

`faces.tsv` uses native `(i,k,j)` order. Its 32 f32 words per cell include
the prior 26 applied-face operands plus six pre-limit correction faces.
`rk_writer.tsv` uses the same coordinate order. The producer preserves the
first 61 targets of PR #474 and adds the receiver/seam cells. The replay
requires all 54 prior donor rows and 8,792 prior writer values to remain
bitwise identical, verifies the field/type/coordinate inventory, and joins
all 382 captured cells to source-compatible directional tendency and RK
output calculations. Compatibility does not identify executed FMA
instructions. The six pre-limit face words at the earlier `(113,70,12)`
witness also match the PR #469 producer trace in both cases.

The 54 selected donors have 324 incident shared faces. Each donor/receiver
pair has identical pre-limit correction, post-limit correction and
low-order words; the original post word equals f32(pre × the recorded
outward donor scale). Four sampled Y-seam pairs also match on both tiles.
These checks use the **unchanged** host operator. No modified limiter or
candidate host step was executed. [Interpretation and limits](../../../docs/NATIVE_QNC_CANDIDATE_INPUTS_20261028.md)
keep the selected-neighborhood, one-rank and unresolved physical-number
basis explicit. The α endpoint still loses 54 fixed-M0 profiles / 378
channel cells.
