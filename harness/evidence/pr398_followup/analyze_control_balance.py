"""Read preserved PR397 controls; no KDM or RTTOV calls, no checkpoint edits."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

FIELDS = ("th", "qv", "qc", "qr", "qi", "qs", "qg", "nccn", "nc", "ni", "nr", "bg")
EXPECTED = "8cfe28df6ef336454cfa595cc70f7a4ddec2e5cd8cbd393c0c7ce8106c904c59"


def summarize(v, g):
    obs = g - v
    nv, no, ng = (float(np.linalg.norm(a)) for a in (v, obs, g))
    return {
        "prior_L2": nv, "observation_L2": no, "total_L2": ng,
        "total_Linf": float(np.max(np.abs(g))),
        "prior_observation_dot": float(np.dot(v.ravel(), obs.ravel())),
        "prior_observation_cosine": None if nv * no == 0 else float(np.dot(v.ravel(), obs.ravel()) / (nv * no)),
        "total_over_prior_L2": None if nv == 0 else ng / nv,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    digest = hashlib.sha256(args.checkpoint.read_bytes()).hexdigest()
    if digest != EXPECTED:
        raise ValueError("Expected immutable PR397 checkpoint")
    with np.load(args.checkpoint, allow_pickle=False) as data:
        v = data["control__optimizer_v_state_control"].copy()
        g = data["control__optimizer_final_gradient_v_state"].copy()
        vt = data["control__optimizer_v_theta_control"].copy()
        gt = data["control__optimizer_final_gradient_v_theta"].copy()
        if v.shape != (12, 1, 39) or g.shape != v.shape:
            raise ValueError("Unexpected State layout")
        combined = np.concatenate((g.ravel(), gt.ravel()))
        np.testing.assert_array_equal(combined, data["control__optimizer_final_gradient_combined"])
        if np.any(vt != 0) or np.any(gt != 0):
            raise ValueError("Physical parameter controls must remain inactive")
        counts = {}
        for i, field in enumerate(FIELDS):
            active = data[f"control__b_sigma__{field}"] != 0
            counts[field] = int(np.count_nonzero(active))
            if np.any(v[i][~active] != 0) or np.any(g[i][~active] != 0):
                raise ValueError(f"Inactive {field} control changed")
        if counts != dict(zip(FIELDS, (39, 12, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0))):
            raise ValueError("Unexpected active controls")
    jb = float(0.5 * np.sum(v * v))
    np.testing.assert_allclose(jb, 0.2284737909127953, rtol=1e-13)
    result = {
        "schema": "pr398.control_balance.v1", "input_sha256": digest,
        "source_receipt": "harness/evidence/pr395_tq_state_capture_2026-10-10/RESULT_3d2e97f159.json",
        "coordinates": "normalized initial State control; lower-native zero-based layers",
        "definition": "g_prior=v; g_observation=g_total-v; complete CVT/M/H chain",
        "KDM_calls": 0, "RTTOV_calls": 0, "Jb": jb, "active_counts": counts,
        "combined": summarize(v, g),
        "blocks": {field: summarize(v[i], g[i]) for i, field in enumerate(FIELDS)},
        "layers": [{"field": field, "layer": k, "prior": float(v[i, 0, k]),
                    "observation": float(g[i, 0, k] - v[i, 0, k]),
                    "total": float(g[i, 0, k])}
                   for i, field in enumerate(FIELDS[:2]) for k in range(39)],
        "fixed_sign_linear_surrogate_decrease": float(0.5 * np.sum(g * g)),
        "limitations": "Surrogate excludes nonlinear curvature/branches; not a nonlinear bound or forecast skill. No raw H adjoint attribution.",
    }
    with args.output.open("x") as out:
        json.dump(result, out, indent=2, allow_nan=False)
        out.write("\n")


if __name__ == "__main__":
    main()
