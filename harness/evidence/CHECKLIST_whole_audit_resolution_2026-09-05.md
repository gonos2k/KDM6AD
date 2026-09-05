# Whole-audit resolution checklist — 2026-09-05

This checklist resolves the code and evidence-contract findings against public
base `1a40d114` (PR #207), on `codex/resolve-ami-and-audit`. It preserves all
50 baseline IDs (A01–A10, B01–B36, H01–H04), five user AMI/observation items,
and the follow-up R rows. The original review covered 359 public source/test/build
files plus one historical metadata file and selected private KDM6 host seams.
This resolution changes the affected paths; it is not a proof of every possible
input, branch, platform, or meteorological outcome.

Implementation and independent Green/Red teams used `gpt-5.6-luna` / `xhigh`,
as required by AGENTS.md. Their first resolution reviews found the R items.
A final team retry hit the account usage limit; the parent resolved the last
counterexamples and ran the final tests. Do not describe those last parent
checks as completed independent team approval.

“Resolved in code” closes the stated reproducible defect with the evidence
below. “Contract-limited” closes an overclaim or states a caller precondition;
it does not certify the unresolved physics. Private source closure does not
establish a rebuilt host executable. No fresh WRF/MPI forecast, live RTTOV
assimilation, M1 transfer measurement, or M2 operand trace was run.

## Baseline findings

### A — priority findings

| ID | Contract to resolve | Resolution | Bounded acceptance check |
| --- | --- | --- | --- |
| A01 | State updates must apply the complete warm/cold, latent-heat, and paired moment equations; a cold-only mask must not leak into warm generated rates. | **Resolved in code; tests passed.** `oracle/kdm6/coordinator.py`, `libtorch/src/coordinator.cpp`; patch and valid-moment focused regression are present. | Run the focused Python/C++ route checks on a valid moment pair. Host f32/WRF bitwise campaigns are separate validation and are not required to close this oracle finding. |
| A02 | All-sky calls must pass the actual `p_lay` through the producer, shard, writer, and RTTOV boundary. | **Resolved in code; tests passed.** `oracle/kdm6/da_driver.py`, `oracle/kdm6/obs/allsky_shard.py`; patch and boundary witness are present. | Run the portable shifted-layer-pressure rejection. Live all-sky execution is a separate integration check. |
| A03 | Masked or nonfinite model-state cells must be rejected during both candidate selection and manifest storage. | **Resolved in code; tests passed.** `harness/g33_real_column_batch.py` plus shared NetCDF reader; patch and transport-edge regression are present. | Verify a masked fill cannot enter a produced fixture. Normal batch execution is a separate integration check. |
| A04 | The externally anchored C++ root must bind every internal contract, descriptor, container, and probe payload consumed by verification. | **Resolved in code; tests passed.** `harness/g33_bundle_io.py`; patch and publication tamper regression are present. | Verify a nested payload mutation fails under an unchanged external root. The real publication path is a separate integration check. |
| A05 | A requested module override must either compile those exact bytes through the full producer or be refused before build. | **Resolved in code; tests passed.** `harness/g33_refine_experiment.py`, `harness/g33_fortran/refine_build.sh`; patch and experiment regression are present. | Exercise accepted canonical and refused override decisions. Full overlay/build/manifest integration is a separate parent check. |
| A06 | Every ncmin locality consumer, including the local oracle, must use the same validated algorithm and experiment contract. | **Resolved in code; tests passed.** `harness/g33_ncmin_locality.py`; patch is present and a focused contract test is available. | Run all analysis consumers and prove the contract cannot be silently replaced by an unvalidated run or fixture. |
| A07 | MPI attribution requires requested and actual decomposition plus hashes of the active initial, boundary, and auxiliary inputs. | **Resolved in code; tests passed.** `harness/g33_mpi_divergence.py`, `harness/run_ss_case.py`; patch and run-identity regression are present. | Close the code identity gate with the portable producer/gate tests and mismatch refusal. MPI science remains a separately unrun validation; no MPI result is claimed here. |
| A08 | The new frozen dry-density contract must reach both live all-sky calls using the original background and forcing. | **Resolved in code; tests passed.** `oracle/kdm6/da_driver.py`, `oracle/tests/test_da_driver_osse.py`; patch is present and focused test changes are present. | Verify the portable boundary supplies the frozen density to both calls. Live RTTOV fixture execution remains a separate integration check. |
| A09 | Nonempty carry proof must validate identity, values, and the complete record universe on both loops. | **Resolved in code; tests passed.** `harness/make_g33m_evidence_artifact.py`; patch and evidence-edge regression are present. | Run nonempty equal and one-sided-missing carry cases through artifact generation and verification. |
| A10 | Refinement comparison must bind raw initial and forcing values, not only key sets and timing metadata. | **Resolved in code; tests passed.** `harness/g33_refine_analyze.py`; patch and experiment regression are present. | Verify changed atmospheric bytes are refused in the independent analyzer and in formal production bundles. |

### B — bounded implementation and evidence findings

| ID | Contract to resolve | Resolution | Bounded acceptance check |
| --- | --- | --- | --- |
| B01 | The parity helper must fail closed on intermediate `Inf` and schema asymmetry; this is distinct from the strict raw-bit gate. | **Resolved in code; tests passed.** `harness/compare_step1_kdm6_bitwise.py`, `libtorch/tools/kdm6_parity.py`, `harness/strict_bitwise_nc.py`; patch and evidence-edge regression are present. | Run finite/nonfinite and asymmetric-dimension cases and confirm no false `CONSISTENT` result. |
| B02 | `dt <= 0` must be an exact no-op before precision-changing conversions, while normal positive host timesteps retain the operational f32 contract. | **Resolved in code; tests passed.** `libtorch/src/runtime.cpp`, `libtorch/src/coordinator.cpp`, Python coordinator; patch and coordinator tests are present. | Run direct runtime/coordinator cases for negative, zero, and positive `dt`. Host-boundary integration is separate. |
| B03 | The v2 ABI must define which full, short, and unknown layouts may be inspected and what handle is returned on wrong-version errors. | **Resolved in code; tests passed.** `libtorch/bridge/kdm6_c_api.{h,cpp}`, `docs/PR2_ABI_V2_DESIGN.md`; patch and C ABI test changes are present. | Native c_abi execution tests the framed layouts and documented error/handle behavior; fresh-process symbol loading is a separate check. |
| B04 | The v2 public error contract must state that internal failures may discard internal outputs; allocation/copy order must not imply a stronger transaction guarantee. | **Contract-limited, reviewed.** `libtorch/bridge/kdm6_c_api.{h,cpp}`, ABI design document; the contract is narrowed accordingly. | Review the narrowed contract and verify callers do not rely on transactional output preservation. No new fault-injection guarantee is required, and the promise is not extended to v1/AD. |
| B05 | All shape products and allocation sizes must be checked in a wide integer domain before allocation. | **Resolved in code; tests passed.** `libtorch/include/kdm6/state.h`, `libtorch/src/state.cpp`, C ABI; patch and smoke/ABI test changes are present. | Exercise zero, negative, dimension, and product-overflow cases without attempting a huge allocation. |
| B06 | Full-domain H configuration must be deeply immutable, including nested arrays and tensors, before H/J evaluation. | **Resolved in code; tests passed.** `oracle/kdm6/da_fulldomain.py`; patch and DA identity regression are present. | Mutate nested inputs after signature creation and verify both the signature and frozen computation remain unchanged in every caller. |
| B07 | Empty observations are valid only after model-grid validation; a valid empty payload must return typed empty indices/distances. | **Resolved in code; tests passed.** `oracle/kdm6/obs/obs_ingest.py`; patch and `test_audit_obs_boundaries.py` are present. | Run empty-valid and empty-invalid-grid cases through the public ingestion boundary. Caller-wide integration is a separate parent check. |
| B08 | Derived pressure, Exner, density, height, and layer thickness must satisfy finite and physical-domain checks; invalid pressure must not be rescued by a log clamp. | **Resolved in code; tests passed.** `oracle/kdm6/obs/model_profile_builder.py`, `oracle/kdm6/io/frame_reader.py`; patch and observation-boundary regression are present. | Verify rejects at raw and derived boundaries. Coverage of every production profile caller is a separate integration check. |
| B09 | RTTOV ASCII parsing must consume complete tokens, reject `BAD` or malformed rectangular data, and preserve separate overflow-quality policy. | **Resolved in code; tests passed.** `oracle/kdm6/obs/_rttov_reference/rttov_ascii.py`; patch and observation parser regression are present. | Run truncated, `BAD`, nonfinite, and valid records through the parser and its caller. |
| B10 | Duplicate channel files must be rejected rather than silently using the last writer. | **Resolved in code; tests passed.** `oracle/kdm6/obs/gk2a_l1b.py`, `oracle/kdm6/obs/gk2a_l1b_fd.py`; patch and existing/new GK2A tests are present. | Exercise duplicate, missing, and complete channel sets for KO and FD readers. |
| B11 | Cached mappings need an explicit footprint/coordinate identity contract; equal length alone cannot prove reuse is valid. | **Contract-limited, reviewed.** Bounded policy closure is available under the documented same-coordinate/order caller precondition; the exact-coordinate/order precondition and all examined public callers agree. | Document the precondition and inspect all callers that reuse the mapping. Generic same-length/different-footprint rejection is outside this bounded contract unless the policy changes. |
| B12 | Sensitivity sharding must represent and validate `xland` and `ncmin` where the contract says they affect the computation. | **Resolved in code; tests passed.** `oracle/kdm6/da_parallel.py`; patch and DA identity regression are present. | Verify fields survive shard construction, slicing, and recombination, including absent/invalid dimensions. |
| B13 | Final public manifests must be redacted only after outputs and drift records are complete, and both public copies must describe that same final payload. | **Resolved in code; tests passed.** `oracle/scripts/run_fulldomain_lc05.py`; patch and DA artifact tests are present. | Build a final artifact with outputs/drift, then compare redacted manifests and their hashes after finalization. |
| B14 | Synthetic impact comparison must run from a public checkout without hashing private LC05 files; private provenance is optional and explicit. | **Resolved in code; tests passed.** `oracle/scripts/p0_4b1_impact_comparison.py`; patch is present. | Run synthetic-only mode in a public checkout and separately verify explicit private mode fails clearly when assets are absent. |
| B15 | The `dend` documentation and direct fixture must use `rho`, as production does; the separate unresolved `nr/ni` number-unit question (`#/kg_d` versus `#/m^3`) must not be folded into this row. | **Resolved in code; tests passed.** `oracle/kdm6/sedimentation.py` and focused sedimentation tests; docs/fixture correction patch is present, reviewed with the density/surface counterexample. | Run the direct regression and review the docs/fixture against the production `rho` consumer. This bounded row can close without a WRF campaign; `nr/ni` units remain a separate science decision. |
| B16 | G33N upper `rho` and `dz` must be positive and finite before being used as scientific weights. | **Resolved in code; tests passed.** `harness/g33_number_transport.py`; patch and transport-edge regression are present. | Exercise zero, negative, nonfinite, and valid records through parser, ledger, and report. |
| B17 | Number-basis recovery must not infer a transfer from only the first call when a stream contains multiple calls/substeps. | **Resolved in code; tests passed.** `harness/g33_number_basis.py`, `harness/g33_number_transport.py`; patch and transport regression are present. | Verify multi-call and multisubstep streams are refused or explicitly represented, while the single-call contract still passes. |
| B18 | Halo evidence must retain repeated rank copies for comparison and reject malformed or empty dumps as evidence. | **Resolved in code; tests passed.** `harness/g33_dyn_probe.py`; patch and transport-edge regression are present. | Run duplicate-rank, malformed, empty, and valid halo cases through the loader and divergence report. |
| B19 | Even-sample median must average the two middle values, rather than selecting the upper middle. | **Resolved in code; tests passed.** `harness/g33_defect_magnitude.py`; patch and transport regression are present. | Verify `[0.1, 0.3]` gives `0.2` and retain odd-sample behavior. |
| B20 | Empty populations, missing basis values, and `pii`-only forcing must report unavailable rather than crash or become numeric zero. | **Resolved in code; tests passed.** `harness/g33_dual_ledger.py`, `harness/g33_number_basis.py`, `harness/g33_refine_analyze.py`, `harness/g33_number_transport.py`; patch and transport/experiment tests are present. | Run each no-data combination through ledger, ratio, and final report paths. |
| B21 | Real-column density comparisons must declare whether frame zero or a sibling terminal frame is intended. | **Resolved in code; tests passed.** `harness/g33_real_column_density.py`; patch and transport regression are present. | Verify frame metadata and selection for single-frame and multi-frame inputs; retain the single `wrfinput` result. |
| B22 | The cold-gate instrumentation label must use the same boundary as the runtime (`>= 0`), including the equality case at `t0c`. | **Resolved in code; tests passed.** `harness/g33_overlay/coordinator.cpp.overlay`; patch is present. | Build/generate the overlay and check the equality boundary in emitted labels and replay records. |
| B23 | G33F duplicate `INIT` and future versions, and G33R duplicate `FIXTURE`, must be rejected by the parser/protocol gate. | **Resolved in code; tests passed.** `harness/g33_fortran/g33_fortran_dump.py`, `harness/g33_fortran_bundle_io.py`, `harness/g33_fortran/refine_build.sh`; patch and generator tests are present. | Run duplicate, future, malformed, and valid protocol records through both parser and bundle verification. |
| B24 | C++ custom segment durations must be finite, strictly positive, uniform under the current header, and consistent with the fixture total/header. | **Resolved in code; tests passed.** `harness/g33_overlay/abc_driver.cpp`, `g33_refine_driver.cpp`, build scripts; patch and generator regression are present. | Exercise `[-100,200,200]`, `[250,50]`, empty, nonuniform, and valid schedules through build and header checks. |
| B25 | The CLI advertised fixture registry and the set actually accepted by build scripts must be identical and fail closed. | **Resolved in code; tests passed.** `harness/g33_overlay/*_build.sh`, overlay drivers; patch and generator regression are present. | Registry selection tests and syntax compilation of both drivers for both added fixtures pass; the canonical driver is linked and executed separately. |
| B26 | Comparator and producer stage order must be recorded accurately; differing identities must not be given a falsely precise earliest location. | **Resolved in code; tests passed.** `harness/g33_expectation.py`, `harness/compare_substep_stage.py`; patch and experiment regression are present. | Run init→call and call→init permutations and verify refusal/qualified attribution when both differ. |
| B27 | The factorial `screens=` parameter must be applied or rejected as unsupported; silently ignoring a requested screen is invalid. | **Resolved in code; tests passed.** `harness/g33_factorial.py`; patch and experiment regression are present. | Compare screened and unscreened requests and verify the CLI advertises the actual supported behavior. |
| B28 | Unsupported NetCDF dtypes, schema mismatches, zero-cell records, and empty evidence need explicit decision-census semantics; an empty equality set is not a pass. | **Contract-limited, reviewed.** `harness/gateb_g3_check.py`, `harness/g33_fortran/g33_fortran_dump.py`, self-check paths; patch and evidence-edge tests are present. | Run unsupported, empty, zero-cell, and valid evidence and inspect exit class plus census. |
| B29 | Recertification must bind the entire declared output stream; multiple forecast files must fail the one-file contract instead of validating the first only. | **Resolved in code; tests passed.** `harness/build_c4_evidence.py`; patch and run-identity regression are present. | Verify exactly one supported file, its SHA, full duration, and refusal with rollover/additional files. |
| B30 | Legacy self-check must state the actual update/outflow and surface operand provenance; formal replay and bundle gates retain their separate scope. | **Contract-limited, reviewed.** `harness/g33_selfcheck.py`, `harness/g33_surface_selfcheck.py`; patch and evidence tests are present. | Run complete and truncated/misbound records and verify provenance failures; do not merge this with formal replay claims. |
| B31 | Standalone artifact generation must label dirty-tree state consistently with gateb decisions. | **Resolved in code; tests passed.** `harness/gateb_g3_check.py`, `harness/g33_selfcheck.py`, `harness/g33_surface_selfcheck.py`; patch and evidence tests are present. | Generate clean, dirty, and rejected artifacts and compare labels with gate outcomes. |
| B32 | Commit and source-digest fields require strict format validation, and malformed manifests must return a stable evidence error. | **Resolved in code; tests passed.** `harness/g33_build_provenance.py`, `harness/g33_result.py`, bundle readers; patch and publication-binding tests are present. | Run malformed JSON, duplicate keys, bad commit/digest, missing file, and valid manifests through every verifier. |
| B33 | SS runner restoration and lock release must happen on success and every exception path. | **Resolved in code; tests passed.** `harness/run_ss_case.py`; patch and run-identity regression are present. | Inject restoration failure and verify lock release/archive cleanup, then run the normal path. |
| B34 | Offline substep comparison must be labeled as comparison-only when no producer/binary attestation is present. | **Contract-limited, reviewed.** `harness/compare_substep_stage.py`, self-check/report paths; patch and evidence tests are present. | Verify fresh producer-attested and offline inputs receive distinct verdicts and wording. |
| B35 | Full-domain `connected_fields` metadata must distinguish the global union from fields actually connected for each observation time/partition. | **Resolved in code; tests passed.** `oracle/kdm6/da_fulldomain.py`; patch and DA identity regression are present. | Run multi-time and partitioned observations and verify per-position metadata plus global union. |
| B36 | Direct helpers must reject nonfinite/invalid `xland`, dimensions, subcycle inputs, and overflow-prone exponential parameters within their declared support. | **Resolved in code; tests passed.** `libtorch/src/runtime.cpp`, `libtorch/include/kdm6/runtime.h`, coordinator/state tests; patch and native test changes are present. | Exercise direct helper boundaries and overflow cases, then verify supported runtime/host calls remain unchanged. |

### H — private host findings

The host tree and `host_fortran/` are outside this public checkout. Private
source/preprocess patches may be present in the canonical host work, but no
public diff is evidence that a host binary changed. Source/preprocess closure
and binary/build provenance are separate claims.

| ID | Contract to resolve | Resolution | Bounded acceptance check |
| --- | --- | --- | --- |
| H01 | Host `237/337` effective-radius negotiation and FARMS selector must be checked at the actual host call boundary, without broadening the finding to public `37/137` or the ABI. | **Source-only resolved.** Active source/hash witness and preprocess syntax checks passed; no host build/install/run. | Parent review plus source/preprocess syntax checks close the bounded code item. A host build or selector campaign is separate and must not be implied. |
| H02 | Archived `host_fortran` sources must be distinguished from the actual host shim, driver, init, and binary provenance. | **Source-only resolved.** Active source/hash witness and preprocess syntax checks passed; no host build/install/run. | Verify the source/archive labels and retain the separate binary/build provenance limitation; do not claim an archive-to-binary match. |
| H03 | QIB must not reuse P3 metadata incorrectly, and post-bridge checks must cover both NaN and Inf for the declared output set. | **Source-only resolved.** Active source/hash witness and preprocess syntax checks passed; no host build/install/run. | Parent review plus source/preprocess syntax checks close the bounded code item. A host finite/nonfinite campaign remains separate. |
| H04 | `INTENT(OUT)` `rhox` must not be read before initialization; later reset behavior must be evaluated separately from the static defect. | **Source-only resolved.** Active source/hash witness and preprocess syntax checks passed; no host build/install/run. | Parent review plus source/preprocess syntax checks close the bounded code item. Runtime impact/build evidence remains a separate limitation. |

## User-requested observation and AMI additions

These five rows are additional scope and are not substituted for any baseline
ID. The measurement is an independent audit artifact; it does not establish a
production forecast, RTTOV, or data-assimilation rerun.

| ID | Requested contract | Resolution | Bounded acceptance check |
| --- | --- | --- | --- |
| U01 | AMI quality bits are bits 14–15, with DN extracted from the channel's declared valid-width word. | Resolved: literal DQF 0/1/2/3 and combined embedded/masked NetCDF ingestion pass. | Run KO and FD readers through production ingestion and verify masked values and quality flags remain separate. |
| U02 | DN width must be read per channel from `number_of_valid_bits_per_pixel`, validated in the supported 11–14 range, and never assumed to be a universal 13 bits. | Resolved: all 32 KO/FD variable attributes inspected; widths 11–14 passed explicitly. | Verify all 16 KO and 16 FD channel records against their file attributes and calibration path. |
| U03 | Actual KO/FD data must be measured, rather than inferred from a synthetic word or calibration table. | Measured: production sample and full-raster summary are public reports under docs/reports; calibration/source/file hashes recorded. | Parent review should verify the tracked report is the public measurement record and keep any full-raster supplement local. No assimilation or forecast rerun is required to close this measurement row, and none is claimed. |
| U04 | Empty collocation must validate a nonempty model grid and then return typed empty indices/distances without `torch.cat([])` failure. | Resolved: empty-valid and empty-invalid-grid regressions pass through payload conversion. | Run empty, invalid-grid, and normal observations through all callers and record the focused test result. |
| U05 | The physically nearest candidate is selected by actual great-circle distance before usability filtering; an unusable nearest candidate may therefore preempt a usable second candidate. | Contract-limited: documented distance-first selection retained; no nearest-usable reassignment. | Parent review should confirm the documented policy and examined callers agree. This row requires policy confirmation, not a new regression or nearest-usable fallback. |

## Science and policy items intentionally left open

The following items must remain visible when this checklist is updated:

* **M1:** the applied 10-minute WRF transport residual has not been measured
  here. **M2:** the first negative QIB operand has not been instrumented here.
  Neither is resolved by a unit test or by the AMI work.
* The unresolved `nr/ni` number-unit question (`#/kg_d` versus `#/m^3`) and any
  related number/column convention require a declared meteorological contract
  and host measurement. They must not be silently “fixed” by changing a local
  fixture or by relabeling a diagnostic. The B15 `dend=rho` docs/fixture error
  is a separate bounded fix.
* Legacy `ncmin` scalar/last-column compatibility remains an intentional or
  contract-limited behavior until its producer/consumer and unit policy are
  explicitly changed and measured. It is not a blanket resolution of the
  number-transport findings.

The validation record below covers the bounded checks. Unrun integration and
physical measurements remain separate from code closure.

## Re-review additions from the current resolution reports

These rows capture accepted, actionable additions from the current green/red
resolution reports. They supplement the 50 baseline IDs and do not replace or
reopen them. The parent checked the final fixes and reran the local suites recorded below.
No WRF, MPI, host-build, forecast, or assimilation pass is implied.

| R ID | Accepted addition | Resolution | Bounded recheck or closure condition |
| --- | --- | --- | --- |
| R01 | AMI `uint16` endianness must be normalized before bit extraction in both KO and FD readers. | Resolved: unsigned 16-bit byte order normalized; literal and NetCDF cases pass. | Run the big-endian KO/FD boundary cases and compare DN, quality, and masking independently. |
| R02 | AMI stride must be a positive integer; zero, negative, and boolean stride values must fail at the reader boundary. | Resolved: positive integer strides enforced by the shared helper. | Exercise invalid and valid stride metadata in both reader paths. |
| R03 | KO/FD channel files must agree on declared grid/geolocation attributes and shape before combining data. | Resolved: per-channel shape/geolocation equality checked before combining. | Supply mismatched attributes and dimensions and verify deterministic refusal. |
| R04 | KO/FD resolver ambiguity must fail closed rather than selecting one of multiple channel files. | Resolved: multiple resolver hits fail explicitly. | Exercise two resolver hits plus missing and single-hit cases. |
| R05 | RTTOV `RADIANCE%QUALITY` overflow must be rejected as nonfinite at the parser boundary. | Resolved: nonfinite RTTOV quality refused; finite nonzero quality retained. | Run overflow, nonfinite, malformed, and valid quality records through the parser/caller. |
| R06 | Public full-domain observation evaluation must not expose a mutable `mask` alias that changes the frozen H/J contract. | Resolved: exposed mask is a clone of the captured mask; mutation regression passes. | Either freeze/copy the exposed mask or enforce a documented immutable boundary, then run mutation/signature regression. |
| R07 | Arbitrary Python callback closure state remains an explicit caller contract boundary. | Contract-limited: callbacks must remain stable/stateless for evaluator lifetime. Closure state is caller-owned; no generic cloning claim. | Require a stable, importable, provenance-attested callback or choose an enforceable minimal guard; document the caller limitation. |
| R08 | Generic DA/all-sky adapters must carry declared number-floor controls rather than silently using one default. | Resolved: frozen ncmin controls reach generic cloud H and background trajectory. | Exercise land/sea/all-sky floor controls and verify the generic API's serialized contract. |
| R09 | Generic DA paths must preserve and validate `xland` through evaluation and shard boundaries. | Resolved: captured xland is cloned, validated and fingerprinted. | Mutate or mis-shape `xland` after capture and verify refusal or stable results. |
| R10 | Serialized full-domain artifacts must retain connected-field metadata needed to distinguish the global union from fields connected at each observation position. | Resolved: JSON-safe per-position/partition connected-field metadata is serialized. | Inspect `run_fulldomain_analysis` output and add/verify per-time/partition connected metadata without claiming a direct-evaluator gap. |
| R11 | The final public JSON hash must be computed over the cycle-free finalized public payload. | Resolved: canonical public JSON hash scope is machine-labelled and independently recomputed by the test; NPZ uses file-byte SHA. | Build a finalized artifact, recompute the public digest independently, and verify report/sidecar agree. Historical artifacts remain unchanged. |
| R12 | Arbitrary-root redaction must remove absolute path fragments recursively from all public fields, including argv, environment, drift, and output records. | Resolved: finalized manifest recursively scrubs arbitrary-root paths while preserving URLs. | Inject nested root paths and verify the public payload contains no absolute fragments. |
| R13 | Redaction must refuse key collisions instead of silently overwriting a public field. | Resolved: redacted-key collisions raise an error. | Exercise colliding redacted keys and verify a stable refusal. |
| R14 | MPI experiment identity must publish explicit validity/status evidence before divergence analysis. | Resolved: failed/unstable producer metadata is refused before comparison. | Validate accepted, failed, and missing status records; do not infer an MPI result without a run. |
| R15 | MPI binary stability must compare before/after digests and report the stable decision. | Resolved: before/after stability declarations and hashes are checked. | Exercise replacement and unchanged binary cases and verify the status record. |
| R16 | MPI input identity must reject omitted ordinary namelist assignments and ambiguous multidomain/default-name schemas. | Resolved: unsupported omitted/default or multidomain forms are refused, not inferred. | Run explicit canonical, omitted-default, and ambiguous multidomain cases through the identity gate. |
| R17 | Auxiliary parity must compare the complete declared initial-condition field set, including hydrometeor fields, not only `T`/`QVAPOR`. | Resolved: every declared REQUIRED field is compared at frame zero. | Mutate each IC field independently and verify a mismatch is reported. |
| R18 | Auxiliary parity must reject an empty or wrongly oriented `Time` dimension and enforce the declared schema before frame zero. | Resolved: exact dimension identity and nonempty Time checked before access. | Exercise empty, reordered, mismatched, and valid schemas. |
| R19 | G3 partial census must be labelled as partial or bound to an expected census; a single nonempty legacy record must not imply complete coverage. | Contract-limited: legacy diff listings report PARTIAL/comparison_only, decision=false; no invented census. | Verify the report states its coverage and does not issue a formal whole-census pass from an empty equality set. |
| R20 | Per-rank duplicate dynamics records must be rejected before transport aggregation. | Resolved: per-file duplicate records and malformed binaries rejected; repeated cross-rank halo copies remain allowed. | Exercise duplicate identity, malformed, empty, and valid per-rank records. |
| R21 | Strict schedule parsing must accept the declared object form and reject arrays, duplicate keys, and malformed schedule records. | Resolved: strict object/duplicate-key schedule parsing and typed failures tested. | Run accepted and refused schedule fixtures through the four-case gate. |
| R22 | Covered publication/provenance/result readers must convert deep-JSON recursion failure into a typed evidence error. | Resolved: covered readers include g33_dump header/key JSON; deep recursion becomes typed evidence error. | Exercise deeply nested and cyclic/malformed payloads through each covered reader and preserve bounded scope. |
| R23 | Streaming hashes must detect file growth/truncation while hashing and retain the declared root-digest binding. | Resolved: bounded streaming retains framed digest; growth/truncation and symlinks refused. | Exercise stable, grew, truncated, and symlink/path cases and verify refusal/status. |
| R24 | Python control scaling must define the supported domain of `exp(alpha)` and handle out-of-domain parameters explicitly. | Resolved: finite alpha must yield a positive finite exp factor in its dtype; valid gradients preserved. | Decide and test the declared boundary for large/nonfinite `alpha`; do not claim a production failure from the direct helper alone. |
| R25 | Python `compute_loops_max` must resolve its negative `dtcldcr` behavior consistently with the declared direct-helper contract. | Resolved: finite elapsed time, positive denominator and INT_MAX range checked before casting. | Choose refusal or documented support and add the narrow helper regression; keep this separate from the C++ runtime boundary. |
| R26 | Complete-rain evaporation transfer ordering must be checked across Python and C++ before asserting parity for nonzero cold-rate cases. | Resolved: paired nr transfers to nccn before cold/D5/conservation, matching the Fortran/C++ boundary. Mixed-phase qg/bg=200 counterexample passes. | Compare the transfer/zeroing boundary on a nonzero cold-rate fixture; do not claim forecast or final-field science validation. |
| R27 | Private H04 conservative cleanup is source/preprocess resolved, with build provenance kept separate. | Source-only resolved: active conservative pre-reset rhox read removed; private hash/source/syntax checks passed. | Review the private source/preprocess diff; no host build or runtime claim follows. |
| R28 | Historical public C4 manifests retaining an old source SHA must not be reissued or relabelled as current without a new build. | Contract-limited: historical C4 source SHA remains historical. Reissue requires a fresh build and provenance; no current recertification claimed. | Preserve source-snapshot versus binary/toolchain provenance and issue a new manifest only from a rebuilt, fully hashed artifact. |

| R29 | Legacy G33R without geometry must not crash after advertising partial tables. | Resolved: CLI returns explicit geometry unavailable (exit 2); the archive parser remains supported. | Real parsed legacy files and CLI regression. |
| R30 | Signed-zero input words must remain distinct in factorial and number-budget comparisons. | Resolved: shared f32 bit conversion preserves +0/-0. | Literal 00000000 versus 80000000 through both consumers. |
| R31 | Standalone factorial must bind G33N forcing to G33R inventory operands. | Resolved: shared require_window_forcing reused by producer and consumer, at recorded precision. | Real combined streams with only upper density changed are refused. |
| R32 | Density coefficients may not publish NaN from invalid forcing. | Resolved: raw and derived forcing checked; the separate invalid-number census retains explicit nonfinite counts. | Actual synthetic NetCDF zero/negative/NaN/Inf pressure and existing census tests. |
| R33 | Finite raw inputs can produce invalid derived fixture forcing. | Resolved: p/dz/rho/Exner domains and f32 representation checked before replacing the manifest; fixture loader rejects bad decoded words. | Flat geopotential/zero pressure/mass/DNW and invalid xland preserve the previous manifest. |
| R34 | C++ nsplit must consume the entire integer token. | Resolved: from_chars rejects trailing junk, whitespace, signs, zero and overflow. | Real compiled driver negative and positive cases. |
| R35 | Absolute number response units must state their assumed basis. | Contract-limited: factorial and dual ledger explicitly mark the dry-specific assumption; number-unit physics remains open. | Output metadata and documentation review; numerical formulas unchanged. |
| R36 | Direct sedimentation helpers must not broadcast a different column grid. | Resolved: Python/C++ metadata-only shape checks cover main and ice substeps. | Malformed work/forcing/mstep and empty-grid regressions; native ctest and AD checks. |

| R37 | CI must execute the synthetic NetCDF paths used to validate these fixes. | Resolved configuration: netCDF4 1.7.4 pinned in both harness and oracle jobs; latest CI run verifies the environments. | Initial harness CI failed during collection without netCDF4; the dependency is installed rather than bypassing the tests. |

### Open measurements kept separate from the re-review fixes

* **Number units:** `nr`/`ni` (`#/kg_d` versus `#/m^3`) and the host/kernel number
  convention remain open until the meteorological contract and a host
  measurement are supplied.
* **M1/M2:** the applied transport residual and first surviving negative QIB
  operand remain unmeasured; no local patch closes either item.
* **D4:** the one-ULP freeze/heat `T` difference remains open for operand and
  operation-order measurement. It is not a reason to claim an all-science
  failure or to silently relax the parity gate.

## Validation of this resolution

- Public oracle: `cd oracle && python3 -m pytest -q` — **958 passed, 26 skipped**.
- Portable harness: `python3 -m pytest -q harness/tests` — **1,565 passed, 59 skipped, 308 deselected**. The initial run exposed an overbroad number-census guard; the final run passed after restoring its explicit invalid-value counting contract.
- Final public-hash/finalizer follow-up: **47 passed, 2 skipped**.
- Shipped native build: `cmake --build ... --parallel 2`, then ctest — **17/17 passed**. The nine-export C ABI surface is unchanged.
- C++↔oracle regression: **4 passed**. Recompiled standalone refinement CLI: **10 passed**, using its default 20-second fixture (`--segments=10,10`); malformed `nsplit` and schedules refused. An initial parent invocation supplied a 300-second schedule to that 20-second fixture and was correctly refused; this was an invocation mismatch, not a weakened test.
- Static overlay verification: all four source pins and macro-off text identity pass.
- Actual G3.3 gate on code commit `2b2f7a8`: substep, surface (including the density operand, 10 checked fields), fourcase fixture binding and all four C++ A/B/C algorithm/case pairs **PASS with strict raw-bit equality**. The first run exposed a stale 9-field shell pin, which was corrected to the verified 10-field set; no numerical tolerance changed.
- AMI synthetic NetCDF/literal tests and the KO/FD production sample are described in [AMI_INPUT_CONTRACT.md](../../docs/AMI_INPUT_CONTRACT.md). See the [production sample](../../docs/reports/ami_bit_decode_20260905.json) and [full-raster summary](../../docs/reports/ami_bit_decode_full_raster_summary_20260905.json). The two reports have different selection and provenance scopes.
- Private source witness covers all four KDM6 scheme paths and active conservative rhox cleanup. GNU Fortran preprocess/syntax checks passed; generated private variants were not hand-edited or rebuilt. Old C4 manifests are not current build evidence.

Additional unclosed observations remain scoped: historical Python/C++ inactive-BRS and HM threshold differences need a reachable precision-specific trace before a policy change; partial private callers/ProgB INTENT(OUT) assumptions and RWORDSIZE=4 remain conditional host API limitations. None is evidence of a newly measured operational forecast failure. M1, M2, number units and D4 are open as stated above.
