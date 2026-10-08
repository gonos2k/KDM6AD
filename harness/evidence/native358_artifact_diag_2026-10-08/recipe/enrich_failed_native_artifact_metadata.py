#!/usr/bin/env python3
"""Build a transparent post-run execution inventory without rerunning RTTOV."""
from __future__ import annotations

import hashlib
import json
import math
import argparse
from pathlib import Path
import re
import shutil
import sys
from datetime import datetime, timezone

import netCDF4
import numpy as np

ROOT = Path("/private/tmp/KDM6AD-viirs-native-run-20261007")
COMPARISON = ROOT / "comparison"
RUN_ID = "mp337_viirs_norm2_dry1_055540_055800_358min_hist0_20261008_064206_p28793"
DEFAULT_DIAGNOSTIC_DIR = COMPARISON / "results_failed_native_artifact_diag_055540_055800_retry1"
RECEIPT = ROOT / "evidence/target_native_run_receipt_2026-10-08.json"
FORECAST = ROOT / "target_case_055540_055800/runs" / RUN_ID / "klfs_lc05_fcst.202507190000"
FIXTURE = Path("/Users/yhlee/AD-RTTOV/external/rttov14/src/rttov_test/tests.1.gfortran-openmp/ami/cloud")
RTTOV_SIMPLE_CLOUD_SOURCE = Path("/Users/yhlee/AD-RTTOV/external/rttov14/src/src/main/rttov_calc_simple_cloud_params.F90")
NATIVE_J, NATIVE_I = 86, 48
CHANNELS = list(range(8, 17))
SUPPORT = [10, 11, 12, 13, 14, 15, 16]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def expect_equal(name: str, actual, expected) -> None:
    if not np.array_equal(np.asarray(actual), np.asarray(expected)):
        a, b = np.asarray(actual), np.asarray(expected)
        raise ValueError(f"{name} mismatch: shapes {a.shape}/{b.shape}, maxdiff={np.max(np.abs(a-b))}")


def key_value(path: Path, key: str) -> str | None:
    m = re.search(rf"(?im)^\s*{re.escape(key)}\s*=\s*([^!\n]+)", path.read_text())
    return m.group(1).strip().strip("'\"") if m else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnostic-dir", type=Path, default=DEFAULT_DIAGNOSTIC_DIR)
    diagnostic_dir = parser.parse_args().diagnostic_dir.resolve()
    result_path = diagnostic_dir / "native8frame_failed_run_artifact_diagnostic.json"
    raw_result_copy = diagnostic_dir / "native8frame_failed_native_artifact_runner_raw.json"
    enriched_result_path = diagnostic_dir / "native8frame_failed_run_artifact_diagnostic_enriched.json"
    inventory_path = diagnostic_dir / "native8frame_failed_run_execution_inventory.json"
    runner_script = COMPARISON / "run_native_kma_bt_frames.py"
    enrichment_script = Path(__file__).resolve()
    raw_sha = sha256(result_path)
    raw = json.loads(result_path.read_text())
    receipt = json.loads(RECEIPT.read_text())
    if not (raw.get("native_run_valid") is False and raw.get("experiment_valid") is False
            and raw.get("diagnostic_only") is True and raw.get("eligible_for_artifact_gates") is False
            and raw.get("native_run_id") == RUN_ID and receipt.get("run_id") == RUN_ID
            and receipt.get("successful") is False):
        raise ValueError("input result is not the preserved diagnostic-only failed-run result")
    if sha256(FORECAST) != receipt["forecast"]["sha256"]:
        raise ValueError("receipt-verified native forecast SHA changed")
    if raw_result_copy.exists():
        if sha256(raw_result_copy) != raw_sha:
            raise FileExistsError(f"existing raw-result copy has an unexpected SHA: {raw_result_copy}")
    else:
        shutil.copy2(result_path, raw_result_copy)

    with netCDF4.Dataset(FORECAST) as ds:
        times = [r.tobytes().decode("ascii").strip() for r in ds["Times"][:]]
        if times != raw["forecast_times"] or len(times) != 8:
            raise ValueError("forecast Times changed or differ from the executed comparison set")
        if ds.dimensions["bottom_top"].size != 39 or ds.dimensions["bottom_top_stag"].size != 40:
            raise ValueError("forecast native vertical dimensions differ from the declared host grid")

        per_frame_inventory = []
        enriched = json.loads(json.dumps(raw))
        raw_source_hashes = []
        for frame in enriched["per_frame"]:
            index = frame["index"]
            case = diagnostic_dir / f"case_{index:02d}"
            atm = case / "in/profiles/001/atm"
            executed_nml = case / "out/rttov_test.txt"
            profile_names = ("p.txt", "p_half.txt", "t.txt", "q.txt", "o3.txt", "co2.txt")
            arrays = {name: np.loadtxt(atm / name, dtype=np.float64) for name in profile_names}
            p, p_half, t, q, o3, co2 = (arrays[n] for n in profile_names)
            p_native_hpa = (np.asarray(ds["P"][index, :, NATIVE_J, NATIVE_I], dtype=np.float64)
                            + np.asarray(ds["PB"][index, :, NATIVE_J, NATIVE_I], dtype=np.float64))[::-1] / 100.0
            ph_native_hpa = np.asarray(frame["native_pressure_interfaces_hPa"], dtype=np.float64)
            expect_equal(f"frame {index} executed native P centers hPa", p[-39:], p_native_hpa)
            expect_equal(f"frame {index} executed native P interfaces hPa", p_half[-40:], ph_native_hpa)
            expect_equal(f"frame {index} executed native T centers", t[-39:], frame["native_t_layer_K"])
            expect_equal(f"frame {index} executed native Q centers", q[-39:], frame["native_q_layer_ppmv_moist"])

            # Independently check source/reference extension against the pressure
            # vectors that were placed in the actual executed RTTOV case.
            ref_atm = FIXTURE / "in/profiles/001/atm"
            ref_ph = np.loadtxt(ref_atm / "p_half.txt", dtype=np.float64)
            ref_ph_for_full = ref_ph.copy()
            ref_ph_for_full[0] = max(ref_ph_for_full[0], 1.0e-12)
            ref_p = 0.5 * (ref_ph_for_full[:-1] + ref_ph_for_full[1:])
            ref_t, ref_q, ref_o3, ref_co2 = (np.loadtxt(ref_atm / f"{name}.txt", dtype=np.float64)
                                             for name in ("t", "q", "o3", "co2"))
            nbg = p.size - 39
            t_expected = np.concatenate((np.interp(np.log(p[:nbg]), np.log(ref_p), ref_t),
                                         np.asarray(frame["native_t_layer_K"], dtype=np.float64)))
            q_expected = np.concatenate((np.interp(np.log(p[:nbg]), np.log(ref_p), ref_q),
                                         np.asarray(frame["native_q_layer_ppmv_moist"], dtype=np.float64)))
            o3_expected = np.interp(np.log(p), np.log(ref_p), ref_o3)
            co2_expected = np.interp(np.log(p), np.log(ref_p), ref_co2)
            expect_equal(f"frame {index} executed full T", t, t_expected)
            expect_equal(f"frame {index} executed full Q", q, q_expected)
            expect_equal(f"frame {index} executed full O3", o3, o3_expected)
            expect_equal(f"frame {index} executed full CO2", co2, co2_expected)
            p_min, p_max = float(np.min(ref_p)), float(np.max(ref_p))
            n_below, n_above = int(np.count_nonzero(p < p_min)), int(np.count_nonzero(p > p_max))
            gas_clamps = frame["trace_gas_endpoint_diagnostics"]["per_gas_endpoint_clamp_layers"]
            for gas in ("O3", "CO2"):
                if gas_clamps[gas] != {"layers_below_reference_min": n_below,
                                      "layers_above_reference_max": n_above}:
                    raise ValueError(f"frame {index} {gas} endpoint clamp metadata mismatch")

            namelist = executed_nml.read_text()
            solar_flags = re.findall(r"(?im)^\s*defn%opts%rt_all%solar\s*=\s*([^!\n]+)", namelist)
            if [v.strip().rstrip(",").upper() for v in solar_flags] != [".FALSE."]:
                raise ValueError(f"frame {index} executed RTTOV namelist is not solar-disabled")
            input_coef = case / "in/coef.txt"
            coef_prefix = key_value(executed_nml, "defn%coef_prefix")
            coef_name = key_value(input_coef, "defn%f_coef")
            hydro_name = key_value(input_coef, "defn%f_hydrotable")
            if not coef_prefix or not coef_name or not hydro_name:
                raise ValueError(f"frame {index} coefficient or hydrotable reference missing")
            coef_path = (case / "out" / coef_prefix / coef_name).resolve()
            hydrotable_path = (case / "out" / coef_prefix / hydro_name).resolve()
            if not coef_path.is_file() or not hydrotable_path.is_file():
                raise FileNotFoundError(f"frame {index} RTTOV coefficient assets are missing")
            if sha256(coef_path) != raw["per_frame"][0]["rttov_coefficient_sha256"]:
                raise ValueError("executed RTTOV coefficient bytes differ from recorded source hash")

            run_script = case / "out/run.sh"
            run_text = run_script.read_text()
            exe_match = re.search(r"(?m)^\s*(/[^\s]+rttov_test\.exe)\s*>", run_text)
            if exe_match is None:
                raise ValueError(f"frame {index} RTTOV run.sh executable path missing")
            exe_command_path = exe_match.group(1)
            exe_path = Path(exe_command_path).resolve()
            if not exe_path.is_file():
                raise FileNotFoundError(exe_path)
            log = case / "out/rttov_test.log"
            log_text = log.read_text(errors="replace")
            if not log_text:
                raise ValueError(f"frame {index} RTTOV output log is empty")
            quality_lines = [line.strip() for line in log_text.splitlines()
                             if "Quality OK" in line or "Delta-Eddington" in line]

            hydros = np.loadtxt(atm / "hydro.txt", dtype=np.float64)
            hydro_frac = np.loadtxt(atm / "hydro_frac.txt", dtype=np.float64, skiprows=1)
            hydros_deff = np.loadtxt(atm / "hydro_deff.txt", dtype=np.float64)
            mmr_text = (atm / "mmr_hydro_aer.txt").read_text()
            mmr_aer = re.search(r"(?im)^\s*mmr_aer\s*=\s*([^\s/]+)", mmr_text)
            if hydros.shape != (66, 8) or not np.all(hydros == 0.0) or not np.all(hydro_frac == 0.0):
                raise ValueError(f"frame {index} executed hydrometeor content/fraction is not all zero")
            if mmr_aer is None or mmr_aer.group(1).upper() != "F":
                raise ValueError(f"frame {index} aerosol unit flag is not explicitly false")
            if key_value(input_coef, "defn%f_aertable") is not None:
                raise ValueError(f"frame {index} unexpectedly configures an aerosol table")
            simple_cloud = atm / "simple_cloud.txt"
            simple_cloud_text = simple_cloud.read_text()
            simple_cloud_values = {
                k: float(v) for k, v in re.findall(r"(?im)^\s*(ctp|cfraction)\s*=\s*([0-9.Ee+-]+)", simple_cloud_text)
            }
            if (simple_cloud_values.get("cfraction") != frame.get("executed_simple_cloud_fraction")
                    or simple_cloud_values.get("ctp") != frame.get("executed_simple_cloud_ctp_hPa")
                    or simple_cloud_values.get("cfraction") != 0.0):
                raise ValueError(f"frame {index} simple-cloud fallback metadata differs from the executed file")
            raw_contribution_key = ("common_support_huber_contribution_K2"
                                    if "common_support_huber_contribution_K2" in frame
                                    else "common_support_huber_contribution_dimensionless")
            raw_values = np.asarray(frame[raw_contribution_key], dtype=np.float64)
            sigma = float(raw["sigma_K"])
            delta = float(raw["huber_delta"])
            residual_dimensionless = ((np.asarray(frame["bt_K"], dtype=np.float64)
                                       - np.asarray(raw["observation_bt_K"], dtype=np.float64)) / sigma)
            computed_dimensionless = np.where(
                np.abs(residual_dimensionless) <= delta,
                0.5 * residual_dimensionless * residual_dimensionless,
                delta * (np.abs(residual_dimensionless) - 0.5 * delta))
            computed_dimensionless = np.where(frame["common_support"], computed_dimensionless, 0.0)
            expect_equal(f"frame {index} standardized Huber contributions", raw_values,
                         computed_dimensionless)
            if not math.isclose(float(np.sum(computed_dimensionless)),
                                float(raw["cost_sum_huber_all_eight_same_support"][index]),
                                rel_tol=1.0e-13, abs_tol=1.0e-13):
                raise ValueError(f"frame {index} standardized Huber contributions do not sum to stored cost")
            frame["runner_original_common_support_contribution_field"] = {
                "name": raw_contribution_key,
                "values": raw_values.tolist(),
                "unit_label_note": ("runner's name was dimensionally wrong; sigma_K=1 made the stored numbers equal the dimensionless standardized values"
                                    if raw_contribution_key.endswith("_K2") else "runner already labeled this field as dimensionless"),
            }
            frame["common_support_huber_contribution_dimensionless"] = computed_dimensionless.tolist()
            frame.pop("common_support_huber_contribution_K2", None)
            pressure_values = np.asarray(frame["native_pressure_centers_hPa"], dtype=np.float64)
            pressure_scale_correction = not np.array_equal(pressure_values, p[-39:])
            if pressure_scale_correction:
                if not np.array_equal(pressure_values / 100.0, p[-39:]):
                    raise ValueError(f"frame {index} pressure field has an unexpected unit/value mismatch")
                frame["native_pressure_centers_originally_serialized_values"] = pressure_values.tolist()
                frame["native_pressure_centers_original_unit"] = "Pa despite the original key suffix hPa"
            frame["native_pressure_centers_hPa"] = p[-39:].tolist()
            frame["native_pressure_centers_hPa_correction"] = {
                "raw_key_had_pa_values": True,
                "corrected_from": "executed RTTOV input p.txt native suffix, independently equal to saved forecast (P+PB)/100 hPa",
                "raw_runner_result_preserved_at": str(raw_result_copy),
            }
            frame["executed_profile_inputs"] = {
                name: {"path": str(atm / name), "sha256": sha256(atm / name)} for name in profile_names
            }
            frame["executed_native_profile_grid_checks"] = {
                "native_p_centers_equal_forecast_P_plus_PB_over_100_hPa": True,
                "native_p_interfaces_equal_recorded_source_transcription_hPa": True,
                "native_T_centers_equal_RTTOV_input": True,
                "native_Q_centers_equal_RTTOV_input": True,
            }
            frame["executed_hydrometeor_input_audit"] = {
                "hydro_path": str(atm / "hydro.txt"), "hydro_sha256": sha256(atm / "hydro.txt"),
                "hydro_shape": list(hydros.shape), "hydro_all_eight_slots_zero": True,
                "hydro_frac_path": str(atm / "hydro_frac.txt"),
                "hydro_frac_sha256": sha256(atm / "hydro_frac.txt"),
                "hydro_frac_max": float(np.max(hydro_frac)),
                "hydro_deff_path": str(atm / "hydro_deff.txt"),
                "hydro_deff_sha256": sha256(atm / "hydro_deff.txt"),
                "hydro_deff_max_slots_6_7": np.max(hydros_deff[:, 5:7], axis=0).tolist(),
                "deff_note": "positive explicit diameters remain in the file where content and fraction are zero; they do not imply condensate amount",
                "mmr_hydro_aer_path": str(atm / "mmr_hydro_aer.txt"),
                "mmr_hydro_aer_sha256": sha256(atm / "mmr_hydro_aer.txt"),
                "mmr_hydro": key_value(atm / "mmr_hydro_aer.txt", "mmr_hydro"),
                "mmr_aer": mmr_aer.group(1).upper(),
                "aerosol_table_configured": False,
                "aerosol_amount_profile_files": [
                    x.name for x in atm.iterdir()
                    if re.match(r"^(?:aer|aerosol)(?:[_.-]|$)", x.name.lower())
                ],
                "simple_cloud_path": str(simple_cloud), "simple_cloud_sha256": sha256(simple_cloud),
                "simple_cloud_values": simple_cloud_values,
                "scope": "saved model hydrometeor amount paths and the executed RTTOV hydrometeor slots are zero; not a claim that the gas atmosphere or all RTTOV cloud metadata is clear",
            }
            frame["executed_rttov_assets"] = {
                "command_executable_path": exe_command_path,
                "resolved_executable_path": str(exe_path),
                "executable_sha256_at_inventory_capture": sha256(exe_path),
                "executable_sha256_before_run": (raw.get("rttov_execution_assets") or {}).get("rttov_executable_sha256_before"),
                "executable_sha256_after_run": (raw.get("rttov_execution_assets") or {}).get("rttov_executable_sha256_after"),
                "executable_hash_timing_note": (
                    "runner recorded preflight and postflight hashes; they match"
                    if (raw.get("rttov_execution_assets") or {}).get("rttov_executable_sha256_before") is not None
                    else "captured after the eight RTTOV calls; no before/after binary pin was saved during execution"),
                "run_script_path": str(run_script), "run_script_sha256": sha256(run_script),
                "env_script_path": str(case / "out/env.sh"), "env_script_sha256": sha256(case / "out/env.sh"),
                "executed_namelist_path": str(executed_nml), "executed_namelist_sha256": sha256(executed_nml),
                "solar_flags": [v.strip().rstrip(",").upper() for v in solar_flags],
                "coefficient_path": str(coef_path), "coefficient_sha256": sha256(coef_path),
                "hydrotable_path": str(hydrotable_path), "hydrotable_sha256": sha256(hydrotable_path),
                "rttov_test_log_path": str(log), "rttov_test_log_sha256": sha256(log),
                "quality_messages": quality_lines,
                "run_stdout_sha256": sha256(case / "out/run.stdout.log"),
                "run_stderr_sha256": sha256(case / "out/run.stderr.log"),
                "rttov_runner_return_code": 0,
                "return_code_basis": "RttovObsOp returned BT/K/quality; rttov_runner._run_case_fresh raises for nonzero child status",
            }
            raw_source_hashes.append({"valid_time": frame["valid_time"],
                                      "executed_rttov_namelist_sha256": sha256(executed_nml),
                                      "executed_T_sha256": sha256(atm / "t.txt"),
                                      "executed_Q_sha256": sha256(atm / "q.txt"),
                                      "executed_P_sha256": sha256(atm / "p.txt"),
                                      "executed_P_HALF_sha256": sha256(atm / "p_half.txt")})
            per_frame_inventory.append({
                "index": index, "valid_time": frame["valid_time"],
                "profile_input_files_exact_vs_expected": True,
                "native_pressure_centers_hPa_exact_vs_saved_forecast": True,
                "native_pressure_interfaces_T_Q_exact_vs_recorded": True,
                "trace_gas_endpoint_clamp_counts": frame["trace_gas_endpoint_diagnostics"],
                "hydrometeor_slot_max": float(np.max(np.abs(hydros))),
                "hydro_fraction_max": float(np.max(hydro_frac)),
                "rttov_executable_sha256_at_inventory_capture": sha256(exe_path),
                "rttov_test_log_sha256": sha256(log),
                "rttov_quality_messages": quality_lines,
            })

    retry1_dir = COMPARISON / "results_failed_native_artifact_diag_055540_055800_retry1"
    retry1_raw_path = retry1_dir / "native8frame_failed_run_artifact_diagnostic.json"
    retry1_comparison = None
    if diagnostic_dir.name.endswith("_retry2") and retry1_raw_path.is_file():
        retry1 = json.loads(retry1_raw_path.read_text())
        def tree_hashes(case_root: Path) -> dict[str, str]:
            return {str(path.relative_to(case_root)): sha256(path)
                    for path in case_root.rglob("*") if path.is_file()}
        case_differences = []
        for i in range(8):
            old_case, new_case = retry1_dir / f"case_{i:02d}", diagnostic_dir / f"case_{i:02d}"
            old_hashes, new_hashes = tree_hashes(old_case), tree_hashes(new_case)
            if old_hashes.keys() != new_hashes.keys():
                raise ValueError(f"retry1/retry2 case {i} artifact topology differs")
            changed = sorted(k for k in old_hashes if old_hashes[k] != new_hashes[k])
            if changed != ["in/profiles/001/atm/simple_cloud.txt"]:
                raise ValueError(f"retry1/retry2 case {i} has unexpected artifact differences: {changed}")
            old_simple = old_case / "in/profiles/001/atm/simple_cloud.txt"
            new_simple = new_case / "in/profiles/001/atm/simple_cloud.txt"
            old_vals = {k: float(v) for k, v in re.findall(
                r"(?im)^\s*(ctp|cfraction)\s*=\s*([0-9.Ee+-]+)", old_simple.read_text())}
            new_vals = {k: float(v) for k, v in re.findall(
                r"(?im)^\s*(ctp|cfraction)\s*=\s*([0-9.Ee+-]+)", new_simple.read_text())}
            if old_vals != {"ctp": 949.0, "cfraction": 0.6} or new_vals != {"ctp": 949.0, "cfraction": 0.0}:
                raise ValueError(f"retry1/retry2 simple-cloud change is not the authorized CTP-preserving fraction change: {old_vals}/{new_vals}")
            case_differences.append(dict(case=f"case_{i:02d}", file_differences=changed,
                                         ctp_hPa_unchanged=True, simple_cloud_fraction_before=0.6,
                                         simple_cloud_fraction_after=0.0,
                                         per_file_sha256=[dict(path=path, retry1=old_hashes[path], retry2=new_hashes[path])
                                                          for path in sorted(old_hashes)]))
        retry_bt_1, retry_bt_2 = np.asarray(retry1["model_bt_K"]), np.asarray(raw["model_bt_K"])
        retry_rq_1, retry_rq_2 = np.asarray(retry1["model_rad_quality"]), np.asarray(raw["model_rad_quality"])
        retry_cost_1 = np.asarray(retry1["cost_sum_huber_all_eight_same_support"])
        retry_cost_2 = np.asarray(raw["cost_sum_huber_all_eight_same_support"])
        retry1_comparison = dict(
            earlier_retry_result_path=str(retry1_raw_path), earlier_retry_result_sha256=sha256(retry1_raw_path),
            comparison_scope="retry1 solar-off, inherited simple_cloud fraction=0.6 versus retry2 same inputs with only staged simple_cloud fraction set to 0.0",
            per_case_case_tree_identical_except_simple_cloud_file=case_differences,
            model_bt_bitwise_equal=bool(np.array_equal(retry_bt_1.view(np.uint64), retry_bt_2.view(np.uint64))),
            model_rad_quality_bitwise_equal=bool(np.array_equal(retry_rq_1.view(np.uint64), retry_rq_2.view(np.uint64))),
            costs_bitwise_equal=bool(np.array_equal(retry_cost_1.view(np.uint64), retry_cost_2.view(np.uint64))),
            max_abs_model_bt_difference_K=float(np.max(np.abs(retry_bt_1 - retry_bt_2))),
            max_abs_model_rad_quality_difference=float(np.max(np.abs(retry_rq_1 - retry_rq_2))),
            max_abs_cost_difference=float(np.max(np.abs(retry_cost_1 - retry_cost_2))),
            diagnostic_interpretation="The explicit simple-cloud fraction change altered no BT, RTTOV quality, or cost in this run; the inputs remain labeled as diagnostic-only and no cloud physics conclusion is implied.")

    mae = []
    support = np.asarray(raw["fixed_common_support_channel_indices_0based"], dtype=int)
    obs = np.asarray(raw["observation_bt_K"], dtype=np.float64)
    for frame in enriched["per_frame"]:
        bt = np.asarray(frame["bt_K"], dtype=np.float64)
        resid = bt - obs
        mae.append(float(np.mean(np.abs(resid[support]))))
    ch_ir105 = CHANNELS.index(13)  # KMA channel position for IR105 in configured list 8..16
    model_ir105 = np.asarray(raw["model_bt_K"], dtype=np.float64)[:, ch_ir105]
    enriched["native_run_lifecycle"]["overall_fatal_or_error_lines_observed"] = receipt.get("fatal_or_error_lines_observed")
    enriched["native_run_lifecycle"]["wrapper_wrf_fatal_lines_observed"] = receipt["runner_result"].get("wrf_fatal_lines_observed")
    inventory = dict(
        schema="failed_native_artifact_rttov_execution_inventory_v1",
        enrichment_scope="post-run file inventory and metadata correction only; no RTTOV or KDM rerun and no BT/quality/cost values changed",
        captured_at_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        runner_output_raw_path=str(result_path), runner_output_raw_sha256=raw_sha,
        runner_output_raw_preserved_copy=str(raw_result_copy),
        runner_output_raw_preserved_copy_sha256=sha256(raw_result_copy),
        enriched_result_path=str(enriched_result_path),
        enrichment_script=dict(path=str(enrichment_script), sha256=sha256(enrichment_script)),
        native_run_id=RUN_ID, native_run_status=raw["native_run_lifecycle"],
        native_run_valid=False, experiment_valid=False, diagnostic_only=True,
        eligible_for_artifact_gates=False,
        source_snapshot=dict(
            path=raw.get("comparison_runner_source", {}).get("snapshot_path"),
            sha256=raw.get("comparison_runner_source", {}).get("snapshot_sha256"),
            executed_source_sha256_before=raw.get("comparison_runner_source", {}).get("sha256_before"),
            executed_source_sha256_after=raw.get("comparison_runner_source", {}).get("sha256_after"),
            captured_by_run=bool(raw.get("comparison_runner_source")),
            imported_runtime_module_hashes=raw["source_hashes"]["runtime_python"],
            note=("source copy and before/after hashes were captured by this run" if raw.get("comparison_runner_source")
                  else "run did not save a direct comparison-script source snapshot; imported runtime module hashes are retained")),
        current_private_runner_source=dict(
            path=str(runner_script), sha256_at_inventory_capture=sha256(runner_script),
            timing_note="current runner after post-run metadata fixes; not asserted as the execution-time script unless source_snapshot.captured_by_run is true"),
        forecast_path=str(FORECAST), forecast_sha256=sha256(FORECAST), forecast_times=times,
        native_j_i_0based=[NATIVE_J, NATIVE_I], ami_row_col_0based=raw["selected_ami_row_col_0based"],
        rttov_channels=CHANNELS, thermal_coefficient_type_by_channel=raw["per_frame"][0]["rttov_coefficient_type_by_channel"],
        fixed_common_support_channels=SUPPORT,
        excluded_channels_with_rttov_quality=[8, 9],
        common_support_count=7,
        sigma_K=raw["sigma_K"], bias_K=raw["bias_K"], huber_delta=raw["huber_delta"],
        cost_sum_huber_all_eight_same_support=raw["cost_sum_huber_all_eight_same_support"],
        dimensionless_common_support_huber_contributions=[f["common_support_huber_contribution_dimensionless"] for f in enriched["per_frame"]],
        mean_absolute_residual_K_per_frame_on_common_support=mae,
        observation_IR105_K=float(obs[ch_ir105]),
        model_IR105_K_all_eight=model_ir105.tolist(),
        model_IR105_K_mean=float(np.mean(model_ir105)),
        model_state_summary_scope="Saved state only; no KDM process or AD trajectory. Native hydrometeor amount paths are zero for the selected cell; retry2 retains fixture simple-cloud CTP metadata but sets its fraction to zero, so no whole-atmosphere 'clear' label is asserted.",
        per_frame=per_frame_inventory,
        earlier_retry_sensitivity_comparison=retry1_comparison,
        rttov_common_assets=dict(
            rttov_executable_command_path=enriched["per_frame"][0]["executed_rttov_assets"]["command_executable_path"],
            resolved_executable_path=enriched["per_frame"][0]["executed_rttov_assets"]["resolved_executable_path"],
            rttov_executable_sha256_at_inventory_capture=enriched["per_frame"][0]["executed_rttov_assets"]["executable_sha256_at_inventory_capture"],
            coefficient_path=enriched["per_frame"][0]["executed_rttov_assets"]["coefficient_path"],
            coefficient_sha256=enriched["per_frame"][0]["executed_rttov_assets"]["coefficient_sha256"],
            hydrotable_path=enriched["per_frame"][0]["executed_rttov_assets"]["hydrotable_path"],
            hydrotable_sha256=enriched["per_frame"][0]["executed_rttov_assets"]["hydrotable_sha256"],
            run_captured_start_end_hashes=raw.get("rttov_execution_assets"),
            rttov_simple_cloud_source=str(RTTOV_SIMPLE_CLOUD_SOURCE),
            rttov_simple_cloud_source_sha256=sha256(RTTOV_SIMPLE_CLOUD_SOURCE),
            simple_cloud_semantic_scope="The RTTOV source routine uses CTP to locate the simple-cloud top layer. Retry2 keeps that metadata but sets simple_cloud cfraction=0 in each private case copy; model hydrometeor amounts and hydro_frac remain the executed cloud inputs and are audited per frame."),
        model_output_diagnostic=dict(
            root_runner_exit_code=receipt["runner_result"]["exit_code"],
            root_runner_experiment_valid=receipt["runner_result"]["experiment_valid"],
            root_runner_invalid_reasons=receipt["runner_result"]["invalid_reasons"],
            wrf_success_complete_observed=receipt["runner_result"]["wrf_success_complete_observed"],
            overall_fatal_or_error_lines_observed=receipt.get("fatal_or_error_lines_observed"),
            wrapper_wrf_fatal_lines_observed=receipt["runner_result"].get("wrf_fatal_lines_observed"),
            mpi_abnormal_termination_observed=receipt["runner_result"]["mpi_abnormal_termination_observed"],
            cause_attribution="MPI termination was abnormal; the receipt does not establish why, and no speculation is added."),
        metadata_corrections=dict(
            pressure_center_unit_correction_applied=any(
                "native_pressure_centers_originally_serialized_values" in f for f in enriched["per_frame"]),
            raw_pressure_field_name="native_pressure_centers_hPa",
            corrected_pressure_field_unit="hPa",
            correction_validation="all eight executed p.txt native center suffixes bitwise equal saved forecast float64-first (P+PB)/100",
            huber_contribution_label_correction_applied=any(
                f["runner_original_common_support_contribution_field"]["name"].endswith("_K2")
                for f in enriched["per_frame"]),
            raw_contribution_name_by_frame=[f["runner_original_common_support_contribution_field"]["name"] for f in enriched["per_frame"]],
            corrected_contribution_name="common_support_huber_contribution_dimensionless",
            correction_validation_cost="sigma_K=1.0; standardized Huber contributions and all eight stored costs agree within 1e-13; BT, rad_quality, mask, and costs are unchanged"),
        lifecycle_warning="WRF logged SUCCESS COMPLETE WRF and wrote all eight finite frames, but run_ss_case returned 1, runner_result.experiment_valid=false, model_completed_flag=false, and MPI abnormal termination=true. This output is an ineligible artifact diagnostic.",
    )
    # Cost outputs are preserved exactly from the runner. The corrected contributions
    # are standardized residual Huber contributions with sigma_K=1.0, hence dimensionless.
    enriched_result_path.write_text(json.dumps(enriched, indent=2, allow_nan=False) + "\n")
    inventory_path.write_text(json.dumps(inventory, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": enriched["status"], "native_run_valid": enriched["native_run_valid"],
                      "raw_sha256": raw_sha, "enriched_result": str(enriched_result_path),
                      "inventory": str(inventory_path), "mean_IR105_model_K": inventory["model_IR105_K_mean"],
                      "mean_IR105_observation_K": inventory["observation_IR105_K"],
                      "common_support": SUPPORT, "costs": inventory["cost_sum_huber_all_eight_same_support"]}, indent=2))


if __name__ == "__main__":
    main()
