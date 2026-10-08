#!/usr/bin/env python3
"""Value-only native-column AMI KMA-BT diagnostic for one completed WRF run.

This does not advance KDM6, optimize a state, compute an adjoint, or claim temporal
collocation. It runs the existing cloud RTTOV path once for each of eight saved native
frames and compares every result with one retained AMI pixel under a fixed common mask.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys

import netCDF4
import numpy as np
import torch

RUN_RECEIPT = Path("/private/tmp/KDM6AD-viirs-native-run-20261007/evidence/target_native_run_receipt_2026-10-08.json")
OBS_ROOT = Path("/private/tmp/KDM6AD-viirs-observation-context-20261007")
OBS_RESULT = OBS_ROOT / "harness/evidence/VIIRS_AMI_candidate_result_2026-10-07.json"
GEOM_RESULT = OBS_ROOT / "harness/evidence/VIIRS_geometry_result_2026-10-07.json"
OBS_RESULT_SHA256 = "7cbe37a71ef3289fd120ac5b7f0b7c05ec37e85e6c85935b1b52963b1e9d7b4f"
GEOM_RESULT_SHA256 = "d27c828ad1823a21a580fc1331a92d22caf15414f9f2a0fb9f9c63a4906f86be"
GEOMETRY_SOURCE_SHA256 = "51355eb6835963c2f564d18dc28ac3e40f5fa54ece0118f1c75d366095b4362c"
AMI_SOURCE_SHA256 = "d4eb8db5d39d28997c13f8bc8c5a316cc282df2d71da7470a8482e6b28442221"
ORACLE_ROOT = OBS_ROOT / "oracle"
REF_FIXTURE = Path("/Users/yhlee/AD-RTTOV/external/rttov14/src/rttov_test/tests.1.gfortran-openmp/ami/cloud")
WRF_SHARE = Path("/private/tmp/KDM6AD-viirs-native-run-20261007/isolated_project/host/KIM-meso_v1.0/share")
WRF_P8W_PRIMARY_SOURCE = WRF_SHARE / "wrf_timeseries.F"
WRF_P8W_FALLBACK_SOURCE = WRF_SHARE / "wrf_timeseries.f90"
WRF_P8W_SOURCE = (WRF_P8W_PRIMARY_SOURCE if WRF_P8W_PRIMARY_SOURCE.is_file()
                  else WRF_P8W_FALLBACK_SOURCE)
WRF_P8W_SOURCE_KIND = ("authoritative_wrf_fortran_source" if WRF_P8W_SOURCE == WRF_P8W_PRIMARY_SOURCE
                       else "explicit_f90_source_fallback_transcribed_in_python")
WRF_P8W_EXPECTED_SHA256 = {
    str(WRF_P8W_PRIMARY_SOURCE): "0e86d176a5acbeac82dcf062dff543f4a8a3b4df08841d79679640adbfe96eb1",
    str(WRF_P8W_FALLBACK_SOURCE): "707f89702edfe41c416907b8d6130ebadbabb5d23c5982a3ac48f499e5f34f55",
}
J, I = 86, 48
OBS_ROW, OBS_COL = 320, 48
CHANNELS = tuple(range(8, 17))
HUBER_DELTA = 1.0
F64 = {"dtype": torch.float64}
TARGET_FRAME_TIMES = tuple(
    f"2025-07-19_05:{minute:02d}:{second:02d}"
    for minute, second in ((55, 40), (56, 0), (56, 20), (56, 40),
                           (57, 0), (57, 20), (57, 40), (58, 0)))

STATE_VARS = ("THM", "QVAPOR", "QCLOUD", "QRAIN", "QICE", "QSNOW", "QGRAUP",
              "QNCCN", "QNCLOUD", "QNICE", "QNRAIN", "QIB")
G = np.float32(9.81)
R_D = np.float64(287.0)
R_V = np.float64(461.6)
CP = 7.0 * R_D / 2.0
RCP = R_D / CP
T0 = np.float64(300.0)
P0 = np.float64(100000.0)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def validate_p8w_source() -> str:
    expected = WRF_P8W_EXPECTED_SHA256.get(str(WRF_P8W_SOURCE))
    if expected is None:
        raise RuntimeError(f"unrecognized WRF P8W source selection: {WRF_P8W_SOURCE}")
    if not WRF_P8W_SOURCE.is_file():
        raise FileNotFoundError(f"selected WRF P8W source is missing: {WRF_P8W_SOURCE}")
    actual = sha256(WRF_P8W_SOURCE)
    if actual != expected:
        raise RuntimeError(
            f"selected WRF P8W source changed: {WRF_P8W_SOURCE} "
            f"sha256={actual}, expected={expected}")
    return actual


def write_vector(path: Path, values) -> None:
    arr = np.asarray(values, dtype=np.float64).reshape(-1)
    if not np.isfinite(arr).all():
        raise ValueError(f"non-finite values for {path}")
    path.write_text("".join(f"{v:.17E}\n" for v in arr))


def stage_thermal_only_fixture(case_fixture: Path) -> dict:
    """Disable solar and fixture cloud-fraction fallback only in a frame copy."""
    nml = case_fixture / "out" / "rttov_test.txt"
    original = nml.read_text()
    pattern = re.compile(r"(?im)^(\s*defn%opts%rt_all%solar\s*=\s*)(\.(?:TRUE|FALSE)\.)([^\n]*)$")
    matches = list(pattern.finditer(original))
    if len(matches) != 1 or matches[0].group(2).upper() != ".TRUE.":
        raise ValueError("expected exactly one solar=.TRUE. in the copied RTTOV fixture")
    updated, count = pattern.subn(lambda m: f"{m.group(1)}.FALSE.{m.group(3)}", original)
    if count != 1 or [m.group(2).upper() for m in pattern.finditer(updated)] != [".FALSE."]:
        raise ValueError("failed to establish solar=.FALSE. in the staged thermal-only fixture")
    nml.write_text(updated)
    simple_cloud = case_fixture / "in" / "profiles" / "001" / "atm" / "simple_cloud.txt"
    simple_text = simple_cloud.read_text()
    ctp_pattern = re.compile(r"(?im)^(\s*ctp\s*=\s*)([^!\n]+)$")
    frac_pattern = re.compile(r"(?im)^(\s*cfraction\s*=\s*)([^!\n]+)$")
    ctp_matches, frac_matches = list(ctp_pattern.finditer(simple_text)), list(frac_pattern.finditer(simple_text))
    if len(ctp_matches) != 1 or len(frac_matches) != 1:
        raise ValueError("copied RTTOV simple_cloud.txt must contain one CTP and one CFraction")
    original_ctp = float(ctp_matches[0].group(2).strip())
    original_fraction = float(frac_matches[0].group(2).strip())
    simple_updated, count = frac_pattern.subn(lambda m: f"{m.group(1)}0.0", simple_text)
    if count != 1 or float(frac_pattern.search(simple_updated).group(2).strip()) != 0.0:
        raise ValueError("failed to disable the staged simple-cloud fraction fallback")
    if float(ctp_pattern.search(simple_updated).group(2).strip()) != original_ctp:
        raise ValueError("staging the simple-cloud fraction unexpectedly changed CTP")
    simple_cloud.write_text(simple_updated)
    return dict(solar_namelist_sha256=sha256(nml), simple_cloud_sha256=sha256(simple_cloud),
                original_simple_cloud_ctp_hPa=original_ctp,
                original_simple_cloud_fraction=original_fraction,
                staged_simple_cloud_fraction=0.0)


def p8w_for_column(ds, ti: int, j: int, i: int) -> np.ndarray:
    """Python REAL(4) transcription of the selected WRF share calc_p8w source."""
    p = np.asarray(ds["P"][ti, :, j, i] + ds["PB"][ti, :, j, i], dtype=np.float32)
    ph = np.asarray(ds["PH"][ti, :, j, i], dtype=np.float32)
    phb = np.asarray(ds["PHB"][ti, :, j, i], dtype=np.float32)
    fnm = np.asarray(ds["FNM"][ti, :], dtype=np.float32)
    fnp = np.asarray(ds["FNP"][ti, :], dtype=np.float32)
    zw = np.asarray((ph + phb) / G, dtype=np.float32)
    zm = np.asarray(np.float32(0.5) * (zw[:-1] + zw[1:]), dtype=np.float32)
    out = np.empty((p.size + 1,), dtype=np.float32)
    out[1:-1] = fnm[1:] * p[1:] + fnp[1:] * p[:-1]
    w1 = np.float32((zw[0] - zm[1]) / (zm[0] - zm[1]))
    w2 = np.float32(1.0) - w1
    out[0] = w1 * p[0] + w2 * p[1]
    # Fortran z1=z(k_end-1), z2=z(k_end-2): Python zm[-1], zm[-2].
    w1 = np.float32((zw[-1] - zm[-2]) / (zm[-1] - zm[-2]))
    w2 = np.float32(1.0) - w1
    out[-1] = np.exp(w1 * np.log(p[-1]) + w2 * np.log(p[-2])).astype(np.float32)
    if not np.isfinite(out).all() or not np.all(out[:-1] > out[1:]):
        raise ValueError("derived native P8W is invalid or not bottom-up decreasing")
    return out


def selected_frame(ds, ti: int) -> dict:
    """Read one paired (j,i) column only. All model arrays remain bottom-up."""
    if int(getattr(ds, "USE_THETA_M", 1)) != 1:
        raise ValueError("only USE_THETA_M=1 frame reconstruction is supported")
    arrays = {name: np.asarray(ds[name][ti, :, J, I], dtype=np.float64)
              for name in STATE_VARS}
    # Match frame_reader's float64-first P/PB sum for state forcing and EOS
    # density. The WRF REAL(4) P+PB sum used by calc_p8w is separate in that helper.
    p_pa = (np.asarray(ds["P"][ti, :, J, I], dtype=np.float64)
            + np.asarray(ds["PB"][ti, :, J, I], dtype=np.float64))
    qv = arrays["QVAPOR"]
    thm = arrays["THM"] + T0
    pii = np.power(p_pa / P0, RCP)
    th = thm / (1.0 + (R_V / R_D) * qv)
    rho_d = p_pa / (R_D * thm * pii)
    rho_m = rho_d * (1.0 + qv)
    ph64 = np.asarray(ds["PH"][ti, :, J, I], dtype=np.float64)
    phb64 = np.asarray(ds["PHB"][ti, :, J, I], dtype=np.float64)
    z_w = (ph64 + phb64) / float(G)
    delz = z_w[1:] - z_w[:-1]
    xland = float(ds["XLAND"][ti, J, I])
    seaice = float(ds["SEAICE"][ti, J, I]) if "SEAICE" in ds.variables else None
    surface = {name: float(ds[name][ti, J, I]) for name in
               ("TSK", "T2", "Q2", "U10", "V10", "HGT")}
    if not all(name in ds.variables for name in ("MU", "MUB", "C1H", "C2H", "DNW")):
        raise ValueError("native host dry-layer diagnostic requires MU/MUB/C1H/C2H/DNW")
    mu = np.float32(ds["MU"][ti, J, I])
    mub = np.float32(ds["MUB"][ti, J, I])
    c1h = np.asarray(ds["C1H"][ti, :], dtype=np.float32)
    c2h = np.asarray(ds["C2H"][ti, :], dtype=np.float32)
    dnw = np.asarray(ds["DNW"][ti, :], dtype=np.float32)
    host_dry_mass = (-(c1h * (mu + mub) + c2h) * dnw / np.float32(9.81)).astype(np.float32)
    if host_dry_mass.shape != p_pa.shape or not np.isfinite(host_dry_mass).all() or np.any(host_dry_mass <= 0.0):
        raise ValueError("native host-derived dry layer mass is invalid")
    lat = float(ds["XLAT"][ti, J, I]); lon = float(ds["XLONG"][ti, J, I])
    if xland != 2.0 or (seaice is not None and seaice != 0.0):
        raise ValueError(f"selected model cell is not open ocean: XLAND={xland}, SEAICE={seaice}")
    if not all(np.isfinite(x).all() for x in (p_pa, rho_d, delz)) or not all(
            math.isfinite(x) for x in (*surface.values(), lat, lon)):
        raise ValueError("selected model column contains non-finite inputs")
    return dict(state=arrays, p_pa=p_pa, th=th, pii=pii, rho_m=rho_m,
                rho_d=rho_d, delz=delz, p8w_pa=p8w_for_column(ds, ti, J, I),
                host_dry_mass_kg_m2=host_dry_mass,
                xland=xland, seaice=seaice, surface=surface, lat=lat, lon=lon,
                time=ds["Times"][ti].tobytes().decode("ascii").strip())


def column_diagnostics(native: dict, t_native: np.ndarray) -> dict:
    """Value-only state snapshot using WRF's stored MU/eta layer mass formula."""
    s = native["state"]
    mass = native["host_dry_mass_kg_m2"].astype(np.float64)
    qc, qi, qs = s["QCLOUD"], s["QICE"], s["QSNOW"]
    qr, qg = s["QRAIN"], s["QGRAUP"]
    nc, ni, nr, ng = s["QNCLOUD"], s["QNICE"], s["QNRAIN"], s["QIB"]
    cloudy_liq = qc > 0.0
    cloudy_ice = qi > 0.0
    rho_d = native["rho_d"]
    active_nc_cm3 = rho_d[cloudy_liq] * nc[cloudy_liq] / 1.0e6

    def path_g_m2(amount):
        return float(np.sum(np.asarray(amount, dtype=np.float64) * mass) * 1000.0)

    return dict(
        temperature_min_K=float(np.min(t_native)), temperature_max_K=float(np.max(t_native)),
        cloudy_liquid_temperature_min_K=(float(np.min(t_native[cloudy_liq])) if np.any(cloudy_liq) else None),
        cloudy_liquid_temperature_max_K=(float(np.max(t_native[cloudy_liq])) if np.any(cloudy_liq) else None),
        qc_positive_layers=int(np.count_nonzero(cloudy_liq)), qi_positive_layers=int(np.count_nonzero(cloudy_ice)),
        qs_positive_layers=int(np.count_nonzero(qs > 0.0)),
        qn_number_concentration_basis="rho_d[kg dry air m-3] * N[kg dry air-1] / 1e6 = # cm-3; dry-number diagnostic mode",
        nc_cm3_min_on_qc_positive=(float(np.min(active_nc_cm3)) if active_nc_cm3.size else None),
        nc_cm3_max_on_qc_positive=(float(np.max(active_nc_cm3)) if active_nc_cm3.size else None),
        qc_positive_nc_nonpositive_layers=int(np.count_nonzero((qc > 0.0) & (nc <= 0.0))),
        qi_positive_ni_nonpositive_layers=int(np.count_nonzero((qi > 0.0) & (ni <= 0.0))),
        qr_positive_nr_nonpositive_layers=int(np.count_nonzero((qr > 0.0) & (nr <= 0.0))),
        qg_positive_bg_nonpositive_layers=int(np.count_nonzero((qg > 0.0) & (ng <= 0.0))),
        cloud_lwp_g_m2=path_g_m2(qc), cloud_iwp_qi_g_m2=path_g_m2(qi),
        snow_path_qs_g_m2=path_g_m2(qs), rain_wp_g_m2=path_g_m2(qr),
        graupel_path_qg_g_m2=path_g_m2(qg),
        sum_wrf_host_dry_layer_mass_kg_m2=float(np.sum(mass, dtype=np.float64)),
        sum_eos_rho_d_times_delz_kg_m2=float(np.sum(rho_d * native["delz"], dtype=np.float64)),
        wrf_host_dry_layer_mass_kg_m2=mass.tolist(),
        diagnostic_scope="saved background state only; not a KDM process budget, analysis increment, or conservation proof")


def load_reference() -> dict:
    atm = REF_FIXTURE / "in/profiles/001/atm"
    p_half = np.loadtxt(atm / "p_half.txt", dtype=np.float64)
    # The reference fixture has no explicit p.txt. Match RTTOV v14's own
    # arithmetic full-level pressure derived from p_half (top floor = 1e-12 hPa).
    p_half_for_full = p_half.copy()
    p_half_for_full[0] = max(p_half_for_full[0], 1.0e-12)
    p = 0.5 * (p_half_for_full[:-1] + p_half_for_full[1:])
    return {"p_half": p_half, "p": p,
            **{k: np.loadtxt(atm / f"{k}.txt", dtype=np.float64)
               for k in ("t", "q", "o3", "co2")}}


def extend_above_native_top(native: dict, ref: dict) -> tuple[np.ndarray, ...]:
    """Reference profile above native top; retain all 39 model centers and 40 faces."""
    p_native = native["p_pa"][::-1] / 100.0
    t_native = native["th"][::-1] * native["pii"][::-1]
    qv_native = native["state"]["QVAPOR"][::-1].copy()
    from kdm6.obs.model_profile_builder import qv_to_q_ppmv_moist
    q_native = qv_to_q_ppmv_moist(torch.as_tensor(qv_native, **F64), gas_units=2,
                                  qv_convention="mixing_ratio_kgkg_dry").numpy()
    p_half_native = native["p8w_pa"][::-1].astype(np.float64) / 100.0
    ptop = float(p_half_native[0])
    ip = int(np.searchsorted(ref["p_half"], ptop, side="left"))
    bg_half = np.concatenate((ref["p_half"][:ip], [ptop]))
    if len(bg_half) < 2:
        raise ValueError("native top is above the available reference profile")
    partial = float(np.sqrt(bg_half[-2] * bg_half[-1]))
    bg_p = np.concatenate((ref["p"][:max(ip - 1, 0)], [partial]))
    p_lay = np.concatenate((bg_p, p_native))
    p_half = np.concatenate((bg_half[:-1], p_half_native))
    if len(p_lay) != len(p_half) - 1 or len(p_native) != 39 or len(p_half_native) != 40:
        raise ValueError("unexpected native/extended layer dimensions")
    if not np.array_equal(p_lay[-39:], p_native) or not np.array_equal(p_half[-40:], p_half_native):
        raise ValueError("native center/interface suffix changed during extension")
    t_ref = np.interp(np.log(bg_p), np.log(ref["p"]), ref["t"])
    q_ref = np.interp(np.log(bg_p), np.log(ref["p"]), ref["q"])
    t_native = np.asarray(t_native, dtype=np.float64)
    q_native = np.asarray(q_native, dtype=np.float64)
    t = np.concatenate((t_ref, t_native))
    q = np.concatenate((q_ref, q_native))
    o3 = np.interp(np.log(p_lay), np.log(ref["p"]), ref["o3"])
    co2 = np.interp(np.log(p_lay), np.log(ref["p"]), ref["co2"])
    for label, arr in (("p_lay", p_lay), ("p_half", p_half), ("T", t), ("Q", q),
                       ("O3", o3), ("CO2", co2)):
        if not np.isfinite(arr).all():
            raise ValueError(f"non-finite extended {label}")
    return p_lay, p_half, t, q, o3, co2


def trace_gas_endpoint_diagnostics(p_lay_hpa: np.ndarray, ref: dict) -> dict:
    """Describe np.interp endpoint extension for fixture O3/CO2 over this grid."""
    ref_p = np.asarray(ref["p"], dtype=np.float64)
    p = np.asarray(p_lay_hpa, dtype=np.float64)
    p_min, p_max = float(np.min(ref_p)), float(np.max(ref_p))
    below = int(np.count_nonzero(p < p_min))
    above = int(np.count_nonzero(p > p_max))
    per_gas = {
        name: dict(layers_below_reference_min=below, layers_above_reference_max=above)
        for name in ("O3", "CO2")
    }
    return dict(reference_pressure_min_hPa=p_min, reference_pressure_max_hPa=p_max,
                extended_layer_count=int(p.size), endpoint_policy="numpy.interp holds endpoint values outside reference pressure bounds",
                per_gas_endpoint_clamp_layers=per_gas)


def ami_geometry(ami: dict, viirs_geometry: dict, surface_elevation_km: float) -> dict:
    def ami_tangent(lat_lon, geometry):
        lat, lon = np.deg2rad(lat_lon)
        a, b = geometry["earth_equatorial_radius"], geometry["earth_polar_radius"]
        normal = a / np.sqrt(1 - (1 - b*b/(a*a))*np.sin(lat)**2)
        point = normal*np.array([np.cos(lat)*np.cos(lon), np.cos(lat)*np.sin(lon),
                                 b*b/(a*a)*np.sin(lat)])
        slon = geometry["sub_longitude"]
        satellite = geometry["nominal_satellite_height"]*np.array([np.cos(slon), np.sin(slon), 0])
        ray = satellite-point
        east = np.array([-np.sin(lon), np.cos(lon), 0])
        north = np.array([-np.sin(lat)*np.cos(lon), -np.sin(lat)*np.sin(lon), np.cos(lat)])
        up = np.array([np.cos(lat)*np.cos(lon), np.cos(lat)*np.sin(lon), np.sin(lat)])
        enu = np.array([ray@east, ray@north, ray@up])
        if enu[2] <= 0:
            raise ValueError("AMI satellite is below the local horizon")
        return (enu[:2]/enu[2],
                float(np.rad2deg(np.arctan2(np.hypot(*enu[:2]), enu[2]))),
                float(np.rad2deg(np.arctan2(enu[0], enu[1]))))
    lat, lon = ami["ami_lat_lon"]
    _, zen, az = ami_tangent((lat, lon), ami["ami_metadata"]["geos"])
    return dict(zenangle=float(zen), azangle=float(az),
                sunzenangle=0.0, sunazangle=0.0,
                latitude=float(lat), longitude=float(lon), elevation=float(surface_elevation_km)), dict(
                    solar_angle_source="explicit zero angles; each staged thermal-only RTTOV case asserts rt_all%solar=.FALSE., so the solar angles are unconsumed",
                    ami_pixel_lat_lon=[float(lat), float(lon)],
                    satellite_viewing_geometry="computed at AMI pixel center with retained AMI GEOS navigation",
                    elevation_source="selected WRF native cell HGT, meters converted to RTTOV kilometers")


def validate_completed_run(receipt_path: Path, expected_run_id: str, explicit_forecast: Path | None):
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("status") != "COMPLETE" or not receipt.get("forecast_file_created"):
        raise RuntimeError("native run is not complete; no forecast will be opened or RTTOV called")
    runner_result = receipt.get("runner_result") or {}
    if not (receipt.get("successful") is True
            and runner_result.get("exit_code") == 0
            and runner_result.get("experiment_valid") is True
            and runner_result.get("model_completed_flag") is True):
        raise RuntimeError(
            "native comparison requires a successful, experiment-valid runner result; "
            "a WRF completion line alone is insufficient")
    if receipt.get("run_id") != expected_run_id:
        raise ValueError("native run receipt run_id differs from the requested target run")
    run_dir = Path(receipt["run_directory"])
    candidates = sorted(run_dir.glob("klfs_lc05_fcst.*"))
    if len(candidates) != 1:
        raise ValueError(f"expected exactly one forecast in completed run dir, found {len(candidates)}")
    forecast = candidates[0]
    if explicit_forecast is not None and forecast.resolve() != explicit_forecast.resolve():
        raise ValueError("explicit forecast path differs from unique run-directory forecast")
    expected_sha = receipt.get("forecast_sha256")
    if not expected_sha or sha256(forecast) != expected_sha:
        raise ValueError("forecast SHA does not match completion receipt")
    return receipt, forecast


def validate_failed_run_artifact_diagnostic(receipt_path: Path, expected_run_id: str,
                                            explicit_forecast: Path | None):
    """Allow value-only H diagnostics from one fully verified, runner-invalid artifact.

    This is deliberately separate from validate_completed_run: it never changes the
    operational completed/valid-run gate and marks every resulting value ineligible
    for native-experiment acceptance.
    """
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("status") != "COMPLETE" or receipt.get("run_id") != expected_run_id:
        raise ValueError("failed-run artifact diagnostic requires the exact completed target receipt")
    run_dir = Path(receipt["run_directory"]).resolve()
    if run_dir.name != expected_run_id or not run_dir.is_dir():
        raise ValueError("receipt run directory does not identify the exact target archive")
    result = receipt.get("runner_result") or {}
    if not (receipt.get("successful") is False
            and receipt.get("forecast_file_created") is True
            and receipt.get("forecast_generated") is True
            and result.get("run_id") == expected_run_id
            and result.get("exit_code") == 1
            and result.get("experiment_valid") is False
            and result.get("model_completed_flag") is False
            and result.get("wrf_success_complete_observed") is True
            and result.get("wrf_fatal_lines_observed") is False
            and result.get("mpi_abnormal_termination_observed") is True
            and result.get("wrapper_marker_observed") == receipt.get("wrapper_marker_expected")):
        raise ValueError("receipt does not match the narrowly allowed WRF-success/MPI-invalid case")
    if result.get("private_comparison_gate") != "NOT_PASSED: runner exit_code is nonzero and experiment_valid is false":
        raise ValueError("receipt's existing private comparison gate is not the expected rejection")

    expected_times = list(TARGET_FRAME_TIMES)
    discovery = receipt.get("verified_output_discovery") or {}
    forecast_record = receipt.get("forecast") or {}
    recorded_forecast = Path(forecast_record.get("path", "")).resolve()
    if not recorded_forecast.is_relative_to(run_dir):
        raise ValueError("receipt forecast path escapes the exact run archive")
    archived_forecasts = sorted(run_dir.glob("klfs_lc05_fcst.*"))
    if len(archived_forecasts) != 1 or archived_forecasts[0].resolve() != recorded_forecast:
        raise ValueError("expected exactly one forecast in the failed run archive")
    if (receipt.get("completion_times") != expected_times
            or receipt.get("latest_model_time") != expected_times[-1]
            or forecast_record.get("times") != expected_times
            or discovery.get("times") != expected_times
            or discovery.get("time_count") != 8):
        raise ValueError("receipt does not prove all eight exact target output times")
    if (discovery.get("status") != "verified"
            or discovery.get("archive_path") != str(recorded_forecast)
            or discovery.get("archive_sha256") != forecast_record.get("sha256")
            or discovery.get("case_sha256") != forecast_record.get("sha256")
            or discovery.get("archive_case_hash_match") is not True
            or discovery.get("finite_all_numeric") is not True
            or discovery.get("numeric_elements_checked") != 635785640
            or discovery.get("variable_count") != 254
            or discovery.get("numeric_variable_count") != 253):
        raise ValueError("receipt's complete finite-output/hash verification is incomplete or inconsistent")
    if sha256(recorded_forecast) != forecast_record.get("sha256"):
        raise ValueError("failed-run forecast bytes differ from the monitor-verified SHA")
    discovery_case = Path(discovery.get("case_path", "")).resolve()
    if not discovery_case.is_file() or sha256(discovery_case) != forecast_record.get("sha256"):
        raise ValueError("receipt-verified case output is missing or no longer byte-identical")
    if explicit_forecast is not None and recorded_forecast != explicit_forecast.resolve():
        raise ValueError("explicit forecast path differs from the monitor-verified artifact")

    binary = receipt.get("binary_after_hashes") or {}
    if not (binary.get("executable_stable") is True
            and binary.get("library_stable") is True
            and binary.get("executable_sha256_before") == receipt.get("executable_sha256")
            and binary.get("executable_sha256_after") == receipt.get("executable_sha256")
            and binary.get("library_sha256_before") == receipt.get("library_sha256")
            and binary.get("library_sha256_after") == receipt.get("library_sha256")):
        raise ValueError("executable/library hashes are not stable across the run")
    inputs = receipt.get("final_input_hashes") or {}
    if not inputs or any(v.get("stable") is not True or v.get("before") != v.get("after")
                         for v in inputs.values()):
        raise ValueError("native initialization or boundary inputs changed during the run")
    return receipt, recorded_forecast


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-receipt", type=Path, default=RUN_RECEIPT)
    ap.add_argument("--run-id", default="mp337_viirs_norm2_dry1_055540_055800_358min_hist0_20261008_064206_p28793")
    ap.add_argument("--forecast", type=Path)
    ap.add_argument("--output-root", type=Path, required=True)
    ap.add_argument("--failed-run-artifact-diagnostic", action="store_true",
                    help="explicitly permit value-only H on the one verified failed-run artifact; output remains ineligible for experiment/artifact gates")
    args = ap.parse_args()
    if args.output_root.exists():
        raise FileExistsError(f"output root already exists: {args.output_root}")
    runner_source_path = Path(__file__).resolve()
    runner_source_sha_before = sha256(runner_source_path)
    p8w_source_sha_before = validate_p8w_source()
    # Hard gate: do this before input obs, NetCDF forecast, or any RTTOV setup.
    if args.failed_run_artifact_diagnostic:
        run_receipt, forecast_path = validate_failed_run_artifact_diagnostic(
            args.run_receipt, args.run_id, args.forecast)
    else:
        run_receipt, forecast_path = validate_completed_run(args.run_receipt, args.run_id, args.forecast)
    args.output_root.mkdir(parents=True)
    runner_snapshot_path = args.output_root / "provenance" / "run_native_kma_bt_frames.py"
    runner_snapshot_path.parent.mkdir(parents=True)
    shutil.copy2(runner_source_path, runner_snapshot_path)
    if sha256(runner_snapshot_path) != runner_source_sha_before:
        raise RuntimeError("comparison-runner source snapshot differs from its launch bytes")

    torch.set_num_threads(1)
    sys.path.insert(0, str(ORACLE_ROOT))
    from kdm6 import state as state_module
    from kdm6.state import State, Forcing
    from kdm6.io import frame_reader
    from kdm6.obs.model_profile_builder import (RttovProfileConfig, model_to_rttov_tensors,
                                                qv_to_q_ppmv_moist)
    from kdm6.obs.rttov_input_builder import RttovInputConfig
    from kdm6.obs.rttov_case_writer import make_live_run_k, cloud_fixture_case_dir
    from kdm6.obs.rttov_obs_operator import RttovObsOp
    from kdm6.obs import obs_loss
    from kdm6.obs.obs_loss import compute_obs_loss
    from kdm6 import rttov_bridge
    from kdm6.obs import model_profile_builder, rttov_case_writer, rttov_input_builder
    from kdm6.obs import rttov_obs_operator, ami_bt_coordinate, rttov_runner

    imported_modules = (state_module, obs_loss, frame_reader, model_profile_builder, rttov_case_writer,
                        rttov_input_builder, rttov_obs_operator, ami_bt_coordinate,
                        rttov_runner, rttov_bridge)
    for module in imported_modules:
        if not Path(module.__file__).resolve().is_relative_to(ORACLE_ROOT.resolve()):
            raise RuntimeError(f"KDM source imported from an unexpected tree: {module.__file__}")
    runtime_source_hashes = {str(Path(module.__file__).resolve().relative_to(ORACLE_ROOT.resolve())):
                             sha256(Path(module.__file__)) for module in imported_modules}
    obs_start_sha = sha256(OBS_RESULT); geo_start_sha = sha256(GEOM_RESULT)
    receipt_start_sha = sha256(args.run_receipt)
    forecast_start_sha = sha256(forecast_path)

    obs = json.loads(OBS_RESULT.read_text())
    viirs_geo = json.loads(GEOM_RESULT.read_text())
    if sha256(OBS_RESULT) != OBS_RESULT_SHA256 or sha256(GEOM_RESULT) != GEOM_RESULT_SHA256:
        raise ValueError("retained AMI/VIIRS candidate result bytes changed")
    ami_source = OBS_ROOT / "harness/evidence/VIIRS_AMI_candidate_source_2026-10-07.py"
    if obs.get("producer_sha256") != AMI_SOURCE_SHA256 or sha256(ami_source) != AMI_SOURCE_SHA256:
        raise ValueError("AMI candidate producer source hash differs from the pin")
    geometry_source = OBS_ROOT / "harness/evidence/VIIRS_geometry_source_2026-10-07.py"
    if (sha256(geometry_source) != GEOMETRY_SOURCE_SHA256
            or viirs_geo.get("producer_sha256") != GEOMETRY_SOURCE_SHA256):
        raise ValueError("VIIRS/AMI geometry producer differs from its pinned source")
    calibration_file = ORACLE_ROOT / "kdm6/obs/data/gk2a_ami_cal_202507190000.json"
    if sha256(calibration_file) != obs.get("calibration_sha256"):
        raise ValueError("bundled KMA calibration differs from retained AMI candidate")
    for source_record in obs["ami_metadata"]["source_files"]:
        source_path = Path(source_record["source_path"])
        if sha256(source_path) != source_record["sha256"]:
            raise ValueError(f"retained AMI source file changed: {source_path}")
    if obs["ami_row_col_0based"] != [OBS_ROW, OBS_COL] or obs["channels"] != ["wv063", "wv069", "wv073", "ir087", "ir096", "ir105", "ir112", "ir123", "ir133"]:
        raise ValueError("retained observation candidate row/channel order changed")
    if not np.array_equal(np.asarray(obs["dqf"], dtype=np.float64), np.zeros(9)):
        raise ValueError("selected AMI candidate no longer has nine DQF-zero thermal channels")
    if viirs_geo.get("pixel_time_verified") is not False or viirs_geo.get("ami_clock_verified") is not False:
        raise ValueError("time/clock scope markers changed; expected conditional timing")
    y_bt = torch.as_tensor(obs["bt_K"], **F64).reshape(1, 9)
    geo = None
    geo_assumption = None
    fixture = cloud_fixture_case_dir().resolve()
    if fixture != REF_FIXTURE.resolve():
        raise ValueError(f"resolved all-sky fixture differs from pinned original: {fixture}")
    if not fixture.is_dir():
        raise FileNotFoundError(f"all-sky fixture missing: {fixture}")
    ref = load_reference()
    fixture_hashes = {str(p.relative_to(fixture)): sha256(p) for p in sorted(fixture.rglob("*")) if p.is_file()}
    coefficient_path = rttov_case_writer._resolve_coef_path(fixture)
    coefficient_channel_types = rttov_case_writer._coef_channel_types(coefficient_path)
    if not all(coefficient_channel_types.get(c) == 0 for c in CHANNELS):
        raise ValueError("thermal AMI channel set contains a non-thermal RTTOV coefficient type")
    coefficient_sha256 = sha256(coefficient_path)
    coef_text = (fixture / "in" / "coef.txt").read_text()
    hydro_name_match = re.search(r"(?im)^\s*defn%f_hydrotable\s*=\s*['\"]([^'\"]+)['\"]", coef_text)
    coef_prefix_match = re.search(r"(?m)^\s*defn%coef_prefix\s*=\s*'([^']+)'", (fixture / "out" / "rttov_test.txt").read_text())
    if hydro_name_match is None or coef_prefix_match is None:
        raise ValueError("fixture hydrotable path or coefficient prefix is missing")
    hydrotable_path = (fixture / "out" / coef_prefix_match.group(1) / hydro_name_match.group(1)).resolve()
    if not hydrotable_path.is_file():
        raise FileNotFoundError(f"RTTOV hydrotable missing: {hydrotable_path}")
    hydrotable_sha256 = sha256(hydrotable_path)
    run_script_text = (fixture / "out" / "run.sh").read_text()
    executable_match = re.search(r"(?m)^\s*(/[^\s]+rttov_test\.exe)\s*>", run_script_text)
    if executable_match is None:
        raise ValueError("pinned RTTOV fixture run.sh does not identify one absolute rttov_test.exe")
    rttov_executable_command_path = executable_match.group(1)
    rttov_executable_path = Path(rttov_executable_command_path).resolve()
    if not rttov_executable_path.is_file():
        raise FileNotFoundError(f"RTTOV executable from fixture run.sh is missing: {rttov_executable_path}")
    rttov_executable_sha_before = sha256(rttov_executable_path)

    times_expected = list(TARGET_FRAME_TIMES)
    with netCDF4.Dataset(forecast_path) as ds:
        if ds.dimensions["bottom_top"].size != 39 or ds.dimensions["bottom_top_stag"].size != 40:
            raise ValueError("native forecast is not on the expected 39-layer/40-interface WRF grid")
        actual_times = [row.tobytes().decode("ascii").strip() for row in ds["Times"][:]]
        if actual_times != times_expected:
            raise ValueError(f"forecast Times differ from the declared eight frames: {actual_times}")
        frames = []
        for ti, stamp in enumerate(actual_times):
            native = selected_frame(ds, ti)
            geo, geo_assumption = ami_geometry(obs, viirs_geo,
                                                native["surface"]["HGT"] / 1000.0)
            expected_lat, expected_lon = obs["selected_viirs_sample"]["native_lat_lon"]
            if abs(native["lat"] - expected_lat) > 1.0e-5 or abs(native["lon"] - expected_lon) > 1.0e-5:
                raise ValueError(f"native cell moved from selected VIIRS point at {stamp}: {native['lat']},{native['lon']}")
            p_lay_np, p_half_np, t_np, q_np, o3_np, co2_np = extend_above_native_top(native, ref)
            trace_gas_diagnostics = trace_gas_endpoint_diagnostics(p_lay_np, ref)
            # Exact native center and interface arrays are serialized as explicit
            # p.txt and p_half.txt; the writer validates that paired explicit grid.
            qv = torch.as_tensor(native["state"]["QVAPOR"], **F64)
            arrays = [torch.as_tensor(native["state"][v], **F64) for v in STATE_VARS]
            state = State(th=torch.as_tensor(native["th"], **F64),
                          qv=qv, qc=arrays[2], qr=arrays[3], qi=arrays[4],
                          qs=arrays[5], qg=arrays[6], nccn=arrays[7], nc=arrays[8],
                          ni=arrays[9], nr=arrays[10], bg=arrays[11])
            forcing = Forcing(rho=torch.as_tensor(native["rho_m"], **F64),
                              pii=torch.as_tensor(native["pii"], **F64),
                              p=torch.as_tensor(native["p_pa"], **F64),
                              delz=torch.as_tensor(native["delz"], **F64))
            # A frame's own background dry-air measure, fixed for this value-only H call.
            rho_d_native = torch.as_tensor(native["rho_d"], **F64)
            state_td = State(*(torch.flip(field, [-1]) for field in state))
            forcing_td = Forcing(rho=torch.flip(forcing.rho, [-1]), pii=torch.flip(forcing.pii, [-1]),
                                 p=torch.flip(forcing.p, [-1]) / 100.0, delz=torch.flip(forcing.delz, [-1]))
            rho_d_td = torch.flip(rho_d_native, [-1])
            p_lay = torch.as_tensor(p_lay_np, **F64)
            p_half = torch.as_tensor(p_half_np, **F64)
            pcfg = RttovProfileConfig(gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
                                      rttov_layer_pressure=p_lay,
                                      rttov_level_pressure=p_half, cloud=True,
                                      rho_d=rho_d_td, dry_number=True)
            prof = model_to_rttov_tensors(state_td, forcing_td, pcfg,
                                          xland=torch.tensor([native["xland"]], **F64),
                                          ncmin_land=10.0, ncmin_sea=10.0)
            # Top T/Q use only the original RTTOV reference profile above the native
            # top interface; native center values below it are inserted unchanged.
            prof = prof._replace(t_lay=torch.as_tensor(t_np, **F64),
                                 q_lay=torch.as_tensor(q_np, **F64))
            if not np.array_equal(prof.p_lay.detach().cpu().numpy(), p_lay_np):
                raise ValueError("RTTOV cloud builder changed the declared pressure centers")
            if not np.array_equal(prof.p_half.detach().cpu().numpy(), p_half_np):
                raise ValueError("RTTOV cloud builder changed native/reference interfaces")
            if len(t_np) != len(p_half_np) - 1 or not np.array_equal(p_lay_np[-39:], native["p_pa"][::-1] / 100.0):
                raise ValueError("extended grid does not preserve all native centers")
            # Above-native cloud fields are explicitly clear. The 39 native suffix is
            # the direct output of model_to_rttov_tensors on the same native pressures.
            ptop = p_half_np[-40]
            above = torch.as_tensor(p_lay_np < ptop, dtype=torch.float64)
            cloud_fields = [prof.clw, prof.ciw, prof.deff_liq, prof.deff_ice, prof.cfrac]
            cloud_fields = [f * (1.0 - above) for f in cloud_fields]
            prof = prof._replace(clw=cloud_fields[0], ciw=cloud_fields[1],
                                 deff_liq=cloud_fields[2], deff_ice=cloud_fields[3], cfrac=cloud_fields[4])

            from kdm6.obs.model_profile_builder import qv_to_q_ppmv_moist
            q2_moist = qv_to_q_ppmv_moist(torch.tensor(native["surface"]["Q2"], **F64), gas_units=2,
                                          qv_convention="mixing_ratio_kgkg_dry")
            surface = dict(
                skin=dict(surftype=1, watertype=1, t=native["surface"]["TSK"], salinity=35.0,
                          foam_fraction=0.0, snow_fraction=0.0, fastem=[3.0, 5.0, 15.0, 0.1, 0.3]),
                near_surface=dict(t2m=native["surface"]["T2"], q2m=float(q2_moist),
                                  wind_u10m=native["surface"]["U10"], wind_v10m=native["surface"]["V10"],
                                  wind_fetch=0.0))
            case_fixture = args.output_root / f"fixture_{ti:02d}"
            shutil.copytree(fixture, case_fixture)
            staged_fixture_modes = stage_thermal_only_fixture(case_fixture)
            atm = case_fixture / "in/profiles/001/atm"
            write_vector(atm / "p_half.txt", p_half_np)
            write_vector(atm / "p.txt", p_lay_np)
            write_vector(atm / "t.txt", t_np)
            write_vector(atm / "q.txt", q_np)
            write_vector(atm / "o3.txt", o3_np)
            write_vector(atm / "co2.txt", co2_np)
            icfg = RttovInputConfig(coef_id="retained-GK2A-AMI-cloud", channels=CHANNELS,
                                    geometry=geo, surface=surface)
            run_k = make_live_run_k(args.output_root / f"case_{ti:02d}",
                                    fixture_case_dir=case_fixture, solar_channels=(),
                                    ami_kma_bt=True)
            bt_t, rq_t = RttovObsOp.apply(run_k, icfg, prof.t_lay, prof.q_lay,
                                          prof.p_lay, prof.p_half, *cloud_fields)
            executed_namelist = args.output_root / f"case_{ti:02d}" / "out" / "rttov_test.txt"
            executed_solar_flags = re.findall(
                r"(?im)^\s*defn%opts%rt_all%solar\s*=\s*([^!\n]+)",
                executed_namelist.read_text())
            if [v.strip().rstrip(",").upper() for v in executed_solar_flags] != [".FALSE."]:
                raise ValueError(f"executed RTTOV case is not explicitly solar-disabled at {stamp}")
            executed_atm = args.output_root / f"case_{ti:02d}" / "in/profiles/001/atm"
            executed_simple_cloud = executed_atm / "simple_cloud.txt"
            simple_text = executed_simple_cloud.read_text()
            ctp_match = re.search(r"(?im)^\s*ctp\s*=\s*([^!\n]+)", simple_text)
            frac_match = re.search(r"(?im)^\s*cfraction\s*=\s*([^!\n]+)", simple_text)
            if (ctp_match is None or frac_match is None
                    or float(ctp_match.group(1).strip()) != staged_fixture_modes["original_simple_cloud_ctp_hPa"]
                    or float(frac_match.group(1).strip()) != 0.0):
                raise ValueError(f"executed RTTOV case inherited a nonzero simple-cloud fraction at {stamp}")
            executed_profile_arrays = {
                "p.txt": np.loadtxt(executed_atm / "p.txt", dtype=np.float64),
                "p_half.txt": np.loadtxt(executed_atm / "p_half.txt", dtype=np.float64),
                "t.txt": np.loadtxt(executed_atm / "t.txt", dtype=np.float64),
                "q.txt": np.loadtxt(executed_atm / "q.txt", dtype=np.float64),
                "o3.txt": np.loadtxt(executed_atm / "o3.txt", dtype=np.float64),
                "co2.txt": np.loadtxt(executed_atm / "co2.txt", dtype=np.float64),
            }
            expected_profile_arrays = {"p.txt": p_lay_np, "p_half.txt": p_half_np,
                                       "t.txt": t_np, "q.txt": q_np,
                                       "o3.txt": o3_np, "co2.txt": co2_np}
            if any(not np.array_equal(executed_profile_arrays[name], expected_profile_arrays[name])
                   for name in expected_profile_arrays):
                raise ValueError(f"RTTOV case profile files differ from declared T/Q/P inputs at {stamp}")
            native_p_hpa = native["p_pa"][::-1] / 100.0
            native_ph_hpa = native["p8w_pa"][::-1].astype(np.float64) / 100.0
            native_t_input = t_np[-39:]
            native_q_input = q_np[-39:]
            if not (np.array_equal(executed_profile_arrays["p.txt"][-39:], native_p_hpa)
                    and np.array_equal(executed_profile_arrays["p_half.txt"][-40:], native_ph_hpa)
                    and np.array_equal(executed_profile_arrays["t.txt"][-39:], native_t_input)
                    and np.array_equal(executed_profile_arrays["q.txt"][-39:], native_q_input)):
                raise ValueError(f"RTTOV executed input lost native P/P_HALF/T/Q suffix at {stamp}")
            bt = bt_t.detach().cpu().numpy().reshape(9)
            rq = rq_t.detach().cpu().numpy().reshape(9)
            if not np.isfinite(bt).all() or not np.isfinite(rq).all():
                raise ValueError(f"non-finite RTTOV output at {stamp}")
            frames.append(dict(index=ti, valid_time=stamp, bt_K=bt.tolist(), rad_quality=rq.tolist(),
                               residual_model_minus_observation_K=(bt - np.asarray(obs["bt_K"])).tolist(),
                               native_center_lat_lon=[native["lat"], native["lon"]],
                               xland=native["xland"], seaice=native["seaice"],
                               dry_density_policy="fixed per saved frame: rho_m/(1+qv_entry); EOS-derived rho_m from P+PB, THM, QVAPOR",
                               native_pressure_centers_hPa=native_p_hpa.tolist(),
                               native_pressure_interfaces_hPa=native_ph_hpa.tolist(),
                               native_t_layer_K=t_np[-39:].tolist(), native_q_layer_ppmv_moist=q_np[-39:].tolist(),
                               native_layer_centers_preserved=True, native_interfaces_preserved=True,
                               background_layers_above_native_top=len(p_lay_np)-39,
                               model_surface=native["surface"], surface_q2_ppmv_moist=float(q2_moist),
                               trace_gas_endpoint_diagnostics=trace_gas_diagnostics,
                               geometry=geo, geometry_assumptions=geo_assumption,
                               rttov_solar_enabled=False, rttov_solar_channel_ids=[],
                               rttov_coefficient_path=str(coefficient_path),
                               rttov_coefficient_sha256=coefficient_sha256,
                               rttov_coefficient_type_by_channel={str(c): coefficient_channel_types[c] for c in CHANNELS},
                               staged_fixture_rttov_test_sha256=staged_fixture_modes["solar_namelist_sha256"],
                               staged_fixture_simple_cloud_sha256=staged_fixture_modes["simple_cloud_sha256"],
                               staged_fixture_simple_cloud_ctp_hPa=staged_fixture_modes["original_simple_cloud_ctp_hPa"],
                               original_fixture_simple_cloud_fraction=staged_fixture_modes["original_simple_cloud_fraction"],
                               staged_simple_cloud_fraction=staged_fixture_modes["staged_simple_cloud_fraction"],
                               executed_simple_cloud_path=str(executed_simple_cloud),
                               executed_simple_cloud_sha256=sha256(executed_simple_cloud),
                               executed_simple_cloud_ctp_hPa=float(ctp_match.group(1).strip()),
                               executed_simple_cloud_fraction=float(frac_match.group(1).strip()),
                               executed_rttov_test_path=str(executed_namelist),
                               executed_rttov_test_sha256=sha256(executed_namelist),
                               executed_rttov_solar_flag=executed_solar_flags[0].strip(),
                               executed_profile_inputs={name: dict(path=str(executed_atm / name),
                                   sha256=sha256(executed_atm / name)) for name in executed_profile_arrays},
                               executed_native_input_match=dict(p_centers_hPa=True,
                                   p_interfaces_hPa=True, t_centers_K=True, q_centers_ppmv_moist=True),
                               rttov_run_assets=dict(executable_command_path=rttov_executable_command_path,
                                   executable_resolved_path=str(rttov_executable_path),
                                   executable_sha256=rttov_executable_sha_before,
                                   run_script_path=str(args.output_root / f"case_{ti:02d}" / "out/run.sh"),
                                   run_script_sha256=sha256(args.output_root / f"case_{ti:02d}" / "out/run.sh"),
                                   run_stdout_sha256=sha256(args.output_root / f"case_{ti:02d}" / "out/run.stdout.log"),
                                   run_stderr_sha256=sha256(args.output_root / f"case_{ti:02d}" / "out/run.stderr.log"),
                                   rttov_test_log_sha256=sha256(args.output_root / f"case_{ti:02d}" / "out/rttov_test.log"),
                                   child_exit_code=0,
                                   child_exit_code_basis="rttov_runner._run_case_fresh raises on nonzero exit; BT/K parse returned for this frame"),
                               model_diagnostics=column_diagnostics(native, t_np[-39:][::-1].copy()),
                               fixture_case_hashes={str(p.relative_to(case_fixture)): sha256(p) for p in sorted(case_fixture.rglob("*")) if p.is_file()}))
            # The live run's case output is retained for actual KMA transform audit,
            # but remove its copied fixture to avoid duplicating the large reference set.
            shutil.rmtree(case_fixture)

    rq_matrix = np.asarray([f["rad_quality"] for f in frames], dtype=np.float64)
    bt_matrix = np.asarray([f["bt_K"] for f in frames], dtype=np.float64)
    common = np.asarray(obs["dqf"], dtype=np.float64) == 0
    common &= np.all(rq_matrix == 0, axis=0)
    costs = []
    for frame in frames:
        pred = torch.as_tensor(frame["bt_K"], **F64).reshape(1, 9)
        m = torch.as_tensor(common, dtype=torch.float64).reshape(1, 9)
        cost = compute_obs_loss(pred, {"bt": y_bt}, m, 1.0, delta=HUBER_DELTA)
        costs.append(float(cost.detach()))
    for frame in frames:
        residual = np.asarray(frame["bt_K"]) - np.asarray(obs["bt_K"])
        standardized_residual = residual / 1.0  # sigma_K=1.0
        contribution = np.where(np.abs(standardized_residual) <= HUBER_DELTA,
                                0.5 * standardized_residual * standardized_residual,
                                HUBER_DELTA * (np.abs(standardized_residual) - 0.5 * HUBER_DELTA))
        frame["common_support_huber_contribution_dimensionless"] = np.where(common, contribution, 0.0).tolist()
        frame["common_support"] = common.tolist()
    if (sha256(OBS_RESULT) != obs_start_sha or sha256(GEOM_RESULT) != geo_start_sha
            or sha256(args.run_receipt) != receipt_start_sha or sha256(forecast_path) != forecast_start_sha):
        raise RuntimeError("native forecast, run receipt, or retained obs geometry changed during comparison")
    p8w_source_sha_after = sha256(WRF_P8W_SOURCE)
    if p8w_source_sha_after != p8w_source_sha_before or p8w_source_sha_after != WRF_P8W_EXPECTED_SHA256[str(WRF_P8W_SOURCE)]:
        raise RuntimeError("selected WRF P8W source changed during comparison")
    rttov_executable_sha_after = sha256(rttov_executable_path)
    if rttov_executable_sha_after != rttov_executable_sha_before:
        raise RuntimeError("RTTOV executable changed during the eight-frame comparison")
    coefficient_sha256_after = sha256(coefficient_path)
    hydrotable_sha256_after = sha256(hydrotable_path)
    runner_source_sha_after = sha256(runner_source_path)
    if (coefficient_sha256_after != coefficient_sha256
            or hydrotable_sha256_after != hydrotable_sha256
            or runner_source_sha_after != runner_source_sha_before):
        raise RuntimeError("RTTOV assets or comparison runner source changed during evaluation")
    runtime_source_hashes_end = {str(Path(module.__file__).resolve().relative_to(ORACLE_ROOT.resolve())):
                                 sha256(Path(module.__file__)) for module in imported_modules}
    if runtime_source_hashes_end != runtime_source_hashes:
        raise RuntimeError("an imported Python runtime source file changed during RTTOV calls")
    diagnostic_only = bool(args.failed_run_artifact_diagnostic)
    result = dict(schema="native8frame_kma_value_only_v1",
        status=("DIAGNOSTIC_ONLY_FAILED_NATIVE_RUN" if diagnostic_only else "COMPLETE"),
        native_run_valid=(not diagnostic_only), native_exit_code=(1 if diagnostic_only else 0),
        experiment_valid=(False if diagnostic_only else True), diagnostic_only=diagnostic_only,
        eligible_for_artifact_gates=(not diagnostic_only),
        diagnostic_scope=("value-only H of saved states from a WRF-success forecast whose launcher returned 1 and experiment_valid=false; diagnostic values cannot satisfy native-run acceptance" if diagnostic_only else None),
        native_run_lifecycle=dict(receipt_status=run_receipt.get("status"),
            runner_exit_code=(run_receipt.get("runner_result") or {}).get("exit_code", 0),
            runner_experiment_valid=(run_receipt.get("runner_result") or {}).get("experiment_valid", True),
            model_completed_flag=(run_receipt.get("runner_result") or {}).get("model_completed_flag", True),
            wrf_success_complete_observed=(run_receipt.get("runner_result") or {}).get("wrf_success_complete_observed", True),
            mpi_abnormal_termination_observed=(run_receipt.get("runner_result") or {}).get("mpi_abnormal_termination_observed", False),
            native_runner_invalid_reasons=(run_receipt.get("runner_result") or {}).get("invalid_reasons", [])),
        overall_fatal_or_error_lines_observed=run_receipt.get("fatal_or_error_lines_observed"),
        wrapper_wrf_fatal_lines_observed=(run_receipt.get("runner_result") or {}).get("wrf_fatal_lines_observed"),
        rttov_execution_status="completed_for_all_eight_frames",
        rttov_frames_completed=len(frames),
        native_run_id=run_receipt["run_id"], forecast_path=str(forecast_path),
        forecast_sha256=sha256(forecast_path), run_receipt_sha256=sha256(args.run_receipt),
        forecast_times=times_expected, selected_native_j_i_0based=[J, I],
        selected_native_lat_lon=frames[0]["native_center_lat_lon"],
        selected_ami_row_col_0based=[OBS_ROW, OBS_COL],
        selected_ami_lat_lon=obs["ami_lat_lon"],
        ami_center_vs_native_center_distance_m=obs["center_distance_from_viirs_m"],
        time_scope="conditional nominal comparison only: AMI pixel UTC/time and pixel acquisition time are not verified; no collocation claim",
        observation_result_path=str(OBS_RESULT), observation_result_sha256=sha256(OBS_RESULT),
        observation_candidate_source_sha256=obs["producer_sha256"], observation_bt_K=obs["bt_K"],
        observation_dqf=obs["dqf"], channels=obs["channels"], rttov_channel_ids=list(CHANNELS),
        normalized_dry=True, dry_number=True, huber_delta=HUBER_DELTA, sigma_K=1.0, bias_K=0.0,
        fixed_common_support_channel_indices_0based=np.flatnonzero(common).tolist(),
        fixed_common_support_rttov_channels=[CHANNELS[k] for k in np.flatnonzero(common)],
        common_support_count=int(common.sum()),
        excluded_from_common_support_by_any_rttov_quality=[CHANNELS[k] for k in range(9) if not common[k]],
        cost_sum_huber_all_eight_same_support=costs,
        model_bt_K=bt_matrix.tolist(), model_rad_quality=rq_matrix.tolist(),
        per_frame=frames, geometry=geo, geometry_assumptions=geo_assumption,
        sun_geometry_assumption="solar angles are set to (0,0); the executed per-frame RTTOV namelist is checked for rt_all%solar=.FALSE., making those angles unconsumed",
        surface_assumptions=dict(ocean_salinity_psu=35.0, foam_fraction=0.0, snow_fraction=0.0,
            fastem=[3.0,5.0,15.0,0.1,0.3], watertype=1, wind_fetch_m=0.0,
            wind_fetch_basis="thermal-only; no solar channels; zero is explicit, not measured",
            rttov_solar_enabled=False, rttov_solar_channel_ids=[], solar_angles=[0.0,0.0],
            simple_cloud_fraction_fallback=0.0,
            simple_cloud_ctp_retained_but_no_fraction="per-frame copied simple_cloud.txt retains CTP while setting cfraction=0; explicit hydro_frac.txt is the model cloud-fraction input",
            surface_tskin_t2m_q2_wind_hgt_from_each_native_saved_frame=True),
        background_profile_source=str(REF_FIXTURE / "in/profiles/001/atm"),
        background_profile_sha256=fixture_hashes, background_assumption="T/Q from the original RTTOV AMI cloud-fixture reference are interpolated only above each frame's native top; native T/Q centers and pressure faces are preserved. O3/CO2 use the same reference profiles across the extended grid because the saved model state has no O3/CO2 fields.",
        trace_gas_interpolation=dict(source="original RTTOV AMI cloud fixture", variables=["O3", "CO2"],
            pressure_bounds_hPa=[float(np.min(ref["p"])), float(np.max(ref["p"]))],
            method="numpy.interp in log-pressure with constant endpoint values outside the source bounds; per-frame clamp counts are recorded"),
        pressure_interface_method="Python REAL(4) transcription of calc_p8w in the selected isolated WRF source using saved frame P/PB/PH/PHB/FNM/FNP; the host Fortran routine was not executed on these frames; no C5 pressure/profile fallback",
        p8w_source=dict(path=str(WRF_P8W_SOURCE), selection_kind=WRF_P8W_SOURCE_KIND,
            expected_sha256=WRF_P8W_EXPECTED_SHA256[str(WRF_P8W_SOURCE)],
            sha256_before=p8w_source_sha_before, sha256_after=p8w_source_sha_after,
            execution_claim="source used to transcribe the Python interface calculation; raw host calc_p8w was not executed"),
        rho_d_method="existing frame-reader EOS reconstruction per saved frame; no shared initial-condition density and no live-density AD",
        native_precision_contract="Native P centers and EOS density match frame_reader's float64-first P+PB sum on stored REAL(4) fields; native P8W interfaces are produced by a Python REAL(4) transcription of the selected source calc_p8w operations, which sum P+PB in REAL(4); the host Fortran routine was not executed. THM/QVAPOR reconstruction uses float64 arithmetic on stored REAL(4) fields.",
        no_kdm_step=True, no_optimizer=True, no_da_window=True, no_fd=True,
        no_full_forecast_claim=True, physical_srf_compatibility_approved=False,
        kma_coordinate_approved=False, science_approved=False,
        source_paths=dict(native_forecast_runner="/private/tmp/KDM6AD-viirs-native-run-20261007",
            oracle_root=str(ORACLE_ROOT), gk2a_geometry_source=str(OBS_ROOT / "harness/evidence/VIIRS_geometry_source_2026-10-07.py"),
            core_p8w_source=str(WRF_P8W_SOURCE)),
        comparison_runner_source=dict(path=str(runner_source_path),
            sha256_before=runner_source_sha_before, sha256_after=runner_source_sha_after,
            snapshot_path=str(runner_snapshot_path), snapshot_sha256=sha256(runner_snapshot_path)),
        observation_source_files=obs["ami_metadata"]["source_files"],
        ami_time_metadata=obs["ami_metadata"],
        source_hashes=dict(runtime_python=runtime_source_hashes,
            gk2a_geometry_helper=sha256(geometry_source), p8w_selected_source_before=p8w_source_sha_before,
            p8w_selected_source_after=p8w_source_sha_after,
            rttov_coefficients=coefficient_sha256,
            rttov_hydrotable_before=hydrotable_sha256, rttov_hydrotable_after=hydrotable_sha256_after,
            rttov_executable_before=rttov_executable_sha_before,
            rttov_executable_after=rttov_executable_sha_after,
            comparison_runner_before=runner_source_sha_before, comparison_runner_after=runner_source_sha_after,
            ami_candidate_source=sha256(OBS_ROOT / "harness/evidence/VIIRS_AMI_candidate_source_2026-10-07.py"),
            ami_candidate_result=obs_start_sha, viirs_geometry_result=geo_start_sha,
            ami_calibration=sha256(calibration_file)),
        software=dict(python=sys.version, numpy=np.__version__, torch=torch.__version__, netcdf4=netCDF4.__version__),
        rttov_execution_assets=dict(coefficient_path=str(coefficient_path),
            coefficient_sha256=coefficient_sha256, rttov_executable_command_path=rttov_executable_command_path,
            rttov_executable_resolved_path=str(rttov_executable_path),
            rttov_executable_sha256_before=rttov_executable_sha_before,
            rttov_executable_sha256_after=rttov_executable_sha_after,
            hydrotable_path=str(hydrotable_path), hydrotable_sha256_before=hydrotable_sha256,
            hydrotable_sha256_after=hydrotable_sha256_after,
            comparison_runner_path=str(runner_source_path), comparison_runner_sha256_before=runner_source_sha_before,
            comparison_runner_sha256_after=runner_source_sha_after,
            output_cases=[f"case_{i:02d}" for i in range(8)],
            child_exit_code=0,
            child_exit_code_basis="each checked RTTOV runner call returned BT/K/quality; nonzero exit raises"),
        immutable_fixture_hashes=fixture_hashes)
    out = args.output_root / ("native8frame_failed_run_artifact_diagnostic.json" if diagnostic_only
                              else "native8frame_kma_value_only.json")
    out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": result["status"], "output": str(out),
                      "native_run_valid": result["native_run_valid"],
                      "eligible_for_artifact_gates": result["eligible_for_artifact_gates"],
                      "common_support_count": result["common_support_count"],
                      "costs": costs}, indent=2))


if __name__ == "__main__":
    main()
