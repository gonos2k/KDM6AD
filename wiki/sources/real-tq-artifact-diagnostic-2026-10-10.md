---
title: Actual RTTOV T/Q diagnostic on a failed native artifact
type: source
date_modified: 2026-10-10
---
# Actual RTTOV T/Q artifact diagnostic

The [bounded diagnostic report](../../harness/evidence/pr394_real_tq_diagnostic_2026-10-10/REPORT.md)
and [checklist](../../harness/evidence/CHECKLIST_pr394_real_tq_diagnostic_2026-10-10.md)
record actual all-sky RTTOV and one iteration of the single-column helper on
a cached 39-level column from the historical launcher-invalid run. A pure
20-second KDM preflight matched the cached endpoint bitwise; the separately
evaluated baseline H matched stored BT and Jo exactly with seven good channels.

The helper returned Jb_state=0.02141671856035715, Jtheta=0 and
Jo=26.45074405369286, totaling 26.472160772253215. The final audit retained
the same seven channels and signature. All-sky routing and inactive parameter
controls were preserved. Initial increments were limited to potential
temperature and dry-air water-vapor mixing ratio.

These results establish bounded real-RTTOV numerical integration, not a new
valid native case or independent observation matchup. The full returned state
and final-slot QC/NC were not persisted; physical-temperature and relative-qv
ranges and cloud-generation conclusions cannot be recovered from saved norms.
Setup failures are retained separately, including two failed H-probe captures.
Logical successful-result counts do not measure executable launches.

Receipt metadata was corrected after execution. The accompanying reconstructed
raw JSON is explicitly not an independently captured original write stream.
The baseline driver has a recorded hash without an archived source snapshot;
the analysis driver is source/hash matched. Production and immutable input
hashes were unchanged. No host run or large forecast read was performed.

New normal native execution, observation QA/time/parallax/footprint and physical
interpretation remain open. The management score stays 54/75; neither this
diagnostic nor repeated CI earns an independent-case score.

Related: [[single-column-tq-allsky-pin-2026-10-10]],
[[native-target-artifact-diagnostic-2026-10-08]].

## Later bounded endpoint inference

The [known-zero addendum](../../harness/evidence/pr395_endpoint_bounds_2026-10-10/REPORT.md)
checks the recorded final callback hashes against the known [1,39] positive-zero
f64 payload. All nine condensate/precipitation and particle fields listed there
match. This supports a clear final observation-slot endpoint under the recorded
serialization and conventional hash-identity assumptions, without restoring a
general private array or excluding transient intermediate clouds. Prior/norm
bounds also limit the selected initial k3 water ratio to about 97.23%; they do
not recover actual layer increments or endpoint RH. The original execution
source and receipt remain unchanged.
