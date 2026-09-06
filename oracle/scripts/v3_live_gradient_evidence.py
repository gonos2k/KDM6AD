"""V3 GK2A--KDM6--RTTOV first derivative evidence.

This is an evidence runner, rather than a pytest fixture.  It pins one real
GK2A KO slot to one real, geolocated KDM ``wrfinput_d01`` frame, records the
asset/source hashes and the complete observation mask/loss contract, and can
run a small set of central finite differences through the same profile writer
and RTTOV ``runK`` boundary used by the observation operator.

The default command is inventory-only.  ``--live`` is required before invoking
RTTOV.  Fixture pressure/T/Q files remain explicitly ``wiring_only``: they
define the RTTOV test case's grid/top reference and do not establish real
geometry or collocation validity.

The script writes one JSON document and uses a distinct temporary case root for
every baseline and FD call.  It never rewrites a stored ancestor run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import torch


REPO = Path(__file__).resolve().parents[2]
DEFAULT_KDM = Path(
    "/Users/yhlee/KDM6AD+/KIM-meso_v1.0/test/"
    "ss_real_case_20260619_063620/SS/wrfinput_d01"
)
DEFAULT_GK2A = Path("/Users/yhlee/KDM6AD-k/GK2A")
DEFAULT_CAL = REPO / "oracle/kdm6/obs/data/gk2a_ami_cal_202507190000.json"
DEFAULT_STAMP = "202507190000"
DEFAULT_EPS = (1.0, 0.3, 0.1, 0.03)
FD_REL_TOL = 5.0e-2
ALL_CHANNELS = tuple(range(1, 17))
def sha256_file(path: Path, *, chunk: int = 1024 * 1024) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while data := stream.read(chunk):
            digest.update(data)
    return digest.hexdigest()


def source_record(path: Path, *, role: str, evidence_level: str) -> dict[str, Any]:
    path = Path(path)
    return {
        "role": role,
        "evidence_level": evidence_level,
        "path": str(path),
        "exists": path.is_file(),
        "size_bytes": path.stat().st_size if path.is_file() else None,
        "sha256": sha256_file(path),
    }


def build_provenance(cal_path: Path, *, all_sky=False) -> dict[str, Any]:
    """Hash code and the fixture/runtime inputs that define the run boundary."""
    code = {REPO / "oracle/scripts/v3_live_gradient_evidence.py"}
    code.update((REPO / "oracle/kdm6").rglob("*.py"))
    records = [source_record(p, role="code", evidence_level="implementation")
               for p in sorted(code)]
    try:
        from kdm6.obs.rttov_case_writer import default_fixture_case_dir, cloud_fixture_case_dir
        fixture = cloud_fixture_case_dir() if all_sky else default_fixture_case_dir()
    except Exception:
        fixture = None
    if fixture is not None:
        # Keep a complete fixture manifest: geometry, surface, datetime, gases,
        # hydrotable switches and profile templates all affect the executable
        # boundary.  Every fixture item remains wiring_only because it is not
        # the actual GK2A pixel geometry.
        for path in sorted(p for p in fixture.rglob("*") if p.is_file()):
            records.append(source_record(
                path, role="RTTOV fixture input", evidence_level="wiring_only"))
        # Resolve the actual files named by the trusted fixture, rather than
        # assuming the selected runtime directory contains the loaded assets.
        config = (fixture / "out/rttov_test.txt").read_text()
        prefix = re.search(r"defn%coef_prefix\s*=\s*'([^']+)'", config)
        if prefix:
            for key, value in re.findall(r"defn%(f_coef|f_hydrotable)\s*=\s*'([^']+)'",
                                         (fixture / "in/coef.txt").read_text()):
                path = (fixture / "out" / prefix.group(1) / value).resolve()
                records.append(source_record(path, role=key, evidence_level="runtime"))
        exe = re.search(r"(/\S+\.exe)", (fixture / "out/run.sh").read_text())
        if exe:
            records.append(source_record(Path(exe.group(1)).resolve(),
                                         role="fixture run.sh executable", evidence_level="runtime"))
    runtime_candidates = []
    try:
        from kdm6.obs.rttov_runner import ad_rttov_home, rttov_runtime_root
        runtime = rttov_runtime_root()
        if runtime is not None:
            runtime_candidates.append(runtime / "bin/rttov_test.exe")
        runtime_candidates.append(ad_rttov_home() / "external/rttov14/src/bin/rttov_test.exe")
    except Exception:
        pass
    for exe in runtime_candidates:
        if exe.is_file():
            records.append(source_record(exe, role="RTTOV executable", evidence_level="runtime"))
            break
    return {
        "code_and_runtime": records,
        "calibration_table": source_record(
            cal_path, role="GK2A calibration table", evidence_level="actual"),
        "fixture_note": "RTTOV fixture inputs are wiring_only and do not validate real geometry/collocation.",
    }


def _finite_stats(a: torch.Tensor | np.ndarray) -> dict[str, Any]:
    if isinstance(a, torch.Tensor):
        a = a.detach().cpu()
    x = np.asarray(a, dtype=np.float64)
    finite = np.isfinite(x)
    vals = x[finite]
    return {
        "shape": list(x.shape),
        "finite_count": int(finite.sum()),
        "total_count": int(x.size),
        "min": float(vals.min()) if vals.size else None,
        "max": float(vals.max()) if vals.size else None,
    }


def _radiance_text_resolution(path: Path) -> dict[str, Any]:
    """Describe the emitted BT ASCII quantum before its temporary case is removed."""
    text = path.read_text()
    match = re.search(r"RADIANCE%BT\s*=\s*\((.*?)\)", text, re.S)
    if match is None:
        return {"sha256": sha256_file(path), "size_bytes": path.stat().st_size,
                "bt_block": "missing"}
    tokens = re.findall(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?", match.group(1))
    quanta = []
    for token in tokens:
        mantissa, _, exponent = token.lower().partition("e")
        digits = len(mantissa.split(".", 1)[1]) if "." in mantissa else 0
        quanta.append(10.0 ** ((int(exponent) if exponent else 0) - digits))
    quantum = max(quanta) if quanta else None
    return {
        "sha256": sha256_file(path), "size_bytes": path.stat().st_size,
        "bt_block_values": len(tokens), "bt_decimal_quantum_upper_bound": quantum,
        "bt_block": "RADIANCE%BT",
    }


def _require_actual_assets(kdm_path: Path, gk2a_root: Path, cal_path: Path, stamp: str):
    from kdm6.obs.gk2a_l1b import CLEAN_IR_CHANNELS, slot_files

    files = [Path(p) for p in slot_files(gk2a_root, stamp, channels=CLEAN_IR_CHANNELS)]
    missing = [str(p) for p in [kdm_path, cal_path, *files] if not p.is_file()]
    return files, missing


def build_inventory(kdm_path: Path, gk2a_root: Path, cal_path: Path, stamp: str,
                    *, stride: int, max_dist_km: float) -> dict[str, Any]:
    """Read and validate the real slot/frame without invoking RTTOV."""
    from kdm6.io.frame_reader import read_wrfout_frame
    from kdm6.obs.gk2a_l1b import AMI_CHANNELS, CLEAN_IR_CHANNELS, load_cal_table, read_ko_slot
    from kdm6.obs.obs_ingest import payload_to_column_obs

    files, missing = _require_actual_assets(kdm_path, gk2a_root, cal_path, stamp)
    result: dict[str, Any] = {
        "slot": stamp,
        "stride": stride,
        "max_dist_km": max_dist_km,
        "requested_channels": list(CLEAN_IR_CHANNELS),
        "asset_missing": missing,
        "assets": [
            source_record(kdm_path, role="actual KDM frame", evidence_level="actual"),
            source_record(cal_path, role="GK2A FD calibration table", evidence_level="actual"),
            *[source_record(p, role="GK2A KO channel", evidence_level="actual") for p in files],
        ],
    }
    if missing:
        result["status"] = "missing_actual_asset"
        return result

    cal = load_cal_table(cal_path)
    frame = read_wrfout_frame(str(kdm_path), 0, nccn_policy="init_profile")
    payload = read_ko_slot(files, cal, stride=stride)
    columns = payload_to_column_obs(
        payload, frame.meta["lat"], frame.meta["lon"], max_dist_km=max_dist_km)

    clean_indices = [AMI_CHANNELS.index(ch) for ch in CLEAN_IR_CHANNELS]
    assigned = columns.col_of_obs >= 0
    usable = (columns.obs_quality[:, clean_indices] == 0).all(dim=1)
    assigned_usable = assigned.new_zeros(columns.bt.shape[0], dtype=torch.bool)
    # ``col_of_obs`` is observation -> column.  An observation-level quality
    # check is recorded separately; this mask is for deterministic column picks.
    for obs_idx in torch.where(assigned)[0].tolist():
        col_idx = int(columns.col_of_obs[obs_idx])
        assigned_usable[col_idx] = bool((payload.obs_quality[obs_idx, clean_indices] == 0).all())
    chosen = torch.where(assigned_usable)[0]
    result.update({
        "status": "inventory_ok",
        "frame": {
            "valid_time_utc": frame.meta.get("valid_time_utc"),
            "shape": list(frame.state.th.shape),
            "nx": frame.meta["nx"], "ny": frame.meta["ny"],
            "kme": frame.meta["kme"],
            "nccn_fallback": bool(frame.meta["nccn_fallback"]),
            "lat": _finite_stats(frame.meta["lat"]),
            "lon": _finite_stats(frame.meta["lon"]),
            "state_fields": list(frame.state._fields),
            "state_dtype": str(frame.state.th.dtype),
            "forcing_fields": list(frame.forcing._fields),
        },
        "observation": {
            "valid_time_utc": payload.valid_time_utc,
            "n_obs": payload.n_obs,
            "n_channels": payload.nch,
            "payload_bt": _finite_stats(payload.bt),
            "payload_lat": _finite_stats(payload.lat),
            "payload_lon": _finite_stats(payload.lon),
            "quality_zero_by_channel": [
                int((payload.obs_quality[:, c] == 0).sum()) for c in range(payload.nch)
            ],
            "bias_source": "absent in GK2A payload; no bias correction applied",
            "bias_present": payload.bias is not None,
            "channel_gate_source": "absent in GK2A payload; no channel gate applied",
            "channel_gate_present": payload.channel_gate is not None,
            "mask_contract": "obs_quality == 0; combined mask waits for live rad_quality == 0",
        },
        "collocation": {
            "n_model_columns": int(frame.state.th.shape[0]),
            "n_assigned": columns.n_assigned,
            "n_dropped_far": columns.n_dropped_far,
            "n_dropped_collision": columns.n_dropped_collision,
            "assigned_usable_clean_ir": int(chosen.numel()),
            "selected_column_order": "ascending flattened WRF b=j*nx+i",
        },
        "selection": {
            "candidate_count": int(chosen.numel()),
            "candidate_columns_first": chosen[:16].tolist(),
            "candidate_columns_last": chosen[-16:].tolist(),
            "selection_rule": "assigned observation with all nine requested clean-IR quality flags == 0; live adds qc+qi+qs > 1e-6",
        },
    })
    # Distances are not exposed in ColumnObs; recompute only for selected owners
    # from the source observation coordinates for an audit-friendly summary.
    owner_dist = []
    for obs_idx in torch.where(columns.col_of_obs >= 0)[0].tolist():
        col_idx = int(columns.col_of_obs[obs_idx])
        dlat = frame.meta["lat"][col_idx] - payload.lat[obs_idx]
        dlon = frame.meta["lon"][col_idx] - payload.lon[obs_idx]
        # Haversine is the same implementation used by collocation.
        from kdm6.obs.obs_ingest import haversine_km
        owner_dist.append(float(haversine_km(payload.lat[obs_idx], payload.lon[obs_idx],
                                             frame.meta["lat"][col_idx], frame.meta["lon"][col_idx])))
    result["collocation"]["assigned_distance_km"] = _finite_stats(np.asarray(owner_dist))
    return result


def _state_subset(frame, columns: list[int]):
    from kdm6.state import Forcing, State
    ix = torch.as_tensor(columns, dtype=torch.long)
    return (State(**{name: getattr(frame.state, name)[ix] for name in frame.state._fields}),
            Forcing(**{name: getattr(frame.forcing, name)[ix] for name in frame.forcing._fields}),
            frame.xland[ix])


def _direction(shape: tuple[int, ...], *, seed: int, max_abs: float) -> torch.Tensor:
    gen = torch.Generator(device="cpu").manual_seed(seed)
    v = torch.randn(shape, generator=gen, dtype=torch.float64)
    return v / v.abs().amax().clamp_min(1.0) * max_abs


def _relative_positive_direction(reference: torch.Tensor, *, seed: int,
                                 fractional_max: float) -> torch.Tensor:
    """Generate a direction bounded by ``fractional_max * abs(reference)``.

    For positive state variables this keeps both central-FD endpoints in the
    same admissible domain for ``|epsilon| <= 1``.  It is an evidence helper;
    it does not alter the KDM update or its positivity subgradient.
    """
    if not (math.isfinite(fractional_max) and 0.0 <= fractional_max <= 1.0):
        raise ValueError("fractional_max must be finite and in [0, 1]")
    if not bool(torch.isfinite(reference).all()) or not bool((reference >= 0).all()):
        raise ValueError("relative-positive direction requires finite nonnegative reference")
    gen = torch.Generator(device=reference.device).manual_seed(seed)
    raw = torch.randn(tuple(reference.shape), generator=gen,
                      dtype=torch.float64, device=reference.device)
    scale = raw.abs().amax().clamp_min(1.0)
    return reference.detach().to(torch.float64) * raw / scale * fractional_max


def _profile_and_obs(state, forcing, cfg, *, run_k, xland=None, detach_state=True):
    from kdm6.da_driver import _blend_above_model_top, _flip
    from kdm6.obs.model_profile_builder import model_to_rttov_tensors
    from kdm6.obs.rttov_obs_operator import RttovObsOp
    from kdm6.state import State

    if detach_state:
        leaves = State(*(getattr(state, name).detach().clone().to(torch.float64)
                         for name in state._fields))
        leaves = leaves._replace(th=leaves.th.requires_grad_(True),
                                 qv=leaves.qv.requires_grad_(True))
    else:
        leaves = state
    ff = type(forcing)(rho=_flip(forcing.rho), pii=_flip(forcing.pii),
                       p=_flip(forcing.p) / 100.0, delz=_flip(forcing.delz))
    prof = model_to_rttov_tensors(
        State(*(_flip(getattr(leaves, n)) for n in leaves._fields)), ff, cfg.profile_cfg,
        xland=xland)
    t_lay, q_lay = prof.t_lay, prof.q_lay
    if cfg.t_ref is not None:
        if ff.p.ndim == 1:
            p_top = ff.p[0].reshape(1)
            t_lay = _blend_above_model_top(t_lay.unsqueeze(0), cfg.t_ref,
                                           prof.p_lay, p_top,
                                           octaves=cfg.t_blend_octaves).squeeze(0)
            q_lay = _blend_above_model_top(q_lay.unsqueeze(0), cfg.q_ref,
                                           prof.p_lay, p_top,
                                           octaves=cfg.q_blend_octaves).squeeze(0)
        else:
            p_top = ff.p[:, 0]
            t_lay = _blend_above_model_top(t_lay, cfg.t_ref, prof.p_lay, p_top,
                                           octaves=cfg.t_blend_octaves)
            q_lay = _blend_above_model_top(q_lay, cfg.q_ref, prof.p_lay, p_top,
                                           octaves=cfg.q_blend_octaves)
    if getattr(cfg.profile_cfg, "cloud", False):
        bt, rq = RttovObsOp.apply(
            run_k, cfg.input_cfg, t_lay, q_lay, prof.p_lay, prof.p_half,
            prof.clw, prof.ciw, prof.deff_liq, prof.deff_ice, prof.cfrac)
    else:
        bt, rq = RttovObsOp.apply(run_k, cfg.input_cfg, t_lay, q_lay,
                                  prof.p_lay, prof.p_half)
    return leaves, prof, t_lay, q_lay, bt, rq


def _select_columns(ranked, max_profiles, column=None):
    """Select only already collocated, usable, hydrometeor-bearing columns."""
    if max_profiles < 1:
        raise ValueError("max_profiles must be positive")
    owners = [col for col, _ in ranked]
    if column is not None:
        if max_profiles != 1:
            raise ValueError("an explicit column requires max_profiles=1")
        if column not in owners:
            raise ValueError("requested column is not an assigned usable hydrometeor column")
        return [column]
    if len(owners) < max_profiles:
        raise RuntimeError(f"only {len(owners)} assigned usable columns; need {max_profiles}")
    return owners[:max_profiles]


def _run_live(kdm_path: Path, gk2a_root: Path, cal_path: Path, stamp: str,
              *, stride: int, max_dist_km: float, max_profiles: int,
              eps: tuple[float, ...], out_path: Path,
              all_sky: bool = False, column: int | None = None) -> dict[str, Any]:
    """Run actual profile->K->BT->J and central FD for three state directions."""
    import numpy as np
    from kdm6.io.frame_reader import read_wrfout_frame
    from kdm6.obs.gk2a_l1b import (AMI_CHANNELS, CLEAN_IR_CHANNELS, load_cal_table,
                                   read_ko_slot, slot_files)
    from kdm6.obs.obs_ingest import payload_to_column_obs
    from kdm6.obs.model_profile_builder import RttovProfileConfig
    from kdm6.obs.rttov_case_writer import fixture_layer_pressure, make_live_run_k
    from kdm6.obs.rttov_fixture import fixture_p_half, fixture_tq
    from kdm6.obs.rttov_input_builder import RttovInputConfig
    from kdm6.obs.obs_loss import compute_obs_loss
    from kdm6.state import State
    from kdm6.runtime import kdm6_step
    from kdm6.da_driver import OsseObsConfig

    frame = read_wrfout_frame(str(kdm_path), 0, nccn_policy="init_profile")
    payload = read_ko_slot(
        [Path(p) for p in slot_files(gk2a_root, stamp, channels=CLEAN_IR_CHANNELS)],
        load_cal_table(cal_path), stride=stride)
    cols = payload_to_column_obs(payload, frame.meta["lat"], frame.meta["lon"],
                                 max_dist_km=max_dist_km)
    clean = [AMI_CHANNELS.index(ch) for ch in CLEAN_IR_CHANNELS]
    owners = [i for i in range(cols.bt.shape[0]
              ) if int((cols.obs_quality[i, clean] == 0).sum()) == len(clean)]
    # The cloud profile bridge is intentionally single-column (the production
    # all-sky batch path shards this operation).  Keep this evidence runner's
    # live case to one real column so it cannot accidentally use the clear-sky
    # batched shortcut or misassociate a cloud K row.
    if all_sky and max_profiles != 1:
        raise ValueError("live all-sky evidence requires --max-profiles 1 (single-column bridge)")
    # Keep the real-column selection deterministic while ensuring the KDM map
    # has an active hydrometeor source for the requested qc direction.  A zero
    # cloud column is a valid negative control, but cannot evidence a cloud
    # tangent through M.
    qtot = (frame.state.qc + frame.state.qi + frame.state.qs)[owners].sum(dim=1)
    ranked = sorted(((col, float(amount)) for col, amount in zip(owners, qtot.tolist())
                     if amount > 1.0e-6), key=lambda item: (-item[1], item[0]))
    owners = _select_columns(ranked, max_profiles, column)
    hydrometeor_total = (frame.state.qc + frame.state.qi + frame.state.qs)[owners].sum(dim=1)
    state, forcing, xland = _state_subset(frame, owners)
    y = cols.bt[owners]
    yq = cols.obs_quality[owners]
    tr, qr = fixture_tq()
    p_half = torch.as_tensor(np.asarray(fixture_p_half(), dtype=float), dtype=torch.float64)
    p_lay = torch.as_tensor(np.asarray(fixture_layer_pressure(), dtype=float), dtype=torch.float64)
    input_cfg = RttovInputConfig(coef_id="ami_501_test", channels=ALL_CHANNELS)
    # The frozen dry-air density is a background measure, in the same reversed
    # model order consumed by _profile_and_obs.  It is required for the actual
    # hydrometeor bridge and remains fixed while the initial qc direction varies.
    rho_d = (torch.flip(forcing.rho / (1.0 + state.qv), [-1])[0].detach().clone()
             if all_sky else None)
    profile_cfg = RttovProfileConfig(
        gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
        rttov_layer_pressure=p_lay, rttov_level_pressure=p_half,
        cloud=all_sky, rho_d=rho_d)
    obs_cfg = OsseObsConfig(
        run_k=None, profile_cfg=profile_cfg, input_cfg=input_cfg, obs_sigma=1.0,
        t_ref=torch.as_tensor(np.asarray(tr, dtype=float), dtype=torch.float64),
        q_ref=torch.as_tensor(np.asarray(qr, dtype=float), dtype=torch.float64))
    obs = {"bt": y, "obs_quality": yq}
    report: dict[str, Any] = {
        "status": "live_started",
        "selection": {
            "columns": owners, "n_profiles": len(owners),
            "selection_rule": ("explicit assigned usable hydrometeor column" if column is not None
                               else "assigned clean-IR columns ranked by qc+qi+qs > 1e-6"),
            "hydrometeor_total": hydrometeor_total.detach().cpu().tolist(),
        },
        "observation_contract": {
            "mask": "(obs_quality == 0) & (rad_quality == 0)",
            "bias": {"source": "absent", "effective": "zero"},
            "channel_gate": {"source": "absent", "effective": "one after quality"},
            "sigma": {"source": "script config", "value": 1.0, "units": "K",
                       "R": "diag(sigma**2) = 1 K^2"},
            "huber_delta": 1.0,
            "time": {
                "GK2A": stamp,
                "KDM": frame.meta.get("valid_time_utc"),
                "RTTOV": "fixture profile datetime; actual satellite time is not overlaid",
            },
        },
        "serialization_contract": {
            "writer_format": "%.16E",
            "approx_decimal_digits": 16,
            "rttov_output_realprec": 12,
            "rttov_output_format": "E21.12",
            "radiance_fd_resolution": "recorded from each emitted RADIANCE%BT block; FD bound is mask_count*quantum/(4*epsilon) per plus/minus case",
            "fixture_grid_evidence_level": "wiring_only",
            "collocation_geometry_evidence_level": "actual (GK2A/KDM lat/lon)",
            "rttov_geometry_evidence_level": "wiring_only (fixture angles; no per-pixel angle aux supplied)",
        },
        "observation_mode": "all_sky" if all_sky else "clear_sky",
        "directions": {},
    }

    def invoke(s, case_name):
        # Each invocation gets a separate root. The temporary root is below the
        # requested output directory's parent, never below an ancestor run.
        case_root = Path(tempfile.mkdtemp(prefix=f"{case_name}-", dir=scratch_path))
        live = make_live_run_k(case_root)
        seen: dict[str, Any] = {}

        def recording(rin):
            seen["rin"] = rin
            value = live(rin)
            seen["result"] = value
            return value

        initial = State(*(f.detach().clone().to(torch.float64).requires_grad_(True)
                          for f in s))
        evolved, handle = kdm6_step(initial, forcing, dt=20.0, xland=xland)
        # model_to_rttov_tensors' cloud staging is deliberately a single-column
        # boundary.  Keep the batch dimension for the initial-state derivative,
        # but pass its one selected real column into M->H.
        evolved_col = State(*(v[0] for v in evolved)) if all_sky else evolved
        forcing_col = type(forcing)(*(v[0] for v in forcing)) if all_sky else forcing
        leaves, prof, t_lay, q_lay, bt, rq = _profile_and_obs(
            evolved_col, forcing_col, obs_cfg, run_k=recording,
            xland=xland[0] if all_sky else xland,
            detach_state=False)
        mask = ((yq == 0) & (rq == 0)).to(torch.float64)
        j = compute_obs_loss(bt, obs, mask, sigma=1.0, delta=1.0)
        grad = torch.autograd.grad(j, (initial.th, initial.qv, initial.qc), allow_unused=True)
        handle.close()
        rin = seen["rin"]
        output = seen["result"]
        radiance_path = case_root / "out" / "k" / "radiance.txt"
        radiance_resolution = _radiance_text_resolution(radiance_path)
        profile_info = {k: _finite_stats(v) for k, v in rin.profile.items()}
        serial_errors = {}
        serialized_values = {}
        for field, values in rin.profile.items():
            if field not in ("T", "Q"):
                continue
            expected_all = np.asarray(values, dtype=np.float64)
            written_all = expected_all.copy()
            abs_errors = []
            unequal_diffs = []
            for p in range(rin.nprofiles):
                source = Path(case_root) / "in" / "profiles" / f"{p + 1:03d}" / "atm" / ("t.txt" if field == "T" else "q.txt")
                written = np.loadtxt(source).reshape(-1)
                expected = np.asarray(values[p]).reshape(-1)
                written_all[p] = written
                diff = np.abs(written - expected)
                abs_errors.append(float(np.max(diff)))
                unequal = written != expected
                unequal_diffs.extend(diff[unequal].tolist())
            serial_errors[field] = {
                "max_abs": max(abs_errors),
                "unchanged_roundtrip": bool(np.array_equal(written_all, expected_all)),
                "min_nonzero_abs": min(unequal_diffs) if unequal_diffs else None,
                "profiles_checked": rin.nprofiles,
            }
            serialized_values[field] = written_all
        return {
            "case_root": str(case_root),
            "case_root_ephemeral": True,
            "profile": profile_info,
            "profile_config_hash": rin.config_hash,
            "kdm_step": {
                "dt_seconds": 20.0,
                "xland": xland.detach().cpu().tolist(),
                "state_in": {k: _finite_stats(getattr(s, k)) for k in s._fields},
                "state_input_domain": {
                    "qv_min": float(s.qv.min()),
                    "qv_negative_count": int((s.qv < 0).sum()),
                    "qc_min": float(s.qc.min()),
                    "qc_negative_count": int((s.qc < 0).sum()),
                    "admissible_qv_qc": bool((s.qv >= 0).all() and (s.qc >= 0).all()),
                },
                "state_out": {k: _finite_stats(getattr(evolved, k)) for k in evolved._fields},
                "derivative_scope": "initial KDM state -> evolved state -> RTTOV profile/H/J",
            },
            "bt": _finite_stats(bt.detach()),
            "bt_values": bt.detach().cpu().tolist(),
            "K": {k: _finite_stats(v) for k, v in output[1].items()},
            "K_contract": "RTTOV BT-space K used as K^T lambda; dK/dx is not claimed",
            "rad_quality": _finite_stats(rq),
            "rad_quality_values": rq.detach().cpu().tolist(),
            "rad_quality_zero": int((rq == 0).sum()),
            "mask_kept": int(mask.sum()),
            "mask_values": mask.detach().cpu().tolist(),
            "J": float(j.detach()),
            "radiance_output": radiance_resolution,
            "gradient": {
                "th": _finite_stats(grad[0]) if grad[0] is not None else None,
                "qv": _finite_stats(grad[1]) if grad[1] is not None else None,
                "qc": _finite_stats(grad[2]) if grad[2] is not None else None,
                "th_values": grad[0].detach().cpu().tolist() if grad[0] is not None else None,
                "qv_values": grad[1].detach().cpu().tolist() if grad[1] is not None else None,
                "qc_values": grad[2].detach().cpu().tolist() if grad[2] is not None else None,
            },
            "serialization": serial_errors,
            "serialized_values": {k: v.tolist() for k, v in serialized_values.items()},
            "fixture_case": str(__import__("kdm6.obs.rttov_case_writer", fromlist=["default_fixture_case_dir"]).default_fixture_case_dir()),
        }

    with tempfile.TemporaryDirectory(prefix="v3-live-gradient-", dir=out_path.parent) as scratch:
        scratch_path = Path(scratch)
        base = invoke(state, "base")
        report["baseline"] = base
        directions = {
            "th": _direction(tuple(state.th.shape), seed=60409, max_abs=1.0),
            # qv is positivity-limited in the model and profile bridge.  A
            # relative direction keeps central-FD endpoints admissible for
            # |epsilon|<=1; the old absolute probe remains in the bounded A1
            # diagnostic as an explicit kink regression.
            "qv": _relative_positive_direction(state.qv, seed=60410,
                                                 fractional_max=1.0e-1),
            "qc": _relative_positive_direction(state.qc, seed=60411,
                                                 fractional_max=1.0e-1),
        }
        for name, direction in directions.items():
            g = base["gradient"][name + "_values"]
            if g is None:
                report["directions"][name] = {"status": "unresolved", "reason": "AD gradient is None"}
                continue
            direction_dot = float((np.asarray(g) * direction.numpy()).sum())
            drep = {"status": "running", "direction_max_abs": float(direction.abs().max()),
                    "AD_directional_J": direction_dot, "eps": {}}
            for e in eps:
                plus = state._replace(**{name: getattr(state, name) + e * direction})
                minus = state._replace(**{name: getattr(state, name) - e * direction})
                p = invoke(plus, f"{name}-plus-{e:g}")
                m = invoke(minus, f"{name}-minus-{e:g}")
                same_mask = (p["mask_values"] == base["mask_values"] == m["mask_values"])
                fd = (p["J"] - m["J"]) / (2.0 * e)
                drep["eps"][str(e)] = {
                    "plus_J": p["J"], "minus_J": m["J"], "central_FD_J": fd,
                    "abs_error_vs_AD": abs(fd - direction_dot),
                    "relative_error_vs_AD": abs(fd - direction_dot) / max(abs(direction_dot), 1.0e-12),
                    "fd_relative_tolerance": FD_REL_TOL,
                    "same_mask": same_mask,
                    "input_admissible": bool(
                        p["kdm_step"]["state_input_domain"]["admissible_qv_qc"]
                        and m["kdm_step"]["state_input_domain"]["admissible_qv_qc"]),
                    "rad_quality_changed_count": {
                        "plus": int(np.count_nonzero(
                            np.asarray(p["rad_quality_values"]) !=
                            np.asarray(base["rad_quality_values"]))),
                        "minus": int(np.count_nonzero(
                            np.asarray(m["rad_quality_values"]) !=
                            np.asarray(base["rad_quality_values"]))),
                    },
                    "serialization_changed_count": {
                        field: {
                            "plus": int(np.count_nonzero(
                                np.asarray(p["serialized_values"][field]) !=
                                np.asarray(base["serialized_values"][field]))),
                            "minus": int(np.count_nonzero(
                                np.asarray(m["serialized_values"][field]) !=
                                np.asarray(base["serialized_values"][field]))),
                        }
                        for field in ("T", "Q")
                    },
                    "serialization_plus": p["serialization"],
                    "serialization_minus": m["serialization"],
                    "fd_output_rounding_bound": (
                        p["radiance_output"].get("bt_decimal_quantum_upper_bound", 0.0)
                        * p["mask_kept"] / (4.0 * e)
                        + m["radiance_output"].get("bt_decimal_quantum_upper_bound", 0.0)
                        * m["mask_kept"] / (4.0 * e)),
                    "rad_quality_status": (
                        "unchanged" if p["rad_quality_values"] == base["rad_quality_values"] ==
                        m["rad_quality_values"] else
                        "changed_but_quality_mask_unchanged" if same_mask else "changed_mask"),
                    "resolution_status": "resolved" if same_mask and any(
                        int(np.count_nonzero(np.asarray(p["serialized_values"][field]) !=
                                             np.asarray(base["serialized_values"][field]))) > 0
                        and int(np.count_nonzero(np.asarray(m["serialized_values"][field]) !=
                                                 np.asarray(base["serialized_values"][field]))) > 0
                        for field in ("T", "Q")) else "unresolved",
                }
            vals = list(drep["eps"].values())
            drep["status"] = _direction_status(direction_dot, vals, base["mask_kept"])
            report["directions"][name] = drep
        if base["mask_kept"] == 0:
            report["no_usable_channels"] = (
                "RTTOV rad_quality and the actual GK2A clean-IR obs_quality have no "
                "jointly usable channel for this mode; FD values are diagnostic only.")
            for d in report["directions"].values():
                d["status"] = "unresolved"
                d["reason"] = "no jointly usable observation channels"
        report["status"] = (
            "live_complete" if base["mask_kept"] > 0
            and all(d["status"] == "pass" for d in report["directions"].values())
            else "live_complete_with_unresolved_directions")
    return report


def _direction_status(ad, rows, mask_kept):
    """First-order FD evidence requires a non-vacuous, resolved direction."""
    if mask_kept <= 0 or not math.isfinite(ad) or ad == 0.0 or not rows:
        return "unresolved"
    for row in rows:
        bound = row.get("fd_output_rounding_bound")
        if (not row["same_mask"] or not row.get("input_admissible", False)
                or row["resolution_status"] != "resolved"
                or not math.isfinite(row["central_FD_J"])
                or not math.isfinite(row["relative_error_vs_AD"])
                or row["relative_error_vs_AD"] > FD_REL_TOL
                or bound is None or not math.isfinite(bound)
                or bound > abs(ad) * FD_REL_TOL):
            return "unresolved"
    return "pass"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kdm", type=Path, default=DEFAULT_KDM)
    parser.add_argument("--gk2a-root", type=Path, default=DEFAULT_GK2A)
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CAL)
    parser.add_argument("--stamp", default=DEFAULT_STAMP)
    parser.add_argument("--stride", type=int, default=8)
    parser.add_argument("--max-dist-km", type=float, default=4.0)
    parser.add_argument("--max-profiles", type=int, default=1)
    parser.add_argument("--column", type=int, help="explicit collocated hydrometeor column for a diagnosed case")
    parser.add_argument("--all-sky", action="store_true",
                        help="include the single-column hydrometeor bridge and cloud K fields")
    parser.add_argument("--eps", type=float, nargs="+", default=list(DEFAULT_EPS))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--live", action="store_true", help="invoke the external RTTOV runK")
    args = parser.parse_args(argv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    inv = build_inventory(args.kdm, args.gk2a_root, args.calibration, args.stamp,
                          stride=args.stride, max_dist_km=args.max_dist_km)
    report = {
        "evidence_id": "V3-GK2A-KDM6-RTTOV-live-gradient-v1",
        "status": inv["status"],
        "evidence_level": "actual_inventory_only",
        "claim": "first-order K^T gradient contract; no dK/dx/full Hessian claim",
        "direction_contract": {
            "qv": "relative-positive |direction| <= 0.1*qv; absolute negative-domain probe is separate A1 evidence",
            "qc": "relative-positive |direction| <= 0.1*qc; zero qc cells remain zero and provide no qc direction",
            "admissibility": "every plus/minus initial qv and qc value must be nonnegative",
        },
        "runtime": {"python": platform.python_version(), "torch": torch.__version__,
                    "numpy": np.__version__, "platform": platform.platform()},
        "inputs": {"kdm": str(args.kdm), "gk2a_root": str(args.gk2a_root),
                   "calibration": str(args.calibration), "stamp": args.stamp},
        "provenance": build_provenance(args.calibration, all_sky=args.all_sky),
        "observation_contract": {
            "mask": "(obs_quality == 0) & (rad_quality == 0)",
            "bias": {"source": "GK2A payload has no bias field", "effective": "zero"},
            "channel_gate": {"source": "GK2A payload has no channel_gate field", "effective": "one after quality"},
            "R": {"source": "explicit evidence-run configuration", "sigma": 1.0,
                  "units": "K", "form": "diagonal R=sigma**2=1 K^2"},
            "loss": {"form": "Huber", "delta": 1.0},
            "geometry": {
                "collocation": "actual GK2A/KDM coordinates",
                "RTTOV": "fixture default geometry; this run does not claim actual viewing/solar geometry validation",
            },
            "time": {
                "GK2A": args.stamp,
                "KDM": inv.get("frame", {}).get("valid_time_utc"),
                "RTTOV": "fixture profile datetime; actual satellite time is not overlaid",
            },
        },
        "inventory": inv,
    }
    if args.live:
        if inv["status"] != "inventory_ok":
            raise SystemExit(f"cannot run live evidence: {inv['status']} ({inv['asset_missing']})")
        report["live"] = _run_live(
            args.kdm, args.gk2a_root, args.calibration, args.stamp,
            stride=args.stride, max_dist_km=args.max_dist_km,
            max_profiles=args.max_profiles, eps=tuple(args.eps), out_path=args.out,
            all_sky=args.all_sky, column=args.column)
        report["status"] = report["live"]["status"]
        report["evidence_level"] = "actual_collocation_plus_fixture_geometry_live_rttov"
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "out": str(args.out)}, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
