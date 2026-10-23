# Native-domain ice factorial: executed value comparison

The prepared 234 × 282 native grid (65,988 columns, 39 mass levels) has now
been evaluated in all four ice-only modes. See the
[execution report](../harness/evidence/domain_ice_factorial_2026-10-23/REPORT.md)
for measurements and source/input hashes. This is an offline, dt=20 s physics
experiment initialized from the saved MP137 00:00:40 endpoint. It is not a
capture of the next native MP input, a full host step, or a DA cycle.

The first-ice velocity handoff (raw `vt` or `vt/DELZ`) and ice arrival rule
(Legacy post-update cap or actual-departure inventory transfer) form the four
arms. The main rain/snow/graupel chain stays Legacy. These alternatives remain
isolated research builds; neither operational defaults nor installed libraries
are changed. The [earlier one-column study](NATIVE_ICE_FACTORIAL.md) is retained
as historical evidence rather than overwritten by regional results.

## Execution and batch identity

`python -m harness.run_domain_ice_factorial` validates a dry-run plan by default;
`--execute --output-dir <fresh-directory>` explicitly executes one arm. The
runner admits the fixed manifest and experimental executable by SHA-256,
reads each chunk once into bytes, hashes and decodes the same bytes, verifies
C-order coordinates with **NX=234, NY=282**, and checks echoed tensors bitwise.
The batch partition is 128 × 512 plus 452 columns. It is part of the operator
identity because batch-wide scheduling reductions can change the substeps;
these results do not establish B=1 or alternate-partition equivalence.

Four arms execute sequentially, each with up to ten single-thread workers.
Receipts bind input, executable, mode, dt, thresholds, request, response and
native column bounds. A resumed chunk is accepted only after these identities
and the response echo/hash are rechecked. The resource wrapper uses Darwin
`/usr/bin/time -l`; RSS is bytes for one child process, not the aggregate of ten
workers. This measurement wrapper is not a portable Linux resource collector.

## Water and applied-state diagnostics

The measure is the **actual request's** fixed `DEN[k] * DELZ[k]` in kg/m².
For each column, six water-species changes are multiplied by that measure in
binary64 and the rounded products are summed with `math.fsum`. Raw kernel,
cleanup and final-applied changes are reported separately. The reported total
precipitation is a call increment, numerically kg/m² = mm for water; snow/ice
and graupel diagnostics are subsets, never additional terms or multiplied by dt.

The raw-state/reported-precipitation residual and a 256-epsilon numerical gate
are diagnostic comparisons. They do not certify physical conservation: the
raw velocity work units remain conditional, the main Legacy chain is unchanged,
and no domain-wide internal departure/arrival trace was collected.

All spatial means are **unweighted column means**; rank percentiles select
sorted samples without interpolation. No cell areas or map factors enter this
analysis. Consequently no regional mass in kg or map-area average is claimed.

The offline cleanup uses the audited interior mode-2 threshold at every stored
column, followed by the existing moist-theta finish with dt=20 s. This diagnoses
applied `H_RATE`, `QV_RATE`, `QC_RATE` and state changes. It does not emulate
native boundary cleanup, mass/map scaling, RK, retained-memory consumption or
other physics. `H_RATE` is moist-theta K/s, not a physical-temperature or BT rate.

## What is public and what remains private

The report contains all 516 chunk receipts, four 65,988-column diagnostic
archives, five post-hoc slices of actual B=512/final452 responses, and an exact
snapshot of the final runner used for the three later arms. The first raw_cap
arm preceded the resource-parser fix and lacks a separately frozen controller
source hash; its model binary and numerical inputs/outputs are pinned. Full request/response streams and complete
finish profiles stay in the private research evidence directory. Public
arithmetic replay and receipt verification are distinct from rerunning KDM.

The changed maps have not received new-map JVP/VJP/FD certification here.
A candidate is not selected by this report. Existing accepted Legacy AD and
RTTOV milestones remain valid within their earlier scopes; there are no new
RTTOV evaluations, host integrations, optimization trials or forecast-skill
claims. The historical host number payload has not been migrated or certified.
