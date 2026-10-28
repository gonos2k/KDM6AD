# Frozen applied-face guard replay

Run from the repository root:

```bash
python3 -m harness.evidence.native_qnc_applied_face_guard_2026-10-28.replay
```

The replay first verifies the PR #471 manifest, source pins, raw records and
published analysis, then pins the new evaluator source and compares its result
with this packet's `analysis.json` byte for byte. It makes **zero host, KDM6,
RTTOV or optimizer calls**. The parent packet contains the actual four host
steps; this packet does not add a host run.
The evaluator functions operate on supplied in-memory records; their direct
calls do not authenticate those records. The official replay performs that
provenance check before calling them.

The predicate uses the saved PR #471 seven-cell RK3 QNC words. It rounds a
trial donor scale into six correction-face words, mirrors each at the adjacent
receiver, and checks all seven exact saved-face residuals and source-compatible
binary32 RK results. Control passes at its recorded scale. The α candidate's
one-ULP decrement fails the exact residual condition even though its target
f32 NC is positive. Two ULP pass **this selected-star predicate**; see
[`analysis.json`](analysis.json) and the [interpretation](../../../docs/NATIVE_QNC_APPLIED_FACE_GUARD_20261028.md).

The search bound of three decrements is a bounded replay of this witness. It
is not a production scale selection rule, a physical number-budget proof, or
evidence of full-domain candidate admissibility. The fixed `M0` still loses
54 profiles and 378 channel cells in the executed α checkpoint.
