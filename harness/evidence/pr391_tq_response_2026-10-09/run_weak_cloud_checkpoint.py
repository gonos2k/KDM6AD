#!/usr/bin/env python3
"""One predeclared T-0.8 K local run from the already captured private NPZ."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from oracle.kdm6.runtime import kdm6_step, make_parameters
from oracle.kdm6.state import State, Forcing
from oracle.kdm6.thermo import compute_qs_water, default_thermo_params
CHECKPOINT = ROOT / "graphify-out/pr391-red/selected_column_checkpoint.npz"
OUT_NPZ = ROOT / "graphify-out/pr391-red/weak_cloud_Tminus0p8_checkpoint.npz"
OUT_JSON = Path(__file__).resolve().parent / "RESULT_weak_cloud_Tminus0p8.json"
FIELDS = ("th", "qv", "qc", "qr", "qi", "qs", "qg", "nccn", "nc", "ni", "nr", "bg")
K = 3
DTYPE = torch.float64


def main():
    z = np.load(CHECKPOINT)
    base = State(*(torch.tensor(z[f"state_in_baseline_{name}"], dtype=DTYPE).reshape(1, -1)
                   for name in FIELDS))
    f = Forcing(
        rho=torch.tensor(z["rho_m_forcing_native_bottomup_kg_m3"], dtype=DTYPE).reshape(1, -1),
        pii=torch.tensor(z["pii_native_bottomup"], dtype=DTYPE).reshape(1, -1),
        p=torch.tensor(z["p_center_native_bottomup_Pa"], dtype=DTYPE).reshape(1, -1),
        delz=torch.tensor(z["delz_native_bottomup_m"], dtype=DTYPE).reshape(1, -1))
    s = base._replace(th=base.th.clone(), qv=base.qv.clone())
    s.th[0, K] -= 0.8 / f.pii[0, K]
    t_entry = s.th * f.pii
    qs_entry = compute_qs_water(t_entry, f.p, params=default_thermo_params())
    rh_entry = s.qv / qs_entry
    sin = State(*(x.detach().clone().requires_grad_(True) for x in s))
    xland = torch.tensor([float(z["xland"][0])], dtype=DTYPE)
    sout, handle = kdm6_step(sin, f, params=make_parameters(dtype=DTYPE), dt=20.0,
                             value_only=False, xland=xland, ncmin_land=10.0,
                             ncmin_sea=10.0, normalized_dry=True)
    rho_d_runtime = f.rho / (1.0 + s.qv)
    ct_g_m3 = (sout.qc + sout.qi) * rho_d_runtime * 1000.0
    cfrac = torch.where(ct_g_m3 > 1.0e-6,
                        torch.full_like(ct_g_m3, 1.0-1.0e-6),
                        torch.zeros_like(ct_g_m3))
    dirs = []
    for name in ("physical_T_K", "dry_qv_kgkg"):
        tangent = State(*(torch.zeros_like(x) for x in sin))
        if name == "physical_T_K":
            dth = torch.zeros_like(sin.th)
            dth[0, K] = 1.0 / f.pii[0, K]
            tangent = tangent._replace(th=dth)
        else:
            dq = torch.zeros_like(sin.qv)
            dq[0, K] = 1.0
            tangent = tangent._replace(qv=dq)
        jt = handle.jvp(tangent)
        vals = [jt.qv[0,K], jt.qc[0,K], jt.th[0,K]*f.pii[0,K], jt.nc[0,K], jt.nccn[0,K]]
        dirs.append({"direction": name, "input_direction":
                     ("dtheta=1/pii at selected native level; qv unchanged" if name == "physical_T_K"
                      else "dqv=1 at selected native level; theta unchanged"),
                     "selected_output_order": ["qv", "qc", "T", "nc_dry_specific", "nccn_dry_specific"],
                     "jvp": [float(v) for v in vals],
                     "all_selected_jvp_finite": bool(torch.isfinite(torch.stack(vals)).all())})
    handle.close()
    input_state = {name: x.detach().cpu().numpy()[0] for name, x in zip(FIELDS, s)}
    output_state = {name: x.detach().cpu().numpy()[0] for name, x in zip(FIELDS, sout)}
    arrays = {f"state_in_{name}": val for name, val in input_state.items()}
    arrays.update({f"state_out_{name}": val for name, val in output_state.items()})
    arrays.update({"rho_m_forcing": z["rho_m_forcing_native_bottomup_kg_m3"],
                   "pii": z["pii_native_bottomup"], "p_center_Pa": z["p_center_native_bottomup_Pa"],
                   "delz_m": z["delz_native_bottomup_m"],
                   "p_interface_wrf_Pa": z["p_interface_wrf_native_bottomup_Pa"],
                   "rho_d_optical_reference": z["rho_d_optical_reference_native_bottomup_kg_m3"],
                   "rho_d_runtime_entry": rho_d_runtime.detach().cpu().numpy()[0]})
    np.savez_compressed(OUT_NPZ, **arrays)
    result = {"input_checkpoint": str(CHECKPOINT.relative_to(ROOT)),
              "input_source": "cached native baseline NPZ only; no forecast read or hash",
              "source_saved_forecast_sha256_reference": "ac73e382b3102a9fdad3cd5c9e4ec46b6b25a5997dba53aa1b369b0b9ac8153e",
              "case": {"time": "2025-07-19_05:55:40", "wrf_j_1based": 87, "wrf_i_1based": 49,
                       "wrf_k_bottomup_0based": K, "delta_T_K": -0.8,
                       "theta_delta_K": float(-0.8/f.pii[0,K]), "qv_factor": 1.0,
                       "dt_s": 20.0, "normalized_dry": True, "nccn_policy": "stored value from baseline"},
              "selected_entry": {"T_K": float(s.th[0,K]*f.pii[0,K]),
                                 "qv_kgkg_dry": float(s.qv[0,K]),
                                 "p_Pa": float(f.p[0,K]),
                                 "qs_water_kgkg_dry": float(qs_entry[0,K]),
                                 "q_over_qs_water": float(rh_entry[0,K]),
                                 "sw_percent": float((rh_entry[0,K]-1.0)*100.0),
                                 "activation_gate_sw_gt_zero": bool((rh_entry[0,K]-1.0)*100.0 > 0.0)},
              "selected_output": {"T_K": float((sout.th[0,K]*f.pii[0,K]).detach()),
                                  "theta_K": float(sout.th[0,K].detach()),
                                  "qv_kgkg_dry": float(sout.qv[0,K].detach()),
                                  "qc_kgkg_dry": float(sout.qc[0,K].detach()),
                                  "qi_kgkg_dry": float(sout.qi[0,K].detach()),
                                  "nc_dry_specific": float(sout.nc[0,K].detach()),
                                  "nccn_dry_specific": float(sout.nccn[0,K].detach()),
                                  "condensate_g_m3_using_runtime_entry_rho_dry": float(ct_g_m3[0,K].detach()),
                                  "derived_binary_cfrac": float(cfrac[0,K].detach()),
                                  "cloud_positive_layers_1based": (torch.nonzero(sout.qc[0] > 0, as_tuple=False).flatten()+1).tolist()},
              "all_output_state_fields_finite": all(bool(torch.isfinite(v).all()) for v in sout),
              "whole_runtime_jvp": {"operator": "one 20s whole kdm6_step(normalized_dry=True) call; no observer/diagnostic trace",
                                    "selected_layer": K+1, "directions": dirs,
                                    "derivative_scope": "whole map at this point; no FD/VJP or all-branch census performed for this supplemental point"},
              "checkpoint_npz": str(OUT_NPZ.relative_to(ROOT)),
              "checkpoint_keys": sorted(arrays)}
    OUT_JSON.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(json.dumps({"output_json": str(OUT_JSON), "output_npz": str(OUT_NPZ),
                      "qc": result["selected_output"]["qc_kgkg_dry"],
                      "cfrac": result["selected_output"]["derived_binary_cfrac"],
                      "finite": result["all_output_state_fields_finite"],
                      "jvp_finite": [d["all_selected_jvp_finite"] for d in dirs]}, indent=2))


if __name__ == "__main__":
    main()
