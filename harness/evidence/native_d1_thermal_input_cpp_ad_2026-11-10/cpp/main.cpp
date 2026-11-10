// Full captured f64 kdm6_fn path with a live, test-only pre2 QG/BRS hook.
#include "kdm6/runtime.h"
#include <torch/torch.h>
#include <torch/csrc/autograd/autograd.h>
#include <array>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace kdm6::testing {
void enable_pre2_input_hook(bool enabled);
std::pair<torch::Tensor, torch::Tensor> pre2_input_hook_values();
std::map<std::string, torch::Tensor> stage_hook_values();
}
namespace {
using torch::Tensor;
constexpr int K = 39, STATE = 12, FORCING = 4;
constexpr int QG17 = 6 * K + 16, BRS17 = 11 * K + 16;
constexpr int TH16 = 15, QV16 = K + 15, PII16 = K + 15;
const auto F64 = torch::TensorOptions().dtype(torch::kFloat64).device(torch::kCPU);
const auto F32 = torch::TensorOptions().dtype(torch::kFloat32).device(torch::kCPU);

void need(bool ok, const std::string& why) { if (!ok) throw std::runtime_error(why); }
std::string word(double value) {
    std::uint64_t bits;
    std::memcpy(&bits, &value, sizeof(bits));
    std::ostringstream out;
    out << std::hex << bits;
    return out.str();
}
void emit(std::ostream& out, const std::vector<double>& a) {
    out << '[';
    for (std::size_t i = 0; i < a.size(); ++i) {
        if (i) out << ',';
        out << std::setprecision(17) << a[i];
    }
    out << ']';
}
void emit_words(std::ostream& out, const std::vector<double>& a) {
    out << '[';
    for (std::size_t i = 0; i < a.size(); ++i) {
        if (i) out << ',';
        out << '"' << word(a[i]) << '"';
    }
    out << ']';
}
std::vector<double> values(const Tensor& t) {
    auto flat = t.contiguous().to(torch::kCPU);
    const auto* p = flat.data_ptr<double>();
    return {p, p + flat.numel()};
}
double stage_scalar(const Tensor& t) {
    need(t.dim() == 2 && t.size(0) == 1 && t.size(1) == K, "stage tensor shape");
    auto selected = t[0][15].contiguous().to(torch::kCPU);
    if (selected.scalar_type() == torch::kBool) return *selected.data_ptr<bool>() ? 1.0 : 0.0;
    need(selected.scalar_type() == torch::kFloat64, "stage tensor dtype");
    return *selected.data_ptr<double>();
}
void emit_stage_scalars(std::ostream& out, const std::map<std::string, Tensor>& stages) {
    out << '{';
    bool first = true;
    for (const auto& entry : stages) {
        if (!first) out << ',';
        first = false;
        out << '"' << entry.first << "\":" << std::setprecision(17) << stage_scalar(entry.second);
    }
    out << '}';
}
void emit_stage_types(std::ostream& out, const std::map<std::string, Tensor>& stages) {
    out << '{';
    bool first = true;
    for (const auto& entry : stages) {
        if (!first) out << ',';
        first = false;
        const auto type = entry.second.scalar_type();
        need(type == torch::kFloat64 || type == torch::kBool, "stage type inventory");
        out << '"' << entry.first << "\":\"" << (type == torch::kBool ? "bool" : "f64") << '"';
    }
    out << '}';
}
double stage_value(const std::map<std::string, Tensor>& stages, const std::string& name) {
    const auto it = stages.find(name);
    need(it != stages.end(), "missing thermal diagnostic stage: " + name);
    return stage_scalar(it->second);
}
double dot_values(const std::vector<double>& a, const std::vector<double>& b) {
    need(a.size() == b.size(), "thermal VJP dot shape");
    double out = 0.0;
    for (std::size_t i = 0; i < a.size(); ++i) out += a[i] * b[i];
    return out;
}
void emit_thermal_endpoint(std::ostream& out,
                           const std::map<std::string, Tensor>& stages,
                           const std::map<std::string, Tensor>& baseline,
                           double th16, double qv16, double pii16) {
    const auto d1 = [&](const char* name) {
        return stage_value(stages, std::string("d1_melt_producer.") + name);
    };
    const double activated = stage_value(stages, "fd_satadj_inner.activated_fraction");
    const bool psmlt_raw = d1("psmlt_dt") == d1("psmlt_capped");
    const bool pgmlt_raw = d1("pgmlt_dt") == d1("pgmlt_capped");
    const bool warm = d1("warm") != 0.0;
    const bool snow_active = d1("snow_active") != 0.0;
    const bool graupel_active = d1("graupel_active") != 0.0;
    const bool graupel_mask = stage_value(stages, "d1_entry_coeres_inputs.graupel_mask") != 0.0;
    const bool activation_at_upper = activated >= 1.0;
    const bool base_activation_at_upper =
        stage_value(baseline, "fd_satadj_inner.activated_fraction") >= 1.0;
    const double qs = d1("qs");
    const double qg = d1("qg");
    const double psmlt_capped = d1("psmlt_capped");
    const double pgmlt_capped = d1("pgmlt_capped");
    out << "{\"input\":{\"th16\":" << std::setprecision(17) << th16
        << ",\"qv16\":" << qv16 << ",\"pii16\":" << pii16
        << ",\"physical_t16\":" << th16 * pii16 << "},\"d1_branch\":{\"warm\":"
        << (warm ? "true" : "false") << ",\"snow_active\":" << (snow_active ? "true" : "false")
        << ",\"graupel_active\":" << (graupel_active ? "true" : "false")
        << ",\"graupel_mask\":" << (graupel_mask ? "true" : "false")
        << ",\"psmlt_cap_is_raw_candidate\":" << (psmlt_raw ? "true" : "false")
        << ",\"pgmlt_cap_is_raw_candidate\":" << (pgmlt_raw ? "true" : "false")
        << ",\"t\":" << d1("t") << ",\"t1\":" << d1("t1")
        << ",\"temperature_margin_k\":" << d1("t") - d1("t0c")
        << ",\"qs\":" << qs << ",\"qg\":" << qg
        << ",\"psmlt_capped\":" << psmlt_capped << ",\"pgmlt_capped\":" << pgmlt_capped
        << ",\"snow_mass_reserve\":" << qs + psmlt_capped
        << ",\"graupel_mass_reserve\":" << qg + pgmlt_capped
        << ",\"cpm_used\":" << d1("cpm") << ",\"n0sfac\":" << d1("n0sfac")
        << ",\"work2\":" << d1("work2") << ",\"pgmlt_raw\":" << d1("pgmlt_raw")
        << "},\"activation\":{\"sw_percent\":"
        << stage_value(stages, "fd_satadj_inner.sw_percent")
        << ",\"activated_fraction\":" << activated
        << ",\"activation_fraction_at_upper_bound\":" << (activation_at_upper ? "true" : "false")
        << ",\"activation_upper_bound_changed_vs_baseline\":"
        << (activation_at_upper != base_activation_at_upper ? "true" : "false")
        << ",\"ncact_raw\":" << stage_value(stages, "fd_satadj_inner.ncact_raw")
        << ",\"ncact\":" << stage_value(stages, "fd_satadj_inner.ncact")
        << ",\"nccn_floor_active\":"
        << (stage_value(stages, "fd_satadj_inner.nccn_floor_active") != 0.0 ? "true" : "false")
        << ",\"nccn_cap_active\":"
        << (stage_value(stages, "fd_satadj_inner.nccn_cap_active") != 0.0 ? "true" : "false")
        << "}}";
}
struct Input {
    std::array<double, STATE * K> state{};
    std::array<double, FORCING * K> forcing{};
    float xland = 0;
    double dt = 0;
    explicit Input(const char* path) {
        std::ifstream f(path, std::ios::binary);
        need(static_cast<bool>(f), "input binary unavailable");
        char magic[15];
        f.read(magic, sizeof(magic));
        need(f.gcount() == static_cast<std::streamsize>(sizeof(magic))
             && std::memcmp(magic, "KDM6_PRE2_INPUT", sizeof(magic)) == 0,
             "input binary magic");
        f.read(reinterpret_cast<char*>(state.data()), sizeof(double) * state.size());
        need(static_cast<bool>(f), "truncated state input");
        f.read(reinterpret_cast<char*>(forcing.data()), sizeof(double) * forcing.size());
        need(static_cast<bool>(f), "truncated forcing input");
        f.read(reinterpret_cast<char*>(&xland), sizeof(xland));
        f.read(reinterpret_cast<char*>(&dt), sizeof(dt));
        need(static_cast<bool>(f) && f.peek() == EOF, "input binary length");
        need(dt == 20.0 && xland == 2.0f, "selected native controls");
        for (auto v : state) need(std::isfinite(v), "nonfinite state input");
        for (auto v : forcing) need(std::isfinite(v), "nonfinite forcing input");
    }
};
Tensor double_reverse_jvp(const Tensor& y, const Tensor& x, const Tensor& v) {
    auto u = torch::zeros_like(y).requires_grad_(true);
    auto jt = torch::autograd::grad({(y * u).sum()}, {x}, {}, true, true, false)[0];
    return torch::autograd::grad({(jt * v).sum()}, {u}, {}, true, false, false)[0];
}
struct Eval {
    Tensor final;
    Tensor pre2_qg;
    Tensor pre2_brs;
    Tensor selected;
    std::map<std::string, Tensor> stages;
};
struct Map {
    Tensor forcing;
    Tensor xland;
    double dt;
    explicit Map(const Input& in)
        : forcing(torch::from_blob(const_cast<double*>(in.forcing.data()), {FORCING, K}, F64).clone()),
          xland(torch::from_blob(const_cast<float*>(&in.xland), {1}, F32).clone()), dt(in.dt) {}
    Eval operator()(const Tensor& x, bool hook) const {
        need(x.sizes() == torch::IntArrayRef({STATE, K}) && x.scalar_type() == torch::kFloat64,
             "packed f64 state shape");
        const auto s = [&](int i) { return x[i].unsqueeze(0); };
        kdm6::State state{s(0),s(1),s(2),s(3),s(4),s(5),s(6),s(7),s(8),s(9),s(10),s(11)};
        const auto f = [&](int i) { return forcing[i].unsqueeze(0); };
        kdm6::Forcing forc{f(0),f(1),f(2),f(3)};
        kdm6::testing::enable_pre2_input_hook(hook);
        auto result = kdm6::kdm6_fn(state, forc, kdm6::make_parameters(0), dt,
                                    xland, 10.0, 10.0, kdm6::PhysicsOptions{}, false);
        std::vector<Tensor> out;
        for (auto* field : result.state_out.fields()) out.push_back(field->squeeze(0));
        auto packed = torch::stack(out);
        if (!hook) return Eval{packed, Tensor(), Tensor(), Tensor(), {}};
        auto [qg, brs] = kdm6::testing::pre2_input_hook_values();
        need(qg.defined() && brs.defined() && qg.sizes() == torch::IntArrayRef({1, K})
             && brs.sizes() == qg.sizes(), "pre2 live hook tensors");
        // Packed C ABI level 16 is index 15; capture k_zero is 23.
        auto selected = torch::stack({qg[0][15], brs[0][15]});
        return Eval{packed, qg, brs, selected, kdm6::testing::stage_hook_values()};
    }
};
struct Direction {
    const char* name;
    int index;
    double seed;
};
struct ThermalDirection {
    const char* name;
    bool th16;
    bool qv16;
    const char* normalization;
    std::vector<double> steps;
};
}  // namespace

int main(int argc, char** argv) {
    try {
        need(argc == 2, "usage: native_pre2_input_ad INPUT_BIN");
        torch::set_num_threads(1);
        const Input in(argv[1]);
        const Map map(in);
        auto state0 = torch::from_blob(const_cast<double*>(in.state.data()), {STATE, K}, F64).clone();
        auto off = map(state0, false);
        auto x = state0.clone().requires_grad_(true);
        auto on = map(x, true);
        auto value_final = values(off.final);
        auto graph_final = values(on.final);
        auto pre2_qg = values(on.pre2_qg);
        auto pre2_brs = values(on.pre2_brs);
        auto selected = values(on.selected);
        std::vector<std::string> numeric_stage_names;
        std::vector<Tensor> numeric_stage_tensors;
        for (const auto& entry : on.stages) {
            if (entry.second.scalar_type() == torch::kFloat64) {
                numeric_stage_names.push_back(entry.first);
                numeric_stage_tensors.push_back(entry.second[0][15]);
            }
        }
        need(numeric_stage_names.size() >= 60, "process stage inventory");
        auto stage_output = torch::stack(numeric_stage_tensors);
        auto final_output = torch::stack({on.final[8][15], on.final[7][15]});
        need(value_final.size() == graph_final.size() && value_final.size() == STATE * K,
             "final state inventory");
        for (std::size_t i = 0; i < value_final.size(); ++i)
            need(word(value_final[i]) == word(graph_final[i]), "hook off/on full state changed");
        auto gq = torch::autograd::grad({on.selected[0]}, {x}, {}, true, false, false)[0];
        auto gb = torch::autograd::grad({on.selected[1]}, {x}, {}, true, false, false)[0];
        auto gnc = torch::autograd::grad({final_output[0]}, {x}, {}, true, false, false)[0];
        auto gnccn = torch::autograd::grad({final_output[1]}, {x}, {}, true, false, false)[0];
        const std::vector<std::string> thermal_vjp_names{
            "d1_melt_producer.t1",
            "d1_melt_producer.work2",
            "d1_melt_producer.psmlt_capped_g",
            "d1_melt_producer.pgmlt_raw",
        };
        std::vector<std::vector<double>> thermal_vjp_rows;
        for (const auto& name : thermal_vjp_names) {
            const auto it = on.stages.find(name);
            need(it != on.stages.end(), "missing selected thermal VJP stage: " + name);
            const auto gradient = torch::autograd::grad(
                {it->second[0][15]}, {x}, {}, true, false, false)[0];
            thermal_vjp_rows.push_back(values(gradient));
        }
        const auto directions = std::vector<Direction>{
            {"qg17_relative", QG17, in.state[QG17]},
            {"brs17_relative", BRS17, in.state[BRS17]},
            {"joint17_relative", -1, 0.0},
        };
        const std::vector<ThermalDirection> thermal_directions{
            {"th16_abs", true, false, "absolute K potential-temperature increment", {1.0e-2, 1.0e-3, 1.0e-4}},
            {"qv16_rel", false, true, "relative qv increment", {1.0e-3, 1.0e-4}},
            {"th16_abs_qv16_rel_joint", true, true,
             "joint: absolute K potential-temperature and relative qv increments", {1.0e-3, 1.0e-4}},
        };
        std::cout << "{\"schema\":\"kdm6.native_nc_process_graph_cpp_ad.v1\",\"stage_numeric_order\":[";
        for (std::size_t i = 0; i < numeric_stage_names.size(); ++i) {
            if (i) std::cout << ',';
            std::cout << '"' << numeric_stage_names[i] << '"';
        }
        std::cout << "],\"baseline\":{\"value_final_raw\":";
        emit_words(std::cout, value_final);
        std::cout << ",\"graph_final_raw\":";
        emit_words(std::cout, graph_final);
        std::cout << ",\"pre2_qg_raw\":";
        emit_words(std::cout, pre2_qg);
        std::cout << ",\"pre2_brs_raw\":";
        emit_words(std::cout, pre2_brs);
        std::cout << ",\"selected\":";
        emit(std::cout, selected);
        std::cout << ",\"stage_scalars\":";
        emit_stage_scalars(std::cout, on.stages);
        std::cout << ",\"stage_types\":";
        emit_stage_types(std::cout, on.stages);
        std::cout << "},\"vjp\":{\"pre2_qg\":";
        emit(std::cout, values(gq));
        std::cout << ",\"pre2_brs\":";
        emit(std::cout, values(gb));
        std::cout << ",\"final_nc16\":";
        emit(std::cout, values(gnc));
        std::cout << ",\"final_nccn16\":";
        emit(std::cout, values(gnccn));
        std::cout << "},\"directions\":{";
        for (std::size_t di = 0; di < directions.size(); ++di) {
            if (di) std::cout << ',';
            const auto& dir = directions[di];
            auto v = torch::zeros_like(x);
            if (dir.index >= 0) v.reshape({STATE*K})[dir.index] = dir.seed;
            else {
                v.reshape({STATE*K})[QG17] = in.state[QG17];
                v.reshape({STATE*K})[BRS17] = in.state[BRS17];
            }
            const auto jv = values(double_reverse_jvp(on.selected, x, v));
            const auto stage_jv = values(double_reverse_jvp(stage_output, x, v));
            const auto final_jv = values(double_reverse_jvp(final_output, x, v));
            std::cout << '"' << dir.name << "\":{\"seed_qg17\":" << std::setprecision(17)
                      << (dir.index == BRS17 ? 0.0 : in.state[QG17])
                      << ",\"seed_brs17\":" << (dir.index == QG17 ? 0.0 : in.state[BRS17])
                      << ",\"jvp\":";
            emit(std::cout, jv);
            std::cout << ",\"stage_jvp\":";
            emit(std::cout, stage_jv);
            std::cout << ",\"final_jvp\":";
            emit(std::cout, final_jv);
            std::cout << ",\"finite_differences\":{";
            const auto steps = std::vector<double>{1.0e-3, 1.0e-4, 1.0e-5, 1.0e-6};
            for (std::size_t hi = 0; hi < steps.size(); ++hi) {
                if (hi) std::cout << ',';
                const double h = steps[hi];
                auto up = in.state, lo = in.state;
                if (dir.index == QG17 || dir.index < 0) {
                    up[QG17] = in.state[QG17] * (1.0 + h);
                    lo[QG17] = in.state[QG17] * (1.0 - h);
                }
                if (dir.index == BRS17 || dir.index < 0) {
                    up[BRS17] = in.state[BRS17] * (1.0 + h);
                    lo[BRS17] = in.state[BRS17] * (1.0 - h);
                }
                auto high = map(torch::from_blob(up.data(), {STATE,K}, F64).clone(), true);
                auto low = map(torch::from_blob(lo.data(), {STATE,K}, F64).clone(), true);
                std::cout << '"' << std::setprecision(8) << h << "\":{\"high_input\":["
                          << std::setprecision(17) << up[QG17] << ',' << up[BRS17] << "],\"low_input\":["
                          << lo[QG17] << ',' << lo[BRS17] << "],\"high\":";
                emit(std::cout, values(high.selected));
                std::cout << ",\"low\":";
                emit(std::cout, values(low.selected));
                std::cout << ",\"high_stages\":";
                emit_stage_scalars(std::cout, high.stages);
                std::cout << ",\"low_stages\":";
                emit_stage_scalars(std::cout, low.stages);
                std::cout << ",\"high_final_raw\":";
                emit_words(std::cout, values(high.final));
                std::cout << ",\"low_final_raw\":";
                emit_words(std::cout, values(low.final));
                std::cout << '}';
            }
            std::cout << "}}";
        }
        std::cout << "},\"thermal_vjp\":{\"schema\":\"kdm6.native_d1_thermal_stage_vjp.v1\",\"selected_k_index0\":15,\"state_order\":[\"th\",\"qv\",\"qc\",\"qr\",\"qi\",\"qs\",\"qg\",\"nccn\",\"nc\",\"ni\",\"nr\",\"bg\"],\"rows\":{";
        for (std::size_t i = 0; i < thermal_vjp_names.size(); ++i) {
            if (i) std::cout << ',';
            std::cout << '\"' << thermal_vjp_names[i] << "\":{\"values\":";
            emit(std::cout, thermal_vjp_rows[i]);
            std::cout << ",\"raw_hex\":";
            emit_words(std::cout, thermal_vjp_rows[i]);
            std::cout << '}';
        }
        std::cout << "}},\"thermal_directions\":{\"schema\":\"kdm6.native_d1_thermal_directions.v1\",\"input\":{\"th16\":"
                  << std::setprecision(17) << in.state[TH16]
                  << ",\"qv16\":" << in.state[QV16]
                  << ",\"pii16\":" << in.forcing[PII16]
                  << ",\"physical_t16\":" << in.state[TH16] * in.forcing[PII16]
                  << ",\"th16_raw\":\"" << word(in.state[TH16])
                  << "\",\"qv16_raw\":\"" << word(in.state[QV16]) << "\"},\"baseline_d1_branch\":";
        emit_thermal_endpoint(std::cout, on.stages, on.stages,
                              in.state[TH16], in.state[QV16], in.forcing[PII16]);
        std::cout << ",\"directions\":{";
        const auto gnc_values = values(gnc);
        const auto gnccn_values = values(gnccn);
        for (std::size_t ti = 0; ti < thermal_directions.size(); ++ti) {
            if (ti) std::cout << ',';
            const auto& dir = thermal_directions[ti];
            auto v = torch::zeros_like(x);
            if (dir.th16) v.reshape({STATE*K})[TH16] = 1.0;
            if (dir.qv16) v.reshape({STATE*K})[QV16] = in.state[QV16];
            const auto input_direction = values(v);
            const auto selected_jv = values(double_reverse_jvp(on.selected, x, v));
            const auto stage_jv = values(double_reverse_jvp(stage_output, x, v));
            const auto final_selected_jv = values(double_reverse_jvp(final_output, x, v));
            const auto final_state_jv = values(double_reverse_jvp(on.final, x, v));
            std::cout << '\"' << dir.name << "\":{\"normalization\":\"" << dir.normalization
                      << "\",\"packed_indices\":{\"th16\":" << TH16 << ",\"qv16\":" << QV16
                      << "},\"seed\":{\"th16\":" << (dir.th16 ? 1.0 : 0.0)
                      << ",\"qv16\":" << (dir.qv16 ? in.state[QV16] : 0.0)
                      << "},\"jvp\":{\"selected_pre2_qg_brs\":";
            emit(std::cout, selected_jv);
            std::cout << ",\"stage_jvp\":";
            emit(std::cout, stage_jv);
            std::cout << ",\"final_nc_nccn\":";
            emit(std::cout, final_selected_jv);
            std::cout << ",\"final_state\":";
            emit(std::cout, final_state_jv);
            std::cout << ",\"final_state_raw\":";
            emit_words(std::cout, final_state_jv);
            std::cout << "},\"vjp_dot_checks\":{";
            for (std::size_t ri = 0; ri < thermal_vjp_names.size(); ++ri) {
                if (ri) std::cout << ',';
                const auto it = std::find(numeric_stage_names.begin(), numeric_stage_names.end(),
                                          thermal_vjp_names[ri]);
                need(it != numeric_stage_names.end(), "missing thermal VJP stage in JVP order");
                const auto index = static_cast<std::size_t>(it - numeric_stage_names.begin());
                const double dot = dot_values(thermal_vjp_rows[ri], input_direction);
                const double jvp = stage_jv[index];
                std::cout << '\"' << thermal_vjp_names[ri] << "\":{\"stage_jvp\":" << std::setprecision(17) << jvp
                          << ",\"vjp_dot\":" << dot << ",\"dot_minus_jvp\":" << dot - jvp << '}';
            }
            const double nc_dot = dot_values(gnc_values, input_direction);
            const double nccn_dot = dot_values(gnccn_values, input_direction);
            std::cout << ",\"final_nc16\":{\"jvp\":" << final_selected_jv[0]
                      << ",\"vjp_dot\":" << nc_dot << ",\"dot_minus_jvp\":" << nc_dot - final_selected_jv[0] << '}';
            std::cout << ",\"final_nccn16\":{\"jvp\":" << final_selected_jv[1]
                      << ",\"vjp_dot\":" << nccn_dot << ",\"dot_minus_jvp\":" << nccn_dot - final_selected_jv[1] << "}},\"finite_differences\":{";
            for (std::size_t hi = 0; hi < dir.steps.size(); ++hi) {
                if (hi) std::cout << ',';
                const double h = dir.steps[hi];
                auto up = in.state, lo = in.state;
                if (dir.th16) {
                    up[TH16] = in.state[TH16] + h;
                    lo[TH16] = in.state[TH16] - h;
                }
                if (dir.qv16) {
                    up[QV16] = in.state[QV16] * (1.0 + h);
                    lo[QV16] = in.state[QV16] * (1.0 - h);
                }
                auto high = map(torch::from_blob(up.data(), {STATE,K}, F64).clone(), true);
                auto low = map(torch::from_blob(lo.data(), {STATE,K}, F64).clone(), true);
                std::ostringstream hkey;
                hkey << std::setprecision(8) << h;
                std::cout << '\"' << hkey.str() << "\":{\"h\":" << std::setprecision(17) << h
                          << ",\"high_branch\":";
                emit_thermal_endpoint(std::cout, high.stages, on.stages,
                                      up[TH16], up[QV16], in.forcing[PII16]);
                std::cout << ",\"low_branch\":";
                emit_thermal_endpoint(std::cout, low.stages, on.stages,
                                      lo[TH16], lo[QV16], in.forcing[PII16]);
                std::cout << ",\"high_input\":{\"th16\":" << up[TH16]
                          << ",\"qv16\":" << up[QV16]
                          << ",\"physical_t16\":" << up[TH16] * in.forcing[PII16]
                          << ",\"th16_raw\":\"" << word(up[TH16])
                          << "\",\"qv16_raw\":\"" << word(up[QV16]) << "\"}"
                          << ",\"low_input\":{\"th16\":" << lo[TH16]
                          << ",\"qv16\":" << lo[QV16]
                          << ",\"physical_t16\":" << lo[TH16] * in.forcing[PII16]
                          << ",\"th16_raw\":\"" << word(lo[TH16])
                          << "\",\"qv16_raw\":\"" << word(lo[QV16]) << "\"},\"high_selected_pre2\":";
                emit(std::cout, values(high.selected));
                std::cout << ",\"low_selected_pre2\":";
                emit(std::cout, values(low.selected));
                std::cout << ",\"high_stages\":";
                emit_stage_scalars(std::cout, high.stages);
                std::cout << ",\"low_stages\":";
                emit_stage_scalars(std::cout, low.stages);
                std::cout << ",\"high_final_raw\":";
                emit_words(std::cout, values(high.final));
                std::cout << ",\"low_final_raw\":";
                emit_words(std::cout, values(low.final));
                std::cout << '}';
            }
            std::cout << "}}";
        }
        std::cout << "}}}\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "NATIVE_PRE2_INPUT_CPP_AD_FAILED: " << e.what() << '\n';
        return 1;
    }
}
