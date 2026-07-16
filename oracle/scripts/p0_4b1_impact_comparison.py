#!/usr/bin/env python3
"""P0-4b.1 component 4 — legacy vs conservative impact comparison (P0-4b.2 rev).

Runs the legacy_reference and conservative_experiment sedimentation on the SAME
inputs and reports where the previously-vanishing mass goes: surface
precipitation, per-level hydrometeor profiles, species, numbers, graupel volume
proxy, gradients — for one step (synthetic heavy rain) and a 1 h / 3 h
microphysics-window trajectory on real LC05 columns (prescribed forcing, with
the operational xland + ncmin_land=100 / ncmin_sea=10 configuration).

All-sky BT / observation-cost comparison requires the local RTTOV runtime; if
unavailable this script records "deferred" rather than fabricating numbers.

Output: docs/reports/p0_4b1_impact_comparison.json
Analysis-only; no repo behavior change.
"""
import hashlib
import json
import math
import pathlib
import platform
import subprocess
import sys

import torch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from kdm6.state import State, Forcing                              # noqa: E402
from kdm6.runtime import _kdm6_pure, make_parameters               # noqa: E402
from kdm6.water_budget import kdm6_step_with_water_budget          # noqa: E402
from kdm6.sed_conservative import kdm6_step_conservative_experiment  # noqa: E402

FCST = "/Users/yhlee/KDM6AD-k/host/lc05_da_run/klfs_lc05_fcst.202507190000"
MANIFEST = "/Users/yhlee/KDM6AD-k/host/lc05_da_run/klfs_lc05_fcst.RESTORE_MANIFEST.json"
OUT = pathlib.Path(__file__).resolve().parents[2] / "docs" / "reports"
HYDRO = ("qr", "qs", "qg", "qi")
# Operational LC05 all-sky/DA land-sea configuration (windows only; the
# synthetic one-step case has no land/sea geography)
NCMIN_LAND = 100.0
NCMIN_SEA = 10.0


def _sha256(path, chunk=1 << 24):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def provenance():
    root = pathlib.Path(__file__).resolve().parents[2]
    code_sha = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
    return {
        "code_sha": code_sha,
        "script_sha256": _sha256(__file__),
        "trajectory": FCST,
        "trajectory_sha256": _sha256(FCST),
        "restore_manifest_sha256": _sha256(MANIFEST),
        "trajectory_provenance": ("faithful reconstruction (regenerated 3h/5-min run per "
                                  "RESTORE_MANIFEST), not the byte-identical original"),
        "torch_version": torch.__version__,
        "python_version": platform.python_version(),
        "window_dt": 300.0,
        "one_step_dt": 120.0,
        "xland_used_in_windows": True,
        "xland_used_in_one_step": False,
        "ncmin_land": NCMIN_LAND,
        "ncmin_sea": NCMIN_SEA,
    }


def _mk(cv, K):
    return torch.tensor([[v] * K for v in cv], dtype=torch.float64)


def _heavy_rain(K=4):
    s = State(th=_mk([285., 285.], K), qv=_mk([1.6e-2] * 2, K), qc=_mk([2e-3] * 2, K),
              qr=_mk([5e-3, 8e-3], K), qi=_mk([0.] * 2, K), qs=_mk([0.] * 2, K),
              qg=_mk([0.] * 2, K), nccn=_mk([1e9] * 2, K), nc=_mk([1e8] * 2, K),
              ni=_mk([0.] * 2, K), nr=_mk([1e5, 2e5], K), bg=_mk([0.] * 2, K))
    f = Forcing(rho=_mk([1.1] * 2, K), pii=_mk([0.98] * 2, K),
                p=_mk([9.5e4] * 2, K), delz=_mk([400.] * 2, K))
    return s, f


def field_stats(a, b):
    """legacy a vs conservative b: where the mass moved."""
    d = (b - a)
    return {"max_abs_diff": float(d.abs().max()), "mean_diff": float(d.mean()),
            "rel_l2": float(d.norm() / (a.norm() + 1e-300))}


def one_step_comparison():
    s, f = _heavy_rain()
    outL, budL = kdm6_step_with_water_budget(s, f, dt=120.0)
    outC, budC, attC = kdm6_step_conservative_experiment(s, f, dt=120.0)
    w = f.rho * f.delz
    rec = {
        "surface_precip_kg_m2": {
            "legacy_diag": budL.surface_precip_diag_kg_m2.tolist(),
            "conservative_actual": budC.surface_precip_diag_kg_m2.tolist(),
        },
        "column_loss_kg_m2": {
            "legacy": budL.sed_column_loss_kg_m2.tolist(),
            "conservative": budC.sed_column_loss_kg_m2.tolist(),
        },
        "closure_residual": {
            "legacy_gap": budL.sed_surface_diag_gap_kg_m2.tolist(),
            "conservative_gap": budC.sed_surface_diag_gap_kg_m2.tolist(),
        },
        "state_field_diffs": {x: field_stats(getattr(outL, x), getattr(outC, x))
                              for x in ("qr", "qs", "qg", "qi", "qc", "qv", "nr", "nc", "ni", "bg", "th")},
        "hydro_mass_retained_kg_m2": {
            "legacy": (w * (outL.qr + outL.qs + outL.qg + outL.qi)).sum(-1).tolist(),
            "conservative": (w * (outC.qr + outC.qs + outC.qg + outC.qi)).sum(-1).tolist(),
        },
        "qr_profile_col0": {"legacy": outL.qr[0].tolist(), "conservative": outC.qr[0].tolist()},
        "nan_inf": {"legacy": bool(sum(~torch.isfinite(getattr(outL, x)).all() for x in outL._fields)),
                    "conservative": bool(sum(~torch.isfinite(getattr(outC, x)).all() for x in outC._fields))},
    }
    # gradient comparison (VJP norm through each variant).
    # SCOPE (P0-4b.2): synthetic heavy-rain SINGLE-step VJP norms w.r.t.
    # (qr, qv, th) — a sensitivity-path indicator, NOT an LC05-window or
    # observation-space adjoint measurement (those remain unmeasured).
    def grad_norm(step_fn):
        s2, f2 = _heavy_rain()
        s2 = State(*(t.clone().requires_grad_(t.dtype.is_floating_point) for t in s2))
        out = step_fn(s2, f2)
        loss = sum((getattr(out, x) ** 2).sum() for x in HYDRO)
        gs = torch.autograd.grad(loss, [getattr(s2, x) for x in ("qr", "qv", "th")],
                                 allow_unused=True)
        return [float(g.norm()) if g is not None else None for g in gs]

    nL = grad_norm(lambda s2, f2: _kdm6_pure(s2, f2, make_parameters(), 120.0))
    nC = grad_norm(lambda s2, f2: kdm6_step_conservative_experiment(s2, f2, dt=120.0)[0])
    combL = math.sqrt(sum(v * v for v in nL if v is not None))
    combC = math.sqrt(sum(v * v for v in nC if v is not None))
    rec["vjp_synthetic_one_step"] = {
        "note": ("synthetic heavy-rain single-step VJP norms wrt (qr, qv, th); "
                 "LC05/observation-space adjoint impact is unmeasured"),
        "inputs": ["qr", "qv", "th"],
        "legacy": nL,
        "conservative": nC,
        "per_input_ratio": [(nC[i] / nL[i]) if (nL[i] and nC[i] is not None) else None
                            for i in range(len(nL))],
        "combined_euclidean_norm": {
            "legacy": combL, "conservative": combC,
            "ratio": (combC / combL) if combL else None,
        },
    }
    return rec


def window_comparison(n_steps, sel_n=256):
    """1h/3h microphysics-window trajectory on real LC05 precipitating columns
    (prescribed per-frame forcing, like the DA window). n_steps intervals use
    forcing frames 0..n_steps-1 (36 intervals span the full 3 h trajectory)."""
    from kdm6.io.frame_reader import read_wrfout_frame
    fr0 = read_wrfout_frame(FCST, 0)
    s0 = State(*fr0.state)
    f0 = Forcing(*fr0.forcing)
    hydro0 = ((f0.rho * f0.delz) * (s0.qr + s0.qs + s0.qg + s0.qi)).sum(-1)
    sel = torch.argsort(hydro0, descending=True)[:sel_n]          # heaviest columns
    xl = fr0.xland[sel]                # fixed land/sea mask, same for both variants
    xL = State(*(t[sel] for t in fr0.state))
    xC = State(*(t[sel] for t in fr0.state))
    p = make_parameters()
    precL = precC = None
    for t in range(n_steps):
        frt = read_wrfout_frame(FCST, min(t, 36))
        ft = Forcing(*(x[sel] for x in frt.forcing))
        xL, budL = kdm6_step_with_water_budget(
            xL, ft, p, dt=300.0, xland=xl, ncmin_land=NCMIN_LAND, ncmin_sea=NCMIN_SEA)
        xC, budC, _ = kdm6_step_conservative_experiment(
            xC, ft, p, dt=300.0, xland=xl, ncmin_land=NCMIN_LAND, ncmin_sea=NCMIN_SEA)
        precL = budL.surface_precip_diag_kg_m2 if precL is None else precL + budL.surface_precip_diag_kg_m2
        precC = budC.surface_precip_diag_kg_m2 if precC is None else precC + budC.surface_precip_diag_kg_m2
    w = ft.rho * ft.delz
    hL = (w * (xL.qr + xL.qs + xL.qg + xL.qi)).sum(-1)
    hC = (w * (xC.qr + xC.qs + xC.qg + xC.qi)).sum(-1)
    return {
        "n_steps": n_steps, "n_columns": sel_n,
        "xland_used": True, "ncmin_land": NCMIN_LAND, "ncmin_sea": NCMIN_SEA,
        "cum_precip_kg_m2": {"legacy_diag_mean": float(precL.mean()),
                             "conservative_actual_mean": float(precC.mean()),
                             "ratio_of_means": float(precC.mean() / precL.mean()),
                             "mean_of_per_column_ratios": float(
                                 (precC / precL.clamp(min=1e-12)).mean())},
        "final_hydro_mass_kg_m2": {"legacy_mean": float(hL.mean()),
                                   "conservative_mean": float(hC.mean())},
        "final_state_diffs": {x: field_stats(getattr(xL, x), getattr(xC, x))
                              for x in ("qr", "qs", "qg", "qi", "qv", "th")},
        "qv_th_knockon": {"qv_mean_diff": float((xC.qv - xL.qv).mean()),
                          "th_mean_diff": float((xC.th - xL.th).mean())},
    }


def main():
    art = {
        "artifact": "p0_4b1_impact_comparison",
        "role": "legacy_reference vs conservative_experiment (P0-4b.1 component 4, P0-4b.2 corrected)",
        "provenance": provenance(),
        "one_step_heavy_rain_dt120": one_step_comparison(),
    }
    try:
        art["window_1h_lc05_heaviest256"] = window_comparison(12)
        art["window_3h_lc05_heaviest256"] = window_comparison(36)
    except Exception as e:                                        # noqa: BLE001
        art["window_lc05"] = f"skipped: {e}"
    # all-sky BT comparison needs the local RTTOV runtime — do not fabricate
    art["allsky_bt_comparison"] = ("deferred: requires the local RTTOV runtime/science "
                                   "assets (host-coupled); state-space impacts above are "
                                   "the merge-decision inputs")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "p0_4b1_impact_comparison.json").write_text(json.dumps(art, indent=1))
    o = art["one_step_heavy_rain_dt120"]
    print("one-step: precip legacy", o["surface_precip_kg_m2"]["legacy_diag"],
          "→ conservative", o["surface_precip_kg_m2"]["conservative_actual"])
    print("retained hydro: legacy", o["hydro_mass_retained_kg_m2"]["legacy"],
          "→ conservative", o["hydro_mass_retained_kg_m2"]["conservative"])
    v = o["vjp_synthetic_one_step"]["combined_euclidean_norm"]
    print(f"VJP combined norm (synthetic 1-step): legacy {v['legacy']:.5f} → "
          f"conservative {v['conservative']:.5f} (ratio {v['ratio']:.3f})")
    if "window_3h_lc05_heaviest256" in art:
        w3 = art["window_3h_lc05_heaviest256"]
        print(f"3h window: aggregate cum precip ratio (cons/legacy) = "
              f"{w3['cum_precip_kg_m2']['ratio_of_means']:.3f}")
    print("artifact:", OUT / "p0_4b1_impact_comparison.json")


if __name__ == "__main__":
    torch.set_grad_enabled(True)
    main()
