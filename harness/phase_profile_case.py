"""Replay an input-selected 39-level phase event in the fp64 Python oracle.

The optional NetCDF capture reads a retained 5 km model file. Public replay
uses only the copied input vectors; it is not an mp37/native-host execution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "oracle"))
sys.path.insert(0, str(ROOT / "harness"))

import torch  # noqa: E402
from kdm6.state import State, Forcing  # noqa: E402
from kdm6.io.frame_reader import (  # noqa: E402
    derive_p_pii, derive_th, derive_rho, derive_delz,
)
from kdm6.runtime import kdm6_fn, make_parameters  # noqa: E402
from kdm6.process_controls import ProcessControls  # noqa: E402
from kdm6.sensitivity_diagnostics import SensitivityTrace  # noqa: E402
from phase_transfer_contract import PhaseTransfer, check_phase_budget  # noqa: E402


FRAME_SHA256 = "30ee8656cedf57cc827ad041e4ed8084d8bbf5afdbe0a21b28b33564544bca9f"
TIME_INDEX = 1
J, I, K = 96, 172, 21  # zero-based, native bottom-up model indices
DT = 20.0
ALPHA = math.log(1e6)  # diagnostic counterfactual; no operational coefficient change
STATE_SOURCE = {
    "qv": "QVAPOR", "qc": "QCLOUD", "qr": "QRAIN", "qi": "QICE",
    "qs": "QSNOW", "qg": "QGRAUP", "nccn": "QNCCN", "nc": "QNCLOUD",
    "ni": "QNICE", "nr": "QNRAIN", "bg": "QIB",
}
RAW_FIELDS = ("THM", "P", "PB", "PH", "PHB", *STATE_SOURCE.values())
PHASE_FIELDS = ("qc", "qi", "qr", "qg", "nc", "ni", "nr", "t")
RATE_FIELDS = ("pinuc", "pfrzdtc", "pfrzdtr", "ninuc", "nfrzdtc", "nfrzdtr")


def _tensor(values):
    arr = np.asarray(values, dtype=np.float64)
    return torch.from_numpy(arr.copy()).reshape(1, -1)


def _state_forcing(raw):
    if set(raw) != set(RAW_FIELDS):
        raise ValueError("public profile must contain the complete declared raw-field set")
    v = {name: _tensor(raw[name]) for name in RAW_FIELDS}
    if any(x.shape != (1, 40 if name in ("PH", "PHB") else 39)
           for name, x in v.items()):
        raise ValueError("expected native 39 center levels and 40 interfaces")
    if not all(bool(torch.isfinite(x).all()) for x in v.values()):
        raise ValueError("public profile contains nonfinite raw input")
    qv = v["QVAPOR"]
    p, pii = derive_p_pii(v["P"], v["PB"])
    state = State(
        th=derive_th(v["THM"], qv),
        **{name: v[source] for name, source in STATE_SOURCE.items()},
    )
    forcing = Forcing(
        rho=derive_rho(p, v["THM"], pii, qv), pii=pii, p=p,
        delz=derive_delz(v["PH"], v["PHB"]),
    )
    return state, forcing


def _cell(record, fields):
    return {name: float(getattr(record, name)[0, K]) for name in fields}


def run_profile(raw, *, controlled: bool):
    """Return values at the owning D2–D4 stage and later separate boundaries."""
    state, forcing = _state_forcing(raw)
    trace = SensitivityTrace()
    control = (ProcessControls(alpha_freeze=torch.tensor(ALPHA, dtype=torch.float64))
               if controlled else None)
    kdm6_fn(state, forcing, make_parameters(), DT, torch.tensor([1.0]),
             100.0, 10.0, control, diagnostic_trace=trace)
    records = trace.by_name("d2_d4_freeze")
    if len(records) != 1:
        raise ValueError("expected one D2–D4 stage on the 20 s profile")
    rec = records[0]
    if not bool(rec.branch[0, K]):
        raise ValueError("selected phase cell did not take the cold branch")
    factor = math.exp(ALPHA) if controlled else 1.0
    raw_amounts = {name: float(rec.operands[f"pre_control_{name}"][0, K])
                   for name in ("pinuc", "pfrzdtc", "ninuc", "nfrzdtc")}
    applied = _cell(rec.rates, RATE_FIELDS)
    prior = _cell(rec.state_in, PHASE_FIELDS)
    after = _cell(rec.state_out, PHASE_FIELDS)
    cpm = float(rec.operands["consumed_cpm"][0, K])
    xlf = float(rec.operands["consumed_xlf"][0, K])
    transfers = (
        PhaseTransfer("contact", "qc", "qi",
                      np.array([raw_amounts["pinuc"] * factor]),
                      np.array([applied["pinuc"]]), xlf),
        PhaseTransfer("immersion", "qc", "qi",
                      np.array([raw_amounts["pfrzdtc"] * factor]),
                      np.array([applied["pfrzdtc"]]), xlf),
        PhaseTransfer("rain_freeze", "qr", "qg",
                      np.array([applied["pfrzdtr"]]),
                      np.array([applied["pfrzdtr"]]), xlf),
    )
    budget = check_phase_budget(
        {name: np.array([prior[name]]) for name in ("qc", "qi", "qr", "qg")},
        {name: np.array([after[name]]) for name in ("qc", "qi", "qr", "qg")},
        np.array([prior["t"]]), np.array([after["t"]]), np.array([cpm]),
        transfers,
    )
    later = {}
    for stage in ("state_update", "picons", "satadj", "cleanup"):
        found = trace.by_name(stage)
        if len(found) != 1:
            raise ValueError(f"expected one separate {stage} boundary")
        later[stage] = _cell(found[0].state_out, ("qc", "qi", "t"))
    return {
        "controlled": controlled, "control_alpha": ALPHA if controlled else None,
        "control_factor": factor, "phase_before": prior, "phase_after": after,
        "producer_after_own_caps": raw_amounts, "applied": applied,
        "consumed_cpm": cpm, "consumed_xlf": xlf,
        "mass_residual_max": max(float(np.abs(x).max()) for x in budget.mass_residual.values()),
        "heat_residual_j_per_kg": float(budget.heat_residual_j_per_kg[0]),
        "later_stage_after": later,
    }


def capture(frame: Path):
    digest = hashlib.sha256(frame.read_bytes()).hexdigest()
    if digest != FRAME_SHA256:
        raise ValueError(f"source file SHA256 changed: {digest}")
    import netCDF4

    with netCDF4.Dataset(frame) as ds:
        if tuple(len(ds.dimensions[x]) for x in ("bottom_top", "south_north", "west_east")) != (39, 282, 234):
            raise ValueError("source dimensions changed")
        # Candidate selection uses ONLY input state: cold mixed-phase liquid,
        # nonzero paired numbers, land; rank by max(qc*qi), then flat index.
        theta = np.asarray(ds["T"][TIME_INDEX]) + 300.0
        p = np.asarray(ds["P"][TIME_INDEX]) + np.asarray(ds["PB"][TIME_INDEX])
        temp = theta * (p / 1e5) ** (287.0 / 1004.5)
        qc, qi = (np.asarray(ds[name][TIME_INDEX]) for name in ("QCLOUD", "QICE"))
        nc, ni = (np.asarray(ds[name][TIME_INDEX]) for name in ("QNCLOUD", "QNICE"))
        land = np.asarray(ds["XLAND"][TIME_INDEX])
        eligible = ((temp > 245) & (temp < 273.15) & (qc > 1e-6)
                    & (qi > 1e-8) & (nc > 100) & (ni > 0)
                    & (land[None] == 1))
        score = np.where(eligible, qc * qi, 0.0).max(axis=0)
        j, i = np.unravel_index(int(score.argmax()), score.shape)
        if (j, i) != (J, I) or not eligible[K, J, I]:
            raise ValueError(f"input-selected candidate changed: {(j, i)}")
        raw = {name: np.asarray(ds[name][TIME_INDEX, :, J, I], dtype=np.float64).tolist()
               for name in RAW_FIELDS}
    cases = {"baseline": run_profile(raw, controlled=False),
             "diagnostic_control": run_profile(raw, controlled=True)}
    return {
        "schema": "cross-phenomena-phase-profile-v1",
        "scope": "offline_fp64_oracle_on_retained_native_39_level_input",
        "native_host_executed_for_this_capture": False,
        "operational_physics_changed": False,
        "source": {"basename": frame.name, "sha256": digest, "time_index": TIME_INDEX,
                   "input_selection": "land; 245<T<273.15 K; qc>1e-6; qi>1e-8; nc>100; ni>0; max(qc*qi), first flat-index tie"},
        "selected": {"j_zero_based": J, "i_zero_based": I, "k_zero_based": K,
                     "levels": 39, "score": float(score[J, I]),
                     "eligible_columns": int(eligible.any(axis=0).sum())},
        "runtime": {"python": platform.python_version(), "torch": torch.__version__,
                    "numpy": np.__version__, "dt_s": DT},
        "input": {"raw_native_column": raw, "xland": 1.0},
        "cases": cases,
        "accepted_full_energy_or_native_phase_contract": False,
    }


def replay_evidence(data):
    """Re-run the public fp64 profile and reject missing or changed stage values.

    The original NetCDF hash is provenance recorded by capture(), not rehashed
    here. This checks the supplied vectors against the current Python oracle.
    """
    if (data.get("schema") != "cross-phenomena-phase-profile-v1"
            or data.get("scope") != "offline_fp64_oracle_on_retained_native_39_level_input"
            or data.get("native_host_executed_for_this_capture") is not False
            or data.get("operational_physics_changed") is not False
            or data.get("accepted_full_energy_or_native_phase_contract") is not False
            or data.get("source", {}).get("sha256") != FRAME_SHA256
            or data.get("source", {}).get("time_index") != TIME_INDEX
            or data.get("selected", {}).get("j_zero_based") != J
            or data.get("selected", {}).get("i_zero_based") != I
            or data.get("selected", {}).get("k_zero_based") != K
            or data.get("selected", {}).get("levels") != 39
            or data.get("input", {}).get("xland") != 1.0
            or set(data.get("cases", {})) != {"baseline", "diagnostic_control"}):
        raise ValueError("phase-profile identity, scope or case set changed")
    raw = data["input"]["raw_native_column"]
    _state_forcing(raw)
    if not math.isclose(data["selected"]["score"],
                        raw["QCLOUD"][K] * raw["QICE"][K], rel_tol=1e-7):
        raise ValueError("selected input score changed")
    for name, controlled in (("baseline", False), ("diagnostic_control", True)):
        observed = data["cases"][name]
        prior, after, applied = (observed[key] for key in
                                 ("phase_before", "phase_after", "applied"))
        raw_amounts = observed["producer_after_own_caps"]
        factor = observed["control_factor"]
        xlf = observed["consumed_xlf"]
        budget = check_phase_budget(
            {key: np.array([prior[key]]) for key in ("qc", "qi", "qr", "qg")},
            {key: np.array([after[key]]) for key in ("qc", "qi", "qr", "qg")},
            np.array([prior["t"]]), np.array([after["t"]]),
            np.array([observed["consumed_cpm"]]),
            (PhaseTransfer("contact", "qc", "qi",
                           np.array([raw_amounts["pinuc"] * factor]),
                           np.array([applied["pinuc"]]), xlf),
             PhaseTransfer("immersion", "qc", "qi",
                           np.array([raw_amounts["pfrzdtc"] * factor]),
                           np.array([applied["pfrzdtc"]]), xlf),
             PhaseTransfer("rain_freeze", "qr", "qg",
                           np.array([applied["pfrzdtr"]]),
                           np.array([applied["pfrzdtr"]]), xlf)),
        )
        number_applied = applied["ninuc"] + applied["nfrzdtc"]
        if (not math.isclose(prior["nc"] - after["nc"], number_applied,
                             rel_tol=0, abs_tol=1e-6)
                or not math.isclose(after["ni"] - prior["ni"], number_applied,
                                    rel_tol=0, abs_tol=1e-6)):
            raise ValueError(f"{name}: number application changed")
        if (not math.isclose(observed["mass_residual_max"],
                             max(float(np.abs(x).max()) for x in budget.mass_residual.values()),
                             rel_tol=0, abs_tol=1e-15)
                or not math.isclose(observed["heat_residual_j_per_kg"],
                                    float(budget.heat_residual_j_per_kg[0]),
                                    rel_tol=0, abs_tol=1e-10)):
            raise ValueError(f"{name}: reported budget residual changed")
        regenerated = run_profile(raw, controlled=controlled)
        if set(observed) != set(regenerated):
            raise ValueError(f"{name}: incomplete phase-stage evidence")
        if observed["controlled"] is not controlled:
            raise ValueError(f"{name}: control marker changed")
        for section in ("producer_after_own_caps", "applied"):
            if set(observed[section]) != set(regenerated[section]):
                raise ValueError(f"{name}: {section} field set changed")
            for field, value in regenerated[section].items():
                if not math.isclose(observed[section][field], value,
                                    rel_tol=1e-8, abs_tol=1e-20):
                    raise ValueError(f"{name}: {section}.{field} changed")
        for section in ("phase_before", "phase_after"):
            if set(observed[section]) != set(regenerated[section]):
                raise ValueError(f"{name}: {section} field set changed")
            for field, value in regenerated[section].items():
                if not math.isclose(observed[section][field], value,
                                    rel_tol=0, abs_tol=5e-10 if field == "t" else 1e-12):
                    raise ValueError(f"{name}: {section}.{field} changed")
        for field in ("t", "qc", "qi", "qr", "qg"):
            recorded_delta = observed["phase_after"][field] - observed["phase_before"][field]
            regenerated_delta = regenerated["phase_after"][field] - regenerated["phase_before"][field]
            if not math.isclose(recorded_delta, regenerated_delta,
                                rel_tol=1e-6, abs_tol=1e-11 if field == "t" else 1e-15):
                raise ValueError(f"{name}: phase delta {field} changed")
        for field in ("consumed_cpm", "consumed_xlf", "control_factor"):
            if not math.isclose(observed[field], regenerated[field],
                                rel_tol=1e-8, abs_tol=0):
                raise ValueError(f"{name}: {field} changed")
        if observed["control_alpha"] != regenerated["control_alpha"]:
            raise ValueError(f"{name}: control alpha changed")
        if set(observed["later_stage_after"]) != set(regenerated["later_stage_after"]):
            raise ValueError(f"{name}: later stage set changed")
        for stage, fields in regenerated["later_stage_after"].items():
            if set(observed["later_stage_after"][stage]) != set(fields):
                raise ValueError(f"{name}: later stage fields changed")
            for field, value in fields.items():
                if not math.isclose(observed["later_stage_after"][stage][field], value,
                                    rel_tol=0, abs_tol=5e-10 if field == "t" else 1e-12):
                    raise ValueError(f"{name}: {stage}.{field} changed")
    return {"scope": "public_vector_oracle_replay_only", "case_count": 2,
            "native_host_executed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frame", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = capture(args.frame)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
