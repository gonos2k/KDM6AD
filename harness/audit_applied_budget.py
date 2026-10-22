"""Value-only applied-change ledger for a saved native substep experiment.

No KDM, native model, RTTOV or AD is executed. Fixed captured dry-air column
weights turn water mixing-ratio changes into kg m-2; this is a change ledger,
not a closed physical budget or a named-process attribution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

WATER_FIELDS = ("QV", "QC", "QR", "QI", "QS", "QG")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _array(value, shape, name):
    out = np.asarray(value, dtype=np.float64)
    if out.shape != shape or not np.isfinite(out).all():
        raise ValueError(f"{name} must be finite with shape {shape}")
    return out


def split_changes(before, raw, clean, dt, weights):
    """Separate KDM and cleanup changes without inferring either's physics.

    The six water rows have a declared kg-water/kg-dry-air coordinate. Weights
    are fixed kg-dry-air/m2 at the captured MP entry, not moving control fields.
    Negative raw entries are allowed: cleanup can add water when repairing them.
    """
    if isinstance(dt, bool) or not np.isscalar(dt) or not np.isfinite(dt) or dt <= 0:
        raise ValueError("dt must be a positive finite fixed scalar")
    before = np.asarray(before, dtype=np.float64)
    if before.ndim != 2 or before.shape[0] != 6 or before.shape[1] < 1:
        raise ValueError("before must contain six complete nonempty water rows")
    before = _array(before, before.shape, "before")
    raw = _array(raw, before.shape, "raw")
    clean = _array(clean, before.shape, "clean")
    weights = _array(weights, (before.shape[1],), "weights")
    if np.any(weights <= 0) or np.any(before < 0) or np.any(clean < 0):
        raise ValueError("fixed weights must be positive and before/clean water nonnegative")
    kernel, cleanup, applied = raw-before, clean-raw, clean-before
    residual = applied-(kernel+cleanup)
    bound = 32*np.finfo(np.float64).eps*np.maximum(np.maximum(abs(before), abs(raw)), abs(clean))
    verified = bool(np.all(abs(residual) <= bound))
    fields = {}
    for index, name in enumerate(WATER_FIELDS):
        dz = cleanup[index]
        fields[name] = {
            "kernel_change_ratio": kernel[index].tolist(),
            "cleanup_change_ratio": dz.tolist(),
            "applied_change_ratio": applied[index].tolist(),
            "kernel_mean_rate_ratio_per_s": (kernel[index]/dt).tolist(),
            "cleanup_mean_rate_ratio_per_s": (dz/dt).tolist(),
            "applied_mean_rate_ratio_per_s": (applied[index]/dt).tolist(),
            "cleanup_changed_levels_1based": (np.flatnonzero(dz != 0)+1).tolist(),
            "cleanup_max_removed_ratio": float(np.max(np.maximum(-dz, 0.))),
            "cleanup_removed_kg_m2": float(weights @ np.maximum(-dz, 0.)),
            "cleanup_added_kg_m2": float(weights @ np.maximum(dz, 0.)),
            "kernel_change_kg_m2": float(weights @ kernel[index]),
            "cleanup_change_kg_m2": float(weights @ dz),
            "applied_change_kg_m2": float(weights @ applied[index]),
        }
    totals = {name+"_change_kg_m2": float(np.sum(values*weights[None, :]))
              for name, values in (("kernel", kernel), ("cleanup", cleanup), ("applied", applied))}
    totals["algebraic_split_residual_kg_m2"] = float(np.sum(residual*weights[None, :]))
    return {"fields": fields, "total_water": totals,
            "algebraic_split_verified": verified,
            "max_ratio_split_residual": float(np.max(abs(residual)))}


def audit(report):
    """Read the exact v1 saved-composition layout; never alter the input arrays."""
    if report.get("schema") != "kdm6.microphysics_observation_ad.v1":
        raise ValueError("requires a saved microphysics_observation_ad.v1 report")
    contract = report["kernel_contract"]
    if contract.get("physics_variant") != 0 or contract.get("dry_number") != 0:
        raise ValueError("this audit labels only the captured legacy/raw kernel case")
    options = report.get("native_prep_phase", {}).get("namelist_options", {})
    required = {"mp_physics": 137, "use_theta_m": 1, "no_mp_heating": 0,
                "use_q_diabatic": 0, "mp_zero_out": 2, "mp_zero_out_all": 0}
    if any(options.get(name) != value for name, value in required.items()):
        raise ValueError("requires the audited MP137 moist-theta/cleanup namelist contract")
    raw = np.asarray(report["kernel_after"], dtype=np.float64)
    if raw.ndim != 2 or raw.shape[0] != 12 or raw.shape[1] < 1:
        raise ValueError("kernel_after must have twelve nonempty state rows")
    levels = raw.shape[1]
    raw = _array(raw, (12, levels), "kernel_after")
    clean = _array(report["clean_after"], raw.shape, "clean_after")
    x = _array(report["native_X"], (3*levels+2,), "native_X")
    rest = _array(report["native_rest"], (10, levels), "native_rest")
    before = np.vstack((x[levels:2*levels], rest[:5]))
    dt = contract["dt_seconds"]
    captured = report["native_f32_replay"]["captured_f32"]
    rho = _array(captured["DEN"], (levels,), "captured dry DEN")
    dz = _array(captured["DELZ"], (levels,), "captured DELZ")
    if np.any(rho <= 0) or np.any(dz <= 0):
        raise ValueError("captured dry density and layer thickness must be positive")
    weights = rho*dz
    ledger = split_changes(before, raw[1:7], clean[1:7], dt, weights)
    finish = report["applied_finish"]
    qv_rate = _array(finish["QV_RATE"], (levels,), "QV_RATE")
    qc_rate = _array(finish["QC_RATE"], (levels,), "QC_RATE")
    thm = _array(finish["T_NEW_AFTER"], (levels,), "T_NEW_AFTER")
    heating = _array(finish["H_RATE"], (levels,), "H_RATE")
    qv_error = qv_rate-(clean[1]-before[0])/dt
    qc_error = qc_rate-(clean[2]-before[1])/dt
    heating_error = thm-(x[:levels]+dt*heating)
    heat_bound = 32*np.finfo(np.float64).eps*np.maximum(1., np.maximum(abs(thm), abs(x[:levels])))
    rates_ok = bool(np.all(qv_error == 0) and np.all(qc_error == 0) and
                    np.all(abs(heating_error) <= heat_bound))
    number = {}
    for name, row, prior in (("NN", 7, 5), ("NC", 8, 6), ("NI", 9, 7), ("NR", 10, 8)):
        number[name] = {"coordinate": "legacy raw operand; no host dry-number inventory certified",
                        "kernel_change_raw": (raw[row]-rest[prior]).tolist(),
                        "cleanup_change_raw": (clean[row]-raw[row]).tolist(),
                        "cleanup_exact_identity": bool(np.array_equal(clean[row], raw[row]))}
    pairs = {}
    for name, mass_row, number_row in (("QC_NC", 2, 8), ("QI_NI", 4, 9), ("QR_NR", 3, 10)):
        mask = (clean[mass_row] == 0) & (clean[number_row] > 0)
        newly = mask & (raw[mass_row] > 0)
        pairs[name] = {"clean_zero_mass_positive_raw_number_levels_1based": (np.flatnonzero(mask)+1).tolist(),
                       "newly_zero_mass_after_cleanup_levels_1based": (np.flatnonzero(newly)+1).tolist(),
                       "raw_number_at_newly_zero_mass_levels": clean[number_row, newly].tolist(),
                       "interpretation": "inactive mass with retained raw number; no compensating number transfer inferred"}
    return {"schema": "kdm6.applied_change_ledger.v1", "levels": levels, "dt_seconds": dt,
            "native_column": report["native_snapshot"],
            "audited_namelist_options": options,
            "weight_contract": {"kind": "fixed captured MP-entry density-thickness layer measure; not an RK/MU flux ledger",
                                "formula": "captured_DEN * captured_DELZ, binary32 values promoted before product",
                                "units": "kg_dry_air m-2", "rho_d_kg_m3": rho.tolist(),
                                "delz_m": dz.tolist(), "weights_kg_m2": weights.tolist(),
                                "column_dry_mass_kg_m2": float(np.sum(weights))},
            "water_coordinate": "kg water / kg dry air; changes interpreted with the same fixed captured weights",
            "water": ledger, "number": number, "mass_number_pairs": pairs,
            "finish_checks": {"QV_RATE_maxabs_error": float(np.max(abs(qv_error))),
                              "QC_RATE_maxabs_error": float(np.max(abs(qc_error))),
                              "THM_after_minus_before_dtH_maxabs_K": float(np.max(abs(heating_error))),
                              "rounding_consistent": rates_ok},
            "surface_exports_available_for_this_fp64_call": False,
            "cleanup_rule_recomputed": False,
            "cleanup_threshold_available_in_source_report": False,
            "input_derivative_verification_passed": report.get("passed"),
            "closed_water_budget_certified": False, "closed_energy_budget_certified": False,
            "closed_number_budget_certified": False, "number_basis_certified": False,
            "passed": bool(ledger["algebraic_split_verified"] and rates_ok and
                           all(v["cleanup_exact_identity"] for v in number.values())),
            "limits": "fixed-measure state-change decomposition, not named KDM process rates; same-call sedimentation exports and a full energy/number ledger are absent; no conservation proof, AD, native integration, RTTOV evaluation or unit repair"}


def run(source, output):
    source, output = Path(source), Path(output)
    if output.exists() or output.is_symlink() or output.resolve() in (source.resolve(), Path(__file__).resolve()):
        raise ValueError("output must be new and distinct from input/source")
    pinned = sha(source)
    report = audit(json.loads(source.read_text()))
    if sha(source) != pinned:
        raise RuntimeError("input changed while reading the saved report")
    report.update(source_report=str(source.resolve()), source_report_sha256=pinned,
                  audit_source_sha256=sha(__file__))
    with output.open("x") as stream:
        stream.write(json.dumps(report, indent=2, allow_nan=False)+"\n")
    if not report["passed"]:
        raise SystemExit("applied change identity check failed; see the saved ledger")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.input, args.output)
    print(json.dumps({"passed": result["passed"], **result["water"]["total_water"]}, indent=2))
