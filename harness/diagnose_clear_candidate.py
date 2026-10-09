#!/usr/bin/env python3
"""Reproduce the saved case_00 native-column clear/saturation diagnostic.

Reads the archived RTTOV inputs from the evidence zip and independently checks
their native suffix against the public enriched receipt. It does not run KDM6,
RTTOV, a forecast, or an optimizer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import zipfile
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from oracle.kdm6.da_cvt import make_default_cvt  # noqa: E402
from oracle.kdm6.state import State  # noqa: E402
from oracle.kdm6.thermo import (  # noqa: E402
    compute_qs_ice, compute_qs_water, default_thermo_params,
)

ZIP_DEFAULT = ROOT / "harness/evidence/NATIVE_target_artifact_receipts_2026-10-08.zip"
PUBLIC_DEFAULT = ROOT / "harness/evidence/native358_artifact_diag_2026-10-08/results/native8frame_failed_run_artifact_diagnostic_enriched.json"
FORECAST_DEFAULT = Path("/private/tmp/KDM6AD-viirs-native-run-20261007/target_case_055540_055800/runs/mp337_viirs_norm2_dry1_055540_055800_358min_hist0_20261008_064206_p28793/klfs_lc05_fcst.202507190000")
OUT_DEFAULT = ROOT / "harness/evidence/pr391_clear_state_2026-10-09/result.json"

PREFIX = "rttov_retry2/case_00/in/profiles/001/"
MEMBERS = {
    "p_hpa": PREFIX + "atm/p.txt",
    "t_k": PREFIX + "atm/t.txt",
    "q_ppmv_moist": PREFIX + "atm/q.txt",
    "gas_units": PREFIX + "gas_units.txt",
    "gas_units_log": "rttov_retry2/case_00/out/gas_units.log",
    "channels": "rttov_retry2/case_00/in/channels.txt",
    "lprofiles": "rttov_retry2/case_00/in/lprofiles.txt",
    "hydro_content": PREFIX + "atm/hydro.txt",
    "hydro_fraction": PREFIX + "atm/hydro_frac.txt",
    "hydro_deff": PREFIX + "atm/hydro_deff.txt",
}
MWATER = 18.01528
MDRY = 28.9647


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def vec(data: bytes) -> np.ndarray:
    return np.fromstring(data.decode("ascii"), sep=" ", dtype=np.float64)


def numpy_qs(t: np.ndarray, p_pa: np.ndarray, tp) -> tuple[np.ndarray, np.ndarray]:
    """Independent NumPy transcription of thermo.py's water/ice equations."""
    tr = tp.ttp / np.maximum(t, 1.0)
    ew_raw = tp.psat * np.exp(np.log(tr) * tp.xa) * np.exp(tp.xb * (1.0 - tr))
    ei_raw = tp.psat * np.exp(np.log(tr) * tp.xai) * np.exp(tp.xbi * (1.0 - tr))
    ew = np.minimum(ew_raw, 0.99 * p_pa)
    ei = np.minimum(np.where(t < tp.ttp, ei_raw, ew_raw), 0.99 * p_pa)
    qw = np.maximum(tp.ep2 * ew / np.maximum(p_pa - ew, tp.qmin), tp.qmin)
    qi = np.maximum(tp.ep2 * ei / np.maximum(p_pa - ei, tp.qmin), tp.qmin)
    return qw, qi


def bisection_saturation(t0: float, p: float, q: float, tp) -> float:
    """Solve qs_water(T,p)=q below t0; saturation is monotone in this bracket."""
    lo, hi = 120.0, t0
    def f(t: float) -> float:
        a, _ = numpy_qs(np.array([t]), np.array([p]), tp)
        return float(a[0] - q)
    if f(lo) >= 0.0 or f(hi) <= 0.0:
        raise ValueError("water saturation root is not bracketed on [120 K, T0]")
    for _ in range(100):
        mid = (lo + hi) / 2.0
        if f(mid) > 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2.0


def state_tensor(arrays: dict[str, np.ndarray]) -> State:
    return State(*(torch.tensor(arrays[k].copy(), dtype=torch.float64).reshape(1, -1)
                   for k in ("th", "qv", "qc", "qr", "qi", "qs", "qg",
                             "nccn", "nc", "ni", "nr", "bg")))


def active_counts(sigma: State) -> dict[str, int]:
    return {name: int((getattr(sigma, name) > 0).sum().item())
            for name in State._fields}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", type=Path, default=ZIP_DEFAULT)
    ap.add_argument("--public", type=Path, default=PUBLIC_DEFAULT)
    ap.add_argument("--forecast", type=Path, default=FORECAST_DEFAULT)
    ap.add_argument("--output", type=Path, default=OUT_DEFAULT)
    args = ap.parse_args()
    if args.output.exists() or args.output.is_symlink():
        ap.error("output already exists; choose a fresh --output path to preserve the prior receipt")

    with zipfile.ZipFile(args.zip) as z:
        raw = {name: z.read(member) for name, member in MEMBERS.items()}
    p_hpa, t, qppm = (vec(raw[k]) for k in ("p_hpa", "t_k", "q_ppmv_moist"))
    if not (p_hpa.shape == t.shape == qppm.shape == (66,)):
        raise ValueError(f"expected 66 RTTOV layers, got {p_hpa.shape}, {t.shape}, {qppm.shape}")
    if "gas_units = 2" not in raw["gas_units"].decode() or "ppmv" not in raw["gas_units_log"].decode().lower():
        raise ValueError("archived gas units do not identify moist-air ppmv")
    hydro_content = vec(raw["hydro_content"])
    hydro_fraction = vec(raw["hydro_fraction"])
    hydro_deff = vec(raw["hydro_deff"])
    channels = [int(x) for x in raw["channels"].decode().split() if x.lstrip("+-").isdigit()]
    public = json.loads(args.public.read_text())
    frame = public["per_frame"][0]
    n = 39
    # RTTOV input is top-down. Its native suffix is the final 39 layers;
    # reverse it to WRF State's bottom-up k=0..38 order.
    p_native = p_hpa[-n:][::-1].copy()
    t_native = t[-n:][::-1].copy()
    q_native_ppmv = qppm[-n:][::-1].copy()
    chi_native = q_native_ppmv * 1e-6
    if not np.isfinite(np.r_[p_hpa, t, qppm]).all() or np.any(chi_native >= 1.0) or np.any(chi_native < 0.0):
        raise ValueError("profile must have finite values and a physical moist-air mole fraction in [0,1)")
    q_native = (MWATER / MDRY) * chi_native / (1.0 - chi_native)
    p_public = np.asarray(frame["native_pressure_centers_hPa"], dtype=np.float64)
    t_public = np.asarray(frame["native_t_layer_K"], dtype=np.float64)
    q_public = np.asarray(frame["native_q_layer_ppmv_moist"], dtype=np.float64)
    public_exact = (np.array_equal(p_native[::-1], p_public) and
                    np.array_equal(t_native[::-1], t_public) and
                    np.array_equal(q_native_ppmv[::-1], q_public))
    if not public_exact:
        raise ValueError("archived native P/T/Q do not match the paired public receipt")

    tp = default_thermo_params()
    p_pa = p_native * 100.0
    qs_np, qsi_np = numpy_qs(t_native, p_pa, tp)
    tt = torch.tensor(t_native.copy(), dtype=torch.float64)
    pp = torch.tensor(p_pa.copy(), dtype=torch.float64)
    qs_torch = compute_qs_water(tt, pp, params=tp).detach().numpy()
    qsi_torch = compute_qs_ice(tt, pp, params=tp).detach().numpy()
    if not np.isfinite(np.r_[p_native, t_native, q_native, qs_np, qsi_np]).all():
        raise ValueError("non-finite input or saturation result")
    if np.any(p_pa <= 0) or np.any(t_native <= 0) or np.any(q_native <= 0):
        raise ValueError("pressure, temperature, and humidity must be positive")
    abs_np_torch_water = float(np.max(np.abs(qs_np - qs_torch)))
    abs_np_torch_ice = float(np.max(np.abs(qsi_np - qsi_torch)))
    if max(abs_np_torch_water, abs_np_torch_ice) > 1e-14:
        raise AssertionError("independent NumPy formula differs materially from oracle")
    ratio = q_native / qs_np
    ratio_ice = q_native / qsi_np
    if not np.isfinite(np.r_[ratio, ratio_ice]).all():
        raise ValueError("non-finite saturation ratio")
    idx = int(np.argmax(ratio))
    # Actual vapor pressure from dry mass mixing ratio; es from same source formula.
    tr = tp.ttp / max(float(t_native[idx]), 1.0)
    es = tp.psat * math.exp(math.log(tr) * tp.xa) * math.exp(tp.xb * (1.0 - tr))
    e = p_pa[idx] * q_native[idx] / (tp.ep2 + q_native[idx])
    chi_at_max = float(q_native_ppmv[idx] * 1e-6)
    e_optics = p_pa[idx] * chi_at_max
    t_sat = bisection_saturation(float(t_native[idx]), float(p_pa[idx]), float(q_native[idx]), tp)
    cold = t_native < tp.ttp
    cold_ice_ratio = ratio_ice[cold]
    cold_ice_idx = int(np.flatnonzero(cold)[int(np.argmax(cold_ice_ratio))]) if cold.any() else None

    # Read only the selected native forecast column for correspondence/control masks.
    from netCDF4 import Dataset
    if not args.forecast.is_file():
        raise FileNotFoundError(args.forecast)
    with Dataset(args.forecast, "r") as ds:
        j, i = 86, 48
        def col(name: str) -> np.ndarray:
            values = ds.variables[name][0, :, j, i]
            if np.ma.isMaskedArray(values) and np.ma.getmaskarray(values).any():
                raise ValueError(f"{name}: selected native column contains masked values")
            result = np.asarray(values, dtype=np.float64)
            if result.shape != (39,) or not np.isfinite(result).all():
                raise ValueError(f"{name}: requires 39 finite native values")
            return result
        perturb_t, thm, qv = col("T"), col("THM"), col("QVAPOR")
        ppert, pb = col("P"), col("PB")
        p_model = ppert + pb
        pii = (p_model / 100000.0) ** (287.0 / 1004.5)
        th_model = (thm + 300.0) / (1.0 + (461.6 / 287.0) * qv)
        t_model = th_model * pii
        q_model_ppmv = (MDRY / MWATER) * qv / (1.0 + qv * (MDRY / MWATER)) * 1e6
        fields = {k: col(v) for k, v in {
            "qc": "QCLOUD", "qr": "QRAIN", "qi": "QICE", "qs": "QSNOW",
            "qg": "QGRAUP", "nccn": "QNCCN", "nc": "QNCLOUD", "ni": "QNICE",
            "nr": "QNRAIN", "bg": "QIB"}.items()}
        # `th` is the potential-temperature control state; RTTOV consumes T.
        state = state_tensor({"th": th_model, "qv": qv, **fields})
        # Strictly compare the derived physical P/T/Q back to the archived native
        # suffix before reporting projected CVT masks.
        native_parity = {
            "p_hPa_max_abs": float(np.max(np.abs(p_model / 100.0 - p_native))),
            "t_K_max_abs": float(np.max(np.abs(t_model - t_native))),
            "q_ppmv_moist_max_abs": float(np.max(np.abs(q_model_ppmv - q_native_ppmv))),
            "q_ppmv_max_abs_vs_public": float(np.max(np.abs(q_model_ppmv[::-1] - q_public))),
            "time_coordinate": str(ds.variables["Times"][0].tobytes().decode(errors="ignore").strip("\x00"))
                if "Times" in ds.variables else "not-recorded",
            "j_zero_based": j, "i_zero_based": i,
        }
        qv_pos = int(np.count_nonzero(qv > 0))
        hydro_zero = {f: bool(np.all(fields[f] == 0)) for f in ("qc", "qr", "qi", "qs", "qg")}

    # These are conversion-roundoff checks, not operational forward parity gates.
    if (native_parity["time_coordinate"] != "2025-07-19_05:55:40"
            or native_parity["p_hPa_max_abs"] != 0.0
            or native_parity["t_K_max_abs"] > 1e-10
            or native_parity["q_ppmv_moist_max_abs"] > 1e-8):
        raise ValueError("selected forecast time/P/T/Q do not correspond to archived case_00")

    _, sig_default = make_default_cvt(state)
    default_counts = active_counts(sig_default)
    # The recorded v10 path uses qv_levels=39 and conserving mass-hydrometeor
    # diagonal sigma zero. This is projected onto the case_00 column only.
    _, sig_v10_projection = make_default_cvt(
        state, qv_levels=39,
        sigma_overrides={"qc": 0.0, "qi": 0.0, "qs": 0.0},
    )
    v10_counts = active_counts(sig_v10_projection)
    if sum(default_counts.values()) != 51 or sum(v10_counts.values()) != 78:
        raise AssertionError(f"unexpected projected controls: {default_counts} / {v10_counts}")

    receipt = {
        "scope": "offline single-column thermodynamic diagnostic; no KDM6/RTTOV/optimizer/forecast execution",
        "source_identity": {
            "archive": str(args.zip), "archive_sha256": sha256(args.zip),
            "public_enriched": str(args.public), "public_sha256": sha256(args.public),
            "archive_members_sha256": {k: hashlib.sha256(v).hexdigest() for k, v in raw.items()},
            "forecast_path": str(args.forecast),
            "forecast_hash": "not read here; Red owns one before/after whole-file hash",
        },
        "profile_identity": {
            "case": "case_00", "profile": "001", "channels_ami_physical_ids": channels,
            "n_rttov_layers": 66, "n_native_layers": 39,
            "native_suffix_rttov_layer_1based": [28, 66],
            "gas_units_input": raw["gas_units"].decode().strip(),
            "gas_units_run_log_excerpt": raw["gas_units_log"].decode().strip(),
            "native_suffix_exactly_matches_public_P_T_Q": bool(public_exact),
            "arrays_order_in_this_receipt": "WRF State bottom-up k=0..38; archive native suffix reversed from RTTOV top-down",
            "saved_rttov_hydro_inputs": {
                "hydro_content_values": int(hydro_content.size),
                "hydro_content_nonzero_values": int(np.count_nonzero(hydro_content)),
                "hydro_fraction_values": int(hydro_fraction.size),
                "hydro_fraction_nonzero_values": int(np.count_nonzero(hydro_fraction)),
                "hydro_deff_values": int(hydro_deff.size),
                "hydro_deff_nonzero_values": int(np.count_nonzero(hydro_deff)),
                "hydro_deff_minmax": [float(np.min(hydro_deff)), float(np.max(hydro_deff))],
                "interpretation": "saved hydro content and fraction are all zero; deff size parameters are nonzero and do not establish condensate content",
            },
        },
        "conversion": {
            "Q_input": "ppmv over moist air, gas_units=2",
            "formula": "chi=Q_ppmv*1e-6; w_dry=(18.01528/28.9647)*chi/(1-chi)",
            "constants_source": "oracle/kdm6/obs/model_profile_builder.py exact optics writer constants _M_WATER/_M_DRY_AIR",
            "inverse_not_using_Rd_over_Rv": True,
        },
        "thermodynamics": {
            "source": "oracle/kdm6/thermo.py default_thermo_params; independent NumPy implementation and executed Torch functions",
            "executed_constants_f64": {k: float(getattr(tp, k)) for k in ("rd", "rv", "ep2", "ttp", "psat", "xa", "xb", "xai", "xbi", "qmin")},
            "f32_rounded_coefficients_are_used_by_default_thermo_params": True,
            "numpy_vs_torch_qs_water_max_abs_kgkg": abs_np_torch_water,
            "numpy_vs_torch_qs_ice_max_abs_kgkg": abs_np_torch_ice,
            "ratio_q_over_qs_water_by_RTTOV_layer_1_to_66_native_suffix_only": [None] * 27 + [float(x) for x in ratio[::-1]],
            "ratio_q_over_qs_ice_by_RTTOV_layer_1_to_66_native_suffix_only": [None] * 27 + [float(x) for x in ratio_ice[::-1]],
            "max_q_over_qs_water": float(ratio[idx]),
            "max_location": {
                "native_suffix_topdown_index_0based": 38 - idx,
                "native_suffix_topdown_position_1based": 39 - idx,
                "rttov_layer_1based": 27 + (39 - idx),
                "wrf_bottomup_k_0based": idx,
                "fortran_k_1based": idx + 1,
            },
            "at_max": {
                "p_hPa": float(p_native[idx]), "T_K": float(t_native[idx]),
                "q_ppmv_moist": float(q_native_ppmv[idx]),
                "q_dry_kgkg": float(q_native[idx]), "qs_water_kgkg": float(qs_np[idx]),
                "qs_minus_q_kgkg": float(qs_np[idx] - q_native[idx]),
                "e_over_es_from_dry_mixing_ratio_using_thermo_ep2": float(e / es),
                "e_over_es_from_archived_moist_mole_fraction": float(e_optics / es),
                "es_Pa": float(es), "e_thermo_ep2_Pa": float(e), "e_optics_mole_fraction_Pa": float(e_optics),
                "constant_p_q_water_saturation_root_T_K": t_sat,
                "cooling_to_root_K": float(t_native[idx] - t_sat),
            },
            "min_max_q_over_qs_water_native39": [float(np.min(ratio)), float(np.max(ratio))],
            "max_q_over_qs_ice": float(np.max(ratio_ice)),
            "max_q_over_qs_ice_on_T_below_ttp_branch": float(np.max(cold_ice_ratio)) if cold_ice_ratio.size else None,
            "max_cold_ice_branch_location": (None if cold_ice_idx is None else {
                "native_suffix_topdown_index_0based": 38 - cold_ice_idx,
                "native_suffix_topdown_position_1based": 39 - cold_ice_idx,
                "rttov_layer_1based": 27 + (39 - cold_ice_idx),
                "wrf_bottomup_k_0based": cold_ice_idx,
                "fortran_k_1based": cold_ice_idx + 1,
                "temperature_K": float(t_native[cold_ice_idx]),
            }),
            "max_q_over_qs_ice_location": {
                "native_suffix_topdown_index_0based": 38 - int(np.argmax(ratio_ice)),
                "native_suffix_topdown_position_1based": 39 - int(np.argmax(ratio_ice)),
                "rttov_layer_1based": 27 + (39 - int(np.argmax(ratio_ice))),
                "wrf_bottomup_k_0based": int(np.argmax(ratio_ice)),
                "fortran_k_1based": 1 + int(np.argmax(ratio_ice)),
                "temperature_K": float(t_native[int(np.argmax(ratio_ice))]),
                "ice_branch_active_T_below_ttp": bool(t_native[int(np.argmax(ratio_ice))] < tp.ttp),
            },
            "all_native_layer_results_finite_and_positive": True,
            "qs_is_saturation_mixing_ratio_not_vapor_pressure_ratio": True,
        },
        "selected_actual_case00_state": {
            **native_parity,
            "input_grid_indices_zero_based": {"j": 86, "i": 48},
            "qv_positive_layers": qv_pos,
            "direct_hydrometeor_mass_fields_zero": hydro_zero,
            "qnccn_positive_layers": int(np.count_nonzero(fields["nccn"] > 0)),
            "cvt_control_coordinate": "th is potential temperature; RTTOV native T is th*Exner. WRF T is a perturbation; not the CVT th variable.",
            "default_make_default_cvt_active_count_projection": default_counts,
            "default_make_default_cvt_total_active_projection": sum(default_counts.values()),
            "v10_normalized_conserving_qv39_mask_projection": v10_counts,
            "v10_projection_total_active": sum(v10_counts.values()),
            "projection_note": "These active counts apply the documented CVT builder/mode to this archived state only; v10 report was a separate 00:00 run, not this target case_00/05:55:40 optimizer execution.",
            "indirect_cloud_creation_note": "Zero-background hydro controls and eps=0 pin direct hydro rows; active th/qv controls can still create condensate through model processes.",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({
        "output": str(args.output), "public_exact": public_exact,
        "max_ratio": receipt["thermodynamics"]["max_q_over_qs_water"],
        "max_location": receipt["thermodynamics"]["max_location"],
        "gap_kgkg": receipt["thermodynamics"]["at_max"]["qs_minus_q_kgkg"],
        "cooling_K": receipt["thermodynamics"]["at_max"]["cooling_to_root_K"],
        "default_active": sum(default_counts.values()), "v10_projected_active": sum(v10_counts.values()),
        "native_parity": native_parity,
    }, indent=2))


if __name__ == "__main__":
    main()
