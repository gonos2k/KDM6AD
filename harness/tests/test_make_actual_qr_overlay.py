"""Generator tests for the isolated QR-only candidate overlay."""

import json
import hashlib
from pathlib import Path
import shutil

import pytest

from harness.make_actual_qr_overlay import MARKER, create_overlay, render_overlay
from harness.make_rain_boundary_overlay import render_factorial_base
from harness.make_ice_factorial_overlay import FACTORIAL_SOURCE_PINS


ROOT = Path(__file__).resolve().parents[2]
E4_ANCHOR = "// ═══════════════════════════════════════════════════════════════════════════\n// E4: Ice substep\n"


def _copy_pinned_sources(root: Path, destination: Path):
    source_root = destination
    (source_root / "src").mkdir(parents=True)
    for name in FACTORIAL_SOURCE_PINS:
        shutil.copy2(root / "libtorch" / "src" / name, source_root / "src" / name)
    return source_root


def _write_base_overlay(root: Path, destination: Path):
    source_root = _copy_pinned_sources(root, destination.parent / "source")
    destination.mkdir()
    files = render_factorial_base(source_root)
    for name, content in files.items():
        (destination / name).write_bytes(content)
    return files


def test_overlay_changes_only_qr_wrapper_and_preserves_legacy_function_bytes(tmp_path):
    base_dir = tmp_path / "base"
    base = _write_base_overlay(ROOT, base_dir)
    rendered, manifest = render_overlay(tmp_path / "source", base_dir)

    assert set(rendered) == set(base)
    assert {name for name in base if rendered[name] != base[name]} == {
        "sedimentation.cpp"
    }
    assert manifest["changed_translation_units"] == ["sedimentation.cpp"]
    assert manifest["default"] == "legacy"
    assert manifest["required_ice_mode"] == "norm_actual"
    assert manifest["scope"].startswith("QR mass state/fall only")

    base_source = base["sedimentation.cpp"].decode()
    candidate_source = rendered["sedimentation.cpp"].decode()
    legacy_signature = "SubstepAdvectionOutputs substep_advection_torch(\n"
    preserved_signature = "SubstepAdvectionOutputs legacy_main_substep(\n"
    assert base_source.count(legacy_signature) == 1
    assert candidate_source.count(preserved_signature) == 1
    old_function = base_source[
        base_source.index(legacy_signature) : base_source.index(E4_ANCHOR)
    ]
    new_function = candidate_source[
        candidate_source.index(preserved_signature) : candidate_source.index(MARKER)
    ]
    assert (
        new_function.replace("legacy_main_substep", "substep_advection_torch", 1)
        == old_function
    )
    assert candidate_source.count(MARKER) == 1
    assert 'selected == nullptr ? "legacy" : selected' in candidate_source
    assert 'mode == "legacy"' in candidate_source
    assert 'std::string(ice) == "norm_actual"' in candidate_source


def test_create_overlay_writes_new_outputs_and_refuses_existing_or_aliased_paths(
    tmp_path,
):
    base_dir = tmp_path / "base"
    base = _write_base_overlay(ROOT, base_dir)

    output = tmp_path / "overlay"
    manifest = create_overlay(tmp_path / "source", base_dir, output)
    assert set(p.name for p in output.iterdir()) == set(base) | {"source_sha256.json"}
    stored = json.loads((output / "source_sha256.json").read_text())
    assert stored == manifest
    for name, contents in base.items():
        output_bytes = (output / name).read_bytes()
        assert (
            hashlib.sha256(output_bytes).hexdigest() == stored["overlay_sha256"][name]
        )
        assert len(contents) > 0

    sentinel = tmp_path / "already-there"
    sentinel.mkdir()
    marker = sentinel / "owned.txt"
    marker.write_text("preserve this")
    with pytest.raises(ValueError, match="new"):
        create_overlay(tmp_path / "source", base_dir, sentinel)
    assert marker.read_text() == "preserve this"

    with pytest.raises(ValueError, match="overlap"):
        create_overlay(
            tmp_path / "source", base_dir, (tmp_path / "source" / "generated")
        )
    assert not (tmp_path / "source" / "generated").exists()


def test_bad_base_or_source_pin_fails_before_creating_output(tmp_path):
    base_dir = tmp_path / "base"
    source_root = _copy_pinned_sources(ROOT, tmp_path / "source")
    base_dir.mkdir()
    for name, contents in render_factorial_base(source_root).items():
        (base_dir / name).write_bytes(contents)
    bad_base = tmp_path / "bad-base"
    shutil.copytree(base_dir, bad_base)
    changed = bad_base / "sedimentation.cpp"
    changed.write_bytes(changed.read_bytes() + b"\n// tampered\n")
    output = tmp_path / "bad-base-output"
    with pytest.raises(ValueError, match="differs"):
        create_overlay(source_root, bad_base, output)
    assert not output.exists()

    source = source_root / "src" / "sedimentation.cpp"
    source.write_bytes(source.read_bytes() + b"\n// changed public source\n")
    output = tmp_path / "changed-source-output"
    with pytest.raises(ValueError, match="source pin mismatch"):
        create_overlay(source_root, base_dir, output)
    assert not output.exists()
