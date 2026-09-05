"""Focused PR208 regressions for replay identity and artifact migration."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import torch


_ROOT = Path(__file__).resolve().parents[1]


def _load(name, filename):
    path = _ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def replay():
    return _load("review208_replay", "p0_4b1_lc05_replay_audit.py")


@pytest.fixture(scope="module")
def impact():
    return _load("review208_impact", "p0_4b1_impact_comparison.py")


@pytest.fixture(scope="module")
def migration():
    return _load("review208_migration", "p0_4b2_migrate_artifact_schema.py")


def _identity(mod):
    meta = mod._ckpt_meta("traj", "script", "tree")
    prov = {
        "producer_code_sha": "head",
        "script_sha256": "script",
        "kdm6_tree_sha256": "tree",
        "trajectory": mod.FCST,
        "trajectory_sha256": "traj",
        "restore_manifest_sha256": "manifest",
        "torch_version": "torch",
        "python_version": "python",
        "python_optimize": 0,
        "dt": mod.DT,
        "frame_start": 0,
        "frame_stop_exclusive": mod.N_CUM_STEPS,
        "endpoint_frame": 36,
        "xland_used": True,
        "ncmin_land": mod.NCMIN_LAND,
        "ncmin_sea": mod.NCMIN_SEA,
        "n_shards": 16,
    }
    return meta, prov


def _checkpoint(mod, meta, prov):
    stored = dict(prov)
    return {
        "meta": meta,
        "provenance": stored,
        "frames": [{"frame": 0,
                    "sink_sum_of_column_equivalents_kg_m2": 1.0,
                    "affected_fraction": 0.5}],
        "cum36_sink": torch.ones(4, dtype=torch.float64),
        "cum36_species": {sp: 1.0 for sp in mod.SPECIES},
        "cum36_proj": 1.0,
    }


@pytest.mark.parametrize("mutate", [
    "frame_sink", "frame_fraction", "tensor", "species", "projection",
])
def test_review208_replay_rejects_nonfinite_checkpoint_payload(replay, mutate):
    meta, prov = _identity(replay)
    ck = _checkpoint(replay, meta, prov)
    if mutate == "frame_sink":
        ck["frames"][0]["sink_sum_of_column_equivalents_kg_m2"] = float("nan")
    elif mutate == "frame_fraction":
        ck["frames"][0]["affected_fraction"] = float("inf")
    elif mutate == "tensor":
        ck["cum36_sink"][0] = float("nan")
    elif mutate == "species":
        ck["cum36_species"]["qr"] = float("inf")
    else:
        ck["cum36_proj"] = float("nan")
    with pytest.raises(RuntimeError, match="refusing to resume"):
        replay._validate_resume(ck, meta, prov, n_columns=4)


def test_review208_replay_pressure_is_explicit_value_error_even_for_bad_order(replay):
    p = torch.tensor([[100.0, 200.0], [100.0, 50.0]], dtype=torch.float64)
    with pytest.raises(ValueError, match="K-order mismatch"):
        replay._validate_top_first_pressure(p)
    with pytest.raises(ValueError, match="must be finite"):
        replay._validate_top_first_pressure(
            torch.tensor([[100.0, float("nan")]], dtype=torch.float64))
    assert replay._ckpt_meta("a", "b", "c")["python_optimize"] >= 0


def test_review208_replay_end_identity_detects_source_or_input_drift(replay, monkeypatch, tmp_path):
    trajectory = tmp_path / "trajectory"
    manifest = tmp_path / "manifest"
    trajectory.write_bytes(b"trajectory-v1")
    manifest.write_bytes(b"manifest-v1")
    monkeypatch.setattr(replay, "FCST", str(trajectory))
    monkeypatch.setattr(replay, "MANIFEST", str(manifest))
    prov = {
        "trajectory_sha256": replay._sha256(trajectory),
        "restore_manifest_sha256": replay._sha256(manifest),
        "script_sha256": replay._sha256(replay.__file__),
        "kdm6_tree_sha256": replay._kdm6_tree_sha256(),
    }
    assert replay._end_identity_check(prov)["ok"]
    trajectory.write_bytes(b"trajectory-v2")
    check = replay._end_identity_check(prov)
    assert not check["ok"] and "trajectory_sha256" in check["mismatches"]


def test_review208_impact_end_identity_covers_synthetic_source_tree(impact, monkeypatch):
    prov = impact.provenance(include_trajectory=False)
    assert impact._end_identity_check(prov)["ok"]
    monkeypatch.setattr(impact, "_kdm6_tree_sha256", lambda: "changed-tree")
    check = impact._end_identity_check(prov)
    assert not check["ok"] and "kdm6_tree_sha256" in check["mismatches"]


@pytest.mark.parametrize("payload,renames", [
    ({"legacy": 1, "new": 2}, {"legacy": "new"}),
    ({"domain_sum_kg_m2": 1, "sum_of_column_equivalents_kg_m2": 2},
     {"domain_sum_kg_m2": "sum_of_column_equivalents_kg_m2"}),
])
def test_review208_migration_rejects_key_collision(migration, payload, renames):
    with pytest.raises(ValueError, match="both keys already exist"):
        migration._rename(payload, renames)


def test_review208_migration_renames_clean_legacy_value(migration):
    payload = {"code_sha": "abc"}
    assert migration._rename(payload, {"code_sha": "producer_code_sha"})
    assert payload == {"producer_code_sha": "abc"}


def test_review208_migration_collision_does_not_partially_mutate(migration):
    payload = {"legacy_a": 1, "legacy_b": 2, "new_b": 3}
    with pytest.raises(ValueError, match="both keys already exist"):
        migration._rename(payload, {
            "legacy_a": "new_a", "legacy_b": "new_b",
        })
    assert payload == {"legacy_a": 1, "legacy_b": 2, "new_b": 3}
