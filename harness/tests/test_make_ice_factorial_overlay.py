"""Source-generation checks for the private ice-only 2x2 instrumentation."""

from pathlib import Path

import pytest

from harness import make_ice_boundary_overlay as base
from harness import make_ice_factorial_overlay as overlay


def test_factorial_modes_keep_main_chain_legacy_and_trace_three_stages():
    root = Path(__file__).parents[2]
    source_paths = {
        name: root / "libtorch/src" / name for name in overlay.FACTORIAL_SOURCE_PINS
    }
    assert {
        name: base.sha256(path) for name, path in source_paths.items()
    } == overlay.FACTORIAL_SOURCE_PINS

    coordinator = overlay.instrument_factor_coordinator(
        source_paths["coordinator.cpp"].read_text()
    )
    runtime = overlay.instrument_factor_runtime(source_paths["runtime.cpp"].read_text())
    conservative = overlay.instrument_factor_conservative_sedimentation(
        source_paths["sedimentation_conservative.cpp"].read_text()
    )
    legacy = overlay.instrument_factor_legacy_sedimentation(
        source_paths["sedimentation.cpp"].read_text()
    )

    assert "const MainSubstepFn main_substep_fn =" in coordinator
    assert "conservative ? sed::substep_advection_conservative" in coordinator
    assert 'ice_factor_mode != "legacy"' in coordinator
    assert "variant == PhysicsVariant::Legacy" in coordinator
    assert 'ice_factor_mode == "raw_cap"' in coordinator
    assert 'ice_factor_mode == "norm_cap"' in coordinator
    assert 'ice_factor_mode == "raw_actual"' in coordinator
    assert 'ice_factor_mode == "norm_actual"' in coordinator
    assert "normalize_ice_handoff || ice_factor_normalize_first" in coordinator
    assert "ice_factor_actual_departure" in coordinator
    assert runtime.count('trace_factorial_water_stage("pre_sed"') == 1
    assert runtime.count('trace_factorial_water_stage("post_sed"') == 1
    assert runtime.count('trace_factorial_water_stage("post_micro"') == 1
    assert "level_bottom0=" in runtime
    assert "std::setprecision(17)" in runtime
    assert "torch::NoGradGuard no_grad" in runtime
    assert "main_substep_fn(" in coordinator
    assert "out_applied_qi" in conservative
    assert "arrival_applied_qi" in conservative
    assert "falk_qi_code_value" in conservative
    assert "dqi_in = prev_out_qi" in conservative
    assert '" factor_mode=" << mode << " recurrence=legacy_stored_falk"' in legacy


def test_factorial_generators_fail_closed_on_source_or_anchor_drift():
    root = Path(__file__).parents[2]
    coordinator = (root / "libtorch/src/coordinator.cpp").read_text()
    runtime = (root / "libtorch/src/runtime.cpp").read_text()
    with pytest.raises(RuntimeError, match="already has the factorial mode selector"):
        overlay.instrument_factor_coordinator(coordinator + "\n" + overlay.MODE_MARKER)
    with pytest.raises(RuntimeError, match="already has factorial water tracing"):
        overlay.instrument_factor_runtime(runtime + "\n" + overlay.WATER_MARKER)
    with pytest.raises(RuntimeError, match="expected exactly one"):
        overlay.base.replace_once("anchor anchor", "anchor", "new", "test")
