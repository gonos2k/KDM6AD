# S3 selected applied-face and RK rounding ledger

S3 remains **OPEN**. This reuses the five-cell native QNCLOUD capture from
[the 2026-09-28 neighbor run](REPORT_S3_native_qn_neighbors_2026-09-28.md).
It executes a public scalar replay, not a new host forecast. The stream SHA-256
is `848eae8889159d880640134581f29b3e830638cfb5f68cd6c3219ae3969747dd`.

The replay uses the actual `S3QNAX` divergence operands. Limiter-local PD face
arrays are not substitutes: two receivers' local arrays differ from the faces
their recorded divergences consumed. All five original RK-after words replay
bit-for-bit before applying a counterfactual.

The prescribed factor `3F7FFFFF` multiplies the donor's five outgoing high-order
correction faces in binary32. Four modified internal face words are copied to
the measured opposite receiver faces; east xR is an external face. Low-order
faces, source tendencies, geometry and RK coefficients stay fixed. The donor
changes from `BAEC299F` (-0.0018017775) to `3C35A32B` (+0.0110862656).
The four receiver stores retain their original words. This establishes local
nonnegativity for this counterfactual only.
Their source-order RK numerators also retain the original words; the small
face changes disappear before the final receiver state stores.

In the declared operator measure `W=1/(msftx*msfty*abs(rdzw))`, the exact-rational
internal numerator changes pair as ±45.5329971395 (west), ±0.1778632701 (south),
±0.3557265402 (north), and ±40.9666635839 (upper). Each pair's sum is exactly zero.

| Change over the five-cell counterfactual | Operator-weighted value |
| --- | ---: |
| Exact signed east xR numerator term | +0.17786327007619562 |
| Sum of source-order binary32 RK numerator changes | +56.4597924237205 |
| Sum of final stored states times the stored RK denominator | +56.45979023574415 |
| Change in divergence/RK rounding relative to exact face exchange | +56.281929153644306 |
| Final division/store rounding contribution | -0.0000021879763481 |

The decomposition is `sum(W*delta(M_new*q_stored)) = external_xR +
change_in_divergence_and_RK_rounding + division_store_rounding`, using the
stored source-order RK denominator `M_new`.

These are conditional operator quantities, not particle counts in approved
physical units. The rounding row is the difference between the baseline and
counterfactual arithmetic errors. It shows why exact face-coefficient pairing
and five nonnegative stores cannot certify the applied stored budget. A native
repair still needs the full source/RK budget, shared values across tile/MPI
seams, and actual external-boundary accounting; the physical QN basis remains
separate. No fixed ULP decrement or operational change is approved here.

Run `python harness/replay_s3_applied_face_budget.py` and
`pytest -q harness/tests/test_s3_applied_face_budget.py`.
