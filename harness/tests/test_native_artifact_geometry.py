"""Endpoint regression for the PR389 report-only distance error."""
import hashlib
import importlib.util
import math
import ast
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("geometry_correction", ROOT / "harness/correct_native_artifact_geometry.py")
geometry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(geometry)


def chord_distance(first, second):
    def xyz(point):
        p, l = map(math.radians, point)
        return math.cos(p) * math.cos(l), math.cos(p) * math.sin(l), math.sin(p)
    a, b = xyz(first), xyz(second)
    chord = math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
    return 2 * geometry.EARTH_RADIUS_M * math.asin(chord / 2)


def test_actual_endpoint_correction_preserves_historical_files():
    result = ROOT / "harness/evidence/native358_artifact_diag_2026-10-08/results/native8frame_failed_run_artifact_diagnostic_enriched.json"
    obs = ROOT / "harness/evidence/VIIRS_AMI_candidate_result_2026-10-07.json"
    before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (result, obs)]
    record = geometry.correction_record(result, obs)
    distances = record["corrected_distances"]
    assert distances["ami_center_vs_native_center_distance_m"] == pytest.approx(679.550498963, abs=1e-7)
    assert distances["ami_center_vs_viirs_center_distance_m"] == pytest.approx(686.643622876, abs=1e-7)
    assert distances["native_center_vs_viirs_center_distance_m"] == pytest.approx(7.367358701, abs=1e-7)
    assert record["historical_mislabelled_ami_native_distance_m"] != distances["ami_center_vs_native_center_distance_m"]
    for pair, name in [(('ami', 'native'), 'ami_center_vs_native_center_distance_m'),
                       (('ami', 'viirs'), 'ami_center_vs_viirs_center_distance_m'),
                       (('native', 'viirs'), 'native_center_vs_viirs_center_distance_m')]:
        assert distances[name] == pytest.approx(chord_distance(*(record['endpoints_lat_lon'][k] for k in pair)), abs=1e-7)
    assert before == [hashlib.sha256(p.read_bytes()).hexdigest() for p in (result, obs)]
    assert record["native_run_valid"] is False and record["eligible_for_artifact_gates"] is False


def test_analytic_distance_and_invalid_endpoint():
    assert geometry.spherical_distance_m((0, 0), (0, 0)) == 0
    assert geometry.spherical_distance_m((0, 0), (0, 90)) == pytest.approx(math.pi * geometry.EARTH_RADIUS_M / 2)
    with pytest.raises(ValueError):
        geometry.spherical_distance_m((91, 0), (0, 0))


def test_next_producer_patch_routes_distinct_endpoints(tmp_path):
    original = ROOT / "harness/evidence/native358_artifact_diag_2026-10-08/recipe/run_native_kma_bt_frames.py"
    next_source = tmp_path / original.name
    next_source.write_bytes(original.read_bytes())
    subprocess.run(["git", "apply", str(ROOT / "harness/evidence/NATIVE_geometry_next_producer_2026-10-08.patch")],
                   cwd=tmp_path, check=True)
    tree = ast.parse(next_source.read_text())
    # Evaluate only the producer's endpoint-map expression, not model/RTTOV code.
    calls = [n.value for n in ast.walk(tree) if isinstance(n, ast.keyword)
             and n.arg is None and isinstance(n.value, ast.Call)
             and isinstance(n.value.func, ast.Name) and n.value.func.id == "distance_fields"]
    assert len(calls) == 1
    obs = json.loads((ROOT / "harness/evidence/VIIRS_AMI_candidate_result_2026-10-07.json").read_text())
    actual = eval(compile(ast.Expression(calls[0]), str(next_source), "eval"),
                  {"distance_fields": geometry.distance_fields},
                  {"obs": obs, "frames": [{"native_center_lat_lon": obs["selected_viirs_sample"]["native_lat_lon"]}]})
    assert actual["ami_center_vs_native_center_distance_m"] == pytest.approx(679.550498963, abs=1e-7)
    assert actual["ami_center_vs_viirs_center_distance_m"] == obs["center_distance_from_viirs_m"]


def test_mismatched_endpoint_pair_is_rejected(tmp_path):
    original = ROOT / "harness/evidence/native358_artifact_diag_2026-10-08/results/native8frame_failed_run_artifact_diagnostic_enriched.json"
    result = json.loads(original.read_text())
    result["selected_native_lat_lon"][0] += .1
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(result))
    with pytest.raises(ValueError, match="same selected endpoints"):
        geometry.correction_record(changed, ROOT / "harness/evidence/VIIRS_AMI_candidate_result_2026-10-07.json")


def test_cli_does_not_overwrite_existing_output(tmp_path, monkeypatch):
    output = tmp_path / "existing.json"
    output.write_bytes(b"preserve this result\n")
    import sys
    monkeypatch.setattr(sys, "argv", ["correction", str(ROOT / "harness/evidence/native358_artifact_diag_2026-10-08/results/native8frame_failed_run_artifact_diagnostic_enriched.json"),
                                     str(ROOT / "harness/evidence/VIIRS_AMI_candidate_result_2026-10-07.json"), str(output)])
    with pytest.raises(FileExistsError):
        geometry.main()
    assert output.read_bytes() == b"preserve this result\n"
