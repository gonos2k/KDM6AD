#!/usr/bin/env python3
"""Create an isolated runtime.cpp overlay with fp64 stage-budget tracing.

This generator never edits its input tree. It instruments the supplied
``src/runtime.cpp`` into a new output directory and writes a source hash
manifest. The runtime emits key/value text only when
KDM6_SAME_CALL_BUDGET_TRACE is set. Trace mode fails closed unless all measured
water and weight tensors are binary64.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


EXPECTED_RUNTIME_SHA256 = "4a56110c91b7495aea0542531eb809a048bb7994747cea2be826f9a2f6e26f7a"
MARKER = "// BEGIN generated same-call water-budget trace"

INCLUDES = """
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <locale>
"""

HELPER = r'''// BEGIN generated same-call water-budget trace
void trace_same_call_water(const char* stage, int subcycle, double dt_call,
                           double dtcld, int loops,
                           const CoordinatorState& s,
                           const CoordinatorForcing& f) {
    const char* path = std::getenv("KDM6_SAME_CALL_BUDGET_TRACE");
    if (path == nullptr || *path == '\0') return;
    const torch::Tensor* waters[] = {&s.qv, &s.qc, &s.qr, &s.qi, &s.qs, &s.qg};
    const char* names[] = {"qv", "qc", "qr", "qi", "qs", "qg"};
    for (int n = 0; n < 6; ++n) {
        TORCH_CHECK(waters[n]->scalar_type() == torch::kFloat64,
                    "same-call trace requires binary64 water state; ", names[n]);
    }
    TORCH_CHECK(f.den.scalar_type() == torch::kFloat64 &&
                f.delz.scalar_type() == torch::kFloat64,
                "same-call trace requires binary64 DEN and DELZ");
    TORCH_CHECK(s.qv.sizes() == f.den.sizes() && f.den.sizes() == f.delz.sizes(),
                "same-call trace requires matching (column, level) shapes");

    torch::NoGradGuard no_grad;
    const auto rho_dz = f.den * f.delz;
    const auto q_total = s.qv + s.qc + s.qr + s.qi + s.qs + s.qg;
    std::ofstream out(path, std::ios::out | std::ios::app);
    TORCH_CHECK(out.good(), "cannot append same-call budget trace: ", path);
    out.imbue(std::locale::classic());
    out << std::setprecision(17);
    for (int64_t b = 0; b < s.qv.size(0); ++b) {
        const auto weight = rho_dz.select(0, b);
        out << "stage=" << stage
            << " record=column"
            << " subcycle=" << subcycle
            << " dt_call=" << dt_call
            << " loops=" << loops
            << " dtcld=" << dtcld
            << " column=" << b;
        for (int n = 0; n < 6; ++n) {
            const double mass = (weight * waters[n]->select(0, b)).sum().item<double>();
            out << ' ' << names[n] << "_kg_m2=" << mass;
        }
        const double total = (weight * q_total.select(0, b)).sum().item<double>();
        out << " total_kg_m2=" << total << '\n';
        for (int64_t k = 0; k < s.qv.size(1); ++k) {
            out << "stage=" << stage
                << " record=level"
                << " subcycle=" << subcycle
                << " dt_call=" << dt_call
                << " loops=" << loops
                << " dtcld=" << dtcld
                << " column=" << b
                << " level=" << k
                << " DEN_kg_m3=" << f.den.select(0, b).select(0, k).item<double>()
                << " DELZ_m=" << f.delz.select(0, b).select(0, k).item<double>();
            for (int n = 0; n < 6; ++n) {
                out << ' ' << names[n] << "_kg_kg="
                    << waters[n]->select(0, b).select(0, k).item<double>();
            }
            out << " qtotal_kg_kg=" << q_total.select(0, b).select(0, k).item<double>()
                << " weight_kg_m2=" << weight.select(0, k).item<double>()
                << " water_layer_kg_m2="
                << (weight.select(0, k) * q_total.select(0, b).select(0, k)).item<double>()
                << '\n';
        }
    }
    TORCH_CHECK(out.good(), "failed writing same-call budget trace: ", path);
}
// END generated same-call water-budget trace
'''


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected one {label} anchor, found {count}")
    return text.replace(old, new, 1)


def instrument(source: str) -> str:
    if MARKER in source:
        raise RuntimeError("source already contains the generated trace marker")
    source = replace_once(source, "#include <cmath>\n",
                          "#include <cmath>\n" + INCLUDES,
                          "standard include")
    source = replace_once(source, "// Fail-loud variant gate (C3), shared by the kdm6_fn/kdm6_step options\n",
                          HELPER + "\n// Fail-loud variant gate (C3), shared by the kdm6_fn/kdm6_step options\n",
                          "anonymous-namespace helper insertion")

    source = replace_once(
        source,
        "    const double dtcld = static_cast<float>(dt / static_cast<double>(loops));\n\n    auto cur = cs;",
        "    const double dtcld = static_cast<float>(dt / static_cast<double>(loops));\n"
        "    trace_same_call_water(\"entry\", -1, dt, dtcld, loops, cs, cf);\n\n"
        "    auto cur = cs;",
        "entry trace call",
    )
    source = replace_once(
        source,
        "        auto sed = sedimentation_chain(\n",
        "        trace_same_call_water(\"pre_sed\", i, dt, dtcld, loops, cur_pyc, cf_pyc);\n"
        "        auto sed = sedimentation_chain(\n",
        "pre-sed trace call",
    )
    source = replace_once(
        source,
        "        rain_inc  = (i == 0) ? sed.rain_increment",
        "        trace_same_call_water(\"post_sed\", i, dt, dtcld, loops, cur, cf);\n"
        "        rain_inc  = (i == 0) ? sed.rain_increment",
        "post-sed trace call",
    )
    source = replace_once(
        source,
        "                              entry_cpm, entry_xl);\n    }\n\n    // Surface increments accumulated",
        "                              entry_cpm, entry_xl);\n"
        "        trace_same_call_water(\"post_micro\", i, dt, dtcld, loops, cur, cf);\n"
        "    }\n\n    // Surface increments accumulated",
        "post-micro trace call",
    )
    source = replace_once(
        source,
        "    return FnResult{\n        /*state_out=*/std::move(state_out),",
        "    if (std::getenv(\"KDM6_SAME_CALL_BUDGET_TRACE\") != nullptr &&\n"
        "        *std::getenv(\"KDM6_SAME_CALL_BUDGET_TRACE\") != '\\0') {\n"
        "        trace_same_call_water(\"exit\", loops, dt, dtcld, loops,\n"
        "                              state_to_coord(state_out, forcing), cf);\n"
        "    }\n"
        "    return FnResult{\n        /*state_out=*/std::move(state_out),",
        "exit trace call",
    )
    return source


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--libtorch-source", type=Path, required=True,
                        help="libtorch source tree containing the exact reviewed runtime.cpp")
    parser.add_argument("--output", type=Path, required=True,
                        help="new private directory; it must not already exist")
    args = parser.parse_args()
    source_root = args.libtorch_source.resolve()
    output = args.output.resolve()
    source_runtime = source_root / "src/runtime.cpp"
    if not source_runtime.is_file() or not (source_root / "CMakeLists.txt").is_file():
        parser.error("--libtorch-source must contain CMakeLists.txt and src/runtime.cpp")
    current_hash = sha256(source_runtime)
    if current_hash != EXPECTED_RUNTIME_SHA256:
        parser.error(
            "runtime.cpp no longer matches the reviewed source pin; re-audit before regenerating "
            f"(expected {EXPECTED_RUNTIME_SHA256}, got {current_hash})"
        )
    if output.exists():
        parser.error(f"output already exists; choose a fresh directory: {output}")
    if output == source_root or source_root in output.parents:
        parser.error("output must be outside the input source tree")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    target_runtime = output / "runtime.cpp"
    target_runtime.write_text(instrument(source_runtime.read_text()))
    manifest = {
        "schema": "kdm6.same_call_budget_runtime_overlay.v1",
        "input_libtorch_source": str(source_root),
        "input_runtime_sha256": current_hash,
        "overlay_runtime_sha256": sha256(target_runtime),
        "overlay_runtime": str(target_runtime),
        "instrumented_stages": ["entry", "pre_sed", "post_sed", "post_micro", "exit"],
        "trace_environment_variable": "KDM6_SAME_CALL_BUDGET_TRACE",
        "trace_numeric_contract": "binary64-only state, DEN, DELZ; 17 significant digits",
    }
    (output / "source_sha256.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"overlay_runtime": str(target_runtime),
                      "overlay_runtime_sha256": manifest["overlay_runtime_sha256"],
                      "manifest": str(output / "source_sha256.json")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
