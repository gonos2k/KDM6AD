#!/usr/bin/env python3
"""Bounded DOM1 nine-channel analysis and matched seven-channel comparison.

Same native background, held20s forcing, T/Q prior and max_iter3. Quality must
stay zero on the complete selected support. Existing operational Edd3 stays.
"""
from __future__ import annotations
import importlib.util
import json
import multiprocessing as mp
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
PACKET = Path(__file__).resolve().parent
PRIVATE = Path("/Users/yhlee/KDM6AD-k/host/research_evidence/pr420_nine_channel_20261013")
OUTPUT = PRIVATE / "DOM_ANALYSIS_PAIR_ONCE_01"
sys.path.insert(0, str(ROOT / "oracle"))
sys.path.insert(0, str(PACKET))
from trace_saved07 import RetainingPool, sha, write


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def check(pins):
    for path, digest in pins.items():
        if sha(path) != digest:
            raise ValueError("bound experiment source/input/asset changed: " + path)


def main():
    base_plan = json.loads((ROOT / "harness/evidence/pr417_hourly_rttov_2026-10-12/PLAN.json").read_text())
    if (not __debug__ or os.environ.get("PYTHONOPTIMIZE") != "0"
            or sys.executable != base_plan["python_executable"]
            or any(os.environ.get(k) != v for k, v in base_plan["thread_environment"].items())):
        raise ValueError("original interpreter/assertions/single-thread environment required")
    prep_path = PACKET / "PAIRED_DOM1_PREPARATION.json"
    prep = json.loads(prep_path.read_text())
    if OUTPUT.exists():
        raise FileExistsError("fresh single-run pair only; no retry/warm start")
    paths = [Path(__file__), PACKET / "trace_saved07.py", prep_path, PACKET / "CASE.json",
             Path(prep["intake_manifest_path"]), Path(prep["intake_npz_path"])]
    driver_path = ROOT / "harness/evidence/pr418_nine_channels_2026-10-12/run_case_analysis_nine.py"
    driver = module(driver_path, "pr420_current_nine_driver")
    intake = module(driver.INTAKE_SOURCE, "pr420_current_case_intake")
    legacy = driver.load_module(driver.LEGACY_DRIVER, "pr420_fixed_analysis_primitives")
    manifest, arrays = intake.load_bound_intake(prep["intake_manifest_path"], prep["intake_npz_path"])
    paths.extend(driver._analysis_source_paths(legacy))
    paths += [ROOT / p for p in (
        "oracle/kdm6/da_single_column.py", "oracle/kdm6/da_fulldomain.py", "oracle/kdm6/da_dual.py",
        "oracle/kdm6/da_window.py", "oracle/kdm6/da_cvt.py", "oracle/kdm6/runtime.py",
        "oracle/kdm6/coordinator.py", "oracle/kdm6/obs/allsky_shard.py",
        "oracle/kdm6/obs/model_profile_builder.py", "oracle/kdm6/obs/rttov_case_writer.py",
        "oracle/kdm6/obs/rttov_obs_operator.py", "oracle/kdm6/obs/rttov_runner.py",
        "oracle/kdm6/obs/ami_bt_coordinate.py")]
    pins = {str(p.resolve()): sha(p) for p in paths}
    source_skin = legacy.TEMPLATE_FIXTURE / "in/profiles/001/sfc/01/skin.txt"
    pins[str(source_skin.resolve())] = "32e8b5de4a58937324399b2f16162da6200fdfe0b0493f018dc94b565ca4351b"
    old_assets = json.loads((ROOT / "harness/evidence/pr412_native_process_case_2026-10-12/PREDECLARED.json").read_text())["external_assets_before"]
    for p, record in old_assets.items():
        if not Path(p).is_relative_to(Path("/private/tmp/KDM6AD-viirs-native-run-20261007")):
            pins[p] = record["sha256"]
    contexts = {}
    for name, channels in (("DOM9", tuple(range(8, 17))), ("DOM7", tuple(range(10, 17)))):
        runprep = prep["runs"][name]
        fixture = Path(runprep["fixture"]["prepared_fixture_copy"])
        for relative, digest in runprep["prepared_file_hashes_after_dom1_edit"].items():
            path = fixture / relative
            if sha(path) != digest:
                raise ValueError("prepared DOM fixture changed: " + str(path))
            pins[str(path)] = digest
        text = (fixture / "out/rttov_test.txt").read_text()
        assert re.findall(r"(?im)^\s*defn%opts%scatt%thermal_solver\s*=\s*(\d+)", text) == ["1"]
        assert re.findall(r"(?im)^\s*defn%opts%rt_all%solar\s*=\s*([^!\n]+)", text)[0].strip() == ".FALSE."
        ctx = driver.build_inputs(manifest, arrays, fixture, legacy.TEMPLATE_FIXTURE, legacy, channels=channels)
        ctx["run_manifest"]["H_scientific_variant"] = {
            "thermal_solver": 1, "name": "RTTOV built-in DOM thermal",
            "baseline_operational_thermal_solver": 3,
            "scope": "separate explicitly opt-in research H; M/C/prior/forcing/budget unchanged",
            "compare_channel_sets_within_same_variant": True,
            "historical_Edd7_is_separate_operator_comparison": True,
            "coefficient_or_input_humidity_tuning": False}
        contexts[name] = ctx
    check(pins)
    plan = {"schema": "pr420_dom1_same_case_pair_v1", "display_timezone": "KST",
            "case_id": manifest["case_id"], "run_order": ["DOM9", "DOM7"],
            "thermal_solver": 1, "operator_change_explicit": "Edd3 to built-in DOM1 for research pair only",
            "C_M_prior_forcing_sigma_bias_max_iter_unchanged": True,
            "max_iter": 3, "max_eval_policy": "unchanged PyTorch default; observed strong-Wolfe counts reported",
            "source_DQF_zero_required": True, "model_quality_zero_all_selected_required": True,
            "channel_removal_or_warning_waiver": False, "bindings": pins,
            "output_root": str(OUTPUT), "native_levels": 39,
            "native_interface_identity_independently_verified": False,
            "actual_pixel_UTC_verified": False, "native_runs_or_new_data_acquisition": 0,
            "retained_raw_case_outputs": True,
            "asset_check_scope": "before/after each complete bounded analysis; not per internal RTTOV subprocess",
            "runs": {n: {"channels": list(c["rttov_cfg"]["channels"]), "run_manifest": c["run_manifest"]} for n, c in contexts.items()}}
    write(PACKET / "ANALYSIS_PLAN.json", plan)
    OUTPUT.mkdir(mode=0o700)
    write(OUTPUT / "STARTED_ONCE.json", {"plan_sha256": sha(PACKET / "ANALYSIS_PLAN.json")})
    import torch
    torch.set_num_threads(1)
    if str(torch.__version__) != "2.13.0":
        raise ValueError("original Torch version required")
    results = {}
    try:
        with mp.get_context("spawn").Pool(1) as pool:
            for name in plan["run_order"]:
                check(pins)
                ctx = contexts[name]
                capture = driver.prepare_capture_module()
                run = OUTPUT / name
                kwargs = {"channels": tuple(range(8, 17))} if name == "DOM9" else {}
                result = capture.run_capture(
                    xb=ctx["xb"], forcings=(ctx["forcing"],), y_bt=ctx["y_bt"], y_rq=ctx["y_rq"],
                    xland=ctx["xland"], clear_cfg=ctx["clear_cfg"], rttov_cfg=ctx["rttov_cfg"],
                    window_config=ctx["window_config"], obs_time=1,
                    pool=RetainingPool(pool), max_iter=3, n_workers=1,
                    private_checkpoint=run / "private/accepted_state.npz",
                    public_receipt=run / "CAPTURE.json", case_root=run / "h_cases",
                    native_intake_context_path=Path(prep["intake_manifest_path"]),
                    native_intake_context_sha256=prep["intake_manifest_sha256"],
                    native_intake_npz_path=Path(prep["intake_npz_path"]),
                    native_intake_npz_sha256=prep["intake_npz_sha256"],
                    run_manifest=ctx["run_manifest"], **kwargs)
                audit = driver._audit_initial_objectives_selected(result, ctx["y_bt"], expected_channels=len(ctx["rttov_cfg"]["channels"]))
                results[name] = {"capture": result, "objective_audit": audit}
                if result.get("status") != "RETURNED_DIAGNOSTIC_ONLY" or audit["status"] != "CROSSCHECKED":
                    raise ValueError(name + " fixed-support capture or objective audit failed")
                for case in (run / "h_cases").glob("**/case"):
                    assert [int(v) for v in (case / "in/channels.txt").read_text().split()] == list(ctx["rttov_cfg"]["channels"])
                    assert re.findall(r"(?im)^\s*defn%opts%scatt%thermal_solver\s*=\s*(\d+)", (case / "out/rttov_test.txt").read_text()) == ["1"]
                write(PACKET / (name + "_CAPTURE.json"), result)
                write(PACKET / (name + "_AUDIT.json"), audit)
                print(json.dumps({"run": name, "status": result["status"], "J": result["objective"]["Jtotal"],
                                  "n_valid": result["objective"]["n_valid"], "gradient": result["final_control_gradient"]}), flush=True)
        check(pins)
        write(PACKET / "ANALYSIS_RESULT.json", {"status": "RETURNED_TWO_ACTUAL_DOM_ANALYSES",
              "runs": {n: {"status": r["capture"]["status"], "objective_audit": r["objective_audit"]["status"],
                        "n_valid": r["capture"]["objective"]["n_valid"],
                        "logical_H_calls": len(r["capture"]["logical_h_calls"])} for n, r in results.items()},
              "plan_sha256": sha(PACKET / "ANALYSIS_PLAN.json"), "same_problem_except_selected_channels": True,
              "native_model_runs": 0, "actual_pixel_UTC_verified": False})
    except Exception as exc:
        write(OUTPUT / "FAILED.json", {"error": repr(exc), "completed_runs": list(results), "automatic_retry": False})
        raise


if __name__ == "__main__":
    main()
