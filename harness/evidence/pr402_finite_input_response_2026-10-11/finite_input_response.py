#!/usr/bin/env python3
"""Prepare, then optionally execute, four bounded PR402 finite-input trials.

Default mode is preflight only. Execution is a separate one-shot stage requiring
the frozen plan hash and a unique execution ID. The driver reuses the PR401
center baseline and production RTTOV parser/coordinate transform.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "oracle"))

PACKET = ROOT / "harness/evidence/pr402_finite_input_response_2026-10-11"
PR399_RESULT = ROOT / "harness/evidence/pr399_vertical_neighbor_2026-10-10/NEIGHBOR_RESULT_attempt2.json"
PR399_PLAN = ROOT / "harness/evidence/pr399_vertical_neighbor_2026-10-10/NEIGHBOR_PLAN_attempt2.json"
PR401_RESULT = ROOT / "harness/evidence/pr401_fixed_input_k_response_2026-10-10/final_v2/K_RESPONSE.json"
PR401_NPZ = Path("/Users/yhlee/KDM6AD-k/host/research_evidence/pr401_fixed_input_k_response_20261010/center_86_48_rttov_k_response_v2.npz")
PRIVATE_ROOT = Path("/Users/yhlee/KDM6AD-k/host/research_evidence/pr402_finite_input_response_20261011")
RUNNER_SOURCE = ROOT / "oracle/kdm6/obs/rttov_runner.py"
EXECUTOR_SOURCE = PACKET / "execute_finite_response.py"
CHANNEL_IDS = tuple(range(10, 17))
STATIC_OUT_FILES = ("run.sh", "env.sh", "rttov_test.txt")
TRIALS = (
    "skin_minus_0p5K", "skin_plus_0p5K",
    "o3_source_minus_1pct", "o3_source_plus_1pct",
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def parse_assignments(text: str) -> dict[str, str]:
    ret = {}
    for line in text.splitlines():
        match = re.match(r"\s*([\w%()]+)\s*=\s*([^!]+?)\s*$", line)
        if match:
            ret[match.group(1).casefold()] = match.group(2).strip().rstrip(",")
    return ret


def read_skin_temperature(text: str) -> float:
    pattern = re.compile(
        r"(?im)^\s*k0%t\s*=\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?)\s*$"
    )
    hits = pattern.findall(text)
    if len(hits) != 1:
        raise ValueError(f"skin.txt must contain exactly one k0%t assignment, got {len(hits)}")
    return float(hits[0].replace("D", "E").replace("d", "e"))


def replace_skin_temperature(text: str, value_k: float) -> str:
    if not np.isfinite(value_k):
        raise ValueError("skin temperature must be finite")
    pattern = re.compile(
        r"(?im)^(?P<prefix>\s*k0%t\s*=\s*)(?P<value>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?)(?P<suffix>\s*)$"
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise ValueError(f"skin.txt must contain exactly one k0%t assignment, got {len(matches)}")
    return pattern.sub(lambda m: f"{m.group('prefix')}{value_k:.6f}{m.group('suffix')}", text, count=1)


def write_vector(path: Path, values: np.ndarray) -> None:
    values = np.asarray(values, dtype=np.float64).reshape(-1)
    if not np.isfinite(values).all():
        raise ValueError(f"non-finite input vector: {path}")
    path.write_text("".join(f"{value:.17E}\n" for value in values))


def file_inventory(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256(path)
        for path in sorted(root.rglob("*")) if path.is_file()
    }


def compare_inventory(base: dict[str, str], trial: dict[str, str], expected_changed: str) -> dict:
    if set(base) != set(trial):
        raise ValueError("trial input file set differs from the preserved center")
    changed = sorted(name for name in base if base[name] != trial[name])
    if changed != [expected_changed]:
        raise ValueError(f"expected only {expected_changed} to change, got {changed}")
    return {"changed_files": changed,
            "unchanged_file_count": len(base) - 1,
            "baseline_changed_file_sha256": base[expected_changed],
            "trial_changed_file_sha256": trial[expected_changed]}


def library_manifest(executable: Path) -> dict:
    proc = subprocess.run(["otool", "-L", str(executable)], check=True,
                          capture_output=True, text=True)
    libraries = []
    for line in proc.stdout.splitlines()[1:]:
        raw = line.strip().split(" (", 1)[0]
        if not raw:
            continue
        path = Path(raw)
        resolved = path.resolve(strict=False)
        row = {"install_name": raw, "resolved_path": str(resolved), "sha256": None}
        if resolved.is_file():
            try:
                row["sha256"] = sha256(resolved)
                row["hash_status"] = "HASHED_FILE"
            except OSError as exc:
                row["hash_status"] = f"UNREADABLE:{type(exc).__name__}"
        else:
            row["hash_status"] = "UNAVAILABLE_SYSTEM_OR_SHARED_CACHE"
        libraries.append(row)
    return {"otool_stdout": proc.stdout, "libraries": libraries}


def runtime_assets(center_case: Path, result: dict, plan: dict) -> dict:
    out = center_case / "out"
    run_script = out / "run.sh"
    run_text = run_script.read_text()
    exe_match = re.search(r"^\s*(/[^\s>]+)\s*>", run_text, re.M)
    if exe_match is None:
        raise ValueError("saved run.sh has no absolute RTTOV executable redirection line")
    exe_path = Path(exe_match.group(1)).resolve()
    nml = parse_assignments((out / "rttov_test.txt").read_text())
    coef_prefix = Path(nml.get("defn%coef_prefix", "").strip("'\""))
    if not coef_prefix.is_absolute():
        raise ValueError("saved coefficient prefix is not absolute")
    coef_fields = parse_assignments((center_case / "in/coef.txt").read_text())
    coef_rel = Path(coef_fields["defn%f_coef"].strip("'\""))
    hydro_rel = Path(coef_fields["defn%f_hydrotable"].strip("'\""))
    coef_path = (coef_prefix / coef_rel).resolve()
    hydro_path = (coef_prefix / hydro_rel).resolve()
    expected_coef = result["rttov_assets"]["coefficient_sha256"]
    expected_exe = result["rttov_assets"]["executable_sha256"]
    require(sha256(coef_path) == expected_coef, "resolved coef.txt coefficient differs from PR399 hash")
    require(sha256(exe_path) == expected_exe, "run.sh executable differs from PR399 hash")
    return {
        "run_script_path": str(run_script),
        "run_script_sha256": sha256(run_script),
        "env_sh_path": str(out / "env.sh"),
        "env_sh_sha256": sha256(out / "env.sh"),
        "rttov_test_namelist_path": str(out / "rttov_test.txt"),
        "rttov_test_namelist_sha256": sha256(out / "rttov_test.txt"),
        "run_script_executable_literal": exe_match.group(1),
        "rttov_executable_resolved_path": str(exe_path),
        "rttov_executable_sha256": sha256(exe_path),
        "coef_prefix_literal": str(coef_prefix),
        "coef_prefix_resolved": str(coef_prefix.resolve()),
        "coefficient_relative_path": str(coef_rel),
        "coefficient_resolved_path": str(coef_path),
        "coefficient_sha256": sha256(coef_path),
        "hydrotable_relative_path": str(hydro_rel),
        "hydrotable_resolved_path": str(hydro_path),
        "hydrotable_sha256": sha256(hydro_path),
        "library_manifest": library_manifest(exe_path),
    }


def resolve_trial_assets(runtime: dict) -> dict:
    exe = Path(runtime["rttov_executable_resolved_path"])
    current = {
        "rttov_executable_sha256": sha256(exe),
        "coefficient_sha256": sha256(Path(runtime["coefficient_resolved_path"])),
        "hydrotable_sha256": sha256(Path(runtime["hydrotable_resolved_path"])),
        "library_manifest": library_manifest(exe),
    }
    return current


def create_trial_case(center_case: Path, target: Path, trial_name: str,
                      skin_delta: float | None, o3_trial: np.ndarray | None,
                      center_skin_text: str, center_skin_t: float) -> dict:
    if target.exists():
        raise FileExistsError(f"trial case already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    shutil.copytree(center_case / "in", target / "in", symlinks=False)
    out = target / "out"
    out.mkdir(mode=0o700)
    for name in STATIC_OUT_FILES:
        shutil.copy2(center_case / "out" / name, out / name)
    (out / "k").mkdir(mode=0o700)
    (out / "direct").mkdir(mode=0o700)
    for path in target.rglob("*"):
        if path.is_dir():
            os.chmod(path, 0o700)
        elif path.is_file():
            os.chmod(path, 0o600)

    expected_changed = None
    actual_perturbation = None
    if skin_delta is not None:
        expected_changed = "profiles/001/sfc/01/skin.txt"
        trial_skin = center_skin_t + skin_delta
        skin_path = out / "../in/profiles/001/sfc/01/skin.txt"
        center_text = center_skin_text
        skin_path.write_text(replace_skin_temperature(center_text, trial_skin))
        actual_perturbation = read_skin_temperature(skin_path.read_text()) - center_skin_t
        if actual_perturbation == 0.0:
            raise ValueError(f"skin direction {trial_name} is lost in six-decimal serialization")
    else:
        expected_changed = "profiles/001/atm/o3.txt"
        if o3_trial is None:
            raise ValueError(f"O3 trial {trial_name} lacks a profile vector")
        o3_path = out / "../in/profiles/001/atm/o3.txt"
        write_vector(o3_path, o3_trial)
        actual_perturbation = (np.loadtxt(o3_path, dtype=np.float64)
                               - np.loadtxt(center_case / "in/profiles/001/atm/o3.txt", dtype=np.float64))

    center_inputs = file_inventory(center_case / "in")
    trial_inputs = file_inventory(target / "in")
    # Convert from case-relative expected paths to in-tree paths for exact inventory comparison.
    expected_in_tree = expected_changed.replace("profiles/", "profiles/")
    diff = compare_inventory(center_inputs, trial_inputs, expected_in_tree)
    empty_outputs = {
        "k": sorted(p.name for p in (out / "k").iterdir()),
        "direct": sorted(p.name for p in (out / "direct").iterdir()),
    }
    if any(empty_outputs.values()):
        raise ValueError(f"trial copied saved RTTOV outputs: {empty_outputs}")
    out_files = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    if out_files != sorted(STATIC_OUT_FILES):
        raise ValueError(f"trial output directory contains non-launch files: {out_files}")
    return {
        "trial_name": trial_name,
        "trial_case_path": str(target),
        "runner_path": str(out / "run.sh"),
        "wrapper_calls_planned": 1,
        "expected_input_file_change": expected_changed,
        "input_diff": diff,
        "input_file_count": len(center_inputs),
        "input_sha256": trial_inputs,
        "input_o3_actual_delta_min_max": (
            [float(np.min(actual_perturbation)), float(np.max(actual_perturbation))]
            if isinstance(actual_perturbation, np.ndarray) else None
        ),
        "input_scalar_actual_delta": (
            float(actual_perturbation) if np.isscalar(actual_perturbation) else None
        ),
        "out_static_files": {
            name: sha256(out / name) for name in STATIC_OUT_FILES
        },
        "empty_output_directories": empty_outputs,
        "out_directory_file_list": out_files,
    }


def prepare_plan(output_dir: Path, plan_id: str | None = None) -> dict:
    require(EXECUTOR_SOURCE.is_file(),
            f"final preflight requires the root one-shot executor source: {EXECUTOR_SOURCE}")
    result = json.loads(PR399_RESULT.read_text())
    plan = json.loads(PR399_PLAN.read_text())
    pr401 = json.loads(PR401_RESULT.read_text())
    runner_source = RUNNER_SOURCE.read_text()
    fence = '{"OMP_NUM_THREADS": "1", "OMP_DYNAMIC": "FALSE", "OMP_THREAD_LIMIT": "1"}'
    require(fence in runner_source, "production run_rttov_k OMP thread fence changed")
    require(result.get("status") == "ALL_NINE_ROWS_RETURNED", "PR399 center result is incomplete")
    center_rows = [r for r in result["results"] if int(r["j"]) == 86 and int(r["i"]) == 48]
    require(len(center_rows) == 1, "PR399 result does not identify exactly one center")
    center = center_rows[0]
    center_case = Path(center["case_output_dir"]).resolve()
    require(center_case.is_dir(), f"preserved center case is missing: {center_case}")
    require(center["case_role"] == "REUSED_PR398_V2_CENTRAL_H", "center role changed")
    require(center["channels_1based"] == list(CHANNEL_IDS), "center channel order changed")
    require(center["all_seven_rad_quality_zero"], "center baseline quality gate failed")
    require(not center["automatic_retry"], "center baseline contains automatic retry")
    require(pr401["scope"]["center_cell_j_i"] == [86, 48], "PR401 baseline is not the center")
    require(pr401["run_contract"]["prior_bt_abs_max_diff_k"] == 0.0,
            "PR401 center baseline does not exactly replay prior BT")
    private_npz = Path(pr401["private_npz"]["path"])
    require(sha256(private_npz) == pr401["private_npz"]["sha256"],
            "PR401 canonical response NPZ hash mismatch")

    with np.load(private_npz, allow_pickle=False) as z:
        kma = {name: z[name].copy() for name in z.files}
    p_matrix = np.asarray(kma["log_pressure_interpolation_matrix"], dtype=np.float64)
    source_o3 = np.asarray(kma["reference_o3_ppmv_moist"], dtype=np.float64)
    center_o3 = np.asarray(kma["active_o3_ppmv_moist"], dtype=np.float64)
    if p_matrix.shape != (66, 69) or source_o3.shape != (69,) or center_o3.shape != (66,):
        raise ValueError("PR401 center P/O3 dimensions do not match 66x69 contract")
    o3_beta = 0.01 * source_o3
    o3_delta = p_matrix @ o3_beta
    require(np.allclose(p_matrix @ source_o3, center_o3, rtol=0.0, atol=2e-13),
            "PR401 center P/reference O3 does not reproduce active input")

    center_skin_path = center_case / "in/profiles/001/sfc/01/skin.txt"
    center_skin_text = center_skin_path.read_text()
    center_skin_t = read_skin_temperature(center_skin_text)
    assets_before = runtime_assets(center_case, center, plan)
    if assets_before["coefficient_sha256"] != pr401["provenance"]["coefficient_sha256"]:
        raise ValueError("resolved center coefficient differs from PR401 baseline")
    baseline_inventory = {
        "center_input_files": file_inventory(center_case / "in"),
        "center_static_out_files": {
            name: sha256(center_case / "out" / name) for name in STATIC_OUT_FILES
        },
        "center_saved_k_outputs": {
            "radiance_k_sha256": sha256(center_case / "out/k/radiance.txt"),
            "profiles_k_sha256": sha256(center_case / "out/k/profiles_k.txt"),
        },
    }
    original_case_records_before = {
        name: sha256(center_case / "out" / name) for name in STATIC_OUT_FILES
    } | {
        "out/k/radiance.txt": baseline_inventory["center_saved_k_outputs"]["radiance_k_sha256"],
        "out/k/profiles_k.txt": baseline_inventory["center_saved_k_outputs"]["profiles_k_sha256"],
    }

    set_id = plan_id or uuid.uuid4().hex[:12]
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,40}", set_id):
        raise ValueError("plan_id must be 8-40 safe alphanumeric/dash/underscore characters")
    private_set = PRIVATE_ROOT / "cases" / set_id
    if private_set.exists():
        raise FileExistsError(f"PR402 trial set already exists: {private_set}")
    private_set.mkdir(parents=True, exist_ok=False, mode=0o700)
    os.chmod(PRIVATE_ROOT, 0o700)
    os.chmod(private_set.parent, 0o700)
    os.chmod(private_set, 0o700)

    trial_specs = [
        ("skin_minus_0p5K", -0.5, None),
        ("skin_plus_0p5K", +0.5, None),
        ("o3_source_minus_1pct", None, center_o3 - o3_delta),
        ("o3_source_plus_1pct", None, center_o3 + o3_delta),
    ]
    trial_records = []
    for trial_name, skin_delta, o3_trial in trial_specs:
        trial_records.append(create_trial_case(
            center_case, private_set / trial_name, trial_name,
            skin_delta, o3_trial, center_skin_text, center_skin_t
        ))

    original_case_records_after = {
        name: sha256(center_case / "out" / name) for name in STATIC_OUT_FILES
    } | {
        "out/k/radiance.txt": sha256(center_case / "out/k/radiance.txt"),
        "out/k/profiles_k.txt": sha256(center_case / "out/k/profiles_k.txt"),
    }
    require(original_case_records_before == original_case_records_after,
            "preflight changed a saved center launch/output file")
    assets_after = resolve_trial_assets(assets_before)
    asset_hash_keys = ("rttov_executable_sha256", "coefficient_sha256",
                       "hydrotable_sha256")
    before_projection = {k: assets_before[k] for k in asset_hash_keys}
    after_projection = {k: assets_after[k] for k in asset_hash_keys}
    require(before_projection == after_projection,
            "RTTOV executable/coefficient/hydrotable changed during preflight")
    require(assets_before["library_manifest"]["libraries"]
            == assets_after["library_manifest"]["libraries"],
            "linked library paths/hashes changed during preflight")

    output_dir.mkdir(parents=True, exist_ok=True)
    plan_path = output_dir / "K_RESPONSE_PLAN.json"
    diff_path = output_dir / "INPUT_DIFFS.csv"
    report_path = output_dir / "REPORT.md"
    for path in (plan_path, diff_path, report_path):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite preflight artifact: {path}")
    plan_payload = {
        "schema": "pr402_finite_input_response_plan_v1",
        "status": "PREFLIGHT_READY_NOT_EXECUTED",
        "trial_set_id": set_id,
        "scope": {
            "center": {"j": 86, "i": 48, "time": center["native_time_label"],
                       "case_role": center["case_role"]},
            "runner": "case/out/run.sh through production run_rttov_k(case/out)",
            "trial_count": len(trial_records),
            "max_wrapper_calls": 4,
            "preflight_wrapper_calls": 0,
            "automatic_retry": False,
            "baseline_run": "reuse PR401 final-v2 center KMA BT/K; no fifth run",
            "calls": {"RTTOV_wrapper": 0, "H": 0, "K": 0, "M": 0,
                      "Model_H": 0, "native": 0, "optimizer": 0,
                      "preprocessing": 0, "acquisition": 0},
        },
        "direction_plan": {
            "skin": "actual k0%t +/- 0.5 K, serialized to six decimals",
            "o3": "reference O3 +/-1% across 69 levels; saved P[66,69] maps beta to active 66-layer O3; active ASCII vector uses .17E serialization",
            "channels": list(CHANNEL_IDS),
            "fixed_contract": {"sigma_K": 1.0, "bias_K": 0.0,
                               "huber_delta_K": 1.0, "support": [1.0] * 7},
            "unit_direction_scale": {
                "skin": {"d": "+1 K skin temperature", "h": 0.5,
                         "trial_offsets": [-0.5, 0.5]},
                "o3": {"d": "+1% of the saved 69-level reference O3 mapped by P",
                       "h": 1.0, "trial_offsets": [-1.0, 1.0]},
            },
            "finite_response_definition": {
                "B0": "preserved PR401 center KMA BT; no new baseline run",
                "raw_change_plus_minus": "B_plus-B0 and B_minus-B0, reported separately in K",
                "E_plus": "(B_plus-B0)-h*(K0@d), in K",
                "E_minus": "(B_minus-B0)+h*(K0@d), in K",
                "D_FD": "(B_plus-B_minus)/(2*h), in K per unit d",
                "D_h_ideal": "K0@d using PR401 unit direction d",
                "D_h_serialized": "K0@delta_input_actual/h using each trial's parsed serialized input vector; report separately from ideal D_h",
                "signed_error": "D_FD-D_h_ideal, in K per unit d",
                "relative_error": "signed_error/max(abs(D_FD),abs(D_h_ideal)) only if that denominator>=1e-6 K per unit d; otherwise null and report absolute error",
                "relative_denominator": "max(abs(D_FD),abs(D_h_ideal))",
                "relative_error_near_zero_threshold": {"value": 1e-6, "units": "K per unit d", "applies_to": "relative-error denominator"},
                "deltaJo_actual": "J(x_trial)-J(x0), dimensionless normalized Huber cost",
                "deltaJo_linear": "baseline Huber slope dot D_h (or one-sided K direction), dimensionless",
            },
        },
        "baseline": {
            "pr399_result_path": str(PR399_RESULT),
            "pr399_result_sha256": sha256(PR399_RESULT),
            "pr399_plan_path": str(PR399_PLAN),
            "pr399_plan_sha256": sha256(PR399_PLAN),
            "pr401_baseline_path": str(PR401_RESULT),
            "pr401_baseline_sha256": sha256(PR401_RESULT),
            "pr401_private_npz_path": str(PR401_NPZ),
            "pr401_private_npz_sha256": sha256(PR401_NPZ),
            "center_case_path_read_only": str(center_case),
            "input_sha256": baseline_inventory["center_input_files"],
            "center_case_outputs_sha256": baseline_inventory["center_saved_k_outputs"],
            "baseline_skin_t_k": center_skin_t,
            "baseline_source_o3_ppmv_moist_min_max": [float(source_o3.min()), float(source_o3.max())],
            "baseline_active_o3_ppmv_moist_min_max": [float(center_o3.min()), float(center_o3.max())],
            "baseline_cost_jo_dimensionless": pr401["summary"]["baseline_jo_huber_dimensionless"],
            "baseline_bt_kma_k": kma["kma_bt_k"].tolist(),
        },
        "runtime_assets": assets_before,
        "production_runner_source": {
            "path": str(RUNNER_SOURCE),
            "sha256": sha256(RUNNER_SOURCE),
            "thread_fence": {
                "OMP_NUM_THREADS": "1",
                "OMP_DYNAMIC": "FALSE",
                "OMP_THREAD_LIMIT": "1",
            },
            "executor": "run_rttov_k(case/out), which launches sh run.sh in a bounded child process group",
        },
        "historical_baseline_library_identity": "UNKNOWN_NOT_RECORDED",
        "runtime_asset_unchanged_during_preflight": True,
        "original_case_unchanged_during_preflight": {
            "before": original_case_records_before,
            "after": original_case_records_after,
        },
        "trials": trial_records,
        "execution_guard": {
            "required_plan_sha256_argument": True,
            "execution_id_required": True,
            "guard_file_exclusive_create": True,
            "guard_path": str(private_set / "EXECUTION_GUARD.json"),
            "lock_path": str(private_set / "EXECUTION_LOCK"),
            "failure_record_path": str(private_set / "EXECUTION_FAILURE.json"),
            "one_shot": True,
            "automatic_retry": False,
            "max_wrapper_calls": 4,
            "executor_source_required_before_final_freeze": True,
        },
        "execution_source": {
            "path": str(EXECUTOR_SOURCE),
            "sha256": sha256(EXECUTOR_SOURCE),
        },
        "preflight_provenance": {
            "helper_path": str(Path(__file__).resolve()),
            "helper_sha256": sha256(Path(__file__).resolve()),
            "source_pr401_k_response_path": str(PR401_RESULT),
            "trial_directory_mode_octal": oct(private_set.stat().st_mode & 0o777),
            "trial_case_directories": [r["trial_case_path"] for r in trial_records],
        },
        "limits": [
            "This is phase-1 preflight only; no wrapper/run.sh/RTTOV was invoked.",
            "No fresh baseline run, fifth call, H/M/model/native/preprocessing/acquisition or optimizer call is planned.",
            "Trials change only skin k0%t or the active O3 profile; every other center input and all launch settings remain hash-identical.",
            "No trial output is accepted until the one-shot execution stage, quality gate and source/asset postchecks complete.",
        ],
    }
    with plan_path.open("x") as stream:
        json.dump(plan_payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
    diff_rows = []
    for trial in trial_records:
        diff_rows.append({
            "trial": trial["trial_name"],
            "changed_input": trial["expected_input_file_change"],
            "baseline_sha256": trial["input_diff"]["baseline_changed_file_sha256"],
            "trial_sha256": trial["input_diff"]["trial_changed_file_sha256"],
            "actual_scalar_delta": trial["input_scalar_actual_delta"],
            "actual_o3_delta_min": (trial["input_o3_actual_delta_min_max"][0]
                                     if trial["input_o3_actual_delta_min_max"] else None),
            "actual_o3_delta_max": (trial["input_o3_actual_delta_min_max"][1]
                                     if trial["input_o3_actual_delta_min_max"] else None),
            "unchanged_file_count": trial["input_diff"]["unchanged_file_count"],
            "trial_case_path": trial["trial_case_path"],
            "wrapper_calls_planned": trial["wrapper_calls_planned"],
            "saved_outputs_copied": False,
        })
    with diff_path.open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(diff_rows[0]))
        writer.writeheader()
        writer.writerows(diff_rows)
    report = render_preflight_report(plan_payload, trial_records)
    report_path.write_text(report)
    return {"plan": plan_payload, "plan_path": plan_path,
            "plan_sha256": sha256(plan_path), "diff_path": diff_path,
            "report_path": report_path}


def render_preflight_report(plan: dict, trials: list[dict]) -> str:
    lines = [
        "# PR402 finite-input response preflight",
        "",
        "This packet is phase-1 only. It prepared four isolated input cases from the saved PR398 center and made **zero wrapper/RTTOV calls**. It did not run a new baseline, model, M, optimizer, preprocessing, or acquisition.",
        "",
        f"Frozen plan ID: `{plan['trial_set_id']}`. The root/Red preflight gate must approve the exact `K_RESPONSE_PLAN.json` SHA-256 before the separate one-shot execute stage. That stage is limited to four wrapper launches, one per trial, with no automatic retry.",
        "",
        "| Trial | Only changed input | Actual delta | Unchanged inputs | Wrapper planned | Saved K/radiance copied? |",
        "|---|---|---:|---:|---:|:---:|",
    ]
    for trial in trials:
        delta = trial["input_scalar_actual_delta"]
        if delta is None:
            delta = trial["input_o3_actual_delta_min_max"]
        lines.append(
            f"| {trial['trial_name']} | `{trial['expected_input_file_change']}` | `{delta}` | "
            f"{trial['input_diff']['unchanged_file_count']} | 1 | No |"
        )
    lines += [
        "",
        "Skin values are serialized with the source's six-decimal scalar format. O3 trials perturb the saved 69-level fixture reference by ±1%, map the signed source beta through the hash-bound PR401 66×69 matrix P, and serialize the resulting active 66-layer O3 with `.17E`. `INPUT_DIFFS.csv` and the per-trial inventories show that only the declared input file changed; pressure, T/Q, O3/CO2 except for the designated O3 trials, surface, geometry, channels, namelist and launch files remain bound.",
        "",
        "Each case's `out/` contains only the unchanged `run.sh`, `env.sh`, `rttov_test.txt` and empty `k/`/`direct/` output directories. The production runner target is `<trial>/out/run.sh`; the saved center `out/k` results were not copied. The resolved executable, coefficient, hydrotable and linked library paths/hashes are frozen in `K_RESPONSE_PLAN.json`; preflight rechecks them and confirms the original center outputs are unchanged.",
        "",
        "This does not authorize or record an execution. The future execution stage requires the exact plan hash and a unique execution ID, takes an exclusive lock, creates a one-shot guard before the first call, stops after any wrapper failure, and preserves a failure record without retry. A quality failure retains all seven rows and withholds any accepted cost/result; it never fabricates a value or silently drops a channel.",
        "The predeclared unit directions are d=+1 K for skin with h=0.5, and d=+1% of the saved 69-level reference O3 mapped through P with h=1. The executor will report raw B±−B0 separately, E±=[B±−B0]∓h(K0d), D_FD=(B+−B−)/(2h), ideal K0d, and K applied to the actually serialized input deltas. Relative errors use max(|D_FD|,|K0d|) as the denominator; they are null when that value is below 1e−6 K per unit d, while the signed absolute error remains reportable.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preflight", action="store_true", help="prepare four cases only (default)")
    parser.add_argument("--plan-id", help="unique safe id for a new preflight case set")
    parser.add_argument("--output-dir", type=Path, default=PACKET)
    args = parser.parse_args()
    result = prepare_plan(args.output_dir, args.plan_id)
    print(json.dumps({"status": result["plan"]["status"],
                      "plan_path": str(result["plan_path"]),
                      "plan_sha256": result["plan_sha256"],
                      "plan_id": result["plan"]["trial_set_id"],
                      "wrapper_calls": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
