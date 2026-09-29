# S1: bounded full-tile ice-substep census

The selected column in [the normalized mp337 run](REPORT_S1_normalized_ice_native_2026-09-30.md)
had `mstep_i=1` and zero bottom ice-number export. To find whether the same
40 s retained-input run contains a qualifying column elsewhere, this
experiment records only the per-call counts from the existing conservative
ice substep: columns with `mstep_i>=2`, columns with positive **actual capped**
bottom `dn_out`, and their intersection. The [diagnostic patch](../s1_ice_census.patch)
is applied after the existing S1 face-trace patch and is active only with
`KDM6_S1_ICE_CENSUS`. It does not change the numerical update.

An isolated library was built from PR #344 main plus those two patches and
linked with the already measured private mp337 selector-2 ISO/wrapper objects
ahead of the unchanged host archive. The same new executable ran with census
OFF and ON for 40 s at `dt=20 s`, one local MPI rank on `en0` and one thread.
Both runs completed and saved exactly 0, 20 and 40 s. Their four saved output
files have identical SHA-256 hashes, and all 254 common forecast variables
match raw-bit at every frame. The census-OFF outputs also match the PR #344
selector-2 run byte for byte; the bounded selected-column face trace is
byte-identical to its prior capture.

The independent host tile log declares two disjoint owned tiles per time
step: 32,712 and 32,248 columns. The [pinned census](s1_ice_census_2026-09-30.log)
has exactly four records and covers 129,920 column-calls across the two
steps. Every record has max `mstep_i=1`, zero columns with `mstep_i>=2`, and
zero positive bottom ice-number departures. The selected-column trace from
PR #344 still has 14 positive **internal** number faces, so the bottom-zero
result is not a claim that no ice number moved anywhere.

This is a **negative witness limited to this 40 s trajectory**. It cannot
close S1's native multi-substep/nonzero-bottom condition or choose the
physical QN basis under S2. It also does not prove those events cannot occur
later or under another eligible native state. Extending the same case merely
to await a pass is not a substitute for a predeclared physical input and
time-window criterion. Source, build, input, run, and output hashes are in the
[receipt](native_s1_ice_census_2026-09-30.json). GitHub CI replays the small
public census; it does not execute the private host.
