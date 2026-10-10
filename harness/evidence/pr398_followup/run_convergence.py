#!/usr/bin/env python3
"""Prepare or run the one-shot PR398 eight-iteration convergence check.

Default invocation only validates the bound PR395 native intake, reuses its
input builder, copies the declared RTTOV template, and writes a preflight.
The single analysis call requires the explicit ``--execute-after-review``
flag. It uses the original native ``xb``, zero-initialized controls, same
forcing/observation/prior/sigma/bias, and the existing all-sky capture helper.
No native model or separate H/M probe is run by this driver.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import multiprocessing as mp
import os
from pathlib import Path
import sys

import numpy as np
import torch

from comparison_audit import build_comparison_audit

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "oracle"))

EXPERIMENT_ID = "PR398_CONVERGENCE_8ITER_20261010"
MAX_ITER = 8
EXPECTED_MAX_EVAL = 10  # PyTorch 2.13 default int(1.25*8); observed, not passed to LBFGS.
EXPECTED_TORCH_VERSION = "2.13.0"
PR397_RESULT = ROOT / "harness/evidence/pr395_tq_state_capture_2026-10-10/RESULT_3d2e97f159.json"
PR397_RESULT_SHA256 = "c49808c0331754eeb9ab9f77a88083119d5834852281db890b2827f6acf6eeca"
PR397_DRIVER = ROOT / "harness/evidence/pr395_tq_state_capture_2026-10-10/DRIVER_3d2e97f159.json"
PR397_DRIVER_SHA256 = "836ac71bdf069c1a677e8d3e770cab3e31cfaf807d8a13ccab9884b01bb49333"
RUN_ANALYSIS = ROOT / "harness/evidence/pr395_native_tq_intake_2026-10-10/run_analysis.py"
CAPTURE_HELPER = ROOT / "harness/evidence/pr395_tq_state_capture_2026-10-10/capture_tq_state.py"
PREDECLARATION = ROOT / "harness/evidence/pr398_followup/PREDECLARATION.json"
EVIDENCE_DIR = ROOT / "harness/evidence/pr398_followup"
ANALYSIS_ROOT = ROOT / "graphify-out/pr398-convergence-8iter-20261010"
RUN_ROOT = ANALYSIS_ROOT / f"run-{EXPERIMENT_ID}-sourcechecked7"
PREFLIGHT = RUN_ROOT / "preflight.json"
ONCE_LOCK = ANALYSIS_ROOT / "RUN_STARTED_ONCE.json"
PRIVATE_CHECKPOINT = ANALYSIS_ROOT / "private/accepted-final-pr398-convergence.npz"
RESULT_RECEIPT = EVIDENCE_DIR / "RESULT_PR398_CONVERGENCE_8ITER_20261010.json"
DRIVER_RECEIPT = EVIDENCE_DIR / "DRIVER_PR398_CONVERGENCE_8ITER_20261010.json"
CAPTURE_INTERNAL_RECEIPT = RUN_ROOT / "capture_internal/RESULT.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _source_hashes() -> dict[str, str]:
    source_files = {
        "input_builder": RUN_ANALYSIS,
        "capture_helper": CAPTURE_HELPER,
        "comparison_audit": ROOT / "harness/evidence/pr398_followup/comparison_audit.py",
        "single_column_adapter": ROOT / "oracle/kdm6/da_single_column.py",
        "dual_minimizer": ROOT / "oracle/kdm6/da_dual.py",
        "window_adjoint": ROOT / "oracle/kdm6/da_window.py",
    }
    return {name: _sha256(path) for name, path in source_files.items()}


def _fixture_hashes(analysis, fixture_info: dict) -> dict:
    fixture = RUN_ROOT / "rttov_fixture"
    relative_files = (
        "in/profiles/001/atm/p.txt", "in/profiles/001/atm/p_half.txt",
        "in/profiles/001/atm/o3.txt", "in/profiles/001/atm/co2.txt",
        "in/profiles/001/atm/simple_cloud.txt", "out/rttov_test.txt",
        "out/run.sh", "out/env.sh",
    )
    static = {rel: _sha256(fixture / rel) for rel in relative_files}
    executable = Path(fixture_info["rttov_executable"]["path"])
    coefficient = Path(analysis._resolve_coef_path(fixture))
    assets = {"executable": {"path": str(executable), "sha256": _sha256(executable)},
              "coefficient": {"path": str(coefficient), "sha256": _sha256(coefficient)}}
    return {"fixture_files": static, "execution_assets": assets}


def _input_fingerprints(capture, ctx: dict) -> dict:
    return {
        "xb_state_sha256": capture.state_sha256(ctx["xb"]),
        "forcing_sha256": capture.forcing_sha256(ctx["forcing"]),
        "y_bt_sha256": capture.array_sha256(ctx["y_bt"]),
        "y_rq_sha256": capture.array_sha256(ctx["y_rq"]),
        "xland_sha256": capture.array_sha256(ctx["xland"]),
        "window_config": capture._jsonable(ctx["window_config"]),
        "h_configuration": capture._public_h_config_summary(ctx["rttov_cfg"]),
    }


def _verify_pr397_baseline(analysis, capture, intake_binding: dict, ctx: dict,
                           fixture_info: dict) -> dict:
    if _sha256(PR397_RESULT) != PR397_RESULT_SHA256:
        raise ValueError("hash-pinned PR397 baseline receipt changed")
    baseline = json.loads(PR397_RESULT.read_text())
    if (baseline.get("status") != "RETURNED_DIAGNOSTIC_ONLY"
            or baseline.get("input_validity", {}).get("status") != "VALIDATED_NATIVE_INPUT"
            or baseline.get("numerical_return", {}).get("status") != "RETURNED"
            or baseline.get("physical_matchup_and_science_acceptance", {}).get("science_accepted") is not False):
        raise ValueError("PR397 baseline is not the expected diagnostic-only accepted-state record")
    checkpoint_path = Path(baseline["private_checkpoint"]["path"])
    if _sha256(checkpoint_path) != baseline["private_checkpoint"]["sha256"]:
        raise ValueError("PR397 baseline private NPZ does not match its recorded digest")
    if _sha256(PR397_DRIVER) != PR397_DRIVER_SHA256:
        raise ValueError("hash-pinned PR397 baseline driver receipt changed")
    baseline_driver = json.loads(PR397_DRIVER.read_text())
    if baseline_driver.get("capture_receipt_sha256") != PR397_RESULT_SHA256:
        raise ValueError("PR397 driver receipt does not bind the pinned capture RESULT")
    if (baseline_driver.get("rttov_fixture_immutable_during_analysis") is not True
            or baseline_driver.get("rttov_execution_assets_stable_during_analysis") is not True
            or baseline_driver.get("fixture_hashes_before")
            != baseline_driver.get("fixture_hashes_after")
            or baseline_driver.get("rttov_execution_assets_before")
            != baseline_driver.get("rttov_execution_assets_after")):
        raise ValueError("PR397 baseline driver did not prove stable fixture/execution assets")
    old_intake = baseline["native_intake_context"]
    if (old_intake["sha256"] != intake_binding["manifest_sha256"]
            or old_intake["npz_sha256"] != intake_binding["npz_sha256"]):
        raise ValueError("PR398 input differs from the PR397 baseline intake")
    state_hash = capture.state_sha256(ctx["xb"])
    forcing_hash = capture.forcing_sha256(ctx["forcing"])
    if (state_hash != baseline["state_array_sha256"]["background_initial"]
            or state_hash != old_intake["initial_state_sha256"]
            or forcing_hash != baseline["forcing_array_sha256"]["forcing_window"][0]
            or forcing_hash != old_intake["forcing_window_0_sha256"]):
        raise ValueError("PR398 xb/forcing differs from the hash-bound PR397 initial state")
    if (capture.array_sha256(ctx["y_bt"]) != capture.array_sha256(
            np.asarray(baseline["observations"]["y_bt_K"], dtype=np.float64))
            or capture.array_sha256(ctx["y_rq"]) != capture.array_sha256(
                np.asarray(baseline["observations"]["observation_dqf"], dtype=np.float64))):
        raise ValueError("PR398 BT/DQF observation differs from the PR397 baseline")
    current_h = capture._public_h_config_summary(ctx["rttov_cfg"])
    prior_h = dict(baseline["effective_h_configuration"])
    current_h.pop("fixture_case_dir", None)
    prior_h.pop("fixture_case_dir", None)
    if current_h != prior_h:
        raise ValueError("PR398 effective H configuration differs from PR397 after path normalization")
    current_fixture = _fixture_hashes(analysis, fixture_info)
    if current_fixture["fixture_files"] != baseline_driver["fixture_hashes_before"]:
        raise ValueError("PR398 copied RTTOV fixture files differ from PR397 execution files")
    prior_assets = baseline_driver["rttov_execution_assets_before"]
    if (current_fixture["execution_assets"]["executable"]["sha256"]
            != prior_assets["executable"]["sha256"]
            or current_fixture["execution_assets"]["coefficient"]["sha256"]
            != prior_assets["coefficient"]["sha256"]):
        raise ValueError("PR398 RTTOV executable/coefficient differs from PR397 actual-run assets")
    adapter = baseline["adapter_metadata"]
    fixed_adapter = {
        "obs_time": 1, "n_forcings": 1, "huber_delta_K": 1.0,
        "observation_sigma_K": 1.0, "observation_bias_K": 0.0,
        "state_prior": {
            "th_sigma_K": 0.8, "qv_sigma_log": 0.08,
            "qv_levels_from_bottom": 12,
            "active_fields_at_initial_state": ["th", "qv"],
            "active_counts_from_built_sigma": {
                "th": 39, "qv": 12, "qc": 0, "qr": 0, "qi": 0,
                "qs": 0, "qg": 0, "nccn": 0, "nc": 0, "ni": 0,
                "nr": 0, "bg": 0,
            },
            "non_tq_fields_fixed_zero": ["qc", "qr", "qi", "qs", "qg", "nccn", "nc", "ni", "nr", "bg"],
        },
        "parameter_prior": {"active": [], "theta_b": [0.4, 3030.0, 2590000000000000.0, 1.0],
                            "sigma_log": [0.0, 0.0, 0.0, 0.0]},
        "initial_state_control": "zero initialized by existing dual minimizer",
        "window_config_projection": ["th", "qv"],
        "partition_control": False, "pseudo_rh": False,
    }
    if any(adapter.get(key) != value for key, value in fixed_adapter.items()):
        raise ValueError("PR397 baseline prior/observation/control contract differs from PR398 declaration")
    initial = baseline["objective"]["initial_zero_control_closure"]
    return {
        "receipt_path": str(PR397_RESULT),
        "receipt_sha256": PR397_RESULT_SHA256,
        "driver_path": str(PR397_DRIVER),
        "driver_sha256": PR397_DRIVER_SHA256,
        "capture_npz_sha256": baseline["private_checkpoint"]["sha256"],
        "same_intake": True,
        "same_xb_sha256": state_hash,
        "same_forcing_sha256": forcing_hash,
        "same_observations": True,
        "same_effective_h_config_ignoring_fixture_path": True,
        "same_fixture_files_as_pr397_driver": True,
        "same_executable_and_coefficient_as_pr397_driver": True,
        "same_observation_prior_control_contract": True,
        "initial_Jo": initial["Jo"],
        "initial_operator_signature_sha256": initial["operator_signature_sha256"],
        "initial_frozen_mask": initial["frozen_mask"],
    }


def _write_private_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    with path.open("x") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True) + "\n")
    path.chmod(0o600)


def _configure_context(analysis, arrays, intake_binding, observation_receipt, fixture_copy):
    ctx = analysis.build_run_inputs(
        arrays, intake_binding["manifest"], observation_receipt, fixture_copy)
    # Keep the historical manifest enum as the experiment ID; the pinned
    # PyTorch 2.13 implementation computes max_eval=int(max_iter*1.25).
    ctx["run_manifest"].update({
        "max_iter": MAX_ITER,
        "experiment_id": EXPERIMENT_ID,
        "optimizer_max_eval_policy": "pytorch_lbfgs_default_ceil_1.25_max_iter",
        "purpose": "bounded_convergence_test; not cloud seeking or science acceptance",
    })
    ctx["rttov_cfg"]["rttov_timeout"] = analysis.DEFAULT_RTTOV_TIMEOUT
    ctx["run_manifest"]["native_intake_manifest_sha256"] = intake_binding["manifest_sha256"]
    ctx["run_manifest"]["native_intake_npz_sha256"] = intake_binding["npz_sha256"]
    if (tuple(ctx["window_config"].active_fields) != ("th", "qv")
            or ctx["window_config"].params is not None
            or ctx["window_config"].eta is not None
            or ctx["window_config"].eta_pre is not None):
        raise ValueError("builder output changed the fixed PR395 state-control contract")
    if ctx["run_manifest"].get("parameter_prior_active") != []:
        raise ValueError("parameter prior controls must remain inactive")
    return ctx


def prepare_preflight() -> dict:
    if PREFLIGHT.exists() or RUN_ROOT.exists() or ONCE_LOCK.exists():
        raise FileExistsError("PR398 run root/lock already exists; do not overwrite or retry")
    analysis = _load(RUN_ANALYSIS, "pr395_native_tq_analysis_builder")
    if str(torch.__version__) != EXPECTED_TORCH_VERSION:
        raise RuntimeError(f"PR398 max_eval predeclaration requires PyTorch {EXPECTED_TORCH_VERSION}; found {torch.__version__}")
    declaration = json.loads(PREDECLARATION.read_text())
    if (declaration.get("experiment_id") != EXPERIMENT_ID
            or declaration.get("max_iter") != MAX_ITER
            or declaration.get("max_eval_policy")
            != "pytorch_lbfgs_default_ceil_1.25_max_iter"
            or declaration.get("torch_version_expected") != EXPECTED_TORCH_VERSION
            or declaration.get("baseline", {}).get("result_sha256") != PR397_RESULT_SHA256
            or declaration.get("baseline", {}).get("driver_sha256") != PR397_DRIVER_SHA256
            or declaration.get("baseline", {}).get("initial_zero_control_Jo") != 26.588575903055926
            or declaration.get("baseline", {}).get("initial_operator_signature_sha256")
            != "2564e3298a383f3b9bdb348cc5abbd68156653b633f4963551fdc799132d1e59"
            or declaration.get("science_acceptance") != "NOT_ASSESSED"):
        raise ValueError("PR398 declaration differs from the executable fixed protocol")
    intake_binding, arrays = analysis.require_valid_intake(
        analysis.INTAKE_MANIFEST, analysis.INTAKE_NPZ)
    observation_receipt = json.loads(analysis.OBS_RECEIPT.read_text())
    RUN_ROOT.mkdir(parents=True, mode=0o700)
    RUN_ROOT.chmod(0o700)
    fixture_copy = RUN_ROOT / "rttov_fixture"
    fixture_info = analysis._prepare_fixture_copy(
        analysis.TEMPLATE_FIXTURE.resolve(), fixture_copy, arrays)
    ctx = _configure_context(
        analysis, arrays, intake_binding, observation_receipt, fixture_copy)
    capture = _load(CAPTURE_HELPER, "pr398_capture_adapter")
    baseline_binding = _verify_pr397_baseline(
        analysis, capture, intake_binding, ctx, fixture_info)
    record = {
        "schema": "pr398_convergence_preflight_v1",
        "experiment_id": EXPERIMENT_ID,
        "status": "PREPARED_NO_ANALYSIS_EXECUTED",
        "run_root": str(RUN_ROOT),
        "input_validity": "VALIDATED_NATIVE_INPUT",
        "intake_manifest_sha256": intake_binding["manifest_sha256"],
        "intake_npz_sha256": intake_binding["npz_sha256"],
        "observation_receipt_sha256": analysis.sha256(analysis.OBS_RECEIPT),
        "predeclaration_sha256": _sha256(PREDECLARATION),
        "template_fixture": fixture_info,
        "template_hashes": _fixture_hashes(analysis, fixture_info),
        "observation_receipt_identity_sha256": analysis.sha256(analysis.OBS_RECEIPT),
        "input_fingerprints": _input_fingerprints(capture, ctx),
        "source_sha256": _source_hashes(),
        "production_source_snapshot": capture._source_snapshot(),
        "pr397_baseline_binding": baseline_binding,
        "fixed_contract": ctx["run_manifest"],
        "state_shape": list(ctx["xb"].th.shape),
        "forcing_shape": list(ctx["forcing"].p.shape),
        "active_fields": list(ctx["window_config"].active_fields),
        "parameter_prior_active": [],
        "controls_start_at_zero": True,
        "max_iter": MAX_ITER,
        "max_eval_policy": {
            "value_expected": EXPECTED_MAX_EVAL,
            "torch_version": EXPECTED_TORCH_VERSION,
            "policy": "PyTorch LBFGS default, observed after run; driver does not pass max_eval",
        },
        "native_rerun": False,
        "warm_start": False,
        "additional_H_or_M_before_execution": 0,
        "automatic_retry": False,
        "science_acceptance": "NOT_ASSESSED",
        "purpose": "test iteration/gradient trajectory only; not cloud seeking",
    }
    _write_private_json(PREFLIGHT, record)
    return record


def _execute_once(preflight: dict) -> int:
    if (RESULT_RECEIPT.exists() or DRIVER_RECEIPT.exists()
            or PRIVATE_CHECKPOINT.exists() or CAPTURE_INTERNAL_RECEIPT.exists()):
        raise FileExistsError("PR398 result destination already exists; one-shot execution is locked")
    if str(torch.__version__) != EXPECTED_TORCH_VERSION:
        raise RuntimeError("PyTorch version changed after preflight; refusing the one-shot analysis")
    if (preflight.get("status") != "PREPARED_NO_ANALYSIS_EXECUTED"
            or preflight.get("experiment_id") != EXPERIMENT_ID
            or not PREFLIGHT.is_file()):
        raise ValueError("execution requires a previously written, reviewed PR398 preflight")
    if _sha256(PREDECLARATION) != preflight.get("predeclaration_sha256"):
        raise ValueError("predeclaration changed after review")
    os.environ.update(OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
                      OMP_THREAD_LIMIT="1", VECLIB_MAXIMUM_THREADS="1")
    torch.set_num_threads(1)
    analysis = _load(RUN_ANALYSIS, "pr395_native_tq_analysis_builder")
    intake_binding, arrays = analysis.require_valid_intake(
        analysis.INTAKE_MANIFEST, analysis.INTAKE_NPZ)
    observation_receipt = json.loads(analysis.OBS_RECEIPT.read_text())
    fixture_copy = RUN_ROOT / "rttov_fixture"
    ctx = _configure_context(
        analysis, arrays, intake_binding, observation_receipt, fixture_copy)
    actual_bindings = (intake_binding["manifest_sha256"], intake_binding["npz_sha256"])
    if actual_bindings != (preflight["intake_manifest_sha256"], preflight["intake_npz_sha256"]):
        raise ValueError("native intake changed after the preflight was prepared")
    if _source_hashes() != preflight["source_sha256"]:
        raise ValueError("builder/capture/solver source changed after preflight review")
    if ctx["run_manifest"] != preflight["fixed_contract"]:
        raise ValueError("rebuilt experiment manifest differs from the reviewed preflight")
    capture = _load(CAPTURE_HELPER, "pr398_capture_adapter")
    if analysis.sha256(analysis.OBS_RECEIPT) != preflight["observation_receipt_identity_sha256"]:
        raise ValueError("observation receipt changed after preflight review")
    if _fixture_hashes(analysis, preflight["template_fixture"]) != preflight["template_hashes"]:
        raise ValueError("copied RTTOV template or execution assets changed after preflight review")
    if _input_fingerprints(capture, ctx) != preflight["input_fingerprints"]:
        raise ValueError("xb/forcing/observation/config builder output changed after preflight review")
    if capture._source_snapshot() != preflight["production_source_snapshot"]:
        raise ValueError("production DA/RTTOV/thermodynamics source changed after preflight review")
    baseline_binding = _verify_pr397_baseline(
        analysis, capture, intake_binding, ctx, preflight["template_fixture"])
    if baseline_binding != preflight["pr397_baseline_binding"]:
        raise ValueError("hash-bound PR397 baseline differs from the reviewed preflight")
    try:
        fd = os.open(ONCE_LOCK, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise RuntimeError("PR398 analysis was already claimed; do not retry") from exc
    with os.fdopen(fd, "w") as stream:
        stream.write(json.dumps({"status": "RUN_STARTED_ONCE", "experiment_id": EXPERIMENT_ID,
                                 "preflight_sha256": _sha256(PREFLIGHT)}, sort_keys=True) + "\n")
    before = capture._source_snapshot()
    pool = None
    try:
        pool = mp.get_context("spawn").Pool(1)
        result = capture.run_capture(
            xb=ctx["xb"], forcings=(ctx["forcing"],),
            y_bt=ctx["y_bt"], y_rq=ctx["y_rq"], xland=ctx["xland"],
            clear_cfg=ctx["clear_cfg"], rttov_cfg=ctx["rttov_cfg"],
            window_config=ctx["window_config"], obs_time=1, pool=pool,
            private_checkpoint=PRIVATE_CHECKPOINT,
            public_receipt=CAPTURE_INTERNAL_RECEIPT,
            case_root=RUN_ROOT / "h_cases",
            native_intake_context_path=analysis.INTAKE_MANIFEST,
            native_intake_context_sha256=intake_binding["manifest_sha256"],
            native_intake_npz_path=analysis.INTAKE_NPZ,
            native_intake_npz_sha256=intake_binding["npz_sha256"],
            run_manifest=ctx["run_manifest"], max_iter=MAX_ITER, n_workers=1,
            rttov_timeout=analysis.DEFAULT_RTTOV_TIMEOUT)
    finally:
        if pool is not None:
            pool.close()
            pool.join()
    after = capture._source_snapshot()
    optimization = result.get("optimization", {})
    objective_audit = (
        analysis._audit_initial_objectives(result, ctx["y_bt"])
        if result.get("status") == "RETURNED_DIAGNOSTIC_ONLY"
        else {"status": "NOT_AUDITED_NONRETURN", "crosschecks": {}}
    )
    max_eval_observed = optimization.get("max_eval")
    baseline = preflight["pr397_baseline_binding"]
    if not CAPTURE_INTERNAL_RECEIPT.is_file():
        raise RuntimeError("capture adapter returned without its private staging receipt")
    capture_receipt = json.loads(CAPTURE_INTERNAL_RECEIPT.read_text())
    public_result = {
        **capture_receipt,
        "schema": "pr398_convergence_capture_v1",
        "experiment_id": EXPERIMENT_ID,
        "purpose": "bounded convergence test; not cloud seeking or science acceptance",
        "max_iter": MAX_ITER,
        "max_eval_policy": "pytorch_lbfgs_default_ceil_1.25_max_iter",
        "max_eval_expected_from_pinned_torch": EXPECTED_MAX_EVAL,
        "max_eval_observed": max_eval_observed,
        "max_eval_was_explicitly_passed": False,
        "preflight_path": str(PREFLIGHT),
        "preflight_sha256": _sha256(PREFLIGHT),
        "unique_run_root": str(RUN_ROOT),
        "input_builder_sha256": _sha256(RUN_ANALYSIS),
        "capture_helper_sha256": _sha256(CAPTURE_HELPER),
        "source_sha256": _source_hashes(),
        "torch_version": str(torch.__version__),
        "native_intake_manifest_sha256": intake_binding["manifest_sha256"],
        "native_intake_npz_sha256": intake_binding["npz_sha256"],
        "pr397_baseline_binding": baseline,
    }
    _write_private_json(RESULT_RECEIPT, public_result)
    baseline_result = json.loads(PR397_RESULT.read_text())
    baseline_driver = json.loads(PR397_DRIVER.read_text())
    comparison_audit = build_comparison_audit(
        result, baseline_result, baseline_driver, preflight,
        (ROOT / "oracle/kdm6/da_fulldomain.py").read_text())
    comparison_checks = {key: value for key, value in
                         comparison_audit["checks"].items()
                         if key != "raw_cross_run_signature_equal"}
    checks = {
        "returned_diagnostic_only": result.get("status") == "RETURNED_DIAGNOSTIC_ONLY",
        "iteration_limit_recorded_as_eight": optimization.get("max_iter") == MAX_ITER,
        "pytorch_default_max_eval_observed_as_ten": max_eval_observed == EXPECTED_MAX_EVAL,
        "one_final_audit": optimization.get("n_audit_evals") == 1,
        "fixed_support_initial_audit_crosschecked": objective_audit.get("status") == "CROSSCHECKED",
        "capture_source_unchanged": before == after,
        **comparison_checks,
    }
    driver = {
        "schema": "pr398_convergence_driver_v1",
        "experiment_id": EXPERIMENT_ID,
        "status": "RETURNED_DIAGNOSTIC_ONLY" if all(checks.values()) else "RETURNED_WITH_CHECK_FAILURES",
        "preflight_path": str(PREFLIGHT),
        "preflight_sha256": _sha256(PREFLIGHT),
        "capture_receipt_path": str(RESULT_RECEIPT),
        "capture_receipt_sha256": _sha256(RESULT_RECEIPT) if RESULT_RECEIPT.exists() else None,
        "private_checkpoint": result.get("private_checkpoint"),
        "actual_max_iter": optimization.get("max_iter"),
        "actual_max_eval": max_eval_observed,
        "max_eval_was_explicitly_passed": False,
        "objective_audit": objective_audit,
        "baseline_comparison_audit": comparison_audit,
        "checks": checks,
        "source_sha256_before": before,
        "source_sha256_after": after,
        "source_sha256": _source_hashes(),
        "torch_version": str(torch.__version__),
        "H_or_M_re_evaluations_for_crosscheck": 0,
        "native_rerun": False,
        "automatic_retry": False,
        "physical_matchup_and_science_acceptance": "NOT_ASSESSED",
        "max_eval_policy": "pytorch_lbfgs_default_ceil_1.25_max_iter",
        "max_eval_expected_from_pinned_torch": EXPECTED_MAX_EVAL,
        "unique_run_root": str(RUN_ROOT),
        "native_intake_manifest_sha256": intake_binding["manifest_sha256"],
        "native_intake_npz_sha256": intake_binding["npz_sha256"],
        "pr397_baseline_binding": baseline,
    }
    _write_private_json(DRIVER_RECEIPT, driver)
    return 0 if all(checks.values()) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-after-review", action="store_true",
                        help="perform the single analysis call after preflight/source review")
    args = parser.parse_args()
    if not PREDECLARATION.is_file():
        raise FileNotFoundError(f"predeclared protocol is missing: {PREDECLARATION}")
    created_preflight = not PREFLIGHT.exists()
    if created_preflight:
        preflight = prepare_preflight()
    else:
        preflight = json.loads(PREFLIGHT.read_text())
        if preflight.get("experiment_id") != EXPERIMENT_ID:
            raise ValueError("preflight belongs to a different experiment")
    if not args.execute_after_review:
        print(json.dumps({"status": preflight["status"], "preflight": str(PREFLIGHT),
                          "experiment_id": EXPERIMENT_ID}, indent=2))
        return 0
    if created_preflight:
        print(json.dumps({"status": "PREPARED_NO_ANALYSIS_EXECUTED",
                          "note": "review and coordinate before a separate execute invocation",
                          "preflight": str(PREFLIGHT)}, indent=2))
        return 0
    return _execute_once(preflight)


if __name__ == "__main__":
    raise SystemExit(main())
