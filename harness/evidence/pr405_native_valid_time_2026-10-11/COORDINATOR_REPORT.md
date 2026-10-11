# Native valid-time linkage: correction and actual remaining input dependency

The current native file's final boundary **record start** is July19 09UTC, but its `NEXTBDYTIME` gives July19 12UTC. Earlier PR398/400/404 records used the final `Times` value as the coverage endpoint; the statements “BC ends09” and “12-hour output is beyond the boundary solely because Times ends09” were too restrictive. Their original records remain preserved. This dated correction supersedes that interpretation for the inspected file.

## New source evidence

Only the canonical IC `Times` and BC `Times`/encoded `THISBDYTIME`/`NEXTBDYTIME` variables were read. BC records represent00→03,03→06,06→09 and09→12. No IC/BC meteorological arrays or forecast files were read or large files rehashed; stat/mtime stability guards surround the metadata read.

Authoritative runnable host source `share/output_wrf.F:983–987` writes THIS=current record and NEXT=current plus `bdyfrq`. `share/input_wrf.F:1182–1192` reads start/end and uses `this<=current<next`; further guards at1254–1267 distinguish ordinary versus dynamical-adjoint branches. Generated/preprocessed files are supporting artifacts, not the source authority. The metadata's final endpoint12 is not permission to advance at/past12; a saved final state at12 can have been reached by the preceding interval. No compiled-branch or runtime equivalence claim is added.

| Target under declared nominal-time-as-model-UTC research assumption | Lead from existing July19 00 IC | After final BC interval endpoint12 |
|---|---:|---:|
| July20 05:56 | 29h56m | 17h56m |
| July21 05:56 | 53h56m | 41h56m |

Actual pixel UTC remains uncertified. The existing local20-second analysis needs a native background at05:55:40 and nominal slot05:56. The current eight-frame intake additionally expects outputs through05:58; that adds two minutes to the host output/coverage requirement, not to the nominal observation time. The result records these separately.

## Native candidates and pending work

Cached receipts document short canonical/pinned sources, the accepted July19 05:55:40–05:58 run, and a separate hourly forecast through July19 12. The84-path inventory counts initialization suffixes, not every path's full valid-time horizon. No named cached candidate demonstrates a July20/21 valid state. This is not a census of all84 horizons or a global archive-absence conclusion.

Initialization on the observation's date is not itself required. A July19 initialization could support a later valid-date comparison if its lineage, full native state/forcing/pressure/surface and necessary boundary coverage are established. Same-initialization different valid dates are not independent initializations or proof of independent weather events; lead differences must be reported.

`NATIVE_TIME_LINKAGE.json` links the two preserved L1B result IDs/slots to the time assumption and target native times. Both remain `PENDING_NATIVE_INPUT`; selected native run/state data are null and analysis_executed=false. The present IC/BC interval does not reach either target. No relabeling, extended `run_hours`, unsupported BC extrapolation or substitute model/reanalysis data was used. The original provider/archive question is already outstanding and is not repeated.

Once either date is ready, reuse the existing all-sky,seven-channel,T/Q-only, fixed-physics,1K,zero-bias/prior configuration and preserve baseline/analysis/final audit with state/total gradient. The other date need not delay the first. No new launcher, waiting process or solver was added here.

## Verification and management

Eight focused temporal tests check record start versus interval endpoint, a valid later-date target from an earlier initialization, final-state versus advance endpoint semantics, malformed/discontinuous metadata and target-before-initialization refusal. These are time-coordinate counterexamples, not writer/microphysics/RTTOV reruns or native analyses. Green/Red independently checked the metadata/source interpretation and bounded cached-horizon claims.

The user's assessment at PR404 main`cc0a2edb` updates the same100-point rubric from78 to79: the first L1B area is15/15 and all other scores remain12/8/10/13/11/5/5. This is transcribed management assessment, not an independent validation or automatic score increase from this correction. External SST/MLS/VIIRS/L2 remain deferred extensions.
