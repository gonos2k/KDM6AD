# S10 cold graupel mass–volume pair

**S10 remains OPEN.** A selected native mp237 call now identifies the process
that first makes graupel mass positive while the stored bulk-volume moment
stays zero. This is a read-only measurement of the existing calculation, not a
density fallback or a physical correction.

The fixed tap selects step 1, `(j,i,k)=(2,142,17)` at the cold stage-2
graupel update. It records the actual post-limiter mass rates, routing
fractions, seven non-`rhox` volume rates, `dtcld`, and both state words before
and after the source updates. It **never reads or emits `rhox`**: the eighth
volume term, `pgdep/rhox`, cannot be reconstructed from this record because
the density output may be unassigned. The pair-only overlay also removes the
14 inherited `S10SHAPE` numeric writes that would read unassigned ProgB
outputs; it keeps the integer validity events. The older two-run attempt that
included those writes is excluded as diagnostic-only evidence.

The [single bounded S10PAIR row](S10_stage2_pair_run1/s10pair_selected_row.txt)
has SHA-256
`d6ddd23a07be6bc7d1a47f97e4f38ab0a21cbe6a02baa60f2d76906aaba10c2b`.
The [path-redacted run receipt](S10_stage2_pair_run1/revised_run_receipt.json)
has SHA-256
`67f18487f68a6a544a7e40b9d5b8412d1d686ce405f5878c83c8558ee0f8da63`.
The receipt pins canonical source `4f0103c8…`, generated overlay
`37013f0d…`, fresh object and executable, LC05 inputs, effective namelist,
run identities, and saved 0/20-second frames. Both completed 20-second runs
used the same executable, one MPI rank and one thread. Log OFF emitted no S10
events; log ON emitted exactly one S10PAIR row and no S10SHAPE rows. Their
history files have the same SHA-256 `cb92a376…`; both frames passed strict
raw-bit comparison. This supports instrumentation noninterference for this
bounded execution.

The configured macro-OFF `.f90` comparison **did not pass byte identity**:
the injected blocks leave nine extra blank lines. After removing blank-only
lines the statements match, and marker stripping restores the canonical
source exactly. That source check is separate from the measured same-executable
history result. A failed earlier compile invocation used the wrong generated
file path and produced no object; it is not a scientific run.

| Stored or applied quantity | Raw REAL4 word | Value |
| --- | --- | ---: |
| Graupel mass `qg` before | `00000000` | 0 |
| Bulk volume `brs` before | `00000000` | 0 |
| Applied mass rate `paacw` | `29A04152` | 7.116758625556191×10⁻¹⁴ |
| Paired `denr`-converted volume rate `baacw` | `24A419EE` | 7.116758911429811×10⁻¹⁷ |
| `dtcld` | `41A00000` | 20 s |
| Graupel mass `qg` after | `2BC851A6` | 1.4233516709011296×10⁻¹² |
| Bulk volume `brs` after | `00000000` | 0 |

All other captured graupel mass rates and listed non-`rhox` volume rates are
zero; `delta2=delta3=1`. Source-order binary32 multiplication of `paacw`
by `dtcld` reproduces `qg` after exactly. Applying `baacw` for the same interval
**without an additional density quotient** would yield a positive volume word
`26CD206A` (1.4233518352255213×10⁻¹⁵), but the executed store is zero.
The source computes `baacw=paacw/denr`; it is a density-converted paired term,
distinct from the unrecorded `pgdep/rhox` quotient.
Thus this event does have a positive mass **and** a positive paired volume
source; its missing final volume is not evidence that `paacw` lacks a volume
term.

The source expression for the actual volume store also includes
`pgdep/rhox`. The recorded `pgdep` numerator is exactly zero; the preceding
ProgB inactive branch does not define `rhox` for this state. The tap does not
observe that divisor or the quotient, so it cannot certify its numeric value
or prove which floating-point operation selected the zero final store. It
does establish a concrete path where an undefined density quotient is used
in the same sum as a valid positive `baacw` transfer. The next isolated
algorithm change is an exact-zero-rate bypass of that quotient, followed by
the same source-order mass/volume and latent-heat comparison. Positive trace
states, other density consumers, full moment validity, and the operational
default remain unapproved.

The previously prepared C-arm guard checks **current** `qg==0` together with
`pgdep==0`. At this volume consumer, the mass store has already made `qg`
positive (`2BC851A6`), so that guard would take the original division and
miss this event. The next opt-in guard must not rely on the post-mass `qg==0`
predicate for an exactly zero process numerator. It must also avoid printing
an unassigned density in its own logger and reject any nonzero rate with an
invalid divisor. These are requirements for a future change, not validated
behavior of this capture.
