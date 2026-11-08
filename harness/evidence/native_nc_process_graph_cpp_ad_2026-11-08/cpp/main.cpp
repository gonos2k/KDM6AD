// Full captured f64 kdm6_fn path with a live, test-only pre2 QG/BRS hook.
#include "kdm6/runtime.h"
#include <torch/torch.h>
#include <torch/csrc/autograd/autograd.h>
#include <array>
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
        const auto directions = std::vector<Direction>{
            {"qg17_relative", QG17, in.state[QG17]},
            {"brs17_relative", BRS17, in.state[BRS17]},
            {"joint17_relative", -1, 0.0},
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
        std::cout << "}}\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "NATIVE_PRE2_INPUT_CPP_AD_FAILED: " << e.what() << '\n';
        return 1;
    }
}
