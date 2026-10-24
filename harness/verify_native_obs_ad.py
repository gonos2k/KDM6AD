"""Verify a saved native column's T/Q/pressure/cloud path through real RTTOV-K.

No host integration or optimization is performed. Satellite pixel acquisition
time is not established by the archived KO product; nominal-slot cost evidence
must not be promoted to an operational time-collocation certificate.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil

import numpy as np

EPSILONS = (1e-2, 3e-3, 1e-3, 3e-4, 1e-4)
FD_ATOL, FD_RTOL, DOT_RTOL = 1e-8, 3e-5, 1e-10
PROFILE_KEYS = ("T", "Q", "P", "P_HALF")
CLOUD_KEYS = ("HYDRO6", "HYDRO7", "HYDRO_DEFF6", "HYDRO_DEFF7")
CHANNELS = tuple(range(10, 17))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def _api():
    from oracle.kdm6.obs import native_profile_builder
    return native_profile_builder


def pack(values):
    return np.ascontiguousarray(np.concatenate([v.reshape(-1) for v in values]), dtype=np.float64)


def unpack(x, levels):
    if not isinstance(x, np.ndarray) or x.dtype != np.float64:
        raise TypeError("native column must be a binary64 ndarray")
    if x.shape != (4*levels+1,) or not np.isfinite(x).all():
        raise ValueError("native column must contain three L vectors and L+1 interfaces, all finite")
    return x[:levels], x[levels:2*levels], x[2*levels:3*levels], x[3*levels:]


@dataclass
class Snapshot:
    x: np.ndarray
    geometry: dict
    constants: dict
    reference: dict
    observation: np.ndarray
    obs_mask: np.ndarray
    provenance: dict
    cloud: dict | None = None
    rho_d: np.ndarray | None = None
    ncmin: tuple = (0., 0.)
    xland: float | None = None


def load_snapshot(checkpoint, observations, *, i, j, expected_time, time_audit, levels=39,
                  nominal_time=None, namelist=None, all_sky=False):
    """Read the same completed checkpoint for every native model/profile field."""
    import netCDF4
    from harness.native_replay_compare import _read_frame, _decoded_char_frame
    if (levels != 39 or type(i) is not int or type(j) is not int
            or not (1 <= i <= 234 and 1 <= j <= 282)):
        raise ValueError("this evidence loader requires a column of the native 234x282x39 grid")
    i0, j0, index = i-1, j-1, (j-1)*234+i-1
    audit = json.loads(Path(time_audit).read_text())
    nominal_time = expected_time if nominal_time is None else nominal_time
    nominal = datetime.strptime(nominal_time, "%Y-%m-%d_%H:%M:%S").strftime("%Y%m%d%H%M")
    slots = {row["filename_nominal_slot"] for row in audit["KO_original_files"]}
    if slots != {nominal}:
        raise ValueError("KO source nominal slot differs from the requested nominal KO slot")
    ncmin = (0., 0.)
    if namelist is not None:
        from harness.run_ss_case import _namelist_assignments
        nml = _namelist_assignments(Path(namelist).read_text())
        def first(name):
            return float(nml[name][0].replace("D", "E").replace("d", "e"))
        if first("mp_physics") != 137 or first("use_theta_m") != 1:
            raise ValueError("native profile requires the selected MP137 moist-theta coordinate")
        ncmin = tuple(float(np.float32(first(n))) for n in ("ncmin_land", "ncmin_sea"))
    elif all_sky:
        raise ValueError("native cloud mapping requires the executed namelist and number thresholds")
    cloud = rho_d = xland = None
    with netCDF4.Dataset(checkpoint) as ds:
        ds.set_auto_maskandscale(False)
        if namelist is not None and (getattr(ds, "MP_PHYSICS", None) != 137 or
                                     getattr(ds, "USE_THETA_M", None) != 1):
            raise ValueError("checkpoint physics/thermodynamic coordinate differs from MP137/use_theta_m=1")
        for name, size in (("west_east", 234), ("south_north", 282),
                           ("bottom_top", 39), ("bottom_top_stag", 40)):
            if len(ds.dimensions.get(name, ())) != size:
                raise ValueError(f"checkpoint {name} dimension differs from the native case")
        tv = ds.variables["Times"]
        if np.dtype(tv.dtype).kind not in ("S", "U") or "Time" not in tv.dimensions:
            raise ValueError("checkpoint Times must be a Time-indexed character variable")
        stamp = _decoded_char_frame(_read_frame(tv, 0))
        if stamp != expected_time:
            raise ValueError(f"checkpoint Times {stamp} != requested model boundary {expected_time}")
        def column(name, interface=False):
            v = ds.variables[name]
            dims = ("Time", "bottom_top_stag" if interface else "bottom_top", "south_north", "west_east")
            if tuple(v.dimensions) != dims or np.dtype(v.dtype).kind != "f" or np.dtype(v.dtype).itemsize != 4:
                raise ValueError(f"{name} must be a native binary32 field on {dims}")
            if any(a in v.ncattrs() for a in ("scale_factor", "add_offset")):
                raise ValueError(f"packed field {name} is unsupported")
            out = np.asarray(v[0, :, j0, i0], dtype=np.float32)
            if not np.isfinite(out).all():
                raise ValueError(f"{name} has nonfinite values")
            return out
        thm, qv = column("THM_2"), column("QVAPOR")
        # Explicit native REAL4 sums are widened once. The continuous profile
        # operator's arithmetic is then fp64, rather than f32 rounding AD.
        pc = np.asarray(column("P")+column("PB"), dtype=np.float32)
        phi = np.asarray(column("PH_2", True)+column("PHB", True), dtype=np.float32)
        geometry = {}
        for name in ("FNM", "FNP"):
            v = ds.variables[name]
            a = np.asarray(_read_frame(v, 0))
            if tuple(v.dimensions) != ("Time", "bottom_top") or a.dtype.kind != "f" or a.dtype.itemsize != 4 or a.shape != (levels,):
                raise ValueError(f"{name} must be the native REAL4 mass-level weights")
            geometry[name.lower()] = a.astype(np.float64)
        if all_sky:
            cloud = {key: column(name).astype(np.float64) for key, name in (
                ("qc", "QCLOUD"), ("qi", "QICE"), ("qs", "QSNOW"),
                ("nc", "QNCLOUD"), ("ni", "QNICE"))}
            volume = np.asarray(column("AL")+column("ALB"), dtype=np.float32)
            if np.any(volume <= 0):
                raise ValueError("native dry-air volume must be positive")
            rho_d = np.asarray(np.float32(1.)/volume, dtype=np.float32).astype(np.float64)
            xland = float(ds.variables["XLAND"][0, j0, i0])
    with np.load(observations, allow_pickle=False) as archive:
        # The bound snapshot archive stores one already-selected time, either
        # as a scalar string or a character vector, not a NetCDF Time axis.
        source_stamp = _decoded_char_frame(archive["history__Times"])
        if source_stamp != nominal_time:
            raise ValueError("observation bundle background time differs from its nominal KO slot")
        if not np.array_equal(archive["ko_channel_ids_1based"], CHANNELS):
            raise ValueError("archived KO channel order differs from the requested seven channels")
        obs = np.asarray(archive["obs_bt"][index], dtype=np.float64)
        dqf, qc = archive["obs_dqf"][index], archive["obs_qc"][index]
        mask = np.asarray((dqf == 0) & (qc == 0), dtype=np.float64)
        if obs.shape != (7,) or mask.shape != (7,) or not np.isfinite(obs[mask > 0]).all() or not mask.any():
            raise ValueError("selected KO observation is invalid or has no usable channel")
        reference = {new: np.asarray(archive[old], dtype=np.float64) for new, old in (
            ("p_lay_hpa", "rttov_reference__p_lay_hPa"),
            ("p_half_hpa", "rttov_reference__p_half_hPa"),
            ("t_k", "rttov_reference__t_K"), ("q_ppmv", "rttov_reference__q_ppmv"))}
    constants = dict(alpha=float(np.array(0x3FCDDED2, dtype=np.uint32).view(np.float32)),
                     t0=300., kappa=float(np.array(0x3E924925, dtype=np.uint32).view(np.float32)),
                     p0=100000., g=float(np.float32(9.81)))
    return Snapshot(pack([v.astype(np.float64) for v in (thm, qv, pc, phi)]), geometry,
                    constants, reference, obs[None, :], mask[None, :],
                    {"checkpoint_time": stamp, "nominal_KO_slot": nominal_time,
                     "model_minus_nominal_slot_seconds": (datetime.strptime(stamp, "%Y-%m-%d_%H:%M:%S")-
                         datetime.strptime(nominal_time, "%Y-%m-%d_%H:%M:%S")).total_seconds(),
                     "observation_time_audit_status": audit["status"],
                     "pixel_acquisition_time_verified": False,
                     "native_indices_1based": [i, j], "native_flat_index0": index,
                     "native_levels": levels, "native_interfaces": levels+1,
                     "coordinate": "native moist-theta perturbation, QV dry mass ratio, full Pa pressure, full geopotential",
                     "scope": "same-checkpoint model fields, nominal-slot diagnostic cost; no exact pixel-time collocation proof"},
                    cloud, rho_d, ncmin, xland)


def clear_template(source, target):
    """Copy a prepared native-size case; freeze its trace gases/surface/geometry."""
    source, target = Path(source), Path(target)
    if target.exists() or target.is_symlink():
        raise ValueError("clear template target must be new")
    source, target = source.resolve(), target.resolve()
    if source == target or source in target.parents or target in source.parents:
        raise ValueError("native template source and target must be disjoint")
    shutil.copytree(source, target)
    for path in (target/"out").iterdir():
        if path.name in ("direct", "k") and path.is_dir():
            # The test driver opens files in these existing directories; it
            # does not create the directories itself.
            for child in path.iterdir():
                shutil.rmtree(child) if child.is_dir() else child.unlink()
        elif path.name not in ("run.sh", "env.sh", "rttov_test.txt"):
            shutil.rmtree(path) if path.is_dir() else path.unlink()
    for relative, keys in (("out/rttov_test.txt", ("f_hydro", "f_hydro_frac")),
                           ("in/coef.txt", ("f_hydrotable",))):
        path = target/relative
        text = path.read_text()
        for key in keys:
            text, count = re.subn(rf"(?mi)^([ \t]*defn%{key}[ \t]*=)[^\n]*$",
                                  lambda m: m.group(1)+" ''", text)
            if count != 1:
                raise ValueError(f"expected one {key} in the copied native case")
        path.write_text(text)
    simple = target/"in/profiles/001/atm/simple_cloud.txt"
    text, count = re.subn(r"(?mi)^([ \t]*cfraction[ \t]*=)[^\n]*$",
                          lambda m: m.group(1)+" 0.0", simple.read_text())
    if count != 1:
        raise ValueError("expected one simple-cloud fraction in the native template")
    simple.write_text(text)


def verify(args):
    dest, work = Path(args.output), Path(args.workspace)
    initial = [Path(getattr(args, n)).resolve() for n in
               ("checkpoint", "observations", "template", "executable", "time_audit")]
    if dest.resolve() in initial or dest.exists() or dest.is_symlink():
        raise ValueError("output must be new and distinct from all inputs and sources")
    if work.exists() or work.is_symlink() or work.resolve() == dest.resolve():
        raise ValueError("workspace must be new and distinct from output")
    template_path = Path(args.template).resolve()
    if template_path in dest.resolve().parents or dest.resolve() in template_path.parents:
        raise ValueError("output and input template must be disjoint")
    if work.resolve() in template_path.parents or template_path in work.resolve().parents:
        raise ValueError("workspace and input template must be disjoint")
    import torch
    from oracle.kdm6.obs.rttov_input_builder import RttovInputConfig
    from oracle.kdm6.obs.rttov_case_writer import make_live_run_k, _resolve_coef_path
    from oracle.kdm6.obs.rttov_obs_operator import RttovObsOp
    from oracle.kdm6.obs.obs_loss import compute_obs_loss
    root = Path(__file__).resolve().parents[1]
    source = {n: Path(getattr(args, n)).resolve() for n in ("checkpoint", "observations", "template", "executable", "time_audit", "namelist")}
    files = {n: p for n, p in source.items() if n != "template"}
    for relative in ("harness/verify_native_obs_ad.py", "harness/native_replay_compare.py",
                     "oracle/kdm6/obs/native_profile_builder.py", "oracle/kdm6/obs/model_profile_builder.py",
                     "oracle/kdm6/obs/rttov_input_builder.py", "oracle/kdm6/obs/rttov_obs_operator.py",
                     "oracle/kdm6/obs/rttov_case_writer.py", "oracle/kdm6/obs/rttov_runner.py",
                     "oracle/kdm6/obs/_rttov_reference/rttov_ascii.py", "oracle/kdm6/obs/obs_loss.py",
                     "oracle/kdm6/obs/ami_bt_coordinate.py", "oracle/kdm6/obs/gk2a_l1b.py",
                     "oracle/kdm6/obs/data/gk2a_ami_cal_202507190000.json"):
        files[relative] = root/relative
    files["harness/run_ss_case.py"] = root/"harness/run_ss_case.py"
    if args.all_sky:
        files["oracle/kdm6/obs/native_cloud_profile.py"] = root/"oracle/kdm6/obs/native_cloud_profile.py"
        # The existing DSD observation bridge imports the physical preamble and
        # its parameters. Pin that source tree rather than only the thin adapter.
        for path in sorted((root/"oracle/kdm6").glob("*.py")):
            files[str(path.relative_to(root))] = path
    for relative in ("out/rttov_test.txt", "out/run.sh", "out/env.sh", "in/coef.txt"):
        files["template/"+relative] = source["template"]/relative
    for path in sorted((source["template"]/"in/profiles/001").rglob("*")):
        if path.is_file():
            files["template/"+str(path.relative_to(source["template"]))] = path
    files["coefficient"] = _resolve_coef_path(source["template"])
    if dest.resolve() in files.values() or dest.exists() or dest.is_symlink():
        raise ValueError("output must be new and distinct from all inputs and sources")
    if work.exists() or work.is_symlink():
        raise ValueError("workspace must be new")
    # Pin the actual executable named by run.sh, not a merely supplied binary.
    run_text = (source["template"]/"out/run.sh").read_text()
    bins = re.findall(r"(?m)^\s*([^#\s]+\.exe)\s", run_text)
    if len(bins) != 1 or Path(bins[0]).resolve() != source["executable"]:
        raise ValueError("the pinned executable differs from the actual template run.sh")
    pinned = {n: sha(p) for n, p in files.items()}
    snapshot = load_snapshot(source["checkpoint"], source["observations"], i=args.i, j=args.j,
                             expected_time=args.model_time, nominal_time=args.nominal_time,
                             time_audit=source["time_audit"], namelist=source["namelist"],
                             all_sky=args.all_sky, levels=args.levels)
    api = _api()
    geom = api.FrozenNativeProfileGeometry(**{k: torch.from_numpy(v.copy()) for k, v in snapshot.geometry.items()})
    config = api.NativeObservationConfig(**snapshot.constants)
    reference = api.UpperReferenceProfile(**{k: torch.from_numpy(v.copy()) for k, v in snapshot.reference.items()},
                                           fixed_upper_count=args.upper_layers)
    native_size = 4*args.levels+1
    controls = snapshot.x.copy()
    keys = PROFILE_KEYS
    control_names = ("theta_m_pert", "qv", "p_center_Pa", "phi_interfaces")
    if args.all_sky:
        from oracle.kdm6.obs import native_cloud_profile as cloud_api
        controls = np.concatenate((controls, snapshot.rho_d, *(snapshot.cloud[k] for k in ("qc", "qi", "qs", "nc", "ni"))))
        keys += CLOUD_KEYS
        control_names += ("rho_d", "qc", "qi", "qs", "nc", "ni")
    def control_arrays(x):
        expected = native_size+(6*args.levels if args.all_sky else 0)
        if not isinstance(x, np.ndarray) or x.dtype != np.float64 or x.shape != (expected,) or not np.isfinite(x).all():
            raise ValueError("native observation control vector has invalid shape, dtype or finite values")
        values = list(unpack(x[:native_size], args.levels))
        if args.all_sky:
            values += list(x[native_size:].reshape(6, args.levels))
        return values
    def state(x, *, grad=False):
        return tuple(torch.from_numpy(v.copy()).requires_grad_(grad) for v in control_arrays(x))
    def project(*values):
        native = api.NativeObservationState(*values[:4])
        if not args.all_sky:
            return api.native_to_rttov_profile(native, geom, config, reference)
        return cloud_api.native_to_rttov_cloud_profile(
            native, cloud_api.NativeCloudState(*values[5:]), geom, config, reference,
            rho_d=values[4], xland=torch.tensor([snapshot.xland], dtype=torch.float64),
            ncmin_land=snapshot.ncmin[0], ncmin_sea=snapshot.ncmin[1])
    def profile_values(p):
        values = (p.t_lay, p.q_lay, p.p_lay, p.p_half)
        if args.all_sky:
            values += (p.clw, p.ciw, p.deff_liq, p.deff_ice)
        return values
    work.mkdir(parents=True)
    template = work/"clear_template"
    if args.all_sky:
        shutil.copytree(source["template"], template)
    else:
        clear_template(source["template"], template)
    actual = make_live_run_k(work/"trial", fixture_case_dir=template, ami_kma_bt=True, timeout=args.timeout)
    calls = []
    cached = {}
    def run_k(rin):
        bt, k, rq = actual(rin)
        calls.append({"config_hash": rin.config_hash, "quality": np.asarray(rq).tolist()})
        cached.update(k=k)
        return bt, k, rq
    cfg = RttovInputConfig(coef_id=sha(files["coefficient"]), channels=CHANNELS, pressure_gradients=True)
    obs = {"bt": torch.from_numpy(snapshot.observation)}
    def evaluate(x, *, grad=False):
        s = state(x, grad=grad)
        p = project(*s)
        arguments = (run_k, cfg, *profile_values(p)[:4])
        if args.all_sky:
            arguments += (*profile_values(p)[4:], p.cfrac)
        bt, rq = RttovObsOp.apply(*arguments)
        mask = torch.from_numpy(snapshot.obs_mask)*(rq == 0).to(torch.float64)
        if not bool(mask.any()):
            raise ValueError("no channel survives the observed/RTTOV quality mask")
        cost = compute_obs_loss(bt, obs, mask, args.sigma, delta=args.huber_delta)
        return cost, bt, mask, s, p
    cost, bt, mask, fields, profile = evaluate(controls, grad=True)
    seed = torch.autograd.grad(cost, bt, retain_graph=True)[0]
    gradient = torch.autograd.grad(cost, fields)
    # Explicit serialization of first-order covectors, outside the live graph.
    gx = pack([v.detach().numpy() for v in gradient])
    base_bt = bt.detach().numpy()
    base_mask = mask.detach().numpy()
    base_cost = float(cost.detach())
    base_k = {key: np.asarray(cached["k"][key], dtype=np.float64).copy() for key in keys}
    base_cf = None if not args.all_sky else profile.cfrac.detach().numpy()
    base_seed = seed.detach().numpy()
    phase = np.arange(args.levels)
    ds = [np.zeros_like(v) for v in control_arrays(controls)]
    ds[0] = .2*np.sin(.37*(phase+1))
    ds[1] = .02*control_arrays(controls)[1]*np.cos(.29*(phase+2))
    ds[2] = 10.*np.cos(.31*(phase+1))
    ds[3] = 2.*np.sin(.27*(np.arange(args.levels+1)+1))
    directions = {}
    for i, name in enumerate(("theta_m", "qv", "pressure", "geopotential")):
        only = [np.zeros_like(v) for v in ds]
        only[i] = ds[i]
        directions[name] = pack(only)
    # Retain the original very small PH direction and add a larger one so its
    # pressure-only BT signal can be resolved above external-run roundoff.
    directions["geopotential_resolved"] = 1000.*directions["geopotential"]
    if args.all_sky:
        raw = control_arrays(controls)
        ds[4] = .01*raw[4]*np.sin(.31*(phase+1))
        for index in range(5, 10):
            ds[index] = .02*raw[index]*np.cos(.33*(phase+index))
        for name, indices in (("dry_density", (4,)), ("cloud_mass", (5, 6, 7)),
                              ("cloud_number", (8, 9))):
            only = [np.zeros_like(v) for v in ds]
            for index in indices:
                only[index] = ds[index]
            if any(np.any(v) for v in only):
                directions[name] = pack(only)
    directions["mixed"] = pack(ds)
    reports = {}
    for name, direction in directions.items():
        vs = tuple(torch.from_numpy(v.copy()) for v in control_arrays(direction))
        def outputs(*values):
            return profile_values(project(*values))
        _, products = torch.autograd.functional.jvp(outputs, fields, vs)
        dbt = sum(np.einsum("pcl,l->pc", base_k[key], v.detach().numpy())
                  for key, v in zip(keys, products))
        lhs = float(np.sum(dbt*base_seed))
        rhs = float(np.sum(gx*direction))
        dot = abs(lhs-rhs)/max(abs(lhs), abs(rhs), 1e-12)
        trials = []
        for eps in EPSILONS:
            try:
                plus = evaluate(controls+eps*direction)
                minus = evaluate(controls-eps*direction)
                cp, bp, mp = (float(plus[0].detach()), plus[1].detach().numpy(), plus[2].numpy())
                cm, bm, mm = (float(minus[0].detach()), minus[1].detach().numpy(), minus[2].numpy())
                eligible = bool(np.array_equal(mp, base_mask) and np.array_equal(mm, base_mask))
                if args.all_sky:
                    eligible &= bool(np.array_equal(plus[4].cfrac.detach().numpy(), base_cf) and
                                     np.array_equal(minus[4].cfrac.detach().numpy(), base_cf))
                fd_bt = (bp-bm)/(2*eps)
                fd_cost = (cp-cm)/(2*eps)
                ratio_bt = np.abs(fd_bt-dbt)/(FD_ATOL+FD_RTOL*np.maximum(np.abs(fd_bt), np.abs(dbt)))
                ratio_cost = abs(fd_cost-rhs)/(FD_ATOL+FD_RTOL*max(abs(fd_cost), abs(rhs)))
                kept_ratio = ratio_bt[base_mask > 0]
                trials.append({"epsilon": eps, "eligible": eligible,
                               "BT_per_channel_tolerance_ratio": ratio_bt.tolist(),
                               "cost_FD": fd_cost, "cost_tolerance_ratio": float(ratio_cost),
                               "max_tolerance_ratio": float(max(np.max(kept_ratio), ratio_cost))})
            except ValueError as exc:
                trials.append({"epsilon": eps, "eligible": False, "reason": str(exc)})
        eligible = [t for t in trials if t["eligible"]]
        best = min(eligible, key=lambda t: t["max_tolerance_ratio"]) if eligible else None
        frozen_pressure_dbt = sum(np.einsum("pcl,l->pc", base_k[key], v.detach().numpy())
                                  for key, v in zip(keys, products) if key not in ("P", "P_HALF"))
        reports[name] = {"dot_lhs": lhs, "dot_rhs": rhs, "dot_relative_error": dot,
                         "BT_JVP": dbt.tolist(), "cost_VJP_direction": rhs,
                         "cost_direction_without_RTTOV_pressure_K": float(np.sum(frozen_pressure_dbt*base_seed)),
                         "best_epsilon": None if best is None else best["epsilon"],
                         "best_max_tolerance_ratio": None if best is None else best["max_tolerance_ratio"],
                         "trials": trials, "passed": bool(best and best["max_tolerance_ratio"] <= 1 and dot <= DOT_RTOL)}
    if any(sha(files[n]) != value for n, value in pinned.items()):
        raise RuntimeError("a pinned input, template, executable or helper changed during verification")
    report = {"schema": "kdm6.native_observation_ad.v1", "source": {n: str(p) for n, p in files.items()},
              "input_sha256": pinned, "native_snapshot": snapshot.provenance,
              "all_sky": args.all_sky,
              "constants": snapshot.constants, "channels": CHANNELS,
              "criterion": {"FD_atol": FD_ATOL, "FD_rtol": FD_RTOL, "dot_rtol": DOT_RTOL, "epsilons": EPSILONS},
              "observation": snapshot.observation.tolist(), "BT_KMA": base_bt.tolist(),
              "mask": base_mask.tolist(), "cost": base_cost, "sigma_K": args.sigma,
              "Huber_delta": args.huber_delta, "native_upper_layers": args.upper_layers,
              "pressure_K_maxabs": {key: float(np.max(np.abs(base_k[key]))) for key in ("P", "P_HALF")},
              "profile": {key: value.detach().numpy().tolist() for key, value in zip(keys, profile_values(profile))},
              "profile_K": {key: value.tolist() for key, value in base_k.items()},
              "control_order": control_names,
              "native_controls": {name: value.tolist() for name, value in zip(control_names, control_arrays(controls))},
              "native_cost_covector_fields": {name: value.detach().numpy().tolist() for name, value in zip(control_names, gradient)},
              "native_cost_covector": gx.tolist(),
              "cloud_fraction": None if base_cf is None else base_cf.tolist(),
              "directions": reports, "external_RTTOV_calls": len(calls),
              "passed": all(r["passed"] for r in reports.values()),
              "limits": "one native T/Q/pressure column; optional qc/qi/qs/nc/ni IR cloud bridge and explicit live dry density; fixed O3/CO2 layer values, surface and geometry; nominal KO slot/pixel time unverified; no native integration, optimization, complete HostWindow, RK or HVP; rain/graupel not mapped to the legacy VIS/IR slots"}
    with dest.open("x") as stream:
        stream.write(json.dumps(report, indent=2, allow_nan=False)+"\n")
    print(json.dumps({"passed": report["passed"], "directions": {k: v["passed"] for k, v in reports.items()},
                      "calls": len(calls)}, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("checkpoint", "observations", "template", "executable", "time-audit", "namelist", "workspace", "output"):
        p.add_argument("--"+name, type=Path, required=True)
    p.add_argument("--i", type=int, default=156)
    p.add_argument("--j", type=int, default=21)
    p.add_argument("--levels", type=int, default=39)
    p.add_argument("--upper-layers", type=int, default=27)
    p.add_argument("--nominal-time", default="2025-07-19_00:00:00")
    p.add_argument("--model-time", required=True)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--all-sky", action="store_true")
    mode.add_argument("--clear-sky", action="store_true")
    p.add_argument("--sigma", type=float, default=1.)
    p.add_argument("--huber-delta", type=float, default=1.)
    p.add_argument("--timeout", type=float, default=300.)
    verify(p.parse_args())
