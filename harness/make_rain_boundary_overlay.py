"""Create a private, value-only rain-sedimentation trace over frozen v6 sources.

The supplied base overlay must be byte-identical to rendering the current
factorial source generators from their pinned public sources. This overlay
adds rain QR traces to the Legacy main substep and surface return only; it does
not alter runtime.cpp, conservative ice sedimentation, or any physics formula.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from harness import make_ice_factorial_overlay as factorial

RAIN_TRACE_ENV = "KDM6_RAIN_BOUNDARY_TRACE"
RAIN_SED_MARKER = "// BEGIN generated KDM6 rain sedimentation trace"
RAIN_COORD_MARKER = "// BEGIN generated KDM6 rain surface trace"
TUS = (
    "runtime.cpp",
    "coordinator.cpp",
    "sedimentation.cpp",
    "sedimentation_conservative.cpp",
)

RAIN_SED_HELPER = r"""// BEGIN generated KDM6 rain sedimentation trace
bool rain_boundary_trace_enabled() {
    const char* path = std::getenv("KDM6_RAIN_BOUNDARY_TRACE");
    return path != nullptr && *path != '\0';
}

std::atomic<std::uint64_t> next_rain_trace_call_index{0};
thread_local std::int64_t active_rain_trace_call_index = -1;

void trace_rain_substep(
    bool top, std::int64_t k, int n, double dtcld,
    const torch::Tensor& mstep, const torch::Tensor& gate,
    const torch::Tensor& dend, const torch::Tensor& dend_safe,
    const torch::Tensor& delz, const torch::Tensor& delz_safe,
    const torch::Tensor& delz_prev,
    const torch::Tensor& work1_qr, const torch::Tensor& workn_qr,
    const torch::Tensor& qr_before, const torch::Tensor& qr_above_cap,
    const torch::Tensor& falk_qr, const torch::Tensor& falk_qr_prev,
    const torch::Tensor& dqr_k, const torch::Tensor& dqr_above,
    const torch::Tensor& fall_qr_before, const torch::Tensor& fall_qr_after,
    const torch::Tensor& qr_after) {
    if (!rain_boundary_trace_enabled()) return;
    torch::NoGradGuard no_grad;
    const torch::Tensor* inputs[] = {&mstep, &gate, &dend, &dend_safe,
        &delz, &delz_safe, &delz_prev, &work1_qr, &workn_qr, &qr_before,
        &qr_above_cap, &falk_qr, &falk_qr_prev, &dqr_k, &dqr_above,
        &fall_qr_before, &fall_qr_after, &qr_after};
    for (const auto* tensor : inputs) {
        TORCH_CHECK(tensor->scalar_type() == torch::kFloat64 &&
                    tensor->dim() == 1 && tensor->numel() == qr_before.numel(),
                    "rain layer trace requires matching binary64 column vectors");
    }
    const auto out_attempt = falk_qr * dtcld / dend_safe;
    const auto out_min_attempt_before = torch::minimum(out_attempt, qr_before);
    torch::Tensor arrival_attempt;
    torch::Tensor arrival_min_attempt_above;
    if (top) {
        arrival_attempt = torch::zeros_like(out_attempt);
        arrival_min_attempt_above = torch::zeros_like(out_attempt);
    } else {
        // Reconstruct only under NoGradGuard; preserve the source expression's
        // left-to-right multiply/divide order and label it as a trace value.
        arrival_attempt = falk_qr_prev * delz_prev / delz_safe * dtcld / dend_safe;
        arrival_min_attempt_above = torch::minimum(arrival_attempt, qr_above_cap);
    }
    const char* mode_env = std::getenv("KDM6_ICE_FACTORIAL_MODE");
    const char* mode = (mode_env == nullptr || *mode_env == '\0') ? "legacy" : mode_env;
    const char* path = std::getenv("KDM6_RAIN_BOUNDARY_TRACE");
    std::ofstream out(std::string(path) + ".qr.tsv", std::ios::out | std::ios::app);
    TORCH_CHECK(out.good(), "cannot append rain sedimentation trace: ", path, ".qr.tsv");
    out.imbue(std::locale::classic());
    out << std::setprecision(17);
    for (int64_t b = 0; b < qr_before.size(0); ++b) {
        auto value = [b](const torch::Tensor& t) { return t.select(0, b).item<double>(); };
        double above_attempt = 0.0;
        double above_min_attempt = 0.0;
        double above_falk = 0.0;
        double above_cap = 0.0;
        double applied_arrival = 0.0;
        double delz_above = 0.0;
        if (!top) {
            delz_above = value(delz_prev);
            above_falk = value(falk_qr_prev);
            above_cap = value(qr_above_cap);
            // These expressions are formed after branch selection to avoid
            // indexing k-1 for the top layer. The actual `dqr_above` operand
            // is the source tensor passed directly from the kernel.
            above_attempt = value(arrival_attempt);
            above_min_attempt = value(arrival_min_attempt_above);
            applied_arrival = value(dqr_above);
        }
        out << "schema=kdm6.rain_boundary.v1 record=qr_layer"
            << " factor_mode=" << mode
            << " call_index=" << active_rain_trace_call_index
            << " n=" << n << " dtcld_s=" << dtcld
            << " column=" << b << " level_top0=" << k
            << " top=" << (top ? 1 : 0)
            << " mstep=" << value(mstep) << " gate=" << value(gate)
            << " DEND_code=" << value(dend) << " DEND_safe_code=" << value(dend_safe)
            << " DELZ_code=" << value(delz) << " DELZ_safe_code=" << value(delz_safe)
            << " DELZ_above_code=" << delz_above
            << " work1_qr_code=" << value(work1_qr) << " workn_qr_code=" << value(workn_qr)
            << " QR_before_code=" << value(qr_before)
            << " falk_qr_stored_code=" << value(falk_qr)
            << " falk_qr_prev_stored_code=" << above_falk
            << " QR_out_cap_operand_code=" << value(qr_before)
            << " QR_above_cap_operand_post_update_code=" << above_cap
            << " dqr_out_attempt_reconstructed_code=" << value(out_attempt)
            << " dqr_out_min_attempt_before_diagnostic_code=" << value(out_min_attempt_before)
            << " dqr_out_applied_operand_code=" << (top ? 0.0 : value(dqr_k))
            << " dqr_out_operand_present=" << (top ? 0 : 1)
            << " dqr_arrival_attempt_reconstructed_code=" << above_attempt
            << " dqr_arrival_min_attempt_above_diagnostic_code=" << above_min_attempt
            << " dqr_arrival_applied_operand_code=" << applied_arrival
            << " arrival_operand_present=" << (top ? 0 : 1)
            << " QR_realized_before_minus_after_code=" << value(qr_before) - value(qr_after)
            << " QR_after_code=" << value(qr_after)
            << " fall_qr_accum_before_code=" << value(fall_qr_before)
            << " fall_qr_accum_after_code=" << value(fall_qr_after)
            << '\n';
    }
    TORCH_CHECK(out.good(), "failed writing rain sedimentation trace");
}
// END generated KDM6 rain sedimentation trace
"""

RAIN_COORD_HELPER = r"""// BEGIN generated KDM6 rain surface trace
bool rain_surface_trace_enabled() {
    const char* path = std::getenv("KDM6_RAIN_BOUNDARY_TRACE");
    return path != nullptr && *path != '\0';
}

void trace_rain_surface(
    std::int64_t call_index, double dtcld, int64_t bottom_top0,
    const torch::Tensor& fall_qr_bottom,
    const torch::Tensor& fall_qs_bottom,
    const torch::Tensor& fall_qg_bottom,
    const torch::Tensor& fall_qi_bottom,
    const torch::Tensor& delz_bottom,
    const torch::Tensor& total_mm,
    const torch::Tensor& snow_ice_mm,
    const torch::Tensor& graupel_mm) {
    if (!rain_surface_trace_enabled()) return;
    torch::NoGradGuard no_grad;
    const torch::Tensor* tensors[] = {&fall_qr_bottom, &fall_qs_bottom,
        &fall_qg_bottom, &fall_qi_bottom, &delz_bottom, &total_mm,
        &snow_ice_mm, &graupel_mm};
    for (const auto* t : tensors) {
        TORCH_CHECK(t->scalar_type() == torch::kFloat64,
                    "rain surface trace requires binary64 tensors");
    }
    const char* mode_env = std::getenv("KDM6_ICE_FACTORIAL_MODE");
    const char* mode = (mode_env == nullptr || *mode_env == '\0') ? "legacy" : mode_env;
    const char* path = std::getenv("KDM6_RAIN_BOUNDARY_TRACE");
    std::ofstream out(std::string(path) + ".surface.tsv", std::ios::out | std::ios::app);
    TORCH_CHECK(out.good(), "cannot append rain surface trace: ", path, ".surface.tsv");
    out.imbue(std::locale::classic());
    out << std::setprecision(17);
    for (int64_t b = 0; b < total_mm.numel(); ++b) {
        auto value = [b](const torch::Tensor& t) { return t.reshape({-1}).select(0, b).item<double>(); };
        out << "schema=kdm6.rain_boundary.v1 record=surface"
            << " factor_mode=" << mode << " call_index=" << call_index
            << " column=" << b << " bottom_level_top0=" << bottom_top0
            << " dtcld_s=" << dtcld
            << " fall_qr_bottom_code=" << value(fall_qr_bottom)
            << " fall_qs_bottom_code=" << value(fall_qs_bottom)
            << " fall_qg_bottom_code=" << value(fall_qg_bottom)
            << " fall_qi_bottom_code=" << value(fall_qi_bottom)
            << " DELZ_bottom_m=" << value(delz_bottom)
            << " DENR_surface_constant=" << constants::DENR
            << " surface_total_from_rain_increment_mm=" << value(total_mm)
            << " surface_snow_ice_subset_mm=" << value(snow_ice_mm)
            << " surface_graupel_subset_mm=" << value(graupel_mm) << '\n';
    }
    TORCH_CHECK(out.good(), "failed writing rain surface trace");
}
// END generated KDM6 rain surface trace
"""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"expected one {label} anchor, found {count}")
    return source.replace(old, new, 1)


def render_factorial_base(source_root: Path) -> dict[str, bytes]:
    source_root = Path(source_root).resolve()
    source_text = {}
    for name, expected_sha in factorial.FACTORIAL_SOURCE_PINS.items():
        path = source_root / "src" / name
        if not path.is_file():
            raise ValueError(f"missing pinned public source: {path}")
        raw = path.read_bytes()
        actual = sha256_bytes(raw)
        if actual != expected_sha:
            raise ValueError(
                f"source pin mismatch for {name}: expected {expected_sha}, got {actual}"
            )
        source_text[name] = raw.decode()
    return {
        "runtime.cpp": factorial.instrument_factor_runtime(
            source_text["runtime.cpp"]
        ).encode(),
        "coordinator.cpp": factorial.instrument_factor_coordinator(
            source_text["coordinator.cpp"]
        ).encode(),
        "sedimentation.cpp": factorial.instrument_factor_legacy_sedimentation(
            source_text["sedimentation.cpp"]
        ).encode(),
        "sedimentation_conservative.cpp": factorial.instrument_factor_conservative_sedimentation(
            source_text["sedimentation_conservative.cpp"]
        ).encode(),
    }


def validate_base_overlay(source_root: Path, base_overlay: Path) -> dict[str, bytes]:
    expected = render_factorial_base(source_root)
    base_overlay = Path(base_overlay).resolve()
    for name, rendered in expected.items():
        path = base_overlay / name
        if not path.is_file():
            raise ValueError(f"missing base overlay translation unit: {path}")
        actual = path.read_bytes()
        if actual != rendered:
            raise ValueError(
                f"supplied base overlay differs from current pinned factorial rendering: {name}"
            )
    return expected


def instrument_rain_sedimentation(source: str) -> str:
    if RAIN_SED_MARKER in source:
        raise RuntimeError("sedimentation source already has the rain boundary trace")
    source = replace_once(
        source,
        "#include <algorithm>\n",
        "#include <algorithm>\n#include <atomic>\n#include <cstdint>\n",
        "rain trace counter includes",
    )
    source = replace_once(
        source,
        "}  // namespace\n\nSubstepAdvectionOutputs substep_advection_torch(",
        RAIN_SED_HELPER + "\n}  // namespace\n\n"
        "std::int64_t begin_rain_boundary_call() {\n"
        "    if (!rain_boundary_trace_enabled()) {\n"
        "        active_rain_trace_call_index = -1;\n"
        "        return -1;\n"
        "    }\n"
        "    active_rain_trace_call_index = static_cast<std::int64_t>(\n"
        "        next_rain_trace_call_index.fetch_add(1, std::memory_order_relaxed));\n"
        "    return active_rain_trace_call_index;\n"
        "}\n"
        "SubstepAdvectionOutputs substep_advection_torch(",
        "rain trace helper and call-index hooks",
    )

    top_anchor = (
        "        const int64_t k = 0;\n"
        "        // §34: falk REAL(f32) — one f32 rounding of the f64 chain (work1 f64 via vt f64), mirror ice path.\n"
    )
    source = replace_once(
        source,
        top_anchor,
        "        const int64_t k = 0;\n"
        "        const auto qr_top_before = qr_cols[k];\n"
        "        const auto fall_qr_top_before = fall_qr_cols[k];\n"
        "        // §34: falk REAL(f32) — one f32 rounding of the f64 chain (work1 f64 via vt f64), mirror ice path.\n",
        "rain top before snapshots",
    )
    top_update = "        qr_cols[k] = torch::clamp(qr_cols[k] - falk_qr_top * dtcld / dend_safe_col(k), 0.0);\n"
    if source.count(top_update) != 1:
        raise RuntimeError(
            f"expected one original top QR update, found {source.count(top_update)}"
        )
    source = replace_once(
        source,
        top_update,
        top_update
        + "        trace_rain_substep(/*top=*/true, k, n, dtcld, mstep_col_safe, gate_col,\n"
        "            dend_col(k), dend_safe_col(k), delz_col(k), delz_safe_col(k), delz_col(k),\n"
        "            work1_qr_col(k), workn_qr_col(k), qr_top_before, qr_top_before,\n"
        "            falk_qr_top, falk_qr_top, qr_top_before, qr_top_before,\n"
        "            fall_qr_top_before, fall_qr_cols[k], qr_cols[k]);\n",
        "rain top trace call",
    )

    interior_anchor = "    for (int64_t k = 1; k < K; ++k) {\n        auto falk_qr_k ="
    source = replace_once(
        source,
        interior_anchor,
        "    for (int64_t k = 1; k < K; ++k) {\n"
        "        const auto qr_before_k = qr_cols[k];\n"
        "        const auto qr_above_cap_post_update = qr_cols[k - 1];\n"
        "        const auto fall_qr_k_before = fall_qr_cols[k];\n"
        "        auto falk_qr_k =",
        "rain interior before snapshots",
    )
    interior_update = (
        "        qr_cols[k] = torch::clamp(qr_cols[k] - dqr_k + dqr_above, 0.0);\n"
    )
    if source.count(interior_update) != 1:
        raise RuntimeError(
            f"expected one original interior QR update, found {source.count(interior_update)}"
        )
    source = replace_once(
        source,
        interior_update,
        interior_update
        + "        trace_rain_substep(/*top=*/false, k, n, dtcld, mstep_col_safe, gate_col,\n"
        "            dend_col(k), dend_safe_col(k), delz_col(k), delz_safe_col(k), delz_col(k - 1),\n"
        "            work1_qr_col(k), workn_qr_col(k), qr_before_k, qr_above_cap_post_update,\n"
        "            falk_qr_k, falk_qr_prev, dqr_k, dqr_above,\n"
        "            fall_qr_k_before, fall_qr_cols[k], qr_cols[k]);\n",
        "rain interior trace call",
    )
    return source


def instrument_rain_surface(source: str) -> str:
    if RAIN_COORD_MARKER in source:
        raise RuntimeError("coordinator source already has the rain boundary trace")
    source = replace_once(
        source,
        "namespace kdm6 {\n\nnamespace {\n",
        "namespace kdm6 {\n\nnamespace sed {\nstd::int64_t begin_rain_boundary_call();\n}\n\nnamespace {\n"
        + RAIN_COORD_HELPER
        + "\n",
        "rain surface trace helper",
    )
    call_anchor = "    const int64_t K = state.qr.size(-1);\n"
    source = replace_once(
        source,
        call_anchor,
        call_anchor
        + "    const std::int64_t rain_call_index = sed::begin_rain_boundary_call();\n",
        "rain trace call index",
    )
    surface_anchor = (
        "    auto surface = sed::surface_accumulation_torch(\n"
        "        fall_qr_b, fall_qs_b, fall_qg_b, fall_qi_b, delz_b, dtcld\n"
        "    );\n"
    )
    source = replace_once(
        source,
        surface_anchor,
        surface_anchor + "    trace_rain_surface(rain_call_index, dtcld, bottom,\n"
        "        fall_qr_b, fall_qs_b, fall_qg_b, fall_qi_b, delz_b,\n"
        "        surface.rain_increment, surface.snow_increment, surface.graupel_increment);\n",
        "rain surface trace call",
    )
    return source


def render_rain_overlay(
    source_root: Path, base_overlay: Path
) -> tuple[dict[str, bytes], dict]:
    base_bytes = validate_base_overlay(source_root, base_overlay)
    rendered = dict(base_bytes)
    rendered["sedimentation.cpp"] = instrument_rain_sedimentation(
        base_bytes["sedimentation.cpp"].decode()
    ).encode()
    rendered["coordinator.cpp"] = instrument_rain_surface(
        base_bytes["coordinator.cpp"].decode()
    ).encode()
    manifest = {
        "schema": "kdm6.rain_boundary_overlay.v1",
        "generator_sha256": sha256_bytes(Path(__file__).read_bytes()),
        "factorial_generator_sha256": sha256_bytes(
            Path(factorial.__file__).read_bytes()
        ),
        "base_generator_sha256": sha256_bytes(
            Path(factorial.base.__file__).read_bytes()
        ),
        "physics_map_changed": False,
        "source_root": str(Path(source_root).resolve()),
        "source_pins": dict(factorial.FACTORIAL_SOURCE_PINS),
        "base_overlay": str(Path(base_overlay).resolve()),
        "base_overlay_sha256": {
            name: sha256_bytes(data) for name, data in base_bytes.items()
        },
        "overlay_sha256": {name: sha256_bytes(data) for name, data in rendered.items()},
        "trace_environment_variable": RAIN_TRACE_ENV,
        "record_schemas": ["kdm6.rain_boundary.v1"],
        "translation_units_changed_from_base": ["sedimentation.cpp", "coordinator.cpp"],
        "translation_units_identical_to_base": [
            "runtime.cpp",
            "sedimentation_conservative.cpp",
        ],
        "operation_contract": "original QR arithmetic expressions and order retained; attempts reconstructed only under helper-local NoGradGuard; dqr_k/dqr_above captured from original operands",
    }
    return rendered, manifest


def paths_overlap(left: Path, right: Path) -> bool:
    left, right = left.resolve(), right.resolve()
    return left == right or left in right.parents or right in left.parents


def create_overlay(source_root: Path, base_overlay: Path, output: Path) -> dict:
    source_root, base_overlay = (
        Path(source_root).resolve(),
        Path(base_overlay).resolve(),
    )
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError(f"output exists or is a symlink: {output}")
    if paths_overlap(output, source_root) or paths_overlap(output, base_overlay):
        raise ValueError(
            "output must not overlap the public source or supplied base overlay tree"
        )
    rendered, manifest = render_rain_overlay(source_root, base_overlay)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    for name, data in rendered.items():
        with (output / name).open("xb") as stream:
            stream.write(data)
    manifest["output_dir"] = str(output.resolve())
    with (output / "source_sha256.json").open("x") as stream:
        stream.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--base-overlay", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = create_overlay(args.source_root, args.base_overlay, args.output)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    print(
        json.dumps(
            {
                "output_dir": manifest["output_dir"],
                "overlay_sha256": manifest["overlay_sha256"],
                "manifest": str(Path(manifest["output_dir"]) / "source_sha256.json"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
