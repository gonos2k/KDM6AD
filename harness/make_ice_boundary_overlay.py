#!/usr/bin/env python3
"""Create a source-pinned, private trace overlay for legacy ice sedimentation.

Only the three copied C++ translation units are written to the output. The
input tree, operational library, and host installation are never modified.
The trace is opt-in through KDM6_ICE_BOUNDARY_TRACE and emits binary64 values
from value-only helper scopes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SOURCE_PINS = {
    "runtime.cpp": "4a56110c91b7495aea0542531eb809a048bb7994747cea2be826f9a2f6e26f7a",
    "coordinator.cpp": "9253e1741cb8926f98fc088c56579a015472ea43b7ef0b365ef2c42bd2660152",
    "sedimentation.cpp": "1fd41e6dff2f99cf80cf9f318245cb50cb2d107d2f9053f8c65802f6b4037c2a",
}
TRACE_ENV = "KDM6_ICE_BOUNDARY_TRACE"
SCHEMA = "kdm6.ice_boundary_trace.v1"
MARKER = "// BEGIN generated KDM6 ice boundary trace"

SED_INCLUDES = """
#include <algorithm>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <locale>
"""
COORD_INCLUDES = """
#include <iomanip>
#include <locale>
"""

SED_HELPER = r"""// BEGIN generated KDM6 ice boundary trace
bool ice_boundary_trace_enabled() {
    const char* path = std::getenv("KDM6_ICE_BOUNDARY_TRACE");
    return path != nullptr && *path != '\0';
}

void trace_ice_layer(
    int n, int64_t k, bool top, double dtcld,
    const torch::Tensor& mstep_col, const torch::Tensor& gate_col,
    const torch::Tensor& dend, const torch::Tensor& dend_safe,
    const torch::Tensor& delz, const torch::Tensor& delz_safe,
    const torch::Tensor& delz_prev,
    const torch::Tensor& work1_qi, const torch::Tensor& workn_qi,
    const torch::Tensor& qi_before, const torch::Tensor& ni_before,
    const torch::Tensor& falk_qi, const torch::Tensor& falk_ni,
    const torch::Tensor& fall_qi_before, const torch::Tensor& fall_qi_after,
    const torch::Tensor& fall_ni_before, const torch::Tensor& fall_ni_after,
    const torch::Tensor& applied_out_qi, const torch::Tensor& applied_out_ni,
    const torch::Tensor& upstream_falk_qi, const torch::Tensor& upstream_falk_ni,
    const torch::Tensor& source_post_qi, const torch::Tensor& source_post_ni,
    const torch::Tensor& applied_arrival_qi, const torch::Tensor& applied_arrival_ni,
    const torch::Tensor& qi_after, const torch::Tensor& ni_after) {
    if (!ice_boundary_trace_enabled()) return;
    const torch::Tensor* tensors[] = {
        &mstep_col, &gate_col, &dend, &dend_safe, &delz, &delz_safe, &delz_prev,
        &work1_qi, &workn_qi, &qi_before, &ni_before, &falk_qi, &falk_ni,
        &fall_qi_before, &fall_qi_after, &fall_ni_before, &fall_ni_after,
        &applied_out_qi, &applied_out_ni, &upstream_falk_qi, &upstream_falk_ni,
        &source_post_qi, &source_post_ni, &applied_arrival_qi, &applied_arrival_ni,
        &qi_after, &ni_after};
    for (const auto* t : tensors) {
        TORCH_CHECK(t->scalar_type() == torch::kFloat64,
                    "ice boundary trace requires binary64 tensors");
    }
    torch::NoGradGuard no_grad;
    const auto attempted_out_qi = falk_qi * dtcld / dend_safe;
    const auto attempted_out_ni = falk_ni * dtcld;
    const auto attempted_arrival_qi = top
        ? torch::zeros_like(falk_qi)
        : upstream_falk_qi * delz_prev / delz_safe * dtcld / dend_safe;
    const auto attempted_arrival_ni = top
        ? torch::zeros_like(falk_ni)
        : upstream_falk_ni * delz_prev / delz_safe * dtcld;
    const auto actual_out_qi = top ? qi_before - qi_after : applied_out_qi;
    const auto actual_out_ni = top ? ni_before - ni_after : applied_out_ni;
    const auto zero = torch::zeros_like(qi_before);
    const auto zero_ni = torch::zeros_like(ni_before);
    const auto& src_qi = top ? zero : source_post_qi;
    const auto& src_ni = top ? zero_ni : source_post_ni;
    const char* path = std::getenv("KDM6_ICE_BOUNDARY_TRACE");
    std::ofstream out(path, std::ios::out | std::ios::app);
    TORCH_CHECK(out.good(), "cannot append ice boundary trace: ", path);
    out.imbue(std::locale::classic());
    out << std::setprecision(17);
    for (int64_t b = 0; b < qi_before.size(0); ++b) {
        auto value = [b](const torch::Tensor& t) {
            return t.select(0, b).item<double>();
        };
        out << "schema=kdm6.ice_boundary_trace.v1 record=ice_layer order=top_first"
            << " substep=" << n << " dtcld_s=" << dtcld
            << " column=" << b << " level_top0=" << k << " top=" << (top ? 1 : 0)
            << " mstep=" << value(mstep_col) << " gate=" << value(gate_col)
            << " DEND_kg_m3=" << value(dend) << " DEND_safe_kg_m3=" << value(dend_safe)
            << " DELZ_m=" << value(delz) << " DELZ_safe_m=" << value(delz_safe)
            << " DELZ_above_m=" << (top ? 0.0 : value(delz_prev))
            << " work1_qi=" << value(work1_qi) << " workn_qi=" << value(workn_qi)
            << " QI_before_kg_kg=" << value(qi_before)
            << " NI_before_number_m3=" << value(ni_before)
            << " falk_qi_stored_kg_m3_s=" << value(falk_qi)
            << " falk_ni_stored_number_m3_s=" << value(falk_ni)
            << " fall_qi_accum_before_kg_m3_s=" << value(fall_qi_before)
            << " fall_qi_accum_after_kg_m3_s=" << value(fall_qi_after)
            << " fall_ni_accum_before_number_m3_s=" << value(fall_ni_before)
            << " fall_ni_accum_after_number_m3_s=" << value(fall_ni_after)
            << " out_attempt_qi_kg_kg=" << value(attempted_out_qi)
            << " out_applied_qi_kg_kg=" << value(actual_out_qi)
            << " upstream_falk_qi_stored_kg_m3_s=" << (top ? 0.0 : value(upstream_falk_qi))
            << " source_post_QI_kg_kg=" << value(src_qi)
            << " arrival_attempt_qi_kg_kg=" << value(attempted_arrival_qi)
            << " arrival_applied_qi_kg_kg=" << (top ? 0.0 : value(applied_arrival_qi))
            << " QI_after_kg_kg=" << value(qi_after)
            << " top_clip_qi_kg_kg=" << (top ? std::max(0.0, value(attempted_out_qi)-value(qi_before)) : 0.0)
            << " out_attempt_ni_number_m3=" << value(attempted_out_ni)
            << " out_applied_ni_number_m3=" << value(actual_out_ni)
            << " upstream_falk_ni_stored_number_m3_s=" << (top ? 0.0 : value(upstream_falk_ni))
            << " source_post_NI_number_m3=" << value(src_ni)
            << " arrival_attempt_ni_number_m3=" << value(attempted_arrival_ni)
            << " arrival_applied_ni_number_m3=" << (top ? 0.0 : value(applied_arrival_ni))
            << " NI_after_number_m3=" << value(ni_after)
            << " top_clip_ni_number_m3=" << (top ? std::max(0.0, value(attempted_out_ni)-value(ni_before)) : 0.0)
            << '\n';
    }
    TORCH_CHECK(out.good(), "failed writing ice boundary trace");
}
// END generated KDM6 ice boundary trace
"""

COORD_HELPER = r"""// BEGIN generated KDM6 ice boundary trace
bool ice_boundary_trace_enabled() {
    const char* path = std::getenv("KDM6_ICE_BOUNDARY_TRACE");
    return path != nullptr && *path != '\0';
}

void trace_ice_velocity_stage(const char* stage,
                              const torch::Tensor& work1_qi,
                              const torch::Tensor& workn_qi,
                              const torch::Tensor& delz,
                              const torch::Tensor& dend,
                              const torch::Tensor& mstep_col,
                              int mstepmax, double dtcld,
                              PhysicsVariant variant,
                              const char* velocity_basis) {
    if (!ice_boundary_trace_enabled()) return;
    const torch::Tensor* tensors[] = {&work1_qi, &workn_qi, &delz, &dend, &mstep_col};
    for (const auto* t : tensors) TORCH_CHECK(t->scalar_type() == torch::kFloat64,
                                               "ice velocity trace requires binary64 tensors");
    torch::NoGradGuard no_grad;
    const char* path = std::getenv("KDM6_ICE_BOUNDARY_TRACE");
    std::ofstream out(path, std::ios::out | std::ios::app);
    TORCH_CHECK(out.good(), "cannot append ice velocity trace: ", path);
    out.imbue(std::locale::classic());
    out << std::setprecision(17);
    for (int64_t b = 0; b < work1_qi.size(0); ++b) {
        for (int64_t k = 0; k < work1_qi.size(1); ++k) {
            out << "schema=kdm6.ice_boundary_trace.v1 record=ice_velocity order=top_first"
                << " stage=" << stage << " basis=" << velocity_basis
                << " dtcld_s=" << dtcld << " mstepmax=" << mstepmax
                << " variant=" << static_cast<uint32_t>(variant)
                << " column=" << b << " level_top0=" << k
                << " mstep=" << mstep_col.select(0,b).item<double>()
                << " work1_qi=" << work1_qi.select(0,b).select(0,k).item<double>()
                << " workn_qi=" << workn_qi.select(0,b).select(0,k).item<double>()
                << " DEND_kg_m3=" << dend.select(0,b).select(0,k).item<double>()
                << " DELZ_m=" << delz.select(0,b).select(0,k).item<double>() << '\n';
        }
    }
    TORCH_CHECK(out.good(), "failed writing ice velocity trace");
}

void trace_ice_bottom(const torch::Tensor& fall_qi,
                      const torch::Tensor& fall_ni,
                      const torch::Tensor& delz_bottom,
                      const torch::Tensor& rain_mm,
                      const torch::Tensor& snow_ice_mm,
                      const torch::Tensor& graupel_mm,
                      int64_t levels, double dtcld) {
    if (!ice_boundary_trace_enabled()) return;
    const torch::Tensor* tensors[] = {&fall_qi, &fall_ni, &delz_bottom,
                                      &rain_mm, &snow_ice_mm, &graupel_mm};
    for (const auto* t : tensors) TORCH_CHECK(t->scalar_type() == torch::kFloat64,
                                               "ice bottom trace requires binary64 tensors");
    torch::NoGradGuard no_grad;
    const char* path = std::getenv("KDM6_ICE_BOUNDARY_TRACE");
    std::ofstream out(path, std::ios::out | std::ios::app);
    TORCH_CHECK(out.good(), "cannot append ice bottom trace: ", path);
    out.imbue(std::locale::classic());
    out << std::setprecision(17);
    for (int64_t b = 0; b < fall_qi.size(0); ++b) {
        out << "schema=kdm6.ice_boundary_trace.v1 record=ice_bottom order=top_first"
            << " dtcld_s=" << dtcld << " column=" << b << " levels=" << levels
            << " bottom_top0=" << (levels-1)
            << " fall_qi_bottom_kg_m3_s=" << fall_qi.select(0,b).item<double>()
            << " fall_ni_bottom_number_m3_s=" << fall_ni.select(0,b).item<double>()
            << " DELZ_bottom_m=" << delz_bottom.select(0,b).item<double>()
            << " rain_increment_total_mm=" << rain_mm.select(0,b).item<double>()
            << " snow_ice_subset_mm=" << snow_ice_mm.select(0,b).item<double>()
            << " graupel_subset_mm=" << graupel_mm.select(0,b).item<double>() << '\n';
    }
    TORCH_CHECK(out.good(), "failed writing ice bottom trace");
}
// END generated KDM6 ice boundary trace
"""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def replace_once(source: str, old: str, new: str, label: str) -> str:
    n = source.count(old)
    if n != 1:
        raise RuntimeError(f"expected exactly one {label} anchor, found {n}")
    return source.replace(old, new, 1)


def instrument_sedimentation(source: str) -> str:
    if MARKER in source:
        raise RuntimeError("sedimentation source already traced")
    source = replace_once(
        source,
        '#include "kdm6/ops.h"\n',
        '#include "kdm6/ops.h"\n' + SED_INCLUDES,
        "sedimentation standard includes",
    )
    source = replace_once(
        source,
        "}  // namespace\n\nSubstepAdvectionOutputs substep_advection_torch(",
        SED_HELPER
        + "\n}  // namespace\n\nSubstepAdvectionOutputs substep_advection_torch(",
        "sedimentation anonymous helper",
    )
    source = replace_once(
        source,
        "    // Top\n    {\n        const int64_t k = 0;\n",
        "    // Top\n    {\n        const int64_t k = 0;\n"
        "        auto qi_top_entry = qi_cols[k];\n"
        "        auto ni_top_entry = ni_cols[k];\n"
        "        auto fall_qi_top_before = fall_qi_cols[k];\n"
        "        auto fall_ni_top_before = fall_ni_cols[k];\n",
        "ice top entry snapshots",
    )
    source = replace_once(
        source,
        "        falk_qi_prev = falk_qi_top;  falk_ni_prev = falk_ni_top;\n",
        "        if (ice_boundary_trace_enabled()) {\n"
        "            auto zero = torch::zeros_like(qi_cols[k]);\n"
        "            trace_ice_layer(n, k, true, dtcld, mstep_col_safe, gate_col,\n"
        "                dend_col(k), dend_safe_col(k), delz_col(k), delz_safe_col(k), zero,\n"
        "                work1_qi_col(k), workn_qi_col(k), qi_top_entry, ni_top_entry,\n"
        "                falk_qi_top, falk_ni_top, fall_qi_top_before, fall_qi_cols[k],\n"
        "                fall_ni_top_before, fall_ni_cols[k], zero, zero, zero, zero, zero, zero,\n"
        "                zero, zero, qi_cols[k], ni_cols[k]);\n"
        "        }\n"
        "        falk_qi_prev = falk_qi_top;  falk_ni_prev = falk_ni_top;\n",
        "ice top trace call",
    )
    source = replace_once(
        source,
        "    for (int64_t k = 1; k < K; ++k) {\n        auto falk_qi_k =",
        "    for (int64_t k = 1; k < K; ++k) {\n"
        "        auto qi_entry_k = qi_cols[k];\n"
        "        auto ni_entry_k = ni_cols[k];\n"
        "        auto fall_qi_k_before = fall_qi_cols[k];\n"
        "        auto fall_ni_k_before = fall_ni_cols[k];\n"
        "        auto upstream_qi_k = falk_qi_prev;\n"
        "        auto upstream_ni_k = falk_ni_prev;\n"
        "        auto source_post_qi_k = qi_cols[k - 1];\n"
        "        auto source_post_ni_k = ni_cols[k - 1];\n"
        "        auto falk_qi_k =",
        "ice interior snapshots",
    )
    source = replace_once(
        source,
        "        falk_qi_prev = falk_qi_k;  falk_ni_prev = falk_ni_k;  // carry stored falk\n",
        "        if (ice_boundary_trace_enabled()) {\n"
        "            trace_ice_layer(n, k, false, dtcld, mstep_col_safe, gate_col,\n"
        "                dend_col(k), dend_safe_col(k), delz_col(k), delz_safe_col(k), delz_col(k-1),\n"
        "                work1_qi_col(k), workn_qi_col(k), qi_entry_k, ni_entry_k, falk_qi_k, falk_ni_k,\n"
        "                fall_qi_k_before, fall_qi_cols[k], fall_ni_k_before, fall_ni_cols[k],\n"
        "                dqi_k, dni_k, upstream_qi_k, upstream_ni_k, source_post_qi_k, source_post_ni_k,\n"
        "                dqi_above, dni_above, qi_cols[k], ni_cols[k]);\n"
        "        }\n"
        "        falk_qi_prev = falk_qi_k;  falk_ni_prev = falk_ni_k;  // carry stored falk\n",
        "ice interior trace call",
    )
    return source


def instrument_coordinator(source: str) -> str:
    if MARKER in source:
        raise RuntimeError("coordinator source already traced")
    source = replace_once(
        source,
        "#include <fstream>\n",
        "#include <fstream>\n#include <iomanip>\n#include <locale>\n",
        "coordinator trace includes",
    )
    source = replace_once(
        source,
        "}  // namespace\n\n// ─── F1c: cold phase chain",
        COORD_HELPER + "\n}  // namespace\n\n// ─── F1c: cold phase chain",
        "coordinator trace helpers",
    )
    source = replace_once(
        source,
        "    auto w1_qi = work1_qi, wn_qi = workn_qi;\n",
        "    auto w1_qi = work1_qi, wn_qi = workn_qi;\n"
        '    trace_ice_velocity_stage("runtime_input_normalized", w1_qi, wn_qi, forcing.delz,\n'
        '        forcing.dend, mstep_col_ice, mstepmax_ice, dtcld, variant, "vt_over_delz");\n',
        "initial ice velocity trace",
    )
    source = replace_once(
        source,
        "    // ── Ice substepping ─────────────────────────────────────────────────────\n",
        '    trace_ice_velocity_stage("post_main_handoff", w1_qi, wn_qi, forcing.delz,\n'
        "        forcing.dend, mstep_col_ice, mstepmax_ice, dtcld, variant,\n"
        '        normalize_ice_handoff ? "vt_over_delz" : "raw_vt");\n'
        "\n    // ── Ice substepping ─────────────────────────────────────────────────────\n",
        "main-to-ice velocity trace",
    )
    source = replace_once(
        source,
        "    auto surface = sed::surface_accumulation_torch(\n"
        "        fall_qr_b, fall_qs_b, fall_qg_b, fall_qi_b, delz_b, dtcld\n"
        "    );\n",
        "    auto surface = sed::surface_accumulation_torch(\n"
        "        fall_qr_b, fall_qs_b, fall_qg_b, fall_qi_b, delz_b, dtcld\n"
        "    );\n"
        "    trace_ice_bottom(fall_qi_b, fall_ni.index({Slice(), bottom}), delz_b,\n"
        "        surface.rain_increment, surface.snow_increment, surface.graupel_increment, K, dtcld);\n",
        "ice bottom diagnostic trace",
    )
    return source


def instrument_runtime(source: str) -> str:
    # The request/response tool already pins exact KDM inputs and output. Keep
    # runtime.cpp byte-identical; copy it as an explicit overlay source pin.
    return source


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-root", type=Path, required=True)
    p.add_argument(
        "--base-build",
        type=Path,
        required=True,
        help="existing completed research CMake build; read-only",
    )
    p.add_argument("--request", type=Path, required=True)
    p.add_argument(
        "--output", type=Path, required=True, help="must be a new private directory"
    )
    a = p.parse_args()
    source_root = a.source_root.resolve()
    build = a.base_build.resolve()
    request = a.request.resolve()
    out = a.output.resolve()
    src = {name: source_root / "src" / name for name in SOURCE_PINS}
    for name, path in src.items():
        if not path.is_file():
            p.error(f"missing source {path}")
        got = sha256(path)
        if got != SOURCE_PINS[name]:
            p.error(
                f"{name} changed since review (expected {SOURCE_PINS[name]}, got {got})"
            )
    required_build_files = {
        "base_archive": build / "libkdm6.a",
        "compile_flags": build / "CMakeFiles/kdm6.dir/flags.make",
        "tool_object": build
        / "CMakeFiles/kdm6_column_budget.dir/tools/kdm6_column_budget.cpp.o",
        "tool_link": build / "CMakeFiles/kdm6_column_budget.dir/link.txt",
        "capi_object": build / "CMakeFiles/kdm6_c.dir/bridge/kdm6_c_api.cpp.o",
        "capi_link": build / "CMakeFiles/kdm6_c.dir/link.txt",
    }
    for label, path in required_build_files.items():
        if not path.is_file():
            p.error(f"missing required immutable build input {label}: {path}")
    if not request.is_file():
        p.error(f"request file missing: {request}")
    if out.exists():
        p.error(f"output must be new: {out}")
    if source_root in out.parents or build in out.parents:
        p.error("output must be outside source and base build trees")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.mkdir()
    snap = out / "source_snapshot"
    overlay = out / "overlay"
    snap.mkdir()
    overlay.mkdir()
    base_hashes = {}
    overlay_hashes = {}
    for name, path in src.items():
        base_text = path.read_text()
        (snap / name).write_text(base_text)
        base_hashes[name] = sha256(snap / name)
        if name == "runtime.cpp":
            instrumented = instrument_runtime(base_text)
        elif name == "coordinator.cpp":
            instrumented = instrument_coordinator(base_text)
        else:
            instrumented = instrument_sedimentation(base_text)
        target = overlay / name
        target.write_text(instrumented)
        overlay_hashes[name] = sha256(target)
    manifest = {
        "schema": SCHEMA,
        "source_root": str(source_root),
        "source_sha256": base_hashes,
        "overlay_source_sha256": overlay_hashes,
        "request_path": str(request),
        "request_sha256": sha256(request),
        "base_build_path": str(build),
        "base_build_inputs_sha256": {
            name: sha256(path) for name, path in required_build_files.items()
        },
        "trace_environment_variable": TRACE_ENV,
        "trace_records": ["ice_velocity", "ice_layer", "ice_bottom"],
        "orientation": "sedimentation top_first; public WRF model state bottom_first",
        "physics_change": False,
        "numeric_contract": "trace-enabled run rejects non-binary64 state, forcing, and local ice operands",
        "unit_contract": {
            "QI_state": "nominal water mass-mixing-ratio coordinate; DEN*DELZ*QI is a nominal state-inventory measure in kg m-2",
            "NI_state": "raw KDM operand interpreted as volumetric number (# m-3) by source equations; incoming host producer basis is not certified here",
            "legacy_velocity_handoff": "post-main-reslope raw VT_i/Vtni values are handed to ice substeps without /DELZ in Legacy; raw falk/outflow/arrival fields are executed algebraic values, not physically certified flux dimensions",
            "trace_suffixes": "field suffixes name the nominal coordinate/consumer; they do not assert dimensionally consistent physical fluxes where the legacy handoff is unnormalized",
            "interface_terms": "DEN*DELZ-weighted QI and DELZ-weighted NI departures/arrivals are state-equivalent terms from the actual update recurrence, not a certification of physical flux conservation",
            "bottom_comparison": "stored-falk equivalent versus applied bottom state outflow is a numerical state-coordinate comparison, not a certified physical surface flux",
        },
    }
    (out / "build_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    (out / "BUILD_NOTES.md").write_text(
        "# Private ice-boundary overlay build\n\n"
        "Compile only `overlay/coordinator.cpp` and `overlay/sedimentation.cpp` with the exact flags in the pinned base build's `CMakeFiles/kdm6.dir/flags.make`; keep `-ffp-contract=off`. Copy the pinned `libkdm6.a`, replace only its `coordinator.cpp.o` and `sedimentation.cpp.o` archive members with the new objects, run `ranlib`, and link the unchanged `kdm6_column_budget` and `kdm6_c` objects using their pinned link commands. Keep every output under this private evidence directory. `runtime.cpp` is included as an unchanged source snapshot because the binary request binds its state and forcing; no host or installed library is changed.\n\n"
        f"Trace only with `{TRACE_ENV}=/absolute/new/trace.tsv`; the raw trace records are strict key/value lines with `schema={SCHEMA}`.\n"
    )
    print(
        json.dumps(
            {
                "overlay": str(overlay),
                "manifest": str(out / "build_manifest.json"),
                "overlay_source_sha256": overlay_hashes,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
