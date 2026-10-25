"""Add a value-only block22 observer to the receipt-pinned research coordinator.

The observer never supplies a value to physics or AD. Actual value/first-order
noninterference must be measured separately against the unmodified library.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from harness.make_rain_boundary_overlay import replace_once

SOURCE_SHA256 = "373e77cc9f81bd77603c6993a53cd8dfd5e9b3b401da6e102d90bc16028f280e"
TRACE_ENV = "KDM6_BLOCK22_ACTIVATION_TRACE"
MARKER = "// BEGIN generated block22 activation observer"

HELPER = r'''// BEGIN generated block22 activation observer
thread_local std::uint64_t activation_trace_call = 0;
thread_local std::uint64_t activation_schedule_call = 0;
thread_local double activation_trace_dt = 0.0;
bool activation_trace_enabled() {
    const char* path = std::getenv("KDM6_BLOCK22_ACTIVATION_TRACE");
    return path != nullptr && *path != '\0';
}
void activation_trace_begin(double dt) {
    if (activation_trace_enabled()) {
        ++activation_trace_call;
        activation_trace_dt = dt;
    }
}
void trace_activation(const char* stage, double dt,
    std::initializer_list<std::pair<const char*, torch::Tensor>> fields) {
    if (!activation_trace_enabled()) return;
    // Explicit value-only observer. Nothing extracted here returns to physics.
    torch::NoGradGuard guard;
    TORCH_CHECK(activation_trace_call > 0, "activation trace has no microphysics context");
    std::ofstream out(std::getenv("KDM6_BLOCK22_ACTIVATION_TRACE"), std::ios::app);
    TORCH_CHECK(out.good(), "cannot append activation trace");
    out.imbue(std::locale::classic());
    out << std::setprecision(17);
    if (out.tellp() == 0) out << "call\tstage\trow0\tlevel_bottom0\tdt_s\tfield\tkind\tvalue\n";
    for (const auto& field : fields) {
        const auto& value = field.second;
        TORCH_CHECK(value.dim() == 2 && value.size(0) == 512 && value.size(1) == 39,
                    "activation observer requires original B512 by39");
        TORCH_CHECK(value.scalar_type() == torch::kFloat64 || value.scalar_type() == torch::kBool,
                    "activation observer requires fp64/bool fields");
        for (int k : {4,16,17,18}) {
            out << activation_trace_call << '\t' << stage << "\t368\t" << k << '\t'
                << dt << '\t' << field.first << '\t'
                << (value.scalar_type() == torch::kBool ? "bool" : "f64") << '\t'
                << value.select(0,368).select(0,k).item<double>() << '\n';
        }
        if (value.scalar_type() == torch::kBool) {
            // Packed row-major boolean diagnostics for all 512x39 cells.
            // These are observer-only comparisons of actual operands.
            auto packed = value.contiguous().cpu();
            const bool* bits = packed.data_ptr<bool>();
            const char* hex = "0123456789abcdef";
            out << activation_trace_call << '\t' << stage << "\t-1\t-1\t" << dt
                << '\t' << field.first << "\tbits\t";
            for (int i=0; i<512*39; i+=8) {
                unsigned byte=0;
                for (int j=0; j<8 && i+j<512*39; ++j) if (bits[i+j]) byte |= 1u<<j;
                out << hex[byte>>4] << hex[byte&15];
            }
            out << '\n';
        }
    }
    TORCH_CHECK(out.good(), "failed writing activation trace");
}
void trace_activation_schedule(const torch::Tensor& main, int mainmax,
    const torch::Tensor& ice, int icemax, double dt) {
    if (!activation_trace_enabled()) return;
    torch::NoGradGuard guard;
    ++activation_schedule_call;
    TORCH_CHECK(main.dim()==1 && ice.dim()==1 && main.size(0)==512 && ice.size(0)==512,
                "schedule observer requires original B512");
    std::ofstream out(std::getenv("KDM6_BLOCK22_ACTIVATION_TRACE"), std::ios::app);
    TORCH_CHECK(out.good(), "cannot append activation schedule");
    out.imbue(std::locale::classic());
    out << std::setprecision(17);
    if (out.tellp()==0) out << "call\tstage\trow0\tlevel_bottom0\tdt_s\tfield\tkind\tvalue\n";
    for (int b=-1; b<512; ++b) {
        out << activation_schedule_call << "\tschedule\t" << b << "\t-1\t" << dt
            << '\t' << (b<0 ? "mstepmax_main" : "mstep_main") << "\tf64\t"
            << (b<0 ? double(mainmax) : main.select(0,b).item<double>()) << '\n';
        out << activation_schedule_call << "\tschedule\t" << b << "\t-1\t" << dt
            << '\t' << (b<0 ? "mstepmax_ice" : "mstep_ice") << "\tf64\t"
            << (b<0 ? double(icemax) : ice.select(0,b).item<double>()) << '\n';
    }
    TORCH_CHECK(out.good(), "failed writing activation schedule");
}
// END generated block22 activation observer
'''


def trace(stage, fields, dt="dtcld"):
    entries = ", ".join('{"' + name + '", ' + expression + '}' for name, expression in fields)
    return f'    trace_activation("{stage}", {dt}, {{{entries}}});\n'


def state_fields(name):
    return [(key, name + "." + key) for key in ("t", "qv", "qc", "nc", "nccn")]


def instrument_coordinator(source):
    if MARKER in source:
        raise ValueError("activation observer already present")
    def insert(anchor, addition, label):
        nonlocal source
        source = replace_once(source, anchor, anchor + addition, label)

    insert('#include "kdm6/coordinator.h"\n',
           '#include <initializer_list>\n#include <utility>\n', "observer includes")
    insert("namespace kdm6 {\n\nnamespace {\n", HELPER + "\n", "observer helpers")
    source = replace_once(source, "    auto state_pre = state;\n",
        "    activation_trace_begin(dtcld);\n" + trace("micro_entry", state_fields("state"))
        + "    auto state_pre = state;\n", "microphysics invocation")
    insert("        /*midpoint_trace=*/full_params.midpoint_trace\n    );\n",
           trace("post_state_update", state_fields("new_state")), "post-state-update")
    for statement, stage in [
        ("    new_state = reclassify_large_ice_to_snow(new_state, forcing.dend);\n", "post_reclass_ice"),
        ("    new_state = reclassify_small_rain_to_cloud(new_state, forcing.dend);\n", "post_reclass_rain"),
        ("    new_state = apply_threshold_cleanup(new_state);\n", "post_threshold"),
        ("                                          /*qcrmin=*/1.0e-9, /*ncmin_tensor=*/ncmin_for_slope);\n", "post_final_dsd"),
    ]:
        insert(statement, trace(stage, state_fields("new_state")), stage)
    insert("    auto qs1 = thermo::compute_qs_water(state.t, forcing.p, thermo_params);\n",
           trace("activation_entry", state_fields("state") + [("qs1", "qs1"),
                 ("p", "forcing.p"), ("rho_d", "forcing.dend"), ("xl", "xl"), ("cpm", "cpm_safe")]),
           "actual activation entry")
    insert("        ops::safe_pow(sw_ratio, constants::ACTK)  // libm pow (bit-matches gfortran on float32)\n    );\n",
           trace("activation_fraction", [(n, n) for n in ("qs1_safe", "sw_percent", "sw_ratio", "activated_fraction")]
                 + [("sw_positive", "sw_percent > 0.0"), ("sw_at_zero", "sw_percent == 0.0"),
                    ("fraction_saturated", "activated_fraction >= 1.0"), ("sw_ratio_at_one", "sw_ratio == 1.0")]),
           "activation fraction")
    insert("    auto ncact = torch::minimum(ncact_raw, torch::clamp(state.nccn, /*min=*/0.0) / dtcld);\n",
           trace("activation_pre_gate", [("ncact_raw", "ncact_raw"), ("ncact_capped", "ncact"),
                 ("raw_zero", "ncact_raw <= 0.0"),
                 ("reservoir_tie", "ncact_raw == torch::clamp(state.nccn, 0.0) / dtcld"),
                 ("reservoir_cap", "ncact_raw > torch::clamp(state.nccn, 0.0) / dtcld")]),
           "number cap before gate")
    insert("    auto pcact = torch::minimum(pcact_raw, torch::clamp(state.qv, /*min=*/0.0) / dtcld);\n",
           trace("activation_gated", [("ncact", "ncact"), ("pcact_raw", "pcact_raw"), ("pcact", "pcact"),
                 ("qv_cap_tie", "pcact_raw == torch::clamp(state.qv, 0.0) / dtcld"),
                 ("qv_cap", "pcact_raw > torch::clamp(state.qv, 0.0) / dtcld")]), "gated actual rates")
    insert("    auto qs1_pp = thermo::compute_qs_water(t_pp, forcing.p, thermo_params);\n",
           trace("post_activation", [(n, n) for n in ("qv_pp_raw", "qv_pp", "qc_pp", "t_pp", "nc_pp", "nccn_pp", "qs1_pp")]),
           "post-activation state")
    insert("    auto nccn_final = torch::clamp(nccn_final_raw, constants::NCCN_MIN, constants::NCCN_MAX);\n",
           trace("post_satadj", [(n, n) for n in ("qv_final", "qc_final", "t_final", "nc_final", "nccn_final_raw", "nccn_final", "nc_evap_amount")]
                 + [("pcond", "sat.pcond"), ("complete_evap", "sat.cloud_complete_evap"),
                    ("pcond_positive", "sat.pcond > 0.0"),
                    ("nccn_below_min", "nccn_final_raw < constants::NCCN_MIN"),
                    ("nccn_at_min", "nccn_final_raw == constants::NCCN_MIN"),
                    ("nccn_at_max", "nccn_final_raw == constants::NCCN_MAX"),
                    ("nccn_above_max", "nccn_final_raw > constants::NCCN_MAX")]), "satadj and reservoir results")
    # Observe the actual threshold masks. No new comparison enters the returned state.
    insert("    auto keep_qg = (state.qg > qcrmin).to(dtype);\n",
           trace("threshold_masks", [(n, n + " != 0") for n in ("keep_qc", "keep_qi", "keep_qr", "keep_qs", "keep_qg")],
                 dt="activation_trace_dt"), "threshold masks")
    insert("    auto nc_at_max = den * state.qc * std::pow(constants::LAMDACMAX, constants::DMC) / pidnc;\n",
           trace("final_dsd_before_absolute_cap", [("nc_before", "state.nc"),
                 ("nc_snapped", "nc_snapped"), ("nc_gated", "nc_new"),
                 ("ncmin", "ncmin_t"), ("nc_at_max", "nc_at_max"),
                 ("nc_snap_gate", "state.nc >= ncmin_t"),
                 ("nc_snap_changed", "nc_snapped != state.nc"),
                 ("nc_at_absolute_max", "nc_new == constants::NCMAX"),
                 ("nc_absolute_cap_would_apply", "nc_new > constants::NCMAX")],
                 dt="activation_trace_dt"), "final cloud DSD gates")
    start = source.index("SedimentationOutputs sedimentation_chain(")
    part = source[start:]
    part = replace_once(part, "    const int64_t K = state.qr.size(-1);\n",
        "    trace_activation_schedule(mstep_col_main, mstepmax_main, mstep_col_ice, mstepmax_ice, dtcld);\n"
        + "    const int64_t K = state.qr.size(-1);\n", "actual sedimentation schedule")
    return source[:start] + part


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coordinator", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output_dir.exists() or args.output_dir.is_symlink():
        raise FileExistsError("observer output directory must be new")
    source = args.coordinator.read_bytes()
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError("coordinator is not the receipt-pinned actual-QR source")
    output = instrument_coordinator(source.decode()).encode()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    with (args.output_dir / "coordinator.cpp").open("xb") as stream:
        stream.write(output)
    receipt = {"schema": "kdm6.block22_activation_observer.v1", "source_sha256": SOURCE_SHA256,
               "coordinator_sha256": hashlib.sha256(output).hexdigest(),
               "producer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "trace_env": TRACE_ENV, "B": 512, "L": 39, "row0": 368,
               "levels_bottom0": [4, 16, 17, 18], "scope": "value-only observer; noninterference requires separate measured evidence"}
    with (args.output_dir / "source_receipt.json").open("x") as stream:
        stream.write(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
