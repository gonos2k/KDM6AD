# PR #208 이후 감사 해소 체크리스트

기준 main `27cfef11a89fd9e4a08cf262c0c9b7eb4602a4ab`.
90개 원장 행은 중복·별칭·기각된 주장도 보존한 검토 기록이며 결함 90개라는 뜻이 아니다.
수학적 대상, 단위, 적용 경계와 실제 증거를 먼저 확인했다. 원래 375개 검토 경로와
추가 linker 2개 경로의 Green/Red 감사를 바탕으로 수정하고, 변경 경로의 독립 재검토에서 발견된 추가 연결 오류도 수정했다.
팀은 Luna xhigh, 동시에 최대 7개 에이전트다.

## 원래 검토 항목

| 행 | 원래 ID | 원래 검토 대상 | 상태 | 현재 근거 |
|---|---|---|---|---|
| 1 | DA-CORE-RED-01 | t=0 observation covector is added after the final per-step active-field projection, so a returned x0 adjoint can contain inactive fields and legacy minimization can update them. | 수정 · 검증 완료 | [oracle/kdm6/da_window.py](../../oracle/kdm6/da_window.py) · [oracle/kdm6/da_linearization.py](../../oracle/kdm6/da_linearization.py) |
| 2 | DA-CORE-RED-02 | Partition-composed x_a is passed to build_cvt_record, whose ratios and creation counts describe the diagonal CVT only; partition movement is therefore misattributed. | 수정 · 검증 완료 | [oracle/kdm6/da_minimizer.py](../../oracle/kdm6/da_minimizer.py) · [oracle/kdm6/da_dual.py](../../oracle/kdm6/da_dual.py) |
| 3 | DA-CORE-UNIT-01 | The frozen dual adapter accepts scalar sigma for a mixed BT(K)/reflectance/BT(K) observable and silently underweights the solar slot. | 수정 · 검증 완료 | [oracle/kdm6/da_dual.py](../../oracle/kdm6/da_dual.py) · [oracle/kdm6/obs/rttov_case_writer.py](../../oracle/kdm6/obs/rttov_case_writer.py) |
| 4 | DA-EXEC-RED-01 | Full-domain clear and all-sky H/K paths collocate by lat/lon but drop per-observation geometry and surface/near-surface state; fixture auxiliary defaults can then be reused for all profiles. This blocks a location-specific real-observation H claim, while existing explicitly labeled pathology/conserving stress artifacts remain valid for their stated purpose and no measured BT/forecast error is claimed. | 코드 수정 · 실측 범위 별도 | [oracle/kdm6/da_fulldomain.py](../../oracle/kdm6/da_fulldomain.py) |
| 5 | DA-EXEC-RED-02 | Relative RTTOV executable tokens are hashed relative to the parent process CWD although run.sh executes with out/ as CWD. | 수정 · 검증 완료 | [oracle/scripts/run_fulldomain_lc05.py](../../oracle/scripts/run_fulldomain_lc05.py) |
| 6 | DA-EXEC-RED-03 | Final-time OSSE observations use forcings[-1] when t equals the final state time. With T interval forcings this is a reasonable piecewise-constant endpoint convention and truth/innovation use the same H; the evidence does not establish a wrong-time numerical result under the current contract. | 계약 범위 유지 | [oracle/kdm6/da_driver.py](../../oracle/kdm6/da_driver.py) · [oracle/kdm6/da_window.py](../../oracle/kdm6/da_window.py) |
| 7 | DA-EXEC-RED-04 | Public OSSE and shard APIs normalize every observation time with int(t), moving non-integral requested times to a different state/checkpoint. | 수정 · 검증 완료 | [oracle/kdm6/da_driver.py](../../oracle/kdm6/da_driver.py) · [oracle/kdm6/da_parallel.py](../../oracle/kdm6/da_parallel.py) |
| 8 | DA-EXEC-RED-05 | The optional top-profile blend enters when t_ref is present and indexes q_ref unconditionally; q_ref alone is silently ignored. | 수정 · 검증 완료 | [oracle/kdm6/da_driver.py](../../oracle/kdm6/da_driver.py) |
| 9 | DA-EXEC-RED-06 | Direct ShardSpec construction permits duplicate indices within one shard; reassembly overwrites one duplicate and returns a finite wrong adjoint. | 수정 · 검증 완료 | [oracle/kdm6/da_parallel.py](../../oracle/kdm6/da_parallel.py) |
| 10 | DA-EXEC-RED-07 | Replay resume checks Python float type but not finiteness, so NaN/Inf metric payloads can be restored and serialized. | 수정 · 검증 완료 | [oracle/scripts/p0_4b1_lc05_replay_audit.py](../../oracle/scripts/p0_4b1_lc05_replay_audit.py) · [oracle/tests/test_review208_da_execution.py](../../oracle/tests/test_review208_da_execution.py) |
| 11 | DA-EXEC-RED-08 | Replay pressure ordering is enforced by a bare assert removed under python -O, while optimization state is absent from provenance. | 수정 · 검증 완료 | [oracle/scripts/p0_4b1_lc05_replay_audit.py](../../oracle/scripts/p0_4b1_lc05_replay_audit.py) · [oracle/tests/test_review208_da_execution.py](../../oracle/tests/test_review208_da_execution.py) |
| 12 | DA-EXEC-RED-09 | Impact/replay scripts snapshot hashes at startup and do not check end-of-run drift, so later reads may not match published provenance. | 수정 · 검증 완료 | [oracle/scripts/p0_4b1_lc05_replay_audit.py](../../oracle/scripts/p0_4b1_lc05_replay_audit.py) · [oracle/scripts/p0_4b1_impact_comparison.py](../../oracle/scripts/p0_4b1_impact_comparison.py) |
| 13 | DA-EXEC-RED-10 | Artifact schema migration renames by assignment without checking whether the new key already exists, silently losing the existing value. | 수정 · 검증 완료 | [oracle/scripts/p0_4b2_migrate_artifact_schema.py](../../oracle/scripts/p0_4b2_migrate_artifact_schema.py) · [oracle/tests/test_review208_da_execution.py](../../oracle/tests/test_review208_da_execution.py) |
| 14 | DA-EXEC-G-001 | Followup supersedes the initial P2: evaluator n_valid counts radiance plus pseudo objective terms, while top-level report n_valid counts BT/radiance coverage. This is naming/schema ambiguity, not an optimizer or objective undercount. | 코드 수정 · 실측 범위 별도 | [oracle/kdm6/da_fulldomain.py](../../oracle/kdm6/da_fulldomain.py) |
| 15 | DA-EXEC-G-002 | All-sky worker prepends oracle/tests to sys.path. No current shadowing import or numerical behavior change was reproduced; this remains structural reproducibility risk. | 코드 수정 · 실측 범위 별도 | [oracle/kdm6/da_fulldomain.py](../../oracle/kdm6/da_fulldomain.py) |
| 16 | P2-OBS-01 | Direct pack/operator accepts P_HALF with three profile rows for T/Q with two profiles and forwards the unpaired pressure row to a runner. | 수정 · 검증 완료 | [oracle/kdm6/obs/rttov_input_builder.py](../../oracle/kdm6/obs/rttov_input_builder.py) · [oracle/kdm6/obs/rttov_case_writer.py](../../oracle/kdm6/obs/rttov_case_writer.py) |
| 17 | P2-OBS-FRAME-XLAND-CATEGORY | Frame reader accepts finite XLAND values outside WRF {1,2}; its fallback classifies all values except 1 as water and can synthesize wrong CCN. | 수정 · 검증 완료 | [oracle/kdm6/io/frame_reader.py](../../oracle/kdm6/io/frame_reader.py) · [oracle/tests/test_review208_observation_boundaries.py](../../oracle/tests/test_review208_observation_boundaries.py) |
| 18 | P2-OBS-EMPTY-RTTOV-CASE | Direct serializer/writer accepts empty profile/layer axes and can create a zero-profile, zero-channel case that its parser rejects. | 수정 · 검증 완료 | [oracle/kdm6/obs/rttov_input_builder.py](../../oracle/kdm6/obs/rttov_input_builder.py) · [oracle/kdm6/obs/rttov_case_writer.py](../../oracle/kdm6/obs/rttov_case_writer.py) |
| 19 | RT-RED-01 | Python final ice limiter uses scalar c.NCMIN while C++ uses per-cell ncmin_tensor. Evidence is valid, but the authoritative mathematics note documents this as the current Python/C++ operational boundary. | 계약 범위 유지 | [docs/KDM6AD_differentiable_mathematics.md](../../docs/KDM6AD_differentiable_mathematics.md) |
| 20 | RT-RED-02 | nccn=None leaves nr after complete evaporation in the optional component helper. The normal driver always threads nccn and performs the paired zero/addback transfer; the helper is documented as a partial bare-state boundary. | 계약 범위 유지 | [docs/KDM6AD_differentiable_mathematics.md](../../docs/KDM6AD_differentiable_mathematics.md) |
| 21 | RT-RED-03 | C++ Handle::jvp accepts GraphOptions.create_graph but hardcodes create_graph=false for the second gradient, so a requested higher-order tangent is detached. | 수정 · 검증 완료 | [libtorch/include/kdm6/runtime.h](../../libtorch/include/kdm6/runtime.h) · [libtorch/src/runtime.cpp](../../libtorch/src/runtime.cpp) |
| 22 | RT-RED-04 | Direct C++ kdm6_fn lacks common rank/shape validation, allowing broadcast-compatible qv/qc/nc/nccn/t or p/pii fields on the wrong (B,K) measure. Sedimentation-owned mismatches are already rejected and are excluded from this narrowed finding. | 수정 · 검증 완료 | [libtorch/src/runtime.cpp](../../libtorch/src/runtime.cpp) · [harness/g33_overlay/runtime.cpp.overlay](../../harness/g33_overlay/runtime.cpp.overlay) |
| 23 | ABI-RED-001 | Finite dt is accepted at the C boundary although operational f32 staging can produce a zero denominator or an internal out-of-range-loop error. | 수정 · 검증 완료 | [libtorch/bridge/kdm6_c_api.cpp](../../libtorch/bridge/kdm6_c_api.cpp) · [libtorch/bridge/kdm6_c_api.h](../../libtorch/bridge/kdm6_c_api.h) |
| 24 | ABI-RED-002 | Finite nonnegative ncmin can overflow float32 materialization of both where arms and be reported as INTERNAL. | 수정 · 검증 완료 | [libtorch/bridge/kdm6_c_api.cpp](../../libtorch/bridge/kdm6_c_api.cpp) · [libtorch/tests/test_c_abi.cpp](../../libtorch/tests/test_c_abi.cpp) |
| 25 | ABI-RED-003 | Implementation reads struct_size first, but the test does not prove no read beyond a four-byte caller object. | 수정 · 검증 완료 | [libtorch/tests/test_c_abi.cpp](../../libtorch/tests/test_c_abi.cpp) |
| 26 | ABI-GREEN-EXTENT-LIMIT | Explicit dimensions cannot be checked against allocation extents carried by raw pointers. | 계약 범위 유지 | [libtorch/bridge/kdm6_c_api.h](../../libtorch/bridge/kdm6_c_api.h) |
| 27 | ABI-LINKER-SUPPLEMENT | No export mismatch, platform-normalization error, or additional linker finding. | 기각 | [harness/evidence/SCIENCE_STATUS.md](../../harness/evidence/SCIENCE_STATUS.md) |
| 28 | TOOLS-GREEN-001 | Halo and first-difference branches print rows and unconditionally return 0 after a structurally valid report; rc=0 means command completion. | 기각 | [harness/evidence/SCIENCE_STATUS.md](../../harness/evidence/SCIENCE_STATUS.md) |
| 29 | TOOLS-RED-07 | No decomposition dump is rendered as blank observed halos, although no halo was compared. | 수정 · 검증 완료 | [harness/g33_dyn_probe.py](../../harness/g33_dyn_probe.py) |
| 30 | TOOLS-RED-08 | Raw-word equality accepts matching nonfinite halo/owner state. | 수정 · 검증 완료 | [harness/g33_dyn_probe.py](../../harness/g33_dyn_probe.py) |
| 31 | TOOLS-GREEN-004 / TOOLS-RED-01 | The generic helper requires no numeric match, so its universal comparison is vacuous on empty supported populations. | 수정 · 검증 완료 | [harness/strict_bitwise_nc.py](../../harness/strict_bitwise_nc.py) · [harness/build_c4_evidence.py](../../harness/build_c4_evidence.py) |
| 32 | TOOLS-RED-02 | Explicit frame access always indexes axis zero rather than locating the dimension named Time. | 수정 · 검증 완료 | [harness/strict_bitwise_nc.py](../../harness/strict_bitwise_nc.py) · [harness/build_c4_evidence.py](../../harness/build_c4_evidence.py) |
| 33 | TOOLS-GREEN-003 / TOOLS-RED-03 | Old helper returns zero for a clean first-tile subset but visibly labels the scope. | 계약 범위 유지 | [harness/compare_substep_stage.py](../../harness/compare_substep_stage.py) · [harness/compare_rate_dump.py](../../harness/compare_rate_dump.py) |
| 34 | TOOLS-RED-04 | Old comparator fits K orientation by minimum differences without an independent declaration. | 수정 · 검증 완료 | [harness/compare_substep_stage.py](../../harness/compare_substep_stage.py) · [harness/compare_rate_dump.py](../../harness/compare_rate_dump.py) |
| 35 | TOOLS-RED-05 | Raw equality does not establish a finite physical rate. | 수정 · 검증 완료 | [harness/compare_rate_dump.py](../../harness/compare_rate_dump.py) |
| 36 | TOOLS-RED-06 | Group 4 cannot establish the documented stale-east-muu explanation because it omits the operand actually read by the stencil. | 수정 · 검증 완료 | [harness/g33_dyn_probe.py](../../harness/g33_dyn_probe.py) · [docs/HOST_INTEGRATION.md](../../docs/HOST_INTEGRATION.md) |
| 37 | TOOLS-GREEN-002 | Legacy C4 block selects each side independently and does not validate pair case/input/grid/producer identity. | 수정 · 검증 완료 | [harness/build_c4_evidence.py](../../harness/build_c4_evidence.py) |
| 38 | TOOLS-RED-12 | C4's numeric threshold is weaker than the declared 254-variable WRF schema. | 수정 · 검증 완료 | [harness/build_c4_evidence.py](../../harness/build_c4_evidence.py) |
| 39 | TOOLS-GREEN-005 / TOOLS-RED-16 | Shape and optional DX/DY checks do not bind the map file to the run or reject nonfinite/zero physical weights. | 수정 · 검증 완료 | [harness/g33_mpi_divergence.py](../../harness/g33_mpi_divergence.py) |
| 40 | TOOLS-GREEN-006 | Nonpositive grid factors pass arithmetic-only validation. | 수정 · 검증 완료 | [harness/run_ss_case.py](../../harness/run_ss_case.py) |
| 41 | TOOLS-RED-09 | Malformed grid identity can be treated as a controlled perturbation while decomposition remains unknown. | 수정 · 검증 완료 | [harness/g33_mpi_divergence.py](../../harness/g33_mpi_divergence.py) |
| 42 | TOOLS-RED-10 | Consumer trusts mutable stable metadata instead of deriving consistency from hashes. | 수정 · 검증 완료 | [harness/g33_mpi_divergence.py](../../harness/g33_mpi_divergence.py) |
| 43 | TOOLS-RED-11 | Contradictory failed-run metadata can enter divergence analysis. | 수정 · 검증 완료 | [harness/g33_mpi_divergence.py](../../harness/g33_mpi_divergence.py) |
| 44 | TOOLS-RED-13 | A successful report can have no numeric selected field. | 수정 · 검증 완료 | [harness/g33_mpi_divergence.py](../../harness/g33_mpi_divergence.py) |
| 45 | TOOLS-RED-14 | fixed_mask_frame is not checked alongside requested frames. | 수정 · 검증 완료 | [harness/g33_mpi_divergence.py](../../harness/g33_mpi_divergence.py) |
| 46 | TOOLS-RED-15 | Human table and machine artifact disagree about unavailable populations. | 수정 · 검증 완료 | [harness/g33_mpi_divergence.py](../../harness/g33_mpi_divergence.py) |
| 47 | P-DOC-2 | STATUS points reviewers to a removed/non-current mechanical checker. | 수정 · 검증 완료 | [docs/STATUS.md](../../docs/STATUS.md) |
| 48 | F-1 / GEN-RED-001 | Recognized records from the nonselected v1/v3 grammar are silently omitted. | 수정 · 검증 완료 | [harness/g33_fortran/g33_fortran_dump.py](../../harness/g33_fortran/g33_fortran_dump.py) · [harness/g33_fortran_bundle_io.py](../../harness/g33_fortran_bundle_io.py) |
| 49 | F-2-numeric / GEN-RED-002 | Positive noncanonical outer-loop labels become the expected schedule identity. | 수정 · 검증 완료 | [harness/g33_fortran/g33_fortran_dump.py](../../harness/g33_fortran/g33_fortran_dump.py) · [harness/g33_fortran/g33_fortran_semantics.py](../../harness/g33_fortran/g33_fortran_semantics.py) |
| 50 | F-2-chain / GEN-RED-003 | Unknown chain passes lower parser/normalizer boundaries but fails current semantic/comparator consumers. | 수정 · 검증 완료 | [harness/g33_fortran/g33_fortran_dump.py](../../harness/g33_fortran/g33_fortran_dump.py) · [harness/g33_fortran/g33_fortran_semantics.py](../../harness/g33_fortran/g33_fortran_semantics.py) |
| 51 | GEN-RED-004 | STATE/STAGE output is checked for finiteness but not the documented nonnegative prognostic domain. | 수정 · 검증 완료 | [harness/g33_fortran/g33_fortran_dump.py](../../harness/g33_fortran/g33_fortran_dump.py) |
| 52 | G-1 / GEN-RED-007 | Pressure/rho/delz/theta vertical physics is reversed in standalone G33R input. | 수정 · 검증 완료 | [harness/g33_overlay/g33_refine_driver.cpp](../../harness/g33_overlay/g33_refine_driver.cpp) |
| 53 | GEN-GREEN-XLAND | Arbitrary finite low-level values classify by the documented threshold; fixture/parser authority is exact 1/2. | 기각 | [harness/evidence/SCIENCE_STATUS.md](../../harness/evidence/SCIENCE_STATUS.md) |
| 54 | GEN-GREEN-SUBCYCLE | The direct entry's caller-supplied auxiliary contract differs intentionally from production wrapper behavior. | 기각 | [harness/evidence/SCIENCE_STATUS.md](../../harness/evidence/SCIENCE_STATUS.md) |
| 55 | REPLAY-GREEN-001 | Probe and producer disagree on outer-loop count and effective f32 dt for nonintegral elapsed times. | 수정 · 검증 완료 | [harness/g33_schedule_probe.py](../../harness/g33_schedule_probe.py) · [harness/g33_overlay/coordinator.cpp.overlay](../../harness/g33_overlay/coordinator.cpp.overlay) |
| 56 | R-RED-01 | Bundle verifier has authority B,K but does not pass it to lineage; truncated n=1 or partial n>1 evidence can retain mstep. | 수정 · 검증 완료 | [harness/g33_bundle_io.py](../../harness/g33_bundle_io.py) · [harness/g33_schedule_probe.py](../../harness/g33_schedule_probe.py) |
| 57 | R-RED-02 | C++ common state snapshots lack finite/domain validation before raw-bit comparison. | 수정 · 검증 완료 | [harness/g33_evidence_validate.py](../../harness/g33_evidence_validate.py) · [harness/g33_fourcase_comparator.py](../../harness/g33_fourcase_comparator.py) |
| 58 | R-RED-03 | Replay dictionaries overwrite identities and lack independent expected stage/cell census. | 수정 · 검증 완료 | [harness/g33_replay.py](../../harness/g33_replay.py) |
| 59 | R-RED-04 | Malformed evidence is not accepted as a schedule but escapes the declared ProbeError/bundle-error channel. | 수정 · 검증 완료 | [harness/g33_schedule_probe.py](../../harness/g33_schedule_probe.py) · [harness/g33_bundle_io.py](../../harness/g33_bundle_io.py) |
| 60 | R-RED-05 | Standalone selfcheck does not bind all intrinsic container headers to its sealed authority. | 코드 수정 · native 증거 대기 | [harness/g33_selfcheck.py](../../harness/g33_selfcheck.py) · [harness/g33_dump.py](../../harness/g33_dump.py) |
| 61 | R-RED-06 | Helpers infer the cell universe and lack finite/domain checks for all consumed maps. | 수정 · 검증 완료 | [harness/g33_update_replay.py](../../harness/g33_update_replay.py) |
| 62 | PUB-01 | Gate B records verifier runtime and identity without enforcing runtime or semantics identity before a decision-valid write. | 수정 · 검증 완료 | [harness/gateb_g33m_check.py](../../harness/gateb_g33m_check.py) |
| 63 | PUB-02 | RESULT_INDEX.json is documented as the authority but has no current executable consumer or consistency validator. | 수정 · 검증 완료 | [harness/evidence/RESULT_INDEX.json](../../harness/evidence/RESULT_INDEX.json) · [harness/gateb_g33m_check.py](../../harness/gateb_g33m_check.py) |
| 64 | PUB-03 | Evidence-error results are written as valid_for_decision when debug_only is false. | 수정 · 검증 완료 | [harness/gateb_g33m_check.py](../../harness/gateb_g33m_check.py) |
| 65 | PUB-04 | Generated per-stage divergence rows are not closed over the artifact's own total. | 수정 · 검증 완료 | [harness/make_g33m_evidence_artifact.py](../../harness/make_g33m_evidence_artifact.py) · [harness/g33_expectation.py](../../harness/g33_expectation.py) |
| 66 | PUB-05 | Condensation closure collects loop-1 cells while wording can imply a multi-loop closure. | 수정 · 검증 완료 | [harness/make_g33m_evidence_artifact.py](../../harness/make_g33m_evidence_artifact.py) |
| 67 | P-DOC-1 | STATUS presents nr and rho*dz*nr as an unconditional physical number basis while SCIENCE_STATUS leaves #/kg_d versus #/m3 OPEN. | 수정 · 검증 완료 | [docs/STATUS.md](../../docs/STATUS.md) |
| 68 | P-DOC-2 | STATUS names deleted test_g33_claims.py as a current mechanical registry check. | 수정 · 검증 완료 | [docs/STATUS.md](../../docs/STATUS.md) |
| 69 | TRANSPORT-01 | Same-run validation binds G33P/G33N rho and delz but leaves G33P INITIAL qv unbound to G33N. | 수정 · 검증 완료 | [harness/g33_number_transport.py](../../harness/g33_number_transport.py) · [harness/g33_refine_experiment.py](../../harness/g33_refine_experiment.py) |
| 70 | TRANSPORT-02 | real-column batch formats an unavailable fraction as a percentage and can take a median over an empty set. | 수정 · 검증 완료 | [harness/g33_real_column_batch.py](../../harness/g33_real_column_batch.py) |
| 71 | TRANSPORT-03 | Conservative direct sedimentation helpers lack the legacy exact-shape guard. | 수정 · 검증 완료 | [libtorch/src/sedimentation_conservative.cpp](../../libtorch/src/sedimentation_conservative.cpp) · [harness/g33_overlay/sedimentation_conservative.cpp.overlay](../../harness/g33_overlay/sedimentation_conservative.cpp.overlay) |
| 72 | TRANSPORT-04 | column() uses metric-aware transfer recovery but retains a thickness-only predicted-residual formula. | 수정 · 검증 완료 | [harness/g33_number_transport.py](../../harness/g33_number_transport.py) · [harness/g33_arms.py](../../harness/g33_arms.py) |
| 73 | TRANSPORT-05 | Conservative direct helpers accept broadcastable malformed column grids. | 수정 · 검증 완료 | [libtorch/src/sedimentation_conservative.cpp](../../libtorch/src/sedimentation_conservative.cpp) · [oracle/kdm6/sed_conservative.py](../../oracle/kdm6/sed_conservative.py) |
| 74 | EXPERIMENTS-01 | QR process-ledger execution drops frozen mode and width, running carry bundles with rezero/default identity. | 수정 · 검증 완료 | [harness/g33_qr_process_ledger.py](../../harness/g33_qr_process_ledger.py) · [harness/g33_ncmin_locality.py](../../harness/g33_ncmin_locality.py) |
| 75 | EXPERIMENTS-02 | Standalone process-ledger weighting compares decoded floats without raw-bit/domain/full cross-protocol binding. | 수정 · 검증 완료 | [harness/g33_qr_process_ledger.py](../../harness/g33_qr_process_ledger.py) |
| 76 | EXPERIMENTS-03 | Factorial pair validation is outside responses() and incomplete for G33N initial moisture/state. | 수정 · 검증 완료 | [harness/g33_factorial.py](../../harness/g33_factorial.py) · [harness/g33_number_transport.py](../../harness/g33_number_transport.py) |
| 77 | EXPERIMENTS-04 | Factorial partition counts collapse signed-zero output differences because decoded Python floats compare equal. | 수정 · 검증 완료 | [harness/g33_factorial.py](../../harness/g33_factorial.py) |
| 78 | EXPERIMENTS-05 | Locality analysis rereads mutable fixture XLAND/NCMIN controls after execution instead of using immutable staged controls. | 수정 · 검증 완료 | [harness/g33_refine_experiment.py](../../harness/g33_refine_experiment.py) · [harness/g33_ncmin_locality.py](../../harness/g33_ncmin_locality.py) |
| 79 | PHY-C1 | C1 helper can return nonzero warm-cell component rates because the helper has no outer supcol gate. | 계약 범위 유지 | [oracle/kdm6/coordinator.py](../../oracle/kdm6/coordinator.py) |
| 80 | PHY-C2 | C2 helper can return nonzero warm-cell component rates because activation masks omit outer supcol gate. | 계약 범위 유지 | [oracle/kdm6/coordinator.py](../../oracle/kdm6/coordinator.py) |
| 81 | PHY-SLOPE | Standalone slope_rain leaves vtn positive for nr<=0 although active Fortran slope_rain zeros it. | 수정 · 검증 완료 | [libtorch/src/slope.cpp](../../libtorch/src/slope.cpp) · [oracle/kdm6/slope.py](../../oracle/kdm6/slope.py) |
| 82 | HOST-R01 | hail_opt=1 changes Fortran initialization but is absent from both AD wrappers/C++ defaults. | 소스 수정 · 호스트 실행 미측정 | [docs/HOST_INTEGRATION.md](../../docs/HOST_INTEGRATION.md) |
| 83 | HOST-R02 | Generic driver writes optional refl_sfc without PRESENT; active adjoint caller omits it. | 소스 수정 · 호스트 실행 미측정 | [docs/HOST_INTEGRATION.md](../../docs/HOST_INTEGRATION.md) |
| 84 | HOST-R03 | AD dispatch checks core state fields but can forward absent optional rhopo3d/outputs to required wrapper dummies. | 소스 수정 · 호스트 실행 미측정 | [docs/HOST_INTEGRATION.md](../../docs/HOST_INTEGRATION.md) |
| 85 | HOST-R04 | Conservative v2 first-call SAVE gate is unsynchronized inside possible OpenMP tile loop. | 소스 수정 · 호스트 실행 미측정 | [docs/HOST_INTEGRATION.md](../../docs/HOST_INTEGRATION.md) |
| 86 | HOST-R05 | Host finite scans omit DELT/ncmin controls and finite-error helpers use placeholder coordinates. | 소스 수정 · 호스트 실행 미측정 | [docs/HOST_INTEGRATION.md](../../docs/HOST_INTEGRATION.md) |
| 87 | HOST-R06 | Host apply script and Makefile emit macOS dylib/rpath flags while documentation advertises Linux and macOS wiring. | 코드 수정 · 실측 범위 별도 | [docs/HOST_INTEGRATION.md](../../docs/HOST_INTEGRATION.md) |
| 88 | PHY-C1-FORWARD | Nonzero raw C1 warm-cell helper output proves a forward warm-cell state bug. | 기각 | [harness/evidence/SCIENCE_STATUS.md](../../harness/evidence/SCIENCE_STATUS.md) |
| 89 | PHY-C2-FORWARD | Nonzero raw C2 warm-cell helper output proves a forward warm-cell state bug. | 기각 | [harness/evidence/SCIENCE_STATUS.md](../../harness/evidence/SCIENCE_STATUS.md) |
| 90 | PUB-CURRENT-WRONG-BUNDLE | The runtime/index gaps prove that an invalid or wrong-bundle conclusion has already been issued as current. | 기각 | [harness/evidence/SCIENCE_STATUS.md](../../harness/evidence/SCIENCE_STATUS.md) |

## 독립 재검토에서 추가로 확인한 경로

| ID | 해소 또는 유지한 계약 | 회귀 근거 |
|---|---|---|
| DA-REVIEW208-LIN-TIME-01 | retained adjoint/tangent도 공통 시각 정규화; fractional/bool/비유한값 거부, 유효 alias 보존 | [DA 시험](../../oracle/tests/test_review208_da_core.py) |
| DA-EXEC-RED-04 / 05 후속 | mixed sigma와 기준 T/Q 쌍을 direct OSSE·ShardSpec·builder·worker 경계에 전달 | [driver](../../oracle/tests/test_review208_da_driver.py), [shards](../../oracle/tests/test_review208_da_parallel.py) |
| DA-EXEC-RED-02 후속 | 따옴표로 감싼 literal exe 지원; solar 검증도 실제 out/cwd 기준 계수 파일 사용 | [실제 호출 경계 시험](../../oracle/tests/test_review208_fulldomain.py) |
| PARENT-H-RED-01 | signature는 고정 window의 captured data 검사. stateless callback·외부 fixture 불변은 실행 계약; 임의 closure identity로 확대하지 않음 | [closure 계약](../../oracle/kdm6/da_fulldomain.py) |
| HOST-REV-01 | hail 검사를 추가한 두 AD dispatch도 OPTIONAL config_flags의 PRESENT를 먼저 확인 | [private 범위](../../docs/HOST_INTEGRATION.md) |
| TOOLS-REVIEW208-RED-01 | campaign controls 재계산·37/137 arm·sibling status·선택적 schema binding 확인. Self hash는 무결성이며 외부 schema의 진실성은 호출자 계약 | [도구 회귀](../../harness/tests/test_review208_tools.py) |
| TOOLS-REVIEW208-RED-02 / 06 | zero-cell/zero-frame·Times 누락은 INSUFFICIENT | [도구 회귀](../../harness/tests/test_review208_tools.py) |
| TOOLS-REVIEW208-RED-03 / 04 / 05 | np/matches 형식, exe before/after/final/stable 모순, 중복 active input identity 거부 | [도구 회귀](../../harness/tests/test_review208_tools.py) |
| TOOLS-REVIEW208-TEST-01 | 새 테스트의 root import를 실제 독립 pytest 호출로 확인 | [도구 회귀](../../harness/tests/test_review208_tools.py) |
| EXPERIMENTS-01 / EXP-RED-001 후속 | 실제 gated_text의 carry 인자와 일치; 테스트 대체 함수도 실제 signature 유지 | [QR 호출 시험](../../harness/tests/test_review208_transport.py) |
| EXPERIMENTS-05 / EXP-RED-004 후속 | staged bytes 재해시; 동일 바이트에서 차원·input digest·locality 분류 도출 | [fixture 권위 시험](../../harness/tests/test_review208_transport.py) |
| EXP-RED-005 | undefined/absent response는 null, 유효한 측정 0은 숫자. 기존 coefficients의 invalid 처리 유지 | [factorial 시험](../../harness/tests/test_g33_factorial.py) |
| PUB-208-RED-01 | attested/anchored/decision_valid/tier/verdict를 writer·index에서 함께 확인; unattested 후보는 승격 불가 | [판정 계약 시험](../../harness/tests/test_review208_abi_green.py) |
| PUB-208-RED-02 | supersession cycle과 임의 withdrawn successor 거부. 기존 null-current 역사 기록의 명시적 no-replacement만 보존 | [index 시험](../../harness/tests/test_review208_abi_green.py) |
| REPLAY-208-RED-01 | n>1도 여섯 field·shape·domain·dtcld·mstep 검증 | [probe 시험](../../harness/tests/test_review208_abi_green.py) |
| REPLAY-208-RED-02 | coverage가 공통 finite/domain 검사를 재사용하여 all-NaN census 거부 | [replay 시험](../../harness/tests/test_review208_abi_green.py) |
| ABI-RED-003 후속 | 4-byte prefix를 memcpy로 읽어 full-struct 정렬/객체 수명 가정을 제거; 실제 guard-page 시험 유지 | [ABI 시험](../../libtorch/tests/test_c_abi.cpp), [framing 계약](../../docs/PR2_ABI_V2_DESIGN.md) |

## 반복 제시된 AMI 검토

- [x] U1: DQF 14·15비트와 DN 영역 분리 재확인.
- [x] U2: 변수 속성의 채널별 유효 비트 수 전달 재확인.
- [x] U3: literal hexadecimal, 11–14비트 경계, NetCDF 마스크 조합 회귀시험 재확인.
- [x] U4: 빈 collocation은 빈 결과; 실행할 RTTOV의 빈 profile/layer/channel은 명시적 거부.
- [x] U5 검토: 거리 우선 소유권은 현재 계약으로 유지. 품질 불량 최근접 픽셀이
  격자를 선점할 수 있으며, 품질 우선 정책으로 바꿨다고 주장하지 않는다.

근거: [AMI 계약](../../docs/AMI_INPUT_CONTRACT.md),
[literal-word 시험](../../oracle/tests/test_ami_word_contract.py),
[기존 실제 자료의 전체 래스터 집계](../../docs/reports/ami_bit_decode_full_raster_summary_20260905.json),
[기존 production 표본](../../docs/reports/ami_bit_decode_20260905.json).
이번 세션은 기존 실제 자료 측정 기록과 현재 함수를 재검토했으며 전체 래스터를 다시 실행하지 않았다.
품질 비트와 DN 폭의 외부 대조: [Satpy AMI 원본 reader](https://satpy.readthedocs.io/en/v0.54.0/_modules/satpy/readers/ami_l1b.html).

## 별도 미측정 과제

- M1: 실제 10분 WRF에서 적용된 유출·유입 잔차 재계측 — OPEN.
- M2: 첫 음수 QIB 셀의 갱신 피연산자·경향 추적 — OPEN.
- 호스트/커널 입자수 단위 계약 — OPEN; 밀도 가중 수지는 조건부 해석.
- D4: 한 ULP 차이의 실제 피연산자 측정 — OPEN.
- 실제 위치별 관측 H·예보/동화 성능 — 이번 합성·소스 검증으로 인증하지 않음.
- private host 수정은 소스·전처리·부분 syntax 검증; 재빌드/WRF/MPI 실행 전 배포 parity를 재인증하지 않음.
- 별도 AD4DVAR A3-01은 기존 PR157의 수정과 mutation 회귀를 재확인했다.
  A3-03 실제 레이더 고정영역 비교는 원자료·검증시각 부재로 OPEN이며 KDM6AD 검증 수치에 합치지 않는다.

## 최종 검증

- Oracle 전체: **1,008 passed / 26 skipped**, 33 warnings (기존 tuple 반환 사용 경고 등).
- 공개 C++ 재빌드: **CTest 17/17**; guard-page ABI 시험 추가 후 해당 target 재빌드·재실행 PASS.
- Oracle↔C++: **4 passed**. 9개 ABI symbol 및 KMP 환경 보존 검사 PASS.
- 합성 f32 old/new ABI: warm/mixed/cold × dt 0/1/60/300, **12사례·192배열·1,980값 raw-bit 동일**.
- C++ refinement: B=3/K=4 초기·최종 각144 word가 canonical fixture/공개 ABI와 raw-bit 동일.
- Portable harness: **1,615 passed / 59 skipped / 309 deselected**. Local-only 호스트/Fortran 시험을 실행 수에 넣지 않았다.
- clean-source 계측 selfcheck: 커밋 고정 후 실행 대기.
- Private host: 7개 source hash, driver/init 전처리, wrapper 부분 syntax, shell 지원 플랫폼 검사 PASS. 전체 호스트 build/run 없음.
- 별도 AD4DVAR: 기존 A3-01 21개 시험 PASS; 두 구형 분모 mutation은 각각 기대한 회귀 실패. PR157 CI 네 개 모두 SUCCESS.

테스트 수는 부모의 최종 실행 기준이며 팀별 중복 실행 수를 합산하지 않았다.
외부 자료가 없는 skip을 실행 성공으로 세지 않는다. 합성 f32 비교는 역사적12시간 WRF parity를 재인증하지 않는다.
