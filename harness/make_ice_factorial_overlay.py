"""Generate a private 2x2 overlay for the Legacy main chain and ice-only factors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from harness import make_ice_boundary_overlay as base


MODE_ENV = "KDM6_ICE_FACTORIAL_MODE"
FACTOR_MODES = ("raw_cap", "norm_cap", "raw_actual", "norm_actual")
MODE_MARKER = "// BEGIN generated KDM6 ice factorial selector"
WATER_MARKER = "// BEGIN generated KDM6 factorial water stage trace"
ICE_LAYER_MARKER = "// BEGIN generated KDM6 factorial conservative ice trace"
FACTORIAL_SOURCE_PINS = {
    **base.SOURCE_PINS,
    "sedimentation_conservative.cpp": "53b13bc505b0e46327942b3b4070a541ce04f23f7a37d3b0bf60d731f8659694",
}

WATER_INCLUDES = """
#include <fstream>
#include <iomanip>
#include <locale>
"""

WATER_HELPER = r"""// BEGIN generated KDM6 factorial water stage trace
void trace_factorial_water_stage(const char* stage, int subcycle,
                                 double dt_call, double dtcld, int loops,
                                 const CoordinatorState& s,
                                 const CoordinatorForcing& f) {
    const char* path = std::getenv("KDM6_ICE_BOUNDARY_TRACE");
    if (path == nullptr || *path == '\0') return;
    const torch::Tensor* fields[] = {&s.qv, &s.qc, &s.qr, &s.qi, &s.qs, &s.qg};
    const char* names[] = {"qv", "qc", "qr", "qi", "qs", "qg"};
    for (int n = 0; n < 6; ++n) {
        TORCH_CHECK(fields[n]->scalar_type() == torch::kFloat64,
                    "factorial water trace requires binary64 state fields");
    }
    TORCH_CHECK(f.den.scalar_type() == torch::kFloat64 &&
                f.delz.scalar_type() == torch::kFloat64,
                "factorial water trace requires binary64 DEND/DELZ");
    const char* mode_env = std::getenv("KDM6_ICE_FACTORIAL_MODE");
    const char* mode = (mode_env == nullptr || *mode_env == '\0') ? "legacy" : mode_env;
    const std::string out_path = std::string(path) + ".water.tsv";
    torch::NoGradGuard no_grad;
    std::ofstream out(out_path, std::ios::out | std::ios::app);
    TORCH_CHECK(out.good(), "cannot append factorial water-stage trace: ", out_path);
    out.imbue(std::locale::classic());
    out << std::setprecision(17);
    for (int64_t b = 0; b < s.qv.size(0); ++b) {
        for (int64_t k = 0; k < s.qv.size(1); ++k) {
            out << "schema=kdm6.ice_factorial_water_stage.v1 record=water_stage"
                << " stage=" << stage << " factor_mode=" << mode
                << " subcycle=" << subcycle << " dt_call_s=" << dt_call
                << " loops=" << loops << " dtcld_s=" << dtcld
                << " column=" << b << " level_bottom0=" << k
                << " DEND_kg_m3=" << f.dend.select(0,b).select(0,k).item<double>()
                << " DELZ_m=" << f.delz.select(0,b).select(0,k).item<double>();
            for (int n = 0; n < 6; ++n) {
                out << ' ' << names[n] << "_kg_kg="
                    << fields[n]->select(0,b).select(0,k).item<double>();
            }
            out << '\n';
        }
    }
    TORCH_CHECK(out.good(), "failed writing factorial water-stage trace");
}
// END generated KDM6 factorial water stage trace
"""

ICE_LAYER_HELPER = r"""// BEGIN generated KDM6 factorial conservative ice trace
void trace_factorial_ice_layer(
    int n, int64_t k, double dtcld,
    const torch::Tensor& mstep, const torch::Tensor& gate,
    const torch::Tensor& dend, const torch::Tensor& dend_safe,
    const torch::Tensor& delz, const torch::Tensor& delz_safe,
    const torch::Tensor& work1_qi, const torch::Tensor& workn_qi,
    const torch::Tensor& qi_before, const torch::Tensor& ni_before,
    const torch::Tensor& falk_qi, const torch::Tensor& falk_ni,
    const torch::Tensor& out_attempt_qi, const torch::Tensor& out_attempt_ni,
    const torch::Tensor& out_applied_qi, const torch::Tensor& out_applied_ni,
    const torch::Tensor& arrival_applied_qi, const torch::Tensor& arrival_applied_ni,
    const torch::Tensor& qi_after, const torch::Tensor& ni_after) {
    const char* path = std::getenv("KDM6_ICE_BOUNDARY_TRACE");
    if (path == nullptr || *path == '\0') return;
    const torch::Tensor* tensors[] = {
        &mstep, &gate, &dend, &dend_safe, &delz, &delz_safe, &work1_qi, &workn_qi,
        &qi_before, &ni_before, &falk_qi, &falk_ni, &out_attempt_qi, &out_attempt_ni,
        &out_applied_qi, &out_applied_ni, &arrival_applied_qi, &arrival_applied_ni,
        &qi_after, &ni_after};
    for (const auto* t : tensors) {
        TORCH_CHECK(t->scalar_type() == torch::kFloat64,
                    "factorial conservative ice trace requires binary64 tensors");
    }
    torch::NoGradGuard no_grad;
    const char* mode_env = std::getenv("KDM6_ICE_FACTORIAL_MODE");
    const char* mode = (mode_env == nullptr || *mode_env == '\0') ? "legacy" : mode_env;
    const std::string out_path = std::string(path) + ".layers.tsv";
    std::ofstream out(out_path, std::ios::out | std::ios::app);
    TORCH_CHECK(out.good(), "cannot append factorial ice layer trace: ", out_path);
    out.imbue(std::locale::classic());
    out << std::setprecision(17);
    for (int64_t b = 0; b < qi_before.size(0); ++b) {
        auto value = [b](const torch::Tensor& t) { return t.select(0, b).item<double>(); };
        out << "schema=kdm6.ice_factorial_layer.v1 record=ice_factor_layer order=top_first"
            << " factor_mode=" << mode << " recurrence=actual_departure substep=" << n
            << " dtcld_s=" << dtcld << " column=" << b << " level_top0=" << k
            << " mstep=" << value(mstep) << " gate=" << value(gate)
            << " DEND_kg_m3=" << value(dend) << " DEND_safe_kg_m3=" << value(dend_safe)
            << " DELZ_m=" << value(delz) << " DELZ_safe_m=" << value(delz_safe)
            << " work1_qi=" << value(work1_qi) << " workn_qi=" << value(workn_qi)
            << " QI_before_kg_kg=" << value(qi_before)
            << " NI_before_number_m3=" << value(ni_before)
            << " falk_qi_code_value=" << value(falk_qi)
            << " falk_ni_code_value=" << value(falk_ni)
            << " out_attempt_qi=" << value(out_attempt_qi)
            << " out_attempt_ni=" << value(out_attempt_ni)
            << " out_applied_qi=" << value(out_applied_qi)
            << " out_applied_ni=" << value(out_applied_ni)
            << " arrival_applied_qi=" << value(arrival_applied_qi)
            << " arrival_applied_ni=" << value(arrival_applied_ni)
            << " QI_after_kg_kg=" << value(qi_after)
            << " NI_after_number_m3=" << value(ni_after) << '\n';
    }
    TORCH_CHECK(out.good(), "failed writing factorial conservative ice trace");
}
// END generated KDM6 factorial conservative ice trace
"""


def instrument_factor_runtime(source: str) -> str:
    if WATER_MARKER in source:
        raise RuntimeError("runtime source already has factorial water tracing")
    source = base.replace_once(
        source,
        "#include <cmath>\n",
        "#include <cmath>\n" + WATER_INCLUDES,
        "runtime water trace includes",
    )
    source = base.replace_once(
        source,
        "// Fail-loud variant gate (C3), shared by the kdm6_fn/kdm6_step options\n",
        WATER_HELPER
        + "\n// Fail-loud variant gate (C3), shared by the kdm6_fn/kdm6_step options\n",
        "runtime water trace helper",
    )
    source = base.replace_once(
        source,
        "        auto sed = sedimentation_chain(\n",
        '        trace_factorial_water_stage("pre_sed", i, dt, dtcld, loops, cur, cf);\n'
        "        auto sed = sedimentation_chain(\n",
        "per-subcycle pre-sed water stage",
    )
    source = base.replace_once(
        source,
        "        rain_inc  = (i == 0) ? sed.rain_increment",
        '        trace_factorial_water_stage("post_sed", i, dt, dtcld, loops, cur, cf);\n'
        "        rain_inc  = (i == 0) ? sed.rain_increment",
        "post-sed water stage",
    )
    source = base.replace_once(
        source,
        "                              entry_cpm, entry_xl);\n    }\n\n    // Surface increments accumulated",
        "                              entry_cpm, entry_xl);\n"
        '        trace_factorial_water_stage("post_micro", i, dt, dtcld, loops, cur, cf);\n'
        "    }\n\n    // Surface increments accumulated",
        "post-micro water stage",
    )
    return source


def instrument_factor_conservative_sedimentation(source: str) -> str:
    if ICE_LAYER_MARKER in source:
        raise RuntimeError("conservative sedimentation already has factorial tracing")
    source = base.replace_once(
        source,
        '#include "kdm6/sedimentation_conservative.h"\n',
        '#include "kdm6/sedimentation_conservative.h"\n'
        "#include <cstdlib>\n#include <fstream>\n#include <iomanip>\n#include <locale>\n",
        "conservative factorial trace includes",
    )
    source = base.replace_once(
        source,
        "}  // namespace\n\nSubstepAdvectionOutputs substep_advection_conservative(",
        ICE_LAYER_HELPER
        + "\n}  // namespace\n\nSubstepAdvectionOutputs substep_advection_conservative(",
        "conservative factorial trace helper",
    )
    source = base.replace_once(
        source,
        "        auto falk_qi = (dend_col(k) * qi_cols[k] * in.work1_qi.select(-1, k)\n",
        "        auto qi_before_k = qi_cols[k];\n"
        "        auto ni_before_k = ni_cols[k];\n"
        "        auto falk_qi = (dend_col(k) * qi_cols[k] * in.work1_qi.select(-1, k)\n",
        "conservative ice pre-state capture",
    )
    source = base.replace_once(
        source,
        "        if (k == 0) {\n"
        "            qi_cols[k] = qi_cols[k] - dqi_out;\n"
        "            ni_cols[k] = ni_cols[k] - dni_out;\n"
        "        } else {\n"
        "            // mass: ρΔz-conserving transfer; number: legacy Δz-only measure.\n"
        "            auto dqi_in = prev_out_qi * (dend_safe_col(k - 1) * delz_col(k - 1))\n"
        "                          / (dend_safe_col(k) * delz_safe_col(k));\n"
        "            auto dni_in = prev_out_ni * delz_col(k - 1) / delz_safe_col(k);\n"
        "            qi_cols[k] = qi_cols[k] - dqi_out + dqi_in;\n"
        "            ni_cols[k] = ni_cols[k] - dni_out + dni_in;\n"
        "        }\n"
        "        prev_out_qi = dqi_out;\n",
        "        torch::Tensor dqi_in = torch::zeros_like(dqi_out);\n"
        "        torch::Tensor dni_in = torch::zeros_like(dni_out);\n"
        "        if (k == 0) {\n"
        "            qi_cols[k] = qi_cols[k] - dqi_out;\n"
        "            ni_cols[k] = ni_cols[k] - dni_out;\n"
        "        } else {\n"
        "            // mass: ρΔz-conserving transfer; number: legacy Δz-only measure.\n"
        "            dqi_in = prev_out_qi * (dend_safe_col(k - 1) * delz_col(k - 1))\n"
        "                     / (dend_safe_col(k) * delz_safe_col(k));\n"
        "            dni_in = prev_out_ni * delz_col(k - 1) / delz_safe_col(k);\n"
        "            qi_cols[k] = qi_cols[k] - dqi_out + dqi_in;\n"
        "            ni_cols[k] = ni_cols[k] - dni_out + dni_in;\n"
        "        }\n"
        '        if (std::getenv("KDM6_ICE_BOUNDARY_TRACE") != nullptr) {\n'
        "            auto out_attempt_qi = falk_qi * dtcld / dend_safe_col(k);\n"
        "            auto out_attempt_ni = falk_ni * dtcld;\n"
        "            trace_factorial_ice_layer(n, k, dtcld, mstep_col_safe, gate_col,\n"
        "                dend_col(k), dend_safe_col(k), delz_col(k), delz_safe_col(k),\n"
        "                in.work1_qi.select(-1,k), in.workn_qi.select(-1,k), qi_before_k, ni_before_k,\n"
        "                falk_qi, falk_ni, out_attempt_qi, out_attempt_ni, dqi_out, dni_out,\n"
        "                dqi_in, dni_in, qi_cols[k], ni_cols[k]);\n"
        "        }\n"
        "        prev_out_qi = dqi_out;\n",
        "conservative actual ice departure and arrival trace",
    )
    return source


def instrument_factor_legacy_sedimentation(source: str) -> str:
    source = base.instrument_sedimentation(source)
    source = base.replace_once(
        source,
        '    const char* path = std::getenv("KDM6_ICE_BOUNDARY_TRACE");\n'
        "    std::ofstream out(path, std::ios::out | std::ios::app);\n",
        '    const char* path = std::getenv("KDM6_ICE_BOUNDARY_TRACE");\n'
        '    const char* mode_env = std::getenv("KDM6_ICE_FACTORIAL_MODE");\n'
        "    const char* mode = (mode_env == nullptr || *mode_env == '\\0') ? \"legacy\" : mode_env;\n"
        "    std::ofstream out(path, std::ios::out | std::ios::app);\n",
        "legacy trace factorial mode provenance",
    )
    return base.replace_once(
        source,
        'out << "schema=kdm6.ice_boundary_trace.v1 record=ice_layer order=top_first"\n'
        '            << " substep=" << n << " dtcld_s=" << dtcld\n',
        'out << "schema=kdm6.ice_boundary_trace.v1 record=ice_layer order=top_first"\n'
        '            << " factor_mode=" << mode << " recurrence=legacy_stored_falk"\n'
        '            << " substep=" << n << " dtcld_s=" << dtcld\n',
        "legacy trace factorial mode field",
    )


def instrument_factor_coordinator(source: str) -> str:
    if MODE_MARKER in source:
        raise RuntimeError("coordinator already has the factorial mode selector")
    source = base.instrument_coordinator(source)
    # Mode parsing sits inside sedimentation_chain. Its main substep function
    # remains selected exclusively by PhysicsVariant; factorial modes are
    # fail-closed to PhysicsVariant::Legacy.
    source = base.replace_once(
        source,
        "    const MainSubstepFn main_substep_fn =\n",
        MODE_MARKER + "\n"
        '    const char* ice_factor_env = std::getenv("KDM6_ICE_FACTORIAL_MODE");\n'
        '    const std::string ice_factor_mode = ice_factor_env == nullptr ? "legacy" : ice_factor_env;\n'
        '    TORCH_CHECK(ice_factor_mode == "legacy" || ice_factor_mode == "raw_cap" ||\n'
        '                ice_factor_mode == "norm_cap" || ice_factor_mode == "raw_actual" ||\n'
        '                ice_factor_mode == "norm_actual",\n'
        '                "unsupported KDM6_ICE_FACTORIAL_MODE: ", ice_factor_mode);\n'
        '    if (ice_factor_mode != "legacy") {\n'
        "        TORCH_CHECK(variant == PhysicsVariant::Legacy,\n"
        '                    "ice factorial modes require the Legacy main physics chain");\n'
        "    }\n"
        "    const bool ice_factor_normalize_first =\n"
        '        ice_factor_mode == "norm_cap" || ice_factor_mode == "norm_actual";\n'
        "    const bool ice_factor_actual_departure =\n"
        '        ice_factor_mode == "raw_actual" || ice_factor_mode == "norm_actual";\n'
        "    const MainSubstepFn main_substep_fn =\n",
        "ice-only factor selector",
    )
    source = base.replace_once(
        source,
        "    const IceSubstepFn ice_substep_fn =\n"
        "        conservative ? sed::ice_substep_advection_conservative : sed::ice_substep_advection_torch;\n",
        "    const IceSubstepFn legacy_ice_substep_fn =\n"
        "        conservative ? sed::ice_substep_advection_conservative : sed::ice_substep_advection_torch;\n"
        "    const IceSubstepFn ice_substep_fn = ice_factor_actual_departure\n"
        "        ? sed::ice_substep_advection_conservative : legacy_ice_substep_fn;\n",
        "ice-only substep selector",
    )
    source = base.replace_once(
        source,
        '        normalize_ice_handoff ? "vt_over_delz" : "raw_vt");\n',
        '        (normalize_ice_handoff || ice_factor_normalize_first) ? "vt_over_delz" : "raw_vt");\n',
        "factorial ice trace basis metadata",
    )
    source = base.replace_once(
        source,
        "            w1_qi = normalize_ice_handoff ? pre.slope.vt_i / delz_safe : pre.slope.vt_i;\n"
        "            wn_qi = normalize_ice_handoff ? pre.slope.vtn_i / delz_safe : pre.slope.vtn_i;\n",
        "            const bool normalize_ice_first = normalize_ice_handoff || ice_factor_normalize_first;\n"
        "            w1_qi = normalize_ice_first ? pre.slope.vt_i / delz_safe : pre.slope.vt_i;\n"
        "            wn_qi = normalize_ice_first ? pre.slope.vtn_i / delz_safe : pre.slope.vtn_i;\n",
        "first ice handoff normalization factor",
    )
    return source


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--base-build", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source_root, build, request, output = (
        args.source_root.resolve(),
        args.base_build.resolve(),
        args.request.resolve(),
        args.output.resolve(),
    )
    sources = {name: source_root / "src" / name for name in FACTORIAL_SOURCE_PINS}
    for name, path in sources.items():
        if not path.is_file():
            parser.error(f"missing source: {path}")
        got = base.sha256(path)
        if got != FACTORIAL_SOURCE_PINS[name]:
            parser.error(
                f"source pin changed for {name}: expected {FACTORIAL_SOURCE_PINS[name]}, got {got}"
            )
    build_inputs = {
        "base_archive": build / "libkdm6.a",
        "compile_flags": build / "CMakeFiles/kdm6.dir/flags.make",
        "tool_object": build
        / "CMakeFiles/kdm6_column_budget.dir/tools/kdm6_column_budget.cpp.o",
        "tool_link": build / "CMakeFiles/kdm6_column_budget.dir/link.txt",
        "capi_object": build / "CMakeFiles/kdm6_c.dir/bridge/kdm6_c_api.cpp.o",
        "capi_link": build / "CMakeFiles/kdm6_c.dir/link.txt",
    }
    for key, path in build_inputs.items():
        if not path.is_file():
            parser.error(f"missing base build input {key}: {path}")
    if not request.is_file():
        parser.error(f"missing saved request: {request}")
    if output.exists():
        parser.error(f"output must be new: {output}")
    if source_root in output.parents or build in output.parents:
        parser.error("output must be outside source and base build trees")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    snapshots, overlays = output / "source_snapshot", output / "overlay"
    snapshots.mkdir()
    overlays.mkdir()
    base_hashes, overlay_hashes = {}, {}
    for name, path in sources.items():
        text = path.read_text()
        (snapshots / name).write_text(text)
        base_hashes[name] = base.sha256(snapshots / name)
        if name == "runtime.cpp":
            rendered = instrument_factor_runtime(text)
        elif name == "coordinator.cpp":
            rendered = instrument_factor_coordinator(text)
        elif name == "sedimentation.cpp":
            rendered = instrument_factor_legacy_sedimentation(text)
        elif name == "sedimentation_conservative.cpp":
            rendered = instrument_factor_conservative_sedimentation(text)
        else:
            raise AssertionError(f"unhandled factorial translation unit: {name}")
        target = overlays / name
        target.write_text(rendered)
        overlay_hashes[name] = base.sha256(target)
    manifest = {
        "schema": "kdm6.ice_factorial_overlay.v1",
        "generator_sha256": base.sha256(Path(__file__)),
        "source_root": str(source_root),
        "source_sha256": base_hashes,
        "overlay_source_sha256": overlay_hashes,
        "request_path": str(request),
        "request_sha256": base.sha256(request),
        "base_build_path": str(build),
        "base_build_inputs_sha256": {
            name: base.sha256(path) for name, path in build_inputs.items()
        },
        "factor_mode_environment_variable": MODE_ENV,
        "factor_modes": list(FACTOR_MODES),
        "default_when_unset": "legacy",
        "main_chain": "always selected only by PhysicsVariant; factorial modes fail unless Legacy",
        "factors": {
            "handoff": "raw post-main VT_i/Vtni versus normalized VT_i/DELZ and Vtni/DELZ for first ice handoff only",
            "arrival_departure": "legacy stored-falk, post-reservoir-capped arrival versus existing conservative ice actual-departure recurrence",
        },
        "unit_contract": {
            "QI_state": "nominal mass-mixing-ratio coordinate; DEN*DELZ*QI is nominal state inventory",
            "NI_state": "raw KDM operand source-equation basis; original host input basis not certified",
            "legacy_raw_handoff": "work1/2 receive raw post-main VT_i/Vtni; algebraic trace labels are not physical flux certification",
        },
        "operational_map_changed": False,
        "experimental_ice_map_varies": True,
        "trace_environment_variable": "KDM6_ICE_BOUNDARY_TRACE",
        "water_stage_trace": {
            "path": "<KDM6_ICE_BOUNDARY_TRACE>.water.tsv",
            "schema": "kdm6.ice_factorial_water_stage.v1",
            "stages": ["pre_sed", "post_sed", "post_micro"],
            "orientation": "WRF state order, level_bottom0=0 is bottom",
            "values": "binary64 exact values formatted with 17 significant digits; emitted only when trace env is set",
        },
        "ice_layer_trace": {
            "path": "<KDM6_ICE_BOUNDARY_TRACE>.layers.tsv for actual-departure recurrence; main trace for legacy stored-falk recurrence",
            "schemas": ["kdm6.ice_factorial_layer.v1", "kdm6.ice_boundary_trace.v1"],
            "orientation": "top_first, level_top0=0 is top",
            "direct_actual_fields": [
                "out_applied_qi",
                "out_applied_ni",
                "arrival_applied_qi",
                "arrival_applied_ni",
            ],
            "unit_caveat": "legacy velocity handoff and corresponding falk-derived fields remain executed algebraic values; suffixes do not certify physical flux dimensions",
        },
    }
    (output / "build_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    print(
        json.dumps(
            {
                "overlay": str(overlays),
                "manifest": str(output / "build_manifest.json"),
                "overlay_source_sha256": overlay_hashes,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
