#!/usr/bin/env python3
"""One bounded three-time selected-column diagnostic from a completed MP137 child.
Reads only Times metadata and declared j103/i48 column/wind slices at 05/06/07 UTC.
No WRF, KDM, M/H, RTTOV, optimizer, or forecast writes/calls are performed.
"""

from __future__ import annotations
import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import netCDF4
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
PACKET = Path(__file__).resolve().parent
SS = Path(
    "/Users/yhlee/KDM6AD-k/host/KIM-meso_v1.0/test/ss_real_case_20260619_063620/SS"
)
RUN_DIR = SS / "runs/mp137_termparity_720min_hist60_np4_20260718_185625"
FORECAST = RUN_DIR / "klfs_lc05_fcst.202507190000"
PRIVATE_ROOT = Path(
    "/Users/yhlee/KDM6AD-k/host/research_evidence/pr416_hourly_column_20261012"
)
PRIVATE_NPZ = PRIVATE_ROOT / "private/hourly_j103_i48_05_06_07.npz"
PLAN_PATH = PACKET / "PLAN.json"
CSV_PATH = PACKET / "PROFILE.csv"
SUMMARY_PATH = PACKET / "SUMMARY.json"
V2_INTAKE = (
    ROOT
    / "harness/evidence/pr406_native_case_consumer_2026-10-11/intake_native_case_v2.py"
)
LEGACY_INTAKE = (
    ROOT / "harness/evidence/pr395_native_tq_intake_2026-10-10/intake_native_tq.py"
)
READER_SOURCE = (
    ROOT
    / "harness/evidence/native358_artifact_diag_2026-10-08/recipe/run_native_kma_bt_frames.py"
)
HOURLY_AUDIT = (
    ROOT
    / "harness/evidence/pr415_window_numerical_finish_2026-10-12/HOURLY_IDENTITY_AUDIT.json"
)
HOURLY_AUDIT_MD = (
    ROOT
    / "harness/evidence/pr415_window_numerical_finish_2026-10-12/HOURLY_IDENTITY_AUDIT.md"
)
EXPECTED = {
    "j": 103,
    "i": 48,
    "latitude_deg": 36.195343017578125,
    "longitude_deg": 122.0966796875,
    "coordinate_abs_tolerance_deg": 1e-6,
}
TIMES = ["2025-07-19_05:00:00", "2025-07-19_06:00:00", "2025-07-19_07:00:00"]
INDICES = [5, 6, 7]
STATE = (
    "THM",
    "QVAPOR",
    "QCLOUD",
    "QRAIN",
    "QICE",
    "QSNOW",
    "QGRAUP",
    "QNCCN",
    "QNCLOUD",
    "QNICE",
    "QNRAIN",
    "QIB",
)
MASS_HYDRO = ("QCLOUD", "QRAIN", "QICE", "QSNOW", "QGRAUP")
COLUMN = STATE + ("P", "PB", "FNM", "FNP", "C1H", "C2H", "DNW")
COLUMN_3D = STATE + ("P", "PB")
COLUMN_1D = ("FNM", "FNP", "C1H", "C2H", "DNW")
INTERFACES = ("PH", "PHB")
SURFACE = (
    "XLAND",
    "SEAICE",
    "TSK",
    "T2",
    "Q2",
    "U10",
    "V10",
    "HGT",
    "MU",
    "MUB",
    "XLAT",
    "XLONG",
)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def array_sha(a):
    return hashlib.sha256(np.ascontiguousarray(np.asarray(a)).tobytes()).hexdigest()


def fstat(path):
    s = Path(path).stat()
    return {
        "path": str(path),
        "size_bytes": s.st_size,
        "mtime_ns": s.st_mtime_ns,
        "inode": s.st_ino,
        "device": s.st_dev,
    }


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load source {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def arithmetic():
    legacy = load(LEGACY_INTAKE, "pr416_pr395_intake")
    return legacy, legacy.load_reader(), load(V2_INTAKE, "pr416_selected_frame")


def times_text(raw):
    return [row.tobytes().decode("ascii").strip("\x00 ") for row in raw]


def run_gate():
    terminal = (SS / "terminal_parity.log").read_text()
    nml = (RUN_DIR / "namelist.input").read_text()
    if (
        (RUN_DIR / "exit_code").read_text().strip() != "0"
        or "mp137 = mp137_termparity_720min_hist60_np4_20260718_185625" not in terminal
    ):
        raise ValueError("candidate run identity/exit evidence changed")
    if (
        "TERMINAL PARITY: PASS" not in terminal
        or nml.count("mp_physics                          = 137") != 1
    ):
        raise ValueError("candidate parity/MP137 namelist evidence changed")
    for rank in range(4):
        if (
            "2025-07-19_12:00:00 wrf: SUCCESS COMPLETE WRF"
            not in (RUN_DIR / f"rsl.error.{rank:04d}").read_text()
        ):
            raise ValueError(f"rank {rank} lacks successful terminal marker")
    return {
        "run_dir": str(RUN_DIR),
        "exit_code": 0,
        "mp_physics": 137,
        "ranks": 4,
        "terminal": "2025-07-19_12:00:00",
    }


def hash_sources():
    files = [
        Path(__file__),
        V2_INTAKE,
        LEGACY_INTAKE,
        READER_SOURCE,
        HOURLY_AUDIT,
        HOURLY_AUDIT_MD,
        SS / "terminal_parity.log",
        SS / "run_terminal_parity.sh",
        SS / "run_ss_case.py",
        RUN_DIR / "namelist.input",
        RUN_DIR / "exit_code",
    ] + [RUN_DIR / f"rsl.error.{i:04d}" for i in range(4)]
    result = {}
    for p in files:
        if not p.is_file():
            raise FileNotFoundError(p)
        result[str(p.resolve())] = {"sha256": sha(p), "size_bytes": p.stat().st_size}
    return result


def schema_for(ds, names):
    out = {}
    for n in names:
        if n not in ds.variables:
            raise ValueError(f"required NetCDF variable missing: {n}")
        v = ds[n]
        out[n] = {
            "dims": list(v.dimensions),
            "shape": list(v.shape),
            "dtype": str(v.dtype),
            "units": str(getattr(v, "units", "UNSPECIFIED")),
        }
    return out


def declare():
    if PRIVATE_ROOT.exists() or CSV_PATH.exists() or SUMMARY_PATH.exists():
        raise FileExistsError("refusing to declare over existing PR416 outputs")
    if PLAN_PATH.exists():
        raise FileExistsError(PLAN_PATH)
    gate = run_gate()
    sources = hash_sources()
    legacy, reader, _ = arithmetic()
    p8w_sha = reader.validate_p8w_source()
    before = fstat(FORECAST)
    with netCDF4.Dataset(FORECAST, "r") as ds:
        dims = {
            k: len(v) if not v.isunlimited() else "UNLIMITED"
            for k, v in ds.dimensions.items()
        }
        attrs = {
            k: str(getattr(ds, k))
            for k in ("START_DATE", "SIMULATION_START_DATE", "DX", "DY", "USE_THETA_M")
            if k in ds.ncattrs()
        }
        if (
            int(dims.get("bottom_top", -1)) != 39
            or int(dims.get("bottom_top_stag", -1)) != 40
        ):
            raise ValueError("expected 39 mass and 40 interface levels")
        if float(ds.getncattr("DX")) != 5000 or float(ds.getncattr("DY")) != 5000:
            raise ValueError("expected 5km grid")
        times = times_text(ds["Times"][:])
        if len(times) != 13 or [times[i] for i in INDICES] != TIMES:
            raise ValueError("predeclared hourly Times mismatch")
        names = tuple(
            dict.fromkeys(
                COLUMN
                + INTERFACES
                + SURFACE
                + tuple(
                    n
                    for n in ("U", "V", "W", "COSALPHA", "SINALPHA")
                    if n in ds.variables
                )
            )
        )
        schemas = schema_for(ds, names)
    plan = {
        "schema": "pr416_hourly_fixed_column_read_v1",
        "status": "PREDECLARED_NO_COLUMN_READ",
        "candidate_run": gate,
        "forecast_file": {
            **before,
            "full_sha256": None,
            "hash_policy": "No full 4.13GB hash; selected slices receive per-array hashes.",
        },
        "forecast_parent_relation": {
            "parent_path": str(SS / "klfs_lc05_fcst.202507190000"),
            "same_inode": False,
            "selected_source": str(FORECAST),
            "rule": "Use only the run-specific child.",
        },
        "point": EXPECTED,
        "times": [{"index": i, "time": t} for i, t in zip(INDICES, TIMES)],
        "metadata": {"dimensions": dims, "attrs": attrs, "all_times": times},
        "variables": schemas,
        "read_contract": {
            "netcdf_openings": 1,
            "time_indices": INDICES,
            "time_values": TIMES,
            "j": 103,
            "i": 48,
            "column_variables_3d": list(COLUMN_3D),
            "column_vertical_vectors": list(COLUMN_1D),
            "interface_variables": list(INTERFACES),
            "surface_variables": list(SURFACE),
            "U_slice": "U[t,:,j,i:i+2]",
            "V_slice": "V[t,:,j:j+2,i]",
            "W_slice": "W[t,:,j,i]",
            "rotation": "selected COSALPHA/SINALPHA scalars only if both variables exist",
            "no_full_grid_arrays": True,
            "no_time_interpolation": True,
            "no_reselection": True,
            "no_forecast_writes": True,
        },
        "outputs": {
            "absent_at_declaration": True,
            "profile_csv": str(CSV_PATH),
            "summary_json": str(SUMMARY_PATH),
            "private_npz": str(PRIVATE_NPZ),
        },
        "arithmetic": {
            "selected_frame_source": str(V2_INTAKE),
            "selected_frame_sha256": sources[str(V2_INTAKE.resolve())]["sha256"],
            "reader_source": str(READER_SOURCE),
            "reader_sha256": sources[str(READER_SOURCE.resolve())]["sha256"],
            "p8w_source": str(reader.WRF_P8W_SOURCE),
            "p8w_source_sha256": p8w_sha,
            "p8w_note": "Python REAL(4) transcription; host Fortran routine not executed",
        },
        "source_receipts": sources,
        "analysis_calls": {
            "native_model_run": 0,
            "KDM_M": 0,
            "all_sky_H": 0,
            "RTTOV": 0,
            "optimizer": 0,
        },
        "limits": [
            "Model state diagnostic only; not observed cloud truth or process attribution.",
            "No exact hourly build or input-byte binding; chainp START_DATE/Times discrepancy unresolved.",
            "Final boundary interval [09:00,12:00) is end-exclusive for further advancement.",
        ],
    }
    with PLAN_PATH.open("x") as f:
        json.dump(plan, f, indent=2, allow_nan=False)
        f.write("\n")
    print("PREDECLARED_NO_COLUMN_READ", flush=True)


def read_checked(legacy, ds, name, raw, shape, ti):
    values = legacy._check_selected_hyperslab(
        ds[name],
        raw,
        expected_shape=shape,
        time_index=ti,
        j=EXPECTED["j"],
        i=EXPECTED["i"],
    )
    return np.array(values, copy=True), np.array(
        np.ma.getmaskarray(raw), dtype=np.bool_, copy=True
    )


def execute():
    if not PLAN_PATH.is_file():
        raise FileNotFoundError("PLAN.json required")
    plan_sha = sha(PLAN_PATH)
    plan = json.loads(PLAN_PATH.read_text())
    if plan.get("status") != "PREDECLARED_NO_COLUMN_READ":
        raise ValueError("plan not in no-read state")
    if PRIVATE_ROOT.exists() or CSV_PATH.exists() or SUMMARY_PATH.exists():
        raise FileExistsError("refusing repeat or overwrite")
    for path, record in plan["source_receipts"].items():
        if (
            sha(Path(path)) != record["sha256"]
            or Path(path).stat().st_size != record["size_bytes"]
        ):
            raise ValueError(f"source changed: {path}")
    expected = {
        k: v
        for k, v in plan["forecast_file"].items()
        if k in ("path", "size_bytes", "mtime_ns", "inode", "device")
    }
    if fstat(FORECAST) != expected:
        raise ValueError("forecast stat changed after declaration")
    PRIVATE_ROOT.mkdir(mode=0o700, parents=False, exist_ok=False)
    PRIVATE_ROOT.chmod(0o700)
    private_dir = PRIVATE_ROOT / "private"
    private_dir.mkdir(mode=0o700)
    private_dir.chmod(0o700)
    with (PRIVATE_ROOT / "READ_STARTED_ONCE.json").open("x") as f:
        json.dump(
            {
                "plan_sha256": plan_sha,
                "forecast": str(FORECAST),
                "times": TIMES,
                "j": 103,
                "i": 48,
            },
            f,
            indent=2,
        )
        f.write("\n")
    try:
        legacy, reader, v2 = arithmetic()
        if reader.validate_p8w_source() != plan["arithmetic"]["p8w_source_sha256"]:
            raise ValueError("P8W source changed")
        before = fstat(FORECAST)
        archive = {}
        samples = []
        profile = []
        with netCDF4.Dataset(FORECAST, "r") as ds:
            times = times_text(ds["Times"][:])
            if times != plan["metadata"]["all_times"]:
                raise ValueError("Times changed")
            dims = {
                k: len(v) if not v.isunlimited() else "UNLIMITED"
                for k, v in ds.dimensions.items()
            }
            if dims != plan["metadata"]["dimensions"]:
                raise ValueError("NetCDF dimensions changed after declaration")
            meta_names = tuple(plan["variables"])
            if schema_for(ds, meta_names) != plan["variables"]:
                raise ValueError(
                    "variable shape/dtype/units metadata changed after declaration"
                )
            for ti, t in zip(INDICES, TIMES):
                if times[ti] != t:
                    raise ValueError("selected time mismatch")
                rawmap = {}
                maskmap = {}
                for name in COLUMN_3D:
                    a, m = read_checked(
                        legacy, ds, name, ds[name][ti, :, 103, 48], (39,), ti
                    )
                    rawmap[name] = a
                    maskmap[name] = m
                for name in COLUMN_1D:
                    a, m = read_checked(legacy, ds, name, ds[name][ti, :], (39,), ti)
                    rawmap[name] = a
                    maskmap[name] = m
                for name in INTERFACES:
                    a, m = read_checked(
                        legacy, ds, name, ds[name][ti, :, 103, 48], (40,), ti
                    )
                    rawmap[name] = a
                    maskmap[name] = m
                for name in SURFACE:
                    a, m = read_checked(legacy, ds, name, ds[name][ti, 103, 48], (), ti)
                    rawmap[name] = a
                    maskmap[name] = m
                if "U" in ds.variables:
                    a, m = read_checked(
                        legacy, ds, "U", ds["U"][ti, :, 103, 48:50], (39, 2), ti
                    )
                    rawmap["U"] = a
                    maskmap["U"] = m
                if "V" in ds.variables:
                    a, m = read_checked(
                        legacy, ds, "V", ds["V"][ti, :, 103:105, 48], (39, 2), ti
                    )
                    rawmap["V"] = a
                    maskmap["V"] = m
                if "W" in ds.variables:
                    a, m = read_checked(
                        legacy, ds, "W", ds["W"][ti, :, 103, 48], (40,), ti
                    )
                    rawmap["W"] = a
                    maskmap["W"] = m
                if "COSALPHA" in ds.variables and "SINALPHA" in ds.variables:
                    for name in ("COSALPHA", "SINALPHA"):
                        a, m = read_checked(
                            legacy, ds, name, ds[name][ti, 103, 48], (), ti
                        )
                        rawmap[name] = a
                        maskmap[name] = m
                native = v2._selected_frame(reader, ds, ti, 103, 48)
                lat, lon = native["lat"], native["lon"]
                if (
                    abs(lat - EXPECTED["latitude_deg"])
                    > EXPECTED["coordinate_abs_tolerance_deg"]
                    or abs(lon - EXPECTED["longitude_deg"])
                    > EXPECTED["coordinate_abs_tolerance_deg"]
                ):
                    raise ValueError(f"fixed point geo mismatch at {t}: {lat},{lon}")
                if native["xland"] != 2.0 or native["seaice"] != 0.0:
                    raise ValueError(f"not ocean/no-ice at {t}")
                theta_m = native["state"]["THM"] + reader.T0
                theta_dry = native["th"]
                temperature = theta_dry * native["pii"]
                z_w = (
                    rawmap["PH"].astype(np.float64) + rawmap["PHB"].astype(np.float64)
                ) / float(reader.G)
                zc = 0.5 * (z_w[:-1] + z_w[1:])
                p8w = np.asarray(native["p8w_pa"])
                ug = vg = None
                if "U" in rawmap and "V" in rawmap:
                    ug = 0.5 * (
                        rawmap["U"][:, 0].astype(np.float64)
                        + rawmap["U"][:, 1].astype(np.float64)
                    )
                    vg = 0.5 * (
                        rawmap["V"][:, 0].astype(np.float64)
                        + rawmap["V"][:, 1].astype(np.float64)
                    )
                ue = vn = None
                if ug is not None and "COSALPHA" in rawmap:
                    c, s = float(rawmap["COSALPHA"]), float(rawmap["SINALPHA"])
                    ue = ug * c - vg * s
                    vn = vg * c + ug * s
                state = native["state"]
                for name, a in rawmap.items():
                    archive[f"raw_ti{ti}_{name}"] = a
                for name, a in maskmap.items():
                    archive[f"mask_ti{ti}_{name}"] = a
                for name, a in [
                    ("pressure_center_Pa", native["p_pa"]),
                    ("p8w_interface_Pa", p8w),
                    ("theta_m_K", theta_m),
                    ("theta_dry_K", theta_dry),
                    ("temperature_K", temperature),
                    ("rho_d_kg_m3", native["rho_d"]),
                    ("rho_m_kg_m3", native["rho_m"]),
                    ("z_interface_m", z_w),
                    ("z_center_m", zc),
                    ("delz_m", native["delz"]),
                ]:
                    archive[f"derived_ti{ti}_{name}"] = np.asarray(a)
                if ug is not None:
                    archive[f"derived_ti{ti}_U_grid_center_ms"] = ug
                    archive[f"derived_ti{ti}_V_grid_center_ms"] = vg
                if ue is not None:
                    archive[f"derived_ti{ti}_U_east_ms"] = ue
                    archive[f"derived_ti{ti}_V_north_ms"] = vn
                sample = {
                    "time_index": ti,
                    "time": t,
                    "latitude_deg": lat,
                    "longitude_deg": lon,
                    "xland": native["xland"],
                    "seaice": native["seaice"],
                    "surface": native["surface"],
                    "source_dtypes": {n: str(a.dtype) for n, a in rawmap.items()},
                    "units": {
                        n: str(getattr(ds[n], "units", "UNSPECIFIED")) for n in rawmap
                    },
                    "mask_counts": {
                        n: int(np.count_nonzero(maskmap[n])) for n in rawmap
                    },
                    "raw_slice_sha256": {n: array_sha(a) for n, a in rawmap.items()},
                    "p_center_range_Pa": [
                        float(native["p_pa"].min()),
                        float(native["p_pa"].max()),
                    ],
                    "p8w_bottom_top_Pa": [float(p8w[0]), float(p8w[-1])],
                    "temperature_min_max_K": [
                        float(temperature.min()),
                        float(temperature.max()),
                    ],
                    "theta_dry_min_max_K": [
                        float(theta_dry.min()),
                        float(theta_dry.max()),
                    ],
                    "qv_min_max": [
                        float(state["QVAPOR"].min()),
                        float(state["QVAPOR"].max()),
                    ],
                    "rho_d_min_max_kg_m3": [
                        float(native["rho_d"].min()),
                        float(native["rho_d"].max()),
                    ],
                    "rho_m_min_max_kg_m3": [
                        float(native["rho_m"].min()),
                        float(native["rho_m"].max()),
                    ],
                    "delz_min_max_m": [
                        float(native["delz"].min()),
                        float(native["delz"].max()),
                    ],
                    "hydrometeor_column_mass_kg_m2": {
                        n: float(
                            np.sum(
                                state[n].astype(np.float64)
                                * native["rho_d"]
                                * native["delz"]
                            )
                        )
                        for n in MASS_HYDRO
                    },
                    "host_dry_mass_sum_kg_m2": float(
                        np.sum(native["host_dry_mass_kg_m2"], dtype=np.float64)
                    ),
                    "wind_rotation_available": ue is not None,
                }
                samples.append(sample)
                for k in range(39):
                    profile.append(
                        {
                            "time_index": ti,
                            "time": t,
                            "j": 103,
                            "i": 48,
                            "latitude_deg": lat,
                            "longitude_deg": lon,
                            "model_k": k,
                            "pressure_center_Pa": native["p_pa"][k],
                            "p8w_lower_Pa": p8w[k],
                            "p8w_upper_Pa": p8w[k + 1],
                            "PH_raw": rawmap["PH"][k],
                            "PHB_raw": rawmap["PHB"][k],
                            "z_bottom_m": z_w[k],
                            "z_top_m": z_w[k + 1],
                            "z_center_m": zc[k],
                            "delz_m": native["delz"][k],
                            "THM_raw": float(rawmap["THM"][k]),
                            "theta_m_K": float(theta_m[k]),
                            "theta_dry_K": float(theta_dry[k]),
                            "temperature_K": temperature[k],
                            "rho_d_kg_m3": native["rho_d"][k],
                            "rho_m_kg_m3": native["rho_m"][k],
                            **{n: float(rawmap[n][k]) for n in STATE[1:]},
                            "U_grid_center_ms": float(ug[k]) if ug is not None else "",
                            "V_grid_center_ms": float(vg[k]) if vg is not None else "",
                            "U10_raw": float(native["surface"]["U10"]),
                            "V10_raw": float(native["surface"]["V10"]),
                            "W_lower_ms": float(rawmap["W"][k])
                            if "W" in rawmap
                            else "",
                            "W_upper_ms": float(rawmap["W"][k + 1])
                            if "W" in rawmap
                            else "",
                            "U_east_ms": float(ue[k]) if ue is not None else "",
                            "V_north_ms": float(vn[k]) if vn is not None else "",
                        }
                    )
        after = fstat(FORECAST)
        if before != after:
            raise ValueError("forecast changed during slice extraction")
        if sha(PLAN_PATH) != plan_sha:
            raise ValueError("plan changed during read")
        with PRIVATE_NPZ.open("xb") as f:
            np.savez_compressed(f, **archive)
        PRIVATE_NPZ.chmod(0o600)
        fields = list(profile[0].keys())
        with CSV_PATH.open("x", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(profile)
        summary = {
            "schema": "pr416_hourly_selected_column_summary_v1",
            "status": "READ_COMPLETE_NO_MODEL_CALLS",
            "plan_sha256": plan_sha,
            "run_id": "mp137_termparity_720min_hist60_np4_20260718_185625",
            "forecast_path": str(FORECAST),
            "forecast_sha256": None,
            "times": TIMES,
            "time_indices": INDICES,
            "column": EXPECTED,
            "grid": {"dx_m": 5000, "dy_m": 5000, "mass_levels": 39, "interfaces": 40},
            "ocean_no_seaice_verified": all(
                s["xland"] == 2.0 and s["seaice"] == 0.0 for s in samples
            ),
            "wind_semantics": {
                "U/V_grid_center": "mean of adjacent staggered native faces; native grid coordinates retained",
                "earth_rotation": "Ue=Ug*COSALPHA-Vg*SINALPHA; Vn=Vg*COSALPHA+Ug*SINALPHA when both scalars exist",
                "earth_relative_available": all(
                    s["wind_rotation_available"] for s in samples
                ),
            },
            "samples": samples,
            "forecast_stat_before": before,
            "forecast_stat_after": after,
            "profile_csv": {
                "path": str(CSV_PATH),
                "size_bytes": CSV_PATH.stat().st_size,
                "sha256": sha(CSV_PATH),
            },
            "private_npz": {
                "path": str(PRIVATE_NPZ),
                "size_bytes": PRIVATE_NPZ.stat().st_size,
                "sha256": sha(PRIVATE_NPZ),
                "mode": oct(PRIVATE_NPZ.stat().st_mode & 0o777),
                "parent_mode": oct(PRIVATE_NPZ.parent.stat().st_mode & 0o777),
                "array_count": len(archive),
            },
            "analysis_calls": plan["analysis_calls"],
            "derived_units": {
                "temperature": "K",
                "theta_m": "K",
                "theta_dry": "K",
                "pressure_center": "Pa",
                "p8w_interface": "Pa",
                "height": "m",
                "delz": "m",
                "rho_d": "kg m-3",
                "rho_m": "kg m-3",
                "U/V/W": "m s-1",
                "hydrometeor_column_mass": "kg m-2",
            },
            "small_source_receipts": plan["source_receipts"],
            "limits": plan["limits"],
        }
        with SUMMARY_PATH.open("x") as f:
            json.dump(summary, f, indent=2, allow_nan=False)
            f.write("\n")
        print("READ_COMPLETE_NO_MODEL_CALLS", flush=True)
    except Exception as exc:
        with (PRIVATE_ROOT / "FAILURE.json").open("x") as f:
            json.dump(
                {
                    "status": "FAILED_NO_RETRY",
                    "error": repr(exc),
                    "plan_sha256": plan_sha,
                    "read_started_once": True,
                },
                f,
                indent=2,
            )
            f.write("\n")
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--declare", action="store_true")
    p.add_argument("--execute", action="store_true")
    a = p.parse_args()
    if a.declare == a.execute:
        raise ValueError("pass exactly one of --declare or --execute")
    declare() if a.declare else execute()


if __name__ == "__main__":
    main()
