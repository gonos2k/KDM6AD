#!/usr/bin/env python3
"""Retained C5 NC -> live KMA BT -> diagnostic loss -> first-order VJP/FD.

No KDM time integration or native host run. Tensor extraction below is evidence
serialization after differentiation; profile assembly stays in the Torch graph.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import sys

import netCDF4
import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "oracle"))
from kdm6.state import State, Forcing  # noqa: E402
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
    state = State(*(tensor(a) for a in saved["native_state_top_surface"]))
    forcing = Forcing(*(tensor(a) for a in saved["native_forcing_top_surface"]))
    bg = int(saved["above_model_top_background_mask"].sum())
    if state.nc.numel() != 39 or bg != 24:
        raise ValueError("expected the retained 39 native + 24 reference-top layers")
    np.testing.assert_array_equal(saved["native_mask"], np.arange(63) >= bg)
    rho = tensor(saved["native_rho_dry_top_surface"])
    cfg = RttovProfileConfig(2, "mixing_ratio_kgkg_dry", cloud=True,
                             rho_d=rho, dry_number=True)
    xland = tensor([float(saved["native_xland"])])
    input_cfg = RttovInputConfig("retained-C5-AMI-DOM32", tuple(range(8, 17)))
    fixed = [tensor(saved[key])[None, :] for key in (
        "extended_temperature_K", "extended_q_ppmv_moist",
        "extended_p_center_hPa", "extended_p_half_hPa")]
    cfrac = tensor(saved["extended_cfrac"])[None, :]
    cloud_keys = ("extended_hydro6_g_m3", "extended_hydro7_g_m3",
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

    def cloud(nc):
        prof = model_to_rttov_tensors(state._replace(nc=nc), forcing, cfg,
                                     xland=xland, ncmin_land=10, ncmin_sea=10)
        return prof.clw, prof.ciw, prof.deff_liq, prof.deff_ice

    def external(label, nc):
        native = cloud(nc)
        full = [torch.cat((tensor(saved[key][:bg]), value))[None, :]
                for key, value in zip(cloud_keys, native)]
        if label == "base":
            for key, value in zip(cloud_keys, full):
                np.testing.assert_array_equal(value.detach().numpy()[0], saved[key])
        run_k = make_live_run_k(args.output / label, fixture_case_dir=args.fixture,
                                ami_kma_bt=True)
        bt, quality = RttovObsOp.apply(run_k, input_cfg, *fixed, *full, cfrac)
        mask = _build_mask(obs, quality)
        loss = compute_obs_loss(bt, obs, mask, sigma=1.0, delta=1.0)
        return bt, quality, mask, loss

    nc = state.nc.clone().requires_grad_(True)
    direction = 0.01 * state.nc
    bt, quality, mask, loss = external("base", nc)
    covector, = torch.autograd.grad(loss, nc)
    directional = float((covector * direction).sum())
    h = 1e-4
    bp, qp, mp, lp = external("plus", state.nc + h * direction)
    bm, qm, mm, lm = external("minus", state.nc - h * direction)
    fd = float((lp - lm) / (2 * h))
    relative = abs(directional - fd) / max(abs(directional), abs(fd), 1e-30)
    stable = all(torch.equal(quality, q) and torch.equal(mask, m)
                 for q, m in ((qp, mp), (qm, mm)))
    finite = all(torch.isfinite(a).all() for a in (bt, bp, bm, covector, loss, lp, lm))
    passed = bool(finite and stable and mask.sum() == 7 and relative <= 1e-5
                  and directional != 0 and torch.count_nonzero(covector) > 0)
    result = {
        "status": "LIVE_KMA_COST_VJP_FD_PASS" if passed else "NUMERICAL_CHECK_FAILED",
        "scope": "C5 fixed-state NC optical direction -> actual DOM32 -> KMA BT -> diagnostic Huber loss -> VJP; no microphysics step or DAWindow/native trajectory",
        "bt_coordinate": "kma_v3_0", "h": h, "direction": "0.01*NC",
        "sigma_K": 1.0, "sigma_is_calibrated": False, "huber_delta": 1.0,
        "model_bt_K": bt.detach().numpy().tolist(), "observation_bt_K": values,
        "base_quality": quality.numpy().tolist(), "mask": mask.numpy().tolist(),
        "support_quality_unchanged": stable,
        "loss": float(loss.detach()), "plus_loss": float(lp), "minus_loss": float(lm),
        "vjp_directional_loss": directional, "fd_directional_loss": fd,
        "relative_error": relative,
        "accepted_observation_cost": False, "physical_srf_compatibility_approved": False,
        "physical_number_basis_resolved": False, "operational_approval": False,
        "provenance": {"cli_argv": sys.argv, "source_sha256": sha(__file__),
                       "profile_sha256": sha(args.profile),
                       "observation_record_sha256": sha(args.observation_record),
                       "calibration_sha256": sha(cal_path),
                       "coefficient_sha256": sha(_resolve_coef_path(args.output / "base")),
                       "fixture_source_hashes": fixture_hashes,
                       "executed_namelist_sha256": sha(args.output / "base/out/rttov_test.txt"),
                       "source_files": {name: sha(ROOT / name) for name in (
                           "oracle/kdm6/obs/ami_bt_coordinate.py",
                           "oracle/kdm6/obs/rttov_case_writer.py",
                           "oracle/kdm6/obs/rttov_obs_operator.py",
                           "oracle/kdm6/obs/obs_loss.py",
                           "oracle/kdm6/obs/model_profile_builder.py")},
                       "python": platform.python_version(), "torch": str(torch.__version__),
                       "numpy": str(np.__version__)},
    }
    run_script = args.output / "base/out/run.sh"
    exe = re.search(r"(?m)^exec\s+(\S+\.exe)\s*$", run_script.read_text())
    if exe is None:
        raise ValueError("cannot identify the executed RTTOV binary in the retained run script")
    result["provenance"]["rttov_executable_path"] = str(Path(exe.group(1)).resolve())
    result["provenance"]["rttov_executable_sha256"] = sha(exe.group(1))
    result["provenance"]["run_script_sha256"] = sha(run_script)
    np.savez_compressed(args.output / "derivatives.npz", direction=direction.numpy(),
                        covector=covector.detach().numpy(), BASE=bt.detach().numpy(),
                        PLUS=bp.detach().numpy(), MINUS=bm.detach().numpy(), MASK=mask.numpy())
    (args.output / "result.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result, indent=2, allow_nan=False))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
