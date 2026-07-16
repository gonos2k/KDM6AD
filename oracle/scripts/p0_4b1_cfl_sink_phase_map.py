#!/usr/bin/env python3
"""P0-4b.1 component 1 — CFL–sink phase map.

Measures the interface-sink (D) dependence on the per-substep fall ratio
c = vt·dt_sub/Δz for the LEGACY sedimentation substep, against the simplified
theory D_theory = ρΔz·q·max(2c−1, 0) (uniform metric, no inflow from above,
single interface). Also measures the mstep interaction at fixed TOTAL CFL —
the operational mstep rule (mstep = clamp(floor(vmax·dtcld+1),1,100)) targets
per-substep c < 1 but NOT c < 1/2, so c ∈ (1/2, 1) is common by construction
whenever vmax·dtcld > 1.

Outputs: docs/reports/p0_4b1_cfl_sink_phase_map.json (+ .png heatmap).
Analysis-only: calls the legacy substep directly; no repo behavior change.
"""
import json
import pathlib
import sys

import torch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from kdm6.sedimentation import (            # noqa: E402
    SubstepAdvectionState, substep_advection_torch, default_substep_advection_params,
)
from kdm6.water_budget import SedimentationLedger   # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[2] / "docs" / "reports"


def run_case(*, K, c_sub, mstep, q_profile, rho=1.0, dz=500.0, dtcld=60.0):
    """One column, one species (qr). c_sub = per-substep fall ratio (w1·dtcld/mstep).
    Returns per-interface defect, cap counts, loss, diag (kg/m²)."""
    B = 1
    w1_val = c_sub * mstep / dtcld           # so w1·dtcld/mstep == c_sub
    full = lambda v: torch.full((B, K), float(v), dtype=torch.float64)
    q = torch.tensor([q_profile], dtype=torch.float64)
    st = SubstepAdvectionState(qr=q, nr=full(0.0), qs=full(0.0), qg=full(0.0), brs=full(0.0))
    led = SedimentationLedger()
    z = full(0.0)
    fall = [z.clone() for _ in range(5)]
    for n in range(1, mstep + 1):
        out = substep_advection_torch(
            st, *fall, full(w1_val), full(0.0), full(0.0), full(0.0),
            full(dz), full(rho), mstep=mstep, dtcld=dtcld,
            params=default_substep_advection_params(), ledger=led)
        st = out.state
        fall = [out.fall_qr, out.fall_nr, out.fall_qs, out.fall_qg, out.fall_brs]
    att = led.finalize()
    w0 = rho * dz * float(q.sum())
    return {
        "D_total": float(att.interface_defect_by_species_kg_m2["qr"][0]),
        "D_detail": att.interface_defect_detail_kg_m2["qr"][0].tolist(),
        "A_total": float(att.positivity_projection_by_species_kg_m2["qr"][0]),
        "L": float(att.column_loss_by_species_kg_m2["qr"][0]),
        "P_diag": float(att.wrf_fallout_diag_by_species_kg_m2["qr"][0]),
        "gap": float(att.gap_by_species_kg_m2["qr"][0]),
        "inflow_cap_binds": int(att.cap_flags["qr_inflow_cap"].sum()),
        "initial_mass": w0,
        "sink_over_initial": float(att.interface_defect_by_species_kg_m2["qr"][0]) / w0 if w0 else 0.0,
        "sink_over_diag": (float(att.interface_defect_by_species_kg_m2["qr"][0])
                           / float(att.wrf_fallout_diag_by_species_kg_m2["qr"][0])
                           if float(att.wrf_fallout_diag_by_species_kg_m2["qr"][0]) else None),
    }


def main():
    torch.set_grad_enabled(False)
    q0, rho, dz = 1e-3, 1.0, 500.0
    c_grid = [round(0.05 * i, 2) for i in range(1, 31)]          # 0.05 .. 1.50

    # ── sweep 1: pure phase map (K=2, uniform q, mstep=1) vs theory ──────────
    sweep1 = []
    for c in c_grid:
        r = run_case(K=2, c_sub=c, mstep=1, q_profile=[q0, q0], rho=rho, dz=dz)
        # theory for the single interface, uniform q, no inflow from above:
        # top loses min(c,1)q, keeps q(1-min(c,1))+A; inflow capped by post-top.
        c_eff = min(c, 1.0)
        r["c"] = c
        r["D_theory"] = rho * dz * q0 * max(2 * c_eff - 1.0, 0.0)
        sweep1.append(r)

    # ── sweep 2: mstep interaction at fixed TOTAL CFL (K=2, uniform q) ───────
    sweep2 = []
    for c_total in (0.6, 0.9, 1.2, 1.8, 2.4):
        for mstep in (1, 2, 3, 4, 6, 8):
            c_sub = c_total / mstep
            if c_sub > 1.5:
                continue
            r = run_case(K=2, c_sub=c_sub, mstep=mstep, q_profile=[q0, q0])
            r.update({"c_total": c_total, "mstep": mstep, "c_sub": round(c_sub, 4)})
            sweep2.append(r)

    # ── sweep 3: vertical structure (K=8, gradients, deeper columns) ─────────
    sweep3 = []
    K = 8
    profiles = {
        "uniform": [q0] * K,
        "decreasing_down": [q0 * (1 - 0.1 * k) for k in range(K)],
        "increasing_down": [q0 * (0.3 + 0.1 * k) for k in range(K)],
        "midlevel_peak": [q0 * v for v in (0.1, 0.4, 1.0, 1.0, 0.6, 0.3, 0.1, 0.05)],
    }
    for name, prof in profiles.items():
        for c in (0.3, 0.6, 0.9, 1.2):
            r = run_case(K=K, c_sub=c, mstep=1, q_profile=prof)
            r.update({"profile": name, "c": c, "K": K})
            sweep3.append(r)

    # ── operational-rule note: per-substep c implied by the mstep rule ───────
    # mstep = clamp(floor(C_total + 1), 1, 100) → c_sub = C_total / mstep
    rule = []
    for C in [round(0.1 * i, 1) for i in range(1, 61)]:          # C_total 0.1..6.0
        mstep = max(min(int(C + 1.0), 100), 1)
        rule.append({"C_total": C, "mstep": mstep, "c_sub": round(C / mstep, 4),
                     "cap_region": C / mstep > 0.5})

    art = {
        "artifact": "p0_4b1_cfl_sink_phase_map",
        "role": "P0-4b.1 component 1 — synthetic CFL–sink phase map (legacy substep)",
        "config": {"q0": q0, "rho": rho, "dz": dz, "dtcld": 60.0},
        "sweep1_phase_map_K2_uniform_mstep1": sweep1,
        "sweep2_mstep_interaction_fixed_total_cfl": sweep2,
        "sweep3_vertical_structure_K8": sweep3,
        "operational_mstep_rule_c_sub": rule,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "p0_4b1_cfl_sink_phase_map.json").write_text(json.dumps(art, indent=1))

    # heatmap: sweep2 (c_total × mstep → sink/initial)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        cts = sorted({r["c_total"] for r in sweep2})
        mss = sorted({r["mstep"] for r in sweep2})
        M = np.full((len(cts), len(mss)), np.nan)
        for r in sweep2:
            M[cts.index(r["c_total"]), mss.index(r["mstep"])] = r["sink_over_initial"]
        fig, axes = plt.subplots(1, 2, figsize=(11, 4))
        ax = axes[0]
        ax.plot([r["c"] for r in sweep1], [r["D_total"] for r in sweep1], "o-", label="measured D")
        ax.plot([r["c"] for r in sweep1], [r["D_theory"] for r in sweep1], "--", label="theory ρΔz·q·max(2c−1,0)")
        ax.axvline(0.5, color="gray", ls=":"), ax.set_xlabel("per-substep c"), ax.set_ylabel("D [kg/m²]")
        ax.set_title("K=2 uniform, mstep=1"), ax.legend()
        ax = axes[1]
        im = ax.imshow(M, aspect="auto", origin="lower",
                       extent=(min(mss) - .5, max(mss) + .5, min(cts) - .15, max(cts) + .15))
        ax.set_xlabel("mstep"), ax.set_ylabel("C_total"), ax.set_title("sink / initial mass")
        fig.colorbar(im, ax=ax)
        fig.tight_layout()
        fig.savefig(OUT / "p0_4b1_cfl_sink_phase_map.png", dpi=110)
        print("heatmap written")
    except Exception as e:                                        # noqa: BLE001
        print(f"heatmap skipped: {e}")

    # console summary
    fire = [r for r in sweep1 if r["inflow_cap_binds"] > 0]
    print(f"sweep1: cap first fires at c = {fire[0]['c'] if fire else 'never'}")
    on = [r for r in rule if r["cap_region"]]
    print(f"operational rule: c_sub > 1/2 for C_total in "
          f"[{on[0]['C_total']}, ...] → {len(on)}/{len(rule)} of grid")
    worst = max(sweep1, key=lambda r: r["sink_over_initial"])
    print(f"sweep1 worst: c={worst['c']} sink/initial={worst['sink_over_initial']:.3f} "
          f"sink/diag={worst['sink_over_diag']}")
    print("artifact:", OUT / "p0_4b1_cfl_sink_phase_map.json")


if __name__ == "__main__":
    main()
