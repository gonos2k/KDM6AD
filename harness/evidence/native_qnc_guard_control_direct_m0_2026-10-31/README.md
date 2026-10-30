# QNC-guard-only Control direct M0, 2026-10-31

The finalized QNC-guard-only Control checkpoint was evaluated on the original
fixed observation support. Its independently replayed Huber numerator is
**4,153,768.353915674** and cost is **11.007967186042567**, versus original
Control **11.007963317242059** (difference **+0.000003868800508399772**).
The prior QNC-guard plus QI boundary-pilot Control cost was
**11.008295588872157**; guard-only minus pilot Control is
**−0.00032840282958979117**. These are different host endpoints and do not
isolate a named physical process. The original 53,906 profiles / 377,342
channel cells remain valid, quality zero and finite in all 129 direct blocks.
These are counts recorded by producer receipts, not independent proof that
RTTOV executed.

Run the official offline replay from the repository root with Python and NumPy:

```
python harness/evidence/native_qnc_guard_control_direct_m0_2026-10-31/packet_replay.py
python harness/evidence/native_qnc_guard_control_direct_m0_2026-10-31/test_packet_replay.py
```

The reader verifies the archive and verifier source hashes, runner snapshot,
checkpoint and host-receipt identities, each attempt/result/capture, the
original baseline packet and its objective, and runtime/RTTOV asset identity
against the hash-pinned #483 archive. It enforces the original 65,988-profile
B512 ordering (129 blocks including tail), channels 10–16, unchanged M0,
per-cell direct/profile validity and zero quality. It also verifies receipt source
indices and ordering, profile count, channel and BT coordinates, geometry/surface
mode, direct driver flags and zero recovered K. It reproduces channel-then-
chunk Huber sums (delta 1 K, sigma 1 K, zero bias) and the fixed normalizer;
it makes zero model calls. It depends on the original baseline and #483 archive
in this checkout. The archive's binding and the source snapshot contain local
paths and should be reviewed before external publication.

The pinned `executed_sources/verify_export_executed.py.txt` is the offline
exporter used on the stopped finalized run. It checked the accessible private
source pins, trace-on/off host receipts, plans, build receipt, retained
checkpoint, and operational source-tree hash, then copied only the binding,
summary, attempts, results and captures. It replayed that copy again. A subsequent read-only check compared all 391
archived files byte for byte against the finalized producer files; all hashes
matched. The exact exporter source used is preserved separately; the current
verifier additionally checks receipt profile ordering and direct-driver semantics. The
archive contains those copies, not the private raw call folders, host checkpoint,
native observations or RTTOV installation. `packet_replay.py` checks the
hash-pinned archive and verifier; it cannot reopen private inputs or certify
their physical meaning. [Source and build resolution](SOURCE_RESOLUTION.md)
records identities and limits.

The calculation is a fixed-support BT/cost diagnostic, not an accepted analysis,
named-process attribution, applied mass/number budget, physical certification
of raw number units, higher-derivative proof or forecast-skill result. The
observation nominal slot is 00:00 and the host checkpoint is 00:01; pixel UTC
is unverified. The direct observation calculation does not certify host ice
radius or reflectivity diagnostics. The RTTOV executable, coefficient and calibration files, environment and run
scripts, Python executable, Torch extension and netCDF4 extension are hash-pinned.
Other shared libraries and transitive native dependencies are not fully pinned.
