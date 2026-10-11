"""Synthetic case-to-capture boundary tests; no M/H/optimizer invocation."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

PACKET = Path(__file__).parent


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, PACKET / file)
    result = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(result)
    return result


helper = module("case_test_intake_helpers", "test_native_case_intake.py")
driver = module("case_test_analysis_driver", "run_case_analysis.py")


def bound_ready_case(tmp_path):
    """A clearly synthetic July20 BG-only archive and decoded L1B point bundle."""
    bg, slot, date, slot_obt = "2025-07-20_05:55:40", "2025-07-20_05:56:00", "20250720", "202507200556"
    names = ["wv063", "wv069", *helper.intake.ANALYSIS_CHANNEL_NAMES.values()]
    lat, lon = 35.41925069326254, 122.13724164654832
    bt = np.arange(280.0, 289.0)
    payload = tmp_path / "observation.npz"
    np.savez(payload, **{date + "_patch_bt_K": np.broadcast_to(bt, (5, 5, 9)),
        date + "_patch_reader_dqf": np.zeros((5, 5, 9)),
        date + "_patch_latitude_deg": np.full((5, 5), lat),
        date + "_patch_longitude_deg": np.full((5, 5), lon)})
    point = {"row": 320, "column": 48, "latitude_deg": lat, "longitude_deg": lon,
             "bt_K_by_channel": dict(zip(names, bt.tolist())),
             "reader_dqf_by_channel": {n: 0 for n in names}}
    geos = {"earth_equatorial_radius": 6378137.0, "earth_polar_radius": 6356752.3,
            "nominal_satellite_height": 42164000.0, "sub_longitude": 2.2375121010567303}
    scene = {"date": date, "selected_nominal_slot_obt": slot_obt,
             "nearest_pixel": point, "status": "POINT_WITHIN_RADIUS", "nearest_pixel_within_2p5km": True,
             "time_interpretation": "Filename label and scene acquisition are OBT; mission_reference_time is planned UTC; payload valid_time_utc remains unset."}
    metadata = tmp_path / "DECODE_RECEIPT.json"
    metadata.write_text(json.dumps({"private_npz_path": str(payload), "private_npz_sha256": driver.sha(payload),
        "scenes": [{**scene, "reader_metadata": {"nominal_slot_obt": slot_obt, "pixel_utc_time_verified": False,
                     "payload_valid_time_role": "unset; filename label is OBT and no documented UTC conversion was applied",
                     "projection_type": "GEOS", "geos_header_upper_left_rad": {"image_upperleft_latitude":0.77, "image_upperleft_longitude":2.09},
                     "image_shape": [500,500], "geos": geos, "channels": names}}]}))
    result = tmp_path / "L1B_RESULT.json"
    result.write_text(json.dumps({"schema": "pr403_gk2a_l1b_heldout_result_v1", "status": "DECODED_GK2A_L1B_SCENES_ONLY",
          "private_payload_path": str(payload), "private_payload_sha256": driver.sha(payload),
          "private_decode_receipt_path": str(metadata), "scenes": [scene]}))
    obs = {"source_result_path": str(result), "source_result_sha256": driver.sha(result),
           "source_payload_path": str(payload), "source_payload_sha256": driver.sha(payload),
           "source_metadata_path": str(metadata), "source_metadata_sha256": driver.sha(metadata),
           "nearest_pixel": {k: point[k] for k in ("row", "column", "latitude_deg", "longitude_deg")}}
    run = tmp_path / "run_jul20_core"
    helper.make_run_receipts(run, run_id=run.name, start_date="2025-07-19_00:00:00")
    helper.make_forecast(run / "klfs_lc05_fcst.202507190000", times=(bg,), selected_latlon=(lat, lon))
    case = helper.case_template(run.name, run, "2025-07-19_00:00:00", case_id="synthetic_jul20_core",
               output_dir=tmp_path / "intake", background=bg, slot=slot, l1b=obs)
    case["native"]["column"].update(expected_latitude_deg=lat, expected_longitude_deg=lon)
    case_path = helper.write_case(tmp_path / "CASE.json", case)
    ready = helper.intake.load_case(case_path)
    manifest_path, npz_path = Path(case["output"]["manifest_path"]), Path(case["output"]["private_npz_path"])
    legacy = driver.load_module(driver.LEGACY_DRIVER, "case_test_driver_primitives")
    template = tmp_path / "template"
    skin = template / "in/profiles/001/sfc/01/skin.txt"
    skin.parent.mkdir(parents=True)
    skin.write_text("\n".join(["k0%surftype=1", "k0%watertype=1", "k0%salinity=35", "k0%foam_fraction=0", "k0%snow_fraction=0"] +
                              [f"k0%fastem({i})=0" for i in range(1, 6)]) + "\n")
    ctx = driver.build_inputs(ready["manifest"], ready["arrays"], tmp_path / "fixture-copy", template, legacy)
    return case, manifest_path, npz_path, ready, ctx


def test_bg_only_case_reaches_case_specific_capture_binding(tmp_path):
    case, manifest_path, npz_path, ready, ctx = bound_ready_case(tmp_path)
    capture = driver.prepare_capture_module()
    binding, coordinates, arrays, manifest = capture._validate_intake_binding(
        ctx["xb"], (ctx["forcing"],), manifest_path, driver.sha(manifest_path), npz_path, driver.sha(npz_path))
    assert binding["actual_saved_times"] == ["2025-07-20_05:55:40"]
    assert binding["state_time_mapping"]["1"]["source"] == "DERIVED_LOCAL_M_SLOT_NOT_SAVED_HOST"
    assert binding["state_time_mapping"]["1"]["time"] == "2025-07-20_05:56:00"
    assert arrays["native_window_host_dry_mass_kg_m2"].shape == (1, 39)
    assert manifest["case_id"] == case["case_id"]
    assert coordinates["PH_raw_native_bottomup"]["units"] == "m2 s-2"
    assert "viirs" not in json.dumps(ctx["run_manifest"]).lower()


def test_state_mutation_rejected_before_analysis(tmp_path):
    _, manifest_path, npz_path, _, ctx = bound_ready_case(tmp_path)
    capture = driver.prepare_capture_module()
    changed = ctx["xb"]._replace(th=ctx["xb"].th + 1)
    with pytest.raises(ValueError, match="State differs"):
        capture._validate_intake_binding(changed, (ctx["forcing"],), manifest_path,
                                         driver.sha(manifest_path), npz_path, driver.sha(npz_path))


def test_forcing_mutation_rejected_before_analysis(tmp_path):
    _, manifest_path, npz_path, _, ctx = bound_ready_case(tmp_path)
    capture = driver.prepare_capture_module()
    changed = ctx["forcing"]._replace(p=ctx["forcing"].p + 1)
    with pytest.raises(ValueError, match="Forcing differs"):
        capture._validate_intake_binding(ctx["xb"], (changed,), manifest_path,
                                         driver.sha(manifest_path), npz_path, driver.sha(npz_path))


def test_payload_values_are_checked_against_bound_point(tmp_path):
    _, _, _, ready, _ = bound_ready_case(tmp_path)
    changed = copy.deepcopy(ready["manifest"])
    changed["observation"]["nearest_pixel"]["bt_K_by_channel"]["ir105"] += 1
    with pytest.raises(ValueError, match="decoded payload differs"):
        driver.observation_values(changed)


def test_wrong_fixture_rejected_before_loading_or_creating_outputs(tmp_path):
    with pytest.raises(ValueError, match="declared GK2A-AMI template"):
        driver.execute(tmp_path / "absent.json", tmp_path / "absent.npz",
                       tmp_path / "analysis", tmp_path / "different-sensor-fixture")
    assert not (tmp_path / "analysis").exists()


def test_geometric_mismatch_rejected_before_capture_entry(tmp_path):
    _, _, _, ready, _ = bound_ready_case(tmp_path)
    arrays = {key: value.copy() for key, value in ready["arrays"].items()}
    arrays["native_surface__latitude_deg"][0] += 1
    legacy = driver.load_module(driver.LEGACY_DRIVER, "case_test_roi_primitives")
    with pytest.raises(ValueError, match="outside the declared L1B point radius"):
        driver.build_inputs(ready["manifest"], arrays, tmp_path / "copy", tmp_path / "template", legacy)


def test_case_core_capture_entry_without_executing_M_H_or_optimizer(tmp_path):
    _, manifest_path, npz_path, _, ctx = bound_ready_case(tmp_path)
    capture = driver.prepare_capture_module()
    calls = []

    def stop_at_analysis_entry(*args, **kwargs):
        calls.append(kwargs["obs_time"])
        raise RuntimeError("TEST_STOP_BEFORE_M_H_OPTIMIZER")

    result = capture.run_capture(xb=ctx["xb"], forcings=(ctx["forcing"],), y_bt=ctx["y_bt"], y_rq=ctx["y_rq"],
        xland=ctx["xland"], clear_cfg=ctx["clear_cfg"], rttov_cfg=ctx["rttov_cfg"], window_config=ctx["window_config"],
        obs_time=1, pool=object(), max_iter=3, private_checkpoint=tmp_path / "capture/private/result.npz",
        public_receipt=tmp_path / "capture/RESULT.json", case_root=tmp_path / "capture/h_cases",
        native_intake_context_path=manifest_path, native_intake_context_sha256=driver.sha(manifest_path),
        native_intake_npz_path=npz_path, native_intake_npz_sha256=driver.sha(npz_path),
        run_manifest=ctx["run_manifest"], analysis_runner=stop_at_analysis_entry)
    assert calls == [1]
    assert result["numerical_return"]["minimizer_returned_state"] is False
    assert "TEST_STOP_BEFORE_M_H_OPTIMIZER" in json.dumps(result)
    assert not (tmp_path / "capture/private/result.npz").exists()
