#!/usr/bin/env python3
"""P0-4b.1 component 2 — LC05 frame-replay susceptibility audit (P0-4b.2 rev).

Runs the P0-4b sedimentation attribution on ONE oracle step (dt=300 s) applied
to EACH of the 37 restored LC05 forcing-trajectory frames (5-min cadence,
2025-07-19 00:00→03:00, 65,988 columns × 39 levels), with the operational
LC05 land/sea configuration (xland + ncmin_land=100 / ncmin_sea=10).

NAMING CONTRACT: this is a *susceptibility audit* — WRF history frames are not
the exact pre-physics host states, so per-frame replay sums must NOT be called
"water actually lost in the host integration". They measure how often and how
strongly the interface sink fires across the real LC05 state space.

INTERVAL CONVENTION (P0-4b.2): the trajectory holds 37 state frames but only
36 five-minute intervals. "3 h cumulative" sums the 36 replay steps started
from frames 0..35; frame 36 is the endpoint state, reported separately.

Output: docs/reports/p0_4b1_lc05_replay_audit.json
Analysis-only; no repo behavior change.
"""
import hashlib
import json
import os
import pathlib
import platform
import subprocess
import sys
import time

import torch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from kdm6.io.frame_reader import read_wrfout_frame          # noqa: E402
from kdm6.state import State, Forcing                       # noqa: E402
from kdm6.water_budget import kdm6_step_with_sed_attribution  # noqa: E402

FCST = "/Users/yhlee/KDM6AD-k/host/lc05_da_run/klfs_lc05_fcst.202507190000"
MANIFEST = "/Users/yhlee/KDM6AD-k/host/lc05_da_run/klfs_lc05_fcst.RESTORE_MANIFEST.json"
OUT = pathlib.Path(__file__).resolve().parents[2] / "docs" / "reports"
SPECIES = ("qr", "qs", "qg", "qi")
DT = 300.0
# Operational LC05 all-sky/DA land-sea configuration
NCMIN_LAND = 100.0
NCMIN_SEA = 10.0
N_CUM_STEPS = 36     # frames 0..35 start the 36 five-minute intervals of the 3 h window


def q(t, ps):
    t = t.to(torch.float64)
    return {f"p{int(p*100):02d}": float(torch.quantile(t, p)) for p in ps}


def _sha256(path, chunk=1 << 24):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _kdm6_tree_sha256():
    """Combined content hash of the imported kdm6 package (working tree, every
    .py, sorted and path-tagged) — the physics lives there, not in this script."""
    root = pathlib.Path(__file__).resolve().parents[1] / "kdm6"
    h = hashlib.sha256()
    for p in sorted(root.rglob("*.py")):
        h.update(str(p.relative_to(root)).encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def provenance(traj_sha=None, script_sha=None, kdm6_sha=None):
    root = pathlib.Path(__file__).resolve().parents[2]
    code_sha = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
    return {
        "code_sha": code_sha,
        "script_sha256": script_sha or _sha256(__file__),
        "kdm6_tree_sha256": kdm6_sha or _kdm6_tree_sha256(),
        "trajectory": FCST,
        "trajectory_sha256": traj_sha or _sha256(FCST),
        "restore_manifest_sha256": _sha256(MANIFEST),
        "trajectory_provenance": ("faithful reconstruction (regenerated 3h/5-min run per "
                                  "RESTORE_MANIFEST), not the byte-identical original"),
        "torch_version": torch.__version__,
        "python_version": platform.python_version(),
        "dt": DT,
        "frame_start": 0,
        "frame_stop_exclusive": N_CUM_STEPS,
        "endpoint_frame": 36,
        "xland_used": True,
        "ncmin_land": NCMIN_LAND,
        "ncmin_sea": NCMIN_SEA,
        "n_shards": 16,
    }


def _ckpt_meta(traj_sha, script_sha, kdm6_sha):
    """Config + content + code fingerprint — a checkpoint from a different
    trajectory (by BYTES, not path), a different script revision, a different
    kdm6 physics tree, or a different config must never be silently resumed."""
    return {"artifact": "p0_4b1_lc05_replay_audit",
            "trajectory": FCST, "trajectory_sha256": traj_sha,
            "script_sha256": script_sha, "kdm6_tree_sha256": kdm6_sha, "dt": DT,
            "ncmin_land": NCMIN_LAND, "ncmin_sea": NCMIN_SEA,
            "n_cum_steps": N_CUM_STEPS}


def main():
    torch.set_grad_enabled(False)
    frames = []
    cum36_sink = None                                  # per-column, frames 0..35 only
    cum36_species = {sp: 0.0 for sp in SPECIES}        # domain sums, frames 0..35
    cum36_proj = 0.0
    # Optional per-frame checkpoint/resume (a ~45 min run should survive an
    # interrupted host): set P0_4B1_REPLAY_CKPT to a writable path to enable.
    ckpt = os.environ.get("P0_4B1_REPLAY_CKPT")
    start_frame = 0
    traj_sha = script_sha = kdm6_sha = ck_meta = None
    if ckpt:
        script_sha = _sha256(__file__)
        kdm6_sha = _kdm6_tree_sha256()    # the physics package, not just this script
        traj_sha = _sha256(FCST)          # content hash, computed once at startup
        ck_meta = _ckpt_meta(traj_sha, script_sha, kdm6_sha)
    if ckpt and pathlib.Path(ckpt).exists():
        ck = torch.load(ckpt, weights_only=True)   # tensors + plain containers only
        ok = (ck.get("meta") == ck_meta
              and 0 < len(ck.get("frames", [])) <= 37
              and [r["frame"] for r in ck["frames"]] == list(range(len(ck["frames"]))))
        if not ok:
            raise RuntimeError(
                f"stale or mismatched replay checkpoint at {ckpt} (different "
                "trajectory bytes, script revision, or config; or non-contiguous "
                "frames) — delete it or point P0_4B1_REPLAY_CKPT elsewhere")
        frames, cum36_sink = ck["frames"], ck["cum36_sink"]
        cum36_species, cum36_proj = ck["cum36_species"], ck["cum36_proj"]
        start_frame = len(frames)
        print(f"resuming from checkpoint: {start_frame} frames done", flush=True)
    t0 = time.time()
    N_SHARDS = 16    # mstep-aware sharding: batch-global mstepmax makes ONE heavy
    #                  column dominate the whole domain's substep count (the da_shard
    #                  rationale) — audit per shard, then concatenate per-column stats.
    for fr_i in range(start_frame, 37):
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
            _, budget, att = kdm6_step_with_sed_attribution(
                s, f, dt=DT, xland=fr.xland[lo:hi],
                ncmin_land=NCMIN_LAND, ncmin_sea=NCMIN_SEA)
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
        if fr_i < N_CUM_STEPS:
            cum36_sink = sink_tot if cum36_sink is None else cum36_sink + sink_tot
            for sp in SPECIES:
                cum36_species[sp] += float(sink_by_sp[sp].sum())
            cum36_proj += float(proj_tot.sum())

        det = torch.cat(parts["det"])
        worst_k = det.abs().argmax(dim=-1)             # (B,) interface index, TOP-FIRST
        # Pressure lookup (P0-4b.2 fix): the attribution detail's k is in the
        # sedimentation chain's TOP-FIRST order, while the frame reader's f.p is
        # WRF bottom-up — flip p, and use the half-level mean between the two
        # cells sharing interface k (an interface is between levels, not at one).
        p_tf = torch.flip(f_full.p, dims=(-1,))        # (B, K) top-first
        assert bool((p_tf[:, :-1] <= p_tf[:, 1:]).all()), \
            "top-first pressure must increase downward — K-order mismatch"
        rec = {
            "frame": fr_i,
            "minutes": fr_i * 5,
            "n_columns": B,
            "n_affected": n_aff,
            "affected_fraction": n_aff / B,
            "sink_per_column_mean_kg_m2": float(sink_tot.mean()),
            "sink_domain_sum_kg_m2": float(sink_tot.sum()),
            "species_sink_sum_kg_m2": {sp: float(sink_by_sp[sp].sum()) for sp in SPECIES},
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
            "worst_interface": None,
            "n_subcycles": parts["nsub"],
            "surface_precip_diag_sum_kg_m2": float(diag_tot.sum()),
        }
        if n_aff:
            k_mode = int(torch.mode(worst_k[affected]).values)
            p_iface = 0.5 * (p_tf[affected][:, k_mode] + p_tf[affected][:, k_mode + 1])
            rec["worst_interface"] = {
                "k_mode_affected_top_first": k_mode,
                "p_hPa_at_mode_half_level": float(p_iface.mean() / 100.0),
            }
        frames.append(rec)
        if ckpt:
            # atomic: a kill mid-write must never leave a truncated checkpoint
            torch.save({"meta": ck_meta, "frames": frames,
                        "cum36_sink": cum36_sink, "cum36_species": cum36_species,
                        "cum36_proj": cum36_proj}, ckpt + ".tmp")
            os.replace(ckpt + ".tmp", ckpt)
        print(f"frame {fr_i:2d} ({fr_i*5:3d} min): affected {n_aff}/{B} "
              f"({100*n_aff/B:.1f}%), sink_sum={float(sink_tot.sum()):.3f} kg/m² "
              f"diag_sum={float(diag_tot.sum()):.3f} "
              f"[{time.time()-t0:.0f}s]", flush=True)
        del parts, sink_by_sp, sink_tot, det

    # cumulative replay sums (susceptibility measure, NOT in-host loss)
    sp_sum_total = sum(cum36_species.values())
    cum = {
        "note": "sum over frame replays — NOT in-host accumulated loss (frames are "
                "5-min history states, each replayed for one dt=300 oracle step). "
                "The 3 h window has 36 intervals: cumulative sums cover replay "
                "steps started from frames 0..35; frame 36 is the endpoint state.",
        "cum_1h_domain_sum_kg_m2": float(sum(fr_["sink_domain_sum_kg_m2"]
                                             for fr_ in frames[:12])),
        "cumulative_3h": {
            "n_replay_steps": N_CUM_STEPS,
            "domain_sum_kg_m2": float(sum(fr_["sink_domain_sum_kg_m2"]
                                          for fr_ in frames[:N_CUM_STEPS])),
            "per_column_kg_m2": {
                "mean": float(cum36_sink.mean()), **q(cum36_sink, (0.50, 0.90, 0.99)),
                "max": float(cum36_sink.max()),
            },
            "species_sink_sum_kg_m2": {sp: cum36_species[sp] for sp in SPECIES},
            "species_share": {sp: (cum36_species[sp] / sp_sum_total if sp_sum_total else 0.0)
                              for sp in SPECIES},
            "projection_sum_kg_m2": cum36_proj,
            "interface_defect_sum_kg_m2": sp_sum_total,
        },
        "endpoint_frame36": {
            "note": "frame 36 (t=3 h endpoint state) replay, NOT part of the 3 h cumulative",
            "sink_domain_sum_kg_m2": frames[36]["sink_domain_sum_kg_m2"],
            "affected_fraction": frames[36]["affected_fraction"],
        },
        "all_37_frame_replay_domain_sum_kg_m2": float(sum(fr_["sink_domain_sum_kg_m2"]
                                                          for fr_ in frames)),
    }
    art = {
        "artifact": "p0_4b1_lc05_replay_audit",
        "role": "LC05 frame-replay susceptibility audit (P0-4b.1 component 2, P0-4b.2 corrected)",
        "provenance": provenance(traj_sha=traj_sha, script_sha=script_sha,
                                 kdm6_sha=kdm6_sha),
        "dt_seconds": DT,
        "frames": frames,
        "cumulative_replay": cum,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "p0_4b1_lc05_replay_audit.json").write_text(json.dumps(art, indent=1))
    if ckpt:
        pathlib.Path(ckpt).unlink(missing_ok=True)
    print("\nartifact:", OUT / "p0_4b1_lc05_replay_audit.json")
    print(f"total wall: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
