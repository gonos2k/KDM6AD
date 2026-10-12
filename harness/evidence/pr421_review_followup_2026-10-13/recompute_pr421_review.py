#!/usr/bin/env python3
"""Recompute public PR421 review numbers without running model code."""
from __future__ import annotations

import csv
from datetime import datetime
import hashlib
import json
import math
import re
from pathlib import Path
from zoneinfo import ZoneInfo


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PR420 = ROOT / "harness/evidence/pr420_nine_channel_analysis_2026-10-13"
PRIVATE = Path("/Users/yhlee/KDM6AD-k/host/research_evidence/pr420_nine_channel_20261013/DOM_ANALYSIS_PAIR_ONCE_01")
CHANNELS_CSV = PR420 / "CHANNELS.csv"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def read_flag(nml: str, name: str) -> bool:
    match = re.search(rf"(?im)^\s*defn%opts%[^\n]*%{re.escape(name)}\s*=\s*([^!\n]+)", nml)
    if match is None:
        raise ValueError(f"missing setting {name}")
    value = match.group(1).strip().rstrip(",").upper()
    if value not in {".TRUE.", ".FALSE."}:
        raise ValueError(f"{name} is not a logical: {value}")
    return value == ".TRUE."


def read_scalar(nml: str, group: str, name: str) -> float:
    match = re.search(
        rf"(?im)^\s*defn%opts%{re.escape(group)}%{re.escape(name)}\s*=\s*([^!\n]+)", nml)
    if match is None:
        raise ValueError(f"missing setting {group}.{name}")
    return float(match.group(1).strip().rstrip(","))


def read_channels(path: Path) -> list[int]:
    return [int(x) for x in path.read_text().split()]


def huber(residual: float, delta: float = 1.0, sigma: float = 1.0) -> float:
    x = abs(residual / sigma)
    return 0.5 * x * x if x <= delta else delta * (x - 0.5 * delta)


def inspect_cases() -> dict:
    captures = {label: load_json(PR420 / f"{label}_CAPTURE.json") for label in ("DOM7", "DOM9")}
    plan = load_json(PR420 / "ANALYSIS_PLAN.json")
    if plan["thermal_solver"] != 1 or plan["channel_removal_or_warning_waiver"]:
        raise ValueError("PR420 plan does not pin the expected DOM1/no-waiver variant")
    expected_channels = {"DOM7": list(range(10, 17)), "DOM9": list(range(8, 17))}
    cases_by_run = {}
    for label, channels in expected_channels.items():
        case_paths = sorted((PRIVATE / label / "h_cases").glob("*/*/case"))
        if len(case_paths) != 6:
            raise ValueError(f"expected 6 retained H cases for {label}, got {len(case_paths)}")
        if captures[label]["actual_h_configuration"]["channels"] != channels:
            raise ValueError(f"public capture {label} channel list mismatch")
        if captures[label]["effective_h_configuration"]["channels"] != channels:
            raise ValueError(f"effective H {label} channel list mismatch")
        call_entries = []
        for case in case_paths:
            channels_path = case / "in/channels.txt"
            nml_path = case / "out/rttov_test.txt"
            channels_found = read_channels(channels_path)
            nml_text = nml_path.read_text()
            thermal = int(read_scalar(nml_text, "scatt", "thermal_solver"))
            streams = int(read_scalar(nml_text, "scatt", "dom_nstreams"))
            accuracy = read_scalar(nml_text, "scatt", "dom_accuracy")
            opdep = read_scalar(nml_text, "scatt", "dom_opdep_threshold")
            flags = {
                "solar": read_flag(nml_text, "solar"),
                "plane_parallel": read_flag(nml_text, "plane_parallel"),
                "lambertian": read_flag(nml_text, "lambertian"),
                "lambertian_fixed_angle": read_flag(nml_text, "lambertian_fixed_angle"),
            }
            if channels_found != channels or thermal != 1 or streams != 8 or accuracy != 0.0 or opdep != 0.0:
                raise ValueError(f"unexpected DOM settings in retained case {case}")
            if flags != {"solar": False, "plane_parallel": False,
                         "lambertian": False, "lambertian_fixed_angle": True}:
                raise ValueError(f"unexpected geometry/surface flags in retained case {case}: {flags}")
            call_entries.append({
                "call": case.parent.parent.name,
                "case_path": str(case),
                "channels": channels_found,
                "rttov_test_txt_sha256": sha256(nml_path),
                "channels_txt_sha256": sha256(channels_path),
                "run_sh_sha256": sha256(case / "out/run.sh"),
                "env_sh_sha256": sha256(case / "out/env.sh"),
                "coef_txt_sha256": sha256(case / "in/coef.txt"),
                "configured": {
                    "thermal_solver": thermal,
                    "dom_nstreams": streams,
                    "dom_accuracy": accuracy,
                    "dom_opdep_threshold": opdep,
                    **flags,
                },
            })
        cases_by_run[label] = call_entries

    guide = Path("/Users/yhlee/AD-RTTOV/external/rttov14/src/docs/users_guide_rttov14_v1.1.pdf")
    return {
        "analysis_plan_path": str(PR420 / "ANALYSIS_PLAN.json"),
        "analysis_plan_sha256": sha256(PR420 / "ANALYSIS_PLAN.json"),
        "public_capture_sha256": {
            label: sha256(PR420 / f"{label}_CAPTURE.json") for label in expected_channels
        },
        "captured_case_count": sum(len(x) for x in cases_by_run.values()),
        "runs": cases_by_run,
        "static_prepared_fixture_rttov_test_sha256": {
            label: sha256(Path(captures[label]["actual_h_configuration"]["fixture_case_dir"]) / "out/rttov_test.txt")
            for label in expected_channels
        },
        "declared_plan_solver": plan["thermal_solver"],
        "guide": {
            "title": "RTTOV v14 Users' Guide",
            "document_id": "NWPSAF-MO-UD-055",
            "version": "1.1.1",
            "date": "2026-01-21",
            "local_pdf_path": str(guide),
            "local_pdf_sha256": sha256(guide),
            "official_url": "https://nwp-saf.eumetsat.int/site/download/documentation/rtm/docs_rttov14/users_guide_rttov14_v1.1.pdf",
            "support": [
                "Section 8.4.2, Table 8.11, p.73: thermal_solver_dom is integer 1; delta-Eddington is integer 3 and default.",
                "Section 8.4.2, p.73: DOM requires strict plane-parallel atmospheric geometry and RTTOV applies it automatically even when the configured plane_parallel flag is false.",
                "Section 8.4.2, p.73: DOM treats the surface as Lambertian independently of the lambertian option and does not use the specularity parameter.",
                "Section 8.4.2, p.73: DOM streams default to 8; dom_opdep_threshold 0 excludes no layers. dom_accuracy 0 is the default with no truncation; its described azimuthal-loop criterion is for solar radiation, disabled in this thermal-only run.",
            ],
        },
        "configured_vs_documented_effective_behavior": {
            "configured_namelist": {
                "plane_parallel": False,
                "lambertian": False,
                "lambertian_fixed_angle": True,
                "solar": False,
                "thermal_solver": 1,
                "dom_nstreams": 8,
                "dom_accuracy": 0.0,
                "dom_opdep_threshold": 0.0,
            },
            "documented_DOM_behavior": {
                "strict_plane_parallel": "applied automatically by RTTOV whenever DOM is selected, independent of the configured false flag",
                "surface_reflection": "Lambertian under DOM, independent of the configured false lambertian option; specularity is not used",
                "runtime_flags_instrumented": False,
            },
            "interpretation": "The namelist booleans are preserved as configured inputs; RTTOV's documented DOM behavior supplies the effective plane-parallel/Lambertian treatment. Do not describe false namelist values as proof that DOM ran spherical geometry or a non-Lambertian surface.",
        },
    }


def recompute_numeric() -> dict:
    captures = {label: load_json(PR420 / f"{label}_CAPTURE.json") for label in ("DOM7", "DOM9")}
    direction = load_json(PR420 / "DIRECTION_RESULT.json")
    direction_plan = load_json(PR420 / "DIRECTION_PLAN.json")
    with (PR420 / "CHANNELS.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    row_by_id = {int(row["ami_channel_id_1based"]): row for row in rows}
    if sorted(row_by_id) != list(range(8, 17)):
        raise ValueError("channel CSV does not contain exact physical channel IDs 8..16")

    # Recompute channel costs from public O-B/O-A residuals and Huber arithmetic.
    for channel, row in row_by_id.items():
        for prefix in ("dom1_7", "dom1_9"):
            if channel < 10 and prefix == "dom1_7":
                continue
            for suffix, residual_key, cost_key in (
                ("initial", f"{prefix}_O_minus_B_K", f"{prefix}_initial_huber_cost"),
                ("final", f"{prefix}_O_minus_A_K", f"{prefix}_final_huber_cost"),
            ):
                if not math.isclose(huber(float(row[residual_key])), float(row[cost_key]), rel_tol=0.0, abs_tol=1e-12):
                    raise ValueError(f"Huber recomputation mismatch channel {channel} {prefix} {suffix}")

    common_ids = list(range(10, 17))
    extra_ids = [8, 9]
    cost = {}
    for label, prefix in (("DOM7", "dom1_7"), ("DOM9", "dom1_9")):
        run_rows = [row_by_id[ch] for ch in (common_ids if label == "DOM7" else range(8, 17))]
        initial_jo = sum(float(r[f"{prefix}_initial_huber_cost"]) for r in run_rows)
        final_jo = sum(float(r[f"{prefix}_final_huber_cost"]) for r in run_rows)
        cap = captures[label]
        objective = cap["objective"]
        if not math.isclose(initial_jo, objective["initial_zero_control_closure"]["Jo"], abs_tol=1e-9):
            raise ValueError(f"{label} channel-cost sum does not match initial Jo")
        if not math.isclose(final_jo, objective["Jo"], abs_tol=1e-9):
            raise ValueError(f"{label} channel-cost sum does not match final Jo")
        cost[label] = {
            "initial_zero_control_Jo_recomputed": initial_jo,
            "final_Jo_recomputed": final_jo,
            "final_Jb_state": float(objective["Jb_state"]),
            "final_Jtheta": float(objective["Jtheta"]),
            "final_Jtotal_capture": float(objective["Jtotal"]),
        }

    common_initial_dom7 = sum(float(row_by_id[ch]["dom1_7_initial_huber_cost"]) for ch in common_ids)
    common_initial_dom9 = sum(float(row_by_id[ch]["dom1_9_initial_huber_cost"]) for ch in common_ids)
    common_final_dom7 = sum(float(row_by_id[ch]["dom1_7_final_huber_cost"]) for ch in common_ids)
    common_final_dom9 = sum(float(row_by_id[ch]["dom1_9_final_huber_cost"]) for ch in common_ids)
    extra_initial = sum(float(row_by_id[ch]["dom1_9_initial_huber_cost"]) for ch in extra_ids)
    extra_final = sum(float(row_by_id[ch]["dom1_9_final_huber_cost"]) for ch in extra_ids)
    extra_gain = extra_initial - extra_final
    total_dom9_gain = cost["DOM9"]["initial_zero_control_Jo_recomputed"] - cost["DOM9"]["final_Jo_recomputed"]
    common_dom9_gain = common_initial_dom9 - common_final_dom9

    plus = direction["results"]["plus"]
    minus = direction["results"]["minus"]
    step = float(direction_plan["step_control_units"])
    fd_recomputed = (float(plus["Jtotal"]) - float(minus["Jtotal"])) / (2.0 * step)
    ad = float(direction["directional_AD"])
    grad_norm = float(captures["DOM9"]["final_control_gradient"]["combined_l2_norm"])
    returned_total = float(captures["DOM9"]["objective"]["Jtotal"])
    prior_gradient_norm = math.sqrt(2.0 * cost["DOM9"]["final_Jb_state"])
    if not math.isclose(fd_recomputed, float(direction["directional_FD"]), rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("DIRECTION_RESULT central FD does not match public plus/minus costs")
    return {
        "schema": "pr421_public_numeric_recompute_v1",
        "inputs": {
            "DOM7_CAPTURE_sha256": sha256(PR420 / "DOM7_CAPTURE.json"),
            "DOM9_CAPTURE_sha256": sha256(PR420 / "DOM9_CAPTURE.json"),
            "CHANNELS_csv_sha256": sha256(CHANNELS_CSV),
            "DIRECTION_RESULT_sha256": sha256(PR420 / "DIRECTION_RESULT.json"),
            "DIRECTION_PLAN_sha256": sha256(PR420 / "DIRECTION_PLAN.json"),
            "no_private_checkpoint_values_used": True,
        },
        "common_7_cost_plus_prior": {
            "initial_common7_Jo_DOM7": common_initial_dom7,
            "initial_common7_Jo_DOM9": common_initial_dom9,
            "initial_common7_equal": math.isclose(common_initial_dom7, common_initial_dom9, abs_tol=1e-12),
            "final_common7_Jo_DOM7": common_final_dom7,
            "final_common7_Jo_DOM9": common_final_dom9,
            "final_common7_observation_cost_delta_DOM9_minus_DOM7": common_final_dom9 - common_final_dom7,
            "final_common7_plus_prior_DOM7": common_final_dom7 + cost["DOM7"]["final_Jb_state"] + cost["DOM7"]["final_Jtheta"],
            "final_common7_plus_prior_DOM9": common_final_dom9 + cost["DOM9"]["final_Jb_state"] + cost["DOM9"]["final_Jtheta"],
            "final_common7_plus_prior_delta_DOM9_minus_DOM7": (
                common_final_dom9 + cost["DOM9"]["final_Jb_state"] + cost["DOM9"]["final_Jtheta"]
                - common_final_dom7 - cost["DOM7"]["final_Jb_state"] - cost["DOM7"]["final_Jtheta"]),
            "full_objective_prior_terms": {label: {"Jb_state": row["final_Jb_state"], "Jtheta": row["final_Jtheta"]} for label,row in cost.items()},
        },
        "added_channel_8_9_loss_gain": {
            "initial_added2_Jo": extra_initial,
            "final_added2_Jo": extra_final,
            "added2_gain": extra_gain,
            "added2_fractional_reduction": extra_gain / extra_initial,
            "DOM9_total_Jo_gain": total_dom9_gain,
            "DOM9_common7_gain": common_dom9_gain,
            "added2_gain_share_of_total_DOM9_Jo_gain": extra_gain / total_dom9_gain,
            "common7_gain_share_of_total_DOM9_Jo_gain": common_dom9_gain / total_dom9_gain,
            "added2_initial_share_of_DOM9_initial_Jo": extra_initial / cost["DOM9"]["initial_zero_control_Jo_recomputed"],
            "added2_final_share_of_DOM9_final_Jo": extra_final / cost["DOM9"]["final_Jo_recomputed"],
            "per_channel": {
                str(ch): {
                    "name": row_by_id[ch]["channel_name"],
                    "O_minus_B_K": float(row_by_id[ch]["dom1_9_O_minus_B_K"]),
                    "O_minus_A_K": float(row_by_id[ch]["dom1_9_O_minus_A_K"]),
                    "initial_huber_cost": float(row_by_id[ch]["dom1_9_initial_huber_cost"]),
                    "final_huber_cost": float(row_by_id[ch]["dom1_9_final_huber_cost"]),
                    "huber_gain": float(row_by_id[ch]["dom1_9_initial_huber_cost"]) - float(row_by_id[ch]["dom1_9_final_huber_cost"]),
                } for ch in extra_ids
            },
            "scope": "per-channel Huber arithmetic at the captured 9-channel point; raw whole-vector Jo across N is not a performance comparison",
        },
        "directional_minus_point_and_norm_ratio": {
            "lower_minus_point_Jo": float(minus["Jo"]),
            "lower_minus_point_Jb": float(minus["Jb"]),
            "lower_minus_point_Jtotal": float(minus["Jtotal"]),
            "captured_returned_point_Jtotal": returned_total,
            "returned_minus_lower_point_Jtotal": returned_total - float(minus["Jtotal"]),
            "plus_point_Jtotal": float(plus["Jtotal"]),
            "step_control_units": step,
            "central_FD_recomputed_from_public_endpoints": fd_recomputed,
            "AD_directional": ad,
            "captured_full_gradient_L2": grad_norm,
            "prior_gradient_L2_from_half_squared_control_norm": prior_gradient_norm,
            "full_gradient_over_prior_gradient_L2_ratio": grad_norm / prior_gradient_norm,
            "FD_over_AD_ratio": fd_recomputed / ad,
            "FD_over_full_gradient_L2_norm_ratio": fd_recomputed / grad_norm,
            "absolute_error": abs(fd_recomputed - ad),
            "relative_error_vs_AD": abs(fd_recomputed - ad) / max(abs(ad), 1e-30),
            "plus_minus_quality_all_zero": all(
                value == 0.0 for side in (plus, minus) for row in side["quality"] for value in row),
        },
    }


def main() -> None:
    settings = inspect_cases()
    numeric = recompute_numeric()
    settings["created_at_kst"] = datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    numeric["created_at_kst"] = settings["created_at_kst"]
    settings_path = HERE / "DOM_EFFECTIVE_SETTINGS.json"
    numeric_path = HERE / "NUMERIC_REVIEW.json"
    settings_path.write_text(json.dumps(settings, indent=2, allow_nan=False) + "\n")
    numeric_path.write_text(json.dumps(numeric, indent=2, allow_nan=False) + "\n")
    print(json.dumps({
        "settings": str(settings_path),
        "numeric": str(numeric_path),
        "case_count": settings["captured_case_count"],
        "final_common7_plus_prior_delta": numeric["common_7_cost_plus_prior"]["final_common7_plus_prior_delta_DOM9_minus_DOM7"],
        "added2_gain_share": numeric["added_channel_8_9_loss_gain"]["added2_gain_share_of_total_DOM9_Jo_gain"],
        "minuspoint_Jtotal": numeric["directional_minus_point_and_norm_ratio"]["lower_minus_point_Jtotal"],
    }, indent=2))


if __name__ == "__main__":
    main()
