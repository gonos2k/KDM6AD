"""Generate a three-cell value observer over the frozen actual-QR candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from harness import make_actual_qr_overlay as candidate
from harness.make_rain_boundary_overlay import paths_overlap, replace_once, sha256_bytes

TRACE_ENV = "KDM6_APPLIED_TRANSFER_TRACE"
CHUNK_ENV = "KDM6_APPLIED_TRANSFER_CHUNK"
MARKER = "// BEGIN generated applied transfer observer"
TUS = (
    "runtime.cpp",
    "coordinator.cpp",
    "sedimentation.cpp",
    "sedimentation_conservative.cpp",
)

HELPER = r"""// BEGIN generated applied transfer observer
thread_local std::uint64_t applied_transfer_call = 0;
bool applied_transfer_enabled() {
    const char* path = std::getenv("KDM6_APPLIED_TRANSFER_TRACE");
    return path != nullptr && *path != '\0';
}
void applied_transfer_begin() {
    if (applied_transfer_enabled()) ++applied_transfer_call;
}
void trace_applied_transfer(const std::string& stage, int group, double dt,
    std::initializer_list<std::pair<const char*, torch::Tensor>> fields) {
    if (!applied_transfer_enabled()) return;
    // Explicit value-only serialization. No tensor or scalar from this helper
    // is returned to the live physics/AD path.
    torch::NoGradGuard guard;
    const char* chunk_env = std::getenv("KDM6_APPLIED_TRANSFER_CHUNK");
    TORCH_CHECK(chunk_env != nullptr, "missing applied transfer chunk");
    const std::string chunk_text(chunk_env);
    TORCH_CHECK(chunk_text == "34" || chunk_text == "40", "unsupported trace block");
    const int chunk = chunk_text == "34" ? 34 : 40;
    const int column = chunk == 34 ? 281 : 250;
    const std::vector<int> levels = chunk == 34 ? std::vector<int>{17,18} : std::vector<int>{17};
    TORCH_CHECK(applied_transfer_call > 0, "trace has no microphysics context");
    for (const auto& field : fields) {
        const auto& value = field.second;
        TORCH_CHECK(value.dim() == 2 && value.size(0) == 512 && value.size(1) == 39,
                    "transfer trace requires original B512 by39 native state");
        TORCH_CHECK(value.scalar_type() == torch::kFloat64 || value.scalar_type() == torch::kBool,
                    "transfer trace requires fp64/bool fields");
    }
    std::ofstream out(std::getenv("KDM6_APPLIED_TRANSFER_TRACE"), std::ios::out | std::ios::app);
    TORCH_CHECK(out.good(), "cannot append applied transfer trace");
    out.imbue(std::locale::classic());
    out << std::setprecision(17);
    if (out.tellp() == 0) out << "call\tstage\tgroup\tchunk\tcolumn\tlevel_bottom0\tdt\tfield\tvalue\n";
    for (const int k : levels) {
        for (const auto& field : fields) {
            out << applied_transfer_call << '\t' << stage << '\t' << group << '\t'
                << chunk << '\t' << column << '\t' << k << '\t' << dt << '\t'
                << field.first << '\t' << field.second.select(0,column).select(0,k).item<double>() << '\n';
        }
    }
    TORCH_CHECK(out.good(), "failed writing applied transfer trace");
}
// END generated applied transfer observer
"""


def trace(stage, fields, *, group="0", indent="    "):
    values = ", ".join('{"' + name + '", ' + expr + "}" for name, expr in fields)
    return (
        indent + f'trace_applied_transfer("{stage}", {group}, dtcld, {{{values}}});\n'
    )


def water(s):
    return [(name, f"{s}.{name}") for name in ("qv", "qc", "qr", "qi", "qs", "qg", "t")]


def rates(w, c, m):
    return [
        (name, f"{c}.{name}")
        for name in ("psdep", "pgdep", "psevp", "pgevp", "pinud", "pidep")
    ] + [("prevp", f"{w}.prevp"), ("pseml", f"{m}.pseml"), ("pgeml", f"{m}.pgeml")]


def instrument_coordinator(text):
    if MARKER in text:
        raise ValueError("observer already present")
    text = replace_once(
        text,
        '#include "kdm6/coordinator.h"\n',
        '#include "kdm6/coordinator.h"\n#include <cstdint>\n#include <initializer_list>\n#include <utility>\n',
        "observer includes",
    )
    text = replace_once(
        text,
        "namespace kdm6 {\n\nnamespace {\n",
        "namespace kdm6 {\n\nnamespace {\n" + HELPER + "\n",
        "observer helper",
    )
    text = replace_once(
        text,
        "    auto state_pre = state;\n",
        "    applied_transfer_begin();\n"
        + trace(
            "micro_entry",
            water("state") + [("rho", "forcing.dend"), ("delz", "forcing.delz")],
        )
        + "    auto state_pre = state;\n",
        "micro entry",
    )
    text = replace_once(
        text,
        "    auto scaled = scale_rates_for_conservation(\n",
        trace(
            "pre_limits",
            water("working")
            + rates("warm_out", "cold_out", "mf5")
            + [("supcol", "pre2.supcol")],
        )
        + "    auto scaled = scale_rates_for_conservation(\n",
        "group pre",
    )
    anchor = "        cold_params.cloud_water_riming.ncmin_tensor\n    );\n"
    text = replace_once(
        text,
        anchor,
        anchor
        + trace(
            "post_limits",
            water("working")
            + rates("scaled.warm", "scaled.cold", "scaled.mf")
            + [("supcol", "pre2.supcol")],
        ),
        "group post",
    )
    anchor = "        /*midpoint_trace=*/full_params.midpoint_trace\n    );\n    // BRS density re-clamp #4"
    text = replace_once(
        text,
        anchor,
        "        /*midpoint_trace=*/full_params.midpoint_trace\n    );\n"
        + trace("post_state_update", water("new_state"))
        + "    // BRS density re-clamp #4",
        "actual state update result",
    )
    for statement, stage in [
        (
            "    new_state = reclassify_large_ice_to_snow(new_state, forcing.dend);\n",
            "post_reclass_ice",
        ),
        (
            "    new_state = reclassify_small_rain_to_cloud(new_state, forcing.dend);\n",
            "post_reclass_rain",
        ),
        ("    new_state = apply_threshold_cleanup(new_state);\n", "post_threshold"),
    ]:
        text = replace_once(
            text, statement, statement + trace(stage, water("new_state")), stage
        )
    anchor = "        dtcld\n    );\n\n    // F1h: paired threshold cleanup"
    text = replace_once(
        text,
        anchor,
        "        dtcld\n    );\n"
        + trace("post_satadj", water("new_state"))
        + "\n    // F1h: paired threshold cleanup",
        "actual satadj result",
    )
    anchor = "                                          /*qcrmin=*/1.0e-9, /*ncmin_tensor=*/ncmin_for_slope);\n"
    text = replace_once(
        text,
        anchor,
        anchor + trace("micro_exit", water("new_state")),
        "final DSD boundary",
    )
    start = text.index("ConservedRates scale_rates_for_conservation(")
    end = text.index("CoordinatorState state_update(", start)
    part = text[start:end]
    part = replace_once(
        part,
        "    auto dtype = state.qc.dtype();\n",
        "    int transfer_group = 0;\n    auto dtype = state.qc.dtype();\n",
        "group counter",
    )
    anchor = "        for (auto* r : rates) { *r = *r * factor; }\n"
    if part.count(anchor) != 2:
        raise RuntimeError("expected two limiter lambdas")
    fields = [
        (name, f"cold.{name}") for name in ("psdep", "pgdep", "psevp", "pgevp")
    ] + [(name, name) for name in ("value", "source", "factor", "gate")]
    logging = (
        "        ++transfer_group;\n"
        + trace("limiter_before", fields, group="transfer_group", indent="        ")
        + anchor
        + trace("limiter_after", fields, group="transfer_group", indent="        ")
    )
    part = part.replace(anchor, logging)
    text = text[:start] + part + text[end:]
    start = text.index("CoordinatorState state_update(")
    end = text.index("CoordinatorState apply_satadj_step(", start)
    part = text[start:end]
    raw = [(q, q + "_new") for q in ("qv", "qc", "qr", "qi", "qs", "qg")] + [
        (q + "_before", "state." + q) for q in ("qv", "qc", "qr", "qi", "qs", "qg")
    ]
    raw += [
        (name, name)
        for name in (
            "dqv_sum",
            "dqc_rate_sum",
            "dqc_amount",
            "dqr_rate_sum",
            "dqr_amount",
            "dqi_rate_sum",
            "dqi_amount",
            "dqs_sum",
            "dqg_rate_sum",
            "dqg_amount",
            "cold_mask",
            "warm_mask",
            "delta2",
            "delta3",
        )
    ]
    raw += rates("warm", "cold", "mf") + [("supcol", "pre.supcol")]
    anchor = "    return CoordinatorState{\n        // §53t: NO qv clamp"
    part = replace_once(
        part, anchor, trace("state_update_raw", raw) + anchor, "raw preclamp update"
    )
    return text[:start] + part + text[end:]


def render_overlay(source_root, factorial_base, actual_base):
    expected, _ = candidate.render_overlay(Path(source_root), Path(factorial_base))
    original = {name: (Path(actual_base) / name).read_bytes() for name in TUS}
    if original != expected:
        raise ValueError("actual base does not match pinned candidate rendering")
    result = dict(original)
    result["coordinator.cpp"] = instrument_coordinator(
        original["coordinator.cpp"].decode()
    ).encode()
    return result, {
        "schema": "kdm6.applied_transfer_overlay.v1",
        "producer_sha256": sha256_bytes(Path(__file__).read_bytes()),
        "candidate_generator_sha256": sha256_bytes(
            Path(candidate.__file__).read_bytes()
        ),
        "base_sha256": {k: sha256_bytes(v) for k, v in original.items()},
        "overlay_sha256": {k: sha256_bytes(v) for k, v in result.items()},
        "changed_TUs": ["coordinator.cpp"],
        "trace_environment": TRACE_ENV,
        "chunk_environment": CHUNK_ENV,
        "targets": {
            "34": {"column": 281, "levels_bottom0": [17, 18]},
            "40": {"column": 250, "levels_bottom0": [17]},
        },
        "physics_changed": False,
        "scope": "phase-capped group-pre/limited rates and actual coordinator boundaries only; no uncapped C4/D2-D3 attempt attribution",
    }


def create_overlay(source_root, factorial_base, actual_base, output):
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("output must be new")
    if any(
        paths_overlap(output, Path(p))
        for p in [source_root, factorial_base, actual_base]
    ):
        raise ValueError("output overlaps source/base")
    result, meta = render_overlay(source_root, factorial_base, actual_base)
    output.mkdir(parents=True)
    for name, data in result.items():
        with (output / name).open("xb") as out:
            out.write(data)
    with (output / "source_sha256.json").open("x") as out:
        json.dump(meta, out, indent=2)
        out.write("\n")
    return meta


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ["source-root", "factorial-base", "actual-base", "output"]:
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    try:
        create_overlay(a.source_root, a.factorial_base, a.actual_base, a.output)
    except (OSError, ValueError, RuntimeError) as exc:
        p.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
