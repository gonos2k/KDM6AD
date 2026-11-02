"""Source-pinned ice-boundary overlay generation checks; no model execution."""

from __future__ import annotations

import pytest

from harness import make_ice_boundary_overlay as overlay
from harness.historical_ice_sources import checked_factorial_root


def test_exact_source_pins_and_only_copied_tus_are_instrumented():
    root = checked_factorial_root()
    before = {
        name: overlay.sha256(root / "src" / name)
        for name in overlay.SOURCE_PINS
    }
    assert before == overlay.SOURCE_PINS
    runtime = (root / "src/runtime.cpp").read_text()
    coordinator = (root / "src/coordinator.cpp").read_text()
    sedimentation = (root / "src/sedimentation.cpp").read_text()

    runtime_overlay = overlay.instrument_runtime(runtime)
    coordinator_overlay = overlay.instrument_coordinator(coordinator)
    sedimentation_overlay = overlay.instrument_sedimentation(sedimentation)

    assert runtime_overlay == runtime
    assert (
        overlay.MARKER in coordinator_overlay
        and overlay.MARKER in sedimentation_overlay
    )
    assert (
        coordinator_overlay.count('trace_ice_velocity_stage("runtime_input_normalized"')
        == 1
    )
    assert (
        coordinator_overlay.count('trace_ice_velocity_stage("post_main_handoff"') == 1
    )
    assert coordinator_overlay.count("trace_ice_bottom(") == 2  # helper plus call site
    assert (
        sedimentation_overlay.count("trace_ice_layer(") == 3
    )  # helper + top + interior
    assert "torch::NoGradGuard no_grad" in coordinator_overlay
    assert "torch::NoGradGuard no_grad" in sedimentation_overlay
    assert {
        name: overlay.sha256(root / "src" / name)
        for name in overlay.SOURCE_PINS
    } == before


@pytest.mark.parametrize("which", ["coordinator", "sedimentation"])
def test_generator_refuses_already_instrumented_source(which):
    root = checked_factorial_root()
    source = (root / "src" / f"{which}.cpp").read_text()
    if which == "runtime":
        transform = overlay.instrument_runtime
    elif which == "coordinator":
        transform = overlay.instrument_coordinator
    else:
        transform = overlay.instrument_sedimentation
    with pytest.raises(RuntimeError, match="already traced"):
        transform(source + "\n" + overlay.MARKER)


def test_anchor_replacement_requires_exactly_one_match():
    with pytest.raises(RuntimeError, match="found 0"):
        overlay.replace_once("none", "anchor", "new", "test")
    with pytest.raises(RuntimeError, match="found 2"):
        overlay.replace_once("anchor anchor", "anchor", "new", "test")
