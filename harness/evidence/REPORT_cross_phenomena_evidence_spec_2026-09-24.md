# X11: fixed case manifests and common evidence checks

Earlier replayers deliberately pin case-specific facts: PR #227's five
required noninterference files, X2's two native mp37 calls and six phase
stages per call, and G1's expected substep consumers. Those constants must
not be inferred from whatever records happen to arrive, or an omitted event
could be treated as an originally shorter experiment.

This pilot keeps the **X2 expected manifest fixed in its case replayer** and
adds one small common `audit_evidence` function. Its plan names expected
event keys and distinguishes:

* `measured`: needs a declared source SHA-256; no synthetic generator or
  derived parent is allowed.
* `derived`: needs unique, earlier declared parent events. It is not relabelled
  as an independent native measurement.
* `synthetic`: needs a declared generator ID and no measured source SHA.

The common check rejects missing, extra, duplicate or relabelled keys, wrong
tiers, source/pinned-payload SHA changes, invented parentage and invalid
source/generator contracts. The X2 native replayer now uses it for its
code-fixed 12-event measured set **in addition to** its original raw-record
digest, phase order, f32/f64 source-store arithmetic and run-identity checks.
The common function does not weaken or replace those case-specific checks.

Five new tests and the retained X2 native replay tests passed together
(`27/27`) with warnings treated as errors. The new tests include one measured,
one derived and one synthetic record; false native relabelling, omitted or
duplicate events, wrong source/payload digest, changed generator and wrong
derived parent all reject.

`audit_evidence` verifies a caller-supplied **independent** plan against
records. It cannot prove that the caller really fixed the plan before
observing results; X2's code-owned constants provide that property for its
one case. A declared measured source digest is also not proof that the
private original RSL/NetCDF was freshly rehashed by public CI. This layer
establishes schema/provenance consistency, not scientific acceptance,
operational parity or a universal evidence-certification framework.
