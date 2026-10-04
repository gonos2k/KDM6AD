#!/usr/bin/env python3
"""One-hour prescribed-forcing KDM -> live KMA diagnostic cost/VJP/FD.

No private host run or assimilation update. Pure KDM steps use explicit
non-reentrant activation checkpoints; recomputation has no external I/O or
accepted-interval accumulation. Optics uses each last step's entry humidity.
The retained 00:00 observation is a fixed diagnostic target, not hour-long
time-collocated evidence. Tensor extraction is value-only evidence logging.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import resource
import time
import re
import sys

import netCDF4
import numpy as np
import torch
from torch.utils.checkpoint import checkpoint

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "oracle"))
from kdm6.state import State, Forcing  # noqa: E402
from kdm6.runtime import _kdm6_pure, make_parameters  # noqa: E402
from kdm6.sed_conservative import CONSERVATIVE_SED_FNS  # noqa: E402
from kdm6.obs.gk2a_l1b import _read_ami_bt, load_cal_table  # noqa: E402
from kdm6.obs.model_profile_builder import (  # noqa: E402
    RttovProfileConfig, model_to_rttov_tensors)
from kdm6.obs.rttov_input_builder import RttovInputConfig  # noqa: E402
from kdm6.obs.rttov_case_writer import make_live_run_k, _resolve_coef_path  # noqa: E402
from kdm6.obs.rttov_obs_operator import RttovObsOp, _build_mask  # noqa: E402
from kdm6.obs.obs_loss import compute_obs_loss  # noqa: E402


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--observation-record", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (sha(args.profile) != "7915ef9bc9fab4983ab47776c1a3345384c21f09bddc2a6d540d36c4755194d4"
            or sha(args.observation_record) != "ce445a0c7908793eb4388a235bdabaf922138c210093c67c45b813f74367fc3b"):
        raise ValueError("this bounded probe requires the retained C5 profile and observation receipt")
    fixture_hashes = {str(p.relative_to(args.fixture)): sha(p)
                      for p in sorted(args.fixture.rglob("*")) if p.is_file()}
    reference = json.loads((ROOT / "harness/evidence/C5_nc_bt_dom32_result_2026-10-03.json").read_text())
    if fixture_hashes != reference["fixture_source_hashes"]:
        raise ValueError("the retained DOM32 fixture source bytes changed")
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.mkdir(parents=True)
    with np.load(args.profile) as archive:
        saved = {key: archive[key].copy() for key in archive.files}
    def tensor(a):
        return torch.as_tensor(a, dtype=torch.float64)
    state = State(*(tensor(a)[None, :] for a in saved["native_state_bottom_up"]))
    forcing = Forcing(*(tensor(a)[None, :] for a in saved["native_forcing_bottom_up"]))
    forcing_top = Forcing(*(a[0].flip(0) for a in forcing))
    bg = int(saved["above_model_top_background_mask"].sum())
    if state.nc.numel() != 39 or bg != 24:
        raise ValueError("expected the retained 39 native + 24 reference-top layers")
    np.testing.assert_array_equal(saved["native_mask"], np.arange(63) >= bg)
    cfg = RttovProfileConfig(2, "mixing_ratio_kgkg_dry", cloud=True, dry_number=True)
    parameters = make_parameters()
    xland = tensor([float(saved["native_xland"])])
    input_cfg = RttovInputConfig("retained-C5-AMI-DOM32", tuple(range(8, 17)))
    fixed = [tensor(saved[key])[None, :] for key in (
        "extended_p_center_hPa", "extended_p_half_hPa")]
    cloud_keys = ("extended_temperature_K", "extended_q_ppmv_moist",
                  "extended_hydro6_g_m3", "extended_hydro7_g_m3",
                  "extended_hydro_deff6_um", "extended_hydro_deff7_um")

    old_obs = json.loads(args.observation_record.read_text())
    if old_obs["pixel_zero_based"] != [411, 338] or len(old_obs["channels"]) != 9:
        raise ValueError("expected the retained C5 pixel and nine-channel observation record")
    cal_path = ROOT / "oracle/kdm6/obs/data/gk2a_ami_cal_202507190000.json"
    cal = load_cal_table(cal_path)["channels"]
    values, flags = [], []
    for item in old_obs["channels"]:
        if sha(item["path"]) != item["sha256"]:
            raise ValueError("retained KO input bytes changed")
        with netCDF4.Dataset(item["path"], "r") as ds:
            bt, quality = _read_ami_bt(ds["image_pixel_values"], cal[item["channel"]])
        values.append(float(bt[411, 338]))
        flags.append(float(quality[411, 338]))
    obs = {"bt": tensor([values]), "obs_quality": tensor([flags]),
           "channel_gate": tensor(old_obs["combined_mask"])}
    if obs["channel_gate"].sum() != 7:
        raise ValueError("the predeclared common seven-channel support changed")

    def step(*values):
        # Explicit checkpoint contract: deterministic pure transition only.
        return tuple(_kdm6_pure(State(*values), forcing, parameters, dt=20.0,
            xland=xland, ncmin_land=10.0, ncmin_sea=10.0, dry_number=True,
            normalize_ice_handoff=True, sed_substep_fns=CONSERVATIVE_SED_FNS))

    def external(label, current, entry):
        prof = model_to_rttov_tensors(State(*(a[0].flip(0) for a in current)),
            forcing_top, cfg, xland=xland, ncmin_land=10, ncmin_sea=10,
            entry_qv=entry.qv[0].flip(0))
        native = (prof.t_lay, prof.q_lay, prof.clw, prof.ciw,
                  prof.deff_liq, prof.deff_ice)
        full = [torch.cat((tensor(saved[key][:bg]), value))[None, :]
                for key, value in zip(cloud_keys, native)]
        cfrac = torch.cat((tensor(saved["extended_cfrac"][:bg]), prof.cfrac))[None, :]
        run_k = make_live_run_k(args.output / label, fixture_case_dir=args.fixture,
                                ami_kma_bt=True)
        bt, quality = RttovObsOp.apply(run_k, input_cfg, full[0], full[1],
                                      *fixed, *full[2:], cfrac)
        mask = _build_mask(obs, quality)
        loss = compute_obs_loss(bt, obs, mask, sigma=1.0, delta=1.0)
        return bt, quality, mask, loss, cfrac

    checkpoints = (1, 30, 180)  # fixed before results: 20, 600, 3600 seconds
    h = 1e-4
    direction = 0.01 * state.qv
    records, arrays = {}, {"direction": direction.numpy(),
                           "INPUT_STATE": np.stack([a.numpy() for a in state])}
    initial_qv = state.qv.clone().requires_grad_(True)
    probe = state._replace(qv=initial_qv)
    plain = step(*probe)
    checked = checkpoint(step, *probe, use_reentrant=False)
    checkpoint_equal = all(np.array_equal(a.detach().numpy().view(np.uint64),
                                          b.detach().numpy().view(np.uint64))
                           for a, b in zip(plain, checked))
    if not checkpoint_equal:
        raise RuntimeError("checkpoint changes first-step state values")
    del plain, checked

    began = time.monotonic()
    for label, offset in (("base", 0.0), ("plus", h), ("minus", -h)):
        qv = initial_qv if label == "base" else state.qv + offset * direction
        current = state._replace(qv=qv)
        for number in range(1, checkpoints[-1] + 1):
            entry = current
            values = (checkpoint(step, *entry, use_reentrant=False)
                      if label == "base" else step(*entry))
            current = State(*values)
            finite = all(torch.isfinite(a).all() for a in current)
            if not finite:
                failure = {"status": "NONFINITE_MICROPHYSICS_STATE", "trajectory": label,
                           "step": number, "source_sha256": sha(__file__)}
                (args.output / "failure.json").write_text(json.dumps(failure, indent=2))
                raise RuntimeError(f"non-finite {label} state at step {number}")
            if number % 10 == 0:
                print(f"{label}: step {number}/180, modeled={number*20}s, "
                      f"wall={time.monotonic()-began:.1f}s", flush=True)
            if number not in checkpoints:
                continue
            bt, quality, mask, loss, cfrac = external(f"{label}_{number}", current, entry)
            row = records.setdefault(str(number), {})
            row[label] = {"cost": float(loss.detach()), "quality": quality.numpy().tolist(),
                          "mask": mask.numpy().tolist(), "cfrac": cfrac.detach().numpy().tolist()}
            arrays[f"{label.upper()}_{number}"] = bt.detach().numpy()
            arrays[f"STATE_{label.upper()}_{number}"] = np.stack([a.detach().numpy() for a in current])
            if label == "base":
                covector, = torch.autograd.grad(loss, initial_qv,
                    retain_graph=number != checkpoints[-1])
                row["vjp_directional_cost"] = float((covector * direction).sum())
                arrays[f"COVECTOR_{number}"] = covector.detach().numpy()
            print(f"{label}: analysis checkpoint {number*20}s cost={row[label]['cost']:.12g}", flush=True)

    all_passed = True
    for number in checkpoints:
        row = records[str(number)]
        fd = (row["plus"]["cost"]-row["minus"]["cost"])/(2*h)
        ad = row["vjp_directional_cost"]
        rel = abs(ad-fd)/max(abs(ad),abs(fd),1e-30)
        stable = all(row["base"][key] == row[label][key]
                     for key in ("quality", "mask", "cfrac") for label in ("plus", "minus"))
        support = float(np.sum(row["base"]["mask"]))
        passed = bool(np.isfinite([fd, ad, rel]).all() and stable and support == 7
                      and ad != 0 and rel <= 1e-5)
        row.update(modeled_seconds=number*20, fd_directional_cost=fd,
                   relative_error=rel, support_quality_cfrac_unchanged=stable,
                   numerical_pass=passed)
        all_passed &= passed

    # Explicit value-only reference: verify checkpointing did not change values.
    value_replay = {}
    reference_state = state
    with torch.no_grad():
        for number in range(1, checkpoints[-1] + 1):
            reference_state = State(*step(*reference_state))
            if number in checkpoints:
                plain_state = np.stack([a.numpy() for a in reference_state])
                stored_state = arrays[f"STATE_BASE_{number}"]
                value_replay[str(number)] = bool(np.array_equal(
                    plain_state.view(np.uint64), stored_state.view(np.uint64)))
    all_passed &= all(value_replay.values())

    # A single predeclared control-space descent trial, not a retrieval or cycle.
    trial_alpha = 0.01  # v=0.01*qv, so this is +0.01% initial humidity
    trial = state._replace(qv=state.qv + trial_alpha * direction)
    for number in range(1, checkpoints[-1] + 1):
        entry = trial
        trial = State(*step(*entry))
        if not all(torch.isfinite(a).all() for a in trial):
            raise RuntimeError(f"non-finite analysis trial at step {number}")
    trial_bt, tq, tm, trial_loss, tc = external("analysis_trial_180", trial, entry)
    reference_end = records["180"]["base"]
    trial_stable = (tq.numpy().tolist() == reference_end["quality"]
                    and tm.numpy().tolist() == reference_end["mask"]
                    and tc.numpy().tolist() == reference_end["cfrac"])
    trial_cost = float(trial_loss)
    trial_pass = bool(np.isfinite(trial_cost) and trial_stable
                      and trial_cost < reference_end["cost"])
    analysis_trial = {"alpha": trial_alpha, "relative_initial_qv_change": 0.0001,
        "base_cost": reference_end["cost"], "trial_cost": trial_cost,
        "cost_change": trial_cost-reference_end["cost"],
        "linear_predicted_change": trial_alpha*records["180"]["vjp_directional_cost"],
        "support_quality_cfrac_unchanged": trial_stable,
        "computational_descent_accepted": trial_pass,
        "scientific_analysis_approved": False, "host_writeback_performed": False}
    arrays["ANALYSIS_TRIAL_BT"] = trial_bt.numpy()
    arrays["ANALYSIS_TRIAL_STATE"] = np.stack([a.numpy() for a in trial])
    all_passed &= trial_pass
    result = {"status": "LONG_KMA_COST_VJP_FD_PASS" if all_passed else "NUMERICAL_CHECK_FAILED",
        "scope": "One-hour fixed-forcing Python KDM trajectory, per-call entry density, live KMA cost/initial-qv VJP and one diagnostic descent trial. Fixed nominal00:00 target; no collocated forecast validation, retrieval/cycling, DAWindow/native run or science approval",
        "model_steps": 180, "dt_seconds": 20, "checkpoint_steps": list(checkpoints),
        "h": h, "direction": "0.01*initial_qv; bottom-up 39 native levels",
        "checkpoint_first_step_values_bit_equal": checkpoint_equal,
        "plain_value_replay_raw_bits_equal": value_replay,
        "checkpoint_contract": "non-reentrant checkpoint of pure KDM only; no external I/O or cumulative accepted ledger in recomputation",
        "sigma_K": 1.0, "sigma_is_calibrated": False, "huber_delta": 1.0,
        "observation_bt_K": obs["bt"].numpy().tolist(),
        "observation_target_is_time_collocated": False,
        "wall_seconds": time.monotonic()-began,
        "peak_rss_platform_units": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "checkpoint_results": records,
        "analysis_trial": analysis_trial,
        "accepted_observation_cost": False, "physical_srf_compatibility_approved": False,
        "physical_number_basis_resolved": False, "operational_approval": False,
        "provenance": {"cli_argv": sys.argv, "source_sha256": sha(__file__),
            "profile_sha256": sha(args.profile), "observation_record_sha256": sha(args.observation_record),
            "calibration_sha256": sha(cal_path), "fixture_source_hashes": fixture_hashes,
            "coefficient_sha256": sha(_resolve_coef_path(args.output / "base_180")),
            "executed_namelist_sha256": sha(args.output / "base_180/out/rttov_test.txt"),
            "source_files": {name: sha(ROOT/name) for name in (
                "oracle/kdm6/runtime.py", "oracle/kdm6/coordinator.py", "oracle/kdm6/sed_conservative.py",
                "oracle/kdm6/obs/ami_bt_coordinate.py", "oracle/kdm6/obs/rttov_case_writer.py",
                "oracle/kdm6/obs/rttov_obs_operator.py", "oracle/kdm6/obs/obs_loss.py",
                "oracle/kdm6/obs/model_profile_builder.py", "oracle/kdm6/rttov_bridge.py")},
            "python": platform.python_version(), "torch": str(torch.__version__), "numpy": str(np.__version__)}}
    run_script = args.output / "base_180/out/run.sh"
    exe = re.search(r"(?m)^exec\s+(\S+\.exe)\s*$", run_script.read_text())
    if exe is None:
        raise ValueError("cannot identify the RTTOV binary")
    result["provenance"].update(rttov_executable_path=str(Path(exe.group(1)).resolve()),
        rttov_executable_sha256=sha(exe.group(1)), run_script_sha256=sha(run_script))
    np.savez_compressed(args.output/"arrays.npz", **arrays)
    (args.output/"result.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(json.dumps({"status": result["status"], "wall_seconds": result["wall_seconds"],
        "checkpoints": {k: {f: v[f] for f in ("modeled_seconds", "relative_error", "numerical_pass")}
                        for k, v in records.items()}, "analysis_trial": analysis_trial}, indent=2), flush=True)
    raise SystemExit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
