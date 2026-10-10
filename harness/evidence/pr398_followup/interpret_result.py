#!/usr/bin/env python3
"""Create a separate read-only interpretation audit for the executed PR398 run."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from comparison_audit import build_comparison_audit

ROOT = Path(__file__).resolve().parents[3]
RESULT = ROOT / "harness/evidence/pr398_followup/RESULT_PR398_CONVERGENCE_8ITER_20261010.json"
DRIVER = ROOT / "harness/evidence/pr398_followup/DRIVER_PR398_CONVERGENCE_8ITER_20261010.json"
BASELINE_RESULT = ROOT / "harness/evidence/pr395_tq_state_capture_2026-10-10/RESULT_3d2e97f159.json"
BASELINE_DRIVER = ROOT / "harness/evidence/pr395_tq_state_capture_2026-10-10/DRIVER_3d2e97f159.json"
PREFLIGHT = ROOT / (
    "graphify-out/pr398-convergence-8iter-20261010/"
    "run-PR398_CONVERGENCE_8ITER_20261010-sourcechecked7/preflight.json")
OUT = ROOT / "harness/evidence/pr398_followup/POSTRUN_INTERPRETATION.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    if OUT.exists():
        raise FileExistsError(f"interpretation audit already exists: {OUT}")
    result = json.loads(RESULT.read_text())
    driver = json.loads(DRIVER.read_text())
    baseline_result = json.loads(BASELINE_RESULT.read_text())
    baseline_driver = json.loads(BASELINE_DRIVER.read_text())
    preflight = json.loads(PREFLIGHT.read_text())
    source = (ROOT / "oracle/kdm6/da_fulldomain.py").read_text()
    audit = build_comparison_audit(
        result, baseline_result, baseline_driver, preflight, source,
        current_driver_checks=driver.get("checks", {}))
    payload = {
        **audit,
        "experiment_id": "PR398_CONVERGENCE_8ITER_20261010",
        "receipt_hashes": {
            "result_sha256": sha256(RESULT),
            "original_driver_sha256": sha256(DRIVER),
            "private_checkpoint_sha256": result["private_checkpoint"]["sha256"],
            "preflight_sha256": sha256(PREFLIGHT),
            "baseline_result_sha256": sha256(BASELINE_RESULT),
            "baseline_driver_sha256": sha256(BASELINE_DRIVER),
        },
        "saved_endpoint_diagnostic": {
            "path": "harness/evidence/pr398_followup/SAVED_ENDPOINTS.json",
            "sha256": sha256(ROOT / "harness/evidence/pr398_followup/SAVED_ENDPOINTS.json"),
            "additional_model_M_or_H_calls": 0,
        },
        "historical_policy_label": {
            "stored_manifest_token": "pytorch_lbfgs_default_ceil_1.25_max_iter",
            "actual_pinned_torch_behavior": "PyTorch 2.13 sets default max_eval=int(max_iter*1.25); for max_iter=8 this is 10",
            "max_eval_was_explicitly_passed": False,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("x") as stream:
        stream.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    OUT.chmod(0o600)
    print(json.dumps({"status": payload["status"], "output": str(OUT),
                      "sha256": sha256(OUT)}, indent=2))
    return 0 if payload["status"] == "SAME_FIXED_H_INPUTS_PATH_SENSITIVE_RAW_SIGNATURE_DIFFERENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
