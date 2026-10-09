#!/usr/bin/env python3
"""Synthetic evaluator counterexample: fixed S, new RTTOV QC flag, lower J.

Uses the existing normalized-dry fulldomain test input shape and the real
RttovObsOp -> allsky_shard -> make_fulldomain_obs_eval path. Only the profile
builder and injected run_k are tiny controlled test doubles; no RTTOV binary,
microphysics integration, or optimizer is run.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "oracle"))
sys.path.insert(0, str(ROOT / "oracle/tests"))

from test_normalized_dry_fulldomain import inputs  # noqa: E402
import kdm6.da_fulldomain as fd  # noqa: E402
import kdm6.obs.model_profile_builder as builder  # noqa: E402
import kdm6.obs.rttov_case_writer as writer  # noqa: E402
from kdm6.obs.model_profile_builder import RttovProfileTensors  # noqa: E402
from kdm6.obs.rttov_input_builder import RttovInputConfig  # noqa: E402
from kdm6.da_driver import OsseObsConfig  # noqa: E402
from kdm6.rttov_bridge import freeze_dry_air_density  # noqa: E402

F64 = dict(dtype=torch.float64)
CHANNELS = tuple(range(8, 17))
FROZEN_SUPPORT = (0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


class InlinePool:
    """Execute the existing spawn-safe all-sky worker inline for the tiny fixture."""
    def map(self, fn, jobs):
        return [fn(job) for job in jobs]


def main() -> None:
    torch.set_num_threads(1)
    fr, co, grids = inputs()  # existing test fixture: one 2-level cloudy column
    y_bt = co.bt[:, 7:16].to(torch.float64).detach().clone()
    y_rq = co.obs_quality[:, 7:16].to(torch.float64).detach().clone()
    gate = torch.tensor([FROZEN_SUPPORT], **F64)
    xland = fr.xland.to(torch.float64).detach().clone()
    xb, forcing = fr.state, fr.forcing
    p_lay = torch.as_tensor(grids["p_lay"], **F64)
    p_half = torch.as_tensor(grids["p_half"], **F64)
    rho_d = freeze_dry_air_density(xb, forcing)
    profile_cfg = builder.RttovProfileConfig(
        gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
        rttov_layer_pressure=p_lay, rttov_level_pressure=p_half, cloud=True)
    input_cfg = RttovInputConfig(coef_id="synthetic-qc-audit", channels=CHANNELS)
    clear_cfg = OsseObsConfig(
        run_k=None,
        profile_cfg=profile_cfg._replace(cloud=False),
        input_cfg=input_cfg,
        obs_sigma=1.0,
        t_blend_octaves=0.0,
        q_blend_octaves=0.0,
    )
    rttov_cfg = dict(
        rho_d=rho_d.detach().cpu().numpy().copy(),
        channels=CHANNELS,
        coef_id="synthetic-qc-audit",
        p_lay=p_lay.cpu().numpy().copy(),
        p_half=p_half.cpu().numpy().copy(),
        t_ref=np.full(len(grids["p_lay"]), 280.0),
        q_ref=np.full(len(grids["p_lay"]), 1000.0),
        dry_number=False,
        ami_kma_bt=True,
        ncmin_land=10.0,
        ncmin_sea=10.0,
        t_blend_octaves=0.0,
        q_blend_octaves=0.0,
    )

    def fake_profile(leaves, fcol, cfg, **_kwargs):
        # Keep each all-sky connected State field structurally present, while
        # making the fake BT control transparent and independent of clouds.
        t = leaves.th * fcol.pii
        q = leaves.qv * 0.0 + 1000.0
        zero_nc = leaves.nc * 0.0
        zero_ni = leaves.ni * 0.0
        return RttovProfileTensors(
            t_lay=t,
            q_lay=q,
            p_lay=cfg.rttov_layer_pressure,
            p_half=cfg.rttov_level_pressure,
            clw=leaves.qc + zero_nc,
            ciw=leaves.qi + leaves.qs + zero_ni,
            deff_liq=torch.ones_like(t) * 10.0 + zero_nc,
            deff_ice=torch.ones_like(t) * 40.0 + zero_ni,
            cfrac=leaves.qc * 0.0 + 0.5,
        )

    call_rows: list[dict] = []
    baseline_t = {"value": None}

    def fake_run_k(rin):
        t = np.asarray(rin.profile["T"], dtype=np.float64)
        mean_t = float(t.mean())
        if baseline_t["value"] is None:
            baseline_t["value"] = mean_t
        lost = mean_t > baseline_t["value"] + 0.4
        bt = np.full((rin.nprofiles, len(CHANNELS)), 300.0, dtype=np.float64)
        rq = np.zeros((rin.nprofiles, len(CHANNELS)), dtype=np.int32)
        if lost:
            # The synthetic flagged radiance is artificially perfect, making
            # it especially clear when the evaluator still lets it lower J.
            # Channels 8/9 were pre-excluded by the frozen gate; their fake
            # flags clear on the trial but must not change S.
            bt[:, 2] = 280.0
            rq[:, 0:2] = 0
            rq[:, 2] = 32768
        else:
            rq[:, 0:2] = 32768
        kshape = (rin.nprofiles, len(CHANNELS), rin.nlayers)
        k = {name: np.zeros(kshape, dtype=np.float64) for name in
             ("T", "Q", "HYDRO6", "HYDRO7", "HYDRO_DEFF6", "HYDRO_DEFF7")}
        call_rows.append({"mean_T_K": mean_t, "lost_channel_support": lost,
                          "flagged_channel_ids_1based": [CHANNELS[i] for i in np.flatnonzero(rq[0])],
                          "BT_K": bt[0].tolist(), "rad_quality": rq[0].tolist()})
        return bt, k, rq

    def fake_run_k_factory(_case_dir, **_kwargs):
        return fake_run_k

    root = ROOT / "graphify-out/pr392-support/runs/evaluator"
    root.mkdir(parents=True, exist_ok=True)
    with __import__("unittest.mock", fromlist=["patch"]).patch.object(
            builder, "model_to_rttov_tensors", fake_profile), \
         __import__("unittest.mock", fromlist=["patch"]).patch.object(
            writer, "make_live_run_k", fake_run_k_factory):
        evaluate = fd.make_fulldomain_obs_eval(
            xb, forcing, y_bt, y_rq, xland,
            torch.tensor([0], dtype=torch.int64),
            torch.empty(0, dtype=torch.int64),
            clear_cfg, rttov_cfg, str(root),
            n_workers=1, pool=InlinePool(), obs_time=0,
            huber_delta=1.0, x_slot_bg=xb, channel_gate=gate)
        baseline_mask = evaluate.mask.detach().clone()
        base = evaluate(0, xb)
        trial_state = xb._replace(th=xb.th + 1.0)
        trial = evaluate(0, trial_state)

    result = {
        "study": "PR392 frozen-support QC-loss evaluator counterexample",
        "scope": "Synthetic fake-run_k reproduction through the real RttovObsOp, allsky_shard worker, make_fulldomain_obs_eval, and existing ObsEvalResult protocol. No RTTOV binary, KDM6 step, or optimizer was run.",
        "source_head": __import__("subprocess").check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "repro_script_sha256": sha(Path(__file__).resolve()),
        "test_fixture_source": str(ROOT / "oracle/tests/test_normalized_dry_fulldomain.py"),
        "fixed_mask": baseline_mask[0].tolist(),
        "preexcluded_channel_ids_1based": [8, 9],
        "preexcluded_channel_gate": [0, 0],
        "fixed_n_valid": base.n_valid,
        "base": {"J": float(base.j), "n_valid": base.n_valid,
                 "signature": base.signature, "fake_run_quality": call_rows[1]["rad_quality"]},
        "trial": {"J": float(trial.j), "n_valid": trial.n_valid,
                  "signature": trial.signature,
                  "fake_run_quality": call_rows[2]["rad_quality"],
                  "flagged_channel_ids_1based": call_rows[2]["flagged_channel_ids_1based"]},
        "J_change": float(trial.j) - float(base.j),
        "calls": call_rows,
        "interpretation": "The evaluator fixes S from the background probe (7 channels); channels 8/9 are pre-excluded by the explicit gate. The fake run_k clears their baseline-only flags at trial and flags active channel 10 with 32768 while returning an artificially perfect BT for that channel. The trial still returns the same fixed mask count and signature, and J falls by 19.5 because the flagged BT remains inside _part_loss. This shows pre-excluded channel flags can change without changing S, but a new flag on S is not rejected. The evaluator does not reward a reduced mask count; it rewards an invalid newly flagged BT because trial rad_quality is returned by sharded_allsky but not checked against S.",
        "limitations": ["Controlled radiances/QC are synthetic; this demonstrates call-path behavior only.",
                       "Not evidence that the real RTTOV flag always produces a lower BT or that an optimizer accepted this trial.",
                       "No optimization, line search, microphysics, native run, or real RTTOV call was executed."],
        "source_sha256": {
            path: sha(ROOT / path) for path in (
                "oracle/kdm6/da_fulldomain.py",
                "oracle/kdm6/obs/allsky_shard.py",
                "oracle/kdm6/da_dual.py",
                "oracle/kdm6/da_minimizer.py",
                "oracle/kdm6/obs/rttov_obs_operator.py")},
    }
    out = ROOT / "harness/evidence/pr392_fixed_support_2026-10-09/RESULT.json"
    out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
