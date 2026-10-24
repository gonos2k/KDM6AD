"""Batched native-profile construction and selected-row RTTOV evaluation.

The KDM batch stays full-width in ``NativeBatchMicrophysics``.  This module
only selects rows whose original number/moment receipt and post-KDM native
cloud profiles are admissible for the current RTTOV bridge.  It writes their
per-row native pressures, geometry, surface, and cloud profiles to one RTTOV
case.  Invalid rows keep their B-batch background, have explicit reasons, and
do not enter the observation support.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
import re
import shutil

import numpy as np
import torch

from oracle.kdm6.obs.native_batch_profile import native_to_rttov_cloud_profile_batch
from oracle.kdm6.obs.native_cloud_profile import (
    NativeCloudState,
    native_to_rttov_cloud_profile,
)
from oracle.kdm6.obs.native_profile_builder import (
    FrozenNativeProfileGeometry,
    NativeObservationConfig,
    NativeObservationState,
    UpperReferenceProfile,
)


CHANNELS = tuple(range(10, 17))
PROFILE_FIELDS = (
    "T",
    "Q",
    "P",
    "P_HALF",
    "HYDRO6",
    "HYDRO7",
    "HYDRO_DEFF6",
    "HYDRO_DEFF7",
)
_PROFILE_ATTRS = {
    "T": "t_lay",
    "Q": "q_lay",
    "P": "p_lay",
    "P_HALF": "p_half",
    "HYDRO6": "clw",
    "HYDRO7": "ciw",
    "HYDRO_DEFF6": "deff_liq",
    "HYDRO_DEFF7": "deff_ice",
}


def _torch_fixed(value, *, device):
    """Copy fixed numeric metadata into a non-gradient float64 tensor."""
    return torch.as_tensor(
        np.asarray(value, dtype=np.float64).copy(), dtype=torch.float64, device=device
    )


def _native_profile_config(config):
    try:
        raw = config["prep_configuration"]
        return NativeObservationConfig(
            **{name: float(raw[name]) for name in ("alpha", "t0", "kappa", "p0", "g")}
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "case config lacks valid native profile thermodynamic constants"
        ) from exc


def _native_upper(block, *, device):
    try:
        reference = block["reference"]
        return UpperReferenceProfile(
            p_lay_hpa=_torch_fixed(reference["p_lay_hpa"], device=device),
            p_half_hpa=_torch_fixed(reference["p_half_hpa"], device=device),
            t_k=_torch_fixed(reference["t_k"], device=device),
            q_ppmv=_torch_fixed(reference["q_ppmv"], device=device),
            fixed_upper_count=int(reference["fixed_upper_count"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "block lacks the pinned fixed upper RTTOV reference profile"
        ) from exc


def _block_arrays(block):
    """Validate the observation/eligibility arrays without altering their rows."""
    flat = np.asarray(block["flat_indices"])
    if flat.ndim != 1 or flat.dtype.kind not in "iu" or not flat.size:
        raise ValueError("block.flat_indices must be a nonempty integer vector")
    batch = int(flat.size)
    obs = np.asarray(block["obs_bt"], dtype=np.float64)
    dqf = np.asarray(block["obs_dqf"])
    qc_raw = np.asarray(block["obs_qc_raw"])
    qc_codes = np.asarray(block.get("obs_qc_codes"))
    if obs.shape != (batch, len(CHANNELS)):
        raise ValueError(f"block.obs_bt must have shape ({batch},{len(CHANNELS)})")
    if dqf.shape != obs.shape or dqf.dtype.kind not in "iu":
        raise ValueError("block.obs_dqf must be an integer matrix matching obs_bt")
    if qc_raw.shape != obs.shape or qc_raw.dtype.kind not in "iuf":
        raise ValueError("block.obs_qc_raw must be a numeric matrix matching obs_bt")
    if qc_codes.shape != obs.shape or qc_codes.dtype.kind not in "iu":
        raise ValueError("block.obs_qc_codes must be an integer matrix matching obs_bt")
    if not np.isfinite(qc_raw).all() or not np.array_equal(
        qc_raw, qc_codes.astype(np.float64)
    ):
        raise ValueError(
            "block.obs_qc_codes must be the exact integer decoding of raw QC"
        )
    admission = block.get("initial_admission")
    if not isinstance(admission, dict):
        raise ValueError("block.initial_admission must be a mapping")
    cost_eligible = np.asarray(admission.get("cost_eligible"))
    negative_nc = np.asarray(admission.get("negative_nc"))
    negative_ni = np.asarray(admission.get("negative_ni"))
    for name, value in (
        ("cost_eligible", cost_eligible),
        ("negative_nc", negative_nc),
        ("negative_ni", negative_ni),
    ):
        if value.shape != (batch,) or value.dtype != np.bool_:
            raise ValueError(f"block.initial_admission.{name} must be bool[{batch}]")
    reasons = admission.get("reasons")
    if reasons is not None and len(reasons) != batch:
        raise ValueError(f"block.initial_admission.reasons must have {batch} entries")
    source_good = (dqf == 0) & (qc_codes == 0) & np.isfinite(obs)
    return (
        batch,
        obs,
        dqf,
        qc_raw,
        qc_codes,
        source_good,
        cost_eligible,
        negative_nc,
        negative_ni,
        reasons,
    )


def _row_geometry(block, row):
    fields = block.get("rttov_geometry")
    required = (
        "zenangle",
        "azangle",
        "sunzenangle",
        "sunazangle",
        "latitude",
        "longitude",
        "elevation",
    )
    if not isinstance(fields, dict) or set(fields) != set(required):
        raise ValueError(f"block.rttov_geometry must contain exactly {list(required)}")
    return {name: float(np.asarray(fields[name])[row]) for name in required}


def _optical_cloud_state(cloud_raw, rho_d):
    """Convert raw native NC/NI with the same live dry density used by optics.

    The KDM rest/input coordinates remain unchanged. Only the observation
    bridge's NC/NI arguments use ``N_raw / rho_d``; this helper is shared by
    preflight, primal profile building, and JVP so none uses a frozen density.
    """
    return NativeCloudState(
        cloud_raw.qc,
        cloud_raw.qi,
        cloud_raw.qs,
        cloud_raw.nc / rho_d,
        cloud_raw.ni / rho_d,
    )


def _profile_inputs(output, rows, block, *, config):
    """Select physics outputs and fixed geometry for validated rows."""
    device = output.native_profile.thm_pert.device
    ix = torch.as_tensor(rows, dtype=torch.long, device=device)
    native = NativeObservationState(
        output.native_profile.thm_pert.index_select(0, ix),
        output.native_profile.qv.index_select(0, ix),
        output.native_profile.p_center_Pa.index_select(0, ix),
        output.native_profile.phi_interfaces.index_select(0, ix),
    )
    cloud_raw = NativeCloudState(
        output.cloud_state.qc.index_select(0, ix),
        output.cloud_state.qi.index_select(0, ix),
        output.cloud_state.qs.index_select(0, ix),
        output.cloud_state.nc.index_select(0, ix),
        output.cloud_state.ni.index_select(0, ix),
    )
    rho_d = output.rho_d.index_select(0, ix)
    cloud = _optical_cloud_state(cloud_raw, rho_d)
    xland = _torch_fixed(block["xland"], device=device).index_select(0, ix)
    geometry = FrozenNativeProfileGeometry(
        fnm=_torch_fixed(block["fnm"], device=device),
        fnp=_torch_fixed(block["fnp"], device=device),
    )
    reference = _native_upper(block, device=device)
    ncmin_land = float(config["experiment"]["ncmin_land"])
    ncmin_sea = float(config["experiment"]["ncmin_sea"])
    return native, cloud, rho_d, xland, geometry, reference, ncmin_land, ncmin_sea


def _validate_selected_inputs(block, output, config, candidates):
    """Validate candidate rows separately so one bad moment never drops a whole block."""
    from oracle.kdm6.obs.rttov_case_writer import _validate_geometry, _validate_surface

    b = int(len(block["flat_indices"]))
    if (
        output.native_profile.thm_pert.shape[0] != b
        or output.cloud_state.qc.shape[0] != b
    ):
        raise ValueError("physics output batch size differs from the source block")
    for name in ("thm_pert", "qv", "p_center_Pa"):
        value = getattr(output.native_profile, name)
        if value.ndim != 2 or value.shape[0] != b:
            raise ValueError(f"output.native_profile.{name} must have B rows")
    surfaces = block.get("surface_profiles")
    if not isinstance(surfaces, (tuple, list)) or len(surfaces) != b:
        raise ValueError(f"block.surface_profiles must have {b} per-row entries")
    row_errors = {}
    native_all = output.native_profile
    cloud_all = output.cloud_state
    device = native_all.thm_pert.device
    shared_geometry = FrozenNativeProfileGeometry(
        fnm=_torch_fixed(block["fnm"], device=device),
        fnp=_torch_fixed(block["fnp"], device=device),
    )
    native_config = _native_profile_config(config)
    upper = _native_upper(block, device=device)
    xland = np.asarray(block["xland"], dtype=np.float64)
    if xland.shape != (b,):
        raise ValueError(f"block.xland must have shape ({b},)")
    for row in candidates:
        try:
            _validate_geometry([_row_geometry(block, row)], 1)
            _validate_surface([surfaces[row]], 1, solar_enabled=False)
            native = NativeObservationState(
                native_all.thm_pert[row],
                native_all.qv[row],
                native_all.p_center_Pa[row],
                native_all.phi_interfaces[row],
            )
            cloud_raw = NativeCloudState(
                cloud_all.qc[row],
                cloud_all.qi[row],
                cloud_all.qs[row],
                cloud_all.nc[row],
                cloud_all.ni[row],
            )
            rho_d = output.rho_d[row]
            cloud = _optical_cloud_state(cloud_raw, rho_d)
            native_to_rttov_cloud_profile(
                native,
                cloud,
                shared_geometry,
                native_config,
                upper,
                rho_d=rho_d,
                xland=float(xland[row]),
                ncmin_land=float(config["experiment"]["ncmin_land"]),
                ncmin_sea=float(config["experiment"]["ncmin_sea"]),
            )
        except (TypeError, ValueError) as exc:
            row_errors[int(row)] = f"post_microphysics_profile_invalid:{exc}"
    return row_errors


def _profile_arrays(profiles):
    """Copy the differentiable profile fields for a durable receipt."""
    fields = {
        "T": profiles.t_lay,
        "Q": profiles.q_lay,
        "P": profiles.p_lay,
        "P_HALF": profiles.p_half,
        "HYDRO6": profiles.clw,
        "HYDRO7": profiles.ciw,
        "HYDRO_DEFF6": profiles.deff_liq,
        "HYDRO_DEFF7": profiles.deff_ice,
        "CFRAC": profiles.cfrac,
    }
    return {
        name: np.array(value.detach().cpu().numpy(), dtype=np.float64, copy=True)
        for name, value in fields.items()
    }


def _empty_profile_arrays(batch, nlevels, nupper):
    layers = nlevels + nupper
    fields = {
        "T": layers,
        "Q": layers,
        "P": layers,
        "P_HALF": layers + 1,
        "HYDRO6": layers,
        "HYDRO7": layers,
        "HYDRO_DEFF6": layers,
        "HYDRO_DEFF7": layers,
        "CFRAC": layers,
    }
    return {
        name: np.empty((0, size), dtype=np.float64) for name, size in fields.items()
    }


def _rttov_input_config(config, block, rows):
    from oracle.kdm6.obs.rttov_case_writer import _resolve_coef_path
    from oracle.kdm6.obs.rttov_input_builder import RttovInputConfig

    paths = config.get("paths")
    if not isinstance(paths, dict) or "template" not in paths:
        raise ValueError("case config requires the resolved RTTOV template path")
    template = Path(paths["template"])
    digest = hashlib.sha256()
    with _resolve_coef_path(template).open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    coef_id = digest.hexdigest()
    geometry = [_row_geometry(block, int(row)) for row in rows]
    surfaces = [block["surface_profiles"][int(row)] for row in rows]
    return RttovInputConfig(
        coef_id=coef_id,
        channels=CHANNELS,
        pressure_gradients=True,
        geometry=geometry,
        surface=surfaces,
    )


def _integer_quality(value, shape):
    array = np.asarray(value)
    if (
        array.shape != shape
        or array.dtype.kind not in "iuf"
        or not np.isfinite(array).all()
    ):
        raise ValueError(
            f"RTTOV model quality must be finite numeric with shape {shape}"
        )
    if not np.equal(array, np.rint(array)).all():
        raise ValueError("RTTOV model quality flags must be integer-valued")
    return np.asarray(np.rint(array), dtype=np.int32)


def _namelist_flag(path, name, value):
    """Set a simple boolean in the copied case namelist, rejecting ambiguous edits."""
    text = Path(path).read_text()
    flag = ".TRUE." if value else ".FALSE."
    pattern = re.compile(
        rf"(?mi)^([ \t]*defn%{re.escape(name)}[ \t]*=[ \t]*)(\.TRUE\.|\.FALSE\.)([ \t]*,?[ \t]*(?:!.*)?)$"
    )
    matches = list(pattern.finditer(text))
    if len(matches) > 1:
        raise ValueError(f"duplicate defn%{name} assignments in copied case")
    if matches:
        match = matches[0]
        text = text[: match.start()] + match.group(1) + flag + text[match.end(2) :]
    else:
        group = re.fullmatch(
            r"\s*&rttov_test_nml\s*\n(?P<body>.*?)^\s*/\s*", text, re.M | re.I | re.S
        )
        if group is None:
            raise ValueError("copied direct case requires one complete rttov_test_nml")
        end = group.end("body")
        text = text[:end] + f"  defn%{name} = {flag}\n" + text[end:]
    Path(path).write_text(text)


def _read_namelist_flag(path, name):
    assignments = re.findall(
        rf"(?mi)^[ \t]*defn%{re.escape(name)}[ \t]*=[ \t]*([^!\n]+)",
        Path(path).read_text(),
    )
    if not assignments:
        return None
    if len(assignments) != 1:
        raise ValueError(f"expected at most one defn%{name} in copied RTTOV namelist")
    value = assignments[0].strip().rstrip(",").strip().upper()
    if value not in (".TRUE.", ".FALSE."):
        raise ValueError(f"unsupported defn%{name} value in copied RTTOV namelist")
    return value == ".TRUE."


def _case_direct_radiance(case_out, nprofiles, *, channels, timeout, kma_bt):
    from oracle.kdm6.obs.rttov_runner import run_rttov_direct

    result = run_rttov_direct(
        case_out, nchannels=len(channels), expected_nprofiles=nprofiles, timeout=timeout
    )
    bt = np.asarray(result["bt"], dtype=np.float64)
    if not kma_bt:
        return bt, result["rad_quality"], {"bt_coordinate": "rttov_native"}
    from oracle.kdm6.obs._rttov_reference.rttov_ascii import parse_rttov_ascii_blocks
    from oracle.kdm6.obs.ami_bt_coordinate import (
        read_ami_filters,
        read_kma_calibration,
        transform_rttov_to_kma,
    )
    from oracle.kdm6.obs.rttov_case_writer import _resolve_coef_path

    case_root = Path(case_out).parent
    blocks = parse_rttov_ascii_blocks(Path(case_out) / "direct" / "radiance.txt")
    if "RADIANCE%TOTAL" not in blocks:
        raise ValueError("direct RTTOV output lacks RADIANCE%TOTAL needed for KMA BT")
    total = np.asarray(blocks["RADIANCE%TOTAL"], dtype=np.float64)
    expected_shape = (nprofiles, len(channels))
    if total.size != nprofiles * len(channels):
        raise ValueError(
            "direct TOTAL radiance count differs from profile/channel count"
        )
    bt_kma, _, _ = transform_rttov_to_kma(
        bt,
        total.reshape(expected_shape),
        {},
        channels,
        read_ami_filters(_resolve_coef_path(case_root)),
        read_kma_calibration(),
    )
    return bt_kma, result["rad_quality"], {"bt_coordinate": "kma_v3_0"}


def _selected_profile_context(block, output, rows, config):
    native, cloud, rho_d, xland, geometry, upper, ncmin_land, ncmin_sea = (
        _profile_inputs(output, rows, block, config=config)
    )
    return native_to_rttov_cloud_profile_batch(
        native,
        cloud,
        geometry,
        _native_profile_config(config),
        upper,
        rho_d=rho_d,
        xland=xland,
        ncmin_land=ncmin_land,
        ncmin_sea=ncmin_sea,
    )


def evaluate_observation_batch(block, output, config, workspace, *, with_k=True):
    """Build row-valid native profiles and run one batched RTTOV observation call.

    The physics ``output`` is already produced from the full, unfiltered KDM
    block.  Initial number failures and post-microphysics profile failures only
    remove observation rows; the row's original KDM background is never mutated
    or removed. ``with_k=True`` is the baseline operator path. ``with_k=False``
    performs a direct-value RTTOV call with the K output disabled for FD trials.
    The caller owns and may clean ``workspace`` after it records the completed
    block; failures leave the case/logs in place for inspection.
    """
    if type(with_k) is not bool:
        raise TypeError("with_k must be bool")
    (
        batch,
        obs,
        dqf,
        qc_raw,
        qc_codes,
        source_good,
        cost_eligible,
        negative_nc,
        negative_ni,
        initial_reasons,
    ) = _block_arrays(block)
    if not hasattr(output, "native_profile") or not hasattr(output, "cloud_state"):
        raise TypeError(
            "output must be NativeBatchOutput from the full-B physics adapter"
        )
    rows = np.flatnonzero(cost_eligible).astype(np.int64)
    invalid_reasons = _validate_selected_inputs(block, output, config, rows)
    profile_valid = cost_eligible.copy()
    profile_valid[list(invalid_reasons)] = False

    reasons = [[] for _ in range(batch)]
    for row in range(batch):
        if negative_nc[row]:
            reasons[row].append("negative_initial_nc")
        if negative_ni[row]:
            reasons[row].append("negative_initial_ni")
        if initial_reasons is not None and initial_reasons[row]:
            text = str(initial_reasons[row]).strip()
            if text and text not in reasons[row]:
                reasons[row].append(f"initial_admission:{text}")
        bad_dqf = np.flatnonzero(dqf[row] != 0).tolist()
        bad_qc = np.flatnonzero(qc_codes[row] != 0).tolist()
        bad_obs = np.flatnonzero(~np.isfinite(obs[row])).tolist()
        if bad_dqf:
            reasons[row].append(f"source_dqf_nonzero_channels0={bad_dqf}")
        if bad_qc:
            reasons[row].append(f"source_qc_nonzero_channels0={bad_qc}")
        if bad_obs:
            reasons[row].append(f"source_bt_nonfinite_channels0={bad_obs}")
        if row in invalid_reasons:
            reasons[row].append(invalid_reasons[row])

    rows = np.flatnonzero(profile_valid).astype(np.int64)
    quality = np.full((batch, len(CHANNELS)), -1, dtype=np.int32)
    output_device = output.native_profile.thm_pert.device
    bt_full = torch.full(
        (batch, len(CHANNELS)), float("nan"), dtype=torch.float64, device=output_device
    )
    k_cache = {}
    profile_arrays = _empty_profile_arrays(
        batch, int(block.get("L", 39)), int(block["reference"]["fixed_upper_count"])
    )
    receipt = {
        "mode": "K" if with_k else "direct",
        "baseline_operator": bool(with_k),
        "K_calls": 0,
        "direct_calls": 0,
        "K_recovered": 0,
        "nprofiles": int(rows.size),
        "channels": list(CHANNELS),
        "bt_coordinate": "kma_v3_0",
        "pressure_gradients": True,
        "source_flat_indices": np.asarray(block["flat_indices"], dtype=np.int64)[
            rows
        ].tolist(),
    }
    if rows.size:
        from oracle.kdm6.obs.rttov_case_writer import make_live_run_k, write_rttov_case
        from oracle.kdm6.obs.rttov_obs_operator import RttovObsOp

        profiles = _selected_profile_context(block, output, rows, config)
        profile_arrays.update(_profile_arrays(profiles))
        input_config = _rttov_input_config(config, block, rows)
        paths = config["paths"]
        template = Path(paths["template"])
        case_dir = Path(workspace) / ("case_k" if with_k else "case_direct")
        timeout = float(config.get("rttov_timeout_seconds", 180.0))
        if not math.isfinite(timeout) or timeout <= 0.0:
            raise ValueError("rttov_timeout_seconds must be positive and finite")
        fixture_namelist = template / "out" / "rttov_test.txt"
        inherited_do_k = _read_namelist_flag(fixture_namelist, "do_k")
        inherited_do_direct = _read_namelist_flag(fixture_namelist, "do_direct")
        if with_k:
            workspace_path = Path(workspace)
            workspace_path.mkdir(parents=True, exist_ok=True)
            k_template = workspace_path / "template_k"
            if k_template.exists() or k_template.is_symlink():
                raise FileExistsError(
                    f"K-run template destination already exists: {k_template}"
                )
            shutil.copytree(template, k_template)
            k_template_namelist = k_template / "out" / "rttov_test.txt"
            _namelist_flag(k_template_namelist, "do_direct", False)
            k_template_do_k = _read_namelist_flag(k_template_namelist, "do_k")
            k_template_do_direct = _read_namelist_flag(k_template_namelist, "do_direct")
            if k_template_do_k != inherited_do_k or k_template_do_direct is not False:
                raise ValueError(
                    "copied K-run template must preserve do_k and disable do_direct"
                )
            run_k = make_live_run_k(
                case_dir, fixture_case_dir=k_template, timeout=timeout, ami_kma_bt=True
            )
            call_receipt = {
                "K_calls": 0,
                "direct_calls": 0,
                "K_recovered": 0,
                "config_hashes": [],
            }

            def counted_run_k(rttov_input):
                from harness.native_satellite_replay import recover_k

                recovered = recover_k(
                    rttov_input,
                    block,
                    rows,
                    profile_arrays,
                    profile_valid,
                    config,
                    case_dir,
                    k_template,
                )
                if recovered is None:
                    value, k, rad_quality = run_k(rttov_input)
                    call_receipt["K_calls"] += 1
                else:
                    value, k, rad_quality, recovery_receipt = recovered
                    call_receipt["K_recovered"] += 1
                    call_receipt["recovery"] = recovery_receipt
                call_receipt["config_hashes"].append(rttov_input.config_hash)
                call_receipt["KMA_profile_counts"] = [int(rttov_input.nprofiles)]
                k_cache.clear()
                k_cache.update(
                    {
                        name: np.array(value, dtype=np.float64, copy=True)
                        for name, value in k.items()
                    }
                )
                return value, k, rad_quality

            selected_bt, selected_quality = RttovObsOp.apply(
                counted_run_k,
                input_config,
                profiles.t_lay,
                profiles.q_lay,
                profiles.p_lay,
                profiles.p_half,
                profiles.clw,
                profiles.ciw,
                profiles.deff_liq,
                profiles.deff_ice,
                profiles.cfrac,
            )
            bt_values = np.array(
                selected_bt.detach().cpu().numpy(), dtype=np.float64, copy=True
            )
            quality_values = _integer_quality(
                selected_quality.detach().cpu().numpy(), (len(rows), len(CHANNELS))
            )
            receipt.update(call_receipt)
            receipt["config_hash"] = call_receipt["config_hashes"][-1]
            receipt["driver_flags"] = {
                "template_do_k": inherited_do_k,
                "template_do_direct": inherited_do_direct,
                "K_template_do_k": k_template_do_k,
                "K_template_do_direct": k_template_do_direct,
            }
        else:
            from oracle.kdm6.obs.rttov_input_builder import pack_rttov_input

            rttov_input = pack_rttov_input(profiles, input_config)
            case_out = write_rttov_case(
                rttov_input, case_dir, fixture_case_dir=template, overwrite=True
            )
            nml = Path(case_out) / "rttov_test.txt"
            _namelist_flag(nml, "do_k", False)
            _namelist_flag(nml, "do_direct", True)
            bt_values, model_quality, direct_receipt = _case_direct_radiance(
                case_out, len(rows), channels=CHANNELS, timeout=timeout, kma_bt=True
            )
            quality_values = _integer_quality(model_quality, (len(rows), len(CHANNELS)))
            receipt.update(
                {
                    "K_calls": 0,
                    "direct_calls": 1,
                    "config_hash": rttov_input.config_hash,
                    "driver_flags": {
                        "template_do_k": inherited_do_k,
                        "template_do_direct": inherited_do_direct,
                        "case_do_k": False,
                        "case_do_direct": True,
                    },
                    **direct_receipt,
                }
            )
            # Direct radiance and quality are emitted by the runner; use its exact
            # returned BT unless a KMA-coordinate replay transformed the TOTAL block.
            if not isinstance(bt_values, np.ndarray):
                bt_values = np.asarray(bt_values, dtype=np.float64)
            bt_values = np.asarray(bt_values, dtype=np.float64).reshape(
                len(rows), len(CHANNELS)
            )
            selected_bt = torch.as_tensor(
                bt_values, dtype=torch.float64, device=output_device
            )

        if bt_values.shape != (len(rows), len(CHANNELS)):
            raise ValueError(
                "RTTOV BT output shape differs from selected profiles/channels"
            )
        if not np.isfinite(bt_values).all():
            raise ValueError("RTTOV BT output contains nonfinite values")
        bt_full = torch.full(
            (batch, len(CHANNELS)),
            float("nan"),
            dtype=selected_bt.dtype,
            device=selected_bt.device,
        )
        index = torch.as_tensor(rows, dtype=torch.long, device=selected_bt.device)
        bt_full = bt_full.index_copy(0, index, selected_bt)
        quality[rows] = quality_values
        if "rttov_geometry" in block and "surface_profiles" in block:
            receipt["per_profile_geometry_surface"] = True
        receipt["case_dir"] = str(case_dir)

    for row in rows:
        bad_model = np.flatnonzero(quality[row] != 0).tolist()
        if bad_model:
            reasons[row].append(f"rttov_quality_nonzero_channels0={bad_model}")
    baseline_valid = profile_valid[:, None] & source_good & (quality == 0)
    for row in range(batch):
        if profile_valid[row] and not baseline_valid[row].any():
            reasons[row].append(
                "no_channel_passed_strict_zero_source_and_model_quality"
            )
        if not reasons[row]:
            reasons[row].append("profile_admitted")
    reason_array = np.asarray([";".join(items) for items in reasons], dtype=np.str_)
    return {
        "bt": bt_full,
        "quality": quality,
        "profile_valid": profile_valid,
        "baseline_valid_mask": baseline_valid,
        "source_valid_mask": source_good,
        "reasons": reason_array,
        "rows": rows.astype(np.int32),
        "profile_arrays": profile_arrays,
        "k": k_cache,
        "receipt": receipt,
    }


def profile_jvp(block, primal_output, tangent_output, config, rows):
    """Map the explicit full-B microphysics JVP through native profile/cloud prep.

    This is a pure-Torch profile JVP on the same selected rows used by the RTTOV
    K run. Dry NC/NI conversion in the native cloud builder uses the identical
    live ``rho_d`` for the primal and tangent maps; the kernel's ``rest`` rows are
    supplied to physics unchanged by its caller.
    """
    rows = np.asarray(rows)
    if rows.ndim != 1 or rows.dtype.kind not in "iu":
        raise ValueError("rows must be an integer vector of selected native columns")
    device = primal_output.native_profile.thm_pert.device
    if rows.size == 0:
        nlevels = int(block.get("L", 39))
        nupper = int(block["reference"]["fixed_upper_count"])
        nlay = nlevels + nupper
        return {
            name: np.empty(
                (0, nlay if name != "P_HALF" else nlay + 1), dtype=np.float64
            )
            for name in PROFILE_FIELDS
        }
    index = torch.as_tensor(rows, dtype=torch.long, device=device)
    p = primal_output
    d = tangent_output
    raw_cloud = (
        p.cloud_state.nc.index_select(0, index),
        p.cloud_state.ni.index_select(0, index),
    )
    rho_primal = p.rho_d.index_select(0, index)
    primals = (
        p.native_profile.thm_pert.index_select(0, index),
        p.native_profile.qv.index_select(0, index),
        p.native_profile.p_center_Pa.index_select(0, index),
        p.native_profile.phi_interfaces.index_select(0, index),
        p.cloud_state.qc.index_select(0, index),
        p.cloud_state.qi.index_select(0, index),
        p.cloud_state.qs.index_select(0, index),
        raw_cloud[0],
        raw_cloud[1],
        rho_primal,
    )
    tangents = (
        d.native_profile.thm_pert.index_select(0, index),
        d.native_profile.qv.index_select(0, index),
        d.native_profile.p_center_Pa.index_select(0, index),
        d.native_profile.phi_interfaces.index_select(0, index),
        d.cloud_state.qc.index_select(0, index),
        d.cloud_state.qi.index_select(0, index),
        d.cloud_state.qs.index_select(0, index),
        d.cloud_state.nc.index_select(0, index),
        d.cloud_state.ni.index_select(0, index),
        d.rho_d.index_select(0, index),
    )
    xland = _torch_fixed(block["xland"], device=device).index_select(0, index)
    geometry = FrozenNativeProfileGeometry(
        fnm=_torch_fixed(block["fnm"], device=device),
        fnp=_torch_fixed(block["fnp"], device=device),
    )
    upper = _native_upper(block, device=device)
    profile_config = _native_profile_config(config)
    ncmin_land = float(config["experiment"]["ncmin_land"])
    ncmin_sea = float(config["experiment"]["ncmin_sea"])

    def build(thm, qv, p_center, phi, qc, qi, qs, nc, ni, rho_d):
        native = NativeObservationState(thm, qv, p_center, phi)
        cloud = _optical_cloud_state(NativeCloudState(qc, qi, qs, nc, ni), rho_d)
        result = native_to_rttov_cloud_profile_batch(
            native,
            cloud,
            geometry,
            profile_config,
            upper,
            rho_d=rho_d,
            xland=xland,
            ncmin_land=ncmin_land,
            ncmin_sea=ncmin_sea,
        )
        return tuple(getattr(result, _PROFILE_ATTRS[name]) for name in PROFILE_FIELDS)

    _value, tangent = torch.autograd.functional.jvp(
        build, primals, tangents, create_graph=False, strict=False
    )
    return {
        name: np.array(value.detach().cpu().numpy(), dtype=np.float64, copy=True)
        for name, value in zip(PROFILE_FIELDS, tangent)
    }
