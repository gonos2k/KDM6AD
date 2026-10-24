"""Saved-data anchors for the unified direction construction and attribution."""

from pathlib import Path
import hashlib
import json

import numpy as np

from harness.run_native_candidate_observation import direction_vectors, EXPERIMENT

ROOT = Path(__file__).resolve().parents[2]
E = ROOT / "harness/evidence/saved_candidate_attribution_2026-10-24"


def test_unified_vectors_preserve_executed_native_direction_and_zero_rest():
    before = json.loads(
        (
            ROOT
            / "harness/evidence/norm_actual_observation_2026-10-24/native13188_cost.json"
        ).read_text()
    )
    executed = json.loads(
        (
            ROOT
            / "harness/evidence/actual_qr_transport_2026-10-24/observation_result.json"
        ).read_text()
    )
    x = np.array(before["prep_X"], dtype=np.float64)
    rest = np.ones((10, 39), dtype=np.float64)
    directions = direction_vectors(x, rest, EXPERIMENT)
    for name, (dx, dr) in directions.items():
        saved = np.array(executed["direction_checks"][name]["direction_x"])
        # Native saved vectors anchor the mathematical direction. A few binary64
        # ulps allow libm/vector-sine portability; physical FD gates are unchanged.
        np.testing.assert_allclose(
            dx, saved, rtol=4 * np.finfo(float).eps, atol=4 * np.finfo(float).eps
        )
        np.testing.assert_array_equal(
            dr, np.array(executed["direction_checks"][name]["rest_direction"])
        )
        assert not dr.any()


def test_historical_manifests_bind_the_executed_snapshots_without_rewrite():
    resolution = json.loads((E / "historical_source_resolution.json").read_text())
    for path, record in resolution["executed_source_snapshots"].items():
        actual = hashlib.sha256((ROOT / record["snapshot"]).read_bytes()).hexdigest()
        assert actual == record["sha256"]
        for name in resolution["immutable_manifests"]:
            manifest = json.loads((ROOT / name).read_text())
            if path in manifest["source_sha256"]:
                assert manifest["source_sha256"][path] == actual


def test_saved_analysis_source_and_artifact_pins():
    manifest = json.loads((E / "manifest.json").read_text())
    assert manifest["new_KDM_calls"] == manifest["new_RTTOV_calls"] == 0
    for group in ["source_sha256", "input_sha256", "artifact_sha256"]:
        assert manifest[group]
        for path, digest in manifest[group].items():
            assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, (
                path
            )
