#!/usr/bin/env python3
"""Read-only audit of preserved PR399 native-neighbor RTTOV inputs/products.

Reads source receipts, NPZs, active profile/surface files, fixture assets and
existing direct RTTOV K outputs. Never invokes RTTOV, KDM6, M/H, an optimizer,
or a native model. Writes only FIXED_INPUTS.json and REPORT.md here.
"""

from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "harness/evidence/pr400_input_compatibility_2026-10-10"
P = ROOT / "harness/evidence/pr399_vertical_neighbor_2026-10-10"
RESULT, PLAN, POST = (
    P / n
    for n in (
        "NEIGHBOR_RESULT_attempt2.json",
        "NEIGHBOR_PLAN_attempt2.json",
        "NEIGHBOR_POSTRUN_AUDIT_attempt2.json",
    )
)
INTAKE = ROOT / "harness/evidence/pr395_native_tq_intake_2026-10-10/INTAKE.json"
INTAKE_NPZ = (
    ROOT
    / "graphify-out/pr395-native-tq-intake-2026-10-10/private/native_column_8frame.npz"
)
NATIVE = Path(
    "/Users/yhlee/KDM6AD-k/host/research_evidence/pr398_sensitivity_20261010/native_patch_3x3_frames_1_4_6_v3.npz"
)
ARCHIVE = Path(
    "/Users/yhlee/KDM6AD-k/host/research_evidence/pr399_native_neighbor_h_20261010/attempt2_native_3x3_direct_h_inputs_outputs.npz"
)
REF = Path(
    "/Users/yhlee/AD-RTTOV/external/rttov14/src/rttov_test/tests.1.gfortran-openmp/ami/cloud/in/profiles/001/atm"
)
WRITER = ROOT / "harness/evidence/pr395_native_tq_intake_2026-10-10/run_analysis.py"
READER = (
    ROOT
    / "harness/evidence/native358_artifact_diag_2026-10-08/recipe/run_native_kma_bt_frames.py"
)
DRIVER = P / "neighbor_rttov.py"
SENSOR_JSON = OUT / "SENSOR_COMPATIBILITY.json"
SENSOR_REPORT = OUT / "SENSOR_COMPATIBILITY_REPORT.md"


def sha(p):
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def assignment_map(path):
    out = {}
    for line in Path(path).read_text().splitlines():
        m = re.match(r"\s*([\w%()]+)\s*=\s*([^!]+?)\s*$", line)
        if m:
            out[m.group(1).lower()] = m.group(2).strip().rstrip(",")
    return out


def group(path, prefix, names):
    s = Path(path).read_text()
    out = {}
    for name in names:
        m = re.search(rf"(?im)^\s*{prefix}%{re.escape(name)}\s*=\s*([^,!\s]+)", s)
        if not m:
            raise ValueError(f"{path}: missing {prefix}%{name}")
        out[name.lower()] = float(m.group(1))
    return out


def q_ppmv(qv):
    # Exact source-equivalent dry mixing-ratio conversion used by KDM6 RTTOV bridge.
    md, mv = 28.9647e-3, 18.01528e-3
    w = np.maximum(np.asarray(qv, dtype=np.float64), 0.0)
    nw = w / mv
    return 1e6 * nw / (1.0 / md + nw)


def k_fields(path):
    """Inventory serialized RTTOV PROFILES_K records; no K run is made here."""
    txt = Path(path).read_text()
    ret = {}
    pat = re.compile(r"PROFILES_K\(\s*(\d+)\)%(.*?)=\s*\((.*?)\)", re.S)
    for m in pat.finditer(txt):
        key = m.group(2).strip().upper()
        vals = [
            float(x.replace("D", "E").replace("d", "e"))
            for x in re.findall(
                r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[EeDd][-+]?\d+)?", m.group(3)
            )
        ]
        x = ret.setdefault(
            key, {"records": 0, "elements": 0, "nonzero": 0, "max_abs": 0.0}
        )
        x["records"] += 1
        x["elements"] += len(vals)
        x["nonzero"] += sum(v != 0.0 for v in vals)
        x["max_abs"] = max(x["max_abs"], max((abs(v) for v in vals), default=0.0))
    return ret


def audit():
    r, p, a = (json.loads(x.read_text()) for x in (RESULT, PLAN, POST))
    intake = json.loads(INTAKE.read_text())
    if r.get("status") != "ALL_NINE_ROWS_RETURNED" or len(r.get("results", [])) != 9:
        raise ValueError("PR399 result is not the complete nine-row result")
    if (
        sha(ARCHIVE) != r["private_npz"]["sha256"]
        or sha(NATIVE) != p["inputs"]["native_v3_npz_sha256"]
        or sha(INTAKE_NPZ) != p["inputs"]["pr395_intake_npz_sha256"]
    ):
        raise ValueError("private/native/intake NPZ hash binding failed")
    with np.load(ARCHIVE, allow_pickle=False) as z:
        s = {k: z[k].copy() for k in z.files}
    with np.load(NATIVE, allow_pickle=False) as z:
        native = {k: z[k].copy() for k in z.files}
    fields = s["surface_fields"].tolist()
    rows = []
    profile_file_max = {}
    surface_max = {}
    k_all = {}
    emis = []
    output_hashes = {}
    namelists = {}
    result_by = {(int(x["j"]), int(x["i"])): x for x in r["results"]}
    common_assets = next(
        x["rttov_assets"]
        for x in r["results"]
        if "prepared_fixture_info" in x.get("rttov_assets", {})
    )
    ref_half = np.loadtxt(REF / "p_half.txt", dtype=np.float64)
    h = ref_half.copy()
    h[0] = max(h[0], 1e-12)
    ref_p = 0.5 * (h[:-1] + h[1:])
    logref = np.log(ref_p)
    ref = {
        n: np.loadtxt(REF / f"{n}.txt", dtype=np.float64)
        for n in ("t", "q", "o3", "co2")
    }
    ref_hash = {n: sha(REF / f"{n}.txt") for n in ("p_half", "t", "q", "o3", "co2")}
    if (
        len(ref_p) != 69
        or len(ref_half) != 70
        or any(len(v) != 69 for v in ref.values())
        or not np.all(np.diff(ref_p) > 0)
    ):
        raise ValueError(
            "fixture reference grid is not 69/70 top-down ascending pressure"
        )
    recorded_ref = intake["upper_reference_assumption"]["files"]
    for name, digest in ref_hash.items():
        if recorded_ref[name]["sha256"] != digest:
            raise ValueError(
                f"current {name} fixture differs from PR395 intake receipt"
            )
    for ix, ((j, i), row) in enumerate(sorted(result_by.items())):
        case = Path(row["case_output_dir"])
        atm = case / "in/profiles/001/atm"
        expected = {
            "p.txt": s["profile_p_lay_hPa"][ix],
            "p_half.txt": s["profile_p_half_hPa"][ix],
            "t.txt": s["profile_t_K"][ix],
            "q.txt": s["profile_q_ppmv"][ix],
            "o3.txt": s["profile_o3_ppmv"][ix],
            "co2.txt": s["profile_co2_ppmv"][ix],
        }
        files = {}
        for name, arr in expected.items():
            actual = np.loadtxt(atm / name, dtype=np.float64)
            diff = float(np.max(np.abs(actual - arr)))
            tol = 1e-12 if name in ("t.txt", "q.txt") else 2e-13
            if actual.shape != arr.shape or diff > tol:
                raise ValueError(
                    f"active {name} differs from preserved NPZ at {(j, i)} ({diff})"
                )
            profile_file_max[name] = max(profile_file_max.get(name, 0.0), diff)
            files[name] = {
                "sha256": sha(atm / name),
                "length": int(actual.size),
                "max_abs_diff_from_archive": diff,
            }
        # Independently reconstruct native suffix plus fixture reference extension.
        y, x = j - 85, i - 47
        pn = native["native_patch__p_pa"][0, y, x, ::-1] / 100.0
        ph = (
            native["native_patch__p_half_calc_p8w_bottomup_Pa"][0, y, x, ::-1].astype(
                np.float64
            )
            / 100.0
        )
        ip = int(np.searchsorted(ref_half, float(ph[0]), side="left"))
        bh = np.r_[ref_half[:ip], ph[0]]
        bp = np.r_[ref_p[: max(ip - 1, 0)], np.sqrt(bh[-2] * bh[-1])]
        if bp.size != 27:
            raise ValueError(
                f"fixture source contributes {bp.size} upper reference layers, expected 27 at {(j, i)}"
            )
        pl = np.r_[bp, pn]
        pi = np.r_[bh[:-1], ph]
        o3 = np.interp(np.log(pl), logref, ref["o3"])
        co2 = np.interp(np.log(pl), logref, ref["co2"])
        tr = np.interp(np.log(bp), logref, ref["t"])
        qr = np.interp(np.log(bp), logref, ref["q"])
        tnative = (
            s["state_native_bottomup"][ix, 0] * s["forcing_native_bottomup"][ix, 1]
        )[::-1]
        qnative = q_ppmv(s["state_native_bottomup"][ix, 1][::-1])
        reconstructed = {
            "p.txt": pl,
            "p_half.txt": pi,
            "t.txt": np.r_[tr, tnative],
            "q.txt": np.r_[qr, qnative],
            "o3.txt": o3,
            "co2.txt": co2,
        }
        recdiff = {}
        for name, arr in reconstructed.items():
            d = float(np.max(np.abs(arr - expected[name])))
            recdiff[name] = d
            if d > (1e-11 if name in ("t.txt", "q.txt") else 2e-13):
                raise ValueError(
                    f"independent source formula does not reproduce {name} at {(j, i)} ({d})"
                )
        sv = {n: float(s["surface_values"][ix, k]) for k, n in enumerate(fields)}
        skin_path = case / "in/profiles/001/sfc/01/skin.txt"
        near_path = case / "in/profiles/001/sfc/01/near_surface.txt"
        skin = group(
            skin_path,
            "k0",
            [
                "surftype",
                "watertype",
                "salinity",
                "foam_fraction",
                "snow_fraction",
                *[f"fastem({n})" for n in range(1, 6)],
                "t",
            ],
        )
        near = group(
            near_path, "s0", ["t2m", "q2m", "wind_u10m", "wind_v10m", "wind_fetch"]
        )
        sd = {
            "TSK": abs(skin["t"] - sv["TSK"]),
            "T2": abs(near["t2m"] - sv["T2"]),
            "Q2_ppmv": abs(near["q2m"] - float(q_ppmv([sv["Q2"]])[0])),
            "U10": abs(near["wind_u10m"] - sv["U10"]),
            "V10": abs(near["wind_v10m"] - sv["V10"]),
        }
        for name, d in sd.items():
            surface_max[name] = max(surface_max.get(name, 0.0), d)
        if max(sd.values()) > 5.1e-7:
            raise ValueError(f"surface file/native mismatch at {(j, i)}: {sd}")
        if sv["xland"] != 2 or sv["seaice"] != 0:
            raise ValueError(f"cell {(j, i)} is not open ocean and ice free")
        nml = assignment_map(case / "out/rttov_test.txt")
        norm = {k: v.upper() for k, v in nml.items()}
        req = {
            "defn%opts%rt_all%solar": ".FALSE.",
            "defn%do_direct": ".TRUE.",
            "defn%do_k": ".TRUE.",
            "defn%run_gas_units": "2",
            "defn%nlevels": "67",
            "defn%nchannels": "7",
        }
        channels = [int(v) for v in (case / "in/channels.txt").read_text().split()]
        if (
            any(norm.get(k) != v for k, v in req.items())
            or channels != list(range(10, 17))
            or "gas_units = 2"
            not in (case / "in/profiles/001/gas_units.txt").read_text()
        ):
            raise ValueError(f"RTTOV option/input file mismatch at {(j, i)}")
        namelists[f"{j},{i}"] = nml
        assets = row.get("rttov_assets", {})
        prepared = assets.get("prepared_fixture_info")
        if prepared is None:
            prepared = common_assets["prepared_fixture_info"]
        source_assets = assets.get(
            "source_asset_sha256", common_assets["source_asset_sha256"]
        )
        for key, spec in source_assets.items():
            asset = Path(spec["path"])
            if asset.is_file() and sha(asset) != spec["sha256"]:
                raise ValueError(f"pinned {key} changed")
        for key in ("ami_coefficient", "rttov_executable"):
            spec = prepared[key]
            if sha(spec["path"]) != spec["sha256"]:
                raise ValueError(f"prepared {key} changed")
        for fn in ("rttov_test.txt", "run.sh"):
            output_hashes.setdefault(fn, {})[f"{j},{i}"] = sha(case / "out" / fn)
        ep = case / "out/k/emissivity_out.txt"
        ev = [
            float(v)
            for v in re.findall(
                r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[EeDd][-+]?\d+)?", ep.read_text()
            )
        ][1:]
        emis += ev
        ek = case / "out/k/emissivity_k.txt"
        ekv = [
            float(v)
            for v in re.findall(
                r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[EeDd][-+]?\d+)?", ek.read_text()
            )
        ][1:]
        rk = case / "out/k/diffuse_reflectance_k.txt"
        rkv = [
            float(v)
            for v in re.findall(
                r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[EeDd][-+]?\d+)?", rk.read_text()
            )
        ][1:]
        if len(ekv) != 7 or len(rkv) != 7:
            raise ValueError(
                f"expected seven direct surface K output channels at {(j, i)}"
            )
        kp = case / "out/k/profiles_k.txt"
        kf = k_fields(kp)
        for key, v in kf.items():
            d = k_all.setdefault(
                key, {"records": 0, "elements": 0, "nonzero": 0, "max_abs": 0.0}
            )
            for nm in ("records", "elements", "nonzero"):
                d[nm] += v[nm]
            d["max_abs"] = max(d["max_abs"], v["max_abs"])
        rows.append(
            {
                "cell_j_i": [j, i],
                "case_id": row["case_id"],
                "active_profiles": files,
                "independent_reconstruction_max_abs": recdiff,
                "native_layers": 39,
                "reference_layers": int(bp.size),
                "native_pressure_suffix_exact": bool(np.array_equal(pl[-39:], pn)),
                "native_interface_suffix_exact": bool(np.array_equal(pi[-40:], ph)),
                "gas_reference_min_max_hPa": [float(ref_p.min()), float(ref_p.max())],
                "native_levels_below_reference_min": int(
                    np.count_nonzero(pn < ref_p.min())
                ),
                "native_levels_above_reference_max": int(
                    np.count_nonzero(pn > ref_p.max())
                ),
                "native_surface": sv,
                "actual_skin_file": skin,
                "actual_near_surface_file": near,
                "surface_rounding_differences": sd,
                "channels": channels,
                "selected_rttov_namelist": {k: nml[k] for k in req},
                "gas_units_file_sha256": sha(case / "in/profiles/001/gas_units.txt"),
                "emissivity_output": {"sha256": sha(ep), "values": ev},
                "emissivity_k": {
                    "sha256": sha(ek),
                    "elements": len(ekv),
                    "nonzero": sum(v != 0 for v in ekv),
                    "values": ekv,
                },
                "diffuse_reflectance_k": {
                    "sha256": sha(rk),
                    "elements": len(rkv),
                    "nonzero": sum(v != 0 for v in rkv),
                    "values": rkv,
                },
                "profiles_k": {"sha256": sha(kp), "channel_profiles": 7, "fields": kf},
                "pinned_assets": {
                    "coefficient_sha256": prepared["ami_coefficient"]["sha256"],
                    "executable_sha256": prepared["rttov_executable"]["sha256"],
                    "static_skin_sha256": source_assets["static_surface_skin"][
                        "sha256"
                    ],
                    "case_role": "reused center H output"
                    if "prepared_fixture_info" not in assets
                    else "new neighbor H output",
                },
            }
        )
    if len(set(output_hashes["rttov_test.txt"].values())) != 1:
        raise ValueError(
            "executed RTTOV namelist differs across the nine returned cases"
        )
    static = group(
        result_by[(85, 47)]["rttov_assets"]["source_asset_sha256"][
            "static_surface_skin"
        ]["path"],
        "k0",
        [
            "surftype",
            "watertype",
            "salinity",
            "foam_fraction",
            "snow_fraction",
            *[f"fastem({n})" for n in range(1, 6)],
        ],
    )
    sensor_context = {"available": False}
    if SENSOR_JSON.is_file():
        sensor = json.loads(SENSOR_JSON.read_text())
        conclusion = sensor["compatibility_conclusion"]
        sensor_context = {
            "available": True,
            "result_sha256": sha(SENSOR_JSON),
            "report_sha256": sha(SENSOR_REPORT) if SENSOR_REPORT.is_file() else None,
            "status": conclusion["status"],
            "channel_scope": conclusion["channel_scope"],
            "upstream_la_srf_payload_verified": False,
            "pixel_bt_recomputed": sensor["scope"]["dn_bt_arithmetic_recomputed"],
        }
    return {
        "schema": "pr400_fixed_input_compatibility_audit_v1",
        "status": "READ_ONLY_FIXED_INPUT_AUDIT_COMPLETE",
        "audit_calls": {
            "RTTOV": 0,
            "M": 0,
            "H": 0,
            "Model_H": 0,
            "optimizer": 0,
            "native_run": 0,
            "external_acquisition": 0,
        },
        "source_hashes": {
            "result": sha(RESULT),
            "plan": sha(PLAN),
            "postrun": sha(POST),
            "driver": sha(DRIVER),
            "driver_matches_executed_sha": sha(DRIVER) == r["source_driver_sha256"],
            "PR395_writer": sha(WRITER),
            "profile_reader": sha(READER),
            "intake_json": sha(INTAKE),
            "intake_npz": sha(INTAKE_NPZ),
            "native_npz": sha(NATIVE),
            "PR399_archive_npz": sha(ARCHIVE),
            "reference_files": ref_hash,
            "reference_files_match_PR395_intake_receipt": True,
            "RTTOV_executable": r["results"][0]["rttov_assets"]["source_asset_sha256"][
                "rttov_executable"
            ],
            "RTTOV_coefficient": r["results"][0]["rttov_assets"]["source_asset_sha256"][
                "rttov_coefficient"
            ],
        },
        "profile_contract": {
            "case_count": len(rows),
            "source_fixture_grid": {"layers": 69, "interfaces": 70},
            "native_layers": 39,
            "reference_layers_used_above_native_top": 27,
            "RTTOV_layers": 66,
            "interfaces": 67,
            "native_centers_and_P8W_suffix_preserved": True,
            "native_TQ_policy": "fixed RTTOV fixture supplies T/Q only above native top; saved native 39-layer T and dry-mixing-ratio qv occupy the suffix",
            "gas_policy": "fixture O3/CO2 interpolated in log pressure across complete extended grid; np.interp holds endpoint outside fixture range",
            "reference_fixture": str(REF),
            "reference_pressure_range_hPa": [float(ref_p.min()), float(ref_p.max())],
            "native_levels_below_fixture_min_total": sum(
                x["native_levels_below_reference_min"] for x in rows
            ),
            "native_levels_above_fixture_max_total": sum(
                x["native_levels_above_reference_max"] for x in rows
            ),
            "gas_units": 2,
            "qv_convention": "dry mixing ratio kg/kg converted to RTTOV moist-air ppmv",
            "conversion_molar_masses_kg_mol": {
                "dry_air": 0.0289647,
                "water_vapor": 0.01801528,
            },
            "max_active_file_difference_from_archive": profile_file_max,
            "per_cell": rows,
        },
        "surface_contract": {
            "dynamic_RTTOV_surface_fields": ["TSK", "T2", "Q2", "U10", "V10"],
            "native_context_fields": ["HGT", "xland", "seaice"],
            "geometry": "one fixed AMI candidate geometry reused across all nine columns; HGT was not varied per neighbor in that fixed geometry",
            "all_cells_xland_2_seaice_0": True,
            "fixed_skin_parameters": static,
            "dynamic_q2_conversion": "dry mixing ratio to RTTOV moist-air ppmv with gas_units=2",
            "wind_fetch_m": 0.0,
            "actual_emissivity_output_range": [min(emis), max(emis)],
            "emissivity_is_RTTOV_output_not_external_validation": True,
            "max_surface_rounding_differences": surface_max,
            "options": {
                "solar": False,
                "ir_sea_emis_model": 2,
                "mw_sea_emis_model": 3,
                "use_foam_fraction": False,
                "lambertian": False,
                "use_tskin_eff": False,
            },
        },
        "observation_operator": {
            "channels_1based": [10, 11, 12, 13, 14, 15, 16],
            "ami_kma_bt": True,
            "gas_units": 2,
            "qv_convention": "mixing_ratio_kgkg_dry",
            "cloud": True,
            "rho_d": "saved native rho/(1+qv)",
            "dry_number": True,
            "ncmin_land": 10.0,
            "ncmin_sea": 10.0,
            "t_blend_octaves": 0.0,
            "q_blend_octaves": 0.0,
            "do_direct": True,
            "do_k": True,
            "solar": False,
            "fixed_observation": {
                "sigma_K": r["fixed_observation"]["sigma_K"],
                "bias_K": r["fixed_observation"]["bias_K"],
                "huber_delta_K": r["fixed_observation"]["huber_delta_K"],
                "support": r["fixed_observation"]["frozen_support"],
            },
            "rttov_namelist_assignments_by_cell": namelists,
            "direct_rttov_k_inventory": {
                "new_neighbor_profiles_k_files": sum(
                    x["pinned_assets"]["case_role"] == "new neighbor H output"
                    for x in rows
                ),
                "reused_center_profiles_k_files": sum(
                    x["pinned_assets"]["case_role"] == "reused center H output"
                    for x in rows
                ),
                "inspected_profiles_k_files_total": len(rows),
                "channel_profiles_per_file": 7,
                "aggregated_fields_across_all_inspected_files": k_all,
                "emissivity_k": {
                    "elements_total": sum(
                        len(x["emissivity_k"]["values"]) for x in rows
                    ),
                    "nonzero_total": sum(x["emissivity_k"]["nonzero"] for x in rows),
                    "sha256_by_cell": {
                        "%d,%d" % tuple(x["cell_j_i"]): x["emissivity_k"]["sha256"]
                        for x in rows
                    },
                },
                "diffuse_reflectance_k": {
                    "elements_total": sum(
                        len(x["diffuse_reflectance_k"]["values"]) for x in rows
                    ),
                    "nonzero_total": sum(
                        x["diffuse_reflectance_k"]["nonzero"] for x in rows
                    ),
                    "sha256_by_cell": {
                        "%d,%d" % tuple(x["cell_j_i"]): x["diffuse_reflectance_k"][
                            "sha256"
                        ]
                        for x in rows
                    },
                },
                "output_file_hashes_recorded_per_cell": True,
                "KDM6AD_Model_H_or_model_composed_derivative": False,
                "scope": "8 PR399 neighbor RTTOV runK products plus 1 existing PR398 center K output reused with the center H result; no KDM6AD Model_H, JVP/VJP, or end-to-end derivative validation",
            },
        },
        "sensor_compatibility_context": sensor_context,
        "launch_file_hashes": output_hashes,
        "limitations": [
            "Read-only audit of preserved PR399 attempt-2 inputs and outputs; no new radiation/model calls.",
            "RTTOV reference T/Q/O3/CO2 fixture values are reproducible inputs, not independently validated as the atmospheric profile for this observation.",
            "Fixed surface parameters and RTTOV emissivity model were not independently validated or tuned.",
            "Direct RTTOV K products do not certify KDM6AD Model_H/JVP/VJP or any model-composed derivative.",
            "No input, sigma, bias, support, or scientific-acceptance decision was changed.",
        ],
    }


def render(d):
    p = d["profile_contract"]
    s = d["surface_contract"]
    o = d["observation_operator"]
    k = o["direct_rttov_k_inventory"]
    km = k["aggregated_fields_across_all_inspected_files"]
    sensor = d.get("sensor_compatibility_context", {})
    sensor_note = (
        f" The separate sensor audit reports {sensor['status']}: IR133's LA calibration tuple is v3.0 while the installed RTTOV coefficient uses the v3.1 shifted center; the LA header does not identify the upstream SRF payload and no pixel BT arithmetic was recomputed. See `SENSOR_COMPATIBILITY_REPORT.md` and `SENSOR_COMPATIBILITY.json` (result SHA-256 {sensor['result_sha256']})."
        if sensor.get("available")
        else " The separate sensor/SRF compatibility audit was not present when this report was generated."
    )
    return f"""# PR400 fixed-input compatibility audit

Read-only audit of the preserved PR399 direct-H input archive and the source path that constructed it. The audit made zero RTTOV, M, H, Model_H, optimizer, native-run, or acquisition calls. It does not alter controls or claim the fixed values are physically correct.

## Atmospheric profiles and gas reference

The source RTTOV fixture has 69 full pressure layers and 70 interfaces. For each selected native column, 27 upper fixture levels are retained and the native profile supplies its full 39-layer lower suffix, giving 66 RTTOV layers and 67 interfaces. The native center-pressure and REAL(4)-transcribed P8W suffixes are preserved. T and Q use the fixed fixture only above the native top; no fixture-grid remapping of native model layers is used.

O3 and CO2 are interpolated from the same fixture across the full extended pressure grid in log pressure. `numpy.interp` holds endpoint values beyond the reference bounds. The fixture is a reproducible source, not an independently validated atmospheric profile for this observation. The reference pressure range is {p["reference_pressure_range_hPa"][0]:.8g}–{p["reference_pressure_range_hPa"][1]:.8g} hPa; {p["native_levels_below_fixture_min_total"]} native layers across the nine columns fall below its minimum, and {p["native_levels_above_fixture_max_total"]} lie above its maximum (six lowest native levels in each column), where O3/CO2 use the held high-pressure endpoint. Native qv is dry mixing ratio and converts to RTTOV gas_units=2, ppmv over moist air, using the recorded molar masses.

All six active profile files (p, p_half, T, Q, O3, CO2) were compared with the PR399 private NPZ and independently reconstructed from the saved native NPZ plus fixture reference. Per-cell file hashes and maximum differences appear in `FIXED_INPUTS.json`.

## Surface inputs and options

Dynamic RTTOV surface fields are TSK, T2, Q2, U10, and V10. All nine saved cells are XLAND=2 and ice-free. HGT, XLAND, and sea ice remain preserved as native context; the comparison reuses one fixed AMI geometry across columns, so HGT is not varied per neighbor. Actual skin and near-surface files match the saved native values after the writer's six-decimal formatting; Q2 uses the dry-mixing-ratio to moist-air ppmv conversion.

The static fixture contributes surface type 1, water type 1, salinity 35, foam/snow fractions 0, and FASTEM values `[3, 5, 15, 0.1, 0.3]`; native TSK replaces its skin temperature. Executed settings include IR sea emissivity model 2, microwave model 3, foam-fraction use disabled, Lambertian disabled, effective skin temperature disabled, and solar disabled. RTTOV `emissivity_out.txt` ranges {s["actual_emissivity_output_range"][0]:.9g}–{s["actual_emissivity_output_range"][1]:.9g}; it is model output under these pinned settings, not an externally validated emissivity. Channels are 10–16. The profile path uses gas_units=2, native qv as dry mixing ratio, cloud enabled, saved native rho_d, dry-number mode, ncmin 10 for land/sea, and zero T/Q blend octaves. The complete parsed namelist assignments for every cell are retained in JSON; their file hashes are identical across the nine cases.

## Preserved RTTOV K products

The eight new neighbor cases retain seven-channel `profiles_k.txt` products, and the preserved PR398 center case has one K file reused with its center H result. Across those nine direct RTTOV runK outputs, T has {km["T"]["nonzero"]}/{km["T"]["elements"]} nonzero entries, Q has {km["Q"]["nonzero"]}/{km["Q"]["elements"]}, O3 has {km["O3"]["nonzero"]}/{km["O3"]["elements"]}, and CO2 has {km["CO2"]["nonzero"]}/{km["CO2"]["elements"]}. Skin-T and near-surface T2/Q2/U10/V10 counts are {km["SKIN( 1)%T"]["nonzero"]}/{km["SKIN( 1)%T"]["elements"]}, {km["NEAR_SURFACE( 1)%T2M"]["nonzero"]}/{km["NEAR_SURFACE( 1)%T2M"]["elements"]}, {km["NEAR_SURFACE( 1)%Q2M"]["nonzero"]}/{km["NEAR_SURFACE( 1)%Q2M"]["elements"]}, {km["NEAR_SURFACE( 1)%WIND_U10M"]["nonzero"]}/{km["NEAR_SURFACE( 1)%WIND_U10M"]["elements"]}, and {km["NEAR_SURFACE( 1)%WIND_V10M"]["nonzero"]}/{km["NEAR_SURFACE( 1)%WIND_V10M"]["elements"]}. JSON also gives each field's maximum absolute value and file hash. Direct emissivity-K and diffuse-reflectance-K contain {k["emissivity_k"]["nonzero_total"]}/{k["emissivity_k"]["elements_total"]} and {k["diffuse_reflectance_k"]["nonzero_total"]}/{k["diffuse_reflectance_k"]["elements_total"]} nonzero entries; FASTEM is {km["SKIN( 1)%FASTEM"]["nonzero"]}/{km["SKIN( 1)%FASTEM"]["elements"]} and salinity is {km["SKIN( 1)%SALINITY"]["nonzero"]}/{km["SKIN( 1)%SALINITY"]["elements"]}. These are preserved direct RTTOV K products. No KDM6AD Model_H or model-composed derivative was run, so this does not establish end-to-end KDM6AD derivative support or validation.

## Provenance and scope

`FIXED_INPUTS.json` binds the PR399 plan/result/postrun receipts, PR395 intake, native and PR399 private NPZs, writer and profile reader source, source fixture files, per-case active files, RTTOV coefficient/executable, and actual namelist settings by SHA-256. It makes no input, cost, bias, sigma, support, or acceptance change. The upper fixture atmosphere and surface/emissivity assumptions remain conditional inputs.{sensor_note}

Validation: ran this read-only audit helper and parsed its JSON output. No radiation or model calculation was executed by the audit.
"""


if __name__ == "__main__":
    data = audit()
    (OUT / "FIXED_INPUTS.json").write_text(
        json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    (OUT / "REPORT.md").write_text(render(data))
    print(
        json.dumps(
            {
                "status": data["status"],
                "cells": len(data["profile_contract"]["per_cell"]),
                "rttov_k_outputs": data["observation_operator"][
                    "direct_rttov_k_inventory"
                ]["inspected_profiles_k_files_total"],
                "json": str(OUT / "FIXED_INPUTS.json"),
                "report": str(OUT / "REPORT.md"),
            },
            indent=2,
        )
    )
