# Same selected host column: stage and bounded derivative screening

This packet uses the native `(203,149)` column from the archived host call, 39 native levels and 20 seconds. It combines three analyses from one input lineage. The [report](../../../docs/NATIVE_HOST_SHARED_SCREENING_20261112.md) gives the numerical interpretation and explicit remaining gates.

## Replay

Run from this directory:

```sh
python3 -m unittest discover -s . -p 'test_*.py'
PYTHONOPTIMIZE=1 python3 -O -m unittest discover -s . -p 'test_*.py'
```

`stage_compare.py` replays the same-input f32/f64 stage comparison. `stage_inventory.py` lists the archived f64 baseline's 51 stages and 505 stage/field combinations. `water_diagnostic.py` computes a conditional 39-layer water inventory from the archived f32 B=1 input/output words. `screening_replay.py` validates the bounded f64 state and forcing screening. Public replay performs no KDM6, host, or RTTOV model call.

## Source and execution linkage

- The f32 reference is #580's complete 624-word input and 510-word output. The f64 baseline exactly widens those f32 input values. The three screening centers change only TH16 according to the pinned #583 words. A public, SHA-pinned preflight plan defines ten directions and the initial `h=10⁻⁴`. Replay reconstructs every endpoint's 624 input words from its named center, direction, seed, sign, and step. The later adaptive plan is bound to that first result.
- The first screening made 129 calls including three effective-direction graphs. The bounded second pass made 123 new calls and reused four installed outputs only after checking their #583 source words and provenance. The 9.6 MiB `raw/screening_raw.zip` preserves 647 original numeric artifacts, including call inputs, outputs, and full stage captures; `raw/screening_raw_manifest.json` pins each member. Stage CSVs are checked for complete status, 19,656 rows, 51 stages, 39 levels, two substeps, and input/output word linkage.
- The original private producer source digests are in the run receipts. Archive copies of the producer scripts and the f64 baseline receipt replace machine-specific absolute paths with explicit redaction markers; the baseline receipt retains its original-byte SHA-256, and source copies have separate redacted digests. Private DSO and Torch dependency hashes are recorded, but the DSO binaries are not published or independently rebuilt in this replay. Loader logs are not published. Recorded KDM thread and loader settings do not establish identity of every inherited environment variable.
- The installed f64 DSO exported a Legacy state-only AD entry point. The isolated capture DSO exported the joint state+forcing graph entry point. Their forward output words match at every recorded value comparison; joint JVP/VJP results belong to the isolated graph. The earlier f32 host-column call, f64 installed value call, and f64 capture graph are separately attributed executions.

## What the saved values show

The 122 screened endpoint pairs of installed and capture output each match across all 468 state words. The full captures show two large-step PII activation-mask crossings and no smaller-step captured Boolean or schedule differences. Among 61 center/direction/step diagnostics, 59 retain captured masks and two cross; NC16 has 26 resolved output-word comparisons and 35 equal-word, unresolved comparisons. These are **screening categories**, not derivative acceptances. In particular, positive NC perturbations from NC=0 show the same NC16 output at `+h` and `+2h` for three step scales while differing from the center. No derivative accuracy threshold was declared for this packet, so there are zero certified derivative passes or failures. Captured-mask stability does not certify uninstrumented branches.

The same archived f32 B=1 call gives a conditional water residual of approximately `−0.4662958822 kg m⁻²` if `rho` is the compatible dry-air mass density and the six water fields are dry-air mixing ratios. Those assumptions are **not established** for this operational call. The result excludes host cleanup and transport and cannot be used as a conservation verdict. The inventory names exact missing capture labels for further process ledgers; it does not prove that no equivalent quantity exists elsewhere.

The packet changes no KDM physics or ABI. It does not verify full host tile AD, physical number/volume conventions, applied process budgets, or GK2A–RTTOV BT and cost sensitivity. `scientific_status` and `physical_unit_status` remain `INCONCLUSIVE`.
