from __future__ import annotations

import json
import os
import struct
import sys
import copy
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import g33_s15_probe as s15


def test_qib_replayer_reconstructs_one_nonnegative_to_negative_update() -> None:
    row = {
        "kind": "QIB", "step": "7", "rk": "2", "owner": str(s15.QIB_OWNER_SITE), "tile_i0": "1", "tile_i1": "2",
        "tile_j0": "3", "tile_j1": "4", "i": "1", "j": "3", "k": "8",
        "before": "00000000", "after": "BF800000", "reference": "00000000",
        "advect": "00000000", "msfty": "3F800000", "other_tend": "BF800000",
        "dt": "3F800000", "c1": "00000000", "c2": "3F800000",
        "muold": "3F800000", "munew": "3F800000",
    }
    replay = s15.replay_qib(row)
    assert replay["key"] == (7, 2, s15.QIB_OWNER_SITE, 1, 3, 8)
    assert replay["replayed_after_bits"] == "BF800000"


def test_else_arm_rejects_stale_scalar2_as_the_transition_input() -> None:
    # In the ELSE arm, scalar_2 may retain any value from an earlier stage;
    # scalar_1 is the actual reference used by the update formula.
    row = {
        "kind": "QIB", "step": "1", "rk": "2", "owner": str(s15.QIB_OWNER_SITE), "tile_i0": "1", "tile_i1": "2",
        "tile_j0": "3", "tile_j1": "4", "i": "1", "j": "3", "k": "8",
        "before": "3F800000", "after": "BF800000", "reference": "00000000",
        "advect": "00000000", "msfty": "3F800000", "other_tend": "BF800000",
        "dt": "3F800000", "c1": "00000000", "c2": "3F800000",
        "muold": "3F800000", "munew": "3F800000",
    }
    with pytest.raises(s15.ProbeError, match="not the formula's reference input"):
        s15.replay_qib(row)
    row["before"] = row["reference"]
    assert s15.replay_qib(row)["after_bits"] == "BF800000"


def test_qib_nonfinite_overflow_is_not_counted_as_negative_transition() -> None:
    row = {
        "kind": "QIB", "step": "1", "rk": "2", "owner": str(s15.QIB_OWNER_SITE), "tile_i0": "1", "tile_i1": "2",
        "tile_j0": "3", "tile_j1": "4", "i": "1", "j": "3", "k": "8",
        "before": "00000000", "after": "FF800000", "reference": "00000000",
        "advect": "7F7FFFFF", "msfty": "BF800000", "other_tend": "00000000",
        "dt": "40000000", "c1": "00000000", "c2": "3F800000",
        "muold": "3F800000", "munew": "3F800000",
    }
    with pytest.raises(s15.ProbeError, match="non-finite output"):
        s15.replay_qib(row)
    row["after"] = "BF800000"
    with pytest.raises(s15.ProbeError, match="non-finite QIB tendency or mass intermediate"):
        s15.replay_qib(row)


def test_generic_scalar_fma_replay_matches_a_rk3_word_not_separate_f32() -> None:
    # This A operand row is owner 1 as reconstructed from source call order (A
    # emitted no owner field). It proves only the generic arithmetic model; it
    # is not a QIB-owned witness.
    operands = {
        "reference": "00000000", "advect": "9CACBD58", "msfty": "3F7E69D1",
        "other_tend": "00000000", "dt": "41A00000", "c1": "3FB1B880",
        "c2": "C7102616", "muold": "47B9E6F4", "munew": "47B9DC7A",
    }
    replay = s15.replay_rk_scalar_f32(operands)
    separate_new_mass = s15.add32(
        s15.mul32(s15.f32(operands["c1"]), s15.f32(operands["munew"])),
        s15.f32(operands["c2"])
    )
    assert s15.f32_word(separate_new_mass) == "47B9FBBD"
    assert s15.f32_word(s15.fma32(
        s15.f32(operands["c1"]), s15.f32(operands["munew"]), s15.f32(operands["c2"])
    )) == "47B9FBBC"
    assert replay["replayed_after_bits"] == "9693AF7D"


def test_tendency_replay_preserves_separate_f32_multiply_then_add() -> None:
    # This triple distinguishes two binary32 operations from a fused update.
    operands = {
        "reference": "00000000", "advect": "C046AAD9", "msfty": "41140B97",
        "other_tend": "BFCE8378", "dt": "3F800000", "c1": "00000000",
        "c2": "3F800000", "muold": "3F800000", "munew": "3F800000",
    }
    replay = s15.replay_rk_scalar_f32(operands)
    separate = s15.add32(
        s15.mul32(s15.f32(operands["advect"]), s15.f32(operands["msfty"])),
        s15.f32(operands["other_tend"]),
    )
    fused = s15.fma32(s15.f32(operands["advect"]), s15.f32(operands["msfty"]),
                      s15.f32(operands["other_tend"]))
    assert s15.f32_word(separate) == "C1F2AFC0"
    assert s15.f32_word(fused) == "C1F2AFBF"
    assert replay["tendency_bits"] == "C1F2AFC0"


def test_fma32_uses_exact_nearest_even_binary32_rounding() -> None:
    assert s15.f32_word(s15.fma32(1.0, 2.0 ** -24, 1.0)) == "3F800000"
    assert s15.f32_word(s15.fma32(1.0, 3.0 * 2.0 ** -24, 1.0)) == "3F800002"


def test_qib_replayer_rejects_an_index_alias_from_non_qib_owner() -> None:
    row = {
        "kind": "QIB", "step": "1", "rk": "2", "owner": "4",
        "tile_i0": "1", "tile_i1": "2", "tile_j0": "3", "tile_j1": "4",
        "i": "1", "j": "3", "k": "8", "before": "00000000",
        "after": "BF800000", "reference": "00000000", "advect": "00000000",
        "msfty": "3F800000", "other_tend": "BF800000", "dt": "3F800000",
        "c1": "00000000", "c2": "3F800000", "muold": "3F800000",
        "munew": "3F800000",
    }
    with pytest.raises(s15.ProbeError, match="non-QIB scalar owner"):
        s15.replay_qib(row)


def test_pre_link_binding_checks_r6_sources_preprocessed_objects_and_archive(tmp_path: Path) -> None:
    def put(name: str, contents: str) -> tuple[Path, str]:
        path = tmp_path / name
        path.write_text(contents)
        return path, s15.sha256(path)

    sources = {"module_em.F": put("module_em.F", "src em")}
    preprocessed = {"module_em.f90": put("module_em.f90", "pre em")}
    objects = {"module_em.o": put("module_em.o", "object em")}
    archive_path, archive_sha = put("libwrflib.a", "baseline archive")
    receipt = {
        "schema": "KDM6AD-S15-FOCUSED-COMPILE-RECEIPT-v2",
        "qib_owner_site": s15.QIB_OWNER_SITE,
        "qib_owner_name": s15.QIB_OWNER_NAME,
        "generated_shadow_source_sha256": {k: v[1] for k, v in sources.items()},
        "files": {
            "preprocessed_fortran": {
                k: {"sha256": v[1]} for k, v in preprocessed.items()
            },
            "objects": {k: {"sha256": v[1]} for k, v in objects.items()},
        },
        "baseline_link_inputs": {
            "untouched_s8_archive": {
                "sha256": archive_sha, "bytes": archive_path.stat().st_size,
            }
        },
    }
    receipt_path = tmp_path / "r6.json"
    receipt_path.write_text(json.dumps(receipt))
    binding = {
        "compile_receipt": {"path": str(receipt_path), "sha256": s15.sha256(receipt_path)},
        "owner_site": s15.QIB_OWNER_SITE,
        "owner_name": s15.QIB_OWNER_NAME,
        "generated_shadow_sources": {
            k: {"path": str(v[0]), "sha256": v[1]} for k, v in sources.items()
        },
        "preprocessed_fortran": {
            k: {"path": str(v[0]), "sha256": v[1]} for k, v in preprocessed.items()
        },
        "objects": {
            k: {"path": str(v[0]), "sha256": v[1]} for k, v in objects.items()
        },
        "baseline_archive": {"path": str(archive_path), "sha256": archive_sha},
    }
    assert s15.verify_pre_link_binding(binding) == {"bound_inputs_verified": 4}
    sources["module_em.F"][0].write_text("changed source")
    with pytest.raises(s15.ProbeError, match="generated_shadow_sources file is missing or changed"):
        s15.verify_pre_link_binding(binding)


def test_plan_pin_rejects_mutated_plan_even_when_binding_is_unchanged(tmp_path: Path) -> None:
    plan = tmp_path / "plan.json"
    plan.write_text('{"pre_link_binding":{"owner_site":5}}\n')
    pinned = s15.sha256(plan)
    plan.write_text('{"pre_link_binding":{"owner_site":5},"comment":"changed"}\n')
    with pytest.raises(s15.ProbeError, match="differs from the external pin"):
        s15.verify_plan_pin(plan, pinned)


def test_s15_public_packet_paths_are_redacted_and_original_pins_are_listed() -> None:
    import re

    evidence = Path(__file__).resolve().parents[1] / "evidence"
    public_dir = evidence / "s15_b20_public"
    manifest_path = public_dir / "s15_native_B_20S_public_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["redacted_projection"] is True
    assert manifest["executable_original"] is False
    assert manifest["verification_status"]["original_private_evidence"].startswith("LOCAL_VERIFIED")
    assert manifest["verification_status"]["public_projection_files"].startswith("PUBLIC_REDACTED")

    projections = manifest["public_projections"]
    originals = {item["represents_original"]: item["original_sha256"] for item in projections}
    assert originals == {
        "s15_native_compile_receipt_2026-09-26_r6.json":
            "67183b38e001a5137159778823c4b5032d475b72d9cbf05d572fca16cbfecf3b",
        "s15_native_owner_schedule_2026-09-26.json":
            "34d671cefcbad485a3d3ccf276e91c60933cce86394485574080dbcd1e58cf8c",
        "s15_native_discovery_b_event_reference_2026-09-26.json":
            "b28204f00124d5f4e7358e9f0e554c75b541acdf1113526f6ccc0907d869078b",
    }
    repo_root = Path(__file__).resolve().parents[2]
    public_files = [repo_root / "harness/g33_s15_probe.py", Path(__file__),
                    evidence / "S15_NATIVE_B_20S_RESULT.md",
                    evidence / "S15_NATIVE_PROBE_DESIGN.md",
                    evidence / "REPORT_S15_step2_40s_native_2026-09-26.md",
                    evidence / "CHECKLIST_S15_step2_40s_native_2026-09-26.md",
                    evidence / "s15_native_step2_40s_plan_2026-09-26.json",
                    evidence / "s15_native_step2_40s_plan_2026-09-26.json.sha256",
                    manifest_path, Path(str(manifest_path) + ".sha256")]
    for item in projections:
        projection_path = repo_root / item["filename"]
        public_files.extend([projection_path, Path(str(projection_path) + ".sha256")])
    slash = chr(47)
    private_path_patterns = (
        re.compile(slash + "Users" + slash + r"[^/]+" + slash),
        re.compile(slash + "private" + slash + r"[^/]+" + slash),
    )
    for path in public_files:
        text = path.read_text()
        assert not any(pattern.search(text) for pattern in private_path_patterns), path


def test_s15_step2_public_qib_witness_rows_replay_exactly() -> None:
    evidence = Path(__file__).resolve().parents[1] / "evidence"
    public_dir = evidence / "s15_step2_public"
    witness_path = public_dir / "s15_native_step2_qib_witnesses_public_2026-09-26.json"
    witness = json.loads(witness_path.read_text())
    summaries = witness["owner_schedule"]
    assert summaries["step"] == 2
    assert summaries["owner_site"] == s15.QIB_OWNER_SITE
    assert summaries["total_transition_occurrences"] == 87937
    assert summaries["transition_counts"] == [18356, 11017, 36182, 20849, 1038, 495]
    assert summaries["summary_keys"] == s15.expected_qib_summary_keys(2)
    assert len(witness["first_qib_events"]) == 6
    observed_keys = []
    for item in witness["first_qib_events"]:
        row = item["record"]
        replay = s15.replay_qib(row)
        assert item["replay"]["status"] == "exact_f32_replay_pass"
        assert item["replay"]["matches"] is True
        assert replay["before_bits"] == item["replay"]["before_bits"]
        assert replay["after_bits"] == item["replay"]["captured_after_bits"]
        assert replay["replayed_after_bits"] == item["replay"]["replayed_after_bits"]
        observed_keys.append(list(replay["key"]))
    expected_positive = [
        [2, 1, 5, 143, 2, 16], [2, 1, 5, 144, 143, 14],
        [2, 2, 5, 111, 2, 16], [2, 2, 5, 146, 143, 13],
        [2, 3, 5, 141, 2, 17], [2, 3, 5, 141, 143, 16],
    ]
    assert observed_keys == expected_positive


def test_s15_step2_public_packet_is_path_free_and_original_receipts_are_pinned() -> None:
    import re

    evidence = Path(__file__).resolve().parents[1] / "evidence"
    public_dir = evidence / "s15_step2_public"
    manifest_path = public_dir / "s15_native_step2_40s_public_manifest_2026-09-26.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["redacted_projection"] is True
    assert manifest["executable_original"] is False
    assert manifest["native_summary"]["qib_transition_occurrences"] == 87937
    assert manifest["native_summary"]["qib_rk_stage_transition_occurrences"] == {
        "1": 29373, "2": 57031, "3": 1533,
    }
    assert manifest["native_summary"]["trace_melt_rows"] == 258
    assert manifest["native_summary"]["trace_melt_rhox_valid_rows"] == 0
    originals = manifest["original_private_receipt_sha256"]
    assert originals["step2_link_receipt_2026-09-26.json"] == \
        "ce1a8f7f14845a09062644b16f6d41bfd7a2279c2a7caeac7f5e68b9b35e0b2d"
    assert originals["step2_same_exe_pair_receipt_2026-09-26.json"] == \
        "3adb2957fe0300a42b11430d13e5ebddc67ccd01e70973d156afa1c580141b6a"
    assert manifest["redacted_receipt_projections"]["link"]["represents_original_private_receipt"]["sha256"] == \
        "ce1a8f7f14845a09062644b16f6d41bfd7a2279c2a7caeac7f5e68b9b35e0b2d"
    assert manifest["redacted_receipt_projections"]["compile"]["objects"]["module_em.o"]["sha256"] == \
        "f0b0ed1ccec81bdd53826a38cd2e88c6ad5b016199c72ef7bfcd7e05f5d258cc"
    repo_root = Path(__file__).resolve().parents[2]
    public_files = [manifest_path, Path(str(manifest_path) + ".sha256")]
    for item in manifest["public_supporting_files"]:
        path = repo_root / item["filename"]
        assert s15.sha256(path) == item["sha256"]
        public_files.append(path)
    for item in manifest["public_projections"]:
        path = evidence / item["filename"]
        assert s15.sha256(path) == item["sha256"]
        assert path.with_suffix(path.suffix + ".sha256").read_text().split()[0] == item["sha256"]
        public_files.extend([path, path.with_suffix(path.suffix + ".sha256")])
    slash = chr(47)
    private_path_patterns = (
        re.compile(slash + "Users" + slash + r"[^/]+" + slash),
        re.compile(slash + "private" + slash + r"[^/]+" + slash),
    )
    for path in public_files:
        text = path.read_text()
        assert not any(pattern.search(text) for pattern in private_path_patterns), path


def test_postlink_guard_binds_r6_objects_inputs_and_fresh_executable(tmp_path: Path) -> None:
    def put(name: str, contents: str) -> tuple[Path, str]:
        path = tmp_path / name
        path.write_text(contents)
        return path, s15.sha256(path)

    src, src_sha = put("module_em.F", "source")
    pp, pp_sha = put("module_em.f90", "preprocessed")
    obj, obj_sha = put("module_em.o", "r6 object")
    archive_path, archive_sha = put("libwrflib.a", "S8 archive")
    compile = {
        "schema": "KDM6AD-S15-FOCUSED-COMPILE-RECEIPT-v2",
        "qib_owner_site": s15.QIB_OWNER_SITE, "qib_owner_name": s15.QIB_OWNER_NAME,
        "generated_shadow_source_sha256": {"module_em.F": src_sha},
        "files": {"preprocessed_fortran": {"module_em.f90": {"sha256": pp_sha}},
                  "objects": {"module_em.o": {"sha256": obj_sha}}},
        "baseline_link_inputs": {"untouched_s8_archive": {
            "sha256": archive_sha, "bytes": archive_path.stat().st_size}},
    }
    compile_path = tmp_path / "compile.json"
    compile_path.write_text(json.dumps(compile))
    binding = {
        "compile_receipt": {"path": str(compile_path), "sha256": s15.sha256(compile_path)},
        "owner_site": s15.QIB_OWNER_SITE, "owner_name": s15.QIB_OWNER_NAME,
        "generated_shadow_sources": {"module_em.F": {"path": str(src), "sha256": src_sha}},
        "preprocessed_fortran": {"module_em.f90": {"path": str(pp), "sha256": pp_sha}},
        "objects": {"module_em.o": {"path": str(obj), "sha256": obj_sha}},
        "baseline_archive": {"path": str(archive_path), "sha256": archive_sha},
    }
    input_path, input_sha = put("namelist.input", "retained LC05 input")
    exe_path, exe_sha = put("wrf_B.exe", "fresh B executable")
    plan = {
        "pre_link_binding": binding,
        "owner_schedule": {"input_hashes": {"namelist.input": input_sha}},
        "post_link_guard_contract": {
            "schema": "KDM6AD-S15-OVERLAY-LINK-RECEIPT-v2",
            "status": "owner_scoped_plan_bound_B_link_pass",
        },
    }
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan))
    plan_sha = s15.sha256(plan_path)
    link = {
        "schema": "KDM6AD-S15-OVERLAY-LINK-RECEIPT-v2",
        "status": "owner_scoped_plan_bound_B_link_pass",
        "plan_sha256": plan_sha,
        "compile_receipt_sha256": binding["compile_receipt"]["sha256"],
        "canonical_host_modified": False,
        "s15_overlay_objects": {"module_em.o": {"path": str(obj), "sha256": obj_sha}},
        "untouched_s8_archive": {"path": str(archive_path), "sha256": archive_sha},
        "executable": {"path": str(exe_path), "sha256": exe_sha},
        "input_files": {"namelist.input": {"path": str(input_path), "sha256": input_sha}},
    }
    link_path = tmp_path / "link.json"
    link_path.write_text(json.dumps(link))
    link_sha = s15.sha256(link_path)
    assert s15.verify_postlink_binding(plan_path, plan_sha, link_path, link_sha) == {
        "r6_objects_verified": 1, "launch_inputs_verified": 1,
        "prelink_inputs_verified": 4,
    }

    pre_run_plan = {
        "schema": "KDM6AD-S15-NATIVE-B-PRE-RUN-PLAN-v1",
        "build_plan": {"path": plan_path.name, "sha256": plan_sha},
        "link_receipt": {"path": link_path.name, "sha256": link_sha},
        "executable": {"path": str(exe_path), "sha256": exe_sha},
        "input_files": {"namelist.input": {"path": str(input_path), "sha256": input_sha}},
    }
    pre_run_path = tmp_path / "pre_run_plan.json"
    pre_run_path.write_text(json.dumps(pre_run_plan))
    pre_run_sha = s15.sha256(pre_run_path)
    assert s15.verify_postlink_binding(pre_run_path, pre_run_sha, link_path, link_sha) == {
        "r6_objects_verified": 1, "launch_inputs_verified": 1,
        "prelink_inputs_verified": 4,
    }

    wrong_pre_run = dict(pre_run_plan)
    wrong_pre_run["executable"] = {"path": str(exe_path), "sha256": "0" * 64}
    pre_run_path.write_text(json.dumps(wrong_pre_run))
    with pytest.raises(s15.ProbeError, match="differs from the immutable pre-run plan"):
        s15.verify_postlink_binding(pre_run_path, s15.sha256(pre_run_path), link_path, link_sha)

    link["executable"]["sha256"] = s15.STALE_A_EXECUTABLE_SHA256
    link_path.write_text(json.dumps(link))
    with pytest.raises(s15.ProbeError, match="stale A executable"):
        s15.verify_postlink_binding(plan_path, plan_sha, link_path, s15.sha256(link_path))

    link["executable"]["sha256"] = exe_sha
    link["s15_overlay_objects"]["module_em.o"]["sha256"] = "0" * 64
    link_path.write_text(json.dumps(link))
    with pytest.raises(s15.ProbeError, match="object digest differs from r6"):
        s15.verify_postlink_binding(plan_path, plan_sha, link_path, s15.sha256(link_path))

    # The historical B20 plan remains valid as step 1, but cannot be promoted
    # into the step-2 native lane with the same receipts.
    with pytest.raises(s15.ProbeError, match="step-2 launch requires an immutable step-2 B pre-run plan"):
        s15.verify_postlink_binding(
            plan_path, plan_sha, link_path, s15.sha256(link_path),
            required_capture_step=2,
        )


def _step2_build_plan_fixture(evidence: Path) -> dict[str, object]:
    step2_public = evidence / "s15_native_step2_40s_plan_2026-09-26.json"
    step2_sha = s15.sha256(step2_public)
    public_plan = json.loads(step2_public.read_text())
    runner_path = Path(__file__).resolve().parents[2] / "harness" / "run_ss_case.py"
    return {
        "schema": "KDM6AD-S15-STEP2-BUILD-PLAN-v1",
        "capture_step": 2,
        "capture_window": s15.capture_window_for_step(2),
        "qib_summary_keys": s15.expected_qib_summary_keys(2),
        "owner_schedule": {
            "owner_site": s15.QIB_OWNER_SITE,
            "owner_name": s15.QIB_OWNER_NAME,
            "expected_summary_keys": s15.expected_qib_summary_keys(2),
            "expected_summary_cardinality": 6,
            "input_hashes": public_plan["scope"]["input_hashes"],
        },
        "run_contract": {
            "step_seconds": 20, "dt_seconds": 20, "duration_seconds": 40,
            "run_minutes": 0, "run_seconds": 40,
            "history_interval": 0, "history_interval_s": 20,
            "physics": "mp_physics=37 (Fortran KDM6)",
            "ranks": 1, "threads": 1, "fixed_dt": True,
            "history_times": [
                "2025-07-19_00:00:00",
                "2025-07-19_00:00:20",
                "2025-07-19_00:00:40",
            ],
            "expected_frame_indices": [0, 1, 2],
            "use_adaptive_time_step": False,
            "step_to_output_time": False,
            "effective_namelist_sha256": "a" * 64,
            "base_namelist_sha256": public_plan["scope"]["input_hashes"]["namelist.input"],
            "runner": {"path": str(runner_path), "sha256": s15.sha256(runner_path)},
        },
        "step2_schedule": {
            "capture_step": 2,
            "summary_keys": s15.expected_qib_summary_keys(2),
        },
        "trusted_step2_plan": {"path": str(step2_public), "sha256": step2_sha},
    }


def test_step2_launch_contract_requires_trusted_public_plan_and_fixed_schedule() -> None:
    evidence = Path(__file__).resolve().parents[1] / "evidence"
    step2_public = evidence / "s15_native_step2_40s_plan_2026-09-26.json"
    build_plan = _step2_build_plan_fixture(evidence)
    assert s15.verify_step2_build_contract(build_plan, step2_public.parent)

    step1_window = dict(build_plan, capture_window=s15.CAPTURE_WINDOW)
    with pytest.raises(s15.ProbeError, match="window or summary keys"):
        s15.verify_step2_build_contract(step1_window, step2_public.parent)

    step1_keys = dict(build_plan, qib_summary_keys=s15.expected_qib_summary_keys(1))
    with pytest.raises(s15.ProbeError, match="window or summary keys"):
        s15.verify_step2_build_contract(step1_keys, step2_public.parent)

    bad_duration = dict(build_plan, run_contract=dict(build_plan["run_contract"], duration_seconds=20))
    with pytest.raises(s15.ProbeError, match="dt=20s/40s/1-rank run contract"):
        s15.verify_step2_build_contract(bad_duration, step2_public.parent)

    b20_ref = evidence / "s15_b20_public" / \
        "s15_native_discovery_b_event_reference_2026-09-26_public.json"
    wrong_public = dict(build_plan,
                        trusted_step2_plan={"path": str(b20_ref), "sha256": s15.sha256(b20_ref)})
    with pytest.raises(s15.ProbeError, match="step-2 plan schema"):
        s15.verify_step2_build_contract(wrong_public, b20_ref.parent)


@pytest.mark.parametrize("path", [
    ("capture_step",),
    ("capture_window", "first_timestep"),
    ("capture_window", "last_timestep"),
    ("qib_summary_keys", 0, 1),  # RK stage 1 is numerically equal to True.
    ("qib_summary_keys", 0, 3),  # tile lower bound 1 is numerically equal to True.
    ("owner_schedule", "owner_site"),
    ("owner_schedule", "expected_summary_cardinality"),
    ("owner_schedule", "expected_summary_keys", 0, 1),
    ("owner_schedule", "expected_summary_keys", 0, 3),
    ("step2_schedule", "capture_step"),
    ("step2_schedule", "summary_keys", 0, 1),
    ("step2_schedule", "summary_keys", 0, 3),
    ("run_contract", "step_seconds"),
    ("run_contract", "dt_seconds"),
    ("run_contract", "duration_seconds"),
    ("run_contract", "run_minutes"),
    ("run_contract", "run_seconds"),
    ("run_contract", "history_interval"),
    ("run_contract", "history_interval_s"),
    ("run_contract", "ranks"),
    ("run_contract", "threads"),
    ("run_contract", "expected_frame_indices", 1),
])
def test_step2_build_contract_rejects_json_boolean_in_every_numeric_class(
        path: tuple[object, ...]) -> None:
    evidence = Path(__file__).resolve().parents[1] / "evidence"
    plan = copy.deepcopy(_step2_build_plan_fixture(evidence))
    target: object = plan
    for part in path[:-1]:
        target = target[part]  # type: ignore[index]
    target[path[-1]] = True  # type: ignore[index]
    with pytest.raises(s15.ProbeError, match="JSON integer"):
        s15.verify_step2_build_contract(
            plan, evidence / "s15_native_step2_40s_plan_2026-09-26.json"
        )


@pytest.mark.parametrize("path", [
    ("scope", "capture_timestep"),
    ("scope", "dt_seconds"),
    ("scope", "duration_seconds"),
    ("scope", "ranks"),
    ("scope", "threads"),
    ("probe", "default_capture_step"),
    ("probe", "capture_window", "first_timestep"),
    ("probe", "capture_window", "last_timestep"),
    ("probe", "default_capture_window", "first_timestep"),
    ("probe", "default_capture_window", "last_timestep"),
    ("probe", "qib_owner", "site"),
    ("probe", "call_owner_order", 0, "site"),
    ("probe", "call_owner_order", 1, "site"),
    ("probe", "call_owner_order", 2, "site"),
    ("probe", "call_owner_order", 3, "site"),
    ("probe", "call_owner_order", 4, "site"),
    ("owner_schedule", "owner_site"),
    ("owner_schedule", "rk_stages", 0),
    ("owner_schedule", "rk_stages", 1),
    ("owner_schedule", "rk_stages", 2),
    ("owner_schedule", "tile_bounds", 0, 0),
    ("owner_schedule", "tile_bounds", 0, 2),
    ("owner_schedule", "tile_bounds", 1, 0),
    ("owner_schedule", "expected_summary_cardinality"),
    ("owner_schedule", "expected_summary_keys", 0, 1),
    ("owner_schedule", "expected_summary_keys", 0, 3),
    ("melt_schedule", "capture_timestep"),
    ("scope", "dt_seconds"),
    ("scope", "duration_seconds"),
    ("scope", "ranks"),
    ("scope", "threads"),
])
def test_trusted_public_plan_rejects_boolean_numeric_mutations(path: tuple[object, ...]) -> None:
    evidence = Path(__file__).resolve().parents[1] / "evidence"
    original = evidence / "s15_native_step2_40s_plan_2026-09-26.json"
    plan = json.loads(original.read_text())
    target: object = plan
    for part in path[:-1]:
        target = target[part]  # type: ignore[index]
    target[path[-1]] = True  # type: ignore[index]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", dir=evidence,
                                     prefix=".s15_step2_bad_type_") as stream:
        stream.write(json.dumps(plan))
        stream.flush()
        with pytest.raises(s15.ProbeError, match="code-fixed contract|JSON integer"):
            s15.verify_step2_public_plan(Path(stream.name), s15.sha256(Path(stream.name)))


@pytest.mark.parametrize(("path", "replacement"), [
    (("melt_schedule", "capture_timestep"), 1),
    (("probe", "default_capture_window", "first_timestep"), 2),
    (("owner_schedule", "rk_stages"), [1, 2]),
    (("owner_schedule", "tile_bounds", 0), [1, 235, 1, 141]),
    (("probe", "call_owner_order", 4, "site"), 6),
    (("probe", "call_owner_order", 4, "loop"), "other_owner_loop"),
    (("scope", "input_hashes", "wrfinput_d01"), "0" * 64),
    (("fresh_step2_build_pins", "macro"), "OTHER_CAPTURE_MACRO"),
    (("pair_acceptance", "empty_unpopulated_streams"), "pass empty captures"),
])
def test_trusted_public_plan_rejects_operational_tree_mutations(
        path: tuple[object, ...], replacement: object) -> None:
    evidence = Path(__file__).resolve().parents[1] / "evidence"
    original = evidence / "s15_native_step2_40s_plan_2026-09-26.json"
    plan = json.loads(original.read_text())
    target: object = plan
    for part in path[:-1]:
        target = target[part]  # type: ignore[index]
    target[path[-1]] = replacement  # type: ignore[index]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", dir=evidence,
                                     prefix=".s15_step2_bad_contract_") as stream:
        stream.write(json.dumps(plan))
        stream.flush()
        with pytest.raises(s15.ProbeError, match="code-fixed contract"):
            s15.verify_step2_public_plan(Path(stream.name), s15.sha256(Path(stream.name)))


@pytest.mark.parametrize(("schema", "pinned_step", "requested_step"), [
    ("KDM6AD-S15-STEP2-BUILD-PLAN-v1", 2, 1),
    ("KDM6AD-S15-B20-BUILD-PLAN-v1", 1, 2),
])
def test_explicit_cli_capture_step_must_match_plan(schema: str, pinned_step: int,
                                                   requested_step: int) -> None:
    if pinned_step == 2:
        plan = {"schema": schema, "capture_step": pinned_step}
    else:
        plan = {"schema": schema, "capture_window": s15.capture_window_for_step(pinned_step)}
    with pytest.raises(s15.ProbeError, match="differs from plan-pinned step"):
        s15.require_capture_step_matches(plan, requested_step)


@pytest.mark.parametrize(("pinned_step", "requested_step"), [(2, 1), (1, 2)])
def test_prelink_cli_rejects_explicit_step_mismatch(tmp_path: Path,
                                                   pinned_step: int,
                                                   requested_step: int) -> None:
    evidence = Path(__file__).resolve().parents[1] / "evidence"
    if pinned_step == 2:
        plan = _step2_build_plan_fixture(evidence)
    else:
        plan = {"schema": "KDM6AD-S15-B20-BUILD-PLAN-v1",
                "capture_window": s15.capture_window_for_step(1)}
    # Reach the mismatch guard before prelink inputs are examined.
    plan_path = tmp_path / f"step{pinned_step}.json"
    plan_path.write_text(json.dumps(plan))
    rc = s15._main([
        "prelink-check", "--plan", str(plan_path), "--plan-sha256", s15.sha256(plan_path),
        "--capture-step", str(requested_step),
    ])
    assert rc == 2


@pytest.mark.parametrize(("schema", "pinned_step", "requested_step"), [
    ("KDM6AD-S15-STEP2-BUILD-PLAN-v1", 2, 1),
    ("KDM6AD-S15-B20-BUILD-PLAN-v1", 1, 2),
])
def test_launch_gate_rejects_explicit_step_mismatch_before_receipt_validation(
        tmp_path: Path, schema: str, pinned_step: int, requested_step: int) -> None:
    if pinned_step == 2:
        plan = {"schema": schema, "capture_step": pinned_step}
    else:
        plan = {"schema": schema, "capture_window": s15.capture_window_for_step(pinned_step)}
    plan_path = tmp_path / "build.json"
    link_path = tmp_path / "link.json"
    plan_path.write_text(json.dumps(plan))
    link_path.write_text("{}")
    with pytest.raises(s15.ProbeError, match="differs from plan-pinned step"):
        s15.verify_postlink_binding(
            plan_path, s15.sha256(plan_path), link_path, s15.sha256(link_path),
            required_capture_step=requested_step,
        )


@pytest.mark.parametrize(("pinned_step", "requested_step"), [(2, 1), (1, 2)])
def test_launch_cli_rejects_explicit_step_mismatch(tmp_path: Path,
                                                  pinned_step: int,
                                                  requested_step: int) -> None:
    if pinned_step == 2:
        plan = {"schema": "KDM6AD-S15-STEP2-BUILD-PLAN-v1", "capture_step": 2}
    else:
        plan = {"schema": "KDM6AD-S15-B20-BUILD-PLAN-v1",
                "capture_window": s15.capture_window_for_step(1)}
    plan_path = tmp_path / "build.json"
    link_path = tmp_path / "link.json"
    plan_path.write_text(json.dumps(plan))
    link_path.write_text("{}")
    rc = s15._main([
        "launch-check", "--plan", str(plan_path), "--plan-sha256", s15.sha256(plan_path),
        "--link-receipt", str(link_path), "--link-receipt-sha256", s15.sha256(link_path),
        "--capture-step", str(requested_step),
    ])
    assert rc == 2


def test_strip_audit_restores_original_base_arm_byte_for_byte() -> None:
    original = "before\n      old statement\n    after\n"
    instrumented = "before\n" + s15._s15_guard(
        "replace", "      new statement\n", "      old statement\n"
    ) + "    after\n"
    assert s15._s15_strip(instrumented) == original


def test_qib_index_import_is_guarded_and_restores_original_source() -> None:
    source = (
        "  USE module_state_description, only: param_first_scalar, p_qr, p_qv, p_qc, "
        "p_qg, p_qi, p_qs, tiedtkescheme,ntiedtkescheme, heldsuarez, &\n"
    )
    generated = s15.add_qib_index_import(source)
    assert "p_qi, p_qs, p_qib, tiedtkescheme" in generated
    assert "#ifdef KDM6_PROGB_VALIDITY_CAPTURE" in generated
    assert s15._s15_strip(generated) == source


def test_progb_gate_snapshot_precedes_continued_call_arguments() -> None:
    source = "".join(
        "   call ProgB_param(a, &\n"
        "                   b, &\n"
        f"! S10_CAPTURE_BEGIN:progb_call_{site}\n"
        f"#ifdef {s15.S10_MACRO}\n"
        "                   c)\n"
        "#else\n"
        "                   c)\n"
        "#endif\n"
        f"! S10_CAPTURE_END:progb_call_{site}\n"
        for site in range(1, 8)
    )
    generated = s15._record_progb_gate_inputs(source)
    for site in range(1, 8):
        snapshot = generated.index(f"KDM6AD-S15-PROBE BEGIN:progb_gate_inputs_{site}")
        call = generated.index("call ProgB_param(a, &", snapshot)
        call_guard = generated.index(f"#ifdef {s15.S10_MACRO}", call)
        assert snapshot < call < call_guard
        assert generated.index("                   b, &", call) < generated.index(
            "                   c)", call
        )
    assert s15._s15_strip(generated) == source


def test_s15_melt_locals_precede_complete_integer_declaration() -> None:
    source = (
        "   integer                            :: i, j, k, mstepmax,mstepmax_i,         &\n"
        "                                         iprt, latd, lond, loop, loops, ifsat, &\n"
        "                                         n, idim, kdim\n"
    )
    generated = s15._insert_s15_mp_locals(source)
    s15_locals = generated.index("KDM6AD-S15-PROBE BEGIN:mp_locals")
    integer_statement = generated.index("   integer                            :: i, j, k")
    assert s15_locals < integer_statement
    assert s15._s15_strip(generated) == source


def test_qib_capture_threads_domain_timestep_into_all_rk_calls() -> None:
    call = (
        "CALL rk_update_scalar(scalar_1, rk_step=rk_step, dt=dt_rk, &\n"
        "                     kte=k_end)\n"
    )
    source = call * 5
    generated = s15.instrument_solve_em(source)
    assert generated.count("s15_step=grid%itimestep") == 5
    assert all(f"s15_owner={site}" in generated for site in range(1, 6))
    assert [generated.count(f"s15_owner={site}") for site in range(1, 6)] == [1] * 5
    assert "s15_step=itimestep" not in generated
    assert s15._s15_strip(generated) == source


def test_shadow_digest_audit_rejects_active_macro_payload_changes(tmp_path: Path) -> None:
    staged = tmp_path / "module_em.F"
    staged.write_text("#ifdef KDM6_PROGB_VALIDITY_CAPTURE\nlogger\n#endif\n")
    pinned = s15.sha256(staged)
    s15.check_shadow_digest(staged, pinned, "module_em.F")
    staged.write_text("#ifdef KDM6_PROGB_VALIDITY_CAPTURE\nlogger\nphysics_change\n#endif\n")
    with pytest.raises(s15.ProbeError, match="generated shadow digest mismatch"):
        s15.check_shadow_digest(staged, pinned, "module_em.F")


def test_s15_capture_switch_also_enables_s10_validity_mask() -> None:
    s10_gate = (
        "     kdm6_progb_capture_env = ''\n"
        "     call get_environment_variable('KDM6_PROGB_VALIDITY_CAPTURE_LOG', &\n"
        "          kdm6_progb_capture_env)\n"
        "     capture_enabled = (trim(kdm6_progb_capture_env) == '1')\n"
    )
    generated = s15.unify_capture_gate(s10_gate)
    assert "KDM6_S15_NATIVE_CAPTURE_LOG" in generated
    assert "KDM6_PROGB_VALIDITY_CAPTURE_LOG" in generated
    assert s15._s15_strip(generated) == s10_gate


def test_gate_input_capture_wraps_all_seven_progB_calls_and_strips_exactly() -> None:
    source = "".join(
        f"   call ProgB_param({i}, &\n"
        f"! S10_CAPTURE_BEGIN:progb_call_{i}\n#ifdef {s15.S10_MACRO}\n"
        "                   value, &\n"
        "                   capture_args)\n#else\n"
        "                   value, &\n"
        "                   original_args)\n#endif\n"
        f"! S10_CAPTURE_END:progb_call_{i}\n"
        for i in range(1, 8)
    )
    instrumented = s15._record_progb_gate_inputs(source)
    assert instrumented.count("s15_gate_qg(i,k) = qrs_tmp(i,k,3)") == 7
    assert instrumented.count("s15_gate_brs(i,k) = brs(i,k)") == 7
    assert s15._s15_strip(instrumented) == source


def test_melt_replayer_never_decodes_undefined_rhox() -> None:
    row = _melt_row()
    replay = s15.replay_melt(row)
    assert replay["rhox_valid"] is False
    assert replay["rhox_used"] is None
    assert replay["apparent_density_raw"] is None
    assert replay["pair_class"] == "invalid_nonpositive_volume"
    assert replay["post_volume_finite"] is None
    assert replay["post_pair_class"] == "untrusted_rhox_undefined"
    assert replay["apparent_density_post"] is None
    assert replay["thermal_latent_exact_match"] is None
    assert replay["thermal_work_j_m2_conditional"] is None
    plausible_but_undefined = dict(row, brs1=s15.f32_word(0.001875))
    untrusted = s15.replay_melt(plausible_but_undefined)
    assert untrusted["post_pair_class"] == "untrusted_rhox_undefined"
    assert untrusted["apparent_density_post"] is None
    assert untrusted["thermal_latent_exact_match"] is None
    invalid_output = dict(row, brs1="FF800000")
    assert s15.replay_melt(invalid_output)["post_volume_finite"] is None


def test_melt_replayer_refuses_a_rhox_word_when_validity_is_false() -> None:
    row = dict(_melt_row(), rhox=s15.f32_word(400.0))
    with pytest.raises(s15.ProbeError, match="must not be read"):
        s15.replay_melt(row)


def test_plan_rejects_capture_without_qib_summary_census(tmp_path: Path) -> None:
    row = {
        "kind": "QIB", "step": "7", "rk": "2", "owner": str(s15.QIB_OWNER_SITE),
        "tile_i0": "1", "tile_i1": "2",
        "tile_j0": "3", "tile_j1": "4", "i": "1", "j": "3", "k": "8",
        "before": "00000000", "after": "BF800000", "reference": "00000000",
        "advect": "00000000", "msfty": "3F800000", "other_tend": "BF800000",
        "dt": "3F800000", "c1": "00000000", "c2": "3F800000",
        "muold": "3F800000", "munew": "3F800000",
    }
    capture = tmp_path / "events.csv"
    capture.write_text(",".join(s15.QIB_COLUMNS) + "\n" + ",".join(row[k] for k in s15.QIB_COLUMNS) + "\n")
    plan, plan_sha = _write_independent_plan(tmp_path, capture, {
        "capture_window": s15.CAPTURE_WINDOW,
        "qib_transition_count": 1,
        "qib_summary_keys": [[1, 2, s15.QIB_OWNER_SITE, 1, 2, 3, 4]],
        "qib_first_event_keys": [[1, 2, s15.QIB_OWNER_SITE, 1, 3, 8]],
        "melt_first_event_count": 0,
        "melt_first_event_keys": [],
        "first_qib_key": [1, 2, s15.QIB_OWNER_SITE, 1, 3, 8],
        "first_melt_key": None,
    })
    rows, summaries = s15.parse_capture(capture)
    assert summaries is None
    with pytest.raises(s15.ProbeError, match="requires the complete S15QC"):
        s15.verify_plan(rows, plan, summaries, plan_sha, capture)


def test_plan_rejects_summary_keys_outside_source_owner_schedule(tmp_path: Path) -> None:
    capture = tmp_path / "owner_schedule.txt"
    capture.write_text("\n".join(_summary_lines()) + "\n")
    expected = {
        "capture_window": s15.CAPTURE_WINDOW,
        "qib_transition_count": 0,
        "qib_owner_site": s15.QIB_OWNER_SITE,
        "qib_owner_name": s15.QIB_OWNER_NAME,
        "qib_summary_keys": s15.expected_qib_summary_keys(),
        "qib_first_event_keys": [None] * len(s15.expected_qib_summary_keys()),
        "melt_first_event_count": 0,
        "melt_first_event_keys": [],
        "first_qib_key": None,
        "first_melt_key": None,
    }
    plan, _ = _write_independent_plan(tmp_path, capture, expected)
    value = json.loads(plan.read_text())
    value["owner_schedule"]["expected_summary_keys"] = [
        [1, 1, s15.QIB_OWNER_SITE, 10, 20, 3, 4]
    ]
    plan.write_text(json.dumps(value, sort_keys=True))
    pinned = s15.sha256(plan)
    rows, summaries = s15.parse_capture(capture)
    with pytest.raises(s15.ProbeError, match="source-declared owner schedule"):
        s15.verify_plan(rows, plan, summaries, pinned, capture)


def _signed(word: str) -> int:
    return struct.unpack(">i", bytes.fromhex(word))[0]


def _expected_qib_rows(first_by_key: dict[tuple[int, ...], list[int] | None]) -> list[list[int] | None]:
    return [first_by_key.get(tuple(key)) for key in s15.expected_qib_summary_keys()]


def _melt_row() -> dict[str, str]:
    return {
        "kind": "MELT", "step": "1", "lat": "11", "substep": "0",
        "progb_site": "7", "i": "4", "k": "9",
        "qg0": s15.f32_word(1.0), "brs0": s15.f32_word(0.0),
        "qcrmin": s15.f32_word(2.0), "brs_min": s15.f32_word(1.0e-15),
        "qg_gate": s15.f32_word(1.0), "brs_gate": s15.f32_word(0.0),
        "rhox_valid": "0", "rhox": "", "t0": s15.f32_word(273.0),
        "t1": s15.f32_word(248.0), "cpm": s15.f32_word(1000.0),
        "xlf": s15.f32_word(100000.0), "pgmlt": s15.f32_word(-0.25),
        "qr0": s15.f32_word(1.0), "qr1": s15.f32_word(1.25),
        "qg1": s15.f32_word(0.75), "brs1": s15.f32_word(0.0),
        "den": s15.f32_word(2.0), "dz": s15.f32_word(3.0),
    }


def _native_melt_line(row: dict[str, str]) -> str:
    fields = [int(row[k]) for k in ("step", "lat", "substep", "progb_site", "i", "k")]
    before = [row[k] for k in ("qg0", "brs0", "qcrmin", "brs_min", "qg_gate", "brs_gate")]
    fields.extend(_signed(word) for word in before)
    fields.append(int(row["rhox_valid"]))
    if row["rhox_valid"] == "1":
        fields.append(_signed(row["rhox"]))
    after = [row[k] for k in ("t0", "t1", "cpm", "xlf", "pgmlt", "qr0", "qr1",
                               "qg1", "brs1", "den", "dz")]
    fields.extend(_signed(word) for word in after)
    return "S15M " + " ".join(map(str, fields))


def _summary_lines(counts: dict[tuple[int, ...], int] | None = None) -> list[str]:
    """Build the source-predeclared six-key owner/tile/RK summary census."""
    counts = counts or {}
    return [f"S15QC {' '.join(map(str, key))} {counts.get(tuple(key), 0)}"
            for key in s15.expected_qib_summary_keys()]


def _write_independent_plan(tmp_path: Path, capture: Path,
                            expected: dict[str, object]) -> tuple[Path, str]:
    expected = {"qib_owner_site": s15.QIB_OWNER_SITE,
                "qib_owner_name": s15.QIB_OWNER_NAME, **expected}
    owner_schedule = {
        "owner_site": s15.QIB_OWNER_SITE,
        "owner_name": s15.QIB_OWNER_NAME,
        "expected_summary_keys": s15.expected_qib_summary_keys(),
        "expected_summary_cardinality": len(s15.expected_qib_summary_keys()),
    }
    reference_path = tmp_path / "independent_reference.json"
    reference_path.write_text(json.dumps(
        {"schema": s15.REFERENCE_SCHEMA, **expected}, sort_keys=True
    ))
    plan_path = tmp_path / "expected_plan.json"
    plan = {
        "protocol": s15.PROTOCOL,
        "status": "independent_expected_plan",
        **expected,
        "owner_schedule": owner_schedule,
        "capture_sha256": s15.sha256(capture),
        "independent_reference": {
            "path": reference_path.name,
            "sha256": s15.sha256(reference_path),
            "method": "independent uninstrumented full-field scan",
        },
    }
    plan_path.write_text(json.dumps(plan, sort_keys=True))
    return plan_path, s15.sha256(plan_path)


def test_native_stream_replay_links_first_events_to_stage_summary(tmp_path: Path) -> None:
    q_words = [
        "00000000", "BF800000", "00000000", "00000000", "3F800000", "BF800000",
        "3F800000", "00000000", "3F800000", "3F800000", "3F800000",
    ]
    q_line = "S15Q " + " ".join(map(str, [1, 2, s15.QIB_OWNER_SITE,
                                             1, 235, 1, 142, 206, 2, 8])) + " " + \
        " ".join(map(str, map(_signed, q_words)))
    summary_lines = _summary_lines({(1, 2, s15.QIB_OWNER_SITE, 1, 235, 1, 142): 1})
    melt_words = [s15.f32_word(value) for value in
                  (1.0, 0.0, 2.0, 1.0e-15, 1.0, 0.0, 273.0, 248.0, 1000.0,
                   100000.0, -0.25, 1.0, 1.25, 0.75, 0.0, 2.0, 3.0)]
    melt_meta = [1, 11, 0, 7, 4, 9]
    # A false validity bit has no following rhox word.
    m_line = "S15M " + " ".join(map(str, melt_meta + list(map(_signed, melt_words[:6])) + [0] + list(map(_signed, melt_words[6:]))))
    capture = tmp_path / "stdout.txt"
    capture.write_text("noise before records\n" + q_line + "\n" +
                       "\n".join(summary_lines) + "\n" + m_line + "\n")
    rows, summaries = s15.parse_capture(capture)
    assert len(rows) == 2
    assert summaries == [tuple(key + [1 if key == [1, 2, s15.QIB_OWNER_SITE, 1, 235, 1, 142] else 0])
                         for key in s15.expected_qib_summary_keys()]
    expected = {
        "capture_window": s15.CAPTURE_WINDOW,
        "qib_transition_count": 1, "melt_first_event_count": 1,
        "melt_first_event_keys": [[1, 11, 0, 7, 4, 9]],
        "qib_summary_keys": s15.expected_qib_summary_keys(),
        "qib_first_event_keys": _expected_qib_rows({
            (1, 2, s15.QIB_OWNER_SITE, 1, 235, 1, 142):
                [1, 2, s15.QIB_OWNER_SITE, 206, 2, 8],
        }),
        "first_qib_key": [1, 2, s15.QIB_OWNER_SITE, 206, 2, 8],
        "first_melt_key": [1, 11, 0, 7, 4, 9],
    }
    plan, plan_sha = _write_independent_plan(tmp_path, capture, expected)
    assert s15.verify_plan(rows, plan, summaries, plan_sha, capture) == {
        "qib_transitions": 1, "trace_melt_first_events": 1,
    }

    out_of_tile = [dict(row) for row in rows]
    out_of_tile[0]["i"] = "236"
    with pytest.raises(s15.ProbeError, match="outside its owned tile"):
        s15.verify_plan(out_of_tile, plan, summaries, plan_sha, capture)

    repeated_melt = [dict(row) for row in rows] + [dict(rows[1], i="5")]
    with pytest.raises(s15.ProbeError, match="duplicate trace-melt witness for timestep/latitude-row/substep"):
        s15.verify_plan(repeated_melt, plan, summaries, plan_sha, capture)

    without_summary = tmp_path / "no_summary.txt"
    without_summary.write_text("noise\n" + q_line + "\n" + m_line + "\n")
    missing_rows, missing_summaries = s15.parse_capture(without_summary)
    assert missing_summaries == []
    missing_plan, missing_plan_sha = _write_independent_plan(tmp_path, without_summary, expected)
    with pytest.raises(s15.ProbeError, match="requires the complete S15QC"):
        s15.verify_plan(missing_rows, missing_plan, missing_summaries,
                        missing_plan_sha, without_summary)


def test_plan_pins_each_positive_tile_first_qib_cell_key(tmp_path: Path) -> None:
    words = [
        "00000000", "BF800000", "00000000", "00000000", "3F800000", "BF800000",
        "3F800000", "00000000", "3F800000", "3F800000", "3F800000",
    ]
    def q_row(tile: tuple[int, int, int, int], cell: tuple[int, int, int]) -> str:
        return "S15Q " + " ".join(map(str, [1, 2, s15.QIB_OWNER_SITE, *tile, *cell])) + " " + \
            " ".join(map(str, map(_signed, words)))

    tile_a = (1, 235, 1, 142)
    tile_b = (1, 235, 143, 283)
    first = q_row(tile_a, (1, 3, 8))
    second = q_row(tile_b, (5, 150, 9))
    summaries_text = "\n".join(_summary_lines({
        (1, 2, s15.QIB_OWNER_SITE, *tile_a): 1,
        (1, 2, s15.QIB_OWNER_SITE, *tile_b): 1,
    })) + "\n"
    capture = tmp_path / "two_tiles.txt"
    capture.write_text(first + "\n" + second + "\n" + summaries_text)
    rows, summaries = s15.parse_capture(capture)
    expected = {
        "capture_window": s15.CAPTURE_WINDOW,
        "qib_transition_count": 2,
        "qib_summary_keys": s15.expected_qib_summary_keys(),
        "qib_first_event_keys": _expected_qib_rows({
            (1, 2, s15.QIB_OWNER_SITE, *tile_a): [1, 2, s15.QIB_OWNER_SITE, 1, 3, 8],
            (1, 2, s15.QIB_OWNER_SITE, *tile_b): [1, 2, s15.QIB_OWNER_SITE, 5, 150, 9],
        }),
        "melt_first_event_count": 0,
        "melt_first_event_keys": [],
        "first_qib_key": [1, 2, s15.QIB_OWNER_SITE, 1, 3, 8],
        "first_melt_key": None,
    }
    plan, plan_sha = _write_independent_plan(tmp_path, capture, expected)
    assert s15.verify_plan(rows, plan, summaries, plan_sha, capture)["qib_transitions"] == 2

    # Same counts and tiles, but a different in-tile first cell on the second tile.
    relocated = q_row(tile_b, (6, 150, 39))
    bad_capture = tmp_path / "two_tiles_relocated.txt"
    bad_capture.write_text(first + "\n" + relocated + "\n" + summaries_text)
    bad_rows, bad_summaries = s15.parse_capture(bad_capture)
    bad_plan, bad_plan_sha = _write_independent_plan(tmp_path, bad_capture, expected)
    with pytest.raises(s15.ProbeError, match="per-tile first QIB event key"):
        s15.verify_plan(bad_rows, bad_plan, bad_summaries, bad_plan_sha, bad_capture)


def test_plan_pins_complete_first_melt_key_census(tmp_path: Path) -> None:
    first = _melt_row()
    second = dict(first, substep="1", i="5")
    summary = "\n".join(_summary_lines())
    capture = tmp_path / "two_substeps.txt"
    capture.write_text(summary + "\n" + _native_melt_line(first) + "\n" +
                       _native_melt_line(second) + "\n")
    rows, summaries = s15.parse_capture(capture)
    expected = {
        "capture_window": s15.CAPTURE_WINDOW,
        "qib_transition_count": 0,
        "qib_summary_keys": s15.expected_qib_summary_keys(),
        "qib_first_event_keys": [None] * len(s15.expected_qib_summary_keys()),
        "melt_first_event_count": 2,
        "melt_first_event_keys": [[1, 11, 0, 7, 4, 9], [1, 11, 1, 7, 5, 9]],
        "first_qib_key": None,
        "first_melt_key": [1, 11, 0, 7, 4, 9],
    }
    plan, plan_sha = _write_independent_plan(tmp_path, capture, expected)
    assert s15.verify_plan(rows, plan, summaries, plan_sha, capture)["trace_melt_first_events"] == 2

    moved = dict(second, substep="2")
    bad_capture = tmp_path / "two_substeps_moved.txt"
    bad_capture.write_text(summary + "\n" + _native_melt_line(first) + "\n" +
                           _native_melt_line(moved) + "\n")
    bad_rows, bad_summaries = s15.parse_capture(bad_capture)
    bad_plan, bad_plan_sha = _write_independent_plan(tmp_path, bad_capture, expected)
    with pytest.raises(s15.ProbeError, match="first-melt key census"):
        s15.verify_plan(bad_rows, bad_plan, bad_summaries, bad_plan_sha, bad_capture)



def test_native_melt_stream_decodes_rhox_only_in_valid_gate_arm(tmp_path: Path) -> None:
    row = dict(_melt_row(), qg_gate=s15.f32_word(3.0), rhox_valid="1",
               rhox=s15.f32_word(400.0), brs1="BA23D70A")
    words_before = [row[k] for k in ("qg0", "brs0", "qcrmin", "brs_min", "qg_gate", "brs_gate")]
    words_after = [row[k] for k in ("t0", "t1", "cpm", "xlf", "pgmlt", "qr0", "qr1",
                                     "qg1", "brs1", "den", "dz")]
    ints = [1, 11, 0, 7, 4, 9] + [_signed(w) for w in words_before] + [1, _signed(row["rhox"])]
    ints += [_signed(w) for w in words_after]
    capture = tmp_path / "valid_melt.txt"
    capture.write_text("S15M " + " ".join(map(str, ints)) + "\n")
    rows, summaries = s15.parse_capture(capture)
    assert summaries == []
    assert rows[0]["rhox_valid"] == "1"
    assert s15.f32(rows[0]["rhox"]) == 400.0


def test_independent_plan_requires_external_digest_pin(tmp_path: Path) -> None:
    capture = tmp_path / "stream.txt"
    capture.write_text("\n".join(_summary_lines()) + "\n")
    expected = {
        "capture_window": s15.CAPTURE_WINDOW,
        "qib_transition_count": 0,
        "qib_summary_keys": s15.expected_qib_summary_keys(),
        "qib_first_event_keys": [None] * len(s15.expected_qib_summary_keys()),
        "melt_first_event_count": 0,
        "melt_first_event_keys": [],
        "first_qib_key": None,
        "first_melt_key": None,
    }
    plan, pinned = _write_independent_plan(tmp_path, capture, expected)
    plan.write_text(plan.read_text().replace('"qib_transition_count": 0', '"qib_transition_count": 1'))
    rows, summaries = s15.parse_capture(capture)
    with pytest.raises(s15.ProbeError, match="external pin"):
        s15.verify_plan(rows, plan, summaries, pinned, capture)


def test_qib_summary_census_rejects_negative_tile_transition_count(tmp_path: Path) -> None:
    q_words = [
        "00000000", "BF800000", "00000000", "00000000", "3F800000", "BF800000",
        "3F800000", "00000000", "3F800000", "3F800000", "3F800000",
    ]
    q_line = "S15Q " + " ".join(map(str, [1, 2, s15.QIB_OWNER_SITE,
                                             1, 235, 1, 142, 1, 3, 8])) + " " + \
        " ".join(map(str, map(_signed, q_words)))
    capture = tmp_path / "negative_count.txt"
    summary_lines = _summary_lines({(1, 2, s15.QIB_OWNER_SITE, 1, 235, 1, 142): 2})
    summary_lines[-1] = summary_lines[-1].rsplit(" ", 1)[0] + " -1"
    capture.write_text(q_line + "\n" + "\n".join(summary_lines) + "\n")
    rows, summaries = s15.parse_capture(capture)
    expected = {
        "capture_window": s15.CAPTURE_WINDOW,
        "qib_transition_count": 1,
        "qib_summary_keys": s15.expected_qib_summary_keys(),
        "qib_first_event_keys": _expected_qib_rows({
            (1, 2, s15.QIB_OWNER_SITE, 1, 235, 1, 142):
                [1, 2, s15.QIB_OWNER_SITE, 1, 3, 8],
        }),
        "melt_first_event_count": 0,
        "melt_first_event_keys": [],
        "first_qib_key": [1, 2, s15.QIB_OWNER_SITE, 1, 3, 8],
        "first_melt_key": None,
    }
    plan, pinned = _write_independent_plan(tmp_path, capture, expected)
    with pytest.raises(s15.ProbeError, match="cannot be negative"):
        s15.verify_plan(rows, plan, summaries, pinned, capture)


def test_melt_replayer_checks_gate_cap_temperature_and_positive_measure() -> None:
    valid = dict(_melt_row(), qg_gate=s15.f32_word(3.0), rhox_valid="1",
                 rhox=s15.f32_word(400.0), brs1="BA23D70A")
    replay = s15.replay_melt(valid)
    assert replay["thermal_work_j_m2_conditional"] == replay["latent_cooling_j_m2_conditional"]
    assert replay["thermal_latent_exact_match"] is True
    assert replay["brs1_update_bits"] == "BA23D70A"
    assert replay["brs1_replay_scope"] == "source_order_f32_update"

    assert replay["rhox_used"] == 400.0

    wrong_post_volume = dict(valid, brs1=s15.f32_word(12345.0))
    with pytest.raises(s15.ProbeError, match="brs update does not replay"):
        s15.replay_melt(wrong_post_volume)

    bad_gate = dict(valid, qg_gate=s15.f32_word(1.0))
    with pytest.raises(s15.ProbeError, match="validity does not match"):
        s15.replay_melt(bad_gate)

    overdraw = dict(valid, pgmlt="C0000000", qg1="BF800000", qr1="40400000")
    with pytest.raises(s15.ProbeError, match="invalid post-melt mass state|exceeds available"):
        s15.replay_melt(overdraw)

    bad_measure = dict(valid, den="C0000000")
    with pytest.raises(s15.ProbeError, match="positive physical measure"):
        s15.replay_melt(bad_measure)

    bad_temperature = dict(valid, t1=valid["t0"])
    with pytest.raises(s15.ProbeError, match="temperature update does not replay"):
        s15.replay_melt(bad_temperature)

    invalid_rhox = dict(_melt_row(), rhox_valid="1", rhox=s15.f32_word(400.0))
    with pytest.raises(s15.ProbeError, match="validity does not match"):
        s15.replay_melt(invalid_rhox)

    nonfinite = dict(valid, qg0="7F800000", qcrmin="7F800000", qg1="7F800000")
    with pytest.raises(s15.ProbeError, match="non-finite required melt operand"):
        s15.replay_melt(nonfinite)


def _write_window_plan(tmp_path: Path, capture: Path, capture_step: int,
                       expected: dict[str, object], method: str) -> tuple[Path, str]:
    expected = {"qib_owner_site": s15.QIB_OWNER_SITE,
                "qib_owner_name": s15.QIB_OWNER_NAME,
                "capture_window": s15.capture_window_for_step(capture_step),
                **expected}
    schedule = s15.expected_qib_summary_keys(capture_step)
    expected["qib_summary_keys"] = schedule
    owner_schedule = {
        "owner_site": s15.QIB_OWNER_SITE,
        "owner_name": s15.QIB_OWNER_NAME,
        "expected_summary_keys": schedule,
        "expected_summary_cardinality": len(schedule),
    }
    reference_path = tmp_path / f"step{capture_step}_reference.json"
    reference_path.write_text(json.dumps(
        {"schema": s15.REFERENCE_SCHEMA, **expected}, sort_keys=True
    ))
    plan_path = tmp_path / f"step{capture_step}_plan.json"
    plan = {
        "protocol": s15.PROTOCOL,
        "status": "independent_expected_plan",
        **expected,
        "owner_schedule": owner_schedule,
        "capture_sha256": s15.sha256(capture),
        "independent_reference": {
            "path": reference_path.name,
            "sha256": s15.sha256(reference_path),
            "method": method,
        },
    }
    plan_path.write_text(json.dumps(plan, sort_keys=True))
    return plan_path, s15.sha256(plan_path)


def test_public_b20_step1_projection_still_replays_with_synthetic_event_operands(
    tmp_path: Path,
) -> None:
    evidence = Path(__file__).resolve().parents[1] / "evidence" / "s15_b20_public"
    manifest_path = evidence / "s15_native_B_20S_public_manifest.json"
    reference_path = evidence / "s15_native_discovery_b_event_reference_2026-09-26_public.json"
    manifest = json.loads(manifest_path.read_text())
    projected_ref = json.loads(reference_path.read_text())["reference"]
    manifest_projection = next(
        item for item in manifest["public_projections"]
        if item["filename"].endswith("s15_native_discovery_b_event_reference_2026-09-26_public.json")
    )
    assert s15.sha256(manifest_path) == manifest_path.with_name(
        manifest_path.name + ".sha256"
    ).read_text().split()[0]
    assert s15.sha256(reference_path) == manifest_projection["sha256"]
    assert s15.CAPTURE_WINDOW == s15.capture_window_for_step(1)
    assert projected_ref["capture_window"] == s15.CAPTURE_WINDOW
    assert projected_ref["qib_summary_keys"] == s15.expected_qib_summary_keys()
    assert projected_ref["qib_transition_count"] == 0
    assert manifest["discovery"]["owner5_summary_counts"] == [0] * 6
    assert manifest["discovery"]["trace_melt_rows"] == 51

    summaries = _summary_lines()
    melt_lines = []
    for step, lat, substep, owner, i, k in projected_ref["melt_first_event_keys"]:
        row = dict(_melt_row(), step=str(step), lat=str(lat), substep=str(substep),
                   progb_site=str(owner), i=str(i), k=str(k))
        melt_lines.append(_native_melt_line(row))
    capture = tmp_path / "synthetic_b20_step1_stream.txt"
    capture.write_text("\n".join(summaries + melt_lines) + "\n")
    expected = {field: projected_ref[field] for field in s15.REFERENCE_FIELDS}
    plan, pin = _write_window_plan(
        tmp_path, capture, 1, expected, projected_ref["method"]
    )
    rows, parsed_summaries = s15.parse_capture(capture)
    assert s15.verify_plan(rows, plan, parsed_summaries, pin, capture) == {
        "qib_transitions": 0,
        "trace_melt_first_events": 51,
    }


def test_step2_window_is_explicit_and_restricts_the_allowed_steps(tmp_path: Path) -> None:
    assert s15.CAPTURE_WINDOW["first_timestep"] == 1
    assert s15.expected_qib_summary_keys()[0][0] == 1
    assert s15.capture_window_for_step(2)["first_timestep"] == 2
    assert s15.expected_qib_summary_keys(2) == [
        [2, 1, 5, 1, 235, 1, 142], [2, 1, 5, 1, 235, 143, 283],
        [2, 2, 5, 1, 235, 1, 142], [2, 2, 5, 1, 235, 143, 283],
        [2, 3, 5, 1, 235, 1, 142], [2, 3, 5, 1, 235, 143, 283],
    ]
    with pytest.raises(s15.ProbeError, match="choose 1 or 2"):
        s15.capture_window_for_step(3)
    with pytest.raises(s15.ProbeError, match="exactly pin supported timestep"):
        s15.capture_step_for_window({"first_timestep": 3, "last_timestep": 3})


def test_step2_plan_rejects_step1_event_rows(tmp_path: Path) -> None:
    words = ["00000000", "BF800000", "00000000", "00000000", "3F800000",
             "BF800000", "3F800000", "00000000", "3F800000", "3F800000",
             "3F800000"]
    q_line = "S15Q " + " ".join(map(str, [1, 2, s15.QIB_OWNER_SITE,
                                             1, 235, 1, 142, 1, 3, 8])) + " " + \
        " ".join(map(str, map(_signed, words)))
    summaries = [f"S15QC {' '.join(map(str, key))} 0"
                 for key in s15.expected_qib_summary_keys(2)]
    capture = tmp_path / "step1_row_in_step2_window.txt"
    capture.write_text("\n".join([q_line, *summaries]) + "\n")
    expected = {
        "qib_transition_count": 0,
        "qib_first_event_keys": [None] * 6,
        "melt_first_event_count": 0,
        "melt_first_event_keys": [],
        "first_qib_key": None,
        "first_melt_key": None,
    }
    plan, pin = _write_window_plan(tmp_path, capture, 2, expected, "pinned test fixture")
    rows, parsed_summaries = s15.parse_capture(capture)
    with pytest.raises(s15.ProbeError, match="outside the pinned timestep-2 window"):
        s15.verify_plan(rows, plan, parsed_summaries, pin, capture)


def test_prepare_generates_distinct_step1_default_and_explicit_step2_guards() -> None:
    use = (
        "  USE module_state_description, only: param_first_scalar, p_qr, p_qv, p_qc, "
        "p_qg, p_qi, p_qs, tiedtkescheme,ntiedtkescheme, heldsuarez, &\n"
    )
    signature = "                             rk_step, dt, spec_zone,        &\n"
    declaration = "   INTEGER ,                INTENT(IN   ) :: scs, sce, rk_step, spec_zone\n"
    anchor = "    IF ( rk_step == 1 ) THEN\n"
    formula = (
        "        scalar_2(i,k,j,im) = ((c1(k)*muold(i)+c2(k))*scalar_1(i,k,j,im)   &\n"
        "                             + dt*tendency(i,k,j))/(c1(k)*munew(i)+c2(k))\n"
    )
    source = use + signature * 2 + declaration * 2 + anchor + formula * 2 + \
        "END SUBROUTINE rk_update_scalar\n"
    step1 = s15.instrument_module_em(source)
    step2 = s15.instrument_module_em(source, capture_step=2)
    assert "s15_step.eq.1" in step1 and "s15_step.eq.2" not in step1
    assert "s15_step.eq.2" in step2 and "s15_step.eq.1" not in step2
    assert s15._s15_strip(step1) == source
    assert s15._s15_strip(step2) == source


def test_melt_overlay_step_is_explicit_and_step1_remains_default() -> None:
    gate = (
        "     kdm6_progb_capture_env = ''\n"
        "     call get_environment_variable('KDM6_PROGB_VALIDITY_CAPTURE_LOG', &\n"
        "          kdm6_progb_capture_env)\n"
        "     capture_enabled = (trim(kdm6_progb_capture_env) == '1')\n"
    )
    calls = "".join(
        f"   call ProgB_param({site}, &\n"
        f"! S10_CAPTURE_BEGIN:progb_call_{site}\n#ifdef {s15.S10_MACRO}\n"
        "                   c)\n#else\n                   c)\n#endif\n"
        f"! S10_CAPTURE_END:progb_call_{site}\n"
        for site in range(1, 8)
    )
    declaration = (
        "   integer                            :: i, j, k, mstepmax,mstepmax_i,         &\n"
        "                                         iprt, latd, lond, loop, loops, ifsat, &\n"
        "                                         n, idim, kdim\n"
    )
    melt_anchor = (
        "            if(qrs(i,k,3).gt.0.) then\n"
        "! revised \n"
        "              coeres = (rslope2(i,k,3))*sqrt(rslope(i,k,3)*rslopeb(i,k,3))           &\n"
    )
    brs_update = "              brs(i,k) = brs(i,k) + (pgmlt(i,k)/rhox(i,k))\n"
    source = gate + calls + declaration + "   do loop = 1,loops\n" + melt_anchor + brs_update
    step1 = s15.instrument_module_mp(source)
    step2 = s15.instrument_module_mp(source, capture_step=2)
    assert "capture_step.eq.1" in step1 and "capture_step.eq.2" not in step1
    assert "capture_step.eq.2" in step2 and "capture_step.eq.1" not in step2
    assert s15._s15_strip(step1) == source
    assert s15._s15_strip(step2) == source


def test_native_stream_rejects_unknown_s15_event_tag(tmp_path: Path) -> None:
    capture = tmp_path / "unknown_s15_record.txt"
    capture.write_text("ordinary WRF output\nS15QX 2 1 5\n")
    with pytest.raises(s15.ProbeError, match="unknown S15 event record 'S15QX'"):
        s15.parse_capture(capture)
    with pytest.raises(s15.ProbeError, match="unknown S15 event record 'S15QX'"):
        s15.extract_s15_event_stream(capture, tmp_path / "unknown_s15_selected.txt")


def test_step2_filter_excludes_step1_s10_rows_and_preserves_s15_schedule(
    tmp_path: Path,
) -> None:
    summaries = [f"S15QC {' '.join(map(str, key))} 0"
                 for key in s15.expected_qib_summary_keys(2)]
    full_stdout = tmp_path / "full-rank0.stdout"
    full_stdout.write_text("WRF startup\nS10SLP 1 73 113 5\n" +
                           "S10DIAG 1 73 113 5 0 1 0\n" +
                           "\n".join(summaries) + "\n")
    full_rows, full_summaries = s15.parse_capture(full_stdout)
    assert full_rows == []
    assert full_summaries == [tuple(key + [0])
                              for key in s15.expected_qib_summary_keys(2)]
    selected = tmp_path / "selected-s15.events"
    receipt = s15.extract_s15_event_stream(full_stdout, selected)
    assert receipt["selected_record_count"] == 6
    assert receipt["s10_records_excluded_from_replay"] is True
    assert receipt["full_stdout"]["sha256"] == s15.sha256(full_stdout)
    assert receipt["selected_s15_stream"]["sha256"] == s15.sha256(selected)
    assert b"S10" not in selected.read_bytes()
    rows, parsed = s15.parse_capture(selected)
    expected = {
        "qib_transition_count": 0,
        "qib_first_event_keys": [None] * 6,
        "melt_first_event_count": 0,
        "melt_first_event_keys": [],
        "first_qib_key": None,
        "first_melt_key": None,
    }
    plan, pin = _write_window_plan(tmp_path, selected, 2, expected, "pinned step2 fixture")
    assert s15.verify_plan(rows, plan, parsed, pin, selected) == {
        "qib_transitions": 0,
        "trace_melt_first_events": 0,
    }


def test_s15_event_extraction_refuses_full_stdout_hardlink_without_mutation(
    tmp_path: Path,
) -> None:
    full_stdout = tmp_path / "full.stdout"
    full_stdout.write_bytes(b"S10SLP 1 73 113 5\nS15QC 2 1 5 1 235 1 142 0\n")
    original = full_stdout.read_bytes()
    selected_hardlink = tmp_path / "selected.events"
    os.link(full_stdout, selected_hardlink)
    with pytest.raises(s15.ProbeError, match="aliases full stdout"):
        s15.extract_s15_event_stream(full_stdout, selected_hardlink)
    assert full_stdout.read_bytes() == original
    assert selected_hardlink.read_bytes() == original

    existing_output = tmp_path / "existing.events"
    existing_output.write_bytes(b"preserve this existing output\n")
    with pytest.raises(s15.ProbeError, match="output must not already exist"):
        s15.extract_s15_event_stream(full_stdout, existing_output)
    assert full_stdout.read_bytes() == original
