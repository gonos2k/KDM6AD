"""Replay one original B512 block's saved cloud/profile/BT response with NumPy.

No physics or RTTOV is called. K times a finite profile difference is a local
linear projection, not the full native-input JVP and not process attribution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

PHASES = (("baseline", 0.0), ("alpha0p25", 0.25), ("alpha0p5", 0.5), ("alpha1", 1.0))
PROFILE_FIELDS = ("T", "Q", "P", "P_HALF", "HYDRO6", "HYDRO7", "HYDRO_DEFF6", "HYDRO_DEFF7")
INV_DMC = float(np.float32(1.0 / np.float32(3.0)))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finite_profile_projection(k_by_field, before, after):
    """Contract rounded binary64 products, retaining separate field terms."""
    terms = {}
    channels = None
    for name in PROFILE_FIELDS:
        k = np.asarray(k_by_field[name])
        p0, p1 = np.asarray(before[name]), np.asarray(after[name])
        if (k.dtype != np.float64 or p0.dtype != np.float64 or p1.dtype != np.float64
                or k.ndim != 2 or p0.ndim != 1 or p0.shape != p1.shape
                or k.shape[1] != p0.size or not all(np.isfinite(x).all() for x in (k, p0, p1))):
            raise ValueError(f"invalid K/profile layout for {name}")
        channels = k.shape[0] if channels is None else channels
        if k.shape[0] != channels:
            raise ValueError("K fields disagree on channel count")
        product = k * (p1 - p0)[None, :]
        terms[name] = [math.fsum(map(float, row)) for row in product]
    total = [math.fsum(terms[name][c] for name in PROFILE_FIELDS) for c in range(channels)]
    return {"by_field_K": terms, "total_K": total,
            "scope": "baseline RTTOV K times observed finite profile change; not native-input JVP"}


def moment_diameter_ratio(q0, n0, rho0, d0, q1, n1, rho1):
    """Active, unclipped cloud-slope scaling with the executed f32 reciprocal."""
    values = (q0, n0, rho0, d0, q1, n1, rho1)
    if not all(math.isfinite(x) and x > 0 for x in values):
        raise ValueError("positive finite cloud moments/density/diameter required")
    ratio = ((rho1 * q1) / (rho0 * q0)) * (n0 / n1)
    return d0 * math.exp(INV_DMC * math.log(ratio))


def _profile_row(arrays, phase, row):
    rows = arrays[phase + "_profile_rows"]
    if (rows.ndim != 1 or rows.dtype.kind not in "iu" or len(np.unique(rows)) != len(rows)
            or np.any(rows < 0) or np.any(rows >= 512)):
        raise ValueError(f"invalid saved profile-row mapping: {phase}")
    found = np.flatnonzero(rows == row)
    if len(found) != 1:
        raise ValueError(f"target row is not profile-eligible: {phase}")
    return int(found[0])


def analyze(manifest_path):
    manifest_path = Path(manifest_path).resolve(strict=True)
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema") != "kdm6.saved_block22_response_input.v1":
        raise ValueError("unsupported saved-block response schema")
    if (manifest.get("target_flat_index0") != 11632 or manifest.get("native_mass_level1") != 18
            or manifest.get("channel_id") != 13):
        raise ValueError("manifest target differs from the declared block22 case")
    inventory = manifest_path.parent / "source_inventory.json"
    if sha(inventory) != manifest["source_inventory_sha256"]:
        raise ValueError("saved source inventory hash differs")
    record = manifest["input_npz"]
    relative = Path(record["file"])
    raw_path = manifest_path.parent / relative
    path = raw_path.resolve(strict=True)
    if (relative.is_absolute() or ".." in relative.parts or raw_path.is_symlink()
            or manifest_path.parent not in path.parents):
        raise ValueError("saved input must remain inside its manifest directory")
    if sha(path) != record["sha256"] or path.stat().st_size != record["bytes"]:
        raise ValueError("saved response input hash/size differs")
    with np.load(path, allow_pickle=False) as archive:
        arrays = {name: archive[name].copy() for name in archive.files}
    flat = arrays["flat_index"]
    if not np.array_equal(flat, np.arange(22 * 512, 23 * 512)):
        raise ValueError("analysis requires the complete original block22, without B1 remapping")
    target, k1, channel = 11632, 18, 13
    row = int(np.flatnonzero(flat == target)[0])
    k = k1 - 1
    ci = channel - 10
    for phase, _ in PHASES:
        for name in ("theta_m", "qv", "native_after_thm_pert", "native_after_qv",
                     "cloud_qc", "cloud_nc", "rho_d"):
            value = arrays[phase + "_" + name]
            if value.dtype != np.float64 or value.shape != (512, 39) or not np.isfinite(value).all():
                raise ValueError(f"invalid native field {phase}/{name}")
        if arrays[phase + "_finish"].shape != (5, 512, 39):
            raise ValueError("saved finish must retain five native 39-level fields")
        if (arrays[phase + "_bt"].shape != (512, 7)
                or arrays[phase + "_bt"].dtype != np.float64):
            raise ValueError("saved BT must retain the original B512/seven-channel layout")
    base_pr = _profile_row(arrays, "baseline", row)
    nrt = arrays["baseline_profile_T"].shape[1]
    rt_k = nrt - 1 - k
    if nrt < 39:
        raise ValueError("RTTOV profile cannot truncate native levels")
    before = {name: arrays["baseline_profile_" + name][base_pr] for name in PROFILE_FIELDS}
    k_fields = {name: arrays["baseline_K_" + name][base_pr] for name in PROFILE_FIELDS}
    if any(value.shape[0] != 7 for value in k_fields.values()):
        raise ValueError("baseline K must retain all seven channels")
    bt0 = arrays["baseline_bt"][row]
    base_qc = float(arrays["baseline_cloud_qc"][row, k])
    base_nc = float(arrays["baseline_cloud_nc"][row, k])
    base_rho = float(arrays["baseline_rho_d"][row, k])
    base_d = float(before["HYDRO_DEFF6"][rt_k])
    base_cf = arrays["baseline_profile_CFRAC"][base_pr]
    baseline_mask = arrays["baseline_mask"]
    if baseline_mask.dtype != np.bool_ or baseline_mask.shape != (512, 7) or not baseline_mask[row, ci]:
        raise ValueError("target channel is not on frozen baseline support")
    endpoints, linearizations, relations, distribution = [], {}, {}, {}
    for phase, alpha in PHASES:
        pr = _profile_row(arrays, phase, row)
        after = {name: arrays[phase + "_profile_" + name][pr] for name in PROFILE_FIELDS}
        qc, nc, rho = (float(arrays[phase + "_" + name][row, k])
                       for name in ("cloud_qc", "cloud_nc", "rho_d"))
        bt = arrays[phase + "_bt"][row]
        cf = arrays[phase + "_profile_CFRAC"][pr]
        prediction = moment_diameter_ratio(base_qc, base_nc, base_rho, base_d, qc, nc, rho)
        endpoints.append({
            "alpha": alpha, "input_theta_m_K": float(arrays[phase + "_theta_m"][row, k]),
            "input_qv_kgkg_dry": float(arrays[phase + "_qv"][row, k]),
            "stored_state_input_theta_delta_K": float(arrays[phase + "_theta_m"][row, k]
                                                      - arrays["baseline_theta_m"][row, k]),
            "stored_state_input_qv_delta_kgkg_dry": float(arrays[phase + "_qv"][row, k]
                                                         - arrays["baseline_qv"][row, k]),
            "QC_after_kgkg_dry": qc, "NC_after_legacy_raw": nc, "rho_d_kg_m3": rho,
            "QC_ratio_to_baseline": qc / base_qc, "NC_ratio_to_baseline": nc / base_nc,
            "profile_T_K": float(after["T"][rt_k]),
            "liquid_content_g_m3": float(after["HYDRO6"][rt_k]),
            "liquid_effective_diameter_um": float(after["HYDRO_DEFF6"][rt_k]),
            "moment_ratio_diameter_um": prediction,
            "diameter_ratio_error_um": float(after["HYDRO_DEFF6"][rt_k]) - prediction,
            "cloud_fraction": float(cf[rt_k]),
            "column_CFRAC_changed_layers": int(np.count_nonzero(cf != base_cf)),
            "IR105_BT_K": float(bt[ci]), "IR105_BT_delta_K": float(bt[ci] - bt0[ci]),
        })
        projection = finite_profile_projection(k_fields, before, after)
        actual = bt - bt0
        projection["actual_BT_delta_K"] = actual.tolist()
        projection["actual_minus_projection_K"] = (actual - projection["total_K"]).tolist()
        projection["IR105_by_field_K"] = {name: term[ci] for name, term in projection["by_field_K"].items()}
        linearizations[phase] = projection
        dinput_q = arrays[phase + "_qv"] - arrays["baseline_qv"]
        dinput_t = arrays[phase + "_theta_m"] - arrays["baseline_theta_m"]
        dfinish = arrays[phase + "_finish"] - arrays["baseline_finish"]
        dq = arrays[phase + "_native_after_qv"] - arrays["baseline_native_after_qv"]
        dc = arrays[phase + "_cloud_qc"] - arrays["baseline_cloud_qc"]
        dt = arrays[phase + "_native_after_thm_pert"] - arrays["baseline_native_after_thm_pert"]
        relations[phase] = {"scope": "all 512 columns × 39 layers; differences are stored-state differences",
            "QV_max_residual_kgkg": float(np.max(np.abs(dq - dinput_q - 20.0 * dfinish[2]))),
            "QC_max_residual_kgkg": float(np.max(np.abs(dc - 20.0 * dfinish[3]))),
            "THM_max_residual_K": float(np.max(np.abs(dt - dinput_t - 20.0 * dfinish[1])))}
        selected = baseline_mask[:, ci]
        changes = np.abs(arrays[phase + "_bt"][selected, ci] - arrays["baseline_bt"][selected, ci])
        if not np.isfinite(changes).all():
            raise ValueError("saved phase loses finite BT on the block's baseline support")
        quality = arrays[phase + "_quality"]
        if quality.shape != (512, 7) or quality.dtype.kind not in "iu" or np.any(quality[selected, ci] != 0):
            raise ValueError("saved phase changes model quality on baseline IR105 support")
        distribution[phase] = {"supported_columns": int(selected.sum()),
            "p95_abs_delta_BT_K": float(np.quantile(changes, .95)),
            "max_abs_delta_BT_K": float(changes.max()),
            "over_1K": int(np.count_nonzero(changes > 1.0)),
            "over_5K": int(np.count_nonzero(changes > 5.0))}
    restricted_checks = {}
    for name, value in arrays.items():
        if name.startswith("restricted_alpha1_"):
            original = "alpha1_" + name.removeprefix("restricted_alpha1_")
            if original in arrays:
                restricted_checks[name] = value.tobytes() == arrays[original].tobytes()
    if not restricted_checks or not all(restricted_checks.values()):
        raise ValueError("restricted alpha1 differs from its original full-B512 reference")
    captured = {}
    rows = {"TH_absolute_dry_K": 0, "QV_kgkg_dry": 1, "QC_kgkg_dry": 2,
            "QI_kgkg_dry": 4, "NN_legacy_raw": 7, "NC_legacy_raw": 8}
    for stage in ("before", "raw", "clean_replay"):
        state = arrays["restricted_applied_" + stage]
        if state.shape != (12, 512, 39) or state.dtype != np.float64 or not np.isfinite(state).all():
            raise ValueError("restricted captured state must retain its original full B512")
        captured[stage] = {name: float(state[index, row, k]) for name, index in rows.items()}
    probe_profile = {name: arrays["baseline_profile_jvp_" + name][base_pr]
                     for name in PROFILE_FIELDS}
    probe_terms = finite_profile_projection(k_fields,
                     {name: np.zeros_like(value) for name, value in probe_profile.items()},
                     probe_profile)
    saved_probe = arrays["baseline_bt_jvp"][row]
    probe_total = np.asarray(probe_terms["total_K"], dtype=np.float64)
    if probe_total.tobytes() != saved_probe.tobytes():
        raise ValueError("saved fixed-probe K/profile contraction does not reproduce its BT JVP")
    return {"schema": "kdm6.saved_block22_response_analysis.v1",
        "scope": "Saved original B512 results only; zero KDM/RTTOV/host calls.",
        "input_manifest_sha256": sha(manifest_path), "input_npz_sha256": sha(path),
        "analyzer_sha256": sha(Path(__file__)),
        "target": {"flat_index0": target, "block0": 22, "row0": row, "native_i1": 167,
                   "native_j1": 50, "native_mass_level1": k1, "RTTOV_layer1": rt_k + 1},
        "diameter_exponent": {"executed_f32_reciprocal_promoted_to_f64": INV_DMC,
                              "scope": "finite active/unclipped moment-ratio prediction anchored at baseline"},
        "endpoints": endpoints, "baseline_K_finite_profile_projection": linearizations,
        "restricted_vs_original_alpha1_bitwise": restricted_checks,
        "restricted_alpha1_direct_capture_at_target": captured,
        "saved_fixed_probe": {
            "scope": "Original independent sinusoidal native-input probe, NOT the candidate descent direction.",
            "theta_direction_K": arrays["baseline_direction_theta"][row].tolist(),
            "qv_direction_kgkg_dry": arrays["baseline_direction_qv"][row].tolist(),
            "saved_BT_JVP_K": saved_probe.tolist(), "reconstructed_BT_JVP_K": probe_total.tolist(),
            "IR105_by_profile_field_K": {name: term[ci] for name, term in probe_terms["by_field_K"].items()},
            "interpretation": "Per unit probe parameter at the baseline; cannot scale by trial alpha or treat as finite BT. Block22 was not an independent sparse-FD pilot."},
        "input_output_rate_relations": relations, "block_IR105_distribution": distribution,
        "new_model_calls": 0,
        "limits": ["Four coarse endpoints do not locate a threshold or establish discontinuity/smoothness.",
                   "Baseline K times finite profile change is not the original T/Q-direction JVP.",
                   "Profile-coordinate contributions are not named microphysical process causality.",
                   "No new derivative, forecast-skill, host/RK or conservation certification.",
                   "Number payload remains legacy raw; physical host number units are not newly certified."]}


def plot_response(result, output_dir):
    """Render saved endpoints as discrete points, not a sampled continuous curve."""
    import matplotlib.pyplot as plt

    output = Path(output_dir)
    if output.exists() or output.is_symlink():
        raise FileExistsError("response plots require a fresh directory")
    output.mkdir(parents=True, exist_ok=False)
    points = result["endpoints"]
    alpha = [row["alpha"] for row in points]
    fig, axes = plt.subplots(2, 3, figsize=(17, 10), constrained_layout=True)
    series = (
        ("QC_after_kgkg_dry", 1000, "Clean QC at native level 18", "g/kg dry air"),
        ("NC_after_legacy_raw", 1e-6, "Clean NC at native level 18", "legacy raw coordinate / 10^6"),
        ("liquid_effective_diameter_um", 1, "Liquid effective diameter", "micrometers"),
        ("liquid_content_g_m3", 1, "Liquid content at RTTOV layer 49", "g/m³"),
    )
    for ax, (key, scale, title, unit) in zip(axes.flat[:4], series):
        ax.plot(alpha, [row[key] * scale for row in points], "o--", color="#2466a1")
        ax.set(title=title, xlabel="alpha", ylabel=unit, xticks=alpha)
        ax.grid(alpha=0.2)
    axes[0, 2].axhline(5.02, color="gray", linestyle=":", label="inner radius floor ×2")
    axes[0, 2].axhline(52, color="gray", linestyle="-.", label="outer diameter ceiling")
    axes[0, 2].legend(fontsize=9)
    phases = [phase for phase, _ in PHASES]
    projected = [result["baseline_K_finite_profile_projection"][phase]["total_K"][3] for phase in phases]
    axes[1, 1].plot(alpha, [row["IR105_BT_delta_K"] for row in points], "ko--", label="Actual saved BT change")
    axes[1, 1].plot(alpha, projected, "s--", color="#bd691c", label="Baseline K × finite profile change")
    axes[1, 1].set(title="IR105 observation response", xlabel="alpha", ylabel="K", xticks=alpha)
    axes[1, 1].legend(fontsize=9)
    axes[1, 1].grid(alpha=0.2)
    terms = result["baseline_K_finite_profile_projection"]["alpha1"]["IR105_by_field_K"]
    axes[1, 2].barh(list(terms), list(terms.values()), color="#719dbb")
    axes[1, 2].set(title="Alpha=1 finite-profile linear projection", xlabel="K; profile coordinates, not process attribution")
    axes[1, 2].axvline(0, color="black", linewidth=0.7)
    fig.suptitle("Original B512 block 22, column (i=167,j=50): saved endpoints only\n"
                 "Native level 18 / RTTOV layer 49; CFRAC unchanged across all 66 target-column layers\n"
                 "Dashed segments only guide the eye; no small-alpha threshold location or new model execution")
    fig.savefig(output / "saved_block22_response.png", dpi=150)
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--plot-dir", type=Path)
    args = parser.parse_args(argv)
    if args.output_json.exists() or args.output_json.is_symlink():
        raise FileExistsError("analysis JSON requires a new path")
    if args.plot_dir is not None:
        if args.plot_dir.exists() or args.plot_dir.is_symlink():
            raise FileExistsError("response plots require a fresh directory")
        output, plots = args.output_json.resolve(), args.plot_dir.resolve()
        if output == plots or output in plots.parents or plots in output.parents:
            raise ValueError("JSON and plot output paths must not overlap")
    result = analyze(args.manifest)
    with args.output_json.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    if args.plot_dir is not None:
        plot_response(result, args.plot_dir)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
