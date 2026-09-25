# S2: bounded mp37 rain-number trace; physical basis remains OPEN

This evidence closes one executed-path measurement within S2. It does not
resolve whether stored QNR represents particles per dry-air kilogram or per
cubic metre, so **S2 remains OPEN**. The operational mp37 physics was not
changed.

## Run and input

Both lanes used the retained 5 km case inputs: `wrfinput_d01`
(`5a9ae8da…c4d970`), `wrfbdy_d01` (`d46e5d71…c5e6c`), and `wrfchainp_d01`
(`c8e300d2…c0c4e3`). The run used mp37, a 20 s timestep, 40 s total, one MPI
rank on a 1×1 grid, and one model thread. Output frames were saved at 0, 20,
and 40 s by setting the distinct `history_interval_s=20` namelist key.

The instrumented cell and level were fixed before the rerun at Fortran
`(i=144,j=153,k=13)` from the prior native number capture. In the retained
input, QRAIN is `4.32440720e-5 kg kg-1` and QCLOUD is `2.31869446e-4 kg kg-1`,
while QNRAIN, QNICE, QNCLOUD and QNCCN are zero. Across the full input, all four
number fields are zero; 163,530 levels have positive QRAIN. The
Thompson-only `make_RainNumber` fallback is not a KDM6 initializer: its
`THOMPSON`/`THOMPSONAERO` guard excludes mp37.

The control and capture executables were freshly linked from the same WRF
objects, static archives and shared libraries. Each used a shadow build of the
canonical private-host source `host/KIM-meso_v1.0/phys/module_mp_kdm6.F`
(current local source at SHA `fc0a72d3…2b66eb5`) with binary32 reals,
`-ffp-contract=off`, and the same WRF flags. The instrumented
source is guarded by `KDM6_S2_NUMBER_CAPTURE`; stripping those blocks reproduces
the canonical file byte for byte. Its SHA-256 is
`fc0a72d33a5e61803fea56eb9118018039c6da8b5775813032b4861a2bd66eb5`; build,
link, executable and input identities are recorded in
`native_s2_number_trace_2026-09-25.json`. The canonical private source, installed
executable and `libwrflib.a` stayed unchanged.
The replay independently checks the pinned canonical source and `wrfinput`
hashes, capture hash and event-key universe. The executable, boundary/chain
input and history-file identities are preserved as run-receipt evidence; the
arithmetic replayer does not reopen or independently authenticate those files.

## Executed QNR path

At the host boundary, QNR is copied into local NR without a density factor
(`module_mp_kdm6.F:388`) and copied back the same way at return (`:425`). At
K13 the first call enters with QNR 0. The measured snow-melt branch passes the
`qrs_snow > qcrmin` threshold (`:1387-1389`), computes `sfac=1.570686592e9`,
and applies `psmlt=-1.520126318e-7`, increasing rain NR by `238.7642059` in the
source field. The host returns QNRAIN `237.9217834`, which matches the 20 s
history field bit for bit.

The same cell enters the second call with QNR `216.7449951`. The rain DSD gate
passes both `qcrmin=1e-9` and `nrmin=0.01` (`module_mp_kdm6.F:1550`), producing
`lambda=4648.4990` and `n0r=5.082491046e9`. The `nrmax=5e7` and source-bundle
`source > max(nrmin,nrs)` caps do not bind at K13. The separate autoconversion
number-rate gate has QCI below its critical `qcr` at K13, so `nraut` is zero;
this measurement does not attribute the observed QNR to autoconversion. The
first-call snow-melt source and second-call rain-number DSD/transport are
captured as separate, source-ordered events.

At each internal face the capture retains the upper cell's actual departure
and the lower cell's separately capped arrival. Around K13 the step-2 values
are:

| Interface | QNR departure | QNR arrival | QR departure | QR arrival |
|---|---:|---:|---:|---:|
| K14 → K13 | 35.0459251 | 38.0029488 | 4.06750223e-6 | 4.20093875e-6 |
| K13 → K12 | 19.5404701 | 21.4704304 | 7.32715898e-6 | 7.71013583e-6 |

The cell uses `mstep=1`; bottom export in this column is zero. After the second
KDM6 return, QNRAIN at K13 is `234.4465027`, matching the 40 s history exactly.
The second-call host entry differs from the first-call return by `-21.1767883`
between KDM6 calls. That host dynamics interval was not measured as a complete
number ledger, and is kept separate from the within-call QNR source and
sedimentation accounting.

## Conditional measures and thresholds

The replay pairs actual applied transfers on all 38 internal faces. It reports
number transfer under three candidate measures and rain-water mass under moist
and dry-density weights. For the active second call:

| Candidate number measure | Interface mismatch | Weighted departure | Mismatch / departure | Update-ledger closure |
|---|---:|---:|---:|---:|
| `dz·n` (volume-number interpretation) | 0.002348708 | 49,835.8376 | 4.71e-8 | 0.001674372 |
| `rho_m·dz·n` (moist operator measure) | 2,043.68109 | 39,206.9318 | 5.21% | 0.001772010 |
| `rho_d·dz·n` (conditional dry-mass interpretation) | 1,988.27001 | 38,891.9463 | 5.11% | 0.001751423 |

Under `rho_m·dz·q`, the measured mass interface mismatch is `4.38e-10` on
`8.93e-3` weighted departure. Under the conditional dry-mass weight it is
`-8.02e-6` on `8.85e-3`. The signed ledger retains the binary32 state-update
rounding. These results identify the operator's executed measure differences;
they do not select a physical QNR unit.

At the second-call K13 host entry, `rho_m=0.8391379714` and `qv=0.0092842886`,
so the conditional dry density is `rho_d=0.8314188389`. If stored number is per
dry-air kilogram, the number thresholds would map to volume units as
`rho_d·nrmin=0.0083141882` and `rho_d·nrmax=4.1570942e7`. If stored number is
already volumetric, the raw `0.01` and `5e7` thresholds are the volume-basis
candidates. The analogous `ncmin` and `qcrmin` maps are recorded in the
replayer output. These are conditional transformations only; the executable
used the raw thresholds and fields, with no density insertion.

The Registry's `# kg(-1)` declaration and the host's raw copy conflict with the
kernel DSD formula, which dimensionally requires QNR in `m^-3` when lambda is
`m^-1`. Number sedimentation also omits `dend` from its number flux and update,
while mass sedimentation includes it (`module_mp_kdm6.F:1192-1224`). The
measure-dependent residuals cannot decide which side describes physical
particle count. Historical source analysis records the same unresolved basis
and WDM6 inheritance in `FINDING_number_basis_is_inherited_from_wdm6_v1.md`.

## Verification and scope

The selected-column capture contains exactly 1,257 typed REAL(4)/REAL(8) event
records. The replay pins that census in code and requires the expected 38
internal face keys at levels 1–38 and top-cell key at level 39 for each of the
two calls; deleting a face or source event cannot silently shorten the column
or source census. It checks host/local entry and return copies, actual DSD
gates, source-ordered melt/autoconversion thresholds and number updates, each
applied mass/number face cap, and conditional column ledgers. Fourteen focused
replay tests pass. The complete 910 MB control/capture history files have the
same SHA-256; `strict_bitwise_nc.py` reports 253/253 common numeric fields
raw-bit identical, plus exact equality for the `Times` character variable (254
common variables in total) at 0, 20 and 40 s.
After the history-file SHA equality and all three frame comparisons were
recorded, the two 910 MB history copies were removed from the ignored scratch
tree; run receipts, hashes, rank logs, selected capture and replay remain.

The 20 s preliminary control was valid but too short to include the required
second KDM6 call and active-transfer witness. A first 40 s control run omitted
`history_interval_s` and produced no history frames. Both runs were excluded
from the paired evidence; a first capture-link attempt also failed before model
start because of a stale Torch library path.
The corrected 40 s pair and these excluded attempts are identified separately
in the evidence manifest.

This is one rain-number trace in one column of one retained forecast. It does
not settle the physical number basis or threshold policy, the inter-call
dynamics number budget, other number species, `mstep>1`, the mp137 ABI, forecast
impact, or radiation/observation acceptance. The capture has no independent
temperature operand at the warm/cold cap and update sites; the replay pins their
observed per-step level sets and cross-stage keys, but does not independently
reconstruct thermodynamic branch selection. `graphify update .` rebuilt the
structural public graph (13,154 nodes, 22,557 edges and 1,025 communities;
HTML visualization was skipped because the graph exceeds the 5,000-node
limit). A follow-up query links the new replayer to its tests and local
helpers, but the public worktree excludes the private host, so it cannot expose
the Fortran producer-to-consumer path. The changed Markdown files did not
receive the skill's semantic extraction pass; that coverage is explicitly
incomplete. Direct canonical-source and instrumented-run tracing remain the
evidence for this private mp37 path.
