#!/usr/bin/env python3
"""Prepare two saved-hour all-sky value-only H contexts; never calls H or M.

Inputs are only the already saved PR416 j103/i48 NPZ profiles at 06 and 07 UTC.
The original AMI file contributes GEOS navigation metadata only; no observed BT,
DQF, residual, fit cost, readiness manifest, or synthetic run receipt is used.
"""

from __future__ import annotations
import hashlib
import importlib.util
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
PACKET = Path(__file__).resolve().parent
PRIVATE_ROOT = Path(
    "/Users/yhlee/KDM6AD-k/host/research_evidence/pr417_hourly_rttov_20261012"
)
PRIVATE_NPZ = PRIVATE_ROOT / "TIME_INPUTS.npz"
PRIVATE_PREPARED = PRIVATE_ROOT / "PREPARED.json"
PLAN_PATH = PACKET / "PLAN.json"
PR416_PACKET = ROOT / "harness/evidence/pr416_hourly_column_2026-10-12"
PR416_SUMMARY = PR416_PACKET / "SUMMARY.json"
PR416_PLAN = PR416_PACKET / "PLAN.json"
PR416_EXTRACTOR = PR416_PACKET / "extract_hourly_column.py"
PR416_PRIVATE_NPZ = Path(
    "/Users/yhlee/KDM6AD-k/host/research_evidence/pr416_hourly_column_20261012/private/hourly_j103_i48_05_06_07.npz"
)
OBSERVATIONS = ROOT / "harness/evidence/pr414_ami_window_2026-10-12/OBSERVATIONS.json"
PR414_PLAN = (
    ROOT / "harness/evidence/pr414_ami_window_2026-10-12/WINDOW_PREDECLARED.json"
)
LEGACY_DRIVER = (
    ROOT / "harness/evidence/pr395_native_tq_intake_2026-10-10/run_analysis.py"
)
V2_INTAKE = (
    ROOT
    / "harness/evidence/pr406_native_case_consumer_2026-10-11/intake_native_case_v2.py"
)
V2_DRIVER = (
    ROOT
    / "harness/evidence/pr407_native_saved_time_bound_2026-10-11/run_case_analysis.py"
)
READER_SOURCE = (
    ROOT
    / "harness/evidence/native358_artifact_diag_2026-10-08/recipe/run_native_kma_bt_frames.py"
)
TEMPLATE_FIXTURE = Path(
    "/private/tmp/KDM6AD-viirs-native-run-20261007/comparison/results_failed_native_artifact_diag_055540_055800_retry2/case_00"
)
CHANNELS = tuple(range(10, 17))
TIMES = {6: "2025-07-19_06:00:00", 7: "2025-07-19_07:00:00"}
STATE_TO_RAW = {
    "th": "THM",
    "qv": "QVAPOR",
    "qc": "QCLOUD",
    "qr": "QRAIN",
    "qi": "QICE",
    "qs": "QSNOW",
    "qg": "QGRAUP",
    "nccn": "QNCCN",
    "nc": "QNCLOUD",
    "ni": "QNICE",
    "nr": "QNRAIN",
    "bg": "QIB",
}
VALUE_H_RUNNER = PACKET / "run_hourly_h.py"
SOURCE_MODULES = [
    VALUE_H_RUNNER,
    V2_DRIVER,
    V2_INTAKE,
    LEGACY_DRIVER,
    READER_SOURCE,
    ROOT / "oracle/kdm6/obs/allsky_shard.py",
    ROOT / "oracle/kdm6/obs/model_profile_builder.py",
    ROOT / "oracle/kdm6/obs/rttov_input_builder.py",
    ROOT / "oracle/kdm6/obs/rttov_obs_operator.py",
    ROOT / "oracle/kdm6/obs/rttov_case_writer.py",
    ROOT / "oracle/kdm6/obs/rttov_runner.py",
    ROOT / "oracle/kdm6/rttov_bridge.py",
    ROOT / "oracle/kdm6/state.py",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def array_sha(value) -> str:
    return hashlib.sha256(np.ascontiguousarray(np.asarray(value)).tobytes()).hexdigest()


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load pinned source {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def json_safe(value):
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


def require_expected_assets(pr414_plan: dict) -> dict:
    assets = pr414_plan["external_assets"]
    if len(assets) != 33:
        raise ValueError(f"expected frozen 33-asset PR414 set, found {len(assets)}")
    checked = {}
    for path, record in assets.items():
        p = Path(path)
        if (
            not p.is_file()
            or p.stat().st_size != record["bytes"]
            or str(p.resolve()) != record["resolved_path"]
        ):
            raise ValueError(f"PR414 asset path/size/resolution mismatch: {path}")
        digest = sha256(p)
        if digest != record["sha256"]:
            raise ValueError(f"PR414 expected asset SHA mismatch: {path}")
        checked[path] = dict(record)
    return checked


def read_geometry_only() -> tuple[dict, dict]:
    """Read only the common projection/navigation fields; never consume BT/DQF."""
    source = json.loads(OBSERVATIONS.read_text())
    slots = source["slots"]
    if len(slots) != 3:
        raise ValueError("expected the existing three-slot PR414 observation metadata")
    point = slots[0]["nearest_pixel"]
    geos = slots[0]["reader_geos"]
    for slot in slots:
        if slot["nearest_pixel"] != point or slot["reader_geos"] != geos:
            raise ValueError(
                "PR414 scenes no longer share the same fixed pixel/GEOS navigation"
            )
    if (
        point["row"] != 289
        or point["column"] != 49
        or point["latitude_deg"] != 36.19700231203294
        or point["longitude_deg"] != 122.09240151533507
    ):
        raise ValueError("original fixed PR414 AMI pixel changed")
    # Deliberately select only projection/navigation fields; observed target arrays
    # are never returned, copied into TIME_INPUTS, or used to compute a residual.
    return point, geos


def saved_native(arrays, reader, ti: int) -> dict:
    def raw(name):
        return np.asarray(arrays[f"raw_ti{ti}_{name}"])

    def derived(name):
        return np.asarray(arrays[f"derived_ti{ti}_{name}"])

    state = {rawname: raw(rawname).astype(np.float64) for rawname in reader.STATE_VARS}
    theta_dry = derived("theta_dry_K").astype(np.float64)
    p_pa = derived("pressure_center_Pa").astype(np.float64)
    pii = np.power(p_pa / reader.P0, reader.RCP)
    rho_d = derived("rho_d_kg_m3").astype(np.float64)
    rho_m = derived("rho_m_kg_m3").astype(np.float64)
    delz = derived("delz_m").astype(np.float64)
    p8w = derived("p8w_interface_Pa").astype(np.float32)
    host_mass = (
        -(
            raw("C1H").astype(np.float32)
            * (raw("MU").astype(np.float32) + raw("MUB").astype(np.float32))
            + raw("C2H").astype(np.float32)
        )
        * raw("DNW").astype(np.float32)
        / np.float32(9.81)
    ).astype(np.float32)
    surface = {
        name: float(raw(name)) for name in ("TSK", "T2", "Q2", "U10", "V10", "HGT")
    }
    return {
        "state": state,
        "th": theta_dry,
        "pii": pii,
        "p_pa": p_pa,
        "p8w_pa": p8w,
        "rho_d": rho_d,
        "rho_m": rho_m,
        "delz": delz,
        "host_dry_mass_kg_m2": host_mass,
        "PH_raw": raw("PH").astype(np.float64),
        "PHB_raw": raw("PHB").astype(np.float64),
        "xland": float(raw("XLAND")),
        "seaice": float(raw("SEAICE")),
        "surface": surface,
        "lat": float(raw("XLAT")),
        "lon": float(raw("XLONG")),
        "time": TIMES[ti],
        "raw": {name: raw(name).copy() for name in reader.STATE_VARS},
    }


def prepare_once() -> None:
    if PLAN_PATH.exists() or PRIVATE_ROOT.exists():
        raise FileExistsError("refusing to overwrite a prior PR417 preparation or plan")
    if not PR416_PRIVATE_NPZ.is_file() or not PR416_SUMMARY.is_file():
        raise FileNotFoundError("PR416 saved summary/private NPZ are required")
    pr416 = json.loads(PR416_SUMMARY.read_text())
    if (
        pr416.get("status") != "READ_COMPLETE_NO_MODEL_CALLS"
        or pr416.get("private_npz", {}).get("path") != str(PR416_PRIVATE_NPZ)
        or sha256(PR416_PRIVATE_NPZ) != pr416["private_npz"]["sha256"]
    ):
        raise ValueError("PR416 summary/private source pair is not hash-bound")
    pr414 = json.loads(PR414_PLAN.read_text())
    expected_assets = require_expected_assets(pr414)
    point, geos = read_geometry_only()
    legacy = load_module(LEGACY_DRIVER, "pr417_pr395_builder")
    reader = legacy.load_module(legacy.NATIVE_READER, "pr417_native_reference_reader")
    v2 = load_module(V2_INTAKE, "pr417_v2_arithmetic_and_reference_builder")
    if (
        reader.validate_p8w_source()
        != reader.WRF_P8W_EXPECTED_SHA256[str(reader.WRF_P8W_SOURCE)]
    ):
        raise ValueError("pinned Python P8W source does not match expected digest")
    template = legacy.TEMPLATE_FIXTURE.resolve()
    skin_file = template / "in/profiles/001/sfc/01/skin.txt"
    if not skin_file.is_file():
        raise FileNotFoundError(skin_file)
    source_paths = [
        Path(__file__),
        PR416_SUMMARY,
        PR416_PLAN,
        PR416_EXTRACTOR,
        PR416_PRIVATE_NPZ,
        PR414_PLAN,
        OBSERVATIONS,
        V2_DRIVER,
        V2_INTAKE,
        LEGACY_DRIVER,
        READER_SOURCE,
        Path(reader.WRF_P8W_SOURCE),
        skin_file,
        *SOURCE_MODULES,
    ]
    source_bindings = {}
    for p in source_paths:
        if not p.is_file():
            raise FileNotFoundError(p)
        source_bindings[str(p.resolve())] = {
            "sha256": sha256(p),
            "size_bytes": p.stat().st_size,
        }
    # Ensure the expected-asset registry and live files agree before any private output is written.
    for path, record in expected_assets.items():
        if sha256(Path(path)) != record["sha256"]:
            raise ValueError(
                f"external execution asset changed during preflight: {path}"
            )

    geos_source = {
        "nearest_pixel": {
            k: point[k] for k in ("row", "column", "latitude_deg", "longitude_deg")
        },
        "reader_geos": geos,
        "source_path": str(OBSERVATIONS.resolve()),
        "source_sha256": sha256(OBSERVATIONS),
        "role": "navigation/geometry metadata only; BT/DQF targets and residuals are not used",
    }
    out_root = PRIVATE_ROOT
    out_root.mkdir(mode=0o700, parents=False, exist_ok=False)
    out_root.chmod(0o700)
    private_dir = out_root / "private"
    private_dir.mkdir(mode=0o700)
    private_dir.chmod(0o700)
    with (out_root / "PREPARE_STARTED_ONCE.json").open("x") as marker:
        json.dump(
            {
                "status": "PREPARATION_STARTED_NO_H_CALLS",
                "times": [TIMES[6], TIMES[7]],
                "source_pr416_npz_sha256": sha256(PR416_PRIVATE_NPZ),
            },
            marker,
            indent=2,
        )
        marker.write("\n")
    contexts = {}
    npz_arrays = {}
    fixture_paths = {}
    fixture_source = template
    with np.load(PR416_PRIVATE_NPZ, allow_pickle=False) as input_npz:
        for ti in (6, 7):
            native = saved_native(input_npz, reader, ti)
            native_lat = 36.195343017578125
            native_lon = 122.0966796875
            lat1, lon1 = math.radians(native_lat), math.radians(native_lon)
            lat2, lon2 = (
                math.radians(point["latitude_deg"]),
                math.radians(point["longitude_deg"]),
            )
            dlat, dlon = lat2 - lat1, lon2 - lon1
            distance_m = (
                2
                * 6371008.77
                * math.asin(
                    min(
                        1.0,
                        math.sqrt(
                            math.sin(dlat / 2) ** 2
                            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
                        ),
                    )
                )
            )
            if (
                native["xland"] != 2.0
                or native["seaice"] != 0.0
                or abs(native["lat"] - native_lat) > 1e-6
                or abs(native["lon"] - native_lon) > 1e-6
                or distance_m > 2500.0
            ):
                raise ValueError(f"saved native point/radius changed at {TIMES[ti]}")
            extra, ref_info = v2._coordinates_and_reference(reader, native)
            # Each time gets its own p-grid, upper-reference extension and rho_d.
            for name, value in extra.items():
                npz_arrays[f"t{ti}__{name}"] = np.asarray(value).copy()
            for field, raw_name in v2.STATE_TO_RAW.items():
                vals = native["th"] if field == "th" else native["state"][raw_name]
                npz_arrays[f"t{ti}__state__{field}"] = np.asarray(
                    vals, dtype=np.float64
                ).reshape(1, 39)
            npz_arrays[f"t{ti}__forcing__rho"] = (
                native["rho_m"].astype(np.float64).reshape(1, 39)
            )
            npz_arrays[f"t{ti}__forcing__pii"] = (
                native["pii"].astype(np.float64).reshape(1, 39)
            )
            npz_arrays[f"t{ti}__forcing__p"] = (
                native["p_pa"].astype(np.float64).reshape(1, 39)
            )
            npz_arrays[f"t{ti}__forcing__delz"] = (
                native["delz"].astype(np.float64).reshape(1, 39)
            )
            npz_arrays[f"t{ti}__xland"] = np.asarray(
                [native["xland"]], dtype=np.float64
            )
            npz_arrays[f"t{ti}__rho_d_frozen"] = (
                native["rho_d"].astype(np.float64).reshape(1, 39)
            )
            # Preserve source-float32 arrays and masks in the private H input bundle.
            for name, value in native["raw"].items():
                npz_arrays[f"t{ti}__raw__{name}"] = np.asarray(value).copy()
                npz_arrays[f"t{ti}__raw_mask__{name}"] = np.asarray(
                    input_npz[f"mask_ti{ti}_{name}"], dtype=np.bool_
                ).copy()
            for name in (
                "P",
                "PB",
                "PH",
                "PHB",
                "FNM",
                "FNP",
                "C1H",
                "C2H",
                "DNW",
                "U",
                "V",
                "W",
                "COSALPHA",
                "SINALPHA",
            ):
                npz_arrays[f"t{ti}__raw__{name}"] = np.asarray(
                    input_npz[f"raw_ti{ti}_{name}"]
                ).copy()
                npz_arrays[f"t{ti}__raw_mask__{name}"] = np.asarray(
                    input_npz[f"mask_ti{ti}_{name}"], dtype=np.bool_
                ).copy()
            npz_arrays[f"t{ti}__y_placeholder_zero_not_observation"] = np.zeros(
                (1, 7), dtype=np.float64
            )
            npz_arrays[f"t{ti}__channel_gate_placeholder"] = np.ones(
                (1, 7), dtype=np.float64
            )
            # Geometry is held to original PR414 point/GEOS; state-specific H10 is passed
            # exactly as the V4 builder does (raw U10/V10, no rotation; basis unknown).
            geo_reader = reader
            geometry, geometry_context = geo_reader.ami_geometry(
                {
                    "ami_lat_lon": [native["lat"], native["lon"]],
                    "ami_metadata": {"geos": geos},
                },
                {},
                float(native["surface"]["HGT"]) / 1000.0,
            )
            static_skin = legacy._read_scalar_fields(skin_file, "k0")
            static_skin["t"] = native["surface"]["TSK"]
            import torch

            q2 = torch.as_tensor([native["surface"]["Q2"]], dtype=torch.float64)
            q2_ppmv = float(
                legacy.qv_to_q_ppmv_moist(
                    q2, gas_units=2, qv_convention="mixing_ratio_kgkg_dry"
                )[0]
            )
            surface = {
                "skin": static_skin,
                "near_surface": {
                    "t2m": native["surface"]["T2"],
                    "q2m": q2_ppmv,
                    "wind_u10m": native["surface"]["U10"],
                    "wind_v10m": native["surface"]["V10"],
                    "wind_fetch": 0.0,
                },
            }
            fixture_path = out_root / f"fixture_{ti:02d}"
            fixture_arrays = dict(extra)
            fixture_manifest = legacy._prepare_fixture_copy(
                fixture_source, fixture_path, fixture_arrays
            )
            fixture_paths[str(ti)] = {
                "path": str(fixture_path),
                "manifest": fixture_manifest,
            }
            contexts[str(ti)] = {
                "time": TIMES[ti],
                "native_column": {
                    "j": 103,
                    "i": 48,
                    "lat": native["lat"],
                    "lon": native["lon"],
                    "distance_to_ami_pixel_m": distance_m,
                },
                "GEOS_point_metadata_source": geos_source,
                "geometry": json_safe(geometry),
                "geometry_context": json_safe(geometry_context),
                "surface": json_safe(surface),
                "H_config": {
                    "channels": list(CHANNELS),
                    "coef_id": "paired-case_00-GK2A-AMI",
                    "fixture_case_dir": str(fixture_path),
                    "dry_number": True,
                    "ami_kma_bt": True,
                    "ncmin_land": 10.0,
                    "ncmin_sea": 10.0,
                    "t_blend_octaves": 0.0,
                    "q_blend_octaves": 0.0,
                    "rho_d_key": f"t{ti}__rho_d_frozen",
                    "p_lay_key": f"t{ti}__p_lay_rttov_topdown_hPa",
                    "p_half_key": f"t{ti}__p_half_rttov_topdown_hPa",
                    "t_ref_key": f"t{ti}__t_rttov_topdown_K",
                    "q_ref_key": f"t{ti}__q_rttov_topdown_ppmv",
                    "H10_wind_basis": "raw WRF U10/V10 passed as existing V4 surface fields; no rotation applied; basis not independently verified",
                },
                "reference_binding": ref_info,
                "diagnostic_mode": "value-only H; no obs target, no residual, no objective/cost report",
            }
    # Save generated H inputs before the exclusive plan; the final plan binds their SHA.
    with PRIVATE_NPZ.open("xb") as stream:
        np.savez_compressed(stream, **npz_arrays)
    PRIVATE_NPZ.chmod(0o600)
    fixture_hashes = {}
    for time_index, item in fixture_paths.items():
        target = Path(item["path"])
        for relative, digest in item["manifest"]["prepared_files_sha256"].items():
            candidate = (
                Path(relative) if Path(relative).is_absolute() else target / relative
            )
            if not candidate.is_file() or sha256(candidate) != digest:
                raise ValueError(
                    f"prepared fixture hash mismatch for t{time_index}: {candidate}"
                )
            fixture_hashes[str(candidate.resolve())] = digest
    bindings = {path: record["sha256"] for path, record in source_bindings.items()}
    bindings[str(PRIVATE_NPZ.resolve())] = sha256(PRIVATE_NPZ)
    plan_path = str(PLAN_PATH.resolve())
    python_exec = pr414["python_executable"]
    thread_env = dict(pr414["thread_environment"])
    output_root = PRIVATE_ROOT / "H_RUN_20261012_01"
    if output_root.exists():
        raise FileExistsError(f"H output root must be fresh: {output_root}")
    plan = {
        "schema": "pr417_hourly_two_time_value_only_h_prep_v1",
        "status": "PREPARED_INPUTS_NO_H_CALLS",
        "plan_path": plan_path,
        "run_id": "PR417_JUL19_HOURLY_06_07_VALUE_H_20261012",
        "root_main": "eaff1939",
        "time_indices": [6, 7],
        "max_logical_H_calls": 2,
        "runner_sha256": sha256(VALUE_H_RUNNER),
        "python_executable": python_exec,
        "thread_environment": thread_env,
        "output_root": str(output_root),
        "source_pr416_summary": str(PR416_SUMMARY),
        "source_pr416_summary_sha256": sha256(PR416_SUMMARY),
        "source_pr416_plan": str(PR416_PLAN),
        "source_pr416_plan_sha256": sha256(PR416_PLAN),
        "source_pr416_extractor": str(PR416_EXTRACTOR),
        "source_pr416_extractor_sha256": sha256(PR416_EXTRACTOR),
        "source_pr416_npz": str(PR416_PRIVATE_NPZ),
        "source_pr416_npz_sha256": sha256(PR416_PRIVATE_NPZ),
        "source_pr414_plan": str(PR414_PLAN),
        "source_pr414_plan_sha256": sha256(PR414_PLAN),
        "times": [{"index": 6, "time": TIMES[6]}, {"index": 7, "time": TIMES[7]}],
        "native_column": {
            "j": 103,
            "i": 48,
            "latitude_deg": 36.195343017578125,
            "longitude_deg": 122.0966796875,
        },
        "ami_geometry_point": {
            "row": 289,
            "column": 49,
            "latitude_deg": 36.19700231203294,
            "longitude_deg": 122.09240151533507,
            "source": "PR414 GEOS navigation only",
        },
        "observation_use": {
            "GEOS_navigation_only": True,
            "BT_or_DQF_targets_loaded_as_targets": False,
            "no_observation_residual_or_cost": True,
            "dummy_y_shape_only": "zeros[1,7], not observation values",
            "channel_gate_placeholder": "ones[1,7] quality gate only; not observation support",
        },
        "H_call_contract": {
            "planned_calls": 2,
            "times": [TIMES[6], TIMES[7]],
            "channels": list(CHANNELS),
            "grad": False,
            "all_sky": True,
            "dry_number": True,
            "ami_kma_bt": True,
            "frozen_rho_d_per_snapshot": True,
            "each_time_own_p_lay_p_half": True,
            "RTTOV_value_only": True,
            "ignore_returned_cost": True,
            "no_H_at_05": True,
            "no_M_or_optimizer": True,
            "no_native_model_run": True,
            "no_observation_cost_or_fit": True,
        },
        "diagnostic_limits": [
            "PR416 hourly child producer executable/input byte identity remains unbound.",
            "P8W is a hash-validated Python REAL(4) source transcription, not host Fortran execution.",
            "The reported raw NC count basis is not independently validated.",
            "H10 uses raw U10/V10 as the unchanged V4 surface contract; rotation/basis is not changed by this diagnostic.",
            "No result establishes cloud truth or process attribution.",
        ],
        "external_assets": expected_assets,
        "source_bindings": source_bindings,
        "bindings": bindings,
        "fixture_hashes": fixture_hashes,
        "private_root": str(PRIVATE_ROOT),
        "private_npz": str(PRIVATE_NPZ),
        "time_inputs_npz_sha256": sha256(PRIVATE_NPZ),
        "prepared_receipt": str(PRIVATE_PREPARED),
        "prepared_fixtures": fixture_paths,
        "time_contexts": contexts,
        "time_input_keys": sorted(npz_arrays),
        "analysis_calls": {
            "H": 0,
            "M": 0,
            "RTTOV": 0,
            "optimizer": 0,
            "native_model_run": 0,
        },
    }
    with PLAN_PATH.open("x") as f:
        json.dump(plan, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    # Validate every original PR414 asset and every prepared fixture after writing.
    for path, record in expected_assets.items():
        if (
            sha256(Path(path)) != record["sha256"]
            or Path(path).stat().st_size != record["bytes"]
            or str(Path(path).resolve()) != record["resolved_path"]
        ):
            raise ValueError(f"PR414 external asset changed after preparation: {path}")
    for time_key, item in fixture_paths.items():
        for rel, digest in item["manifest"]["prepared_files_sha256"].items():
            path = Path(item["path"]) / rel
            if not path.is_file() or sha256(path) != digest:
                raise ValueError(f"prepared fixture binding mismatch {time_key}:{rel}")
    prepared = {
        "schema": "pr417_hourly_h_prepared_inputs_v1",
        "status": "PREPARED_TWO_TIME_H_INPUTS_NO_H_CALLS",
        "plan_sha256": sha256(PLAN_PATH),
        "time_inputs_npz": str(PRIVATE_NPZ),
        "time_inputs_sha256": sha256(PRIVATE_NPZ),
        "time_inputs_size_bytes": PRIVATE_NPZ.stat().st_size,
        "time_inputs_mode": oct(PRIVATE_NPZ.stat().st_mode & 0o777),
        "private_dir_mode": oct((PRIVATE_ROOT / "private").stat().st_mode & 0o777),
        "fixture_manifests": fixture_paths,
        "external_assets_checked": len(expected_assets),
        "source_bindings": source_bindings,
        "analysis_calls": plan["H_call_contract"],
    }
    with PRIVATE_PREPARED.open("x") as f:
        json.dump(prepared, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    print(
        json.dumps(
            {
                "status": prepared["status"],
                "plan_sha256": prepared["plan_sha256"],
                "time_inputs_sha256": prepared["time_inputs_sha256"],
                "external_assets_checked": len(expected_assets),
            }
        )
    )


def load_context(plan, time_index: int) -> dict:
    """Root runner API: rebuild one H-only context from the pinned private bundle."""
    if isinstance(plan, (str, Path)):
        plan_path = Path(plan).resolve()
        plan_obj = json.loads(plan_path.read_text())
    else:
        plan_obj = plan
        plan_path = Path(plan_obj["plan_path"]).resolve()
    if int(time_index) not in (6, 7):
        raise ValueError("only prepared Times indices 6 and 7 exist")
    prepared = json.loads(PRIVATE_PREPARED.read_text())
    if prepared["plan_sha256"] != sha256(plan_path):
        raise ValueError("prep receipt plan hash mismatch")
    if sha256(PRIVATE_NPZ) != prepared["time_inputs_sha256"]:
        raise ValueError("private TIME_INPUTS hash mismatch")
    with np.load(PRIVATE_NPZ, allow_pickle=False) as a:
        state_fields = tuple(STATE_TO_RAW)
        from kdm6.state import State, Forcing
        import torch

        state = State(
            *(
                torch.as_tensor(a[f"t{time_index}__state__{f}"], dtype=torch.float64)
                for f in state_fields
            )
        )
        forcing = Forcing(
            **{
                f: torch.as_tensor(
                    a[f"t{time_index}__forcing__{f}"], dtype=torch.float64
                )
                for f in ("rho", "pii", "p", "delz")
            }
        )
        meta = plan_obj["time_contexts"][str(time_index)]
        cfgmeta = meta["H_config"]
        cfg = {
            "channels": tuple(cfgmeta["channels"]),
            "coef_id": cfgmeta["coef_id"],
            "fixture_case_dir": cfgmeta["fixture_case_dir"],
            "p_lay": a[cfgmeta["p_lay_key"]].copy(),
            "p_half": a[cfgmeta["p_half_key"]].copy(),
            "t_ref": a[cfgmeta["t_ref_key"]].copy(),
            "q_ref": a[cfgmeta["q_ref_key"]].copy(),
            "rho_d": a[cfgmeta["rho_d_key"]].copy(),
            "dry_number": True,
            "ami_kma_bt": True,
            "ncmin_land": 10.0,
            "ncmin_sea": 10.0,
            "t_blend_octaves": 0.0,
            "q_blend_octaves": 0.0,
            "geometry": meta["geometry"],
            "surface": meta["surface"],
        }
        xland = torch.as_tensor(a[f"t{time_index}__xland"], dtype=torch.float64)
    return {"state": state, "forcing": forcing, "xland": xland, "rttov_cfg": cfg}


def main():
    import argparse

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prepare", action="store_true")
    a = p.parse_args()
    if not a.prepare:
        raise ValueError("pass --prepare to create the exclusive two-time H inputs")
    prepare_once()


if __name__ == "__main__":
    main()
