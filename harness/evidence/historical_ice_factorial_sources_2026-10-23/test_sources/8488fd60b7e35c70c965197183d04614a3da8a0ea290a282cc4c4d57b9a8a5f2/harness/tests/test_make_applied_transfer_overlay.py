"""Generator contract for the value-only applied-transfer observer overlay."""

import difflib
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from harness import make_actual_qr_overlay
from harness.make_applied_transfer_overlay import (
    MARKER,
    TUS,
    create_overlay,
    render_overlay,
)
from harness.make_ice_factorial_overlay import FACTORIAL_SOURCE_PINS
from harness.make_rain_boundary_overlay import render_factorial_base


ROOT = Path(__file__).resolve().parents[2]


def _write_overlay(path: Path, sources: dict[str, bytes]):
    path.mkdir()
    for name, content in sources.items():
        (path / name).write_bytes(content)


def _fixtures(tmp_path: Path):
    source_root = tmp_path / "source"
    (source_root / "src").mkdir(parents=True)
    for name in FACTORIAL_SOURCE_PINS:
        shutil.copy2(ROOT / "libtorch" / "src" / name, source_root / "src" / name)

    factorial_base = tmp_path / "factorial_base"
    factorial_sources = render_factorial_base(source_root)
    _write_overlay(factorial_base, factorial_sources)

    actual_sources, _ = make_actual_qr_overlay.render_overlay(
        source_root, factorial_base
    )
    actual_base = tmp_path / "actual_base"
    _write_overlay(actual_base, actual_sources)
    return source_root, factorial_base, actual_base, actual_sources


def _assert_insertion_only(before: str, after: str):
    matcher = difflib.SequenceMatcher(
        a=before.splitlines(keepends=True),
        b=after.splitlines(keepends=True),
        autojunk=False,
    )
    edits = [opcode for opcode in matcher.get_opcodes() if opcode[0] != "equal"]
    assert edits
    assert all(tag == "insert" for tag, *_ in edits), edits[:8]


def test_render_instruments_only_coordinator_and_preserves_all_base_lines(tmp_path):
    source_root, factorial_base, actual_base, actual_sources = _fixtures(tmp_path)
    rendered, manifest = render_overlay(source_root, factorial_base, actual_base)

    assert set(rendered) == set(TUS)
    assert {name for name in TUS if rendered[name] != actual_sources[name]} == {
        "coordinator.cpp"
    }
    assert manifest["changed_TUs"] == ["coordinator.cpp"]
    assert manifest["physics_changed"] is False
    assert manifest["targets"] == {
        "34": {"column": 281, "levels_bottom0": [17, 18]},
        "40": {"column": 250, "levels_bottom0": [17]},
    }
    assert "no uncapped C4/D2-D3 attempt attribution" in manifest["scope"]

    before = actual_sources["coordinator.cpp"].decode()
    after = rendered["coordinator.cpp"].decode()
    _assert_insertion_only(before, after)
    assert after.count(MARKER) == 1
    assert "applied_transfer_begin();" in after
    assert 'trace_applied_transfer("micro_entry"' in after
    assert 'trace_applied_transfer("pre_limits"' in after
    assert 'trace_applied_transfer("post_limits"' in after
    assert 'trace_applied_transfer("state_update_raw"' in after
    assert 'trace_applied_transfer("post_threshold"' in after
    assert 'trace_applied_transfer("micro_exit"' in after


@pytest.mark.parametrize("base_kind", ["factorial", "actual"])
def test_wrong_base_overlay_is_refused_before_output_creation(tmp_path, base_kind):
    source_root, factorial_base, actual_base, _ = _fixtures(tmp_path)
    bad_factorial = tmp_path / "bad_factorial"
    bad_actual = tmp_path / "bad_actual"
    shutil.copytree(factorial_base, bad_factorial)
    shutil.copytree(actual_base, bad_actual)
    target = bad_factorial if base_kind == "factorial" else bad_actual
    file = target / "coordinator.cpp"
    file.write_bytes(file.read_bytes() + b"\n// corrupted fixture\n")
    output = tmp_path / f"out_bad_{base_kind}"

    with pytest.raises(
        ValueError,
        match="differs|current pinned factorial rendering|actual base",
    ):
        create_overlay(source_root, bad_factorial, bad_actual, output)
    assert not output.exists()


def test_create_writes_new_four_tu_overlay_and_refuses_existing_output(tmp_path):
    source_root, factorial_base, actual_base, actual_sources = _fixtures(tmp_path)
    output = tmp_path / "applied_overlay"
    manifest = create_overlay(source_root, factorial_base, actual_base, output)

    assert set(path.name for path in output.iterdir()) == set(TUS) | {
        "source_sha256.json"
    }
    saved = json.loads((output / "source_sha256.json").read_text())
    assert saved == manifest
    for name in TUS:
        content = (output / name).read_bytes()
        assert hashlib.sha256(content).hexdigest() == manifest["overlay_sha256"][name]
        if name != "coordinator.cpp":
            assert content == actual_sources[name]

    sentinel = tmp_path / "already_exists"
    sentinel.mkdir()
    marker = sentinel / "owner.txt"
    marker.write_text("keep")
    with pytest.raises(ValueError, match="new"):
        create_overlay(source_root, factorial_base, actual_base, sentinel)
    assert marker.read_text() == "keep"


def test_symlink_output_and_input_tree_overlap_are_refused_without_writes(tmp_path):
    source_root, factorial_base, actual_base, _ = _fixtures(tmp_path)
    target = tmp_path / "symlink_target"
    target.mkdir()
    link = tmp_path / "out_link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="new"):
        create_overlay(source_root, factorial_base, actual_base, link)
    assert list(target.iterdir()) == []

    source_alias = source_root / "generated"
    with pytest.raises(ValueError, match="overlaps"):
        create_overlay(source_root, factorial_base, actual_base, source_alias)
    assert not source_alias.exists()

    base_alias = actual_base / "generated"
    with pytest.raises(ValueError, match="overlaps"):
        create_overlay(source_root, factorial_base, actual_base, base_alias)
    assert not base_alias.exists()


def test_pinned_public_source_mismatch_is_refused_before_output_creation(tmp_path):
    source_root, factorial_base, actual_base, _ = _fixtures(tmp_path)
    changed = source_root / "src" / "coordinator.cpp"
    changed.write_bytes(changed.read_bytes() + b"\n// changed pinned source\n")
    output = tmp_path / "changed_source_out"
    with pytest.raises(ValueError, match="source pin mismatch"):
        create_overlay(source_root, factorial_base, actual_base, output)
    assert not output.exists()
