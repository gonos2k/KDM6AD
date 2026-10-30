# East-edge RTTOV input witness

This bounded offline extract joins ten original fixed-M0 profiles `(234,3..11,52)` across original Control, QNC-guard-only Control and QNC-guard plus late-boundary-pilot Control. It reads saved case inputs, checkpoint-word witness, direct BT captures and observations; no host, KDM, RTTOV, K or optimizer calls are made. Cases have native 39 levels, reversed after a fixed 27-layer clear upper prefix, giving 66 RTTOV layers. `analysis.json` joins each changed QICE/QNICE native level to its corresponding saved optical row; it lists channel 10–16 BT and delta=1 Huber changes. `witness.json` contains all 66 rows for each state, exact f32 changed moment words, observations and BTs. Channel losses are **unweighted Huber numerators**; division by the original 377342-cell M0 gives the domain cost contribution.

At each location original versus guard-only saved ice content, ice diameter, cloud fraction and all seven BTs agree. Pilot versus guard-only changes ice content in 5–14 layers and diameter in 1–6 layers; no cloud fractions change. The seven-channel Huber sum increases at every profile, with total contribution **+0.000328402829590676**. The changed inputs and BTs belong to the same saved profiles in direct block calls, but these are three whole checkpoint states, not controlled ice-only perturbations; no independent causal decomposition is implied.

The case writer uses `hydro.txt` slot 7 for QI-plus-QS ice in g/m³ and slot 6 for liquid, `hydro_deff.txt` slot 7 for effective **diameter** in µm, and `hydro_frac.txt` for cloud fraction. The cloud builder clips nonnegative contents, uses a content-weighted ice/snow radius and clamps diameter to 10–120 µm; its binary cloud gate uses total liquid plus ice exceeding 1e-6 g/m³. The analysis labels whether a *saved diameter* equals a bound and whether the *serialized* total exceeds the threshold. Equality with a bound does not identify whether a prior clamp was active, and comparisons of rounded serialized inputs cannot recover pre-serialization branch values. QNICE words retain their raw checkpoint meaning: physical number units are unresolved. These observations do not validate host diagnostic radii or physical budgets.

## Provenance and reproduction

`extract.py` is a private-workspace extractor. It checks checkpoint identities in the original receipt and guard/pilot bindings, fixed profile selection, chunk captures, pilot archive hashes, channel and direct-call metadata. It reads the archived pilot case via the private `call.tar.gz` files and hashes each extracted file. The export was regenerated with this explicit-check extractor; its validation also runs under Python optimization. Original and guard case files remain as directories. **Important:** the original case input files were not individually hash-pinned at execution, and the pilot archive hashes were made after the calls; saved case inputs are retained evidence, not cryptographic proof of executed input bytes. Guard-only case inputs also receive extraction-time hashes. Public replay cannot reopen these private workspaces or independently certify execution. The public original baseline and pilot packet anchor their selected BTs, and the prior checkpoint-word packet anchors changed moments. The separate guard-only packet independently anchors guard BTs when the cross-check below is run; optical records remain bounded private exports. The complete prior baseline and pilot packet retain their own limitations and must be checked separately.

From the repository root:

```sh
python3 -m harness.evidence.native_qi_m0_cost_decomposition_2026-10-31.replay
python3 harness/evidence/east_optical_witness_2026-10-31/replay.py
python3 -m unittest discover -s harness/evidence/east_optical_witness_2026-10-31 -p 'test_*.py'
```

The nominal observation is 00:00 while the checkpoint is 00:01:00; individual pixel UTC is unverified. Existing RTTOV upper-background/model-top assumptions remain unchanged. This result is not a validation of boundary mass or number conservation, JVP/VJP, analysis acceptance or forecast skill.

The packet's source reference is repository commit `3816ba82`. The guard and pilot bindings both record `native_checkpoint_observation.py` SHA-256 `115bdf2b8db76b69852fe5262c01723d198660dc9be9f7361a0ed1023671ba14`, `native_observation_batch.py` SHA-256 `602ca5c676014d6f14b94682053b5ba249af3a6f0ce34e3af92e01199c51e0cb`, and `run_native_candidate_observation.py` SHA-256 `74b2ce806988761d1e162cd432e271faa4ce4bfac10817a4810e5a70ecb16fa5`; all three match that commit. The observation interpretation is source-checked against its native cloud builder, profile builder, cloud bridge and case writer. The source-tree digest in a saved binding is a recorded snapshot, not an individual executed-source proof for each optical module.

For the 82 changed native levels, the saved guard-to-pilot diameter categories differ on 29; none changes side of the threshold as computed from serialized liquid and ice values. This records output categories, not proof of internal clamp activation or an exact pre-serialization branch crossing. `analysis.json` gives each level's values and flags. At `(234,52)`, channel 10–16 Huber numerator changes are `+1.54215326, −1.07883603, −2.24164119, −1.13041158, +4.34900745, +5.34192646, +4.12197263`; summed over all ten they are `+10.73247167, +12.60376608, +6.73707901, +14.64147075, +25.98225973, +29.17382713, +24.04930616`. Divide these numerators by 377342 for their fixed-support cost contributions.

The separate QNC-guard-only packet supplies the third state's direct captures. Once both packets are present, verify that join using its pinned archive:

```sh
python3 harness/evidence/east_optical_witness_2026-10-31/crosscheck_qnc.py harness/evidence/native_qnc_guard_control_direct_m0_2026-10-31/chunk_artifacts.tar.gz
```

This required stacked-packet check verifies the archive SHA, binding, chunk receipt and capture hashes, direct/K metadata, selected flat rows and case ordinals, validity, quality and exact BTs at all ten profiles. The main replay likewise verifies the pilot control archive and case ordinals. The original ordinal is anchored only to the private result receipt at extraction time. The QNC packet's own complete replay remains necessary for its broader receipt and source checks.

The strengthened exporter used for the regenerated witness has SHA-256 `f4671bbc8836efdc2e934990329948ed1452d96b48ce050ff802d53ea52d9695`; the resulting `witness.json` SHA-256 is `a7748163ccf75252ec6fa8d0b38b26973dbceb8c5d24fef537ee3db356fc0136`. These are recorded export-time identities, not independent proof of execution.

`source_manifest.json` pins the exact six packet Python sources, including the executed extractor snapshot, replay, both cross-checks, analysis and tests. The official replay and separate guard cross-check check the fixed inventory and all six hashes before reading numeric evidence. The manifest is anchored by the enclosing repository revision; its self-hash is deliberately not included, and the manifest and source pins do not independently authenticate execution. The mutation suite verifies that both entry points reject an altered helper before numeric inputs are read.
