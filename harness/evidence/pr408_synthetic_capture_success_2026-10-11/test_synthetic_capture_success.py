"""One positive, synthetic-H run through the real PR395 capture/DA path.

The test consumes the existing PR407 V4 test adapter with a temporary case.
The native intake needs the local pinned P8W and upper-reference inputs; public
CI skips this positive integration when those private inputs are unavailable.
"""
from __future__ import annotations

import importlib.util
import json
import stat
from pathlib import Path

import numpy as np
import pytest


PACKET = Path(__file__).resolve().parent
PR407 = Path(__file__).resolve().parents[1] / "pr407_native_saved_time_bound_2026-10-11"
ROOT = Path(__file__).resolve().parents[3]


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


adapter_tests = _module(PR407 / "test_case_analysis_adapter.py", "pr408_case_adapter_test_helpers")
driver = adapter_tests.driver


def _required_private_input_paths() -> list[Path]:
    """Only the actual V4 intake's pinned pressure/reference sources are prerequisites."""
    legacy = driver.load_module(driver.LEGACY_DRIVER, "pr408_asset_probe_driver")
    # Import only the exact reader module pinned by the legacy driver. This
    # probe does not open a forecast or load the private reference vectors.
    reader = driver.load_module(legacy.NATIVE_READER, "pr408_native_reader_asset_probe")
    return [reader.WRF_P8W_SOURCE] + [
        reader.REF_FIXTURE / "in/profiles/001/atm" / f"{name}.txt"
        for name in ("p_half", "t", "q", "o3", "co2")]


def _require_local_native_reference_assets() -> None:
    missing = [str(path) for path in _required_private_input_paths() if not Path(path).is_file()]
    if missing:
        pytest.skip("local synthetic capture requires pinned V4 P8W/reference inputs; missing: "
                    + ", ".join(missing))


def _synthetic_inputs(tmp_path: Path, monkeypatch):
    """Reuse the established V4 case builder and the existing seven-channel synthetic H."""
    _require_local_native_reference_assets()
    tmp_path.mkdir(parents=True, exist_ok=True)
    case_scratch = tmp_path / "case"
    case_scratch.mkdir()
    case, manifest_path, npz_path, ready, ctx = adapter_tests.bound_ready_case(case_scratch)
    fixture = _module(ROOT / "oracle/tests/test_da_single_column.py", "pr408_existing_da_single_column_fixture")
    synthetic_inputs = (
        ctx["xb"], (ctx["forcing"],), ctx["y_bt"], ctx["y_rq"], ctx["xland"],
        ctx["clear_cfg"], ctx["rttov_cfg"], ctx["window_config"])
    observed_h_calls = fixture._install_synthetic_allsky(monkeypatch, inputs=synthetic_inputs)
    return fixture, case, manifest_path, npz_path, ready, ctx, observed_h_calls


def run_synthetic_capture_success(output_root: Path, scratch_root: Path, monkeypatch, *,
                                  private_checkpoint: Path | None = None,
                                  public_receipt: Path | None = None,
                                  case_root: Path | None = None) -> dict:
    """Run unchanged V4 adapter + real KDM6/LBFGS/final-audit through synthetic all-sky H."""
    output_root = Path(output_root).resolve()
    if output_root.exists():
        raise FileExistsError(f"synthetic capture run ID already exists; refusing overwrite: {output_root}")
    fixture, case, manifest_path, npz_path, ready, ctx, observed_h_calls = _synthetic_inputs(
        Path(scratch_root), monkeypatch)
    capture = driver.prepare_capture_module()
    checkpoint = Path(private_checkpoint or output_root / "private" / "accepted_state.npz").resolve()
    public_receipt = Path(public_receipt or output_root / "CAPTURE.json").resolve()
    h_case_root = Path(case_root or output_root / "h_cases").resolve()
    result = capture.run_capture(
        xb=ctx["xb"], forcings=(ctx["forcing"],), y_bt=ctx["y_bt"], y_rq=ctx["y_rq"],
        xland=ctx["xland"], clear_cfg=ctx["clear_cfg"], rttov_cfg=ctx["rttov_cfg"],
        window_config=ctx["window_config"], obs_time=1, pool=fixture.InlinePool(),
        private_checkpoint=checkpoint, public_receipt=public_receipt, case_root=h_case_root,
        native_intake_context_path=manifest_path,
        native_intake_context_sha256=driver.sha(manifest_path),
        native_intake_npz_path=npz_path, native_intake_npz_sha256=driver.sha(npz_path),
        run_manifest=ctx["run_manifest"], max_iter=3, n_workers=1)

    assert result["status"] == "RETURNED_DIAGNOSTIC_ONLY"
    assert result["numerical_return"]["status"] == "RETURNED"
    assert result["numerical_return"]["final_accepted_state_audit_callback"] is True
    assert result["objective"]["n_audit_evals"] == 1
    assert result["objective"]["n_valid"] == 7
    assert result["production_source_sha256_before_after"]["unchanged"] is True
    assert len(result["logical_h_calls"]) == len(observed_h_calls)
    assert len(observed_h_calls) >= 3
    assert all(np.all(np.asarray(call["rad_quality"]) == 0)
               for call in result["logical_h_calls"])

    legacy = driver.load_module(driver.LEGACY_DRIVER, "pr408_capture_result_audit")
    independent_audit = legacy._audit_initial_objectives(result, ctx["y_bt"])
    assert independent_audit["status"] == "CROSSCHECKED"
    objective = result["objective"]
    assert objective["Jtotal"] == pytest.approx(
        objective["Jb_state"] + objective["Jtheta"] + objective["Jo"], rel=1e-12, abs=1e-14)
    assert objective["Jtotal"] == pytest.approx(objective["Jtotal_final_trace"], rel=1e-12, abs=1e-14)
    assert objective["Jtheta"] == 0.0
    assert result["adapter_metadata"]["parameter_prior"]["active"] == []

    checkpoint_record = result["private_checkpoint"]
    assert checkpoint_record["path"] == str(checkpoint.resolve())
    assert checkpoint_record["sha256"] == driver.sha(checkpoint)
    assert stat.S_IMODE(checkpoint.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(checkpoint.stat().st_mode) == 0o600
    with np.load(checkpoint, allow_pickle=False) as archive:
        private = {key: archive[key].copy() for key in archive.files}
    assert private["background_initial_state__th"].shape == (1, 39)
    assert private["returned_analysis_initial_state__th"].shape == (1, 39)
    assert private["background_slot_state__th"].shape == (1, 39)
    assert private["final_slot_state__th"].shape == (1, 39)
    assert private["observation_y_bt_K"].shape == (1, 7)
    assert private["observation_y_dqf"].shape == (1, 7)
    assert private["final_slot_bt_K"].shape == (1, 7)
    assert np.isfinite(private["final_slot_bt_K"]).all()
    assert private["final_slot_rad_quality"].shape == (1, 7)
    assert np.array_equal(private["final_slot_rad_quality"], np.zeros((1, 7)))
    assert np.array_equal(private["final_slot_frozen_mask"], np.ones((1, 7)))
    assert np.array_equal(private["observation_y_bt_K"], ctx["y_bt"].detach().cpu().numpy())
    assert np.array_equal(private["observation_y_dqf"], np.zeros((1, 7)))
    for state in ("background_initial_state", "returned_analysis_initial_state",
                  "background_slot_state", "final_slot_state"):
        for field in fixture_module_state_fields(fixture):
            values = private[f"{state}__{field}"]
            assert values.shape == (1, 39) and np.isfinite(values).all()

    gradient_state = private["control__optimizer_final_gradient_v_state"]
    gradient_theta = private["control__optimizer_final_gradient_v_theta"]
    gradient_combined = private["control__optimizer_final_gradient_combined"]
    assert np.isfinite(gradient_state).all() and np.isfinite(gradient_theta).all()
    assert gradient_combined.size == gradient_state.size + gradient_theta.size
    np.testing.assert_array_equal(
        gradient_combined.reshape(-1),
        np.concatenate((gradient_state.reshape(-1), gradient_theta.reshape(-1))))
    gradient_summary = result["final_control_gradient"]
    assert float(np.linalg.norm(gradient_state)) == pytest.approx(
        gradient_summary["state_l2_norm"], rel=1e-12, abs=1e-12)
    assert float(np.linalg.norm(gradient_theta)) == pytest.approx(
        gradient_summary["theta_l2_norm"], rel=1e-12, abs=1e-12)
    assert result["control_background"]["b_sigma_by_state_field"]["th"]["shape"] == [1, 39]
    assert result["control_background"]["b_sigma_by_state_field"]["qv"]["shape"] == [1, 39]
    sigma_th = private["control__b_sigma__th"]
    sigma_qv = private["control__b_sigma__qv"]
    assert np.all(sigma_th == np.float64(0.8))
    np.testing.assert_array_equal(sigma_qv[0, :12], np.full(12, 0.08))
    assert sigma_qv[0, 12] == 0.0
    assert np.all(private["control__parameter_sigma_log"] == 0.0)
    with open(public_receipt, encoding="utf-8") as stream:
        saved_receipt = json.load(stream)
    assert saved_receipt["status"] == "RETURNED_DIAGNOSTIC_ONLY"
    assert saved_receipt["private_checkpoint"]["sha256"] == driver.sha(checkpoint)
    assert saved_receipt["private_checkpoint"]["contains_full_state_arrays"] is True
    assert saved_receipt["private_checkpoint"]["public_receipt_contains_full_state_arrays"] is False

    checkpoint_sha, public_sha = driver.sha(checkpoint), driver.sha(public_receipt)
    with pytest.raises(FileExistsError, match="fresh paths"):
        capture.run_capture(
            xb=ctx["xb"], forcings=(ctx["forcing"],), y_bt=ctx["y_bt"], y_rq=ctx["y_rq"],
            xland=ctx["xland"], clear_cfg=ctx["clear_cfg"], rttov_cfg=ctx["rttov_cfg"],
            window_config=ctx["window_config"], obs_time=1, pool=fixture.InlinePool(),
            private_checkpoint=checkpoint, public_receipt=public_receipt, case_root=h_case_root,
            native_intake_context_path=manifest_path,
            native_intake_context_sha256=driver.sha(manifest_path),
            native_intake_npz_path=npz_path, native_intake_npz_sha256=driver.sha(npz_path),
            run_manifest=ctx["run_manifest"], max_iter=3, n_workers=1)
    assert driver.sha(checkpoint) == checkpoint_sha
    assert driver.sha(public_receipt) == public_sha

    return {"result": result, "independent_audit": independent_audit,
            "checkpoint": checkpoint, "public_receipt": public_receipt,
            "manifest": ready["manifest"], "npz_path": npz_path,
            "case": case, "ctx": ctx, "h_calls": observed_h_calls,
            "output_root": output_root, "test_source_sha256": driver.sha(Path(__file__))}


def fixture_module_state_fields(fixture) -> tuple[str, ...]:
    return tuple(fixture._inputs()[0]._fields)


def test_synthetic_capture_success_runs_real_kdm_and_publishes_auditable_checkpoint(
        tmp_path, monkeypatch):
    result = run_synthetic_capture_success(tmp_path / "success", tmp_path / "scratch", monkeypatch)
    assert result["result"]["status"] == "RETURNED_DIAGNOSTIC_ONLY"
