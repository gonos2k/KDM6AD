from pathlib import Path

import pytest

from harness import make_ice_factorial_overlay as factorial
from harness.make_rain_boundary_overlay import (
    RAIN_COORD_MARKER,
    RAIN_SED_MARKER,
    create_overlay,
    instrument_rain_sedimentation,
    instrument_rain_surface,
    render_factorial_base,
    render_rain_overlay,
)

ROOT = Path(__file__).resolve().parents[2]
V6_OVERLAY = Path(
    "/Users/yhlee/KDM6AD-k/host/research_evidence/"
    "mp137_ice_factorial_20261023/overlay_build_v6/overlay"
)


def test_public_four_source_pins_and_rendered_current_v6_overlay_match():
    rendered = render_factorial_base(ROOT / "libtorch")
    assert set(rendered) == {
        "runtime.cpp",
        "coordinator.cpp",
        "sedimentation.cpp",
        "sedimentation_conservative.cpp",
    }
    assert set(factorial.FACTORIAL_SOURCE_PINS) == set(rendered)
    if not V6_OVERLAY.is_dir():
        pytest.skip("private v6 overlay is not present in this checkout")
    for name, data in rendered.items():
        assert (V6_OVERLAY / name).read_bytes() == data


def test_trace_instrumentation_preserves_all_original_qr_expressions():
    base = render_factorial_base(ROOT / "libtorch")
    original = base["sedimentation.cpp"].decode()
    traced = instrument_rain_sedimentation(original)
    untouched_expressions = (
        "qr_cols[k] = torch::clamp(qr_cols[k] - falk_qr_top * dtcld / dend_safe_col(k), 0.0);",
        "auto dqr_k = torch::minimum(falk_qr_k * dtcld / dend_safe_col(k), qr_cols[k]);",
        "auto dqr_above = torch::minimum(\n"
        "            falk_qr_prev * delz_col(k - 1) / delz_safe_col(k) * dtcld / dend_safe_col(k), qr_cols[k - 1]);",
        "qr_cols[k] = torch::clamp(qr_cols[k] - dqr_k + dqr_above, 0.0);",
    )
    for expression in untouched_expressions:
        assert original.count(expression) == 1
        assert traced.count(expression) == 1

    assert traced.index(untouched_expressions[0]) < traced.index(
        "trace_rain_substep(/*top=*/true"
    )
    assert traced.index(untouched_expressions[3]) < traced.index(
        "trace_rain_substep(/*top=*/false"
    )
    helper = traced.split(RAIN_SED_MARKER, 1)[1].split(
        "// END generated KDM6 rain sedimentation trace", 1
    )[0]
    assert helper.index("torch::NoGradGuard no_grad;") < helper.index(
        "const auto out_attempt = falk_qr * dtcld / dend_safe;"
    )
    assert "dqr_out_min_attempt_before_diagnostic_code" in helper
    assert "QR_realized_before_minus_after_code" in helper
    assert "falk_qr_prev_stored_code" in helper
    assert "QR_above_cap_operand_post_update_code" in helper
    assert "arrival_attempt = torch::zeros_like(out_attempt)" in helper
    assert 'arrival_operand_present=" << (top ? 0 : 1)' in helper


def test_surface_trace_logs_existing_fall_rates_and_returned_surface_values_only():
    base = render_factorial_base(ROOT / "libtorch")
    original = base["coordinator.cpp"].decode()
    traced = instrument_rain_surface(original)
    surface_call = (
        "auto surface = sed::surface_accumulation_torch(\n"
        "        fall_qr_b, fall_qs_b, fall_qg_b, fall_qi_b, delz_b, dtcld\n"
        "    );"
    )
    assert original.count(surface_call) == 1
    assert traced.count(surface_call) == 1
    trace_call = "trace_rain_surface(rain_call_index, dtcld, bottom,"
    assert traced.index(surface_call) < traced.index(trace_call)
    helper = traced.split(RAIN_COORD_MARKER, 1)[1].split(
        "// END generated KDM6 rain surface trace", 1
    )[0]
    for field in (
        "fall_qr_bottom_code",
        "fall_qs_bottom_code",
        "fall_qg_bottom_code",
        "fall_qi_bottom_code",
        "DELZ_bottom_m",
        "surface_total_from_rain_increment_mm",
        "surface_snow_ice_subset_mm",
        "surface_graupel_subset_mm",
    ):
        assert field in helper
    assert "torch::NoGradGuard no_grad;" in helper


def test_generator_copies_runtime_and_conservative_and_only_edits_rain_tus(tmp_path):
    if not V6_OVERLAY.is_dir():
        pytest.skip("private v6 overlay is not present in this checkout")
    output = tmp_path / "rain-overlay"
    manifest = create_overlay(ROOT / "libtorch", V6_OVERLAY, output)
    assert manifest["translation_units_changed_from_base"] == [
        "sedimentation.cpp",
        "coordinator.cpp",
    ]
    assert (output / "runtime.cpp").read_bytes() == (
        V6_OVERLAY / "runtime.cpp"
    ).read_bytes()
    assert (output / "sedimentation_conservative.cpp").read_bytes() == (
        V6_OVERLAY / "sedimentation_conservative.cpp"
    ).read_bytes()
    assert (output / "sedimentation.cpp").read_bytes() != (
        V6_OVERLAY / "sedimentation.cpp"
    ).read_bytes()
    assert (output / "coordinator.cpp").read_bytes() != (
        V6_OVERLAY / "coordinator.cpp"
    ).read_bytes()
    assert (output / "source_sha256.json").is_file()


def test_base_overlay_must_match_factor_generators_and_output_cannot_overlap(tmp_path):
    base = render_factorial_base(ROOT / "libtorch")
    fake_base = tmp_path / "base-overlay"
    fake_base.mkdir()
    for name, data in base.items():
        (fake_base / name).write_bytes(data)
    mutated = fake_base / "sedimentation.cpp"
    mutated.write_bytes(mutated.read_bytes() + b"\n// changed\n")
    with pytest.raises(ValueError, match="differs from current pinned"):
        render_rain_overlay(ROOT / "libtorch", fake_base)

    with pytest.raises(ValueError, match="overlap"):
        create_overlay(ROOT / "libtorch", fake_base, ROOT / "libtorch" / "rain-overlay")


def test_duplicate_rain_instrumentation_anchor_fails_closed():
    base = render_factorial_base(ROOT / "libtorch")
    source = base["sedimentation.cpp"].decode()
    traced = instrument_rain_sedimentation(source)
    with pytest.raises(RuntimeError, match="already has the rain boundary trace"):
        instrument_rain_sedimentation(traced)


def test_ambiguous_rain_qr_update_anchor_fails_closed():
    base = render_factorial_base(ROOT / "libtorch")
    source = base["sedimentation.cpp"].decode()
    anchor = "        qr_cols[k] = torch::clamp(qr_cols[k] - dqr_k + dqr_above, 0.0);\n"
    assert source.count(anchor) == 1
    ambiguous = source.replace(anchor, anchor + anchor)
    with pytest.raises(RuntimeError, match="expected one original interior QR update"):
        instrument_rain_sedimentation(ambiguous)


def test_generator_refuses_existing_and_symlink_outputs(tmp_path):
    if not V6_OVERLAY.is_dir():
        pytest.skip("private v6 overlay is not present in this checkout")
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(ValueError, match="exists or is a symlink"):
        create_overlay(ROOT / "libtorch", V6_OVERLAY, existing)
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "output-link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="exists or is a symlink"):
        create_overlay(ROOT / "libtorch", V6_OVERLAY, link)
