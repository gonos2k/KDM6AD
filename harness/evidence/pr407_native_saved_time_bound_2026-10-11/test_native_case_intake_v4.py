"""Synthetic runner gates and selected-column NetCDF intake tests; no model run."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import netCDF4
import numpy as np
import pytest

SCRIPT = Path(__file__).with_name("intake_native_case_v4.py")
spec = importlib.util.spec_from_file_location("pr406_native_case_intake", SCRIPT)
intake = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(intake)

BG = "2025-07-19_05:55:40"
SLOT = "2025-07-19_05:56:00"
DIAG = "2025-07-19_05:56:40"
INITIAL_P = np.concatenate((np.linspace(95000.0, 6000.0, 38), [5760.0])).astype(np.float32)


def case_template(run_id=None, run_dir=None, initial_time=None, *, case_id="jul19_native_core",
                  output_dir=None, l1b=None, diagnostic_times=None, background=BG, slot=SLOT):
    output_dir = Path(output_dir or Path("/tmp/pr406-case-out") / case_id)
    obs = {
        "scene_date": slot[:10].replace("-", ""),
        "nominal_slot_obt": intake.datetime.strptime(slot, intake.TIME_FORMAT).strftime("%Y%m%d%H%M"),
        "nominal_obs_model_time": slot,
        "time_assumption": "NOMINAL_FILENAME_TIME_AS_MODEL_UTC_RESEARCH_MODE",
        "observed_pixel_utc": None,
    }
    if l1b is not None:
        obs.update(l1b)
    return {
        "schema": intake.CASE_SCHEMA,
        "case_id": case_id,
        "observation": obs,
        "native": {
            "run_id": run_id,
            "run_dir": str(run_dir) if run_dir is not None else None,
            "initial_time": initial_time,
            "completion_receipt_path": (str(Path(run_dir).parent / f"{run_id}.completion.json")
                                         if run_id is not None and run_dir is not None else None),
            "completion_receipt_sha256": (
                intake.sha256_file(Path(run_dir).parent / f"{run_id}.completion.json")
                if run_id is not None and run_dir is not None
                and (Path(run_dir).parent / f"{run_id}.completion.json").is_file() else None),
            "background_valid_time": background,
            "column": {"j": 1, "i": 2, "expected_latitude_deg": 35.401,
                       "expected_longitude_deg": 122.102, "coordinate_tolerance_deg": 0.00005},
            "diagnostic_times": diagnostic_times or [],
        },
        "analysis": {
            "dt_s": 20, "obs_time": 1, "nominal_obs_model_time": slot,
            "all_sky": True, "channel_ids_1based": list(range(10, 17)),
            "require_source_dqf_zero": True, "control_fields": ["th", "qv"],
            "ncmin_land": 10.0, "ncmin_sea": 10.0,
            "use_adaptive_time_step": False, "step_to_output_time": False,
        },
        "output": {
            "manifest_path": str(output_dir / "INTAKE.json"),
            "private_npz_path": str(output_dir / "private" / f"{case_id}.npz"),
        },
    }


def write_case(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")
    return path


def write_namelist(run_dir: Path, *, time_step=20, history=15, history_s=0,
                   minutes=1, adaptive=".false.", mp_physics=337,
                   start_date=BG, nproc_x=None, nproc_y=None) -> str:
    start = intake.datetime.strptime(start_date, intake.TIME_FORMAT)
    lines = [
        "&time_control",
        f" start_date = '{start_date}',",
        f" start_year = {start.year},",
        f" start_month = {start.month},",
        f" start_day = {start.day},",
        f" start_hour = {start.hour},",
        f" start_minute = {start.minute},",
        f" start_second = {start.second},",
        f" run_minutes = {minutes},",
        " run_seconds = 0,",
        f" history_interval = {history},",
        f" history_interval_s = {history_s},",
        "/",
        "&domains",
        f" time_step = {time_step},",
        (f" nproc_x = {nproc_x}," if nproc_x is not None else ""),
        (f" nproc_y = {nproc_y}," if nproc_y is not None else ""),
        "/",
        "&physics",
        f" mp_physics = {mp_physics},",
        " ncmin_land = 10.0,",
        " ncmin_sea = 10.0,",
        f" use_adaptive_time_step = {adaptive},",
        " step_to_output_time = .false.,",
        "/",
    ]
    text = "\n".join(line for line in lines if line) + "\n"
    (run_dir / "namelist.input").write_text(text)
    effective = "\n".join(line for line in text.splitlines()
                            if "nproc_x" not in line and "nproc_y" not in line).encode()
    return hashlib.sha256(effective).hexdigest()


def make_run_receipts(run_dir: Path, *, run_id="run_dynamic_case_01", valid=True,
                      model_completed=True, exit_code=0, grid="1x1", np_ranks=1,
                      scheme="337", nml_hash=None, controls_override=None,
                      start_date=BG, **namelist_overrides):
    run_dir.mkdir(parents=True, exist_ok=True)
    nml_hash = write_namelist(run_dir, start_date=start_date, **namelist_overrides) if nml_hash is None else nml_hash
    controls = {"label": "case_specific_label", "minutes": namelist_overrides.get("minutes", 1),
                "seconds": 0, "history": namelist_overrides.get("history", 15),
                "history_s": namelist_overrides.get("history_s", 0), "np": np_ranks,
                "namelist_without_grid_sha256": nml_hash}
    if controls_override:
        controls.update(controls_override)
    (run_dir / "exit_code").write_text(f"{exit_code}\n")
    (run_dir / "run_identity.json").write_text(json.dumps({
        "exit_code": exit_code, "experiment_valid": valid,
        "scheme": str(scheme), "actual_proc_grid": grid, "controls": controls,
    }))
    (run_dir / "experiment_valid.json").write_text(json.dumps({
        "exit_code": exit_code, "experiment_valid": valid,
        "model_completed": model_completed, "actual_proc_grid": grid,
    }))
    write_completion_receipt(run_dir, run_id)
    return run_id


def write_completion_receipt(run_dir: Path, run_id: str, *, run_dir_binding=None) -> Path:
    identity_path = run_dir / "run_identity.json"
    valid_path = run_dir / "experiment_valid.json"
    valid = json.loads(valid_path.read_text())
    receipt_path = Path(run_dir_binding or run_dir).parent / f"{run_id}.completion.json"
    receipt = {
        "run_id": run_id, "run_dir": str(Path(run_dir_binding or run_dir).resolve()),
        "launcher_exit_code_file": int((run_dir / "exit_code").read_text().strip()),
        "run_identity_sha256": intake.sha256_file(identity_path),
        "experiment_valid_sha256": intake.sha256_file(valid_path),
        "experiment_valid_receipt": {key: valid[key] for key in
            ("exit_code", "experiment_valid", "model_completed", "actual_proc_grid")},
    }
    receipt_path.write_text(json.dumps(receipt))
    return receipt_path


def refresh_completion_receipt(run_dir: Path, case: dict) -> None:
    path = write_completion_receipt(run_dir, case["native"]["run_id"])
    case["native"]["completion_receipt_path"] = str(path)
    case["native"]["completion_receipt_sha256"] = intake.sha256_file(path)


def make_forecast(path: Path, times=(BG,), *, fill_qv_at=None,
                  selected_latlon=(35.401, 122.102)):
    nt, nk, nks = len(times), 39, 40
    ny, nx = 2, 3
    with netCDF4.Dataset(path, "w") as ds:
        ds.createDimension("Time", nt)
        ds.createDimension("DateStrLen", 19)
        ds.createDimension("bottom_top", nk)
        ds.createDimension("bottom_top_stag", nks)
        ds.createDimension("south_north", ny)
        ds.createDimension("west_east", nx)
        ds.setncattr("USE_THETA_M", 1)
        timevar = ds.createVariable("Times", "S1", ("Time", "DateStrLen"))
        for ti, value in enumerate(times):
            timevar[ti, :] = np.frombuffer(value.encode("ascii"), dtype="S1")
        raw_names = ["THM", "QVAPOR", "QCLOUD", "QRAIN", "QICE", "QSNOW", "QGRAUP",
                     "QNCCN", "QNCLOUD", "QNICE", "QNRAIN", "QIB"]
        cube = ("Time", "bottom_top", "south_north", "west_east")
        for name in raw_names:
            fill = np.float32(-9999.0) if name == "QVAPOR" and fill_qv_at else None
            var = ds.createVariable(name, "f4", cube, fill_value=fill)
            value = 0.001 if name == "QVAPOR" else (1.0e8 if name == "QNCCN" else 0.0)
            var[:] = np.full((nt, nk, ny, nx), value, dtype=np.float32)
        ds["THM"][:] = 0.0

        p = np.concatenate((np.linspace(95000.0, 6000.0, 38), [5760.0])).astype(np.float32)
        for name, values in (("P", p), ("PB", np.zeros(nk, dtype=np.float32))):
            var = ds.createVariable(name, "f4", cube)
            var[:] = np.broadcast_to(values[None, :, None, None], (nt, nk, ny, nx))
        cubes4 = ("Time", "bottom_top_stag", "south_north", "west_east")
        ph = np.zeros((nt, nks, ny, nx), dtype=np.float32)
        phb_levels = np.arange(nks, dtype=np.float32) * np.float32(400.0 * 9.81)
        phb = np.broadcast_to(phb_levels[None, :, None, None], (nt, nks, ny, nx)).copy()
        for name, values in (("PH", ph), ("PHB", phb)):
            ds.createVariable(name, "f4", cubes4)[:] = values
        coeff = ("Time", "bottom_top")
        for name, value in (("FNM", 1.0), ("FNP", 0.0), ("C1H", 1.0), ("C2H", 0.0), ("DNW", -1.0 / 39.0)):
            ds.createVariable(name, "f4", coeff)[:] = np.full((nt, nk), value, dtype=np.float32)
        sfc = ("Time", "south_north", "west_east")
        for name, value in (("XLAND", 2.0), ("SEAICE", 0.0), ("TSK", 300.0), ("T2", 299.0),
                            ("Q2", 0.01), ("U10", 1.0), ("V10", 2.0), ("HGT", 0.0),
                            ("MU", 100000.0), ("MUB", 0.0)):
            ds.createVariable(name, "f4", sfc)[:] = np.full((nt, ny, nx), value, dtype=np.float32)
        lat = np.empty((nt, ny, nx), dtype=np.float32)
        lon = np.empty_like(lat)
        for j in range(ny):
            for i in range(nx):
                lat[:, j, i] = 35.4 + 0.001 * j
                lon[:, j, i] = 122.1 + 0.001 * i
        lat[:, 1, 2] = selected_latlon[0]
        lon[:, 1, 2] = selected_latlon[1]
        ds.createVariable("XLAT", "f4", sfc)[:] = lat
        ds.createVariable("XLONG", "f4", sfc)[:] = lon
        if fill_qv_at is not None:
            ti, j, i = fill_qv_at
            ds["QVAPOR"][ti, 5, j, i] = np.float32(-9999.0)


def make_case_and_run(tmp_path, *, times=(BG,), diagnostic_times=None, start=BG,
                      case_id="case_ready_dynamic", run_minutes=1):
    run_dir = tmp_path / "runs" / "run_dynamic_case_01"
    run_id = make_run_receipts(run_dir, start_date=start, minutes=run_minutes)
    make_forecast(run_dir / "klfs_lc05_fcst.20250719055540", times)
    case = case_template(run_id, run_dir, start, case_id=case_id,
                         output_dir=tmp_path / "outputs" / case_id,
                         diagnostic_times=diagnostic_times, background=BG, slot=SLOT)
    case["native"]["column"].update({"j": 1, "i": 2,
                                    "expected_latitude_deg": 35.401,
                                    "expected_longitude_deg": 122.102})
    case_path = write_case(tmp_path / "cases" / f"{case_id}.json", case)
    return case, case_path, run_dir


def test_pending_run_id_never_opens_forecast_or_creates_npz(tmp_path, monkeypatch):
    case = case_template(output_dir=tmp_path / "pending", case_id="case_pending")
    case["native"]["initial_time"] = None
    case_path = write_case(tmp_path / "pending.case.json", case)
    monkeypatch.setattr(intake, "_load_legacy", lambda: pytest.fail("pending must not load reader"))
    monkeypatch.setattr(intake.netCDF4, "Dataset", lambda *a, **k: pytest.fail("pending must not open forecast"))
    result = intake.load_case(case_path)
    assert result["manifest"]["status"] == "PENDING_NATIVE_INPUT"
    assert result["arrays"] is None
    assert result["manifest"]["native_request"]["run_id"] is None
    assert not Path(case["output"]["private_npz_path"]).exists()


def test_validate_case_requires_background_plus_fixed_one_step_and_allsky_tq():
    case = case_template(run_id=None, run_dir=None, initial_time=None)
    normalized = intake.validate_case(case)
    assert normalized["analysis"]["dt_s"] == 20
    assert normalized["analysis"]["obs_time"] == 1
    assert normalized["native"]["background_valid_time"] == BG
    broken = json.loads(json.dumps(case))
    broken["analysis"]["dt_s"] = 40
    with pytest.raises(ValueError, match="fixed one-step T/Q"):
        intake.validate_case(broken)
    broken = json.loads(json.dumps(case))
    broken["native"]["background_valid_time"] = "2025-07-19_05:55:39"
    with pytest.raises(ValueError, match="exactly 20 seconds"):
        intake.validate_case(broken)


def test_dynamic_run_gate_crosschecks_actual_duration_history_and_fixed_controls(tmp_path):
    run_dir = tmp_path / "run_case_details" / "run_dynamic_details_01"
    run_id = make_run_receipts(run_dir, run_id="run_dynamic_details_01", start_date=BG,
                               minutes=7, history=60, history_s=0)
    case = case_template(run_id, run_dir, BG)
    normalized = intake.validate_case(case)
    gate = intake._completion_gate(normalized)
    assert gate["run_id"] == "run_dynamic_details_01"
    assert gate["namelist"]["case_details"]["minutes"] == 7
    assert gate["namelist"]["case_details"]["history"] == 60
    assert gate["namelist"]["controls"]["mp_physics"] == "337"
    assert gate["completion_receipt_identity_fallback"] is True


def test_missing_explicit_completion_receipt_fails_for_legacy_identity_without_run_id(tmp_path):
    run_dir = tmp_path / "run_missing_receipt" / "run_legacy_no_id_01"
    make_run_receipts(run_dir, run_id="run_legacy_no_id_01", start_date=BG)
    case = case_template("run_legacy_no_id_01", run_dir, BG)
    case["native"]["completion_receipt_path"] = None
    case["native"]["completion_receipt_sha256"] = None
    with pytest.raises(ValueError, match="explicit hash-bound completion receipt"):
        intake.validate_case(case)


def test_completion_receipt_hash_and_run_id_are_required(tmp_path):
    run_dir = tmp_path / "run_receipt_gate" / "run_receipt_gate_01"
    make_run_receipts(run_dir, run_id="run_receipt_gate_01", start_date=BG)
    case = case_template("run_receipt_gate_01", run_dir, BG)
    receipt_path = Path(case["native"]["completion_receipt_path"])
    receipt = json.loads(receipt_path.read_text())
    receipt["run_id"] = "different_archive_id"
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="completion receipt SHA-256"):
        intake._completion_gate(intake.validate_case(case))
    case["native"]["completion_receipt_sha256"] = intake.sha256_file(receipt_path)
    with pytest.raises(ValueError, match="completion receipt run_id"):
        intake._completion_gate(intake.validate_case(case))


def test_declared_identity_run_id_must_match_case_even_with_bound_completion_receipt(tmp_path):
    run_dir = tmp_path / "run_identity_id" / "run_identity_id_01"
    make_run_receipts(run_dir, run_id="run_identity_id_01", start_date=BG)
    identity_path = run_dir / "run_identity.json"
    identity = json.loads(identity_path.read_text())
    identity["run_id"] = "wrong_identity_id"
    identity_path.write_text(json.dumps(identity))
    case = case_template("run_identity_id_01", run_dir, BG)
    refresh_completion_receipt(run_dir, case)
    with pytest.raises(ValueError, match="run_identity run ID differs"):
        intake._completion_gate(intake.validate_case(case))


@pytest.mark.parametrize("receipt_mutation", ["exit", "valid", "model", "grid", "scheme"])
def test_bad_archived_completion_or_identity_is_rejected(tmp_path, receipt_mutation):
    run_dir = tmp_path / "run_bad" / "run_dynamic_bad_01"
    make_run_receipts(run_dir, run_id="run_dynamic_bad_01", start_date=BG)
    if receipt_mutation == "exit":
        (run_dir / "exit_code").write_text("1\n")
    elif receipt_mutation in ("valid", "model", "grid"):
        path = run_dir / "experiment_valid.json"
        data = json.loads(path.read_text())
        data["experiment_valid" if receipt_mutation == "valid" else
             "model_completed" if receipt_mutation == "model" else "actual_proc_grid"] = (
                 False if receipt_mutation != "grid" else "2x1")
        path.write_text(json.dumps(data))
    else:
        path = run_dir / "run_identity.json"
        data = json.loads(path.read_text())
        data["scheme"] = "137"
        path.write_text(json.dumps(data))
    case = case_template("run_dynamic_bad_01", run_dir, BG)
    refresh_completion_receipt(run_dir, case)
    with pytest.raises(ValueError):
        intake._completion_gate(intake.validate_case(case))


def test_effective_namelist_must_match_declared_run_identity_controls(tmp_path):
    run_dir = tmp_path / "run_controls" / "run_dynamic_controls_01"
    make_run_receipts(run_dir, run_id="run_dynamic_controls_01", start_date=BG)
    identity_path = run_dir / "run_identity.json"
    identity = json.loads(identity_path.read_text())
    identity["controls"]["history_s"] = 999
    identity_path.write_text(json.dumps(identity))
    case = case_template("run_dynamic_controls_01", run_dir, BG)
    refresh_completion_receipt(run_dir, case)
    with pytest.raises(ValueError, match="differs from archived namelist"):
        intake._completion_gate(intake.validate_case(case))


def test_actual_netcdf_selected_hyperslab_helper_uses_case_column_and_mask_checks(tmp_path):
    forecast = tmp_path / "slice.nc"
    make_forecast(forecast, times=(BG,), fill_qv_at=(0, 1, 2))
    legacy, _, _ = intake._load_legacy()
    selector = SimpleNamespace(J=1, I=2)
    with netCDF4.Dataset(forecast) as ds:
        with pytest.raises(ValueError, match="masked values"):
            legacy._validate_selected_frame_slices(ds, 0, selector)


def test_parameterized_selected_frame_reads_expected_j_i_without_global_mutation(tmp_path):
    forecast = tmp_path / "selected.nc"
    make_forecast(forecast, times=(BG,))
    legacy, _, reader = intake._load_legacy()
    original_j, original_i = reader.J, reader.I
    with netCDF4.Dataset(forecast) as ds:
        selector = SimpleNamespace(J=1, I=2)
        legacy._validate_selected_frame_slices(ds, 0, selector)
        frame = intake._selected_frame(reader, ds, 0, 1, 2)
    assert frame["time"] == BG
    assert frame["lat"] == pytest.approx(35.401)
    assert frame["lon"] == pytest.approx(122.102)
    assert reader.J == original_j and reader.I == original_i
    assert frame["state"]["QVAPOR"].shape == (39,)
    assert frame["p_pa"].shape == (39,) and frame["p8w_pa"].shape == (40,)


def test_core_intake_needs_only_background_and_optional_diagnostics_are_separate(tmp_path):
    case, case_path, run_dir = make_case_and_run(tmp_path, times=(BG,),
                                               diagnostic_times=[DIAG],
                                               case_id="case_core_bg_only",
                                               start="2025-07-19_00:00:00", run_minutes=358)
    result = intake.load_case(case_path)
    manifest, arrays = result["manifest"], result["arrays"]
    assert manifest["status"] == "READY_CORE_NATIVE_INTAKE"
    assert manifest["native_run"]["selected_times"] == [BG]
    assert manifest["native_run"]["diagnostic_times_omitted"] == [DIAG]
    assert manifest["native_run"]["native_observation_slot_required"] is False
    assert manifest["native_run"]["saved_times_metadata"] == {
        "count": 1, "first": BG, "last": BG,
        "ordered_times_sha256": intake.hashlib.sha256(BG.encode("ascii")).hexdigest(),
    }
    assert manifest["native_run"]["local_forcing_source_valid_time"] == BG
    assert manifest["native_run"]["initial_time"] == "2025-07-19_00:00:00"
    assert arrays["background_initial_state__th"].shape == (1, 39)
    assert arrays["forcing_window_0__p"].shape == (1, 39)
    assert arrays["native_window_state__th"].shape == (1, 39)
    assert arrays["native_window_host_dry_mass_kg_m2"].shape == (1, 39)
    assert arrays["native_window_host_dry_mass_kg_m2"].dtype == np.float32
    assert arrays["p_centers_native_bottomup_Pa"].shape == (39,)
    assert arrays["p_half_native_bottomup_Pa"].shape == (40,)
    assert arrays["p_lay_rttov_topdown_hPa"].shape == (66,)
    assert arrays["p_half_rttov_topdown_hPa"].shape == (67,)
    assert np.array_equal(arrays["p_lay_rttov_topdown_hPa"][-39:],
                          arrays["p_centers_native_bottomup_Pa"][::-1] / 100.0)
    assert np.array_equal(arrays["p_half_rttov_topdown_hPa"][-40:],
                          arrays["p_half_native_bottomup_Pa"][::-1].astype(np.float64) / 100.0)
    loaded_manifest, loaded_arrays = intake.load_bound_intake(
        Path(case["output"]["manifest_path"]), Path(case["output"]["private_npz_path"]),
        require_observation=False)
    assert loaded_manifest["case_id"] == case["case_id"]
    assert np.array_equal(loaded_arrays["background_initial_state__th"],
                          arrays["background_initial_state__th"])
    with pytest.raises(ValueError, match="requires bound PR403"):
        intake.load_bound_intake(Path(case["output"]["manifest_path"]),
                                 Path(case["output"]["private_npz_path"]))


def test_existing_declared_diagnostic_time_adds_only_that_exact_native_frame(tmp_path):
    case, case_path, run_dir = make_case_and_run(tmp_path, times=(BG, DIAG),
                                               diagnostic_times=[DIAG],
                                               case_id="case_optional_diag")
    result = intake.load_case(case_path)
    assert result["manifest"]["native_run"]["selected_times"] == [BG, DIAG]
    assert result["manifest"]["native_run"]["saved_times_metadata"]["last"] == DIAG
    assert result["arrays"]["native_window_state__th"].shape == (2, 39)
    assert result["arrays"]["native_window_forcing__p"].shape == (2, 39)
    assert result["arrays"]["native_window_p_half_calc_p8w_bottomup_Pa"].shape == (2, 40)


def test_observation_source_binding_checks_metadata_payload_slot_and_seven_dqf(tmp_path):
    payload = tmp_path / "original.npz"
    payload.write_bytes(b"synthetic-small-observation-payload")
    payload_sha = intake.sha256_file(payload)
    slot = "2025-07-19_05:56:00"
    slot_obt = "202507190556"
    pixel = {"row": 320, "column": 48, "latitude_deg": 35.41925069326254,
             "longitude_deg": 122.13724164654832, "reader_dqf_by_channel": {
                 name: 0 for name in intake.ANALYSIS_CHANNEL_NAMES.values()}}
    channels = ["wv063", "wv069", "wv073", "ir087", "ir096", "ir105", "ir112", "ir123", "ir133"]
    metadata = {"private_npz_path": str(payload), "private_npz_sha256": payload_sha,
                "scenes": [{"date": "20250719", "selected_nominal_slot_obt": slot_obt,
                            "nearest_pixel": pixel, "reader_metadata": {
                                "nominal_slot_obt": slot_obt, "pixel_utc_time_verified": False,
                                "payload_valid_time_role": "unset; filename label is OBT and no documented UTC conversion was applied",
                                "projection_type": "GEOS", "geos": {"cfac": 1},
                                "geos_header_upper_left_rad": {"image_upperleft_latitude": 0.77,
                                                                 "image_upperleft_longitude": 2.09},
                                "image_shape": [500, 500],
                                "pixel_index_semantics": "zero-based selected-array indices",
                                "channels": channels}}]}
    metadata_path = tmp_path / "DECODE_RECEIPT.json"
    metadata_path.write_text(json.dumps(metadata))
    metadata_sha = intake.sha256_file(metadata_path)
    result = {"schema": "pr403_gk2a_l1b_heldout_result_v1", "status": "DECODED_GK2A_L1B_SCENES_ONLY",
              "private_payload_path": str(payload), "private_payload_sha256": payload_sha,
              "private_decode_receipt_path": str(metadata_path), "scenes": [{
                  "date": "20250719", "selected_nominal_slot_obt": slot_obt,
                  "status": "POINT_WITHIN_RADIUS", "nearest_pixel_within_2p5km": True,
                  "nearest_pixel": pixel,
                  "time_interpretation": "Filename label and scene acquisition are OBT; mission_reference_time is planned UTC; payload valid_time_utc remains unset."}]}
    result_path = tmp_path / "RESULT.json"
    result_path.write_text(json.dumps(result))
    obs = {"source_result_path": str(result_path), "source_result_sha256": intake.sha256_file(result_path),
           "source_payload_path": str(payload), "source_payload_sha256": payload_sha,
           "source_metadata_path": str(metadata_path), "source_metadata_sha256": metadata_sha,
           "scene_date": "20250719", "nominal_slot_obt": slot_obt,
           "nominal_obs_model_time": slot, "time_assumption": "NOMINAL_FILENAME_TIME_AS_MODEL_UTC_RESEARCH_MODE",
           "observed_pixel_utc": None, "nearest_pixel": {k: pixel[k] for k in
               ("row", "column", "latitude_deg", "longitude_deg")}}
    case = case_template(output_dir=tmp_path / "obs", case_id="case_l1b_bound",
                         background=BG, slot=slot, l1b=obs)
    run_dir = tmp_path / "runs" / "run_l1b_bound_01"
    run_id = make_run_receipts(run_dir, run_id="run_l1b_bound_01", start_date=BG)
    make_forecast(run_dir / "klfs_lc05_fcst.20250719055540", times=(BG,),
                  selected_latlon=(pixel["latitude_deg"], pixel["longitude_deg"]))
    case["native"].update({"run_id": run_id, "run_dir": str(run_dir), "initial_time": BG})
    refresh_completion_receipt(run_dir, case)
    case["native"]["column"].update({"expected_latitude_deg": pixel["latitude_deg"],
                                     "expected_longitude_deg": pixel["longitude_deg"]})
    case["output"] = {"manifest_path": str(tmp_path / "obs-ready" / "INTAKE.json"),
                      "private_npz_path": str(tmp_path / "obs-ready" / "private" / "case.npz")}
    case_path = write_case(tmp_path / "obs-ready.case.json", case)
    result_intake = intake.load_case(case_path)
    assert result_intake["manifest"]["status"] == "READY_CORE_NATIVE_INTAKE"
    bound_manifest, _ = intake.load_bound_intake(case["output"]["manifest_path"],
                                                  case["output"]["private_npz_path"])
    assert bound_manifest["observation"]["binding_status"] == "BOUND_GK2A_L1B_SCENE"
    bound = intake._load_result_binding(intake.validate_case(case))
    assert bound["binding_status"] == "BOUND_GK2A_L1B_SCENE"
    assert set(bound["analysis_channel_dqf"]) == {intake.ANALYSIS_CHANNEL_NAMES[c] for c in range(10,17)}
    result["scenes"][0]["nearest_pixel"]["reader_dqf_by_channel"]["ir105"] = 1
    result_path.write_text(json.dumps(result))
    case["observation"]["source_result_sha256"] = intake.sha256_file(result_path)
    metadata["scenes"][0]["nearest_pixel"]["reader_dqf_by_channel"]["ir105"] = 1
    metadata_path.write_text(json.dumps(metadata))
    case["observation"]["source_metadata_sha256"] = intake.sha256_file(metadata_path)
    with pytest.raises(ValueError, match="seven admitted analysis-channel"):
        intake._load_result_binding(intake.validate_case(case))
