"""One native column: prep/KDM/cleanup/finish -> actual RTTOV BT and cost.

This is an offline first-order substep experiment, not a host timestep,
assimilation cycle, f32 parity campaign or higher-derivative contract.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

import numpy as np

from harness.verify_native_obs_ad import (
    CHANNELS, CLOUD_KEYS, DOT_RTOL, EPSILONS, FD_ATOL, FD_RTOL, PROFILE_KEYS,
    load_snapshot, pack, sha, unpack,
)
from harness.verify_native_prep_ad import pack_state, unpack_state


def validate_paths(args):
    """Refuse aliases/overlaps before loading libraries or touching inputs."""
    names = ("trace", "checkpoint", "namelist", "library", "kernel_build_manifest",
             "observations", "template", "executable", "time_audit")
    sources = {name: Path(getattr(args, name)).resolve() for name in names}
    if getattr(args, "native_number_admission", None) is not None:
        sources["native_number_admission"] = Path(args.native_number_admission).resolve()
    dest, work = Path(args.output), Path(args.workspace)
    if dest.exists() or dest.is_symlink() or dest.resolve() in sources.values():
        raise ValueError("output must be new and distinct from inputs")
    if work.exists() or work.is_symlink() or work.resolve() == dest.resolve():
        raise ValueError("workspace must be new and distinct from output")
    template = sources["template"]
    for label, target in (("output", dest.resolve()), ("workspace", work.resolve())):
        if target == template or template in target.parents or target in template.parents:
            raise ValueError(f"{label} and input template must be disjoint")
    if work.resolve() in dest.resolve().parents or dest.resolve() in work.resolve().parents:
        raise ValueError("output and workspace must be disjoint")
    return sources, dest, work


def verify_kernel_build(root, library, manifest_path):
    """Bind the reused research C ABI to its unchanged C++ build sources.

    The historical Fortran shim/test hashes are reported, not compared: this
    experiment calls C directly and the later INOUT fix did not change C++.
    """
    manifest = json.loads(Path(manifest_path).read_text())
    if sha(library) != manifest["library_sha256"]:
        raise ValueError("kernel library differs from the supplied build manifest")
    selected = {name: digest for name, digest in manifest["source_sha256"].items()
                if not name.endswith(".f90")}
    required = {"libtorch/src/runtime.cpp", "libtorch/bridge/kdm6_c_api.cpp",
                "libtorch/include/kdm6/runtime.h", "harness/verify_state_forcing_ad.py"}
    if not required.issubset(selected):
        raise ValueError("kernel build manifest omits required executed sources")
    for name, digest in selected.items():
        path = (root/name).resolve()
        if root.resolve() not in path.parents or sha(path) != digest:
            raise ValueError(f"research kernel source differs from build: {name}")
    return selected


def directions(x, rest, levels):
    """Admissible relative hydrometeor changes; zero reservoirs stay zero."""
    thm, qv, mu, ph = unpack_state(x, levels)
    phase = np.arange(levels)
    zero = [np.zeros_like(v) for v in (thm, qv, mu, ph)]
    result = {}
    for name, index, value in (
        ("theta_m", 0, .2*np.sin(.37*(phase+1))),
        ("qv", 1, .02*qv*np.cos(.29*(phase+2))),
    ):
        parts = [v.copy() for v in zero]
        parts[index] = value
        result[name] = (pack_state(parts), np.zeros_like(rest))
    dr = np.zeros_like(rest)
    for index in (0, 2, 3):  # QC, QI, QS in the ten remaining KDM blocks.
        dr[index] = .02*rest[index]*np.cos(.33*(phase+index+1))
    if np.any(dr):
        result["cloud_mass"] = (np.zeros_like(x), dr)
    dr = np.zeros_like(rest)
    for index in (6, 7):  # NC/NI remain in their captured legacy raw coordinates.
        dr[index] = .02*rest[index]*np.cos(.33*(phase+index+1))
    if np.any(dr):
        result["cloud_number"] = (np.zeros_like(x), dr)
    for name, index, value in (
        ("mu_total", 2, np.array(10.)),
        ("ph_interfaces", 3, 2.*np.sin(.31*(np.arange(levels+1)+1))),
    ):
        parts = [v.copy() for v in zero]
        parts[index] = value
        result[name] = (pack_state(parts), np.zeros_like(rest))
    result["mixed"] = (sum(v[0] for v in result.values()),
                       sum(v[1] for v in result.values()))
    return result


def fd_trial(epsilon, dbt, dcost, plus, minus, mask):
    """One common epsilon must resolve every retained channel and final cost."""
    fd_bt = (plus["bt"]-minus["bt"])/(2*epsilon)
    fd_cost = (plus["cost"]-minus["cost"])/(2*epsilon)
    ratio_bt = np.abs(fd_bt-dbt)/(FD_ATOL+FD_RTOL*np.maximum(np.abs(fd_bt), np.abs(dbt)))
    ratio_cost = abs(fd_cost-dcost)/(FD_ATOL+FD_RTOL*max(abs(fd_cost), abs(dcost)))
    return {"epsilon": epsilon, "eligible": True,
            "BT_FD": fd_bt.tolist(), "BT_per_channel_tolerance_ratio": ratio_bt.tolist(),
            "cost_FD": float(fd_cost), "cost_tolerance_ratio": float(ratio_cost),
            "max_tolerance_ratio": float(max(np.max(ratio_bt[mask > 0]), ratio_cost))}


def observation_arrays(y, levels):
    """The adapter's endpoint coordinate, distinct from packed prep controls."""
    size = 4*levels+1
    if not isinstance(y, np.ndarray) or y.dtype != np.float64:
        raise TypeError("post-finish observation state must be binary64")
    if y.shape != (10*levels+1,) or not np.isfinite(y).all():
        raise ValueError("post-finish observation state has invalid metadata")
    return (*unpack(y[:size], levels), *y[size:].reshape(6, levels))


def verify(args):
    sources, dest, work = validate_paths(args)
    root = Path(__file__).resolve().parents[1]
    build_sources = verify_kernel_build(root, sources["library"], sources["kernel_build_manifest"])
    files = {name: path for name, path in sources.items() if name != "template"}
    for directory in (root/"oracle/kdm6",):
        for path in sorted(directory.rglob("*.py")):
            files[str(path.relative_to(root))] = path
    for relative in ("harness/verify_microphysics_obs_ad.py", "harness/native_microphysics_obs.py",
                     "harness/native_prep_replay.py", "harness/native_finish_replay.py",
                     "harness/native_trace_records.py", "harness/native_replay_compare.py",
                     "harness/verify_native_obs_ad.py", "harness/verify_native_finish_ad.py",
                     "harness/verify_native_prep_ad.py", "harness/verify_state_forcing_ad.py",
                     "harness/run_ss_case.py", "oracle/kdm6/obs/data/gk2a_ami_cal_202507190000.json"):
        files[relative] = root/relative
    for relative in build_sources:
        files[relative] = root/relative
    if "native_number_admission" in sources:
        for relative in ("harness/native_number_boundary.py", "harness/native_number_qualification.py"):
            files[relative] = root/relative
    for directory in ("in", "out"):
        for path in sorted((sources["template"]/directory).rglob("*")):
            if path.is_file() and (directory == "in" or path.name in ("run.sh", "env.sh", "rttov_test.txt")):
                files["template/"+str(path.relative_to(sources["template"]))] = path
    from oracle.kdm6.obs.rttov_case_writer import _resolve_coef_path, make_live_run_k
    files["coefficient"] = _resolve_coef_path(sources["template"])
    run_text = (sources["template"]/"out/run.sh").read_text()
    bins = re.findall(r"(?m)^\s*([^#\s]+\.exe)\s", run_text)
    if len(bins) != 1 or Path(bins[0]).resolve() != sources["executable"]:
        raise ValueError("pinned executable differs from actual run.sh")
    if dest.resolve() in (p.resolve() for p in files.values()):
        raise ValueError("output aliases a pinned source")
    pinned = {name: sha(path) for name, path in files.items()}

    import torch
    from harness.native_microphysics_obs import MicrophysicsObservationState
    from harness.native_prep_replay import load_native_prep_case
    from harness.verify_native_finish_ad import KernelFinish, _api as finish_api
    from harness.verify_native_prep_ad import Prep
    from harness.verify_state_forcing_ad import Kernel
    from oracle.kdm6.obs import native_cloud_profile as cloud_api
    from oracle.kdm6.obs import native_profile_builder as profile_api
    from oracle.kdm6.obs.rttov_input_builder import RttovInputConfig
    from oracle.kdm6.obs.rttov_obs_operator import RttovObsOp
    from oracle.kdm6.obs.obs_loss import compute_obs_loss

    case = load_native_prep_case(sources["trace"], sources["namelist"], sources["checkpoint"],
                                 args.step, args.i, args.j, args.levels)
    snapshot = load_snapshot(sources["checkpoint"], sources["observations"], i=args.i, j=args.j,
                             expected_time=case.phase_provenance["checkpoint_time"], nominal_time=args.nominal_time,
                             time_audit=sources["time_audit"], namelist=sources["namelist"],
                             all_sky=True, levels=args.levels)
    prep = Prep(args.levels, case.geometry, case.config)
    api = finish_api()
    x = pack_state(case.X)
    rest = np.ascontiguousarray(case.captured.state[2:])
    admission = receipt = None
    if "native_number_admission" in sources:
        from harness.native_number_boundary import NativeDryNumberKernel
        from harness.native_number_qualification import apply_receipt
        receipt = json.loads(sources["native_number_admission"].read_text())
        base_forcing = prep.forward(x)
        volume_state = np.ascontiguousarray(np.vstack((base_forcing[0], case.X[1], rest)))
        bindings = {key: sha(sources[key]) for key in ("trace", "namelist", "checkpoint")}
        bindings.update(step=args.step, i=args.i, j=args.j, levels=args.levels,
                        base_native_X_sha256=hashlib.sha256(x.tobytes()).hexdigest())
        dry_state, admission = apply_receipt(receipt, volume_state, np.ascontiguousarray(base_forcing[1:]),
                                              bindings, sha(sources["native_number_admission"]))
        # Admission is fixed once at the reference point. Trial density is not
        # used to reinterpret archived values or regenerate dry-number controls.
        rest = np.ascontiguousarray(dry_state[2:])
    raw_kernel = Kernel(sources["library"], args.levels, case.captured.config["dt"],
                        case.xland, *case.captured.ncmin)
    kernel = raw_kernel if admission is None else NativeDryNumberKernel(raw_kernel, admission=admission)
    finish = KernelFinish(kernel, api.FinishConfig(**case.captured.config),
                          api.ZeroOutConfig(**case.captured.zero))
    adapter = MicrophysicsObservationState(prep, finish)
    geom = profile_api.FrozenNativeProfileGeometry(**{k: torch.from_numpy(v.copy()) for k, v in snapshot.geometry.items()})
    config = profile_api.NativeObservationConfig(**snapshot.constants)
    reference = profile_api.UpperReferenceProfile(**{k: torch.from_numpy(v.copy()) for k, v in snapshot.reference.items()},
                                                  fixed_upper_count=args.upper_layers)
    keys = PROFILE_KEYS+CLOUD_KEYS
    def project(*values):
        return cloud_api.native_to_rttov_cloud_profile(
            profile_api.NativeObservationState(*values[:4]), cloud_api.NativeCloudState(*values[5:]),
            geom, config, reference, rho_d=values[4], xland=snapshot.xland,
            ncmin_land=snapshot.ncmin[0], ncmin_sea=snapshot.ncmin[1])
    def profile_values(profile):
        return (profile.t_lay, profile.q_lay, profile.p_lay, profile.p_half,
                profile.clw, profile.ciw, profile.deff_liq, profile.deff_ice)
    work.mkdir(parents=True)
    template = work/"all_sky_template"
    shutil.copytree(sources["template"], template)
    actual = make_live_run_k(work/"trial", fixture_case_dir=template, ami_kma_bt=True, timeout=args.timeout)
    cached, calls = {}, []
    def run_k(rin):
        bt, k, quality = actual(rin)
        calls.append({"config_hash": rin.config_hash, "quality": np.asarray(quality).tolist()})
        cached.update(k=k)
        return bt, k, quality
    cfg = RttovInputConfig(coef_id=sha(files["coefficient"]), channels=CHANNELS, pressure_gradients=True)
    obs = {"bt": torch.from_numpy(snapshot.observation)}
    def evaluate(xx, rr, *, record=False):
        y, rec = adapter.forward(xx, rr, record=record)
        try:
            fields = tuple(torch.from_numpy(v.copy()).requires_grad_(record) for v in observation_arrays(y, args.levels))
            profile = project(*fields)
            bt, quality = RttovObsOp.apply(run_k, cfg, *profile_values(profile), profile.cfrac)
            mask = torch.from_numpy(snapshot.obs_mask)*(quality == 0).to(torch.float64)
            if not bool(mask.any()):
                raise ValueError("no observed channel survives RTTOV quality")
            cost = compute_obs_loss(bt, obs, mask, args.sigma, delta=args.huber_delta)
            # Explicit serialization of value-only checkpoints and first-order
            # products; no higher graph crosses the opaque C handle boundary.
            result = {"cost": float(cost.detach()), "bt": bt.detach().numpy(),
                      "mask": mask.numpy(), "cf": profile.cfrac.detach().numpy(),
                      "signature": adapter.branch_signature(rec), "state": y}
            if record:
                seed = torch.autograd.grad(cost, bt, retain_graph=True)[0]
                gy = pack([g.detach().numpy() for g in torch.autograd.grad(cost, fields)])
                result.update(seed=seed.detach().numpy(), gy=gy, fields=fields, profile=profile,
                              record=rec, k={key: np.asarray(cached["k"][key]).copy() for key in keys})
            return result
        except BaseException:
            if record:
                adapter.close(rec)
            raise
        finally:
            if not record:
                adapter.close(rec)

    base = evaluate(x, rest, record=True)
    try:
        gx, gr = adapter.vjp(base["record"], base["gy"])
        reports = {}
        trial_directions = directions(x, rest, args.levels)
        if admission is not None:
            from oracle.kdm6 import constants
            phase = np.arange(args.levels)
            # Probe NN away from its declared entry clamp; zero reservoirs
            # and bound cells stay fixed rather than crossing a known kink.
            entry = base["record"].handle.volume_input
            interior = (entry[7] > constants.NCCN_MIN*1.000001) & (entry[7] < constants.NCCN_MAX*.999999)
            for name, row, mask in (("nccn_number", 5, interior),
                                    ("rain_number", 8, np.ones(args.levels, dtype=bool))):
                dr = np.zeros_like(rest)
                dr[row] = .02*rest[row]*np.cos(.33*(phase+row+1))*mask
                if np.any(dr):
                    trial_directions[name] = (np.zeros_like(x), dr)
                    mx, mr = trial_directions["mixed"]
                    trial_directions["mixed"] = (mx, mr+dr)
        for name, (dx, dr) in trial_directions.items():
            dy = adapter.jvp(base["record"], dx, dr)
            vs = tuple(torch.from_numpy(v.copy()) for v in observation_arrays(dy, args.levels))
            _, products = torch.autograd.functional.jvp(lambda *v: profile_values(project(*v)), base["fields"], vs)
            dbt = sum(np.einsum("pcl,l->pc", base["k"][key], value.detach().numpy())
                      for key, value in zip(keys, products))
            lhs = float(np.sum(dbt*base["seed"]))
            rhs = float(np.sum(gx*dx)+np.sum(gr*dr))
            dot = abs(lhs-rhs)/max(abs(lhs), abs(rhs), 1e-12)
            trials = []
            for eps in EPSILONS:
                try:
                    plus = evaluate(x+eps*dx, rest+eps*dr)
                    minus = evaluate(x-eps*dx, rest-eps*dr)
                    eligible = all(np.array_equal(r[key], base[key])
                                   for r in (plus, minus) for key in ("mask", "cf", "signature"))
                    trial = fd_trial(eps, dbt, rhs, plus, minus, base["mask"])
                    trial["eligible"] = eligible
                    trials.append(trial)
                except ValueError as exc:
                    trials.append({"epsilon": eps, "eligible": False, "reason": str(exc)})
            candidates = [r for r in trials if r["eligible"]]
            best = min(candidates, key=lambda r: r["max_tolerance_ratio"]) if candidates else None
            no_pressure = sum(np.einsum("pcl,l->pc", base["k"][key], value.detach().numpy())
                              for key, value in zip(keys, products) if key not in ("P", "P_HALF"))
            reports[name] = {"dot_lhs": lhs, "dot_rhs": rhs, "dot_relative_error": dot,
                             "BT_JVP": dbt.tolist(), "cost_direction_without_RTTOV_pressure_K": float(np.sum(no_pressure*base["seed"])),
                             "best_epsilon": None if best is None else best["epsilon"],
                             "best_max_tolerance_ratio": None if best is None else best["max_tolerance_ratio"],
                             "direction_x": dx.tolist(), "direction_rest": dr.tolist(), "trials": trials,
                             "passed": bool(best and best["max_tolerance_ratio"] <= 1 and dot <= DOT_RTOL)}
        report = {"schema": ("kdm6.microphysics_observation_ad.v1" if admission is None else
                             "kdm6.microphysics_observation_ad.native_dry_numbers.v1"),
                  "source": {k: str(v) for k, v in files.items()},
                  "input_sha256": pinned, "verified_kernel_build_sources": build_sources,
                  "kernel_contract": {"physics_variant": 0, "dry_number": 0, "dt_seconds": kernel.dt,
                                      "xland": case.xland, "ncmin_land_sea": case.captured.ncmin,
                                      "state_blocks": 12, "forcing_order": ["DEN", "PII", "P", "DELZ"]},
                  "native_prep_phase": case.phase_provenance, "native_f32_replay": case.f32_replay,
                  "native_snapshot": snapshot.provenance,
                  "native_X": x.tolist(), "native_rest": rest.tolist(), "post_finish_observation_state": base["state"].tolist(),
                  "kernel_after": base["record"].raw_after.tolist(),
                  "clean_after": base["record"].clean_after.tolist(),
                  "applied_finish": dict(zip(("T_NEW_AFTER", "H_RATE", "QV_RATE", "QC_RATE", "TH_PHY_M_T0"),
                                             base["record"].finish_value.tolist())),
                  "post_finish_cost_covector": base["gy"].tolist(), "native_X_cost_covector": gx.tolist(),
                  "native_rest_cost_covector": gr.tolist(), "branch_signature": base["signature"].tolist(),
                  "criterion": {"FD_atol": FD_ATOL, "FD_rtol": FD_RTOL, "dot_rtol": DOT_RTOL, "epsilons": EPSILONS},
                  "channels": CHANNELS, "observation": snapshot.observation.tolist(), "BT_KMA": base["bt"].tolist(),
                  "mask": base["mask"].tolist(), "cost": base["cost"], "sigma_K": args.sigma, "Huber_delta": args.huber_delta,
                  "cloud_fraction": base["cf"].tolist(), "profile_K": {k: v.tolist() for k, v in base["k"].items()},
                  "profile": {k: v.detach().numpy().tolist() for k, v in zip(keys, profile_values(base["profile"]))},
                  "directions": reports, "external_RTTOV_calls": len(calls),
                  "passed": bool(reports) and all(r["passed"] for r in reports.values()),
                  "limits": "offline native one-column continuous fp64 substep; fixed hybrid/reference/surface/trace-gas geometry; same MU/PH through finish, post-EOS recomputed; legacy raw KDM numbers interpreted conditionally under Registry optical convention; no RK/retained-memory/host-window/optimization/HVP or applied mass/number-budget certificate; pixel time unknown; whole-reference pressure counterexample unresolved"}
        if admission is not None:
            boundary_handle = base["record"].handle
            report["number_boundary"] = {
                "version": "kdm6.native_dry_number.v1", "admission": receipt,
                "research_coordinate_units": "NN/NC/NI/NR number per kg dry air, defined by the explicit receipt; not certification of original host payload",
                "internal_units": "NN/NC/NI/NR kernel volume operands",
                "physical_forcing_unchanged": bool(np.array_equal(
                    boundary_handle.forcing.view(np.uint64), prep.forward(x)[1:].view(np.uint64))),
                "kernel_volume_input": boundary_handle.volume_input.tolist(),
                "kernel_volume_output": boundary_handle.volume_output.tolist(),
                "entry_dry_density": boundary_handle.rho_dry.tolist(),
                "original_host_payload_basis_certified": False,
            }
            report["limits"] = (
                "versioned research dry-number boundary over legacy K with unchanged native DEN/PII/P/DELZ; "
                "input is a fixed declared coordinate pullback of traced kernel-volume operands, not a host/checkpoint unit certificate; "
                "all four number controls/output are dry-specific; no first-step producer or restart migration; "
                "one-column continuous fp64 split map with fixed MU/PH through finish and live prep geometry; "
                "fixed reference/surface/gases, +40s nominal KO offset/pixel time unknown, reconstructed P8W; "
                "no RK/full-host/window optimization/HVP/conservation/skill certificate; whole-reference pressure counterexample retained")
    finally:
        adapter.close(base["record"])
    if any(sha(files[name]) != digest for name, digest in pinned.items()):
        raise RuntimeError("a pinned input/source changed during verification")
    with dest.open("x") as stream:
        stream.write(json.dumps(report, indent=2, allow_nan=False)+"\n")
    print(json.dumps({"passed": report["passed"], "calls": len(calls),
                      "directions": {name: {k: v for k, v in r.items() if k in ("passed", "dot_relative_error", "best_max_tolerance_ratio")}
                                     for name, r in reports.items()}}, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("trace", "checkpoint", "namelist", "library", "kernel-build-manifest", "observations",
                 "template", "executable", "time-audit", "workspace", "output"):
        p.add_argument("--"+name, type=Path, required=True)
    p.add_argument("--step", type=int, default=2)
    p.add_argument("--i", type=int, default=156)
    p.add_argument("--j", type=int, default=21)
    p.add_argument("--levels", type=int, default=39)
    p.add_argument("--upper-layers", type=int, default=27)
    p.add_argument("--nominal-time", default="2025-07-19_00:00:00")
    p.add_argument("--sigma", type=float, default=1.)
    p.add_argument("--huber-delta", type=float, default=1.)
    p.add_argument("--timeout", type=float, default=300.)
    p.add_argument("--native-number-admission", type=Path,
                   help="Opt in to native dry-number v1 using an explicit qualified input receipt")
    verify(p.parse_args())
