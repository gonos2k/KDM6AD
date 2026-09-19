"""Bounded diagnosis of the AMI all-sky quality boundary.

The V3 live record showed a real cloud profile and HYDRO K, but its selected
column had no usable clean-IR channels.  This script probes a deterministic set
of hydrometeor-bearing real KDM columns, retaining the failed high-loading
column as a negative control.  If a moderate column has a non-empty quality
mask, it also checks a direct first-order HYDRO6 content FD against RTTOV's
parsed HYDRO6 K, including the actual profile and BT ASCII round-trip.

Fixture pressure, angles, surface and datetime remain wiring-only.  No quality
flag is weakened or dropped, and this script makes no dK/dx or Hessian claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from pathlib import Path

import numpy as np
import torch

try:  # direct CLI (oracle/scripts on sys.path) and pytest package import
    from v3_live_gradient_evidence import (
        ALL_CHANNELS, DEFAULT_CAL, DEFAULT_GK2A, DEFAULT_KDM, DEFAULT_STAMP,
        _finite_stats, _profile_and_obs, _state_subset, sha256_file,
    )
except ModuleNotFoundError:
    from scripts.v3_live_gradient_evidence import (
        ALL_CHANNELS, DEFAULT_CAL, DEFAULT_GK2A, DEFAULT_KDM, DEFAULT_STAMP,
        _finite_stats, _profile_and_obs, _state_subset, sha256_file,
    )

REPO = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO / "graphify-out/goal-resolution-20260906-2307/cloud/diagnosis.json"


def _asset(path: Path, role: str, level: str) -> dict:
    return {"path": str(path), "role": role, "evidence_level": level,
            "exists": path.is_file(), "size_bytes": path.stat().st_size if path.is_file() else None,
            "sha256": sha256_file(path)}


def _bt_resolution(path: Path) -> dict:
    text = path.read_text()
    match = re.search(r"RADIANCE%BT\s*=\s*\((.*?)\)", text, re.S)
    vals = re.findall(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?",
                     match.group(1) if match else "")
    quanta = []
    for token in vals:
        mantissa, _, exponent = token.lower().partition("e")
        digits = len(mantissa.split(".", 1)[1]) if "." in mantissa else 0
        quanta.append(10.0 ** ((int(exponent) if exponent else 0) - digits))
    return {"path_ephemeral": True, "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
            "bt_values": len(vals), "bt_quantum_upper_bound": max(quanta) if quanta else None}


def decode_quality_bits(values) -> dict:
    """Decode only the pinned RTTOV quality bits needed for this diagnosis."""
    unique = sorted({int(round(float(v))) for row in values for v in row})
    return {"unique_values": unique,
            "delta_eddington_extinction_limit": sorted(
                v for v in unique if v & (1 << 15)),
            "bit15_value": 1 << 15}


def _fixture_hydro_units() -> dict:
    from kdm6.obs.rttov_case_writer import cloud_fixture_case_dir
    path = cloud_fixture_case_dir() / "in/profiles/001/atm/mmr_hydro_aer.txt"
    text = path.read_text()
    match = re.search(r"(?im)^\s*mmr_hydro\s*=\s*\.?\s*([TF])", text)
    if match is None:
        raise RuntimeError(f"fixture hydro unit declaration missing: {path}")
    return {"path": str(path), "sha256": sha256_file(path),
            "mmr_hydro": match.group(1).upper() == "T",
            "declared_content_units": "kg/kg" if match.group(1).upper() == "T" else "g/m^3"}


def _load_boundary(kdm_path, gk2a_root, cal_path, stamp, stride, max_dist):
    from kdm6.io.frame_reader import read_wrfout_frame
    from kdm6.obs.gk2a_l1b import AMI_CHANNELS, CLEAN_IR_CHANNELS, load_cal_table, read_ko_slot, slot_files
    from kdm6.obs.obs_ingest import payload_to_column_obs
    frame = read_wrfout_frame(str(kdm_path), 0, nccn_policy="init_profile")
    files = [Path(x) for x in slot_files(gk2a_root, stamp, channels=CLEAN_IR_CHANNELS)]
    payload = read_ko_slot(files, load_cal_table(cal_path), stride=stride)
    cols = payload_to_column_obs(payload, frame.meta["lat"], frame.meta["lon"], max_dist_km=max_dist)
    clean = [AMI_CHANNELS.index(x) for x in CLEAN_IR_CHANNELS]
    owners = [i for i in range(cols.bt.shape[0])
              if int((cols.obs_quality[i, clean] == 0).sum()) == len(clean)]
    qtot = (frame.state.qc + frame.state.qi + frame.state.qs)[owners].sum(dim=1)
    positive = [(int(c), float(q)) for c, q in zip(owners, qtot.tolist()) if q > 1.0e-6]
    positive.sort(key=lambda x: (x[1], x[0]))
    return frame, payload, cols, clean, positive, files


def _configs(state, forcing, *, all_sky=True):
    from kdm6.obs.model_profile_builder import RttovProfileConfig
    from kdm6.obs.rttov_case_writer import fixture_layer_pressure
    from kdm6.obs.rttov_fixture import fixture_p_half, fixture_tq
    from kdm6.obs.rttov_input_builder import RttovInputConfig
    from kdm6.da_driver import OsseObsConfig
    tr, qr = fixture_tq()
    p_half = torch.as_tensor(np.asarray(fixture_p_half(), dtype=float), dtype=torch.float64)
    p_lay = torch.as_tensor(np.asarray(fixture_layer_pressure(), dtype=float), dtype=torch.float64)
    rho_d = torch.flip(forcing.rho / (1.0 + state.qv), [-1])[0].detach().clone()
    pcfg = RttovProfileConfig(gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
                              rttov_layer_pressure=p_lay, rttov_level_pressure=p_half,
                              cloud=all_sky, rho_d=rho_d if all_sky else None)
    icfg = RttovInputConfig(coef_id="ami_501_test", channels=ALL_CHANNELS)
    return OsseObsConfig(run_k=None, profile_cfg=pcfg, input_cfg=icfg, obs_sigma=1.0,
                         t_ref=torch.as_tensor(np.asarray(tr), dtype=torch.float64),
                         q_ref=torch.as_tensor(np.asarray(qr), dtype=torch.float64))


def _run_column(frame, cols, column, clean, *, out_parent, all_sky=True):
    from kdm6.runtime import kdm6_step
    from kdm6.obs.rttov_case_writer import make_live_run_k
    from kdm6.obs.obs_loss import compute_obs_loss
    from kdm6.state import State
    state, forcing, xland = _state_subset(frame, [column])
    cfg = _configs(state, forcing, all_sky=all_sky)
    obs = {"bt": cols.bt[[column]], "obs_quality": cols.obs_quality[[column]]}
    root = Path(tempfile.mkdtemp(prefix=f"cloud-probe-{column}-", dir=out_parent))
    seen = {}
    def run_k(rin):
        seen["rin"] = rin
        value = make_live_run_k(root)(rin)
        seen["result"] = value
        return value
    initial = State(*(f.detach().clone().to(torch.float64).requires_grad_(True) for f in state))
    evolved, handle = kdm6_step(initial, forcing, dt=20.0, xland=xland)
    evolved_col = State(*(getattr(evolved, k)[0] for k in evolved._fields))
    forcing_col = type(forcing)(*(getattr(forcing, k)[0] for k in forcing._fields))
    _, prof, t_lay, q_lay, bt, rq = _profile_and_obs(
        evolved_col, forcing_col, cfg, run_k=run_k, xland=xland[0], detach_state=False)
    handle.close()
    rin, output = seen["rin"], seen["result"]
    mask = ((obs["obs_quality"] == 0) & (rq == 0))
    j = compute_obs_loss(bt, obs, mask.to(torch.float64), sigma=1.0, delta=1.0)
    rad = _bt_resolution(root / "out/k/radiance.txt")
    clean_mask = [bool(mask[0, c]) for c in clean]
    return {"column": column, "initial_hydrometeor_total": float(
                (state.qc + state.qi + state.qs).sum()),
            "initial_species_max": {k: float(getattr(state, k).max()) for k in ("qc", "qi", "qs")},
            "profile": {k: _finite_stats(v) for k, v in rin.profile.items()},
            "profile_cloud": {k: _finite_stats(getattr(prof, k)) for k in
                              ("clw", "ciw", "deff_liq", "deff_ice", "cfrac")},
            "K_cloud": {k: _finite_stats(output[1][k]) for k in
                        ("HYDRO6", "HYDRO7", "HYDRO_DEFF6", "HYDRO_DEFF7")},
            "bt_values": bt.detach().cpu().tolist(),
            "rad_quality_values": rq.detach().cpu().tolist(),
            "rad_quality_bits": decode_quality_bits(rq.detach().cpu().tolist()),
            "clean_ir_rad_quality_zero": clean_mask,
            "clean_ir_joint_usable": int(sum(clean_mask)),
            "mask_kept": int(mask.sum()), "J": float(j.detach()),
            "radiance_output": rad,
            "units_contract": {"HYDRO6/HYDRO7": "g/m^3", "fixture": _fixture_hydro_units()},
            "fixture_geometry": "wiring_only", "actual_collocation": "GK2A/KDM lat/lon",
            "scratch_ephemeral": True}


def _cloud_content_fd(frame, cols, column, clean, *, out_parent):
    """Direct first-order H/K checks for content and effective diameter."""
    from kdm6.obs.rttov_case_writer import make_live_run_k
    from kdm6.obs.rttov_obs_operator import RttovObsOp
    state, forcing, xland = _state_subset(frame, [column])
    cfg = _configs(state, forcing, all_sky=True)
    captured = {}
    def call(prof, tag):
        root = Path(tempfile.mkdtemp(prefix=f"cloud-fd-{tag}-", dir=out_parent))
        seen = {}
        def run_k(rin):
            seen["rin"] = rin
            value = make_live_run_k(root)(rin)
            seen["result"] = value
            return value
        bt, rq = RttovObsOp.apply(run_k, cfg.input_cfg, prof.t_lay, prof.q_lay,
                                  prof.p_lay, prof.p_half, prof.clw, prof.ciw,
                                  prof.deff_liq, prof.deff_ice, prof.cfrac)
        rin = seen["rin"]
        hydro = np.loadtxt(root / "in/profiles/001/atm/hydro.txt").reshape(-1, 8)[:, 5]
        deff = np.loadtxt(root / "in/profiles/001/atm/hydro_deff.txt").reshape(-1, 7)[:, 5]
        expected = np.asarray(rin.profile["HYDRO6"][0], dtype=float).reshape(-1)
        expected_deff = np.asarray(rin.profile["HYDRO_DEFF6"][0], dtype=float).reshape(-1)
        captured[tag] = {"bt": bt.detach(), "rq": rq.detach(), "rin": rin,
                         "result": seen["result"], "root": root,
                         "hydro6_serialization": {
                             "max_abs": float(np.max(np.abs(hydro - expected))),
                             "changed_count": int(np.count_nonzero(hydro != expected)),
                             "unchanged_roundtrip": bool(np.array_equal(hydro, expected)),
                             "deff6_max_abs": float(np.max(np.abs(deff - expected_deff))),
                             "deff6_changed_count": int(np.count_nonzero(deff != expected_deff))}}
    # Build baseline profile through the same KDM->H path, but do not reuse a
    # stale K cache.  The direct K call above is the authoritative H boundary.
    from kdm6.runtime import kdm6_step
    from kdm6.state import State
    initial = State(*(f.detach().clone().to(torch.float64).requires_grad_(True) for f in state))
    evolved, handle = kdm6_step(initial, forcing, dt=20.0, xland=xland)
    ev = State(*(getattr(evolved, k)[0] for k in evolved._fields))
    fc = type(forcing)(*(getattr(forcing, k)[0] for k in forcing._fields))
    # Obtain the profile on the real M->H path once; direct H calls below then
    # perturb only the emitted cloud field while retaining the same grid/config.
    prep_root = Path(tempfile.mkdtemp(prefix="cloud-fd-prep-", dir=out_parent))
    prep_live = make_live_run_k(prep_root)
    _, prof, t_lay, q_lay, *_ = _profile_and_obs(
        ev, fc, cfg, run_k=prep_live, xland=xland[0], detach_state=False)
    handle.close()
    prof_for_call = prof._replace(t_lay=t_lay, q_lay=q_lay)
    call(prof_for_call, "base")
    base = captured["base"]
    content_lay = int(torch.argmax(prof.clw).item())
    content_eps = min(1.0e-4, 0.1 * float(prof.clw[content_lay].detach()))
    if not np.isfinite(content_eps) or content_eps <= 0.0:
        raise RuntimeError("selected HYDRO6 layer has no positive content for a two-sided FD")
    k_deff = torch.as_tensor(base["result"][1]["HYDRO_DEFF6"], dtype=torch.float64)[0]
    active = (prof.clw.detach() > 0).to(torch.float64)
    deff_score = k_deff.abs().max(dim=0).values * active
    deff_lay = int(torch.argmax(deff_score).item()) if bool((deff_score > 0).any()) else content_lay

    def run_fd(field, kfield, layer, eps_values, unit):
        direction = torch.zeros_like(getattr(prof, field)); direction[layer] = 1.0
        result = {"layer": layer, "field": field, "k_field": kfield,
                  "unit": unit, "eps": []}
        for j, eps in enumerate(eps_values):
            call(prof_for_call._replace(**{field: getattr(prof, field) + eps * direction}),
                 f"{field}-plus-{j}")
            call(prof_for_call._replace(**{field: getattr(prof, field) - eps * direction}),
                 f"{field}-minus-{j}")
            plus = captured[f"{field}-plus-{j}"]; minus = captured[f"{field}-minus-{j}"]
            fd = (plus["bt"] - minus["bt"]) / (2.0 * eps)
            kpred = torch.as_tensor(base["result"][1][kfield], dtype=torch.float64)[0, :, layer]
            rq_same = torch.equal(plus["rq"], base["rq"]) and torch.equal(minus["rq"], base["rq"])
            quantum = _bt_resolution(base["root"] / "out/k/radiance.txt")["bt_quantum_upper_bound"]
            bound = quantum / (2.0 * eps) if quantum is not None else None
            rows = []
            for c in clean:
                signal = abs(float(kpred[c])); err = abs(float(fd[0, c] - kpred[c]))
                usable = bool(float(base["rq"][0, c]) == 0.0 and float(cols.obs_quality[column, c]) == 0.0)
                strong = bool(usable and signal > 0.0 and bound is not None and bound < 0.05 * signal
                              and err <= 0.05 * signal)
                rows.append({"channel_index": c, "mask_usable": usable, "strong_resolved": strong,
                             "FD": float(fd[0, c]), "K_direction": float(kpred[c]),
                             "abs_error": err, "relative_error": err / signal if signal else None})
            result["eps"].append({"epsilon": eps, "rad_quality_same": rq_same,
                                  "fd_rounding_bound": bound, "rows": rows,
                                  "input_serialization": {
                                      "plus": captured[f"{field}-plus-{j}"]["hydro6_serialization"],
                                      "minus": captured[f"{field}-minus-{j}"]["hydro6_serialization"]},
                                  "deff6_serialization": {
                                      "plus": captured[f"{field}-plus-{j}"]["hydro6_serialization"].get("deff6_changed_count"),
                                      "minus": captured[f"{field}-minus-{j}"]["hydro6_serialization"].get("deff6_changed_count")}})
        result["strong_resolved_channels"] = sorted({r["channel_index"] for e in result["eps"]
                                                       for r in e["rows"] if r["strong_resolved"]})
        result["status"] = "resolved_strong_channels" if result["strong_resolved_channels"] else "unresolved"
        return result

    content = run_fd("clw", "HYDRO6", content_lay,
                     (content_eps, content_eps / 2.0, content_eps / 4.0), "g/m^3")
    deff = run_fd("deff_liq", "HYDRO_DEFF6", deff_lay, (0.1, 0.03, 0.01), "micron")
    return {"content": content, "size": deff,
            "baseline_rad_quality_values": base["rq"].cpu().tolist(),
            "baseline_radiance": base["root"] and _bt_resolution(base["root"] / "out/k/radiance.txt"),
            "serialization_profile_format": "%.16E",
            "rttov_output_realprec": 12,
            "rttov_output_format": "E21.12",
            "claim": "first-order HYDRO6 and HYDRO_DEFF6 K only"}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--kdm", type=Path, default=DEFAULT_KDM)
    ap.add_argument("--gk2a-root", type=Path, default=DEFAULT_GK2A)
    ap.add_argument("--calibration", type=Path, default=DEFAULT_CAL)
    ap.add_argument("--stamp", default=DEFAULT_STAMP)
    ap.add_argument("--stride", type=int, default=8)
    ap.add_argument("--max-dist-km", type=float, default=4.0)
    ap.add_argument("--max-candidates", type=int, default=5)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    frame, payload, cols, clean, positive, files = _load_boundary(
        args.kdm, args.gk2a_root, args.calibration, args.stamp, args.stride, args.max_dist_km)
    if not positive:
        raise SystemExit("no hydrometeor-bearing assigned clean-IR columns")
    # Quantile candidates plus the maximum (the V3 failed extremecase negative control).
    idx = sorted(set([0, len(positive) - 1] +
                     [int(round(x)) for x in np.linspace(0, len(positive) - 1,
                                                          max(2, args.max_candidates))]))
    candidates = [positive[i] for i in idx]
    out = {"status": "diagnosis_complete", "selection_rule":
           "assigned clean-IR columns at deterministic hydrometeor quantiles; maximum retained as negative control",
           "assets": [_asset(args.kdm, "actual KDM frame", "actual"),
                      _asset(args.calibration, "GK2A calibration", "actual")],
           "slot": args.stamp, "n_positive_candidates": len(positive),
           "clean_ir_channels": [int(x) for x in clean], "probes": []}
    out["assets"].extend(_asset(p, "actual GK2A KO channel", "actual") for p in files)
    with tempfile.TemporaryDirectory(prefix="cloud-diagnosis-", dir=args.out.parent) as scratch:
        scratch = Path(scratch)
        for column, qtot in candidates:
            try:
                probe = _run_column(frame, cols, column, clean, out_parent=scratch, all_sky=True)
                probe["candidate_qtot"] = qtot
                out["probes"].append(probe)
            except Exception as exc:
                out["probes"].append({"column": column, "candidate_qtot": qtot,
                                      "status": "runtime_error", "error": repr(exc)})
        usable = [p for p in out["probes"] if p.get("clean_ir_joint_usable", 0) > 0]
        if usable:
            chosen = min(usable, key=lambda p: (p["candidate_qtot"], p["column"]))
            try:
                out["cloud_content_fd"] = _cloud_content_fd(
                    frame, cols, chosen["column"], clean, out_parent=scratch)
                out["fd_column"] = chosen["column"]
            except Exception as exc:
                out["cloud_content_fd"] = {"status": "runtime_error", "error": repr(exc)}
        else:
            out["cloud_content_fd"] = {"status": "unresolved", "reason": "no candidate has jointly usable clean IR"}
    args.out.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": out["status"], "probes": len(out["probes"]), "out": str(args.out)}))


if __name__ == "__main__":
    main()
