# C++ four-case bundle — vertical (k) orientation finding

Status: **RESOLVED (PR#67A, commit on harness/g33-cpp-orientation).** Root cause was
the C++ shared-fixture LOAD, exactly as hypothesised below (candidate b). Fixed at
source in `abc_driver.cpp`: `to_host_order()` loads the top-first authority fixture
into the surface-first wrapper State/Forcing (so `runtime.cpp` flip_k yields correct
top-first sedimentation), and `emit_fixture_field` flips back for `--fixture-only`
(the emitted fixture stays byte-identical to the authority; SHA `18ea733b` and F↔C++
parity preserved). The normalizer's compensating `[B,K]` flip is removed and it now
enforces `canonical_k_order == "top-first"`.

**Validation:** on a regenerated bundle, legacy Fortran ↔ legacy C++ (via
`from_fortran_run` / `from_cpp_evidence` + `compare_pair`) is now **bit-identical**
across all 579 ops + stages — no divergence, no flip. The op-set/value inconsistency
below is gone.

--- Original finding (for the record) ---

Found while wiring the real C++ bundle reader (`g33_bundle_io` + `g33_normalize`)
against a real bundle (fixture `18ea733b`, params `4b1c84ef`, identical to the
committed Fortran legacy sample).

## What verifies

- `g33_bundle_io.verify_cpp_evidence` re-checks the whole `{algo}-C-evidence` tree
  (run_contract vs its .sha256, every `schema/*.desc` vs `descriptors.sha256`, every
  `dump/*.g33` payload hash + header binding to contract/descriptor/commit, container
  set completeness). It accepts the real bundle and rejects tamper (tested, no torch).
- **Columns** pair cleanly: C++ payload lane `b` → Fortran column `cpp_flat_index+1`.
- **Stage `[B,K]` tensors** are stored BOTTOM-first (`k=0` = model bottom); flipping
  the storage index to top-first (`canonical_k = K-1-k`) makes the C++ entry state
  (`outer_pre_sed` / `substep_pre` qr, nr, work1, workn, delz_safe, dend_safe, decoded
  mstep/gate) **bit-identical** to the Fortran per-level records at all 12 (col,k).

## The discrepancy

The **op records** do not align under any single k convention:

- C++ `k=0` is labelled `TOP` and carries the 3-op TOP set `{FALK, FALLACC, UPDATE}`;
  C++ `k=3` is `BOTTOM` with the 5-op set — structurally top-first, same as Fortran.
- But the op **values** at C++ `k=0` (TOP) equal Fortran `k=3` (BOTTOM) exactly:
  19 of 25 (col=1) fields are bit-identical to Fortran's opposite cell, e.g.
  `QR_FALK.mul_dend_q` C++-TOP = `0x37b4637d` = Fortran-BOTTOM, not Fortran-TOP.

So the op-dump's structural k-labelling (top-first) and its data ordering
(bottom-first, matching the stage tensors) disagree. Neither mapping is admissible:

- Pair by k-index (C++ k=0 ↔ Fortran k=0): values differ by ~4.6M ULP — an exact
  cross-cell match, not a ~1-ULP residual. A shared-mechanism rung would then be
  mis-read as a real divergence.
- Pair by flipped k (C++ k=0 ↔ Fortran k=3): values align, but the op-SETS differ
  (C++ 3 ops vs Fortran 5) → identity universe mismatch → INVALID_EVIDENCE.

## Why this must be resolved at the source, not guessed

An exact-cross-cell value match is a k-orientation artifact, and picking either
mapping silently would produce a decision-grade WRONG verdict. Resolving it needs
the C++ driver's actual convention: how `fourcase_v1` loads the shared fixture into
its column tensors and how the op-trace assigns `k`/`cell_role` vs how the stage
tensors are stored. Candidates: (a) the op-trace `k`/`cell_role` is mislabelled
relative to the data; (b) the C++ driver loads the fixture vertically reversed vs
the Fortran driver, so the two runs' "top" cells hold different physical data.

Until then `g33_normalize.from_cpp_evidence` is column- and stage-validated but the
op stream is NOT verdict-ready — it must not be fed to `adjudicate` for a real C4
verdict. The Fortran leg (`from_fortran_run`) is validated and unaffected.
