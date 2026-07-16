#!/usr/bin/env python3
"""P0-4b.1 component 2 — LC05 frame-replay susceptibility audit.

Runs the P0-4b sedimentation attribution on ONE oracle step (dt=300 s) applied
to EACH of the 37 restored LC05 forcing-trajectory frames (5-min cadence,
2025-07-19 00:00→03:00, 65,988 columns × 39 levels).

NAMING CONTRACT: this is a *susceptibility audit* — WRF history frames are not
the exact pre-physics host states, so per-frame replay sums must NOT be called
"water actually lost in the host integration". They measure how often and how
strongly the interface sink fires across the real LC05 state space.

Output: docs/reports/p0_4b1_lc05_replay_audit.json
Analysis-only; no repo behavior change.
"""
import json
import pathlib
import sys
import time

import torch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from kdm6.io.frame_reader import read_wrfout_frame          # noqa: E402
from kdm6.state import State, Forcing                       # noqa: E402
from kdm6.water_budget import kdm6_step_with_sed_attribution  # noqa: E402

FCST = "/Users/yhlee/KDM6AD-k/host/lc05_da_run/klfs_lc05_fcst.202507190000"
OUT = pathlib.Path(__file__).resolve().parents[2] / "docs" / "reports"
SPECIES = ("qr", "qs", "qg", "qi")
DT = 300.0


def q(t, ps):
    t = t.to(torch.float64)
    return {f"p{int(p*100):02d}": float(torch.quantile(t, p)) for p in ps}


def main():
    torch.set_grad_enabled(False)
    frames = []
    cum_sink = None
    t0 = time.time()
    N_SHARDS = 16    # mstep-aware sharding: batch-global mstepmax makes ONE heavy
    #                  column dominate the whole domain's substep count (the da_shard
    #                  rationale) — audit per shard, then concatenate per-column stats.
    for fr_i in range(37):
        fr = read_wrfout_frame(FCST, fr_i)
        s_full = State(*fr.state)
        f_full = Forcing(*fr.forcing)
        B = s_full.qv.shape[0]
        bounds = torch.linspace(0, B, N_SHARDS + 1, dtype=torch.int64)
        parts = {"sink_sp": {sp: [] for sp in SPECIES}, "proj": [], "diag_sp": {sp: [] for sp in SPECIES},
                 "det": [], "caps": {sp: 0 for sp in SPECIES}, "nsub": 0}
        for si in range(N_SHARDS):
            lo, hi = int(bounds[si]), int(bounds[si + 1])
            s = State(*(x[lo:hi] for x in s_full))
            f = Forcing(*(x[lo:hi] for x in f_full))
            _, budget, att = kdm6_step_with_sed_attribution(s, f, dt=DT)
            for sp in SPECIES:
                parts["sink_sp"][sp].append(att.interface_defect_by_species_kg_m2[sp])
                parts["diag_sp"][sp].append(att.wrf_fallout_diag_by_species_kg_m2[sp])
                parts["caps"][sp] += int(att.cap_flags[f"{sp}_inflow_cap"].sum())
            parts["proj"].append(torch.stack(
                [att.positivity_projection_by_species_kg_m2[sp] for sp in SPECIES]).sum(dim=0))
            parts["det"].append(torch.stack(
                [att.interface_defect_detail_kg_m2[sp] for sp in SPECIES]).sum(dim=0))
            parts["nsub"] = max(parts["nsub"], int(budget.n_subcycles))
            del att, budget
        sink_by_sp = {sp: torch.cat(parts["sink_sp"][sp]) for sp in SPECIES}
        sink_tot = torch.stack([sink_by_sp[sp] for sp in SPECIES]).sum(dim=0)   # (B,)
        proj_tot = torch.cat(parts["proj"])
        hydro_mass = ((f_full.rho * f_full.delz)
                      * (s_full.qr + s_full.qs + s_full.qg + s_full.qi)).sum(dim=-1)
        diag_tot = torch.stack([torch.cat(parts["diag_sp"][sp]) for sp in SPECIES]).sum(dim=0)
        affected = sink_tot > 1e-9
        n_aff = int(affected.sum())
        cum_sink = sink_tot if cum_sink is None else cum_sink + sink_tot
        f = f_full   # for the pressure lookup below

        det = torch.cat(parts["det"])
        worst_k = det.abs().argmax(dim=-1)                       # (B,) interface index (0=top)
        rec = {
            "frame": fr_i,
            "minutes": fr_i * 5,
            "n_columns": B,
            "n_affected": n_aff,
            "affected_fraction": n_aff / B,
            "sink_total_domain_kg_m2_mean": float(sink_tot.mean()),
            "sink_stats_kg_m2": {
                "mean": float(sink_tot.mean()),
                **q(sink_tot, (0.50, 0.90, 0.99)),
                "max": float(sink_tot.max()),
            },
            "sink_stats_affected_only_kg_m2": ({
                "mean": float(sink_tot[affected].mean()),
                **q(sink_tot[affected], (0.50, 0.90, 0.99)),
                "max": float(sink_tot[affected].max()),
            } if n_aff else None),
            "species_share": {sp: (float(sink_by_sp[sp].sum()) / float(sink_tot.sum())
                                   if float(sink_tot.sum()) else 0.0) for sp in SPECIES},
            "projection_total_kg_m2_sum": float(proj_tot.sum()),
            "sink_over_hydro_mass": {
                "domain": float(sink_tot.sum()) / float(hydro_mass.sum()) if float(hydro_mass.sum()) else 0.0,
                "affected_mean": (float((sink_tot[affected] / hydro_mass[affected].clamp(min=1e-12)).mean())
                                  if n_aff else 0.0),
            },
            "sink_over_diag": {
                "domain": (float(sink_tot.sum()) / float(diag_tot.sum())
                           if float(diag_tot.sum()) else None),
            },
            "cap_binds": {f"{sp}_inflow": parts["caps"][sp] for sp in SPECIES},
            "worst_interface": ({
                "k_mode_affected": int(torch.mode(worst_k[affected]).values),
                "p_hPa_at_mode": float(f.p[affected][:, int(torch.mode(worst_k[affected]).values)]
                                       .mean() / 100.0),
            } if n_aff else None),
            "n_subcycles": parts["nsub"],
            "surface_precip_diag_sum_kg_m2": float(diag_tot.sum()),
        }
        frames.append(rec)
        print(f"frame {fr_i:2d} ({fr_i*5:3d} min): affected {n_aff}/{B} "
              f"({100*n_aff/B:.1f}%), sink_sum={float(sink_tot.sum()):.3f} kg/m² "
              f"diag_sum={float(diag_tot.sum()):.3f} "
              f"[{time.time()-t0:.0f}s]", flush=True)
        del parts, sink_by_sp, sink_tot, det

    # cumulative replay sums (susceptibility measure, NOT in-host loss)
    cum = {
        "note": "sum over frame replays — NOT in-host accumulated loss (frames are "
                "5-min history states, each replayed for one dt=300 oracle step)",
        "cum_1h_domain_sum_kg_m2": float(sum(fr_["sink_total_domain_kg_m2_mean"] * fr_["n_columns"]
                                             for fr_ in frames[:12])),
        "cum_3h_domain_sum_kg_m2": float(sum(fr_["sink_total_domain_kg_m2_mean"] * fr_["n_columns"]
                                             for fr_ in frames)),
        "cum_3h_per_column_kg_m2": {
            "mean": float(cum_sink.mean()), **q(cum_sink, (0.50, 0.90, 0.99)),
            "max": float(cum_sink.max()),
        },
    }
    art = {
        "artifact": "p0_4b1_lc05_replay_audit",
        "role": "LC05 frame-replay susceptibility audit (P0-4b.1 component 2)",
        "trajectory": FCST,
        "dt_seconds": DT,
        "frames": frames,
        "cumulative_replay": cum,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "p0_4b1_lc05_replay_audit.json").write_text(json.dumps(art, indent=1))
    print("\nartifact:", OUT / "p0_4b1_lc05_replay_audit.json")
    print(f"total wall: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
