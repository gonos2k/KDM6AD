# Selected-donor adaptive QNC scale replay

From the repository root:

```bash
python3 -m harness.evidence.native_qnc_selected_adaptive_2026-10-29.replay
```

The replay checks the PR #475 input packet and its parent evidence, pins the
current [analyzer](../../analyze_qnc_selected_adaptive_pilot.py), then
regenerates `analysis.json` byte for byte. It makes **zero host, KDM6,
RTTOV or optimizer calls**. The parent's actual host steps remain distinct
from this frozen-input calculation.

The analyzer exhaustively checks at most 256 lower positive f32 scale words
per selected donor, stopping at its first exact-residual and all-compatible
f32 RK pass. It applies all 54 choices together from the recorded PRE face
words, mirrors each rounded shared word to the receiver, and reports
baseline/candidate failure sets for all 382 captured cells. A separate
max(control, α) coordinate table quantifies the effect of forcing the same
offset map on both cases. Original-compatible arithmetic includes eight
directional choices and 24 RK contraction patterns, including both FMA
orientations of the two-product numerator. The [report](../../../docs/NATIVE_QNC_SELECTED_ADAPTIVE_PILOT_20261029.md)
states the counts and limits.

All selected donors pass within four ULP in these two stored cases. Four
pre-existing receiver cells remain exact-zero/QNC `+0`; no new receiver
failure is predicted. This does **not** certify a changed host executable,
all-domain moment admissibility, a physical number budget, executed FMA
instructions, optical response or a second analysis.
