# S10 first-fatal graupel mass–volume budget

**S10 remains OPEN.** The exact-zero-only mp237 variant from PR #319 stopped
before `pgdep/rhox` when `pgdep` was nonzero and the preceding `ProgB_param`
call had not assigned `rhox`. This follow-up records the defined process
operands at that same first fatal cell. It does not choose a density or change
the operational calculation.

The fixed native input, 20 s step, one rank/thread and local `en0` MPI path
reproduced the earlier `S10ZF` row byte-for-byte. The run stopped at step 1,
loop 1, substep 0, `(j,i,k)=(84,117,17)`. The new `S10ZFB` row contains 24
binary32 words: mass and volume before the stage-2 stores, the mass after its
store, `dtcld`, ten applied graupel mass rates, two routing fractions and seven
defined volume rates. It never reads or logs `rhox`. The [two raw rows](S10_fatal_budget_run1/fatal_rows.txt)
and [path-redacted receipt](S10_fatal_budget_run1/receipt.json) pin the
source, executable, inputs and failed run. This is a **rate/input snapshot**:
`qg` is already stored when the fatal is logged, but `brs` has not yet been
updated. The later `(j,i,k)=(2,142,17)` action-log target was never reached.

| Defined value | REAL4 word | Decoded value |
| --- | --- | ---: |
| `qg` before mass store | `2F3EB97A` | 1.7346293845754701e-10 |
| `brs` before volume store | `00000000` | 0 |
| Applied `pgdep` rate | `AD189462` | −8.673147269822046e-12 |
| Applied `paacw` rate | `35B913DE` | 1.3789356216875603e-6 |
| Paired `baacw` rate | `30BD84FC` | 1.3789356323457014e-9 |
| `qg` after mass store | `37E758D5` | 2.7578711524256505e-5 |

`dtcld` is exactly 20 s. The other eight recorded graupel mass rates and
other six defined volume rates are zero at this cell; `delta2=0` and
`delta3=1`. Binary32 multiplication gives

```text
pgdep * dtcld = -qg_before = 0xAF3EB97A
```

so the deposition/sublimation term exhausts the old trace graupel mass in
the recorded arithmetic. Source-order evaluation of the actual mass update
reproduces `qg_after=0x37E758D5`. At the same time, `paacw` creates new
graupel mass and its defined companion `baacw=paacw/denr` creates a positive
volume source. Their rate ratio is approximately 1000, consistent with this
source expression's `denr` conversion. That ratio is **not** a measured or
approved bulk graupel density.

The old trace mass has no stored `brs` to remove. Thus the new `baacw` source
is present, but the negative `pgdep/rhox` term still lacks a current-call
denominator. The post-mass `qg` exceeds `qcrmin`; the prior `ProgB_param`
gate saw the much smaller pre-mass state, so this does not contradict its
inactive assignment bit. A physical rule for positive trace `qg` with zero
bulk volume is still required before the volume update and its derivative
can be accepted. Inserting 400 kg m⁻³ or suppressing deposition would be a
separate physical choice, not a deduction from this row.

The opt-in logger preserves the previous fatal path and merely emits the
defined budget words immediately before the stop. Focused generator tests
pass, and the generated Fortran object/executable built successfully. The
receipt records hashes for all 17 existing link-file inputs after the run;
16 match the earlier pinned guard build, and the seventeenth is the new
isolated object. This pins the observed executable and dependencies without
claiming historical Gate A identity. The run exited with code 1 before the
20 s frame; no completed trajectory,
instrumentation noninterference or whole-domain budget is claimed. An
isolated compile initially wrote a generated `.mod` into the canonical host
directory because its `-J` argument was malformed. The file was restored to
the exact SHA-256 held by two pre-existing host shadows; canonical `.F`, `.o`
and `libwrflib.a` hashes remained unchanged. The object was then rebuilt
with a correct isolated module output path before the native attempt.
