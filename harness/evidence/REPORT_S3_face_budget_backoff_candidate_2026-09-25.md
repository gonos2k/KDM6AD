# S3 final-RK face-budget backoff prototype

**S3 remains OPEN. The earlier synthetic-neighborhood acceptance claim in this
report is withdrawn.** The vertical outgoing-face signs in the prototype were
reversed. With the source signs restored, the captured donor has five outgoing
correction faces, and the six-cell synthetic neighborhood is rejected because
its vertical receiver becomes negative. This is not a native execution of a
repair and does not close whole-host accepted-state nonnegativity.

## Fixed seeds

The replay input is
`harness/evidence/number_face_flux_2026-09-24.json`, SHA-256
`fcb0cb61b3dcdeded0705d4de8f5161aeae0f071041f9ffd5c4a0f310c2a6596`. Its
captured source baseline is commit `cff7c9b2744c6abda99706cf9830ee608516b7d5`;
the active `module_advect_em.F` SHA-256 is
`58253bdbeb188dd47ed0579fcd2891086be1889b75c0c7d3696c9ad1d213559d`, and the
retained `module_em` object SHA-256 is
`7be51c5276e3e28cefe6482377b9fb9d7e8cb3d1db972efbf2ad2b24137348c2`. Both
captured variants use the same input identity
`12e132ecefa9e0f7e0a0bd67d57353ec3a7ec113ab1b43121474340293125fdf`, 20-s
steps, two tiles, and the 40-s diagnostic capture. Original and normalized
capture histories match their own controls at
`7d2afb3236ea6ea53a1df5c75f17b2b1da27f963ace697a8a912eda871c0f750` and
`a065598b870815220ba36f7b2fbcdc6f65f8d69910c2e261961203b78d6683d8`,
respectively. Those hashes identify the old diagnostic captures; the candidate
was not linked into either run.

The seed is target 5: `QNCLOUD` (species 3), Fortran `(i,k,j)=(233,12,124)`,
step 2, RK stage 3. The test reads its POST-face row and `RK_OPERAND` from the
fixed JSON and replays stored Z→X→Y divergence followed by the existing
source-ordered final-RK binary32/FMA helper.

The native causal path and whole-grid limits are documented in
[REPORT_negative_number_origin_2026-09-24.md](REPORT_negative_number_origin_2026-09-24.md)
and [REPORT_number_face_flux_2026-09-24.md](REPORT_number_face_flux_2026-09-24.md).
The new code path was added to the code graph with `graphify update .`; the
semantic doc update could not run because this fresh worktree has no LLM API key
and Graphify's incremental scan treated 322 docs and 9 papers as changed. No
full-corpus semantic extraction was attempted. This report links the supporting
source reports directly and keeps its synthesis within their measured scope.

| Capture | RK value before | `scalar_old` | `advect_tend` | `scalar_tend` | Donor-only trial xL correction before → after | Donor-only factor | Donor-only RK value after |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| Original | −0.0285397433 (`0xbce9cc2e`) | 0 (`0x00000000`) | −140.5644684 (`0xc30c9081`) | 0 | −3,069,114,843,136 (`0xd432a560`) → −3,069,114,318,848 (`0xd432a55e`) | 0.9999998212 (`0x3f7ffffd`) | +0.0101315593 (`0x3c25fed7`) |
| Normalized | −0.0018450511 (`0xbaf1d5a4`) | 0 (`0x00000000`) | −9.0869264603 (`0xc111640d`) | 0 | −3,028,194,426,880 (`0xd430439d`) → −3,028,194,164,736 (`0xd430439c`) | 0.9999999404 (`0x3f7fffff`) | +0.0238400865 (`0x3cc34c49`) |

These donor-only trials are not accepted connected-face results. Both use
`dt_rk=20` (`0x41a00000`). The low-order xL operands remain fixed:
original `9,717,785,600` (`0x5010ce69`) and normalized `9,720,164,352`
(`0x5010d77c`). The result is sensitive to the executed arithmetic: the
normalized capture's exact-rational POST-face numerator is positive while its
replayed RK store is negative; the original captured face numerator is already
negative. A post-store clamp would conceal both paths and alter the inventory.

## Candidate and bounded exchange check

[`harness/s3_face_budget_backoff.py`](../s3_face_budget_backoff.py) backs off
the donor's already-limited high-minus-low correction faces by one binary32
factor. Low-order faces stay fixed. Every changed outgoing correction must
have a registered receiver, or the candidate rejects the topology. Each
registered shared face is copied as
the same stored REAL4 value into the neighbor's opposite face before evaluating
the affected cells. The candidate accepts only when the donor and connected
receiver final stores are nonnegative; it fails closed if the donor fails at
zero correction or a connected receiver cannot accept the proposed transfer.
It also rejects any paired cells whose metric-weighted RK numerator coefficients
do not cancel for the shared face; equal face bits alone are insufficient for
conservation when metrics differ.
It never changes a scalar after the RK update.

The limiter in the captured `module_advect_em.F` scales vertical `fqz(k+1)<0`
and `fqz(k)>0` as outgoing. The RK divergence uses
`-rdzw(k)*(fqz(k+1)-fqz(k))`. The prototype previously reversed both vertical
sign conventions and omitted the large negative top-face correction from its
receiver set. The corrected donor has five outgoing correction faces. The
six-cell test pairs all five with opposite slots and equal synthetic metrics;
the exact pre-rounding RK-numerator contributions cancel face by face. The
donor becomes nonnegative in both variants, but the newly included synthetic
vertical receiver remains negative (original about −123,349; normalized about
−121,630). The prototype therefore returns `connected_receiver_budget_negative`
and does not publish changed faces. A partial topology is rejected, as is an
unequal-metric receiver. These receivers are synthetic; the captured G2 data
contain no measured adjacent target pair. Actual neighboring RK and face
operands are required before evaluating a repair.

Reproduce with:

```sh
pytest -q harness/tests/test_s3_face_budget_backoff.py
ruff check harness/s3_face_budget_backoff.py harness/tests/test_s3_face_budget_backoff.py
python harness/replay_number_face_flux.py
```

## Limits

- No candidate host executable was built or run. There is no new native positive
  state, whole-grid face ledger, or boundary closure.
- The tests cover a six-cell connected neighborhood with equal synthetic
  metrics and **reject** its donor-only backoff. They do not establish a viable
  correction or conservation across the real grid, tile halos,
  MPI seams, or boundary exports.
- This is stored-number arithmetic only. It makes no physical number-unit,
  absolute particle-count, dry/moist basis, or volume-moment claim.
- No operational default, host source, or saved forecast was changed. S3 stays
  open until a separately built native shadow demonstrates nonnegative accepted
  states and the matching shared-face/export ledger on both paths and affected
  boundaries.
