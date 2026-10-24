"""Generate an isolated QR-only actual-departure candidate over frozen v6."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from harness.make_rain_boundary_overlay import (
    paths_overlap,
    replace_once,
    sha256_bytes,
    validate_base_overlay,
)

MODE_ENV = "KDM6_QR_TRANSPORT"
TRACE_ENV = "KDM6_ACTUAL_QR_TRACE"
MARKER = "// BEGIN generated QR-only actual-departure candidate"

HELPER = r"""// BEGIN generated QR-only actual-departure candidate
namespace {
void check_actual_qr_entry(const SubstepAdvectionInputs& in,
                           const torch::Tensor& count, double dt, double floor) {
    TORCH_CHECK(dt > 0.0 && std::isfinite(dt), "actual QR requires positive finite dt");
    TORCH_CHECK(!count.requires_grad(), "mstep is fixed nondifferentiable metadata");
    // Value-only admission guard; no arithmetic result from this scope is reused.
    torch::NoGradGuard guard;
    const torch::Tensor* fields[] = {&in.state.qr, &in.fall_qr_in, &in.work1_qr,
                                    &in.dend, &in.delz};
    for (const auto* v : fields) {
        TORCH_CHECK(v->scalar_type() == torch::kFloat64 &&
                    torch::isfinite(*v).all().item<bool>(),
                    "actual QR requires finite binary64 inputs");
    }
    TORCH_CHECK((in.state.qr >= 0).all().item<bool>() &&
                (in.work1_qr >= 0).all().item<bool>() &&
                (in.fall_qr_in >= 0).all().item<bool>(), "negative QR/work/fall");
    TORCH_CHECK((in.dend > floor).all().item<bool>() &&
                (in.delz > floor).all().item<bool>(), "invalid native dry geometry");
    TORCH_CHECK(torch::isfinite(count).all().item<bool>() &&
                (count >= 1).all().item<bool>() &&
                (count == torch::floor(count)).all().item<bool>(), "invalid count");
}

void trace_actual_qr(int n, int64_t k, double dt,
    const torch::Tensor& count, const torch::Tensor& gate,
    const torch::Tensor& rho, const torch::Tensor& dz, const torch::Tensor& work,
    const torch::Tensor& before, const torch::Tensor& after,
    const torch::Tensor& departure, const torch::Tensor& arrival,
    const torch::Tensor& fall_before, const torch::Tensor& fall_after) {
    const char* path = std::getenv("KDM6_ACTUAL_QR_TRACE");
    if (path == nullptr || *path == '\0') return;
    torch::NoGradGuard guard;
    std::ofstream out(path, std::ios::out | std::ios::app);
    TORCH_CHECK(out.good(), "cannot append actual QR trace");
    out.imbue(std::locale::classic());
    out << std::setprecision(17);
    if (out.tellp() == 0) out << "n\tk_top0\tcolumn\tdt\tmstep\tgate\trho\tdz\twork\tq_before\tq_after\tdeparture\tarrival\tfall_before\tfall_after\n";
    for (int64_t b = 0; b < before.numel(); ++b) {
        auto v = [b](const torch::Tensor& x) { return x.select(0,b).item<double>(); };
        out << n << '\t' << k << '\t' << b << '\t' << dt << '\t'
            << v(count) << '\t' << v(gate) << '\t' << v(rho) << '\t'
            << v(dz) << '\t' << v(work) << '\t' << v(before) << '\t'
            << v(after) << '\t' << v(departure) << '\t' << v(arrival) << '\t'
            << v(fall_before) << '\t' << v(fall_after) << '\n';
    }
    TORCH_CHECK(out.good(), "failed writing actual QR trace");
}
}  // namespace

SubstepAdvectionOutputs substep_advection_torch(
    const SubstepAdvectionInputs& in, const torch::Tensor& mstep_col,
    int mstepmax, int n, double dtcld, const SubstepAdvectionParams& p) {
    const char* selected = std::getenv("KDM6_QR_TRANSPORT");
    const std::string mode = selected == nullptr ? "legacy" : selected;
    TORCH_CHECK(mode.empty() || mode == "legacy" || mode == "actual_departure",
                "unknown QR transport mode: ", mode);
    if (mode.empty() || mode == "legacy")
        return legacy_main_substep(in, mstep_col, mstepmax, n, dtcld, p);
    const char* ice = std::getenv("KDM6_ICE_FACTORIAL_MODE");
    TORCH_CHECK(ice != nullptr && std::string(ice) == "norm_actual",
                "actual QR candidate requires explicit norm_actual ice mode");
    check_actual_qr_entry(in, mstep_col, dtcld, p.qcrmin);
    // Other main fields retain the exact existing update. The old QR result is
    // replaced, not added a second time. All QR inputs are original entry tensors.
    auto out = legacy_main_substep(in, mstep_col, mstepmax, n, dtcld, p);
    auto count = torch::clamp(mstep_col, 1.0);
    auto gate = (count >= static_cast<double>(n)).to(in.state.qr.dtype());
    std::vector<torch::Tensor> qr, fall;
    torch::Tensor prev_departure;
    for (int64_t k = 0; k < in.state.qr.size(-1); ++k) {
        auto entry = in.state.qr.select(-1,k);
        auto rho = in.dend.select(-1,k);
        auto dz = in.delz.select(-1,k);
        auto work = in.work1_qr.select(-1,k);
        auto falk = (rho * entry * work / count * gate).to(in.state.qr.scalar_type());
        auto departure = torch::minimum(falk * dtcld / rho, entry);
        torch::Tensor arrival = torch::zeros_like(departure);
        if (k > 0)
            arrival = prev_departure * (in.dend.select(-1,k-1) * in.delz.select(-1,k-1)) / (rho * dz);
        auto after = entry - departure + arrival;
        auto fall_before = in.fall_qr_in.select(-1,k);
        auto fall_after = fall_before + departure * rho / dtcld;
        qr.push_back(after);
        fall.push_back(fall_after);
        trace_actual_qr(n, k, dtcld, count, gate, rho, dz, work, entry, after,
                        departure, arrival, fall_before, fall_after);
        prev_departure = departure;
    }
    out.state.qr = torch::stack(qr, -1);
    out.fall_qr = torch::stack(fall, -1);
    return out;
}
// END generated QR-only actual-departure candidate
"""


def render_overlay(source_root: Path, base_overlay: Path):
    original = validate_base_overlay(source_root, base_overlay)
    rendered = dict(original)
    source = original["sedimentation.cpp"].decode()
    if MARKER in source:
        raise ValueError("candidate already present")
    source = replace_once(
        source,
        '#include "kdm6/ops.h"\n',
        '#include "kdm6/ops.h"\n#include <cmath>\n#include <cstdlib>\n#include <fstream>\n#include <iomanip>\n#include <locale>\n',
        "candidate includes",
    )
    source = replace_once(
        source,
        "SubstepAdvectionOutputs substep_advection_torch(\n",
        "SubstepAdvectionOutputs legacy_main_substep(\n",
        "preserved Legacy entry",
    )
    anchor = "// ═══════════════════════════════════════════════════════════════════════════\n// E4: Ice substep\n"
    source = replace_once(source, anchor, HELPER + "\n" + anchor, "candidate wrapper")
    rendered["sedimentation.cpp"] = source.encode()
    return rendered, {
        "schema": "kdm6.actual_qr_overlay.v1",
        "producer_sha256": sha256_bytes(Path(__file__).read_bytes()),
        "base_overlay_sha256": {k: sha256_bytes(v) for k, v in original.items()},
        "overlay_sha256": {k: sha256_bytes(v) for k, v in rendered.items()},
        "mode_environment": MODE_ENV,
        "candidate_mode": "actual_departure",
        "default": "legacy",
        "required_ice_mode": "norm_actual",
        "changed_translation_units": ["sedimentation.cpp"],
        "scope": "QR mass state/fall only; NR and other species retain Legacy main equations; fp64 opt-in, no operational install",
    }


def create_overlay(source_root: Path, base_overlay: Path, output: Path):
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("output must be new")
    if paths_overlap(output, source_root) or paths_overlap(output, base_overlay):
        raise ValueError("output overlaps source/input tree")
    rendered, manifest = render_overlay(source_root, base_overlay)
    output.mkdir(parents=True)
    for name, data in rendered.items():
        with (output / name).open("xb") as stream:
            stream.write(data)
    with (output / "source_sha256.json").open("x") as stream:
        json.dump(manifest, stream, indent=2)
        stream.write("\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--base-overlay", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        create_overlay(args.source_root, args.base_overlay, args.output)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
