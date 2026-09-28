# S10 midpoint plus exact-zero quotient: bounded native feasibility

**S10 remains OPEN.** This isolated mp237 variant composes the previously
unapproved `rho_mid=400 kg m-3` ProgB policy with an exact-zero-rate bypass
at all four `rhox` quotient consumers: `pgmlt`, `pgdep`, `pgevp`, and `pgeml`.
Zero arms use the signed process numerator in place of the quotient. Nonzero
arms require a current-call density assignment that is finite and positive;
otherwise they stop before the division. The guards do not directly edit the
rate, limiter, qg-mass or latent-heat formulas; changed `brs` can still affect
their values later in the trajectory. The operational
default and private canonical host source were not changed.

The generator starts from the pinned private mp237 source, adds the ProgB
validity overlay, applies the midpoint policy once, and then replaces each
quotient once. It does not stack the older C arm with PR #319's stage-2 arm:
their nested replacements would obscure the stage-2 source order. Its
macro-OFF source restores the B-only midpoint source exactly. In configured
WRF preprocessing, macro-OFF `.f90` **fails byte identity** because of 12
additional blank lines; all 3,763 nonblank lines match. This is retained as a
source-check failure, separate from the executed variant.

The fresh object compiled with `-ffp-contract=off` and was linked ahead of
the unchanged host archive. One retained-input, one-rank, one-thread 20-second
logging-OFF run and one logging-ON run using the **same executable** both
completed with saved frames at 0 and 20 seconds. Their complete history SHA
is identical, and both frames pass strict raw-bit comparison. Each history
scan found all 253 numeric variables finite across 158,946,410 checked
cells. No `S10HYFAIL` event occurred. This establishes bounded execution
and logging noninterference, not physical approval.

The [path-redacted paired-run receipt](S10_midpoint_rate_zero_run1/receipt.json)
has SHA-256
`6676f5e22f2f5454c0ff105612aaf906a479f5fa84c665976ee1274a3e0805a8`.
It pins the source, object, executable, input and two run identities without
including private paths or raw shape values.

Against the [earlier completed B-only midpoint control](s10_policy_counterfactual_native_results_2026-09-25.json)
(executable SHA-256 `afbe3768…`, history SHA-256 `4e743933…`), the initial frame
matches raw-bit. At 20 seconds only `QIB` differs: 26,978 of 2,573,532 cells,
maximum absolute difference `1.3887282166238912e-12` in the stored QIB
units. `QGRAUP` remains raw-bit equal at that frame. This is a between-variant
observation using separately built executables; it does not identify which
guard branch caused each changed cell or certify a mass-volume budget.

The logging-ON stream retains the earlier ProgB shape, slope, density and
trace events, but the new guard emits only failure records. It does not count
successful zero bypasses or record each applied rate and heat term. Thus a
completed 20-second run cannot establish that every process was physically
valid. The B midpoint itself changes `brs=qg/400` for positive trace qg and
can alter size, subsequent rates and heating. Choosing 400 as an accepted
trace-graupel density, defining the number/volume basis, replaying the
source-ordered mass-volume-heat budget, and verifying the corresponding AD
path remain separate tasks. The prior exact-zero-only run's nonzero-rate
fatal remains a valid witness for a different branch and is not erased by
this hybrid run.
